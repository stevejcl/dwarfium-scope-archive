import sqlite3
import os
import re
# Encoding changed to UTF-8
DB_NAME = os.path.join("db", "dwarf_backup.db")
CATALOG_FILE = os.path.join("db", "dso_catalog.json")

def create_DsoCatalog_sql():
    return """
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
        """

def create_MtpDevices_sql():
    return """
        CREATE TABLE IF NOT EXISTS MtpDevices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_name TEXT,
            mtp_drive_id TEXT
        )
        """

def create_AstroObject_sql():
    return """
        CREATE TABLE IF NOT EXISTS AstroObject (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            dso_id INTEGER REFERENCES DsoCatalog(id),
            dec TEXT,
            ra TEXT,
            is_group BOOLEAN DEFAULT 0
        )
        """

def create_Dwarf_sql():
    return """
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
        """

def create_DwarfData_sql():
    return """
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
        """

def create_DwarfEntry_sql():
    return """
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
        """

def create_BackupDrive_sql():
    return """
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
        """

def create_BackupEntry_sql():
    return """
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
        """

def create_Settings_sql():
    return """
        CREATE TABLE IF NOT EXISTS Settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parameter TEXT UNIQUE,
            type TEXT,
            valueText TEXT,
            valueInt INTEGER
        )
        """

def create_DarkLibrary_sql():
    return """
        CREATE TABLE IF NOT EXISTS DarkLibrary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            location TEXT UNIQUE,
            backup_drive_id INTEGER,
            last_scan_date DATETIME,
            FOREIGN KEY (backup_drive_id) REFERENCES BackupDrive(id) ON DELETE SET NULL
        )
        """


def create_ManualSessionDrive_sql():
    return """
        CREATE TABLE IF NOT EXISTS ManualSessionDrive (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            description TEXT,
            location TEXT UNIQUE,
            manualsession_dir TEXT,
            backup_drive_id INTEGER,
            last_backup_scan_date DATETIME,
            FOREIGN KEY (backup_drive_id) REFERENCES BackupDrive(id) ON DELETE SET NULL
        )
        """

def create_ManualSession_sql():
    return """
        CREATE TABLE IF NOT EXISTS ManualSession (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_name TEXT NOT NULL,
            session_tag TEXT DEFAULT '',
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
            UNIQUE("session_name", "session_tag", "session_type")
        )
        """

def create_ManualSessionEntry_sql():
    return """
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
            manual_session_drive INTEGER,
            FOREIGN KEY (manual_session_id) REFERENCES ManualSession(id),
            FOREIGN KEY (backup_drive_id) REFERENCES BackupDrive(id),
            FOREIGN KEY (dwarf_id) REFERENCES Dwarf(id),
            FOREIGN KEY (astro_object_id) REFERENCES AstroObject(id),
            FOREIGN KEY (backup_entry_id) REFERENCES BackupEntry(id),
            FOREIGN KEY (astro_group_id) REFERENCES AstroObject(id) ON DELETE SET NULL,
            FOREIGN KEY (manual_session_drive) REFERENCES ManualSessionDrive(id) ON DELETE SET NULL,
            UNIQUE("manual_session_id", "backup_drive_id", "dwarf_id", "backup_entry_id")
        )
        """

SCHEMAS = {
    "DsoCatalog": create_DsoCatalog_sql,
    "AstroObject": create_AstroObject_sql,
    "MtpDevices": create_MtpDevices_sql,
    "Dwarf": create_Dwarf_sql,
    "DwarfData": create_DwarfData_sql,
    "DwarfEntry": create_DwarfEntry_sql,
    "BackupDrive": create_BackupDrive_sql,
    "BackupEntry": create_BackupEntry_sql,
    "Settings": create_Settings_sql,
    "DarkLibrary": create_DarkLibrary_sql,
    "ManualSessionDrive": create_ManualSessionDrive_sql,
    "ManualSession": create_ManualSession_sql,
    "ManualSessionEntry": create_ManualSessionEntry_sql,
}

# Sanity check — catch wrong mappings at import time, not at runtime
assert SCHEMAS["AstroObject"] is create_AstroObject_sql, (
    "SCHEMAS['AstroObject'] must be create_AstroObject_sql — "
    "do not map it to create_DwarfData_sql"
)
  
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

        cursor.execute(create_DsoCatalog_sql())

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

        cursor.execute(create_AstroObject_sql())

        cursor.execute(create_MtpDevices_sql())

        cursor.execute(create_Dwarf_sql())

        cursor.execute(create_DwarfData_sql())

        cursor.execute(create_DwarfEntry_sql())

        cursor.execute(create_BackupDrive_sql())
        cursor.execute(create_BackupEntry_sql())

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_dwarfentry_session_dir ON DwarfEntry(session_dir);
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_backupentry_session_dir ON BackupEntry(session_dir);
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_backupentry_astro_group_id ON BackupEntry(astro_group_id);
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_dwarfentry_astro_group_id ON DwarfEntry(astro_group_id);
        """)

        # Create table for Dark Library
        cursor.execute(create_DarkLibrary_sql())
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_darklibrary_backup_drive_id ON DarkLibrary(backup_drive_id);
        """)

        # Create table for Manual Session Drive
        cursor.execute(create_ManualSessionDrive_sql())

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_manualsessiondrive_location ON ManualSessionDrive(location);
        """)

        cursor.execute(create_ManualSession_sql())

        cursor.execute(create_ManualSessionEntry_sql())

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
    """
    Creates ManualSession and ManualSessionEntry tables (original v3 schema,
    without session_tag and without manual_session_drive column).
    migrate_v4 will upgrade these to the final schema via rebuild_tables,
    so this migration only runs CREATE TABLE IF NOT EXISTS — it is always
    safe to re-run and never overwrites data.
    """
    try:
        print("Migrating Database to V3...")
        cursor = conn.cursor()

        # Use CREATE TABLE IF NOT EXISTS so this is safe even if migrate_v4
        # already ran first (e.g. on a fresh install that jumped straight to v4).
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
                UNIQUE("session_name", "session_type")
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

def migrate_v5(conn):
    try:
        print("Migrating Database to V4...")
        cursor = conn.cursor()

        cursor.execute("PRAGMA foreign_keys = OFF;")

        rebuild_tables( conn, ["Dwarf", "DwarfEntry", "BackupDrive", "BackupEntry"])

        cursor.execute("PRAGMA foreign_keys = ON;")

        # Create table for Manual SessionDrive
        cursor.execute(create_ManualSessionDrive_sql())

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_manualsessiondrive_location ON ManualSessionDrive(location);
        """)

        # Rebuild both ManualSession and ManualSessionEntry using the canonical
        # SQL factory functions. This is cleaner than add_missing_foreign_keys
        # because SQLite's PRAGMA foreign_key_list is unreliable for tables created
        # with CREATE TABLE IF NOT EXISTS. rebuild_tables handles everything:
        # session_tag column, new UNIQUE constraint, and all FKs including
        # manual_session_drive → ManualSessionDrive.
        rebuild_tables(conn, ["ManualSession", "ManualSessionEntry"])

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
        print("Migration v5 applied.")

    except Exception as e:
        print(f"[DB ERROR] Failed to migrate DB: {e}")
        return []


def migrate_v6(conn):
    try:
        print("Migrating Database to V6...")
        cursor = conn.cursor()
        cursor.execute(create_DarkLibrary_sql())
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_darklibrary_backup_drive_id ON DarkLibrary(backup_drive_id);
        """)
        conn.commit()
        print("Migration v6 applied.")
    except Exception as e:
        print(f"[DB ERROR] Failed to migrate DB v6: {e}")
        return []


MIGRATIONS = {
    1: migrate_v1,
    2: migrate_v2,
    3: migrate_v3,
#   4: migrate_v4,  removed
    5: migrate_v5,
    6: migrate_v6,
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

def rename_table(cursor, table_name):
    cursor.execute(f'ALTER TABLE "{table_name}" RENAME TO "{table_name}_old"')
    
def create_table(cursor, table_name):
    cursor.execute(SCHEMAS[table_name]())

def copy_table(cursor, table_name):
    """
    Copy data from table_name_old into table_name.
    Only copies columns that exist in BOTH tables — new columns get their
    DEFAULT values automatically. This handles the case where a migration
    adds columns (e.g. session_tag in ManualSession).
    """
    # Get columns of the OLD table
    cursor.execute(f"PRAGMA table_info({table_name}_old)")
    old_cols = {row[1] for row in cursor.fetchall()}

    # Get columns of the NEW table
    cursor.execute(f"PRAGMA table_info({table_name})")
    new_cols = {row[1] for row in cursor.fetchall()}

    # Only copy columns present in both
    common = [c for c in new_cols if c in old_cols]
    col_list = ", ".join(f'"{c}"' for c in common)

    cursor.execute(f"""
        INSERT INTO "{table_name}" ({col_list})
        SELECT {col_list} FROM "{table_name}_old"
    """)

def drop_old_table(cursor, table_name):
    cursor.execute(f'DROP TABLE "{table_name}_old"')
    
def rebuild_tables(conn, tables):
    cursor = conn.cursor()

    cursor.execute("PRAGMA foreign_keys = OFF")

    # 1 Rename ALL first
    for t in tables:
        print(f"starting rebuild_table: {t}")
        rename_table(cursor, t)

    # 2 Recreate ALL
    for t in tables:
        create_table(cursor, t)

    # 3 Copy data
    for t in tables:
        copy_table(cursor, t)

    # 4 Drop old
    for t in tables:
        drop_old_table(cursor, t)
        print(f"end rebuild_table: {t}")

    cursor.execute("PRAGMA foreign_keys = ON")

    conn.commit()
    

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

def add_missing_foreign_keys(conn, table_name, foreign_keys, unique_constraints_override=None):
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

    needs_rebuild = bool(missing_fks) or (unique_constraints_override is not None)
    if not needs_rebuild:
        print(f"No schema changes needed for {table_name}")
        return

    cursor.execute("PRAGMA foreign_keys = OFF;")

    try:
        print(f"[WARN] Missing FKs in {table_name}, rebuilding table...")

        # 3. Get existing column definitions
        # Keep Auto Increment
        # Get original CREATE TABLE SQL
        cursor.execute("""
            SELECT sql
            FROM sqlite_master
            WHERE type='table' AND name=?
        """, (table_name,))
        create_sql = cursor.fetchone()[0] or ""

        # Detect AUTOINCREMENT column (if any)
        autoinc_column = None

        match = re.search(
            r'"?(\w+)"?\s+INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT',
            create_sql,
            re.IGNORECASE
        )

        if match:
            autoinc_column = match.group(1)

        # Get column metadata
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns_info = cursor.fetchall()

        column_defs = []
        pk_columns = []

        old_columns = [col[1] for col in columns_info]

        for col in columns_info:
            name, col_type, notnull, dflt_value, pk = (
                col[1], col[2], col[3], col[4], col[5]
            )

            col_def = f'"{name}" {col_type}'

            # Case 1: AUTOINCREMENT column (must be inline PK)
            if autoinc_column and name == autoinc_column:
                col_def += " PRIMARY KEY AUTOINCREMENT"

            else:
                # Case 2: normal NOT NULL
                if notnull:
                    col_def += " NOT NULL"

                # Case 3: DEFAULT value (keep as-is)
                if dflt_value is not None:
                    col_def += f" DEFAULT {dflt_value}"

                # Case 4: composite primary key support
                if pk:
                    pk_columns.append(name)

            column_defs.append(col_def)

        # Add composite primary key ONLY if no AUTOINCREMENT column exists
        if pk_columns and not autoinc_column:
            column_defs.append(
                f"PRIMARY KEY ({', '.join(pk_columns)})"
            )

        # 4. Add ALL expected FKs (both existing and missing)
        existing_fks = cursor.execute(f"PRAGMA foreign_key_list({table_name})").fetchall()

        existing_fk_dicts = [
            {
                "column": fk[3],
                "ref_table": fk[2],
                "ref_column": fk[4],
                "on_delete": fk[6] if fk[6] != "NO ACTION" else None
            }
            for fk in existing_fks
            if not fk[2].endswith("_old")
        ]

        def fk_key(fk):
            return (fk["column"], fk["ref_table"], fk["ref_column"])

        merged = {fk_key(fk): fk for fk in existing_fk_dicts}

        for fk in foreign_keys:
            merged[fk_key(fk)] = fk

        all_fks = list(merged.values())

        for fk in all_fks:
            fk_def = (
                f'FOREIGN KEY("{fk["column"]}") '
                f'REFERENCES {fk["ref_table"]}({fk["ref_column"]})'
            )
            if "on_delete" in fk and fk["on_delete"]:
                fk_def += f' ON DELETE {fk["on_delete"]}'
            column_defs.append(fk_def)

        # 5. Add UNIQUE constraints
        if unique_constraints_override is not None:
            # Use new definition
            column_defs.extend(unique_constraints_override)
        else:
            # Keep existing ones
            unique_constraints = get_unique_constraints(cursor, table_name)
            column_defs.extend(unique_constraints)

        # 6. Rename table
        old_table = f"{table_name}_old"
        cursor.execute(f'ALTER TABLE {table_name} RENAME TO {old_table}')

        # 7. Recreate table
        create_stmt = f'CREATE TABLE {table_name} (\n    ' + ',\n    '.join(column_defs) + '\n);'
        print("Executing:\n", create_stmt)
        cursor.execute(create_stmt)

        # 8. Copy data back
        col_list = ", ".join(f'{col}' for col in old_columns)
        cursor.execute(f'INSERT INTO {table_name} ({col_list}) SELECT {col_list} FROM {old_table};')

        # 9. Drop backup
        cursor.execute(f'DROP TABLE {old_table};')
        conn.commit()

        print(f"Table '{table_name}' rebuilt with all declared foreign keys.")

    finally:
        cursor.execute("PRAGMA foreign_keys = ON;")

def rebuild_table(conn, table_name):
    cursor = conn.cursor()

    old = f"{table_name}_old"

    cursor.execute(f'ALTER TABLE "{table_name}" RENAME TO "{old}"')
    cursor.execute(SCHEMAS[table_name]())

    cursor.execute(f"""
        INSERT INTO {table_name}
        SELECT * FROM {old}
    """)

    cursor.execute(f'DROP TABLE {old}')
    conn.commit()
    
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
