import os
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
    with open(image_path, "rb") as f:
        files = {"file": f}
        payload = {"request-json": f'{{"publicly_visible":"n","allow_commercial_use":"n","session":"{session}"}}'}
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

def auto_resolve(api_key, image_path, log=None):
    """Automatically chooses local or online mode depending on the configuration"""
    print_log(f"🔍 Attempted resolution for: {image_path}", log)
    if has_solve_field():
        print_log("🧠 Mode: Local (solve-field)", log)
        return solve_locally(image_path, log)
    else:
        print_log("🌐 Mode: Online (Astrometry.net)", log)
        return solve_online(api_key, image_path, log)
