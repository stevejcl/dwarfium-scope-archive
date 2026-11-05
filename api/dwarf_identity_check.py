"""Is the Dwarf connected the Dwarf chosen on the Dwarf page?

The type check (check_dwarf_type_mismatch) tells a Dwarf 3 from a Mini
from its images, but not two Dwarfs of the same model. Two more checks,
run before a scan:

- On the network (FTP): the Dwarf answering at the IP says its name
  (api/dwarf_identity.read_device_identity), whose last 6 hex digits must
  be the chosen Dwarf's identifier (Dwarf.ble_id) when it has one. Sure,
  and also catches an IP given by the router to another Dwarf.
- From the sessions (USB and FTP): a session folder name holds the date and
  time down to the millisecond, so it belongs to one device. When the
  sessions on the drive are already archived under another Dwarf
  (DwarfEntry.session_dir) and none under the chosen one, the drive is
  that other Dwarf's. Works between two Dwarfs of the same model, without
  network or identifier; says nothing for a new or emptied Dwarf.

Both return None when all is right or when they can't tell.
"""
from __future__ import annotations

import ftplib
import os
import posixpath
import sqlite3

from api.dwarf_backup_db_api import count_dwarf_entries_by_session, get_dwarf_name
from api.dwarf_identity import normalize_ble_id, read_device_identity

# Sessions of another Dwarf needed to say the drive is its own (one
# session could have been copied there by hand)
MIN_FOREIGN_SESSIONS = 2


def check_ip_identity(ble_id: str, ip: str) -> dict | None:
    """Blocking. {"expected": identifier, "found": Bluetooth name} when the
    Dwarf at ip is another one than the identifier says."""
    expected = normalize_ble_id(ble_id)
    if not expected or not ip:
        return None
    info = read_device_identity(ip)
    if not info or not info["ble_id"] or info["ble_id"] == expected:
        return None
    return {"expected": expected, "found": info["name"]}


def list_usb_sessions(scan_root: str) -> list[str]:
    """Names of the session folders at the drive's Astronomy root."""
    try:
        with os.scandir(scan_root) as entries:
            return [e.name for e in entries if e.is_dir()]
    except OSError:
        return []


def list_ftp_sessions(ftp, scan_root: str) -> list[str]:
    """Same over FTP (folders and files alike: only the names are compared)."""
    try:
        return [posixpath.basename(n.rstrip("/")) for n in ftp.nlst(scan_root)]
    except ftplib.all_errors:
        return []


def sessions_owner(conn: sqlite3.Connection, dwarf_id: int, session_names: list[str]) -> dict | None:
    """{"other_id", "other_name", "count", "total"} when the sessions on the
    drive are archived under another Dwarf and none under dwarf_id."""
    names = sorted({n for n in session_names if n})
    if not names or not dwarf_id:
        return None
    counts = count_dwarf_entries_by_session(conn, names)
    if counts is None:                                 # database error
        return None
    if counts.get(dwarf_id, 0):
        return None                                    # known sessions of the chosen Dwarf: it is
    others = [(c, d) for d, c in counts.items() if d != dwarf_id]
    if not others:
        return None                                    # nothing known: can't tell
    count, other_id = max(others)
    if count < min(MIN_FOREIGN_SESSIONS, len(names)):
        return None
    return {"other_id": other_id, "other_name": get_dwarf_name(conn, other_id) or f"#{other_id}",
            "count": count, "total": len(names)}
