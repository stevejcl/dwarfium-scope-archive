"""
api/session_solve.py

Plate solving of one session on demand (Identify target dialog), reusing
the astrometry scan (tools/astrometry_scan.py): same image choice, same
SessionWCS storage.

The RA/DEC of shotsInfo.json is the position requested from the goto, not
always the one really imaged (e.g. early DWARF II sessions with a wrong
longitude). The solve is therefore blind: the recorded position is not
used as a hint.

Pure functions only — no NiceGUI/UI code here.
"""

from __future__ import annotations

from typing import Optional

from api.dwarf_backup_db import connect_db, close_db


def get_solved_position(conn, entry_type: str, entry_id: int) -> Optional[dict]:
    """Plate-solved centre of a session (panel 0), or None:
    {"ra_deg", "dec_deg", "solver", "solved_at"}."""
    try:
        row = conn.execute("""
            SELECT ra_center, dec_center, solver, solved_at FROM SessionWCS
            WHERE entry_type = ? AND entry_id = ? AND panel_num = 0
              AND ra_center IS NOT NULL AND dec_center IS NOT NULL
            ORDER BY solved_at DESC LIMIT 1
        """, (entry_type, entry_id)).fetchone()
    except Exception:
        return None  # SessionWCS not created yet
    if not row:
        return None
    return {"ra_deg": float(row[0]), "dec_deg": float(row[1]),
            "solver": row[2], "solved_at": row[3]}


def _session_dict(conn, entry_type: str, entry_id: int) -> Optional[dict]:
    """Session dict with the fields the astrometry scan uses
    (get_sessions_to_solve), for one entry whatever its quality score."""
    keys = ['entry_type', 'entry_id', 'session_date', 'session_dir',
            'dwarf_file_path', 'stacked_fits_path', 'drive_location', 'object_name']
    if entry_type == 'manual':
        row = conn.execute("""
            SELECT 'manual', mse.id, mse.session_date, mse.session_dir,
                   ms.jpeg_path, ms.stacked_fits_path, msd.location, ao.name
            FROM ManualSessionEntry mse
            JOIN ManualSession ms ON mse.manual_session_id = ms.id
            LEFT JOIN ManualSessionDrive msd ON mse.manual_session_drive = msd.id
            LEFT JOIN AstroObject ao ON mse.astro_object_id = ao.id
            WHERE mse.id = ?""", (entry_id,)).fetchone()
    else:
        row = conn.execute("""
            SELECT 'backup', be.id, be.session_date, be.session_dir,
                   dd.file_path, dd.stacked_fits_path, bd.location, ao.name
            FROM BackupEntry be
            JOIN DwarfData dd ON be.dwarf_data_id = dd.id
            JOIN BackupDrive bd ON be.backup_drive_id = bd.id
            LEFT JOIN AstroObject ao ON be.astro_object_id = ao.id
            WHERE be.id = ?""", (entry_id,)).fetchone()
    return dict(zip(keys, row)) if row else None


def solve_session_blind(db_name: str, entry_type: str, entry_id: int, log=None) -> dict:
    """
    Blind plate solve of one session (BackupEntry: entry_type 'backup',
    ManualSessionEntry: 'manual') and store the result in SessionWCS like
    the astrometry scan does.

    Returns {"ok": bool, "error": i18n key or None, "detail": str,
             "position": get_solved_position(...) or None}.
    """
    from tools.astrometry_scan import (
        ensure_wcs_table, find_image_for_session,
        extract_wcs_from_file, save_wcs, _cleanup_temp,
    )
    from api.astrometry_resolver import auto_resolve, has_solve_field
    from api.dwarf_backup_db_api import get_setting_text

    result = {"ok": False, "error": None, "detail": "", "position": None}
    conn = connect_db(db_name)
    image_path = None
    try:
        ensure_wcs_table(conn)
        api_key = get_setting_text(conn, 'NOVA_ASTRO_API') or ''
        astap_db = get_setting_text(conn, 'ASTAP_DB') or 'D50'

        session = _session_dict(conn, entry_type, entry_id)
        if not session:
            result["error"] = "solve_err_not_found"
            return result

        image_path, img_type = find_image_for_session(session)
        if img_type == 'mosaic_panels':
            # Raw mosaic: solved panel by panel by the astrometry scan
            result["error"] = "solve_err_mosaic"
            return result
        if not image_path:
            result["error"] = "solve_err_no_image"
            return result

        try:
            wcs_file = auto_resolve(api_key, str(image_path), log=log,
                                    astap_db=astap_db, blind=True)
        except Exception as e:
            result["error"] = "solve_err_failed"
            result["detail"] = str(e)
            return result
        wcs_data = extract_wcs_from_file(wcs_file)
        if not wcs_data or wcs_data.get("ra_center") is None:
            result["error"] = "solve_err_failed"
            return result

        if wcs_file.endswith('.ini'):
            solver = 'astap'
        elif 'nova' in wcs_file.lower() or wcs_file.endswith('.wcs'):
            solver = 'nova'
        elif has_solve_field():
            solver = 'local'
        else:
            solver = 'nova'
        save_wcs(conn, session, wcs_data, wcs_file, solver, panel_num=0)
        result["ok"] = True
        result["position"] = get_solved_position(conn, entry_type, entry_id)
        return result
    finally:
        if image_path is not None:
            try:
                _cleanup_temp(image_path)
            except Exception:
                pass
        close_db(conn)
