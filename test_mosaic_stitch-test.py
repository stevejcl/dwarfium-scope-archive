"""
Test autonome de la logique de stitching mosaique.
Aucune dependance a NiceGUI ou au reste du programme.

Usage :
    python test_mosaic_stitch.py
    python test_mosaic_stitch.py --images chemin/img1.png chemin/img2.png
    python test_mosaic_stitch.py --images img1.png img2.png img3.png img4.png
    python test_mosaic_stitch.py --images "C:/tres/long/chemin/panel1.png" "C:/tres/long/chemin/panel2.png"
"""

import sys
import argparse
import platform
import numpy as np
import cv2

import astroalign as aa

# =========================================================
# CODE EXTRAIT DE dwarf_backup_fct.py
# =========================================================

def win_long_path(path: str) -> str:
    """
    Prefixe les chemins Windows avec \\?\\ pour depasser la limite MAX_PATH (260 cars).
    Sans effet sur Linux/macOS.
    """
    if platform.system() != "Windows":
        return path
    path = path.replace("/", "\\")
    if not path.startswith("\\\\?\\"):
        path = "\\\\?\\" + path
    return path


# =========================================================
# CODE EXTRAIT DE dwarf_backup_fct_mosaic.py
# =========================================================

def get_inverted_order(images: list) -> list:
    n = len(images)
    if n == 2:
        return [images[1], images[0]]
    elif n == 4:
        return [images[2], images[3], images[0], images[1]]
    else:
        return list(reversed(images))


def crop_black_borders(image, tolerance=10):
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
            stack, max_area, best_rect = [], 0, (0, 0, 0)
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
        print(f"  Crop error: {e}")
        return image

def png16_to_uint8(img):
    """
    Convertit un PNG 16-bit en 8-bit pour OpenCV.
    """
    if img.dtype == np.uint16:
        img = img.astype(np.float32)
        img = (img / 65535.0) * 255.0  # normalisation
        img = img.astype(np.uint8)
    return img
    

def load_image(path: str):
    """Charge une image en gerant les noms longs Windows via win_long_path."""

    safe_path = win_long_path(path)
    img = cv2.imread(safe_path, cv2.IMREAD_UNCHANGED)  # garde 16-bit
    if img is None:
        raise ValueError(f"Impossible de charger {path}")

    # convertir 16-bit → 8-bit
    img = png16_to_uint8(img)

    # si grayscale → BGR
    if len(img.shape) == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

    return img

def stitch_with_transform1(images, feather_size=31, label: str = ""):
    """
    Crée une mosaïque à partir d'une liste d'images PNG/FITS 16 bits couleur.
    Gère correctement les zones de recouvrement et applique un fondu local (feathering).

    Parameters
    ----------
    images : list of ndarray
        Liste d'images couleur (H,W,3), dtype=uint16 ou float64.
    feather_size : int
        Taille du GaussianBlur pour adoucir les bords.
    label : str
        Label optionnel pour debug/log.
    
    Returns
    -------
    result_uint8 : ndarray
        Image finale uint8 (0-255) fusionnée.
    """
    # --- normaliser toutes les images en float64 [0,1] ---
    images_f = [img.astype(np.float64)/65535.0 for img in images]

    # --- image de référence ---
    ref_color = images_f[0]
    h, w, _ = ref_color.shape

    # --- canvas 3x taille pour gérer les translations ---
    canvas = np.zeros((h*3, w*3, 3), dtype=np.float64)
    weight = np.zeros((h*3, w*3), dtype=np.float64)
    offset_y, offset_x = h, w

    # placer l'image de référence
    canvas[offset_y:offset_y+h, offset_x:offset_x+w] += ref_color
    weight[offset_y:offset_y+h, offset_x:offset_x+w] += 1

    # --- traiter les autres images ---
    for idx, img_color in enumerate(images_f[1:], start=1):
        try:
            # convertir en gris pour astroalign
            img_gray = cv2.cvtColor((img_color*65535).astype(np.uint16), cv2.COLOR_BGR2GRAY)
            ref_gray = cv2.cvtColor((ref_color*65535).astype(np.uint16), cv2.COLOR_BGR2GRAY)

            # garder pixels brillants pour améliorer le calcul du transform
            thresh_src = np.percentile(img_gray, 95)
            thresh_ref = np.percentile(ref_gray, 95)
            img_adj = np.where(img_gray >= thresh_src, img_gray, 0)
            ref_adj = np.where(ref_gray >= thresh_ref, ref_gray, 0)

            # --- calcul du transform ---
            transf, _ = aa.find_transform(img_adj, ref_adj)

            # --- appliquer le transform sur chaque canal ---
            warped_channels = []
            for c in range(3):
                warped_c = np.zeros((canvas.shape[0], canvas.shape[1]), dtype=np.float64)
                warped_c = aa.apply_transform(transf, img_color[..., c], warped_c)
                if isinstance(warped_c, tuple):
                    warped_c = warped_c[0]  # cas où apply_transform renvoie un tuple
                warped_channels.append(warped_c)
            warped_color = np.stack(warped_channels, axis=-1)

            # --- masque et feathering ---
            epsilon = 1e-6
            mask = (warped_color.max(axis=2) > epsilon).astype(np.float64)
            mask = cv2.GaussianBlur(mask, (feather_size, feather_size), 0)
            mask_3d = mask[..., None]

            # --- fusion avec le canvas (fondu local) ---
            canvas[offset_y:offset_y+h, offset_x:offset_x+w] = \
                canvas[offset_y:offset_y+h, offset_x:offset_x+w] * (1 - mask_3d[offset_y:offset_y+h, offset_x:offset_x+w]) + \
                warped_color[offset_y:offset_y+h, offset_x:offset_x+w] * mask_3d[offset_y:offset_y+h, offset_x:offset_x+w]

            weight[offset_y:offset_y+h, offset_x:offset_x+w] += mask[offset_y:offset_y+h, offset_x:offset_x+w]

        except Exception as e:
            print(f"Align failed on image {idx}:", e)

    # --- normalisation finale ---
    weight_safe = np.maximum(weight, 1e-6)
    result = canvas / weight_safe[..., None]
    result = np.clip(result, 0, 1)
    result_uint8 = (result * 255).astype(np.uint8)

    return result_uint8, "ordre naturel"


# visu double image du panneau central

def stitch_with_transform_0(images, label: str = "", feather_size=31):
    """
    Crée une mosaïque à partir d'une liste d'images PNG 16 bits couleur.
    
    images: list of ndarray (H,W,3), dtype=uint16 ou float32/64
    feather_size: int, taille du GaussianBlur pour adoucir les bords
    """
    # --- convertir toutes les images en float64 ---
    images_f = [img.astype(np.float64) for img in images]

    # --- image de référence ---
    ref_color = images_f[0]
    h, w, _ = ref_color.shape

    # --- estimer les translations max pour dimensionner le canvas ---
    translations = [(0, 0)]
    for img in images_f[1:]:
        img_gray = cv2.cvtColor(img.astype(np.uint16), cv2.COLOR_BGR2GRAY)
        ref_gray = cv2.cvtColor(ref_color.astype(np.uint16), cv2.COLOR_BGR2GRAY)

        # garder seulement les pixels brillants pour le calcul
        thresh_src = np.percentile(img_gray, 95)
        thresh_ref = np.percentile(ref_gray, 95)
        img_adj = np.where(img_gray >= thresh_src, img_gray, 0)
        ref_adj = np.where(ref_gray >= thresh_ref, ref_gray, 0)

        try:
            transf, (src_pts, tgt_pts) = aa.find_transform(img_adj, ref_adj)
            dx = int(np.round(np.mean(tgt_pts[:,0] - src_pts[:,0])))
            dy = int(np.round(np.mean(tgt_pts[:,1] - src_pts[:,1])))
            translations.append((dy, dx))
        except Exception as e:
            print("Align failed during translation estimate:", e)
            translations.append((0,0))

    ys = [dy for dy, dx in translations]
    xs = [dx for dy, dx in translations]
    min_y, max_y = int(np.min(ys)), int(np.max(ys))
    min_x, max_x = int(np.min(xs)), int(np.max(xs))

    canvas_h = h + (max_y - min_y)
    canvas_w = w + (max_x - min_x)

    # --- canvas final ---
    canvas = np.zeros((canvas_h, canvas_w, 3), dtype=np.float64)
    weight = np.zeros((canvas_h, canvas_w), dtype=np.float64)

    offset_y = -min_y
    offset_x = -min_x

    # --- placer image de référence ---
    canvas[offset_y:offset_y+h, offset_x:offset_x+w] = ref_color
    weight[offset_y:offset_y+h, offset_x:offset_x+w] = 1

    # --- traiter les autres images ---
    for idx, img in enumerate(images_f[1:], start=1):
        try:
            img_gray = cv2.cvtColor(img.astype(np.uint16), cv2.COLOR_BGR2GRAY)
            ref_gray = cv2.cvtColor(ref_color.astype(np.uint16), cv2.COLOR_BGR2GRAY)

            # pixels brillants
            thresh_src = np.percentile(img_gray, 95)
            thresh_ref = np.percentile(ref_gray, 95)
            img_adj = np.where(img_gray >= thresh_src, img_gray, 0)
            ref_adj = np.where(ref_gray >= thresh_ref, ref_gray, 0)

            # calcul du transform
            transf, _ = aa.find_transform(img_adj, ref_adj)

            # --- appliquer le transform sur le canvas final ---
            warped_channels = []
            for c in range(3):
                warped_c = np.zeros((canvas_h, canvas_w), dtype=np.float64)
                warped_c = aa.apply_transform(transf, img[..., c], warped_c)
                if isinstance(warped_c, tuple):
                    warped_c = warped_c[0]
                warped_channels.append(warped_c)
            warped_color = np.stack(warped_channels, axis=-1)

            # --- masque et feathering ---
            epsilon = 1e-6
            mask = (warped_color.max(axis=2) > epsilon).astype(np.float64)
            mask = cv2.GaussianBlur(mask, (feather_size, feather_size), 0)
            mask_3d = mask[..., None]

            # --- ajouter sur canvas ---
            canvas += warped_color * mask_3d
            weight += mask

        except Exception as e:
            print(f"Align failed on image {idx}:", e)

    # --- normalisation finale ---
    weight_safe = np.maximum(weight, 1e-6)
    result = canvas / weight_safe[..., None]

    # rééchelle pour visualisation
    max_val = np.max(result)
    if max_val > 0:
        result /= max_val

    result_uint8 = (result*255).astype(np.uint8)
    return result_uint8, label

# pas de visu du panneau 1
    
def stitch_with_transform(images, label: str = ""):
    feather_size=31
    """
    Crée une mosaïque à partir d'une liste d'images PNG 16 bits couleur,
    en gérant correctement les zones de recouvrement.
    
    images: list of ndarray (H,W,3), dtype=uint16 ou float32/64
    feather_size: int, taille du GaussianBlur pour adoucir les bords
    """
    # --- convertir toutes les images en float64 ---
    images_f = [img.astype(np.float64) for img in images]

    # --- image de référence ---
    ref_color = images_f[0]
    h, w, _ = ref_color.shape

    # --- estimer translations max pour dimensionner le canvas ---
    translations = [(0, 0)]
    for img in images_f[1:]:
        img_gray = cv2.cvtColor(img.astype(np.uint16), cv2.COLOR_BGR2GRAY)
        ref_gray = cv2.cvtColor(ref_color.astype(np.uint16), cv2.COLOR_BGR2GRAY)

        thresh_src = np.percentile(img_gray, 95)
        thresh_ref = np.percentile(ref_gray, 95)
        img_adj = np.where(img_gray >= thresh_src, img_gray, 0)
        ref_adj = np.where(ref_gray >= thresh_ref, ref_gray, 0)

        try:
            transf, (src_pts, tgt_pts) = aa.find_transform(img_adj, ref_adj)
            dx = int(np.round(np.mean(tgt_pts[:,0] - src_pts[:,0])))
            dy = int(np.round(np.mean(tgt_pts[:,1] - src_pts[:,1])))
            translations.append((dy, dx))
        except Exception as e:
            print("Align failed during translation estimate:", e)
            translations.append((0,0))

    ys = [dy for dy, dx in translations]
    xs = [dx for dy, dx in translations]
    min_y, max_y = int(np.min(ys)), int(np.max(ys))
    min_x, max_x = int(np.min(xs)), int(np.max(xs))

    canvas_h = h + (max_y - min_y)
    canvas_w = w + (max_x - min_x)

    # --- canvas final ---
    canvas = np.zeros((canvas_h, canvas_w, 3), dtype=np.float64)

    offset_y = -min_y
    offset_x = -min_x

    # --- placer image de référence ---
    canvas[offset_y:offset_y+h, offset_x:offset_x+w] = ref_color

    # --- traiter les autres images ---
    for idx, img in enumerate(images_f[1:], start=1):
        try:
            img_gray = cv2.cvtColor(img.astype(np.uint16), cv2.COLOR_BGR2GRAY)
            ref_gray = cv2.cvtColor(ref_color.astype(np.uint16), cv2.COLOR_BGR2GRAY)

            # pixels brillants
            thresh_src = np.percentile(img_gray, 95)
            thresh_ref = np.percentile(ref_gray, 95)
            img_adj = np.where(img_gray >= thresh_src, img_gray, 0)
            ref_adj = np.where(ref_gray >= thresh_ref, ref_gray, 0)

            # calcul du transform
            transf, _ = aa.find_transform(img_adj, ref_adj)

            # --- appliquer le transform sur le canvas final ---
            warped_channels = []
            for c in range(3):
                warped_c = np.zeros((canvas_h, canvas_w), dtype=np.float64)
                warped_c = aa.apply_transform(transf, img[..., c], warped_c)
                if isinstance(warped_c, tuple):
                    warped_c = warped_c[0]
                warped_channels.append(warped_c)
            warped_color = np.stack(warped_channels, axis=-1)

            # --- masque et feathering ---
            epsilon = 1e-6
            mask = (warped_color.max(axis=2) > epsilon).astype(np.float64)
            mask = cv2.GaussianBlur(mask, (feather_size, feather_size), 0)
            mask_3d = mask[..., None]

            # --- fusion avec le canvas (fondu local) ---
            canvas = canvas * (1 - mask_3d) + warped_color * mask_3d

        except Exception as e:
            print(f"Align failed on image {idx}:", e)

    # --- normalisation finale pour affichage ---
    max_val = np.max(canvas)
    if max_val > 0:
        canvas /= max_val

    result_uint8 = (canvas * 255).astype(np.uint8)
    return result_uint8, "ordre naturel"


def stitch_images_sync(images: list, label: str = "") -> tuple:
    """
    Version synchrone de stitch_images pour les tests (sans await).
    Retourne (image_resultat, nom_de_la_tentative_reussie).
    """
    if len(images) == 1:
        return images[0], "single image"

#    stitcher = cv2.Stitcher_create(cv2.Stitcher_SCANS)
    cv2.ocl.setUseOpenCL(False)
    stitcher = cv2.Stitcher_create(cv2.Stitcher_PANORAMA)

    # 1. ordre naturel
    status, pano = stitcher.stitch(images)
    if status == cv2.Stitcher_OK:
        return pano, "ordre naturel"

    # 2. ordre inverse
    print(f"  {label}ordre naturel echoue -> tentative ordre inverse")
    status, pano = stitcher.stitch(get_inverted_order(images))
    if status == cv2.Stitcher_OK:
        return pano, "ordre inverse"

    # 3. rotation 180
    print(f"  {label}ordre inverse echoue -> tentative rotation 180")
    rotated = images.copy()
    rotated[-1] = cv2.rotate(rotated[-1], cv2.ROTATE_180)
    status, pano = stitcher.stitch(rotated)
    if status == cv2.Stitcher_OK:
        return pano, "rotation 180"

    print(f"  {label}rotation 180 echouee -> fallback premiere image")
    return images[0], "fallback (premiere image)"


# =========================================================
# TESTS UNITAIRES : get_inverted_order
# =========================================================

def run_unit_tests():
    print("=" * 55)
    print("TESTS UNITAIRES -- get_inverted_order")
    print("=" * 55)

    tests = [
        {
            "desc": "2 panneaux : [A,B] -> [B,A]",
            "input": ["A", "B"],
            "expected": ["B", "A"],
        },
        {
            "desc": "4 panneaux : [1,2,3,4] -> [3,4,1,2]",
            "input": ["1", "2", "3", "4"],
            "expected": ["3", "4", "1", "2"],
        },
        {
            "desc": "3 panneaux (cas generique) : [A,B,C] -> [C,B,A]",
            "input": ["A", "B", "C"],
            "expected": ["C", "B", "A"],
        },
        {
            "desc": "1 panneau : inchange",
            "input": ["X"],
            "expected": ["X"],
        },
    ]

    all_pass = True
    for t in tests:
        result = get_inverted_order(t["input"])
        ok = result == t["expected"]
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {t['desc']}")
        if not ok:
            print(f"         attendu  : {t['expected']}")
            print(f"         obtenu   : {result}")
            all_pass = False

    print()
    return all_pass


def run_win_long_path_tests():
    print("=" * 55)
    print("TESTS UNITAIRES -- win_long_path")
    print("=" * 55)

    if platform.system() != "Windows":
        print("  [SKIP] Non-Windows : win_long_path retourne le chemin inchange")
        tests = [
            ("/home/user/file.png", "/home/user/file.png"),
            ("relative/path.png", "relative/path.png"),
        ]
        for inp, expected in tests:
            result = win_long_path(inp)
            ok = result == expected
            print(f"  [{'PASS' if ok else 'FAIL'}] '{inp}' -> '{result}'")
    else:
        tests = [
            (
                "C:\\Users\\test\\file.png",
                "\\\\?\\C:\\Users\\test\\file.png",
            ),
            (
                "C:/Users/test/file.png",
                "\\\\?\\C:\\Users\\test\\file.png",
            ),
            (
                "\\\\?\\C:\\already\\prefixed.png",
                "\\\\?\\C:\\already\\prefixed.png",
            ),
        ]
        all_pass = True
        for inp, expected in tests:
            result = win_long_path(inp)
            ok = result == expected
            print(f"  [{'PASS' if ok else 'FAIL'}] '{inp}'")
            print(f"         -> '{result}'")
            if not ok:
                print(f"         attendu : '{expected}'")
                all_pass = False
        print()
        return all_pass

    print()
    return True


# =========================================================
# TEST DE STITCH SUR IMAGES REELLES
# =========================================================

def run_stitch_test(image_paths: list, output: str = "stitch_result.jpg"):
    print("=" * 55)
    print(f"TEST STITCH -- {len(image_paths)} panneau(x)")
    print("=" * 55)

    images = []
    for path in image_paths:
        print(f"  Chargement : {path}")
        if platform.system() == "Windows":
            print(f"  Chemin long : {win_long_path(path)}")
        img = load_image(path)
        if img is None:
            print(f"  ERREUR : impossible de lire '{path}'")
            return False
        h, w = img.shape[:2]
        print(f"  OK : {w}x{h}")
        images.append(img)

    print()

    scale = 1
    print()

    if scale == 1:
        print(f"  Image 100% ")
        result, method = stitch_with_transform(images)
    else:
        images_small = [cv2.resize(img, None, fx=scale, fy=scale) for img in images]
        print(f"  Reduction a {int(scale*100)}% avant stitch")
        result, method = stitch_with_transform(images_small)
    print(f"  Resultat : {method}")

    cv2.imwrite(output, result)

    result = crop_black_borders(result)
    h, w = result.shape[:2]
    print(f"  Taille finale : {w}x{h}")

    cv2.imwrite("stitch_crop_result.jpg", result)
    print(f"  Sauvegarde : {output}")
    print()
    return True


# =========================================================
# IMAGES SYNTHETIQUES (test sans fichiers reels)
# =========================================================

def make_synthetic_panels(n: int, overlap: int = 60) -> list:
    """
    Genere n panneaux synthetiques avec une zone de chevauchement
    contenant un motif de points identifiable par le stitcher.
    """
    h, w = 400, 600
    rng = np.random.default_rng(42)

    total_w = w + (n - 1) * (w - overlap)
    base = np.zeros((h, total_w, 3), dtype=np.uint8)

    for x in range(total_w):
        base[:, x] = [int(30 + x * 180 / total_w), 40, 80]

    for _ in range(300):
        cx = rng.integers(0, total_w)
        cy = rng.integers(0, h)
        r = rng.integers(3, 10)
        color = rng.integers(100, 255, 3).tolist()
        cv2.circle(base, (cx, cy), r, color, -1)

    panels = []
    for i in range(n):
        x_start = i * (w - overlap)
        panel = base[:, x_start:x_start + w].copy()
        cv2.putText(panel, f"Panel {i+1}", (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2)
        panels.append(panel)

    return panels


def run_synthetic_test(n_panels: int):
    print("=" * 55)
    print(f"TEST SYNTHETIQUE -- {n_panels} panneau(x)")
    print("=" * 55)

    panels = make_synthetic_panels(n_panels)
    for i, p in enumerate(panels):
        h, w = p.shape[:2]
        print(f"  Panneau {i+1} : {w}x{h} (synthetique)")

    print()
    result, method = stitch_with_transform(panels, label=f"[{n_panels}p] ")
    print(f"  Resultat : {method}")

    result_cropped = crop_black_borders(result)
    h, w = result_cropped.shape[:2]
    print(f"  Taille finale apres crop : {w}x{h}")

    out = f"stitch_synthetic_{n_panels}panels.jpg"
    cv2.imwrite(win_long_path(out), result_cropped)
    print(f"  Sauvegarde : {out}")
    print()


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Test de la logique de stitching mosaique Dwarfium"
    )
    parser.add_argument(
        "--images", nargs="+", metavar="IMG",
        help="Chemins vers les images panneaux (2 ou 4). "
             "Sans cet argument, des images synthetiques sont generees."
    )
    parser.add_argument(
        "--output", default="stitch_result.jpg",
        help="Fichier de sortie pour le stitch (defaut : stitch_result.jpg)"
    )
    args = parser.parse_args()

    unit_ok = run_unit_tests()
    path_ok = run_win_long_path_tests()

    if args.images:
        stitch_ok = run_stitch_test(args.images, output=args.output)
    else:
        run_synthetic_test(2)
        run_synthetic_test(4)
        stitch_ok = True

    print("=" * 55)
    if unit_ok and path_ok and stitch_ok:
        print("Tous les tests sont passes.")
    else:
        print("Certains tests ont echoue.")
    print("=" * 55)
    sys.exit(0 if (unit_ok and path_ok and stitch_ok) else 1)
