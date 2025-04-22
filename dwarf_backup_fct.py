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
    cursor = conn.cursor()

    if dwarf_id is not None:
        # Vérifie si l'ID existe
        cursor.execute("SELECT COUNT(*) FROM Dwarf WHERE id = ?", (dwarf_id,))
        if cursor.fetchone()[0]:
            return dwarf_id
        elif batch_mode:
            # Crée automatiquement si inexistant
            cursor.execute(
                "INSERT INTO Dwarf (id, name, description) VALUES (?, ?, ?)",
                (dwarf_id, default_name, default_description)
            )
            conn.commit()
            return dwarf_id
        else:
            raise ValueError(f"Dwarf ID {dwarf_id} non trouvé.")

    # Aucun dwarf_id fourni
    cursor.execute("SELECT id, name FROM Dwarf")
    dwarfs = cursor.fetchall()

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
            cursor.execute(
                "INSERT INTO Dwarf (name, description) VALUES (?, ?)",
                (default_name, default_description)
            )
            conn.commit()
            return cursor.lastrowid
        else:
            create = input("No Dwarf. Do you want to create one? (y/n):").strip().lower()
            if create == 'o':
                name = input("Name of the new Dwarf:").strip()
                desc = input("Description: ").strip()
                cursor.execute("INSERT INTO Dwarf (name, description) VALUES (?, ?)", (name, desc))
                conn.commit()
                return cursor.lastrowid
            else:
                raise ValueError("No Dwarf, cancellation.")

def insert_or_get_backup_drive(conn, location, dwarf_id=None):
    cursor = conn.cursor()
    cursor.execute("SELECT id, dwarf_id FROM BackupDrive WHERE location = ?", (location,))
    row = cursor.fetchone()

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

        cursor.execute("""
            INSERT INTO BackupDrive (name, description, astronomy_dir, location, dwarf_id)
            VALUES (?, ?, ?, ?, ?)
        """, (name, description, location, astroDir, dwarf_id))
        conn.commit()
        return cursor.lastrowid, dwarf_id

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

    cursor = conn.execute("""
        INSERT OR IGNORE INTO DwarfData (
            file_path, modification_time, thumbnail_path, file_size,
            dec, ra, target, binning, format, exp_time, gain,
            shotsToTake, shotsTaken, shotsStacked, ircut, width,
            height, media_type, stacked_fits_path, stacked_fits_md5
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        relative_path, mtime, thumbnail, size,
        meta.get('dec'), meta.get('ra'), meta.get('target'),
        meta.get('binning'), meta.get('format'), meta.get('exp_time'),
        meta.get('gain'), meta.get('shotsToTake'), meta.get('shotsTaken'),
        meta.get('shotsStacked'), meta.get('ircut'), None,
        None, None, stacked_path, stacked_md5
    ))

    return cursor.lastrowid

def insert_astro_object(conn, name):
    cursor = conn.execute("SELECT id FROM AstroObject WHERE name = ?", (name,))
    row = cursor.fetchone()
    if row:
        return row[0]
    else:
        cursor = conn.execute("INSERT INTO AstroObject (name, description) VALUES (?, ?)", (name, ""))
        return cursor.lastrowid

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
                conn.execute("""
                    INSERT OR IGNORE INTO BackupEntry (
                        backup_drive_id, dwarf_id, astro_object_id, dwarf_data_id, session_date, session_dir
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (backup_drive_id, dwarf_id, astro_object_id, dwarf_data_id, session_dt_str, session_dir))
                added += 1
            else:
                # Insert entry in DwarfEntry
                conn.execute("""
                    INSERT OR IGNORE INTO DwarfEntry (
                        dwarf_id, astro_object_id, dwarf_data_id, session_date, session_dir
                    ) VALUES (?, ?, ?, ?, ?)
                """, (dwarf_id, astro_object_id, dwarf_data_id, session_dt_str, session_dir))
                added += 1
    return added

def has_related_backup_entries(conn, backup_drive_id):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM BackupEntry WHERE backup_drive_id = ?",
        (backup_drive_id,)
    )
    count = cursor.fetchone()[0]
    return count > 0

def delete_backup_entries_and_dwarf_data(conn, backup_drive_id):
    conn.execute("PRAGMA foreign_keys = ON")  # Enforce FK rules
    cursor = conn.cursor()

    # Step 1: Get all related DwarfData IDs
    cursor.execute("""
        SELECT dwarf_data_id FROM BackupEntry WHERE backup_drive_id = ?
    """, (backup_drive_id,))
    dwarf_data_ids = [row[0] for row in cursor.fetchall() if row[0] is not None]

    # Step 2: Delete related BackupEntry rows
    cursor.execute("DELETE FROM BackupEntry WHERE backup_drive_id = ?", (backup_drive_id,))

    # Step 3: Delete associated DwarfData rows
    for dwarf_data_id in dwarf_data_ids:
        # Optional check: ensure it's not used elsewhere before deleting
        cursor.execute("""
            SELECT COUNT(*) FROM BackupEntry WHERE dwarf_data_id = ?
        """, (dwarf_data_id,))
        count = cursor.fetchone()[0]

        if count == 0:
            cursor.execute("DELETE FROM DwarfData WHERE id = ?", (dwarf_data_id,))

    conn.commit()
    print(f"Deleted {len(dwarf_data_ids)} DwarfData entries (if not reused) and all related BackupEntry rows.")

def delete_dwarf_entries_and_dwarf_data(conn, dwarf_id):
    conn.execute("PRAGMA foreign_keys = ON")  # Enforce FK rules
    cursor = conn.cursor()

    # Step 1: Get all related DwarfData IDs
    cursor.execute("""
        SELECT dwarf_data_id FROM DwarfEntry WHERE dwarf_id = ?
    """, (dwarf_id,))
    dwarf_data_ids = [row[0] for row in cursor.fetchall() if row[0] is not None]

    # Step 2: Delete related BackupEntry rows
    cursor.execute("DELETE FROM DwarfEntry WHERE dwarf_id = ?", (dwarf_id,))

    # Step 3: Delete associated DwarfData rows
    for dwarf_data_id in dwarf_data_ids:
        # Optional check: ensure it's not used elsewhere before deleting
        cursor.execute("""
            SELECT COUNT(*) FROM DwarfEntry WHERE dwarf_data_id = ?
        """, (dwarf_data_id,))
        count = cursor.fetchone()[0]

        if count == 0:
            cursor.execute("DELETE FROM DwarfData WHERE id = ?", (dwarf_data_id,))

    conn.commit()
    print(f"Deleted {len(dwarf_data_ids)} DwarfData entries (if not reused) and all related DwarfEntry rows.")

def is_session_backed_up(conn, session_dir):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM BackupEntry WHERE session_dir = ? LIMIT 1",
        (session_dir,)
    )
    return cursor.fetchone() is not None

def get_session_present_in_Dwarf(conn, session_dir):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT Dwarf.id, Dwarf.name
        FROM DwarfEntry
        JOIN Dwarf ON DwarfEntry.dwarf_id = Dwarf.id
        WHERE DwarfEntry.session_dir = ?
        LIMIT 1
    """, (session_dir,))
    result = cursor.fetchone()
    return result

def get_session_present_in_backupDrive(conn, session_dir):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT BackupDrive.id, BackupDrive.name, BackupDrive.location, BackupDrive.astronomy_dir
        FROM BackupEntry
        JOIN BackupDrive ON BackupEntry.backup_drive_id = BackupDrive.id
        WHERE BackupEntry.session_dir = ?
        LIMIT 1
    """, (session_dir,))
    result = cursor.fetchone()
    return result

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