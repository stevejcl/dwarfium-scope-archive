from pathlib import Path
import shutil
import zipfile
import os
import re
import json
import numpy as np
import cv2

from nicegui import ui, run, Client

from api.dwarf_backup_fct import print_log, win_long_path


# =========================================================
# UI GUARD HELPERS
# =========================================================

def safe_log(log, msg: str) -> None:
    """Write to the log widget only if the client is still connected."""
    try:
        if log is not None:
            log.push(msg)
    except Exception:
        print(msg)  # fallback to console

def safe_progress(progress_bar, value: float) -> None:
    """Update progress bar only if the client is still connected."""
    try:
        if progress_bar is not None:
            progress_bar.value = value
    except Exception:
        pass

# =========================================================
# IMAGE PROCESSING
# =========================================================

def crop_black_borders(image, tolerance=10):
    """Crop black borders by finding the largest valid rectangle."""
    try:
        # memory limit
        cv2.ocl.setUseOpenCL(False)

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        mask = (gray > tolerance).astype(np.uint8) * 255

        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.erode(mask, kernel, iterations=2)

        h, w = mask.shape

        hist = np.zeros(w, dtype=np.int32)
        best_area = 0
        best = (0, 0, w, h)

        def largest_rect(hist):
            stack = []
            max_area = 0
            best_rect = (0, 0, 0)
            for i, val in enumerate(hist):
                start = i
                while stack and stack[-1][1] > val:
                    x, height = stack.pop()
                    width = i - x
                    if width * height > max_area:
                        max_area = width * height
                        best_rect = (x, width, height)
                    start = x
                stack.append((start, val))
            for x, height in stack:
                width = len(hist) - x
                if width * height > max_area:
                    max_area = width * height
                    best_rect = (x, width, height)
            return best_rect

        for y in range(h):
            for x in range(w):
                hist[x] = hist[x] + 1 if mask[y, x] > 0 else 0

            x, width, height = largest_rect(hist.tolist())
            area = width * height

            if area > best_area:
                best_area = area
                best = (x, y - height + 1, width, height)

        if best_area == 0:
            return image

        x, y, w, h = best
        return image[y:y+h, x:x+w]

    except Exception as e:
        print(f"Crop error: {e}")
        return image

def resize_for_stitch(images, scale=0.7):
    return [cv2.resize(img, None, fx=scale, fy=scale) for img in images]

def free_images(images):
    del images
    import gc
    gc.collect()

async def stitch_images(images, log):
    """Robust stitching with multiple fallbacks."""
    try:
        if len(images) == 1:
            return images[0]

        # memory limit
        cv2.ocl.setUseOpenCL(False)

        #stitcher = cv2.Stitcher_create(cv2.Stitcher_PANORAMA)
        stitcher = cv2.Stitcher_create(cv2.Stitcher_SCANS)

        # 1. normal
        status, pano = await run.io_bound(stitcher.stitch, images)

        if status == cv2.Stitcher_OK:
            free_images(images)
            return pano

        safe_log(log, "⚠️ Stitch failed → trying reverse order")

        # 2. reverse
        status, pano = await run.io_bound(stitcher.stitch, list(reversed(images)))
        if status == cv2.Stitcher_OK:
            free_images(images)
            return pano

        safe_log(log, "⚠️ Stitch failed → trying 180° rotation")

        # 3. rotate last image
        rotated = images.copy()
        rotated[-1] = cv2.rotate(rotated[-1], cv2.ROTATE_180)

        status, pano = await run.io_bound(stitcher.stitch, rotated)
        if status == cv2.Stitcher_OK:
            free_images(images)
            return pano

        safe_log(log, "⚠️ Stitch failed → fallback to first image")
        return images[0]

    except Exception as e:
        print(f"Stitch error: {e}")
        free_images(images)
        return images[0] if images else None


async def generate_panorama(images, output_path, thumbnail_path, log):
    try:
        # memory limit
        cv2.ocl.setUseOpenCL(False)
        images_small = resize_for_stitch(images, scale=0.7)
        pano = await stitch_images(images_small, log)
        if pano is None:
            safe_log(log, "⚠️ Panorama failed")
            return

        pano = await run.io_bound(crop_black_borders, pano)

        cv2.imwrite(str(output_path), pano)
        cv2.imwrite(str(thumbnail_path), cv2.resize(pano, (356, 200)))

        safe_log(log, "✔️ Panorama generated")

    except Exception as e:
        print(f"Panorama error: {e}")


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
    m = re.search(r'_(-?\d+)C', name)
    return int(m.group(1)) if m else None


# --------------
# REPAIR ACTION
# --------------

async def repair_mosaic_session(old_session_path: str, new_session_path: str, log, progress_bar):
    """Repair a mosaic session by restoring missing FITS/PNG and rebuilding outputs."""
    try:
        old_path = Path(win_long_path(old_session_path))
        new_path = Path(win_long_path(new_session_path))

        if not old_path.exists() or not new_path.exists():
            safe_log(log, "❌ Session path not found")
            return None

        safe_progress(progress_bar, 40)
        safe_log(log, "ℹ️ Replacing FITS files...")

        old_panels = sorted([d for d in old_path.iterdir() if d.is_dir()])
        new_panels = sorted([d for d in new_path.iterdir() if d.is_dir()])

        if len(old_panels) != len(new_panels):
            safe_log(log, "⚠️ Panel count mismatch")

        for panel_index, (old_panel, new_panel) in enumerate(zip(old_panels, new_panels), start=1):

            # Remove non stacked FITS
            safe_log(log, f"ℹ️ Cleaning panel {panel_index}")
            for file in new_panel.glob("*.fits"):
                if not file.name.startswith("stacked-16"):
                    file.unlink()

            safe_progress(progress_bar, 40 + 8 *(panel_index/len(old_panels)))

            # Restore FITS from old session
            safe_log(log, f"ℹ️ Restoring FITS for panel {panel_index}")
            for old_file in old_panel.glob("*.fits"):
                if not old_file.name.startswith("stacked-16"):
                    await run.io_bound(shutil.copy2, str(old_file), str(new_panel / old_file.name))

            safe_progress(progress_bar, 48 + 12 *(panel_index/len(old_panels)))

            # -----------------------------
            # Copy old PNGs and FITS, rebuild ZIP, generate stacked images (Repair only)
            # -----------------------------
            old_pngs = sorted(old_panel.glob("stacked-16*.png"))
            new_pngs = sorted(new_panel.glob("stacked-16*.png"))

            if len(old_pngs) != len(new_pngs):
                safe_log(log, f"⚠️ PNG mismatch: {old_panel.name}")

            safe_log(log, f"ℹ️ Replacing PNGs for panel {panel_index}...")
            for old_file, new_file in zip(old_pngs, new_pngs):
                await run.io_bound(shutil.copy2, str(old_file), str(new_file))  # replace content, keep name

            safe_progress(progress_bar, 60 + 4 *(panel_index/len(old_panels)))

            old_stacked = sorted(old_panel.glob("stacked-16*.fits"))
            new_stacked = sorted(new_panel.glob("stacked-16*.fits"))

            if len(old_stacked) != len(new_stacked):
                safe_log(log, f"⚠️ stacked-16 FITS mismatch: {old_panel.name}")

            safe_log(log, f"ℹ️ Copying old stacked-16 FITS files for panel {panel_index}...")
            for old_file, new_file in zip(old_stacked, new_stacked):
                await run.io_bound(shutil.copy2, str(old_file), str(new_file))  # replace content, keep name

            safe_progress(progress_bar, 64 + 4 *(panel_index/len(old_panels)))

        # ── Post-loop: shotsInfo, ZIP, panorama ───────────────────────────
        safe_log(log, "ℹ️ Copying shotsInfo.json...")
        old_info = old_path / "shotsInfo.json"
        new_info = new_path / "shotsInfo.json"
        if old_info.exists():
            await run.io_bound(shutil.copy2, str(old_info), str(new_info))

        safe_progress(progress_bar, 75)

        safe_log(log, "ℹ️ Rebuilding ZIP stacked-16_*.zip...")
        print("ℹ️ Rebuilding ZIP stacked-16_*.zip...")
        zip_files = list(new_path.glob("stacked-16_*.zip"))
        if zip_files:
            zip_path = zip_files[0]
            with zipfile.ZipFile(str(zip_path), 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                for subdir in new_path.iterdir():
                    if subdir.is_dir():
                        for f in sorted(subdir.glob("stacked-16*.fits")):
                            await run.io_bound(zf.write, str(f), arcname=f.name)
            safe_log(log, f"✔️ ZIP {zip_path.name} updated")
        else:
            safe_log(log, "⚠️ No ZIP file found, ZIP not updated.")

        safe_progress(progress_bar, 80)

        safe_log(log, "ℹ️ Generating stacked.jpg and stacked_thumbnail.jpg...")
        print("ℹ️ Generating stacked.jpg and stacked_thumbnail.jpg...")
        png_images = []
        for subdir in sorted(new_path.iterdir()):
            if subdir.is_dir():
                for f in sorted(subdir.glob("stacked-16*.png")):
                    img = cv2.imread(str(f))
                    if img is not None:
                        png_images.append(img)

        stacked_path = new_path / "stacked.jpg"
        thumbnail_path = new_path / "stacked_thumbnail.jpg"

        safe_progress(progress_bar, 90)

        if not png_images:
            safe_log(log, "⚠️ No PNG images for panorama, stacked.jpg not generated.")
        elif len(png_images) == 1:
            cv2.imwrite(str(stacked_path), png_images[0])
            thumbnail = cv2.resize(png_images[0], (356, 200))
            cv2.imwrite(str(thumbnail_path), thumbnail)
            safe_log(log, "✔️ stacked.jpg and thumbnail generated from a single image")
        else:
            await generate_panorama(png_images, stacked_path, thumbnail_path, log)

        safe_log(log, "✅ Mosaic session repaired successfully!")
        print("✅ Mosaic session repaired successfully!")
        return stacked_path

    except Exception as error:
        print(f"Repair error: {error}")
        return None
# =========================================================
# MERGE LOGIC (FULL)
# =========================================================

async def merge_mosaic(old_path_str, new_path_str, log, progress_bar):
    try:
        old_path = Path(win_long_path(old_path_str))
        new_path = Path(win_long_path(new_path_str))

        if not old_path.exists() or not new_path.exists():
            safe_log(log, "❌ Session not found")
            return None

        safe_progress(progress_bar, 40)

        old_panels = sorted([d for d in old_path.iterdir() if d.is_dir()])
        new_panels = sorted([d for d in new_path.iterdir() if d.is_dir()])

        if len(old_panels) != len(new_panels):
            safe_log(log, "⚠️ Panel count mismatch")

        final_files = []

        for i, (old_panel, new_panel) in enumerate(zip(old_panels, new_panels), start=1):
            safe_log(log, f"ℹ️ Panel {i}")

            target = None
            for f in new_panel.glob("*.fits"):
                if is_valid_fits(f):
                    target = get_target_prefix(f.name)
                    break

            if not target:
                safe_log(log, f"⚠️ No target for panel {i}")
                continue

            for f in old_panel.glob("*.fits"):
                if f.name.startswith("stacked-16"):
                    continue

                if f.name.startswith("failed_"):
                    new_name = rename_failed(f.name, target)
                else:
                    new_name = rename_file(f.name, target)

                dst = new_panel / new_name
                if dst.exists():
                    dst = new_panel / f"{dst.stem}_old{dst.suffix}"

                await run.io_bound(shutil.copy2, str(f), str(dst))
                final_files.append(dst.name)

            safe_progress(progress_bar, 40 + 20 *(i/len(old_panels)))

        # JSON merge
        safe_log(log, "ℹ️ merging JSON...")

        new_json = new_path / "shotsInfo.json"
        old_json = old_path / "shotsInfo.json"

        if new_json.exists() and old_json.exists():
            with open(str(new_json)) as f:
                new_info = json.load(f)
            with open(str(old_json)) as f:
                old_info = json.load(f)

            for key in ["shotsStacked", "shotsTaken", "shotsToTake"]:
                new_info[key] += old_info.get(key, 0)

            temps = [extract_temp(f) for f in final_files if extract_temp(f) is not None]
            if temps:
                new_info["minTemp"] = min(temps)
                new_info["maxTemp"] = max(temps)

            with open(str(new_json), "w") as f:
                json.dump(new_info, f, indent=2)

        safe_progress(progress_bar, 65)

        # Build panel images
        safe_log(log, "ℹ️ Building new panel images...")
        panel_images = []

        i=1
        for old_panel, new_panel in zip(old_panels, new_panels):
            imgs = []

            for f in sorted(old_panel.glob("stacked-16*.png")):
                img = cv2.imread(str(f))
                if img is not None:
                    imgs.append(img)

            for f in sorted(new_panel.glob("stacked-16*.png")):
                img = cv2.imread(str(f))
                if img is not None:
                    imgs.append(img)

            if imgs:
                pano = await stitch_images(imgs, log)
                if pano is not None:
                    panel_images.append(pano)

            safe_progress(progress_bar, 65 + 20 *(i/len(old_panels)))
            i+=1

        stacked = new_path / "stacked.jpg"
        thumb = new_path / "stacked_thumbnail.jpg"

        if panel_images:
            safe_log(log, "ℹ️ Building panorama...")
            await generate_panorama(panel_images, stacked, thumb, log)

        safe_log(log, "✅ Merge completed")
        return stacked

    except Exception as e:
        print(f"Merge error: {e}")
        return None

