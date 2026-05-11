#!/usr/bin/env python3
"""
tools/astrometry_scan.py — Batch astrometry solver for Dwarfium Scope Archive.

Finds sessions with quality_score >= 65 (green) that have no WCS solution yet,
and runs astrometry.net (local solve-field or Nova API) to compute WCS headers.
Results are stored in the SessionWCS table.

Works for both BackupEntry (Dwarf sessions) and ManualSessionEntry.

Usage:
    python tools/astrometry_scan.py [options]

Options:
    --report            Show pending/solved stats only, no solving
    --force             Re-solve already solved sessions
    --from YYYY-MM-DD   Only sessions from this date
    --to   YYYY-MM-DD   Only sessions up to this date
    --limit N           Max sessions to solve per run (default: 20)
    --min-quality N     Minimum quality score (default: 65)
    --dry-run           Show what would be solved, don't actually solve
    --session NAME      Filter by session dir name (partial match)
    --exact             Exact match on session dir name (no partial)
    --entry-type        Filter by entry type: backup | manual
    --astap-db D20|D50  ASTAP star database (default: D50)
    --astap-path PATH   Force ASTAP executable path
    --db PATH           Path to database (default: auto-detect)
"""

import argparse
import os
import re
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from api.dwarf_backup_db import DB_NAME, connect_db, close_db
from api.dwarf_backup_db_api import get_setting_text
from api.astrometry_resolver import auto_resolve, get_ra_dec_hint_from_fits, has_solve_field, has_astap
from api.dwarf_backup_fct import win_long_path

# ── Console colours ───────────────────────────────────────────────────────────
RED, GREEN, YELLOW, CYAN, RESET = '\033[91m', '\033[92m', '\033[93m', '\033[96m', '\033[0m'

def _c(col, s): return f"{col}{s}{RESET}" if sys.stdout.isatty() else s


# ── DB helpers ────────────────────────────────────────────────────────────────
def ensure_wcs_table(conn: sqlite3.Connection):
    """Create SessionWCS table if it doesn't exist, migrate if needed."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS SessionWCS (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_type      TEXT NOT NULL,
            entry_id        INTEGER NOT NULL,
            panel_num       INTEGER NOT NULL DEFAULT 0,
            ra_center       REAL,
            dec_center      REAL,
            crpix1          REAL,
            crpix2          REAL,
            crval1          REAL,
            crval2          REAL,
            cd1_1           REAL,
            cd1_2           REAL,
            cd2_1           REAL,
            cd2_2           REAL,
            plate_scale     REAL,
            orientation     REAL,
            wcs_file        TEXT,
            solver          TEXT,
            solved_at       TEXT NOT NULL
        )
    """)
    # Migration : ajouter panel_num si absent
    cols = [r[1] for r in conn.execute("PRAGMA table_info(SessionWCS)").fetchall()]
    if 'panel_num' not in cols:
        print("  [DB] Migrating SessionWCS: adding panel_num, rebuilding table...")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS SessionWCS_new (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_type      TEXT NOT NULL,
                entry_id        INTEGER NOT NULL,
                panel_num       INTEGER NOT NULL DEFAULT 0,
                ra_center       REAL,
                dec_center      REAL,
                crpix1          REAL,
                crpix2          REAL,
                crval1          REAL,
                crval2          REAL,
                cd1_1           REAL,
                cd1_2           REAL,
                cd2_1           REAL,
                cd2_2           REAL,
                plate_scale     REAL,
                orientation     REAL,
                wcs_file        TEXT,
                solver          TEXT,
                solved_at       TEXT NOT NULL
            )
        """)
        conn.execute("""
            INSERT INTO SessionWCS_new
                (entry_type, entry_id, panel_num,
                 ra_center, dec_center, crpix1, crpix2, crval1, crval2,
                 cd1_1, cd1_2, cd2_1, cd2_2,
                 plate_scale, orientation, wcs_file, solver, solved_at)
            SELECT entry_type, entry_id, 0,
                   ra_center, dec_center, crpix1, crpix2, crval1, crval2,
                   cd1_1, cd1_2, cd2_1, cd2_2,
                   plate_scale, orientation, wcs_file, solver, solved_at
            FROM SessionWCS
        """)
        conn.execute("DROP TABLE SessionWCS")
        conn.execute("ALTER TABLE SessionWCS_new RENAME TO SessionWCS")
        print("  [DB] Migration done.")

    # Index unique sur (entry_type, entry_id, panel_num)
    conn.execute("DROP INDEX IF EXISTS idx_sessionwcs_entry")
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_sessionwcs_entry
        ON SessionWCS(entry_type, entry_id, panel_num)
    """)
    conn.commit()


def get_sessions_to_solve(conn, date_from, date_to, force, min_quality, limit,
                           session_filter=None, re_solver=None, exact=False, entry_type=None,
                           max_quality=None, dwarf_filter=None, fix_null_ra=False):
    """Return sessions with good quality but no WCS yet."""
    sessions = []

    # ── BackupEntry sessions ───────────────────────────────────────────────────
    if entry_type in (None, 'backup'):
        q = """
            SELECT
                'backup'                  AS entry_type,
                BackupEntry.id            AS entry_id,
                BackupEntry.session_date,
                BackupEntry.session_dir,
                DwarfData.file_path       AS dwarf_file_path,
                DwarfData.stacked_fits_path,
                BackupDrive.location      AS drive_location,
                AstroObject.name          AS object_name,
                SessionQuality.quality_score
            FROM BackupEntry
            JOIN DwarfData      ON BackupEntry.dwarf_data_id   = DwarfData.id
            JOIN BackupDrive    ON BackupEntry.backup_drive_id  = BackupDrive.id
            LEFT JOIN SessionQuality ON BackupEntry.id           = SessionQuality.backup_entry_id
            LEFT JOIN AstroObject    ON BackupEntry.astro_object_id = AstroObject.id
            LEFT JOIN SessionWCS     ON SessionWCS.entry_type = 'backup'
                                    AND SessionWCS.entry_id  = BackupEntry.id
                                    AND SessionWCS.panel_num = 0
            LEFT JOIN Dwarf          ON BackupEntry.dwarf_id = Dwarf.id
            WHERE (SessionQuality.quality_score >= ? OR (? = 0 AND SessionQuality.backup_entry_id IS NULL))
        """
        params = [min_quality, min_quality]
        if max_quality is not None:
            q += " AND SessionQuality.quality_score <= ?"
            params.append(max_quality)
        if dwarf_filter:
            q += " AND Dwarf.name = ?"
            params.append(dwarf_filter)
        if fix_null_ra:
            # Re-solve sessions that have a WCS entry but ra_center is NULL
            q += " AND SessionWCS.id IS NOT NULL AND SessionWCS.ra_center IS NULL"
        elif not force:
            q += " AND SessionWCS.id IS NULL"
        elif re_solver:
            q += " AND SessionWCS.solver = ?"
            params.append(re_solver)
        if date_from:
            q += " AND BackupEntry.session_date >= ?"
            params.append(date_from)
        if date_to:
            q += " AND BackupEntry.session_date <= ?"
            params.append(date_to + "T23:59:59")
        if session_filter:
            if exact:
                q += " AND BackupEntry.session_dir = ?"
                params.append(session_filter)
            else:
                q += " AND LOWER(BackupEntry.session_dir) LIKE ?"
                params.append(f"%{session_filter.lower()}%")
        q += " GROUP BY BackupEntry.id"
        q += " ORDER BY SessionQuality.quality_score DESC"
        if limit:
            q += f" LIMIT {limit}"

        for row in conn.execute(q, params).fetchall():
            sessions.append(dict(zip(
                ['entry_type', 'entry_id', 'session_date', 'session_dir',
                 'dwarf_file_path', 'stacked_fits_path', 'drive_location',
                 'object_name', 'quality_score'], row
            )))

    remaining = limit - len(sessions) if limit else None

    # ── ManualSessionEntry sessions ────────────────────────────────────────────
    if entry_type in (None, 'manual') and (remaining is None or remaining > 0):
        q2 = """
            SELECT
                'manual'                        AS entry_type,
                ManualSessionEntry.id           AS entry_id,
                ManualSessionEntry.session_date,
                ManualSessionEntry.session_dir,
                ManualSession.jpeg_path         AS dwarf_file_path,
                ManualSession.stacked_fits_path AS stacked_fits_path,
                ManualSessionDrive.location     AS drive_location,
                AstroObject.name                AS object_name,
                NULL                            AS quality_score
            FROM ManualSessionEntry
            JOIN ManualSession ON ManualSessionEntry.manual_session_id = ManualSession.id
            LEFT JOIN ManualSessionDrive ON ManualSessionEntry.manual_session_drive = ManualSessionDrive.id
            LEFT JOIN AstroObject        ON ManualSessionEntry.astro_object_id = AstroObject.id
            LEFT JOIN SessionWCS         ON SessionWCS.entry_type = 'manual'
                                        AND SessionWCS.entry_id  = ManualSessionEntry.id
            WHERE ManualSession.jpeg_path IS NOT NULL
               OR ManualSession.stacked_fits_path IS NOT NULL
        """
        params2 = []
        if not force:
            q2 += " AND SessionWCS.id IS NULL"
        if date_from:
            q2 += " AND ManualSessionEntry.session_date >= ?"
            params2.append(date_from)
        if date_to:
            q2 += " AND ManualSessionEntry.session_date <= ?"
            params2.append(date_to + "T23:59:59")
        if session_filter:
            if exact:
                q2 += " AND ManualSessionEntry.session_dir = ?"
                params2.append(session_filter)
            else:
                q2 += " AND LOWER(ManualSessionEntry.session_dir) LIKE ?"
                params2.append(f"%{session_filter.lower()}%")
        q2 += " ORDER BY ManualSessionEntry.session_date DESC"
        if remaining:
            q2 += f" LIMIT {remaining}"

        for row in conn.execute(q2, params2).fetchall():
            sessions.append(dict(zip(
                ['entry_type', 'entry_id', 'session_date', 'session_dir',
                 'dwarf_file_path', 'stacked_fits_path', 'drive_location',
                 'object_name', 'quality_score'], row
            )))

    return sessions


def crop_center(fits_path: Path, margin: float = 0.25) -> Path:
    """
    Crop a fixed margin from each border to keep only the center.
    Default: 25% margin on each side → keeps central 50% of the image.
    Used to avoid stacking border artefacts when solving astrometry.
    Temp file written to tempdir to avoid Windows long path issues.
    """
    try:
        import numpy as np
        from astropy.io import fits as _fits

        with _fits.open(win_long_path(fits_path)) as hdul:
            data = hdul[0].data.astype(np.float32)
            hdr  = hdul[0].header.copy()

        h = data.shape[-2]
        w = data.shape[-1]
        x0 = int(w * margin)
        x1 = int(w * (1 - margin))
        y0 = int(h * margin)
        y1 = int(h * (1 - margin))

        cropped = data[..., y0:y1, x0:x1]
        hdr['NAXIS1'] = x1 - x0
        hdr['NAXIS2'] = y1 - y0
        if 'CRPIX1' in hdr: hdr['CRPIX1'] = float(hdr['CRPIX1']) - x0
        if 'CRPIX2' in hdr: hdr['CRPIX2'] = float(hdr['CRPIX2']) - y0

        tmp_path = Path(tempfile.gettempdir()) / (fits_path.stem + '_crop_tmp.fits')
        _fits.writeto(str(tmp_path), cropped, hdr, overwrite=True)
        print(f"  [crop] {w}x{h} -> {x1-x0}x{y1-y0} (margin={int(margin*100)}%)")
        return tmp_path

    except Exception as e:
        print(f"  [crop] Error: {e}")
        return fits_path


def extract_mono_fits(fits_path: Path) -> Path | None:
    """
    If FITS has NAXIS3 > 1 (colour cube), extract green channel as temp mono FITS.
    ASTAP requires single-channel image.
    Temp file written to tempdir to avoid Windows long path issues.
    Returns original path if already mono, temp file path if colour cube.
    """
    try:
        from astropy.io import fits as _fits
        import numpy as np

        with _fits.open(win_long_path(fits_path)) as hdul:
            data = hdul[0].data
            hdr  = hdul[0].header.copy()

        if data is None or data.ndim < 3:
            return fits_path  # already mono

        # data shape: (3, H, W) — extract green channel (index 1)
        mono = data[1].astype(np.float32)
        hdr['NAXIS'] = 2
        if 'NAXIS3' in hdr:
            del hdr['NAXIS3']

        tmp_path = Path(tempfile.gettempdir()) / (fits_path.stem + '_mono_tmp.fits')
        _fits.writeto(str(tmp_path), mono, hdr, overwrite=True)
        return tmp_path

    except Exception as e:
        print(f"  [FITS] Cannot extract mono channel: {e}")
        return None


def _cleanup_temp(image_path: Path | None):
    """Remove temp mono/crop FITS files from tempdir and session folder."""
    tmp_dir = Path(tempfile.gettempdir())
    for pattern in ['*_mono_tmp.fits', '*_crop_tmp.fits']:
        for tmp in tmp_dir.glob(pattern):
            try:
                tmp.unlink()
            except Exception:
                pass
    # Also clean *.wcs.fits left by Nova/solve-field in session folder
    if image_path:
        for tmp in image_path.parent.glob('*.wcs.fits'):
            try:
                tmp.unlink()
            except Exception:
                pass


def detect_mosaic_restitched(session: dict) -> tuple[bool, bool, Path | None, Path | None]:
    """
    Detect if a mosaic session has been restitched.
    Returns (is_mosaic, is_restitched, session_folder, fits_path)
    - is_mosaic      : True if session dir contains _MOSAIC_
    - is_restitched  : True if FITS is newer than any PNG (= user ran restitch)
    - session_folder : Path to the mosaic folder
    - fits_path      : Path to the global stacked FITS (if exists)
    """
    drive    = session.get('drive_location') or ''
    fits_rel = session.get('stacked_fits_path') or ''
    file_rel = session.get('dwarf_file_path') or ''

    if not drive or not file_rel:
        return False, False, None, None

    session_folder = Path(drive) / Path(file_rel).parent
    if '_MOSAIC_' not in str(session_folder).upper() or not session_folder.exists():
        return False, False, None, None

    fits_path = (Path(drive) / fits_rel) if fits_rel else None
    pngs = list(session_folder.glob('*.png'))

    is_restitched = False
    if pngs and fits_path and fits_path.exists():
        png_mtime  = max(p.stat().st_mtime for p in pngs)
        fits_mtime = fits_path.stat().st_mtime
        is_restitched = fits_mtime > png_mtime

    return True, is_restitched, session_folder, fits_path


def find_image_for_session(session: dict, crop: bool = False, crop_margin: float = 0.20) -> tuple[Path | None, str]:
    """
    Find the best image to send to the solver.
    Priority: stacked FITS > stacked JPG > manual JPEG
    For mosaics: uses global restitched FITS if available, else middle panel FITS.
    Returns (path, 'fits'|'jpg'|None)
    """
    drive    = session.get('drive_location') or ''
    fits_rel = session.get('stacked_fits_path') or ''
    file_rel = session.get('dwarf_file_path') or ''

    # For mosaics: pick the right image (restitched global FITS or middle panel)
    is_mosaic, is_restitched, session_folder, fits_path = detect_mosaic_restitched(session)
    if is_mosaic:
        if is_restitched and fits_path and fits_path.exists():
            # Restitched → use global FITS (panel 0 will be solved in main loop)
            mono = extract_mono_fits(fits_path)
            if mono:
                cropped = crop_center(mono, crop_margin) if crop else mono
                return cropped, 'fits'

        # Raw mosaic (or restitched FITS unreadable) → middle panel FITS for hint only
        # Actual solving is done panel-by-panel in main loop; return None here so
        # main loop can detect this case and call _solve_mosaic_panels directly.
        return None, 'mosaic_panels'

    # 1. Stacked FITS — best quality, extract mono if colour cube
    if drive and fits_rel:
        p = Path(drive) / fits_rel
        if p.exists():
            mono = extract_mono_fits(p)
            if mono:
                cropped = crop_center(mono, crop_margin) if crop else mono
                return cropped, 'fits'

    # 2. stacked.jpg — fallback if no FITS
    if drive and file_rel:
        session_folder = Path(drive) / Path(file_rel).parent
        jpg = session_folder / 'stacked.jpg'
        if jpg.exists():
            return jpg, 'jpg'

    # 3. Manual JPEG (absolute or relative to location)
    if file_rel:
        p = Path(file_rel)
        if p.is_absolute() and p.exists():
            return p, 'jpg'
        if drive:
            p2 = Path(drive) / file_rel
            if p2.exists():
                return p2, 'jpg'

    return None, None


def _parse_ini_wcs(ini_path: str) -> dict | None:
    """Parse ASTAP .ini file which contains all WCS values as key=value pairs."""
    try:
        vals = {}
        for line in Path(ini_path).read_text(encoding='utf-8', errors='replace').splitlines():
            if '=' in line and not line.startswith('CMDLINE') and not line.startswith('COMMENT'):
                k, v = line.split('=', 1)
                try:
                    vals[k.strip()] = float(v.strip())
                except ValueError:
                    vals[k.strip()] = v.strip()

        if vals.get('PLTSOLVD') != 'T':
            return None

        ra     = vals.get('CRVAL1')
        dec    = vals.get('CRVAL2')
        cdelt1 = vals.get('CDELT1')
        crota2 = vals.get('CROTA2') or vals.get('CROTA1') or 0.0
        cd11   = vals.get('CD1_1')
        cd12   = vals.get('CD1_2')
        cd21   = vals.get('CD2_1')
        cd22   = vals.get('CD2_2')

        return {
            'ra_center':   float(ra),
            'dec_center':  float(dec),
            'crpix1':      vals.get('CRPIX1'),
            'crpix2':      vals.get('CRPIX2'),
            'crval1':      float(ra),
            'crval2':      float(dec),
            'cd1_1':       float(cd11) if cd11 is not None else None,
            'cd1_2':       float(cd12) if cd12 is not None else None,
            'cd2_1':       float(cd21) if cd21 is not None else None,
            'cd2_2':       float(cd22) if cd22 is not None else None,
            'plate_scale': abs(cdelt1) * 3600.0 if cdelt1 else None,
            'orientation': float(crota2) if crota2 is not None else None,
        }
    except Exception as e:
        print(f"  [INI] Error parsing ASTAP ini: {e}")
        return None


def extract_wcs_from_file(wcs_file: str) -> dict | None:
    """
    Extract WCS parameters from a solved file.
    For ASTAP: reads from .ini (reliable) then .wcs as fallback.
    For Nova/solve-field: reads from FITS.
    """
    # Try ASTAP .ini first — clean key=value format, always reliable
    ini_file = str(Path(wcs_file).with_suffix('.ini'))
    if Path(ini_file).exists():
        result = _parse_ini_wcs(ini_file)
        if result:
            return result

    try:
        from astropy.io import fits as astropy_fits
        from astropy.wcs import WCS
        import math
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with astropy_fits.open(wcs_file, ignore_missing_end=True) as hdul:
                hdr = hdul[0].header

        wcs = WCS(hdr)
        if not wcs.has_celestial:
            return None

        ra     = hdr.get('CRVAL1') or wcs.wcs.crval[0]
        dec    = hdr.get('CRVAL2') or wcs.wcs.crval[1]
        crpix1 = hdr.get('CRPIX1') or wcs.wcs.crpix[0]
        crpix2 = hdr.get('CRPIX2') or wcs.wcs.crpix[1]

        cd11 = hdr.get('CD1_1')
        cd12 = hdr.get('CD1_2')
        cd21 = hdr.get('CD2_1')
        cd22 = hdr.get('CD2_2')

        # Fallback: compute CD from CDELT + CROTA
        if cd11 is None:
            cdelt1 = hdr.get('CDELT1')
            cdelt2 = hdr.get('CDELT2')
            crota  = hdr.get('CROTA2') or hdr.get('CROTA1') or 0.0
            if cdelt1 is not None and cdelt2 is not None:
                cos_r = math.cos(math.radians(crota))
                sin_r = math.sin(math.radians(crota))
                cd11 =  cdelt1 * cos_r
                cd12 = -cdelt2 * sin_r
                cd21 =  cdelt1 * sin_r
                cd22 =  cdelt2 * cos_r

        # Plate scale (arcsec/pixel)
        try:
            plate_scale = 3600.0 * abs(wcs.proj_plane_pixel_scales()[0].value)
        except Exception:
            cdelt1 = hdr.get('CDELT1')
            plate_scale = abs(cdelt1) * 3600.0 if cdelt1 else (
                math.sqrt(cd11**2 + cd21**2) * 3600.0 if cd11 is not None else None
            )

        # Orientation
        crota2 = hdr.get('CROTA2') or hdr.get('CROTA1')
        if crota2 is not None:
            orientation = float(crota2)
        elif cd11 is not None and cd12 is not None:
            orientation = math.degrees(math.atan2(-cd12, cd11))
        else:
            orientation = None

        return {
            'ra_center':   float(ra),
            'dec_center':  float(dec),
            'crpix1':      float(crpix1),
            'crpix2':      float(crpix2),
            'crval1':      float(ra),
            'crval2':      float(dec),
            'cd1_1':       float(cd11) if cd11 is not None else None,
            'cd1_2':       float(cd12) if cd12 is not None else None,
            'cd2_1':       float(cd21) if cd21 is not None else None,
            'cd2_2':       float(cd22) if cd22 is not None else None,
            'plate_scale': float(plate_scale) if plate_scale is not None else None,
            'orientation': float(orientation) if orientation is not None else None,
        }
    except Exception as e:
        print(f"  [WCS] Error extracting WCS: {e}")
        return None


def save_wcs(conn, session, wcs_data, wcs_file, solver, panel_num=0):
    """Save WCS result to SessionWCS table. Retries on database locked."""
    import time
    solved_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    sql = """
        INSERT INTO SessionWCS
            (entry_type, entry_id, panel_num,
             ra_center, dec_center,
             crpix1, crpix2, crval1, crval2,
             cd1_1, cd1_2, cd2_1, cd2_2,
             plate_scale, orientation, wcs_file, solver, solved_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(entry_type, entry_id, panel_num) DO UPDATE SET
            ra_center=excluded.ra_center, dec_center=excluded.dec_center,
            crpix1=excluded.crpix1, crpix2=excluded.crpix2,
            crval1=excluded.crval1, crval2=excluded.crval2,
            cd1_1=excluded.cd1_1, cd1_2=excluded.cd1_2,
            cd2_1=excluded.cd2_1, cd2_2=excluded.cd2_2,
            plate_scale=excluded.plate_scale, orientation=excluded.orientation,
            wcs_file=excluded.wcs_file, solver=excluded.solver,
            solved_at=excluded.solved_at
    """
    params = (
        session['entry_type'], session['entry_id'], panel_num,
        wcs_data.get('ra_center'), wcs_data.get('dec_center'),
        wcs_data.get('crpix1'),    wcs_data.get('crpix2'),
        wcs_data.get('crval1'),    wcs_data.get('crval2'),
        wcs_data.get('cd1_1'),     wcs_data.get('cd1_2'),
        wcs_data.get('cd2_1'),     wcs_data.get('cd2_2'),
        wcs_data.get('plate_scale'), wcs_data.get('orientation'),
        wcs_file, solver, solved_at,
    )
    for attempt in range(5):
        try:
            conn.execute(sql, params)
            conn.commit()
            return
        except Exception as e:
            if 'locked' in str(e).lower() and attempt < 4:
                print(f"  ⚠️  DB locked — retrying in 3s ({attempt+1}/5)...")
                time.sleep(3)
            else:
                raise


# ── Report ────────────────────────────────────────────────────────────────────
def print_report(conn, min_quality):
    total_backup  = conn.execute("SELECT COUNT(*) FROM BackupEntry").fetchone()[0]
    total_manual  = conn.execute("SELECT COUNT(*) FROM ManualSessionEntry").fetchone()[0]
    solved        = conn.execute("SELECT COUNT(*) FROM SessionWCS").fetchone()[0]
    solved_backup = conn.execute("SELECT COUNT(*) FROM SessionWCS WHERE entry_type='backup'").fetchone()[0]
    solved_manual = conn.execute("SELECT COUNT(*) FROM SessionWCS WHERE entry_type='manual'").fetchone()[0]

    eligible = conn.execute("""
        SELECT COUNT(*) FROM SessionQuality WHERE quality_score >= ?
    """, (min_quality,)).fetchone()[0]

    pending = max(0, eligible - solved_backup)

    print(f"\n{'='*60}")
    print(f"  Astrometry WCS Report")
    print(f"{'-'*60}")
    print(f"  Sessions total   : {total_backup} backup + {total_manual} manual")
    print(f"  Eligible (≥{min_quality})   : {eligible}")
    print(f"  Solved           : {solved} ({solved_backup} backup, {solved_manual} manual)")
    print(f"  Pending          : {pending}")
    print(f"{'-'*60}")

    for solver, count in conn.execute(
        "SELECT solver, COUNT(*) FROM SessionWCS GROUP BY solver"
    ).fetchall():
        print(f"  {solver:10s}: {count} solved")

    rows = conn.execute("""
        SELECT sw.entry_type, sw.ra_center, sw.dec_center,
               sw.plate_scale, sw.solver, sw.solved_at,
               COALESCE(ao_b.name, ao_m.name, '-')          AS obj,
               COALESCE(be.session_dir, me.session_dir, '-') AS session_dir
        FROM SessionWCS sw
        LEFT JOIN BackupEntry        be   ON sw.entry_type = 'backup' AND sw.entry_id = be.id
        LEFT JOIN AstroObject        ao_b ON be.astro_object_id = ao_b.id
        LEFT JOIN ManualSessionEntry me   ON sw.entry_type = 'manual' AND sw.entry_id = me.id
        LEFT JOIN AstroObject        ao_m ON me.astro_object_id = ao_m.id
        ORDER BY sw.solved_at DESC LIMIT 10
    """).fetchall()

    if rows:
        GENERIC = {'mosaic_unknown', 'unknown', 'manual', '-'}
        print(f"\n  Recent solves:")
        print(f"  {'Type':8s} {'Object/Session':50s} {'RA':>9s} {'DEC':>9s} {'Scale\"':>7s} {'Solver':8s}")
        print(f"  {'-'*95}")
        for r in rows:
            scale = f"{r[3]:.2f}" if r[3] else "?"
            obj   = r[6]
            if obj.lower() in GENERIC:
                s = Path(r[7]).name if r[7] else '-'
                for pfx in ('RESTACKED_DWARF_RAW_TELE_MOSAIC_', 'RESTACKED_DWARF_RAW_WIDE_MOSAIC_',
                            'RESTACKED_DWARF_RAW_TELE_', 'RESTACKED_DWARF_RAW_WIDE_',
                            'DWARF_RAW_TELE_MOSAIC_', 'DWARF_RAW_WIDE_MOSAIC_',
                            'DWARF_RAW_TELE_', 'DWARF_RAW_WIDE_'):
                    if s.upper().startswith(pfx):
                        s = s[len(pfx):]
                        break
                obj = s[:50]
            ra_s  = f"{r[1]:9.4f}" if r[1] is not None else "        ?"
            dec_s = f"{r[2]:9.4f}" if r[2] is not None else "        ?"
            print(f"  {r[0]:8s} {obj:50s} {ra_s} {dec_s} {scale:>7s} {r[4]:8s}")
    print(f"{'='*60}\n")


def _solve_mosaic_panels(conn, session, api_key, astap_db, crop, crop_margin, solver):
    """Résoudre chaque panel d'une mosaïque et stocker avec panel_num 1,2,3..."""
    drive    = session.get('drive_location') or ''
    file_rel = session.get('dwarf_file_path') or ''
    if not drive or not file_rel:
        return

    session_folder = Path(drive) / Path(file_rel).parent
    if not session_folder.exists():
        return

    panel_dirs = sorted([d for d in session_folder.iterdir()
                         if d.is_dir() and re.search(r'\(\d+\)', d.name)])
    if not panel_dirs:
        return

    print(f"\n      [MOSAIC] Solving {len(panel_dirs)} panels... [id={session.get('entry_id','?')}] session={session.get('session_dir','?')}")
    for panel_num, panel_dir in enumerate(panel_dirs, start=1):
        # Trouver le FITS du panel
        fits_files = list(panel_dir.glob('stacked-*.fits')) + list(panel_dir.glob('stacked.fits'))
        if not fits_files:
            jpg = panel_dir / 'stacked.jpg'
            panel_img = jpg if jpg.exists() else None
            img_type  = 'jpg'
        else:
            mono = extract_mono_fits(fits_files[0])
            panel_img = crop_center(mono, crop_margin) if (crop and mono) else mono
            img_type  = 'fits'

        if not panel_img:
            print(f"      [MOSAIC] panel {panel_num}: no image")
            continue

        try:
            ra_hint, dec_hint = get_ra_dec_hint_from_fits(str(fits_files[0])) if fits_files else (None, None)
            wcs_file = auto_resolve(api_key, str(panel_img), astap_db=astap_db,
                                    ra_hint=ra_hint, dec_hint=dec_hint)
            wcs_data = extract_wcs_from_file(wcs_file)
            if wcs_data:
                save_wcs(conn, session, wcs_data, wcs_file, solver, panel_num=panel_num)
                print(f"      [MOSAIC] panel {panel_num}: ✅ RA={wcs_data['ra_center']:.4f} DEC={wcs_data['dec_center']:.4f}")
            else:
                print(f"      [MOSAIC] panel {panel_num}: WCS extraction failed")
        except Exception as e:
            print(f"      [MOSAIC] panel {panel_num}: ❌ {e}")
        finally:
            _cleanup_temp(panel_img)

    # ── Panel 0 : centre depuis le FITS d'origine ou bbox des panels ──────────
    # ra_hint from FITS header — already in degrees (get_ra_dec_hint_from_fits converts)
    ra_hint  = session.get('ra_hint')
    dec_hint = session.get('dec_hint')

    solved = conn.execute("""
        SELECT ra_center, dec_center FROM SessionWCS
        WHERE entry_type=? AND entry_id=? AND panel_num > 0
          AND ra_center IS NOT NULL
    """, (session['entry_type'], session['entry_id'])).fetchall()

    if solved:
        if ra_hint is not None and dec_hint is not None:
            # Coordonnées cibles du FITS — déjà en degrés
            ra_c  = float(ra_hint)
            dec_c = float(dec_hint)
        else:
            # Fallback : centre du bbox des panels résolus
            ras  = [r[0] for r in solved]
            decs = [r[1] for r in solved]
            if max(ras) - min(ras) > 180:
                ras = [ra + 360 if ra < 180 else ra for ra in ras]
            ra_c  = ((min(ras) + max(ras)) / 2) % 360
            dec_c = (min(decs) + max(decs)) / 2

        save_wcs(conn, session,
                 {'ra_center': ra_c, 'dec_center': dec_c,
                  'crval1': ra_c, 'crval2': dec_c,
                  'crpix1': None, 'crpix2': None,
                  'cd1_1': None, 'cd1_2': None, 'cd2_1': None, 'cd2_2': None,
                  'plate_scale': None, 'orientation': None},
                 '', solver, panel_num=0)
        src = 'FITS hint' if ra_hint else 'bbox'
        print(f"      [MOSAIC] panel 0 ({src}): RA={ra_c:.4f} DEC={dec_c:.4f} ({len(solved)} panels)")



def main():
    import sys
    # Force UTF-8 output on Windows to avoid cp1252 encoding errors
    if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

    parser = argparse.ArgumentParser(description="Batch astrometry solver for Dwarfium Scope Archive")
    parser.add_argument('--report',      action='store_true', help='Show stats only')
    parser.add_argument('--force',       action='store_true', help='Re-solve already solved sessions')
    parser.add_argument('--from',        dest='date_from',    help='Start date YYYY-MM-DD')
    parser.add_argument('--to',          dest='date_to',      help='End date YYYY-MM-DD')
    parser.add_argument('--limit',       type=int, default=20, help='Max sessions per run (default: 20)')
    parser.add_argument('--min-quality', type=float, default=65.0, help='Min quality score (default: 65)')
    parser.add_argument('--max-quality', type=float, default=None,  help='Max quality score (optional, e.g. 69)')
    parser.add_argument('--fix-null-ra',  action='store_true', help='Re-solve sessions with ra_center IS NULL in SessionWCS')
    parser.add_argument('--dwarf',        default=None,        help='Filter by Dwarf name (exact match, e.g. "Dwarf Mini")')
    parser.add_argument('--dry-run',     action='store_true', help='Show what would be solved')
    parser.add_argument('--db',          default=DB_NAME,     help='Database path')
    parser.add_argument('--session',     default=None,        help='Filter by session dir name (partial match)')
    parser.add_argument('--exact',       action='store_true', help='Exact match on session dir name (no partial)')
    parser.add_argument('--entry-type',  default=None,        choices=['backup', 'manual'], help='Filter by entry type')
    parser.add_argument('--astap-path',  default=None,        help='Force ASTAP executable path')
    parser.add_argument('--crop',        action='store_true', help='Crop borders before solving (helps with stacking artefacts)')
    parser.add_argument('--re-solver',   default=None,        help='Re-solve only sessions solved by this solver (e.g. nova, astap)')
    parser.add_argument('--crop-margin', type=float, default=0.20, help='Crop margin on each side (default: 0.20 = 20%%)')
    parser.add_argument('--delay',        type=float, default=2.0,  help='Delay in seconds between sessions (default: 2)')
    args = parser.parse_args()

    conn = connect_db(args.db)
    ensure_wcs_table(conn)

    if args.report:
        print_report(conn, args.min_quality)
        close_db(conn)
        return

    api_key  = get_setting_text(conn, 'NOVA_ASTRO_API') or ''
    astap_db = getattr(args, 'astap_db', None) or get_setting_text(conn, 'ASTAP_DB') or 'D50'
    if args.astap_path:
        os.environ['ASTAP_PATH'] = args.astap_path

    solver_mode = 'astap' if has_astap() else ('local' if has_solve_field() else ('nova' if api_key else None))

    if solver_mode is None:
        print(_c(RED, "❌ No solver available. Install solve-field or set Nova API key in Settings."))
        close_db(conn)
        return

    print(f"\n  Solver: {_c(CYAN, solver_mode.upper())}")
    if has_astap():
        print(f"  (ASTAP found — Nova API fallback: {'enabled' if api_key else 'no key configured'})")
    elif not has_solve_field() and api_key:
        print(f"  (solve-field not found — using Nova API)")
    elif not has_solve_field() and not api_key:
        print(f"  ⚠️  No fallback solver — set Nova API key in Settings for difficult images")

    # ── Lock file — prevent concurrent scans ─────────────────────────────────
    import tempfile
    lock_file = Path(tempfile.gettempdir()) / 'astrometry_scan.lock'
    if lock_file.exists():
        try:
            pid = int(lock_file.read_text().strip())
            print(_c(RED, f"❌ Scan already running (PID {pid}). Stop it before launching a new one."))
            close_db(conn)
            return
        except Exception:
            pass  # stale lock or unreadable — proceed
    lock_file.write_text(str(os.getpid()))

    try:
        _run_scan(conn, args, api_key, astap_db, solver_mode)
    except KeyboardInterrupt:
        print(_c(YELLOW, "\n  ⚠️  Scan interrupted by user (Ctrl-C)"))
    finally:
        lock_file.unlink(missing_ok=True)
        close_db(conn)


def _run_scan(conn, args, api_key, astap_db, solver_mode):
    """Main scan logic — separated so lock file is always cleaned up."""
    sessions = get_sessions_to_solve(
        conn, args.date_from, args.date_to,
        args.force, args.min_quality, args.limit,
        session_filter=args.session,
        re_solver=args.re_solver,
        exact=args.exact,
        entry_type=args.entry_type,
        max_quality=args.max_quality,
        dwarf_filter=args.dwarf,
        fix_null_ra=args.fix_null_ra,
    )

    if not sessions:
        print(_c(YELLOW, f"\n  No sessions to solve (min quality: {args.min_quality})."))
        print_report(conn, args.min_quality)
        close_db(conn)
        return

    print(f"\n  Found {len(sessions)} session(s) to solve\n")
    print(f"  {'#':>3s}  {'Type':8s} {'Object':25s} {'Score':>6s}  {'Image':5s}  Status")
    print(f"  {'-'*72}")

    solved = failed = skipped = 0

    for i, session in enumerate(sessions, 1):
        obj     = (session.get('object_name') or '?')[:25]
        score   = session.get('quality_score')
        score_s = f"{score:.0f}" if score else "?"

        image_path, img_type = find_image_for_session(
            session, crop=args.crop, crop_margin=args.crop_margin
        )

        # Read RA/DEC hints from original FITS header (before mono extraction)
        if session.get('stacked_fits_path') and session.get('drive_location'):
            orig_fits = Path(session['drive_location']) / session['stacked_fits_path']
            if orig_fits.exists():
                ra, dec = get_ra_dec_hint_from_fits(str(orig_fits))
                session['ra_hint']  = ra
                session['dec_hint'] = dec

        # Skip solar system objects — no star field for plate solving
        SKIP_OBJECTS = {'sun', 'moon', 'lune', 'soleil', 'jupiter', 'saturn',
                        'saturne', 'mars', 'venus', 'mercury', 'mercure',
                        'uranus', 'neptune', 'solar', 'solaire'}
        if any(skip in (session.get('object_name') or '').lower() for skip in SKIP_OBJECTS):
            print(f"  {i:>3d}  {session['entry_type']:8s} {obj:25s} {score_s:>6s}  {'skip':5s}  "
                  + _c(YELLOW, "solar system object — skipped"))
            skipped += 1
            continue

        # ── Detect mosaic type early (needed for force cleanup) ──────────────
        is_mosaic, is_restitched, mosaic_folder, _ = detect_mosaic_restitched(session)

        # ── Force: clean up conflicting panels before re-solving ─────────────
        if args.force and is_mosaic:
            if is_restitched:
                # Will solve panel 0 → remove stale individual panels
                n = conn.execute("""
                    DELETE FROM SessionWCS
                    WHERE entry_type=? AND entry_id=? AND panel_num > 0
                """, (session['entry_type'], session['entry_id'])).rowcount
                conn.commit()
                if n:
                    print(f"      [MOSAIC] force: removed {n} individual panel(s) (restitched → panel 0 only)")
            else:
                # Will solve individual panels → remove stale panel 0
                n = conn.execute("""
                    DELETE FROM SessionWCS
                    WHERE entry_type=? AND entry_id=? AND panel_num = 0
                """, (session['entry_type'], session['entry_id'])).rowcount
                conn.commit()
                if n:
                    print(f"      [MOSAIC] force: removed panel 0 (raw mosaic → individual panels only)")

        # ── Mosaic: panels-only path (raw mosaic, no restitched FITS) ────────
        if img_type == 'mosaic_panels':
            entry_id = session.get('entry_id', '?')
            print(f"  {i:>3d}  {session['entry_type']:8s} {obj:25s} {score_s:>6s}  {'panel':5s}  "
                  + _c(CYAN, f"[id={entry_id}] raw mosaic — solving individual panels..."))
            if not args.dry_run:
                _solve_mosaic_panels(conn, session, api_key, astap_db,
                                     args.crop, args.crop_margin, solver_mode)
            solved += 1
            continue

        if not image_path:
            print(f"  {i:>3d}  {session['entry_type']:8s} {obj:25s} {score_s:>6s}  {'?':5s}  "
                  + _c(YELLOW, "no image found"))
            skipped += 1
            continue

        if args.dry_run:
            print(f"  {i:>3d}  {session['entry_type']:8s} {obj:25s} {score_s:>6s}  {img_type:5s}  "
                  + _c(CYAN, f"[dry-run] {image_path.name}"))
            continue

        try:
            entry_id = session.get('entry_id', '?')
            print(f"  {i:>3d}  {session['entry_type']:8s} {obj:25s} {score_s:>6s}  {img_type:5s}  "
                  + _c(CYAN, f"[id={entry_id}] solving {image_path.name} ({image_path.stat().st_size//1024}KB)..."),
                  end='', flush=True)

            ra_hint  = session.get('ra_hint')
            dec_hint = session.get('dec_hint')
            wcs_file = auto_resolve(api_key, str(image_path), astap_db=astap_db,
                                    ra_hint=ra_hint, dec_hint=dec_hint)
            wcs_data = extract_wcs_from_file(wcs_file)

            if wcs_data:
                if wcs_file.endswith('.ini'):
                    actual_solver = 'astap'
                elif 'nova' in wcs_file.lower() or wcs_file.endswith('.wcs'):
                    actual_solver = 'nova'
                elif has_solve_field():
                    actual_solver = 'local'
                else:
                    actual_solver = 'nova'

                # Correct CRPIX to original image coords if crop was used
                if args.crop and wcs_data and img_type == 'fits':
                    try:
                        from astropy.io import fits as _fits
                        import warnings
                        mono_candidate = Path(tempfile.gettempdir()) / \
                            image_path.name.replace('_crop_tmp.fits', '_mono_tmp.fits')
                        if not mono_candidate.exists():
                            mono_candidate = None
                        src = mono_candidate or image_path
                        with warnings.catch_warnings():
                            warnings.simplefilter("ignore")
                            with _fits.open(str(src)) as hdul:
                                orig_w = hdul[0].header.get('NAXIS1', 1)
                                orig_h = hdul[0].header.get('NAXIS2', 1)
                        margin_x = int(orig_w * args.crop_margin)
                        margin_y = int(orig_h * args.crop_margin)
                        if wcs_data.get('crpix1'):
                            wcs_data['crpix1'] = wcs_data['crpix1'] + margin_x
                        if wcs_data.get('crpix2'):
                            wcs_data['crpix2'] = wcs_data['crpix2'] + margin_y
                    except Exception as e:
                        print(f"  [crop] CRPIX correction failed: {e}")

                # ── Restitched mosaic: save panel 0 (global FITS solved) ──────
                # No individual panels needed — global WCS covers the full mosaic
                save_wcs(conn, session, wcs_data, wcs_file, actual_solver, panel_num=0)
                solved += 1

                print(f"\r  {i:>3d}  {session['entry_type']:8s} {obj:25s} {score_s:>6s}  {img_type:5s}  "
                      + _c(GREEN, f"✅ RA={wcs_data['ra_center']:.4f} DEC={wcs_data['dec_center']:.4f}"
                           + (f" scale={wcs_data['plate_scale']:.2f}\"" if wcs_data.get('plate_scale') else "")
                           + (" [mosaic restitched]" if is_restitched else "")))
            else:
                print(_c(YELLOW, " solved but WCS extraction failed"))
                # ── Restitched mosaic failed → fallback to individual panels ──
                if is_restitched and mosaic_folder:
                    print(f"  {i:>3d}  {session['entry_type']:8s} {obj:25s} {score_s:>6s}  panel  "
                          + _c(CYAN, "panel 0 failed — trying individual panels..."))
                    _solve_mosaic_panels(conn, session, api_key, astap_db,
                                         args.crop, args.crop_margin, solver_mode)
                else:
                    failed += 1

        except Exception as e:
            print(f"\r  {i:>3d}  {session['entry_type']:8s} {obj:25s} {score_s:>6s}  {img_type:5s}  "
                  + _c(RED, f"❌ {e}"))
            # ── Restitched mosaic exception → fallback to individual panels ───
            if is_restitched and mosaic_folder:
                print(f"      [MOSAIC] panel 0 failed — trying individual panels...")
                try:
                    _solve_mosaic_panels(conn, session, api_key, astap_db,
                                         args.crop, args.crop_margin, solver_mode)
                except Exception as e2:
                    print(f"      [MOSAIC] panels also failed: {e2}")
                    failed += 1
            else:
                failed += 1

        finally:
            # Nettoyage systématique — succès, échec ou exception
            _cleanup_temp(image_path)
            # Délai entre sessions pour éviter de surcharger Nova API
            if args.delay > 0 and i < len(sessions):
                import time
                time.sleep(args.delay)

    print(f"\n  {'-'*72}")
    print(f"  Solved: {_c(GREEN, str(solved))}  Failed: {_c(RED, str(failed))}  Skipped: {_c(YELLOW, str(skipped))}")
    print_report(conn, args.min_quality)
    close_db(conn)


if __name__ == '__main__':
    main()