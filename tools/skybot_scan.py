#!/usr/bin/env python3
"""
tools/skybot_scan.py — Batch SkyBot scanner for Dwarfium Scope Archive.

Scans sessions in the database against the IMCCE SkyBot service to detect
comets and asteroids that were in the field at the time of capture.

Results are stored in the SkyBotResult table and can be reported without
re-querying.

Usage:
    # Scan all sessions never queried before
    python tools/skybot_scan.py

    # Scan sessions in a date range
    python tools/skybot_scan.py --from 2025-01-01 --to 2025-12-31

    # Re-scan recent sessions (e.g. for newly discovered objects)
    python tools/skybot_scan.py --from 2025-02-01 --force

    # Show results report only (no scanning)
    python tools/skybot_scan.py --report

    # Show only comets / only asteroids
    python tools/skybot_scan.py --report --type comet
    python tools/skybot_scan.py --report --type asteroid

    # Custom search radius (default: 4.0°)
    python tools/skybot_scan.py --radius 2.0

    # Limit to a specific backup drive
    python tools/skybot_scan.py --backup-drive-id 1

    # Dry run — show what would be scanned without querying SkyBot
    python tools/skybot_scan.py --dry-run
"""

import argparse
import os
import sqlite3
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

# ── Add project root to sys.path ─────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from api.dwarf_backup_db import connect_db, DB_NAME

# ── ANSI colours ──────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def _c(color, text): return f"{color}{text}{RESET}"


# ── DB helpers ────────────────────────────────────────────────────────────────

def ensure_skybot_table(conn: sqlite3.Connection):
    """Create SkyBotResult table if it doesn't exist (no migration needed)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS SkyBotResult (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            backup_entry_id   INTEGER NOT NULL REFERENCES BackupEntry(id) ON DELETE CASCADE,
            object_name       TEXT NOT NULL,
            object_type       TEXT,
            magnitude         REAL,
            ra_deg            REAL,
            dec_deg           REAL,
            angular_dist_deg  REAL,
            queried_at        TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_skybotresult_entry
        ON SkyBotResult(backup_entry_id)
    """)
    conn.commit()


def get_sessions_to_scan(conn: sqlite3.Connection,
                          date_from: str | None,
                          date_to:   str | None,
                          force:     bool,
                          backup_drive_id: int | None) -> list[dict]:
    """
    Return BackupEntry rows that need scanning.
    Joins DwarfData to get RA, Dec and modification_time (used as session date).
    """
    query = """
        SELECT
            BackupEntry.id,
            BackupEntry.session_date,
            BackupEntry.session_dir,
            DwarfData.ra,
            DwarfData.dec,
            DwarfData.target
        FROM BackupEntry
        JOIN DwarfData ON BackupEntry.dwarf_data_id = DwarfData.id
        WHERE DwarfData.ra  IS NOT NULL
          AND DwarfData.dec IS NOT NULL
          AND BackupEntry.session_date IS NOT NULL
    """
    params = []

    if not force:
        query += " AND NOT EXISTS (SELECT 1 FROM SkyBotResult WHERE SkyBotResult.backup_entry_id = BackupEntry.id)"

    if date_from:
        query += " AND BackupEntry.session_date >= ?"
        params.append(date_from)

    if date_to:
        query += " AND BackupEntry.session_date <= ?"
        params.append(date_to + " 23:59:59")

    if backup_drive_id:
        query += " AND BackupEntry.backup_drive_id = ?"
        params.append(backup_drive_id)

    query += " ORDER BY BackupEntry.session_date DESC"

    cursor = conn.execute(query, params)
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def save_results(conn: sqlite3.Connection,
                 entry_id: int,
                 results: list[dict],
                 queried_at: str):
    """Persist SkyBot results for one session."""
    # Remove previous results for this entry (in case of --force re-scan)
    conn.execute("DELETE FROM SkyBotResult WHERE backup_entry_id = ?", (entry_id,))
    for r in results:
        try:
            mag = float(r.get("magnitude", "")) if r.get("magnitude") not in (None, "?", "") else None
        except (ValueError, TypeError):
            mag = None
        conn.execute("""
            INSERT INTO SkyBotResult
                (backup_entry_id, object_name, object_type, magnitude,
                 ra_deg, dec_deg, angular_dist_deg, queried_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entry_id,
            r.get("name", ""),
            r.get("type", ""),
            mag,
            r.get("ra_deg"),
            r.get("dec_deg"),
            r.get("separation_deg"),
            queried_at,
        ))
    conn.commit()


# ── SkyBot query (reuse existing logic) ──────────────────────────────────────

def skybot_query_session(ra_deg: float, dec_deg: float,
                          session_date: str, radius_deg: float,
                          mag_limit: float = 15.0) -> tuple[list, str | None]:
    """Call SkyBot for one session. Returns (results, error_msg)."""
    from components.astro_object_associate import _skybot_query
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        comets,    err1 = _skybot_query(ra_deg, dec_deg, session_date, radius_deg,
                                         find_comets=True, find_asteroids=False)
        asteroids, err2 = _skybot_query(ra_deg, dec_deg, session_date, radius_deg,
                                         find_comets=False, find_asteroids=True)
    all_results = comets + asteroids
    # Filter by magnitude — exclude objects fainter than mag_limit
    filtered = []
    for r in all_results:
        try:
            mag = float(r.get("magnitude", ""))
            if mag <= mag_limit:
                filtered.append(r)
        except (ValueError, TypeError):
            filtered.append(r)  # keep if magnitude unknown
    error = err1 or err2
    return filtered, error


# ── Report ────────────────────────────────────────────────────────────────────

def print_report(conn: sqlite3.Connection, type_filter: str | None, port: int = 8080):
    """Print a summary of all SkyBot hits grouped by object name."""
    query = """
        SELECT
            SkyBotResult.object_name,
            SkyBotResult.object_type,
            SkyBotResult.magnitude,
            SkyBotResult.angular_dist_deg,
            BackupEntry.id            AS entry_id,
            BackupEntry.session_date,
            BackupEntry.session_dir,
            DwarfData.target
        FROM SkyBotResult
        JOIN BackupEntry ON SkyBotResult.backup_entry_id = BackupEntry.id
        JOIN DwarfData   ON BackupEntry.dwarf_data_id = DwarfData.id
    """
    params = []
    if type_filter:
        query += " WHERE LOWER(SkyBotResult.object_type) LIKE ?"
        params.append(f"%{type_filter.lower()}%")
    query += " ORDER BY SkyBotResult.object_type, SkyBotResult.object_name, BackupEntry.session_date DESC"

    cursor = conn.execute(query, params)
    rows = cursor.fetchall()

    if not rows:
        print(_c(YELLOW, "No SkyBot hits found in database."))
        print("Run without --report to start scanning.")
        return

    # Stats
    total_scanned  = conn.execute(
        "SELECT COUNT(*) FROM BackupEntry WHERE dwarf_data_id IS NOT NULL"
    ).fetchone()[0]
    total_queried  = conn.execute(
        "SELECT COUNT(DISTINCT backup_entry_id) FROM SkyBotResult"
    ).fetchone()[0]
    total_hits     = conn.execute(
        "SELECT COUNT(DISTINCT backup_entry_id) FROM SkyBotResult"
    ).fetchone()[0]
    comet_count    = conn.execute(
        "SELECT COUNT(DISTINCT object_name) FROM SkyBotResult WHERE LOWER(object_type) LIKE '%comet%'"
    ).fetchone()[0]
    asteroid_count = conn.execute(
        "SELECT COUNT(DISTINCT object_name) FROM SkyBotResult WHERE LOWER(object_type) NOT LIKE '%comet%'"
    ).fetchone()[0]

    print()
    print(_c(BOLD, "═" * 72))
    print(_c(BOLD, "  🌠 SkyBot Scan Report — Dwarfium Scope Archive"))
    print(_c(BOLD, "═" * 72))
    print(f"  Sessions in DB     : {_c(CYAN,   total_scanned)}")
    print(f"  Sessions scanned   : {_c(CYAN,   total_queried)}")
    print(f"  Sessions with hits : {_c(GREEN,  total_hits)}")
    print(f"  ☄️  Unique comets    : {_c(GREEN,  comet_count)}")
    print(f"  🪨  Unique asteroids : {_c(YELLOW, asteroid_count)}")
    print()

    # Group by (type, name)
    from itertools import groupby
    current_type = None

    for (obj_type, obj_name), group in groupby(rows, key=lambda r: (r[1], r[0])):
        sessions = list(group)
        mag      = sessions[0][2]
        is_comet = "comet" in (obj_type or "").lower()
        icon     = "☄️ " if is_comet else "🪨"

        # Section header when type changes
        if obj_type != current_type:
            current_type = obj_type
            print(_c(BOLD, f"  {icon} {obj_type or 'Unknown type'}"))
            print("  " + "─" * 68)

        mag_str = f"mag {mag:.1f}" if mag else _c(YELLOW, "mag ?  ")
        count   = len(sessions)
        count_str = f"({count} session{'s' if count > 1 else ''})"
        print(f"  {_c(GREEN, obj_name):<40s}  {mag_str}  {_c(CYAN, count_str)}")

        for _, _, _, dist, entry_id, date, session_dir, target in sessions:
            dist_str = f"{dist:.2f}°" if dist else "?"
            date_str = str(date)[:16] if date else "?"
            dir_name = Path(session_dir).name if session_dir else "?"
            label    = target or dir_name
            link     = _c(CYAN, f"http://localhost:{port}/Explore/?SessionId={entry_id}")
            print(f"    {date_str}  {label:<38s}  {dist_str:<8s}")
            print(f"    {'':16s}  {link}")

        print()

    print(_c(BOLD, "═" * 72))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Batch SkyBot scanner — detect comets & asteroids in your sessions.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Usage:")[1] if "Usage:" in __doc__ else ""
    )
    parser.add_argument("--from", dest="date_from", metavar="YYYY-MM-DD",
                        help="Scan sessions from this date")
    parser.add_argument("--to",   dest="date_to",   metavar="YYYY-MM-DD",
                        help="Scan sessions up to this date")
    parser.add_argument("--force", action="store_true",
                        help="Re-scan even sessions already queried")
    parser.add_argument("--report", action="store_true",
                        help="Show report only, no scanning")
    parser.add_argument("--type", choices=["comet", "asteroid"],
                        help="Filter report by object type")
    parser.add_argument("--radius", type=float, default=4.0, metavar="DEG",
                        help="Search radius in degrees (default: 4.0)")
    parser.add_argument("--mag-limit", type=float, default=15.0, metavar="MAG",
                        help="Maximum magnitude to keep (default: 15.0, fainter objects excluded)")
    parser.add_argument("--backup-drive-id", type=int, metavar="ID",
                        help="Limit scan to a specific backup drive")
    parser.add_argument("--delay", type=float, default=1.0, metavar="SEC",
                        help="Delay between SkyBot queries in seconds (default: 1.0)")
    parser.add_argument("--db", default=str(ROOT / DB_NAME),
                        help=f"Path to database (default: {DB_NAME})")
    parser.add_argument("--port", type=int, default=8080, metavar="PORT",
                        help="Port of the running Dwarfium app (default: 8080)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show sessions to scan without querying SkyBot")
    args = parser.parse_args()

    # ── Connect ───────────────────────────────────────────────────────────────
    db_path = Path(args.db)
    if not db_path.exists():
        print(_c(RED, f"Database not found: {db_path}"))
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    ensure_skybot_table(conn)

    # ── Report only ───────────────────────────────────────────────────────────
    if args.report:
        print_report(conn, args.type, args.port)
        conn.close()
        return

    # ── Gather sessions ───────────────────────────────────────────────────────
    sessions = get_sessions_to_scan(
        conn,
        date_from=args.date_from,
        date_to=args.date_to,
        force=args.force,
        backup_drive_id=args.backup_drive_id,
    )

    if not sessions:
        print(_c(GREEN, "✅ No sessions to scan — all up to date."))
        print("Use --force to re-scan already queried sessions.")
        conn.close()
        return

    print()
    print(_c(BOLD, f"🌠 SkyBot Batch Scanner"))
    print(f"   Database  : {db_path}")
    print(f"   Sessions  : {_c(CYAN, len(sessions))} to scan")
    print(f"   Radius    : {args.radius}°")
    print(f"   Mag limit : {args.mag_limit}")
    if args.date_from: print(f"   From      : {args.date_from}")
    if args.date_to:   print(f"   To        : {args.date_to}")
    if args.force:     print(f"   Mode      : {_c(YELLOW, 'FORCE re-scan')}")
    if args.dry_run:   print(f"   Mode      : {_c(YELLOW, 'DRY RUN — no queries')}")
    print()

    if args.dry_run:
        print(_c(BOLD, "Sessions that would be scanned:"))
        for s in sessions:
            print(f"  [{s['id']:5d}]  {str(s['session_date'])[:16]}  {s['target'] or Path(s['session_dir']).name}")
        print()
        conn.close()
        return

    # ── Scan ──────────────────────────────────────────────────────────────────
    hits     = 0
    errors   = 0
    skipped  = 0
    total    = len(sessions)

    for i, session in enumerate(sessions, 1):
        entry_id     = session["id"]
        session_date = session["session_date"]
        target       = session["target"] or Path(session["session_dir"]).name
        ra_hours     = session["ra"]
        dec_str      = session["dec"]

        # Convert RA hours → degrees
        try:
            ra_deg  = float(ra_hours) * 15.0
            dec_deg = float(dec_str)
        except (TypeError, ValueError):
            print(f"  [{i:4d}/{total}]  {_c(YELLOW, 'SKIP')}  {target}  — invalid coords")
            skipped += 1
            continue

        print(f"  [{i:4d}/{total}]  {str(session_date)[:16]}  {target:<40s}", end=" ", flush=True)

        queried_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        results, error = skybot_query_session(ra_deg, dec_deg, session_date, args.radius, args.mag_limit)

        if error:
            print(_c(RED, f"ERROR: {error}"))
            errors += 1
            # Don't mark as queried on network errors — will retry next run
            if "internet" in error.lower() or "reach" in error.lower():
                print(_c(RED, "\n  ⚠ Network error — stopping scan. Run again when connected."))
                break
        else:
            save_results(conn, entry_id, results, queried_at)
            if results:
                names = ", ".join(r["name"] for r in results[:3])
                extra = f" +{len(results)-3} more" if len(results) > 3 else ""
                print(_c(GREEN, f"🌠 {len(results)} hit(s): {names}{extra}"))
                hits += 1
            else:
                print(_c(CYAN, "—"))

        time.sleep(args.delay)

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    print(_c(BOLD, "─" * 50))
    print(f"  Scanned  : {i - skipped - errors}")
    print(f"  With hits: {_c(GREEN, hits)}")
    print(f"  Skipped  : {_c(YELLOW, skipped)}")
    print(f"  Errors   : {_c(RED,    errors)}")
    print()
    if hits:
        print(f"  Run  {_c(CYAN, 'python tools/skybot_scan.py --report')}  to see all hits.")
    print()

    conn.close()


if __name__ == "__main__":
    main()