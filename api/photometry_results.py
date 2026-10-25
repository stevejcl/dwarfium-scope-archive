"""Photometry results of a session (user-requested Oct 2026: the light curve
shown in Explore and kept with the archive).

The Dwarfium Archive Selector Siril script (extern/Dwarfium_archive_selector.py,
its "📈 Photometry" option) copies its results to PHOTOMETRY/<session folder>/
next to the sessions, as FIXED_FOREGROUND - the same convention as its
archive_photometry(): per target star,
  light_curve_<star>.csv / .png        its light curve
  stars_variability_<star>.csv / .png  the variability survey of the field
  comparison_stars_<star>.csv          the comparison stars (findcompstars)
plus the .ssf script and build_sessions.log of the run."""
from __future__ import annotations

import re
from pathlib import Path

OUTPUT_DIR = "PHOTOMETRY"


def results_dir(session_dir) -> Path:
    """PHOTOMETRY/<session folder>/ next to the session."""
    session_dir = Path(session_dir)
    name = re.sub(r"[^\w.-]+", "_", session_dir.name) or "session"
    return session_dir.parent / OUTPUT_DIR / name


def find_results(session_dir) -> list[dict]:
    """The stars measured in the session: [{"star", "curve_png", "curve_csv",
    "survey_png", "survey_csv"}] (paths, None when missing), sorted by star.
    [] when the session has no photometry."""
    if not session_dir:
        return []
    folder = results_dir(session_dir)
    if not folder.is_dir():
        return []
    results = []
    for csv_path in sorted(folder.glob("light_curve_*.csv")):
        star = csv_path.stem[len("light_curve_"):]

        def _file(name):
            path = folder / name
            return path if path.is_file() else None

        results.append({
            "star": star.replace("_", " "),
            "curve_csv": csv_path,
            "curve_png": _file(f"light_curve_{star}.png"),
            "survey_csv": _file(f"stars_variability_{star}.csv"),
            "survey_png": _file(f"stars_variability_{star}.png"),
        })
    return results
