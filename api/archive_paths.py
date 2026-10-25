"""Where the results computed from a session are kept: at the root of its
archive - the backup drive's Astronomy folder (BackupDrive location +
astronomy_dir), at the same level as RESTACKED - rather than next to the
session folder (user-requested Oct 2026: two copies of a session in different
sub-folders of a backup then share the same results, and a result built from
several sessions has one place).

Used for FIXED_FOREGROUND (api/foreground_fix.py) and PHOTOMETRY
(api/photometry_results.py; the Siril script gets the root in
siril_session.json's "astronomy_root")."""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

# Folders of an Astronomy root that hold sessions one level down
_SESSION_GROUPS = {"RESTACKED", "STARTRAILS", "ARCHIVE"}

_cache = {"roots": [], "at": 0.0}
_lock = threading.Lock()
_CACHE_S = 60.0


def _backup_roots() -> list[str]:
    """The Astronomy roots of the backup drives in the database (location +
    astronomy_dir), longest first; kept 60 s."""
    with _lock:
        if time.time() - _cache["at"] < _CACHE_S:
            return _cache["roots"]
    roots = []
    try:
        from api.dwarf_backup_db import DB_NAME, connect_db, close_db
        conn = connect_db(DB_NAME)
        try:
            for location, astro_dir in conn.cursor().execute(
                    "SELECT location, astronomy_dir FROM BackupDrive WHERE location IS NOT NULL").fetchall():
                if location:
                    roots.append(os.path.normcase(os.path.normpath(os.path.join(location, astro_dir or ""))))
        finally:
            close_db(conn)
    except Exception:
        pass
    roots.sort(key=len, reverse=True)
    with _lock:
        _cache.update(roots=roots, at=time.time())
    return roots


def astronomy_root(session_dir) -> Path:
    """The root the session's results go to: the Astronomy folder of the
    backup drive holding it, else (a session on the Dwarf, a folder the
    database doesn't know) its parent folder - its grandparent when that is
    RESTACKED, STARTRAILS or Archive."""
    session_dir = Path(os.path.normpath(str(session_dir)))
    key = os.path.normcase(str(session_dir))
    for root in _backup_roots():
        if key.startswith(root + os.sep):
            return Path(str(session_dir)[:len(root)])
    parent = session_dir.parent
    if parent.name.upper() in _SESSION_GROUPS:
        parent = parent.parent
    return parent
