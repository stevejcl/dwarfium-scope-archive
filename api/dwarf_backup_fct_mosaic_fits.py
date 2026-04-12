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

from astropy.io import fits

from scipy.ndimage import distance_transform_edt, binary_dilation

from nicegui import ui, run, Client

from api.dwarf_backup_fct import print_log, win_long_path

# ─────────────────────────────────────────────
# PART 1 — Import from dwarf_backup_fct_mosaic
# ─────────────────────────────────────────────

from api.dwarf_backup_fct_mosaic import (TRANSFORM_AUTO_SAVE_PATH, load_transforms, crop_black_borders)


# ─────────────────────────────────────────────
# PART 2 — Helpers
# ─────────────────────────────────────────────

def load_fits_data(path: str, hdu_index: int = 0):
    with fits.open(path) as hdul:
        data   = hdul[hdu_index].data.astype(np.float32)
        header = hdul[hdu_index].header.copy()
    return data, header


def warp_channel(channel: np.ndarray, M23: np.ndarray,
                 canvas_w: int, canvas_h: int) -> np.ndarray:
    """Apply a 2×3 affine matrix to one 2-D channel."""
    return cv2.warpAffine(
        channel, M23, (canvas_w, canvas_h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT, borderValue=0.0
    )


def compute_canvas(transforms: list, h: int, w: int):
    corners = np.array([[0,0,1],[w,0,1],[0,h,1],[w,h,1]]).T
    all_c   = np.hstack([M @ corners for M in transforms])
    min_x, max_x = int(np.floor(all_c[0].min())), int(np.ceil(all_c[0].max()))
    min_y, max_y = int(np.floor(all_c[1].min())), int(np.ceil(all_c[1].max()))
    return max_x - min_x, max_y - min_y, -min_x, -min_y


def sigma_clip_median(data: np.ndarray, sigma: float = 3.0, iters: int = 3) -> float:
    """Robust sky background estimate via iterative sigma clipping.
    Ignores bright stars and nebula peaks."""
    d = data.ravel()
    d = d[d > 0]
    if len(d) == 0:
        return 0.0
    for _ in range(iters):
        med = np.median(d)
        std = np.std(d)
        if std == 0:
            break
        d = d[np.abs(d - med) < sigma * std]
    return float(np.median(d)) if len(d) > 0 else 0.0


# ─────────────────────────────────────────────
# PART 3 — Overlap-zone background normalisation
# ─────────────────────────────────────────────

def normalise_panels_overlap(placements: list, masks: list, n_ch: int) -> list:
    """
    Scale panels 1..N so their background matches panel 0 in overlap zones.

    Strategy
    --------
    For each panel i, find pixels that overlap with the union of all previous
    panels. Compute a sigma-clipped sky median on both sides, then apply:

        corrected = (src - bg_src) * (bg_ref / bg_src) + bg_ref

    This corrects both gain differences and pedestal (bias/dark) offsets.
    Each channel is normalised independently.

    Returns a new placements list with corrected float64 channels.
    """
    print("\n── Overlap-zone background normalisation ──")
    n = len(placements)
    normalised = [[ch.astype(np.float64) for ch in placements[0]]]
    placed_mask = masks[0].astype(bool)

    for idx in range(1, n):
        overlap = placed_mask & masks[idx].astype(bool)
        n_px    = int(overlap.sum())
        print(f"  Panel {idx+1}: overlap zone = {n_px} px", end="  ")

        if n_px < 200:
            print("⚠️  too few pixels — skipping normalisation for this panel")
            normalised.append([ch.astype(np.float64) for ch in placements[idx]])
            placed_mask |= masks[idx].astype(bool)
            continue

        new_channels = []
        for c in range(n_ch):
            # Build reference composite from all already-normalised panels
            ref_acc   = np.zeros(n_px, dtype=np.float64)
            ref_count = np.zeros(n_px, dtype=np.float64)
            for prev in range(idx):
                pv = normalised[prev][c][overlap]
                valid = pv > 0
                ref_acc[valid]   += pv[valid]
                ref_count[valid] += 1
            ref_count_safe = np.maximum(ref_count, 1)
            ref_composite  = ref_acc / ref_count_safe

            bg_ref = sigma_clip_median(ref_composite)

            # Source panel sky in overlap
            src_ch   = placements[idx][c].astype(np.float64)
            src_vals = src_ch[overlap]
            bg_src   = sigma_clip_median(src_vals)

            if c == 0:
                print(f"bg_ref={bg_ref:.1f}  bg_src={bg_src:.1f}  "
                      f"scale={bg_ref/max(bg_src,1e-9):.4f}")

            bg_src_safe = bg_src if abs(bg_src) > 1e-9 else 1e-9
            scale       = bg_ref / bg_src_safe

            corrected = (src_ch - bg_src) * scale + bg_ref
            corrected = np.maximum(corrected, 0.0)
            new_channels.append(corrected)

        normalised.append(new_channels)
        placed_mask |= masks[idx].astype(bool)

    return normalised

# ─────────────────────────────────────────────
# PART 4 — Crop Black Corner
# ─────────────────────────────────────────────

def crop_black_borders_fits(fits_data: np.ndarray, tolerance_fraction: float = 0.001) -> np.ndarray:
    """
    Wrapper around crop_black_borders() for FITS float32 data.

    The tolerance in FITS is not an absolute ADU value but a fraction
    of the data range, since FITS panels can have very different scales.
    tolerance_fraction=0.001 means 0.1% of max value = effectively zero.

    Supports 2D (H,W) and 3D (C,H,W) or (H,W,C) FITS arrays.
    """
    # Build a 2D proxy image for border detection (normalised to uint16)
    if fits_data.ndim == 2:
        proxy = fits_data
    elif fits_data.ndim == 3 and fits_data.shape[0] <= 4:
        proxy = fits_data.max(axis=0)        # (C,H,W) → collapse channels
    else:
        proxy = fits_data.max(axis=2)        # (H,W,C) → collapse channels

    data_max = proxy.max()
    if data_max <= 0:
        return fits_data

    # Normalise to uint16 range for cv2 compatibility
    proxy_u16 = (proxy / data_max * 65535).astype(np.uint16)

    # Convert tolerance from fraction to absolute uint16 value
    tolerance_abs = int(tolerance_fraction * 65535)

    # Find the crop box using the existing function (pass the uint16 proxy)
    cropped_proxy = crop_black_borders(proxy_u16, tolerance=tolerance_abs)

    if cropped_proxy.shape == proxy_u16.shape:
        print("  Crop: no black borders found")
        return fits_data

    # Recover the crop coordinates by comparing shapes
    # (crop_black_borders returns image[y:y+rh, x:x+rw] so we need to
    #  re-run the detection — simplest is to call it and compare sizes)
    # Instead: patch crop_black_borders to also return the box (see note below)
    # For now, derive box by running a second call internally:
    y1, x1 = _find_crop_box(proxy_u16, tolerance=tolerance_abs)
    rh = cropped_proxy.shape[0]
    rw = cropped_proxy.shape[1]

    print(f"  Crop: ({x1},{y1}) → {rw}×{rh} px")

    if fits_data.ndim == 2:
        return fits_data[y1:y1+rh, x1:x1+rw]
    elif fits_data.ndim == 3 and fits_data.shape[0] <= 4:
        return fits_data[:, y1:y1+rh, x1:x1+rw]
    else:
        return fits_data[y1:y1+rh, x1:x1+rw, :]


def _find_crop_box(image: np.ndarray, tolerance: int = 5) -> tuple:
    """Returns (y, x) top-left corner of the crop found by crop_black_borders."""
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
    best_area, best = 0, (0, 0, w, h)
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
    x, y, _, _ = best
    return y, x

# ─────────────────────────────────────────────
# PART 5 — Main stitch function
# ─────────────────────────────────────────────

def stitch_fits_from_transforms(fits_paths: list,
                                 output_fits: str = "mosaic_stitched.fits",
                                 hdu_index: int = 0,
                                 feather_size: int = 51,
                                 normalise: bool = True,
                                 crop: bool = True,
                                 log = None,
                                 transforms_path: str = TRANSFORM_AUTO_SAVE_PATH):
    """
    Load saved transforms and apply them to FITS panels.

    Parameters
    ----------
    fits_paths       : ordered list of FITS file paths (same order as PNGs)
    output_fits      : output file path
    hdu_index        : HDU to read from each FITS file (default 0)
    feather_size     : feather blend radius in pixels (match PNG pipeline)
    normalise        : match panel backgrounds in overlap zones (default True)
    crop             : do final crop black corners on the result image
    log              : log.ui if exists else print function
    transforms_path  : path to the .npy file saved by save_transforms()
    """

    # ── Load transforms ──
    transforms = load_transforms(transforms_path)
    assert len(transforms) == len(fits_paths), \
        f"Got {len(transforms)} transforms but {len(fits_paths)} FITS files!"

    # ── Load FITS panels ──
    print_log("\n── Loading FITS panels ──", log)
    panels, headers = [], []
    for p in fits_paths:
        data, hdr = load_fits_data(p, hdu_index)
        panels.append(data)
        headers.append(hdr)
        print(f"  {os.path.basename(p)} → shape {data.shape}  dtype {data.dtype}")

    # ── Detect layout ──
    first = panels[0]
    if first.ndim == 2:
        h, w = first.shape
        n_ch, mode = 1, "2d"
    elif first.ndim == 3 and first.shape[0] <= 4:
        n_ch, h, w = first.shape
        mode = "chw"                     # (C, H, W)  — common FITS convention
    elif first.ndim == 3:
        h, w, n_ch = first.shape
        mode = "hwc"                     # (H, W, C)
    else:
        raise ValueError(f"Unsupported shape: {first.shape}")

    canvas_w, canvas_h, base_x, base_y = compute_canvas(transforms, h, w)
    print_log(f"\n── Canvas: {canvas_w} × {canvas_h} px ──", log)

    # ── Pass 1: warp all panels ──
    print_log("\n── Warping panels ──", log)
    placements, masks = [], []

    for idx, (panel, M_full) in enumerate(zip(panels, transforms)):
        M = M_full[:2].copy()
        M[0, 2] += base_x
        M[1, 2] += base_y

        if mode == "2d":
            channels = [panel]
        elif mode == "chw":
            channels = [panel[c] for c in range(n_ch)]
        else:
            channels = [panel[..., c] for c in range(n_ch)]

        warped = [warp_channel(ch, M, canvas_w, canvas_h) for ch in channels]
        mask   = (np.stack(warped, axis=0).max(axis=0) != 0).astype(np.float64)

        placements.append(warped)
        masks.append(mask)
        print_log(f"  Panel {idx+1} warped ✓", log)

    # ── Pass 1b: overlap-zone background normalisation ──
    if normalise:
        placements = normalise_panels_overlap(placements, masks, n_ch)
    else:
        print("\n── Normalisation skipped (--no-normalise) ──")
        placements = [[ch.astype(np.float64) for ch in p] for p in placements]

    # ── Pass 2: feather weights ──
    print_log("\n── Feather blending ──",log)
    feathers = []
    for mask in masks:
        dist    = distance_transform_edt(mask)
        feather = np.clip(dist / max(feather_size, 1), 0.0, 1.0) \
                  if feather_size > 0 else mask.copy()
        feathers.append(feather)

    total_w      = np.sum(feathers, axis=0)
    total_w_safe = np.maximum(total_w, 1e-9)

    # ── Pass 3: blend ──
    canvas = [np.zeros((canvas_h, canvas_w), dtype=np.float64) for _ in range(n_ch)]
    for warped, feather in zip(placements, feathers):
        w_norm = feather / total_w_safe
        for c, ch in enumerate(warped):
            canvas[c] += ch * w_norm

    # ── Assemble output ──
    if mode == "2d":
        result = canvas[0].astype(np.float32)
    elif mode == "chw":
        result = np.stack(canvas, axis=0).astype(np.float32)
    else:
        result = np.stack(canvas, axis=-1).astype(np.float32)

    print_log(f"\n  Result shape {result.shape}  "
          f"min={result.min():.4f}  max={result.max():.4f}", log)

    # ── Cropping Black corners ──
    if crop:
        print("\n── Cropping black borders ──")
        crop_fits__out = output_fits.replace(".fits", "_crop.fits")
        result_crop = crop_black_borders_fits(result, tolerance_fraction=0.001)
        print(f"  Final size: {result_crop.shape}")

        print(f"\n── Saving → {output_fits} ──")
        hdr = headers[0].copy()
        hdr["HISTORY"] = "Mosaic stitched via saved PNG transforms"
        hdr["HISTORY"] = "Overlap-zone background normalisation applied"
        fits.PrimaryHDU(data=result_crop, header=hdr).writeto(output_fits, overwrite=True)
        print_log(f"  ✅ Saved  ({os.path.getsize(output_fits)/1e6:.1f} MB)", log)

    else:
        print("\n── Cropping skipped (--no-crop) ──")

        # ── Save FITS ──
        print_log(f"\n── Saving → {output_fits} ──", log)
        hdr = headers[0].copy()
        hdr["HISTORY"] = "Mosaic stitched via saved PNG transforms"
        hdr["HISTORY"] = "Overlap-zone background normalisation applied"
        fits.PrimaryHDU(data=result, header=hdr).writeto(output_fits, overwrite=True)
        print_log(f"  ✅ Saved  ({os.path.getsize(output_fits)/1e6:.1f} MB)", log)


