"""A light curve as an AAVSO AID file (user-asked Oct 2026: send the Dwarfs'
photometry to the AAVSO) - its "AAVSO AID File Format" v2.0 (July 2025),
Extended version:

    #TYPE=EXTENDED  #OBSCODE=  #SOFTWARE=  #DELIM=,  #DATE=JD  #OBSTYPE=DSLR
    STARID,DATE,MAGNITUDE,MAGERR,FILTER,TRANS,MTYPE,CNAME,CMAG,KNAME,KMAG,AIRMASS,GROUP,CHART,NOTES

From the Siril script's light_curve_<star>.csv measured with the AAVSO
sequence (its "# aavso_chart:" line - CHART is required): the green channel
of a colour CMOS sensor - FILTER TG, OBSTYPE DSLR (colour CMOS, per the
spec) -, untransformed (TRANS NO), an ensemble of the chart's stars
(MTYPE STD: Vins - Cins + Cstd, CNAME ENSEMBLE, CMAG na), the check star by
its AUID with its computed magnitude, the time at mid-exposure as JD UTC
(the spec takes JD, not HJD). Cloudy and saturated images are left out."""
from __future__ import annotations

import csv
from pathlib import Path

FIELDS = ["STARID", "DATE", "MAGNITUDE", "MAGERR", "FILTER", "TRANS", "MTYPE", "CNAME", "CMAG",
          "KNAME", "KMAG", "AIRMASS", "GROUP", "CHART", "NOTES"]


def read_curve(csv_path) -> tuple[dict, list[dict]]:
    """({"# key": value} header lines, rows as dicts) of a light curve CSV."""
    meta, lines = {}, []
    with open(csv_path, encoding="utf-8", newline="") as f:
        for line in f:
            text = line.strip().strip('"')
            if text.startswith("#"):
                if ":" in text:
                    key, value = text[1:].split(":", 1)
                    meta[key.strip()] = value.strip()
                continue
            lines.append(line)
    return meta, list(csv.DictReader(lines))


def chart_of(csv_path) -> str:
    """The AAVSO chart the light curve was measured with, "" when none (not
    exportable)."""
    try:
        return read_curve(csv_path)[0].get("aavso_chart", "")
    except (OSError, csv.Error):
        return ""


def _field(value, limit: int) -> str:
    text = str(value).replace(",", " ").strip()
    return text[:limit] if text else "na"


def build(csv_path, obscode: str, starid: str, software: str) -> tuple[str, int, int]:
    """(the AID file's text, rows written, rows left out). Raises ValueError
    without an AAVSO chart or an observer code."""
    meta, rows = read_curve(csv_path)
    chart = meta.get("aavso_chart", "")
    if not chart:
        raise ValueError("measured without the AAVSO sequence: no chart")
    if not obscode.strip():
        raise ValueError("no AAVSO observer code")
    check = (meta.get("check_star") or "").split()
    kname = check[0] if check else ""
    check_cols = [c for c in (rows[0].keys() if rows else []) if c.startswith("check_") and c.endswith("_mag")]
    kcol = check_cols[0] if check_cols else None
    out = ["#TYPE=EXTENDED", f"#OBSCODE={obscode.strip().upper()}", f"#SOFTWARE={software[:255]}",
           "#DELIM=,", "#DATE=JD", "#OBSTYPE=DSLR",
           f"# {meta.get('session', '')} - {meta.get('instrument', '')} - site {meta.get('site', '')}".rstrip(" -"),
           "#" + ",".join(FIELDS)]
    written = skipped = 0
    for r in rows:
        if (r.get("cloudy") or "").strip() or (r.get("target_saturated") or "").strip():
            skipped += 1
            continue
        try:
            jd, mag, err = float(r["JD_UTC"]), float(r["mag"]), float(r["err"])
        except (KeyError, TypeError, ValueError):
            skipped += 1
            continue
        kmag = (r.get(kcol) or "").strip() if kcol else ""
        airmass = (r.get("airmass") or "").strip()
        notes = f"|NCOMP={r.get('n_comp', '')}|EXPTIME={meta.get('exposure_s', '')}|ENSEMBLE=AAVSO chart {chart}"
        out.append(",".join([
            _field(starid, 30), f"{jd:.6f}", f"{mag:.3f}", f"{err:.3f}", "TG", "NO", "STD", "ENSEMBLE", "na",
            _field(kname, 20) if kname and kmag else "na", f"{float(kmag):.3f}" if kmag and kname else "na",
            f"{float(airmass):.3f}" if airmass else "na", "na", _field(chart, 20), notes,
        ]))
        written += 1
    return "\n".join(out) + "\n", written, skipped


def write(csv_path, obscode: str, starid: str, software: str) -> tuple[Path, int, int]:
    """The AID file next to the light curve: aavso_<star>.txt. (path, rows
    written, rows left out)."""
    csv_path = Path(csv_path)
    text, written, skipped = build(csv_path, obscode, starid, software)
    name = csv_path.stem[len("light_curve_"):] if csv_path.stem.startswith("light_curve_") else csv_path.stem
    path = csv_path.with_name(f"aavso_{name}.txt")
    path.write_text(text, encoding="utf-8")
    return path, written, skipped
