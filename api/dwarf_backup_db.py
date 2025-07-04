import sqlite3
import os
# Encoding changed to UTF-8
DB_NAME = "db\\dwarf_backup.db"

def connect_db(database:DB_NAME):
    try:
        db_dir = os.path.dirname(database)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)

        conn = sqlite3.connect(database)
        if conn:
            init_db(conn)
        return conn

    except Exception as e:
        print(f"[DB ERROR] Failed to connect DB {database}: {e}")
        return None

def close_db(conn):
    if conn:
        conn.close()

def commit_db(conn):
    if conn:
        conn.commit()

def init_db(conn):
    try:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS Dwarf (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                usb_astronomy_dir TEXT,
                type TEXT,
                last_scan_date DATETIME,
                ip_sta_mode TEXT,
                mtp_id INTEGER,
                FOREIGN KEY (mtp_id) REFERENCES MtpDevices(id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS BackupDrive (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                description TEXT,
                location TEXT UNIQUE,
                astronomy_dir TEXT,
                dwarf_id INTEGER,
                last_backup_scan_date DATETIME,
                FOREIGN KEY (dwarf_id) REFERENCES Dwarf(id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS DwarfData (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT UNIQUE NOT NULL,
                modification_time INTEGER,
                thumbnail_path TEXT,
                file_size INTEGER,
                dec TEXT,
                ra TEXT,
                target TEXT,
                binning TEXT,
                format TEXT,
                exp_time TEXT,
                gain INTEGER,
                shotsToTake INTEGER,
                shotsTaken INTEGER,
                shotsStacked INTEGER,
                ircut TEXT,
                maxTemp INTEGER,
                minTemp INTEGER,
                width TEXT,
                height TEXT,
                media_type INTEGER,
                stacked_fits_path TEXT,
                stacked_fits_md5 TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS BackupEntry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                backup_drive_id INTEGER,
                dwarf_id INTEGER,
                astro_object_id INTEGER,
                dwarf_data_id INTEGER,
                session_date DATETIME,
                session_dir TEXT,
                favorite BOOLEAN DEFAULT 0,
                FOREIGN KEY (backup_drive_id) REFERENCES BackupDrive(id),
                FOREIGN KEY (dwarf_id) REFERENCES Dwarf(id),
                FOREIGN KEY (astro_object_id) REFERENCES AstroObject(id),
                FOREIGN KEY (dwarf_data_id) REFERENCES DwarfData(id),
                UNIQUE("backup_drive_id", "dwarf_id", "dwarf_data_id")
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS DwarfEntry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dwarf_id INTEGER,
                astro_object_id INTEGER,
                dwarf_data_id INTEGER,
                session_date DATETIME,
                session_dir TEXT,
                favorite BOOLEAN DEFAULT 0,
                FOREIGN KEY (dwarf_id) REFERENCES Dwarf(id),
                FOREIGN KEY (astro_object_id) REFERENCES AstroObject(id),
                FOREIGN KEY (dwarf_data_id) REFERENCES DwarfData(id)
                UNIQUE("dwarf_id", "dwarf_data_id")
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS MtpDevices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_name TEXT,
                mtp_drive_id TEXT
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_backupentry_session_dir ON BackupEntry(session_dir);
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_dwarfentry_session_dir ON DwarfEntry(session_dir);
        """)
        # Create table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS DsoCatalog (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                designation TEXT UNIQUE,
                displayName TEXT,
                catalogue TEXT,
                objectNumber INTEGER,
                type TEXT,
                typeCategory TEXT,
                ra TEXT,
                dec TEXT,
                magnitude REAL,
                constellation TEXT,
                size TEXT,
                notes TEXT,
                favorite BOOLEAN,
                alternateNames TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS AstroObject (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                dso_id INTEGER REFERENCES DsoCatalog(id)
            )
        """)
        cursor.execute("""
          CREATE INDEX IF NOT EXISTS idx_catalogue ON DsoCatalog(catalogue);
        """)
        cursor.execute("""
          CREATE INDEX IF NOT EXISTS idx_type ON DsoCatalog(type);
        """)
        cursor.execute("""
          CREATE INDEX IF NOT EXISTS idx_constellation ON DsoCatalog(constellation);
        """)
        # Check if the table is empty
        cursor.execute("SELECT COUNT(*) FROM DsoCatalog")
        row_count = cursor.fetchone()[0]

        if row_count == 0:
            import_dso_catalog(conn)

        conn.commit()

    except Exception as e:
        print(f"[DB ERROR] Failed to init DB: {e}")
        return []

def get_backup_entries(conn):
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

        return cursor.fetchall()

    except Exception as e:
        print(f"[DB ERROR] Failed to fetch backup entries: {e}")
        return []

def get_astro_object_summary(conn):
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                AstroObject.name,
                COUNT(BackupEntry.id) as num_files
            FROM AstroObject
            LEFT JOIN BackupEntry ON AstroObject.id = BackupEntry.astro_object_id
            GROUP BY AstroObject.id
            ORDER BY num_files DESC
        """)

        return cursor.fetchall()

    except Exception as e:
        print(f"[DB ERROR] Failed to fetch astro object summary: {e}")
        return []

import json
def import_dso_catalog(conn):
    try:
        cursor = conn.cursor()

        with open('./db/dso_catalog.json', 'r', encoding='utf-8') as f:
            data = json.load(f)

            for obj in data:
                cursor.execute("""
                    INSERT INTO DsoCatalog (
                        designation, displayName, catalogue, objectNumber,
                        type, typeCategory, ra, dec, magnitude,
                        constellation, size, notes, favorite, alternateNames
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(designation) DO UPDATE SET
                        displayName=excluded.displayName,
                        catalogue=excluded.catalogue,
                        objectNumber=excluded.objectNumber,
                        type=excluded.type,
                        typeCategory=excluded.typeCategory,
                        ra=excluded.ra,
                        dec=excluded.dec,
                        magnitude=excluded.magnitude,
                        constellation=excluded.constellation,
                        size=excluded.size,
                        notes=excluded.notes,
                        favorite=excluded.favorite,
                        alternateNames=excluded.alternateNames
                """, (
                    obj.get('designation'),
                    obj.get('displayName'),
                    obj.get('catalogue'),
                    obj.get('objectNumber'),
                    obj.get('type'),
                    obj.get('typeCategory'),
                    obj.get('ra'),
                    obj.get('dec'),
                    obj.get('magnitude'),
                    obj.get('constellation'),
                    obj.get('size'),
                    obj.get('notes'),
                    int(obj.get('favorite', False)),
                    obj.get('alternateNames')
                ))

            conn.commit()

            # Check inserted data
            cursor.execute("SELECT COUNT(*) FROM DsoCatalog")
            row_count = cursor.fetchone()[0]
            if row_count == 0:
                print(f" no object found in DSO catalog")
            elif row_count == 1:
                print(f" {row_count} object has been inserted in DSO catalog")
            else:
                print(f" {row_count} objects have been inserted in DSO catalog")

    except Exception as e:
        print(f"[DB ERROR] Failed to insert dso_catalog: {e}")
        return []
