#!/usr/bin/env python3
"""
Dwarfium Scope Archive — Duplicate Cleanup Tool
Keeps only the .jpg entry when a basename exists with multiple extensions.
Removes associated DwarfEntry and BackupEntry rows.

Usage:
    python tools/db_cleanup_dupes.py                  # dry-run (safe, no changes)
    python tools/db_cleanup_dupes.py --execute         # apply deletions
    python tools/db_cleanup_dupes.py --db path/to/db  # custom DB path
"""

import sqlite3
import shutil
import os
import sys
import argparse
from datetime import datetime

# ── Colors ───────────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):   print(f"  {GREEN}✔{RESET}  {msg}")
def warn(msg): print(f"  {YELLOW}⚠{RESET}  {msg}")
def fail(msg): print(f"  {RED}✘{RESET}  {msg}")
def info(msg): print(f"  {CYAN}ℹ{RESET}  {msg}")
def dry(msg):  print(f"  {YELLOW}~{RESET}  [DRY-RUN] {msg}")

def section(title):
    print(f"\n{BOLD}{CYAN}{'─'*60}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{'─'*60}{RESET}")

PREFERRED_EXT = {'.jpg', '.jpeg'}

# ── Helpers ───────────────────────────────────────────────────────────────────
def connect(db_path):
    if not os.path.exists(db_path):
        fail(f"DB file not found: {db_path}")
        sys.exit(1)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def backup_db(db_path):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path + f".backup_{ts}"
    shutil.copy2(db_path, backup_path)
    ok(f"Backup created: {backup_path}")
    return backup_path

def strip_ext(path):
    return os.path.splitext(path)[0].lower()

# ── Find duplicates ───────────────────────────────────────────────────────────
def find_duplicate_groups(conn):
    """
    Returns list of groups:
    Each group = list of (dd_id, file_path, ext) sharing the same basename.
    """
    rows = conn.execute("""
        SELECT id, file_path
        FROM DwarfData
        WHERE file_path IS NOT NULL AND file_path != ''
        ORDER BY file_path
    """).fetchall()

    # Group by stripped basename
    groups = {}
    for dd_id, path in rows:
        base = strip_ext(path)
        groups.setdefault(base, []).append((dd_id, path, os.path.splitext(path)[1].lower()))

    return [g for g in groups.values() if len(g) > 1]


def pick_keeper(group):
    """
    From a group of (dd_id, path, ext), return the one to KEEP.
    Priority: .jpg > .jpeg > first alphabetically.
    """
    for ext in ['.jpg', '.jpeg']:
        for item in group:
            if item[2] == ext:
                return item
    # fallback: keep first alphabetically
    return sorted(group, key=lambda x: x[1])[0]


# ── Main logic ────────────────────────────────────────────────────────────────
def run(db_path, execute):
    conn = connect(db_path)

    section("Scanning for duplicates")
    groups = find_duplicate_groups(conn)

    if not groups:
        ok("No duplicates found — nothing to do.")
        conn.close()
        return

    warn(f"{len(groups)} duplicate group(s) found")

    total_dd   = 0
    total_de   = 0
    total_be   = 0
    to_delete  = []   # list of dd_ids to delete

    for group in groups:
        keeper = pick_keeper(group)
        victims = [item for item in group if item[0] != keeper[0]]

        print(f"\n  Group:")
        print(f"    {GREEN}KEEP{RESET}  DwarfData.id={keeper[0]}  {keeper[2]:7}  {keeper[1]}")

        for dd_id, path, ext in victims:
            # Count linked entries
            de_count = conn.execute(
                "SELECT COUNT(*) FROM DwarfEntry WHERE dwarf_data_id=?", (dd_id,)
            ).fetchone()[0]
            be_count = conn.execute(
                "SELECT COUNT(*) FROM BackupEntry WHERE dwarf_data_id=?", (dd_id,)
            ).fetchone()[0]

            print(f"    {RED}DEL{RESET}   DwarfData.id={dd_id}  {ext:7}  {path}")
            print(f"          → DwarfEntry: {de_count} row(s)  "
                  f"BackupEntry: {be_count} row(s) will be deleted")

            to_delete.append(dd_id)
            total_dd += 1
            total_de += de_count
            total_be += be_count

    section("Summary")
    info(f"DwarfData rows to delete  : {total_dd}")
    info(f"DwarfEntry rows to delete : {total_de}")
    info(f"BackupEntry rows to delete: {total_be}")

    if not execute:
        print(f"\n{YELLOW}{BOLD}  DRY-RUN mode — no changes made.{RESET}")
        print(f"  Run with {BOLD}--execute{RESET} to apply deletions.\n")
        conn.close()
        return

    # ── Execute ───────────────────────────────────────────────────────────────
    section("Backing up DB before changes")
    backup_db(db_path)

    section("Applying deletions")
    try:
        conn.execute("BEGIN")

        deleted_de = 0
        deleted_be = 0
        deleted_dd = 0

        for dd_id in to_delete:
            # Delete DwarfEntry first (FK)
            r = conn.execute(
                "DELETE FROM DwarfEntry WHERE dwarf_data_id=?", (dd_id,))
            deleted_de += r.rowcount

            # Delete BackupEntry (FK)
            r = conn.execute(
                "DELETE FROM BackupEntry WHERE dwarf_data_id=?", (dd_id,))
            deleted_be += r.rowcount

            # Delete DwarfData
            r = conn.execute(
                "DELETE FROM DwarfData WHERE id=?", (dd_id,))
            deleted_dd += r.rowcount

        conn.execute("COMMIT")

        ok(f"Deleted {deleted_de} DwarfEntry row(s)")
        ok(f"Deleted {deleted_be} BackupEntry row(s)")
        ok(f"Deleted {deleted_dd} DwarfData row(s)")

        # Verify integrity
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if result == "ok":
            ok("DB integrity check passed after cleanup")
        else:
            fail(f"DB integrity check FAILED: {result}")

    except Exception as e:
        conn.execute("ROLLBACK")
        fail(f"Error during deletion — ROLLBACK applied: {e}")
        sys.exit(1)

    conn.close()
    print(f"\n{GREEN}{BOLD}  Cleanup complete.{RESET}\n")


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Dwarfium DB — Remove duplicate file_path entries, keep .jpg"
    )
    parser.add_argument(
        "--db", default=os.path.join("db", "dwarf_backup.db"),
        help="Path to the SQLite database"
    )
    parser.add_argument(
        "--execute", action="store_true",
        help="Actually apply deletions (default is dry-run)"
    )
    args = parser.parse_args()

    print(f"\n{BOLD}{'═'*60}{RESET}")
    print(f"{BOLD}  Dwarfium — Duplicate Cleanup Tool{RESET}")
    print(f"{BOLD}  {datetime.now():%Y-%m-%d %H:%M:%S}{RESET}")
    if not args.execute:
        print(f"{YELLOW}{BOLD}  MODE: DRY-RUN (no changes will be made){RESET}")
    else:
        print(f"{RED}{BOLD}  MODE: EXECUTE (deletions will be applied!){RESET}")
    print(f"{BOLD}{'═'*60}{RESET}\n")

    run(args.db, args.execute)


if __name__ == "__main__":
    main()
