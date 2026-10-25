"""Photometry results of a session (user-requested Oct 2026: the light curve
shown in Explore and kept with the archive).

The Dwarfium Archive Selector Siril script (extern/Dwarfium_archive_selector.py,
its "📈 Photometry" option) copies its results to
_PHOTOMETRY/<star>/<session folder>/ at the root of the archive, as
_FIXED_FOREGROUND (api/archive_paths.py: the backup's Astronomy folder, the
level of RESTACKED) - by star (user-requested Oct 2026: a star's sessions side
by side, to be put together) - the same convention as its
archive_photometry(): per target star,
  light_curve_<star>.csv / .png        its light curve
  stars_variability_<star>.csv / .png  the variability survey of the field
  comparison_stars_<star>.csv          the comparison stars (findcompstars)
plus the .ssf script and build_sessions.log of the run; and in
_PHOTOMETRY/<star>/ the star's sessions put together (combined_light_curve.csv
/ .png, combined_sessions.csv: the script's combine_star_sessions())."""
from __future__ import annotations

import re
from pathlib import Path

from api.archive_paths import PHOTOMETRY_DIR as OUTPUT_DIR


def safe_name(name: str) -> str:
    """A star's or a session's name as a folder / file name (the script's)."""
    return re.sub(r"[^\w.-]+", "_", name or "")


def session_folders(session_dir) -> list[Path]:
    """The folders holding the session's results: _PHOTOMETRY/<star>/<session>/
    at the archive's root, else where earlier versions put them
    (_PHOTOMETRY/<session>/, PHOTOMETRY/<session>/ next to the session) until
    Analyze all moves them."""
    from api.archive_paths import astronomy_root
    session_dir = Path(session_dir)
    name = safe_name(session_dir.name) or "session"
    base = astronomy_root(session_dir) / OUTPUT_DIR
    folders = sorted(d for d in base.glob(f"*/{name}") if d.is_dir()) if base.is_dir() else []
    for legacy in (base / name, session_dir.parent / "PHOTOMETRY" / name):
        if not folders and legacy.is_dir():
            folders = [legacy]
    return folders


def _combined_count(star_dir: Path) -> int:
    """How many sessions the star's combined curve has - from every drive
    (combined_sessions.csv), else those of this drive."""
    try:
        with open(star_dir / "combined_sessions.csv", encoding="utf-8") as f:
            return max(sum(1 for line in f if line.strip()) - 1, 1)
    except OSError:
        return sum(1 for d in star_dir.iterdir() if d.is_dir())


def find_results(session_dir) -> list[dict]:
    """The stars measured in the session: [{"star", "curve_png", "curve_csv",
    "survey_png", "survey_csv", "combined_png", "combined_csv", "sessions"}]
    (paths, None when missing; the last three: all the star's sessions put
    together, and how many it has), sorted by star.
    [] when the session has no photometry."""
    if not session_dir:
        return []
    results = []
    for folder in session_folders(session_dir):
        for csv_path in sorted(folder.glob("light_curve_*.csv")):
            star = csv_path.stem[len("light_curve_"):]

            def _file(name):
                path = folder / name
                return path if path.is_file() else None

            star_dir = folder.parent if folder.parent.name == star else None
            combined = (star_dir / "combined_light_curve.png") if star_dir else None
            results.append({
                "combined_png": combined if combined and combined.is_file() else None,
                "combined_csv": (star_dir / "combined_light_curve.csv") if combined and combined.is_file() else None,
                "sessions": _combined_count(star_dir) if star_dir else 1,
                "star": star.replace("_", " "),
                "curve_csv": csv_path,
                "curve_png": _file(f"light_curve_{star}.png"),
                "survey_csv": _file(f"stars_variability_{star}.csv"),
                "survey_png": _file(f"stars_variability_{star}.png"),
            })
    return sorted(results, key=lambda r: r["star"])
