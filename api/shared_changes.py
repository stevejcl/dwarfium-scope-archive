"""Several Scope Archive installations sharing the same folders (user-
requested Oct 2026): an executable and a source run, each with its own
database, working on the same Dwarf_Local and the same backup drive. A
transfer, an import or a delete done by one changes the files, but only
its own database: the other one is behind until its next analysis.

Each shared folder gets a small marker, .scope_archive_changes.json, at
its root - one line per installation: when it last changed files there.

    {"a1b2c3d4": {"at": "2026-10-16 21:12:05", "name": "Exe (DwarfiumScopeArchive)"},
     "e5f6a7b8": {"at": "2026-10-16 22:05:40", "name": "Python (dwarfium-scope-archive)"}}

An installation writes only its own line, and only when it changes files
(never on an analysis: no ping-pong between two of them). The Dwarf and
Backup pages warn when another installation's line is newer than this
installation's last full analysis of that folder - kept here, not the
database's scan date: that one only moves when an analysis finds
something, and also with a single session imported.

The roots: each Dwarf's local copy (Dwarf_Local/DWARF_<id>) and each
backup drive's folder (location + astronomy dir) - never the Dwarf's own
storage. The installation's identifier is kept in NiceGUI's general
storage, in the application's folder (not in the database: a database
copied to another installation would bring it along); copied with the
whole folder, it is renewed when the folder doesn't match.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import uuid
from datetime import datetime

MARKER = ".scope_archive_changes.json"
_STORAGE_KEY = "installation_id"
_SEEN_KEY = "shared_changes_seen"      # shared folder -> its last full analysis here


def _app_folder() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.abspath(os.getcwd())


def installation() -> tuple[str, str]:
    """(id, display name) of this installation, created the first time."""
    from nicegui import app
    folder = _app_folder()
    try:
        data = app.storage.general.get(_STORAGE_KEY) or {}
    except Exception:
        data = {}
    if not data.get("id") or os.path.normcase(data.get("folder", "")) != os.path.normcase(folder):
        kind = "Exe" if getattr(sys, "frozen", False) else "Python"
        data = {"id": uuid.uuid4().hex[:8], "folder": folder,
                "name": f"{kind} ({os.path.basename(folder) or folder})"}
        try:
            app.storage.general[_STORAGE_KEY] = data
        except Exception:
            pass
    return data["id"], data.get("name", data["id"])


def _norm(path: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def roots(conn) -> list[str]:
    """The shared folders of this database: each Dwarf's local copy and
    each backup drive's folder."""
    from api.dwarf_backup_fct import get_local_dwarf_dir
    out = []
    try:
        cur = conn.cursor()
        for (dwarf_id,) in cur.execute("SELECT id FROM Dwarf").fetchall():
            out.append(get_local_dwarf_dir(conn, dwarf_id))
        for location, astro_dir in cur.execute("SELECT location, astronomy_dir FROM BackupDrive").fetchall():
            if location:
                out.append(os.path.join(location, astro_dir) if astro_dir else location)
    except Exception as e:
        print(f"[SharedChanges] roots: {e}")
    return out


def root_of(conn, path: str) -> str | None:
    """The shared folder a path is in (the deepest one), None outside."""
    if not path:
        return None
    target = _norm(path)
    best = None
    for root in roots(conn):
        r = _norm(root)
        if target == r or target.startswith(r.rstrip(os.sep) + os.sep):
            if best is None or len(r) > len(_norm(best)):
                best = root
    return best


def _read(root: str) -> dict:
    try:
        with open(os.path.join(root, MARKER), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def mark_changed(conn, *paths: str) -> None:
    """After this installation changed files at these paths: its line of
    the marker of each shared folder concerned. Never raises."""
    try:
        uid, name = installation()
        stamp = now()
        for root in {r for r in (root_of(conn, p) for p in paths) if r}:
            if not os.path.isdir(root):
                continue
            data = _read(root)
            data[uid] = {"at": stamp, "name": name}
            fd, tmp = tempfile.mkstemp(dir=root, prefix=".scope_archive_changes.", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=1, ensure_ascii=False)
                os.replace(tmp, os.path.join(root, MARKER))
            except OSError:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
    except Exception as e:
        print(f"[SharedChanges] marker not written: {e}")


def now() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def mark_analyzed(root: str, started: str) -> None:
    """A full analysis of a shared folder, started at `started` (now()):
    the other installations' changes before it are in this database."""
    from nicegui import app
    if not root:
        return
    try:
        seen = dict(app.storage.general.get(_SEEN_KEY) or {})
        seen[_norm(root)] = started
        app.storage.general[_SEEN_KEY] = seen
    except Exception as e:
        print(f"[SharedChanges] analysis not recorded: {e}")


def _analyzed(root: str) -> str:
    from nicegui import app
    try:
        return str((app.storage.general.get(_SEEN_KEY) or {}).get(_norm(root)) or "")
    except Exception:
        return ""


def changes_by_others(root: str) -> list[dict]:
    """The other installations' changes in a shared folder newer than this
    installation's last full analysis of it. Newest first: [{"name", "at"}]."""
    if not root or not os.path.isdir(root):
        return []
    try:
        uid, _ = installation()
    except Exception:
        return []
    since = _analyzed(root)
    out = []
    for other, entry in _read(root).items():
        if other == uid or not isinstance(entry, dict):
            continue
        at = str(entry.get("at") or "")
        if at and (not since or at > since):
            out.append({"name": str(entry.get("name") or other), "at": at})
    return sorted(out, key=lambda e: e["at"], reverse=True)


def snapshot(root: str) -> frozenset:
    """The session folders of a shared folder (two levels: the sessions and
    those in Archive / RESTACKED / STARTRAILS), to tell whether a sync
    really changed something - an analysis that copies nothing must not
    mark the folder (the other installation would analyze, and so on)."""
    out = set()
    try:
        for entry in os.scandir(root):
            if entry.is_dir() and not entry.name.startswith("."):
                out.add(entry.name)
                try:
                    for sub in os.scandir(entry.path):
                        if sub.is_dir():
                            out.add(entry.name + "/" + sub.name)
                except OSError:
                    pass
    except OSError:
        pass
    return frozenset(out)


def mark_if_changed(conn, root: str, before: frozenset) -> None:
    if root and snapshot(root) != before:
        mark_changed(conn, root)
