"""The darks missing for the sessions already done (Dark Library page).

For one Dwarf: every session it made (backed up, or still on the Dwarf) is
compared with the darks of the Dwarf's libraries, by the same rule as the
dark match badge of Explore (api/dwarf_backup_db_api.find_matching_darks ->
api/dark_library_legacy.pick_dark_set): same camera, gain and binning,
exposure within 2 %, then the temperature range of the session.

The libraries are scanned once (find_matching_darks scans them at each call,
too slow for a whole archive). The result groups the sessions by the dark
they need - camera, exposure, gain, binning - so that the answer is a list of
dark sessions to take, sorted by camera, binning, exposure, gain:

    {"sessions": n, "ok": n, "partial": n, "none": n, "skipped": n,
     "groups": [{"cam", "exp_s", "gain", "binning", "status", "sessions": [..],
                 "min_temp", "max_temp", "available_temps": [..]}]}

status: "none" - no dark of these settings at all; "temperature" - darks of
these settings, none within the session's temperatures (TEMP_MARGIN_C around).
The firmware of a session isn't read (its files may be on a drive that is not
there): the era of its date is used, as for a session without it.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from api.dark_library_legacy import pair_masters, pick_dark_set, scan_legacy_darks

_DARK_RE = re.compile(
    r"dark_exp_(?P<exp>[0-9]+\.?[0-9]*)_gain_(?P<gain>[0-9]+)"
    r"_bin_(?P<bin>[0-9]+)_(?P<temp>-?[0-9]+)C(?:_stack_(?P<stack>[0-9]+))?",
    re.IGNORECASE,
)
_FITS = ("*.fit", "*.fits", "*.fts", "*.FIT", "*.FITS", "*.FTS")


def _fits_files(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    files: set[Path] = set()
    for ext in _FITS:
        files.update(folder.glob(ext))
    return sorted(files)


def _parse_dark(name: str) -> dict | None:
    m = _DARK_RE.search(name)
    if not m:
        return None
    return {"exp_s": float(m.group("exp")), "gain": int(m.group("gain")),
            "binning": int(m.group("bin")), "temp_c": int(m.group("temp")),
            "frames": int(m.group("stack")) if m.group("stack") else None}


def collect_dark_sets(libraries) -> list[dict]:
    """Every dark set of the libraries (CALI_FRAME masters, DWARF_DARK raw
    sets without a master), as find_matching_darks builds them but for all the
    settings."""
    sets: list[dict] = []
    for lib_loc in libraries:
        masters = []
        dark_dir = Path(lib_loc) / "dark"
        if not dark_dir.is_dir():
            dark_dir = Path(lib_loc) / "CALI_FRAME" / "dark"
        for cam in ("cam_0", "cam_1"):
            for f in _fits_files(dark_dir / cam):
                meta = _parse_dark(f.name)
                if not meta:
                    continue
                try:
                    when = datetime.fromtimestamp(f.stat().st_mtime)
                except OSError:
                    when = None
                masters.append({**meta, "cam": cam, "files": [str(f)], "count": 1,
                                "when": when, "legacy": False, "library": lib_loc})
        raws = []
        try:
            raws = [{**s, "library": str(Path(s["folder"]).parent.parent)}
                    for s in scan_legacy_darks(lib_loc)["sets"]]
        except OSError as e:
            print(f"[missing darks] DWARF_DARK: {e}")
        sets.extend(masters)
        sets.extend(pair_masters(masters, raws))
    return sets


def _exposure_seconds(exp_time) -> float | None:
    """A DwarfData.exp_time ("15", "0.5", "15s") in seconds, None when unknown."""
    if exp_time in (None, ""):
        return None
    try:
        from api.dwarf_backup_fct import parse_exposure
        value = parse_exposure(f"{exp_time}s")
    except Exception:
        try:
            value = float(str(exp_time).strip().rstrip("sS"))
        except ValueError:
            return None
    return float(value) if value else None


def prepare_sessions(rows) -> tuple[list[dict], int]:
    """The rows of db_api.get_dwarf_sessions_for_darks as session dicts: the
    sessions without raw frames (RESTACKED_) or without settings are left out,
    one entry per DwarfData. Returns (sessions, number left out for lack of
    settings)."""
    sessions, seen, skipped = [], set(), 0
    for (data_id, date, session_dir, exp_time, gain, binning_raw, min_temp, max_temp, target) in rows:
        if data_id in seen:
            continue
        seen.add(data_id)
        if "RESTACKED" in str(session_dir or "").upper():
            continue
        exp_s = _exposure_seconds(exp_time)
        try:
            gain_i = int(gain)
        except (TypeError, ValueError):
            gain_i = None
        if exp_s is None or gain_i is None:
            skipped += 1
            continue
        try:
            binning = int(str(binning_raw).split("*")[0]) if binning_raw else 1
        except ValueError:
            binning = 1
        sessions.append({
            "id": data_id, "date": str(date or "")[:19], "dir": session_dir or "",
            "target": target or "", "exp_s": exp_s, "gain": gain_i, "binning": binning,
            "min_temp": int(min_temp) if min_temp is not None else None,
            "max_temp": int(max_temp) if max_temp is not None else None,
            "cam": "cam_1" if "_WIDE_" in str(session_dir or "").upper() else "cam_0",
        })
    return sessions, skipped


def _settings_match(d: dict, s: dict) -> bool:
    return (d["cam"] == s["cam"] and d["gain"] == s["gain"] and d["binning"] == s["binning"]
            and abs(d["exp_s"] - s["exp_s"]) <= max(0.05, s["exp_s"] * 0.02))


def analyse_missing_darks(rows, libraries) -> dict:
    """See the module's docstring. Blocking (reads the libraries' folders)."""
    sessions, skipped = prepare_sessions(rows)
    sets = collect_dark_sets(libraries)

    groups: dict = {}
    ok = partial = none = 0
    for s in sessions:
        candidates = [d for d in sets if _settings_match(d, s)]
        best, temp_ok = pick_dark_set(candidates, s["min_temp"], s["max_temp"], s["date"], None)
        if best is not None and (temp_ok or s["min_temp"] is None):
            ok += 1
            continue
        status = "none" if best is None else "temperature"
        if status == "none":
            none += 1
        else:
            partial += 1
        key = (s["cam"], round(s["exp_s"], 3), s["gain"], s["binning"])
        g = groups.setdefault(key, {
            "cam": s["cam"], "exp_s": s["exp_s"], "gain": s["gain"], "binning": s["binning"],
            "status": status, "sessions": [], "min_temp": None, "max_temp": None,
            "available_temps": sorted({d["temp_c"] for d in candidates if d["temp_c"] is not None}),
        })
        g["sessions"].append({"date": s["date"], "target": s["target"], "dir": s["dir"],
                              "min_temp": s["min_temp"], "max_temp": s["max_temp"], "status": status})
        if s["min_temp"] is not None:
            g["min_temp"] = s["min_temp"] if g["min_temp"] is None else min(g["min_temp"], s["min_temp"])
        if s["max_temp"] is not None:
            g["max_temp"] = s["max_temp"] if g["max_temp"] is None else max(g["max_temp"], s["max_temp"])

    # camera, then binning, exposure, gain (user-asked Nov 2026)
    ordered = sorted(groups.values(), key=lambda g: (g["cam"], g["binning"], g["exp_s"], g["gain"]))
    for g in ordered:
        g["sessions"].sort(key=lambda x: x["date"], reverse=True)
    return {"sessions": len(sessions), "ok": ok, "partial": partial, "none": none,
            "skipped": skipped, "groups": ordered}
