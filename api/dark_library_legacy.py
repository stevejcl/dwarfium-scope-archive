"""The raw darks of the Dwarf: Astronomy/DWARF_DARK, next to CALI_FRAME.

Each dark session of the Dwarf leaves its raw frames there, in a folder of
its own, and - on firmwares that make one, a newer one doesn't - the master
it builds from them in CALI_FRAME: one master per setting and temperature
(CALI_FRAME/dark/cam_N/dark_exp_..._22C.fits), a new session at the same
temperature replacing it - one master per temperature met during the session:
its raw frames grouped by the temperature in their names, the master's
_stack_N its frame count (user-found Oct 2026: a session of 10 frames gave
dark_..._23C_stack_7.fits and dark_..._24C_stack_1.fits;
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


def fits_firmware(path) -> str | None:
    """The FIRMWARE keyword of a Dwarf FITS file's header ('1.5.3.9'), read
    without loading the image; None when absent or unreadable."""
    try:
        with open(path, "rb") as f:
            while True:
                block = f.read(2880)
                if len(block) < 80:
                    return None
                for i in range(0, len(block), 80):
                    card = block[i:i + 80].decode("ascii", "replace")
                    if card.startswith("FIRMWARE="):
                        value = card[10:].split("/")[0].strip().strip("'").strip()
                        return value or None
                    if card.startswith("END") and card[3:].strip() == "":
                        return None
    except OSError:
        return None


def folder_firmware(folder) -> str | None:
    """A session's firmware: the FIRMWARE of its first FITS files that carry
    one, its panels' for a mosaic."""
    base = Path(folder) if folder else None
    if base is None or not base.is_dir():
        return None
    for d in [base] + sorted(p for p in base.iterdir() if p.is_dir()):
        for f in _fits_files(d)[:5]:
            fw = fits_firmware(f)
            if fw:
                return fw
    return None


def parse_folder(name: str) -> dict | None:
    """{cam, exp_s, gain, binning, date} from a DWARF_DARK folder name, or None."""
    m = _DIR_RE.match(name)
    if not m:
        return None
    return {"cam": CAMERAS[m.group("cam").lower()], "exp_s": float(m.group("exp")),
            "gain": int(m.group("gain")), "binning": int(m.group("bin")), "date": m.group("date")}


def scan_legacy_darks(location) -> dict:
    """{"dirs": [DWARF_DARK paths], "total": frames, "sets": [..], "errors": [..]}
    - a set: the frames of one folder at one temperature, as the Dwarf builds
    one master per temperature: {folder, cam, exp_s, gain, binning, date,
    temp_c (None when the names carry none), count, frames, files, firmware
    (its frames' FIRMWARE header, None when absent)}."""
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
            firmware = next((fw for fw in map(fits_firmware, files[:3]) if fw), None)
            by_temp: dict = {}
            for f in files:
                m = _TEMP_RE.search(f.name)
                by_temp.setdefault(int(m.group("temp")) if m else None, []).append(f)
            for temp_c, group in sorted(by_temp.items(), key=lambda kv: (kv[0] is None, kv[0] or 0)):
                result["sets"].append({
                    **meta, "when": parse_when(meta["date"]), "legacy": True, "folder": str(folder),
                    "files": [str(f) for f in group], "count": len(group), "frames": len(group), "temp_c": temp_c,
                    "firmware": firmware,
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


PAIR_TEMP_C = 0         # a master is built from its session's frames at its temperature


def pair_masters(masters: list[dict], raw_sets: list[dict]) -> list[dict]:
    """Links each CALI_FRAME master (cam, exp_s, gain, binning, temp_c) to
    the raw set it was built from: same camera and settings, the same
    temperature (PAIR_TEMP_C), the most recent such folder (a later session at the
    same temperature replaced the master). Sets master["raw"] = that set and
    master["when"] = its date when known (a master's file date is the
    copy's, not the session's), master["firmware"] = its firmware (a
    master's header carries none). Returns the raw sets left unpaired."""
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
        m["firmware"] = raw.get("firmware")
        if raw.get("when"):
            m["when"] = raw["when"]
    return [r for r in raw_sets if id(r) not in paired]


TEMP_MARGIN_C = 2       # around the session's range: still a match (user-requested Oct 2026)
TEMP_SLACK_C = 1        # temperatures this close to the best one count as equal
UNKNOWN_FRAMES = 10     # a master without _stack_N: a dark session's usual frame count
ERA_DAYS = 90           # darks this close to the session's date: the same sensor / firmware era


def pick_dark_set(sets: list[dict], min_temp: int | None, max_temp: int | None,
                  session_date=None, session_firmware=None) -> tuple[dict | None, bool]:
    """The dark set for a session among sets already matching its settings
    and camera (each: temp_c - None when unknown -, when - a datetime or
    None -, legacy - DWARF_DARK raw frames without their master, or a
    CALI_FRAME master):

    1. the darks of the session's firmware (FIRMWARE header: the raw
       frames', a master's through its raws) - a firmware update can change
       the raw frames; else, firmware unknown on either side, the darks of
       the session's era: dated within ERA_DAYS of it, before or after - a
       sensor gains hot pixels over time. No dark of another firmware or era
       corrects that, while Siril's dark optimisation makes up for a
       temperature gap (user-asked Oct 2026: darks at several temperatures,
       the date used to win over the temperature). All of them when none is;
    2. among those, the temperature closest to the middle of the session's
       range (within TEMP_SLACK_C), else the sets of unknown temperature;
    3. then the most frames (frames: a master's _stack_N, a raw set's count
       - a master of 1 frame is just a raw frame's noise; UNKNOWN_FRAMES
       when not known);
    4. then the date closest to the session's, before or after (the most
       recent when the session's date is unknown; undated sets last);
    5. on a tie, the CALI_FRAME master.

    (set, temperature matched: within the session's range widened by
    TEMP_MARGIN_C)."""
    if not sets:
        return None, False
    session_dt = parse_when(session_date)

    pool = sets
    same_fw = [s for s in sets if session_firmware and s.get("firmware") == session_firmware]
    if same_fw:
        pool = same_fw
    elif session_dt is not None:
        era = [s for s in sets if s.get("when") is not None
               and abs((s["when"] - session_dt).total_seconds()) <= ERA_DAYS * 86400]
        pool = era or sets

    known = [s for s in pool if s["temp_c"] is not None]
    if min_temp is not None and max_temp is not None and known:
        middle = (min_temp + max_temp) / 2.0
        best = min(abs(s["temp_c"] - middle) for s in known)
        pool = [s for s in known if abs(s["temp_c"] - middle) <= best + TEMP_SLACK_C]
    elif known:
        pool = known

    def distance(s):
        when = s.get("when")
        if when is None:
            return float("inf")
        if session_dt is None:
            return -when.timestamp()            # the most recent
        return abs((when - session_dt).total_seconds())

    def frames(s):
        n = s.get("frames")
        return n if n is not None else UNKNOWN_FRAMES

    chosen = min(pool, key=lambda s: (-frames(s), distance(s), s.get("legacy", False)))
    temp_ok = (min_temp is not None and max_temp is not None and chosen["temp_c"] is not None
               and min_temp - TEMP_MARGIN_C <= chosen["temp_c"] <= max_temp + TEMP_MARGIN_C)
    return chosen, temp_ok
