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

def find_astap(forced_path: str = None) -> str | None:
    """Find astap executable — checks PATH then default install locations."""
    # Allow override via env variable
    import os
    forced_path = forced_path or os.environ.get('ASTAP_PATH')
    if forced_path and Path(forced_path).exists():
        return forced_path

    found = shutil.which("astap") or shutil.which("astap.exe")
    if found:
        return found
    import platform
    if platform.system() == "Windows":
        # Scan all drive letters for common ASTAP install locations
        import string
        drives = [f"{d}:/" for d in string.ascii_uppercase
                  if Path(f"{d}:/").exists()]
        candidates = []
        for drive in drives:
            candidates += [
                f"{drive}Program Files/astap/astap.exe",
                f"{drive}Program Files (x86)/astap/astap.exe",
                f"{drive}astap/astap.exe",
            ]
        for c in candidates:
            # Use os.path for Windows path compatibility (backslash vs forward slash)
            import os
            if os.path.isfile(c):
                return os.path.normpath(c)
    return None


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
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False, dir=tempfile.gettempdir())
        tmp.close()
        import shutil as _shutil
        _shutil.copy2(image_path, tmp.name)
        image_path_safe = tmp.name
        print_log(f"Copied to temp: {tmp.name} (from: {Path(image_path).name})", log)

    if radius <= 10.0:
        radius = 30.0
    astap_dir = str(Path(astap).parent)
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
            focallen = hdr.get('FOCALLEN')
            xpixsz   = hdr.get('XPIXSZ')
            naxis1   = hdr.get('NAXIS1')
            binning  = int(hdr.get('XBINNING', 1))

            # Detect wide lens:
            # 1. CAMERA header = 'WIDE' (recent Dwarf firmware)
            # 2. Session folder name contains '_WIDE_' (D3/Mini naming convention)
            #    e.g. DWARF_RAW_WIDE_NGC7000_EXP_... vs DWARF_RAW_TELE_...
            session_folder = Path(image_path).parent.name.upper()
            is_wide = ('WIDE' in camera or
                       '_WIDE_' in session_folder or
                       session_folder.startswith('DWARF_RAW_WIDE'))
            if is_wide:
                focallen = 24.0
                xpixsz   = xpixsz or 2.0
                print_log(f"Wide lens detected — using focallen=24mm", log)

            if focallen and xpixsz and naxis1:
                fov = round((xpixsz * binning * naxis1) / (focallen * 1000) * (180 / math.pi), 2)
                print_log(f"FOV estimated: {fov}° (camera={camera}, focal={focallen}mm)", log)
    except Exception:
        pass

    cmd = [astap, "-f", image_path_safe, "-r", str(radius), "-s", star_db, "-D", astap_dir,
           "-log", "-z", "0"]  # -z 0 = auto downsample

    # Auto-switch to wide DB for FOV > 5° (ASTAP recommends G05/V05 for large fields)
    if fov and fov > 5.0 and star_db in ('D50', 'D20', 'D80'):
        try:
            from api.dwarf_backup_db import DB_NAME, connect_db, close_db
            from api.dwarf_backup_db_api import get_setting_text as _gst
            _c = connect_db(DB_NAME)
            wide_db = _gst(_c, 'ASTAP_DB_WIDE') or 'G05'
            close_db(_c)
        except Exception:
            wide_db = 'G05'
        cmd = [astap, "-f", image_path_safe, "-r", str(radius), "-s", wide_db, "-D", astap_dir,
               "-log", "-z", "0"]
        print_log(f"Wide FOV ({fov}°) — switching to {wide_db} database", log)

    if fov:
        cmd += ["-fov", str(fov)]
    # If no FOV — don't pass -fov, ASTAP will read from FITS header automatically
    if ra_hint is not None and dec_hint is not None:
        cmd += ["-ra", str(round(ra_hint / 15.0, 6))]   # degrees → hours
        cmd += ["-spd", str(round(dec_hint + 90.0, 4))]  # dec → south pole distance
    else:
        # No hint — replace radius with blind solve
        cmd = [astap, "-f", image_path_safe, "-s", star_db, "-D", astap_dir,
               "-log", "-z", "0", "-r", "180"]
        if fov:
            cmd += ["-fov", str(fov)]
    # RA/DEC hints optional — ASTAP finds solution without them with wide radius

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



def solve_locally(image_path, log=None, downsample=2):
    """Run astrometry.net locally using solve-field"""
    if not has_solve_field():
        raise EnvironmentError("solve-field not found. Install astrometry.net locally.")

    output_dir = Path(image_path).parent
    cmd = [
        "solve-field", image_path,
        "--overwrite",
        "--downsample", str(downsample),
        "--dir", str(output_dir),
        "--no-plots",
    ]
    print_log(f"🔭 Execute : {' '.join(cmd)}", log)
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print_log(result.stderr, log)
        raise RuntimeError("Local resolution failed: " + result.stderr)

    solved_file = str(Path(image_path).with_suffix(".solved"))
    if os.path.exists(solved_file):
        print_log(f"✅ Successful local resolution:{solved_file}", log)
        return solved_file
    else:
        raise FileNotFoundError("Local resolution complete, but .solved file not found")

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
                focallen = hdr.get('FOCALLEN')
                xpixsz   = hdr.get('XPIXSZ')
                naxis1   = hdr.get('NAXIS1', 1)
                binning  = int(hdr.get('XBINNING', 1))

        # Try known Dwarf plate scales first — adjust for binning
        ps = next((v for k, v in DWARF_PS.items() if k.upper() in telescop.upper()), None)
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
                 ra_hint: float = None, dec_hint: float = None) -> str:
    """
    Solve image astrometry using the best available solver.
    Priority: ASTAP (fast, local) > solve-field (local) > Nova API (online)
    ra_hint/dec_hint: explicit coordinates to skip reading from file (useful for temp files)
    """
    print_log(f"Attempted resolution for: {image_path}", log)

    # 1. ASTAP — fastest, Windows-native
    if has_astap():
        print_log(f"Mode: ASTAP (local, fast, db={astap_db})", log)
        if ra_hint is None or dec_hint is None:
            _ra, _dec = get_ra_dec_hint_from_fits(image_path)
            ra_hint  = ra_hint  if ra_hint  is not None else _ra
            dec_hint = dec_hint if dec_hint is not None else _dec
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
        return solve_locally(image_path, log)

    # 3. Nova API — online fallback
    if api_key:
        print_log("Mode: Nova API (online)", log)
        return solve_online(api_key, image_path, log)

    raise EnvironmentError(
        "No solver available. Install ASTAP (https://www.hnsky.org/astap.htm), "
        "solve-field, or set a Nova API key in Settings."
    )