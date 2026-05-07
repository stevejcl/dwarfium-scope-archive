#!/usr/bin/env python3
"""
tools/quality_scan.py — Session quality scorer for Dwarfium Scope Archive.

Computes a quality score (0–100) for each BackupEntry using a two-pass approach:

  Pass 1 — Metadata score (instant, no file I/O):
    - Stack rate  : shotsStacked / shotsToTake         (50%)
    - Exposure    : total exposure time                 (30%)
    - Dark match  : matching dark frames available      (20%)
    → score_A in [0, 100]

  Pass 2 — JPEG image analysis (only if score_A >= threshold, default 40):
    - Dynamic range : spread of pixel histogram         (40%)
    - RMS contrast  : std-dev of pixel values           (40%)
    - Entropy       : information content / detail      (20%)
    → score_C in [0, 100]

  Final score:
    score_A < threshold → quality_score = score_A
    score_A >= threshold → quality_score = score_A * 0.6 + score_C * 0.4

Results are stored in the SessionQuality table (created automatically).

Usage:
    python tools/quality_scan.py                      # all unscored sessions
    python tools/quality_scan.py --from 2025-01-01    # date range
    python tools/quality_scan.py --threshold 40       # Pass 2 threshold
    python tools/quality_scan.py --force              # re-score everything
    python tools/quality_scan.py --report             # show scores, no scanning
    python tools/quality_scan.py --dry-run            # preview only
"""

import argparse
import math
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Project root ─────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from api.dwarf_backup_db import connect_db, DB_NAME
from api.dwarf_backup_fct import is_Restacked, get_total_exposure, get_total_mosaic_exposure

# ── ANSI colours ──────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def _c(color, text): return f"{color}{text}{RESET}"

def _star(score: float) -> str:
    """Convert score to star rating."""
    if score >= 80: return "⭐⭐⭐⭐⭐"
    if score >= 65: return "⭐⭐⭐⭐"
    if score >= 50: return "⭐⭐⭐"
    if score >= 35: return "⭐⭐"
    return "⭐"

def _bar(score: float, width: int = 20) -> str:
    """ASCII progress bar."""
    filled = int(score / 100 * width)
    color  = GREEN if score >= 65 else YELLOW if score >= 40 else RED
    return _c(color, "█" * filled) + "░" * (width - filled)


# ── DB setup ─────────────────────────────────────────────────────────────────

def ensure_quality_table(conn: sqlite3.Connection):
    """Create SessionQuality table if it doesn't exist.
    Also migrates existing table to add UNIQUE constraint on backup_entry_id
    (required for ON CONFLICT upsert to work in SQLite).
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS SessionQuality (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            backup_entry_id   INTEGER NOT NULL UNIQUE REFERENCES BackupEntry(id) ON DELETE CASCADE,
            quality_score     REAL,
            total_exp_seconds REAL,
            score_a           REAL,
            score_c           REAL,
            scored_at         TEXT NOT NULL
        )
    """)
    conn.commit()

    # Migration: if table exists without inline UNIQUE, recreate it
    # Check by looking at the CREATE TABLE statement stored in sqlite_master
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='SessionQuality'"
    ).fetchone()
    if row and 'UNIQUE' not in row[0]:
        # Recreate with UNIQUE constraint
        conn.execute("ALTER TABLE SessionQuality RENAME TO SessionQuality_old")
        conn.execute("""
            CREATE TABLE SessionQuality (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                backup_entry_id   INTEGER NOT NULL UNIQUE REFERENCES BackupEntry(id) ON DELETE CASCADE,
                quality_score     REAL,
                total_exp_seconds REAL,
                score_a           REAL,
                score_c           REAL,
                scored_at         TEXT NOT NULL
            )
        """)
        conn.execute("""
            INSERT INTO SessionQuality
                (id, backup_entry_id, quality_score, total_exp_seconds, score_a, score_c, scored_at)
            SELECT id, backup_entry_id, quality_score, total_exp_seconds, score_a, score_c, scored_at
            FROM SessionQuality_old
        """)
        conn.execute("DROP TABLE SessionQuality_old")
        conn.commit()
        print("[DB] SessionQuality migrated — UNIQUE constraint added on backup_entry_id")


def get_sessions_to_score(conn: sqlite3.Connection,
                           date_from: str | None,
                           date_to:   str | None,
                           force:     bool,
                           backup_drive_id: int | None) -> list[dict]:
    """Return sessions that need scoring."""
    query = """
        SELECT
            BackupEntry.id,
            BackupEntry.session_date,
            BackupEntry.session_dir,
            BackupEntry.backup_drive_id,
            SessionQuality.quality_score,
            DwarfData.shotsStacked,
            DwarfData.shotsToTake,
            DwarfData.exp_time,
            DwarfData.target,
            DwarfData.thumbnail_path,
            DwarfData.stacked_fits_path,
            DwarfData.file_path         AS dwarf_file_path,
            DwarfData.stacked_fits_path,
            BackupDrive.location          AS drive_location,
            BackupDrive.astronomy_dir     AS drive_astro_dir,
            Dwarf.type                    AS dwarf_type
        FROM BackupEntry
        JOIN DwarfData    ON BackupEntry.dwarf_data_id = DwarfData.id
        JOIN BackupDrive  ON BackupEntry.backup_drive_id = BackupDrive.id
        LEFT JOIN Dwarf   ON BackupEntry.dwarf_id = Dwarf.id
        LEFT JOIN SessionQuality ON BackupEntry.id = SessionQuality.backup_entry_id
        WHERE BackupEntry.dwarf_data_id IS NOT NULL
    """
    params = []

    if not force:
        query += " AND SessionQuality.backup_entry_id IS NULL"

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
    cols   = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


# ── Pass 1 — Metadata score ──────────────────────────────────────────────────

def score_metadata(session: dict) -> tuple[float, dict]:
    """
    Compute score_A from DB metadata only.
    Returns (score_A, details_dict).
    """
    details = {}

    # ── Stack rate (50%) ─────────────────────────────────────────────────────
    stacked = session.get("shotsStacked") or 0
    total   = session.get("shotsToTake")  or 0
    if total > 0:
        rate = min(stacked / total, 1.0)
    elif stacked > 0:
        rate = 0.8  # shotsToTake unknown but has stacks
    else:
        rate = 0.0
    stack_score = rate * 100
    details["stack_rate"]  = rate
    details["stacked"]     = stacked
    details["total"]       = total

    # ── Total exposure time (30%) ─────────────────────────────────────────────
    # For RESTACK sessions exp_time is NULL — read from FITS header instead
    session_dir     = session.get("session_dir") or ""
    drive_loc       = session.get("drive_location") or ""
    fits_rel        = session.get("stacked_fits_path") or ""
    file_path_rel   = session.get("dwarf_file_path") or ""

    total_exp_s = 0.0
    if is_Restacked(session_dir):
        # Try to read from FITS header
        fits_abs = None
        if drive_loc and fits_rel:
            fits_abs = str(Path(drive_loc) / fits_rel)
        elif drive_loc and file_path_rel:
            fits_abs = str(Path(drive_loc) / Path(file_path_rel).parent / "stacked.fits")

        if fits_abs:
            if "_MOSAIC_" in session_dir:
                total_exp_s = get_total_mosaic_exposure(str(Path(fits_abs).parent))
            else:
                total_exp_s = get_total_exposure(fits_abs)
    else:
        exp_per_frame = 0.0
        try:
            exp_per_frame = float(session.get("exp_time") or 0)
        except (ValueError, TypeError):
            pass
        total_exp_s = exp_per_frame * stacked

    total_exp_h = total_exp_s / 3600.0

    # Sigmoid-ish scale: 0h=0, 1h≈50, 3h≈80, 6h+=100
    if total_exp_h <= 0:
        exp_score = 0.0
    elif total_exp_h >= 6:
        exp_score = 100.0
    else:
        exp_score = min(100.0, total_exp_h / 6.0 * 100.0 * (1 + math.log1p(total_exp_h)))
        exp_score = min(100.0, exp_score)
    details["total_exp_h"] = round(total_exp_h, 2)
    details["total_exp_s"] = total_exp_s
    details["exp_score"]   = round(exp_score, 1)

    # ── Dark match (20%) — check SkyBotResult (reuse dark match logic) ───────
    # Simple: just check if stacked_fits_path exists as proxy for full pipeline
    has_fits  = bool(session.get("stacked_fits_path"))
    dark_score = 70.0 if has_fits else 30.0  # FITS = likely processed with darks
    details["has_fits"]   = has_fits
    details["dark_score"] = dark_score

    # ── Sensor bonus — Dwarf 3 / Mini have better sensor than Dwarf 2 (10%) ──
    dwarf_type  = (session.get("dwarf_type") or "").lower()
    if "3" in dwarf_type or "mini" in dwarf_type:
        sensor_bonus = 10.0   # Dwarf 3 / Mini
    elif "2" in dwarf_type:
        sensor_bonus = 0.0    # Dwarf 2 baseline
    else:
        sensor_bonus = 5.0    # unknown — give benefit of doubt
    details["dwarf_type"]   = session.get("dwarf_type") or "unknown"
    details["sensor_bonus"] = sensor_bonus

    # ── Weighted total (sensor bonus is additive, capped at 100) ─────────────
    score_a = min(100.0, (stack_score * 0.50 +
                           exp_score   * 0.30 +
                           dark_score  * 0.20) + sensor_bonus * 0.10)

    details["stack_score"] = round(stack_score, 1)
    return round(score_a, 1), details


# ── Pass 2 — JPEG image analysis ────────────────────────────────────────────

def find_stacked_jpg(session: dict) -> Path | None:
    """
    Find the full-resolution stacked.jpg for a session.

    DwarfData.file_path is stored RELATIVE to BackupDrive.location
    and points directly to stacked.jpg
    (e.g. DWARF_RAW_TELE_M42.../stacked.jpg).
    """
    drive_loc  = session.get("drive_location")  or ""
    file_path  = session.get("dwarf_file_path") or ""
    session_dir = session.get("session_dir")    or ""

    candidates = []

    # 1. Best: drive_location / file_path (file_path IS stacked.jpg)
    if drive_loc and file_path:
        candidates.append(Path(drive_loc) / file_path)

    # 2. file_path as absolute fallback
    if file_path:
        candidates.append(Path(file_path))

    # 3. session_dir / stacked.jpg
    if session_dir:
        candidates.append(Path(session_dir) / "stacked.jpg")
    if drive_loc and session_dir:
        candidates.append(Path(drive_loc) / session_dir / "stacked.jpg")

    for p in candidates:
        try:
            if p.exists():
                return p
        except Exception:
            pass
    return None


def score_jpeg(jpg_path: Path) -> tuple[float, dict]:
    """
    Analyse stacked.jpg and return score_C in [0, 100].
    Uses only PIL — no OpenCV required.
    """
    details = {}
    try:
        from PIL import Image, ImageStat
        import statistics

        img = Image.open(jpg_path).convert("L")  # grayscale

        # Resize for speed (max 512px)
        w, h = img.size
        if max(w, h) > 512:
            scale = 512 / max(w, h)
            img   = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

        stat = ImageStat.Stat(img)
        # img.getdata() deprecated in Pillow 14 — use sorted pixel list from histogram
        pixels = [v for v, count in enumerate(img.histogram()) for _ in range(count)]

        # ── Dynamic range (40%) ───────────────────────────────────────────────
        p5  = sorted(pixels)[int(len(pixels) * 0.05)]
        p95 = sorted(pixels)[int(len(pixels) * 0.95)]
        dynamic = p95 - p5  # 0-255
        dyn_score = min(100.0, dynamic / 180.0 * 100.0)
        details["dynamic"]   = dynamic
        details["dyn_score"] = round(dyn_score, 1)

        # ── RMS contrast (40%) ────────────────────────────────────────────────
        rms = stat.stddev[0]  # std-dev of pixel values
        # Good astrophoto: rms 15-60. < 5 = underexposed/flat, > 80 = blown
        if rms < 2:
            rms_score = 0.0
        elif rms > 80:
            rms_score = max(0.0, 100.0 - (rms - 80) * 2)
        else:
            rms_score = min(100.0, rms / 40.0 * 100.0)
        details["rms"]       = round(rms, 1)
        details["rms_score"] = round(rms_score, 1)

        # ── Entropy / detail (20%) ────────────────────────────────────────────
        histogram = img.histogram()  # 256 bins
        total_px  = sum(histogram)
        entropy   = 0.0
        for count in histogram:
            if count > 0:
                p = count / total_px
                entropy -= p * math.log2(p)
        # Max entropy ~8 bits. Astrophotos typically 4-7
        entropy_score = min(100.0, max(0.0, (entropy - 2.0) / 5.0 * 100.0))
        details["entropy"]       = round(entropy, 2)
        details["entropy_score"] = round(entropy_score, 1)

        # ── Weighted total ────────────────────────────────────────────────────
        score_c = (dyn_score     * 0.40 +
                   rms_score     * 0.40 +
                   entropy_score * 0.20)
        return round(score_c, 1), details

    except ImportError:
        print(_c(YELLOW, "  ⚠ PIL not available — skipping image analysis"))
        return 0.0, {"error": "PIL not available"}
    except Exception as e:
        return 0.0, {"error": str(e)}


# ── Report ────────────────────────────────────────────────────────────────────

def print_report(conn: sqlite3.Connection, type_filter: str | None):
    """Print quality score report."""
    # Only scored sessions, ordered by score
    query = """
        SELECT
            BackupEntry.id,
            BackupEntry.session_date,
            SessionQuality.quality_score,
            DwarfData.target,
            DwarfData.shotsStacked,
            DwarfData.exp_time,
            AstroObject.name AS object_name,
            SessionQuality.total_exp_seconds
        FROM SessionQuality
        JOIN BackupEntry ON SessionQuality.backup_entry_id = BackupEntry.id
        JOIN DwarfData   ON BackupEntry.dwarf_data_id = DwarfData.id
        LEFT JOIN AstroObject ON BackupEntry.astro_object_id = AstroObject.id
        WHERE SessionQuality.quality_score IS NOT NULL
        ORDER BY SessionQuality.quality_score DESC
    """
    rows = conn.execute(query).fetchall()

    if not rows:
        print(_c(YELLOW, "No scored sessions yet."))
        print("Run without --report to start scoring.")
        return

    # Stats
    scores  = [r[2] for r in rows]
    total   = conn.execute("SELECT COUNT(*) FROM BackupEntry WHERE dwarf_data_id IS NOT NULL").fetchone()[0]
    unscored = total - len(scores)

    buckets = {
        "⭐⭐⭐⭐⭐ Excellent  (≥80)": [s for s in scores if s >= 80],
        "⭐⭐⭐⭐   Good      (65-79)": [s for s in scores if 65 <= s < 80],
        "⭐⭐⭐     Average   (50-64)": [s for s in scores if 50 <= s < 65],
        "⭐⭐       Fair      (35-49)": [s for s in scores if 35 <= s < 50],
        "⭐         Poor     (<35)":   [s for s in scores if s < 35],
    }

    print()
    print(_c(BOLD, "═" * 72))
    print(_c(BOLD, "  🌟 Session Quality Report — Dwarfium Scope Archive"))
    print(_c(BOLD, "═" * 72))
    print(f"  Total sessions   : {_c(CYAN, total)}")
    print(f"  Scored           : {_c(CYAN, len(scores))}")
    print(f"  Unscored         : {_c(YELLOW, unscored)}")
    if scores:
        print(f"  Average score    : {_c(GREEN, f'{sum(scores)/len(scores):.1f}')}")
    print()
    print(_c(BOLD, "  Distribution:"))
    for label, bucket in buckets.items():
        bar = "█" * len(bucket) if len(bucket) <= 50 else "█" * 50 + "…"
        print(f"  {label:<30s}  {_c(GREEN, bar)}  {len(bucket)}")
    print()

    # Top 20
    print(_c(BOLD, "  Top sessions:"))
    print("  " + "─" * 68)
    for entry_id, date, score, target, stacked, exp_time, obj_name, total_exp_s in rows[:20]:
        label    = obj_name or target or "?"
        date_str = str(date)[:10] if date else "?"
        try:
            # Use stored total_exp_seconds if available (correct for RESTACK)
            if total_exp_s is not None and total_exp_s > 0:
                total_exp = f"{float(total_exp_s) / 3600:.1f}h"
            else:
                total_exp = f"{float(exp_time or 0) * (stacked or 0) / 3600:.1f}h"
        except Exception:
            total_exp = "?"
        print(f"  {_bar(score, 15)}  {score:5.1f}  {_star(score)}  "
              f"{date_str}  {label:<30s}  {total_exp}")

    print()
    print(_c(BOLD, "═" * 72))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Session quality scorer for Dwarfium Scope Archive."
    )
    parser.add_argument("--from", dest="date_from", metavar="YYYY-MM-DD")
    parser.add_argument("--to",   dest="date_to",   metavar="YYYY-MM-DD")
    parser.add_argument("--force",     action="store_true",
                        help="Re-score already scored sessions")
    parser.add_argument("--report",    action="store_true",
                        help="Show report only, no scoring")
    parser.add_argument("--threshold", type=float, default=40.0, metavar="SCORE",
                        help="Min score_A to trigger JPEG analysis (default: 40)")
    parser.add_argument("--backup-drive-id", type=int, metavar="ID")
    parser.add_argument("--dry-run",   action="store_true")
    parser.add_argument("--db", default=str(ROOT / DB_NAME))
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(_c(RED, f"Database not found: {db_path}"))
        sys.exit(1)

    conn = connect_db(str(db_path))
    ensure_quality_table(conn)

    if args.report:
        print_report(conn, None)
        conn.close()
        return

    sessions = get_sessions_to_score(
        conn, args.date_from, args.date_to, args.force, args.backup_drive_id
    )

    if not sessions:
        print(_c(GREEN, "✅ All sessions already scored. Use --force to re-score."))
        conn.close()
        return

    print()
    print(_c(BOLD, "🌟 Session Quality Scanner"))
    print(f"   Database  : {db_path}")
    print(f"   Sessions  : {_c(CYAN, len(sessions))} to score")
    print(f"   Threshold : {args.threshold} (Pass 2 triggered above this)")
    if args.date_from: print(f"   From      : {args.date_from}")
    if args.date_to:   print(f"   To        : {args.date_to}")
    if args.dry_run:   print(f"   Mode      : {_c(YELLOW, 'DRY RUN')}")
    print()

    if args.dry_run:
        for s in sessions:
            target = s.get("target") or Path(s.get("session_dir", "")).name
            print(f"  [{s['id']:5d}]  {str(s.get('session_date',''))[:16]}  {target}")
        conn.close()
        return

    pass1_only = pass2_done = 0

    for i, session in enumerate(sessions, 1):
        target   = session.get("target") or Path(session.get("session_dir", "")).name
        date_str = str(session.get("session_date", ""))[:16]

        score_c = None
        jpg     = None
        # Pass 1
        score_a, det_a = score_metadata(session)
        total_exp_s = det_a.get("total_exp_s", 0.0)

        if score_a < args.threshold:
            final_score = score_a
            pass1_only += 1
            tag = _c(YELLOW, f"A={score_a:5.1f}  (no image analysis)")
        else:
            # Pass 2
            jpg = find_stacked_jpg(session)
            if jpg:
                score_c, det_c = score_jpeg(jpg)
                final_score = round(score_a * 0.6 + score_c * 0.4, 1)
                pass2_done += 1
                tag = _c(GREEN, f"A={score_a:5.1f}  C={score_c:5.1f}  → {final_score:5.1f}")
            else:
                final_score = score_a
                pass1_only += 1
                tag = _c(CYAN, f"A={score_a:5.1f}  (no JPEG found)")

        # Save
        scored_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("""
            INSERT INTO SessionQuality
                (backup_entry_id, quality_score, total_exp_seconds, score_a, score_c, scored_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(backup_entry_id) DO UPDATE SET
                quality_score     = excluded.quality_score,
                total_exp_seconds = excluded.total_exp_seconds,
                score_a           = excluded.score_a,
                score_c           = excluded.score_c,
                scored_at         = excluded.scored_at
        """, (session["id"], final_score, total_exp_s, score_a, score_c, scored_at))
        conn.commit()

        print(f"  [{i:4d}/{len(sessions)}]  {date_str}  {target:<38s}  "
              f"{_bar(final_score, 10)}  {tag}")

    print()
    print(_c(BOLD, "─" * 60))
    print(f"  Pass 1 only  : {pass1_only}  (metadata score)")
    print(f"  Pass 2 done  : {pass2_done}  (+ image analysis)")
    print()
    print(f"  Run  {_c(CYAN, 'python tools/quality_scan.py --report')}  to see results.")
    print()

    conn.close()

def score_entry_ids(db_path: str, entry_ids: list, threshold: float = 40.0) -> int:
    """
    Score a specific list of BackupEntry ids.
    Reuses all existing scoring logic.
    Returns the number of sessions scored.
    """
    conn = connect_db(db_path)
    ensure_quality_table(conn)

    # Build session dicts using same query as get_sessions_to_score
    keys = ['id','session_date','session_dir','backup_drive_id',
            'quality_score','shotsStacked','shotsToTake','exp_time',
            'target','thumbnail_path','stacked_fits_path',
            'dwarf_file_path','drive_location','drive_astro_dir',
            'dwarf_type','stacked_fits_path2']

    scored = 0
    print(f"quality scoring for: {entry_ids}")
    for eid in entry_ids:
        rows = conn.execute("""
            SELECT BackupEntry.id, BackupEntry.session_date,
                   BackupEntry.session_dir, BackupEntry.backup_drive_id,
                   SessionQuality.quality_score,
                   DwarfData.shotsStacked, DwarfData.shotsToTake,
                   DwarfData.exp_time, DwarfData.target,
                   DwarfData.thumbnail_path, DwarfData.stacked_fits_path,
                   DwarfData.file_path, BackupDrive.location,
                   BackupDrive.astronomy_dir, Dwarf.type,
                   DwarfData.stacked_fits_path
            FROM BackupEntry
            JOIN DwarfData   ON BackupEntry.dwarf_data_id  = DwarfData.id
            JOIN BackupDrive ON BackupEntry.backup_drive_id = BackupDrive.id
            LEFT JOIN Dwarf  ON BackupEntry.dwarf_id = Dwarf.id
            LEFT JOIN SessionQuality ON BackupEntry.id = SessionQuality.backup_entry_id
            WHERE BackupEntry.id = ?
        """, (eid,)).fetchall()

        for r in rows:
            session = dict(zip(keys, r))
            score_a, det_a = score_metadata(session)
            total_exp_s = det_a.get("total_exp_s", 0.0)
            score_c = None
            jpg = find_stacked_jpg(session)
            if score_a >= threshold and jpg:
                score_c, _ = score_jpeg(jpg)
                final = round(score_a * 0.6 + score_c * 0.4, 1)
            else:
                final = score_a

            scored_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute("""
                INSERT INTO SessionQuality
                    (backup_entry_id, quality_score, total_exp_seconds,
                     score_a, score_c, scored_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(backup_entry_id) DO UPDATE SET
                    quality_score=excluded.quality_score,
                    total_exp_seconds=excluded.total_exp_seconds,
                    score_a=excluded.score_a,
                    score_c=excluded.score_c,
                    scored_at=excluded.scored_at
            """, (eid, final, total_exp_s, score_a, score_c, scored_at))
            conn.commit()
            scored += 1

    print(f"done : {scored}")
    conn.close()
    return scored

if __name__ == "__main__":
    main()

