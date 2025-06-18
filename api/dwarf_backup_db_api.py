import os
import sys
import sqlite3
from datetime import datetime
from io import StringIO
import csv

from api.dwarf_backup_db import commit_db

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
        cursor.execute(f"SELECT id, name, description, location, astronomy_dir, dwarf_id FROM BackupDrive Where dwarf_id = {dwarf_id}")
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

def get_Objects_backup(conn: sqlite3.Connection, backup_drive_id=None, dwarf_id=None, only_on_dwarf=None, only_on_backup=None):
    try:
        cursor = conn.cursor()

        query = """
            SELECT DISTINCT 
                AstroObject.id, 
                CASE 
                    WHEN AstroObject.description IS NOT NULL AND TRIM(AstroObject.description) != '' 
                    THEN AstroObject.description || ' [' || AstroObject.name || ']' 
                    ELSE AstroObject.name 
                END AS display_name
            FROM AstroObject
            JOIN BackupEntry ON BackupEntry.astro_object_id = AstroObject.id
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
                # Filter BackupEntry to only those with session_dir present in DwarfEntry for same dwarf
                conditions.append("""
                    BackupEntry.session_dir NOT IN (
                        SELECT session_dir FROM DwarfEntry WHERE dwarf_id = ?
                    )
                """)
                params.append(dwarf_id)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY display_name"

        cursor.execute(query, params)

        return cursor.fetchall()

    except Exception as e:
        print(f"[DB ERROR] Failed to fetch get_Objects_backup: {e}")
        return []

def get_Objects_dwarf(conn: sqlite3.Connection, dwarf_id=None, only_on_dwarf=None, only_on_backup=None):
    try:
        cursor = conn.cursor()

        query = """
            SELECT DISTINCT 
                AstroObject.id, 
                CASE 
                    WHEN AstroObject.description IS NOT NULL AND TRIM(AstroObject.description) != '' 
                    THEN AstroObject.description || ' [' || AstroObject.name || ']' 
                    ELSE AstroObject.name 
                END AS display_name
            FROM AstroObject
            JOIN DwarfEntry ON DwarfEntry.astro_object_id = AstroObject.id
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

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY display_name"

        cursor.execute(query, params)

        return cursor.fetchall()

    except Exception as e:
        print(f"[DB ERROR] Failed to fetch get_Objects_backup: {e}")
        return []

def get_countObjects_backup(conn: sqlite3.Connection, backup_drive_id=None, dwarf_id=None, only_on_dwarf=None, only_on_backup=None):
    try:
        cursor = conn.cursor()

        query = """
                SELECT COUNT(*)
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

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        cursor.execute(query, params)

        return cursor.fetchone()[0]

    except Exception as e:
        print(f"[DB ERROR] Failed to fetch get_Objects_backup: {e}")
        return []

def get_countObjects_dwarf(conn: sqlite3.Connection, dwarf_id=None, only_on_dwarf=None, only_on_backup=None):
    try:
        cursor = conn.cursor()

        query = """
            SELECT COUNT(*)
            FROM DwarfEntry
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

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        cursor.execute(query, params)

        return cursor.fetchone()[0]

    except Exception as e:
        print(f"[DB ERROR] Failed to fetch get_countObjects_dwarf: {e}")
        return []

def get_ObjectSelect_backup(conn: sqlite3.Connection, object_id = None, backup_drive_id=None, dwarf_id=None, only_on_dwarf=None, only_on_backup=None):
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
                DwarfData.ra
            FROM BackupEntry
            JOIN DwarfData ON BackupEntry.dwarf_data_id = DwarfData.id
            JOIN BackupDrive ON BackupEntry.backup_drive_id = BackupDrive.id
            JOIN Dwarf ON BackupDrive.dwarf_id = Dwarf.id
            WHERE BackupEntry.astro_object_id = ?
        """
        conditions = []
        params = [object_id]

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

        if conditions:
            query += " AND " + " AND ".join(conditions)

        query += " ORDER BY BackupEntry.session_date DESC"

        cursor.execute(query, params)

        return cursor.fetchall()

    except Exception as e:
        print(f"[DB ERROR] Failed to fetch get_ObjectSelect_backup: {e}")
        return []

def toggle_favorite(conn: sqlite3.Connection, entry_id, label_element, mode):
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

def get_ObjectSelect_dwarf(conn: sqlite3.Connection, object_id = None, dwarf_id=None, only_on_dwarf=None, only_on_backup=None):
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
                DwarfData.ra
            FROM DwarfEntry
            JOIN DwarfData ON DwarfEntry.dwarf_data_id = DwarfData.id
            JOIN Dwarf ON DwarfEntry.dwarf_id = Dwarf.id
            WHERE DwarfEntry.astro_object_id = ?
        """
        conditions = []
        params = [object_id]

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

        if conditions:
            query += " AND " + " AND ".join(conditions)

        cursor.execute(query, params)

        return cursor.fetchall()

    except Exception as e:
        print(f"[DB ERROR] Failed to fetch get_ObjectSelect_dwarf: {e}")
        return []

def get_backup_entries(conn: sqlite3.Connection):
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
                BackupDrive.location
            FROM BackupEntry
            LEFT JOIN AstroObject ON BackupEntry.astro_object_id = AstroObject.id
            LEFT JOIN DwarfData ON BackupEntry.dwarf_data_id = DwarfData.id
            LEFT JOIN Dwarf ON BackupEntry.dwarf_id = Dwarf.id
            LEFT JOIN BackupDrive ON BackupEntry.backup_drive_id = BackupDrive.id
            ORDER BY BackupEntry.id DESC
        """)
        rows = cursor.fetchall()

        return rows
    except Exception as e:
        print(f"[DB ERROR] Failed to fetch backup drives: {e}")
        return []

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
                BackupDrive.location
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
                BackupDrive.location
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

def has_related_dwarf_entries(conn: sqlite3.Connection, dwarf_id: int) -> bool:
    try:
        cursor = conn.cursor()

        # Verify in DwarfEntry
        cursor.execute("SELECT COUNT(*) FROM DwarfEntry WHERE dwarf_id = ?", (dwarf_id,))
        dwarfentry_count = cursor.fetchone()[0]

        # Verify in  BackupDrive
        cursor.execute("SELECT COUNT(*) FROM BackupDrive WHERE dwarf_id = ?", (dwarf_id,))
        backup_count = cursor.fetchone()[0]

        return (dwarfentry_count + backup_count) > 0

    except Exception as e:
        print(f"[DB ERROR] Failed to check related entries for dwarf_id {dwarf_id}: {e}")
        return True  # For Security

def has_related_backup_entries(conn: sqlite3.Connection, backup_drive_id=None):
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM BackupEntry WHERE backup_drive_id = ?",
            (backup_drive_id,)
        )
        count = cursor.fetchone()[0]
        return count > 0

    except Exception as e:
        print(f"[DB ERROR] Failed to verify has related backup entries: {e}")
        return True  # For Security

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

        conn.commit()
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

        conn.commit()
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

            conn.commit()
            print(f"Deleted {len(dwarf_data_ids)} unused DwarfData entries and obsolete BackupEntry rows.")
            return len(dwarf_data_ids)

        else:
            print(f"no Deletion made, because valid_ids has not be set for {backup_drive_id}!")
            return False

    except Exception as e:
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

            conn.commit()
            print(f"Deleted {len(dwarf_data_ids)} unused DwarfData entries and obsolete DwarfEntry rows.")
            return len(dwarf_data_ids)

        else:
            print(f"no Deletion made, because valid_ids has not be set for {dwarf_id}!")
            return False
            
    except Exception as e:
        print(f"[DB ERROR] Failed to delete entries for dwarf_id={dwarf_id}: {e}")
        return False

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

def insert_astro_object(conn: sqlite3.Connection, name=None):
    try:
        if name:
            cursor = conn.execute("SELECT id FROM AstroObject WHERE name = ?", (name,))
            row = cursor.fetchone()
            if row:
                 return row[0] , False
            else:
                cursor = conn.execute("INSERT INTO AstroObject (name, description) VALUES (?, ?)", (name, ""))
                if cursor.rowcount > 0:
                    conn.commit()
                    return cursor.lastrowid , True
                else:
                    print("Error Insert ignored : insert_astro_object")
                    return None, False
        else: 
            return None, False

    except Exception as e:
        print(f"[DB ERROR] Failed to insert astro object {name}: {e}")
        return []

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
                shotsToTake = excluded.shotsToTake,
                shotsTaken = excluded.shotsTaken,
                shotsStacked = excluded.shotsStacked,
                ircut = excluded.ircut,
                maxTemp = excluded.maxTemp,
                minTemp = excluded.minTemp,
                width = excluded.width,
                height = excluded.height,
                media_type = excluded.media_type,
                stacked_fits_path = excluded.stacked_fits_path,
                stacked_fits_md5 = excluded.stacked_fits_md5
            WHERE excluded.modification_time > DwarfData.modification_time
               OR excluded.target != DwarfData.target
        """, (
            file_path, mtime, thumbnail_path, file_size,
            dec, ra, target, binning, format, exp_time, gain,
            shotsToTake, shotsTaken, shotsStacked, ircut, maxTemp, minTemp,
            width, height, media_type, stacked_path, stacked_md5
        ))

        if cursor.rowcount > 0:
            conn.commit()
            if exist_id is None:
                last_id = cursor.lastrowid
                print(f" DwarData : Adding new Id :{last_id}")
                return last_id, last_id
            else:
                print(f" DwarData : Updated existing Id : {exist_id}")
                return exist_id, exist_id

        else:
            row = conn.execute("SELECT id FROM DwarfData WHERE file_path = ?", (file_path,)).fetchone()
            exist_id = row[0] if row else None  # Already existed
            print(f" DwarData : Already Exist Id :{exist_id}")
            return None, exist_id

    except Exception as e:
        print(f"[DB ERROR] Failed to insert or fetch DwarfData: {e}")
        return None, None

def insert_BackupEntry(conn: sqlite3.Connection, backup_drive_id, dwarf_id, astro_object_id, dwarf_data_id, session_dt_str, session_dir):
    try:
        # Insert entry in BackupEntry
        cursor = conn.execute("""
            INSERT OR IGNORE INTO BackupEntry (
                backup_drive_id, dwarf_id, astro_object_id, dwarf_data_id, session_date, session_dir
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(backup_drive_id, dwarf_id, dwarf_data_id)
            DO UPDATE SET
                astro_object_id=excluded.astro_object_id,
                session_date=excluded.session_date,
                session_dir=excluded.session_dir
        """, (backup_drive_id, dwarf_id, astro_object_id, dwarf_data_id, session_dt_str, session_dir))

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


def insert_DwarfEntry(conn: sqlite3.Connection, dwarf_id, astro_object_id, dwarf_data_id, session_dt_str, session_dir):
    try:
        cursor = conn.execute("""
            INSERT INTO DwarfEntry (
                dwarf_id, astro_object_id, dwarf_data_id, session_date, session_dir
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(dwarf_id, dwarf_data_id)
            DO UPDATE SET
                astro_object_id=excluded.astro_object_id,
                session_date=excluded.session_date,
                session_dir=excluded.session_dir
        """, (dwarf_id, astro_object_id, dwarf_data_id, session_dt_str, session_dir))

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

def get_astro_objects(conn: sqlite3.Connection):
    with conn:
        return conn.execute('SELECT id, name, description, dso_id FROM AstroObject').fetchall()

def get_dso_name(conn: sqlite3.Connection, dso_id):
    with conn:
        result = conn.execute('SELECT designation FROM DsoCatalog WHERE id = ?', (dso_id,)).fetchone()
        return result[0] if result else None


def get_dso_name(conn: sqlite3.Connection, dso_id):
    with conn:
        result = conn.execute('SELECT designation FROM DsoCatalog WHERE id = ?', (dso_id,)).fetchone()
        return result[0] if result else None

def get_dso_registered(conn: sqlite3.Connection, dso_id):
    with conn:
        result = conn.execute('SELECT id, designation, displayName, constellation, type, size, magnitude FROM DsoCatalog WHERE id = ?', (dso_id,)).fetchone()
        return result if result else None

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

def update_astro_object(conn: sqlite3.Connection, astro_id, dso_id, description):
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

# MTP DEVICES
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
                conn.commit()
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
