import os
import time
import platform
import subprocess
import requests
import sqlite3
import shutil
from pathlib import Path

from api.dwarf_backup_db_api import get_setting_text
from api.dwarf_backup_fct import safe_print, print_log, get_ra_in_hours
from astropy.io import fits
from astropy.wcs import WCS
from pathlib import Path

import warnings
from astropy.wcs import FITSFixedWarning
warnings.filterwarnings('ignore', category=FITSFixedWarning)

def get_fits_center_coordinates(fits_path, convert_to_hour = False):
    """
    GET RA/DEC of center if WCS exists or from header, else None.
    """
    if not fits_path:
        return None, None
    fits_path = Path(fits_path)
    if not fits_path.exists():
        return None, None

    with fits.open(fits_path) as hdul:
        hdr = hdul[0].header
        try:
            wcs = WCS(hdr)
            if wcs.has_celestial:
                ra, dec = wcs.wcs.crval
                if convert_to_hour:
                    ra = ra / 15
                safe_print(f"RA: {float(ra)}, Dec: {float(dec)}") 
                return float(ra), float(dec)
        except Exception:
            pass

        try:
            # fallback to header values
            if convert_to_hour:
                ra = get_ra_in_hours(hdr)
            else:
                ra = hdr.get('RA')
            dec = hdr.get('DEC')
            if ra is not None and dec is not None:
                safe_print(f"RA: {float(ra)}, Dec: {float(dec)}") 
                return float(ra), float(dec)

        except Exception:
            pass
        return None, None

def has_solve_field():
    """Check if solve-field command is available"""
    return shutil.which("solve-field") is not None

ASTAP_NAMES = ("astap", "astap_cli", "astap.exe", "astap_cli.exe")

# Default install folders (executable and, on Linux/Windows, star databases)
ASTAP_DIRS = {
    "Linux":   ["/opt/astap", "/usr/local/bin", "/usr/bin", str(Path.home() / "astap")],
    "Darwin":  ["/Applications/ASTAP.app/Contents/MacOS", "/usr/local/opt/astap",
                "/opt/homebrew/opt/astap"],
}

# Star database folders used by ASTAP installers when not next to the executable
ASTAP_DB_DIRS = ["/opt/astap", "/usr/local/opt/astap", "/opt/homebrew/opt/astap"]


def find_astap(forced_path: str = None) -> str | None:
    """
    Find the ASTAP executable (GUI 'astap' or command-line 'astap_cli'):
    ASTAP_PATH / forced path, then PATH, then default install locations.
    """
    import os
    import platform
    forced_path = forced_path or os.environ.get('ASTAP_PATH')
    if forced_path and Path(forced_path).exists():
        return forced_path

    for name in ASTAP_NAMES:
        found = shutil.which(name)
        if found:
            return found

    system = platform.system()
    if system == "Windows":
        # Scan all drive letters for common ASTAP install locations
        import string
        drives = [f"{d}:/" for d in string.ascii_uppercase
                  if Path(f"{d}:/").exists()]
        candidates = []
        for drive in drives:
            for folder in ("Program Files/astap", "Program Files (x86)/astap", "astap"):
                candidates += [f"{drive}{folder}/astap.exe", f"{drive}{folder}/astap_cli.exe"]
    else:
        candidates = [f"{d}/{name}" for d in ASTAP_DIRS.get(system, []) for name in ASTAP_NAMES[:2]]

    for c in candidates:
        # Use os.path for Windows path compatibility (backslash vs forward slash)
        if os.path.isfile(c) and (system == "Windows" or os.access(c, os.X_OK)):
            return os.path.normpath(c)
    return None


def find_astap_db_dir(astap: str) -> str:
    """
    Folder holding the ASTAP star databases (d05_*, d50_*, g05_*...).
    Usually next to the executable (Windows, /opt/astap on Linux), but the
    macOS installer puts them in /usr/local/opt/astap.
    """
    astap_path = Path(astap).resolve()   # follow /usr/bin/astap → /opt/astap/astap
    for d in [astap_path.parent, Path(astap).parent, *map(Path, ASTAP_DB_DIRS)]:
        if d.is_dir() and any(d.glob("[a-zA-Z][0-9][0-9]_*")):
            return str(d)
    return str(astap_path.parent)


def has_astap() -> bool:
    return find_astap() is not None


def set_astap_path(path: str):
    """Set ASTAP path via environment variable for current process."""
    import os
    os.environ['ASTAP_PATH'] = path


def get_ra_dec_hint_from_fits(image_path: str):
    """Extract RA/DEC from FITS header to use as solve hint."""
    try:
        from astropy.io import fits as _fits
        with _fits.open(image_path) as hdul:
            hdr = hdul[0].header
            ra  = hdr.get('RA')  or hdr.get('OBJCTRA')  or hdr.get('RA_OBJ')
            dec = hdr.get('DEC') or hdr.get('OBJCTDEC') or hdr.get('DEC_OBJ')
            if ra is not None and dec is not None:
                return float(ra), float(dec)
    except Exception:
        pass
    return None, None


# Wide-angle lens fallback when the FITS header has no usable FOCALLEN.
# DWARF mini wide: FOCALLEN=7,   XPIXSZ=2.9 (1920x1080 → ~45.5° x 25.6° field)
# DWARF 3 wide:    FOCALLEN=6.7, XPIXSZ=2.9 (1920x1080 → ~46.6° x 26.8° field)
# 7 mm is within ASTAP's FOV tolerance for both.
WIDE_FOCALLEN_FALLBACK = 7.0
WIDE_XPIXSZ_FALLBACK   = 2.9


def dwarf_optics(hdr, image_path: str) -> tuple[float | None, float | None, bool]:
    """
    Return (focallen_mm, pixel_size_um, is_wide) from a Dwarf FITS header.
    Wide lens: CAMERA header contains 'WIDE' (recent firmware) or the session
    folder is DWARF_RAW_WIDE_... / contains _WIDE_.
    The header FOCALLEN is trusted for the wide lens; the fallback is only used
    when it is missing or is the tele focal length (> 50 mm).
    """
    camera   = str(hdr.get('CAMERA', '')).upper()
    focallen = hdr.get('FOCALLEN')
    xpixsz   = hdr.get('XPIXSZ')
    session_folder = Path(image_path).parent.name.upper()
    is_wide = ('WIDE' in camera or
               '_WIDE_' in session_folder or
               session_folder.startswith('DWARF_RAW_WIDE'))
    try:
        focallen = float(focallen) if focallen else None
        xpixsz   = float(xpixsz) if xpixsz else None
    except (TypeError, ValueError):
        focallen, xpixsz = None, None
    if is_wide:
        if not focallen or focallen > 50:
            focallen = WIDE_FOCALLEN_FALLBACK
        xpixsz = xpixsz or WIDE_XPIXSZ_FALLBACK
    return focallen, xpixsz, is_wide


def solve_astap(image_path: str, log=None, ra_hint=None,
                dec_hint=None, radius: float = 10.0, downsample: int = 0,
                star_db: str = "D20") -> str:
    """
    Solve with ASTAP (https://www.hnsky.org/astap.htm).
    Much faster than solve-field or Nova — ~10 sec on a typical image.
    Returns path to the .wcs file created alongside the input.
    """
    astap = find_astap()
    if not astap:
        raise EnvironmentError(
            "ASTAP not found. Download from https://www.hnsky.org/astap.htm"
        )

    # ASTAP may fail with paths containing spaces or long paths — copy to temp if needed
    import tempfile
    image_path_safe = image_path
    if ' ' in str(image_path) or len(str(image_path)) > 200:
        suffix = Path(image_path).suffix
        # 'astap_tmp_' prefix: removed with its .ini/.wcs/.log by astrometry_scan._cleanup_temp
        tmp = tempfile.NamedTemporaryFile(prefix="astap_tmp_", suffix=suffix, delete=False, dir=tempfile.gettempdir())
        tmp.close()
        import shutil as _shutil
        _shutil.copy2(image_path, tmp.name)
        image_path_safe = tmp.name
        print_log(f"Copied to temp: {tmp.name} (from: {Path(image_path).name})", log)

    if radius <= 10.0:
        radius = 30.0
    astap_dir = find_astap_db_dir(astap)
    # Detect binning from FITS header — binned images have larger plate scale
    # Adjust search radius accordingly
    try:
        from astropy.io import fits as _fits
        with _fits.open(image_path_safe) as hdul:
            binning = int(hdul[0].header.get('XBINNING', 1))
            if binning >= 2:
                radius = max(radius, 60.0)  # wider search for binned images
                print_log(f"Binning {binning}x detected — search radius extended to {radius}°", log)
    except Exception:
        pass

    # Estimate FOV from FITS header
    # CAMERA header: 'TELE' = telephoto lens, 'WIDE' or 'C20' = wide angle
    fov = None
    try:
        from astropy.io import fits as _fits
        import math
        with _fits.open(image_path_safe) as hdul:
            hdr = hdul[0].header
            camera   = str(hdr.get('CAMERA', '')).upper()
            naxis2   = hdr.get('NAXIS2')   # ASTAP -fov is the image HEIGHT
            binning  = int(hdr.get('XBINNING', 1))
            # image_path, not the temp copy: the session folder name tells the lens
            focallen, xpixsz, is_wide = dwarf_optics(hdr, image_path)
            if is_wide:
                print_log(f"Wide lens detected — focallen={focallen}mm, pixel={xpixsz}µm", log)

            if focallen and xpixsz and naxis2:
                fov = round((xpixsz * binning * naxis2) / (focallen * 1000) * (180 / math.pi), 2)
                print_log(f"FOV estimated: {fov}° (camera={camera}, focal={focallen}mm)", log)
    except Exception:
        pass

    # Auto-switch to wide DB for FOV > 5° (ASTAP recommends G05/V05 for large fields)
    if fov and fov > 5.0 and star_db.upper() in ('D05', 'D50', 'D20', 'D80'):
        try:
            from api.dwarf_backup_db import DB_NAME, connect_db, close_db
            from api.dwarf_backup_db_api import get_setting_text as _gst
            _c = connect_db(DB_NAME)
            wide_db = _gst(_c, 'ASTAP_DB_WIDE') or 'G05'
            close_db(_c)
        except Exception:
            wide_db = 'G05'
        print_log(f"Wide FOV ({fov}°) — switching to {wide_db} database", log)
        star_db = wide_db

    # ASTAP options: -d = database folder, -D = database abbreviation (d50, g05...),
    # -s = max number of stars (NOT the database), -fov = image height in degrees.
    cmd = [astap, "-f", image_path_safe, "-d", astap_dir, "-log", "-z", "0"]
    db = (star_db or "").lower()
    if db and any(Path(astap_dir).glob(f"{db}_*")):
        cmd += ["-D", db]
    else:
        # Requested database not installed — let ASTAP pick the installed one
        print_log(f"ASTAP database '{star_db}' not found in {astap_dir} — using ASTAP default", log)

    # Unknown FOV (e.g. JPEG without FITS header) → 0 = ASTAP auto-detects the scale
    cmd += ["-fov", str(fov) if fov else "0"]

    if ra_hint is not None and dec_hint is not None:
        cmd += ["-r", str(radius)]
        cmd += ["-ra", str(round(ra_hint / 15.0, 6))]    # degrees → hours
        cmd += ["-spd", str(round(dec_hint + 90.0, 4))]  # dec → south pole distance
    else:
        cmd += ["-r", "180"]  # no hint → blind solve

    # Remove results of a previous run so a stale .ini is never read as a success
    for ext in (".ini", ".wcs"):
        try:
            Path(image_path_safe).with_suffix(ext).unlink()
        except Exception:
            pass

    print_log(f"ASTAP: {' '.join(cmd)}", log)
    result = subprocess.run(cmd, capture_output=True, text=True)

    # Print ASTAP log file content if available
    log_path = Path(image_path_safe).with_suffix('.log')
    if log_path.exists():
        try:
            log_content = log_path.read_text(encoding='utf-8', errors='replace').strip()
            if log_content:
                print_log(f"ASTAP log:\n{log_content}", log)
        except Exception:
            pass

    # ASTAP creates .ini (reliable) and .wcs alongside the input
    ini_file = str(Path(image_path_safe).with_suffix(".ini"))
    if Path(ini_file).exists():
        ini_text = Path(ini_file).read_text(encoding='utf-8', errors='replace')
        if 'PLTSOLVD=T' in ini_text:
            print_log(f"ASTAP solved: {ini_file}", log)
            return ini_file
        # Failed — clean up temp FITS if we created it
        if image_path_safe != image_path:
            try: Path(image_path_safe).unlink()
            except Exception: pass
        raise RuntimeError(f"ASTAP_FAILED\nini: {ini_text[:500]}")

    if image_path_safe != image_path:
        try: Path(image_path_safe).unlink()
        except Exception: pass
    raise RuntimeError(
        f"ASTAP_FAILED\nno .ini found. stdout: {result.stdout}\nstderr: {result.stderr}"
    )



def solve_locally(image_path, log=None, downsample=2, ra_hint=None, dec_hint=None,
                  radius: float = 30.0, cpulimit: int = 180):
    """
    Run astrometry.net locally using solve-field.
    Works in a temporary folder (solve-field writes many side files) and copies
    the resulting WCS header next to the image as <name>.wcs.fits, like the
    Nova online solver. Returns the path of that .wcs.fits file.
    Needs index files (e.g. apt package astrometry-data-tycho2).
    """
    if not has_solve_field():
        raise EnvironmentError("solve-field not found. Install astrometry.net locally.")

    import tempfile
    with tempfile.TemporaryDirectory(prefix="solve_field_") as work_dir:
        cmd = [
            "solve-field", str(image_path),
            "--overwrite",
            "--no-plots",
            "--new-fits", "none",
            "--downsample", str(downsample),
            "--dir", work_dir,
            "--cpulimit", str(cpulimit),
            # Dwarf fields go from ~1° (tele) to ~60° (wide): bound the scale search
            "--scale-units", "degwidth", "--scale-low", "0.5", "--scale-high", "90",
        ]
        if ra_hint is not None and dec_hint is not None:
            cmd += ["--ra", str(ra_hint), "--dec", str(dec_hint), "--radius", str(radius)]
        print_log(f"🔭 Execute : {' '.join(cmd)}", log)
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print_log(result.stderr, log)
            raise RuntimeError("Local resolution failed: " + result.stderr)

        stem = Path(image_path).stem
        solved = Path(work_dir) / f"{stem}.solved"
        wcs = Path(work_dir) / f"{stem}.wcs"
        if not solved.exists() or not wcs.exists():
            print_log(result.stdout[-2000:], log)
            raise RuntimeError("Local resolution failed: no solution found "
                               "(check that astrometry.net index files are installed)")

        wcs_file = Path(image_path).with_suffix(".wcs.fits")
        shutil.copy2(wcs, wcs_file)

    print_log(f"✅ Successful local resolution: {wcs_file}", log)
    return str(wcs_file)


def solve_online(api_key, image_path, log=None):
    """Solve using Astrometry.net API (nova.astrometry.net)"""
    #verify default data
    url = "http://nova.astrometry.net/api/upload"
    print_log("🔭 Upload vers Astrometry.net...", log)

    # 1️⃣ Login
    login_url = "http://nova.astrometry.net/api/login"
    r = requests.post(login_url, data={"request-json": f'{{"apikey": "{api_key}"}}'})
    r.raise_for_status()
    session = r.json().get("session")
    if not session:
        raise RuntimeError("Unable to connect to Astrometry.net (check your API key).")

    # 2️⃣ Upload de l’image
    # Build upload params with scale hints from FITS header
    import json as _json
    upload_params = {
        "publicly_visible": "n",
        "allow_commercial_use": "n",
        "session": session,
    }
    # Known plate scales per Dwarf model (arcsec/px at actual FITS resolution)
    # Accounts for firmware upscaling (D2: 1932→3840px)
    DWARF_PS = {
        'DWARFII':    3.01,  # D2 TELE 100mm, upscaled to 3840px — no FOCALLEN in header
        'DWARF II':   3.01,  # plate_scale = 5.98" native / 2x upscale = 3.01"/px at 3840px
        'DWARFIII':   2.75,  # D3 TELE 150mm, native 3856px
        'DWARF III':  2.75,
        'DWARF 3':    2.75,
        'DWARF3':     2.75,
        'DWARF mini': 4.03,  # Mini TELE 150mm, native 1920px (2.9um pixel)
        'DWARFMINI':  4.03,
        'DWARF MINI': 4.03,
    }
    try:
        from astropy.io import fits as _fits
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with _fits.open(image_path) as hdul:
                hdr      = hdul[0].header
                telescop = str(hdr.get('TELESCOP', '')).strip()
                focallen, xpixsz, is_wide = dwarf_optics(hdr, image_path)
                naxis1   = hdr.get('NAXIS1', 1)
                binning  = int(hdr.get('XBINNING', 1))

        # Try known Dwarf plate scales first — adjust for binning.
        # The table holds TELE scales only: skipped for the wide lens.
        ps = None if is_wide else next((v for k, v in DWARF_PS.items() if k.upper() in telescop.upper()), None)
        if ps and binning > 1:
            ps = ps * binning

        # Fallback: compute from FOCALLEN/XPIXSZ
        if ps is None and focallen and xpixsz and float(focallen) > 0:
            ps = (float(xpixsz) * binning / float(focallen)) * 206.265

        # Last resort: guess from image resolution (old D2 FITS have no metadata)
        # Note: D2 recent FITS may have non-standard resolution (cropped/panel)
        # so TELESCOP=DWARFII should already have matched above
        # D2: 3840x2160 (upscaled) → 3.01"/px | 1920x1080 (binning 2x) → 6.02"/px
        # D3: 3856x2180 → 2.75"/px | Mini: 1920x1080 → 4.03"/px
        if ps is None:
            # If TELESCOP is known, 1920x1080 = Mini (already handled above)
            # If no TELESCOP, 1920x1080 = D2 binning 2x
            is_mini = 'mini' in telescop.lower() if telescop else False
            PS_BY_RES = {
                (3856, 2180): 2.75,  # D3 TELE native
                (3840, 2160): 3.01,  # D2 upscaled 1x1
                (1920, 1080): 4.03 if is_mini else 6.02,  # Mini vs D2 binning 2x
                (1928, 1096): 5.98,  # D2 native
                (1932, 1096): 5.98,
            }
            naxis2 = hdr.get('NAXIS2', 0)
            ps = PS_BY_RES.get((int(naxis1), int(naxis2)))
            if ps:
                print_log(f"Nova scale hint: guessed from resolution {naxis1}x{naxis2}", log)

        if ps:
            upload_params["scale_units"] = "arcsecperpix"
            upload_params["scale_lower"] = round(ps * 0.7, 2)
            upload_params["scale_upper"] = round(ps * 1.4, 2)
            print_log(f"Nova scale hint: {ps:.2f} arcsec/px [{upload_params['scale_lower']}-{upload_params['scale_upper']}] ({telescop})", log)
    except Exception:
        pass

    with open(image_path, "rb") as f:
        files = {"file": f}
        payload = {"request-json": _json.dumps(upload_params)}
        r = requests.post(url, files=files, data=payload)
        r.raise_for_status()

    subid = r.json().get("subid")
    if not subid:
        raise RuntimeError("Upload failed: no subi received.")
    print_log(f"🛰️ Submission OK, subid = {subid}", log)

    # 3️⃣ Attente du résultat
    import time
    status_url = f"http://nova.astrometry.net/api/submissions/{subid}"
    print_log("⏳ Waiting for the result...", log)

    for _ in range(60):  # ~5 min max
        time.sleep(5)
        s = requests.get(status_url)
        s.raise_for_status()
        jobs = s.json().get("jobs", [])
        if jobs and jobs[0] is not None:
            job_id = jobs[0]
            print_log(f"🧩 Job found : {job_id}", log)
            break
    else:
        raise TimeoutError("Deadline exceeded: online resolution took too long.")

    # 4️⃣  WCS Upload
    print_log("⏳ Waiting for the result...", log)
    job_url = f"http://nova.astrometry.net/api/jobs/{job_id}"

    for _ in range(60):  # poll ~5 minutes
        time.sleep(5)
        r = requests.get(job_url)
        r.raise_for_status()
        data = r.json()
        status = data.get("status")
        print_log(f"Job status: {status}", log)
        
        if status == "success":
            print_log("✅ Job solved, ready for WCS download", log)
            break
        elif status == "failure":
            raise RuntimeError(f"Job {job_id} failed")
    else:
        raise TimeoutError(f"Job {job_id} did not finish in time")

    wcs_url = f"http://nova.astrometry.net/wcs_file/{job_id}"
    wcs_file = Path(image_path).with_suffix(".wcs.fits")
    r = requests.get(wcs_url)
    r.raise_for_status()
    with open(wcs_file, "wb") as f:
        f.write(r.content)

    print_log(f"✅ WCS downloaded: {wcs_file}", log)

    print_log(f"✅ Successful online resolution : {wcs_file}", log)
    return str(wcs_file)

def auto_resolve(api_key: str, image_path: str, log=None, astap_db: str = "D20",
                 ra_hint: float = None, dec_hint: float = None, blind: bool = False) -> str:
    """
    Solve image astrometry using the best available solver.
    Priority: ASTAP (fast, local) > solve-field (local) > Nova API (online)
    ra_hint/dec_hint: explicit coordinates to skip reading from file (useful for temp files)
    blind: ignore any position hint (FITS header included) and search the
    whole sky — for sessions whose recorded goto position is wrong.
    """
    print_log(f"Attempted resolution for: {image_path}", log)

    if blind:
        ra_hint = dec_hint = None
        print_log("Blind solve: position hint ignored", log)
    elif ra_hint is None or dec_hint is None:
        _ra, _dec = get_ra_dec_hint_from_fits(image_path)
        ra_hint  = ra_hint  if ra_hint  is not None else _ra
        dec_hint = dec_hint if dec_hint is not None else _dec

    # 1. ASTAP — fastest, Windows-native
    if has_astap():
        print_log(f"Mode: ASTAP (local, fast, db={astap_db})", log)
        try:
            return solve_astap(image_path, log=log, ra_hint=ra_hint, dec_hint=dec_hint, star_db=astap_db)
        except RuntimeError as e:
            if 'ASTAP_FAILED' in str(e):
                print_log("ASTAP failed — falling back to next solver", log)
            else:
                raise

    # 2. solve-field — astrometry.net local
    if has_solve_field():
        print_log("Mode: solve-field (local)", log)
        try:
            return solve_locally(image_path, log, ra_hint=ra_hint, dec_hint=dec_hint)
        except RuntimeError as e:
            if not api_key:
                raise
            print_log(f"solve-field failed — falling back to Nova API ({e})", log)

    # 3. Nova API — online fallback
    if api_key:
        print_log("Mode: Nova API (online)", log)
        return solve_online(api_key, image_path, log)

    raise EnvironmentError(
        "No solver available. Install ASTAP (https://www.hnsky.org/astap.htm), "
        "solve-field, or set a Nova API key in Settings."
    )