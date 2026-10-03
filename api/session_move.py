"""
api/session_move.py

Move a session folder inside the archives of its Dwarf (Catalog Edition).

The session folder is never renamed (its name is what the Dwarf produced,
needed for a re-import, and it gives the session object). It is moved:
- to the root of an archive (no group, as on the Dwarf),
- into an existing sub-folder (group of the same targets),
- or into a new sub-folder (new group),
in the same archive or in another archive of the same Dwarf.

The database is not edited by hand: like after a transfer, the backup scan
is run on the moved session folder only (scan_backup_folder with
session_dir_path). What is attached to the old entry (notes, quality /
SkyBot scores, plate solving) is then re-attached to the new one, and the
entry of the old location is removed as the Explore page does when a
session folder is deleted. A later full rescan therefore finds exactly
the same data.

Pure functions only — no NiceGUI/UI code here.
"""

from __future__ import annotations

import os
import shutil
from typing import Optional

from api.dwarf_backup_db import connect_db, close_db
from api.dwarf_backup_fct import (
    scan_backup_folder, extract_astro_name_from_folder, print_log,
)

# Same folders the backup scan ignores
SKIP_DIRS = {"Archive", "CALI_FRAME", "DWARF_DARK", "Solving_Failed"}


def _data_root(location: str, astronomy_dir: Optional[str]) -> str:
    # Built exactly like scan_backup_folder does
    return os.path.join(location, astronomy_dir) if astronomy_dir else location


def is_session_folder(path: str) -> bool:
    """A folder the scan treats as a session (not as a group sub-folder)."""
    name = os.path.basename(os.path.normpath(path))
    return (bool(extract_astro_name_from_folder(name))
            or "_MOSAIC_" in name
            or os.path.isfile(os.path.join(path, "shotsInfo.json")))


def _position_fields(conn, entry_id, ra, dec, data_id) -> dict:
    from api.dso_association import session_position
    p = session_position(conn, "backup", entry_id, ra, dec, data_id)
    return {"ra_deg": p["ra_deg"], "dec_deg": p["dec_deg"],
            "position_source": p["source"], "goto_offset_deg": p["goto_offset_deg"]}


def get_backup_session(conn, backup_entry_id: int) -> Optional[dict]:
    """Archive session of a BackupEntry, with its paths:
    entry_id, backup_drive_id, drive_name, dwarf_id, dwarf_name, dwarf_data_id,
    ra, dec (raw goto values), ra_deg, dec_deg, position_source,
    goto_offset_deg (plate-solved centre when available, see
    dso_association.session_position),
    astro_object_id, object_name, group_name, session_date, location,
    astronomy_dir, data_root, session_path (full path of the folder),
    session_name, subfolder (top-level folder holding it, None at root)."""
    row = conn.execute("""
        SELECT be.id, be.backup_drive_id, bd.name, be.dwarf_id, be.dwarf_data_id,
               be.astro_object_id, ao.name, grp.name, be.session_date,
               bd.location, bd.astronomy_dir, dd.file_path, dw.name, dd.ra, dd.dec
        FROM BackupEntry be
        JOIN BackupDrive bd ON be.backup_drive_id = bd.id
        JOIN DwarfData dd ON be.dwarf_data_id = dd.id
        LEFT JOIN Dwarf dw ON be.dwarf_id = dw.id
        LEFT JOIN AstroObject ao ON be.astro_object_id = ao.id
        LEFT JOIN AstroObject grp ON be.astro_group_id = grp.id
        WHERE be.id = ?
    """, (backup_entry_id,)).fetchone()
    if not row:
        return None
    (entry_id, drive_id, drive_name, dwarf_id, data_id, ao_id, ao_name, group_name,
     session_date, location, astronomy_dir, file_path, dwarf_name, ra, dec) = row
    data_root = _data_root(location, astronomy_dir)
    session_path = os.path.dirname(os.path.join(location, file_path))
    if os.path.basename(session_path) == "Thumbnail":
        session_path = os.path.dirname(session_path)
    rel = os.path.relpath(session_path, data_root)
    parts = rel.split(os.sep)
    return {
        "entry_id": entry_id, "backup_drive_id": drive_id, "drive_name": drive_name,
        "dwarf_id": dwarf_id, "dwarf_name": dwarf_name, "dwarf_data_id": data_id,
        "ra": ra, "dec": dec,
        **_position_fields(conn, entry_id, ra, dec, data_id),
        "astro_object_id": ao_id, "object_name": ao_name, "group_name": group_name,
        "session_date": session_date,
        "location": location, "astronomy_dir": astronomy_dir, "data_root": data_root,
        "session_path": session_path, "session_name": os.path.basename(session_path),
        "subfolder": parts[0] if len(parts) > 1 else None,
    }


def session_image_path(session: dict) -> Optional[str]:
    """Stacked image of an archive session folder, or None: stacked.jpg
    first, then another stacked*.jpg, then stacked.png (first versions only
    had the png) or another stacked*.png, then the thumbnail."""
    folder = session.get("session_path")
    if not folder or not os.path.isdir(folder):
        return None
    try:
        names = os.listdir(folder)
    except OSError:
        return None
    for wanted in (lambda n: n == "stacked.jpg",
                   lambda n: n.startswith("stacked") and n.endswith(".jpg") and "thumbnail" not in n,
                   lambda n: n == "stacked.png",
                   lambda n: n.startswith("stacked") and n.endswith(".png"),
                   lambda n: n == "stacked_thumbnail.jpg"):
        for n in sorted(names):
            if wanted(n.lower()):
                return os.path.join(folder, n)
    return None


def get_object_backup_sessions(conn, astro_object_id: int) -> list[dict]:
    """Archive sessions whose object or group is astro_object_id."""
    ids = [r[0] for r in conn.execute("""
        SELECT be.id FROM BackupEntry be
        WHERE be.astro_object_id = ? OR be.astro_group_id = ?
        ORDER BY be.session_date DESC
    """, (astro_object_id, astro_object_id)).fetchall()]
    return [s for s in (get_backup_session(conn, i) for i in ids) if s]


def find_misfiled_sessions(conn, index: dict, threshold_deg: float) -> list[dict]:
    """
    Check every user group (the default groups Unknown / MOSAIC_Unknown /
    Manual gather unrelated targets and are skipped) like the sessions list
    does, and keep the sessions too far from their group's reference: a
    session filed in the wrong sub-folder, which the object check cannot
    see (the session is consistent with its own object).

    Returns [{"group": (id, name), "reference": (kind, label),
              "sessions": [(session, info)]}] for the groups having at
    least one inconsistent session, sorted by group name. A group without
    a clear majority (reference kind "split") is listed with all its
    sessions.
    """
    from api.dso_association import check_sessions
    from api.dwarf_backup_db_api import DEFAULT_GROUP_NAMES
    placeholders = ", ".join(["?"] * len(DEFAULT_GROUP_NAMES))
    result = []
    for group_id, name in conn.execute(f"""
            SELECT id, name FROM AstroObject
            WHERE is_group = 1 AND name NOT IN ({placeholders})
            ORDER BY name COLLATE NOCASE""", DEFAULT_GROUP_NAMES).fetchall():
        sessions = get_object_backup_sessions(conn, group_id)
        if not sessions:
            continue
        check = check_sessions(conn, index, group_id, sessions, threshold_deg)
        if check["reference"] and check["reference"][0] == "split":
            # No clear majority: list the whole group, nothing singled out
            result.append({"group": (group_id, name), "reference": check["reference"],
                           "sessions": [(s, check["sessions"][s["entry_id"]]) for s in sessions]})
            continue
        bad = [(s, check["sessions"][s["entry_id"]]) for s in sessions
               if check["sessions"][s["entry_id"]]["inconsistent"]]
        if bad:
            bad.sort(key=lambda b: -(b[1]["separation_deg"] or 0))
            result.append({"group": (group_id, name), "reference": check["reference"],
                           "sessions": bad})
    return result


def get_dwarf_archives(conn, dwarf_id: int) -> list[dict]:
    """Archives (BackupDrive) of a Dwarf: id, name, location, astronomy_dir,
    data_root, available (folder reachable now)."""
    archives = []
    for drive_id, name, location, astronomy_dir in conn.execute(
            "SELECT id, name, location, astronomy_dir FROM BackupDrive "
            "WHERE dwarf_id = ? ORDER BY name, id", (dwarf_id,)).fetchall():
        if not location:
            continue
        data_root = _data_root(location, astronomy_dir)
        archives.append({
            "id": drive_id, "name": name or location, "location": location,
            "astronomy_dir": astronomy_dir, "data_root": data_root,
            "available": os.path.isdir(data_root),
        })
    return archives


def list_subfolders(data_root: str) -> list[str]:
    """Top-level group sub-folders of an archive (sessions and the folders
    the scan ignores are left out)."""
    try:
        names = os.listdir(data_root)
    except OSError:
        return []
    return sorted(
        (n for n in names
         if n not in SKIP_DIRS
         and os.path.isdir(os.path.join(data_root, n))
         and not is_session_folder(os.path.join(data_root, n))),
        key=str.lower)


def suggested_subfolders(conn, backup_drive_id: int, astro_object_id: int,
                         exclude_entry_id: Optional[int] = None) -> list[str]:
    """Sub-folders of an archive already holding sessions of the same object."""
    found = []
    for (entry_id,) in conn.execute(
            "SELECT id FROM BackupEntry WHERE backup_drive_id = ? AND astro_object_id = ?",
            (backup_drive_id, astro_object_id)).fetchall():
        if entry_id == exclude_entry_id:
            continue
        s = get_backup_session(conn, entry_id)
        if s and s["subfolder"] and s["subfolder"] not in found:
            found.append(s["subfolder"])
    return sorted(found, key=str.lower)


def count_attached_data(conn, backup_entry_id: int) -> dict:
    """Data attached to the BackupEntry (re-attached to the new entry by a
    move; ManualSessionEntry blocks the move)."""
    def _count(sql):
        try:
            return conn.execute(sql, (backup_entry_id,)).fetchone()[0]
        except Exception:
            return 0
    return {
        "notes": _count("SELECT COUNT(*) FROM SessionNotes WHERE backup_entry_id = ?"),
        "wcs": _count("SELECT COUNT(*) FROM SessionWCS WHERE entry_type = 'backup' AND entry_id = ?"),
        "manual": _count("SELECT COUNT(*) FROM ManualSessionEntry WHERE backup_entry_id = ?"),
    }


def validate_subfolder_name(name: str) -> Optional[str]:
    """Error key for an invalid new sub-folder name, else None."""
    name = (name or "").strip()
    if not name or name in (".", ".."):
        return "move_err_name"
    if any(c in name for c in '/\\:*?"<>|'):
        return "move_err_name"
    if name in SKIP_DIRS or extract_astro_name_from_folder(name) or "_MOSAIC_" in name:
        return "move_err_name"
    return None


def _carry_over_attached_data(conn, old_entry_id: int, new_entry_id: int,
                              old_path: str, new_path: str):
    """
    Re-attach to the new BackupEntry what was computed or entered for the
    old one (the session is the same, only its folder moved): notes,
    quality / SkyBot scores and plate solving results. Without this they
    would be deleted with the old entry (ON DELETE CASCADE), as for a
    session moved by hand.
    """
    with conn:
        conn.execute("UPDATE SessionNotes SET backup_entry_id = ? WHERE backup_entry_id = ?",
                     (new_entry_id, old_entry_id))
        conn.execute("UPDATE SkyBotResult SET backup_entry_id = ? WHERE backup_entry_id = ?",
                     (new_entry_id, old_entry_id))
        # The scan has just created a quality row (folder size) for the new
        # entry: keep the old one, which also holds the scores
        if conn.execute("SELECT 1 FROM SessionQuality WHERE backup_entry_id = ?",
                        (old_entry_id,)).fetchone():
            size_cols = ("folder_size_bytes", "folder_sized_at", "dwarf_size_bytes",
                         "dwarf_size_no_fits_bytes", "dwarf_sized_at")
            fresh = conn.execute(
                f"SELECT {', '.join(size_cols)} FROM SessionQuality WHERE backup_entry_id = ?",
                (new_entry_id,)).fetchone()
            conn.execute("DELETE FROM SessionQuality WHERE backup_entry_id = ?", (new_entry_id,))
            if fresh:
                # Fill the sizes the old row does not have yet
                conn.execute(
                    f"UPDATE SessionQuality SET "
                    f"{', '.join(f'{c} = COALESCE({c}, ?)' for c in size_cols)} "
                    f"WHERE backup_entry_id = ?", (*fresh, old_entry_id))
            conn.execute("UPDATE SessionQuality SET backup_entry_id = ? WHERE backup_entry_id = ?",
                         (new_entry_id, old_entry_id))
        # Plate solving: same entry, and the .wcs file moved with the folder
        old_prefix = os.path.normpath(old_path) + os.sep
        rows = conn.execute(
            "SELECT id, wcs_file FROM SessionWCS WHERE entry_type = 'backup' AND entry_id = ?",
            (old_entry_id,)).fetchall()
        if rows:
            conn.execute("DELETE FROM SessionWCS WHERE entry_type = 'backup' AND entry_id = ?",
                         (new_entry_id,))
        for wcs_id, wcs_file in rows:
            if wcs_file and os.path.normpath(wcs_file).startswith(old_prefix):
                wcs_file = os.path.join(new_path, os.path.relpath(os.path.normpath(wcs_file),
                                                                  os.path.normpath(old_path)))
            conn.execute("UPDATE SessionWCS SET entry_id = ?, wcs_file = ? WHERE id = ?",
                         (new_entry_id, wcs_file, wcs_id))


def _remove_old_entry(conn, backup_drive_id: int, dwarf_id: int, dwarf_data_id: int):
    """Remove the BackupEntry of the old location, as
    delete_backup_entry_and_dwarf_data does when a session folder is
    deleted from Explore; the DwarfData row is kept while the Dwarf entry or
    another archive still uses it."""
    with conn:
        conn.execute(
            "DELETE FROM BackupEntry WHERE backup_drive_id = ? AND dwarf_id = ? AND dwarf_data_id = ?",
            (backup_drive_id, dwarf_id, dwarf_data_id))
        used = conn.execute(
            "SELECT (SELECT COUNT(*) FROM BackupEntry WHERE dwarf_data_id = ?)"
            "     + (SELECT COUNT(*) FROM DwarfEntry WHERE dwarf_data_id = ?)",
            (dwarf_data_id, dwarf_data_id)).fetchone()[0]
        if not used:
            conn.execute("DELETE FROM DwarfData WHERE id = ?", (dwarf_data_id,))


def move_backup_session(db_name: str, backup_entry_id: int, dst_drive_id: int,
                        dst_subfolder: Optional[str], log=None) -> dict:
    """
    Move the session folder of a BackupEntry to the root (dst_subfolder
    empty/None) or to a sub-folder of an archive of the same Dwarf, then
    let the scan register it there and remove the old entry.

    Returns {"ok": bool, "error": error key or None, "new_entry_id",
    "dst_path"}. Error keys are i18n keys (move_err_*).
    """
    result = {"ok": False, "error": None, "new_entry_id": None, "dst_path": None}
    dst_subfolder = (dst_subfolder or "").strip() or None

    conn = connect_db(db_name)
    try:
        src = get_backup_session(conn, backup_entry_id)
        dst = conn.execute(
            "SELECT id, location, astronomy_dir, dwarf_id FROM BackupDrive WHERE id = ?",
            (dst_drive_id,)).fetchone()
        if not src or not dst:
            result["error"] = "move_err_not_found"
            return result
        if dst[3] != src["dwarf_id"]:
            result["error"] = "move_err_other_dwarf"
            return result
        if count_attached_data(conn, backup_entry_id)["manual"]:
            # A manual session is built on this one: its paths would break
            result["error"] = "move_err_manual"
            return result
    finally:
        close_db(conn)

    if dst_subfolder and validate_subfolder_name(dst_subfolder):
        result["error"] = "move_err_name"
        return result
    if not os.path.isdir(src["session_path"]):
        result["error"] = "move_err_src_missing"
        return result
    _, dst_location, dst_astronomy_dir, _ = dst
    dst_root = _data_root(dst_location, dst_astronomy_dir)
    if not os.path.isdir(dst_root):
        result["error"] = "move_err_dst_missing"
        return result

    dst_parent = os.path.join(dst_root, dst_subfolder) if dst_subfolder else dst_root
    dst_path = os.path.join(dst_parent, src["session_name"])
    result["dst_path"] = dst_path
    if os.path.normcase(os.path.abspath(dst_path)) == os.path.normcase(os.path.abspath(src["session_path"])):
        result["error"] = "move_err_same"
        return result
    if os.path.exists(dst_path):
        result["error"] = "move_err_exists"
        return result

    # 1 — move the folder on disk (copy + delete across drives)
    try:
        os.makedirs(dst_parent, exist_ok=True)
        print_log(f"📦 {src['session_path']} → {dst_path}", log)
        shutil.move(src["session_path"], dst_path)
    except Exception as e:
        print_log(f"❌ {e}", log, style="text-red")
        result["error"] = "move_err_io"
        return result

    # 2 — scan the moved session only, as after a transfer
    scan_backup_folder(db_name, dst_location, dst_astronomy_dir, src["dwarf_id"],
                       dst_drive_id, dst_path, log)

    # 3 — find the new entry, then remove the one of the old location
    conn = connect_db(db_name)
    try:
        new_id = None
        for row in conn.execute("""
                SELECT be.id, dd.file_path FROM BackupEntry be
                JOIN DwarfData dd ON be.dwarf_data_id = dd.id
                WHERE be.backup_drive_id = ? AND be.dwarf_id = ? AND be.session_dir = ?
                """, (dst_drive_id, src["dwarf_id"], src["session_name"])).fetchall():
            full = os.path.normcase(os.path.abspath(os.path.join(dst_location, row[1])))
            if full.startswith(os.path.normcase(os.path.abspath(dst_path)) + os.sep):
                new_id = row[0]
                break
        if not new_id:
            # Folder moved but not registered: keep the old entry, a full
            # analysis from Backup Settings will clean it up
            result["error"] = "move_err_scan"
            return result
        result["new_entry_id"] = new_id
        if new_id != backup_entry_id:
            _carry_over_attached_data(conn, backup_entry_id, new_id,
                                      src["session_path"], dst_path)
            _remove_old_entry(conn, src["backup_drive_id"], src["dwarf_id"], src["dwarf_data_id"])
        result["ok"] = True
        return result
    finally:
        close_db(conn)
