"""The raw darks of the Dwarf: Astronomy/DWARF_DARK, next to CALI_FRAME.

Each dark session of the Dwarf leaves its raw frames there, in a folder of
its own, and - on firmwares that make one, a newer one doesn't - the master
it builds from them in CALI_FRAME: one master per setting and temperature
(CALI_FRAME/dark/cam_N/dark_exp_..._22C.fits), a new session at the same
temperature replacing it (user-found Oct 2026:
three dark sessions at three temperatures, three dated folders of 10 raw
frames and three masters; first taken for an older firmware's leftovers):

    DWARF_DARK/wide_exp_15_gain_60_bin_1_2025-11-18-06-40-05-423/
        raw_15s_60_0000_20251118-064019594_22C.fits ...
    DWARF_DARK/tele_exp_15_gain_60_bin_1/raw_15s_60_0000.fits ...   (undated)

tele = cam_0, wide = cam_1. The dated folders' frames end with their sensor
temperature (_22C); the undated ones carry none (temperature unknown).

Scope Archive finds DWARF_DARK where the Dark Library's CALI_FRAME is (copied
side by side by the Transfer page) and pairs each master with the raw
frames it was built from (pair_masters): the master is used, dated by its
raws' session. The raw sets without a master (all of them on a firmware
making none, an older session at the same temperature, a master deleted)
are candidates for a session too -
closest temperature, then closest date, the master on a tie
(pick_dark_set): Siril builds the master from the raw frames.
"""
from __future__ import annotations

import re
import statistics
from datetime import datetime
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
                **meta, "when": parse_when(meta["date"]), "legacy": True, "folder": str(folder), "files": [str(f) for f in files], "count": len(files),
                "temp_c": round(statistics.median(temps)) if temps else None,
            })
            result["total"] += len(files)
    return result


def parse_when(value) -> datetime | None:
    """A date as a datetime: a datetime, a session date ("2025-11-18
    06:40:05.123456"), or a DWARF_DARK folder date ("2025-11-18-06-40-05")."""
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    text = str(value).strip()
    for fmt, size in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%dT%H:%M:%S", 19),
                      ("%Y-%m-%d-%H-%M-%S", 19), ("%Y-%m-%d", 10)):
        try:
            return datetime.strptime(text[:size], fmt)
        except ValueError:
            continue
    return None


PAIR_TEMP_C = 1         # a master and its raws' median temperature: may differ by a degree


def pair_masters(masters: list[dict], raw_sets: list[dict]) -> list[dict]:
    """Links each CALI_FRAME master (cam, exp_s, gain, binning, temp_c) to
    the raw set it was built from: same camera and settings, temperature
    within PAIR_TEMP_C, the most recent such folder (a later session at the
    same temperature replaced the master). Sets master["raw"] = that set and
    master["when"] = its date when known (a master's file date is the
    copy's, not the session's). Returns the raw sets left unpaired."""
    def dated(s):
        return s.get("when") or datetime.min

    paired = set()
    for m in masters:
        twins = [r for r in raw_sets
                 if r["cam"] == m["cam"] and r["gain"] == m["gain"] and r["binning"] == m["binning"]
                 and abs(r["exp_s"] - m["exp_s"]) <= max(0.05, m["exp_s"] * 0.02)
                 and r["temp_c"] is not None and abs(r["temp_c"] - m["temp_c"]) <= PAIR_TEMP_C
                 and id(r) not in paired]
        if not twins:
            continue
        raw = max(twins, key=dated)
        paired.add(id(raw))
        m["raw"] = raw
        if raw.get("when"):
            m["when"] = raw["when"]
    return [r for r in raw_sets if id(r) not in paired]


TEMP_MARGIN_C = 2       # around the session's range: still a match (user-requested Oct 2026)
TEMP_SLACK_C = 2        # temperatures this close to the best one count as equal


def pick_dark_set(sets: list[dict], min_temp: int | None, max_temp: int | None,
                  session_date=None) -> tuple[dict | None, bool]:
    """The dark set for a session among sets already matching its settings
    and camera (each: temp_c - None when unknown -, when - a datetime or
    None -, legacy - DWARF_DARK raw frames without their master, or a
    CALI_FRAME master):

    1. the temperature in the session's range widened by TEMP_MARGIN_C,
       else the closest known one (within TEMP_SLACK_C), else the sets of
       unknown temperature;
    2. among those, the date closest to the session's, before or after (the
       most recent when the session's date is unknown; undated sets last);
    3. on a tie, the CALI_FRAME master.

    (set, temperature matched)."""
    if not sets:
        return None, False
    known = [s for s in sets if s["temp_c"] is not None]
    temp_ok = False
    pool = sets
    if min_temp is not None and max_temp is not None and known:
        in_range = [s for s in known
                    if min_temp - TEMP_MARGIN_C <= s["temp_c"] <= max_temp + TEMP_MARGIN_C]
        if in_range:
            pool, temp_ok = in_range, True
        else:
            middle = (min_temp + max_temp) / 2.0
            best = min(abs(s["temp_c"] - middle) for s in known)
            pool = [s for s in known if abs(s["temp_c"] - middle) <= best + TEMP_SLACK_C]
    elif known:
        pool = known

    session_dt = parse_when(session_date)

    def distance(s):
        when = s.get("when")
        if when is None:
            return float("inf")
        if session_dt is None:
            return -when.timestamp()            # the most recent
        return abs((when - session_dt).total_seconds())

    return min(pool, key=lambda s: (distance(s), s.get("legacy", False))), temp_ok
