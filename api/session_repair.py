"""Repair of a failed (non-mosaic) session on the Dwarf (user-asked Oct 2026,
from DwarfLab's procedure "How I Fixed My Failed Session with the Dwarf3").

A capture that ended badly (the Dwarf hung, an empty battery, a reboot)
keeps its images on the Dwarf, but its stacked FITS is missing (user's
Lion Nebula: no stacked-16_<...>.fits, no img_stacked_counter.png - its
stacked.jpg and stacked-16_<...>.png were there): the session is in neither
the Album nor the Megastack. DwarfLab's way: a short new session with the
same settings (2 images - Astro Dwarf Session's "Repair session"), its FITS
removed, the failed session's images and shotsInfo.json put in it, renamed
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
    if os.path.isfile(os.path.join(failed_dir, SHOTS_INFO)):
        plan["copy"].append((os.path.join(failed_dir, SHOTS_INFO), os.path.join(new_dir, SHOTS_INFO)))
    else:
        plan["warnings"].append("no shotsInfo.json in the failed session")
    return plan


def repair(failed_dir: str, new_dir: str, log=print, progress=None) -> dict:
    """Applies plan_repair(): the new session's own images removed, the failed
    session's copied in (the failed session left as it is), repairInfo.json
    written. Returns the plan with "copied" (count); raises on its error."""
    plan = plan_repair(failed_dir, new_dir)
    if plan["error"]:
        raise ValueError(plan["error"])
    for warning in plan["warnings"]:
        log(f"⚠️ {warning}")
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
