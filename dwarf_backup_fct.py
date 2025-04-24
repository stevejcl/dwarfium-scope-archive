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

from dwarf_backup_db_api import get_backupDrive_id_from_location, insert_astro_object, insert_DwarfData, insert_BackupEntry, insert_DwarfEntry
from dwarf_backup_db_api import is_dwarf_exists, get_dwarf_Names, add_dwarf_detail

def parse_shots_info(json_path):
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
            return {
                "dec": str(raw.get("DEC")),
                "ra": str(raw.get("RA")),
                "target": raw.get("target"),
                "binning": raw.get("binning"),
                "format": raw.get("format"),
                "exp_time": str(raw.get("exp")),
                "gain": raw.get("gain"),
                "shotsToTake": raw.get("shotsToTake"),
                "shotsTaken": raw.get("shotsTaken"),
                "shotsStacked": raw.get("shotsStacked"),
                "ircut": raw.get("ir")
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
            dwarf_id = add_dwarf_detail(conn, default_name, default_description, "", "2")
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
            dwarf_id = add_dwarf_detail(conn, default_name, default_description, "", "2")
            return dwarf_id
        else:
            create = input("No Dwarf. Do you want to create one? (y/n):").strip().lower()
            if create == 'o':
                name = input("Name of the new Dwarf:").strip()
                desc = input("Description: ").strip()
                dwarf_id = add_dwarf_detail(conn, name, desc, "", "2")
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
        stacked_md5 = compute_md5(f)
        break  # On prend le premier trouvé

    meta = parse_shots_info(json_path) if os.path.exists(json_path) else {}
    thumbnail = os.path.relpath(thumbnail_path, root) if os.path.exists(thumbnail_path) else None

    id_value = insert_DwarfData (conn, relative_path, mtime, thumbnail, size,
        meta.get('dec'), meta.get('ra'), meta.get('target'),
        meta.get('binning'), meta.get('format'), meta.get('exp_time'),
        meta.get('gain'), meta.get('shotsToTake'), meta.get('shotsTaken'),
        meta.get('shotsStacked'), meta.get('ircut'), "0",
        "0", 4, stacked_path, stacked_md5)

    return id_value

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

def extract_target_json(astro_path):
    json_path = os.path.join(astro_path, 'shotsInfo.json')
    print(f"json_path: {json_path}")
    meta = parse_shots_info(json_path) if os.path.exists(json_path) else {}
    print(f"target: {meta.get('target')}")
 
    if meta and meta.get('target'):
        return meta.get('target')  
    else:
       return None

def scan_backup_folder(conn, backup_root, astronomy_dir, dwarf_id, backup_drive_id = None):
    if astronomy_dir:
        data_root = os.path.join(backup_root, astronomy_dir)
    else:
        data_root = backup_root
    if not os.path.exists(data_root):
        print(f"❌ {astronomy_dir} folder not found in {backup_root}")
        return 0

    total_added = 0

    for astro_dir in os.listdir(data_root):
        astro_path = os.path.join(data_root, astro_dir)
        if not os.path.isdir(astro_path):
            continue

        subdirs = [d for d in os.listdir(astro_path) if os.path.isdir(os.path.join(astro_path, d))]
        print(f"🔍 Processing Dir: {astro_dir}")

        found_data = False
        total_previous = total_added
        astro_name = extract_astro_name_from_folder(astro_dir)
        if not astro_name:
            check_target_file = os.path.join(astro_path, astro_dir)
            astro_name = extract_target_json(check_target_file)
        if astro_name:
            found_data = True
            astro_object_id = insert_astro_object(conn, astro_name)
            print(f"📂 Processing direct Dwarf data: {astro_dir}")
            total_added += process_dwarf_folder(
                conn, backup_root, astro_path,
                astro_object_id, dwarf_id, backup_drive_id
            )
            if total_added - total_previous == 1:
                print(f"📂 Found 1 new file in {astro_dir}")
            elif total_added != total_previous:
                print(f"📂 Found {total_added - total_previous} new files in {astro_dir}")

        else:
            astro_name = astro_dir
            # Traverse all folders below astro_path
            for root, dirs, files in os.walk(astro_path):
                if not dirs and files:
                    last_dir = os.path.basename(os.path.normpath(root))
                    check_target = extract_astro_name_from_folder(last_dir)
                    if not check_target:
                        check_target = extract_target_json(root)

                    if check_target:
                        if not found_data:
                            if astro_name == "RESTACKED":
                                astro_object_id = insert_astro_object(conn, check_target)
                                print(f"add astro_object_id : {check_target}")
                            else: # use Main AstroDir Name
                                astro_object_id = insert_astro_object(conn, astro_name)
                                print(f"add astro_object_id : {astro_name}")
                                found_data = True
                        print(f"📂 Processing session folder (deep): {root}")
                        total_added += process_dwarf_folder(
                            conn, backup_root, root,
                            astro_object_id, dwarf_id, backup_drive_id
                        )

            if total_added - total_previous == 1:
                print(f"📂 Found 1 new file in {astro_dir}")
            elif total_added != total_previous:
                print(f"📂 Found {total_added - total_previous} new files in {astro_dir}")

        if not found_data:
            print(f"⚠️ Ignored unrecognized folder: {astro_dir}")

    conn.commit()
    return total_added

def process_dwarf_folder (conn, backup_root, dwarf_path, astro_object_id, dwarf_id, backup_drive_id = None): 
    added = 0
    session_date = extract_session_datetime(dwarf_path)
    if not session_date:
        print("Error : No session_date")
        return added

    for filename in os.listdir(dwarf_path):
        if not filename.lower().endswith(("stacked.jpg", "stacked.png")):
            continue

        full_file_path = os.path.join(dwarf_path, filename)
        dwarf_data_id = insert_dwarf_data(conn, backup_root, full_file_path)
        session_dt_str = session_date.strftime("%Y-%m-%d %H:%M:%S.%f")
        session_dir = os.path.basename(os.path.normpath(dwarf_path))

        if dwarf_data_id:
            if backup_drive_id:
                # Insert entry in BackupEntry
                new_id = insert_BackupEntry(conn, backup_drive_id, dwarf_id, astro_object_id, dwarf_data_id, session_dt_str, session_dir)
                added += 1 if new_id != 0 else 0
            else:
                # Insert entry in DwarfEntry
                new_id = insert_DwarfEntry(conn, dwarf_id, astro_object_id, dwarf_data_id, session_dt_str, session_dir)
                added += 1 if new_id != 0 else 0
    return added

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