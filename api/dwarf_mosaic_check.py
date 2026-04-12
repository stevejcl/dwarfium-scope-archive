"""
dwarf_mosaic_check.py
---------------------
Validation functions before merging or repairing a Dwarf mosaic session.

Responsibilities:
  - Read and parse shotsInfo.json
  - Check geometric compatibility of two sessions (viewCols/viewRows, format)
  - Auto-detect whether session B is inverted relative to session A
  - Reorder panels if needed

No NiceGUI dependency: this module can be imported and tested independently.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from api.dwarf_backup_fct import win_long_path

import cv2
import numpy as np

# =========================================================
# STRUCTURES DE DONNEES
# =========================================================

@dataclass
class MosaicInfo:
    """
    Data extracted from the mosaicInfo field of shotsInfo.json.
    coords[i] = (col, row) of panel i+1 in the Dwarf grid.
    """
    viewCols:  int
    viewRows:  int
    panel_paths: list[str]          # chemins relatifs des panels (ordre JSON)
    coords:      list[tuple[int,int]]  # coord [col, row] de chaque panel
    subviewInfo: list[str]

@dataclass
class SessionInfo:
    """
    Session summary extracted from shotsInfo.json.
    Optional fields may be absent depending on firmware version.
    """
    path:          Path
    target:        str
    fmt:           str              # "FITS" ou "PNG"
    exp:           str
    gain:          int
    shots_stacked: int
    shots_taken:   int
    mosaic:        MosaicInfo
    ra:            Optional[float]  = None
    dec:           Optional[float]  = None
    ir:            Optional[str]    = None
    min_temp:      Optional[int]    = None
    max_temp:      Optional[int]    = None
    has_thumbnail: bool             = False  # stacked.jpg present


@dataclass
class CompatibilityResult:
    ok:      bool
    reason:  str                    # short message for UI
    details: list[str] = field(default_factory=list)  # technical details


@dataclass
class OrientationResult:
    inverted:       bool
    auto_detected:  bool            # True = result from detect_inversion()
    score_normal:   float           # correlation without flip
    score_flipped:  float           # correlation with 180° flip
    confidence:     float           # abs(score_flipped - score_normal)


# =========================================================
# READING OF shotsInfo.json
# =========================================================

def read_shots_info(session_path: str | Path) -> Optional[SessionInfo]:
    """
    Read and parse shotsInfo.json at the root of a mosaic session.

    Returns None if the file is missing or malformed.
    Missing fields are filled with default values.
    """
    path = Path(session_path)
    path_to_open = path / "shotsInfo.json"

    if not path_to_open.exists():
            
        # fallback Windows long path
        if os.name == "nt":
            path_to_open = Path(win_long_path(session_path))
            if not path_to_open.exists():
                return None
        else:
            return None

    try:
        with open(path_to_open, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    # ── mosaicInfo field (required) ──────────────────────────────────────────
    mosaic_data = data.get("mosaicInfo")
    if not mosaic_data:
        return None

    viewCols = mosaic_data.get("viewCols", 1)
    viewRows = mosaic_data.get("viewRows", 1)

    subviewInfo = mosaic_data.get("subviewInfo", [])
    # Sort by id to get canonical panel order 1, 2, 3...
    subviews_sorted = sorted(subviewInfo, key=lambda s: s.get("id", 0))
    panel_paths = [s.get("path", "") for s in subviews_sorted]
    coords      = [tuple(s.get("coord", [0, 0])) for s in subviews_sorted]

    mosaic = MosaicInfo(
        viewCols=viewCols,
        viewRows=viewRows,
        panel_paths=panel_paths,
        subviewInfo=subviewInfo,
        coords=coords,
    )

    # ── root fields ───────────────────────────────────────────────────────────
    target        = data.get("target", "UNKNOWN")
    fmt           = data.get("format", "FITS")
    exp           = str(data.get("exp", "?"))
    gain          = int(data.get("gain", 0))
    shots_stacked = int(data.get("shotsStacked", 0))
    shots_taken   = int(data.get("shotsTaken", 0))

    thumbnail_path = path / "stacked.jpg"

    return SessionInfo(
        path          = path,
        target        = target,
        fmt           = fmt,
        exp           = exp,
        gain          = gain,
        shots_stacked = shots_stacked,
        shots_taken   = shots_taken,
        mosaic        = mosaic,
        ra            = data.get("RA"),
        dec           = data.get("DEC"),
        ir            = data.get("ir"),
        min_temp      = data.get("minTemp"),
        max_temp      = data.get("maxTemp"),
        has_thumbnail = thumbnail_path.exists(),
    )


# =========================================================
# COMPATIBILITY
# =========================================================

def check_mosaic_json_compatibility(
    session_a: SessionInfo,
    session_b: SessionInfo,
) -> CompatibilityResult:
    """
    Check that two sessions can be merged.

    Criteria (in priority order):
      1. Same geometry: viewCols x viewRows
      2. Same image format: FITS or PNG
         (mixing FITS and PNG will be rejected by the Dwarf megastack)

    Note: the target field is NOT compared because:
      - the user may have aimed at an adjacent star
      - the field may be "UNKNOWN" if no star is at the centre
      - it is up to the user to confirm visually via the thumbnails
    """
    details = []
    errors  = []

    # Geometry
    cols_a, rows_a = session_a.mosaic.viewCols, session_a.mosaic.viewRows
    cols_b, rows_b = session_b.mosaic.viewCols, session_b.mosaic.viewRows

    if (cols_a, rows_a) == (cols_b, rows_b):
        details.append(f"Geometry OK : {cols_a}x{rows_a}")
    else:
        errors.append(
            f"Incompatible geometry : session A={cols_a}x{rows_a},"
            f" session B={cols_b}x{rows_b}"
        )

    # Format
    if session_a.fmt == session_b.fmt:
        details.append(f"Format OK : {session_a.fmt}")
    else:
        errors.append(
            f"Incompatible Format : session A={session_a.fmt},"
            f" session B={session_b.fmt}"
        )

    # Physical panel count (sub-folders found in the JSON)
    n_a = len(session_a.mosaic.panel_paths)
    n_b = len(session_b.mosaic.panel_paths)
    if n_a == n_b:
        details.append(f"Panels number OK: {n_a}")
    else:
        errors.append(f"Number of different panels: A={n_a}, B={n_b}")

    if errors:
        return CompatibilityResult(
            ok=False,
            reason=errors[0],   # Firstt UI error
            details=details + errors,
        )

    return CompatibilityResult(ok=True, reason="OK", details=details)


def format_session_summary(info: SessionInfo) -> str:
    """
    Return a human-readable summary for UI display (multi-line label).
    Compatible with the NiceGUI 'white-space: pre-line' style.
    """
    mosaic = info.mosaic
    layout = _layout_label(mosaic.viewCols, mosaic.viewRows)
    lines = [
        f"Cible    : {info.target}",
        f"Mosaique : {layout}  ({mosaic.viewCols}x{mosaic.viewRows})",
        f"Format   : {info.fmt}  |  Exp : {info.exp}s  |  Gain : {info.gain}",
        f"Images   : {info.shots_stacked} stackees / {info.shots_taken} prises",
    ]
    if info.ra is not None and info.dec is not None:
        lines.append(f"RA/DEC   : {info.ra:.4f} / {info.dec:.4f}")
    if info.ir:
        lines.append(f"Filtre   : {info.ir}")
    if info.min_temp is not None and info.max_temp is not None:
        lines.append(f"Temp     : {info.min_temp}°C – {info.max_temp}°C")
    return "\n".join(lines)


def _layout_label(cols: int, rows: int) -> str:
    if cols == 2 and rows == 1:
        return "horizontal 2 panels"
    if cols == 1 and rows == 2:
        return "vertical 2 panels"
    if cols == 2 and rows == 2:
        return "grille 4 panels"
    return f"{cols}x{rows} panels"


# =========================================================
# DETECTION D'INVERSION
# =========================================================

def detect_inversion(
    session_a: SessionInfo,
    session_b: SessionInfo,
) -> Optional[OrientationResult]:
    """
    Compare the stacked.jpg thumbnails of both sessions to detect
    whether session B is inverted (180° rotation) relative to session A.

    Method:
      - Resize both images to 512x512
      - Compute Pearson correlation: img_a vs img_b
      - Compute Pearson correlation: img_a vs flip(img_b, 180°)
      - If score_flipped > score_normal → inversion is likely

    Returns None if either session has no stacked.jpg.

    Confidence: abs(score_flipped - score_normal).
      > 0.05      : reliable detection
      0.01..0.05  : uncertain, let the user decide
      < 0.01      : no difference detected
    """
    thumb_a = session_a.path / "stacked.jpg"
    thumb_b = session_b.path / "stacked.jpg"

    if not thumb_a.exists() or not thumb_b.exists():
        return None

    img_a = cv2.imread(str(thumb_a))
    img_b = cv2.imread(str(thumb_b))

    if img_a is None or img_b is None:
        return None

    score_normal  = _correlation(img_a, img_b, flipped=False)
    score_flipped = _correlation(img_a, img_b, flipped=True)
    confidence    = abs(score_flipped - score_normal)
    inverted      = score_flipped > score_normal

    return OrientationResult(
        inverted      = inverted,
        auto_detected = True,
        score_normal  = score_normal,
        score_flipped = score_flipped,
        confidence    = confidence,
    )


def _correlation(img_a: np.ndarray, img_b: np.ndarray, flipped: bool) -> float:
    """Pearson correlation between two images resized to 512x512."""
    SIZE = 512
    g_a = cv2.cvtColor(img_a, cv2.COLOR_BGR2GRAY)
    g_b = cv2.cvtColor(img_b, cv2.COLOR_BGR2GRAY)
    g_a = cv2.resize(g_a, (SIZE, SIZE)).astype(np.float32)
    g_b = cv2.resize(g_b, (SIZE, SIZE)).astype(np.float32)
    if flipped:
        g_b = cv2.rotate(g_b, cv2.ROTATE_180)
    corr = np.corrcoef(g_a.flatten(), g_b.flatten())
    return float(corr[0, 1])


# =========================================================
# REORDONNANCEMENT DES PANELS
# =========================================================

def reorder_panels(
    panel_paths: list,
    inverted: bool,
) -> list:
    """
    Return the list of panel paths in the correct order for copying.

    Inversion logic by panel count:
      2 panels : [1,2] -> [2,1]
      4 panels : [1,2,3,4] -> [3,4,1,2]
      others   : reversed()

    Args:
        panel_paths : ordered list of paths (canonical JSON order, panel 1..N)
        inverted    : True if session B is inverted relative to session A

    Returns:
        list in the order to use when copying into session A panels
    """
    if not inverted:
        return list(panel_paths)

    n = len(panel_paths)
    if n == 2:
        return [panel_paths[1], panel_paths[0]]
    if n == 4:
        return [panel_paths[2], panel_paths[3],
                panel_paths[0], panel_paths[1]]
    return list(reversed(panel_paths))

# =========================================================
# CHECK MOSAIC ENTRY
# =========================================================

def get_mosaic_layout(config: dict):
    cols = config.get("viewCols")
    rows = config.get("viewRows")
    if cols == 2 and rows == 1:
        return cols, rows, "horizontal"
    if cols == 1 and rows == 2:
        return cols, rows, "vertical"
    if cols == 2 and rows == 2:
        return cols, rows, "grid"
    return cols, rows, "unknown"


def check_mosaic_compatibility(configA: dict, configB: dict):
    cA, rA, typeA = get_mosaic_layout(configA)
    cB, rB, typeB = get_mosaic_layout(configB)
    if (cA, rA) != (cB, rB):
        return False, "Different number of panels"
    if typeA != typeB:
        return False, "Different orientation (horizontal/vertical)"
    return True, "OK"


# =========================================================
# UI HELPERS
# =========================================================

def get_thumbnail_path(session_path: str | Path) -> Optional[Path]:
    """Return the thumbnail path if present, None otherwise."""
    print(session_path)
    p = Path(session_path) / "stacked.jpg"
    if p.exists():
        print(f"Path exists: {str(session_path)}")
        return p

    # fallback Windows long path
    if os.name == "nt":
        print(f"fallback Windows")
        p_long = Path(win_long_path(p))
        if p_long.exists():
            print(f"Path exists: {session_path}")
            return p  # ⚠️ on retourne le path normal !

    print(f"Path not exists: {session_path}")


def orientation_confidence_label(result: OrientationResult) -> str:
    """Return a human-readable confidence label for the UI."""
    c = result.confidence
    if c > 0.05:
        direction = "inverted" if result.inverted else "normal"
        return f"Reliable detection: {direction} orientation (confidence {c:.2f})"
    if c > 0.01:
        return f"Uncertain detection (confidence {c:.2f}) — check visually"
    return "No difference detected — check orientation visually"