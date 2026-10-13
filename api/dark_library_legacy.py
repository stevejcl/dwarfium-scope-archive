"""Darks of an older Dwarf firmware: Astronomy/DWARF_DARK (user-requested
Oct 2026), next to CALI_FRAME.

Not one master dark per setting (CALI_FRAME/dark/cam_N/dark_exp_..._13C.fits)
but one folder per setting, holding the raw dark frames:

    DWARF_DARK/tele_exp_15_gain_60_bin_1/raw_15s_60_0000.fits ...
    DWARF_DARK/wide_exp_15_gain_60_bin_1_2025-11-18-06-40-05-423/
        raw_15s_60_0000_20251118-064019594_22C.fits ...

tele = cam_0, wide = cam_1. The dated folders' frames end with their sensor
temperature (_22C); the older ones carry none (temperature unknown).

Scope Archive finds DWARF_DARK where the Dark Library's CALI_FRAME is (copied
side by side by the Transfer page), lists it on the Dark Library page, and
uses its raw frames for a session when no CALI_FRAME master matches - the
current firmware's masters first (find_matching_darks): Siril builds the
master from the raw frames.
"""
from __future__ import annotations

import re
import statistics
from pathlib import Path

LEGACY_DIR_NAME = "DWARF_DARK"
CAMERAS = {"tele": "cam_0", "wide": "cam_1"}

_DIR_RE = re.compile(
    r"^(?P<cam>tele|wide)_exp_(?P<exp>[0-9]+(?:\.[0-9]+)?)_gain_(?P<gain>[0-9]+)_bin_(?P<bin>[0-9]+)"
    r"(?:_(?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{2}-[0-9]{2}-[0-9]{2})(?:-[0-9]+)?)?$",
    re.IGNORECASE,
)
_TEMP_RE = re.compile(r"_(?P<temp>-?[0-9]+)C\.(?:fits?|fts)$", re.IGNORECASE)
_FITS = ("*.fit", "*.fits", "*.fts", "*.FIT", "*.FITS", "*.FTS")


def legacy_roots(location) -> list[Path]:
    """The DWARF_DARK folders of a Dark Library location: next to its
    CALI_FRAME, whether the location is the folder holding CALI_FRAME or
    CALI_FRAME itself."""
    if not location:
        return []
    base = Path(location)
    candidates = [base / LEGACY_DIR_NAME]
    if base.name.upper() == "CALI_FRAME":
        candidates.append(base.parent / LEGACY_DIR_NAME)
    roots, seen = [], set()
    for c in candidates:
        try:
            key = c.resolve()
        except OSError:
            key = c
        if c.is_dir() and key not in seen:
            seen.add(key)
            roots.append(c)
    return roots


def _fits_files(folder: Path) -> list[Path]:
    files: set[Path] = set()
    for ext in _FITS:
        files.update(folder.glob(ext))
    return sorted(files)


def parse_folder(name: str) -> dict | None:
    """{cam, exp_s, gain, binning, date} from a DWARF_DARK folder name, or None."""
    m = _DIR_RE.match(name)
    if not m:
        return None
    return {"cam": CAMERAS[m.group("cam").lower()], "exp_s": float(m.group("exp")),
            "gain": int(m.group("gain")), "binning": int(m.group("bin")), "date": m.group("date")}


def scan_legacy_darks(location) -> dict:
    """{"dirs": [DWARF_DARK paths], "total": frames, "sets": [..], "errors": [..]}
    - a set: {folder, cam, exp_s, gain, binning, date, temp_c (median of the
    frames' temperatures, None when unknown), count, files}."""
    result = {"dirs": [], "total": 0, "sets": [], "errors": []}
    for root in legacy_roots(location):
        result["dirs"].append(str(root))
        for folder in sorted(p for p in root.iterdir() if p.is_dir()):
            meta = parse_folder(folder.name)
            if meta is None:
                result["errors"].append(str(folder))
                continue
            files = _fits_files(folder)
            if not files:
                continue
            temps = [int(m.group("temp")) for m in (_TEMP_RE.search(f.name) for f in files) if m]
            result["sets"].append({
                **meta, "folder": str(folder), "files": [str(f) for f in files], "count": len(files),
                "temp_c": round(statistics.median(temps)) if temps else None,
            })
            result["total"] += len(files)
    return result


def best_legacy_set(locations, exp_s: float, gain: int, binning: int, cam: str | None,
                    min_temp: int | None, max_temp: int | None) -> tuple[dict | None, bool]:
    """The DWARF_DARK set matching a session - same gain and binning,
    exposure within 2% (as for CALI_FRAME), same camera when given - with
    its temperature in the session's range when known, else the closest
    known temperature, else the most recent. (set, temperature matched)."""
    exp_tol = max(0.05, exp_s * 0.02)
    matches = []
    for location in locations:
        for s in scan_legacy_darks(location)["sets"]:
            if s["gain"] != gain or s["binning"] != binning or abs(s["exp_s"] - exp_s) > exp_tol:
                continue
            if cam and s["cam"] != cam:
                continue
            matches.append(s)
    if not matches:
        return None, False

    def recent(s):                      # undated (oldest firmware) last
        return s["date"] or ""

    if min_temp is not None and max_temp is not None:
        in_range = [s for s in matches if s["temp_c"] is not None and min_temp <= s["temp_c"] <= max_temp]
        if in_range:
            return max(in_range, key=recent), True
        known = sorted((s for s in matches if s["temp_c"] is not None), key=recent, reverse=True)
        if known:                       # closest temperature; the most recent of equals (min keeps the first)
            middle = (min_temp + max_temp) / 2.0
            return min(known, key=lambda s: abs(s["temp_c"] - middle)), False
    return max(matches, key=recent), False
