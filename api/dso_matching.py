"""
api/dso_matching.py

Shared catalog/geometry helpers used by multiple pages
(astro_object_associate, recommend_tonight, sky_search_dialog, ...).

Pure functions only — no NiceGUI/UI code here.
"""

from __future__ import annotations

import math
import json
from pathlib import Path
from typing import Optional

from astropy.coordinates import SkyCoord
from astropy import units as u


# ── Angular separation ───────────────────────────────────────────────────────

def angular_sep_deg(ra1_deg: float, dec1_deg: float, ra2_deg: float, dec2_deg: float) -> float:
    """Angular separation in degrees via astropy. Use for one-off / low-volume
    calculations where accuracy matters more than raw speed."""
    c1 = SkyCoord(ra=ra1_deg * u.deg, dec=dec1_deg * u.deg, frame='icrs')
    c2 = SkyCoord(ra=ra2_deg * u.deg, dec=dec2_deg * u.deg, frame='icrs')
    return c1.separation(c2).degree


def angular_sep_deg_fast(ra1_deg: float, dec1_deg: float, ra2_deg: float, dec2_deg: float) -> float:
    """Haversine angular separation in degrees, no astropy object creation.
    Use for tight loops / live UI filtering (e.g. catalog browsing on
    keystroke) where astropy's per-call overhead would add up."""
    r = math.pi / 180
    d_dec = (dec2_deg - dec1_deg) * r
    d_ra  = (ra2_deg  - ra1_deg)  * r
    a = (math.sin(d_dec / 2) ** 2
         + math.cos(dec1_deg * r) * math.cos(dec2_deg * r) * math.sin(d_ra / 2) ** 2)
    return 2 * math.asin(math.sqrt(min(a, 1.0))) / r


# ── Catalog loading (centralized, cached) ────────────────────────────────────

_dso_cache: Optional[list[dict]] = None


def load_dso_catalog(force_reload: bool = False) -> list[dict]:
    """
    Load the DSO catalog, preferring the preprocessed version (with
    ra_deg/dec_deg already computed). Falls back to parsing the raw
    catalog's ra/dec HMS/DMS strings on the fly if only that is available.
    Cached in-process after first load; pass force_reload=True to bypass.
    """
    global _dso_cache
    if _dso_cache is not None and not force_reload:
        return _dso_cache

    from api.dwarf_backup_fct import CATALOG_FILE, SKY_CATALOG_FILE, preprocess_dso_catalog_json

    try:
        preprocess_dso_catalog_json(CATALOG_FILE, SKY_CATALOG_FILE)
    except Exception as e:
        print(f"[dso_matching] preprocess_dso_catalog_json failed: {e}")

    for path in [Path(SKY_CATALOG_FILE), Path(CATALOG_FILE)]:
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)

        if data and data[0].get("ra_deg") is not None:
            _dso_cache = data
            return _dso_cache

        # Raw catalog — convert ra/dec HMS/DMS strings to degrees on the fly
        converted = []
        for entry in data:
            ra_str, dec_str = entry.get("ra", ""), entry.get("dec", "")
            if not ra_str or not dec_str:
                continue
            try:
                parts = ra_str.replace("h", " ").replace("m", " ").replace("s", "").split()
                h, m, s = float(parts[0]), float(parts[1]), float(parts[2])
                ra_deg = (h + m / 60 + s / 3600) * 15.0

                dec_clean = (dec_str.replace("°", " ").replace("'", " ")
                             .replace('"', "").replace("′", " ").replace("″", " "))
                sign = -1 if dec_clean.strip().startswith("-") else 1
                dparts = dec_clean.strip().lstrip("+-").split()
                d, dm, ds = float(dparts[0]), float(dparts[1]), float(dparts[2])
                dec_deg = sign * (d + dm / 60 + ds / 3600)

                e2 = dict(entry)
                e2["ra_deg"], e2["dec_deg"] = ra_deg, dec_deg
                converted.append(e2)
            except Exception:
                pass  # skip malformed entries

        _dso_cache = converted
        return _dso_cache

    _dso_cache = []
    return _dso_cache


# ── Name / nearest-object matching ───────────────────────────────────────────

def normalize_name(name: Optional[str]) -> str:
    import re
    if not name:
        return ""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def build_catalog_name_index(catalog: list[dict]) -> dict[str, str]:
    index: dict[str, str] = {}
    for obj in catalog:
        for candidate in (obj.get("designation") or obj.get("id"),
                          obj.get("displayName") or obj.get("name")):
            key = normalize_name(candidate or "")
            if key:
                index.setdefault(key, obj.get("designation") or obj.get("id"))
    return index

import bisect

def find_nearest_catalog_object(
    ra_deg: float, dec_deg: float,
    catalog_sorted_by_dec: list[dict],
    catalog_decs: list[float],
    max_sep_deg: float,
) -> Optional[str]:
    """
    catalog_sorted_by_dec: catalog entries pre-sorted ascending by dec_deg.
    catalog_decs: parallel list of dec_deg values (same order), used to
    binary-search the relevant declination band instead of scanning the
    whole catalog for every call.
    """
    lo = bisect.bisect_left(catalog_decs, dec_deg - max_sep_deg)
    hi = bisect.bisect_right(catalog_decs, dec_deg + max_sep_deg)

    best_id, best_sep = None, max_sep_deg
    for obj in catalog_sorted_by_dec[lo:hi]:
        sep = angular_sep_deg_fast(ra_deg, dec_deg, obj["ra_deg"], obj["dec_deg"])
        if sep < best_sep:
            best_sep, best_id = sep, (obj.get("designation") or obj.get("id"))
    return best_id


def resolve_catalog_id(
    designation, object_name, description, ra_hours, dec_deg,
    name_index, catalog_sorted_by_dec, catalog_decs,
    max_sep_deg: float = 1.0,
) -> Optional[str]:
    if designation:
        return designation
    for candidate in (description, object_name):
        key = normalize_name(candidate or "")
        if key and key in name_index:
            return name_index[key]
    if ra_hours is not None and dec_deg is not None:
        try:
            ra_deg = float(ra_hours) * 15.0
            dec_deg = float(dec_deg)
        except (TypeError, ValueError):
            return None
        return find_nearest_catalog_object(
            ra_deg, dec_deg, catalog_sorted_by_dec, catalog_decs, max_sep_deg
        )
    return None