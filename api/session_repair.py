"""Repair of a failed (non-mosaic) session on the Dwarf (user-asked Oct 2026,
from DwarfLab's procedure "How I Fixed My Failed Session with the Dwarf3").

A capture that ended badly (the Dwarf hung, an empty battery, a reboot)
keeps its images on the Dwarf, but its stacked FITS is missing (user's
Lion Nebula: no stacked-16_<...>.fits, no img_stacked_counter.png - its
stacked.jpg and stacked-16_<...>.png were there): the session is in neither
the Album nor the Megastack. DwarfLab's way: a short new session with the
same settings (2 images - Astro Dwarf Session's "Repair session"), its FITS
removed, the failed session's images and shotsInfo.json put in it - and its
stacked image / stacked-16 PNG / FITS when there - renamed
to the new session's name and date (their time kept); after a reboot of the
Dwarf the new session shows in the Album with all the images, for the
Megastack. Also a way to megastack two sessions of one region under
different names ("Unknown", a star near the target).

The images' names: <target>_<exposure>s<gain>_<filter>_<YYYYMMDD>-<HHMMSSmmm>_<temp>C.fits
(failed_ in front of a frame the Dwarf didn't stack), their thumbnails
under Thumbnail/ (same name, .jpg)."""
from __future__ import annotations

import json
import os
import re
import shutil

FRAME_RE = re.compile(
    r"^(?P<failed>failed_)?(?P<target>.+)_(?P<expgain>\d+(?:\.\d+)?s\d+)_(?P<filter>[^_]+)_"
    r"(?P<date>\d{8})-(?P<time>\d{9})_(?P<temp>-?\d+)C\.(?P<ext>fits?|jpg)$",
    re.IGNORECASE,
)
THUMBNAIL_DIR = "Thumbnail"
# The failed session's own results, kept (user-asked Oct 2026): fixed names,
# put in place of the new session's
RESULT_FILES = ("stacked.jpg", "stacked_thumbnail.jpg", "img_reference.png", "img_stacked_counter.png")
STACK_PREFIX = "stacked-16_"
SHOTS_INFO = "shotsInfo.json"
REPAIR_INFO = "repairInfo.json"


def is_frame(name: str) -> bool:
    return FRAME_RE.match(name) is not None


def missing_stack(session_dir: str) -> bool:
    """A session whose capture ended badly: its images and shotsInfo.json,
    no stacked-16_*.fits (with or without its stacked.jpg / .png)."""
    try:
        names = os.listdir(session_dir)
    except OSError:
        return False
    lower = [n.lower() for n in names]
    has_frames = any(is_frame(n) and not n.lower().endswith(".jpg") for n in names)
    has_stack = any(n.startswith("stacked-16") and n.endswith(".fits") for n in lower)
    return SHOTS_INFO.lower() in lower and has_frames and not has_stack


def _frames(folder: str) -> list[str]:
    try:
        return sorted(n for n in os.listdir(folder) if is_frame(n))
    except OSError:
        return []


def _template(new_dir: str) -> re.Match | None:
    """A frame of the new session: its target, settings, filter and date."""
    for folder in (new_dir, os.path.join(new_dir, THUMBNAIL_DIR)):
        for name in _frames(folder):
            m = FRAME_RE.match(name)
            if m:
                return m
    return None


def renamed(name: str, template: re.Match) -> str:
    """name with the new session's target and date, its own time, temperature
    and failed_ prefix kept."""
    m = FRAME_RE.match(name)
    if not m:
        return name
    return (f"{m['failed'] or ''}{template['target']}_{m['expgain']}_{m['filter']}_"
            f"{template['date']}-{m['time']}_{m['temp']}C.{m['ext']}")


def _result_copies(failed_dir: str, new_dir: str, template: re.Match) -> list[tuple[str, str]]:
    """The failed session's stacked image, thumbnail, reference... and its
    stacked-16_<...>.png / .fits when there, under the new session's names
    (user-asked Oct 2026: kept, with the small session's name): a stacked-16
    file takes the name of the new session's stacked-16 file (its own
    target, date and time), else the new target and date with its own time."""
    try:
        failed_names, new_names = os.listdir(failed_dir), os.listdir(new_dir)
    except OSError:
        return []
    copies = [(os.path.join(failed_dir, n), os.path.join(new_dir, n))
              for n in RESULT_FILES if n in failed_names]
    new_stacks = [n for n in new_names if n.startswith(STACK_PREFIX)]
    new_base = os.path.splitext(new_stacks[0])[0] if new_stacks else None
    for name in failed_names:
        if not name.startswith(STACK_PREFIX):
            continue
        ext = os.path.splitext(name)[1]
        if new_base is not None:
            dst = new_base + ext
        else:
            m = re.match(r"^stacked-16_(?P<target>.+)_(?P<rest>\d+(?:\.\d+)?s\d+_[^_]+)_(?P<date>\d{8})-(?P<time>\d{9})$",
                         os.path.splitext(name)[0])
            dst = (f"{STACK_PREFIX}{template['target']}_{m['rest']}_{template['date']}-{m['time']}{ext}"
                   if m else name)
        copies.append((os.path.join(failed_dir, name), os.path.join(new_dir, dst)))
    return copies


def plan_repair(failed_dir: str, new_dir: str) -> dict:
    """What repair() will do, nothing changed: {"remove": [paths], "copy":
    [(src, dst)], "warnings": [str], "error": str | None}."""
    plan = {"remove": [], "copy": [], "warnings": [], "error": None}
    if os.path.normcase(os.path.abspath(failed_dir)) == os.path.normcase(os.path.abspath(new_dir)):
        plan["error"] = "the failed session and the new one are the same folder"
        return plan
    template = _template(new_dir)
    if template is None:
        plan["error"] = "no image found in the new session (a session of 2 images at least)"
        return plan
    failed_frames = [n for n in _frames(failed_dir) if not n.lower().endswith(".jpg")]
    if not failed_frames:
        plan["error"] = "no image found in the failed session"
        return plan
    first = FRAME_RE.match(failed_frames[0])
    for key, label in (("expgain", "exposure / gain"), ("filter", "filter")):
        if first[key].lower() != template[key].lower():
            plan["warnings"].append(f"{label} differ: {first[key]} (failed) / {template[key]} (new) - "
                                    "the Megastack may refuse them")
    if first["target"] != template["target"]:
        plan["warnings"].append(f"target renamed: {first['target']} -> {template['target']}")

    for folder in (new_dir, os.path.join(new_dir, THUMBNAIL_DIR)):
        plan["remove"] += [os.path.join(folder, n) for n in _frames(folder)]
    plan["copy"] += [(os.path.join(failed_dir, n), os.path.join(new_dir, renamed(n, template)))
                     for n in failed_frames]
    thumbs = os.path.join(failed_dir, THUMBNAIL_DIR)
    plan["copy"] += [(os.path.join(thumbs, n), os.path.join(new_dir, THUMBNAIL_DIR, renamed(n, template)))
                     for n in _frames(thumbs) if n.lower().endswith(".jpg")]
    plan["copy"] += _result_copies(failed_dir, new_dir, template)
    if os.path.isfile(os.path.join(failed_dir, SHOTS_INFO)):
        plan["copy"].append((os.path.join(failed_dir, SHOTS_INFO), os.path.join(new_dir, SHOTS_INFO)))
    else:
        plan["warnings"].append("no shotsInfo.json in the failed session")
    return plan


def backup_path(backup_dir: str, new_dir: str) -> str:
    """Where backup_new_session() keeps the new session's files."""
    return os.path.join(backup_dir, os.path.basename(os.path.normpath(new_dir)) + "_before_repair")


def backup_new_session(plan: dict, new_dir: str, backup_dir: str) -> tuple[str, int]:
    """Copies the new session's files the repair removes or replaces (its
    images, stacked.jpg, stacked-16..., shotsInfo.json) into
    <backup_dir>/<session>_before_repair/, same layout (user-asked Oct 2026:
    a way back if the repair went wrong). Returns (folder, count); raises
    when a copy fails - nothing changed on the Dwarf then."""
    folder = backup_path(backup_dir, new_dir)
    targets = list(plan["remove"]) + [dst for _, dst in plan["copy"] if os.path.isfile(dst)]
    count = 0
    for path in dict.fromkeys(targets):
        rel = os.path.relpath(path, new_dir)
        dst = os.path.join(folder, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(path, dst)
        count += 1
    return folder, count


def repair(failed_dir: str, new_dir: str, log=print, progress=None, backup_dir: str | None = None) -> dict:
    """Applies plan_repair(): the new session's own images removed, the failed
    session's copied in (the failed session left as it is), repairInfo.json
    written. The new session's stacked-16 files, stacked.jpg... replaced by the
failed session's when it has them, kept otherwise. backup_dir: the new
session's files saved there first (backup_new_session()). Returns the plan
with "copied" (count) and "backup" (folder, when saved); raises on its
error."""
    plan = plan_repair(failed_dir, new_dir)
    if plan["error"]:
        raise ValueError(plan["error"])
    for warning in plan["warnings"]:
        log(f"⚠️ {warning}")
    if backup_dir:
        folder, count = backup_new_session(plan, new_dir, backup_dir)
        plan["backup"] = folder
        log(f"💾 {count} file(s) of the new session saved in {folder}")
    for path in plan["remove"]:
        os.remove(path)
    log(f"ℹ️ {len(plan['remove'])} image(s) of the new session removed")
    total = len(plan["copy"])
    for i, (src, dst) in enumerate(plan["copy"], 1):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        if progress is not None:
            progress(i / total)
    plan["copied"] = total
    with open(os.path.join(new_dir, REPAIR_INFO), "w", encoding="utf-8") as f:
        json.dump({"type": "SESSION_REPAIR", "source_session": os.path.basename(os.path.normpath(failed_dir))}, f, indent=2)
    log(f"✅ {total} file(s) copied from {os.path.basename(os.path.normpath(failed_dir))}")
    return plan


# A capture's folder on the Dwarf: DWARF_RAW_<TELE|WIDE>_<target>_EXP_<exposure>_GAIN_<gain>_<YYYY-MM-DD-HH-MM-SS-mmm>
FOLDER_RE = re.compile(
    r"^DWARF_RAW_(?P<camera>TELE|WIDE)_(?P<target>.+)_EXP_(?P<exp>\d+(?:\.\d+)?)_GAIN_(?P<gain>\d+)_"
    r"(?P<ts>\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2})-\d{1,6}$",
    re.IGNORECASE,
)
# The capture starts after the program (goto, calibration, focus...)
_BEFORE_MIN, _AFTER_MIN = 2, 90


def _target_key(text: str) -> str:
    return re.sub(r"[^0-9a-z]", "", (text or "").lower())


def find_session_folder(astro_dir: str, camera: str, target: str, exposure, gain, start) -> str | None:
    """The capture folder of a program run on the Dwarf (user-asked Oct 2026:
    Astro Dwarf Session's Repair session opens the Repair here with both
    captures): same camera, target (letters and digits), exposure and gain,
    its time the first within _AFTER_MIN after the program's start
    (start: datetime, the Dwarf's local time). None when not found."""
    from datetime import datetime, timedelta
    try:
        exposure, gain = float(exposure), int(float(gain))
        names = os.listdir(astro_dir)
    except (TypeError, ValueError, OSError):
        return None
    best = None
    for name in names:
        m = FOLDER_RE.match(name)
        if not m or m["camera"].upper() != (camera or "TELE").upper():
            continue
        if _target_key(m["target"]) != _target_key(target):
            continue
        if abs(float(m["exp"]) - exposure) > 1e-6 or int(m["gain"]) != gain:
            continue
        when = datetime.strptime(m["ts"], "%Y-%m-%d-%H-%M-%S")
        if start - timedelta(minutes=_BEFORE_MIN) <= when <= start + timedelta(minutes=_AFTER_MIN):
            if best is None or when < best[0]:
                best = (when, name)
    return os.path.join(astro_dir, best[1]) if best else None

