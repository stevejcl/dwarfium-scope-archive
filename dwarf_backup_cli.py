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
import tkinter as tk
from dwarf_backup_ui import ConfigApp 
from dwarf_backup_fct import scan_backup_folder

DB_NAME = "dwarf_backup.db"

def init_db(conn):
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

def show_backup_entries(conn):
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
    
    for row in rows:
        print(f"ID: {row[0]}")
        print(f"  Seession Date: {row[1]}")
        print(f"  Astro Object: {row[2]}")
        print(f"  File Path: {row[3]}")
        print(f"  Dwarf: {row[4]}")
        print(f"  Backup Drive: {row[5]} ({row[6]})")
        print("-" * 40)

def show_astro_object_summary(conn):
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
    for name, count in cursor.fetchall():
        print(f"{name}: {count} file(s)")

def main():
    parser = argparse.ArgumentParser(description="Dwarf Backup Tool (Minimal CLI)")
    parser.add_argument("--gui", action="store_true", help="Launch the GUI for viewing Dwarf backup data")
    parser.add_argument("--dwarf-id", type=int, default=None, help="ID of the Dwarf device")
    parser.add_argument("--db", help="Database file", default=DB_NAME)
    parser.add_argument("folder", nargs="?", help="Backup folder to scan")
    args = parser.parse_args()

    # Connect to the database
    conn = sqlite3.connect(args.db)
    init_db(conn)

    if args.gui:
        # Launch the Tkinter GUI
        root = tk.Tk()
        app = ConfigApp(root, conn)
        root.mainloop()

    if not args.folder:
        show_astro_object_summary(conn)
        show_backup_entries(conn)
    elif not os.path.exists(args.folder):
        print(f"❌ Folder does not exist: {args.folder}")

    else:
        backup_drive_id, dwarf_id = insert_or_get_backup_drive(conn, args.folder, args.dwarf_id)

        print(f"🔍 Scanning: {args.folder}")
        total = scan_backup_folder(conn, args.folder, dwarf_id, backup_drive_id)

        print(f"✅ Scan complete! {total} FITS file(s) indexed.")
        print(f"📦 Database saved to: {args.db}")

        print("")
        show_astro_object_summary(conn)

    conn.close()

if __name__ == "__main__":
    main()
