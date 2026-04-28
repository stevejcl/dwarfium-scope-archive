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
from enum import Enum

from scipy.ndimage import distance_transform_edt, binary_dilation

from nicegui import ui, run, Client

from api.dwarf_backup_fct import print_log, win_long_path


# =========================================================
# STITCH FUNCTION HELPERS
# =========================================================

def infer_mosaic_info_from_images(mosaic_dir: str) -> dict | None:
    """
    Infer mosaic grid and overlap from image sizes when no shotsInfo.json.
    
    Uses:
      - mosaic_dir/stacked.jpg        → total mosaic dimensions
      - mosaic_dir/panel_X/stacked.jpg → single panel dimensions
    """
    try:
        mosaic_dir = Path(mosaic_dir)
        
        # ── Total mosaic size ──────────────────────────────────────────
        root_stacked = mosaic_dir / "stacked.jpg"
        if not root_stacked.exists():
            print_log(f"  ⚠️ No root stacked.jpg in {mosaic_dir}")
            return None
        
        mosaic_img = cv2.imread(str(root_stacked))
        if mosaic_img is None:
            return None
        mosaic_h, mosaic_w = mosaic_img.shape[:2]
        print(f"  Mosaic stacked.jpg: {mosaic_w}x{mosaic_h}")

        # ── Single panel size ──────────────────────────────────────────
        panel_w, panel_h = None, None
        for subdir in sorted(mosaic_dir.iterdir()):
            if not subdir.is_dir():
                continue
            panel_stacked = subdir / "stacked.jpg"
            if panel_stacked.exists():
                panel_img = cv2.imread(str(panel_stacked))
                if panel_img is not None:
                    panel_h, panel_w = panel_img.shape[:2]
                    print(f"  Panel stacked.jpg: {panel_w}x{panel_h}")
                    break

        if panel_w is None:
            print_log(f"  ⚠️ No panel stacked.jpg found")
            return None

        # ── Derive grid and overlap ────────────────────────────────────
        scale_x = math.floor((10 * mosaic_w / panel_w) + 0.5) /10
        scale_y = math.floor((10 * mosaic_h / panel_h) + 0.5) /10

        cols = max(1, math.ceil(scale_x))
        rows = max(1, math.ceil(scale_y))

        geo_overlap_x = max(0.0, 1.0 - (scale_x / cols))
        geo_overlap_y = max(0.0, 1.0 - (scale_y / rows))

        ALIGN_PAD = 0.20
        overlap_x = min(geo_overlap_x + ALIGN_PAD, 0.50)
        overlap_y = min(geo_overlap_y + ALIGN_PAD, 0.50)

        print(f"  Inferred grid: {cols}x{rows} "
              f"geo=({geo_overlap_x:.3f},{geo_overlap_y:.3f}) "
              f"align=({overlap_x:.3f},{overlap_y:.3f})")

        return {
            "cols": cols,
            "rows": rows,
            "overlap_x": overlap_x,
            "overlap_y": overlap_y,
        }

    except Exception as e:
        print_log(f"  ⚠️ infer_mosaic_info_from_images failed: {e}")
        return None

def detect_panel_position(gray: np.ndarray, edge_frac: float = 0.35) -> tuple[int, int]:
    """
    Infer (row, col) from star concentration on panel edges only.
    Uses outer edge_frac strip on each side to avoid center nebula bias.
    
    Stars concentrated on left edge  → panel is RIGHT (col=1)
    Stars concentrated on right edge → panel is LEFT  (col=0)
    Stars concentrated on top edge   → panel is BOTTOM (row=1)
    Stars concentrated on bottom edge→ panel is TOP   (row=0)
    """
    h, w = gray.shape
    ex = int(w * edge_frac)
    ey = int(h * edge_frac)

    left_sum   = float(gray[:, :ex].sum())
    right_sum  = float(gray[:, w-ex:].sum())
    top_sum    = float(gray[:ey, :].sum())
    bot_sum    = float(gray[h-ey:, :].sum())

    col = 1 if left_sum  > right_sum else 0
    row = 1 if top_sum   > bot_sum   else 0

    print(f"    edge sums L={left_sum:.0f} R={right_sum:.0f} "
          f"T={top_sum:.0f} B={bot_sum:.0f} → ({row},{col})")

    return (row, col)


def subsample_for_alignment(gray: np.ndarray, max_stars: int = 50) -> np.ndarray:
    """
    Downsample a masked gray image so astroalign sees fewer, 
    more distinct star triangles.
    Keeps brightest pixels by blurring + downscaling.
    """
    # Remove isolated noise, keep star-like peaks
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # Downscale until star count is manageable
    h, w = blurred.shape
    scale = 1.0
    result = blurred
    while scale > 0.25:
        scale *= 0.5
        small = cv2.resize(blurred, (int(w * scale), int(h * scale)),
                           interpolation=cv2.INTER_LINEAR)
        # Rough star count estimate: non-zero pixels after threshold
        _, thresh = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        n_pixels = thresh.sum() // 255
        if n_pixels <= max_stars * 20:  # rough pixels-per-star estimate
            result = small
            break

    return result

def crop_to_active_region(gray: np.ndarray) -> np.ndarray:
    """
    Crop image to the bounding box of non-zero pixels.
    Removes large black areas that waste astroalign's search space.
    """
    nonzero = np.nonzero(gray)
    if len(nonzero[0]) == 0:
        return gray
    y0, y1 = nonzero[0].min(), nonzero[0].max()
    x0, x1 = nonzero[1].min(), nonzero[1].max()
    return gray[y0:y1+1, x0:x1+1]
    

def equalize_background(images: list) -> list:
    """
    Normalize each image's background level to match the first panel.
    Uses median of the darkest 20% of pixels as background estimate.
    """
    def bg_level(img):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
        flat = gray[gray > 0].flatten()
        return np.percentile(flat, 20) if flat.size > 0 else 1.0

    ref_bg = bg_level(images[0])
    result = [images[0]]

    for img in images[1:]:
        src_bg = bg_level(img)
        ratio  = ref_bg / (src_bg + 1e-6)
        equalized = np.clip(img.astype(np.float64) * ratio, 0, 65535).astype(img.dtype)
        result.append(equalized)
        print(f"  Background equalization: {src_bg:.1f} → {ref_bg:.1f} (ratio={ratio:.3f})")

    return result
 
