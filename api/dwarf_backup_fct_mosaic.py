from pathlib import Path
import shutil
import zipfile
import os
import re
import json
import numpy as np
import cv2
import astroalign as aa
import asyncio
import math
import tempfile

from enum import Enum

from scipy.ndimage import distance_transform_edt, binary_dilation

from nicegui import ui, run, Client

from api.dwarf_backup_fct import safe_print, print_log, win_long_path, files_are_different, _err_path, safe_copy2

from api.dwarf_backup_fct_mosaic_algo import ( infer_mosaic_info_from_images, subsample_for_alignment, crop_to_active_region, equalize_background, detect_panel_position)

TRANSFORM_AUTO_SAVE_PATH = Path("work") / "transforms.npy"

# =========================================================
# UI GUARD HELPERS
# =========================================================

def safe_progress(progress_bar, value: float) -> None:
    """Update progress bar only if the client is still connected."""
    try:
        if progress_bar is not None:
            progress_bar.value = int(round(value))
    except Exception:
        pass

# =========================================================
# IMAGE PROCESSING
# =========================================================

def normalize_to_uint16(data: np.ndarray) -> np.ndarray:
    """
    Normalize any numpy array to uint16 [0, 65535].
    Handles negative values, NaN, inf (typical of calibrated FITS).
    Uses percentiles 0.1/99.9 to ignore outliers.
    """
    data = data.astype(np.float64)
    # replace NaN / inf BEFORE anything else
    data = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)
    finite = data[np.isfinite(data)]
    if finite.size == 0:
        return np.zeros(data.shape, dtype=np.uint16)
    vmin = np.percentile(finite, 0.1)
    vmax = np.percentile(finite, 99.9)
    if vmax <= vmin:
        return np.zeros(data.shape, dtype=np.uint16)
    data = np.clip(data, vmin, vmax)
    data = (data - vmin) / (vmax - vmin) * 65535
    # Final safety (prevents any floating-point drift)
    data = np.clip(data, 0, 1)
    return data.astype(np.uint16)


def load_image(path: str) -> np.ndarray | None:
    """
    Load an image from PNG/JPG/TIFF (8 or 16 bit) or FITS.
    Always returns a BGR uint16 or uint8 array, or None on failure.

    PNG 16-bit : loaded directly via IMREAD_UNCHANGED -> uint16 BGR
    FITS       : loaded via astropy, normalized to uint16, converted to BGR
                 (single channel -> BGR by duplicating channels)
    """
    safe = win_long_path(path)
    ext = path.lower().rsplit(".", 1)[-1]

    if ext in ("fit", "fits", "fts"):
        if not HAS_ASTROPY:
            print_log(f"  ERROR : astropy is required to read FITS files (pip install astropy)")
            return None
        try:
            with astropy_fits.open(safe) as hdul:
                # Take the first HDU with 2D or 3D data
                data = None
                for hdu in hdul:
                    if hdu.data is not None and hdu.data.ndim >= 2:
                        data = hdu.data
                        break
                if data is None:
                    print_log(f"  ERROR : no image data in {path}")
                    return None

                # FITS can be (H,W), (1,H,W), (3,H,W), (H,W,3)
                if data.ndim == 3:
                    if data.shape[0] in (1, 3):   # (C, H, W)
                        data = np.moveaxis(data, 0, -1)  # -> (H, W, C)
                    if data.shape[2] == 1:
                        data = data[:, :, 0]
                    elif data.shape[2] == 3:
                        # RGB -> BGR for OpenCV
                        data = data[:, :, ::-1]

                if data.ndim == 2:
                    # Grayscale image -> duplicate to BGR
                    norm = normalize_to_uint16(data)
                    return cv2.merge([norm, norm, norm])
                else:
                    #  Normalize channel by channel to preserve relative colors
                    channels = []
                    for c in range(data.shape[2]):
                        channels.append(normalize_to_uint16(data[:, :, c]))
                    return cv2.merge(channels)

        except Exception as e:
            print_log(f"  ERROR reading FITS files '{path}' : {e}")
            return None

    else:
        # PNG, JPG, TIFF: IMREAD_UNCHANGED preserves 16-bit
        img = cv2.imread(safe, cv2.IMREAD_UNCHANGED)
        if img is None:
            return None
        if img.ndim == 2:
            img = cv2.merge([img, img, img])
        elif img.shape[2] == 4:
            img = img[:, :, :3]
        return img


def save_image(path: str, img: np.ndarray) -> bool:
    full_path = win_long_path(path)
    success = False

    if path.lower().endswith((".jpg", ".jpeg")):
        if img.dtype == np.uint16:
            # normalize to 0–255
            img_8 = cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX)
            img_8 = img_8.astype(np.uint8)
        else:
            img_8 = img

        success =  cv2.imwrite(full_path, img_8)

    else:
        success =  cv2.imwrite(full_path, img)

    if not success:
        print_log(f"❌ Failed to save image: {full_path}")

    return success
    

def to_gray(img_float64: np.ndarray) -> np.ndarray:
    """
    Convert a float64 BGR image to uint16 grayscale for astroalign.
    Works for both 8-bit (~255 max) and 16-bit (~65535 max) images.
    """
    img16 = np.clip(img_float64, 0, 65535).astype(np.uint16)
    return cv2.cvtColor(img16, cv2.COLOR_BGR2GRAY)

def bright_mask(img_gray: np.ndarray, percentile: float = None) -> np.ndarray:
    """
    Returns an image containing only the brightest pixels (stars).

    Percentile is automatically adapted based on image dynamic range:
      - 8-bit  (max ~255)   : percentile 95  -> keeps ~5% of pixels
      - 16-bit (max ~65535) : percentile 99  -> background is denser,
        threshold must be higher to isolate stars from sky background
    """
    if percentile is None:
        max_val = img_gray.max()
        percentile = 99.0 if max_val > 300 else 95.0

    thresh = np.percentile(img_gray, percentile)
    return np.where(img_gray >= thresh, img_gray, 0)

# =========================================================
# BLACK BORDER CROP
# =========================================================

def crop_black_borders(image, tolerance=5):
    """
    Removes black borders by finding the largest rectangle
    inside the valid area (largest rectangle in histogram algorithm).

    tolerance: threshold for black detection

    Morphological rules:
      - MORPH_CLOSE 3x3 x1: fills 1–2 pixel holes
        without extending the mask beyond real edges.
      - No dilate: would expand mask outside valid area -> blocks crop.
      - No erode: eats feathered edges -> over-crop.

    Optimizations:
      - 2D histogram computed in pure NumPy via vertical cumsum with reset
      - Rows processed in decreasing max order for aggressive early exit
      - ~8x faster than original Python double loop version
    """
    try:
        if image.ndim == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        mask = (gray > tolerance).astype(np.uint8)
        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)

        h, w = mask.shape
        cumsum = mask.astype(np.int32).cumsum(axis=0)
        reset = np.zeros((h, w), dtype=np.int32)
        reset[0] = np.where(mask[0] == 0, cumsum[0], 0)
        for y in range(1, h):
            reset[y] = np.where(mask[y] == 0, cumsum[y], reset[y - 1])
        hist = cumsum - reset

        row_max = hist.max(axis=1)
        order = np.argsort(row_max)[::-1]
        best_area = 0
        best = (0, 0, w, h)

        for y in order:
            if int(row_max[y]) * w <= best_area:
                break
            row = hist[y].tolist()
            stack = []
            for x, val in enumerate(row):
                start = x
                while stack and stack[-1][1] > val:
                    sx, sh = stack.pop()
                    area = (x - sx) * sh
                    if area > best_area:
                        best_area = area
                        best = (sx, int(y) - sh + 1, x - sx, sh)
                    start = sx
                stack.append((start, val))
            for sx, sh in stack:
                area = (w - sx) * sh
                if area > best_area:
                    best_area = area
                    best = (sx, int(y) - sh + 1, w - sx, sh)

        if best_area == 0:
            return image
        x, y, rw, rh = best
        return image[y:y + rh, x:x + rw]

    except Exception as e:
        print_log(f"  Crop error: {e}")
        return image


# =========================================================
# MASKING REGION OF INTEREST WITH JSON INFO
# =========================================================

class StitchMode(Enum):
    STACK   = "stack"    # Case 1 & 3: same FOV, align & combine
    MOSAIC  = "mosaic"   # Case 2: multi-panel panorama with grid info

def get_mosaic_panels(mosaic_dir: str, img_type: str = "jpg") -> list[tuple[str, str]]:
    """Return list of (panel_name, image full path) for a mosaic directory.
    
    img_type: "jpg" for stacked.jpg, "png" for stacked-16*.png, , "fits" for stacked-16*.fits
    """
    panels = []
    try:
        for subdir in sorted(os.listdir(mosaic_dir)):
            panel_path = os.path.join(mosaic_dir, subdir)
            if not os.path.isdir(panel_path):
                continue

            if img_type == "png":
                # Find stacked-16xxxxx.png
                candidates = [
                    f for f in os.listdir(panel_path)
                    if f.startswith("stacked-16") and f.endswith(".png")
                ]
                if not candidates:
                    continue
                img_file = os.path.join(panel_path, sorted(candidates)[-1])  # take latest if multiple
            elif img_type == "fits":
                # Find stacked-16xxxxx.fits
                candidates = [
                    f for f in os.listdir(panel_path)
                    if f.startswith("stacked-16") and f.endswith(".fits")
                ]
                if not candidates:
                    continue
                img_file = os.path.join(panel_path, sorted(candidates)[-1])  # take latest if multiple
            elif img_type == "jpg-new":
                img_file = os.path.join(panel_path, "stacked.jpg")
                if not os.path.isfile(img_file):
                    continue
            else:
                img_file = os.path.join(panel_path, "stacked.jpg")
                if not os.path.isfile(img_file):
                    continue

            panels.append((subdir, img_file))

    except FileNotFoundError as e:
        print_log(f"Mosaic Directory not found: {e}")
    except Exception as e:
        print_log(f"Unexpected error: {e}")

    return panels


def load_mosaic_info(image_path: str) -> dict | None:
    """
    Given an image path like:
      MOSAIC_DIR/Panel_1/stacked-16xxx.png
    Find and parse shotsInfo.json from MOSAIC_DIR/
    """
    try:
        mosaic_dir = Path(image_path).parent.parent  # up 2 levels
        json_path = mosaic_dir / "shotsInfo.json"
        print_log(json_path)
        
        if not json_path.exists():
            print_log(f"  ⚠️ shotsInfo.json not found in {mosaic_dir}")
            return None
        
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            print_log(f"mosaicInfo: {data.get("mosaicInfo", None)}")

        mosaic_info = data.get("mosaicInfo", None)
        print_log(f"mosaicInfo: {mosaic_info}")

        # ── Rebuild if missing ─────────────────────────────────────────
        if mosaic_info is None:
            print_log(f"  ℹ️ mosaicInfo missing → attempting rebuild from images")
            mosaic_info = rebuild_mosaic_info(str(mosaic_dir))

        return mosaic_info
    
    except Exception as e:
        print_log(f"  ⚠️ Failed to load mosaic info: {e}")
        return None


def rebuild_mosaic_info(mosaic_dir: str) -> dict | None:
    """
    Reconstruct mosaicInfo from image sizes and directory structure
    when shotsInfo.json exists but has no mosaicInfo.

    Infers:
    - viewCols, viewRows from mosaic/panel size ratio
    - viewScaleX, viewScaleY from mosaic/panel size ratio
    - subviewInfo from sorted panel subdirectories
    - path prefix from existing subview paths or device detection

    Device path prefixes:
      DWARF 3    : /DWARF3/Astronomy/
      DWARF Mini : /DWARF_mini/Astronomy/
      DWARF 2    : /DWARF_II/Astronomy/   (to verify)
    """
    try:
        mosaic_dir = Path(mosaic_dir)
        json_path  = mosaic_dir / "shotsInfo.json"

        if not json_path.exists():
            print_log(f"  ⚠️ No shotsInfo.json in {mosaic_dir}")
            return None

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if data.get("mosaicInfo"):
            print_log(f"  ℹ️ mosaicInfo already present — skipping rebuild")
            return data["mosaicInfo"]

        # ── Read mosaic + panel sizes ──────────────────────────────────
        root_jpg = mosaic_dir / "stacked.jpg"
        if not root_jpg.exists():
            print_log(f"  ⚠️ No root stacked.jpg")
            return None

        mosaic_img = cv2.imread(str(root_jpg))
        if mosaic_img is None:
            return None
        mosaic_h, mosaic_w = mosaic_img.shape[:2]

        # Find panel subdirs (sorted = DWARF column-major order)
        panel_dirs = sorted([
            d for d in mosaic_dir.iterdir()
            if d.is_dir() and re.search(r'\(\d+\)', d.name)
        ])

        if not panel_dirs:
            print_log(f"  ⚠️ No panel subdirs found")
            return None

        # Get panel size from first panel
        panel_jpg = panel_dirs[0] / "stacked.jpg"
        if not panel_jpg.exists():
            print_log(f"  ⚠️ No stacked.jpg in first panel")
            return None

        panel_img = cv2.imread(str(panel_jpg))
        if panel_img is None:
            return None
        panel_h, panel_w = panel_img.shape[:2]

        # ── Derive grid ────────────────────────────────────────────────
        scale_x = math.floor((10 * mosaic_w / panel_w) + 0.5) /10
        scale_y = math.floor((10 * mosaic_h / panel_h) + 0.5) /10

        cols = max(1, math.ceil(scale_x))
        rows = max(1, math.ceil(scale_y))

        print_log(f"  Rebuilt: mosaic={mosaic_w}x{mosaic_h} "
              f"panel={panel_w}x{panel_h} "
              f"scale=({scale_x:.2f},{scale_y:.2f}) "
              f"grid={cols}x{rows}")

        # ── Detect device path prefix ──────────────────────────────────
        device_prefix = detect_dwarf_device(mosaic_dir, data)

        # ── Build subviewInfo — DWARF column-major order ───────────────
        # (1)=TL, (2)=BL, (3)=BR, (4)=TR → col-major: col0 top→bot, col1 top→bot
        grid_coords = [(r, c) for c in range(cols) for r in range(rows)]

        subview_info = []
        for i, panel_dir in enumerate(panel_dirs):
            panel_id = get_panel_id_from_path(str(panel_dir / "stacked.jpg"))
            if panel_id is None:
                panel_id = i + 1
            coord = grid_coords[i] if i < len(grid_coords) else (0, 0)
            subview_info.append({
                "coord": [coord[1], coord[0]],  # store as [col, row]
                "id":    panel_id,
                "path":  f"{device_prefix}/Astronomy/{mosaic_dir.name}/{panel_dir.name}/"
            })

        mosaic_info = {
            "currentSubviewId": 1,
            "subviewInfo":       subview_info,
            "subviewShotsToTake": data.get("shotsToTake", data.get("shotsToStack", 0)),
            "viewCols":  cols,
            "viewRows":  rows,
            "viewScaleX": f"{scale_x:.2f}",
            "viewScaleY": f"{scale_y:.2f}",
        }

        # ── Inject and save back to JSON ───────────────────────────────
        data["mosaicInfo"] = mosaic_info
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print_log(f"  ✅ mosaicInfo rebuilt and saved → {json_path}")

        return mosaic_info

    except Exception as e:
        print_log(f"  ⚠️ rebuild_mosaic_info failed: {e}")
        return None


def detect_dwarf_device(image_path: str, json_data: dict | None = None) -> str:
    """
    DWARF 3    : 3856x2180 (bin1), ~1928x1090 (bin2)
    DWARF 2    : 3840x2160 (bin1),  1920x1080 (bin2)
    DWARF Mini : 1920x1080 (bin1 only)
    
    Ambiguity: D2 bin2 and DMini both → 1920x1080
               → resolved by binning field in JSON
    """
    try:
        img = cv2.imread(win_long_path(image_path))
        if img is None:
            return "DWARF3"
        h, w = img.shape[:2]

        binning = "1*1"
        if json_data:
            binning = json_data.get("binning", "1*1")

        print_log(f"  Device detect: {w}x{h} bin={binning}")

        # ── DWARF 3 bin1 ───────────────────────────────────────────────
        if w == 3856 and h == 2180:
            return "DWARF3"

        # ── DWARF 3 bin2 ───────────────────────────────────────────────
        if w == 1928 and h == 1090:
            return "DWARF3"

        # ── DWARF 2 bin1 ───────────────────────────────────────────────
        if w == 3840 and h == 2160:
            return "DWARF2"

        # ── Ambiguous 1920x1080 — D2 bin2 or DWARF Mini ───────────────
        if w == 1920 and h == 1080:
            if binning == "2*2":
                return "DWARF2"   # bin2 → must be D2
            if binning == "1*1":
                return "DWARF_MINI"  # bin1 at 1080p → Mini
            # No binning info → check directory hint
            path_str = str(Path(image_path).parent).upper()
            if "MINI" in path_str:
                return "DWARF_MINI"
            return "DWARF2"  # conservative default

        print_log(f"  ⚠️ Unknown resolution {w}x{h} — defaulting to DWARF3")
        return "DWARF3"

    except Exception as e:
        print_log(f"  ⚠️ detect_dwarf_device failed: {e}")
        return "DWARF3"

def detect_stitch_mode(image_paths: list[str]) -> StitchMode:
    """
    Detect stitch mode from image paths:
    - No shotsInfo.json found     → STACK (same FOV, different sessions)
    - shotsInfo.json but 1 panel  → STACK (single panel, multiple sessions)
    - shotsInfo.json with grid    → MOSAIC
    """
    mosaic_info = load_mosaic_info(win_long_path(image_paths[0]))
    
    if mosaic_info is None:
        print_log(f"  📐 No mosaicInfo found → check panels dirs")
        mosaic_dir = Path(win_long_path(image_paths[0])).parent.parent
        print_log(f"mosaic_dir: {mosaic_dir}")
        n_panels = get_mosaic_panels(mosaic_dir)
        if len(n_panels) > 1:
            print_log(f"  📐 {n_panels}-panel mosaicInfo found → MOSAIC mode")
            return StitchMode.MOSAIC

        return StitchMode.STACK

    n_panels = len(mosaic_info.get("subviewInfo", []))
    
    if n_panels <= 1:
        print_log(f"  📐 Single panel mosaicInfo → STACK mode")
        return StitchMode.STACK

    print_log(f"  📐 {n_panels}-panel mosaicInfo found → MOSAIC mode")
    return StitchMode.MOSAIC

# not used
def parse_mosaic_info(mosaic_info: dict) -> dict:
    """Extract grid layout and overlap from mosaicInfo JSON."""
    scale_x = float(mosaic_info["viewScaleX"])
    scale_y = float(mosaic_info["viewScaleY"])
    cols    = int(mosaic_info["viewCols"])
    rows    = int(mosaic_info["viewRows"])

    overlap_x = max(0.0, min(1.0 - (scale_x / cols), 0.90))
    overlap_y = max(0.0, min(1.0 - (scale_y / rows), 0.90))

    grid = {}
    for sv in mosaic_info["subviewInfo"]:
        col, row = sv["coord"]           # JSON is [col, row]
        grid[(row, col)] = sv["id"]      # store as (row, col)

    return {
        "overlap_x": overlap_x,
        "overlap_y": overlap_y,
        "rows": rows,
        "cols": cols,
        "grid": grid,
    }

def get_panel_id_from_path(image_path: str) -> int | None:
    """
    Extract panel id from subdir name.
    e.g. DWARF_RAW_TELE_Unknown(1)_EXP_45... -> 1
    """
    subdir = Path(image_path).parent.name
    match = re.search(r'\((\d+)\)', subdir)
    if match:
        return int(match.group(1))
    print_log(f"  ⚠️ Could not extract panel id from: {subdir}")
    return None


def get_coords_for_images(image_paths: list[str], mosaic_info: dict) -> list[tuple]:
    """
    Return list of (row, col) coords matching the order of image_paths.
    """
    # Build id -> coord from JSON
    id_to_coord = {
        sv["id"]: (sv["coord"][1], sv["coord"][0])  # [col, row] → (row, col)
        for sv in mosaic_info["subviewInfo"]
    }
    
    coords = []
    for path in image_paths:
        panel_id = get_panel_id_from_path(path)
        if panel_id and panel_id in id_to_coord:
            coord = id_to_coord[panel_id]
            print_log(f"  Panel {panel_id} -> coord {coord} ({Path(path).parent.name})")
            coords.append(coord)
        else:
            print_log(f"  ⚠️ Panel id {panel_id} not found in mosaicInfo, using None")
            coords.append(None)
    
    return coords

def get_alignment_order(coords: list) -> list[tuple[tuple, tuple | None]]:
    n = len(coords)

    if n == 2:
        return [((0, 1), None)]  # ← fix: wrap in tuple

    if n == 4:
        coord_to_idx = {c: i for i, c in enumerate(coords)}
        chain_with_fallbacks = [
            (((0,0),(0,1)), ((1,0),(1,1))),
            (((0,0),(1,0)), ((0,1),(1,1))),
            (((1,0),(1,1)), ((0,0),(0,1))),
        ]
        result = []
        for (rc, sc), (rf, sf) in chain_with_fallbacks:
            if rc in coord_to_idx and sc in coord_to_idx:
                primary  = (coord_to_idx[rc], coord_to_idx[sc])
                fallback = (coord_to_idx[rf], coord_to_idx[sf]) \
                           if rf in coord_to_idx and sf in coord_to_idx else None
                result.append((primary, fallback))
        return result

    # fallback
    ref_idx = coords.index((0, 0)) if (0, 0) in coords else 0
    return [((ref_idx, i), None) for i in range(n) if i != ref_idx]
    

def get_alignment_order_old(coords: list) -> list[tuple[int, int]]:
    """
    Return list of (ref_idx, src_idx) pairs for sequential alignment.
    Each panel aligns to its nearest already-placed neighbor.
    
    4-panel snake: 1(0,0) → 2(1,0) → 4(0,1) → 3(1,1)
    """
    n = len(coords)
    
    if n == 2:
        return [(0, 1)]  # simple pair
    
    if n == 4:
        # Map coord -> index
        coord_to_idx = {c: i for i, c in enumerate(coords)}
        
        # Define alignment chain based on adjacency
        # 1→2 (vertical), 1→4 (horizontal), 2→3 (horizontal) or 4→3 (vertical)
        chain = [
            ((0,0), (1,0)),  # panel1 → panel2 (below)
            ((0,0), (0,1)),  # panel1 → panel4 (right)
            ((1,0), (1,1)),  # panel2 → panel3 (right)
        ]
        
        result = []
        for ref_coord, src_coord in chain:
            if ref_coord in coord_to_idx and src_coord in coord_to_idx:
                result.append((coord_to_idx[ref_coord], coord_to_idx[src_coord]))
        return result

    return [(0, i) for i in range(1, n)]  # fallback: all vs ref

def assign_coords_from_content(image_paths: list[str]) -> dict[str, tuple[int, int]]:
    """
    Assign grid coords by analyzing star distribution on panel edges.
    Works for 2x2 grids without JSON.
    """
    coord_map = {}
    for path in image_paths:
        img = cv2.imread(win_long_path(path), cv2.IMREAD_UNCHANGED)
        if img is None:
            coord_map[path] = (0, 0)
            continue
        gray = bright_mask(to_gray(img))
        coord = detect_panel_position(gray)
        print_log(f"  Auto-coord {Path(path).parent.name} → {coord}")
        coord_map[path] = coord

    # Sanity check — warn if duplicate coords detected
    coords = list(coord_map.values())
    if len(set(coords)) < len(coords):
        print_log(f"  ⚠️ Duplicate coords detected: {coords} — content detection may be unreliable")

    return coord_map
    
# No Mosaic Info 
def get_mosaic_overlap_params_fallback(
    image_paths: list[str],
    overlap: float = 0.30,
) -> tuple[float, float, dict[str, tuple[int, int]]]:

    # ── Case 2: Fallback — try to infer from image sizes ──────────────────────
    mosaic_dir = Path(image_paths[0]).parent.parent
    inferred = infer_mosaic_info_from_images(str(mosaic_dir))

    fallback_coords_V1 = {
        1: [(0, 0)],
        2: [(0, 0), (1, 0)],
        4: [(0, 0), (1, 0), (1, 1), (0, 1)],
    }

    fallback_coords_V2 = {
        1: [(0, 0)],
        2: [(0, 0), (0, 1)],
        4: [(0, 0), (1, 0), (1, 1), (0, 1)],
    }

    if inferred:
        overlap_x = inferred["overlap_x"]
        overlap_y = inferred["overlap_y"]
        cols = inferred["cols"]
        row = inferred["rows"]

        n = len(image_paths)
        if n not in fallback_coords_V1:
            #Detect coords from image content — don't trust directory sort order
            coord_map = assign_coords_from_content(image_paths)
            print_log(f"  ⚠️ No mosaicInfo — content-detected coords: "
                f"{[(Path(p).parent.name, c) for p, c in coord_map.items()]}")
        else:
            if (cols == "2" or rows == "1") and n == 2:
                coord_map = {path: fallback_coords_V2[n][i] for i, path in enumerate(image_paths)}
            else :
                coord_map = {path: fallback_coords_V1[n][i] for i, path in enumerate(image_paths)}


    else:
        # Last resort hardcoded fallback
        overlap_x = overlap_y = 0.50
        n = len(image_paths)
        if n not in fallback_coords_V1:
            raise ValueError(f"Unsupported panel count: {n}")
        coord_map = {path: fallback_coords_V1[n][i] for i, path in enumerate(image_paths)}

    print_log(f"  ⚠️ No mosaicInfo — inferred coords: {list(coord_map.values())} "
          f"overlap=({overlap_x:.3f},{overlap_y:.3f})")

    return overlap_x, overlap_y, coord_map
    

def get_mosaic_overlap_params(
    image_paths: list[str],
    mosaic_info: dict | None = None,
    overlap: float = 0.30,
    align_pad=0.20    
) -> tuple[float, float, dict[str, tuple[int, int]]]:

    # ── Case 1: JSON available ─────────────────────────────────────────────────
    if mosaic_info:
        scale_x = float(mosaic_info["viewScaleX"])
        scale_y = float(mosaic_info["viewScaleY"])
        cols    = int(mosaic_info["viewCols"])
        rows    = int(mosaic_info["viewRows"])

        # Geometric overlap from JSON
        geo_overlap_x = max(0.0, 1.0 - (scale_x / cols))
        geo_overlap_y = max(0.0, 1.0 - (scale_y / rows))

        # Padded overlap for alignment — ensures enough stars in the mask zone
        overlap_x = min(geo_overlap_x + align_pad, 0.50)
        overlap_y = min(geo_overlap_y + align_pad, 0.50)

        print_log(f"  scale=({scale_x},{scale_y}) grid={cols}x{rows} "
              f"→ geo=({geo_overlap_x:.3f},{geo_overlap_y:.3f}) "
              f"align=({overlap_x:.3f},{overlap_y:.3f})")
          
        # Build panel_id -> (row, col) — JSON coord is [col, row]
        id_to_coord = {
            sv["id"]: (sv["coord"][1], sv["coord"][0])  # (row, col)
            for sv in mosaic_info["subviewInfo"]
        }

        coord_map = {}
        for path in image_paths:
            panel_id = get_panel_id_from_path(path)
            if panel_id is None or panel_id not in id_to_coord:
                raise ValueError(f"Could not match panel id {panel_id} to mosaicInfo: {path}")
            coord_map[path] = id_to_coord[panel_id]
            print_log(f"  Panel {panel_id} → coord {coord_map[path]}")

        return overlap_x, overlap_y, coord_map

    return get_mosaic_overlap_params_fallback(image_paths, overlap)

def make_overlap_masks(shape: tuple, ref_coord: tuple, src_coord: tuple,
                       overlap_x: float, overlap_y: float) -> tuple:
    """
    Generate (ref_mask, src_mask) based on relative position of two panels.
    coord = (row, col)
    """
    h, w = shape
    ref_mask = np.zeros((h, w), dtype=bool)
    src_mask = np.zeros((h, w), dtype=bool)

    ref_row, ref_col = ref_coord
    src_row, src_col = src_coord

    # Horizontal relationship (left-right)
    if src_col > ref_col:
        # src is to the RIGHT of ref
        overlap_px = int(w * overlap_x)
        ref_mask[:, w - overlap_px:] = True   # ref: keep right edge
        src_mask[:, :overlap_px]     = True   # src: keep left edge

    elif src_col < ref_col:
        # src is to the LEFT of ref
        overlap_px = int(w * overlap_x)
        ref_mask[:, :overlap_px]     = True   # ref: keep left edge
        src_mask[:, w - overlap_px:] = True   # src: keep right edge

    # Vertical relationship (up-down)
    if src_row > ref_row:
        # src is BELOW ref
        overlap_px = int(h * overlap_y)
        ref_mask[h - overlap_px:, :] = True   # ref: keep bottom edge
        src_mask[:overlap_px, :]     = True   # src: keep top edge

    elif src_row < ref_row:
        # src is ABOVE ref
        overlap_px = int(h * overlap_y)
        ref_mask[:overlap_px, :]     = True   # ref: keep top edge
        src_mask[h - overlap_px:, :] = True   # src: keep bottom edge

    return ref_mask, src_mask


def apply_overlap_mask(gray: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """
    Zero out non-overlap regions so astroalign only sees stars in the overlap zone.
    """
    masked = gray.copy()
    masked[~mask] = 0
    return masked

#def prepare_for_alignment(img: np.ndarray, max_size: int = 2048,  asinh_stretch: bool = False) -> np.ndarray:
def prepare_for_alignment(img: np.ndarray,
                           max_size: int = 2048,
                           asinh_stretch: bool = False,
                           asinh_factor: float = 10,
                           bg_blur_ksize: int = 101) -> np.ndarray:
   
    """
    Prepare image for astroalign — returns uint8 color (H,W,3) RGB.
    Astroalign uses mean of channels internally.
    """
    # 1. Handle 16-bit → 8-bit
    if img.dtype == np.uint16:
        img8 = (img / 256).astype(np.uint8)
    elif img.dtype in (np.float64, np.float32):
        img8 = (img / img.max() * 255).astype(np.uint8)
    else:
        img8 = img.copy()

    # 2. Convert BGR → RGB (astroalign/pillow expects RGB)
    if img8.ndim == 3:
        img8 = cv2.cvtColor(img8, cv2.COLOR_BGR2RGB)

    # 3. Downsample if too large
    h, w = img8.shape[:2]
    if max(h, w) > max_size:
        scale = max_size / max(h, w)
        new_w = int(w * scale)
        new_h = int(h * scale)
        img8 = cv2.resize(img8, (new_w, new_h), interpolation=cv2.INTER_AREA)
        print_log(f"  Downsampled for alignment: {w}x{h} → {new_w}x{new_h}")
    

    # 4. Asinh stretch per channel
    if asinh_stretch:
        img_f = img8.astype(np.float64) / 255.0
#        stretched = np.arcsinh(img_f * 10) / np.arcsinh(10)
        stretched = np.arcsinh(img_f * asinh_factor) / np.arcsinh(asinh_factor)
        img8 = (stretched * 255).astype(np.uint8)

    # 5. Background subtraction on mean channel
    gray = np.mean(img8, axis=2).astype(np.uint8)
#    blurred = cv2.GaussianBlur(gray, (101, 101), 0)
    blurred = cv2.GaussianBlur(gray, (bg_blur_ksize, bg_blur_ksize), 0)
    bg = cv2.subtract(gray, blurred)
    bg_norm = cv2.normalize(bg, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)


    # Apply background correction to all channels
    correction = bg_norm.astype(np.float32) / (gray.astype(np.float32) + 1e-6)
    correction = np.clip(correction, 0, 1)
    img8 = (img8.astype(np.float32) * correction[..., None]).astype(np.uint8)

    print_log(f"  end of prepare_for_alignment")

    # Final guarantee: (H, W, 3) uint8 contiguous
    # return np.ascontiguousarray(img8, dtype=np.uint8)

    # ── Collapse to 2D grayscale for astroalign ──────────────────
    #result = np.mean(img8, axis=2).astype(np.float32)  # ← float32 instead of uint8
    #return np.ascontiguousarray(result, dtype=np.float32)

    # ── Collapse to 2D grayscale for astroalign ──────────────────
    result = np.mean(img8, axis=2).astype(np.uint8)
    return np.ascontiguousarray(result, dtype=np.uint8)   # shape (H, W)    

 
def get_coarse_translation(coord: tuple, panel_w: int, panel_h: int,
                            overlap_x: float, overlap_y: float) -> tuple[int, int]:
    """
    Compute expected (tx, ty) translation for a panel based on grid position.
    coord = (row, col)
    """
    row, col = coord
    step_x = int(panel_w * (1.0 - overlap_x))  # e.g. 3856 * 0.90 = 3470
    step_y = int(panel_h * (1.0 - overlap_y))  # e.g. 2180 * 0.90 = 1962
    tx = col * step_x
    ty = row * step_y
    return tx, ty

# =========================================================
# STACKING
# =========================================================

# =========================================================
# STACK SAME PANEL FIXED SIZE SET BY FIST PANEL
# =========================================================

#async def stack_same_panel_aligned(images: list, feather_size: int = 51, main_log = None, log=None) -> tuple:
async def stack_same_panel_aligned(images: list, 
                                    detection_sigma: int = 2,
                                    max_control_points: int = 100,
                                    max_size: int = 2048,
                                    asinh_factor: float = 10,
                                    bg_blur_ksize: int = 101,
                                    main_log = None, log=None) -> tuple:
    """
    Align all images to ref frame then stack keeping ref dimensions.
    """
    src_dtype = images[0].dtype
    max_val   = 65535.0 if src_dtype == np.uint16 else 255.0
    ref = images[0]
    h, w = ref.shape[:2]

    transforms = [np.eye(3)]
    failed = []

    for idx, img in enumerate(images[1:], start=1):

        transf = None
        for use_stretch in [False, True]:
            ref_gray = await run.io_bound(prepare_for_alignment,
                                           ref,
                                           max_size=max_size,
                                           asinh_stretch = use_stretch,
                                           asinh_factor=asinh_factor,
                                           bg_blur_ksize=bg_blur_ksize)
            src_gray = await run.io_bound(prepare_for_alignment,
                                           img,
                                           max_size=max_size,
                                           asinh_stretch = use_stretch,
                                           asinh_factor=asinh_factor,
                                           bg_blur_ksize=bg_blur_ksize)
            
            print_log(f"Trying alignment {'with' if use_stretch else 'without'} stretch...")
            
            try:
                print_log(f"  Trying find Transform ", log)

                transf = await run.cpu_bound(_find_transform_sync, src_gray, ref_gray, detection_sigma=detection_sigma, max_control_points = max_control_points)

                if transf is not None:
                    print_log(f"✅ Found transform {'with' if use_stretch else 'without'} stretch")
                    break
                else:
                    print_log(f"❌ Failed {'with' if use_stretch else 'without'} stretch, trying next...")
            except Exception :
                print_log(f"❌ Failed {'with' if use_stretch else 'without'} stretch, trying next...")
 

        if transf is None:
            # Fallback: try with bright_mask instead of prepare_for_alignment
            try:
                print_log(f"  Fallback: try with bright_mask instead", log)
                ref_bm = bright_mask(to_gray(ref))
                src_bm = bright_mask(to_gray(img))
                print_log(f"  Trying find Transform ", log)
                transf = await run.cpu_bound(_find_transform_sync, src_bm, ref_bm, detection_sigma=detection_sigma, max_control_points = max_control_points/2)
                if transf is not None:
                    print_log(f"  Panel {idx+1} aligned to ref ✓ (bright_mask fallback)", log)
                else:
                    print_log(f"  Panel {idx+1} alignment failed (fallback) - using identity)", log)
            except Exception as e:
                print_log(f"  Panel {idx+1} alignment failed ({e}) (fallback) — using identity", log)
                failed.append(idx + 1)

        transforms.append(transf.params if transf else np.eye(3))

    # Stack in ref frame
    print_log(f"  Stack in ref frame ", log)

    result = ref.astype(np.float64).copy()
    weight = np.ones((h, w), dtype=np.float64)

    # Collect all warped images into a cube
    warped_stack = [ref.astype(np.float64)]

    for img, M_full in zip(images[1:], transforms[1:]):
        M = np.linalg.inv(M_full)[:2]
        #M = M_full[:2].copy()
        placed = cv2.warpAffine(img.astype(np.float64), M, (w, h),
                                flags=cv2.INTER_LINEAR,
                                borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        covered = placed.sum(axis=2) > 0
        # Add to weighted sum only where src has data
        result[covered] += placed[covered]
        weight[covered] += 1.0
        warped_stack.append(placed)

    cube  = np.stack(warped_stack, axis=0)   # ← build cube first
    valid = cube.sum(axis=3) > 0             # ← then compute valid mask
    n     = cube.shape[0]                    # ← then n

    # =========================================================
    # COMPUTE BRIGHTNESS PER IMAGE (valid pixels only)
    # =========================================================
    brightness = []
    for i in range(n):
        valid_pixels = cube[i][valid[i]]
        mean_b = valid_pixels.mean() if valid_pixels.size > 0 else 0.0
        brightness.append(mean_b)
        print_log(f"  Image {i+1} brightness: {mean_b:.1f}")

    brightness = np.array(brightness)  # ← must be np.array before argmax

    base_idx  = int(np.argmax(brightness))
    other_idx = 1 - base_idx
    print_log(f"  base=Image {base_idx+1} (mean={brightness[base_idx]:.1f})")

    result = cube[base_idx].copy()
    missing = ~valid[base_idx]
    result[missing] = cube[other_idx][missing]

    result_norm = np.clip(result / max_val, 0, 1)
    return (result_norm * max_val).astype(src_dtype), failed

def stack_images(images_f: list, transforms: list, 
                 canvas_shape: tuple, base_x: int, base_y: int,
                 method: str = "sigma_clip", label: str = "", log=None) -> np.ndarray:
    """
    Stack aligned images using mean or sigma-clipped mean.
    Better SNR than single frame: noise reduces by √N.
    """
    
    # =========================================================
    # DETECT INPUT DTYPE
    # =========================================================
    src_dtype = images_f[0].dtype
    max_val   = 65535.0 if src_dtype == np.uint16 else 255.0
    print_log(f"  {label}Input dtype: {src_dtype} max_val: {max_val}")

    h, w = canvas_shape
    # Collect all warped images into a cube
    warped_stack = []
    
    for idx, (img, M_full) in enumerate(zip(images_f, transforms)):
        # Convert to float64 internally for math precision
        img_f = img.astype(np.float64)
        M = M_full[:2].copy()
        M[0, 2] += base_x
        M[1, 2] += base_y
        warped = cv2.warpAffine(img_f, M, (w, h),
                                flags=cv2.INTER_LINEAR,
                                borderValue=0)
        warped_stack.append(warped)
        print_log(f"  Warped image {idx+1}/{len(images_f)}")

    # =========================================================
    # CHOOSE METHOD
    # =========================================================
    cube  = np.stack(warped_stack, axis=0)   # ← build cube first
    valid = cube.sum(axis=3) > 0             # ← then compute valid mask
    n     = cube.shape[0]                    # ← then n

    # =========================================================
    # COMPUTE BRIGHTNESS PER IMAGE (valid pixels only)
    # =========================================================
    brightness = []
    for i in range(n):
        valid_pixels = cube[i][valid[i]]
        mean_b = valid_pixels.mean() if valid_pixels.size > 0 else 0.0
        brightness.append(mean_b)
        print_log(f"  Image {i+1} brightness: {mean_b:.1f}")

    brightness = np.array(brightness)  # ← must be np.array before argmax

    # For N=2, use mean without sigma-clip
    n = len(images_f)
    if n == 2:
        print_log(f"  Only 2 images — using brightness (no sigma-clip)")

        base_idx  = int(np.argmax(brightness))
        other_idx = 1 - base_idx
        print_log(f"  N=2: base=Image {base_idx+1} (mean={brightness[base_idx]:.1f})")

        result = cube[base_idx].copy()
        missing = ~valid[base_idx]
        result[missing] = cube[other_idx][missing]

    elif method == "mean":
        count  = np.sum(valid, axis=0).clip(min=1)
        result = np.sum(cube * valid[..., None], axis=0) / count[..., None]

    elif method == "median":
        result = np.median(cube, axis=0)

    elif method == "sigma_clip":
        result = sigma_clip_stack(cube, sigma=2.5, log=log)

    # STACK return:
    result_norm = np.clip(result / max_val, 0, 1)
    return (result_norm * max_val).astype(src_dtype), label
    
def sigma_clip_stack(cube: np.ndarray, sigma: float = 2.5, log=None) -> np.ndarray:
    """
    Sigma-clipped mean stack — removes outliers (satellites, cosmic rays, hot pixels).
    cube shape: (N, H, W, C)
    """
    mean = np.mean(cube, axis=0)
    std  = np.std(cube, axis=0)

    # Mask outliers per pixel
    low  = mean - sigma * std
    high = mean + sigma * std

    # Clip and recompute mean without outliers
    mask = (cube >= low[np.newaxis]) & (cube <= high[np.newaxis])  # (N, H, W, C)
    
    # Weighted sum avoiding zero-division
    count  = np.sum(mask, axis=0).clip(min=1)
    result = np.sum(cube * mask, axis=0) / count

    clipped = np.sum(~mask)
    print_log(f"  Sigma-clip: {clipped} pixels rejected (σ={sigma})")

    return result

# ─────────────────────────────────────────────
# FITS PART 1 — Save transforms (stitch_with_astroalign)
# ─────────────────────────────────────────────
#import sep
def _find_transform_sync(src_gray, ref_gray, detection_sigma = 5, max_control_points = 50, min_area=10):
    """Pure blocking CPU work — called via run.cpu_bound"""

    #sep.set_extract_pixstack(500000)      # default 300000 → increase for dense fields
    #sep.set_sub_object_limit(1024)        # default 1024 → increase for nebula deblending

    for max_pts in [max_control_points, max_control_points//2, max_control_points//3]:
        try:
            print_log(f"  Trying find_transform max_pts={max_pts}")
            transf, _ = aa.find_transform(src_gray, ref_gray, detection_sigma = detection_sigma,
                                           max_control_points=max_pts, min_area= min_area)
            print_log(f"  ✅ Found transform max_pts={max_pts}")
            return transf
        except Exception as e:
            print_log(f"  ↻ max_pts={max_pts} failed: {e}")
    return None
    
def save_transforms(transforms: list, path: str = TRANSFORM_AUTO_SAVE_PATH):
    """
    Save a list of 3×3 numpy arrays to a .npy file.
 
    Usage — add this right after your transform loop:
        save_transforms(transforms, TRANSFORM_AUTO_SAVE_PATH)
    """
    arr = np.stack(transforms, axis=0)   # shape (N, 3, 3)

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    np.save(path, arr)
    print_log(f"  ✅ Transforms saved → {path}  (shape {arr.shape})")

def load_transforms(path: str = TRANSFORM_AUTO_SAVE_PATH) -> list:
    """Load transforms saved by save_transforms()."""
    arr = np.load(path)                  # shape (N, 3, 3)
    transforms = [arr[i] for i in range(arr.shape[0])]
    print_log(f"  ✅ Transforms loaded ← {path}  ({len(transforms)} matrices)")
    return transforms

# =========================================================
# STITCH ASTRO ALIGN with MASK For Mosaic Mode
# =========================================================


async def stitch_with_astroalign(images: list,
                            mode: StitchMode = StitchMode.MOSAIC,
                            stack_method: str = "sigma_clip",
                            coords: list = None,
                            overlap_x: float = None,
                            overlap_y: float = None,
                            label: str = "",
                            feather_size: int = 51,
                            detection_sigma: int = 2,
                            max_control_points: int = 100,
                            max_size: int = 2048,
                            asinh_factor: float = 10,
                            bg_blur_ksize: int = 101,
                            main_log=None,
                            log=None) -> tuple:

    print_log(f"  Stitching: number of images: {len(images)}", main_log)
    print_log(f"  Mode used: {mode}", log)
    src_dtype = images[0].dtype
    max_val   = 65535.0 if src_dtype == np.uint16 else 255.0
    print_log(f"  {label}Input dtype: {src_dtype} max_val: {max_val}")

    failed   = []
    images_f = images
    ref      = images_f[0]
    h, w, _  = ref.shape
    ref_panel_idx = 0

    # ── Reference panel = TL (0,0), fallback to index 0 ──────────────────────
    if coords:
        ref_panel_idx = coords.index((0, 0)) if (0, 0) in coords else 0
    else:
        ref_panel_idx = 0

    alignment_pairs = get_alignment_order(coords) if coords else \
                      [((0, i), None) for i in range(1, len(images_f))]

    print_log(f"  alignment_pairs: {alignment_pairs}")
    transforms = [None] * len(images_f)
    transforms[ref_panel_idx] = np.eye(3)

    all_failed = []
    for primary_pair, fallback_pair in alignment_pairs:
        transf = None
        used_ref_idx, used_src_idx = primary_pair

        # STACK mode doesn't use fallback pairs
        pairs_to_try = [primary_pair] if mode == StitchMode.STACK \
                       else ([primary_pair] + ([fallback_pair] if fallback_pair else []))

        for attempt_pair in pairs_to_try:
            if transf is not None:
                break
            a_ref_idx, a_src_idx = attempt_pair

            # =========================================================
            # STACK MODE
            # =========================================================
            if mode == StitchMode.STACK:

                ref_gray = prepare_for_alignment(images_f[a_ref_idx],
                                                  max_size=max_size,
                                                  asinh_factor=asinh_factor,
                                                  bg_blur_ksize=bg_blur_ksize)
                src_gray = prepare_for_alignment(images_f[a_src_idx],
                                                  max_size=max_size,
                                                  asinh_factor=asinh_factor,
                                                  bg_blur_ksize=bg_blur_ksize)
  
                #print_log(f"  ref_gray: shape={ref_gray.shape} dtype={ref_gray.dtype} "
                #      f"contiguous={ref_gray.flags['C_CONTIGUOUS']} "
                #      f"min={ref_gray.min()} max={ref_gray.max()}")
                #print_log(f"  src_gray: shape={src_gray.shape} dtype={src_gray.dtype} "
                #      f"contiguous={src_gray.flags['C_CONTIGUOUS']} "
                #      f"min={src_gray.min()} max={src_gray.max()}")

                try:
                    transf = await run.cpu_bound(_find_transform_sync, src_gray, ref_gray,
                                                  detection_sigma=detection_sigma,
                                                  max_control_points=max_control_points)
                    if transf is not None:
                        used_ref_idx, used_src_idx = a_ref_idx, a_src_idx
                        print_log(f"  Image {a_src_idx+1} aligned to Image {a_ref_idx+1} ✓", log)
                    else:
                        print_log(f"  Panel {a_src_idx+1} alignment failed to Image {a_ref_idx+1}", log)
                except Exception as e:
                    print_log(f"  Image {a_src_idx+1} alignment failed ({e})", log)
                    # don't append to all_failed here — handled after loop

            # =========================================================
            # MOSAIC MODE
            # =========================================================
            else:
                ref_gray = bright_mask(to_gray(images_f[a_ref_idx]))
                src_gray = bright_mask(to_gray(images_f[a_src_idx]))

                if coords and overlap_x and overlap_y:
                    ref_mask, src_mask = make_overlap_masks(
                        src_gray.shape,
                        ref_coord=coords[a_ref_idx],
                        src_coord=coords[a_src_idx],
                        overlap_x=overlap_x,
                        overlap_y=overlap_y,
                    )
                    ref_gray = apply_overlap_mask(ref_gray, ref_mask)
                    src_gray = apply_overlap_mask(src_gray, src_mask)
                    print_log(f"  Overlap mask applied: ref={ref_mask.sum()} src={src_mask.sum()} active pixels")

                    debug_dir = Path("./debug_masks")
                    debug_dir.mkdir(exist_ok=True)
                    cv2.imwrite(str(debug_dir / f"ref_{a_ref_idx}_src_{a_src_idx}_ref.png"),
                                (ref_gray / ref_gray.max() * 255).astype(np.uint8) if ref_gray.max() > 0 else ref_gray)
                    cv2.imwrite(str(debug_dir / f"ref_{a_ref_idx}_src_{a_src_idx}_src.png"),
                                (src_gray / src_gray.max() * 255).astype(np.uint8) if src_gray.max() > 0 else src_gray)
                    print_log(f"  💾 Debug masks saved → {debug_dir}")

                # ── Adaptive retry loop ────────────────────────────────
                # NOTE: do NOT reset transf=None here — it's set by outer loop
                attempts = [
                    (False, detection_sigma,     max_control_points, False),
                    (False, detection_sigma+1,   max_control_points//2, False),
                    (False, detection_sigma+2,   max_control_points, True),
                    (True,  detection_sigma+1,   max_control_points//2, False),
                ]
                last_do_crop = False
                for do_crop, atmp_sigma, max_pts, do_subsample in attempts:
                    try:
                        if do_crop:
                            ref_sub = subsample_for_alignment(crop_to_active_region(ref_gray)) \
                                      if do_subsample else crop_to_active_region(ref_gray)
                            src_sub = subsample_for_alignment(crop_to_active_region(src_gray)) \
                                      if do_subsample else crop_to_active_region(src_gray)
                        else:
                            ref_sub = subsample_for_alignment(ref_gray) if do_subsample else ref_gray
                            src_sub = subsample_for_alignment(src_gray) if do_subsample else src_gray

                        transf = await run.cpu_bound(_find_transform_sync, src_sub, ref_sub,
                                                      detection_sigma=atmp_sigma,
                                                      max_control_points=max_pts,
                                                      min_area=10)
                        if transf is not None:
                            last_do_crop = do_crop
                            print_log(f"  ✓ [{a_ref_idx+1}→{a_src_idx+1}] sigma={atmp_sigma} "
                                  f"max_pts={max_pts} crop={do_crop} subsample={do_subsample}", log)
                            break  # ← exits attempts loop, transf is set
                        else:
                            print_log(f"  ↻ [{a_ref_idx+1}→{a_src_idx+1}] sigma={atmp_sigma} "
                                  f"crop={do_crop} failed", log)
                    except Exception as e:
                        print_log(f"  ↻ [{a_ref_idx+1}→{a_src_idx+1}] sigma={atmp_sigma} "
                              f"crop={do_crop} failed: {e}", log)

                # transf is either set (success) or None (all attempts failed)
                # outer 'for attempt_pair' loop checks 'if transf is not None: break'

        # ── After all attempt_pairs for this primary_pair ─────────────
        if transf is None:
            print_log(f"  Panel {primary_pair[1]+1} alignment failed (all attempts)", log)
            transforms[primary_pair[1]] = transforms[ref_panel_idx].copy()
            all_failed.append(primary_pair[1] + 1)
        else:
            if mode == StitchMode.STACK:
                transforms[used_src_idx] = transf.params
            elif not last_do_crop:
                if used_ref_idx == ref_panel_idx:
                    transforms[used_src_idx] = transf.params
                else:
                    transforms[used_src_idx] = transforms[used_ref_idx] @ transf.params
            else:
                coarse_tx, coarse_ty = get_coarse_translation(
                    coords[used_src_idx], w, h, overlap_x, overlap_y
                )
                fine   = transf.params.copy()
                coarse = np.array([[1, 0, coarse_tx],
                                   [0, 1, coarse_ty],
                                   [0, 0, 1        ]], dtype=np.float64)
                if used_ref_idx == ref_panel_idx:
                    transforms[used_src_idx] = coarse @ fine
                else:
                    transforms[used_src_idx] = transforms[used_ref_idx] @ coarse @ fine

            print_log(f"  Panel {used_src_idx+1} aligned to Panel {used_ref_idx+1} ✓", log)
            
    # ── STACK fallback if all pairs failed ────────────────────────────────────
    if len(all_failed) == len(alignment_pairs) and mode == StitchMode.MOSAIC:
        print_log("  ⚠️ All MOSAIC alignments failed → falling back to STACK mode", log)
        return await stitch_with_astroalign(images, StitchMode.STACK,
                                       stack_method, None, None, None, label,
                                       feather_size, detection_sigma, max_control_points, max_size, asinh_factor, bg_blur_ksize,
                                       main_log, log)

    failed = all_failed
    # =========================================================
    # SAFETY — fill any missing transforms
    # =========================================================
    for i in range(len(transforms)):
        if transforms[i] is None:
            print_log(f"  Transform {i+1} is None — using identity")
            transforms[i] = np.eye(3)
            if i not in failed:
                failed.append(i + 1)

    save_transforms(transforms, TRANSFORM_AUTO_SAVE_PATH)

    # =========================================================
    # COMPUTE CANVAS SIZE (ROTATION SAFE)
    # =========================================================
    all_corners = []

    corners = np.array([
        [0, 0, 1],
        [w, 0, 1],
        [0, h, 1],
        [w, h, 1]
    ]).T  # shape (3,4)

    for M in transforms:
        warped = M @ corners
        all_corners.append(warped[:2])

    all_corners = np.hstack(all_corners)

    min_x = int(np.floor(np.min(all_corners[0])))
    max_x = int(np.ceil(np.max(all_corners[0])))
    min_y = int(np.floor(np.min(all_corners[1])))
    max_y = int(np.ceil(np.max(all_corners[1])))

    canvas_w = max_x - min_x
    canvas_h = max_y - min_y

    base_x = -min_x
    base_y = -min_y

    print_log(f"  {label}Canvas : {canvas_w}x{canvas_h}",log)

    # =========================================================
    # MODE SPLIT
    # =========================================================
    if mode == StitchMode.STACK:
        print_log(f"  {label}Stack Image",log)
        result, _ = stack_images(images_f, transforms,
                                      (canvas_h, canvas_w),
                                      base_x, base_y,
                                      method=stack_method,
                                      label=label,
                                      log=log)
        return result, all_failed  # stack_images already returns correct dtype
        
    # =========================================================
    # INIT CANVAS
    # =========================================================
    print_log(f"  {label}Blending Panels - Pass 1",log)

    for i, M in enumerate(transforms):
        if M is None:
            print_log(f"  ⚠️ Transform {i} still None before blending — using identity", log)
            transforms[i] = np.eye(3)

    # --- Blending — also heavy, offload ---
    print_log(f"  {label}Blending and Final Pass",log)

    result = await run.cpu_bound(
        _blend_panels_sync, images, transforms, feather_size, max_val, base_x, base_y, canvas_w, canvas_h
    )

    print_log(f"  result min={result.min():.1f} max={result.max():.1f} max_val={max_val}",log)
    if len(failed) > 0:
        print_log(f"  ⚠️ Stitching done: Some Panel can not be aligned, use original one instead", main_log)
    else:
        print_log(f"  ✓ Stitching done: All Panels have been aligned", main_log)

    return result.astype(src_dtype), failed

def _blend_panels_sync(images_f, transforms, feather_size, max_val, base_x, base_y, canvas_w, canvas_h):
    # All your Pass 1 / Pass 2 blending code here
    # No NiceGUI, no log element — plain print_log() only
    # =========================================================
    # BLENDING
    # =========================================================
    # =========================================================
    # PASS 1 : collect all masks
    # =========================================================
    masks = []
    placements = []

    for idx, (img, M_full) in enumerate(zip(images_f, transforms)):
        M = M_full[:2].copy()
        M[0, 2] += base_x
        M[1, 2] += base_y

        placed = cv2.warpAffine(img, M, (canvas_w, canvas_h),
                                flags=cv2.INTER_LINEAR,
                                borderMode=cv2.BORDER_CONSTANT, borderValue=0)

        mask = (placed.sum(axis=2) > 0).astype(np.float64)
        masks.append(mask)
        placements.append((placed, M))

    # Total coverage: how many images cover each pixel
    total_coverage = np.sum(masks, axis=0)  # shape (canvas_h, canvas_w)

    # =========================================================
    # PASS 2 : blend with distance-to-edge feather
    # =========================================================
    print_log(f"  Blending Panels - Pass 2")

    canvas  = np.zeros((canvas_h, canvas_w, 3), dtype=np.float64)

    feathers = []
    for idx, ((placed, M), mask) in enumerate(zip(placements, masks)):
        # Distance from each pixel to the edge of this panel's mask
        # → naturally 0 at border, max at center
        dist = distance_transform_edt(mask)

        # Normalize to [0, 1] and apply feather falloff
        if feather_size > 0:
            feather = np.clip(dist / feather_size, 0.0, 1.0)
        else:
            feather = mask.copy()

        feathers.append(feather)

    print_log(f"  Final Pass")

    # Global weight sum — guaranteed no gaps at intersections
    total_weight = np.sum(feathers, axis=0)
    total_weight_safe = np.maximum(total_weight, 1e-6)

    for idx, ((placed, M), feather) in enumerate(zip(placements, feathers)):
        # Normalize each panel's contribution by total weight at each pixel
        w = feather / total_weight_safe
        canvas += placed * w[..., None]

    result = np.clip(canvas, 0, max_val)

    return result

def create_thumbnail_mosaic(jpg_file_path, mosaic):

    save_image(str(jpg_file_path), cv2.resize(mosaic, (356, 200)))

# =========================================================
# GENERATE PANORAMA
# Returns :
# - OK : True or False (Failed Alignement or error
# - pano_crop : Final Crop Panorama
# - pano : Final Panorama without cropping
#
# 2 Files are generated - 
# output_path - original format
# jpg_path is used for 
#   - jpg format full resolution if thumbnail is False
#   - jpg format thumbnail resolution if thumbnail is True
#
# if alignement error : _err is added to the filename before extension
# =========================================================

async def generate_panorama(image_paths, images, output_path = False, jpg_path = False, thumbnail = False, main_log = None, log = None, stitch_params: dict = None):
    try:
        await asyncio.sleep(0)

        # Unpack params
        from components.stitch_params_editor import STITCH_PARAMS_DEFAULT
        p         = stitch_params or STITCH_PARAMS_DEFAULT
        a         = p["alignment"]
        b         = p["blending"]
        s         = p["stacking"]
        feather_size      = b["feather_size"]
        stack_method      = s["method"]
        detection_sigma   = a["detection_sigma"]
        max_control_points= a["max_control_points"]
        align_pad         = a["align_pad"]
        asinh_factor      = a["asinh_factor"]
        bg_blur_ksize     = a["bg_blur_ksize"]
        max_size          = a["max_size"]

        mode = detect_stitch_mode(image_paths)
        print_log(f"  🔧 Stitch mode: {mode.value}", log)

        status = True

        if mode == StitchMode.STACK:
            # Case 1 & 3 — same FOV, no grid needed
            print_log("Attempt : STACK MODE",log)
            pano, _ = await stitch_with_astroalign(
                images, mode,
                stack_method=stack_method,
                coords = None, overlap_x=None, overlap_y=None,
                label="[stack] ",
                feather_size=feather_size,
                detection_sigma=detection_sigma,
                max_control_points=max_control_points,
                max_size=max_size,
                asinh_factor=asinh_factor,
                bg_blur_ksize=bg_blur_ksize,
                main_log=main_log, log=log
            )

        elif mode == StitchMode.MOSAIC:
            # Case 2 — use mosaicInfo for coords + overlap masks
            mosaic_info = load_mosaic_info(image_paths[0])

            #images = equalize_background(images)  # ← add this
            #save_image("equalize_background",  images[0])

            # Set to None explicitly if you want masking to be optional
            coord_map = None
            overlap_x = overlap_y = 0.0

            if mosaic_info or len(image_paths) in (1, 2, 4):
                overlap_x, overlap_y, coord_map = get_mosaic_overlap_params(image_paths, mosaic_info, align_pad=align_pad)
    
            # Convert coord_map to ordered list matching image_paths
            coords = [coord_map[p] for p in image_paths]
            print_log(f"  coords: {coords}")
            print_log(f"  overlap_x={overlap_x:.3f} overlap_y={overlap_y:.3f}")

            # ── If all panels have the same coord → same FOV → use STACK ──────────
            if len(set(coords)) == 1:
                print_log(f"  📐 Same panel coord {coords[0]} → STACK in ref frame", log)
                pano, failed = await stack_same_panel_aligned( images,
                                                                detection_sigma=detection_sigma,
                                                                max_control_points=max_control_points,
                                                                max_size=max_size,
                                                                asinh_factor=asinh_factor,
                                                                bg_blur_ksize=bg_blur_ksize,
                                                                main_log=main_log, log=log)
            else:
                # ── Normalize panel sizes before mosaic ───────────────────────
                if len(set(img.shape for img in images)) > 1:
                    min_h = min(img.shape[0] for img in images)
                    min_w = min(img.shape[1] for img in images)
                    print_log(f"  ⚠️ Panel size mismatch — cropping all to {min_w}x{min_h}", log)
                    images = [img[:min_h, :min_w] for img in images]

                print_log(f"  coords: {coords}")
                print_log(f"  overlap_x={overlap_x:.3f} overlap_y={overlap_y:.3f}")

                pano, failed = await stitch_with_astroalign(
                    images, mode=mode,
                    stack_method=stack_method,
                    coords=coords,
                    overlap_x=overlap_x, overlap_y=overlap_y,
                    label = "normalize",
                    feather_size=feather_size,
                    detection_sigma=detection_sigma,
                    max_control_points=max_control_points,
                    max_size=max_size,
                    asinh_factor=asinh_factor,
                    bg_blur_ksize=bg_blur_ksize,
                    main_log=main_log, log=log
                )

        if pano is None:
            print_log("⚠️ Panorama failed", main_log)
            return False, None, None

        if failed:
            print_log(f"  ⚠️ {len(failed)} panel(s) used fallback (no alignment): {failed}", main_log)
            status = False
            
        h, w = pano.shape[:2]
        print_log(f"  Size before crop : {w}x{h}", log)
        await run.io_bound(save_image,"pano_no_crop.png", pano)

        pano_crop = await run.io_bound(crop_black_borders, pano)
        h, w = pano_crop.shape[:2]
        print_log( f"  Size after crop : {w}x{h}", log)

        if output_path:
            out = _err_path(output_path) if failed else output_path
        if jpg_path:
            jpg = _err_path(jpg_path)    if failed else jpg_path

        if output_path:
            await run.io_bound(save_image,str(out), pano_crop)
        if jpg_path:
            if thumbnail:
                await run.io_bound(create_thumbnail_mosaic, jpg, pano_crop)
            else:
                await run.io_bound(save_image, str(jpg), pano_crop)

        print_log(" Panorama generated")
        print_log(" ✔️ Panorama generated", main_log)
        return status, pano_crop, pano  # ← return the result

    except Exception as e:
        print_log(f"Panorama error: {e}")
        return False, None, None

# =========================================================
# HELPERS
# =========================================================

def is_valid_fits(f):
    return f.name.endswith(".fits") and not f.name.startswith(("stacked-16", "failed_"))


def get_target_prefix(name):
    return name.split("_")[0]


def rename_file(name, target):
    parts = name.split("_", 1)
    return f"{target}_{parts[1]}" if len(parts) > 1 else name


def rename_failed(name, target):
    base = name.replace("failed_", "")
    return f"failed_{rename_file(base, target)}"


def extract_temp(name):
    m = re.search(r'_(\-?\d+)C\.(fits|fit)$', name, re.IGNORECASE)
    return int(m.group(1)) if m else None

# --------------
# REPAIR ACTION
# --------------

async def repair_mosaic_session(old_session_path: str, new_session_path: str, log, progress_bar, cancel_event, stitch_params: dict = None):
    """Repair a mosaic session by restoring missing FITS/PNG and rebuilding outputs."""
    try:
        old_path = Path(win_long_path(old_session_path))
        new_path = Path(win_long_path(new_session_path))

        if not old_path.exists() or not new_path.exists():
            print_log( "❌ Session path not found", log)
            return None

        safe_progress(progress_bar, 40)
        if cancel_event.is_set():
            print_log("Process Canceled")
            return None

        print_log( "ℹ️ Replacing FITS files...", log)

        old_panels = sorted([d for d in old_path.iterdir() if d.is_dir()])
        new_panels = sorted([d for d in new_path.iterdir() if d.is_dir()])

        if len(old_panels) != len(new_panels):
            print_log( "⚠️ Panel count mismatch", log)

        for panel_index, (old_panel, new_panel) in enumerate(zip(old_panels, new_panels), start=1):

            # Remove non stacked FITS
            print_log( f"ℹ️ Cleaning panel {panel_index}", log)
            for file in new_panel.glob("*.fits"):
                if not file.name.startswith("stacked-16"):
                    file.unlink()

            safe_progress(progress_bar, 40 + 8 *(panel_index/len(old_panels)))
            if cancel_event.is_set():
                break

            # Restore FITS from old session
            print_log( f"ℹ️ Restoring FITS for panel {panel_index}", log)
            for old_file in old_panel.glob("*.fits"):
                if not old_file.name.startswith("stacked-16"):
                    if files_are_different(str(old_file), str(new_panel / old_file.name)):
                        result_copy = await run.io_bound(safe_copy2, str(old_file), str(new_panel / old_file.name))
                        if not result_copy:
                            raise Exception(f"Copy failed without exception: {str(src_file)}")
                    else:
                        safe_print_log(f"Skipping {old_file.name} (unchanged)")

            safe_progress(progress_bar, 48 + 12 *(panel_index/len(old_panels)))
            if cancel_event.is_set():
                break

            # -----------------------------
            # Copy old PNGs and FITS, rebuild ZIP, generate stacked images (Repair only)
            # -----------------------------
            old_pngs = sorted(old_panel.glob("stacked-16*.png"))
            new_pngs = sorted(new_panel.glob("stacked-16*.png"))

            if len(old_pngs) != len(new_pngs):
                print_log( f"⚠️ PNG mismatch: {old_panel.name}", log)

            print_log( f"ℹ️ Replacing PNGs for panel {panel_index}...", log)
            for old_file, new_file in zip(old_pngs, new_pngs):
                if files_are_different(str(old_file), str(new_file)):
                    result_copy = await run.io_bound(safe_copy2, str(old_file), str(new_file))   # replace content, keep name
                    if not result_copy:
                        raise Exception(f"Copy failed without exception: {str(old_file)}")
                else:
                    safe_print_log(f"Skipping {new_file.name} (unchanged)")

            safe_progress(progress_bar, 60 + 4 *(panel_index/len(old_panels)))
            if cancel_event.is_set():
                break

            old_stacked = sorted(old_panel.glob("stacked-16*.fits"))
            new_stacked = sorted(new_panel.glob("stacked-16*.fits"))

            if len(old_stacked) != len(new_stacked):
                print_log( f"⚠️ stacked-16 FITS mismatch: {old_panel.name}", log)

            print_log( f"ℹ️ Copying old stacked-16 FITS files for panel {panel_index}...", log)
            for old_file, new_file in zip(old_stacked, new_stacked):
                if files_are_different(str(old_file), str(new_file)):
                    result_copy = await run.io_bound(safe_copy2, str(old_file), str(new_file))   # replace content, keep name
                    if not result_copy:
                        raise Exception(f"Copy failed without exception: {str(old_file)}")
                else:
                    safe_print_log(f"Skipping {new_file.name} (unchanged)")

            safe_progress(progress_bar, 64 + 4 *(panel_index/len(old_panels)))
            if cancel_event.is_set():
                break

        if cancel_event.is_set():
            print_log("Process Canceled")
            return None

        # ── Post-loop: shotsInfo, ZIP, panorama ───────────────────────────
        print_log( "ℹ️ Copying shotsInfo.json...", log)
        old_info = old_path / "shotsInfo.json"
        new_info = new_path / "shotsInfo.json"
        if old_info.exists():
            if files_are_different(str(old_info), str(new_info), True):
                result_copy = await run.io_bound(safe_copy2, str(old_info), str(new_info))   # replace content, keep name
                if not result_copy:
                    raise Exception(f"Copy failed without exception: {str(old_info)}")
            else:
                safe_print_log(f"Skipping {new_info.name} (unchanged)")

        safe_progress(progress_bar, 75)
        if cancel_event.is_set():
            print_log("Process Canceled")
            return None

        print_log( "ℹ️ Rebuilding ZIP stacked-16_*.zip...", log)
        print_log("ℹ️ Rebuilding ZIP stacked-16_*.zip...")
        zip_files = list(new_path.glob("stacked-16_*.zip"))
        if zip_files:
            zip_path = zip_files[0]
            with zipfile.ZipFile(str(zip_path), 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                for subdir in new_path.iterdir():
                    if subdir.is_dir():
                        for f in sorted(subdir.glob("stacked-16*.fits")):
                            await run.io_bound(zf.write, str(f), arcname=f.name)
            print_log( f"✔️ ZIP {zip_path.name} updated", log)
        else:
            print_log( "⚠️ No ZIP file found, ZIP not updated.", log)

        safe_progress(progress_bar, 80)
        if cancel_event.is_set():
            print_log("Process Canceled")
            return None

        print_log( "ℹ️ Generating stacked.jpg and stacked_thumbnail.jpg...", log)
        print_log("ℹ️ Generating stacked.jpg and stacked_thumbnail.jpg...")
        png_images = []
        png_images_path = []
        for subdir in sorted(new_path.iterdir()):
            if subdir.is_dir():
                for f in sorted(subdir.glob("stacked-16*.png")):
                    img = load_image(str(f))
                    if img is not None:
                        png_images.append(img)
                        png_images_path.append(str(f))

        stacked_path = new_path / "stacked.jpg"
        thumbnail_path = new_path / "stacked_thumbnail.jpg"

        safe_progress(progress_bar, 90)
        if cancel_event.is_set():
            print_log("Process Canceled")
            return None

        final_status= True
        print_log(f"png_images: {len(png_images)}")

        if not png_images:
            print_log( "⚠️ No PNG images for panorama, stacked.jpg not generated.", log)
            return None

        elif len(png_images) == 1:
            save_image(str(stacked_path), png_images[0])
            thumbnail = cv2.resize(png_images[0], (356, 200))
            save_image(str(thumbnail_path), thumbnail)
            print_log( "✔️ stacked.jpg and thumbnail generated from a single image", log)
        else:
            final_status, _,_ = await generate_panorama(png_images_path, png_images, stacked_path, thumbnail_path, True, log, log, stitch_params)

            if final_status : 
                print_log( "✅ Mosaic session repaired successfully!", log)
                print_log("✅ Mosaic session repaired successfully!")
            else : 
                print_log( "✅ Mosaic session repaired with some errors!", log)
                print_log("✅ Mosaic session repaired with some errors!")

        return _err_path(stacked_path) if not final_status else stacked_path

    except Exception as error:
        print_log(f"Repair error: {error}")
        return None


# =========================================================
# MERGE LOGIC (backup helper)
# =========================================================

async def backup_merge_files(work_primary: str) -> dict | None:
    """
    Backup all files that merge_mosaic will overwrite.
    Returns a dict mapping original_path -> backup_path, or None on failure.
    """
    work_path = Path(work_primary)
    backup_dir = Path(tempfile.mkdtemp(prefix="mosaic_backup_"))
    backed_up = {}

    try:
        # Root files
        for name in ["stacked.jpg", "stacked.png", "stacked_thumbnail.jpg"]:
            src = work_path / name
            if src.exists():
                dst = backup_dir / name
                result_copy = await run.io_bound(safe_copy2, str(src), str(dst))
                if not result_copy:
                    raise Exception(f"Copy failed without exception: {str(src)}")
                backed_up[str(src)] = str(dst)

        # Per-panel files
        for panel_dir in sorted(work_path.iterdir()):
            if not panel_dir.is_dir():
                continue
            panel_backup = backup_dir / panel_dir.name
            panel_backup.mkdir(exist_ok=True)

            # stacked.jpg
            jpg = panel_dir / "stacked.jpg"
            if jpg.exists():
                dst = panel_backup / "stacked.jpg"
                result_copy = await run.io_bound(safe_copy2, str(jpg), str(dst))
                if not result_copy:
                    raise Exception(f"Copy failed without exception: {str(jpg)}")
                backed_up[str(jpg)] = str(dst)

            # stacked-16*.png
            for png in panel_dir.glob("stacked-16*.png"):
                dst = panel_backup / png.name
                result_copy = await run.io_bound(safe_copy2, str(png), str(dst))
                if not result_copy:
                    raise Exception(f"Copy failed without exception: {str(png)}")
                backed_up[str(png)] = str(dst)

        print_log(f"  ✅ Backed up {len(backed_up)} files → {backup_dir}")
        return backed_up

    except Exception as e:
        print_log(f"  ⚠️ Backup failed: {e}")
        shutil.rmtree(str(backup_dir), ignore_errors=True)
        return None


async def restore_merge_files(backed_up: dict) -> None:
    """Restore all backed-up files to their original locations."""
    for original, backup in backed_up.items():
        try:
            result_copy = await run.io_bound(safe_copy2, backup, original)
            if not result_copy:
                raise Exception(f"Copy failed without exception: {backup}")
            print_log(f"  ✅ Restored {Path(original).name}")
        except Exception as e:
            print_log(f"  ⚠️ Restore failed for {original}: {e}")


def cleanup_backup(backed_up: dict) -> None:
    """Delete the temp backup directory after accept."""
    if not backed_up:
        return
    # All backups share the same parent temp dir
    backup_dirs = set(str(Path(v).parent) for v in backed_up.values())
    for d in backup_dirs:
        shutil.rmtree(d, ignore_errors=True)
        print_log(f"  🗑️ Backup cleaned up: {d}")

# =========================================================
# MERGE LOGIC (FULL)
# =========================================================

async def merge_mosaic(old_path_str, new_path_str, copy_intermediate_files, log, progress_bar, cancel_event, panel_paths_b=None, stitch_params: dict = None):
    try:
        old_path = Path(win_long_path(old_path_str))
        new_path = Path(win_long_path(new_path_str))
        print_log(f"old_path : {old_path}")
        print_log(f"new_path : {new_path}")

        if not old_path.exists() or not new_path.exists():
            print_log( "❌ Session not found", log)
            return None

        safe_progress(progress_bar, 40)
        if cancel_event.is_set():
            print_log("Process Canceled")
            return None

        new_panels = sorted([d for d in new_path.iterdir() if d.is_dir()])

        if panel_paths_b is not None:
            # Use the reordered/inverted paths provided by the UI
            old_panels = []
            # Debug
            actual_folders = [d.name for d in old_path.iterdir() if d.is_dir()]
            print_log(f"  actual folders in old_path: {actual_folders}")
            
            for p in panel_paths_b:
                panel_name = Path(p).name
                print_log(f"  looking for: '{panel_name}'")
                candidate = old_path / panel_name
                if candidate.exists():
                    old_panels.append(candidate)
                    print_log(f"  ✔️ Panel found: {panel_name}", log)
                else:
                    print_log(f"  ⚠️ Panel not found: {panel_name}", log)
        else:
            old_panels = sorted([d for d in old_path.iterdir() if d.is_dir()])
    
        if len(old_panels) != len(new_panels):
            print_log( "⚠️ Panel count mismatch", log)

        final_files = []

        for i, (old_panel, new_panel) in enumerate(zip(old_panels, new_panels), start=1):
            await asyncio.sleep(0)
            print_log( f"ℹ️ Panel {i}", log)

            if copy_intermediate_files:
                target = None
                for f in new_panel.glob("*.fits"):
                    if is_valid_fits(f):
                        target = get_target_prefix(f.name)
                        break

                if not target:
                    print_log( f"⚠️ No target for panel {i}", log)
                    continue

                # Count files upfront for progress
                panel_files = [f for f in old_panel.glob("*.fits")
                               if not f.name.startswith("stacked-16")]
                total_files = len(panel_files)
                done_files = 0
                print_log(f"Copying {total_files} session files...", log)

                for f in old_panel.glob("*.fits"):
                    if f.name.startswith("stacked-16"):
                        continue

                    if f.name.startswith("failed_"):
                        new_name = rename_failed(f.name, target)
                    else:
                        new_name = rename_file(f.name, target)

                    dst = new_panel / new_name

                    if files_are_different(f, dst):
                        result_copy = await run.io_bound(safe_copy2, str(f), str(dst))
                        if not result_copy:
                            raise Exception(f"Copy failed without exception: {str(f)}")
                    else:
                        safe_print_log(f"Skipping {new_name} (unchanged)")

                    final_files.append(dst.name)
                    done_files += 1
                    if total_files > 0:
                        # Panel copy is steps 40→60, each panel gets equal share
                        panel_share = 20 / len(old_panels)
                        base = 40 + (i - 1) * panel_share
                        safe_progress(progress_bar, int(round(base + panel_share * (done_files / total_files))))
                    if cancel_event.is_set():
                        break
            else:
                print_log( f"ℹ️ skipping copy Fits files for panel {i}", log)

            safe_progress(progress_bar, 40 + 20 *(i/len(old_panels)))
            if cancel_event.is_set():
                break

        if cancel_event.is_set():
            print_log("Process Canceled")
            return None

        # JSON merge
        print_log( "ℹ️ merging JSON...", log)

        new_json = new_path / "shotsInfo.json"
        old_json = old_path / "shotsInfo.json"

        if new_json.exists() and old_json.exists():
            with open(str(new_json)) as f:
                new_info = json.load(f)
            with open(str(old_json)) as f:
                old_info = json.load(f)

            for key in ["shotsStacked", "shotsTaken", "shotsToTake"]:
                new_info[key] += old_info.get(key, 0)

            # Merge min/max temps from both sessions' JSON
            new_min = new_info.get("minTemp")
            old_min = old_info.get("minTemp")
            new_max = new_info.get("maxTemp")
            old_max = old_info.get("maxTemp")

            all_mins = [t for t in [new_min, old_min] if t is not None]
            all_maxs = [t for t in [new_max, old_max] if t is not None]

            if all_mins:
                new_info["minTemp"] = min(all_mins)
            if all_maxs:
                new_info["maxTemp"] = max(all_maxs)
    
            with open(str(new_json), "w") as f:
                json.dump(new_info, f, indent=2)

        safe_progress(progress_bar, 65)
        if cancel_event.is_set():
            print_log("Process Canceled")
            return None

        # Build panel images
        print_log( "ℹ️ Building new panel images...", log)
        panel_images = []
        panel_image_paths = []
        status = True

        for i, (old_panel, new_panel) in enumerate(zip(old_panels, new_panels), start=1):

            # --- Find files (only one expected) ---
            old_file = next(old_panel.glob("stacked-16*.png"), None)
            new_file = next(new_panel.glob("stacked-16*.png"), None)

            print_log(f"old file stacked-16*.png: {old_file}", log)
            print_log(f"new file stacked-16*.png: {new_file}", log)

            # convert to str immediately
            old_file = str(old_file) if old_file else None
            new_file = str(new_file) if new_file else None

            # fallbacks
            if new_file is None:
                fits_file = next(new_panel.glob("stacked-16*.fits"), None)
                if fits_file is not None:
                    new_file = str(fits_file.with_suffix(".png"))

            if new_file is None and old_file is not None:
                new_file = str(new_panel / Path(old_file).name)

            # now all loads are safe
            old_img = load_image(old_file) if old_file else None
            new_img = load_image(new_file) if new_file else None

            # --- Build pano ---
            if old_img is not None and new_img is not None:
                print_log( f"Panel {i}: stitching old + new → {Path(new_file).name}", log)

                jpg_path = Path(new_file).parent / "stacked.jpg"
                status, pano_crop , pano = await generate_panorama([new_file, old_file], [new_img, old_img], Path(new_file), jpg_path, False, log, log, stitch_params)

                if not status:
                    pano = new_img
                    print_log( f"Panorama failed for Panel {i}: using new only → {Path(new_file).name}", log)

            elif new_img is not None:
                print_log( f"Panel {i}: using new only → {Path(new_file).name}", log)
                pano = new_img

            elif old_img is not None:
               print_log( f"Panel {i}: using old only → {Path(old_file).name}", log)
               pano = old_img

            else:
                print_log( f"⚠️ Panel {i}: no images found", log)
                continue

            # --- Save ---
            if pano is not None and new_file is not None:
                panel_images.append(pano)
                panel_image_paths.append(new_file)

            safe_progress(progress_bar, 65 + 20 *(i/len(old_panels)))
            if cancel_event.is_set():
                break

        if cancel_event.is_set():
            print_log("Process Canceled")
            return None

        stacked = new_path / "stacked.png"
        thumb = new_path / "stacked_thumbnail.jpg"

        if panel_images:
            print_log( "ℹ️ Building panorama...", log)
            final_status, _,_ = await generate_panorama(panel_image_paths, panel_images, stacked, thumb, True, log, log, stitch_params)
            if not final_status:
                print_log( f"Final Panorama failed returned old stacked file", log)

        print_log( "✅ Merge completed", log)
        return stacked

    except Exception as e:
        print_log(f"Merge error: {e}")
        return None

async def reset_panel_images(primary_path_str, new_path_str, log, progress_bar, cancel_event):
    """Restore original stacked-16*.png, stacked.jpg and shotsInfo.json from primary session."""
    try:
        primary_path = Path(win_long_path(primary_path_str))
        new_path = Path(win_long_path(new_path_str))

        primary_panels = sorted([d for d in primary_path.iterdir() if d.is_dir()])
        new_panels     = sorted([d for d in new_path.iterdir() if d.is_dir()])

        if len(primary_panels) != len(new_panels):
            print_log("⚠️ Panel count mismatch", log)

        # ── Per-panel: stacked-16*.png + stacked.jpg ─────────────────────
        for i, (primary_panel, new_panel) in enumerate(zip(primary_panels, new_panels), start=1):
            print_log(f"ℹ️ Resetting panel {i}...", log)

            # stacked-16*.png
            primary_pngs = list(primary_panel.glob("stacked-16*.png"))
            if not primary_pngs:
                print_log(f"⚠️ Panel {i}: no stacked PNG found in primary", log)
            for f in primary_pngs:
                dst = new_panel / f.name
                result_copy = await run.io_bound(safe_copy2, str(f), str(dst))
                if not result_copy:
                    raise Exception(f"Copy failed without exception: {str(f)}")
                print_log(f"  ✔️ Restored {f.name}", log)

            # stacked.jpg in subdir
            primary_jpg = primary_panel / "stacked.jpg"
            if primary_jpg.exists():
                result_copy = await run.io_bound(safe_copy2, str(primary_jpg), str(new_panel / "stacked.jpg"))
                if not result_copy:
                    raise Exception(f"Copy failed without exception: {str(primary_jpg)}")
                print_log(f"  ✔️ Restored stacked.jpg in panel {i}", log)
            else:
                print_log(f"  ⚠️ No stacked.jpg in primary panel {i}", log)

            safe_progress(progress_bar, int(round(i / len(primary_panels) * 80)))
            if cancel_event.is_set():
                print_log("Process Canceled")
                return None

        # ── Root: stacked.jpg + stacked_thumbnail.jpg + shotsInfo.json ───
        print_log("ℹ️ Restoring root files...", log)
        for filename in ["stacked.jpg", "stacked_thumbnail.jpg", "shotsInfo.json"]:
            src = primary_path / filename
            if src.exists():
                result_copy = await run.io_bound(safe_copy2, str(src), str(new_path / filename))
                if not result_copy:
                    raise Exception(f"Copy failed without exception: {str(src)}")
                print_log(f"  ✔️ Restored {filename}", log)
            else:
                print_log(f"  ⚠️ {filename} not found in primary", log)

        safe_progress(progress_bar, 100)
        print_log("✅ Reset from primary completed!", log)
        return new_path

    except Exception as e:
        print_log(f"Reset error: {e}")
        return None
