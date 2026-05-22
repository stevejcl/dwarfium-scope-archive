"""
db_backup.py — Database backup utilities for Dwarfium Scope Archive.

Two auto backup files:
- dwarf_backup.db.bak  : created at STARTUP (before any migration) — safe clean state
- dwarf_backup.db.last : created at SHUTDOWN — last known state before exit

Manual backup: copies the DB to a user-chosen folder with a timestamped name.
"""

import os
import shutil
from datetime import datetime
from api.dwarf_backup_db import DB_NAME


def _db_path() -> str:
    return os.path.abspath(DB_NAME)


def auto_backup_db() -> str | None:
    """
    Create db/dwarf_backup.db.bak next to the DB file.
    Called at STARTUP only (before any migration).
    Returns the backup path on success, None on failure.
    """
    src = _db_path()
    if not os.path.exists(src):
        return None
    bak = src + ".bak"
    try:
        shutil.copy2(src, bak)
        print(f"[DB backup] Startup backup → {bak}")
        return bak
    except Exception as e:
        print(f"[DB backup] Startup backup failed: {e}")
        return None


def shutdown_backup_db() -> str | None:
    """
    Create db/dwarf_backup.db.last next to the DB file.
    Called at SHUTDOWN only — does NOT overwrite .bak (startup clean state).
    Returns the backup path on success, None on failure.
    """
    src = _db_path()
    if not os.path.exists(src):
        return None
    last = src + ".last"
    try:
        shutil.copy2(src, last)
        print(f"[DB backup] Shutdown backup → {last}")
        return last
    except Exception as e:
        print(f"[DB backup] Shutdown backup failed: {e}")
        return None


def manual_backup_db(dest_folder: str) -> str | None:
    """
    Copy the DB to dest_folder with a timestamped filename.
    e.g. dwarf_backup_20260522_153045.db
    Returns the backup path on success, None on failure.
    """
    src = _db_path()
    if not os.path.exists(src):
        print(f"[DB backup] Source not found: {src}")
        return None

    try:
        os.makedirs(dest_folder, exist_ok=True)
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"dwarf_backup_{ts}.db"
        dest = os.path.join(dest_folder, name)
        shutil.copy2(src, dest)
        print(f"[DB backup] Manual backup → {dest}")
        return dest
    except Exception as e:
        print(f"[DB backup] Manual backup failed: {e}")
        return None


def get_auto_backup_path() -> str:
    """Return the path of the startup backup file (.bak)."""
    return _db_path() + ".bak"


def get_last_backup_path() -> str:
    """Return the path of the shutdown backup file (.last)."""
    return _db_path() + ".last"
