# Refactored Mosaic Tool (English version)
# Full MERGE + robust stitching + clean structure

import webview
from nicegui import ui, app, run
from pathlib import Path
import shutil
import zipfile
import cv2
import os
import re
import json
import numpy as np

from api.dwarf_backup_fct import print_log

# =========================================================
# IMAGE PROCESSING
# =========================================================

def crop_black_borders(image, tolerance=10):
    """Crop black borders by finding the largest valid rectangle."""
    try:
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


async def stitch_images(images, log):
    """Robust stitching with multiple fallbacks."""
    try:
        if len(images) == 1:
            return images[0]

        stitcher = cv2.Stitcher_create(cv2.Stitcher_PANORAMA)

        # 1. normal
        status, pano = await run.io_bound(stitcher.stitch, images)
        if status == cv2.Stitcher_OK:
            return pano

        print_log("⚠️ Stitch failed → trying reverse order", log)

        # 2. reverse
        status, pano = await run.io_bound(stitcher.stitch, list(reversed(images)))
        if status == cv2.Stitcher_OK:
            return pano

        print_log("⚠️ Stitch failed → trying 180° rotation", log)

        # 3. rotate last image
        rotated = images.copy()
        rotated[-1] = cv2.rotate(rotated[-1], cv2.ROTATE_180)

        status, pano = await run.io_bound(stitcher.stitch, rotated)
        if status == cv2.Stitcher_OK:
            return pano

        print_log("⚠️ Stitch failed → fallback to first image", log)
        return images[0]

    except Exception as e:
        print(f"Stitch error: {e}")
        return images[0] if images else None


async def generate_panorama(images, output_path, thumbnail_path, log):
    try:
        pano = await stitch_images(images, log)
        if pano is None:
            return

        pano = await run.io_bound(crop_black_borders, pano)

        cv2.imwrite(str(output_path), pano)
        cv2.imwrite(str(thumbnail_path), cv2.resize(pano, (356, 200)))

        print_log("✔️ Panorama generated", log)

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

async def repair_mosaic_session(old_session_path: str, new_session_path: str, log):
    """Repair a mosaic session by restoring missing FITS/PNG and rebuilding outputs."""
    try:
        old_path = Path(old_session_path)
        new_path = Path(new_session_path)

        if not old_path.exists() or not new_path.exists():
            print_log("❌ Session path not found", log)
            return None

        print_log("ℹ️ Replacing FITS files...", log)

        old_panels = sorted([d for d in old_path.iterdir() if d.is_dir()])
        new_panels = sorted([d for d in new_path.iterdir() if d.is_dir()])

        if len(old_panels) != len(new_panels):
            print_log("⚠️ Panel count mismatch", log)

        for panel_index, (old_panel, new_panel) in enumerate(zip(old_panels, new_panels), start=1):

            # Remove non stacked FITS
            print_log(f"ℹ️ Cleaning panel {panel_index}", log)
            for file in new_panel.glob("*.fits"):
                if not file.name.startswith("stacked-16"):
                    file.unlink()

            # Restore FITS from old session
            print_log(f"ℹ️ Restoring FITS for panel {panel_index}", log)
            for old_file in old_panel.glob("*.fits"):
                if not old_file.name.startswith("stacked-16"):
                    await run.io_bound(shutil.copy2, old_file, new_panel / old_file.name)

            # -----------------------------
            # Copy old PNGs and FITS, rebuild ZIP, generate stacked images (Repair only)
            # -----------------------------
            old_pngs = sorted(old_panel.glob("stacked-16*.png"))
            new_pngs = sorted(new_panel.glob("stacked-16*.png"))

            if len(old_pngs) != len(new_pngs):
                print_log(f"⚠️ PNG mismatch: {old_panel.name}", log)

            print_log("ℹ️ Replacing PNGs in new session with old session...", log)
            for old_file, new_file in zip(old_pngs, new_pngs):
                await run.io_bound(shutil.copy2, old_file, new_file)  # replace content, keep name

            old_stacked = sorted(old_panel.glob("stacked-16*.fits"))
            new_stacked = sorted(new_panel.glob("stacked-16*.fits"))

            if len(old_stacked) != len(new_stacked):
                print_log(f"⚠️ stacked-16 FITS mismatch: {old_panel.name}", log)

            print_log("ℹ️ Copying old stacked-16 FITS files...", log)
            for old_file, new_file in zip(old_stacked, new_stacked):
                await run.io_bound(shutil.copy2, old_file, new_file)  # copy content to existing file

            print_log("ℹ️ Copying shotsInfo.json...", log)
            old_info = old_path / "shotsInfo.json"
            new_info = new_path / "shotsInfo.json"
            if old_info.exists():
                await run.io_bound(shutil.copy2, old_info, new_info)

            print_log("ℹ️ Rebuilding ZIP stacked-16_*.zip...", log)
            print("ℹ️ Rebuilding ZIP stacked-16_*.zip...")
            zip_files = list(new_path.glob("stacked-16_*.zip"))
            if zip_files:
                zip_path = zip_files[0]
                with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                    for subdir in new_path.iterdir():
                        if subdir.is_dir():
                            for f in sorted(subdir.glob("stacked-16*.fits")):
                                await run.io_bound(zf.write, f, arcname=f.name)
                print_log(f"✔️ ZIP {zip_path.name} updated", log)
            else:
                print_log("⚠️ No ZIP file found, ZIP not updated.", log)

            print_log("ℹ️ Generating stacked.jpg and stacked_thumbnail.jpg...", log)
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

            if not png_images:
                print_log("⚠️ No PNG images for panorama, stacked.jpg not generated.", log)
            elif len(png_images) == 1:
                cv2.imwrite(str(stacked_path), png_images[0])
                thumbnail = cv2.resize(png_images[0], (356, 200))
                cv2.imwrite(str(thumbnail_path), thumbnail)
                print_log("✔️ stacked.jpg and thumbnail generated from a single image", log)
            else:
                await generate_panorama(png_images, stacked_path, thumbnail_path, log)

            print_log("✅ Mosaic session repaired successfully!", log)
            print("✅ Mosaic session repaired successfully!")
            return stacked_path

    except Exception as error:
        print(f"Repair error: {error}")
        return None
# =========================================================
# MERGE LOGIC (FULL)
# =========================================================

async def merge_mosaic(old_path_str, new_path_str, log):
    try:
        old_path = Path(old_path_str)
        new_path = Path(new_path_str)

        if not old_path.exists() or not new_path.exists():
            print_log("❌ Session not found", log)
            return None

        old_panels = sorted([d for d in old_path.iterdir() if d.is_dir()])
        new_panels = sorted([d for d in new_path.iterdir() if d.is_dir()])

        if len(old_panels) != len(new_panels):
            print_log("⚠️ Panel count mismatch", log)

        final_files = []

        for i, (old_panel, new_panel) in enumerate(zip(old_panels, new_panels), start=1):
            print_log(f"ℹ️ Panel {i}", log)

            target = None
            for f in new_panel.glob("*.fits"):
                if is_valid_fits(f):
                    target = get_target_prefix(f.name)
                    break

            if not target:
                print_log(f"⚠️ No target for panel {i}", log)
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

                await run.io_bound(shutil.copy2, f, dst)
                final_files.append(dst.name)

        # JSON merge
        new_json = new_path / "shotsInfo.json"
        old_json = old_path / "shotsInfo.json"

        if new_json.exists() and old_json.exists():
            with open(new_json) as f:
                new_info = json.load(f)
            with open(old_json) as f:
                old_info = json.load(f)

            for key in ["shotsStacked", "shotsTaken", "shotsToTake"]:
                new_info[key] += old_info.get(key, 0)

            temps = [extract_temp(f) for f in final_files if extract_temp(f) is not None]
            if temps:
                new_info["minTemp"] = min(temps)
                new_info["maxTemp"] = max(temps)

            with open(new_json, "w") as f:
                json.dump(new_info, f, indent=2)

        # Build panel images
        panel_images = []

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

        stacked = new_path / "stacked.jpg"
        thumb = new_path / "stacked_thumbnail.jpg"

        if panel_images:
            await generate_panorama(panel_images, stacked, thumb, log)

        print_log("✅ Merge completed", log)
        return stacked

    except Exception as e:
        print(f"Merge error: {e}")
        return None


# =========================================================
# UI
# =========================================================

mode = "Repair"

with ui.card().classes("w-full p-4"):

    mode_toggle = ui.toggle(['Repair', 'Merge'], value=mode, on_change=lambda: switch_mode()).classes("col-span-1 justify-self-center")

    main_label = ui.label("Select the failed session and the new session.")

    with ui.row():
        old_input = ui.input(label="Failed Session", placeholder="Path to the failed session").classes("min-w-[800px] overflow-x-auto whitespace-nowrap")
        ui.button("Choose Failed session", on_click=lambda: select_source_folder("old"))

    with ui.row():
        new_input = ui.input(label="New session", placeholder="Path to the new session").classes("min-w-[800px] overflow-x-auto whitespace-nowrap")
        ui.button("Choose new session", on_click=lambda: select_source_folder("new"))

with ui.card().classes("w-full p-4 mt-2 items-center"):
    action_button = ui.button("Repair Mosaic Session", on_click=lambda: run_action())

    log_ui = ui.log()
    image_ui = ui.image("")

    def switch_mode():
        mode = mode_toggle.value

        if (mode=="Repair"):
            main_label.text = "Select the failed session and the new session"
            action_button.text = "Repair the Mosaic session"
            old_input.label = "Failed session"
            old_input.placeholder = "Path to the failed session"
        else:
            main_label.text = "Select the session to merge and the new session"
            action_button.text = "Merge the 2 Mosaic sessions"
            old_input.label = "Session to merge"
            old_input.placeholder = "Path to the session to merge" 

    async def run_action():
        mode = mode_toggle.value

        if (mode=="Repair"):
            result = await repair_callback()
        else:
            result = await merge_callback()

        if result and result.exists():
            image_ui.set_source(result)
            image_ui.force_reload()

    async def repair_callback():
        print_log( "Starting Repair...", log_ui)
        result = await repair_mosaic_session(old_input.value, new_input.value, log_ui)
        return result

    async def merge_callback():
        print_log( "Starting Merge...", log_ui)
        result = await merge_mosaic(old_input.value, new_input.value, log_ui)
        return result

    async def select_source_folder(source = "old"):
        """Open folder selection dialog."""
        if hasattr(webview, 'FileDialog'):
            folder_mode = webview.FileDialog.FOLDER
        else:
            folder_mode = webview.FOLDER_DIALOG

        folder = await app.native.main_window.create_file_dialog(folder_mode, allow_multiple=False)

        if folder:
            ui.notify(folder[0])
            folder = os.path.normpath(folder[0])
        print (folder)
        if source == "old":
            old_input.set_value(folder)
        else:
            new_input.set_value(folder)
            

ui.run(title="Mosaic Tool", native=True, window_size=(1200, 1024),reload=False)