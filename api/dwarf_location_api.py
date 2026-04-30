# api/dwarf_location_api.py
"""
Dwarfium Scope Archive — ObservationLocation DB API.

CRUD for the ObservationLocation table plus helpers used during
session scanning (default location assignment, FITS/EXIF extraction).
"""

from __future__ import annotations

import os
import sqlite3
import struct
from pathlib import Path
from typing import Optional


# ── Type alias ────────────────────────────────────────────────────────────────
Row = sqlite3.Row


# ─────────────────────────────────────────────────────────────────────────────
# CRUD
# ─────────────────────────────────────────────────────────────────────────────

def get_all_locations(conn: sqlite3.Connection) -> list[dict]:
    """Return all ObservationLocation rows as dicts, default first."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, latitude, longitude, address, comment, is_default
        FROM ObservationLocation
        ORDER BY is_default DESC, name ASC
    """)
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def get_location(conn: sqlite3.Connection, location_id: int) -> Optional[dict]:
    """Return one ObservationLocation by id, or None."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, latitude, longitude, address, comment, is_default
        FROM ObservationLocation WHERE id = ?
    """, (location_id,))
    row = cursor.fetchone()
    if not row:
        return None
    cols = [d[0] for d in cursor.description]
    return dict(zip(cols, row))


def get_default_location(conn: sqlite3.Connection) -> Optional[dict]:
    """Return the location flagged as default, or None."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, latitude, longitude, address, comment, is_default
        FROM ObservationLocation WHERE is_default = 1 LIMIT 1
    """)
    row = cursor.fetchone()
    if not row:
        return None
    cols = [d[0] for d in cursor.description]
    return dict(zip(cols, row))


def get_default_location_id(conn: sqlite3.Connection) -> Optional[int]:
    """Return the id of the default location, or None."""
    loc = get_default_location(conn)
    return loc["id"] if loc else None


def insert_location(conn: sqlite3.Connection, name: str,
                    latitude: Optional[float] = None,
                    longitude: Optional[float] = None,
                    address: str = "",
                    comment: str = "",
                    is_default: bool = False) -> int:
    """
    Insert a new ObservationLocation.
    If is_default=True, clears any existing default first.
    Returns the new row id.
    """
    cursor = conn.cursor()
    if is_default:
        cursor.execute("UPDATE ObservationLocation SET is_default = 0")
    cursor.execute("""
        INSERT INTO ObservationLocation (name, latitude, longitude, address, comment, is_default)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (name, latitude, longitude, address, comment, int(is_default)))
    conn.commit()
    return cursor.lastrowid


def update_location(conn: sqlite3.Connection, location_id: int,
                    name: str,
                    latitude: Optional[float] = None,
                    longitude: Optional[float] = None,
                    address: str = "",
                    comment: str = "",
                    is_default: bool = False) -> bool:
    """Update an existing ObservationLocation. Returns True on success."""
    cursor = conn.cursor()
    if is_default:
        cursor.execute(
            "UPDATE ObservationLocation SET is_default = 0 WHERE id != ?",
            (location_id,)
        )
    cursor.execute("""
        UPDATE ObservationLocation
        SET name=?, latitude=?, longitude=?, address=?, comment=?, is_default=?
        WHERE id=?
    """, (name, latitude, longitude, address, comment, int(is_default), location_id))
    conn.commit()
    return cursor.rowcount > 0


def set_default_location(conn: sqlite3.Connection, location_id: int) -> bool:
    """Set the given location as default, clearing any previous default."""
    cursor = conn.cursor()
    cursor.execute("UPDATE ObservationLocation SET is_default = 0")
    cursor.execute(
        "UPDATE ObservationLocation SET is_default = 1 WHERE id = ?",
        (location_id,)
    )
    conn.commit()
    return cursor.rowcount > 0


def delete_location(conn: sqlite3.Connection, location_id: int) -> bool:
    """
    Delete an ObservationLocation.
    DwarfData and SessionNotes referencing it will be SET NULL (via FK).
    Returns True on success.
    """
    cursor = conn.cursor()
    cursor.execute("DELETE FROM ObservationLocation WHERE id = ?", (location_id,))
    conn.commit()
    return cursor.rowcount > 0


def find_or_create_location_by_coords(conn: sqlite3.Connection,
                                       latitude: float,
                                       longitude: float,
                                       tolerance: float = 0.01) -> int:
    """
    Find an existing location within *tolerance* degrees of (lat, lon).
    Creates a new one named 'GPS {lat:.4f}, {lon:.4f}' if none found.
    Returns the location id.
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id FROM ObservationLocation
        WHERE latitude  BETWEEN ? AND ?
          AND longitude BETWEEN ? AND ?
        ORDER BY is_default DESC
        LIMIT 1
    """, (latitude - tolerance, latitude + tolerance,
          longitude - tolerance, longitude + tolerance))
    row = cursor.fetchone()
    if row:
        return row[0]
    # Create a new location with auto-generated name
    name = f"GPS {latitude:.4f}, {longitude:.4f}"
    return insert_location(conn, name, latitude=latitude, longitude=longitude)


# ─────────────────────────────────────────────────────────────────────────────
# DwarfData assignment
# ─────────────────────────────────────────────────────────────────────────────

def set_dwarfdata_location(conn: sqlite3.Connection,
                            dwarf_data_id: int,
                            location_id: Optional[int]) -> bool:
    """Assign (or clear) the location for a DwarfData row."""
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE DwarfData SET location_id = ? WHERE id = ?",
        (location_id, dwarf_data_id)
    )
    conn.commit()
    return cursor.rowcount > 0


def assign_default_location_if_missing(conn: sqlite3.Connection,
                                        dwarf_data_id: int) -> bool:
    """
    If the DwarfData row has no location_id yet, assign the default location.
    Returns True if an assignment was made.
    """
    cursor = conn.cursor()
    cursor.execute(
        "SELECT location_id FROM DwarfData WHERE id = ?", (dwarf_data_id,)
    )
    row = cursor.fetchone()
    if not row or row[0] is not None:
        return False  # already has a location
    default_id = get_default_location_id(conn)
    if default_id is None:
        return False
    cursor.execute(
        "UPDATE DwarfData SET location_id = ? WHERE id = ?",
        (default_id, dwarf_data_id)
    )
    conn.commit()
    return cursor.rowcount > 0


# ─────────────────────────────────────────────────────────────────────────────
# GPS extraction from files
# ─────────────────────────────────────────────────────────────────────────────

def _dms_to_decimal(dms_value, ref: str) -> Optional[float]:
    """
    Convert a EXIF DMS value (list of rationals) to decimal degrees.
    ref is 'N', 'S', 'E' or 'W'.
    """
    try:
        d = dms_value[0][0] / dms_value[0][1]
        m = dms_value[1][0] / dms_value[1][1]
        s = dms_value[2][0] / dms_value[2][1]
        decimal = d + m / 60.0 + s / 3600.0
        if ref in ("S", "W"):
            decimal = -decimal
        return round(decimal, 6)
    except Exception:
        return None


def extract_gps_from_jpeg(jpeg_path: str) -> tuple[Optional[float], Optional[float]]:
    """
    Extract GPS latitude and longitude from a JPEG EXIF header.
    Returns (latitude, longitude) or (None, None) if not available.
    Requires the 'piexif' library (pip install piexif).
    """
    try:
        import piexif
        exif = piexif.load(jpeg_path)
        gps = exif.get("GPS", {})
        if not gps:
            return None, None

        GPSIFD = piexif.GPSIFD
        lat_val = gps.get(GPSIFD.GPSLatitude)
        lat_ref = gps.get(GPSIFD.GPSLatitudeRef, b"N").decode()
        lon_val = gps.get(GPSIFD.GPSLongitude)
        lon_ref = gps.get(GPSIFD.GPSLongitudeRef, b"E").decode()

        lat = _dms_to_decimal(lat_val, lat_ref) if lat_val else None
        lon = _dms_to_decimal(lon_val, lon_ref) if lon_val else None
        return lat, lon
    except ImportError:
        # piexif not installed — silent fallback
        return None, None
    except Exception:
        return None, None


def extract_gps_from_fits(fits_path: str) -> tuple[Optional[float], Optional[float]]:
    """
    Extract observer GPS coordinates from a FITS header.

    Checks (in order of priority):
      SITELAT / SITELONG  — common convention (degrees, decimal or DMS string)
      OBSGEO-L / OBSGEO-B — IAU convention (decimal degrees)
      LONG-OBS / LAT-OBS  — older convention

    Returns (latitude, longitude) or (None, None).
    Does NOT require astropy — uses a minimal FITS header reader.
    """
    def _parse_deg(val) -> Optional[float]:
        """Accept float, int, or DMS string like '+43:12:34.5'."""
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return float(val)
        s = str(val).strip().replace("'", "").replace('"', "")
        try:
            return float(s)
        except ValueError:
            pass
        # Try DMS
        try:
            sign = -1 if s.startswith("-") else 1
            s = s.lstrip("+-")
            parts = s.replace(":", " ").split()
            d, m, sec = float(parts[0]), float(parts[1]), float(parts[2])
            return sign * (d + m / 60.0 + sec / 3600.0)
        except Exception:
            return None

    lat = lon = None
    try:
        with open(fits_path, "rb") as f:
            header = {}
            while True:
                block = f.read(2880)
                if not block or len(block) < 80:
                    break
                for i in range(0, len(block), 80):
                    card = block[i:i + 80].decode("ascii", errors="replace")
                    key = card[:8].strip()
                    if key == "END":
                        break
                    if "=" in card:
                        val_comment = card[9:].split("/")[0].strip().strip("'").strip()
                        header[key] = val_comment
                if "END" in header or b"END" in block:
                    break

        # Priority 1: SITELAT / SITELONG
        if "SITELAT" in header and "SITELONG" in header:
            lat = _parse_deg(header["SITELAT"])
            lon = _parse_deg(header["SITELONG"])

        # Priority 2: OBSGEO-B / OBSGEO-L
        elif "OBSGEO-B" in header and "OBSGEO-L" in header:
            lat = _parse_deg(header["OBSGEO-B"])
            lon = _parse_deg(header["OBSGEO-L"])

        # Priority 3: LAT-OBS / LONG-OBS
        elif "LAT-OBS" in header and "LONG-OBS" in header:
            lat = _parse_deg(header["LAT-OBS"])
            lon = _parse_deg(header["LONG-OBS"])

    except Exception:
        pass

    return lat, lon


def extract_gps_from_session_folder(session_folder: str,
                                     root: str) -> tuple[Optional[float], Optional[float]]:
    """
    Try to find GPS coordinates for a session by scanning its folder:
      1. stacked-16_*.fits  (FITS header — priority)
      2. stacked.jpg / any *.jpg  (EXIF GPS)

    Returns (latitude, longitude) or (None, None).
    """
    folder = Path(session_folder)
    if not folder.is_absolute():
        folder = Path(root) / folder

    # 1 — FITS header
    fits_candidates = sorted(folder.glob("stacked-16_*.fits"))
    if not fits_candidates:
        fits_candidates = sorted(folder.glob("*.fits"))
    for fits_file in fits_candidates:
        lat, lon = extract_gps_from_fits(str(fits_file))
        if lat is not None and lon is not None:
            return lat, lon

    # 2 — JPEG EXIF
    jpg_candidates = list(folder.glob("stacked.jpg")) + sorted(folder.glob("*.jpg"))
    for jpg_file in jpg_candidates:
        lat, lon = extract_gps_from_jpeg(str(jpg_file))
        if lat is not None and lon is not None:
            return lat, lon

    return None, None


# ─────────────────────────────────────────────────────────────────────────────
# High-level helper called during scan
# ─────────────────────────────────────────────────────────────────────────────

def resolve_location_for_session(conn: sqlite3.Connection,
                                  session_folder: str,
                                  root: str,
                                  dwarf_data_id: int) -> Optional[int]:
    """
    Determine and assign the best location for a newly scanned session:
      1. If GPS found in FITS/JPEG → find or create matching location
      2. Else → assign default location
    Updates DwarfData.location_id and returns the location_id used (or None).
    """
    lat, lon = extract_gps_from_session_folder(session_folder, root)

    if lat is not None and lon is not None:
        location_id = find_or_create_location_by_coords(conn, lat, lon)
    else:
        location_id = get_default_location_id(conn)

    if location_id is not None:
        set_dwarfdata_location(conn, dwarf_data_id, location_id)

    return location_id




def set_manual_session_location(conn: sqlite3.Connection,
                                  manual_session_id: int,
                                  location_id: Optional[int]) -> bool:
    """Assign (or clear) the location for a ManualSession row."""
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE ManualSession SET location_id = ? WHERE id = ?",
        (location_id, manual_session_id)
    )
    conn.commit()
    return cursor.rowcount > 0

# ─────────────────────────────────────────────────────────────────────────────
# Automatic location discovery
# ─────────────────────────────────────────────────────────────────────────────

def detect_location_by_ip() -> tuple[Optional[float], Optional[float], str]:
    """
    Get approximate location from public IP using ip-api.com (free, no key).
    Returns (latitude, longitude, city_name) or (None, None, "").
    """
    try:
        import urllib.request, json
        with urllib.request.urlopen("http://ip-api.com/json/?fields=lat,lon,city,status",
                                    timeout=4) as r:
            data = json.loads(r.read())
        if data.get("status") == "success":
            return float(data["lat"]), float(data["lon"]), data.get("city", "")
    except Exception:
        pass
    return None, None, ""

