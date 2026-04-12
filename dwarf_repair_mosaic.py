import webview
from nicegui import ui, app, run
from pathlib import Path
import shutil
import zipfile
import cv2
import os
import re
import time 
import json
import numpy as np

from api.dwarf_backup_fct import safe_print, print_log

# --------------
# REPAIR ACTION
# --------------

def crop_black_borders_internal(image, tol=10):
    try: 
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        mask = (gray > tol).astype(np.uint8) * 255

        # Érosion pour nettoyer les artefacts de bord
        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.erode(mask, kernel, iterations=2)

        h, w = mask.shape

        # Pour chaque ligne, trouver x_min et x_max valides
        # Puis chercher le plus grand rectangle dont TOUTES les lignes
        # sont entièrement dans le masque.

        # Hauteur max du rectangle inscrit via l'algo "largest rectangle in histogram"
        def largest_rect_in_histogram(hist):
            stack = []
            max_area = 0
            best = (0, 0, 0)  # (x, width, height)
            for i, h in enumerate(hist):
                start = i
                while stack and stack[-1][1] > h:
                    x, height = stack.pop()
                    width = i - x
                    if width * height > max_area:
                        max_area = width * height
                        best = (x, width, height)
                    start = x
                stack.append((start, h))
            for x, height in stack:
                width = len(hist) - x
                if width * height > max_area:
                    max_area = width * height
                    best = (x, width, height)
            return best  # (x_start, width, height)

        # Construire l'histogramme cumulatif vertical
        # hist[col] = nombre de lignes consécutives valides depuis le bas
        best_area = 0
        best_rect = (0, 0, w, h)

        # On fait glisser une fenêtre de y vers le bas
        hist = np.zeros(w, dtype=np.int32)
        best_area = 0
        best_y = 0
        best_x, best_w, best_h = 0, w, h

        for y in range(h):
            # Met à jour l'histogramme : si pixel valide, +1, sinon reset
            for x in range(w):
                if mask[y, x] > 0:
                    hist[x] += 1
                else:
                    hist[x] = 0

            x_start, rect_w, rect_h = largest_rect_in_histogram(hist.tolist())
            area = rect_w * rect_h
            if area > best_area:
                best_area = area
                best_y = y - rect_h + 1
                best_x = x_start
                best_w = rect_w
                best_h = rect_h

        if best_area == 0:
            print("Crop Image : aucun rectangle valide trouvé")
            return image

        cropped = image[best_y:best_y + best_h, best_x:best_x + best_w]
        print(f"Crop : rect trouvé -> x={best_x}, y={best_y}, w={best_w}, h={best_h}")
        return cropped
    except Exception as e:
        print(f"Error during Crop function, {e}")
        return image
        
async def create_panorama ( png_images, stacked_path, thumbnail_path, log ):
    try: 
        stitcher = cv2.Stitcher_create(cv2.Stitcher_PANORAMA)
        status, pano = stitcher.stitch(png_images)
        if status != cv2.Stitcher_OK:
            print_log(f"⚠️ Stitching échoué avec le code {status}", log)
            print(f"⚠️ Stitching échoué avec le code {status}")
        else:
            pano_cropped = await run.io_bound ( crop_black_borders_internal, pano, tol=10)
            cv2.imwrite(str(stacked_path), pano_cropped)
            thumbnail = cv2.resize(pano_cropped, (356, 200))
            cv2.imwrite(str(thumbnail_path), thumbnail)
            print_log("✔️ stacked.jpg et stacked_thumbnail.jpg générés automatiquement", log)
            print("✔️ stacked.jpg et stacked_thumbnail.jpg générés automatiquement")
    except Exception as e:
        print(f"Error during create_panorama function, {e}")
    
async def fix_mosaic_one_click(old_session: str, new_session: str, log):
    try :
        old_path = Path(old_session)
        new_path = Path(new_session)

        if not old_path.exists() or not new_path.exists():
            print_log("❌ Ancienne ou nouvelle session introuvable!", log)
            return None

        print_log("ℹ️ Remplacement des stacked-16*.fits...", log)
        print("ℹ️ Remplacement des stacked-16*.fits...")
        old_subdirs = sorted([d for d in old_path.iterdir() if d.is_dir()])
        new_subdirs = sorted([d for d in new_path.iterdir() if d.is_dir()])

        if len(old_subdirs) != len(new_subdirs):
            print_log("⚠️ Nombre de sous-dossiers différent entre anciennes et nouvelles sessions", log)

        panel = 0
        for old_subdir, new_subdir in zip(old_subdirs, new_subdirs):
            panel += 1

            # -----------------------------
            # 1️⃣ Supprimer les FITS non stacked-16 dans la nouvelle session
            # -----------------------------
            print_log(f"ℹ️ Suppression fits nouvelle session pour le panel {panel}...", log)
            for f in new_subdir.glob("*.fits"):
                if not f.name.startswith("stacked-16"):
                    f.unlink()  # suppression

            # -----------------------------
            # 2️⃣ Copier les FITS NON stacked-16 depuis l'ancienne session
            # -----------------------------
            print_log(f"ℹ️ Copie fits ancienne session... pour le panel {panel}", log)
            for old_file in old_subdir.glob("*.fits"):
                if not old_file.name.startswith("stacked-16"):
                    target_file = new_subdir / old_file.name
                    await run.io_bound(shutil.copy2,old_file, target_file)

        old_pngs = sorted(old_subdir.glob("stacked-16*.png"))
        new_pngs = sorted(new_subdir.glob("stacked-16*.png"))

        if len(old_pngs) != len(new_pngs):
            print_log(f"⚠️ Mismatch PNG : {old_subdir.name}", log)

        print_log("ℹ️ Remplacement png par ancienne session...", log)
        for old_file, new_file in zip(old_pngs, new_pngs):
            await run.io_bound( shutil.copy2,old_file, new_file)  # 👈 remplace contenu, garde le nom

        old_stacked = sorted(old_subdir.glob("stacked-16*.fits"))
        new_stacked = sorted(new_subdir.glob("stacked-16*.fits"))

        if len(old_stacked) != len(new_stacked):
            print_log(f"⚠️ Mismatch stacked-16 : {old_subdir.name}", log)

        print_log("ℹ️ Copie des ancien Fits Stacked-16 ...", log)
        for old_file, new_file in zip(old_stacked, new_stacked):
            await run.io_bound( shutil.copy2, old_file, new_file)
            # 👈 copie contenu vers fichier existant

        print_log("ℹ️ Copie shotsInfo.json...", log)
        old_info = old_path / "shotsInfo.json"
        new_info = new_path / "shotsInfo.json"
        if old_info.exists():
            await run.io_bound(shutil.copy2, old_info, new_info)

        print_log("ℹ️ Reconstruction du ZIP stacked-16_*.zip...", log)
        print("ℹ️ Reconstruction du ZIP stacked-16_*.zip...")
        zip_files = list(new_path.glob("stacked-16_*.zip"))
        if zip_files:
            zip_path = zip_files[0]
            with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                for subdir in new_path.iterdir():
                    if subdir.is_dir():
                        for f in sorted(subdir.glob("stacked-16*.fits")):
                            await run.io_bound(zf.write,f, arcname=f.name)
            print_log(f"✔️ ZIP {zip_path.name} mis à jour", log)
        else:
            print_log("⚠️ Aucun fichier ZIP trouvé, ZIP non mis à jour.", log)

        print_log("ℹ️ Génération du panorama stacked.jpg et stacked_thumbnail.jpg...", log)
        print("ℹ️ Génération du panorama stacked.jpg et stacked_thumbnail.jpg...")
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
            print_log("⚠️ Aucune image PNG pour panorama, stacked.jpg non généré.", log)
        elif len(png_images) == 1:
            cv2.imwrite(str(stacked_path), png_images[0])
            thumbnail = cv2.resize(png_images[0], (356, 200))
            cv2.imwrite(str(thumbnail_path), thumbnail)
            print_log("✔️ stacked.jpg et thumbnail générés à partir d'une seule image", log)
        else:
            await create_panorama( png_images, stacked_path, thumbnail_path, log)

        print_log("✅ Session Mosaic réparée avec succès !", log)
        print("✅ Session Mosaic réparée avec succès !")
        return stacked_path

    except:
        print(f"Error during Merging Mosaic function, {e}")
        return None
# -------------
# MERGE ACTION
# -------------

def extract_temp(filename):
    if filename.startswith("stacked-16"):
        return None

    match = re.search(r'_(-?\d+)C', filename)
    if match:
        return int(match.group(1))
    return None

def strip_panel_suffix(target):
    return re.sub(r'\(\d+\)$', '', target).strip()
    
def get_target_prefix(filename):
    return filename.split("_")[0]
    
def is_valid_fits(f):
    return (
        f.name.endswith(".fits")
        and not f.name.startswith("stacked-16")
        and not f.name.startswith("failed_")
    )

def detect_target_for_panel(subdir):
    for f in subdir.glob("*.fits"):
        if is_valid_fits(f):
            return get_target_prefix(f.name)
    return None

def rename_with_new_target(filename, new_target):
    parts = filename.split("_", 1)
    if len(parts) < 2:
        return filename
    return f"{new_target}_{parts[1]}"

def rename_failed_file(filename, new_target):
    # enlever "failed_"
    rest = filename[len("failed_"):]
    
    parts = rest.split("_", 1)
    if len(parts) < 2:
        return filename
    
    return f"failed_{new_target}_{parts[1]}"

def compute_min_max_temp(fits_files):
    temps = []

    for f in fits_files:
        t = extract_temp(f)
        if t is not None:
            temps.append(t)

    if not temps:
        return None, None

    return min(temps), max(temps)
    
def merge_shots_info(new_info, old_info, log):
    fields = [
        ("mosaicInfo", "subviewShotsToTake"),
        (None, "shotsStacked"),
        (None, "shotsTaken"),
        (None, "shotsToTake"),
    ]

    for parent, key in fields:
        if parent:
            new_info[parent][key] += old_info[parent][key]
            print_log(f"ℹ️ Mise à jour Json : {key} : {new_info[parent][key]}", log)
        else:
            new_info[key] += old_info[key]
            print_log(f"ℹ️ Mise à jour Json : {key} : {new_info[key]}", log)

    return new_info

async def stitch_panel(png_files, png_files_reverse, log):
    try:
        if len(png_files) == 1:
            return cv2.imread(str(png_files[0]))

        img1 = cv2.imread(str(png_files[0]))
        print_log(f" img1 : {str(png_files[0])}", log)
        img2 = cv2.imread(str(png_files[1]))
        print_log(f" img2 : {str(png_files[1])}", log)

        stitcher = cv2.Stitcher_create(cv2.Stitcher_PANORAMA)

        # 1️⃣ Tentative normale
        status, pano = await run.io_bound(stitcher.stitch, [img1, img2])
        del img1, img2
        if status == cv2.Stitcher_OK:
            return pano

        print_log(f"⚠️ Stitch échoué → tentative avec rotation 180° sur la seconde image", log)

        # 2️⃣ Rotation 180° sur la seconde image uniquement
        print_log(f" img2 rot : {str(png_files_reverse[1])}", log)
        img1_test = cv2.imread(str(png_files_reverse[0]))
        img2_test  = cv2.imread(str(png_files_reverse[1]))
        img2_rot = cv2.rotate(img2_test, cv2.ROTATE_180)
        del img2_test
        status, pano = await run.io_bound(stitcher.stitch, [img1_test, img2_rot])
        del img2_rot
        if status == cv2.Stitcher_OK:
            print_log("✔️ Stitch réussi après rotation 180° sur la seconde image", log)
            del img1_test
            return pano

        print_log(f"⚠️ Stitch échoué aprés rotation 180°, renvoie de la 1ère image", log)
        return img1_test

    except Exception as e:
        print(f"Error during stitch_panel function, {e}")

        if len(png_files) == 0:
           return None
        if len(png_files) == 1:
            return cv2.imread(str(png_files[0]))
        else:
            return cv2.imread(str(png_files[1]))

async def build_panel_images(old_path, new_path, log):
    panel_images = []

    old_subdirs = sorted([d for d in old_path.iterdir() if d.is_dir()])
    new_subdirs = sorted([d for d in new_path.iterdir() if d.is_dir()])

    for i, (old_subdir, new_subdir) in enumerate(zip(old_subdirs, new_subdirs), start=1):

        png_files = []
        png_files_reverse = []
      
        # normal
        png_files += sorted(old_subdir.glob("stacked-16*.png"))
        png_files += sorted(new_subdir.glob("stacked-16*.png"))

        # Reverse : old(i) + new(n-i)
        new_subdir_reversed = new_subdirs[-(i)]
        png_files_reverse += sorted(old_subdir.glob("stacked-16*.png"))
        png_files_reverse += sorted(new_subdir_reversed.glob("stacked-16*.png"))         

        if not png_files:
            print_log(f"⚠️ Panel {i} vide", log)
            continue

        print_log(f"ℹ️ Panel {i} → {len(png_files)} images à stitch", log)

        panel_img = await stitch_panel(png_files, png_files_reverse, log)

        if panel_img is not None:
            panel_images.append(panel_img)

    return panel_images

async def merge_mosaic_one_click(old_session: str, new_session: str, log):
    try: 
        old_path = Path(old_session)
        new_path = Path(new_session)

        if not old_path.exists() or not new_path.exists():
            print_log("❌ Ancienne ou nouvelle session introuvable!", log)
            return None

        old_subdirs = sorted([d for d in old_path.iterdir() if d.is_dir()])
        new_subdirs = sorted([d for d in new_path.iterdir() if d.is_dir()])

        if len(old_subdirs) != len(new_subdirs):
            print_log("⚠️ Nombre de sous-dossiers différent entre anciennes et nouvelles sessions", log)

        panel = 0
        
        # 1. détecter target de la nouvelle session
        new_target = None
        for new_subdir in new_subdirs:
            for f in new_subdir.glob("*.fits"):
                if is_valid_fits(f):
                    new_target = get_target_prefix(f.name)
                    break
            if new_target:
                break

        if new_target:
            global_target = strip_panel_suffix(new_target)
            print_log(f"ℹ️ Target globale : {global_target}", log)
            
            if not new_target:
                print_log("? Impossible de détecter la target", log)
                return

        # 2. copier anciens FITS
        panel = 0
        final_fits = []

        for old_subdir, new_subdir in zip(old_subdirs, new_subdirs):
            panel += 1

            print_log(f"ℹ️ Copie fits ancienne session... pour le panel {panel}", log)
            # 👉 target spécifique à CE panel
            new_target = detect_target_for_panel(new_subdir)

            if not new_target:
                print_log(f"⚠️ Impossible de détecter la target pour panel {panel}", log)
                continue

            print_log(f"ℹ️ Target panel {panel} : {new_target}", log)
        
            for f in old_subdir.glob("*.fits"):
                if f.name.startswith("stacked-16"):
                    continue

                old_name = f.name

                # ------------------------
                # CAS FAILED
                # ------------------------
                if old_name.startswith("failed_"):
                    new_name = rename_failed_file(old_name, new_target)

                else:

                    old_target = get_target_prefix(old_name)
                    new_name = old_name
                    if old_target != new_target:
                        new_name = rename_with_new_target(old_name, new_target)

                src = f
                dst = new_subdir / new_name

                if dst.exists():
                    dst = new_subdir / f"{dst.stem}_old{dst.suffix}"

                await run.io_bound(shutil.copy2, src, dst)
                final_fits.append(dst.name)

        # 3. update shotsInfo
        with open(os.path.join(new_path, "shotsInfo.json")) as f:
            new_info = json.load(f)

        with open(os.path.join(old_path, "shotsInfo.json")) as f:
            old_info = json.load(f)

        new_info = merge_shots_info(new_info, old_info, log)

        # 4. update températures
        min_t, max_t = compute_min_max_temp(final_fits)

        if min_t is not None:
            new_info["minTemp"] = min_t
            print_log(f"ℹ️ Temperature Minimale : {min_t}", log)
        if max_t is not None:
            new_info["maxTemp"] = max_t
            print_log(f"ℹ️ Temperature Maximale : {max_t}", log)

        # 5. sauvegarde json
        with open(os.path.join(new_path, "shotsInfo.json"), "w") as f:
            json.dump(new_info, f, indent=2)

        # 6. assemblage des pngs ancienne session et nouvelles
        print_log("ℹ️ Génération du panorama stacked.jpg et stacked_thumbnail.jpg...", log)
        print("ℹ️ Génération du panorama stacked.jpg et stacked_thumbnail.jpg...")

        panel_images = await build_panel_images(old_path, new_path, log)

        stacked_path = new_path / "stacked.jpg"
        thumbnail_path = new_path / "stacked_thumbnail.jpg"

        if not panel_images:
            print_log("⚠️ Aucune image PNG pour panorama, stacked.jpg non généré.", log)
        elif len(panel_images) == 1:
            cv2.imwrite(str(stacked_path), panel_images[0])
            thumbnail = cv2.resize(panel_images[0], (356, 200))
            cv2.imwrite(str(thumbnail_path), thumbnail)
            print_log("✔️ stacked.jpg et thumbnail générés à partir d'une seule image", log)
        else:
            await create_panorama( panel_images, stacked_path, thumbnail_path, log)

        print_log("✅ Session Mosaic mergée avec succès !", log)
        print("✅ Session Mosaic mergée avec succès !")
        return stacked_path

    except:
        print(f"Error during Merging Mosaic function, {e}")

# -------------------------------
# Interface NiceGUI
# -------------------------------
mode = "Repair"

with ui.card().tight().classes("w-full p-4 mt-2 min-w-[1200px] items-center"):

    mode_toggle = ui.toggle(['Repair', 'Megastack'], value=mode, on_change=lambda: switch_mode()).classes("col-span-1 justify-self-center")

    mode_label = ui.label("Sélectionnez la session en erreur et la nouvelle session")

    with ui.row():
        old_dir = ui.input(label="Session en erreur", placeholder="Chemin vers la session échouée").classes("min-w-[800px] overflow-x-auto whitespace-nowrap")
        ui.button("Choisir ancienne session", on_click=lambda: select_source_folder("old"))

    with ui.row():
        new_dir = ui.input(label="Nouvelle session", placeholder="Chemin vers la nouvelle session").classes("min-w-[800px] overflow-x-auto whitespace-nowrap")
        ui.button("Choisir nouvelle session", on_click=lambda: select_source_folder("new"))

with ui.card().classes("w-full p-4 mt-2 items-center"):
    mode_button = ui.button("Réparer la session Mosaic", on_click=lambda: action_callback())

    log = ui.log(max_lines=12).classes('w-full').style('height: 250px; overflow: hidden;')

    stacked_img = ui.image("").classes('w-720')

    def switch_mode():
        mode = mode_toggle.value

        if (mode=="Repair"):
            mode_label.text = "Sélectionnez la session en erreur et la nouvelle session"
            mode_button.text = "Réparer la session Mosaic"
            old_dir.label = "Session en erreur"
            old_dir.placeholder = "Chemin vers la session échouée"
        else:
            mode_label.text = "Sélectionnez la session à fusionner et la nouvelle session"
            mode_button.text = "Fusionner les 2 sessions Mosaic"
            old_dir.label = "Session à fusionner"
            old_dir.placeholder = "Chemin vers la session à fusionner"
 
    async def action_callback():
        mode = mode_toggle.value

        if (mode=="Repair"):
            await repair_callback()
        else:
            await merge_callback()

    async def repair_callback():
        print_log( "Starting Repair...", log)
        stacked_path = await fix_mosaic_one_click(old_dir.value, new_dir.value, log)
        print_log( f"Image Finale : {stacked_path}", log)
        print( f"Image Finale : {stacked_path}")
        if stacked_path.exists():
            stacked_img.set_source(stacked_path)
            stacked_img.force_reload()

    async def merge_callback():
        print_log( "Starting Merge...", log)
        stacked_path = await merge_mosaic_one_click(old_dir.value, new_dir.value, log)
        print_log( f"Image Finale : {stacked_path}", log)
        print( f"Image Finale : {stacked_path}")
        if stacked_path.exists():
            stacked_img.set_source(stacked_path)
            stacked_img.force_reload()

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
            old_dir.set_value(folder)
        else:
            new_dir.set_value(folder)
            
        print(folder)
       


ui.run(title="Mosaic Repair Tool", native=True, window_size=(1200, 1024),reload=False)