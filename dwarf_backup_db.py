import sqlite3

DB_NAME = "dwarf_backup.db"

def connect_db(database:DB_NAME):
    try:
        conn = sqlite3.connect(database)

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
                type TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS BackupDrive (
                id INTEGER PRIMARY KEY,
                name TEXT,
                description TEXT,
                location TEXT UNIQUE,
                astronomy_dir TEXT,
                dwarf_id INTEGER,
                FOREIGN KEY (dwarf_id) REFERENCES Dwarf(id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS AstroObject (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT
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
                FOREIGN KEY (backup_drive_id) REFERENCES BackupDrive(id),
                FOREIGN KEY (dwarf_id) REFERENCES Dwarf(id),
                FOREIGN KEY (astro_object_id) REFERENCES AstroObject(id),
                FOREIGN KEY (dwarf_data_id) REFERENCES DwarfData(id)
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
                FOREIGN KEY (dwarf_id) REFERENCES Dwarf(id),
                FOREIGN KEY (astro_object_id) REFERENCES AstroObject(id),
                FOREIGN KEY (dwarf_data_id) REFERENCES DwarfData(id)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_backupentry_session_dir ON BackupEntry(session_dir);
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_dwarfentry_session_dir ON DwarfEntry(session_dir);
        """)
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
