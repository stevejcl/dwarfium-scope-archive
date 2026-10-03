"""
api/dso_association.py

Helpers for the semi-automatic AstroObject ↔ DsoCatalog association tool
(Catalog Edition page).

Step 1 — link AstroObjects that have no dso_id yet: for each object, take
the RA/DEC of a session that references it (DwarfData through
BackupEntry / DwarfEntry, or ManualSession through ManualSessionEntry),
find the nearest catalog object and let the user confirm it while looking
at the session's stacked image.

Step 2 — find AstroObjects whose sessions' RA/DEC do not match their DSO,
and link them to the right one.

Pure functions only — no NiceGUI/UI code here.
"""

from __future__ import annotations

import base64
import io
import os
from typing import Optional

from api.dso_matching import (
    load_dso_catalog, find_nearest_catalog_object, angular_sep_deg_fast,
    build_catalog_name_index, normalize_name,
)
from api.dwarf_backup_fct import hms_to_hours, dms_to_degrees, get_Backup_fullpath


# Nearest object proposed by default must be within this radius (same
# default as resolve_catalog_id).
NEAREST_MAX_SEP_DEG = 1.0
# Alternatives shown to the user (wide-angle fields often contain several
# catalog objects).
CANDIDATES_RADIUS_DEG = 3.0
CANDIDATES_MAX = 8


# ── Catalog ──────────────────────────────────────────────────────────────────

def load_catalog_index(conn) -> dict:
    """
    Load the DSO catalog once and prepare everything the matching needs:
    entries sorted by declination (for find_nearest_catalog_object), the
    name index, and the designation → DsoCatalog.id map of the database.
    """
    catalog = [o for o in load_dso_catalog()
               if o.get("ra_deg") is not None and o.get("dec_deg") is not None]
    catalog_sorted = sorted(catalog, key=lambda o: o["dec_deg"])
    db_ids = {row[0]: row[1] for row in
              conn.execute("SELECT designation, id FROM DsoCatalog").fetchall()}
    by_designation = {(o.get("designation") or o.get("id")): o for o in catalog}
    return {
        "sorted": catalog_sorted,
        "decs": [o["dec_deg"] for o in catalog_sorted],
        "name_index": build_catalog_name_index(catalog),
        "db_ids": db_ids,
        "by_designation": by_designation,
    }


def _candidate(obj: dict, sep: float, db_id: int, by_name: bool = False) -> dict:
    designation = obj.get("designation") or obj.get("id")
    name = obj.get("displayName") or obj.get("name") or ""
    # displayName often repeats the designation: "M 42 - Great Nebula in Orion"
    if designation and name.startswith(f"{designation} - "):
        name = name[len(designation) + 3:]
    return {
        "dso_id": db_id,
        "designation": designation,
        "name": name,
        "type": obj.get("type") or "",
        "constellation": obj.get("constellation") or "",
        "separation_deg": round(sep, 3),
        "by_name": by_name,
    }


def find_dso_candidates(ra_deg: float, dec_deg: float, index: dict,
                        object_name: Optional[str] = None) -> tuple[Optional[dict], list[dict]]:
    """
    Return (proposal, candidates).

    proposal: nearest catalog object within NEAREST_MAX_SEP_DEG (found with
    find_nearest_catalog_object, as on the Explore page), else None.
    candidates: catalog objects within CANDIDATES_RADIUS_DEG sorted by
    separation, plus the catalog object whose name matches object_name (if
    any), so the user can pick another one in a crowded wide-angle field.
    Only objects present in the DsoCatalog table are returned.
    """
    db_ids = index["db_ids"]
    by_designation = index["by_designation"]

    candidates: list[dict] = []
    for obj in index["sorted"]:
        if abs(obj["dec_deg"] - dec_deg) > CANDIDATES_RADIUS_DEG:
            continue
        designation = obj.get("designation") or obj.get("id")
        if designation not in db_ids:
            continue
        sep = angular_sep_deg_fast(ra_deg, dec_deg, obj["ra_deg"], obj["dec_deg"])
        if sep <= CANDIDATES_RADIUS_DEG:
            candidates.append(_candidate(obj, sep, db_ids[designation]))
    candidates.sort(key=lambda c: c["separation_deg"])
    candidates = candidates[:CANDIDATES_MAX]

    # Catalog object matching the AstroObject name (e.g. "M 42" → M42):
    # flag it if already listed, otherwise add it with its separation.
    key = normalize_name(object_name)
    name_designation = index["name_index"].get(key) if key else None
    if name_designation and name_designation in db_ids:
        for c in candidates:
            if c["designation"] == name_designation:
                c["by_name"] = True
                break
        else:
            obj = by_designation.get(name_designation)
            if obj:
                sep = angular_sep_deg_fast(ra_deg, dec_deg, obj["ra_deg"], obj["dec_deg"])
                candidates.append(_candidate(obj, sep, db_ids[name_designation], by_name=True))

    proposal = None
    nearest = find_nearest_catalog_object(
        ra_deg, dec_deg, index["sorted"], index["decs"], NEAREST_MAX_SEP_DEG)
    if nearest:
        proposal = next((c for c in candidates if c["designation"] == nearest), None)
    return proposal, candidates


# ── Sessions ─────────────────────────────────────────────────────────────────

def parse_coords(ra, dec) -> Optional[tuple[float, float]]:
    """Session RA (hours, HMS string or number) / DEC (DMS string or number)
    → (ra_deg, dec_deg), or None when missing/unparsable."""
    if ra in (None, "") or dec in (None, ""):
        return None
    try:
        ra_deg = hms_to_hours(ra) * 15.0
        dec_deg = dms_to_degrees(dec)
    except Exception:
        return None
    if ra_deg == 0.0 and dec_deg == 0.0:  # parse failure / unset
        return None
    if not (0.0 <= ra_deg <= 360.0 and -90.0 <= dec_deg <= 90.0):
        return None
    return ra_deg, dec_deg


def _first_existing(paths) -> Optional[str]:
    for p in paths:
        if p and os.path.isfile(p):
            return p
    return None


def _session_image(image_path: Optional[str]) -> Optional[str]:
    """The session image itself, else stacked.jpg / stacked_thumbnail.jpg
    next to it."""
    if not image_path:
        return None
    directory = os.path.dirname(image_path)
    return _first_existing([
        image_path,
        os.path.join(directory, "stacked.jpg"),
        os.path.join(directory, "stacked_thumbnail.jpg"),
    ])


def get_unlinked_astro_objects(conn) -> list[tuple]:
    """AstroObjects (not groups) without dso_id: (id, name, description).
    Unknown / MOSAIC_Unknown / Manual objects are included: the scan creates
    one per position, so each can be linked to its own DSO."""
    return conn.execute("""
        SELECT id, name, description FROM AstroObject
        WHERE dso_id IS NULL
          AND COALESCE(is_group, 0) = 0
        ORDER BY name COLLATE NOCASE, id
    """).fetchall()


def get_object_sessions(conn, astro_object_id: int, resolve_images: bool = True) -> list[dict]:
    """
    Sessions referencing an AstroObject that carry usable RA/DEC, newest
    first. Each item: source ('backup' | 'dwarf' | 'manual'), entry_id,
    data_id (DwarfData.id, backup/dwarf) or manual_session_id (manual),
    session_date, session_dir, target, ra, dec (raw), ra_deg, dec_deg,
    image_ref (what resolve_session_image needs) and image_path (full path
    to an existing image, or None — only looked up when resolve_images).
    A DwarfData present both on the Dwarf and in a backup is listed once
    (backup copy preferred).
    """
    sessions: list[dict] = []
    seen_data_ids: set[int] = set()

    backup_rows = conn.execute("""
        SELECT be.id, be.session_date, be.session_dir, dd.id, dd.target, dd.ra, dd.dec,
               dd.file_path, bd.location, be.dwarf_id
        FROM BackupEntry be
        JOIN DwarfData dd ON be.dwarf_data_id = dd.id
        LEFT JOIN BackupDrive bd ON be.backup_drive_id = bd.id
        WHERE be.astro_object_id = ?
    """, (astro_object_id,)).fetchall()
    dwarf_rows = conn.execute("""
        SELECT de.id, de.session_date, de.session_dir, dd.id, dd.target, dd.ra, dd.dec,
               dd.file_path, d.usb_astronomy_dir, de.dwarf_id
        FROM DwarfEntry de
        JOIN DwarfData dd ON de.dwarf_data_id = dd.id
        LEFT JOIN Dwarf d ON de.dwarf_id = d.id
        WHERE de.astro_object_id = ?
    """, (astro_object_id,)).fetchall()

    for source, rows in (("backup", backup_rows), ("dwarf", dwarf_rows)):
        for entry_id, session_date, session_dir, data_id, target, ra, dec, file_path, root, dwarf_id in rows:
            if data_id in seen_data_ids:
                continue
            coords = parse_coords(ra, dec)
            if not coords:
                continue
            seen_data_ids.add(data_id)
            sessions.append({
                "source": source, "entry_id": entry_id, "data_id": data_id,
                "session_date": session_date, "session_dir": session_dir,
                "target": target,
                "ra": ra, "dec": dec, "ra_deg": coords[0], "dec_deg": coords[1],
                "image_ref": ("dwarf", root, file_path, dwarf_id),
            })

    manual_rows = conn.execute("""
        SELECT mse.id, mse.manual_session_id, mse.session_date, ms.session_name, ms.ra, ms.dec,
               COALESCE(ms.jpeg_path, ms.stacked_png_path), mse.session_dir,
               bd.location, msd.location
        FROM ManualSessionEntry mse
        JOIN ManualSession ms ON mse.manual_session_id = ms.id
        LEFT JOIN BackupDrive bd ON mse.backup_drive_id = bd.id
        LEFT JOIN ManualSessionDrive msd ON mse.manual_session_drive = msd.id
        WHERE mse.astro_object_id = ?
    """, (astro_object_id,)).fetchall()
    seen_manual_ids: set[int] = set()
    for (entry_id, manual_session_id, session_date, name, ra, dec, jpeg_path,
         session_dir, location, manual_location) in manual_rows:
        if manual_session_id in seen_manual_ids:
            continue
        coords = parse_coords(ra, dec)
        if not coords:
            continue
        seen_manual_ids.add(manual_session_id)
        # Same resolution order as the Home page favorites
        candidates = []
        if jpeg_path:
            candidates = [
                jpeg_path if os.path.isabs(jpeg_path) else None,
                os.path.join(session_dir, os.path.basename(jpeg_path)) if session_dir else None,
                os.path.join(manual_location, jpeg_path) if manual_location else None,
                os.path.join(location, jpeg_path) if location else None,
            ]
        sessions.append({
            "source": "manual", "entry_id": entry_id,
            "manual_session_id": manual_session_id,
            "session_date": session_date, "session_dir": session_dir,
            "target": name,
            "ra": ra, "dec": dec, "ra_deg": coords[0], "dec_deg": coords[1],
            "image_ref": ("manual", candidates),
        })

    for session in sessions:
        session["image_path"] = resolve_session_image(conn, session) if resolve_images else None

    sessions.sort(key=lambda s: s["session_date"] or "", reverse=True)
    if resolve_images:
        # Sessions with an image to check first
        sessions.sort(key=lambda s: s["image_path"] is None)
    return sessions


def resolve_session_image(conn, session: dict) -> Optional[str]:
    """Full path to an existing image of the session, or None."""
    ref = session.get("image_ref")
    if not ref:
        return None
    if ref[0] == "manual":
        return _first_existing(ref[1])
    _, root, file_path, dwarf_id = ref
    if not file_path:
        return None
    try:
        return _session_image(get_Backup_fullpath(conn, root, "", file_path, dwarf_id))
    except Exception:
        return None


# ── Thumbnail ────────────────────────────────────────────────────────────────

def make_thumbnail_data_url(image_path: Optional[str], max_size: int = 640) -> Optional[str]:
    """Small JPEG of the session image as a data: URL (no static route
    needed, works whatever the drive the session lives on)."""
    if not image_path or not os.path.isfile(image_path):
        return None
    try:
        from PIL import Image
        with Image.open(image_path) as img:
            img.draft("RGB", (max_size, max_size))  # fast JPEG downscale
            img = img.convert("RGB")
            img.thumbnail((max_size, max_size))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception as e:
        print(f"[dso_association] thumbnail failed for {image_path}: {e}")
        return None


# ── Step 2: objects whose sessions do not match their DSO ────────────────────

# A session whose RA/DEC is further than this from its object's catalog
# position is reported (Dwarf tele fields are < 1°, wide fields a few °).
INCONSISTENT_DEFAULT_DEG = 2.0


def get_linked_astro_objects(conn) -> list[tuple]:
    """AstroObjects (not groups) linked to a DSO:
    (id, name, description, dso_id, designation)."""
    return conn.execute("""
        SELECT ao.id, ao.name, ao.description, ao.dso_id, d.designation
        FROM AstroObject ao
        JOIN DsoCatalog d ON ao.dso_id = d.id
        WHERE COALESCE(ao.is_group, 0) = 0
        ORDER BY ao.name COLLATE NOCASE, ao.id
    """).fetchall()


def find_inconsistent_objects(conn, index: dict,
                              threshold_deg: float = INCONSISTENT_DEFAULT_DEG) -> list[dict]:
    """
    AstroObjects having sessions whose RA/DEC is more than threshold_deg
    away from the catalog position of the linked DSO (wrong DSO chosen,
    Unknown object linked to the wrong neighbour, ...). The session object
    itself comes from the session folder name and is kept: the fix is to
    link the object to the right DSO, which survives a rescan.

    Each item: astro_object (id, name, description), dso_id, designation,
    sessions [(session, separation_deg)] (largest separation first, image
    not resolved — see get_object_sessions) and total_sessions (sessions
    with coordinates, consistent ones included).
    """
    result = []
    for ao_id, name, description, dso_id, designation in get_linked_astro_objects(conn):
        obj = index["by_designation"].get(designation)
        if not obj:
            continue
        all_sessions = get_object_sessions(conn, ao_id, resolve_images=False)
        bad = []
        for session in all_sessions:
            sep = angular_sep_deg_fast(session["ra_deg"], session["dec_deg"],
                                       obj["ra_deg"], obj["dec_deg"])
            if sep > threshold_deg:
                bad.append((session, round(sep, 2)))
        if bad:
            bad.sort(key=lambda b: -b[1])
            result.append({
                "astro_object": (ao_id, name, description),
                "dso_id": dso_id,
                "designation": designation,
                "sessions": bad,
                "total_sessions": len(all_sessions),
            })
    return result
