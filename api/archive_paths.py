"""Where the results computed from a session are kept: at the root of its
archive - the backup drive's Astronomy folder (BackupDrive location +
astronomy_dir), at the same level as RESTACKED - rather than next to the
session folder (user-requested Oct 2026: two copies of a session in different
sub-folders of a backup then share the same results, and a result built from
several sessions has one place).

Used for _FIXED_FOREGROUND (api/foreground_fix.py), _PHOTOMETRY
(api/photometry_results.py; the Siril script gets the root in
siril_session.json's "astronomy_root") and _WCS_MOSAIC (components/wcs_mosaic.py)
- named with a leading _ so as not to meet a user's folder (user-requested),
and _WCS_MOSAIC rather than _MOSAIC_WCS: "_MOSAIC_" makes a mosaic session.
api/dwarf_backup_fct.py has none: get_basefolder_from_db_path() gives the
drive's location, get_effective_parent() a folder name only."""
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


# The results' folders at an archive's root
FIXED_FOREGROUND_DIR = "_FIXED_FOREGROUND"
PHOTOMETRY_DIR = "_PHOTOMETRY"
WCS_MOSAIC_DIR = "_WCS_MOSAIC"
# Their names before Oct 2026 (next to the sessions), renamed by migrate_results()
LEGACY_RESULT_DIRS = {"FIXED_FOREGROUND": FIXED_FOREGROUND_DIR, "PHOTOMETRY": PHOTOMETRY_DIR,
                      "MOSAIC_WCS": WCS_MOSAIC_DIR}
# Never sessions: left out of the analyses (api/dwarf_backup_fct.py's scans),
# session moves and transfers
RESULT_DIRS = (FIXED_FOREGROUND_DIR, PHOTOMETRY_DIR, WCS_MOSAIC_DIR, *LEGACY_RESULT_DIRS)


def _is_session(folder: Path) -> bool:
    """A session's folder, as the analysis sees it (api/dwarf_backup_fct.py's
    scan_backup_folder / check_dir_session): named DWARF_RAW_..., a mosaic's,
    or with a Dwarf's shotsInfo.json or stacked image in it. Above sessions
    any number of plain folders (Summer_sky/Galaxies/<sessions>)."""
    from api.dwarf_backup_fct import extract_astro_name_from_folder
    if "_MOSAIC_" in folder.name or extract_astro_name_from_folder(folder.name):
        return True
    try:
        for entry in os.scandir(folder):
            name = entry.name.lower()
            if entry.is_file() and (name == "shotsinfo.json" or (
                    "stacked" in name and name.endswith((".jpg", ".jpeg", ".png", ".fits", ".fit")))):
                return True
    except OSError:
        pass
    return False


def _merge_move(src: Path, dst: Path, log=None) -> int:
    """src moved to dst, merged into it when dst exists: a file already there
    with the same size is the same one (src's removed), a different one keeps
    src's under a _1, _2... name. Returns the number of files moved."""
    import shutil
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return sum(1 for _ in dst.rglob("*") if _.is_file()) if dst.is_dir() else 1
    if src.is_dir() and dst.is_dir():
        moved = sum(_merge_move(child, dst / child.name, log) for child in list(src.iterdir()))
        try:
            src.rmdir()
        except OSError:
            pass
        return moved
    if src.is_file() and dst.is_file() and src.stat().st_size == dst.stat().st_size:
        src.unlink()
        return 0
    n = 1
    while (dst.parent / f"{dst.stem}_{n}{dst.suffix}").exists():
        n += 1
    target = dst.parent / f"{dst.stem}_{n}{dst.suffix}"
    shutil.move(str(src), str(target))
    if log:
        log(f"  {dst.name} already at the root and different: kept as {target.name}")
    return 1


def migrate_results(root, log=None) -> int:
    """FIXED_FOREGROUND, PHOTOMETRY and MOSAIC_WCS folders found below `root`
    (where they were made next to the sessions before Oct 2026), or at it,
    moved to `root` under their new names (_FIXED_FOREGROUND, _PHOTOMETRY,
    _WCS_MOSAIC), merged with those already there (user-requested Oct 2026, run by
    the "Analyze all" page before each folder's analysis). Returns the number
    of files moved; log(text) is told each folder moved."""
    root = Path(root)
    if not root.is_dir():
        return 0
    found = []
    for dirpath, dirnames, _ in os.walk(root):
        here = Path(dirpath)
        for name in list(dirnames):
            if name in RESULT_DIRS:
                dirnames.remove(name)   # not walked into
                if here != root or name in LEGACY_RESULT_DIRS:
                    found.append(here / name)
        # A branch ends at its session (sessions hold no sub-level of
        # sessions, user-stated): the results were next to it, not inside
        dirnames[:] = [name for name in dirnames if not _is_session(here / name)]
    moved = 0
    for old in found:
        try:
            new_name = LEGACY_RESULT_DIRS.get(old.name, old.name)
            n = _merge_move(old, root / new_name, log)
        except OSError as e:
            if log:
                log(f"⚠️ {old}: not moved ({e})")
            continue
        moved += n
        if log:
            log(f"📁 {old.relative_to(root)} -> {new_name} ({n} file(s))")
    return moved + _photometry_by_star(root / PHOTOMETRY_DIR, log)


def _photometry_by_star(base: Path, log=None) -> int:
    """_PHOTOMETRY/<session>/ (the Siril script before Oct 2026) moved to
    _PHOTOMETRY/<star>/<session>/ (user-requested Oct 2026: a star's sessions
    side by side) - a session folder is one with a light_curve_<star>.csv in
    it. Each star's files (named after it) go to its folder, the others (the
    run's build_sessions.log) to every star's; a file already there is kept
    when it is the newer (the session measured again since). Returns the
    files moved."""
    import shutil
    if not base.is_dir():
        return 0
    moved = 0
    for old in sorted(d for d in base.iterdir() if d.is_dir()):
        stars = [p.stem[len("light_curve_"):] for p in old.glob("light_curve_*.csv")]
        if not stars:
            continue   # a star's folder already
        files = [p for p in old.iterdir() if p.is_file()]
        own = {star: [p for p in files if p.stem.endswith("_" + star)] for star in stars}
        shared = [p for p in files if not any(p in paths for paths in own.values())]
        try:
            for star in stars:
                target = base / star / old.name
                target.mkdir(parents=True, exist_ok=True)
                for path in shared + own[star]:
                    dst = target / path.name
                    if dst.exists() and dst.stat().st_mtime >= path.stat().st_mtime:
                        continue   # measured again since: the newer kept
                    shutil.copy2(path, dst)
                    moved += path not in shared
            shutil.rmtree(old)
        except OSError as e:
            if log:
                log(f"⚠️ {old}: not moved ({e})")
            continue
        if log:
            log(f"📁 {PHOTOMETRY_DIR}/{old.name} -> " + ", ".join(f"{PHOTOMETRY_DIR}/{s}/{old.name}" for s in stars))
    return moved
