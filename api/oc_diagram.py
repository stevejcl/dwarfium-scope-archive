"""A star's O-C diagram across its sessions (user-asked Oct 2026: DY Peg timed
three nights on two Dwarfs, about 2.7 min before VSX's prediction - "we gather
the different nights on one diagram").

Every extrema_<star>.csv the Siril script archived (_PHOTOMETRY/<star>/<session>/,
on every backup drive: one Dwarf, one drive) gives its times of maximum /
minimum (HJD). Their O-C are computed again against ONE set of elements - the
ones typed in Astro Dwarf Session for the star (its star_elements.json), else
those of the most recent session - since each session may have used other
ones. A straight line fitted through them (weighted by their errors) gives
corrected elements: its level the epoch's error, its slope the period's; with
the cycles of a single night or two close ones, only the level (the epoch)."""
from __future__ import annotations

import csv
import json
import math
import os
import re
from pathlib import Path

from api.archive_paths import PHOTOMETRY_DIR
from api.photometry_results import read_extrema

_ELEMENTS_RE = re.compile(r"P\s+([\d.]+)\s*d,\s*epoch\s+(?:HJD\s+)?([\d.]+)\s*\(([^)]*)\)")
# Below this cycle span the slope (the period) isn't fitted: the epoch only
_MIN_SPAN_CYCLES = 50


def _key(name: str) -> str:
    name = re.sub(r"^(V\*|\*\*?|NAME)\s+", "", (name or "").strip())
    return re.sub(r"[^0-9a-z]", "", name.lower())


def user_elements(star: str) -> dict | None:
    """{"epoch", "period"} typed in Astro Dwarf Session for the star, or None
    (same file as the Siril script's user_elements())."""
    folder = os.environ.get("ASTRO_DWARF_USER_DIR") or str(Path.home() / ".astro_dwarf_session")
    try:
        with open(os.path.join(folder, "star_elements.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    for entry in (data.values() if isinstance(data, dict) else []):
        if isinstance(entry, dict) and _key(entry.get("name")) == _key(star):
            try:
                return {"epoch": float(entry["epoch_hjd"]), "period": float(entry["period_d"])}
            except (KeyError, TypeError, ValueError):
                return None
    return None


def _file_elements(path: Path) -> dict | None:
    """{"epoch", "period", "source"} of an extrema file's "# elements:" line."""
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if "elements:" in line:
                    m = _ELEMENTS_RE.search(line)
                    if m:
                        return {"period": float(m[1]), "epoch": float(m[2]), "source": m[3]}
                if not line.lstrip('"').startswith("#"):
                    break
    except OSError:
        pass
    return None


def _instrument(session_folder: Path, star_file: str) -> str:
    """The session's instrument (its light curve's "# instrument:" line)."""
    try:
        with open(session_folder / f"light_curve_{star_file}.csv", encoding="utf-8") as f:
            for line in f:
                if not line.lstrip('"').startswith("#"):
                    break
                if "instrument:" in line:
                    return line.split("instrument:", 1)[1].strip().strip('"')
    except OSError:
        pass
    return ""


def collect(star: str, roots) -> tuple[list[dict], list[dict]]:
    """(the star's extrema of every session - {"hjd", "err_min", "type",
    "session", "instrument", "mag", "mtime"} -, the elements each file used)."""
    points, elements = [], []
    for root in dict.fromkeys(str(r) for r in roots if r):
        base = Path(root) / PHOTOMETRY_DIR
        try:
            star_dirs = [d for d in base.iterdir() if d.is_dir() and _key(d.name) == _key(star)]
        except OSError:
            continue
        for star_dir in star_dirs:
            for session in sorted(d for d in star_dir.iterdir() if d.is_dir()):
                for path in session.glob("extrema_*.csv"):
                    star_file = path.stem[len("extrema_"):]
                    used = _file_elements(path)
                    if used:
                        elements.append({**used, "mtime": path.stat().st_mtime})
                    for row in read_extrema(path):
                        try:
                            hjd = float(row["HJD_UTC"])
                        except (KeyError, TypeError, ValueError):
                            continue
                        try:
                            err = float(row.get("err_min") or 0)
                        except ValueError:
                            err = 0.0
                        points.append({"hjd": hjd, "err_min": err, "type": row.get("type") or "",
                                       "mag": row.get("mag") or "", "session": session.name,
                                       "instrument": _instrument(session, star_file),
                                       "mtime": path.stat().st_mtime})
    # The same extremum archived twice (two drives, a run done again): once
    unique = {}
    for p in sorted(points, key=lambda p: p["mtime"]):
        unique[round(p["hjd"], 4)] = p
    return sorted(unique.values(), key=lambda p: p["hjd"]), elements


def diagram(star: str, roots) -> dict | None:
    """The star's O-C diagram: {"elements": {"epoch", "period", "source"},
    "points": [{..., "cycle", "oc_min"}], "fit": {...} | None} - None when
    the star has no timed extremum or no elements."""
    points, used = collect(star, roots)
    if not points:
        return None
    own = user_elements(star)
    if own:
        elements = {**own, "source": "your elements"}
    elif used:
        latest = max(used, key=lambda e: e["mtime"])
        elements = {"epoch": latest["epoch"], "period": latest["period"], "source": latest["source"]}
    else:
        return None
    epoch, period = elements["epoch"], elements["period"]
    for p in points:
        offset = 0.5 if p["type"] == "II" else 0.0
        p["cycle"] = round((p["hjd"] - epoch) / period - offset) + offset
        p["oc_min"] = (p["hjd"] - (epoch + p["cycle"] * period)) * 1440.0
    return {"star": star, "elements": elements, "points": points, "fit": fit(points, epoch, period)}


def fit(points: list[dict], epoch: float, period: float) -> dict | None:
    """O-C = a + b x cycle, weighted (1 / error^2): corrected elements
    {"oc_mean", "oc_err", "slope", "slope_err", "epoch", "epoch_err", "period",
    "period_err", "span"} - the slope only over _MIN_SPAN_CYCLES cycles or
    more, else the mean O-C (the epoch). None without points."""
    if not points:
        return None
    w = [1.0 / max(p["err_min"], 0.05) ** 2 for p in points]
    x = [p["cycle"] for p in points]
    y = [p["oc_min"] for p in points]
    sw = sum(w)
    span = max(x) - min(x)
    mean = sum(wi * yi for wi, yi in zip(w, y)) / sw
    # Its error: the points' own, or their scatter when larger
    scatter = math.sqrt(sum(wi * (yi - mean) ** 2 for wi, yi in zip(w, y)) / sw) if len(y) > 1 else 0.0
    mean_err = max(1.0 / math.sqrt(sw), scatter / math.sqrt(len(y)) if len(y) > 1 else 0.0)
    # The corrected epoch at the latest extremum's cycle: a recent one, as
    # typed in Astro Dwarf Session
    n_last = max(x)
    result = {"oc_mean": mean, "oc_err": mean_err, "slope": None, "slope_err": None, "span": span,
              "epoch": epoch + n_last * period + mean / 1440.0, "epoch_err": mean_err / 1440.0,
              "epoch_cycle": n_last, "period": period, "period_err": None, "n": len(points)}
    if len(points) >= 3 and span >= _MIN_SPAN_CYCLES:
        # Around the points' mean cycle: the new epoch there, a and b uncorrelated
        xm = sum(wi * xi for wi, xi in zip(w, x)) / sw
        sxx = sum(wi * (xi - xm) ** 2 for wi, xi in zip(w, x))
        b = sum(wi * (xi - xm) * (yi - mean) for wi, xi, yi in zip(w, x, y)) / sxx
        b_err = 1.0 / math.sqrt(sxx)
        n0 = round(xm)
        a0 = mean + b * (n0 - xm)
        # The new epoch: the time of cycle n0, among the points
        result.update(slope=b, slope_err=b_err, period=period + b / 1440.0, period_err=b_err / 1440.0,
                      epoch=epoch + n0 * period + a0 / 1440.0, epoch_cycle=n0)
    return result


def plot(result: dict, png_path) -> bool:
    """The diagram as a PNG: O-C (min) per cycle with its error bars, one
    colour per instrument, the fitted line or mean level. False when not drawn."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    points, f = result["points"], result["fit"]
    fig, ax = plt.subplots(figsize=(9, 4.5), dpi=110)
    instruments = sorted({p["instrument"] or "?" for p in points})
    markers = {"max": "o", "I": "o", "II": "s"}
    for i, inst in enumerate(instruments):
        mine = [p for p in points if (p["instrument"] or "?") == inst]
        for kind in sorted({p["type"] for p in mine}):
            pts = [p for p in mine if p["type"] == kind]
            ax.errorbar([p["cycle"] for p in pts], [p["oc_min"] for p in pts], yerr=[p["err_min"] for p in pts],
                        fmt=markers.get(kind, "o"), color=f"C{i}", capsize=3,
                        label=f"{inst}" + (" (II)" if kind == "II" else ""))
    ax.axhline(0, color="grey", lw=0.8, ls=":")
    if f:
        xs = [p["cycle"] for p in points]
        lo, hi = min(xs), max(xs)
        pad = max((hi - lo) * 0.05, 1)
        if f["slope"] is not None:
            xm = f.get("epoch_cycle", (lo + hi) / 2)
            a0 = (f["epoch"] - (result["elements"]["epoch"] + xm * result["elements"]["period"])) * 1440.0
            xx = [lo - pad, hi + pad]
            ax.plot(xx, [a0 + f["slope"] * (v - xm) for v in xx], color="black", lw=1,
                    label=f"fit: {f['slope'] * 60:+.2f} s / cycle")
        else:
            ax.axhline(f["oc_mean"], color="black", lw=1, label=f"mean {f['oc_mean']:+.2f} min")
            ax.axhspan(f["oc_mean"] - f["oc_err"], f["oc_mean"] + f["oc_err"], color="black", alpha=0.08)
    el = result["elements"]
    ax.set_title(f"{result['star']} - O-C against P {el['period']:.7f} d, epoch {el['epoch']:.5f} ({el['source']})",
                 fontsize=9)
    ax.set_xlabel("cycle")
    ax.set_ylabel("O-C (min)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    try:
        fig.savefig(png_path)
        return True
    except OSError:
        return False
    finally:
        plt.close(fig)


def write_csv(result: dict, csv_path) -> None:
    """The points with their O-C, and the elements used, as a CSV."""
    el = result["elements"]
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([f"# {result['star']}: O-C against P {el['period']} d, epoch HJD {el['epoch']} ({el['source']})"])
        writer.writerow(["type", "HJD_UTC", "err_min", "cycle", "O_C_min", "mag", "instrument", "session"])
        for p in result["points"]:
            writer.writerow([p["type"], f"{p['hjd']:.6f}", f"{p['err_min']:.2f}", f"{p['cycle']:g}",
                             f"{p['oc_min']:+.2f}", p["mag"], p["instrument"], p["session"]])
