import sqlite3
import os
# Encoding changed to UTF-8
DB_NAME = os.path.join("db", "dwarf_backup.db")
CATALOG_FILE = os.path.join("db", "dso_catalog.json")

def start_db(database: str = DB_NAME):
    try:
        db_dir = os.path.dirname(database)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)

        conn = sqlite3.connect(database)
        if conn:
            conn.execute("PRAGMA foreign_keys = ON")
            init_db(conn)
        return conn

    except Exception as e:
        print(f"[DB ERROR] Failed to connect DB {database}: {e}")
        return None

def connect_db(database: str = DB_NAME):
    try:
        db_dir = os.path.dirname(database)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)

        conn = sqlite3.connect(database)
        if conn:
            conn.execute("PRAGMA foreign_keys = ON")
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

        # check if migration is needed
        if not is_new_database(conn):
            run_migrations(conn)

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
            CREATE TABLE IF NOT EXISTS AstroObject (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                dso_id INTEGER REFERENCES DsoCatalog(id),
                dec TEXT,
                ra TEXT,
                is_group BOOLEAN DEFAULT 0
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
                astro_group_id INTEGER,
                FOREIGN KEY (backup_drive_id) REFERENCES BackupDrive(id),
                FOREIGN KEY (dwarf_id) REFERENCES Dwarf(id),
                FOREIGN KEY (astro_object_id) REFERENCES AstroObject(id),
                FOREIGN KEY (dwarf_data_id) REFERENCES DwarfData(id),
                FOREIGN KEY (astro_group_id) REFERENCES AstroObject(id) ON DELETE SET NULL,
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
                astro_group_id INTEGER,
                FOREIGN KEY (dwarf_id) REFERENCES Dwarf(id),
                FOREIGN KEY (astro_object_id) REFERENCES AstroObject(id),
                FOREIGN KEY (dwarf_data_id) REFERENCES DwarfData(id),
                FOREIGN KEY (astro_group_id) REFERENCES AstroObject(id) ON DELETE SET NULL,
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
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_backupentry_astro_group_id ON BackupEntry(astro_group_id);
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_dwarfentry_astro_group_id ON DwarfEntry(astro_group_id);
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

        if row_count == 0 or row_count != count_catalog_elements():
            import_dso_catalog(conn)

        # Create table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS Settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parameter TEXT UNIQUE,
                type TEXT,
                valueText TEXT,
                valueInt INTEGER
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ManualSession (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_name TEXT NOT NULL,
                session_type TEXT,
                jpeg_path TEXT,
                modification_time INTEGER,
                thumbnail_path TEXT,
                file_size INTEGER,
                description TEXT,
                dec TEXT,
                ra TEXT,
                exp_time TEXT,
                ircut TEXT,
                maxTemp INTEGER,
                minTemp INTEGER,
                stacked_png_path TEXT,
                stacked_fits_path TEXT,
                stacked_fits_md5 TEXT,
                UNIQUE(session_name, session_type)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ManualSessionEntry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                manual_session_id INTEGER,
                backup_drive_id INTEGER,
                dwarf_id INTEGER,
                astro_object_id INTEGER,
                backup_entry_id INTEGER,
                session_date DATETIME,
                session_dir TEXT,
                favorite BOOLEAN DEFAULT 0,
                astro_group_id INTEGER,
                FOREIGN KEY (manual_session_id) REFERENCES ManualSession(id),
                FOREIGN KEY (backup_drive_id) REFERENCES BackupDrive(id),
                FOREIGN KEY (dwarf_id) REFERENCES Dwarf(id),
                FOREIGN KEY (astro_object_id) REFERENCES AstroObject(id),
                FOREIGN KEY (backup_entry_id) REFERENCES BackupEntry(id),
                FOREIGN KEY (astro_group_id) REFERENCES AstroObject(id) ON DELETE SET NULL,
                UNIQUE("manual_session_id", "backup_drive_id", "dwarf_id", "backup_entry_id")
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_manualsessionentry_session_dir ON ManualSessionEntry(session_dir);
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_manualsessionentry_astro_group_id ON ManualSessionEntry(astro_group_id);
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_manualsessionentry_manual_session_id ON ManualSessionEntry(manual_session_id);
        """)

        # insert default group

        conn.commit()

    except Exception as e:
        print(f"[DB ERROR] Failed to init DB: {e}")
        return []

def migrate_v1(conn):
    try:
        print("Migrating Database to V1...")

        cursor = conn.cursor()
        add_column_if_not_exists(conn, "AstroObject", "dec", "TXT")
        add_column_if_not_exists(conn, "AstroObject", "ra", "TXT")
        add_column_if_not_exists(conn, "AstroObject", "is_group", "BOOLEAN DEFAULT 0")
        add_column_if_not_exists(conn, "DwarfEntry", "astro_group_id", "INTEGER")
        add_column_if_not_exists(conn, "BackupEntry", "astro_group_id", "INTEGER")

        add_missing_foreign_keys(conn, "DwarfEntry", [
            {
                "column": "dwarf_id",
                "ref_table": "Dwarf",
                "ref_column": "id",
            },
            {
                "column": "astro_object_id",
                "ref_table": "AstroObject",
                "ref_column": "id",
            },
            {
                "column": "dwarf_data_id",
                "ref_table": "DwarfData",
                "ref_column": "id",
            },
            {
                "column": "astro_group_id",
                "ref_table": "AstroObject",
                "ref_column": "id",
                "on_delete": "SET NULL"
            }
        ])

        add_missing_foreign_keys(conn, "BackupEntry", [
            {
                "column": "backup_drive_id",
                "ref_table": "BackupDrive",
                "ref_column": "id",
            },
            {
                "column": "dwarf_id",
                "ref_table": "Dwarf",
                "ref_column": "id",
            },
            {
                "column": "astro_object_id",
                "ref_table": "AstroObject",
                "ref_column": "id",
            },
            {
                "column": "dwarf_data_id",
                "ref_table": "DwarfData",
                "ref_column": "id",
            },
            {
                "column": "astro_group_id",
                "ref_table": "AstroObject",
                "ref_column": "id",
                "on_delete": "SET NULL"
            }
        ])

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_backupentry_astro_group_id ON BackupEntry(astro_group_id);
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_dwarfentry_astro_group_id ON DwarfEntry(astro_group_id);
        """)

        commit_db(conn)
        print("Migration v1 applied.")
    except Exception as e:
        print(f"[DB ERROR] Failed to migrate DB: {e}")
        return []

def migrate_v2(conn):
    try:
        print("Migrating Database to V2...")
        cursor = conn.cursor()

        # Create table Settings
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS Settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parameter TEXT UNIQUE,
                type TEXT,
                valueText TEXT,
                valueInt INTEGER
            )
        """)

        # Check if the table is empty
        #cursor.execute("SELECT COUNT(*) FROM Settings")
        #row_count = cursor.fetchone()[0]

        #if row_count == 0:
        #    cursor.execute("INSERT INTO Settings (parameter, type, valueText, valueInt) VALUES (?, ?, ?, ?)", ("DWARF_LOCAL_PATH", "TEXT", "." , 0))
        #    commit_db(conn)
        #    return True

    except Exception as e:
        print(f"[DB ERROR] Failed to migrate DB: {e}")
        return []

def migrate_v3(conn):
    try:
        print("Migrating Database to V3...")
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ManualSession (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_name TEXT NOT NULL,
                session_type TEXT,
                jpeg_path TEXT,
                modification_time INTEGER,
                thumbnail_path TEXT,
                file_size INTEGER,
                description TEXT,
                dec TEXT,
                ra TEXT,
                exp_time TEXT,
                ircut TEXT,
                maxTemp INTEGER,
                minTemp INTEGER,
                stacked_png_path TEXT,
                stacked_fits_path TEXT,
                stacked_fits_md5 TEXT,
                UNIQUE(session_name, session_type)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ManualSessionEntry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                manual_session_id INTEGER,
                backup_drive_id INTEGER,
                dwarf_id INTEGER,
                astro_object_id INTEGER,
                backup_entry_id INTEGER,
                session_date DATETIME,
                session_dir TEXT,
                favorite BOOLEAN DEFAULT 0,
                astro_group_id INTEGER,
                FOREIGN KEY (manual_session_id) REFERENCES ManualSession(id),
                FOREIGN KEY (backup_drive_id) REFERENCES BackupDrive(id),
                FOREIGN KEY (dwarf_id) REFERENCES Dwarf(id),
                FOREIGN KEY (astro_object_id) REFERENCES AstroObject(id),
                FOREIGN KEY (backup_entry_id) REFERENCES BackupEntry(id),
                FOREIGN KEY (astro_group_id) REFERENCES AstroObject(id) ON DELETE SET NULL,
                UNIQUE("manual_session_id","backup_drive_id", "dwarf_id", "backup_entry_id")
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_manualsessionentry_session_dir ON ManualSessionEntry(session_dir);
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_manualsessionentry_astro_group_id ON ManualSessionEntry(astro_group_id);
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_manualsessionentry_manual_session_id ON ManualSessionEntry(manual_session_id);
        """)

        conn.commit()
        print("Migration v3 applied.")

    except Exception as e:
        print(f"[DB ERROR] Failed to migrate DB: {e}")
        return []


MIGRATIONS = {
    1: migrate_v1,
    2: migrate_v2,
    3: migrate_v3
    # Add more later...
}

def run_migrations(conn):
    cursor = conn.cursor()
    current_version = cursor.execute("PRAGMA user_version").fetchone()[0]
    print(f"Current DB version: {current_version}")

    for version in sorted(MIGRATIONS):
        if version > current_version:
            print(f" Applying migration v{version}...")
            MIGRATIONS[version](conn)
            cursor.execute(f"PRAGMA user_version = {version}")
            conn.commit()

def is_new_database(conn):
    """Returns True if the database contains no user-defined tables."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name NOT LIKE 'sqlite_%';
    """)
    return cursor.fetchone() is None

def has_column(conn, table_name, column_name):
    cursor = conn.cursor()

    """Check if a table contains a specific column"""
    cursor.execute(f"PRAGMA table_info({table_name})")
    return any(col[1] == column_name for col in cursor.fetchall())

def add_column_if_not_exists(conn, table_name, column_name, column_type):
    cursor = conn.cursor()
    
    # Get current columns
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]

    if column_name not in columns:
        print(f"Adding column '{column_name}' to '{table_name}'...")
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
        conn.commit()
    else:
        print(f"Column '{column_name}' already exists in '{table_name}'.")

def has_foreign_key(conn, table_name, column_name, ref_table=None, ref_column=None):
    """
    Check if a specific column in a table has a foreign key constraint.
    Optionally check target table and column.
    """
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA foreign_key_list({table_name})")
    fks = cursor.fetchall()
    
    for fk in fks:
        # fk = (id, seq, table, from, to, on_update, on_delete, match)
        if fk[3] == column_name:
            if ref_table and fk[2] != ref_table:
                continue
            if ref_column and fk[4] != ref_column:
                continue
            return True
    return False

def get_unique_constraints(cursor, table_name):
    result = cursor.execute(f'SELECT sql FROM sqlite_master WHERE type="table" AND name="{table_name}"').fetchone()
    if not result or not result[0]:
        return []

    sql = result[0]
    unique_constraints = []

    for line in sql.splitlines():
        line = line.strip().rstrip(',')
        if line.upper().startswith("UNIQUE"):
            unique_constraints.append(line)

    return unique_constraints

def add_missing_foreign_keys(conn, table_name, foreign_keys):
    cursor = conn.cursor()
    
    # 1. Get existing FKs
    cursor.execute(f"PRAGMA foreign_key_list({table_name})")
    existing_fks = cursor.fetchall()

    def fk_exists(column, ref_table, ref_column):
        for fk in existing_fks:
            if fk[3] == column and fk[2] == ref_table and fk[4] == ref_column:
                return True
        return False

    # 2. Filter out already-existing FKs
    missing_fks = [
        fk for fk in foreign_keys
        if not fk_exists(fk["column"], fk["ref_table"], fk["ref_column"])
    ]

    if not missing_fks:
        print(f"All foreign keys already exist in {table_name}")
        return

    print(f"[WARN] Missing FKs in {table_name}, rebuilding table...")

    # 3. Get existing column definitions
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns_info = cursor.fetchall()
    old_columns = [col[1] for col in columns_info]
    column_defs = []
    pk_columns = []

    for col in columns_info:
        name, col_type, notnull, dflt_value, pk = col[1], col[2], col[3], col[4], col[5]
        col_def = f'"{name}" {col_type}'
        if notnull:
            col_def += " NOT NULL"
        if dflt_value is not None:
            col_def += f" DEFAULT {dflt_value}"
        column_defs.append(col_def)
        if pk:
            pk_columns.append(name)

    if pk_columns:
        column_defs.append(f"PRIMARY KEY ({', '.join(pk_columns)})")

    # 4. Add ALL expected FKs (both existing and missing)
    all_fks = foreign_keys  # You could optionally merge with existing FKs if needed

    for fk in all_fks:
        fk_def = (
            f'FOREIGN KEY("{fk["column"]}") '
            f'REFERENCES {fk["ref_table"]}({fk["ref_column"]})'
        )
        if "on_delete" in fk and fk["on_delete"]:
            fk_def += f' ON DELETE {fk["on_delete"]}'
        column_defs.append(fk_def)

    # 5. Add UNIQUE constraints
    unique_constraints = get_unique_constraints(cursor, table_name)
    column_defs.extend(unique_constraints)

    # 6. Rename table
    old_table = f"{table_name}_old"
    cursor.execute(f'ALTER TABLE "{table_name}" RENAME TO "{old_table}"')

    # 7. Recreate table
    create_stmt = f'CREATE TABLE "{table_name}" (\n    ' + ',\n    '.join(column_defs) + '\n);'
    print("Executing:\n", create_stmt)
    cursor.execute(create_stmt)

    # 8. Copy data back
    col_list = ", ".join(f'"{col}"' for col in old_columns)
    cursor.execute(f'INSERT INTO "{table_name}" ({col_list}) SELECT {col_list} FROM "{old_table}";')

    # 9. Drop backup
    cursor.execute(f'DROP TABLE "{old_table}";')
    conn.commit()

    print(f"Table '{table_name}' rebuilt with all declared foreign keys.")

## Other functions

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
def count_catalog_elements():
    with open(CATALOG_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return len(data)

def import_dso_catalog(conn):
    try:
        cursor = conn.cursor()

        with open(CATALOG_FILE, 'r', encoding='utf-8') as f:
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
