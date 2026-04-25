import os
import sys
import sqlite3
import json
import hashlib
import shutil
import argparse
from pathlib import Path
from datetime import datetime
import re
import platform
import subprocess
import glob
import ftplib
from astropy.io import fits
import matplotlib.pyplot as plt
import numpy as np
from auto_stretch import apply_stretch
import cv2

from api.dwarf_backup_db import connect_db, close_db, commit_db
from api.dwarf_backup_db_api import get_backupDrive_id_from_location, insert_astro_object, insert_astro_group, insert_DwarfData, insert_BackupEntry, insert_DwarfEntry, update_astro_object_coord, get_db_local_dwarf_dir
from api.dwarf_backup_db_api import is_dwarf_exists, get_dwarf_Names, add_dwarf_detail, delete_notpresent_backup_entries_and_dwarf_data, delete_notpresent_dwarf_entries_and_dwarf_data
from api.dwarf_backup_db_api import set_dwarf_scan_date, set_backup_scan_date, get_astro_object_groupId, rebuild_manual_session_entries, write_missing_shotsInfo

from astropy.coordinates import SkyCoord
from astropy.io.fits import VerifyError
import astropy.units as u

CATALOG_FILE = os.path.join("db", "dso_catalog.json")
SKY_CATALOG_FILE = os.path.join("db","dso_sky_search_catalog.json")
UNKNOWN = "unknown"
MOSAIC_UNKNOWN = "mosaic_unknown"
MANUAL = "manual"
TAKEN = "Taken"
RESTACK = "Restack"
STARTRAILS = "STARTRAILS"
STARTRAILS_SESSION = "STARTRAILS_DWARF_RAW_WIDE_"

##################
# Print functions
##################
def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode(sys.stdout.encoding, errors='replace').decode())
    except Exception:
        pass  # client disconnected — ignore silently

def print_log(message, log, style = None):
    try:
        if log:
            if style:
                log.push(message, classes=style)
            else:
                log.push(message)
        else:
            safe_print(message)
    except Exception:
        pass  # client disconnected — ignore silently
        
###################
# Files functions
###################

def open_folder(path_var):
    path = path_var.get()
    if os.path.isdir(path):
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    else:
        safe_print(f"[FAIL] Path does not exist: {path}")

def compute_md5(filepath):
    hash_md5 = hashlib.md5()
    filepath_str = str(filepath)
    if filepath_str.startswith("ftp://"):
        # For FTP, read the file in chunks
        url_parts = filepath[6:].split('/', 1)
        ftp_host = url_parts[0]
        ftp_path = url_parts[1]
        with ftplib.FTP(ftp_host) as ftp:
            ftp.login()  # Anonymous by default
            with ftp.transfercmd(f'RETR {ftp_path}') as conn:
                while chunk := conn.recv(4096):
                    hash_md5.update(chunk)
    else:
        with open(win_long_path(filepath), "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)

    return hash_md5.hexdigest()

def files_are_different(src, dst, check_md5=False):
    if not os.path.exists(dst):
        safe_print("files_are_different 1")
        return True
    if os.path.getsize(src) != os.path.getsize(dst):
        safe_print("files_are_different 2")
        return True
    if int(os.path.getmtime(src)) != int(os.path.getmtime(dst)):
        safe_print("files_are_different 3")
        return True
    if check_md5 and compute_md5(src) != compute_md5(dst): return True
    return False

def win_long_path(filepath):
    if os.name == 'nt':
        filepath_str = str(filepath)
        if filepath_str.startswith('\\\\?\\'):
            return filepath_str  # already in long path format
        else:
            return '\\\\?\\' + os.path.abspath(filepath_str)
    else:
        return str(filepath)

def get_directory_size(directory_path: str) -> int:
    total_size = 0

    for dirpath, dirnames, filenames in os.walk(directory_path):
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            if os.path.isfile(file_path):
                total_size += os.path.getsize(file_path)

    return total_size

def get_directory_size_format(directory: str) -> str:
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(directory):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if os.path.isfile(fp):
                total_size += os.path.getsize(fp)
    # Format size nicely
    return format_size(total_size)

def format_size(size_bytes: int) -> str:
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(min(len(size_name) - 1, (size_bytes.bit_length() - 1) // 10))
    p = 1 << (i * 10)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"

def get_file_path(full_path, base_folder):
    # Normalize both paths to use forward slashes and strip trailing slashes
    full_path = os.path.normpath(full_path)
    base_folder = os.path.normpath(base_folder)
    
    # Get the relative path
    return os.path.relpath(full_path, base_folder)

def get_session_file_ref(session_dir, full_path):
    if not session_dir or not full_path:
        return None

    full = Path(full_path)
    session_parts = Path(session_dir).parts

    parts = full.parts

    # find where session_dir starts inside full_path
    for i in range(len(parts)):
        if parts[i:i+len(session_parts)] == session_parts:
            rel = Path(*parts[i:])
            return str(rel)

# get the root directory (ManualSessionDrive) from the Session Dir and a path of a image (with or without tag)
# use for preview image
def get_root_manual_session_dir(session_dir, image_path):

    # 1. Normalize selected_path
    p2 = Path(session_dir).resolve()
    # 2. Remove the relative image_path from the end of selected_path
    base = p2
    for part in reversed(Path(image_path).parts):
        if base.name == part:
            base = base.parent

    return base
   
def get_extension(file_path):
    return os.path.splitext(file_path)[1].lower().lstrip('.')

def has_subdirectories(directory):
    return any(
        os.path.isdir(os.path.join(directory, entry)) and not entry.startswith('.')  and not entry.startswith('Thumbnail')
        for entry in os.listdir(directory)
)

def get_png_name_from_zip(search_dir: str | Path) -> Path:
    """
    Return the PNG path based on the single ZIP file in the directory.
    
    Return None if no ZIP or multiple ZIPs are found.
    """
    search_dir = Path(search_dir)

    zip_files = list(search_dir.glob("*.zip"))

    if len(zip_files) == 0:
        raise None

    return zip_files[0].with_suffix(".png")

def get_fits_name_from_zip(search_dir: str | Path) -> Path:
    """
    Return the PNG path based on the single ZIP file in the directory.
    
    Return None if no ZIP or multiple ZIPs are found.
    """
    search_dir = Path(search_dir)

    zip_files = list(search_dir.glob("*.zip"))

    if len(zip_files) == 0:
        raise None

    return zip_files[0].with_suffix(".fits")

# tranform filename in cas of error
def _err_path(p):
    p = Path(p)
    return p.with_stem(p.stem + "_err") if p else None
    

    
###########################
# Specific Files functions
###########################

def get_effective_parent(path):
    parent = os.path.basename(os.path.dirname(path))
    if parent == "RESTACKED":
        # Return grandparent if parent is RESTACKED
        return os.path.basename(os.path.dirname(os.path.dirname(path)))
    return parent

def get_Backup_fullpath (conn, location, subdir, filename, dwarf_id = None):
    full_path = ""
    if location:
        full_path = location
    if full_path and subdir:
        full_path = os.path.join(full_path, subdir)
    elif subdir:
        full_path = subdir
    if full_path:
        full_path = os.path.join(full_path, filename)
    else:
        full_path = filename

    # use local_copy if not connected
    if not os.path.isdir(os.path.dirname(full_path)) and dwarf_id:
        local_Dwarf_dir = get_local_dwarf_dir(conn, dwarf_id)
        test_path = os.path.join(local_Dwarf_dir, filename)
        full_path = test_path if os.path.isdir(os.path.dirname(test_path)) else full_path

    return full_path

def check_files(full_path: str) -> dict:
    # Get directory from full path
    directory = os.path.dirname(full_path)

    # Look for matching files
    jpg_match = glob.glob(os.path.join(directory, 'stacked.jpg'))
    png_match = glob.glob(os.path.join(directory, 'stacked*.png'))
    tiff_match = glob.glob(os.path.join(directory, 'stacked*.tiff'))
    fits_match = glob.glob(os.path.join(directory, 'stacked*.fits'))
    zip_match = glob.glob(os.path.join(directory, 'stacked*.zip'))
    thumbnail_match = glob.glob(os.path.join(directory, 'stacked_thumbnail.jpg'))

    if tiff_match:
        return {
            'jpg': jpg_match[0] if jpg_match else None,
            'png': png_match[0] if png_match else None,
            'tiff': tiff_match[0] if tiff_match else None,
            'thumbnail': thumbnail_match[0] if thumbnail_match else None
        }
    elif zip_match and not fits_match:
        return {
            'jpg': jpg_match[0] if jpg_match else None,
            'png': png_match[0] if png_match else None,
            'zip': zip_match[0] if zip_match else None,
            'thumbnail': thumbnail_match[0] if thumbnail_match else None
        }
    else :
        return {
            'jpg': jpg_match[0] if jpg_match else None,
            'png': png_match[0] if png_match else None,
            'fits': fits_match[0] if fits_match else None,
            'thumbnail': thumbnail_match[0] if thumbnail_match else None
        }

def count_fits_files(directory):
    try:
        if "_MOSAIC_" in directory and has_subdirectories(directory):
            # Look in subdirectories
            count = 0
            for sub in os.listdir(directory):
                sub_path = os.path.join(directory, sub)
                if os.path.isdir(sub_path):
                    count += sum(
                        1 for f in os.listdir(sub_path)
                        if f.endswith('.fits') and not (f.startswith('stacked-') or f.startswith('failed_'))
                    )
            return count
        else:
            # Normal case: check directly in the directory
            return sum(
                1 for f in os.listdir(directory)
                if f.endswith('.fits') and not (f.startswith('stacked-') or f.startswith('failed_'))
            )

    except Exception as e:
        safe_print(f"Could not access {directory}: {e}")

def count_failed_fits_files(directory):
    return sum(
        1 for f in os.listdir(directory)
        if f.endswith('.fits') and f.startswith('failed_')
    )

def count_tiff_files(directory):
    return sum(
        1 for f in os.listdir(directory)
        if f.endswith('.tiff') and not (f.startswith('stacked-') or f.startswith('failed_'))
    )

def count_failed_tiff_files(directory):
    return sum(
        1 for f in os.listdir(directory)
        if f.endswith('.tiff') and f.startswith('failed_')
    )

def cleanup_fits_files(directory: str, dry_run: bool = False) -> None:
    """
    Remove all FITS files in a directory tree except those starting with 'stacked-16_'.

    Args:
        directory (str): Root directory of the session
        dry_run (bool): If True, only prints what would be deleted
    """

    if not os.path.exists(directory):
        raise ValueError(f"Directory does not exist: {directory}")

    deleted_count = 0
    kept_count = 0

    for dirpath, _, filenames in os.walk(directory):
        for filename in filenames:
            # Normalize case just in case (.FITS, .fits, etc.)
            if filename.lower().endswith(".fits"):
                
                # Keep stacked-16_* files
                if filename.startswith("stacked-16_"):
                    kept_count += 1
                    continue

                file_path = os.path.join(dirpath, filename)

                if dry_run:
                    print(f"[DRY RUN] Would delete: {file_path}")
                else:
                    try:
                        os.remove(file_path)
                        print(f"Deleted: {file_path}")
                        deleted_count += 1
                    except Exception as e:
                        print(f"Error deleting {file_path}: {e}")

    print("\nSummary:")
    print(f"  Deleted FITS files: {deleted_count}")
    print(f"  Kept stacked FITS: {kept_count}")

    return deleted_count 
 
def restore_fits_files(src_backup_folder: str, dst_session_folder: str, app, dry_run: bool = False):
    """
    Restore FITS files from backup to the Dwarf session folder.
    Preserves subfolders and skips existing files.

    Args:
        src_backup_folder (str): Path to the backup session folder
        dst_session_folder (str): Path to the session folder on Dwarf
        dry_run (bool): If True, only prints what would be copied
    """

    if not os.path.exists(src_backup_folder):
        raise ValueError(f"Backup folder does not exist: {src_backup_folder}")

    os.makedirs(dst_session_folder, exist_ok=True)

    restored_count = 0
    skipped_count = 0
    files_to_copy = []
    total_fits_files = 0

    for root, dirs, files in os.walk(src_backup_folder):
        # Determine relative path to preserve folder structure
        rel_path = os.path.relpath(root, src_backup_folder)
        target_dir = os.path.join(dst_session_folder, rel_path)
        os.makedirs(target_dir, exist_ok=True)
        i = 0

        for f in files:
            if f.lower().endswith(".fits") and not f.startswith("stacked-16_"):
                src_file = os.path.join(root, f)
                dst_file = os.path.join(target_dir, f)

                if os.path.exists(dst_file):
                    skipped_count +=1
                    continue  # skip existing files
                files_to_copy.append((src_file, dst_file))               
                total_fits_files += 1

    for i, (src_file, dst_file) in enumerate(files_to_copy, 1):
        if app.cancel_restore:
            break  # stop restoring if cancel requested

        progress = round((i + 1) / total_fits_files * 100)

        if dry_run:
            print(f"[DRY RUN] Would copy: {src_file} → {dst_file}")
        else:
            shutil.copy2(src_file, dst_file)
            restored_count += 1
            print(f"Restored: {dst_file}")
            app.progress.value = round(progress)

    print("\nSummary:")
    print(f"  Restored FITS files: {restored_count}")
    print(f"  Skipped (already exist): {skipped_count}")
    print(f"  Total files: {total_fits_files}")
    
    app.cancel_button.visible = False
    
    return restored_count, skipped_count, total_fits_files
#################
# FITS Functions
#################

def get_total_exposure(fits_file):
    try:
        with fits.open(fits_file) as hdul:
            return float(hdul[0].header.get("EXPTIME", 0))
    except Exception as e:
        safe_print(f"Error reading EXPTIME from {fits_file}: {e}")
        return 0

def get_total_mosaic_exposure(mosaic_dir: str) -> float:
    """
    Return total exposure time (in seconds) for a restacked mosaic directory
    by summing exposures of all stacked_16*.fits files in subdirectories.
    """
    total_exposure = 0.0

    try:
        for subdir in sorted(os.listdir(mosaic_dir)):
            panel_path = os.path.join(mosaic_dir, subdir)
            if not os.path.isdir(panel_path):
                continue

            # Find stacked_16*.fits file
            fits_files = glob.glob(os.path.join(panel_path, "stacked-16*.fits"))
            if not fits_files:
                continue

            fits_path = fits_files[0]
            try:
                # Add this panel’s exposure
                total_exposure += get_total_exposure(fits_path)
            except Exception as e:
                print(f"Error reading exposure for {fits_path}: {e}")

    except FileNotFoundError as e:
        print(f"Mosaic directory not found: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

    return total_exposure

def get_ra_in_hours(hdr):
    ra_value = hdr.get('RA')
 
    try:
        return float(ra_value) / 15 if ra_value is not None else None
    except (TypeError, ValueError):
        return None

def read_fits_metadata(fits_file, convert_to_hour = False):
    """Read RA, DEC, OBJECT, etc. from a local FITS file.
    Returns a dict of metadata, or None if the file is invalid or missing data.
    """
    try:
        with fits.open(fits_file) as hdul:
            if len(hdul) == 0 or hdul[0].header is None:
                # Empty FITS or no header
                return None

            hdr = hdul[0].header

            binning = ''
            if hdr.get('XBINNING') and hdr.get('YBINNING'):
                binning = f"{hdr.get('XBINNING', '')}x{hdr.get('YBINNING', '')}"

            metadata = {
                'TELESCOP': hdr.get('TELESCOP', ''),
                'OBJECT': hdr.get('OBJECT', ''),
                'RA':  get_ra_in_hours(hdr) if convert_to_hour else hdr.get('RA', ''),
                'DEC': hdr.get('DEC', ''),
                'EXPTIME': hdr.get('EXPTIME', ''),
                'DATE-OBS': hdr.get('DATE-OBS', ''),
                'FILTER': hdr.get('FILTER', '').strip(),
                'CAMERA': hdr.get('CAMERA', '').strip(),
                'TEMP': hdr.get('DET-TEMP', ''),
                'GAIN': hdr.get('GAIN', ''),
                'BINNING': binning,
            }
            # If no useful data (RA, DEC, OBJECT, etc.), return None
            if not any(metadata.values()):
                return None

            return metadata

    except (OSError, VerifyError, FileNotFoundError, Exception):
        # Not a FITS file, unreadable, or corrupted
        return None

#######################
# Conversion functions
#######################

def parse_exposure(exp_str):
    """
    Convert exposure string like '30s' or '1/250s' to seconds as float.
    """
    if not exp_str or not exp_str.endswith('s'):
        return 0.0
    value = exp_str[:-1]  # Remove trailing 's'
    if '/' in value:
        # Handle fractional exposure: e.g., '1/250'
        try:
            numerator, denominator = value.split('/')
            return float(numerator) / float(denominator)
        except:
            return 0.0
    else:
        try:
            return float(value)
        except:
            return 0.0

def hours_to_hms(ra_hours_str):
    if not ra_hours_str:
        return "N/A"
    if not isinstance(ra_hours_str, (float, int)):
        if any(x in ra_hours_str for x in ["h", "m", "s"]):
             return ra_hours_str  # Already formatted
    hours = float(ra_hours_str)
    h = int(hours)
    m = int((hours - h) * 60)
    s = (hours - h - m / 60) * 3600
    return f"{h:02d}h {m:02d}m {s:05.2f}s"

def deg_to_dms(dec_deg_str):
    if not dec_deg_str:
        return "N/A"
    if not isinstance(dec_deg_str, (float, int)):
        if any(x in dec_deg_str for x in ["°", "′", "″"]):
            return dec_deg_str  # Already formatted
    dec_deg = float(dec_deg_str)
    sign = "+" if dec_deg >= 0 else "-"
    dec_deg = abs(dec_deg)
    d = int(dec_deg)
    m = int((dec_deg - d) * 60)
    s = (dec_deg - d - m / 60) * 3600
    return f"{sign}{d:02d}° {m:02d}′ {s:05.2f}″"

def hms_to_hours(hms_str: str) -> float:
    """Convert 'HHh MMm SS.Ss' to decimal hours (float)."""
    if isinstance(hms_str, (float, int)):
        return float(hms_str)  # Already numeric

    try:
        hms_str = hms_str.lower().replace('h', ' ').replace('m', ' ').replace('s', '')
        parts = hms_str.strip().split()
        h = float(parts[0]) if len(parts) > 0 else 0
        m = float(parts[1]) if len(parts) > 1 else 0
        s = float(parts[2]) if len(parts) > 2 else 0
        return h + m / 60 + s / 3600
    except Exception as e:
        safe_print(f"[ERROR] Invalid HMS input: {hms_str} → {e}")
        return 0.0

def dms_to_degrees(dms_str: str) -> float:
    """Convert '+DD° MM′ SS.S″' to decimal degrees (float)."""
    if isinstance(dms_str, (float, int)):
        return float(dms_str)  # Already numeric

    try:
        dms_str = dms_str.replace('°', ' ').replace('′', ' ').replace('″', '').replace('’', ' ')
        sign = -1 if dms_str.strip().startswith('-') else 1
        parts = dms_str.strip().lstrip('+-').split()
        d = float(parts[0]) if len(parts) > 0 else 0
        m = float(parts[1]) if len(parts) > 1 else 0
        s = float(parts[2]) if len(parts) > 2 else 0
        return sign * (d + m / 60 + s / 3600)
    except Exception as e:
        safe_print(f"[ERROR] Invalid DMS input: {dms_str} → {e}")
        return 0.0

def format_seconds_hms( total_seconds):
    if not total_seconds or total_seconds == "":
        return "N/A"
    total_seconds = int(float(total_seconds))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or not parts:
        parts.append(f"{seconds}s")
    return ' '.join(parts)

#########################
# DSO Catalog functions
#########################

def preprocess_dso_catalog_json(original_json_path = CATALOG_FILE, output_json_path = SKY_CATALOG_FILE):
    if os.path.exists(output_json_path):
        safe_print(f"[INFO] Using cached DSO catalog: {output_json_path}")
        return  # Already exists

    safe_print("[INFO] Preprocessing original DSO catalog...")

    with open(original_json_path, 'r', encoding='utf-8') as f:
        raw_catalog = json.load(f)

    processed_catalog = []

    for entry in raw_catalog:
        try:
            ra_str = entry.get("ra")
            dec_str = entry.get("dec")
            coord = SkyCoord(ra=ra_str, dec=dec_str, unit=(u.hourangle, u.deg), frame='icrs')
            entry["ra_deg"] = coord.ra.degree
            entry["dec_deg"] = coord.dec.degree
            processed_catalog.append(entry)
        except Exception as e:
            safe_print(f"[WARN] Skipping {entry.get('name')} due to error: {e}")

    with open(output_json_path, 'w', encoding='utf-8') as f:
        json.dump(processed_catalog, f, indent=2)

    safe_print(f"[OK] Preprocessed catalog saved to: {output_json_path}")


def write_target_json(session_dir, original_target, name, description):
    """
    Write target.json in the given session directory.

    Parameters
    ----------
    session_dir : str or Path
        Folder where the target.json file will be written
    original_target : str
        Original target from the telescope (ex: HD 198626)
    name : str
        Identified object name (ex: NGC 6960 - Veil Nebula)
    description : str
        Full description from the database
    """

    data = {
        "original_target": original_target,
        "identified_object": {
            "name": name,
            "description": description
        }
    }

    file_path = Path(session_dir) / "target.json"

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

############################
# DWARF LOCAL Dir functions
############################

def create_local_dwarf_dir(conn: sqlite3.Connection):

    DwarfLocal_dir = get_local_dwarf_dir(conn)
    try:
        os.makedirs(DwarfLocal_dir, exist_ok=True)
        return DwarfLocal_dir
    except Exception as e:
        safe_print(f"[FAIL] Failed to create directory: {e}")
        return False

def get_local_dwarf_dir(conn: sqlite3.Connection, dwarf_id = None):
    local_DB_Dwarf_dir = get_db_local_dwarf_dir(conn)

    if not local_DB_Dwarf_dir:
        local_DB_Dwarf_dir = "."

    local_Main_Dwarf_dir = os.path.join(local_DB_Dwarf_dir, "Dwarf_Local")
    if dwarf_id:
        local_Dwarf_dir = os.path.join(local_Main_Dwarf_dir, f"DWARF_{dwarf_id}")
        return local_Dwarf_dir
    else:
        return local_Main_Dwarf_dir

def empty_local_archive_dwarf_dir(dwarf_id = None):
    local_Main_Dwarf_dir = os.path.join(".", "Dwarf_Local")
    if dwarf_id:
        local_Dwarf_dir = os.path.join(local_Main_Dwarf_dir, f"DWARF_{dwarf_id}")

        if not os.path.exists(local_Dwarf_dir):
            safe_print(f"Local Directory not found: {local_Dwarf_dir}")
            return False

        archive_Dwarf_dir = os.path.join(local_Dwarf_dir, "Archive")

        # empty subdirs
        if not os.path.exists(archive_Dwarf_dir):
            safe_print(f"Archive Directory not found: {archive_Dwarf_dir}")
            return False

        # Loop through everything inside the DWARF_x directory
        for item in os.listdir(archive_Dwarf_dir):
            item_path = os.path.join(archive_Dwarf_dir, item)
            # Prefix to handle long Windows paths
            abs_path = os.path.abspath(item_path)
            if os.name == "nt":
                abs_path = "\\\\?\\" + abs_path

            try:
                if os.path.isfile(abs_path) or os.path.islink(abs_path):
                    os.remove(abs_path)  # remove file or symlink
                elif os.path.isdir(abs_path):
                    shutil.rmtree(abs_path)  # remove directory recursively
            except FileNotFoundError:
                print(f"Already gone: {item_path}")
            except Exception as e:
                safe_print(f"Failed to delete {item_path}. Reason: {e}")

        return True
    else:
        return False

def is_path_local_dwarf_dir(full_path):
    return "Dwarf_Local" in str(full_path)


###############################
# JSON extract parse functions
###############################

def parse_shots_info(json_path, ftp=None):
    try:
        if json_path.startswith("ftp://"):
            # Handle FTP case
            if not ftp:
                safe_print(f"[FAIL] FTP connection is required for {json_path}.")
                return {}

            # Extracting the path on FTP server
            ftp_path = json_path.replace("ftp://", "")
            with open("temp_shotsInfo.json", "wb") as temp_file:
                ftp.retrbinary(f"RETR {ftp_path}", temp_file.write)

            with open("temp_shotsInfo.json", 'r', encoding='utf-8') as f:
                raw = json.load(f)

        else:
            # Local file handling
            with open(json_path, 'r', encoding='utf-8') as f:
                raw = json.load(f)

        format = ""
        shotsToTake = raw.get("shotsToTake")
        shotsTaken = raw.get("shotsTaken")
        # case RESTACKED
        if raw.get("shotsToStack"):
            # default format FITS
            format= "FITS"
            shotsToTake = raw.get("shotsToStack")
            if raw.get("shotsDiscard"):
                shotsTaken = shotsToTake - raw.get("shotsDiscard")

        return {
            "dec": str(raw.get("DEC")),
            "ra": str(raw.get("RA")),
            "target": raw.get("target"),
            "binning": raw.get("binning"),
            "format": raw.get("format") if raw.get('format') is not None else format,
            "exp_time": str(raw.get("exp")) if raw.get('exp') is not None else None,
            "gain": raw.get("gain"),
            "shotsToTake": shotsToTake,
            "shotsTaken": shotsTaken,
            "shotsStacked": raw.get("shotsStacked"),
            "ircut": raw.get("ir"),
            "maxTemp": raw.get("maxTemp"),
            "minTemp": raw.get("minTemp"),
        }

    except Exception as e:
        safe_print(f"Error reading {json_path}: {e}")
        return {}

def extract_session_datetime(filename: str) -> datetime | None:
    try:
        # Try format with dashes: YYYY-MM-DD-HH-MM-SS-fff
        match_dash = re.search(r"(\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}-\d{3,6})", filename)
        if match_dash:
            return datetime.strptime(match_dash.group(1), "%Y-%m-%d-%H-%M-%S-%f")

        # Try compact format: YYYYMMDDHHMMSSfff
        match_compact = re.search(r"(\d{17})", filename)
        if match_compact:
            return datetime.strptime(match_compact.group(1), "%Y%m%d%H%M%S%f")

        match_new = re.search(r"(\d{8}-\d{9})", filename)
        if match_new:
            return datetime.strptime(match_new.group(1), "%Y%m%d-%H%M%S%f")

    except Exception as e:
        safe_print(f"Error parsing datetime from filename: {e}")
    
    return None

# Function to parse shotsInfo.json
def extract_target_json(astro_path):
    json_path = os.path.join(astro_path, 'shotsInfo.json')

    if os.path.exists(json_path):
        with open(json_path, 'r') as file:
            meta = json.load(file)
    else:
        meta = {}

    if meta:
        return meta.get('target'), str(meta['DEC']) if 'DEC' in meta else None, str(meta['RA']) if 'RA' in meta else None
    else:
        return None, None, None

def show_date_session(date_db):
    dt = datetime.strptime(date_db, "%Y-%m-%d %H:%M:%S.%f")
    date_session = dt.strftime("%B %d, %Y at %I:%M:%S %p")
    return date_session

def show_short_date_session(date_db):
    dt = datetime.strptime(date_db, "%Y-%m-%d %H:%M:%S.%f")
    date_session = dt.strftime("%b %d, %Y %I:%M %p")
    return date_session

def extract_astro_name_from_folder(folder_name: str) -> str | None:
    """
    Extract the name of the astronomical object from a folder:
    - DWARF_RAW_TELE_<ASTRO>_EXP_... (Dwarf3)
    - DWARF_RAW_<ASTRO>_EXP_...      (Dwarf2)
    """
    patterns = [
        r"DWARF_RAW_TELE_(.+?)_EXP_",
        r"DWARF_RAW_WIDE_(.+?)_EXP_",
        r"RESTACKED_DWARF_RAW_TELE_MOSAIC_(.+?)_",
        r"RESTACKED_DWARF_RAW_WIDE_MOSAIC_(.+?)_",
        r"RESTACKED_DWARF_RAW_TELE_(.+?)_",
        r"RESTACKED_DWARF_RAW_WIDE_(.+?)_",
        r"DWARF_RAW_(.+?)_EXP_"
    ]
    for pattern in patterns:
        m = re.match(pattern, folder_name)
        if m:
            name = m.group(1).strip()

            # Check if the pattern itself had "MOSAIC"
            if "_MOSAIC_" in pattern:
                name = "MOSAIC_" + name

            return name

    return None

def save_shots_info(json_path, linked_data):
    """
    Save a shotsInfo.json file from the linked_data structure
    (reverse of parse_shots_info).

    linked_data should contain keys like:
    'ra', 'dec', 'target', 'binning', 'format', 'exp_time',
    'gain', 'shotsToTake', 'shotsTaken', 'shotsStacked',
    'ircut', 'maxTemp', 'minTemp'
    """
    try:
        # Build JSON structure similar to original input
        raw = {
            "RA": linked_data.get("ra"),
            "DEC": linked_data.get("dec"),
            "target": linked_data.get("target"),
            "binning": linked_data.get("binning"),
            "format": linked_data.get("format"),
            "exp": float(linked_data["exp_time"]) if linked_data.get("exp_time") else None,
            "gain": linked_data.get("gain"),
            "shotsToTake": linked_data.get("shotsToTake"),
            "shotsTaken": linked_data.get("shotsTaken"),
            "shotsStacked": linked_data.get("shotsStacked"),
            "ir": linked_data.get("ircut"),
            "maxTemp": linked_data.get("maxTemp"),
            "minTemp": linked_data.get("minTemp"),
        }

        # Remove None values for cleanliness
        raw = {k: v for k, v in raw.items() if v is not None}

        # Ensure output directory exists
        dir_path = os.path.dirname(json_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
    
        # Write JSON file
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(raw, f, indent=4, ensure_ascii=False)

        print(f"[OK] Saved {json_path}")

    except Exception as e:
        print(f"[FAIL] Error writing {json_path}: {e}")

#################################
# Object Name functions
#################################

def get_name_object(name):
    name_object = name #name.split(" (")[0]
    # Start by removing anything after the last ' [' (suffix)
    main_part = name.split(" [")[0]

    # Then optionally remove anything after ' (' inside main_part
    main_part = main_part.split(" (")[0]

    # Now detect the suffix from the original name
    bracket_pos = name.rfind(" [")
    suffix = name[bracket_pos:] if bracket_pos != -1 else ""

    # Only re-add suffix if it's not already included
    name_object = (f"{main_part} {suffix}").strip() if suffix and suffix not in main_part else main_part.strip()

    return name_object, main_part

#################################
# Sessions List functions
#################################

def is_Restacked(session_name):
   return session_name.startswith("RESTACKED_")

def transform_session_name_old(name: str) -> str:
    original_name = name.strip()

    # --- Ignore purely numeric DWARF_RAW sessions --- 
    if re.fullmatch(r'DWARF_RAW_\d{17}(_\d+_\d+)?', original_name):
        return None

    # --- Clean known prefixes ---
    name = re.sub(r'^(RESTACKED_)?DWARF_RAW_(TELE_|WIDE_)?', '', original_name)
    name = re.sub(r'^MOSAIC_', '', name)
    name = name.replace('Duo-Band_', '').strip()

    # --- Ignore Sun / Moon sessions (robust underscore-safe match) ---
    if re.search(r'(^|_)Sun(_|$)', name, re.IGNORECASE) or re.search(r'(^|_)Moon(_|$)', name, re.IGNORECASE):
        return None

    # --- Remove exposure/gain and similar metadata ---
    name = re.sub(r'_EXP_[\d\.]+_GAIN_\d+_', '_', name)
    name = re.sub(r'_Astro_|_Unknown_', '_', name)

    # --- Detect and normalize datetime formats ---
    m1 = re.search(r'(\d{8})-(\d{2})(\d{2})', name)
    m2 = re.search(r'(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})', name)
    m3 = re.search(r'(\d{8})_(\d{2}):(\d{2})-\d+', name)

    if m1:
        date, hour, minute = m1.group(1), m1.group(2), m1.group(3)
        display = re.sub(r'\d{8}-\d{9}', f"{date}_{hour}:{minute}", name)
    elif m2:
        year, month, day, hour, minute = m2.groups()
        display = re.sub(
            r'\d{4}-\d{2}-\d{2}-\d{2}-\d{2}(-\d{2,})?',
            f"{year}{month}{day}_{hour}:{minute}", name
        )
    elif m3:
        date, hour, minute = m3.groups()
        display = re.sub(r'(\d{8})_(\d{2}):(\d{2})-\d+', f"{date}_{hour}:{minute}", name)
    else:
        display = name.replace('-', '_')

    # --- Remove trailing milliseconds like -471 ---
    display = re.sub(r'-\d+$', '', display)

    # --- Cleanup --- 
    display = re.sub(r'_EXP_[\d\.]+_GAIN_\d+', '', display)
    display = re.sub(r'__+', '_', display)
    display = display.strip('_')
    display = re.sub(r'_+(\d{8}_\d{2}:\d{2})', r'_\1', display)
    display = display.strip()

    if not re.search(r'[A-Za-z]', display):
        return None

    return display

def transform_session_name(name: str) -> str:
    original_name = name.strip()

    # --- Ignore purely numeric DWARF_RAW sessions ---
    if re.fullmatch(r'DWARF_RAW_\d{17}(_\d+_\d+)?', original_name):
        return None

    # --- Clean known prefixes ---
    name = re.sub(r'^(RESTACKED_)?DWARF_RAW_(TELE_|WIDE_)?', '', original_name)
    name = re.sub(r'^MOSAIC_', '', name)
    name = name.replace('Duo-Band_', '').strip()

    # --- Ignore Sun / Moon sessions (robust underscore-safe match) ---
    if re.search(r'(^|_)Sun(_|$)', name, re.IGNORECASE) or re.search(r'(^|_)Moon(_|$)', name, re.IGNORECASE):
        return None

    # --- Remove exposure/gain and similar metadata ---
    name = re.sub(r'_EXP_[\d\.]+_GAIN_\d+_', '_', name)
    name = re.sub(r'_Astro_|_Unknown_', '_', name)

    # --- Detect and normalize datetime formats ---
    m1 = re.search(r'(\d{8})-(\d{2})(\d{2})', name)
    m2 = re.search(r'(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})', name)
    m3 = re.search(r'(\d{8})_(\d{2}):(\d{2})-\d+', name)

    if m1:
        date, hour, minute = m1.group(1), m1.group(2), m1.group(3)
        display = re.sub(r'\d{8}-\d{9}', f"{date}_{hour}:{minute}", name)
    elif m2:
        year, month, day, hour, minute = m2.groups()
        display = re.sub(
            r'\d{4}-\d{2}-\d{2}-\d{2}-\d{2}(-\d{2,})?',
            f"{year}{month}{day}_{hour}:{minute}",
            name
        )
    elif m3:
        date, hour, minute = m3.groups()
        display = re.sub(r'(\d{8})_(\d{2}):(\d{2})-\d+', f"{date}_{hour}:{minute}", name)
    else:
        display = name.replace('-', '_')

    # --- Remove trailing milliseconds like -471 ---
    display = re.sub(r'-\d+$', '', display)

    # --- Cleanup ---
    display = re.sub(r'_EXP_[\d\.]+_GAIN_\d+', '', display)
    display = re.sub(r'__+', '_', display)
    display = display.strip('_')
    display = re.sub(r'_+(\d{8}_\d{2}:\d{2})', r'_\1', display)
    display = display.strip()

    if not re.search(r'[A-Za-z]', display):
        return None

    return display

def extract_core_name(path: str) -> str:
    filename = Path(path).name  # stacked-16_NGC 2246_45s60_Duo-Band_20251120-013033269.fits

    # Remove extension
    filename_no_ext = filename.replace('.fits', '')
    # For Mosaic ext is zip
    filename_no_ext = filename_no_ext.replace('.zip', '')

    # Extract part after "stacked-XX_"
    m = re.search(r'stacked-\d+_(.+)', filename_no_ext)
    if m:
        return m.group(1)

    return filename_no_ext  # fallback

def extract_datetime_from_session_name(session_name: str):
    """
    Extracts date/time information from a cleaned DWARF session name.

    Returns a datetime_obj
    where:
      - datetime_obj is a Python datetime or None
    """
    if not session_name:
        return None

    # Match date with optional time (accepts '_' or '-' and ':' or '-')
    m = re.search(r'(\d{8})(?:[_\-](\d{2})[:\-](\d{2}))?', session_name)
    if not m:
        return None

    date_str = m.group(1)
    hour = m.group(2)
    minute = m.group(3)

    # Build normalized date string
    if hour and minute:
        full_str = f"{date_str}_{hour}:{minute}"
    else:
        full_str = date_str

    # Try to parse datetime
    dt = None
    try:
        if hour and minute:
            dt = datetime.strptime(full_str, "%Y%m%d_%H:%M")
        else:
            dt = datetime.strptime(full_str, "%Y%m%d")
    except ValueError:
        pass

    return dt


def get_session_detail(conn, row, dwarf_id):
    label_title = ""
    label_text = ""
    thumbnail_path = None
    image_path = None

    if len(row) > 0:
        # extract DB Values
        dwarf_data_id = row[0]
        file_path = row[1]
        exp_time = row[2]
        gainDB = row[3]
        IR_filter  = row[4]
        stacks = row[5]
        backup_path = row[6]  # location from BackupDrive or USB Dwarf
        session_date = row[7]
        session_dir = row[8]
        dwarf_name = row[9]
        minTemp = row[10]
        maxTemp = row[11]
        is_favorite = row[12]  # The favorite column (0 or 1)
        init_target = row[13]
        declination = row[14]
        right_ascencion = row[15]
        astro_object_id = row[16]
        astro_group_id = row[17]
        descriptionDB = row[18]

        # display Values
        session_date = show_short_date_session(session_date)
        lens = "(W) " if ("_WIDE_") in session_dir else ""
        exp = f"{exp_time}s" if exp_time is not None else "N/A"
        exp_value = parse_exposure(exp) if exp != "N/A" else 0
        gain = gainDB if gainDB is not None else "N/A"
        astro_filter = f"{IR_filter}" if IR_filter else "No Filter"

        info_stack = RESTACK if is_Restacked(session_dir) else TAKEN
        target = init_target[:10]
        description,_ =  get_name_object(descriptionDB)
        # Building the details string with the star icon
        label_text = f"{description}\n"
        label_text = label_text + f"{info_stack} with 🔭 {dwarf_name}{lens} 📅 {session_date} ⚙️ Exp {exp}, Gain {gain}, {astro_filter} 📊 Stacks {stacks}\n"
        label_text = label_text + f" RA: {hours_to_hms(right_ascencion)} | Dec: {deg_to_dms(declination)}\n"

        full_path = get_Backup_fullpath (conn, backup_path, "", file_path, dwarf_id)
        astro_files = check_files(full_path)

        # get exposure for Restacked session
        exposure_time = format_seconds_hms(exp_value * stacks)
        if is_Restacked(session_dir):
            if "_MOSAIC_" in full_path:
                exposure_time = format_seconds_hms(get_total_mosaic_exposure(os.path.dirname(full_path)))
            else:
                fits_path = astro_files.get('fits')
                if fits_path and os.path.isfile(fits_path):
                    exposure_time = format_seconds_hms(get_total_exposure(fits_path))

        label_title = f"Session: {session_dir}"
        label_text = label_text + f"{stacks} stacked shots for a total exposure time of {exposure_time}"
        thumbnail_path = astro_files.get('thumbnail')
        image_path = astro_files.get('jpg') or astro_files.get('png')
        print(image_path)
    return label_title, label_text, thumbnail_path, image_path


#################################
# Dwarf ID / Backup Id functions
#################################

def get_or_create_dwarf_id(conn, dwarf_id=None, batch_mode=False, default_name="Default Dwarf", default_description="Auto-created"):

    if dwarf_id is not None:
        # Vérify D exists
        if is_dwarf_exists(conn, dwarf_id):
            return dwarf_id
        elif batch_mode:
            # Create if not found
            dwarf_id = add_dwarf_detail(conn, default_name, default_description, "", "2", "", None)
            return dwarf_id
        else:
            raise ValueError(f"Dwarf ID {dwarf_id} non trouvé.")

    # No dwarf_id given
    dwarfs = get_dwarf_Names(conn)

    if dwarfs:
        if batch_mode:
            # Get the first one
            return dwarfs[0][0]
        else:
            safe_print("Dwarfs existing: ")
            for d_id, d_name in dwarfs:
                safe_print(f"  [{d_id}] {d_name}")
            try:
                dwarf_id = int(input("Enter the ID of the Dwarf to associate:"))
            except ValueError:
                raise ValueError("Invalid ID.")
            return dwarf_id
    else:
        if batch_mode:
            # Create a Dwarf Id if none exists
            dwarf_id = add_dwarf_detail(conn, default_name, default_description, "", "2", "", None)
            return dwarf_id
        else:
            create = input("No Dwarf. Do you want to create one? (y/n):").strip().lower()
            if create == 'o':
                name = input("Name of the new Dwarf:").strip()
                desc = input("Description: ").strip()
                dwarf_id = add_dwarf_detail(conn, name, desc, "", "2", "", None)
                return dwarf_id
            else:
                raise ValueError("No Dwarf, cancellation.")

def insert_or_get_backup_drive(conn, location, dwarf_id=None):
    row = get_backupDrive_id_from_location(conn, location)
    if row:
        found_id, found_dwarf_id = row
        if dwarf_id is None:
            return found_id, found_dwarf_id
        else:
            return found_id, dwarf_id  # dwarf_id given could be replaced
    else:
        try:
            dwarf_id = get_or_create_dwarf_id(conn)
        except ValueError as e:
            safe_print(f"Erreur : {e}")
            safe_print("No action taken. Please create a Dwarf first.")
            sys.exit(1)  

        name = os.path.basename(location.rstrip("\\/"))
        description = f"Auto-added for path {location}"
        astroDir = "DATA_OBJECTS"

        backupDrive_id = add_backupDrive_detail(conn, name, description, location, astroDir, dwarf_id)
        return backupDrive_id, dwarf_id

##########################
# Session Dir functions
##########################

def determine_session_dir(data_root, session_dir_path, ftp_mode=False):
    # session_dir_path must be inside data_root"
    if not session_dir_path.startswith(data_root):
        return None, None

    # Normalize separators for FTP mode
    if ftp_mode:
        data_root = data_root.strip('/')
        session_dir_path = session_dir_path.strip('/')
        if not session_dir_path.startswith(data_root):
            return None, False
        relative_path = os.path.relpath('/' + session_dir_path, '/' + data_root)
        sep = '/'
    else:
        if not session_dir_path.startswith(data_root):
            return None, False
        relative_path = os.path.relpath(session_dir_path, data_root)
        sep = os.sep

    session_dir_main_dir = relative_path.split(sep)[0]
    session_dir = os.path.basename(session_dir_path)
    is_session_dir = session_dir_main_dir == session_dir

    return session_dir_main_dir, is_session_dir

def check_dir_session (root, dirs, files, session_dir_main_dir, session_dir):
    root_basename = os.path.basename(os.path.normpath(root))

    if session_dir_main_dir:
        return session_dir == root_basename

    # ❌ Exclude 'Thumbnail' directory itself
    if root_basename == 'Thumbnail':
        return False

    # ✅ Accept Mosaic main dir, but reject its children
    if "_MOSAIC_" in os.path.basename(os.path.dirname(root)):
        return False  # Reject children of mosaic
    if "_MOSAIC_" in root_basename:
        return True  # Accept parent

    # ✅ Accept normal session dir if:
    #    - it's a leaf with files
    #    - or only contains 'Thumbnail' folder and maybe files
    if not dirs:
        return bool(files)
    elif dirs == ['Thumbnail']:  
        return True

    # ❌ Otherwise it's a container with other subdirs (multi-part or something else)
    return False


#################################
# Dwarf / Backup Data functions
#################################

def insert_dwarf_data(conn, root, filepath, astro_object_id = None, new_astro_object = False):
    relative_path = os.path.relpath(filepath, root)
    safe_print(f"insert_dwarf_data : path : {filepath}")
    safe_print(f"insert_dwarf_data : rel-path : {relative_path}")
    filetype = Path(filepath).suffix[1:].lower()
    size = os.path.getsize(filepath)
    mtime = int(os.path.getmtime(filepath))

    file_path = Path(filepath)
    parent_dir = file_path.parent

    base_dir = os.path.dirname(filepath)
    json_path = os.path.join(base_dir, 'shotsInfo.json')
    thumbnail_path = os.path.join(base_dir, 'stacked_thumbnail.jpg')

    # Search for a stacked*.fits file in same directory
    # For Mosaic search for stacked*.zip
    stacked_path = None
    stacked_md5 = None
    if "_MOSAIC_" in str(parent_dir):
        for f in parent_dir.glob("stacked*.zip"):
            stacked_path = f.relative_to(root).as_posix()
            safe_print(f"test_dwarf_data : stacked_path : {stacked_path}")
            stacked_md5 = compute_md5(f)
            break  # first one found
    else:
        for f in parent_dir.glob("stacked*.fits"):
            stacked_path = f.relative_to(root).as_posix()
            safe_print(f"test_dwarf_data : stacked_path : {stacked_path}")
            stacked_md5 = compute_md5(f)
            break  # first one found

    meta = parse_shots_info(json_path) if os.path.exists(json_path) else {}
    thumbnail = os.path.relpath(thumbnail_path, root) if os.path.exists(thumbnail_path) else None

    # add RA, Dec to Astro_object if just created
    #if astro_object_id and new_astro_object :
    #    update_astro_object_coord(conn, astro_object_id, meta.get('dec'), meta.get('ra'))

    new_value , data_id = insert_DwarfData (conn, relative_path, mtime, thumbnail, size,
        meta.get('dec'), meta.get('ra'), meta.get('target'),
        meta.get('binning'), meta.get('format'), meta.get('exp_time'),
        meta.get('gain'), meta.get('shotsToTake'), meta.get('shotsTaken'),
        meta.get('shotsStacked'), meta.get('ircut'), meta.get('maxTemp'), meta.get('minTemp'),
        "0","0", 4, stacked_path, stacked_md5)

    return new_value, data_id


######################
# SYNC Main functions
######################

def sync_dwarf_sessions(dwarf_id, source_root, local_root="./Dwarf_Local", session_name=None, log=None):
    dwarf_dir = os.path.join(local_root, f"DWARF_{dwarf_id}")
    archive_dir = os.path.join(dwarf_dir, "Archive")
    os.makedirs(archive_dir, exist_ok=True)
    safe_print(f"source_root: {source_root}")

    excluded_dirs = {"Archive", "CALI_FRAME", "Solving_Failed", "DWARF_DARK", "RESTACKED", "STARTRAILS"}
    session_dirs = [
        d for d in os.listdir(source_root) 
        if os.path.isdir(os.path.join(source_root, d)) and d not in excluded_dirs
    ]
    # Look for RESTACKED subdirectory inside source_root
    source_restacked = os.path.join(source_root, "RESTACKED")
    if os.path.isdir(source_restacked):
        session_dirs_RESTACKED = [
            os.path.join("RESTACKED", d)  # keep relative path
            for d in os.listdir(source_restacked)
            if os.path.isdir(os.path.join(source_restacked, d))
        ]
    else:
        session_dirs_RESTACKED = []

    # Look for STARTRAILS subdirectory inside source_root
    source_startrails = os.path.join(source_root, "STARTRAILS")
    if os.path.isdir(source_startrails):
        session_dirs_STARTRAILS = [
            os.path.join("STARTRAILS", d)  # keep relative path
            for d in os.listdir(source_startrails)
            if os.path.isdir(os.path.join(source_startrails, d))
        ]
    else:
        session_dirs_STARTRAILS = []

    # Combine both lists
    all_sessions = session_dirs + session_dirs_RESTACKED + session_dirs_STARTRAILS
    safe_print(all_sessions)

    # If a specific session is provided, filter it
    if session_name:
        all_sessions = [
            s for s in all_sessions
            if s == session_name or s == os.path.join("RESTACKED", session_name) or s == os.path.join("STARTRAILS", session_name)
        ]
    safe_print(f"final all_sessions {all_sessions}")

    # Sessions present in dwarf_dir, excepted in "Archive" and "RESTACKED" and "STARTRAILS"
    local_sessions = [
        d for d in os.listdir(dwarf_dir)
        if os.path.isdir(os.path.join(dwarf_dir, d)) and d not in excluded_dirs
    ]

    # add those in RESTACKED subdirectory
    restacked_path = os.path.join(dwarf_dir, "RESTACKED")
    if os.path.isdir(restacked_path):
        restacked_sessions = [
            os.path.join("RESTACKED", d)
            for d in os.listdir(restacked_path)
            if os.path.isdir(os.path.join(restacked_path, d))
        ]
        local_sessions += restacked_sessions
    safe_print(local_sessions)
    print_log(f"\n🔄 Syncing {len(all_sessions)} sessions from source...\n", log)

    # add those in STARTRAILS subdirectory
    source_startrails = os.path.join(dwarf_dir, "STARTRAILS")
    if os.path.isdir(source_startrails):
        restacked_sessions = [
            os.path.join("STARTRAILS", d)
            for d in os.listdir(source_startrails)
            if os.path.isdir(os.path.join(source_startrails, d))
        ]
        local_sessions += restacked_sessions
    safe_print(local_sessions)
    print_log(f"\n🔄 Syncing {len(all_sessions)} sessions from source...\n", log)

    for session in all_sessions:
        print_log(f"✅ Checking local session {session}.", log)
        src_session = os.path.join(source_root, session)
        dst_session = (
            os.path.join(dwarf_dir, "RESTACKED", session)
            if session_name and session_name.startswith("RESTACKED_")
            else os.path.join(dwarf_dir, "STARTRAILS", session)
            if session_name and session_name.startswith("RESTACKED_")
            else os.path.join(dwarf_dir, session)
        )
        os.makedirs(dst_session, exist_ok=True)
        safe_print(f"src_session {src_session}")
        safe_print(f"dst_session {dst_session}")
        dst_session = os.path.abspath(dst_session)
        safe_print(dst_session)
        for file_name in os.listdir(src_session):
            if file_name.startswith("stacked") or file_name == "shotsInfo.json":
                src_file = win_long_path(os.path.join(src_session, file_name))
                dst_file = win_long_path(os.path.join(dst_session, file_name))
                if files_are_different(src_file, dst_file, file_name == "shotsInfo.json"):
                    safe_print(f"Copying {file_name} to {session}...")
                    print_log(f"📥 Copying {file_name} to {session}...", log)
                    shutil.copy2(src_file, dst_file)
                else:
                    safe_print(f"Skipping {file_name} (unchanged)")
                    print_log(f"✅ Skipping {file_name} (unchanged)", log)

    safe_print("\nCopy complete.")

    # Archive removed sessions only full backup
    if not session_name:
        removed_sessions = set(local_sessions) - set(all_sessions)
        for session in removed_sessions:
            src_path = os.path.join(dwarf_dir, session)
            dst_path = os.path.join(archive_dir, session)

            if os.path.exists(dst_path):
                shutil.rmtree(dst_path)   # careful: deletes everything in that folder!

            print_log(f"📦 Archiving removed session: {session}", log)
            shutil.move(src_path, dst_path)

    print_log("\n✅ Sync complete.", log)
    safe_print("\nSync complete.")

def count_session_fits_files(directory):
    try:
        return sum(
            1 for f in os.listdir(directory)
            if f.endswith('.fits')
        )
    except Exception as e:
        safe_print(f"Could not access {directory}: {e}")
        return 0


def scan_backup_folder(db_name, backup_root, astronomy_dir, dwarf_id, backup_drive_id = None, session_dir_path = None, log=None):
    if not db_name:
        print_log(f"❌ database name can not be empty!",log)
        return 0,0
    conn = connect_db(db_name)
    if not conn:
        print_log(f"❌ {db_name} database couldn't be opened!",log)
        return 0,0

    if astronomy_dir:
        data_root = os.path.join(backup_root, astronomy_dir)
    else:
        data_root = backup_root

    if not data_root or not os.path.exists(data_root):
        if data_root:
            if astronomy_dir:
                print_log(f"❌ {astronomy_dir} folder not found in {backup_root} or not available",log)
            else:
                print_log(f"❌ {backup_root} folder not found or not available",log)
        return 0,0

    # Scan only one session dir
    session_dir_main_dir = None
    session_dir = None
    is_session_dir = None

    if session_dir_path:
        session_dir_main_dir, is_session_dir = determine_session_dir(data_root, session_dir_path)

    if session_dir_main_dir:
        session_dir = os.path.basename(session_dir_path)

    valid_ids = set()
    total_added = 0
    deleted = 0

    skip_dirs = {"Archive", "CALI_FRAME", "DWARF_DARK", "Solving_Failed"}
    for astro_dir in os.listdir(data_root):
        if astro_dir in skip_dirs:
            safe_print(f"Skip: {astro_dir}")
            continue

        astro_path = os.path.join(data_root, astro_dir)
        if not os.path.isdir(astro_path):
            continue

        if session_dir_main_dir and not (session_dir_main_dir == astro_dir):
            continue

        if session_dir_main_dir:
            if is_session_dir:
                print_log(f"🔍 Processing Session Dir: {session_dir}",log)
                safe_print(f"Processing Session Dir: {session_dir}")

        else:
            print_log(f"🔍 Processing Dir:",log)
            print_log(f"🔍 {astro_dir}",log)
            safe_print(f"astro_path Dir: {astro_path}")
            safe_print(f"Processing Dir: {astro_dir}")
    
        found_data = False
        astro_group_id = None
        total_previous = total_added
    
        astro_name = extract_astro_name_from_folder(astro_dir)
        dec_astro = None
        ra_astro = None
        safe_print(f"Processing extract_astro_name_from_folder: {astro_name}")
        find_unknown = False
        if not astro_name:
            check_target_file = astro_path
            safe_print(f"check_target_file Dir: {astro_path}")
            astro_name, dec_astro, ra_astro = extract_target_json(astro_path)
            safe_print(f"Processing extract_target_json: {astro_name}")
        elif astro_name and (astro_name.lower() == UNKNOWN or astro_name.lower() == MOSAIC_UNKNOWN or astro_name.lower() == MANUAL):
            find_unknown = True
            check_target_file = astro_path
            safe_print(f"check_target_file Dir: {astro_path}")
            astro_name_notused, dec_astro, ra_astro = extract_target_json(astro_path)
            # Get Group_id for UNKNOWN, MOSAIC_UNKNOWN or MANUAL
            safe_print(f"Unknown extract Ra: {ra_astro} Dec: {dec_astro}")
            astro_group_id = get_astro_object_groupId(conn, astro_name)
            safe_print(f"astro_group_id (Unknown) {astro_name}")
        if astro_name:
            found_data = True
            safe_print(f"Found data: {astro_name} {find_unknown}")
            if find_unknown:
                astro_object_id, new = insert_astro_object(conn, astro_name, True, dec_astro, ra_astro)
            else:
                astro_object_id, new = insert_astro_object(conn, astro_name)
            if not astro_object_id:
                break
            if new:
                safe_print(f"add astro object : {astro_name}")
                print_log(f"add astro object : {astro_name}",log)
            else:
                safe_print(f"use astro object : {astro_name}")
                print_log(f"use astro object : {astro_name}",log)
            print_log(f"📂 Processing direct Dwarf data:\n {astro_dir}",log)
            new_added, data_ids = process_dwarf_folder(
                conn, backup_root, astro_path,
                astro_object_id, dwarf_id, backup_drive_id, new, astro_group_id
            )
            total_added += new_added
            if data_ids:
                if isinstance(data_ids, (list, tuple, set)):
                    valid_ids.update(data_ids)
                else:
                    valid_ids.add(data_ids)
            if total_added - total_previous == 1:
                print_log(f"📂 Found 1 new Session in {astro_dir}",log)
            elif total_added != total_previous:
                print_log(f"📂 Found {total_added - total_previous} new Sessions in {astro_dir}",log)

        else:
            astro_name = astro_dir
            safe_print(f"astro_name: {astro_name}")
            safe_print(f"astro_path: {astro_path}")
            # Traverse all folders below astro_path
            for root, dirs, files in os.walk(astro_path):
                dec_astro = None
                ra_astro = None
                astro_group_id = None
                safe_print(f"current_dir check: {root},")
                if check_dir_session (root, dirs, files, session_dir_main_dir, session_dir):
                    current_dir = os.path.basename(os.path.normpath(root))
                    safe_print(f"current_dir Dir: {current_dir}")
                    if current_dir == 'Thumbnail':
                        last_dir = os.path.basename(os.path.dirname(root))  # name
                        last_dir_path = os.path.dirname(root)               # full path
                    else:
                        last_dir = current_dir
                        last_dir_path = root
                    
                    safe_print(f"check_target_file Dir: {last_dir}")
                    # Check special STARTRAILS
                    if last_dir.startswith(STARTRAILS_SESSION):
                        print("STARTRAILS detected...")
                        check_target = STARTRAILS
                    else:
                        check_target = extract_astro_name_from_folder(last_dir)
                        if not check_target:
                            safe_print(f"check_target_file Dir: {last_dir_path}")
                            check_target, dec_astro, ra_astro = extract_target_json(last_dir_path)

                    safe_print(f"check_target: {check_target}")
                    if check_target:
                        # case parent directory is a simple dir
                        # so it will be a astro_group except for RESTACKED dir
                        if not found_data:
                            new = False
                            safe_print(f"not found_data")
                            if astro_name == "RESTACKED":
                                if check_target.lower() == UNKNOWN or check_target.lower() == MOSAIC_UNKNOWN or check_target.lower() == MANUAL:
                                    check_target_file = last_dir_path
                                    safe_print(f"check_target_file Dir: {last_dir_path}")
                                    astro_name_notused, dec_astro, ra_astro = extract_target_json(last_dir_path)
                                    safe_print(f"RESTACKED Unknown extract Ra: {ra_astro} Dec: {dec_astro}")
                                    # Get Group_id for UNKNOWN, MOSAIC_UNKNOWN or MANUAL
                                    astro_group_id = get_astro_object_groupId(conn, check_target)
                                    safe_print(f"astro_group_id (Unknown) {check_target}")
                                    astro_object_id, new = insert_astro_object(conn, check_target, True, dec_astro, ra_astro)
                                else:
                                    astro_object_id, new = insert_astro_object(conn, check_target)
                                if not astro_object_id:
                                    break
                                if new:
                                    safe_print(f"add astro object : {check_target}")
                                    print_log(f"add astro object : {check_target}",log)
                                else:
                                    safe_print(f"add astro object : {check_target}")
                                    print_log(f"add astro object : {check_target}",log)
                                #found_data = True
                            else: # use Main AstroDir Name as astro_group
                                safe_print(f"astro_object_id {check_target}")
                                if check_target.lower() == UNKNOWN or check_target.lower() == MOSAIC_UNKNOWN or check_target.lower() == MANUAL:
                                    check_target_file = last_dir_path
                                    safe_print(f"check_target_file Dir: {last_dir_path}")
                                    astro_name_notused, dec_astro, ra_astro = extract_target_json(last_dir_path)
                                    safe_print(f"DIR Unknown extract Ra: {ra_astro} Dec: {dec_astro}")
                                    astro_object_id, new = insert_astro_object(conn, check_target, True, dec_astro, ra_astro)
                                else:
                                    astro_object_id, new = insert_astro_object(conn, check_target)
                                if not astro_object_id:
                                    safe_print(f"not astro_object_id")
                                    break
                                if new:
                                    safe_print(f"add astro object : {astro_name}")
                                    print_log(f"add astro object : {astro_name}",log)
                                else:
                                    safe_print(f"use astro object : {astro_name}")
                                    print_log(f"use astro object : {astro_name}",log)
                                # case parent directory is a simple dir
                                # so it will be a astro_group except for RESTACKED dir
                                # add astro group
                                safe_print(f"astro_group_id {astro_name}")
                                astro_group_id, new_group = insert_astro_group(conn, astro_name)
                                if not astro_group_id:
                                    safe_print(f"not astro_group_id")
                                    break
                                if new_group:
                                    print_log(f"add astro group : {astro_name}",log)
                                else:
                                    print_log(f"use astro group : {astro_name}",log)
                                #found_data = True
                        print_log(f"📂 Processing session folder (deep):\n {os.path.dirname(last_dir_path)}",log)
                        print_log(f"📂 Session: {os.path.basename(last_dir_path)}",log)
                        safe_print(f"Processing session folder (deep): {last_dir_path}")
                        safe_print(f"Using astro_group_id / astro_object_id : {astro_group_id}/{astro_object_id}")
                        new_added, data_ids = process_dwarf_folder(
                            conn, backup_root, last_dir_path,
                            astro_object_id, dwarf_id, backup_drive_id, new, astro_group_id
                        )
                        total_added += new_added
                        safe_print(f"Added : {new_added}")
                        if data_ids:
                            if isinstance(data_ids, (list, tuple, set)):
                                valid_ids.update(data_ids)
                            else:
                                valid_ids.add(data_ids)

            if total_added - total_previous == 1:
                print_log(f"📂 Found 1 new Session in {astro_dir}",log)
            elif total_added != total_previous:
                print_log(f"📂 Found {total_added - total_previous} new Sessions in {astro_dir}",log)
            else:
                print_log(f"📂 No new Session found in {astro_dir}",log)

    if session_dir_main_dir :
        # update scan date if modifications presents
        if not backup_drive_id:
            if deleted or total_added:
                set_dwarf_scan_date(conn, dwarf_id)
        else:
            if deleted or total_added:
                set_backup_scan_date(conn, backup_drive_id)
    else:
        # delete data that are not more present
        if not backup_drive_id:
            deleted = delete_notpresent_dwarf_entries_and_dwarf_data(conn, dwarf_id, valid_ids)
            if deleted == 1:
                print_log(f"📂 Deleted 1 entry in DB not more present",log)
            elif deleted and deleted > 1:
                print_log(f"📂 deleted {deleted} entries in DB not more present",log)
            # update scan date if modifications presents
            if deleted or total_added:
                set_dwarf_scan_date(conn, dwarf_id)
        else:
            deleted = delete_notpresent_backup_entries_and_dwarf_data(conn, backup_drive_id, valid_ids)
            if deleted == 1:
                print_log(f"📂 Deleted 1 entry in DB not more present",log)
            elif deleted and deleted > 1:
                print_log(f"📂 deleted {deleted} entries in DB not more present",log)
            # update scan date if modifications presents
            if deleted or total_added:
                set_backup_scan_date(conn, backup_drive_id)

    # --- Rebuild any orphaned ManualSessionEntry rows ---
    # Must run after BackupEntry rows are up to date and before the
    # connection is closed.  Safe to call on every scan: it no-ops when
    # nothing is orphaned.
    rebuild_result = {"rebuilt": 0, "skipped": 0, "errors": 0}
    if backup_drive_id:
        rebuild_result = rebuild_manual_session_entries(conn)
        # Write shotsInfo.json for any session that doesn't have one yet
        # (covers sessions created before this feature was introduced)
        write_missing_shotsInfo(conn)
        if rebuild_result["rebuilt"] > 0:
            print_log(
                f"🔗 {rebuild_result['rebuilt']} manual session(s) re-linked after scan.",
                log,
            )
        if rebuild_result["skipped"] > 0:
            print_log(
                f"⚠️ {rebuild_result['skipped']} manual session(s) could not be matched "
                f"(drive may be disconnected).",
                log,
            )

    commit_db(conn)
    close_db(conn)
    return total_added, deleted, rebuild_result

def process_dwarf_folder (conn, backup_root, dwarf_path, astro_object_id, dwarf_id, backup_drive_id=None, new_data = False, astro_group_id = None): 
    added = 0
    data_ids = set()
    session_date = extract_session_datetime(dwarf_path)
    if not session_date:
        safe_print("Error : No session_date")
        return added, data_ids

    safe_print(f"process_dwarf_folder - dwarf_path {dwarf_path} ")

    for filename in os.listdir(dwarf_path):
        if not filename.lower().endswith(("stacked.jpg", "stacked.png")):
            continue
        safe_print(f"process_dwarf_folder - filename  {filename}")
        full_file_path = os.path.join(dwarf_path, filename)
        dwarf_data_id, data_id = insert_dwarf_data(conn, backup_root, full_file_path, astro_object_id, new_data)
        session_dt_str = session_date.strftime("%Y-%m-%d %H:%M:%S.%f")
        session_dir = os.path.basename(os.path.normpath(dwarf_path))

        if dwarf_data_id:
            if backup_drive_id:
                # Insert entry in BackupEntry
                new_id = insert_BackupEntry(conn, backup_drive_id, dwarf_id, astro_object_id, dwarf_data_id, session_dt_str, session_dir, astro_group_id)
                added += 1 if new_id != 0 else 0
                safe_print(f"insert_BackupEntry : id : {new_id}")
            else:
                # Insert entry in DwarfEntry
                new_id = insert_DwarfEntry(conn, dwarf_id, astro_object_id, dwarf_data_id, session_dt_str, session_dir, astro_group_id)
                added += 1 if new_id != 0 else 0
        if data_id:
            data_ids.add(data_id)
    return added, data_ids


#########################
# Thumbnail function
#########################

from PIL import Image

def create_thumbnail(input_path: str, output_path: str, size=(356, 200)):
    img = Image.open(input_path)
    if img.mode != "RGB":
        img = img.convert("RGB")

    target_ratio = size[0] / size[1]
    img_ratio = img.width / img.height

    # Crop to match target ratio
    if img_ratio > target_ratio:
        # Image is wider than target: crop width
        new_width = int(img.height * target_ratio)
        left = (img.width - new_width) // 2
        right = left + new_width
        top = 0
        bottom = img.height
    else:
        # Image is taller than target: crop height
        new_height = int(img.width / target_ratio)
        top = (img.height - new_height) // 2
        bottom = top + new_height
        left = 0
        right = img.width

    img_cropped = img.crop((left, top, right, bottom))
    img_resized = img_cropped.resize(size, Image.LANCZOS)
    img_resized.save(output_path, format="JPEG", quality=90)

#########################
# Check Integrity  Functions
#########################

def count_valid_fits_files(directory: str) -> int:
    count = 0

    is_mosaic = "MOSAIC" in directory.upper()

    if is_mosaic:
        # 🔁 recursive scan (subdirectories)
        for dirpath, _, filenames in os.walk(directory):
            for fname in filenames:
                if not fname.lower().endswith(".fits"):
                    continue

                if fname.startswith("stacked-16") or fname.startswith("failed"):
                    continue

                count += 1
    else:
        for fname in os.listdir(directory):
            if not fname.lower().endswith(".fits"):
                continue

            # ❌ exclude unwanted files
            if fname.startswith("stacked-16") or fname.startswith("failed"):
                continue

            count += 1

    return count


def get_shots_stacked(directory: str) -> int | None:

    json_path = os.path.join(directory, "shotsInfo.json")

    if not os.path.isfile(json_path):
        return None

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f).get("shotsStacked")
    except Exception:
        return None


def verify_session(directory: str, session_name, tolerance: int = 0):
    if directory:
        if "RESTACKED" in directory:
            # No Fits for RESTACKED Session
            return None

        shots_stacked = get_shots_stacked(directory)
        fits_count = count_valid_fits_files(directory)

        if shots_stacked is None:
            return {
                "status": "error",
                "path": directory,
                "session": session_name,
                "reason": "missing shotsInfo.json",
                "fits_count": fits_count
            }

        status = "mismatch"
        if fits_count == 0 and shots_stacked !=0:
            status = "no fits available!"
        
        diff = shots_stacked - fits_count

        if diff < 0 or abs(diff) <= tolerance:
            return None  # ✅ OK

        return {
            "status": status,
            "path": directory,
            "session": session_name,
            "shots_stacked": shots_stacked,
            "fits_count": fits_count,
            "missing": diff
        }
    return None
    
def list_error_integrity(conn,  backup_drive_id, backupDrive_location, session_list, log):
    errors = []

    print_log(f" 🔍 Integrity test for  {len(session_list)} sessions", log)

    for session in session_list:
        session_id = session[0]
        session_dir = session[1]
        stacked_fits_path = session[5]
        stacked_path = session[6]
        if stacked_fits_path or stacked_path:
            json_full_path = get_Backup_fullpath(
                conn, 
                backupDrive_location,
                "",
                os.path.dirname(stacked_fits_path or stacked_path)
            )
            #print_log(f"testing: {json_full_path}", log)
            session_name = os.path.basename(os.path.dirname(stacked_fits_path or stacked_path))
            if not stacked_path:
                print_log(f"ℹ️ {session_name} no stacked jpg found", log)
                print_log(f"📂 {json_full_path}", log)
            if not stacked_fits_path and 'MOSAIC' not in session_name:
                print_log(f"ℹ️ {session_name} no stacked fits found", log)
                print_log(f"📂 {json_full_path}", log)

            result = verify_session(json_full_path, session_name)
            if result:
                if result.get("fits_count","") == 0:
                    print_log(f"❌ Integrity error for session: {result.get("session", "")}", log, style = 'text-red')
                else:
                    print_log(f"⚠️ Integrity error for session: {result.get("session", "")}", log, style = 'text-orange')
                print_log(f"📂 {json_full_path}", log)
                if result.get("shots_stacked", False):
                    print_log(f"  Details: {result.get("status","")} {result.get("fits_count","")} fits files found / {result.get("shots_stacked","")} in json info file", log)
                else:
                    print_log(f"  Details: {result.get("status","")}", log) 
                errors.append({
                    **result,
                    "session_id": session_id,
                    "session_dir": session_dir,
                })                

        else : 
            print_log(f"  Ignoring session:{session[1]} no stacked jpg and fits path", log)

    print_log(f"End of Test", log)
    return errors            
    

#########################
# FITS Preview Functions
#########################

def generate_fits_preview_test(fits_path: str) -> str:
    try:
        from astropy.io import fits
        import numpy as np
        import matplotlib.pyplot as plt

        def increase_contrast(image, gain=10):
            return 1 / (1 + np.exp(-gain * (image - 0.5)))

        with fits.open(fits_path) as hdul:
            data = hdul[0].data
            header = hdul[0].header

        if data is None or data.ndim != 3:
            raise ValueError(f"Expected 3D RGB FITS data, got shape {data.shape}")

        image = np.transpose(data, (1, 2, 0)).astype(np.float32)

        bzero = header.get("BZERO", 0)
        bscale = header.get("BSCALE", 1)
        image = image * bscale + bzero

        # Normalization
        vmin = np.percentile(image, 0.1)
        vmax = np.percentile(image, 99.9)
        image = np.clip((image - vmin) / (vmax - vmin), 0, 1)

        # Stretch
        stretch_factor = 25
        image = np.arcsinh(image * stretch_factor)
        image /= np.max(image)

        # Gamma
        gamma = 0.7 #0.8
        image = np.power(image, gamma)

        # Color balance
        r, g, b = image[..., 0], image[..., 1], image[..., 2]
        green_mean = g.mean()

        r = np.clip(r * 1.005, 0, 1)  # reduced red boost #1.05
        g = np.clip(g - 0.45 * green_mean, 0, 1) #0.35
        b = np.clip(b - 0.05 * green_mean, 0, 1) #0.15

        image = np.stack([r, g, b], axis=-1)

        # Contrast boost
        image = increase_contrast(image, gain=6)

        preview_path = fits_path.replace(".fits", "_preview.png")
        plt.imsave(preview_path, image, format='png')

        return preview_path

    except Exception as e:
        safe_print(f"Error generating preview: {e}")
        return "image/image-error.png"

def siril_log_stretch(image, black_point=None, white_point=None, scale=1000.0):
    """
    Logarithmic stretch similar to Siril.

    Parameters
    ----------
    image : np.ndarray
        Input image in float32, assumed normalized in [0,1].
    black_point : float
        Minimum value mapped to 0. If None, use min(image).
    white_point : float
        Maximum value mapped to 1. If None, use max(image).
    scale : float
        Controls the strength of the stretch.

    Returns
    -------
    np.ndarray
        Logarithmically stretched image in [0,1].
    """
    img = np.clip(image, 0, 1)

    if black_point is None:
        black_point = np.min(img)
    if white_point is None:
        white_point = np.max(img)

    # Normalize to [0,1] based on black/white points
    norm = (img - black_point) / (white_point - black_point + 1e-8)
    norm = np.clip(norm, 0, 1)

    # Apply logarithmic stretch
    stretched = np.log1p(scale * norm) / np.log1p(scale)

    return stretched.astype(np.float32)

def arcsinh_stretch(image, factor=10):
    stretched = np.arcsinh(factor * image) / np.arcsinh(factor)
    return stretched.astype(np.float32)

def background_neutralization(image):
    r, g, b = image[...,0], image[...,1], image[...,2]
    r_med, g_med, b_med = np.median(r), np.median(g), np.median(b)

    avg = (r_med + g_med + b_med) / 3.0

    r = np.clip(r * (avg / (r_med + 1e-6)), 0, 1)
    g = np.clip(g * (avg / (g_med + 1e-6)), 0, 1)
    b = np.clip(b * (avg / (b_med + 1e-6)), 0, 1)

    return np.stack([r, g, b], axis=-1)

def apply_black_point(image, black=0.05, white=0.99):
    """
    Adjust black/white levels after stretching.
    """
    img = np.clip((image - black) / (white - black), 0, 1)
    return img

def boost_saturation(image, factor=1.3):
    hsv = cv2.cvtColor((image*255).astype(np.uint8), cv2.COLOR_RGB2HSV).astype(np.float32)
    hsv[...,1] *= factor
    hsv[...,1] = np.clip(hsv[...,1], 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB).astype(np.float32) / 255.0

def simple_color_balance(image):
    r, g, b = image[..., 0], image[..., 1], image[..., 2]
    r_mean, g_mean, b_mean = r.mean(), g.mean(), b.mean()

    avg = (r_mean + g_mean + b_mean) / 3.0

    r = np.clip(r * (avg / (r_mean + 1e-6)), 0, 1)
    g = np.clip(g * (avg / (g_mean + 1e-6)), 0, 1)
    b = np.clip(b * (avg / (b_mean + 1e-6)), 0, 1)

    return np.stack([r, g, b], axis=-1)

def white_balance(image, r=1.3, g=0.85, b=0.9):
    image = image.copy()
    image[..., 0] = np.clip(image[..., 0] * r, 0, 1)  # Red up
    image[..., 1] = np.clip(image[..., 1] * g, 0, 1)  # Green down
    image[..., 2] = np.clip(image[..., 2] * b, 0, 1)  # Blue slightly down
    return image

def stretch_with_highlight_protection(image, shadow_scale=5000.0, highlight_compress=0.7):
    # 1. Clip top 0.1% of pixels before stretching (remove hot pixels / star cores blowing out)
    p_high = np.percentile(image, 99.9)
    image = np.clip(image / p_high, 0, 1)

    # 2. Log stretch for faint detail
    image = siril_log_stretch(image, scale=shadow_scale)

    # 3. Soft highlight compression — pulls down only the bright end
    #    Uses a tone curve: bright pixels are compressed, dark ones untouched
    image = image / (image + highlight_compress * (1 - image))  # Reinhard-style

    return image

def stretch_with_highlight_protection(image, shadow_scale=5000.0, highlight_compress=0.7):
    p_high = np.percentile(image, 99.9)
    image = np.clip(image / p_high, 0, 1)
    image = siril_log_stretch(image, scale=shadow_scale)
    image = image / (image + highlight_compress * (1 - image))
    return image

def subtract_background(image, percentile=30):
    """Per-channel background subtraction."""
    for c in range(image.shape[2]):
        bg = np.percentile(image[..., c], percentile)
        image[..., c] = np.clip(image[..., c] - bg, 0, 1)
    return image

def renormalize(image):
    for c in range(image.shape[2]):
        ch = image[..., c]
        ch_min, ch_max = ch.min(), ch.max()
        if ch_max > ch_min:
            image[..., c] = (ch - ch_min) / (ch_max - ch_min)
    return image

def generate_fits_preview(fits_path: str) -> str:
    try:
        from astropy.io import fits
        import numpy as np
        import matplotlib.pyplot as plt
        safe_print(cv2.__version__)
        def increase_contrast(image, gain=10):
            return 1 / (1 + np.exp(-gain * (image - 0.5)))

        with fits.open(fits_path) as hdul:
            data = hdul[0].data
            header = hdul[0].header

        if data is None:
            raise ValueError("FITS file has no data")

        if data.ndim == 3:
            # If the image is already 3D (RGB), ensure it's in float32 (0-1)
            image_rgb = np.transpose(data, (1, 2, 0)).astype(np.float32)
            image_rgb = np.clip(image_rgb / np.max(image_rgb), 0, 1)
            safe_print(f"Using 3D RGB image: {image_rgb.shape}")

        elif data.ndim == 2:
            # If it's 2D (Bayer pattern), apply demosaicing
            safe_print("Detected 2D Bayer image, applying demosaicing...")

            # Convert to float32 and normalize (0-1)
            data = data.astype(np.float32)
            data -= np.min(data)
            data /= np.max(data)

            # Convert to uint8 (0-255) for OpenCV
            data_8bit = (data * 255).astype(np.uint8)
            image_rgb = cv2.demosaicing(data_8bit, cv2.COLOR_BayerRG2RGB)
            safe_print(f"Demosaiced image shape: {image_rgb.shape}")

            # Convert to float32 (0-1) for further processing
            image_rgb = image_rgb.astype(np.float32) / 255.0

        else:
            raise ValueError(f"Unsupported FITS data shape: {data.shape}")

        # Ensure image is in 0-1 range
        image = np.clip(image_rgb, 0, 1)

        image = subtract_background(image, percentile=30)  # tune 20-35
        image = renormalize(image)

        # --- 2. Stretch with highlight protection ---
        #image = stretch_with_highlight_protection(image, shadow_scale=5000.0, highlight_compress=0.7)
        #image = apply_stretch(image)
        # logarithm stretch
        #image = stretch_with_highlight_protection(image, shadow_scale=5000.0, highlight_compress=0.7)
        image = siril_log_stretch(image, scale=2800.0)
        #image = siril_log_stretch(image, scale=500.0)
        # Gamma to bring down blown-out midtones
        #image = np.power(np.clip(image, 0, 1), 1.9) #1.8
        # 3. Reinhard highlight compression — tame bright areas without gamma fighting stretch
        image = image / (image + 0.6 * (1 - image))
        # 4. Black point — push background back to true black
        image = apply_black_point(image, black=0.05, white=0.95)
        #image = arcsinh_stretch(image, factor=15)   # or sigmoid if you prefer
        image = white_balance(image, r=0.80, g=0.93, b=0.82)
        #image = simple_color_balance(image)
        #image = apply_black_point(image, black=0.08, white=0.98)
        image = boost_saturation(image)

        # Apply contrast boost (optional)
        #image = increase_contrast(image)

        # Color balance
        #r, g, b = image[..., 0], image[..., 1], image[..., 2]
        #green_mean = g.mean()

        # Remove green bias proportionally
        #g = np.clip(g - 0.45 * green_mean, 0, 1)

        # Recombine channels
        #image = np.stack([r, g, b], axis=-1)

        # Ensure values are in range
        image = np.clip(image, 0, 1)

        # Convert back to uint8 for final output
        final_image = (image * 255).astype(np.uint8)
        safe_print(f"Processed image shape: {final_image.shape}")

        preview_path = fits_path.replace(".fits", "_preview.png")
        plt.imsave(preview_path, final_image, format='png')

        return preview_path

    except Exception as e:
        safe_print(f"Error generating preview: {e}")
        return "image/image-error.png"