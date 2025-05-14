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
from cli.dwarf_backup_ui import ConfigApp 
from api.dwarf_backup_fct import scan_backup_folder

from api.dwarf_backup_db import DB_NAME, connect_db, init_db, close_db, get_backup_entries, get_astro_object_summary

def show_backup_entries(conn):
    rows = get_backup_entries(conn)
    
    for row in rows:
        print(f"ID: {row[0]}")
        print(f"  Session Date: {row[1]}")
        print(f"  Astro Object: {row[2]}")
        print(f"  File Path: {row[3]}")
        print(f"  Dwarf: {row[4]}")
        print(f"  Backup Drive: {row[5]} ({row[6]})")
        print("-" * 40)

def show_astro_object_summary(conn):

    for name, count in get_astro_object_summary(conn):
        print(f"{name}: {count} file(s)")

def main():
    parser = argparse.ArgumentParser(description="Dwarf Backup Tool (Minimal CLI)")
    parser.add_argument("--gui", action="store_true", help="Launch the GUI for viewing Dwarf backup data")
    parser.add_argument("--dwarf-id", type=int, default=None, help="ID of the Dwarf device")
    parser.add_argument("--db", help="Database file", default=DB_NAME)
    parser.add_argument("folder", nargs="?", help="Backup folder to scan")
    args = parser.parse_args()


    if args.gui:
        # Launch the Tkinter GUI
        root = tk.Tk()
        app = ConfigApp(root, args.db)
        root.mainloop()

    # Connect to the database
    conn = connect_db(args.db)
    init_db(conn)

    if not args.folder:
        show_astro_object_summary(conn)
        show_backup_entries(conn)
    elif not os.path.exists(args.folder):
        print(f"❌ Folder does not exist: {args.folder}")

    else:
        backup_drive_id, dwarf_id = insert_or_get_backup_drive(conn, args.folder, args.dwarf_id)

        close_db(conn)
        print(f"🔍 Scanning: {args.folder}")
        total, deleted = scan_backup_folder(args.db, args.folder, None, dwarf_id, backup_drive_id)
        if deleted and deleted > 1:
            print(f"✅ Scan complete! {total} FITS file(s) indexed, {deleted} file is not more present.")
        elif deleted == 1:
            print(f"✅ Scan complete! {total} FITS file(s) indexed, {deleted} files are not more present.")
        else:
            print(f"✅ Scan complete! {total} FITS file(s) indexed.")
        print(f"📦 Database saved to: {args.db}")
        conn = connect_db(args.db)
        print("")
        show_astro_object_summary(conn)

    close_db(conn)

if __name__ == "__main__":
    main()
