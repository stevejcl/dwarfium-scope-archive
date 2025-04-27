import os
import sys
import sqlite3

from dwarf_backup_db import commit_db

def is_dwarf_exists(conn: sqlite3.Connection, dwarf_id: None):
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

def get_dwarf_detail(conn: sqlite3.Connection, dwarf_id: None):
    try:
        if dwarf_id:
            cursor = conn.cursor()
            cursor.execute("SELECT name, description, usb_astronomy_dir, type FROM Dwarf WHERE id = ?", (dwarf_id,))
            return cursor.fetchone()
        else:
           return []

    except Exception as e:
        print(f"[DB ERROR] Failed to fetch dwarf detail: {e}")
        return []

def set_dwarf_detail(conn: sqlite3.Connection, name, desc, usb_astronomy_dir, dtype, dwarf_id: None):
    try:
        if dwarf_id:
            cursor = conn.cursor()
            cursor.execute("UPDATE Dwarf SET name=?, description=?, usb_astronomy_dir=?, type=? WHERE id=?",
                           (name, desc, usb_astronomy_dir, dtype, dwarf_id))
            commit_db(conn)
            return True
        else:
            return False

    except Exception as e:
        print(f"[DB ERROR] Failed to fetch dwarf detail: {e}")
        return False

def add_dwarf_detail(conn: sqlite3.Connection, name, desc, usb_astronomy_dir, dtype):
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO Dwarf (name, description, usb_astronomy_dir, type) VALUES (?, ?, ?, ?)",
                       (name, desc, usb_astronomy_dir, dtype))
        dwarf_id = cursor.lastrowid
        commit_db(conn)
        return dwarf_id

    except Exception as e:
        print(f"[DB ERROR] Failed to add dwarf detail: {e}")
        return None

def get_backupDrive_Names(conn: sqlite3.Connection):
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM BackupDrive ORDER BY name")
        return cursor.fetchall()
    except Exception as e:
        print(f"[DB ERROR] Failed to fetch backup drives: {e}")
        return []

def get_backupDrive_detail(conn: sqlite3.Connection, backupDrive_id: None):
    try:
        if backupDrive_id:
            cursor = conn.cursor()
            cursor.execute("SELECT BackupDrive.name, BackupDrive.description, BackupDrive.location, BackupDrive.astronomy_dir, Dwarf.name type FROM BackupDrive, Dwarf WHERE BackupDrive.id = ? and BackupDrive.dwarf_id = Dwarf.id", (backupDrive_id,))
            return cursor.fetchone()
        else:
           return []

    except Exception as e:
        print(f"[DB ERROR] Failed to fetch backup drive detail {backupDrive_id}: {e}")
        return []

def get_backupDrive_id_from_location(conn: sqlite3.Connection, location: None):
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
        cursor.execute("SELECT id, name, description, location, dwarf_id FROM BackupDrive")
        return cursor.fetchall()

    except Exception as e:
        print(f"[DB ERROR] Failed to fetch backupDrive list: {e}")
        return []


def set_backupDrive_detail(conn: sqlite3.Connection, name, desc, astroDir, dwarf_id, location: None):
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

def add_backupDrive_detail(conn: sqlite3.Connection, name, desc, location, astroDir, dwarf_id: None):
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO BackupDrive (name, description, location, astronomy_dir, dwarf_id)
            VALUES (?, ?, ?, ?, ?)
        """, (name, desc, location, astroDir, dwarf_id))
        backupDrive_id = cursor.lastrowid
        commit_db(conn)
        return backupDrive_id

    except Exception as e:
        print(f"[DB ERROR] Failed to add backupDrive detail: {e}")
        return None

def del_dwarf(conn: sqlite3.Connection, dwarf_id: None):
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM Dwarf WHERE id = ?", (dwarf_id,))
        commit_db(conn)
        return True

    except Exception as e:
        print(f"[DB ERROR] Failed to delete Dwarf {dwarf_id}: {e}")
        return False

def del_backupDrive(conn: sqlite3.Connection, backupDrive_id: None):
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

def get_Objects_backup(conn: sqlite3.Connection, backup_drive_id=None, dwarf_id=None, only_on_dwarf=None):
    try:
        cursor = conn.cursor()

        query = """
            SELECT DISTINCT AstroObject.id, AstroObject.name
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

            if only_on_dwarf:
                # Filter BackupEntry to only those with session_dir present in DwarfEntry for same dwarf
                conditions.append("""
                    BackupEntry.session_dir IN (
                        SELECT session_dir FROM DwarfEntry WHERE dwarf_id = ?
                    )
                """)
                params.append(dwarf_id)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY AstroObject.name"

        cursor.execute(query, params)

        return cursor.fetchall()

    except Exception as e:
        print(f"[DB ERROR] Failed to fetch get_Objects_backup: {e}")
        return []

def get_Objects_dwarf(conn: sqlite3.Connection, dwarf_id=None, only_on_backup=None):
    try:
        cursor = conn.cursor()

        query = """
            SELECT DISTINCT AstroObject.id, AstroObject.name
            FROM AstroObject
            JOIN DwarfEntry ON DwarfEntry.astro_object_id = AstroObject.id
            JOIN DwarfData ON DwarfEntry.dwarf_data_id = DwarfData.id
        """
        conditions = []
        params = []

        if dwarf_id:  # not "(All Dwarfs)"
            conditions.append("DwarfEntry.dwarf_id = ?")
            params.append(dwarf_id)

            if only_on_backup:
                # Filter DwarfEntry to only those with session_dir present in BackupEntry for same dwarf
                conditions.append("""
                    DwarfEntry.session_dir IN (
                        SELECT session_dir FROM BackupEntry WHERE dwarf_id = ?
                    )
                """)
                params.append(dwarf_id)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY AstroObject.name"

        cursor.execute(query, params)

        return cursor.fetchall()

    except Exception as e:
        print(f"[DB ERROR] Failed to fetch get_Objects_backup: {e}")
        return []

def get_countObjects_backup(conn: sqlite3.Connection, backup_drive_id=None, dwarf_id=None, only_on_dwarf=None):
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

            if only_on_dwarf:
                # Filter BackupEntry to only those with session_dir present in DwarfEntry for same dwarf
                conditions.append("""
                    BackupEntry.session_dir IN (
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

def get_countObjects_dwarf(conn: sqlite3.Connection, dwarf_id=None, only_on_backup=None):
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

            if only_on_backup:
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

def get_ObjectSelect_backup(conn: sqlite3.Connection, object_id = None, backup_drive_id=None, dwarf_id=None, only_on_dwarf=None):
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
                Dwarf.name
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

            if only_on_dwarf:
                # Filter BackupEntry to only those with session_dir present in DwarfEntry for same dwarf
                conditions.append("""
                    BackupEntry.session_dir IN (
                        SELECT session_dir FROM DwarfEntry WHERE dwarf_id = ?
                    )
                """)
                params.append(dwarf_id)

        if conditions:
            query += " AND " + " AND ".join(conditions)

        cursor.execute(query, params)

        return cursor.fetchall()

    except Exception as e:
        print(f"[DB ERROR] Failed to fetch get_ObjectSelect_backup: {e}")
        return []

def get_ObjectSelect_dwarf(conn: sqlite3.Connection, object_id = None, dwarf_id=None, only_on_backup=None):
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
                Dwarf.name
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

            if only_on_backup:
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

def has_related_backup_entries(conn: sqlite3.Connection, backup_drive_id:None):
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

def delete_backup_entries_and_dwarf_data(conn: sqlite3.Connection, backup_drive_id:None):
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

        conn.commit()
        print(f"Deleted {len(dwarf_data_ids)} DwarfData entries (if not reused) and all related BackupEntry rows.")

    except Exception as e:
        print(f"[DB ERROR] Failed to delete backup entries and dwarf data for {backup_drive_id}: {e}")
        return False

def delete_dwarf_entries_and_dwarf_data(conn: sqlite3.Connection, dwarf_id:None):
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

        conn.commit()
        print(f"Deleted {len(dwarf_data_ids)} DwarfData entries (if not reused) and all related DwarfEntry rows.")

    except Exception as e:
        print(f"[DB ERROR] Failed to delete dwarf entries and dwarf data for {dwarf_id}: {e}")
        return False

def is_session_backed_up(conn: sqlite3.Connection, session_dir:None):
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

def get_session_present_in_Dwarf(conn: sqlite3.Connection, session_dir:None):
    try:
        if session_dir:
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

        return []

    except Exception as e:
        print(f"[DB ERROR] Failed to get session present in Dwarf for {session_dir}: {e}")
        return []

def get_session_present_in_backupDrive(conn: sqlite3.Connection, session_dir:None):
    try:
        if session_dir:
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

        return []

    except Exception as e:
        print(f"[DB ERROR] Failed to get session present in backupDrive for {session_dir}: {e}")
        return []

def insert_astro_object(conn: sqlite3.Connection, name: None):
    try:
        if name:
            cursor = conn.execute("SELECT id FROM AstroObject WHERE name = ?", (name,))
            row = cursor.fetchone()
            if row:
                 return row[0]
            else:
                cursor = conn.execute("INSERT INTO AstroObject (name, description) VALUES (?, ?)", (name, ""))
                return cursor.lastrowid
        else: 
            return None

    except Exception as e:
        print(f"[DB ERROR] Failed to insert astro object {name}: {e}")
        return []

def insert_DwarfData(conn: sqlite3.Connection, file_path, mtime, thumbnail_path, file_size,
        dec, ra, target, binning, format, exp_time, gain, shotsToTake, shotsTaken,
        shotsStacked, ircut, width, height, media_type, stacked_path, stacked_md5):
    try:

        cursor = conn.execute("""
            INSERT OR IGNORE INTO DwarfData (
                file_path, modification_time, thumbnail_path, file_size,
                dec, ra, target, binning, format, exp_time, gain,
                shotsToTake, shotsTaken, shotsStacked, ircut, width,
                height, media_type, stacked_fits_path, stacked_fits_md5
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            file_path, mtime, thumbnail_path, file_size,
            dec, ra, target, binning, format, exp_time, gain,
            shotsToTake, shotsTaken, shotsStacked, ircut, width,
            height, media_type, stacked_path, stacked_md5
        ))

        return cursor.lastrowid

    except Exception as e:
        print(f"[DB ERROR] Failed to insert DwarfData: {e}")
        return []

def insert_BackupEntry(conn: sqlite3.Connection, backup_drive_id, dwarf_id, astro_object_id, dwarf_data_id, session_dt_str, session_dir):
    try:
        # Insert entry in BackupEntry
        cursor = conn.execute("""
            INSERT OR IGNORE INTO BackupEntry (
                backup_drive_id, dwarf_id, astro_object_id, dwarf_data_id, session_date, session_dir
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (backup_drive_id, dwarf_id, astro_object_id, dwarf_data_id, session_dt_str, session_dir))

        return cursor.lastrowid

    except Exception as e:
        print(f"[DB ERROR] Failed to insert BackupEntry: {e}")
        return []


def insert_DwarfEntry(conn: sqlite3.Connection, dwarf_id, astro_object_id, dwarf_data_id, session_dt_str, session_dir):
    try:
        # Insert entry in BackupEntry
        cursor = conn.execute("""
            INSERT OR IGNORE INTO DwarfEntry (
                dwarf_id, astro_object_id, dwarf_data_id, session_date, session_dir
            ) VALUES (?, ?, ?, ?, ?)
         """, (dwarf_id, astro_object_id, dwarf_data_id, session_dt_str, session_dir))

        return cursor.lastrowid

    except Exception as e:
        print(f"[DB ERROR] Failed to insert DwarfEntry: {e}")
        return []

