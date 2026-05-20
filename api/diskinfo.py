"""
api/diskinfo.py
---------------
Persistent disk-space cache stored as  db/diskinfo.json  next to the SQLite
database.  Written every time get_disk_space_info() succeeds on a connected
drive; read back when the drive is offline so the UI can show the last-known
values rather than "—".

Schema of diskinfo.json:
{
  "backup": {
    "<backup_drive_id>": {
      "name":       "My Backup Drive",
      "location":   "D:\\Astro",
      "total_str":  "931.5 GB",
      "used_str":   "811.5 GB",
      "free_str":   "120.0 GB",
      "free_pct":   12.9,
      "total":      1000000000000,
      "used":       871000000000,
      "free":       129000000000,
      "updated_at": "2026-05-16T14:32:00"
    }
  },
  "dwarf": {
    "<dwarf_id>": { ... }
  }
}
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

_DISKINFO_PATH = Path("db") / "diskinfo.json"


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _load_raw() -> dict:
    try:
        if _DISKINFO_PATH.exists():
            with open(_DISKINFO_PATH, encoding="utf-8") as f:
                data = json.load(f)
            # Ensure both top-level keys exist
            data.setdefault("backup", {})
            data.setdefault("dwarf",  {})
            return data
    except Exception as e:
        print(f"[diskinfo] read error: {e}")
    return {"backup": {}, "dwarf": {}}


def _save_raw(data: dict) -> None:
    try:
        _DISKINFO_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_DISKINFO_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[diskinfo] write error: {e}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_disk_info(drive_type: str, drive_id: int | str, info: dict, name: str = "") -> None:
    """
    Persist disk space info for a drive.

    drive_type : "backup" or "dwarf"
    drive_id   : BackupDrive.id or Dwarf.id
    info       : dict returned by get_disk_space_info()
    name       : human-readable drive name (stored for display)
    """
    if not info.get("online"):
        return   # only persist when the drive is actually reachable

    data = _load_raw()
    key  = str(drive_id)
    data[drive_type][key] = {
        "name":       name,
        "location":   info.get("location", ""),
        "total_str":  info["total_str"],
        "used_str":   info["used_str"],
        "free_str":   info["free_str"],
        "free_pct":   info["free_pct"],
        "total":      info["total"],
        "used":       info["used"],
        "free":       info["free"],
        "warning":    info.get("warning", False),
        "critical":   info.get("critical", False),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    _save_raw(data)


def load_disk_info(drive_type: str, drive_id: int | str) -> dict | None:
    """
    Return the last-persisted disk info for a drive, or None if not found.
    The returned dict has the same keys as get_disk_space_info() plus
    ``updated_at`` and ``name``.
    """
    data = _load_raw()
    return data.get(drive_type, {}).get(str(drive_id))


def load_all_disk_info() -> dict:
    """Return the full diskinfo dict  {backup: {...}, dwarf: {...}}."""
    return _load_raw()
