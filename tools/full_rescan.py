"""Analyze everything (user-requested Oct 2026): every Dwarf's local copy
and every backup drive of the database, one after the other - what the
Dwarf and Backup pages' analyses do, for all of them.

The database then matches the files again after anything that changed
them outside this installation: another Scope Archive installation (an
executable and a source run sharing the same Dwarf_Local and drives,
each with its own database), a session folder moved by hand.

For a Dwarf it is its local copy (Dwarf_Local/DWARF_<id>) that counts:
nothing is read from the Dwarf itself, which needs not be connected.
"""
from __future__ import annotations

import os
import platform
import threading
from collections import deque
import subprocess
from dataclasses import dataclass
from datetime import datetime

from api.dwarf_backup_db_api import get_backupDrive_list, get_dwarf_Names
from api.dwarf_backup_fct import get_local_dwarf_dir, scan_backup_folder
from api.dwarf_backup_fct import print_log
from api.archive_paths import migrate_results

DWARF, BACKUP = "dwarf", "backup"


@dataclass
class Target:
    kind: str               # DWARF or BACKUP
    id: int
    name: str
    path: str               # the folder analyzed
    last_scan: str = ""
    dwarf_id: int | None = None
    location: str = ""      # BACKUP: the drive's location and astronomy dir
    astro_dir: str = ""

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.id}"

    @property
    def reachable(self) -> bool:
        return bool(self.path) and os.path.isdir(self.path)


def list_targets(conn) -> list[Target]:
    """The Dwarfs' local copies, then the backup drives."""
    targets = []
    cur = conn.cursor()
    for dwarf_id, name in get_dwarf_Names(conn):
        row = cur.execute("SELECT last_scan_date FROM Dwarf WHERE id = ?", (dwarf_id,)).fetchone()
        targets.append(Target(DWARF, dwarf_id, name, get_local_dwarf_dir(conn, dwarf_id),
                              str((row or [""])[0] or ""), dwarf_id=dwarf_id))
    for drive_id, name, _desc, location, astro_dir, dwarf_id, last_scan in get_backupDrive_list(conn):
        path = os.path.join(location, astro_dir) if location and astro_dir else (location or "")
        targets.append(Target(BACKUP, drive_id, name, path, str(last_scan or ""), dwarf_id=dwarf_id,
                              location=location or "", astro_dir=astro_dir or ""))
    return targets


def analyze(db_name: str, target: Target, log=None, progress_callback=None) -> tuple[int, int]:
    """Blocking. (sessions found, entries removed) - as the Dwarf / Backup
    pages' analyses."""
    # Results made next to the sessions before Oct 2026 moved to the root
    # first (user-requested: api/archive_paths.py's migrate_results)
    try:
        moved = migrate_results(target.path, log=lambda text: print_log(text, log))
        if moved:
            print_log(f"📁 {moved} result file(s) moved to {target.path}", log)
    except Exception as e:
        print_log(f"⚠️ results not moved: {e}", log)
    if target.kind == DWARF:
        result = scan_backup_folder(db_name, target.path, None, target.dwarf_id, None, None,
                                    log, progress_callback)
    else:
        result = scan_backup_folder(db_name, target.location, target.astro_dir, target.dwarf_id, target.id,
                                    None, log, progress_callback)
    total, deleted = (list(result) + [0, 0])[:2] if result else (0, 0)
    return int(total or 0), int(deleted or 0)


# ── log file ──────────────────────────────────────────────────────────────
LOG_DIR = "logs"
_KEEP_LOGS = 20


_SCREEN_BATCH = 50      # lines kept for the screen between two drains (all in the file)


class TeeLog:
    """What the analyses print: every line, with the time, in
    logs/analyze_all_<date>.log (the last _KEEP_LOGS kept); for the screen
    only a queue the page drains a few times a second (drain()).

    Pushing each line to the page from the analysis thread sent thousands of
    messages a minute to every browser open - the server fell behind with
    the browsers' pings and a phone kept losing its connection
    (user-reported)."""

    def __init__(self, ui_log=None):
        self.ui_log = ui_log        # kept for callers; the screen goes through drain()
        self._screen: deque = deque(maxlen=_SCREEN_BATCH)
        self._skipped = 0
        self._lock = threading.Lock()
        os.makedirs(LOG_DIR, exist_ok=True)
        self.path = os.path.abspath(os.path.join(LOG_DIR, f"analyze_all_{datetime.now():%Y%m%d-%H%M%S}.log"))
        self._file = open(self.path, "a", encoding="utf-8")
        _prune_logs()

    def push(self, message, *args, **kwargs):
        try:
            self._file.write(f"{datetime.now():%H:%M:%S}  {message}\n")
            self._file.flush()
        except (OSError, ValueError):
            pass
        with self._lock:
            if len(self._screen) == self._screen.maxlen:
                self._skipped += 1      # in the file only
            self._screen.append(str(message))

    def drain(self) -> tuple[list[str], int]:
        """(the lines for the screen since the last drain, the number left
        out of it - too many at once, they are in the file)."""
        with self._lock:
            lines, skipped = list(self._screen), self._skipped
            self._screen.clear()
            self._skipped = 0
        return lines, skipped

    def close(self):
        try:
            self._file.close()
        except OSError:
            pass


def _prune_logs():
    try:
        logs = sorted(f for f in os.listdir(LOG_DIR) if f.startswith("analyze_all_") and f.endswith(".log"))
        for old in logs[:-_KEEP_LOGS]:
            os.remove(os.path.join(LOG_DIR, old))
    except OSError:
        pass


def open_path(path: str) -> None:
    """The log file in the system's own application."""
    if platform.system() == "Windows":
        os.startfile(path)
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def show_in_folder(path: str) -> None:
    """The file's folder, the file selected - through explorer as the other
    pages open a folder (os.startfile on a folder didn't open it from the
    application's window, user-reported)."""
    path = os.path.normpath(path)
    if platform.system() == "Windows":
        subprocess.Popen(["explorer", "/select,", path])
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", "-R", path])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path)])
