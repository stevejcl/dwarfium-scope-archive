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
from api.dwarf_backup_db_api import get_solved_center_row, get_session_solve_row


def get_solved_position(conn, entry_type: str, entry_id: int) -> Optional[dict]:
    """Plate-solved centre of a session (panel 0), or None:
    {"ra_deg", "dec_deg", "solver", "solved_at"}."""
    row = get_solved_center_row(conn, entry_type, entry_id)
    if not row:
        return None
    return {"ra_deg": float(row[0]), "dec_deg": float(row[1]),
            "solver": row[2], "solved_at": row[3]}


def _session_dict(conn, entry_type: str, entry_id: int) -> Optional[dict]:
    """Session dict with the fields the astrometry scan uses
    (get_sessions_to_solve), for one entry whatever its quality score."""
    keys = ['entry_type', 'entry_id', 'session_date', 'session_dir',
            'dwarf_file_path', 'stacked_fits_path', 'drive_location', 'object_name']
    row = get_session_solve_row(conn, entry_type, entry_id)
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
