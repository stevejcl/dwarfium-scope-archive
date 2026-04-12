"""
Standalone test for astro mosaic stitching logic.
No dependency on NiceGUI or the rest of the program.

Supported formats: PNG 8-bit, PNG 16-bit, FITS (float32/float64/int32)

Usage:
    python test_mosaic_stitch.py --images img1.png img2.png
    python test_mosaic_stitch.py --images img1.fits img2.fits
    python test_mosaic_stitch.py --images img1.png img2.png img3.png img4.png
    python test_mosaic_stitch.py --images img1.png img2.png --output result.png --feather 51
"""

import sys
import argparse
import platform
import time
import numpy as np
import cv2
import os
from scipy.ndimage import distance_transform_edt, binary_dilation
from enum import Enum
from pathlib import Path
import json

import sep
sep.set_extract_pixstack(5000000)  # default is 300000, increase to 5M

try:
    import astroalign as aa
    print(aa.__version__)
except ImportError:
    print("ERROR : astroalign not installed. Run : pip install astroalign")
    sys.exit(1)

try:
    from astropy.io import fits as astropy_fits
    HAS_ASTROPY = True
except ImportError:
    HAS_ASTROPY = False


# =========================================================
# WINDOWS LONG PATH HANDLING
# =========================================================

def win_long_path(path: str) -> str:
    if platform.system() != "Windows":
        return path
    # convert to absolute path
    path = os.path.abspath(path)
    path = path.replace("/", "\\")
    if not path.startswith("\\\\?\\"):
        path = "\\\\?\\" + path
    return path


# =========================================================
# MULTI-FORMAT LOADING
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
            print(f"  ERROR : astropy is required to read FITS files (pip install astropy)")
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
                    print(f"  ERROR : no image data in {path}")
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
            print(f"  ERROR reading FITS files '{path}' : {e}")
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
        print(f"❌ Failed to save image: {full_path}")

    return success

def save_debug_image(gray: np.ndarray, path: str):
    """Save gray image for visual inspection."""
    cv2.imwrite(path, gray)


# =========================================================
# IMAGE PREPARATION FOR STAR DETECTION
# =========================================================

def prepare_for_star_detection(img_gray: np.ndarray, 
                               target_mask_ratio: float = 0.005,
                               max_mask_ratio: float = 0.05,
                               min_stars: int = 10,
                               max_stars: int = 50000,
                               normalize: bool = True) -> np.ndarray:
    """
    Prepare a grayscale image for star detection using astroalign.

    3-step strategy:
      1. Local background subtraction (GaussianBlur large): isolates point sources
         from the background gradient, essential for FITS (Flat-Sky Placement Tests)
         where the background significantly dominates the stars in absolute value.
      2. Clip negative values ​​(residual background after subtraction).
      3. Threshold at the 80th percentile of positive pixels: retains only sources
         clearly above the local background.

    Result: image with only stars, background = 0.
    Compatible with 8-bit and 16-bit (subtraction normalizes the dynamic range).   Prepare une image grayscale pour la detection d'etoiles par astroalign.
    """
    img_f = img_gray.astype(np.float64)

    # Background kernel size: ~5% of the smallest dimension, odd
    min_dim = min(img_f.shape)
    ksize = max(51, int(min_dim * 0.05))
    if ksize % 2 == 0:
        ksize += 1

    # Subtraction of local funds
    background = cv2.GaussianBlur(img_f.astype(np.float32), (ksize, ksize), 0
                                  ).astype(np.float64)
    img_sub = np.clip(img_f - background, 0, None)

    # Threshold on positive pixels only
    positive = img_sub[img_sub > 0]
    if positive.size == 0:
        return np.zeros_like(img_sub, dtype=np.uint16 if normalize else img_sub.dtype)

    # ---- Seuil dynamique ----
    percentiles = np.linspace(70, 99.9, 20)  # teste de 95% à 99.9%
    stars = None

    for p in percentiles:
        thresh = np.percentile(positive, p)
        mask = img_sub >= thresh

        mask_ratio = np.count_nonzero(mask) / img_sub.size
        n_stars = np.count_nonzero(mask)

        if (mask_ratio >= target_mask_ratio and
            mask_ratio <= max_mask_ratio and
            n_stars >= min_stars and
            n_stars <= max_stars):
            stars = np.where(mask, img_sub, 0)
            break

    # Si aucun seuil ne satisfait les conditions, prendre le dernier essai
    if stars is None:
        stars = np.where(mask, img_sub, 0)

    # Normalisation vers uint16 pour astroalign
    max_val = stars.max()
    if max_val > 0:
        stars = (stars / max_val * 65535).astype(np.uint16)
    else:
        stars = stars.astype(np.uint16)

    return stars
    
def estimate_translation(transf):
    tx = transf.params[0, 2]
    ty = transf.params[1, 2]
    return int(np.round(ty)), int(np.round(tx))


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
        print(f"  Crop error: {e}")
        return image


# =========================================================
# CHECK MOSAIC ENTRY
# =========================================================

def get_mosaic_layout(config: dict):
    cols = config.get("viewCols")
    rows = config.get("viewRows")
    if cols == 2 and rows == 1:
        return cols, rows, "horizontal"
    if cols == 1 and rows == 2:
        return cols, rows, "vertical"
    if cols == 2 and rows == 2:
        return cols, rows, "grid"
    return cols, rows, "unknown"


def check_mosaic_compatibility(configA: dict, configB: dict):
    cA, rA, typeA = get_mosaic_layout(configA)
    cB, rB, typeB = get_mosaic_layout(configB)
    if (cA, rA) != (cB, rB):
        return False, "Different number of panels"
    if typeA != typeB:
        return False, "Different orientation (horizontal/vertical)"
    return True, "OK"


def compare_images(img1, img2):
    g1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
    g2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
    g1 = cv2.resize(g1, (512, 512)).astype(np.float32)
    g2 = cv2.resize(g2, (512, 512)).astype(np.float32)
    return np.corrcoef(g1.flatten(), g2.flatten())[0, 1]


def detect_inversion(ref_img, test_img):
    score_normal = compare_images(ref_img, test_img)
    score_flip   = compare_images(ref_img, cv2.flip(test_img, -1))
    print(f"    score normal: {score_normal:.4f}")
    print(f"    flip score  : {score_flip:.4f}")
    return score_flip > score_normal


def reorder_panels_if_needed(panels, inverted):
    if not inverted:
        return panels
    n = len(panels)
    if n == 2:
        return [panels[1], panels[0]]
    if n == 4:
        return [panels[2], panels[3], panels[0], panels[1]]
    return panels


# =========================================================
# HELPERS
# =========================================================

def get_inverted_order(images: list) -> list:
    n = len(images)
    if n == 2:
        return [images[1], images[0]]
    elif n == 4:
        return [images[2], images[3], images[0], images[1]]
    else:
        return list(reversed(images))

# =========================================================
# DIRECTIONAL FEATHERING
# =========================================================

def make_directional_feather(h: int, w: int,
                              overlap_left: int = 0,
                              overlap_right: int = 0,
                              overlap_top: int = 0,
                              overlap_bottom: int = 0,
                              feather_size: int = 51) -> np.ndarray:
    mask = np.ones((h, w), dtype=np.float64)
    if overlap_left > 0:
        mask[:, :overlap_left] *= np.linspace(0.0, 1.0, overlap_left)[None, :]
    if overlap_right > 0:
        mask[:, w - overlap_right:] *= np.linspace(1.0, 0.0, overlap_right)[None, :]
    if overlap_top > 0:
        mask[:overlap_top, :] *= np.linspace(0.0, 1.0, overlap_top)[:, None]
    if overlap_bottom > 0:
        mask[h - overlap_bottom:, :] *= np.linspace(1.0, 0.0, overlap_bottom)[:, None]
    if feather_size > 1:
        fs = feather_size if feather_size % 2 == 1 else feather_size + 1
        mask = cv2.GaussianBlur(mask, (fs, fs), 0)
    return mask


def compute_overlap(translations: list, h: int, w: int,
                    base_y: int, base_x: int) -> list:
    n = len(translations)
    overlaps = [{"left": 0, "right": 0, "top": 0, "bottom": 0} for _ in range(n)]
    rects = []
    for dy, dx in translations:
        y0 = base_y + dy
        x0 = base_x + dx
        rects.append((x0, y0, x0 + w, y0 + h))
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            xi0, yi0, xi1, yi1 = rects[i]
            xj0, yj0, xj1, yj1 = rects[j]
            ox0, oy0 = max(xi0, xj0), max(yi0, yj0)
            ox1, oy1 = min(xi1, xj1), min(yi1, yj1)
            if ox1 <= ox0 or oy1 <= oy0:
                continue
            ow, oh = ox1 - ox0, oy1 - oy0
            if xj0 < xi0:
                overlaps[i]["left"]   = max(overlaps[i]["left"],   ow)
            if xj1 > xi1:
                overlaps[i]["right"]  = max(overlaps[i]["right"],  ow)
            if yj0 < yi0:
                overlaps[i]["top"]    = max(overlaps[i]["top"],    oh)
            if yj1 > yi1:
                overlaps[i]["bottom"] = max(overlaps[i]["bottom"], oh)
    return overlaps


def find_transform_robust(img: np.ndarray, ref: np.ndarray, label: str = "") -> tuple:
    """
    Search for the astroalign transformation with several 
    image preparation fallback strategies.

    Strategies:

      1. Subtract local background + p80 threshold (robust FITS and 16-bit PNG)
      2. Direct p99.5 percentile threshold (fallback if the background is already flat)
      3. Direct p99 percentile threshold (fallback for low-dynamic-range images)

    Returns (transf, True) if successful, (None, False) if all attempts fail.
    """
    img_gray = to_gray(img)
    ref_gray = to_gray(ref)

    strategies = [
        ("local background + p80",  prepare_for_star_detection),
        ("threshold p99.5", lambda g: np.where(g >= np.percentile(g, 99.5), g.astype(np.float64), 0.0)),
        ("threshold p99",  lambda g: np.where(g >= np.percentile(g, 99),   g.astype(np.float64), 0.0)),
        ("threshold p95", lambda g: np.where(g >= np.percentile(g, 95), g.astype(np.float64), 0.0)),
    ]

    for strat_label, prepare in strategies:
        try:
            src_prep = prepare(img_gray.astype(np.float64))
            ref_prep = prepare(ref_gray.astype(np.float64))
            ratio = np.count_nonzero(src_prep) / src_prep.size
            print(f"  {label}Mask ratio: {ratio:.4f}")
            src_nonzero = np.count_nonzero(src_prep)
            ref_nonzero = np.count_nonzero(ref_prep)
            print(f"  {label}Stars detected: src={src_nonzero}, ref={ref_nonzero}")
            transf, _ = aa.find_transform(src_prep, ref_prep)
            print(f"  {label}Alignment OK ({strat_label})")
            return transf, True
        except Exception as e:
            print(f"  {label}Strategy '{strat_label}' failed : {e}")

    return None, False

# =========================================================
# MASK - GRAY FUNCTIONS
# =========================================================

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
# MASKING REGION OF INTEREST WITH JSON INFO
# =========================================================

import re

class StitchMode(Enum):
    STACK   = "stack"    # Case 1 & 3: same FOV, align & combine
    MOSAIC  = "mosaic"   # Case 2: multi-panel panorama with grid info


def load_mosaic_info(image_path: str) -> dict | None:
    """
    Given an image path like:
      MOSAIC_DIR/Panel_1/stacked-16xxx.png
    Find and parse shotsInfo.json from MOSAIC_DIR/
    """
    try:
        mosaic_dir = Path(image_path).parent.parent  # up 2 levels
        json_path = mosaic_dir / "shotsInfo.json"
        print(json_path)
        
        if not json_path.exists():
            print(f"  ⚠️ shotsInfo.json not found in {mosaic_dir}")
            return None
        
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            print(f"mosaicInfo: {data.get("mosaicInfo", None)}")
        return data.get("mosaicInfo", None)
    
    except Exception as e:
        print(f"  ⚠️ Failed to load mosaic info: {e}")
        return None


def detect_stitch_mode(image_paths: list[str]) -> StitchMode:
    """
    Detect stitch mode from image paths:
    - No shotsInfo.json found     → STACK (same FOV, different sessions)
    - shotsInfo.json but 1 panel  → STACK (single panel, multiple sessions)
    - shotsInfo.json with grid    → MOSAIC
    """
    mosaic_info = load_mosaic_info(image_paths[0])
    
    if mosaic_info is None:
        print(f"  📐 No mosaicInfo found → STACK mode")
        return StitchMode.STACK

    n_panels = len(mosaic_info.get("subviewInfo", []))
    
    if n_panels <= 1:
        print(f"  📐 Single panel mosaicInfo → STACK mode")
        return StitchMode.STACK

    print(f"  📐 {n_panels}-panel mosaicInfo found → MOSAIC mode")
    return StitchMode.MOSAIC

# not used
def parse_mosaic_info(mosaic_info: dict) -> dict:
    """Extract grid layout and overlap from mosaicInfo JSON."""
    scale_x = float(mosaic_info["viewScaleX"])
    scale_y = float(mosaic_info["viewScaleY"])
    
    overlap_x = max(0.0, min(1.0 - (scale_x / cols), 0.90))
    overlap_y = max(0.0, min(1.0 - (scale_y / rows), 0.90))
    
    # Build coord -> id mapping
    grid = {}
    for sv in mosaic_info["subviewInfo"]:
        col, row = sv["coord"]
        grid[(row, col)] = sv["id"]
    
    return {
        "overlap_x": overlap_x,
        "overlap_y": overlap_y,
        "rows": mosaic_info["viewRows"],
        "cols": mosaic_info["viewCols"],
        "grid": grid  # (col, row) -> panel id
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
    print(f"  ⚠️ Could not extract panel id from: {subdir}")
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
            print(f"  Panel {panel_id} -> coord {coord} ({Path(path).parent.name})")
            coords.append(coord)
        else:
            print(f"  ⚠️ Panel id {panel_id} not found in mosaicInfo, using None")
            coords.append(None)
    
    return coords


def get_alignment_order(coords: list) -> list[tuple[int, int]]:
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


def prepare_for_alignment(img: np.ndarray, max_size: int = 2048) -> np.ndarray:
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
        print(f"  Downsampled for alignment: {w}x{h} → {new_w}x{new_h}")

    # 4. Asinh stretch per channel
    img_f = img8.astype(np.float64) / 255.0
    stretched = np.arcsinh(img_f * 10) / np.arcsinh(10)
    img8 = (stretched * 255).astype(np.uint8)

    # 5. Background subtraction on mean channel
    gray = np.mean(img8, axis=2).astype(np.uint8)
    blurred = cv2.GaussianBlur(gray, (101, 101), 0)
    bg = cv2.subtract(gray, blurred)
    bg_norm = cv2.normalize(bg, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

    # Apply background correction to all channels
    correction = bg_norm.astype(np.float32) / (gray.astype(np.float32) + 1e-6)
    correction = np.clip(correction, 0, 1)
    img8 = (img8.astype(np.float32) * correction[..., None]).astype(np.uint8)

    # Final guarantee: (H, W, 3) uint8 contiguous
    return np.ascontiguousarray(img8, dtype=np.uint8)


# ─────────────────────────────────────────────
# FITS PART 1 — Save transforms (stitch_with_astroalign)
# ─────────────────────────────────────────────
 
def save_transforms(transforms: list, path: str = "./transforms.npy"):
    """
    Save a list of 3×3 numpy arrays to a .npy file.
 
    Usage — add this right after your transform loop:
        save_transforms(transforms, "./transforms.npy")
    """
    arr = np.stack(transforms, axis=0)   # shape (N, 3, 3)
    np.save(path, arr)
    print(f"  ✅ Transforms saved → {path}  (shape {arr.shape})")
     
# =========================================================
# STITCH ASTRO ALIGN with MASK For Mosaic Mode
# =========================================================

def stitch_with_astroalign(images: list, 
                            mode: StitchMode = StitchMode.MOSAIC,
                            stack_method: str = "sigma_clip",
                            coords: list = None,
                            overlap_x: float = None,
                            overlap_y: float = None,
                            label: str = "",
                            feather_size: int = 51,
                            log=None) -> tuple:

    # =========================================================
    # DETECT INPUT DTYPE
    # =========================================================
    print(f"Mode used: {mode}")
    src_dtype = images[0].dtype
    max_val   = 65535.0 if src_dtype == np.uint16 else 255.0
    print(f"  {label}Input dtype: {src_dtype} max_val: {max_val}")

    failed = [] 
    images_f = images #[img.astype(np.float64) for img in images]
    ref = images_f[0]
    h, w, _ = ref.shape

    alignment_pairs = get_alignment_order(coords) if coords else [(0, i) for i in range(1, len(images_f))]

    transforms = [None] * len(images_f)
    transforms[0] = np.eye(3)

    for ref_idx, src_idx in alignment_pairs:
        if mode == StitchMode.STACK:
            # Full image alignment — no mask, use enhanced star detection
            ref_gray = prepare_for_alignment(images_f[ref_idx])
            src_gray = prepare_for_alignment(images_f[src_idx])

            print(f"  ref_gray: shape={ref_gray.shape} dtype={ref_gray.dtype} "
                  f"contiguous={ref_gray.flags['C_CONTIGUOUS']} "
                  f"min={ref_gray.min()} max={ref_gray.max()}")
            print(f"  src_gray: shape={src_gray.shape} dtype={src_gray.dtype} "
                  f"contiguous={src_gray.flags['C_CONTIGUOUS']} "
                  f"min={src_gray.min()} max={src_gray.max()}")

            try:
                transf, _ = aa.find_transform(src_gray, ref_gray, max_control_points=100)

                print(f"  Image {src_idx+1} aligned to Image {ref_idx+1} ✓")

            except Exception as e:
                print(f"  Panel {src_idx+1} alignment failed ({e})")
                transforms[src_idx] = transforms[ref_idx].copy()
                failed.append(src_idx + 1)

        else:
            ref_gray = bright_mask(to_gray(images_f[ref_idx]))
            src_gray = bright_mask(to_gray(images_f[src_idx]))
        
            if coords and overlap_x and overlap_y:
                ref_mask, src_mask = make_overlap_masks(
                    src_gray.shape,
                    ref_coord=coords[ref_idx],
                    src_coord=coords[src_idx],
                    overlap_x=overlap_x,
                    overlap_y=overlap_y
                )
                ref_gray = apply_overlap_mask(ref_gray, ref_mask)
                src_gray = apply_overlap_mask(src_gray, src_mask)
                print(f"  Overlap mask applied: ref={ref_mask.sum()} src={src_mask.sum()} active pixels")
                
                save_debug_image(ref_gray,  "./tmp/debug_ref_masked.png")
                save_debug_image(src_gray,  "./tmp/debug_src_masked.png")

            try:
                transf, _ = aa.find_transform(src_gray, ref_gray,
                                               detection_sigma=2,
                                           max_control_points=100)
                # Compose if ref is not panel 0
                if ref_idx == 0:
                    transforms[src_idx] = transf.params
                else:
                    transforms[src_idx] = transforms[ref_idx] @ transf.params

                print(f"  Panel {src_idx+1} aligned to Panel {ref_idx+1} ✓")

            except Exception as e:
                print(f"  Panel {src_idx+1} alignment failed ({e})")
                transforms[src_idx] = transforms[ref_idx].copy()
                failed.append(src_idx + 1)
        
    # =========================================================
    # SAFETY — fill any missing transforms
    # =========================================================
    for i in range(len(transforms)):
        if transforms[i] is None:
            print(f"  ⚠️ Transform {i+1} is None — using identity")
            transforms[i] = np.eye(3)
            if i not in failed:
                failed.append(i + 1)

    save_transforms(transforms, "./transforms.npy")

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

    print(f"  {label}Canvas : {canvas_w}x{canvas_h}")

    # =========================================================
    # MODE SPLIT
    # =========================================================
    if mode == StitchMode.STACK:
        print(f"  {label}Stack Image")
        result, failed = stack_images(images_f, transforms,
                                      (canvas_h, canvas_w),
                                      base_x, base_y,
                                      method=stack_method,
                                      label=label,
                                      log=log)
        return result, failed  # stack_images already returns correct dtype
        
    # =========================================================
    # INIT CANVAS
    # =========================================================
    print(f"  {label}Blending Panels - Pass 1")

    canvas = np.zeros((canvas_h, canvas_w, 3), dtype=np.float64)

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
    print(f"  {label}Blending Panels - Pass 2")

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

    print(f"  {label}Final Pass")

    # Global weight sum — guaranteed no gaps at intersections
    total_weight = np.sum(feathers, axis=0)
    total_weight_safe = np.maximum(total_weight, 1e-6)

    for idx, ((placed, M), feather) in enumerate(zip(placements, feathers)):
        # Normalize each panel's contribution by total weight at each pixel
        w = feather / total_weight_safe
        canvas += placed * w[..., None]

    result = np.clip(canvas, 0, max_val)
    print(f"  result min={result.min():.1f} max={result.max():.1f} max_val={max_val}")

    return result.astype(src_dtype), failed

# =========================================================
# STITCH ASTROALIGN
# =========================================================
# ALGO 1 : Bright Mask

def stitch_with_astroalign_OK(images: list, label: str = "",
                          feather_size: int = 51) -> tuple:

    images_f = images #[img.astype(np.float64) for img in images]
    ref = images_f[0]
    h, w, _ = ref.shape

    transforms = [np.eye(3)]  # reference = identity

    # =========================================================
    # ALIGNMENT
    # =========================================================
    ref_gray = bright_mask(to_gray(ref))
    print(f"  ref_gray: shape={ref_gray.shape} dtype={ref_gray.dtype} min={ref_gray.min()} max={ref_gray.max()}")


    for idx, img in enumerate(images_f[1:], start=1):
        img_gray = bright_mask(to_gray(img))
        print(f"  img_gray: shape={img_gray.shape} dtype={img_gray.dtype} min={img_gray.min()} max={img_gray.max()}")
        try:
            transf, _ = aa.find_transform(img_gray, ref_gray, max_control_points=500)
            transforms.append(transf.params)

            print(f"  {label}Image {idx+1} : transform OK")
        except Exception as e:
            print(f"  {label}Image {idx+1} : alignment failed ({e})")
            transforms.append(np.eye(3))

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

    print(f"  {label}Canvas : {canvas_w}x{canvas_h}")

    # =========================================================
    # INIT CANVAS
    # =========================================================
    canvas = np.zeros((canvas_h, canvas_w, 3), dtype=np.float64)
    weight = np.zeros((canvas_h, canvas_w), dtype=np.float64)

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
    # PASS 2 : blend with feather only in overlap zones
    # =========================================================
    canvas = np.zeros((canvas_h, canvas_w, 3), dtype=np.float64)
    weight = np.zeros((canvas_h, canvas_w),    dtype=np.float64)

    for idx, ((placed, M), mask) in enumerate(zip(placements, masks)):
        overlap_zone = (total_coverage > 1) & (mask > 0)

        if feather_size > 0 and np.any(overlap_zone):
            # Dilate overlap zone so feather starts before the boundary
            dilated = binary_dilation(overlap_zone,
                                      iterations=feather_size // 2)
            dilated = dilated & (mask > 0)

            dist_in  = distance_transform_edt(overlap_zone)   # ramps up inside
            dist_out = distance_transform_edt(~overlap_zone)  # ramps up outside

            # Smooth transition: 0.5 at overlap center edge, 1.0 feather_size away
            blend = np.where(
                overlap_zone,
                0.5 + 0.5 * np.clip(dist_in  / feather_size, 0, 1),
                       1.0 - 0.5 * np.clip(dist_out / (feather_size // 2), 0, 1)
            )
            feather = np.where(mask > 0, blend, 0.0)
        else:
            feather = mask.copy()

        canvas += placed * feather[..., None]
        weight += feather
        
    weight_safe = np.maximum(weight, 1e-6)
    result = canvas / weight_safe[..., None]

    max_val = np.max(result)
    if max_val > 0:
        result = result / max_val

    return (result * 255).astype(np.uint8), label


# =========================================================
# STITCH ASTROALIGN
# =========================================================
# ALGO 2 : find_transform_robust

def stitch_with_astroalign_old(images: list, label: str = "",
                            feather_size: int = 51) -> tuple:
    images_f = [img.astype(np.float64) for img in images]
    ref = images_f[0]
    h, w, _ = ref.shape

    transforms   = [None]
    translations = [(0, 0)]

    for idx, img in enumerate(images_f[1:], start=1):
        transf, ok = find_transform_robust(img, ref,
                                           label=f"{label}Image {idx+1} : ")
        if ok:
            transforms.append(transf)
            dy, dx = estimate_translation(transf)
            translations.append((dy, dx))
            print(f"  {label}Image {idx+1} : translation dy={dy}, dx={dx}")
        else:
            print(f"  {label}Image {idx+1} : All attempts failed -> (0,0)")
            transforms.append(None)
            translations.append((0, 0))
        
    ys = [dy for dy, dx in translations]
    xs = [dx for dy, dx in translations]
    min_y, max_y = int(np.min(ys)), int(np.max(ys))
    min_x, max_x = int(np.min(xs)), int(np.max(xs))
    canvas_h = h + (max_y - min_y)
    canvas_w = w + (max_x - min_x)
    base_y = -min_y
    base_x = -min_x

    print(f"  {label}Canvas : {canvas_w}x{canvas_h}")

    overlaps = compute_overlap(translations, h, w, base_y, base_x)

    canvas = np.zeros((canvas_h, canvas_w, 3), dtype=np.float64)
    weight = np.zeros((canvas_h, canvas_w),    dtype=np.float64)

    for idx, (img, transf, (dy, dx), ov) in enumerate(
            zip(images_f, transforms, translations, overlaps)):

        y0, x0 = base_y + dy, base_x + dx
        y1, x1 = y0 + h, x0 + w

        if transf is not None:
            algo_new = 2
            if algo_new == 1:
                M = transf.params[:2].copy()
                M[0, 2] = 0.0
                M[1, 2] = 0.0

                placed = cv2.warpAffine(img, M, (w, h),
                                        flags=cv2.INTER_LINEAR,
                                        borderMode=cv2.BORDER_CONSTANT,
                                        borderValue=0)
            else:
                M = transf.params.copy()
                cx, cy = w / 2, h / 2
                T1 = np.array([[1, 0, -cx],
                               [0, 1, -cy],
                               [0, 0, 1]])
                T2 = np.array([[1, 0, cx],
                               [0, 1, cy],
                               [0, 0, 1]])
                M = (T2 @ M @ T1)[:2]
                M_affine = M_centered[:2]

                placed = cv2.warpAffine(
                    img,
                    M_affine,
                    (w, h),
                    flags=cv2.INTER_LINEAR,
                    borderMode=cv2.BORDER_CONSTANT,
                    borderValue=0
                )
        else:
            placed = img

        old = True
        if old:
            feather = make_directional_feather(
                h, w,
                overlap_left   = ov["left"],
                overlap_right  = ov["right"],
                overlap_top    = ov["top"],
                overlap_bottom = ov["bottom"],
                feather_size   = feather_size,
            )

            if y0 < 0 or x0 < 0 or y1 > canvas_h or x1 > canvas_w:
                print(f"  {label}Image {idx+1} : canvas overflow ignored")
                continue

            canvas[y0:y1, x0:x1] += placed * feather[..., None]
            weight[y0:y1, x0:x1] += feather

        else:
            tile_mask = np.ones((h, w), dtype=np.float64)
            mask_canvas = np.zeros((canvas_h, canvas_w), dtype=np.float64)
            mask_canvas[y0:y1, x0:x1] = tile_mask

            # overlap mask in canvas coordinates
            overlap = (weight[y0:y1, x0:x1] > 0)

            # compute distance transform **inside the tile region**
            if np.any(overlap):
                dist = cv2.distanceTransform(np.ones_like(placed[...,0], dtype=np.uint8), cv2.DIST_L2, 5)
                dist = dist / (np.max(dist) + 1e-6)
                feather_tile = np.clip(dist, 0, 1)
                feather_tile[~overlap] = 1.0
            else:
                feather_tile = np.ones_like(placed[...,0], dtype=np.float64)

            # blend in place
            canvas[y0:y1, x0:x1] += placed * feather_tile[..., None]
            weight[y0:y1, x0:x1] += feather_tile

    weight_safe = np.maximum(weight, 1e-6)
    result = canvas / weight_safe[..., None]
    max_val = np.max(result)
    if max_val > 0:
        result = result / max_val
    return (result * 255).astype(np.uint8), label

# =========================================================
# STACKING
# =========================================================

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
    print(f"  {label}Input dtype: {src_dtype} max_val: {max_val}")

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
        print(f"  Warped image {idx+1}/{len(images_f)}")

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
        print(f"  Image {i+1} brightness: {mean_b:.1f}")

    brightness = np.array(brightness)  # ← must be np.array before argmax

    # For N=2, use mean without sigma-clip
    n = len(images_f)
    if n == 2:
        print(f"  Only 2 images — using brightness (no sigma-clip)")

        base_idx  = int(np.argmax(brightness))
        other_idx = 1 - base_idx
        print(f"  N=2: base=Image {base_idx+1} (mean={brightness[base_idx]:.1f})")

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
    print(f"  Sigma-clip: {clipped} pixels rejected (σ={sigma})")

    return result


# =========================================================
# REAL IMAGE TEST
# =========================================================
# =========================================================
# MAIN PANORAMA FUNCTION
# =========================================================

def run_stitch_test(image_paths: list, output: str = "stitch_result.png",
                    feather_size: int = 51):
    print("=" * 60)
    print(f"TEST STITCH ASTROALIGN -- {len(image_paths)} panel(x)")
    print("=" * 60)

    mode = detect_stitch_mode(image_paths)
    print(f"  🔧 Stitch mode: {mode.value}")
    
  
    has_fits = False
    images = []
    for path in image_paths:
        print(f"  Loading : {path}")
        ext = path.lower().rsplit(".", 1)[-1]
        if ext in ("fit", "fits", "fts"):
            has_fits = True
        img = load_image(path)
        if img is None:
            print(f"  ERROR : failed to read '{path}'")
            return False
        h, w = img.shape[:2]
        print(f"  OK : {w}x{h}  dtype={img.dtype}  max={img.max()}")
        images.append(img)


    if mode == StitchMode.STACK:
        # Case 1 & 3 — same FOV, no grid needed
        print("Attempt : STACK MODE")
        result, _ = stitch_with_astroalign(images, mode, label="[nat] ",
                                            feather_size=feather_size)

    elif mode == StitchMode.MOSAIC:
        # Case 2 — use mosaicInfo for coords + overlap masks
        mosaic_info = load_mosaic_info(image_paths[0])
        coords, overlap_x, overlap_y = None, None, None
        
        if mosaic_info:
            coords   = get_coords_for_images(image_paths, mosaic_info)
            print(coords)
            scale_x  = float(mosaic_info["viewScaleX"])
            scale_y  = float(mosaic_info["viewScaleY"])
            cols    = int(mosaic_info["viewCols"])
            rows    = int(mosaic_info["viewRows"])
            #overlap_x = (scale_x - 1.0) / scale_x
            #overlap_y = (scale_y - 1.0) / scale_y
            # Geometric overlap from JSON
            geo_overlap_x = max(0.0, 1.0 - (scale_x / cols))
            geo_overlap_y = max(0.0, 1.0 - (scale_y / rows))
            # Padded overlap for alignment — ensures enough stars in the mask zone
            ALIGN_PAD = 0.20
            overlap_x = min(geo_overlap_x + ALIGN_PAD, 0.50)
            overlap_y = min(geo_overlap_y + ALIGN_PAD, 0.50)

            print(f"overlap_x: {overlap_x}")
            print(f"overlap_y: {overlap_y}")

        else:
            print("  ⚠️ No mosaicInfo found, stitching without masks")
        
        result, failed = stitch_with_astroalign(
                images, mode= mode, coords=coords,
                overlap_x=overlap_x, overlap_y=overlap_y)
            
    print()
    h, w = result.shape[:2]
    print(f"  Size before crop : {w}x{h}")
    save_image(output, result)
    print(f"  Save (before crop) : {output}")

    print("  Cropping black borders...")
    t0 = time.perf_counter()
    result_crop = crop_black_borders(result)
    print(f"  Crop : {time.perf_counter()-t0:.3f}s")
    h, w = result_crop.shape[:2]
    print(f"  Size after crop : {w}x{h}")
    crop_out = output.replace(".png", "_crop.png").replace(".jpg", "_crop.jpg")
    save_image(crop_out, result_crop)
    print(f"  Save (after crop) : {crop_out}")
    print()
    return True


# =========================================================
# UNIT TESTS
# =========================================================

def run_unit_tests():
    all_pass = True

    print("=" * 60)
    print("UNIT TESTS -- get_inverted_order")
    print("=" * 60)
    for desc, inp, expected in [
        ("2 panels [A,B] -> [B,A]",         ["A","B"],         ["B","A"]),
        ("4 panels [1,2,3,4] -> [3,4,1,2]", ["1","2","3","4"], ["3","4","1","2"]),
        ("3 panels -> reversed",             ["A","B","C"],     ["C","B","A"]),
        ("1 panels  -> unchanged",             ["X"],             ["X"]),
    ]:
        result = get_inverted_order(inp)
        ok = result == expected
        print(f"  [{'PASS' if ok else 'FAIL'}] {desc}")
        if not ok:
            print(f"         expected : {expected}")
            print(f"         result  : {result}")
        all_pass = all_pass and ok
    print()

    print("=" * 60)
    print("UNIT TESTS -- mosaic orientation")
    print("=" * 60)
    ok, _ = check_mosaic_compatibility({"viewCols": 2, "viewRows": 1},
                                        {"viewCols": 2, "viewRows": 1})
    print(f"  [{'PASS' if ok else 'FAIL'}] same horizontal config")
    ok, _ = check_mosaic_compatibility({"viewCols": 2, "viewRows": 1},
                                        {"viewCols": 1, "viewRows": 2})
    print(f"  [{'PASS' if not ok else 'FAIL'}] horizontal vs vertical rejected")
    ok = reorder_panels_if_needed(["P1","P2"], True) == ["P2","P1"]
    print(f"  [{'PASS' if ok else 'FAIL'}] 2-panel inversion")
    ok = reorder_panels_if_needed(["P1","P2","P3","P4"], True) == ["P3","P4","P1","P2"]
    print(f"  [{'PASS' if ok else 'FAIL'}] 4-panel inversion")
    print()

    print("=" * 60)
    print("UNIT TESTS -- adaptive bright_mask")
    print("=" * 60)
    # 8 bits : percentile auto doit etre 95
    gray_8 = np.random.randint(10, 200, (100, 100), dtype=np.uint8).astype(np.float64)
    gray_8[50, 50] = 254
    m8 = bright_mask(gray_8)
    thresh_8 = np.percentile(gray_8, 95)
    ok = m8[50, 50] > 0 and m8[0, 0] == 0 or gray_8[0,0] >= thresh_8
    print(f"  [{'PASS' if ok else 'FAIL'}] 8 bits :  star kept, background filtered")

    # 16 bits : percentile auto doit etre 99
    gray_16 = np.random.randint(1000, 3000, (100, 100)).astype(np.float64)
    gray_16[50, 50] = 45000
    m16 = bright_mask(gray_16)
    ok = m16[50, 50] > 0
    print(f"  [{'PASS' if ok else 'FAIL'}] 16 bits : star kept with percentile 99")
    print()

    print("=" * 60)
    print("UNIT TESTS -- prepare_for_star_detection")
    print("=" * 60)

    # Image with dominant sky background (1200 ADU) + Poisson noise + known stars
    rng = np.random.default_rng(42)
    H, W = 300, 300
    sky = rng.poisson(1200, (H, W)).astype(np.float64)
 
    # Place 5 stars in known positions
    star_positions = [(80, 60), (200, 150), (50, 250), (240, 80), (150, 220)]
    for cx, cy in star_positions:
        y, x = np.ogrid[-cy:H-cy, -cx:W-cx]
        sky += rng.uniform(10000, 30000) * np.exp(-(x**2+y**2)/8)
 
    gray = sky.astype(np.float64)
    prepared = prepare_for_star_detection(gray)
 
    # Test 1 : The star pixels must be retained. (> 0)
    stars_retained = sum(prepared[cy, cx] > 0 for cx, cy in star_positions)
    ok_stars = stars_retained == len(star_positions)
    print(f"  [{'PASS' if ok_stars else 'FAIL'}] stars selected : {stars_retained}/{len(star_positions)}")
 
    # Test 2 : the corners (pure background, far from any star) must be at 0
    corner_pixels = [prepared[0, 0], prepared[0, -1], prepared[-1, 0], prepared[-1, -1]]
    ok_bg = all(v == 0 for v in corner_pixels)
    print(f"  [{'PASS' if ok_bg else 'FAIL'}] sky background = 0 in the corners")
 
    # Test 3 : majority of zeros (background must be removed)
    ok_zeros = (prepared == 0).sum() > (prepared > 0).sum()
    print(f"  [{'PASS' if ok_zeros else 'FAIL'}] majority of zeros (background removed)")
 
    all_pass = all_pass and ok_stars and ok_bg and ok_zeros
    print()

    print("=" * 60)
    print("UNIT TESTS -- normalize_to_uint16")
    print("=" * 60)
    # FITS with negative values
    data_fits = np.random.uniform(-500, 50000, (100, 100)).astype(np.float32)
    data_fits[50, 50] = np.nan
    norm = normalize_to_uint16(data_fits)
    ok_dtype = norm.dtype == np.uint16
    ok_range = norm.min() >= 0 and norm.max() <= 65535
    ok_nan   = norm[50, 50] >= 0  # NaN must be treated
    print(f"  [{'PASS' if ok_dtype else 'FAIL'}] dtype = uint16")
    print(f"  [{'PASS' if ok_range else 'FAIL'}] range [0, 65535]")
    print(f"  [{'PASS' if ok_nan   else 'FAIL'}] NaN handled without crash")
    all_pass = all_pass and ok_dtype and ok_range and ok_nan
    print()

    print("=" * 60)
    print("UNIT TESTS -- directional feathering")
    print("=" * 60)
    h, w, overlap = 10, 20, 5
    m1 = make_directional_feather(h, w, overlap_right=overlap, feather_size=1)
    m2 = make_directional_feather(h, w, overlap_left=overlap,  feather_size=1)
    ok_sum = np.allclose(m1[0, w-overlap:] + m2[0, :overlap], 1.0, atol=1e-9)
    ok_f1  = np.allclose(m1[0, :w-overlap], 1.0, atol=1e-9)
    ok_f2  = np.allclose(m2[0, overlap:],   1.0, atol=1e-9)
    print(f"  [{'PASS' if ok_sum else 'FAIL'}] sum in overlap = 1.0")
    print(f"  [{'PASS' if ok_f1  else 'FAIL'}] free edges m1 = 1.0")
    print(f"  [{'PASS' if ok_f2  else 'FAIL'}] free edges m2 = 1.0")
    all_pass = all_pass and ok_sum and ok_f1 and ok_f2
    print()

    print("=" * 60)
    print("UNIT TESTS -- crop_black_borders")
    print("=" * 60)
    # Case 1 : top/bottom bands
    H, W = 600, 900
    img1 = np.random.randint(30, 200, (H, W, 3), dtype=np.uint8)
    band_h, band_b = 80, 60
    img1[:band_h, :] = 0
    img1[-band_b:, :] = 0
    r = crop_black_borders(img1)
    ok_h = abs(r.shape[0] - (H - band_h - band_b)) <= 5
    print(f"  [{'PASS' if ok_h else 'FAIL'}] top/bottom bands : {W}x{H} -> {r.shape[1]}x{r.shape[0]}"
          f"  (expected h~{H-band_h-band_b})")

    # Case 2 : black borders + feathering
    H, W = 2000, 3000
    img2 = np.random.randint(20, 200, (H, W, 3), dtype=np.uint8)
    img2[:200, :200] = 0;  img2[:200, -200:] = 0
    img2[-200:, :200] = 0; img2[-200:, -200:] = 0
    for i in range(30):
        alpha = i / 30
        img2[:, i]       = (img2[:, i]       * alpha).astype(np.uint8)
        img2[:, -(i+1)]  = (img2[:, -(i+1)]  * alpha).astype(np.uint8)
        img2[i, :]       = (img2[i, :]       * alpha).astype(np.uint8)
        img2[-(i+1), :]  = (img2[-(i+1), :]  * alpha).astype(np.uint8)
    t0 = time.perf_counter()
    r2 = crop_black_borders(img2)
    elapsed = time.perf_counter() - t0
    ok_shape    = r2.shape[0] < H and r2.shape[1] < W
    ok_conserve = r2.shape[0] > H - 500 and r2.shape[1] > W - 500
    print(f"  [{'PASS' if ok_shape    else 'FAIL'}] effective crop : {W}x{H} -> {r2.shape[1]}x{r2.shape[0]}")
    print(f"  [{'PASS' if ok_conserve else 'FAIL'}] conservative crop (no over-crop)")
    print(f"  [INFO] time : {elapsed:.3f}s")
    all_pass = all_pass and ok_h and ok_shape and ok_conserve

    for label, test_img in [
        ("no black borders", np.random.randint(20, 200, (500, 800, 3), dtype=np.uint8)),
        ("all black",        np.zeros((200, 300, 3), dtype=np.uint8)),
    ]:
        r = crop_black_borders(test_img)
        ok = r.shape == test_img.shape
        print(f"  [{'PASS' if ok else 'FAIL'}] {label} -> returns original image")
        all_pass = all_pass and ok
    print()

    print("=" * 60)
    print("UNIT TESTS -- win_long_path")
    print("=" * 60)
    if platform.system() != "Windows":
        print("  [SKIP] Non-Windows : path returned unchanged")
        for p in ["/home/user/file.png", "relative/path.png"]:
            ok = win_long_path(p) == p
            print(f"  [{'PASS' if ok else 'FAIL'}] '{p}'")
    else:
        for inp, expected in [
            ("C:\\Users\\test\\file.png",        "\\\\?\\C:\\Users\\test\\file.png"),
            ("C:/Users/test/file.png",           "\\\\?\\C:\\Users\\test\\file.png"),
            ("\\\\?\\C:\\already\\prefixed.png", "\\\\?\\C:\\already\\prefixed.png"),
        ]:
            result = win_long_path(inp)
            ok = result == expected
            print(f"  [{'PASS' if ok else 'FAIL'}] '{inp}' -> '{result}'")
            all_pass = all_pass and ok
    print()
    return all_pass


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Astro mosaic stitching test (astroalign) — PNG 8/16-bit and FITS"
    )
    parser.add_argument(
        "--images", nargs="+", metavar="IMG", required=True,
        help="Paths to panel images (2 or 4), in numeric order. "
             "Supported formats: .png, .jpg, .tiff, .fit, .fits, .fts"
    )
    parser.add_argument(
        "--output", default="stitch_result.png",
        help="Output file (default: stitch_result.png)"
    )
    parser.add_argument(
        "--feather", type=int, default=51,
        help="Feather blending size in odd pixels (default: 51)"
    )
    args = parser.parse_args()

    unit_ok   = run_unit_tests()
    stitch_ok = run_stitch_test(args.images, output=args.output,
                                feather_size=args.feather)

    print("=" * 60)
    print("All tests passed." if (unit_ok and stitch_ok)
          else "Some tests failed.")
    print("=" * 60)
    sys.exit(0 if (unit_ok and stitch_ok) else 1)