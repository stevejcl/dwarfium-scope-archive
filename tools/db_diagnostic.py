#!/usr/bin/env python3
"""
Dwarfium Scope Archive — DB Diagnostic Tool
Run from project root: python tools/db_diagnostic.py [--db path/to/dwarf_backup.db]
"""

import sqlite3
import re
import shutil
import json
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






def _clean_obj_name(name: str, desc: str = None) -> str:
    """Format object name consistently for reports.
    - Uses description if available, truncated at first comma
    - Removes content in parentheses (type info)
    - Removes duplicate "in Constellation in Constellation" repetitions
    - Replaces underscores with spaces
    - Keeps [original_name] suffix
    """
    if not name:
        return name or ""
    import re as _re
    clean_name = name.replace("_", " ")
    if desc and desc.strip():
        desc_clean = desc.strip().split(",")[0]
        desc_clean = desc_clean.replace("_", " ")
        name_object = f"{desc_clean} [{clean_name}]"
    else:
        name_object = clean_name
    bracket_pos = name_object.rfind(" [")
    suffix = name_object[bracket_pos:] if bracket_pos != -1 else ""
    main_part = name_object[:bracket_pos] if bracket_pos != -1 else name_object
    # Remove content in parentheses
    main_part = _re.sub(r"\s*\([^)]*\)", "", main_part).strip()
    # Remove duplicate "in X in X" -> "in X"
    main_part = _re.sub(r"(\s+in\s+(\S+))\1+", r"\1", main_part).strip()
    if suffix and suffix.strip() not in main_part:
        return f"{main_part} {suffix}".strip()
    return main_part.strip()

    # Replace underscores with spaces in name
    clean_name = name.replace("_", " ")

    if desc and desc.strip():
        # Truncate at first comma
        desc_clean = desc.strip().split(",")[0]
        # Replace underscores
        desc_clean = desc_clean.replace("_", " ")
        name_object = f"{desc_clean} [{clean_name}]"
    else:
        name_object = clean_name

    # Extract suffix [name] if present
    bracket_pos = name_object.rfind(" [")
    suffix = name_object[bracket_pos:] if bracket_pos != -1 else ""
    main_part = name_object[:bracket_pos] if bracket_pos != -1 else name_object

    # Remove content in parentheses
    import re as _re
    main_part = _re.sub(r"\s*\([^)]*\)", "", main_part).strip()

    # Remove " in <Word>" suffix (constellation name)
    main_part = _re.sub(r"\s+in\s+\w+(\s+\w+)?$", "", main_part).strip()

    if suffix and suffix.strip() not in main_part:
        return f"{main_part} {suffix}".strip()
    return main_part.strip()


def ok(msg):   print(f"  {GREEN}✔{RESET}  {msg}")
def warn(msg): print(f"  {YELLOW}⚠{RESET}  {msg}")
def fail(msg): print(f"  {RED}✘{RESET}  {msg}")
def info(msg): print(f"  {CYAN}ℹ{RESET}  {msg}")

def section(title):
    print(f"\n{BOLD}{CYAN}{'─'*54}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'─'*54}{RESET}")

# ── Helpers ───────────────────────────────────────────────────────────────────
def connect(db_path):
    if not os.path.exists(db_path):
        fail(f"DB file not found: {db_path}")
        sys.exit(1)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def table_exists(conn, name):
    cur = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None

def count(conn, table, where=""):
    q = f"SELECT COUNT(*) FROM {table}"
    if where:
        q += f" WHERE {where}"
    return conn.execute(q).fetchone()[0]

# ── Checks ────────────────────────────────────────────────────────────────────

def check_version(conn):
    section("DB Version & Schema")
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    info(f"DB user_version = {version}  (expected: 7)")
    if version < 7:
        warn(f"DB is at version {version} — pending migrations exist (run app to apply)")
    else:
        ok("DB version is up to date")

    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()]
    info(f"Tables found ({len(tables)}): {', '.join(tables)}")

    expected = [
        "AstroObject", "BackupDrive", "BackupEntry", "DarkLibrary",
        "DsoCatalog", "Dwarf", "DwarfData", "DwarfEntry",
        "DwarfSessionsError",
        "ManualSession", "ManualSessionDrive", "ManualSessionEntry",
        "MtpDevices", "Settings"
    ]
    for t in expected:
        if t in tables:
            ok(f"Table {t} present")
        else:
            fail(f"Table {t} MISSING")


def check_counts(conn):
    section("Row Counts")
    tables = {
        "Dwarf":              "Dwarf devices configured",
        "BackupDrive":        "Backup drives configured",
        "DwarfEntry":         "Dwarf session entries",
        "BackupEntry":        "Backup entries",
        "AstroObject":        "Astro objects",
        "DwarfData":          "DwarfData records",
        "DsoCatalog":         "DSO catalog objects",
        "ManualSession":      "Manual sessions",
        "ManualSessionEntry": "Manual session entries",
        "Settings":           "Settings parameters",
        "MtpDevices":         "MTP devices",
        "DarkLibrary":        "Dark library entries",
    }
    for table, label in tables.items():
        if table_exists(conn, table):
            n = count(conn, table)
            color = GREEN if n > 0 else YELLOW
            print(f"  {color}{n:>8}{RESET}  {label}")


def check_integrity(conn):
    section("DB Integrity")

    result = conn.execute("PRAGMA integrity_check").fetchall()
    if result == [("ok",)]:
        ok("integrity_check passed")
    else:
        for row in result:
            fail(f"integrity_check: {row[0]}")

    fk_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
    if not fk_errors:
        ok("No foreign key violations")
    else:
        for e in fk_errors:
            fail(f"FK violation — table={e[0]}, rowid={e[1]}, parent={e[2]}")


def check_orphans(conn):
    section("Orphan Records")

    checks = [
        ("DwarfEntry → DwarfData",
         "SELECT COUNT(*) FROM DwarfEntry "
         "WHERE dwarf_data_id NOT IN (SELECT id FROM DwarfData)"),
        ("DwarfEntry → AstroObject",
         "SELECT COUNT(*) FROM DwarfEntry "
         "WHERE astro_object_id NOT IN (SELECT id FROM AstroObject)"),
        ("DwarfEntry → Dwarf",
         "SELECT COUNT(*) FROM DwarfEntry "
         "WHERE dwarf_id NOT IN (SELECT id FROM Dwarf)"),
        ("BackupEntry → DwarfData",
         "SELECT COUNT(*) FROM BackupEntry "
         "WHERE dwarf_data_id NOT IN (SELECT id FROM DwarfData)"),
        ("BackupEntry → BackupDrive",
         "SELECT COUNT(*) FROM BackupEntry "
         "WHERE backup_drive_id NOT IN (SELECT id FROM BackupDrive)"),
        ("ManualSessionEntry → ManualSession",
         "SELECT COUNT(*) FROM ManualSessionEntry "
         "WHERE manual_session_id NOT IN (SELECT id FROM ManualSession)"),
        ("DwarfData with empty file_path",
         "SELECT COUNT(*) FROM DwarfData "
         "WHERE file_path IS NULL OR file_path = ''"),
    ]

    for label, query in checks:
        try:
            n = conn.execute(query).fetchone()[0]
            if n == 0:
                ok(f"{label}: none")
            else:
                warn(f"{label}: {n} orphan(s) found")
        except Exception as e:
            fail(f"{label}: query error — {e}")


def check_duplicates(conn):
    section("Duplicate Detection")

    checks = [
        ("DwarfData duplicate file_path",
         "SELECT file_path, COUNT(*) c FROM DwarfData "
         "GROUP BY file_path HAVING c > 1"),
        ("AstroObject duplicate names",
         "SELECT name, COUNT(*) c FROM AstroObject "
         "GROUP BY name HAVING c > 1"),
        ("Settings duplicate parameters",
         "SELECT parameter, COUNT(*) c FROM Settings "
         "GROUP BY parameter HAVING c > 1"),
        ("BackupDrive duplicate locations",
         "SELECT location, COUNT(*) c FROM BackupDrive "
         "GROUP BY location HAVING c > 1"),
    ]

    for label, query in checks:
        try:
            rows = conn.execute(query).fetchall()
            if not rows:
                ok(f"{label}: none")
            else:
                warn(f"{label}: {len(rows)} duplicate group(s)")
                for row in rows[:5]:
                    print(f"         → {str(row[0])[:70]}  (×{row[1]})")
        except Exception as e:
            fail(f"{label}: query error — {e}")


def check_settings(conn):
    section("Key Settings")

    key_settings = [
        "DWARF_LOCAL_PATH",
        "NOVA_ASTRO_API",
        "STITCH_PARAMS",
    ]
    for param in key_settings:
        row = conn.execute(
            "SELECT valueText, valueInt FROM Settings WHERE parameter=?",
            (param,)
        ).fetchone()
        if row:
            val = (row[0] or str(row[1]) or "").strip()
            if val:
                # Mask API key
                display = val[:4] + "****" + val[-4:] if param == "NOVA_ASTRO_API" and len(val) > 8 else val[:80]
                ok(f"{param} = {display}")
            else:
                warn(f"{param} is set but empty")
        else:
            warn(f"{param} not configured")

    # Show all settings
    all_settings = conn.execute(
        "SELECT parameter, type, valueText, valueInt FROM Settings ORDER BY parameter"
    ).fetchall()
    if all_settings:
        info(f"All settings ({len(all_settings)}):")
        for param, typ, vtext, vint in all_settings:
            val = vtext if typ == "TEXT" else str(vint)
            print(f"    {param:30}  = {str(val)[:60]}")


def check_dso_catalog(conn):
    section("DSO Catalog")

    n = count(conn, "DsoCatalog")
    if n > 0:
        ok(f"DsoCatalog has {n} objects")
    else:
        fail("DsoCatalog is EMPTY — catalog import may have failed")
        return

    cats = conn.execute(
        "SELECT catalogue, COUNT(*) c FROM DsoCatalog "
        "GROUP BY catalogue ORDER BY c DESC LIMIT 8"
    ).fetchall()
    for cat, c in cats:
        info(f"  {(cat or 'NULL'):15} {c} objects")


def check_files_on_disk(conn):
    section("File Existence Spot-Check (first 20 DwarfData records)")

    # Only check DwarfData linked to a BackupDrive (has a physical location)
    # Entries without a BackupEntry are on the Dwarf device itself — skip them
    rows = conn.execute("""
        SELECT
            DD.id,
            DD.file_path,
            BD.location AS drive_location,
            BD.name     AS drive_name
        FROM DwarfData DD
        INNER JOIN BackupEntry BE ON BE.dwarf_data_id = DD.id
        INNER JOIN BackupDrive BD ON BD.id = BE.backup_drive_id
        WHERE DD.file_path IS NOT NULL
          AND BD.location IS NOT NULL
        GROUP BY DD.id
        ORDER BY DD.id DESC
        LIMIT 20
    """).fetchall()

    if not rows:
        warn("No backup drive DwarfData records to check "
             "(entries on Dwarf device are skipped)")
        return

    missing = 0
    for dd_id, rel_path, drive_loc, drive_name in rows:
        full_path = os.path.join(drive_loc, rel_path)
        label = f"[{drive_name}] {full_path}"
        if os.path.exists(full_path):
            ok(f"EXISTS   {label}")
        else:
            warn(f"MISSING  {label}")
            missing += 1

    if missing == 0:
        ok("All spot-checked files found on disk")
    else:
        warn(f"{missing}/{len(rows)} files not found "
             f"(drive may be disconnected)")


def check_recent_activity(conn):
    section("Recent Activity")

    rows = conn.execute("""
        SELECT DE.session_date, AO.name, DD.file_path
        FROM DwarfEntry DE
        LEFT JOIN AstroObject AO ON DE.astro_object_id = AO.id
        LEFT JOIN DwarfData DD ON DE.dwarf_data_id = DD.id
        ORDER BY DE.session_date DESC LIMIT 5
    """).fetchall()

    if rows:
        info("Last 5 Dwarf sessions:")
        for date, obj, path in rows:
            print(f"    {(date or '?'):20}  {(obj or '?'):20}  {(path or '')}")
    else:
        warn("No DwarfEntry records found")

    rows = conn.execute("""
        SELECT BE.session_date, AO.name, BD.name
        FROM BackupEntry BE
        LEFT JOIN AstroObject AO ON BE.astro_object_id = AO.id
        LEFT JOIN BackupDrive BD ON BE.backup_drive_id = BD.id
        ORDER BY BE.session_date DESC LIMIT 5
    """).fetchall()

    if rows:
        info("Last 5 Backup entries:")
        for date, obj, drive in rows:
            print(f"    {(date or '?'):20}  {(obj or '?'):20}  "
                  f"drive: {drive or '?'}")
    else:
        warn("No BackupEntry records found")


def check_dwarf_devices(conn):
    section("Dwarf Devices & Backup Drives")

    dwarfs = conn.execute(
        "SELECT id, name, type, ip_sta_mode, last_scan_date FROM Dwarf"
    ).fetchall()
    if dwarfs:
        for d in dwarfs:
            info(f"Dwarf [{d[0]}] {d[1]}  type={d[2]}  ip={d[3]}  "
                 f"last_scan={d[4]}")
    else:
        warn("No Dwarf devices configured")

    drives = conn.execute("""
        SELECT BD.id, BD.name, BD.location, BD.last_backup_scan_date, D.name AS dwarf_name
        FROM BackupDrive BD
        LEFT JOIN Dwarf D ON BD.dwarf_id = D.id
    """).fetchall()
    if drives:
        for d in drives:
            did, dname, loc, last_scan, dwarf_name = d
            exists = os.path.exists(loc) if loc else False
            status = f"{GREEN}online{RESET}" if exists else f"{YELLOW}offline{RESET}"
            dwarf_str = f"  [{dwarf_name}]" if dwarf_name else ""
            if exists and loc:
                try:
                    usage = shutil.disk_usage(d[2])
                    total_gb = usage.total / 1024**3
                    free_gb  = usage.free  / 1024**3
                    used_pct = (usage.used / usage.total) * 100
                    disk_info = (f"  {free_gb:.1f} GB free / "
                                 f"{total_gb:.1f} GB total  ({used_pct:.0f}% used)")
                except Exception:
                    disk_info = "  (disk info unavailable)"
            else:
                disk_info = ""
            info(f"BackupDrive [{did}] {dname}{dwarf_str}  {status}{disk_info}")
            if loc:
                print(f"    location: {loc}")
            if last_scan:
                print(f"    last scan: {last_scan}")
    else:
        warn("No backup drives configured")



def check_same_basename_diff_ext(conn):
    section("Same Basename / Different Extension (DwarfData)")

    rows = conn.execute("""
        SELECT
            LOWER(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
                file_path,
                '.fits', ''), '.fit', ''), '.jpg', ''),
                '.jpeg', ''), '.png', '')) AS base_path,
            COUNT(*) AS c
        FROM DwarfData
        GROUP BY base_path
        HAVING c > 1
        ORDER BY c DESC
        LIMIT 30
    """).fetchall()

    if not rows:
        ok("No same-basename / different-extension duplicates found")
        return

    warn(f"{len(rows)} basename group(s) with multiple extensions:")

    for base, c in rows:
        print(f"\n    Base: {base}")

        # Get full details for each file in this group
        files = conn.execute("""
            SELECT id, file_path, file_size, modification_time
            FROM DwarfData
            WHERE LOWER(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
                file_path,
                '.fits', ''), '.fit', ''), '.jpg', ''),
                '.jpeg', ''), '.png', '')) = ?
            ORDER BY file_path
        """, (base,)).fetchall()

        for dd_id, path, size, mtime in files:
            ext = os.path.splitext(path)[1]
            size_str = f"{size:,} bytes" if size else "?"
            mtime_str = str(mtime) if mtime else "?"
            print(f"      DwarfData.id={dd_id}  {ext:7}  size={size_str:15}  mtime={mtime_str}")
            print(f"        path: {path}")

            # DwarfEntry linked
            de_rows = conn.execute("""
                SELECT DE.id, DE.dwarf_id, DE.astro_object_id, DE.session_date,
                       AO.name, D.name
                FROM DwarfEntry DE
                LEFT JOIN AstroObject AO ON DE.astro_object_id = AO.id
                LEFT JOIN Dwarf D ON DE.dwarf_id = D.id
                WHERE DE.dwarf_data_id = ?
            """, (dd_id,)).fetchall()
            for de in de_rows:
                print(f"        → DwarfEntry.id={de[0]}  dwarf_id={de[1]}  "
                      f"object='{de[4] or '?'}'  dwarf='{de[5] or '?'}'  date={de[3]}")

            # BackupEntry linked
            be_rows = conn.execute("""
                SELECT BE.id, BE.backup_drive_id, BE.astro_object_id, BE.session_date,
                       AO.name, BD.name
                FROM BackupEntry BE
                LEFT JOIN AstroObject AO ON BE.astro_object_id = AO.id
                LEFT JOIN BackupDrive BD ON BE.backup_drive_id = BD.id
                WHERE BE.dwarf_data_id = ?
            """, (dd_id,)).fetchall()
            for be in be_rows:
                print(f"        → BackupEntry.id={be[0]}  backup_drive_id={be[1]}  "
                      f"object='{be[4] or '?'}'  drive='{be[5] or '?'}'  date={be[3]}")

def check_storage_json():
    section("NiceGUI Storage JSON")
    storage_path = os.path.join(".nicegui", "storage-general.json")

    if not os.path.exists(storage_path):
        warn(f"Not found: {storage_path}")
        return

    size = os.path.getsize(storage_path)
    mtime = datetime.fromtimestamp(os.path.getmtime(storage_path))
    info(f"File: {storage_path}  ({size} bytes)  modified: {mtime:%Y-%m-%d %H:%M:%S}")

    if size == 0:
        fail("Storage file is EMPTY — corruption detected!")
        return

    try:
        with open(storage_path, "r", encoding="utf-8") as f:
            raw = f.read().strip()
        data = json.loads(raw)
        ok(f"JSON valid — {len(data)} keys")
        for k, v in list(data.items())[:15]:
            print(f"    {k:30} = {str(v)[:60]}")
    except json.JSONDecodeError as e:
        fail(f"JSON CORRUPT: {e}")


# ── Summary ───────────────────────────────────────────────────────────────────



def check_sessions_error(conn):
    section("DwarfSessionsError — Missing Stacked / Errors")

    if not table_exists(conn, "DwarfSessionsError"):
        warn("Table DwarfSessionsError not found (evolution-test only)")
        return

    total   = count(conn, "DwarfSessionsError")
    errors  = count(conn, "DwarfSessionsError", "status = 'ERROR'")
    repaired = count(conn, "DwarfSessionsError", "status = 'REPAIRED'")
    other   = total - errors - repaired

    info(f"Total  : {total}")
    color_e = RED    if errors   > 0 else GREEN
    color_r = GREEN  if repaired > 0 else YELLOW
    print(f"  {color_e}{errors:>6}{RESET}  ERROR    (missing stacked — not yet repaired)")
    print(f"  {color_r}{repaired:>6}{RESET}  REPAIRED (stacked recovered)")
    if other > 0:
        print(f"  {YELLOW}{other:>6}{RESET}  OTHER status")

    # Show ERROR entries
    error_rows = conn.execute("""
        SELECT SE.id, SE.session_date, SE.session_dir,
               SE.session_dir_master, D.name
        FROM DwarfSessionsError SE
        LEFT JOIN Dwarf D ON SE.dwarf_id = D.id
        WHERE SE.status = 'ERROR'
        ORDER BY SE.session_date DESC
        LIMIT 20
    """).fetchall()

    if error_rows:
        print(f"\n  {RED}ERROR sessions (up to 20):{RESET}")
        for row in error_rows:
            se_id, date, session_dir, master, dwarf_name = row
            print(f"    id={se_id}  date={date or '?':20}  dwarf={dwarf_name or '?'}")
            print(f"      session_dir: {session_dir}")
            if master:
                print(f"      master:      {master}")

    # Show REPAIRED entries
    repaired_rows = conn.execute("""
        SELECT SE.id, SE.session_date, SE.session_dir,
               SE.session_dir_master, D.name
        FROM DwarfSessionsError SE
        LEFT JOIN Dwarf D ON SE.dwarf_id = D.id
        WHERE SE.status = 'REPAIRED'
        ORDER BY SE.session_date DESC
        LIMIT 10
    """).fetchall()

    if repaired_rows:
        print(f"\n  {GREEN}REPAIRED sessions (up to 10):{RESET}")
        for row in repaired_rows:
            se_id, date, session_dir, master, dwarf_name = row
            print(f"    id={se_id}  date={date or '?':20}  dwarf={dwarf_name or '?'}")
            print(f"      session_dir: {session_dir}")
            if master:
                print(f"      repaired by: {master}")

def check_repair_history(conn):
    section("Repair / Merge Session History")

    # Find temp_root from Settings (DWARF_LOCAL_PATH as base, or dedicated setting)
    # RepairSessionManager uses a temp_root dir — find it from BackupDrive locations
    drives = conn.execute(
        "SELECT location, name FROM BackupDrive WHERE location IS NOT NULL"
    ).fetchall()

    candidates = []
    for loc, name in drives:
        candidate = os.path.join(loc, "temp_mosaic_repair")
        if os.path.exists(candidate):
            candidates.append((candidate, name))

    # Also check DWARF_LOCAL_PATH
    local_path = conn.execute(
        "SELECT valueText FROM Settings WHERE parameter='DWARF_LOCAL_PATH'"
    ).fetchone()
    if local_path and local_path[0]:
        candidate = os.path.join(local_path[0], "temp_mosaic_repair")
        if os.path.exists(candidate):
            candidates.append((candidate, "Dwarf Local"))

    if not candidates:
        info("Repair history directory not found — Dwarf device may not be connected")
        return

    for temp_root, drive_name in candidates:
        actions_file = os.path.join(temp_root, "actions.json")
        info(f"Repair history: [{drive_name}] {actions_file}")

        if not os.path.exists(actions_file):
            warn("  actions.json not found — no repairs recorded yet")
            continue

        try:
            with open(actions_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            fail(f"  Cannot read actions.json: {e}")
            continue

        entries = data.get("actions", [])
        if not entries:
            warn("  No repair actions recorded")
            continue

        info(f"  {len(entries)} action(s) recorded")

        # Summary by status
        from collections import Counter
        statuses = Counter(e.get("status", "?") for e in entries)
        for status, count in statuses.items():
            color = GREEN if status == "success" else (YELLOW if status == "partial" else RED)
            print(f"    {color}{status:10}{RESET} : {count}")

        # Last 5 entries
        sorted_entries = sorted(entries, key=lambda x: x.get("timestamp", ""), reverse=True)
        print(f"\n  Last 5 actions:")
        for e in sorted_entries[:5]:
            ts        = e.get("timestamp", "?")[:19]
            action    = e.get("action", "?")
            status    = e.get("status", "?")
            primary   = e.get("primary_session", "?")
            tiles     = ""
            if e.get("tiles_repaired") is not None:
                tiles = f"  tiles={e['tiles_repaired']}/{e.get('tiles_total', '?')}"
            repaired  = e.get("tiles_repaired")
            s_color   = GREEN if status == "success" else (YELLOW if status == "partial" else RED)
            print(f"    {ts}  {action:6}  {s_color}{status:8}{RESET}{tiles}")
            print(f"      {primary}")
            if e.get("error"):
                print(f"      {RED}error: {e['error']}{RESET}")



def check_drive_stats(conn):
    section("Sessions & Exposure Time per Drive")

    drives = conn.execute("""
        SELECT BD.id, BD.name, BD.location, D.name AS dwarf_name
        FROM BackupDrive BD
        LEFT JOIN Dwarf D ON BD.dwarf_id = D.id
        WHERE BD.location IS NOT NULL
        ORDER BY BD.id
    """).fetchall()

    if not drives:
        warn("No backup drives configured")
        return

    for did, name, loc, dwarf_name in drives:
        online = os.path.exists(loc) if loc else False
        status = f"{GREEN}online{RESET}" if online else f"{YELLOW}offline{RESET}"
        dwarf_str = f"  [{dwarf_name}]" if dwarf_name else ""
        print(f"\n  BackupDrive [{did}] {name}{dwarf_str}  {status}")
        print(f"    location: {loc}")

        # Session count and exposure stats
        stats = conn.execute("""
            SELECT
                COUNT(DISTINCT BE.id)                          AS session_count,
                COUNT(DISTINCT BE.astro_object_id)             AS object_count,
                SUM(DD.exp_time * DD.shotsStacked)             AS total_exp_sec,
                SUM(DD.shotsStacked)                           AS total_shots,
                MIN(BE.session_date)                           AS first_session,
                MAX(BE.session_date)                           AS last_session
            FROM BackupEntry BE
            JOIN DwarfData DD ON BE.dwarf_data_id = DD.id
            WHERE BE.backup_drive_id = ?
        """, (did,)).fetchone()

        if stats and stats[0]:
            sessions, objects, total_sec, total_shots, first, last = stats
            total_sec = total_sec or 0
            hours   = int(total_sec // 3600)
            minutes = int((total_sec % 3600) // 60)
            seconds = int(total_sec % 60)
            info(f"    Sessions     : {sessions}")
            info(f"    Objects      : {objects}")
            info(f"    Total shots  : {total_shots or 0}")
            info(f"    Total exp    : {hours}h {minutes:02d}m {seconds:02d}s  "
                 f"({total_sec/3600:.2f} hours)")
            info(f"    First session: {first or '?'}")
            info(f"    Last session : {last or '?'}")

            # Top 5 objects by total exposure
            top_objects = conn.execute("""
                SELECT
                    AO.name AS obj_name,
                    AO.description AS obj_desc,
                    COUNT(DISTINCT BE.id)                         AS nb_sessions,
                    SUM(DD.exp_time * DD.shotsStacked)            AS obj_exp_sec
                FROM BackupEntry BE
                JOIN DwarfData DD ON BE.dwarf_data_id = DD.id
                LEFT JOIN AstroObject AO ON BE.astro_object_id = AO.id
                WHERE BE.backup_drive_id = ?
                GROUP BY BE.astro_object_id
                ORDER BY obj_exp_sec DESC
                LIMIT 5
            """, (did,)).fetchall()

            if top_objects:
                print(f"    Top 5 objects by exposure:")
                for obj_name, obj_desc, nb_sess, obj_sec in top_objects:
                    obj_name = _clean_obj_name(obj_name, obj_desc)
                    obj_sec = obj_sec or 0
                    h = int(obj_sec // 3600)
                    m = int((obj_sec % 3600) // 60)
                    print(f"      {obj_name:30}  {nb_sess:3} session(s)  "
                          f"{h}h {m:02d}m")
        else:
            warn("    No sessions found for this drive")

    # Grand total across all drives
    print(f"\n  {'─'*50}")
    totals = conn.execute("""
        SELECT
            COUNT(DISTINCT BE.id)               AS total_sessions,
            COUNT(DISTINCT BE.astro_object_id)  AS total_objects,
            SUM(DD.exp_time * DD.shotsStacked)  AS grand_total_sec,
            SUM(DD.shotsStacked)                AS grand_total_shots
        FROM BackupEntry BE
        JOIN DwarfData DD ON BE.dwarf_data_id = DD.id
    """).fetchone()

    if totals and totals[0]:
        sessions, objects, total_sec, shots = totals
        total_sec = total_sec or 0
        h = int(total_sec // 3600)
        m = int((total_sec % 3600) // 60)
        s = int(total_sec % 60)
        info(f"Grand total — {sessions} sessions  |  {objects} objects  |  "
             f"{shots or 0} shots  |  {h}h {m:02d}m {s:02d}s")

        # Top 20 objects by exposure
        top = conn.execute("""
            SELECT
                AO.name AS obj_name,
                    AO.description AS obj_desc,
                COUNT(DISTINCT BE.id)                 AS nb_sessions,
                SUM(DD.exp_time * DD.shotsStacked)    AS total_sec,
                SUM(DD.shotsStacked)                  AS shots
            FROM BackupEntry BE
            JOIN DwarfData DD ON BE.dwarf_data_id = DD.id
            LEFT JOIN AstroObject AO ON BE.astro_object_id = AO.id
            GROUP BY BE.astro_object_id
            ORDER BY total_sec DESC
            LIMIT 20
        """).fetchall()

        if top:
            print(f"\n  {chr(9472)*50}")
            print(f"  Top 20 Objects by Exposure")
            print(f"  {chr(9472)*50}")
            for i, (obj_name, obj_desc, nb_sess, obj_sec, obj_shots) in enumerate(top, 1):
                obj_name = _clean_obj_name(obj_name, obj_desc)
                obj_sec = obj_sec or 0
                h2 = int(obj_sec // 3600)
                m2 = int((obj_sec % 3600) // 60)
                s2 = int(obj_sec % 60)
                print(f"  {i:>2}.  {obj_name:35}  "
                      f"{nb_sess:3} session(s)  "
                      f"{h2}h {m2:02d}m {s2:02d}s  "
                      f"({obj_shots or 0} shots)")

def check_full_drive_files(conn):
    section("Full Drive Check — Missing Files on Connected Drives")

    # Get all connected drives
    drives = conn.execute(
        "SELECT id, name, location FROM BackupDrive "
        "WHERE location IS NOT NULL ORDER BY id"
    ).fetchall()

    if not drives:
        warn("No backup drives configured")
        return

    online_drives = [(did, name, loc) for did, name, loc in drives if os.path.exists(loc)]
    offline_drives = [(did, name, loc) for did, name, loc in drives if not os.path.exists(loc)]

    if offline_drives:
        for did, name, loc in offline_drives:
            info(f"OFFLINE — skipping BackupDrive [{did}] {name}  ({loc})")

    if not online_drives:
        warn("No drives currently connected — nothing to check")
        return

    total_checked = 0
    total_missing = 0
    total_ok      = 0

    for did, name, loc in online_drives:
        usage = None
        try:
            u = __import__('shutil').disk_usage(loc)
            free_gb  = u.free  / 1024**3
            total_gb = u.total / 1024**3
            used_pct = u.used / u.total * 100
            usage = f"{free_gb:.1f} GB free / {total_gb:.1f} GB  ({used_pct:.0f}% used)"
        except Exception:
            pass

        print(f"\n  {GREEN}ONLINE{RESET}  BackupDrive [{did}] {name}")
        print(f"    location : {loc}")
        if usage:
            print(f"    disk     : {usage}")

        # All DwarfData linked to this drive
        rows = conn.execute("""
            SELECT DD.id, DD.file_path
            FROM DwarfData DD
            INNER JOIN BackupEntry BE ON BE.dwarf_data_id = DD.id
            WHERE BE.backup_drive_id = ?
              AND DD.file_path IS NOT NULL
              AND DD.file_path != ''
            GROUP BY DD.id
            ORDER BY DD.file_path
        """, (did,)).fetchall()

        if not rows:
            info("    No DwarfData entries linked to this drive")
            continue

        missing_rows = []
        for dd_id, rel_path in rows:
            full_path = os.path.join(loc, rel_path)
            total_checked += 1
            if not os.path.exists(full_path):
                missing_rows.append((dd_id, rel_path, full_path))
                total_missing += 1
            else:
                total_ok += 1

        print(f"    checked  : {len(rows)} files")

        if not missing_rows:
            ok(f"    All {len(rows)} files found on disk")
        else:
            warn(f"    {len(missing_rows)} / {len(rows)} files MISSING:")
            for dd_id, rel_path, full_path in missing_rows:
                print(f"      {RED}✘{RESET}  DwarfData.id={dd_id}")
                print(f"         {full_path}")

    print(f"\n  {'─'*50}")
    info(f"Total checked : {total_checked}")
    ok(f"Found         : {total_ok}") if total_ok > 0 else None
    if total_missing > 0:
        fail(f"Missing       : {total_missing}")
    else:
        ok("No missing files on connected drives")

def main():
    parser = argparse.ArgumentParser(
        description="Dwarfium Scope Archive — DB Diagnostic Tool"
    )
    parser.add_argument(
        "--db", default=os.path.join("db", "dwarf_backup.db"),
        help="Path to the SQLite database"
    )
    parser.add_argument(
        "--skip-files", action="store_true",
        help="Skip file existence check on disk (faster)"
    )
    parser.add_argument(
        "--full-check", action="store_true",
        help="Check ALL files on connected drives (may be slow)"
    )
    args = parser.parse_args()

    print(f"\n{BOLD}{'═'*54}{RESET}")
    print(f"{BOLD}  Dwarfium Scope Archive — DB Diagnostic{RESET}")
    print(f"{BOLD}  {datetime.now():%Y-%m-%d %H:%M:%S}{RESET}")
    print(f"{BOLD}{'═'*54}{RESET}")
    info(f"Database: {args.db}")
    info(f"File size: {os.path.getsize(args.db):,} bytes")

    conn = connect(args.db)

    check_version(conn)
    check_counts(conn)
    check_integrity(conn)
    check_orphans(conn)
    check_duplicates(conn)
    check_dwarf_devices(conn)
    check_drive_stats(conn)
    check_settings(conn)
    check_dso_catalog(conn)
    check_recent_activity(conn)
    if not args.skip_files and not args.full_check:
        check_files_on_disk(conn)
    if args.full_check:
        check_full_drive_files(conn)
    check_same_basename_diff_ext(conn)
    check_sessions_error(conn)
    check_repair_history(conn)
    check_storage_json()

    conn.close()

    print(f"\n{BOLD}{'═'*54}{RESET}")
    print(f"{BOLD}  Diagnostic complete{RESET}")
    print(f"{BOLD}{'═'*54}{RESET}\n")


if __name__ == "__main__":
    main()
# (appended — do not run directly)