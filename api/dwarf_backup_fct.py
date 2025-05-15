import os
import sys
import sqlite3
import json
import hashlib
import argparse
from pathlib import Path
from datetime import datetime
import re
import platform
import subprocess
import glob
from astropy.io import fits
import matplotlib.pyplot as plt
import numpy as np
from auto_stretch import apply_stretch
import cv2
from nicegui import ui, run

from api.dwarf_backup_db import connect_db, close_db, commit_db
from api.dwarf_backup_db_api import get_backupDrive_id_from_location, insert_astro_object, insert_DwarfData, insert_BackupEntry, insert_DwarfEntry
from api.dwarf_backup_db_api import is_dwarf_exists, get_dwarf_Names, add_dwarf_detail, delete_notpresent_backup_entries_and_dwarf_data, delete_notpresent_dwarf_entries_and_dwarf_data, set_dwarf_scan_date, set_backup_scan_date

import ftplib
from ftplib import FTP

def parse_shots_info(json_path, ftp=None):
    try:
        if json_path.startswith("ftp://"):
            # Handle FTP case
            if not ftp:
                print(f"❌ FTP connection is required for {json_path}.")
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

        return {
            "dec": str(raw.get("DEC")),
            "ra": str(raw.get("RA")),
            "target": raw.get("target"),
            "binning": raw.get("binning"),
            "format": raw.get("format"),
            "exp_time": str(raw.get("exp")) if raw.get('exp') is not None else None,
            "gain": raw.get("gain"),
            "shotsToTake": raw.get("shotsToTake"),
            "shotsTaken": raw.get("shotsTaken"),
            "shotsStacked": raw.get("shotsStacked"),
            "ircut": raw.get("ir"),
            "maxTemp": raw.get("maxTemp"),
            "minTemp": raw.get("minTemp"),
        }

    except Exception as e:
        print(f"Error reading {json_path}: {e}")
        return {}

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
        print(f"❌ Path does not exist: {path}")

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
        print(f"Error parsing datetime from filename: {e}")
    
    return None

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
        long_path = f"\\\\?\\{os.path.abspath(filepath)}"
        with open(long_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)

    return hash_md5.hexdigest()

def get_or_create_dwarf_id(conn, dwarf_id=None, batch_mode=False, default_name="Default Dwarf", default_description="Auto-created"):

    if dwarf_id is not None:
        # Vérifie si l'ID existe
        if is_dwarf_exists(conn, dwarf_id):
            return dwarf_id
        elif batch_mode:
            # Crée automatiquement si inexistant
            dwarf_id = add_dwarf_detail(conn, default_name, default_description, "", "2", "", None)
            return dwarf_id
        else:
            raise ValueError(f"Dwarf ID {dwarf_id} non trouvé.")

    # Aucun dwarf_id fourni
    dwarfs = get_dwarf_Names(conn)

    if dwarfs:
        if batch_mode:
            # Retourne le premier Dwarf disponible
            return dwarfs[0][0]
        else:
            print("Dwarfs existants :")
            for d_id, d_name in dwarfs:
                print(f"  [{d_id}] {d_name}")
            try:
                dwarf_id = int(input("Enter the ID of the Dwarf to associate:"))
            except ValueError:
                raise ValueError("Invalid ID.")
            return dwarf_id
    else:
        if batch_mode:
            # Crée un Dwarf par défaut si aucun n'existe
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
            return found_id, dwarf_id  # dwarf_id fourni remplace potentiellement
    else:
        try:
            dwarf_id = get_or_create_dwarf_id(conn)
        except ValueError as e:
            print(f"Erreur : {e}")
            print("No action taken. Please create a Dwarf first.")
            sys.exit(1)  

        name = os.path.basename(location.rstrip("\\/"))
        description = f"Auto-added for path {location}"
        astroDir = "DATA_OBJECTS"

        backupDrive_id = add_backupDrive_detail(conn, name, description, location, astroDir, dwarf_id)
        return backupDrive_id, dwarf_id

def insert_dwarf_data(conn, root, filepath):
    relative_path = os.path.relpath(filepath, root)
    print(f"insert_dwarf_data : path : {filepath}")
    print(f"insert_dwarf_data : rel-path : {relative_path}")
    filetype = Path(filepath).suffix[1:].lower()
    size = os.path.getsize(filepath)
    mtime = int(os.path.getmtime(filepath))

    file_path = Path(filepath)
    parent_dir = file_path.parent

    base_dir = os.path.dirname(filepath)
    json_path = os.path.join(base_dir, 'shotsInfo.json')
    thumbnail_path = os.path.join(base_dir, 'stacked_thumbnail.jpg')

    # Chercher un fichier stacked*.fits dans le même dossier
    stacked_path = None
    stacked_md5 = None
    for f in parent_dir.glob("stacked*.fits"):
        stacked_path = f.relative_to(root).as_posix()
        print(f"test_dwarf_data : stacked_path : {stacked_path}")
        stacked_md5 = compute_md5(f)
        break  # On prend le premier trouvé

    meta = parse_shots_info(json_path) if os.path.exists(json_path) else {}
    thumbnail = os.path.relpath(thumbnail_path, root) if os.path.exists(thumbnail_path) else None

    new_value , data_id = insert_DwarfData (conn, relative_path, mtime, thumbnail, size,
        meta.get('dec'), meta.get('ra'), meta.get('target'),
        meta.get('binning'), meta.get('format'), meta.get('exp_time'),
        meta.get('gain'), meta.get('shotsToTake'), meta.get('shotsTaken'),
        meta.get('shotsStacked'), meta.get('ircut'), meta.get('maxTemp'), meta.get('minTemp'),
        "0","0", 4, stacked_path, stacked_md5)

    return new_value, data_id

def extract_astro_name_from_folder(folder_name: str) -> str | None:
    """
    Extract the name of the astronomical object from a folder:
    - DWARF_RAW_TELE_<ASTRO>_EXP_... (Dwarf3)
    - DWARF_RAW_<ASTRO>_EXP_...      (Dwarf2)
    """
    patterns = [
        r"DWARF_RAW_TELE_(.+?)_EXP_",
        r"DWARF_RAW_WIDE_(.+?)_EXP_",
        r"RESTACKED_DWARF_RAW_TELE_(.+?)_",
        r"RESTACKED_DWARF_RAW_WIDE_(.+?)_",
        r"DWARF_RAW_(.+?)_EXP_"
    ]
    for pattern in patterns:
        m = re.match(pattern, folder_name)
        if m:
            return m.group(1).strip()

    return None

# Function to parse shotsInfo.json
def extract_target_json(astro_path, ftp_conn=None):
    json_path = os.path.join(astro_path, 'shotsInfo.json')

    if ftp_conn:
        try:
            with ftp_conn.open(json_path, 'r') as file:
                meta = json.load(file)
        except:
            meta = {}
    else:
        if os.path.exists(json_path):
            with open(json_path, 'r') as file:
                meta = json.load(file)
        else:
            meta = {}

    return meta.get('target') if meta else None

def check_ftp_connection(ip_address):
    """Check FTP connection and determine if Dwarf2 or Dwarf3 is connected."""
    if not ip_address:
        return "❌ Please enter an IP address."

    try:
        with ftplib.FTP(ip_address) as ftp:
            ftp.login()  # Anonymous login
            # Check for Dwarf2 or Dwarf3 directory
            dwarf2_path = "/DWARF_II/Astronomy"
            dwarf3_path = "/Astronomy"

            if dwarf2_path in ftp.nlst("/DWARF_II"):
                return "✅ Connected to Dwarf2 FTP"
            elif dwarf3_path in ftp.nlst("/"):
                return "✅ Connected to Dwarf3 FTP"
            else:
                return "❌ Connected to FTP (not Dwarf)."

    except ftplib.all_errors as e:
        return f"❌ FTP Error: not connected"

# Function to connect to Dwarf via FTP
def connect_to_dwarf(ip_address, status_label):
    status_message = check_ftp_connection(ip_address)
    status_label.text = status_message

def show_date_session(date_db):
    dt = datetime.strptime(date_db, "%Y-%m-%d %H:%M:%S.%f")
    date_session = dt.strftime("%B %d, %Y at %I:%M:%S %p")
    return date_session

def print_log(message, log):
    if log:
        log.push(message)
    else:
        print(message)

def determine_session_dir(data_root, session_dir_path):
    # session_dir_path must be inside data_root"
    if not session_dir_path.startswith(data_root):
        return None, None

    relative_path = os.path.relpath(session_dir_path, data_root)
    session_dir_main_dir = relative_path.split(os.sep)[0]

    session_dir = os.path.basename(session_dir_path)
    is_session_dir = session_dir_main_dir == session_dir

    return session_dir_main_dir, is_session_dir

def check_dir_session (root, dirs, files, session_dir_main_dir, session_dir):
    if session_dir_main_dir:
        if session_dir_main_dir and session_dir == os.path.basename(os.path.normpath(root)):
            return True
        else:
            return False

    elif not dirs and files:
        return True
    else:
        return False

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
    if not os.path.exists(data_root):
        print_log(f"❌ {astronomy_dir} folder not found in {backup_root}",log)
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

    for astro_dir in os.listdir(data_root):
        astro_path = os.path.join(data_root, astro_dir)
        if not os.path.isdir(astro_path):
            continue

        if session_dir_main_dir and not (session_dir_main_dir == astro_dir):
            continue

        if session_dir_main_dir:
            if is_session_dir:
                print_log(f"🔍 Processing Session Dir: {session_dir}",log)
                print(f"🔍 Processing Session Dir: {session_dir}",log)

        else:
            print_log(f"🔍 Processing Dir:",log)
            print_log(f"🔍 {astro_dir}",log)
            print(f"astro_path Dir: {astro_path}")
            print(f"Processing Dir: {astro_dir}")
    
        found_data = False
        total_previous = total_added
    
        astro_name = extract_astro_name_from_folder(astro_dir)
        print(f"Processing extract_astro_name_from_folder: {astro_name}")
        if not astro_name:
            check_target_file = astro_path
            print(f"check_target_file Dir: {astro_path}")
            astro_name = extract_target_json(astro_path)
            print(f"Processing extract_target_json: {astro_name}")
        if astro_name:
            found_data = True
            astro_object_id, new = insert_astro_object(conn, astro_name)
            if not astro_object_id:
                break
            if new:
                print_log(f"add astro object : {astro_name}",log)
            else:
                print_log(f"use astro object : {astro_name}",log)
            print_log(f"📂 Processing direct Dwarf data:\n {astro_dir}",log)
            new_added, data_ids = process_dwarf_folder(
                conn, backup_root, astro_path,
                astro_object_id, dwarf_id, backup_drive_id
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
            # Traverse all folders below astro_path
            for root, dirs, files in os.walk(astro_path):
                if check_dir_session (root, dirs, files, session_dir_main_dir, session_dir):
                    current_dir = os.path.basename(os.path.normpath(root))
                    print(f"current_dir Dir: {current_dir}")
                    if current_dir == 'Thumbnail':
                        last_dir = os.path.basename(os.path.dirname(root))  # Use parent dir
                        last_dir = os.path.basename(os.path.dirname(root))  # name
                        last_dir_path = os.path.dirname(root)               # full path
                    else:
                        last_dir = current_dir
                        last_dir_path = root
                    print(f"check_target_file Dir: {last_dir}")
                    check_target = extract_astro_name_from_folder(last_dir)
                    if not check_target:
                        print(f"check_target_file Dir: {last_dir_path}")
                        check_target = extract_target_json(last_dir_path)

                    print(f"check_target: {check_target}")
                    if check_target:
                        if not found_data:
                            print(f"not found_data")
                            if astro_name == "RESTACKED":
                                astro_object_id, new = insert_astro_object(conn, check_target)
                                if not astro_object_id:
                                    break
                                if new:
                                    print_log(f"add astro object : {check_target}",log)
                                else:
                                    print_log(f"use astro object : {check_target}",log)
                                found_data = True
                            else: # use Main AstroDir Name
                                print(f"astro_object_id {astro_name}")
                                astro_object_id, new = insert_astro_object(conn, astro_name)
                                if not astro_object_id:
                                    print(f"not astro_object_id")
                                    break
                                if new:
                                    print_log(f"add astro object : {astro_name}",log)
                                else:
                                    print_log(f"use astro object : {astro_name}",log)
                                found_data = True
                        print_log(f"📂 Processing session folder (deep):\n {os.path.dirname(last_dir_path)}",log)
                        print_log(f"📂 Session: {os.path.basename(last_dir_path)}",log)
                        print(f"Processing session folder (deep): {last_dir_path}")
                        new_added, data_ids = process_dwarf_folder(
                            conn, backup_root, last_dir_path,
                            astro_object_id, dwarf_id, backup_drive_id
                        )
                        total_added += new_added
                        print(f"Added : {new_added}")
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

        if not found_data:
            print_log(f"⚠️ Ignored unrecognized folder: {astro_dir}",log)

    if session_dir_main_dir :
        # update scan date if modifications presents
        if deleted or total_added:
            set_dwarf_scan_date(conn, dwarf_id)

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

    commit_db(conn)
    close_db(conn)
    return total_added, deleted

def scan_backup_folder_ftp(db_name, backup_root, astronomy_dir, dwarf_id, backup_drive_id = None, log=None):
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
    if not os.path.exists(data_root):
        print_log(f"❌ {astronomy_dir} folder not found in {backup_root}",log)
        return 0,0

    valid_ids = set()
    total_added = 0
    deleted = 0

    for astro_dir in os.listdir(data_root):
        astro_path = os.path.join(data_root, astro_dir)
        if not os.path.isdir(astro_path):
            continue

        #subdirs = [
        #    d for d in os.listdir(astro_path)
        #    if os.path.isdir(os.path.join(astro_path, d)) and d != 'Thumbnail'
        #]
        print_log(f"🔍 Processing Dir: {astro_dir}",log)
        print(f"astro_path Dir: {astro_path}")
        print(f"Processing Dir: {astro_dir}")

        found_data = False
        total_previous = total_added
        astro_name = extract_astro_name_from_folder(astro_dir)
        print(f"Processing extract_astro_name_from_folder: {astro_name}")
        if not astro_name:
            check_target_file = astro_path
            print(f"check_target_file Dir: {astro_path}")
            astro_name = extract_target_json(astro_path)
            print(f"Processing extract_target_json: {astro_name}")
        if astro_name:
            found_data = True
            astro_object_id, new = insert_astro_object(conn, astro_name)
            if not astro_object_id:
                break
            if new:
                print_log(f"add astro object : {astro_name}",log)
            else:
                print_log(f"use astro object : {astro_name}",log)
            print_log(f"📂 Processing direct Dwarf data: {astro_dir}",log)
            new_added, data_ids = process_dwarf_folder(
                conn, backup_root, astro_path,
                astro_object_id, dwarf_id, backup_drive_id
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
            # Traverse all folders below astro_path
            for root, dirs, files in os.walk(astro_path):
                if not dirs and files:
                    current_dir = os.path.basename(os.path.normpath(root))
                    print(f"current_dir Dir: {current_dir}")
                    if current_dir == 'Thumbnail':
                        last_dir = os.path.basename(os.path.dirname(root))  # name
                        last_dir_path = os.path.dirname(root)               # full path
                    else:
                        last_dir = current_dir
                        last_dir_path = root
                    print(f"check_target_file Dir: {last_dir}")
                    check_target = extract_astro_name_from_folder(last_dir)
                    if not check_target:
                        print(f"check_target_file Dir: {last_dir_path}")
                        check_target = extract_target_json(last_dir_path)

                    print(f"check_target: {check_target}")
                    if check_target:
                        if not found_data:
                            print(f"not found_data")
                            if astro_name == "RESTACKED":
                                astro_object_id, new = insert_astro_object(conn, check_target)
                                if not astro_object_id:
                                    break
                                if new:
                                    print_log(f"add astro object : {check_target}",log)
                                else:
                                    print_log(f"use astro object : {check_target}",log)
                                found_data = True
                            else: # use Main AstroDir Name
                                print(f"astro_object_id {astro_name}")
                                astro_object_id, new = insert_astro_object(conn, astro_name)
                                if not astro_object_id:
                                    print(f"not astro_object_id")
                                    break
                                if new:
                                    print_log(f"add astro object : {astro_name}",log)
                                else:
                                    print_log(f"use astro object : {astro_name}",log)
                                found_data = True
                        print_log(f"📂 Processing session folder (deep): {last_dir_path}",log)
                        print(f"Processing session folder (deep): {last_dir_path}")
                        new_added, data_ids = process_dwarf_folder(
                            conn, backup_root, last_dir_path,
                            astro_object_id, dwarf_id, backup_drive_id
                        )
                        total_added += new_added
                        print(f"Added : {new_added}")
                        if data_ids:
                            if isinstance(data_ids, (list, tuple, set)):
                                valid_ids.update(data_ids)
                            else:
                                valid_ids.add(data_ids)

            if total_added - total_previous == 1:
                print_log(f"📂 Found 1 new Session in {astro_dir}",log)
            elif total_added != total_previous:
                print_log(f"📂 Found {total_added - total_previous} new Sessions in {astro_dir}",log)

        if not found_data:
            print_log(f"⚠️ Ignored unrecognized folder: {astro_dir}",log)

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

    commit_db(conn)
    close_db(conn)
    return total_added, deleted

def scan_sub_folder(conn, backup_root, astro_path, astro_dir, total_added, valid_ids, dwarf_id, backup_drive_id = None, log=None):

    if not conn:
        print_log(f"❌ database couldn't be opened!",log)
        return 0,0

    found_data = False
    total_previous = total_added
    astro_name = extract_astro_name_from_folder(astro_dir)
    if not astro_name:
        check_target_file = os.path.join(astro_path, astro_dir)
        astro_name = extract_target_json(check_target_file)
    if astro_name:
        found_data = True
        astro_object_id, new = insert_astro_object(conn, astro_name)
        if not astro_object_id:
            return 0, 0
        if new:
            print_log(f"add astro object : {astro_name}",log)
        else:
            print_log(f"use astro object : {astro_name}",log)
        print_log(f"📂 Processing direct Dwarf data: {astro_dir}",log)
        new_added, data_ids = process_dwarf_folder(
            conn, backup_root, astro_path,
            astro_object_id, dwarf_id, backup_drive_id
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
        # Traverse all folders below astro_path
        for root, dirs, files in os.walk(astro_path):
            if not dirs and files:
                current_dir = os.path.basename(os.path.normpath(root))
                if current_dir == 'Thumbnail':
                    last_dir = os.path.basename(os.path.dirname(root))  # Use parent dir
                else:
                    last_dir = current_dir
                check_target = extract_astro_name_from_folder(last_dir)
                if not check_target:
                    check_target = extract_target_json(root)

                if check_target:
                    if not found_data:
                        if astro_name == "RESTACKED":
                            astro_object_id, new = insert_astro_object(conn, check_target)
                            if not astro_object_id:
                                return 0, 0
                            if new:
                                print_log(f"add astro object : {check_target}",log)
                            else:
                                print_log(f"use astro object : {check_target}",log)
                            found_data = True
                        else: # use Main AstroDir Name
                            astro_object_id, new = insert_astro_object(conn, astro_name)
                            if not astro_object_id:
                                break
                            if new:
                                print_log(f"add astro object : {check_target}",log)
                            else:
                                print_log(f"use astro object : {check_target}",log)
                            found_data = True
                    print_log(f"📂 Processing session folder (deep): {root}",log)
                    new_added, data_ids = process_dwarf_folder(
                        conn, backup_root, root,
                        astro_object_id, dwarf_id, backup_drive_id
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

    if not found_data:
        print_log(f"⚠️ Ignored unrecognized folder: {astro_dir}",log)

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

    commit_db(conn)
    close_db(conn)
    return total_added, deleted

def process_dwarf_folder (conn, backup_root, dwarf_path, astro_object_id, dwarf_id, backup_drive_id=None): 
    added = 0
    data_ids = set()
    session_date = extract_session_datetime(dwarf_path)
    if not session_date:
        print("Error : No session_date")
        return added, data_ids

    print(f"process_dwarf_folder - dwarf_path {dwarf_path} ")

    for filename in os.listdir(dwarf_path):
        if not filename.lower().endswith(("stacked.jpg", "stacked.png")):
            continue
        print(f"process_dwarf_folder - filename  {filename}")
        full_file_path = os.path.join(dwarf_path, filename)
        dwarf_data_id, data_id = insert_dwarf_data(conn, backup_root, full_file_path)
        session_dt_str = session_date.strftime("%Y-%m-%d %H:%M:%S.%f")
        session_dir = os.path.basename(os.path.normpath(dwarf_path))

        if dwarf_data_id:
            if backup_drive_id:
                # Insert entry in BackupEntry
                new_id = insert_BackupEntry(conn, backup_drive_id, dwarf_id, astro_object_id, dwarf_data_id, session_dt_str, session_dir)
                added += 1 if new_id != 0 else 0
                print(f"insert_BackupEntry : id : {new_id}")
            else:
                # Insert entry in DwarfEntry
                new_id = insert_DwarfEntry(conn, dwarf_id, astro_object_id, dwarf_data_id, session_dt_str, session_dir)
                added += 1 if new_id != 0 else 0
        if data_id:
            data_ids.add(data_id)
    return added, data_ids

def get_Backup_fullpath (location, subdir, filename):
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

    return full_path

def get_directory_size(directory: str) -> str:
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

def get_extension(file_path):
    return os.path.splitext(file_path)[1].lower().lstrip('.')

def check_files(full_path: str) -> dict:
    # Get directory from full path
    directory = os.path.dirname(full_path)

    # Look for matching files
    jpg_match = glob.glob(os.path.join(directory, 'stacked.jpg'))
    png_match = glob.glob(os.path.join(directory, 'stacked*.png'))
    tiff_match = glob.glob(os.path.join(directory, 'stacked*.tiff'))
    fits_match = glob.glob(os.path.join(directory, 'stacked*.fits'))

    if tiff_match:
        return {
            'jpg': jpg_match[0] if jpg_match else None,
            'png': png_match[0] if png_match else None,
            'tiff': tiff_match[0] if tiff_match else None,
        }
    else :
        return {
            'jpg': jpg_match[0] if jpg_match else None,
            'png': png_match[0] if png_match else None,
            'fits': fits_match[0] if fits_match else None
        }

def get_directory_size(directory_path: str) -> int:
    total_size = 0

    for dirpath, dirnames, filenames in os.walk(directory_path):
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            if os.path.isfile(file_path):
                total_size += os.path.getsize(file_path)

    return total_size

def count_fits_files(directory):
    return sum(
        1 for f in os.listdir(directory)
        if f.endswith('.fits') and not (f.startswith('stacked-') or f.startswith('failed_'))
    )

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

def generate_fits_preview1(fits_path: str) -> str:
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
        print(f"Error generating preview: {e}")
        return "image/image-error.png"


def generate_fits_preview(fits_path: str) -> str:
    try:
        from astropy.io import fits
        import numpy as np
        import matplotlib.pyplot as plt
        print(cv2.__version__)
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
            print(f"Using 3D RGB image: {image_rgb.shape}")

        elif data.ndim == 2:
            # If it's 2D (Bayer pattern), apply demosaicing
            print("Detected 2D Bayer image, applying demosaicing...")

            # Convert to float32 and normalize (0-1)
            data = data.astype(np.float32)
            data -= np.min(data)
            data /= np.max(data)

            # Convert to uint8 (0-255) for OpenCV
            data_8bit = (data * 255).astype(np.uint8)
            image_rgb = cv2.demosaicing(data_8bit, cv2.COLOR_BayerRG2RGB)
            print(f"Demosaiced image shape: {image_rgb.shape}")

            # Convert to float32 (0-1) for further processing
            image_rgb = image_rgb.astype(np.float32) / 255.0

        else:
            raise ValueError(f"Unsupported FITS data shape: {data.shape}")

        # Ensure image is in 0-1 range
        image = np.clip(image_rgb, 0, 1)

        image = apply_stretch(image)

        # Apply contrast boost (optional)
        image = increase_contrast(image)

        # Color balance
        r, g, b = image[..., 0], image[..., 1], image[..., 2]
        green_mean = g.mean()

        # Remove green bias proportionally
        g = np.clip(g - 0.45 * green_mean, 0, 1)

        # Recombine channels
        image = np.stack([r, g, b], axis=-1)
        image = np.clip(image, 0, 1)  # Ensure values are in range

        # Convert back to uint8 for final output
        final_image = (image * 255).astype(np.uint8)
        print("Processed image shape:", final_image.shape)

        preview_path = fits_path.replace(".fits", "_preview.png")
        plt.imsave(preview_path, final_image, format='png')

        return preview_path

    except Exception as e:
        print(f"Error generating preview: {e}")
        return "image/image-error.png"
