import os
import sys
import sqlite3
from datetime import datetime
from io import StringIO
import csv

from api.dwarf_backup_db import commit_db

# Global list and dictionary
DEFAULT_GROUP_NAMES = ["Unknown", "MOSAIC_Unknown", "Manual"]
DEFAULT_GROUP_IDS = {}

def generate_order_case(field: str, names: list[str], priority=0, else_val=1) -> str:
    lower_names = "', '".join(name.lower() for name in names)
    return f"""CASE
    WHEN LOWER({field}) IN ('{lower_names}') THEN {priority}
    ELSE {else_val}
END"""

########################
# Settings functions
########################

def set_setting_text(conn: sqlite3.Connection, parameter, value):
    try:
        cursor = conn.cursor()

        if get_setting_text(conn, parameter) is None : 
            cursor.execute("INSERT INTO Settings (parameter, type, valueText, valueInt) VALUES (?, ?, ?, ?)", (parameter, "TEXT", value , 0))
        else :
            cursor.execute("UPDATE Settings SET type=?, valueText=?, valueInt=0  WHERE parameter=?",
                           ("TEXT", value, parameter))
        commit_db(conn)
        return True
    except Exception as e:
        print(f"[DB ERROR] Failed to fetch text setting for parameter: {parameter}: {e}")
        return None

def get_setting_text(conn: sqlite3.Connection, parameter):
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT valueText FROM Settings WHERE parameter = ?", (parameter,))
        result = cursor.fetchone()
        return result[0] if result else None
    except Exception as e:
        print(f"[DB ERROR] Failed to fetch text setting for parameter: {parameter}: {e}")
        return None

def set_setting_int(conn: sqlite3.Connection, parameter, value):
    try:
        cursor = conn.cursor()

        if get_setting_text(conn, parameter) is None : 
            cursor.execute("INSERT INTO Settings (parameter, type, valueText, valueInt) VALUES (?, ?, ?, ?)", (parameter, "INT", "", value))
        else :
            cursor.execute("UPDATE Settings SET type=?, valueText='', valueInt=?  WHERE parameter=?",
                           ("INT", value, parameter))
        commit_db(conn)
        return True
    except Exception as e:
        print(f"[DB ERROR] Failed to fetch text setting for parameter: {parameter}: {e}")
        return None

def get_setting_int(conn: sqlite3.Connection, parameter):
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT valueInt FROM Settings WHERE parameter = ?", (parameter,))
        result = cursor.fetchone()
        return result[0] if result else None
    except Exception as e:
        print(f"[DB ERROR] Failed to fetch integer setting for parameter: {parameter}: {e}")
        return None

########################
# Local Dir DB function
########################
# ------------------------------------------
# ✅ Ensure DWARF_LOCAL_PATH is configured
# ------------------------------------------
def ensure_dwarf_local_path(conn: sqlite3.Connection):
    cursor = conn.cursor()
    cursor.execute("SELECT valueText FROM Settings WHERE parameter = ?", ("DWARF_LOCAL_PATH",))
    row = cursor.fetchone()

    if row is None:
        # Try to auto-detect old folder next to the app
        default_path = os.path.abspath("./Dwarf_Local")
        if os.path.isdir(default_path):
            cursor.execute(
                "INSERT INTO Settings (parameter, type, valueText, valueInt) VALUES (?, ?, ?, ?)",
                ("DWARF_LOCAL_PATH", "TEXT", os.path.dirname(default_path), 0)
            )
            conn.commit()
            print(f"[INFO] Detected existing Dwarf_Local at {default_path}")
            return True
        else:
            print("[INFO] Fresh install — user must select a Dwarf_Local path.")
            return False

    value = row[0]
    if not value or value == "Not Defined":
        return False

    # Parent directory must exist
    if not os.path.isdir(value):
        return False

    # Auto-create the Dwarf_Local subfolder if parent exists but subdir doesn't
    dwarf_local = os.path.join(value, "Dwarf_Local")
    if not os.path.isdir(dwarf_local):
        try:
            os.makedirs(dwarf_local, exist_ok=True)
            print(f"[INFO] Created Dwarf_Local at {dwarf_local}")
        except Exception as e:
            print(f"[ERROR] Could not create Dwarf_Local: {e}")
            return False

    return True

def get_db_local_dwarf_dir(conn: sqlite3.Connection):
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT valueText FROM Settings WHERE parameter = ?", ("DWARF_LOCAL_PATH",))
        result = cursor.fetchone()  # Fetch one
        return result[0] if result else "."
    except Exception as e:
        print(f"[DB ERROR] Failed to fetch local_dwarf_dir: {e}")
        return None

##################
# Dwarf functions
##################

def is_dwarf_exists(conn: sqlite3.Connection, dwarf_id=None):
    try:
        if dwarf_id:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM Dwarf WHERE id = ?", (dwarf_id,))
            return cursor.fetchone()[0]
        else:
            return False
    except Exception as e:
        print(f"[DB ERROR] Failed to verify is dwarf exists {dwarf_id}: {e}")
        return False

def get_dwarf_Names(conn: sqlite3.Connection):
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM Dwarf ORDER BY name")
        return cursor.fetchall()
    except Exception as e:
        print(f"[DB ERROR] Failed to fetch dwarfs: {e}")
        return []

def get_dwarf_detail(conn: sqlite3.Connection, dwarf_id=None):
    try:
        if dwarf_id:
            cursor = conn.cursor()
            cursor.execute("SELECT name, description, usb_astronomy_dir, type, last_scan_date, ip_sta_mode, mtp_id FROM Dwarf WHERE id = ?", (dwarf_id,))
            return cursor.fetchone()
        else:
           return []

    except Exception as e:
        print(f"[DB ERROR] Failed to fetch dwarf detail: {e}")
        return []

def set_dwarf_detail(conn: sqlite3.Connection, name, desc, usb_astronomy_dir, dtype, ip_sta_mode, mtp_id, dwarf_id=None):
    try:
        if dwarf_id:
            cursor = conn.cursor()
            cursor.execute("UPDATE Dwarf SET name=?, description=?, usb_astronomy_dir=?, type=?, ip_sta_mode=?, mtp_id=?  WHERE id=?",
                           (name, desc, usb_astronomy_dir, dtype, ip_sta_mode, mtp_id, dwarf_id))
            commit_db(conn)
            return True
        else:
            return False

    except Exception as e:
        print(f"[DB ERROR] Failed to update dwarf detail: {e}")
        return False

def add_dwarf_detail(conn: sqlite3.Connection, name, desc, usb_astronomy_dir, dtype, ip_sta_mode, mtp_id = None):
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO Dwarf (name, description, usb_astronomy_dir, type, ip_sta_mode, mtp_id) VALUES (?, ?, ?, ?, ?, ?)",
                       (name, desc, usb_astronomy_dir, dtype, ip_sta_mode, mtp_id))
        if cursor.rowcount > 0:
            dwarf_id = cursor.lastrowid
            commit_db(conn)
            return dwarf_id
        else:
            print("Error Insert ignored : add_dwarf_detail")
            return None

    except Exception as e:
        print(f"[DB ERROR] Failed to add dwarf detail: {e}")
        return None

def set_dwarf_scan_date(conn: sqlite3.Connection, dwarf_id=None):
    try:
        if dwarf_id:
            date_scan = datetime.now().isoformat(sep=' ', timespec='seconds')  # e.g., '2025-05-05 12:34:56'
            cursor = conn.cursor()
            cursor.execute("UPDATE Dwarf SET last_scan_date=? WHERE id=?",
                           (date_scan, dwarf_id))
            commit_db(conn)
            return True
        else:
            return False

    except Exception as e:
        print(f"[DB ERROR] failed to set dwarf backup last_scan_date: {e}")
        return False

def set_dwarf_mtp_id(conn: sqlite3.Connection, dwarf_id=None, mtp_id = None):
    try:
        if dwarf_id and mtp_id:
            cursor = conn.cursor()
            cursor.execute("UPDATE Dwarf SET mtp_id=? WHERE id=?",
                           (mtp_id, dwarf_id))
            commit_db(conn)
            return True
        else:
            return False

    except Exception as e:
        print(f"[DB ERROR] failed to set dwarf set_dwarf_mtp_id: {e}")
        return False

def get_dwarf_mtp_drive(conn: sqlite3.Connection, path = None):
    try:
        if path:
            cursor = conn.cursor()
            cursor.execute("SELECT Dwarf.id, name, mtp_id FROM Dwarf, MtpDevices WHERE mtp_id = MtpDevices.id and MtpDevices.mtp_drive_id = ? ORDER BY name",
                            (str(path),))
            return cursor.fetchall()

        else:
            return []

    except Exception as e:
        print(f"[DB ERROR] failed to get dwarf get_dwarf_mtp_drive: {e}")
        return []

###################
# Backup functions
###################

def get_backupDrive_Names(conn: sqlite3.Connection):
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM BackupDrive ORDER BY name")
        return cursor.fetchall()
    except Exception as e:
        print(f"[DB ERROR] Failed to fetch backup drives: {e}")
        return []

def get_backupDrive_detail(conn: sqlite3.Connection, backupDrive_id=None):
    try:
        if backupDrive_id:
            cursor = conn.cursor()
            cursor.execute("SELECT BackupDrive.name, BackupDrive.description, BackupDrive.location, BackupDrive.astronomy_dir, Dwarf.name, BackupDrive.last_backup_scan_date FROM BackupDrive, Dwarf WHERE BackupDrive.id = ? and BackupDrive.dwarf_id = Dwarf.id", (backupDrive_id,))
            return cursor.fetchone()
        else:
           return []

    except Exception as e:
        print(f"[DB ERROR] Failed to fetch backup drive detail {backupDrive_id}: {e}")
        return []

def get_backupDrive_id_from_location(conn: sqlite3.Connection, location=None):
    try:
        if location:
            cursor = conn.cursor()
            cursor.execute("SELECT id, dwarf_id FROM BackupDrive WHERE location=?", (location,))
            return cursor.fetchone()
        else:
           return []

    except Exception as e:
        print(f"[DB ERROR] Failed to fetch backup drive from location {location}: {e}")
        return []

def get_backupDrive_list(conn: sqlite3.Connection):
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, description, location, astronomy_dir, dwarf_id, last_backup_scan_date FROM BackupDrive")
        return cursor.fetchall()

    except Exception as e:
        print(f"[DB ERROR] Failed to fetch backupDrive list: {e}")
        return []

def get_backupDrive_list_dwarfId(conn: sqlite3.Connection, dwarf_id = None):
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, description, location, astronomy_dir, dwarf_id FROM BackupDrive WHERE dwarf_id = ?", (dwarf_id,))
        return cursor.fetchall()

    except Exception as e:
        print(f"[DB ERROR] Failed to fetch backupDrive list dwarfId: {e}")
        return []

def set_backupDrive_detail(conn: sqlite3.Connection, name, desc, astroDir, dwarf_id, location=None):
    try:
        if location:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE BackupDrive SET name=?, description=?, astronomy_dir=?, dwarf_id=? WHERE location=?
            """, (name, desc, astroDir, dwarf_id, location))
            commit_db(conn)
            return True
        else:
            return False

    except Exception as e:
        print(f"[DB ERROR] Failed to set backupDrive detail: {e}")
        return False

def add_backupDrive_detail(conn: sqlite3.Connection, name, desc, location, astroDir, dwarf_id=None):
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO BackupDrive (name, description, location, astronomy_dir, dwarf_id)
            VALUES (?, ?, ?, ?, ?)
        """, (name, desc, location, astroDir, dwarf_id))

        if cursor.rowcount > 0:
            backupDrive_id = cursor.lastrowid
            commit_db(conn)
            return backupDrive_id
        else:
            print("Error Insert ignored : add_backupDrive_detail")
            return None

    except Exception as e:
        print(f"[DB ERROR] Failed to add backupDrive detail: {e}")
        return None

def set_backup_scan_date(conn: sqlite3.Connection, backupDrive_id=None):
    try:
        if backupDrive_id:
            date_scan = datetime.now().isoformat(sep=' ', timespec='seconds')  # e.g., '2025-05-05 12:34:56'
            cursor = conn.cursor()
            cursor.execute("UPDATE BackupDrive SET last_backup_scan_date=? WHERE id=?",
                           (date_scan, backupDrive_id))
            commit_db(conn)
            return True
        else:
            return False

    except Exception as e:
        print(f"[DB ERROR] Failed to set backup last_backup_scan_date: {e}")
        return False

###################
# Delete functions
###################

def del_dwarf(conn: sqlite3.Connection, dwarf_id=None):
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM Dwarf WHERE id = ?", (dwarf_id,))
        commit_db(conn)
        return True

    except Exception as e:
        print(f"[DB ERROR] Failed to delete Dwarf {dwarf_id}: {e}")
        return False

def del_backupDrive(conn: sqlite3.Connection, backupDrive_id=None):
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM BackupDrive WHERE id = ?", (backupDrive_id,))
        commit_db(conn)
        return True

    except Exception as e:
        print(f"[DB ERROR] Failed to delete backupDrive {backupDrive_id}: {e}")
        return False

def delete_unused_astro_objects(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("""
            DELETE FROM AstroObject
            WHERE id NOT IN (
                SELECT astro_object_id FROM BackupEntry WHERE astro_object_id IS NOT NULL
                UNION
                SELECT astro_object_id FROM DwarfEntry WHERE astro_object_id IS NOT NULL
                UNION
                SELECT astro_object_id FROM ManualSessionEntry WHERE astro_object_id IS NOT NULL
                UNION
                SELECT astro_group_id FROM BackupEntry WHERE astro_group_id IS NOT NULL
                UNION
                SELECT astro_group_id FROM DwarfEntry WHERE astro_group_id IS NOT NULL
                UNION
                SELECT astro_group_id FROM ManualSessionEntry WHERE astro_group_id IS NOT NULL
            )
        """)
        commit_db(conn)
        print("Unused AstroObject entries deleted.")
        return True
    except Exception as e:
        print(f"[DB ERROR] Failed to delete unused astro objects: {e}")
        return False

def can_delete_astro_object(conn: sqlite3.Connection, astro_id: int) -> bool:
    for table, column in [
        ('BackupEntry', 'astro_object_id'),
        ('DwarfEntry', 'astro_object_id'),
        ('ManualSessionEntry', 'astro_object_id'),
        ('BackupEntry', 'astro_group_id'),
        ('DwarfEntry', 'astro_group_id'),
        ('ManualSessionEntry', 'astro_group_id'),
    ]:
        query = f"SELECT 1 FROM {table} WHERE {column} = ? LIMIT 1"
        if conn.execute(query, (astro_id,)).fetchone():
            return False
    return True

def del_astroObjectId(conn: sqlite3.Connection, astro_id: int ) -> bool:
    try:
        if can_delete_astro_object(conn, astro_id):
            conn.execute("DELETE FROM AstroObject WHERE id = ?", (astro_id,))
            commit_db(conn)
            return True
        else:
            print("[FAIL] Cannot delete: AstroObject is still in use.")
            return False

    except Exception as e:
        print(f"[DB ERROR] Failed to delete astro_object {astro_id}: {e}")
        return False

def del_astroObjects(conn: sqlite3.Connection):
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM AstroObject")
        commit_db(conn)
        return True

    except Exception as e:
        print(f"[DB ERROR] Failed to delete astro_object: {e}")
        return False

####################################
# Dwarf- Backup Relations functions
####################################

def get_backupDrive_dwarfId(conn: sqlite3.Connection, backup_drive_id=None):
    try:
        if backup_drive_id:
            cursor = conn.cursor()
            # Get the dwarf_id for the given BackupDrive
            cursor.execute("SELECT dwarf_id FROM BackupDrive WHERE id = ?", (backup_drive_id,))
            result = cursor.fetchone()
            return result[0] if result else None
        else:
            return None
    except Exception as e:
        print(f"[DB ERROR] Failed to fetch backupDrive dwarfId: {e}")
        return []

def get_backupDrive_dwarfNames(conn: sqlite3.Connection, backup_drive_id=None):
    try:
        if backup_drive_id:
            cursor = conn.cursor()
            # Fetch dwarfs linked to this backup
            cursor.execute("""
                SELECT DISTINCT Dwarf.id, Dwarf.name
                FROM Dwarf
                JOIN BackupDrive ON BackupDrive.dwarf_id = Dwarf.id
                WHERE BackupDrive.id = ?
                ORDER BY Dwarf.name
            """, (backup_drive_id,))
            return cursor.fetchall()
        else:
            return None
    except Exception as e:
        print(f"[DB ERROR] Failed to fetch backupDrive dwarfNames: {e}")
        return []

display_name_expr = """
CASE 
    WHEN AstroObject.description IS NOT NULL AND TRIM(AstroObject.description) != '' 
    THEN AstroObject.description || ' [' || AstroObject.name || ']' 
    ELSE AstroObject.name 
END
"""

group_display_expr = """
CASE 
    WHEN AstroGroup.description IS NOT NULL AND TRIM(AstroGroup.description) != '' 
    THEN AstroGroup.description || ' [' || AstroGroup.name || ']' 
    ELSE AstroGroup.name 
END
"""

def get_Objects_backup(conn: sqlite3.Connection, backup_drive_id=None, dwarf_id=None, only_on_dwarf=None, only_on_backup=None, filter_object=None):
    try:
        cursor = conn.cursor()

        query = f"""
            SELECT DISTINCT 
                AstroObject.id, 
                {display_name_expr} AS display_name,
                AstroObject.dso_id,
                AstroObject.is_group
            FROM AstroObject
            JOIN BackupEntry
                ON (
                    (AstroObject.id = BackupEntry.astro_object_id AND BackupEntry.astro_group_id IS NULL)
                    OR
                    (AstroObject.id = BackupEntry.astro_object_id AND BackupEntry.astro_group_id IS NOT NULL AND AstroObject.description != '' )
                    OR
                    (AstroObject.id = BackupEntry.astro_group_id AND BackupEntry.astro_object_id IS NOT NULL AND AstroObject.description = '')
                )
            JOIN BackupDrive ON BackupEntry.backup_drive_id = BackupDrive.id
            JOIN DwarfData ON BackupEntry.dwarf_data_id = DwarfData.id
        """
        conditions = []
        params = []

        if backup_drive_id:
            conditions.append("BackupEntry.backup_drive_id = ?")
            params.append(backup_drive_id)

        if dwarf_id:  # not "(All Dwarfs)"
            conditions.append("BackupEntry.dwarf_id = ?")
            params.append(dwarf_id)

            if only_on_dwarf and not only_on_backup:
                # Filter BackupEntry to only those with session_dir present in DwarfEntry for same dwarf
                conditions.append("""
                    BackupEntry.session_dir IN (
                        SELECT session_dir FROM DwarfEntry WHERE dwarf_id = ?
                    )
                """)
                params.append(dwarf_id)

            if only_on_backup and not only_on_dwarf:
                # Filter BackupEntry to only those with session_dir not present in DwarfEntry for same dwarf
                conditions.append("""
                    BackupEntry.session_dir NOT IN (
                        SELECT session_dir FROM DwarfEntry WHERE dwarf_id = ?
                    )
                """)
                params.append(dwarf_id)

        if filter_object:
            conditions.append("LOWER(display_name) LIKE ?")
            params.append(f"%{filter_object.lower()}%")
    
        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        order_case_sql = generate_order_case("display_name", DEFAULT_GROUP_NAMES)
        query += f"""
            ORDER BY 
                {order_case_sql},
                display_name
        """

        cursor.execute(query, params)

        return cursor.fetchall()

    except Exception as e:
        print(f"[DB ERROR] Failed to fetch get_Objects_backup: {e}")
        return []

def get_Objects_duplicate_backup(conn: sqlite3.Connection, backup_drive_id=None, dwarf_id=None, only_on_dwarf=None, only_on_backup=None, filter_object=None):
    try:
        cursor = conn.cursor()

        query = f"""
            SELECT DISTINCT 
                AstroObject.id, 
                {display_name_expr} AS display_name,
                AstroObject.dso_id,
                AstroObject.is_group
            FROM AstroObject
            JOIN BackupEntry
                ON (
                    (AstroObject.id = BackupEntry.astro_object_id AND BackupEntry.astro_group_id IS NULL)
                    OR
                    (AstroObject.id = BackupEntry.astro_object_id AND BackupEntry.astro_group_id IS NOT NULL AND AstroObject.description != '' )
                    OR
                    (AstroObject.id = BackupEntry.astro_group_id AND BackupEntry.astro_object_id IS NOT NULL)
                )
            JOIN BackupDrive ON BackupEntry.backup_drive_id = BackupDrive.id
            JOIN DwarfData ON BackupEntry.dwarf_data_id = DwarfData.id
        """
        conditions = []
        params = []

        # Filter Duplicates Sessions
        conditions.append("""
            BackupEntry.session_dir IN (
                SELECT session_dir
                FROM BackupEntry
                GROUP BY session_dir
                HAVING COUNT(*) > 1
            ) 
        """)

        if backup_drive_id:
            conditions.append("BackupEntry.backup_drive_id = ?")
            params.append(backup_drive_id)

        if dwarf_id:  # not "(All Dwarfs)"
            conditions.append("BackupEntry.dwarf_id = ?")
            params.append(dwarf_id)

            if only_on_dwarf and not only_on_backup:
                # Filter BackupEntry to only those with session_dir present in DwarfEntry for same dwarf
                conditions.append("""
                    BackupEntry.session_dir IN (
                        SELECT session_dir FROM DwarfEntry WHERE dwarf_id = ?
                    )
                """)
                params.append(dwarf_id)

            if only_on_backup and not only_on_dwarf:
                # Filter BackupEntry to only those with session_dir not present in DwarfEntry for same dwarf
                conditions.append("""
                    BackupEntry.session_dir NOT IN (
                        SELECT session_dir FROM DwarfEntry WHERE dwarf_id = ?
                    )
                """)
                params.append(dwarf_id)

        if filter_object:
            conditions.append("LOWER(display_name) LIKE ?")
            params.append(f"%{filter_object.lower()}%")
    
        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        order_case_sql = generate_order_case("display_name", DEFAULT_GROUP_NAMES)
        query += f"""
            ORDER BY 
                {order_case_sql},
                display_name
        """

        cursor.execute(query, params)

        return cursor.fetchall()

    except Exception as e:
        print(f"[DB ERROR] Failed to fetch get_Objects_duplicate_backup: {e}")
        return []

def get_Objects_dwarf(conn: sqlite3.Connection, dwarf_id=None, only_on_dwarf=None, only_on_backup=None, filter_object=None):
    try:
        cursor = conn.cursor()

        query = f"""
            SELECT DISTINCT 
                AstroObject.id, 
                {display_name_expr} AS display_name,
                AstroObject.dso_id,
                AstroObject.is_group
            FROM AstroObject
            JOIN DwarfEntry
                ON (
                    (AstroObject.id = DwarfEntry.astro_object_id AND DwarfEntry.astro_group_id IS NULL)
                    OR
                    (AstroObject.id = DwarfEntry.astro_object_id AND DwarfEntry.astro_group_id IS NOT NULL AND AstroObject.description != '' )
                    OR
                    (AstroObject.id = DwarfEntry.astro_group_id AND DwarfEntry.astro_object_id IS NOT NULL)
                )
            JOIN DwarfData ON DwarfEntry.dwarf_data_id = DwarfData.id
        """
        conditions = []
        params = []

        if dwarf_id:  # not "(All Dwarfs)"
            conditions.append("DwarfEntry.dwarf_id = ?")
            params.append(dwarf_id)

            if only_on_dwarf and not only_on_backup:
                # Filter DwarfEntry to only those with session_dir not present in BackupEntry for same dwarf
                conditions.append("""
                    DwarfEntry.session_dir NOT IN (
                        SELECT session_dir FROM BackupEntry WHERE dwarf_id = ?
                    )
                """)
                params.append(dwarf_id)

            if only_on_backup and not only_on_dwarf:
                # Filter DwarfEntry to only those with session_dir present in BackupEntry for same dwarf
                conditions.append("""
                    DwarfEntry.session_dir IN (
                        SELECT session_dir FROM BackupEntry WHERE dwarf_id = ?
                    )
                """)
                params.append(dwarf_id)

        if filter_object:
            conditions.append("LOWER(display_name) LIKE ?")
            params.append(f"%{filter_object.lower()}%")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        order_case_sql = generate_order_case("display_name", DEFAULT_GROUP_NAMES)
        query += f"""
            ORDER BY 
                {order_case_sql},
                display_name
        """

        cursor.execute(query, params)

        return cursor.fetchall()

    except Exception as e:
        print(f"[DB ERROR] Failed to fetch get_Objects_dwarf: {e}")
        return []

def get_countObjects_backup(conn: sqlite3.Connection, backup_drive_id=None, dwarf_id=None, only_on_dwarf=None, only_on_backup=None, filter_object=None):
    try:
        cursor = conn.cursor()

        query = """
                SELECT COUNT(*)
                FROM BackupEntry
                JOIN BackupDrive ON BackupEntry.backup_drive_id = BackupDrive.id
                JOIN DwarfData ON BackupEntry.dwarf_data_id = DwarfData.id
                JOIN AstroObject ON BackupEntry.astro_object_id = AstroObject.id
                LEFT JOIN AstroObject AS AstroGroup ON BackupEntry.astro_group_id = AstroGroup.id
        """
        conditions = []
        params = []

        if backup_drive_id:
            conditions.append("BackupEntry.backup_drive_id = ?")
            params.append(backup_drive_id)

        if dwarf_id:  # not "(All Dwarfs)"
            conditions.append("BackupEntry.dwarf_id = ?")
            params.append(dwarf_id)

            if only_on_dwarf and not only_on_backup:
                # Filter BackupEntry to only those with session_dir present in DwarfEntry for same dwarf
                conditions.append("""
                    BackupEntry.session_dir IN (
                        SELECT session_dir FROM DwarfEntry WHERE dwarf_id = ?
                    )
                """)
                params.append(dwarf_id)

            if only_on_backup and not only_on_dwarf:
                # Filter BackupEntry to only those with session_dir not present in DwarfEntry for same dwarf
                conditions.append("""
                    BackupEntry.session_dir NOT IN (
                        SELECT session_dir FROM DwarfEntry WHERE dwarf_id = ?
                    )
                """)
                params.append(dwarf_id)

        if filter_object:
            conditions.append(f"(LOWER({display_name_expr}) LIKE ? OR LOWER({group_display_expr}) LIKE ?)")
            params.append(f"%{filter_object.lower()}%")
            params.append(f"%{filter_object.lower()}%")
        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        cursor.execute(query, params)

        return cursor.fetchone()[0]

    except Exception as e:
        print(f"[DB ERROR] Failed to fetch get_countObjects_backup: {e}")
        return []

def get_countObjects_duplicate_backup(conn: sqlite3.Connection, backup_drive_id=None, dwarf_id=None, only_on_dwarf=None, only_on_backup=None, filter_object=None):
    try:
        cursor = conn.cursor()

        query = """
                SELECT COUNT(*)
                FROM BackupEntry
                JOIN BackupDrive ON BackupEntry.backup_drive_id = BackupDrive.id
                JOIN DwarfData ON BackupEntry.dwarf_data_id = DwarfData.id
                JOIN AstroObject ON BackupEntry.astro_object_id = AstroObject.id
                LEFT JOIN AstroObject AS AstroGroup ON BackupEntry.astro_group_id = AstroGroup.id
        """
        conditions = []
        params = []

        # Filter Duplicates Sessions
        conditions.append("""
            BackupEntry.session_dir IN (
                SELECT session_dir
                FROM BackupEntry
                GROUP BY session_dir
                HAVING COUNT(*) > 1
            ) 
        """)

        if backup_drive_id:
            conditions.append("BackupEntry.backup_drive_id = ?")
            params.append(backup_drive_id)

        if dwarf_id:  # not "(All Dwarfs)"
            conditions.append("BackupEntry.dwarf_id = ?")
            params.append(dwarf_id)

            if only_on_dwarf and not only_on_backup:
                # Filter BackupEntry to only those with session_dir present in DwarfEntry for same dwarf
                conditions.append("""
                    BackupEntry.session_dir IN (
                        SELECT session_dir FROM DwarfEntry WHERE dwarf_id = ?
                    )
                """)
                params.append(dwarf_id)

            if only_on_backup and not only_on_dwarf:
                # Filter BackupEntry to only those with session_dir not present in DwarfEntry for same dwarf
                conditions.append("""
                    BackupEntry.session_dir NOT IN (
                        SELECT session_dir FROM DwarfEntry WHERE dwarf_id = ?
                    )
                """)
                params.append(dwarf_id)

        if filter_object:
            conditions.append(f"(LOWER({display_name_expr}) LIKE ? OR LOWER({group_display_expr}) LIKE ?)")
            params.append(f"%{filter_object.lower()}%")
            params.append(f"%{filter_object.lower()}%")
        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        cursor.execute(query, params)

        return cursor.fetchone()[0]

    except Exception as e:
        print(f"[DB ERROR] Failed to fetch get_countObjects_duplicate_backup: {e}")
        return []

def get_countObjects_dwarf(conn: sqlite3.Connection, dwarf_id=None, only_on_dwarf=None, only_on_backup=None, filter_object=None):
    try:
        cursor = conn.cursor()

        query = """
            SELECT COUNT(*)
            FROM DwarfEntry
            JOIN DwarfData ON DwarfEntry.dwarf_data_id = DwarfData.id
            JOIN AstroObject ON DwarfEntry.astro_object_id = AstroObject.id
            LEFT JOIN AstroObject AS AstroGroup ON DwarfEntry.astro_group_id = AstroGroup.id
        """
        conditions = []
        params = []

        if dwarf_id:  # not "(All Dwarfs)"
            conditions.append("DwarfEntry.dwarf_id = ?")
            params.append(dwarf_id)

            if only_on_dwarf and not only_on_backup:
                # Filter DwarfEntry to only those with session_dir not present in BackupEntry for same dwarf
                conditions.append("""
                    DwarfEntry.session_dir NOT IN (
                        SELECT session_dir FROM BackupEntry WHERE dwarf_id = ?
                    )
                """)
                params.append(dwarf_id)

            if only_on_backup and not only_on_dwarf:
                # Filter DwarfEntry to only those with session_dir present in BackupEntry for same dwarf
                conditions.append("""
                    DwarfEntry.session_dir IN (
                        SELECT session_dir FROM BackupEntry WHERE dwarf_id = ?
                    )
                """)
                params.append(dwarf_id)

        if filter_object:
            conditions.append(f"(LOWER({display_name_expr}) LIKE ? OR LOWER({group_display_expr}) LIKE ?)")
            params.append(f"%{filter_object.lower()}%")
            params.append(f"%{filter_object.lower()}%")
        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        cursor.execute(query, params)

        return cursor.fetchone()[0]

    except Exception as e:
        print(f"[DB ERROR] Failed to fetch get_countObjects_dwarf: {e}")
        return []

def get_ObjectSelect_backup(conn: sqlite3.Connection, object_id = None, dso_id = None, backup_drive_id=None, dwarf_id=None, only_on_dwarf=None, only_on_backup=None, is_group = False, filter_object=None, session_id = None):
    try:
        cursor = conn.cursor()

        query = f"""
            SELECT 
                DwarfData.id,
                DwarfData.file_path,
                DwarfData.exp_time,
                DwarfData.gain,
                DwarfData.ircut,
                DwarfData.shotsStacked,
                BackupDrive.location,
                BackupEntry.session_date,
                BackupEntry.session_dir,
                Dwarf.name,
                DwarfData.minTemp,
                DwarfData.maxTemp,
                BackupEntry.favorite,
                DwarfData.target,
                DwarfData.dec,
                DwarfData.ra,
                BackupEntry.astro_object_id,
                BackupEntry.astro_group_id,
                {display_name_expr} AS object_display_name,
                BackupEntry.backup_drive_id,
                BackupEntry.dwarf_id
            FROM BackupEntry
            JOIN DwarfData ON BackupEntry.dwarf_data_id = DwarfData.id
            JOIN BackupDrive ON BackupEntry.backup_drive_id = BackupDrive.id
            JOIN Dwarf ON BackupDrive.dwarf_id = Dwarf.id
            JOIN AstroObject ON BackupEntry.astro_object_id = AstroObject.id
            LEFT JOIN AstroObject AS AstroGroup ON BackupEntry.astro_group_id = AstroGroup.id
        """

        where_clauses = []
        params = []

        if object_id is not None:
            if not is_group :
                where_clauses.append("BackupEntry.astro_object_id = ?")
            else:
                where_clauses.append("BackupEntry.astro_group_id = ?")
            params.append(object_id)

        elif dso_id is not None:
            if not is_group :
                where_clauses.append("""
                    BackupEntry.astro_object_id IN (
                        SELECT id FROM AstroObject WHERE dso_id = ?
                    )
                """)
            else:
                where_clauses.append("""
                    BackupEntry.astro_group_id IN (
                        SELECT id FROM AstroObject WHERE dso_id = ?
                    )
                """)
            params.append(dso_id)

        if backup_drive_id:
            where_clauses.append("BackupEntry.backup_drive_id = ?")
            params.append(backup_drive_id)

        if dwarf_id:  # not "(All Dwarfs)"
            where_clauses.append("BackupEntry.dwarf_id = ?")
            params.append(dwarf_id)

            if only_on_dwarf and not only_on_backup:
                # Filter BackupEntry to only those with session_dir present in DwarfEntry for same dwarf
                where_clauses.append("""
                    BackupEntry.session_dir IN (
                        SELECT session_dir FROM DwarfEntry WHERE dwarf_id = ?
                    )
                """)
                params.append(dwarf_id)

            if only_on_backup and not only_on_dwarf:
                # Filter BackupEntry to only those with session_dir not present in DwarfEntry for same dwarf
                where_clauses.append("""
                    BackupEntry.session_dir NOT IN (
                        SELECT session_dir FROM DwarfEntry WHERE dwarf_id = ?
                    )
                """)
                params.append(dwarf_id)

        if filter_object:
            where_clauses.append(f"(LOWER(object_display_name) LIKE ? OR LOWER({group_display_expr}) LIKE ?)")
            params.append(f"%{filter_object.lower()}%")
            params.append(f"%{filter_object.lower()}%")

        if session_id:
            where_clauses.append("BackupEntry.id = ?")
            params.append(session_id)

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        query += " ORDER BY BackupEntry.session_date DESC"

        cursor.execute(query, params)

        return cursor.fetchall()

    except Exception as e:
        print(f"[DB ERROR] Failed to fetch get_ObjectSelect_backup: {e}")
        return []

def get_ObjectSelect_duplicate_backup(conn: sqlite3.Connection, object_id = None, dso_id = None, backup_drive_id=None, dwarf_id=None, only_on_dwarf=None, only_on_backup=None, is_group = False, filter_object=None, session_id = None):
    try:
        cursor = conn.cursor()

        query = f"""
            SELECT 
                DwarfData.id,
                DwarfData.file_path,
                DwarfData.exp_time,
                DwarfData.gain,
                DwarfData.ircut,
                DwarfData.shotsStacked,
                BackupDrive.location,
                BackupEntry.session_date,
                BackupEntry.session_dir,
                Dwarf.name,
                DwarfData.minTemp,
                DwarfData.maxTemp,
                BackupEntry.favorite,
                DwarfData.target,
                DwarfData.dec,
                DwarfData.ra,
                BackupEntry.astro_object_id,
                BackupEntry.astro_group_id,
                {display_name_expr} AS object_display_name,
                BackupEntry.backup_drive_id,
                BackupEntry.dwarf_id
            FROM BackupEntry
            JOIN DwarfData ON BackupEntry.dwarf_data_id = DwarfData.id
            JOIN BackupDrive ON BackupEntry.backup_drive_id = BackupDrive.id
            JOIN Dwarf ON BackupDrive.dwarf_id = Dwarf.id
            JOIN AstroObject ON BackupEntry.astro_object_id = AstroObject.id
            LEFT JOIN AstroObject AS AstroGroup ON BackupEntry.astro_group_id = AstroGroup.id
        """

        where_clauses = []
        params = []

        # Filter Duplicates Sessions
        where_clauses.append("""
            BackupEntry.session_dir IN (
                SELECT session_dir
                FROM BackupEntry
                GROUP BY session_dir
                HAVING COUNT(*) > 1
            ) 
        """)

        if object_id is not None:
            if not is_group :
                where_clauses.append("BackupEntry.astro_object_id = ?")
            else:
                where_clauses.append("BackupEntry.astro_group_id = ?")
            params.append(object_id)

        elif dso_id is not None:
            if not is_group :
                where_clauses.append("""
                    BackupEntry.astro_object_id IN (
                        SELECT id FROM AstroObject WHERE dso_id = ?
                    )
                """)
            else:
                where_clauses.append("""
                    BackupEntry.astro_group_id IN (
                        SELECT id FROM AstroObject WHERE dso_id = ?
                    )
                """)
            params.append(dso_id)

        if backup_drive_id:
            where_clauses.append("BackupEntry.backup_drive_id = ?")
            params.append(backup_drive_id)

        if dwarf_id:  # not "(All Dwarfs)"
            where_clauses.append("BackupEntry.dwarf_id = ?")
            params.append(dwarf_id)

            if only_on_dwarf and not only_on_backup:
                # Filter BackupEntry to only those with session_dir present in DwarfEntry for same dwarf
                where_clauses.append("""
                    BackupEntry.session_dir IN (
                        SELECT session_dir FROM DwarfEntry WHERE dwarf_id = ?
                    )
                """)
                params.append(dwarf_id)

            if only_on_backup and not only_on_dwarf:
                # Filter BackupEntry to only those with session_dir not present in DwarfEntry for same dwarf
                where_clauses.append("""
                    BackupEntry.session_dir NOT IN (
                        SELECT session_dir FROM DwarfEntry WHERE dwarf_id = ?
                    )
                """)
                params.append(dwarf_id)

        if filter_object:
            where_clauses.append(f"(LOWER(object_display_name) LIKE ? OR LOWER({group_display_expr}) LIKE ?)")
            params.append(f"%{filter_object.lower()}%")
            params.append(f"%{filter_object.lower()}%")

        if session_id:
            where_clauses.append("BackupEntry.id = ?")
            params.append(session_id)

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        query += " ORDER BY BackupEntry.session_date DESC"

        cursor.execute(query, params)

        return cursor.fetchall()

    except Exception as e:
        print(f"[DB ERROR] Failed to fetch get_ObjectSelect_duplicate_backup: {e}")
        return []

def get_ObjectSelect_dwarf(conn: sqlite3.Connection, object_id = None, dso_id = None, dwarf_id=None, only_on_dwarf=None, only_on_backup=None, is_group = False, filter_object=None, session_id = None):
    try:
        cursor = conn.cursor()

        query = f"""
            SELECT 
                DwarfData.id,
                DwarfData.file_path,
                DwarfData.exp_time,
                DwarfData.gain,
                DwarfData.ircut,
                DwarfData.shotsStacked,
                Dwarf.usb_astronomy_dir,
                DwarfEntry.session_date,
                DwarfEntry.session_dir,
                Dwarf.name,
                DwarfData.minTemp,
                DwarfData.maxTemp,
                DwarfEntry.favorite,
                DwarfData.target,
                DwarfData.dec,
                DwarfData.ra,
                DwarfEntry.astro_object_id,
                DwarfEntry.astro_group_id,
                {display_name_expr} AS object_display_name,
                Null,
                DwarfEntry.dwarf_id
            FROM DwarfEntry
            JOIN DwarfData ON DwarfEntry.dwarf_data_id = DwarfData.id
            JOIN Dwarf ON DwarfEntry.dwarf_id = Dwarf.id
            JOIN AstroObject ON DwarfEntry.astro_object_id = AstroObject.id
            LEFT JOIN AstroObject AS AstroGroup ON DwarfEntry.astro_group_id = AstroGroup.id
        """

        where_clauses = []
        params = []

        if object_id is not None:
            if not is_group :
                where_clauses.append("DwarfEntry.astro_object_id = ?")
            else:
                where_clauses.append("DwarfEntry.astro_group_id = ?")
            params.append(object_id)

        elif dso_id is not None:
            if not is_group :
                where_clauses.append("""
                    DwarfEntry.astro_object_id IN (
                        SELECT id FROM AstroObject WHERE dso_id = ?
                    )
                """)
            else:
                where_clauses.append("""
                    DwarfEntry.astro_group_id IN (
                        SELECT id FROM AstroObject WHERE dso_id = ?
                    )
                """)
            params.append(dso_id)

        if dwarf_id:  # not "(All Dwarfs)"
            where_clauses.append("DwarfEntry.dwarf_id = ?")
            params.append(dwarf_id)

            if only_on_dwarf and not only_on_backup:
                # Filter DwarfEntry to only those with session_dir not present in BackupEntry for same dwarf
                where_clauses.append("""
                    DwarfEntry.session_dir NOT IN (
                        SELECT session_dir FROM BackupEntry WHERE dwarf_id = ?
                    )
                """)
                params.append(dwarf_id)

            if only_on_backup and not only_on_dwarf:
                # Filter DwarfEntry to only those with session_dir present in BackupEntry for same dwarf
                where_clauses.append("""
                    DwarfEntry.session_dir IN (
                        SELECT session_dir FROM BackupEntry WHERE dwarf_id = ?
                    )
                """)
                params.append(dwarf_id)

        if filter_object:
            where_clauses.append(f"(LOWER(object_display_name) LIKE ? OR LOWER({group_display_expr}) LIKE ?)")
            params.append(f"%{filter_object.lower()}%")
            params.append(f"%{filter_object.lower()}%")

        if session_id:
            where_clauses.append("DwarfEntry.id = ?")
            params.append(session_id)

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        query += " ORDER BY DwarfEntry.session_date DESC"

        cursor.execute(query, params)

        return cursor.fetchall()

    except Exception as e:
        print(f"[DB ERROR] Failed to fetch get_ObjectSelect_dwarf: {e}")
        return []


##############################
# ManualSession query functions
##############################

def get_Objects_manual(conn: sqlite3.Connection, backup_drive_id=None, dwarf_id=None, filter_object=None):
    """
    Return the distinct list of AstroObjects that have at least one ManualSessionEntry.
    Mirrors the signature of get_Objects_backup / get_Objects_dwarf so ManualExplore
    can call it the same way.

    Result columns (per row):
        [0] AstroObject.id
        [1] display_name  (description + name, or name alone)
        [2] AstroObject.dso_id
        [3] AstroObject.is_group
    """
    try:
        cursor = conn.cursor()

        query = f"""
            SELECT DISTINCT
                AstroObject.id,
                {display_name_expr} AS display_name,
                AstroObject.dso_id,
                AstroObject.is_group
            FROM AstroObject
            JOIN ManualSessionEntry
                ON (
                    -- Prefer the group label when the object belongs to a named group
                    (AstroObject.id = ManualSessionEntry.astro_object_id AND ManualSessionEntry.astro_group_id IS NULL)
                    OR
                    (AstroObject.id = ManualSessionEntry.astro_object_id AND ManualSessionEntry.astro_group_id IS NOT NULL AND AstroObject.description != '')
                    OR
                    (AstroObject.id = ManualSessionEntry.astro_group_id  AND ManualSessionEntry.astro_object_id IS NOT NULL AND AstroObject.description = '')
                )
            JOIN ManualSession ON ManualSessionEntry.manual_session_id = ManualSession.id
        """
        conditions = []
        params = []

        if backup_drive_id:
            conditions.append("ManualSessionEntry.backup_drive_id = ?")
            params.append(backup_drive_id)

        if dwarf_id:
            conditions.append("ManualSessionEntry.dwarf_id = ?")
            params.append(dwarf_id)

        if filter_object:
            conditions.append("LOWER(display_name) LIKE ?")
            params.append(f"%{filter_object.lower()}%")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        order_case_sql = generate_order_case("display_name", DEFAULT_GROUP_NAMES)
        query += f"""
            ORDER BY
                {order_case_sql},
                display_name
        """

        cursor.execute(query, params)
        return cursor.fetchall()

    except Exception as e:
        print(f"[DB ERROR] Failed to fetch get_Objects_manual: {e}")
        return []


def get_countObjects_manual(conn: sqlite3.Connection, backup_drive_id=None, dwarf_id=None, filter_object=None):
    """
    Return the total number of ManualSessionEntry rows matching the given filters.
    Used to populate the 'Total matching sessions' label in ManualExplore.
    """
    try:
        cursor = conn.cursor()

        query = f"""
            SELECT COUNT(*)
            FROM ManualSessionEntry
            JOIN ManualSession ON ManualSessionEntry.manual_session_id = ManualSession.id
            JOIN AstroObject ON ManualSessionEntry.astro_object_id = AstroObject.id
            LEFT JOIN AstroObject AS AstroGroup ON ManualSessionEntry.astro_group_id = AstroGroup.id
        """
        conditions = []
        params = []

        if backup_drive_id:
            conditions.append("ManualSessionEntry.backup_drive_id = ?")
            params.append(backup_drive_id)

        if dwarf_id:
            conditions.append("ManualSessionEntry.dwarf_id = ?")
            params.append(dwarf_id)

        if filter_object:
            conditions.append(f"(LOWER({display_name_expr}) LIKE ? OR LOWER({group_display_expr}) LIKE ?)")
            params.append(f"%{filter_object.lower()}%")
            params.append(f"%{filter_object.lower()}%")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        cursor.execute(query, params)
        return cursor.fetchone()[0]

    except Exception as e:
        print(f"[DB ERROR] Failed to fetch get_countObjects_manual: {e}")
        return 0


def get_ObjectSelect_manual(conn: sqlite3.Connection, object_id=None, dso_id=None,
                             backup_drive_id=None, dwarf_id=None,
                             is_group=False, filter_object=None, session_id=None):
    """
    Return all ManualSession rows for a given AstroObject (or group), with every
    piece of data the ManualExplore detail panel needs.

    Result columns (per row) — keep this index table in sync with ManualExploreApp:
        [0]  ManualSession.id
        [1]  ManualSession.session_name        <- base session name
        [2]  ManualSession.session_tag         <- optional tag / sub-folder ('' when unused)
        [3]  ManualSession.session_type        <- 'Stellar Studio' | 'Manual' | ...
        [4]  ManualSession.jpeg_path
        [5]  ManualSession.thumbnail_path
        [6]  ManualSession.description
        [7]  ManualSession.dec
        [8]  ManualSession.ra
        [9]  ManualSession.exp_time
        [10] ManualSession.ircut
        [11] ManualSession.maxTemp
        [12] ManualSession.minTemp
        [13] ManualSession.stacked_png_path
        [14] ManualSession.stacked_fits_path
        [15] ManualSessionEntry.session_date
        [16] ManualSessionEntry.session_dir    <- physical base folder on backup drive
        [17] ManualSessionEntry.favorite
        [18] ManualSessionEntry.astro_object_id
        [19] ManualSessionEntry.astro_group_id
        [20] display_name                      <- AstroObject display name
        [21] ManualSessionEntry.backup_drive_id
        [22] ManualSessionEntry.dwarf_id
        [23] ManualSessionEntry.backup_entry_id <- FK to BackupEntry (may be NULL)
        [24] ManualSessionEntry.id              <- own PK, used for delete / favorite toggle
        [25] Dwarf.name                         <- may be NULL if dwarf not set
        [26] BackupDrive.name                   <- may be NULL if drive not set
    """
    try:
        cursor = conn.cursor()

        query = f"""
            SELECT
                ManualSession.id,
                ManualSession.session_name,
                ManualSession.session_tag,
                ManualSession.session_type,
                ManualSession.jpeg_path,
                ManualSession.thumbnail_path,
                ManualSession.description,
                ManualSession.dec,
                ManualSession.ra,
                ManualSession.exp_time,
                ManualSession.ircut,
                ManualSession.maxTemp,
                ManualSession.minTemp,
                ManualSession.stacked_png_path,
                ManualSession.stacked_fits_path,
                ManualSessionEntry.session_date,
                ManualSessionEntry.session_dir,
                ManualSessionEntry.favorite,
                ManualSessionEntry.astro_object_id,
                ManualSessionEntry.astro_group_id,
                {display_name_expr} AS display_name,
                ManualSessionEntry.backup_drive_id,
                ManualSessionEntry.dwarf_id,
                ManualSessionEntry.backup_entry_id,
                ManualSessionEntry.id,
                Dwarf.name,
                BackupDrive.name
            FROM ManualSessionEntry
            JOIN ManualSession ON ManualSessionEntry.manual_session_id = ManualSession.id
            JOIN AstroObject   ON ManualSessionEntry.astro_object_id  = AstroObject.id
            LEFT JOIN AstroObject AS AstroGroup ON ManualSessionEntry.astro_group_id = AstroGroup.id
            LEFT JOIN Dwarf       ON ManualSessionEntry.dwarf_id       = Dwarf.id
            LEFT JOIN BackupDrive ON ManualSessionEntry.backup_drive_id = BackupDrive.id
        """

        where_clauses = []
        params = []

        # --- Object / group filter ---
        if object_id is not None:
            if not is_group:
                where_clauses.append("ManualSessionEntry.astro_object_id = ?")
            else:
                where_clauses.append("ManualSessionEntry.astro_group_id = ?")
            params.append(object_id)

        elif dso_id is not None:
            # Match all AstroObjects sharing the same DSO catalogue entry
            if not is_group:
                where_clauses.append("""
                    ManualSessionEntry.astro_object_id IN (
                        SELECT id FROM AstroObject WHERE dso_id = ?
                    )
                """)
            else:
                where_clauses.append("""
                    ManualSessionEntry.astro_group_id IN (
                        SELECT id FROM AstroObject WHERE dso_id = ?
                    )
                """)
            params.append(dso_id)

        # --- Optional drive / dwarf filters ---
        if backup_drive_id:
            where_clauses.append("ManualSessionEntry.backup_drive_id = ?")
            params.append(backup_drive_id)

        if dwarf_id:
            where_clauses.append("ManualSessionEntry.dwarf_id = ?")
            params.append(dwarf_id)

        # --- Text search across display_name and group name ---
        if filter_object:
            where_clauses.append(f"(LOWER(display_name) LIKE ? OR LOWER({group_display_expr}) LIKE ?)")
            params.append(f"%{filter_object.lower()}%")
            params.append(f"%{filter_object.lower()}%")

        # --- Direct session lookup (e.g. auto-selection from another page) ---
        if session_id:
            where_clauses.append("ManualSessionEntry.id = ?")
            params.append(session_id)

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        query += " ORDER BY ManualSessionEntry.session_date DESC"

        cursor.execute(query, params)
        return cursor.fetchall()

    except Exception as e:
        print(f"[DB ERROR] Failed to fetch get_ObjectSelect_manual: {e}")
        return []


def toggle_favorite_manual(conn: sqlite3.Connection, entry_id: int) -> int:
    """
    Toggle the favorite flag on a ManualSessionEntry row (identified by its own PK).
    Returns the new value (0 or 1), or 0 on error.
    """
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE ManualSessionEntry SET favorite = NOT favorite WHERE id = ?",
            (entry_id,)
        )
        commit_db(conn)
        cursor.execute("SELECT favorite FROM ManualSessionEntry WHERE id = ?", (entry_id,))
        row = cursor.fetchone()
        return row[0] if row else 0

    except Exception as e:
        print(f"[DB ERROR] Failed to toggle_favorite_manual for entry_id={entry_id}: {e}")
        return 0


def get_ManualSession_by_entry_id(conn: sqlite3.Connection, entry_id: int):
    """
    Load a single ManualSession + ManualSessionEntry row by ManualSessionEntry.id.
    Used by AddManualSession when opened in edit mode (ManualEntryId URL parameter).

    Returns the same column layout as get_ObjectSelect_manual (26 columns), or [].
    """
    return get_ObjectSelect_manual(conn, session_id=entry_id)


def get_ManualSession_by_backup_entry_id(conn: sqlite3.Connection, backup_drive_id: int, dwarf_id: int, dwarf_data_id: int):
    """
    Return ALL ManualSessionEntry rows linked to the BackupEntry identified by
    (backup_drive_id, dwarf_id, dwarf_data_id).

    A single backup session can have multiple linked manual imports (e.g. the same
    target imported at different times or with different session types), so this
    intentionally returns all of them — not just the first one.

    Each row uses the same 26-column layout as get_ObjectSelect_manual.
    Returns [] if nothing is linked or on error.
    """
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT mse.id
            FROM ManualSessionEntry mse
            JOIN BackupEntry be ON be.id = mse.backup_entry_id
            WHERE mse.backup_drive_id = ?
              AND mse.dwarf_id = ?
              AND be.dwarf_data_id = ?
            ORDER BY mse.session_date DESC
        """, (backup_drive_id, dwarf_id, dwarf_data_id))
        entry_ids = [row[0] for row in cursor.fetchall()]
        if not entry_ids:
            return []
        # Build the full rows for each ManualSessionEntry found
        rows = []
        for eid in entry_ids:
            result = get_ObjectSelect_manual(conn, session_id=eid)
            if result:
                rows.append(result[0])
        return rows
    except Exception as e:
        print(f"[DB ERROR] Failed to fetch get_ManualSession_by_backup_entry_id: {e}")
        return []


#####################
# Favorite functions
#####################

def toggle_favorite(conn: sqlite3.Connection, entry_id, mode):
    try:
        cursor = conn.cursor()
        if mode=="backup":
            cursor.execute("UPDATE BackupEntry SET favorite = NOT favorite WHERE BackupEntry.dwarf_data_id = (SELECT id FROM DwarfData WHERE id = ?)", (entry_id,))
        else:
            cursor.execute("UPDATE DwarfEntry SET favorite = NOT favorite WHERE DwarfEntry.dwarf_data_id = (SELECT id FROM DwarfData WHERE id = ?)", (entry_id,))
        commit_db(conn)

        if mode=="backup":
            cursor.execute("SELECT favorite FROM BackupEntry WHERE BackupEntry.dwarf_data_id = (SELECT id FROM DwarfData WHERE id = ?)", (entry_id,))
        else:
            cursor.execute("SELECT favorite FROM DwarfEntry WHERE DwarfEntry.dwarf_data_id = (SELECT id FROM DwarfData WHERE id = ?)", (entry_id,))

        return cursor.fetchone()[0]

    except Exception as e:
        print(f"[DB ERROR] Failed to toggle_favorite: {e}")
        return 0

def get_backup_favorites(conn: sqlite3.Connection):
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                BackupEntry.id,
                BackupEntry.session_date,
                AstroObject.name AS object_name,
                DwarfData.file_path,
                Dwarf.name AS dwarf_name,
                BackupDrive.name AS backup_drive_name,
                BackupDrive.location,
                AstroObject.description AS description
            FROM BackupEntry
            LEFT JOIN AstroObject ON BackupEntry.astro_object_id = AstroObject.id
            LEFT JOIN DwarfData ON BackupEntry.dwarf_data_id = DwarfData.id
            LEFT JOIN Dwarf ON BackupEntry.dwarf_id = Dwarf.id
            LEFT JOIN BackupDrive ON BackupEntry.backup_drive_id = BackupDrive.id
            WHERE BackupEntry.favorite = TRUE
            ORDER BY BackupEntry.id DESC
        """)
        rows = cursor.fetchall()

        return rows
    except Exception as e:
        print(f"[DB ERROR] Failed to fetch backup favorites: {e}")
        return []

def get_dwarf_favorites(conn: sqlite3.Connection):
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                DwarfEntry.id,
                DwarfEntry.session_date,
                AstroObject.name AS object_name,
                DwarfData.file_path,
                Dwarf.name AS dwarf_name,
                BackupDrive.name AS backup_drive_name,
                BackupDrive.location,
                AstroObject.description AS description
            FROM DwarfEntry
            LEFT JOIN AstroObject ON DwarfEntry.astro_object_id = AstroObject.id
            LEFT JOIN DwarfData ON DwarfEntry.dwarf_data_id = DwarfData.id
            LEFT JOIN Dwarf ON DwarfEntry.dwarf_id = Dwarf.id
            LEFT JOIN BackupDrive ON DwarfEntry.backup_drive_id = BackupDrive.id
            WHERE DwarfEntry.favorite = TRUE
            ORDER BY DwarfEntry.id DESC
        """)
        rows = cursor.fetchall()

        return rows
    except Exception as e:
        print(f"[DB ERROR] Failed to fetch dwarf favorites: {e}")
        return []

def get_manual_favorites(conn: sqlite3.Connection):
    """
    Return favorite ManualSessionEntry rows.
    Columns:
        [0] ManualSessionEntry.id
        [1] ManualSessionEntry.session_date
        [2] ManualSession.session_name      (object name)
        [3] ManualSession.jpeg_path
        [4] Dwarf.name
        [5] BackupDrive.name
        [6] BackupDrive.location
        [7] ManualSession.description
        [8] ManualSessionEntry.session_dir
        [9] ManualSession.session_type
    """
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                mse.id,
                mse.session_date,
                ms.session_name,
                COALESCE(ms.jpeg_path, ms.stacked_png_path) AS jpeg_path,
                d.name   AS dwarf_name,
                bd.name  AS backup_drive_name,
                bd.location,
                ms.description,
                mse.session_dir,
                ms.session_type
            FROM ManualSessionEntry mse
            JOIN ManualSession ms  ON mse.manual_session_id = ms.id
            LEFT JOIN BackupDrive bd ON mse.backup_drive_id = bd.id
            LEFT JOIN Dwarf d        ON mse.dwarf_id        = d.id
            WHERE mse.favorite = 1
            ORDER BY mse.session_date DESC
        """)
        return cursor.fetchall()
    except Exception as e:
        print(f"[DB ERROR] Failed to fetch manual favorites: {e}")
        return []


#########################
# Related data functions
#########################

def has_related_dwarf_entries(conn: sqlite3.Connection, dwarf_id: int) -> bool:
    try:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT 1 FROM DwarfEntry WHERE dwarf_id = ? LIMIT 1",
            (dwarf_id,)
        )
        if cursor.fetchone():
            return True

        cursor.execute(
            "SELECT 1 FROM BackupDrive WHERE dwarf_id = ? LIMIT 1",
            (dwarf_id,)
        )
        return cursor.fetchone() is not None

    except Exception as e:
        print(f"[DB ERROR] Failed to check related entries for dwarf_id {dwarf_id}: {e}")
        return True  # For Security

def has_related_backup_entries(conn: sqlite3.Connection, backup_drive_id: int):
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM BackupEntry WHERE backup_drive_id = ? LIMIT 1",
            (backup_drive_id,)
        )
        return cursor.fetchone() is not None

    except Exception as e:
        print(f"[DB ERROR] Failed to verify has related backup entries: {e}")
        return True  # For Security

def has_related_manual_entries(conn: sqlite3.Connection, backup_drive_id: int):
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM ManualSessionEntry WHERE backup_drive_id = ? LIMIT 1",
            (backup_drive_id,)
        )
        return cursor.fetchone() is not None

    except Exception as e:
        print(f"[DB ERROR] Failed to verify has related manual entries: {e}")
        return True  # For Security

def has_related_manual_sessions(conn: sqlite3.Connection, backup_drive_id: int,  dwarf_id: int, dwarf_data_id: int) -> bool:
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 1
                FROM ManualSessionEntry mse
                JOIN BackupEntry be ON be.id = mse.backup_entry_id
                WHERE mse.backup_drive_id = ?
                  AND mse.dwarf_id = ?
                  AND be.dwarf_data_id = ?
                LIMIT 1
            """, (backup_drive_id, dwarf_id, dwarf_data_id)
        )
        return cursor.fetchone() is not None

    except Exception as e:
        print(f"[DB ERROR] Failed to verify has related manual sessions: {e}")
        return False


#########################
# Related data functions
#########################

def delete_manual_session_entry(conn: sqlite3.Connection, entry_id: int) -> bool:
    """
    Delete a single ManualSessionEntry row and, if the parent ManualSession has no
    remaining entries, delete the ManualSession record as well.

    Args:
        conn:     active DB connection
        entry_id: ManualSessionEntry.id (the PK of the entry row, NOT ManualSession.id)

    Returns True on success, False on error.
    """
    try:
        cursor = conn.cursor()

        # Retrieve the parent manual_session_id before deleting the entry
        cursor.execute(
            "SELECT manual_session_id FROM ManualSessionEntry WHERE id = ?",
            (entry_id,)
        )
        row = cursor.fetchone()
        if not row:
            print(f"[WARN] ManualSessionEntry id={entry_id} not found.")
            return False

        manual_session_id = row[0]

        # Delete the entry row
        cursor.execute("DELETE FROM ManualSessionEntry WHERE id = ?", (entry_id,))

        # If the parent ManualSession has no more entries, delete it too
        cursor.execute(
            "SELECT COUNT(*) FROM ManualSessionEntry WHERE manual_session_id = ?",
            (manual_session_id,)
        )
        remaining = cursor.fetchone()[0]
        if remaining == 0:
            cursor.execute("DELETE FROM ManualSession WHERE id = ?", (manual_session_id,))
            print(f"[INFO] ManualSession id={manual_session_id} deleted (no more entries).")

        commit_db(conn)
        return True

    except Exception as e:
        print(f"[DB ERROR] Failed to delete_manual_session_entry id={entry_id}: {e}")
        conn.rollback()
        return False


def delete_manual_entries(conn: sqlite3.Connection, backup_drive_id=None):
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        cursor = conn.cursor()

        # Step 1: Collect all ManualSession IDs referenced by entries on this drive
        cursor.execute("""
            SELECT manual_session_id FROM ManualSessionEntry WHERE backup_drive_id = ?
        """, (backup_drive_id,))
        manual_session_ids = [row[0] for row in cursor.fetchall() if row[0] is not None]

        # Step 2: Delete the ManualSessionEntry rows for this backup drive
        cursor.execute(
            "DELETE FROM ManualSessionEntry WHERE backup_drive_id = ?",
            (backup_drive_id,)
        )

        # Step 3: For each parent ManualSession, delete it only if no other
        #         ManualSessionEntry still references it (from another backup drive)
        for manual_session_id in manual_session_ids:
            cursor.execute("""
                SELECT COUNT(*) FROM ManualSessionEntry WHERE manual_session_id = ?
            """, (manual_session_id,))
            count = cursor.fetchone()[0]

            if count == 0:
                cursor.execute(
                    "DELETE FROM ManualSession WHERE id = ?",
                    (manual_session_id,)
                )

        commit_db(conn)
        print(
            f"Deleted {len(manual_session_ids)} ManualSessionEntry rows and "
            f"orphaned ManualSession records for backup_drive_id={backup_drive_id}."
        )
        return True

    except Exception as e:
        print(f"[DB ERROR] Failed to delete manual entries for backup_drive_id={backup_drive_id}: {e}")
        return False
        
def delete_backup_entries_and_dwarf_data(conn: sqlite3.Connection, backup_drive_id=None):
    try:
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
                cursor.execute("UPDATE BackupDrive SET last_backup_scan_date=NULL WHERE id=?", (backup_drive_id,))

        commit_db(conn)
        print(f"Deleted {len(dwarf_data_ids)} DwarfData entries (if not reused) and all related BackupEntry rows.")

    except Exception as e:
        print(f"[DB ERROR] Failed to delete backup entries and dwarf data for {backup_drive_id}: {e}")
        return False

def delete_dwarf_entries_and_dwarf_data(conn: sqlite3.Connection, dwarf_id=None):
    try:
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
                cursor.execute("UPDATE Dwarf SET last_scan_date=NULL WHERE id=?", (dwarf_id,))

        commit_db(conn)
        print(f"Deleted {len(dwarf_data_ids)} DwarfData entries (if not reused) and all related DwarfEntry rows.")

    except Exception as e:
        print(f"[DB ERROR] Failed to delete dwarf entries and dwarf data for {dwarf_id}: {e}")
        return False

def delete_notpresent_backup_entries_and_dwarf_data(conn: sqlite3.Connection, backup_drive_id: int,  valid_ids: list[int]):
    try:
        conn.execute("PRAGMA foreign_keys = ON")  # Enforce FK rules
        cursor = conn.cursor()

        if valid_ids:
            placeholders = ",".join("?" for _ in valid_ids)

            # Step 1: Get orphaned dwarf_data_id values for this backup_drive_id (not in valid_ids)
            cursor.execute(f"""
                SELECT dwarf_data_id FROM BackupEntry
                WHERE backup_drive_id = ? AND dwarf_data_id IS NOT NULL AND dwarf_data_id NOT IN ({placeholders})
            """, (backup_drive_id, *valid_ids))
            dwarf_data_ids = [row[0] for row in cursor.fetchall()]

            # Step 2: Delete obsolete BackupEntry rows for this backup_drive_id
            cursor.execute(f"""
                DELETE FROM BackupEntry
                WHERE backup_drive_id = ? AND dwarf_data_id IS NOT NULL AND dwarf_data_id NOT IN ({placeholders})
            """, (backup_drive_id, *valid_ids))

            # Step 3: Delete orphaned DwarfData rows (only if not referenced anymore)
            for dwarf_data_id in dwarf_data_ids:
                cursor.execute("""
                    SELECT COUNT(*) FROM BackupEntry WHERE dwarf_data_id = ?
                """, (dwarf_data_id,))
                count = cursor.fetchone()[0]
                print(f" COUNT(*) FROM BackupEntry {count}")
                if count == 0:
                    cursor.execute("DELETE FROM DwarfData WHERE id = ?", (dwarf_data_id,))

            commit_db(conn)
            print(f"Deleted {len(dwarf_data_ids)} unused DwarfData entries and obsolete BackupEntry rows.")
            return len(dwarf_data_ids)

        else:
            print(f"no Deletion made, because valid_ids has not be set for {backup_drive_id}!")
            return False

    except Exception as e:
        print(f"[DB ERROR] Failed to delete entries for backup_drive_id={backup_drive_id}: {e}")
        return False

def delete_backup_entry_and_dwarf_data(conn: sqlite3.Connection, backup_drive_id: int,  dwarf_id: int, dwarf_data_id: int) -> bool:
    try:
        cursor = conn.cursor()

        if dwarf_data_id:
            # Delete the backup entry directly
            cursor.execute("""
                DELETE FROM BackupEntry
                WHERE backup_drive_id = ?
                  AND dwarf_id = ?
                  AND dwarf_data_id = ?
            """, (backup_drive_id, dwarf_id, dwarf_data_id))

            if cursor.rowcount > 0:
                # Check if dwarf_data_id is still referenced
                cursor.execute("SELECT COUNT(*) FROM BackupEntry WHERE dwarf_data_id = ?", (dwarf_data_id,))
                count = cursor.fetchone()[0]
                print(f"[DEBUG] Remaining references to dwarf_data_id={dwarf_data_id}: {count}")

                if count == 0:
                    cursor.execute("DELETE FROM DwarfData WHERE id = ?", (dwarf_data_id,))

                conn.commit()
                return True

        return False

    except Exception as e:
        conn.rollback()
        print(f"[DB ERROR] Failed to delete entries for backup_drive_id={backup_drive_id}: {e}")
        return False

def delete_notpresent_dwarf_entries_and_dwarf_data(conn: sqlite3.Connection, dwarf_id: int, valid_ids: list[int]):
    try:
        conn.execute("PRAGMA foreign_keys = ON")  # Enforce FK rules
        cursor = conn.cursor()

        if valid_ids:
            placeholders = ",".join("?" for _ in valid_ids)

            # Step 1: Get orphaned dwarf_data_id values for this dwarf_id (not in valid_ids)
            cursor.execute(f"""
                SELECT dwarf_data_id FROM DwarfEntry
                WHERE dwarf_id = ? AND dwarf_data_id IS NOT NULL AND dwarf_data_id NOT IN ({placeholders})
            """, (dwarf_id, *valid_ids))
            dwarf_data_ids = [row[0] for row in cursor.fetchall()]

            # Step 2: Delete obsolete DwarfEntry rows for this dwarf_id
            cursor.execute(f"""
                DELETE FROM DwarfEntry
                WHERE dwarf_id = ? AND dwarf_data_id IS NOT NULL AND dwarf_data_id NOT IN ({placeholders})
            """, (dwarf_id, *valid_ids))

            # Step 3: Delete orphaned DwarfData rows (only if not referenced anymore)
            for dwarf_data_id in dwarf_data_ids:
                cursor.execute("""
                    SELECT COUNT(*) FROM DwarfEntry WHERE dwarf_data_id = ?
                """, (dwarf_data_id,))
                count = cursor.fetchone()[0]

                if count == 0:
                    cursor.execute("DELETE FROM DwarfData WHERE id = ?", (dwarf_data_id,))

            commit_db(conn)
            print(f"Deleted {len(dwarf_data_ids)} unused DwarfData entries and obsolete DwarfEntry rows.")
            return len(dwarf_data_ids)

        else:
            print(f"no Deletion made, because valid_ids has not be set for {dwarf_id}!")
            return False
            
    except Exception as e:
        print(f"[DB ERROR] Failed to delete entries for dwarf_id={dwarf_id}: {e}")
        return False

#########################
# Session data functions
#########################

def get_sessions_backup(conn: sqlite3.Connection, backup_drive_id=None, dwarf_id=None, session_dir=None, session_id=None):
    try:
        cursor = conn.cursor()

        query = """
            SELECT DISTINCT 
                BackupEntry.id, 
                BackupEntry.session_dir, 
                BackupEntry.session_date, 
                BackupEntry.astro_object_id, 
                BackupEntry.astro_group_id,
                DwarfData.stacked_fits_path,
                DwarfData.file_path
            FROM BackupEntry
            JOIN BackupDrive ON BackupEntry.backup_drive_id = BackupDrive.id
            JOIN DwarfData ON BackupEntry.dwarf_data_id = DwarfData.id
        """
        conditions = []
        params = []

        if backup_drive_id:
            conditions.append("BackupEntry.backup_drive_id = ?")
            params.append(backup_drive_id)

        if dwarf_id:  # not "(All Dwarfs)"
            conditions.append("BackupEntry.dwarf_id = ?")
            params.append(dwarf_id)

        if session_dir:
            conditions.append("BackupEntry.session_dir = ?")
            params.append(session_dir)

        if session_id:
            conditions.append("BackupEntry.id = ?")
            params.append(session_id)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += f"""
            ORDER BY BackupEntry.session_date DESC
        """

        cursor.execute(query, params)

        return cursor.fetchall()

    except Exception as e:
        print(f"[DB ERROR] Failed to fetch get_sessions_backup: {e}")
        return []

def get_session_backup_details(conn: sqlite3.Connection, backupEntryId = None):
    try:
        cursor = conn.cursor()

        query = """
            SELECT 
                DwarfData.id,
                DwarfData.file_path,
                DwarfData.exp_time,
                DwarfData.gain,
                DwarfData.ircut,
                DwarfData.shotsStacked,
                BackupDrive.location,
                BackupEntry.session_date,
                BackupEntry.session_dir,
                Dwarf.name,
                DwarfData.minTemp,
                DwarfData.maxTemp,
                BackupEntry.favorite,
                DwarfData.target,
                DwarfData.dec,
                DwarfData.ra,
                BackupEntry.astro_object_id,
                BackupEntry.astro_group_id,
                CASE 
                    WHEN AstroObject.description IS NOT NULL AND TRIM(AstroObject.description) != '' 
                    THEN AstroObject.description || ' [' || AstroObject.name || ']' 
                    ELSE AstroObject.name 
                END AS object_display_name,
                BackupEntry.backup_drive_id,
                BackupEntry.dwarf_id
            FROM BackupEntry
            JOIN DwarfData ON BackupEntry.dwarf_data_id = DwarfData.id
            JOIN BackupDrive ON BackupEntry.backup_drive_id = BackupDrive.id
            JOIN Dwarf ON BackupDrive.dwarf_id = Dwarf.id
            JOIN AstroObject ON BackupEntry.astro_object_id = AstroObject.id
        """

        where_clauses = []
        params = []

        if backupEntryId is not None:
            where_clauses.append("BackupEntry.id = ?")
            params.append(backupEntryId)

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        cursor.execute(query, params)

        return cursor.fetchall()

    except Exception as e:
        print(f"[DB ERROR] Failed to fetch get_session_backup_details: {e}")
        return []

def get_sessions_dwarf(conn: sqlite3.Connection, dwarf_id=None, session_dir=None):
    try:
        cursor = conn.cursor()

        query = """
            SELECT DISTINCT 
                DwarfEntry.id, 
                DwarfEntry.session_dir, 
                DwarfEntry.session_date, 
                DwarfEntry.astro_object_id, 
                DwarfEntry.astro_group_id,
                DwarfData.stacked_fits_path
            FROM DwarfEntry
            JOIN Dwarf ON DwarfEntry.dwarf_id = Dwarf.id
            JOIN DwarfData ON DwarfEntry.dwarf_data_id = DwarfData.id
        """
        conditions = []
        params = []

        if dwarf_id:  # not "(All Dwarfs)"
            conditions.append("DwarfEntry.dwarf_id = ?")
            params.append(dwarf_id)

        if session_dir:
            conditions.append("DwarfEntry.session_dir = ?")
            params.append(session_dir)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += f"""
            ORDER BY DwarfEntry.session_date DESC
        """

        cursor.execute(query, params)

        return cursor.fetchall()

    except Exception as e:
        print(f"[DB ERROR] Failed to fetch get_sessions_dwarf: {e}")
        return []

def get_session_dwarf_details(conn: sqlite3.Connection, dwarfEntryId = None):
    try:
        cursor = conn.cursor()

        query = """
            SELECT 
                DwarfData.id,
                DwarfData.file_path,
                DwarfData.exp_time,
                DwarfData.gain,
                DwarfData.ircut,
                DwarfData.shotsStacked,
                Dwarf.usb_astronomy_dir,
                DwarfEntry.session_date,
                DwarfEntry.session_dir,
                Dwarf.name,
                DwarfData.minTemp,
                DwarfData.maxTemp,
                DwarfEntry.favorite,
                DwarfData.target,
                DwarfData.dec,
                DwarfData.ra,
                DwarfEntry.astro_object_id,
                DwarfEntry.astro_group_id,
                CASE 
                    WHEN AstroObject.description IS NOT NULL AND TRIM(AstroObject.description) != '' 
                    THEN AstroObject.description || ' [' || AstroObject.name || ']' 
                    ELSE AstroObject.name 
                END AS object_display_name,
                DwarfEntry.dwarf_id
            FROM DwarfEntry
            JOIN DwarfData ON DwarfEntry.dwarf_data_id = DwarfData.id
            JOIN Dwarf ON DwarfEntry.dwarf_id = Dwarf.id
            JOIN AstroObject ON DwarfEntry.astro_object_id = AstroObject.id
        """

        where_clauses = []
        params = []

        if dwarfEntryId is not None:
            where_clauses.append("DwarfEntry.id = ?")
            params.append(dwarfEntryId)

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        cursor.execute(query, params)

        return cursor.fetchall()

    except Exception as e:
        print(f"[DB ERROR] Failed to fetch get_session_dwarf_details: {e}")
        return []

def is_session_backed_up(conn: sqlite3.Connection, session_dir=None):
    try:
        if session_dir:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM BackupEntry WHERE session_dir = ? LIMIT 1",
               (session_dir,)
            )
            return cursor.fetchone() is not None
        return None

    except Exception as e:
        print(f"[DB ERROR] Failed to verify is session backed up for {session_dir}: {e}")
        return None

def get_session_present_in_Dwarf(conn: sqlite3.Connection, session_dir=None):
    try:
        if session_dir:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT Dwarf.id, Dwarf.name, Dwarf.usb_astronomy_dir, DwarfData.file_path
                FROM DwarfEntry
                JOIN Dwarf ON DwarfEntry.dwarf_id = Dwarf.id
                JOIN DwarfData ON DwarfEntry.dwarf_data_id = DwarfData.id
                WHERE DwarfEntry.session_dir = ?
                LIMIT 1
            """, (session_dir,))
            result = cursor.fetchone()
            return result

        return []

    except Exception as e:
        print(f"[DB ERROR] Failed to get session present in Dwarf for {session_dir}: {e}")
        return []

def get_session_present_in_backupDrive(conn: sqlite3.Connection, session_dir=None):
    try:
        if session_dir:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT BackupDrive.id, BackupDrive.name, BackupDrive.location, BackupDrive.astronomy_dir, DwarfData.file_path
                FROM BackupEntry
                JOIN BackupDrive ON BackupEntry.backup_drive_id = BackupDrive.id
                JOIN DwarfData ON BackupEntry.dwarf_data_id = DwarfData.id
                WHERE BackupEntry.session_dir = ?
                LIMIT 1
            """, (session_dir,))
            result = cursor.fetchone()
            return result

        return []

    except Exception as e:
        print(f"[DB ERROR] Failed to get session present in backupDrive for {session_dir}: {e}")
        return []

########################
# Insert data functions
########################

def insert_DwarfData(conn: sqlite3.Connection, file_path, mtime, thumbnail_path, file_size,
        dec, ra, target, binning, format, exp_time, gain, shotsToTake, shotsTaken,
        shotsStacked, ircut, maxTemp, minTemp, width, height, media_type, stacked_path, stacked_md5):
    try:

        # Try to fetch existing ID first
        row = conn.execute("SELECT id FROM DwarfData WHERE file_path = ?", (file_path,)).fetchone()
        exist_id = row[0] if row else None

        cursor = conn.execute("""
            INSERT INTO DwarfData (
                file_path, modification_time, thumbnail_path, file_size,
                dec, ra, target, binning, format, exp_time, gain,
                shotsToTake, shotsTaken, shotsStacked, ircut, maxTemp, minTemp,
                width, height, media_type, stacked_fits_path, stacked_fits_md5
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_path) DO UPDATE SET
                modification_time = excluded.modification_time,
                thumbnail_path = excluded.thumbnail_path,
                file_size = excluded.file_size,
                dec = excluded.dec,
                ra = excluded.ra,
                target = excluded.target,
                binning = excluded.binning,
                format = excluded.format,
                exp_time = excluded.exp_time,
                gain = excluded.gain,
                ircut = excluded.ircut,
                width = excluded.width,
                height = excluded.height,
                media_type = excluded.media_type,
                stacked_fits_path = excluded.stacked_fits_path,
                stacked_fits_md5 = excluded.stacked_fits_md5
            WHERE excluded.modification_time > DwarfData.modification_time
               OR excluded.target != DwarfData.target
            -- shotsToTake, shotsTaken, shotsStacked, maxTemp, minTemp
            -- intentionally excluded from UPDATE : these belong to the original
            -- session and must never be overwritten by a rescan (e.g. after a
            -- Merge/Megastack replaces the stacked.jpg and shotsInfo.json)
        """, (
            file_path, mtime, thumbnail_path, file_size,
            dec, ra, target, binning, format, exp_time, gain,
            shotsToTake, shotsTaken, shotsStacked, ircut, maxTemp, minTemp,
            width, height, media_type, stacked_path, stacked_md5
        ))

        if cursor.rowcount > 0:
            commit_db(conn)
            if exist_id is None:
                last_id = cursor.lastrowid
                print(f" DwarfData : Adding new Id :{last_id}")
                return last_id, last_id
            else:
                print(f" DwarfData : Updated existing Id : {exist_id}")
                return exist_id, exist_id

        else:
            row = conn.execute("SELECT id FROM DwarfData WHERE file_path = ?", (file_path,)).fetchone()
            exist_id = row[0] if row else None  # Already existed
            print(f" DwarfData : Already Exist Id :{exist_id}")
            return None, exist_id

    except Exception as e:
        print(f"[DB ERROR] Failed to insert or fetch DwarfData: {e}")
        return None, None

def insert_BackupEntry(conn: sqlite3.Connection, backup_drive_id, dwarf_id, astro_object_id, dwarf_data_id, session_dt_str, session_dir, astro_group_id):
    try:
        # Insert entry in BackupEntry
        cursor = conn.execute("""
            INSERT OR IGNORE INTO BackupEntry (
                backup_drive_id, dwarf_id, astro_object_id, dwarf_data_id, session_date, session_dir, astro_group_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(backup_drive_id, dwarf_id, dwarf_data_id)
            DO UPDATE SET
                astro_object_id=excluded.astro_object_id,
                session_date=excluded.session_date,
                session_dir=excluded.session_dir,
                astro_group_id=excluded.astro_group_id
        """, (backup_drive_id, dwarf_id, astro_object_id, dwarf_data_id, session_dt_str, session_dir, astro_group_id))

        if cursor.rowcount > 0:
            backupEntry_id = cursor.lastrowid
            if not backupEntry_id:
                print(f"Backup data updated: {backup_drive_id},{dwarf_id},{dwarf_data_id}")
            commit_db(conn)
            return backupEntry_id
        else:
            print("Error Insert ignored : insert_BackupEntry")
            return None

    except Exception as e:
        print(f"[DB ERROR] Failed to insert BackupEntry: {e}")
        return []

def insert_DwarfEntry(conn: sqlite3.Connection, dwarf_id, astro_object_id, dwarf_data_id, session_dt_str, session_dir, astro_group_id):
    try:
        cursor = conn.execute("""
            INSERT INTO DwarfEntry (
                dwarf_id, astro_object_id, dwarf_data_id, session_date, session_dir, astro_group_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(dwarf_id, dwarf_data_id)
            DO UPDATE SET
                astro_object_id=excluded.astro_object_id,
                session_date=excluded.session_date,
                session_dir=excluded.session_dir,
                astro_group_id=excluded.astro_group_id
        """, (dwarf_id, astro_object_id, dwarf_data_id, session_dt_str, session_dir, astro_group_id))

        if cursor.rowcount > 0:
            dwarfEntry_id = cursor.lastrowid
            if not dwarfEntry_id:
                print(f"Dwarf Data updated: {dwarf_id},{dwarf_data_id}")
            commit_db(conn)
            return dwarfEntry_id
        else:
            print("Error Insert ignored : insert_DwarfEntry")
            return None

    except Exception as e:
        print(f"[DB ERROR] Failed to insert DwarfEntry: {e}")
        return []

def insert_ManualSession(conn: sqlite3.Connection, session_name, session_tag, session_type, jpeg_path, modification_time, thumbnail_path, file_size,
        description, dec, ra, exp_time, IR_filter, maxTemp, minTemp, stacked_png_path, stacked_fits_path, stacked_fits_md5):
    try:

        # Try to fetch existing ID first
        row = conn.execute(
            "SELECT id FROM ManualSession WHERE session_name = ? AND session_tag = ? AND session_type = ?",
            (session_name, session_tag, session_type)
        ).fetchone()
        exist_id = row[0] if row else None

        cursor = conn.execute("""
            INSERT INTO ManualSession (
                session_name, session_tag, session_type, jpeg_path, modification_time, thumbnail_path, file_size,
                description, dec, ra, exp_time, ircut, maxTemp, minTemp,
                stacked_png_path, stacked_fits_path, stacked_fits_md5
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_name, session_tag, session_type) DO UPDATE SET
                jpeg_path = excluded.jpeg_path,
                modification_time = excluded.modification_time,
                thumbnail_path = excluded.thumbnail_path,
                file_size = excluded.file_size,
                description = excluded.description,
                dec = excluded.dec,
                ra = excluded.ra,
                exp_time = excluded.exp_time,
                ircut = excluded.ircut,
                maxTemp = excluded.maxTemp,
                minTemp = excluded.minTemp,
                stacked_png_path = excluded.stacked_png_path,
                stacked_fits_path = excluded.stacked_fits_path,
                stacked_fits_md5 = excluded.stacked_fits_md5
            WHERE excluded.modification_time > ManualSession.modification_time
               OR excluded.description != ManualSession.description
        """, (
            session_name, session_tag, session_type, jpeg_path, modification_time, thumbnail_path, file_size,
            description, dec, ra, exp_time, IR_filter, maxTemp, minTemp,
            stacked_png_path, stacked_fits_path, stacked_fits_md5
        ))

        if cursor.rowcount > 0:
            commit_db(conn)
            if exist_id is None:
                last_id = cursor.lastrowid
                print(f" ManualSession : Adding new Id :{last_id}")
                return last_id, last_id
            else:
                print(f" ManualSession : Updated existing Id : {exist_id}")
                return exist_id, exist_id

        else:
            row = conn.execute(
                "SELECT id FROM ManualSession WHERE session_name = ? AND session_tag = ? AND session_type = ?",
                (session_name, session_tag, session_type)
            ).fetchone()
            exist_id = row[0] if row else None  # Already existed
            print(f" ManualSession : Already Exist Id :{exist_id}")
            return None, exist_id

    except Exception as e:
        print(f"[DB ERROR] Failed to insert or fetch ManualSession: {e}")
        return None, None

def update_manual_session(conn: sqlite3.Connection, manual_session_id: int,
                          session_name, session_tag, session_type, jpeg_path,
                          modification_time, thumbnail_path, file_size, description,
                          dec, ra, exp_time, IR_filter, maxTemp, minTemp,
                          stacked_png_path, stacked_fits_path, stacked_fits_md5) -> bool:
    """Update an existing ManualSession by id — used in edit mode.

    Unlike insert_ManualSession (which uses ON CONFLICT on session_name),
    this always updates the specific row regardless of name changes.
    """
    try:
        conn.execute("""
            UPDATE ManualSession SET
                session_name      = ?,
                session_tag       = ?,
                session_type      = ?,
                jpeg_path         = ?,
                modification_time = ?,
                thumbnail_path    = ?,
                file_size         = ?,
                description       = ?,
                dec               = ?,
                ra                = ?,
                exp_time          = ?,
                ircut             = ?,
                maxTemp           = ?,
                minTemp           = ?,
                stacked_png_path  = ?,
                stacked_fits_path = ?,
                stacked_fits_md5  = ?
            WHERE id = ?
        """, (session_name, session_tag, session_type, jpeg_path,
              modification_time, thumbnail_path, file_size, description,
              dec, ra, exp_time, IR_filter, maxTemp, minTemp,
              stacked_png_path, stacked_fits_path, stacked_fits_md5,
              manual_session_id))
        commit_db(conn)
        print(f"[DB] ManualSession {manual_session_id} updated.")
        return True
    except Exception as e:
        print(f"[DB ERROR] update_manual_session: {e}")
        return False

def update_manual_session_image(conn: sqlite3.Connection, manual_session_id: int,
                                jpeg_path: str, thumbnail_path: str | None = None) -> bool:
    """Update jpeg_path (and optionally thumbnail_path) for an existing ManualSession.

    Called when the explore page finds an image on disk via fallback scan but the DB
    entry has no jpeg_path recorded (e.g. session imported from a Stellar Studio zip
    before the zip-extraction fix).
    """
    try:
        if thumbnail_path:
            conn.execute(
                "UPDATE ManualSession SET jpeg_path = ?, thumbnail_path = ? WHERE id = ?",
                (jpeg_path, thumbnail_path, manual_session_id)
            )
        else:
            conn.execute(
                "UPDATE ManualSession SET jpeg_path = ? WHERE id = ?",
                (jpeg_path, manual_session_id)
            )
        commit_db(conn)
        print(f"[DB] ManualSession {manual_session_id} jpeg_path updated: {jpeg_path}")
        return True
    except Exception as e:
        print(f"[DB ERROR] update_manual_session_image: {e}")
        return False

def insert_ManualSessionEntry(conn: sqlite3.Connection, manual_session_id, backup_drive_id, dwarf_id, astro_object_id, backup_entry_id, session_dt_str, session_dir, astro_group_id, manual_session_drive_id=None):
    try:
        # Insert entry in BackupEntry
        cursor = conn.execute("""
            INSERT OR IGNORE INTO ManualSessionEntry (
                manual_session_id, backup_drive_id, dwarf_id, astro_object_id, backup_entry_id, session_date, session_dir, astro_group_id, manual_session_drive
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(manual_session_id, backup_drive_id, dwarf_id, backup_entry_id)
            DO UPDATE SET
                astro_object_id=excluded.astro_object_id,
                session_date=excluded.session_date,
                session_dir=excluded.session_dir,
                astro_group_id=excluded.astro_group_id,
                manual_session_drive=excluded.manual_session_drive
        """, (manual_session_id, backup_drive_id, dwarf_id, astro_object_id, backup_entry_id, session_dt_str, session_dir, astro_group_id, manual_session_drive_id))

        if cursor.rowcount > 0:
            manualSessionEntry_id = cursor.lastrowid
            if not manualSessionEntry_id :
                print(f"Manual Session data updated: {manual_session_id} {backup_drive_id},{dwarf_id},{backup_entry_id}")
            commit_db(conn)
            return manualSessionEntry_id
        else:
            print("Error Insert ignored : insert_ManualSessionEntry")
            return None

    except Exception as e:
        print(f"[DB ERROR] Failed to insert ManualSessionEntry: {e}")
        return []


##############################
# DarkLibrary functions
##############################

def get_DarkLibrary_list(conn):
    """
    Result columns: [0]id [1]name [2]location [3]backup_drive_id
                    [4]last_scan_date [5]BackupDrive.name [6]BackupDrive.location
                    [7]Dwarf.name [8]Dwarf.id
    """
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT dl.id, dl.name, dl.location, dl.backup_drive_id,
                   dl.last_scan_date, bd.name, bd.location, d.name, d.id
            FROM DarkLibrary dl
            LEFT JOIN BackupDrive bd ON dl.backup_drive_id = bd.id
            LEFT JOIN Dwarf       d  ON bd.dwarf_id        = d.id
            ORDER BY d.name, bd.name
        """)
        return cursor.fetchall()
    except Exception as e:
        print(f"[DB ERROR] get_DarkLibrary_list: {e}")
        return []


def get_or_create_DarkLibrary(conn, location, backup_drive_id, name=None):
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM DarkLibrary WHERE location = ?", (location,))
        row = cursor.fetchone()
        now = datetime.now().isoformat(sep=" ", timespec="seconds")
        if row:
            cursor.execute("""
                UPDATE DarkLibrary
                SET backup_drive_id = COALESCE(?, backup_drive_id),
                    last_scan_date  = ?
                WHERE id = ?
            """, (backup_drive_id, now, row[0]))
            commit_db(conn)
            return row[0]
        effective_name = name or os.path.basename(location) or location
        cursor.execute("""
            INSERT INTO DarkLibrary (name, location, backup_drive_id)
            VALUES (?, ?, ?)
        """, (effective_name, location, backup_drive_id))
        new_id = cursor.lastrowid
        commit_db(conn)
        return new_id
    except Exception as e:
        print(f"[DB ERROR] get_or_create_DarkLibrary: {e}")
        return None


def delete_DarkLibrary(conn, library_id):
    try:
        conn.execute("DELETE FROM DarkLibrary WHERE id = ?", (library_id,))
        commit_db(conn)
        return True
    except Exception as e:
        print(f"[DB ERROR] delete_DarkLibrary: {e}")
        return False


def find_matching_darks(conn, dwarf_id, exp_s, gain, binning, min_temp, max_temp):
    """
    Search all DarkLibrary locations for the given dwarf_id.
    Matching: exact gain+binning, exposure within 2%, best temp.
    Returns: {"status": "matched"|"partial"|"none", "files": [...],
              "count": int, "library": str|None, "temp_match": bool}
    """
    import re as _re
    from pathlib import Path

    DARK_RE = _re.compile(
        r"dark_exp_(?P<exp>[0-9]+\.?[0-9]*)_gain_(?P<gain>[0-9]+)"
        r"_bin_(?P<bin>[0-9]+)_(?P<temp>-?[0-9]+)C",
        _re.IGNORECASE,
    )

    def parse_dark(name):
        m = DARK_RE.search(name)
        if not m:
            return None
        try:
            return {"exp_s": float(m.group("exp")), "gain": int(m.group("gain")),
                    "binning": int(m.group("bin")), "temp_c": int(m.group("temp"))}
        except Exception:
            return None

    def glob_fits(folder):
        p = Path(folder)
        if not p.is_dir():
            return []
        files = []
        for ext in ("*.fit","*.fits","*.fts","*.FIT","*.FITS","*.FTS"):
            files.extend(p.glob(ext))
        return sorted(set(files))

    empty = {"status": "none", "files": [], "count": 0, "library": None, "temp_match": False}

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT dl.location FROM DarkLibrary dl
            JOIN BackupDrive bd ON dl.backup_drive_id = bd.id
            WHERE bd.dwarf_id = ? AND dl.location IS NOT NULL
        """, (dwarf_id,))
        libs = [r[0] for r in cursor.fetchall()]
    except Exception as e:
        print(f"[DB ERROR] find_matching_darks: {e}")
        return empty

    if not libs:
        return empty

    exp_tol = max(0.05, exp_s * 0.02)
    candidates = []

    for lib_loc in libs:
        from pathlib import Path as _P
        _dark_dir = _P(lib_loc) / "dark"
        if not _dark_dir.is_dir():
            _dark_dir = _P(lib_loc) / "CALI_FRAME" / "dark"
            if not _dark_dir.is_dir():
                continue
        for cam in ("cam_0", "cam_1"):
            for f in glob_fits(str(_dark_dir / cam)):
                meta = parse_dark(f.name)
                if not meta:
                    continue
                if meta["gain"] != gain or meta["binning"] != binning:
                    continue
                if abs(meta["exp_s"] - exp_s) > exp_tol:
                    continue
                candidates.append((str(f), meta, lib_loc))

    if not candidates:
        return empty

    temp_match = False
    if min_temp is not None and max_temp is not None:
        in_range = [(f,m,l) for (f,m,l) in candidates
                    if min_temp <= m["temp_c"] <= max_temp]
        if in_range:
            candidates = in_range
            temp_match = True

    if not temp_match:
        temps = [m["temp_c"] for (_,m,_) in candidates]
        mean_t = ((min_temp+max_temp)/2.0 if (min_temp is not None and max_temp is not None)
                  else sorted(temps)[len(temps)//2])
        best_d = min(abs(m["temp_c"]-mean_t) for (_,m,_) in candidates)
        candidates = [(f,m,l) for (f,m,l) in candidates
                      if abs(m["temp_c"]-mean_t) == best_d]

    files = sorted([f for (f,_,_) in candidates])
    status = "matched" if (temp_match or min_temp is None) else "partial"
    return {"status": status, "files": files, "count": len(files),
            "library": candidates[0][2] if candidates else None,
            "temp_match": temp_match}


def _resolve_cali_frame_root(location):
    from pathlib import Path
    base = Path(location)
    if (base / "dark").is_dir() or (base / "bias").is_dir() or (base / "flat").is_dir():
        return base
    sub = base / "CALI_FRAME"
    if sub.is_dir():
        return sub
    return None


def _detect_ir_code(ir_str):
    s = (ir_str or "").strip().lower()
    if "astro" in s:                                         return 1
    if any(x in s for x in ("dual","duo","band","narrow")): return 2
    if any(x in s for x in ("none","off","clear","ircut")): return 0
    return None


def _scan_calib_subfolders(parent_dir):
    from pathlib import Path
    result = {}
    p = Path(parent_dir)
    if not p.is_dir():
        return result
    for cam_dir in sorted(p.iterdir()):
        if not cam_dir.is_dir():
            continue
        name = cam_dir.name.lower()
        if name.startswith("cam_0"):
            cam = "cam_0"
        elif name.startswith("cam_1"):
            cam = "cam_1"
        else:
            continue
        files = [f.name for f in sorted(cam_dir.iterdir()) if f.is_file()]
        if files:
            result.setdefault(cam, []).extend(files)
    return result


def scan_dark_library(location):
    """
    Inventory a CALI_FRAME directory — dark, bias and flat frames.
    Returns: {"total": int, "by_cam": {...}, "bias": {...}, "flat": {...},
              "cali_frame_dir": str, "errors": [...]}
    """
    import re as _re
    from pathlib import Path

    DARK_RE = _re.compile(
        r"dark_exp_(?P<exp>[0-9]+\.?[0-9]*)_gain_(?P<gain>[0-9]+)"
        r"_bin_(?P<bin>[0-9]+)_(?P<temp>-?[0-9]+)C",
        _re.IGNORECASE,
    )

    result = {"total": 0, "by_cam": {}, "bias": {}, "flat": {}, "cali_frame_dir": None, "errors": []}

    cali_root = _resolve_cali_frame_root(location)
    if cali_root is None:
        return result
    result["cali_frame_dir"] = str(cali_root)

    dark_root = cali_root / "dark"
    if dark_root.is_dir():
        for cam_dir in sorted(dark_root.iterdir()):
            if not cam_dir.is_dir():
                continue
            entries = []
            files = []
            for ext in ("*.fit","*.fits","*.fts","*.FIT","*.FITS","*.FTS"):
                files.extend(cam_dir.glob(ext))
            for f in sorted(set(files)):
                m = DARK_RE.search(f.name)
                if not m:
                    result["errors"].append(str(f))
                    continue
                try:
                    entries.append({"file": str(f), "exp_s": float(m.group("exp")),
                                    "gain": int(m.group("gain")), "binning": int(m.group("bin")),
                                    "temp_c": int(m.group("temp"))})
                    result["total"] += 1
                except Exception as ex:
                    result["errors"].append(f"{f}: {ex}")
            if entries:
                result["by_cam"][cam_dir.name] = entries

    result["bias"] = _scan_calib_subfolders(cali_root / "bias")
    result["flat"] = _scan_calib_subfolders(cali_root / "flat")
    return result


def find_matching_bias_flat(location, cam_name, ir_filter, gain):
    """Find best matching bias and flat files in CALI_FRAME."""
    from pathlib import Path

    cali_root = _resolve_cali_frame_root(location)
    if cali_root is None:
        return {"bias_file": None, "flat_file": None, "bias_dir": None, "flat_dir": None}

    ir_code = _detect_ir_code(ir_filter)

    def find_flat_file(cam_dir):
        if not cam_dir.is_dir():
            return None
        candidates = []
        for f in sorted(cam_dir.iterdir()):
            if not f.is_file():
                continue
            n = f.name.lower()
            if n.startswith("flat_") and (ir_code is None or f"_ir_{ir_code}" in n):
                candidates.append(str(f))
        return candidates[0] if candidates else None

    def find_bias_file(cam_dir):
        if not cam_dir.is_dir():
            return None
        for f in sorted(cam_dir.iterdir()):
            if not f.is_file():
                continue
            if f.name.lower().startswith("bias_"):
                return str(f)
        return None

    def score_dir(name, ir_code):
        n = name.lower()
        sc = len(n) // 10
        if ir_code is not None:
            if f"ir_{ir_code}" in n:  sc += 10
            elif "ir_" in n:          sc -= 2
        return sc

    flat_file = flat_dir = None
    flat_root = cali_root / "flat"
    if flat_root.is_dir():
        flat_file = find_flat_file(flat_root / cam_name)
        if not flat_file:
            candidates = [p for p in flat_root.iterdir()
                          if p.is_dir() and p.name.lower().startswith(cam_name.lower())]
            if candidates:
                best = sorted(candidates, key=lambda p: score_dir(p.name, ir_code), reverse=True)[0]
                flat_dir = str(best)

    bias_file = bias_dir = None
    bias_root = cali_root / "bias"
    if bias_root.is_dir():
        bias_file = find_bias_file(bias_root / cam_name)
        if not bias_file:
            candidates = [p for p in bias_root.iterdir()
                          if p.is_dir() and p.name.lower().startswith(cam_name.lower())]
            if candidates:
                best = sorted(candidates, key=lambda p: score_dir(p.name, ir_code), reverse=True)[0]
                bias_dir = str(best)

    return {"bias_file": bias_file, "flat_file": flat_file,
            "bias_dir": bias_dir, "flat_dir": flat_dir}


async def generate_siril_session_json(conn, row, backup_location, session_full_dir=""):
    """Generate siril_session.json from a session row."""
    import os
    from pathlib import Path
    from datetime import datetime as _dt

    exp_time    = row[2];  gain       = row[3];  ir_filter  = row[4]
    stacks      = row[5];  session_dir= row[8];  dwarf_name = row[9]
    min_temp    = row[10]; max_temp   = row[11]; target     = row[13]
    dec         = row[14]; ra         = row[15]; dwarf_id   = row[20]
    binning_raw = row[21] if len(row) > 21 else None
    try:
        binning = int(str(binning_raw).split("*")[0]) if binning_raw else 1
    except Exception:
        binning = 1

    # Get dwarf_id from BackupDrive when None
    if dwarf_id is None and row[19]:
        try:
            r = conn.cursor().execute("SELECT dwarf_id FROM BackupDrive WHERE id=?", (row[19],)).fetchone()
            if r: dwarf_id = r[0]
        except Exception:
            pass

    cam_name = "cam_1" if (session_dir and "_WIDE_" in str(session_dir).upper()) else "cam_0"

    # Resolve full session path
    if session_full_dir and os.path.isdir(session_full_dir):
        full_session_dir = session_full_dir
    elif os.path.isabs(session_dir or "") and os.path.isdir(session_dir):
        full_session_dir = session_dir
    else:
        full_session_dir = os.path.join(backup_location, session_dir) if backup_location else (session_dir or "")
        if not os.path.isdir(full_session_dir) and backup_location:
            alt = os.path.join(backup_location, os.path.basename(session_dir or ""))
            if os.path.isdir(alt):
                full_session_dir = alt

    print(f"[siril_json] full_session_dir={full_session_dir} exists={os.path.isdir(full_session_dir)}")

    # Collect lights
    lights = []
    if os.path.isdir(full_session_dir):
        is_mosaic = "_MOSAIC_" in str(full_session_dir).upper()
        fits_files = []
        if is_mosaic:
            for panel_dir in sorted(Path(full_session_dir).iterdir()):
                if panel_dir.is_dir():
                    for ext in (".fits",".fit",".fts",".FIT",".FITS",".FTS"):
                        fits_files.extend(panel_dir.glob(f"*{ext}"))
        else:
            for ext in (".fits",".fit",".fts",".FIT",".FITS",".FTS"):
                fits_files.extend(Path(full_session_dir).glob(f"*{ext}"))
        for f in sorted(set(fits_files)):
            n = f.name.lower()
            if not any(n.startswith(x) for x in ("stacked","pp_","r_pp_","dsl_")):
                lights.append(str(f))
        print(f"[siril_json] found {len(lights)} light files")

    dark_result = find_matching_darks(
        conn, dwarf_id,
        float(exp_time) if exp_time else 0,
        int(gain) if gain else 0,
        binning,
        int(min_temp) if min_temp is not None else None,
        int(max_temp) if max_temp is not None else None,
    )

    bias_dir = flat_dir = bias_file = flat_file = cali_frame_dir = None
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT dl.location FROM DarkLibrary dl
            JOIN BackupDrive bd ON dl.backup_drive_id = bd.id
            WHERE bd.dwarf_id = ? AND dl.location IS NOT NULL
        """, (dwarf_id,))
        for (lib_loc,) in cursor.fetchall():
            bf = find_matching_bias_flat(lib_loc, cam_name, ir_filter, int(gain) if gain else 0)
            if bf["bias_file"] or bf["bias_dir"] or bf["flat_file"] or bf["flat_dir"]:
                bias_dir  = bf.get("bias_dir")
                flat_dir  = bf.get("flat_dir")
                bias_file = bf.get("bias_file")
                flat_file = bf.get("flat_file")
                _base = Path(lib_loc)
                if (_base/"dark").is_dir() or (_base/"bias").is_dir():
                    cali_frame_dir = str(_base)
                elif (_base/"CALI_FRAME").is_dir():
                    cali_frame_dir = str(_base/"CALI_FRAME")
                break
    except Exception as e:
        print(f"[generate_siril_session_json] bias/flat lookup failed: {e}")

    return {
        "generated_by": "Dwarfium Scope Archive",
        "generated_at": _dt.now().strftime("%Y-%m-%d %H:%M:%S"),
        "session": {
            "target": target or "Unknown", "date": str(row[7]) if row[7] else "",
            "session_dir": full_session_dir, "cam": cam_name, "dwarf": dwarf_name or "",
            "exp_s": float(exp_time) if exp_time else 0,
            "gain": int(gain) if gain else 0, "binning": binning,
            "ir_filter": ir_filter or "",
            "min_temp": int(min_temp) if min_temp is not None else None,
            "max_temp": int(max_temp) if max_temp is not None else None,
            "shots_stacked": int(stacks) if stacks else 0,
            "ra": float(ra) if ra else None, "dec": float(dec) if dec else None,
        },
        "lights": lights,
        "darks": {"status": dark_result["status"], "files": dark_result["files"],
                  "count": dark_result["count"], "temp_match": dark_result["temp_match"],
                  "library": dark_result["library"]},
        "bias_file": bias_file, "flat_file": flat_file,
        "bias_dir":  bias_dir,  "flat_dir":  flat_dir,
        "cali_frame_dir": cali_frame_dir,
    }



def get_or_create_ManualSessionDrive(conn: sqlite3.Connection, location: str, name: str = None, description: str = None, manualsession_dir: str = None, backup_drive_id: int = None):
    try:
        # Try to fetch existing ID first
        row = conn.execute("SELECT id FROM ManualSessionDrive WHERE location = ?", (location,)).fetchone()
        if row:
            # Row already exists — update backup_drive_id in case it changed after
            # a DB wipe + rescan (the FK was SET NULL but the drive is back)
            if backup_drive_id is not None:
                conn.execute(
                    "UPDATE ManualSessionDrive SET backup_drive_id = ? WHERE id = ?",
                    (backup_drive_id, row[0])
                )
                commit_db(conn)
            return row[0]

        # Insert new one
        cursor = conn.execute("""
            INSERT INTO ManualSessionDrive (location, name, description, manualsession_dir, backup_drive_id)
            VALUES (?, ?, ?, ?, ?)
        """, (location, name, description, manualsession_dir, backup_drive_id))
        commit_db(conn)
        return cursor.lastrowid

    except Exception as e:
        print(f"[DB ERROR] Failed to get or create ManualSessionDrive: {e}")
        return None



def write_missing_shotsInfo(conn) -> dict:
    """
    One-shot utility: write shotsInfo.json into every ManualSession folder
    that does not already have one.
    Returns {"written": N, "skipped": N, "errors": N}
    """
    import json as _json

    written = skipped = errors = 0

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                ms.session_name, ms.session_tag, ms.session_type,
                ms.dec, ms.ra, ms.description,
                mse.session_dir, mse.session_date, mse.backup_entry_id,
                bd.location AS backup_drive_location,
                bd.astronomy_dir,
                d.name AS dwarf_name,
                be.session_dir AS backup_session_dir
            FROM ManualSession ms
            JOIN ManualSessionEntry mse ON mse.manual_session_id = ms.id
            LEFT JOIN BackupDrive bd ON bd.id = mse.backup_drive_id
            LEFT JOIN Dwarf d        ON d.id  = mse.dwarf_id
            LEFT JOIN BackupEntry be ON be.id = mse.backup_entry_id
        """)
        rows = cursor.fetchall()

        for (session_name, session_tag, session_type,
             dec, ra, description,
             session_dir, session_date, backup_entry_id,
             backup_drive_location, astronomy_dir,
             dwarf_name, backup_session_dir) in rows:

            if not session_dir or not os.path.isdir(session_dir):
                skipped += 1
                continue

            shots_path = os.path.join(session_dir, "shotsInfo.json")
            if os.path.isfile(shots_path):
                skipped += 1
                continue

            norm_sd = os.path.normpath(session_dir)
            if session_tag:
                manualsession_dir = os.path.normpath(os.path.dirname(os.path.dirname(norm_sd)))
            else:
                manualsession_dir = os.path.normpath(os.path.dirname(norm_sd))

            try:
                shots_info = {
                    "session_name":          session_name          or "",
                    "session_tag":           session_tag           or "",
                    "session_type":          session_type          or "",
                    "session_dir":           session_dir           or "",
                    "backup_drive_location": backup_drive_location or "",
                    "manualsession_dir":     manualsession_dir,
                    "dwarf_name":            dwarf_name            or "",
                    "backup_session_dir":    backup_session_dir    or "",
                    "session_date":          str(session_date) if session_date else "",
                    "dec":                   dec         or "",
                    "ra":                    ra          or "",
                    "description":           description or "",
                }
                with open(shots_path, "w", encoding="utf-8") as f:
                    _json.dump(shots_info, f, indent=2, ensure_ascii=False)
                written += 1
            except Exception as e:
                print(f"[DB ERROR] write_missing_shotsInfo: failed for '{session_name}': {e}")
                errors += 1

    except Exception as outer_e:
        print(f"[DB ERROR] write_missing_shotsInfo outer failure: {outer_e}")
        errors += 1

    print(f"[INFO] write_missing_shotsInfo — written={written}, skipped={skipped}, errors={errors}")
    return {"written": written, "skipped": skipped, "errors": errors}


def rebuild_manual_session_entries(conn: sqlite3.Connection) -> dict:
    """
    Reconstruct orphaned ManualSessionEntry rows after a DB wipe + backup rescan.

    Strategy
    --------
    After a full DB reset, BackupDrive rows are rebuilt by the backup scanner with
    new primary key ids.  ManualSession rows survive untouched (they hold all
    metadata), but every ManualSessionEntry is gone because its FK targets no
    longer exist.

    ManualSessionDrive is the anchor: it stores the physical location of every
    backup drive that has ever hosted a manual session, independently of BackupDrive.
    For each ManualSession that has no ManualSessionEntry, this function:

      1. Finds which ManualSessionDrive owns the session by prefix-matching
         ManualSession.stacked_fits_path / jpeg_path against ManualSessionDrive.location.
      2. Re-links ManualSessionDrive.backup_drive_id to the new BackupDrive row
         (matched by location).
      3. Looks up the matching BackupEntry by session_dir (optional link).
      4. Re-creates the AstroObject from stored RA/Dec/description.
      5. Inserts the ManualSessionEntry.

    Returns a dict:
        {
            "rebuilt":  int,   # entries successfully created
            "skipped":  int,   # ManualSessions with no matching drive on disk
            "errors":   int,   # unexpected failures
        }
    """
    from api.dwarf_backup_fct import MANUAL, UNKNOWN

    rebuilt = 0
    skipped = 0
    errors  = 0

    try:
        cursor = conn.cursor()

        # ── Step 1: find all ManualSessions with no entry at all ──────────────
        cursor.execute("""
            SELECT
                ms.id,
                ms.session_name,
                ms.session_tag,
                ms.session_type,
                ms.dec,
                ms.ra,
                ms.description,
                ms.jpeg_path,
                ms.stacked_fits_path,
                ms.stacked_png_path
            FROM ManualSession ms
            WHERE NOT EXISTS (
                SELECT 1 FROM ManualSessionEntry mse
                WHERE mse.manual_session_id = ms.id
            )
        """)
        orphans = cursor.fetchall()

        if not orphans:
            print("[INFO] rebuild_manual_session_entries: no orphaned ManualSession rows found.")
            return {"rebuilt": 0, "skipped": 0, "errors": 0}

        print(f"[INFO] rebuild_manual_session_entries: {len(orphans)} orphaned ManualSession(s) to process.")

        # ── Step 2: load ManualSessionDrive rows for prefix matching ──────────
        # Longest location prefix wins — order DESC by length
        cursor.execute("""
            SELECT id, location, manualsession_dir, backup_drive_id
            FROM ManualSessionDrive
            ORDER BY LENGTH(location) DESC
        """)
        drives = cursor.fetchall()

        # ── Step 3: re-link ManualSessionDrive → new BackupDrive ids ──────────
        # BackupDrive was rebuilt by the scanner with new ids; re-match by location
        cursor.execute("SELECT id, location FROM BackupDrive")
        backup_drives = {os.path.normpath(loc): bid for bid, loc in cursor.fetchall() if loc}

        for msd_id, msd_location, msd_dir, old_bd_id in drives:
            norm = os.path.normpath(msd_location)
            new_bd_id = backup_drives.get(norm)
            if new_bd_id and new_bd_id != old_bd_id:
                cursor.execute(
                    "UPDATE ManualSessionDrive SET backup_drive_id = ? WHERE id = ?",
                    (new_bd_id, msd_id)
                )
                print(f"[INFO] ManualSessionDrive id={msd_id}: backup_drive_id updated "
                      f"{old_bd_id} → {new_bd_id}")

        commit_db(conn)

        # Reload drives with updated backup_drive_id values
        cursor.execute("""
            SELECT id, location, manualsession_dir, backup_drive_id
            FROM ManualSessionDrive
            ORDER BY LENGTH(location) DESC
        """)
        drives = cursor.fetchall()

        # ── Step 4: ensure the Manual astro_group exists ──────────────────────
        astro_group_id, _ = insert_astro_group(conn, MANUAL)

        # ── Step 5: process each orphan ───────────────────────────────────────
        for (ms_id, session_name, session_tag, session_type,
             dec, ra, description, jpeg_path,
             stacked_fits_path, stacked_png_path) in orphans:

            try:
                # Find the ManualSessionDrive whose location is a prefix of any
                # stored file path. Try jpeg first, then fits, then png.
                reference_paths = [p for p in (jpeg_path, stacked_fits_path, stacked_png_path) if p]

                matched_msd = None
                for msd_id, msd_location, msd_dir, msd_bd_id in drives:
                    norm_loc = os.path.normpath(msd_location)
                    for ref in reference_paths:
                        if os.path.normpath(ref).startswith(norm_loc):
                            matched_msd = (msd_id, msd_location, msd_dir, msd_bd_id)
                            break
                    if matched_msd:
                        break

                if not matched_msd:
                    print(f"[WARN] rebuild: no ManualSessionDrive matched "
                          f"ManualSession '{session_name}' (id={ms_id}) — skipped.")
                    skipped += 1
                    continue

                msd_id, msd_location, msd_dir, backup_drive_id = matched_msd

                # Reconstruct session_dir from manualsession_dir / name [/ tag]
                session_dir = os.path.join(msd_dir, session_name)
                if session_tag:
                    session_dir = os.path.join(session_dir, session_tag)
                session_dir = os.path.normpath(session_dir)

                if not os.path.isdir(session_dir):
                    print(f"[WARN] rebuild: session folder not found on disk: "
                          f"'{session_dir}' — skipped.")
                    skipped += 1
                    continue

                # dwarf_id comes from the BackupDrive (one drive → one Dwarf)
                cursor.execute(
                    "SELECT dwarf_id FROM BackupDrive WHERE id = ?",
                    (backup_drive_id,)
                )
                bd_row = cursor.fetchone()
                dwarf_id = bd_row[0] if bd_row else None

                # Try to find a matching BackupEntry by session_dir basename
                session_dirname = os.path.basename(
                    os.path.dirname(session_dir) if session_tag else session_dir
                )
                cursor.execute("""
                    SELECT id FROM BackupEntry
                    WHERE backup_drive_id = ?
                      AND session_dir LIKE ?
                    LIMIT 1
                """, (backup_drive_id, f"%{session_dirname}%"))
                be_row = cursor.fetchone()
                backup_entry_id = be_row[0] if be_row else None

                # Re-create or retrieve the AstroObject
                astro_object_id = None
                obj_name = description or session_name
                if obj_name:
                    is_unknown = obj_name.lower() in (UNKNOWN.lower(), "unknown")
                    astro_object_id, _ = insert_astro_object(
                        conn, obj_name, is_unknown, dec, ra
                    )

                # Insert the ManualSessionEntry
                session_dt_str = datetime.now().isoformat(sep=' ', timespec='seconds')
                insert_ManualSessionEntry(
                    conn,
                    manual_session_id       = ms_id,
                    backup_drive_id         = backup_drive_id,
                    dwarf_id                = dwarf_id,
                    astro_object_id         = astro_object_id,
                    backup_entry_id         = backup_entry_id,
                    session_dt_str          = session_dt_str,
                    session_dir             = session_dir,
                    astro_group_id          = astro_group_id,
                    manual_session_drive_id = msd_id,
                )

                print(f"[INFO] rebuild: ManualSessionEntry created for "
                      f"'{{session_name}}' (tag='{{session_tag}}', "
                      f"backup_drive_id={{backup_drive_id}}).")
                rebuilt += 1

            except Exception as inner_e:
                print(f"[DB ERROR] rebuild: failed for ManualSession id={{ms_id}}: {{inner_e}}")
                errors += 1

    except Exception as outer_e:
        print(f"[DB ERROR] rebuild_manual_session_entries: outer failure: {{outer_e}}")
        errors += 1

    print(f"[INFO] rebuild_manual_session_entries complete — "
          f"rebuilt={{rebuilt}}, skipped={{skipped}}, errors={{errors}}")
    return {{"rebuilt": rebuilt, "skipped": skipped, "errors": errors}}


#########################
# Astro Object functions
#########################

def get_astro_objects(conn: sqlite3.Connection):
    placeholders = ', '.join(['?'] * len(DEFAULT_GROUP_NAMES))  # → "?, ?, ?"
    query = f'''
        SELECT id, name, description, dso_id 
        FROM AstroObject 
        WHERE name NOT IN ({placeholders})
    '''
    with conn:
        return conn.execute(query, DEFAULT_GROUP_NAMES).fetchall()

def get_astro_object_by_id(conn: sqlite3.Connection, object_id: int):
    """Return a single AstroObject row (id, name, description, dso_id) by id."""
    with conn:
        return conn.execute(
            "SELECT id, name, description, dso_id FROM AstroObject WHERE id = ?",
            (object_id,)
        ).fetchone()

def get_astro_object_description(conn: sqlite3.Connection, object_id=None):
    with conn:
        result = conn.execute('SELECT description FROM AstroObject Where id = ? ', (object_id,)).fetchone()
        return result[0] if result else None

def get_astro_object_groupId(conn: sqlite3.Connection, name):
    with conn:
        result = conn.execute('SELECT id FROM AstroObject Where name = ? and is_group = True', (name,)).fetchone()
        return result[0] if result else None

def update_astro_object_name(conn: sqlite3.Connection, object_id=None, newName=None):
    try:
        with conn:
            if newName:
                cursor = conn.execute("SELECT id FROM AstroObject WHERE id = ?", (object_id,))
                row = cursor.fetchone()
                if row:
                    conn.execute('UPDATE AstroObject SET name=? WHERE id=?', (newName, object_id))
                    return True
                else:
                    print("Error Update no Data : update_astro_object_name")
                    return False
            else: 
                return False

    except Exception as e:
        print(f"[DB ERROR] Failed to update astro object {newName}: {e}")
        return False

def update_astro_object_description(conn: sqlite3.Connection, object_id=None, description=None):
    try:
        with conn:
            if description:
                cursor = conn.execute("SELECT id FROM AstroObject WHERE id = ?", (object_id,))
                row = cursor.fetchone()
                if row:
                    conn.execute('UPDATE AstroObject SET description=? WHERE id=?', (description, object_id))
                    return True
                else:
                    print("Error Update no Data : update_astro_object_description")
                    return False
            else: 
                return False

    except Exception as e:
        print(f"[DB ERROR] Failed to update astro object {name}: {e}")
        return False

def update_astro_object_coord(conn: sqlite3.Connection, astro_id, dec, ra):
    try:
        if astro_id:
            # Check if the object exists
            cursor = conn.execute("SELECT id FROM AstroObject WHERE id = ?", (astro_id,))
            row = cursor.fetchone()
            if row:
                # Now perform the update
                update_cursor = conn.execute(
                    'UPDATE AstroObject SET dec = ?, ra = ? WHERE id = ?',
                    (dec, ra, astro_id)
                )
                if update_cursor.rowcount > 0:
                    commit_db(conn)
                    return astro_id, True  # return the ID updated
                else:
                    print("[WARN] Update skipped: no change or row not found.")
                    return astro_id, False
        return None, False

    except Exception as e:
        print(f"[DB ERROR] Failed to update astro object ID {astro_id}: {e}")
        return None, False

def values_differ(a, b):
    return (a is None) != (b is None) or (a != b and a is not None and b is not None)

def insert_astro_object(conn: sqlite3.Connection, name=None, unknown=False, dec=None, ra=None):
    try:
        if name:
            query = "SELECT id, dec, ra FROM AstroObject WHERE is_group = False AND name = ?"
            params = [name]

            if unknown:
                if dec is None:
                    query += " AND dec IS NULL"
                else:
                    query += " AND dec = ?"
                    params.append(dec)

                if ra is None:
                    query += " AND ra IS NULL"
                else:
                    query += " AND ra = ?"
                    params.append(ra)

            cursor = conn.execute(query, tuple(params))
            row = cursor.fetchone()
            if row:
                astro_id, existing_dec, existing_ra = row

                # Convert for comparison
                if values_differ(dec, existing_dec) or values_differ(ra, existing_ra):
                    update_astro_object_coord(conn, astro_id, dec, ra)

                return astro_id , False
            else:
                cursor = conn.execute("INSERT INTO AstroObject (name, dec, ra, description, is_group) VALUES (?, ?, ?, ?, ?)", (name, dec, ra, "", False))
                if cursor.rowcount > 0:
                    commit_db(conn)
                    return cursor.lastrowid , True
                else:
                    print("Error Insert ignored : insert_astro_object")
                    return None, False
        else: 
            return None, False

    except Exception as e:
        print(f"[DB ERROR] Failed to insert astro object {name}: {e}")
        return None, False

##########################
# Default group functions
##########################

def insert_default_groups(conn: sqlite3.Connection):
    """Ensure default groups are in DB and store their IDs in DEFAULT_GROUP_IDS."""
    for name in DEFAULT_GROUP_NAMES:
        group_id, _ = insert_astro_group(conn, name)
        if group_id:
            DEFAULT_GROUP_IDS[name] = group_id
        else:
            print(f"[WARN] Could not insert or fetch group: {name}")

def get_default_group_id(name: str):
    """Get the ID of a default group by name."""
    return DEFAULT_GROUP_IDS.get(name)

def insert_astro_group(conn: sqlite3.Connection, name=None):
    try:
        if name:
            cursor = conn.execute("SELECT id FROM AstroObject WHERE is_group = True and name = ?", (name,))
            row = cursor.fetchone()
            if row:
                 return row[0] , False
            else:
                cursor = conn.execute("INSERT INTO AstroObject (name, description, is_group) VALUES (?, ?, ?)", (name, "", True))
                if cursor.rowcount > 0:
                    commit_db(conn)
                    return cursor.lastrowid , True
                else:
                    print("Error Insert ignored : insert_astro_group")
                    return None, False
        else: 
            return None, False

    except Exception as e:
        print(f"[DB ERROR] Failed to insert astro group {name}: {e}")
        return None, None

################
# DSO functions
################

def get_dso_name(conn: sqlite3.Connection, dso_id):
    with conn:
        result = conn.execute('SELECT designation FROM DsoCatalog WHERE id = ?', (dso_id,)).fetchone()
        return result[0] if result else None

def get_dso_registered(conn: sqlite3.Connection, dso_id):
    with conn:
        result = conn.execute('SELECT id, designation, displayName, constellation, type, size, magnitude FROM DsoCatalog WHERE id = ?', (dso_id,)).fetchone()
        return result if result else None

def get_dso_registered_by_designation(conn: sqlite3.Connection, designation):
    with conn:
        result = conn.execute('SELECT id FROM DsoCatalog WHERE designation = ?', (designation,)).fetchone()
        return result[0] if result else None

def get_dso_filtered(conn: sqlite3.Connection, search='', constellation=None, dso_type=None):
    query = 'SELECT id, designation, displayName, constellation, type FROM DsoCatalog WHERE 1=1'
    params = []
    if search:
        query += ' AND (designation LIKE ? OR displayName LIKE ? OR constellation LIKE ? OR type LIKE ?)'
        s = f'%{search}%'
        params.extend([s, s, s, s])
    if constellation:
        query += ' AND constellation = ?'
        params.append(constellation)
    if dso_type:
        query += ' AND type = ?'
        params.append(dso_type)
    query += ' ORDER BY designation'
    with conn:
        return conn.execute(query, params).fetchall()

def update_astro_object_dso(conn: sqlite3.Connection, astro_id, dso_id, description):
    with conn:
        dso = conn.execute('SELECT displayName, constellation, type, size, magnitude FROM DsoCatalog WHERE id = ?', (dso_id,)).fetchone()
        if dso:
            displayName, constellation, type_, size, mag = dso
            descriptionDB = f"{displayName.split(',')[0].strip()} ({type_}) in {constellation}, size: {size or 'N/A'}, mag: {mag or 'N/A'}"
            if not description :
                description = descriptionDB
            conn.execute('UPDATE AstroObject SET dso_id=?, description=? WHERE id=?', (dso_id, description, astro_id))
            commit_db(conn)

def get_dso_description(conn: sqlite3.Connection, dso_id):
    with conn:
        dso = conn.execute('SELECT displayName, constellation, type, size, magnitude FROM DsoCatalog WHERE id = ?', (dso_id,)).fetchone()
        if dso:
            displayName, constellation, type_, size, mag = dso
            description = f"{displayName.split(',')[0].strip()} ({type_}) in {constellation}, size: {size or 'N/A'}, mag: {mag or 'N/A'}"
            return description
        else:
            return None

def export_associations(conn: sqlite3.Connection):
    rows = []
    with conn:
        data = conn.execute('''
            SELECT ao.id, ao.name, ao.description, d.designation, d.displayName
            FROM AstroObject ao
            LEFT JOIN DsoCatalog d ON ao.dso_id = d.id
            ORDER BY ao.id
        ''').fetchall()
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['AstroObject ID', 'Name', 'Description', 'DSO Designation', 'DSO Display Name'])
    writer.writerows(data)
    output.seek(0)
    return output.read()

########################
# MTP DEVICES functions
########################

def device_exists_in_db(conn: sqlite3.Connection, mtp_drive_id):
    try:
        exists = False
        if mtp_drive_id:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM MtpDevices WHERE mtp_drive_id = ?", (mtp_drive_id,))
            exists = cursor.fetchone() is not None
        return exists
    except Exception as e:
        print(f"[DB ERROR] Failed to insert device_exists_in_db: {e}")
        return False

# Add MTP Device to Database
def add_mtp_device_to_db(conn: sqlite3.Connection, device_name, mtp_drive_id):
    try:
        if device_name:
            cursor = conn.cursor()
            conn.execute("SELECT id FROM MtpDevices WHERE device_name = ?", (device_name,))
            row = cursor.fetchone()
            if row:
                 return True
            else:
                cursor.execute("INSERT INTO MtpDevices (device_name, mtp_drive_id) VALUES (?, ?)", (device_name, mtp_drive_id))
                commit_db(conn)
                return True
    except Exception as e:
        print(f"[DB ERROR] Failed to insert add_mtp_device_to_db: {e}")
        return False

def get_mtp_devices(conn: sqlite3.Connection):
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM MtpDevices")
        return cursor.fetchall()
    except Exception as e:
        print(f"[DB ERROR] Failed to fetch MtpDevices: {e}")
        return []

def get_mtp_device(conn: sqlite3.Connection, mtp_id):
    try:
        if mtp_id:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM MtpDevices where id = ?", (mtp_id,))
            result = cursor.fetchall()  # Fetch all results as a list
            return result if result else []  # Return list or empty list
        else: 
            return []
    except Exception as e:
        print(f"[DB ERROR] Failed to fetch MtpDevices: {e}")
        return []

#########################
# DwarfSessionsError
#########################

def insert_dwarf_session_error(conn: sqlite3.Connection, dwarf_id, session_date, session_dir) -> bool:
    """
    Insert a Mosaic session in error (no stacked.jpg but shotsInfo.json present).
    Uses INSERT OR IGNORE on (dwarf_id, session_dir) — safe to call on every scan,
    never overwrites an existing REPAIRED status.
    Returns True if a new row was inserted.
    """
    try:
        session_dt_str = session_date.strftime("%Y-%m-%d %H:%M:%S.%f") if session_date else None
        cursor = conn.execute("""
            INSERT INTO DwarfSessionsError (dwarf_id, session_date, session_dir, status)
            VALUES (?, ?, ?, 'ERROR')
            ON CONFLICT(dwarf_id, session_dir) DO NOTHING
        """, (dwarf_id, session_dt_str, session_dir))
        if cursor.lastrowid:
            commit_db(conn)
            return True
        return False
    except Exception as e:
        print(f"[DB ERROR] insert_dwarf_session_error: {e}")
        return False


def update_dwarf_session_error_repaired(conn: sqlite3.Connection, dwarf_id, session_dir, session_dir_master) -> bool:
    """
    Mark a session error as REPAIRED and record the master session used.
    Called when a repairInfo.json is detected during scan.
    """
    try:
        cursor = conn.execute("""
            UPDATE DwarfSessionsError
            SET status = 'REPAIRED', session_dir_master = ?
            WHERE dwarf_id = ? AND session_dir = ?
        """, (session_dir_master, dwarf_id, session_dir))
        if cursor.rowcount > 0:
            commit_db(conn)
            return True
        return False
    except Exception as e:
        print(f"[DB ERROR] update_dwarf_session_error_repaired: {e}")
        return False


def get_dwarf_sessions_error(conn: sqlite3.Connection, dwarf_id, status=None) -> list:
    """
    Return sessions in error for a given Dwarf.
    Optionally filter by status ('ERROR', 'REPAIRED').
    """
    try:
        if status:
            rows = conn.execute("""
                SELECT id, dwarf_id, session_date, session_dir, session_dir_master, status
                FROM DwarfSessionsError
                WHERE dwarf_id = ? AND status = ?
                ORDER BY session_date DESC
            """, (dwarf_id, status)).fetchall()
        else:
            rows = conn.execute("""
                SELECT id, dwarf_id, session_date, session_dir, session_dir_master, status
                FROM DwarfSessionsError
                WHERE dwarf_id = ?
                ORDER BY session_date DESC
            """, (dwarf_id,)).fetchall()
        return rows if rows else []
    except Exception as e:
        print(f"[DB ERROR] get_dwarf_sessions_error: {e}")
        return []


def get_dwarf_session_error_by_dir(conn: sqlite3.Connection, dwarf_id, session_dir) -> dict | None:
    """
    Return a single DwarfSessionsError row by (dwarf_id, session_dir).
    Used in Explore to check if a session is a REPAIR.
    """
    try:
        row = conn.execute("""
            SELECT id, dwarf_id, session_date, session_dir, session_dir_master, status
            FROM DwarfSessionsError
            WHERE dwarf_id = ? AND session_dir = ?
        """, (dwarf_id, session_dir)).fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "dwarf_id": row[1],
            "session_date": row[2],
            "session_dir": row[3],
            "session_dir_master": row[4],
            "status": row[5],
        }
    except Exception as e:
        print(f"[DB ERROR] get_dwarf_session_error_by_dir: {e}")
        return None