"""
(c) 2026, Stefan Schmidt-Bilkenroth
SPDX-License-Identifier: GPL-3.0-or-later

Dwarfum Session Selector
Version 1.0.0
"""

"""
ChangeLog:
    0.9.0   initial release, beta state for gathering feedback
    1.0.0   add Dwarfium Scope Archive scripts compatibility
    1.0.1   add photometry option (variable star light curve), by Dwarfium Scope Archive
"""

from genericpath import exists

import sirilpy as s
from sirilpy import LogColor

s.ensure_installed(["PyQt6"])

import csv
import json
import os
import re
import shlex
import shutil
import sys
import zipfile
from datetime import datetime, timedelta

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

APP_NAME = "Dwarfium Archive Selector"
VERSION = "0.9.1"
BUILD = "20260312"
AUTHOR = "Stefan Schmidt-Bilkenroth"

PRESET_FILE = "dwarfium-archive-select.json"
PRESET_JSON = """
{
    "archive_dir": null
}
"""

HELP_MD = """
## Help for Dwarfium Archive Selector

>This script is for convenience when preparing processing sessions shot
with smart telescopes made by Dwarf Lab. Its intention is, to ease preparation
of light images for stacking inside Siril.
The script assumes, that the Archive is organized the same way as on the
Dwwarf Lab devices. This can be achieved by either using tool like `rsync`
to archive the sessions or by using **Dwarfium Scope Archive**, which is my
recommendation. Thanks to JC. Lesaint for his tool.

### Step 1: Select the Folder containing your archived Dwarf session

>Click the button `Change` and use the File Selector Dialog to chose
the **Astronomy** folder containing all the Dwarf Sessions you have collected.
After choosing a folder, the path to the folder is shown in green color.
The folder is saved in the preferences of the script (in Siril preferences folder)
When the path to the Archive is shown in red color, the path is not available.
This can happen, when the Archive is located on an external drive and this one
is not connected, when the script is started.

>With the `Refresh` button you can trigger to scan the archive once again
in case you have added or removed sessions in the archive, after the script
was already started

>You can't change the Siril Home directory within this script, the path is
only shown for your information.

### Step 2: Select the Target in the left panel

>After choosing an Archive folder, the script will parse the file tree inside
the archive and gather information for all sessions found in the Archive.
The folder names inside the archive are parsed based on the naming pattern used
by Dwarf Lab when storing sessions onto their devices.
The script also inspects the `shotsinfo.json` file inside each session for
additional information (number of stacked images, filter selection, ...)

>All the targets, based on the Dwarf Lab naming schema, found in these sessions
are then displayed in the left panel. Ths number of session found for each target
is shown in parenthesis.

>It can happen, that some folder names with sessions do not match the naming
schema. These are ignored by the script but you can check the Siril Log for
more information.

>MegaStack sessions are ignored, as they do not contain indiviudal image, only
the result of the MegaStack processing. Check the Siril Log for more information.

### Step 3: Select the Sessions in the right panel

>After chosing a target in the left panel the right panel shows all sessions
on this target with session start date, number of stacked images, exposre time,
gain and filter.

>In the right pane you can chose one or more sessions. In the bottom the number
of selected images updates accordingly and is showing the total count of images
across the selected sessions.

### Step 4: Copy the lights from the selected sessions

>When you have at least selected one session with at least 1 image, the `Copy`
Button gets enabled. When you are happy with your selection, click on the
`Copy` button.

>The script will check if there are any images in the lights folder inside
the current Siril Home and if necessary ask for confirmation to delete them.
Also the `process` folder in Siril Home is deleted.

>Then it will start to copy all the images of the selected session from the
Archive into the new "lights" folder inside Siril home.
>This can take a while, but the progress of these file copy operation is
shown next to the `Copy` button.

### Step 5: Close the script window and continue your workflow

>After copying the files is completed you can close the script and
continue your workflow.

### ToDos:
- add safeguards around file operations
- move archive scan to background thread, be more responsive on slower systems
- proper handling of Mosaic sessions

### Caveats
>This script is provided as is and the Author takes now liability on its
functionality and any damage or loss of data when using the script.

### Legal Information:

**Author**: Stefan Schmidt-Bilkenroth

For suggestions, support and issues feel free to contact me:

>facebook: `https://www.facebook.com/stefan.ssb`

>mastodon: `https://gruene.social/@ssb`

>e-mail: `ssb@mac.com`

(c) 2026, Stefan Schmidt-Bilkenroth

SPDX-License-Identifier: GPL-3.0-or-later
"""

# ── photometry helpers ────────────────────────────────────────────────────
_FITS_BLOCK = 2880

# Older DWARF II firmware wrote no FOCALLEN / XPIXSZ in its tele FITS (2.2.18
# does: 100 mm, 1.45 um, Sep 2026): plate scale (arcsec/px at the
# FITS resolution) by image width, as Dwarfium Scope Archive's
# api/astrometry_resolver.py - 3840 px upscaled, 1920 px binned, 1928/1932 native
_D2_PLATE_SCALE_BY_WIDTH = {3840: 3.01, 1920: 6.02, 1928: 5.98, 1932: 5.98}
_D2_TELE_FOCAL_MM = 100.0


def read_fits_cards(path):
    """The primary header's cards of a FITS file: list of (offset, key,
    value, comment), value without quotes for strings. Reads the header
    blocks only, no image data (no astropy in Siril's Python)."""
    cards = []
    with open(path, "rb") as f:
        offset = 0
        while True:
            block = f.read(_FITS_BLOCK)
            if len(block) < _FITS_BLOCK:
                return cards
            for i in range(0, _FITS_BLOCK, 80):
                card = block[i:i + 80].decode("ascii", errors="replace")
                key = card[:8].strip()
                if key == "END":
                    return cards
                value, comment = "", ""
                if card[8:10] == "= ":
                    rest = card[10:]
                    if rest.lstrip().startswith("'"):
                        start = rest.index("'") + 1
                        end = rest.find("'", start)
                        while end != -1 and rest[end + 1:end + 2] == "'":  # '' escape
                            end = rest.find("'", end + 2)
                        value = rest[start:end].replace("''", "'").rstrip() if end != -1 else rest[start:]
                        comment = rest[end + 1:].partition("/")[2].strip() if end != -1 else ""
                    else:
                        value, _, comment = rest.partition("/")
                        value, comment = value.strip(), comment.strip()
                cards.append((offset + i, key, value, comment))
            offset += _FITS_BLOCK


def local_utc_offset_hours(date_obs):
    """This PC's UTC offset in hours at the wall-clock time date_obs (an ISO
    string), daylight saving time included; 0.0 when not readable."""
    try:
        local = datetime.fromisoformat(str(date_obs).strip().replace("Z", ""))
        return local.astimezone().utcoffset().total_seconds() / 3600.0
    except (ValueError, OverflowError, OSError, AttributeError):
        return 0.0


def fix_dwarf_date_obs(path):
    """The DWARF writes DATE-OBS as the END of the exposure (its comment says
    so), while Siril takes it as the start and adds half the exposure for the
    light curve's time: shift it back by EXPTIME, in place - only on the
    copies in Siril's lights/ folder. Returns True when changed (a file
    already fixed, or a DATE-OBS not marked as end of exposure, is kept)."""
    cards = read_fits_cards(path)
    by_key = {key: (offset, value, comment) for offset, key, value, comment in cards}
    if "DATE-OBS" not in by_key or "EXPTIME" not in by_key:
        return False
    offset, value, comment = by_key["DATE-OBS"]
    if "end of exposure" not in comment.lower():
        return False
    try:
        end = datetime.fromisoformat(value.strip().replace("Z", ""))
        start = end - timedelta(seconds=float(by_key["EXPTIME"][1]))
    except ValueError:
        return False
    card = f"DATE-OBS= '{start.isoformat(timespec='milliseconds')}' / Time start of exposure (end - EXPTIME)"
    with open(path, "r+b") as f:
        f.seek(offset)
        f.write(card.ljust(80)[:80].encode("ascii"))
    return True


# The DWARF's raw FITS are 16-bit files holding 12-bit data (saturated at 4095
# - a DWARF 3 sub, Oct 2026) while Siril's photometry takes a star as
# saturated above 60000 ADU by default: stars above this level, a bit under
# 4095 minus the dark level, are left out
_DWARF_12BIT_MAX = 4095
# Longest exposure a model allows, when shorter than what the star could take
# (user-reported Oct 2026: 15 s at most on a DWARF II)
_MAX_EXPOSURE_BY_TELESCOP = {"DWARFII": 15.0}
# Not linear well before 4095: on the user's HD 216964 session (Oct 2026) the
# target came out 0.04 mag fainter with its peak at 3300 - 3700 ADU than
# under 3000 (3700 before)
_DWARF_12BIT_PHOT_MAX = 3300


def fits_data_max(path):
    """Highest pixel value of a 2-D 16-bit FITS (BZERO applied), None when
    not readable (numpy missing, another format)."""
    try:
        import numpy as np
    except ImportError:
        return None
    cards = {key: value for _, key, value, _ in read_fits_cards(path)}
    try:
        if int(cards.get("BITPIX", 0)) != 16 or int(cards.get("NAXIS", 0)) != 2:
            return None
        width, height = int(cards["NAXIS1"]), int(cards["NAXIS2"])
        bzero = float(cards.get("BZERO", 0) or 0)
    except (KeyError, ValueError):
        return None
    with open(path, "rb") as f:
        header_blocks = 0
        while True:
            block = f.read(_FITS_BLOCK)
            if len(block) < _FITS_BLOCK:
                return None
            header_blocks += 1
            if any(block[i:i + 8] == b"END     " for i in range(0, _FITS_BLOCK, 80)):
                break
    data = np.fromfile(path, dtype=">i2", count=width * height, offset=header_blocks * _FITS_BLOCK)
    return float(data.max()) + bzero if data.size else None


_VSX_URL = "https://www.aavso.org/vsx/index.php"
_VSX_HEADERS = {"User-Agent": "Dwarfium-Archive-Selector (Siril script)", "Accept": "application/json"}


def _vsx_object(name, timeout):
    """VSX's "VSXObject" for the star ({} when unknown). requests when
    Siril's Python has it, else urllib with a User-Agent and certifi's
    certificates when there (user-reported Oct 2026: "Not found in VSX" from
    Siril while Astro Dwarf Session - requests - found DY Peg). Raises on a
    network / HTTP error."""
    import json as _json
    params = {"view": "api.object", "format": "json", "ident": name}
    try:
        import requests
    except ImportError:
        requests = None
    if requests is not None:
        response = requests.get(_VSX_URL, params=params, headers=_VSX_HEADERS, timeout=timeout)
        response.raise_for_status()
        payload = response.json() if response.content.strip() else {}
    else:
        import ssl
        import urllib.parse
        import urllib.request
        try:
            import certifi
            context = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            context = ssl.create_default_context()
        request = urllib.request.Request(_VSX_URL + "?" + urllib.parse.urlencode(params), headers=_VSX_HEADERS)
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            body = response.read().decode("utf-8", "replace").strip()
        payload = _json.loads(body) if body else {}
    return (payload.get("VSXObject") if isinstance(payload, dict) else None) or {}


def _header_center(cards):
    """(ra, dec) of the header's pointing in degrees, None when missing or
    0, 0 (a session without a target)."""
    try:
        ra, dec = float(cards.get("RA") or 0), float(cards.get("DEC") or 0)
    except (TypeError, ValueError):
        return None
    return None if ra == 0 and dec == 0 else (ra, dec)


def vsx_star(name, timeout=10, errors=None):
    """{"type", "max", "min", "amplitude"} of a variable star from AAVSO's VSX
    (user-requested Oct 2026: the exposure check's amplitude was an eclipse
    depth of 1 mag, DY Peg - a pulsating star - varies by about 0.6), None
    when not found or offline. "amplitude" in the same band as max/min, None
    when min is itself an amplitude ("(0.6)") or missing. errors: why it
    failed appended to it ("not in VSX", or the network error)."""
    try:
        obj = _vsx_object(name, timeout)
    except Exception as e:
        if errors is not None:
            errors.append(f"{type(e).__name__}: {e}"[:200])
        return None
    if not obj:
        if errors is not None:
            errors.append("not in VSX")
        return None

    def _mag(text):
        m = re.match(r"\s*([\d.]+)", str(text or ""))
        return float(m.group(1)) if m else None

    def _signed(text):
        m = re.match(r"\s*([+-]?[\d.]+)", str(text or ""))
        return float(m.group(1)) if m else None

    max_mag, min_text = _mag(obj.get("MaxMag")), str(obj.get("MinMag") or "")
    min_mag = None if min_text.strip().startswith("(") else _mag(min_text)
    amplitude = (min_mag - max_mag) if max_mag is not None and min_mag is not None else None
    if amplitude is None and min_text.strip().startswith("("):
        amplitude = _mag(min_text.strip()[1:])   # "(0.6)": given as an amplitude
    return {"type": obj.get("VariabilityType") or "", "max": max_mag, "min": min_mag,
            "amplitude": amplitude if amplitude and amplitude > 0 else None,
            "ra": _mag(obj.get("RA2000")), "dec": _signed(obj.get("Declination2000"))}


def moon_at(when_utc, ra, dec):
    """(illuminated fraction 0-1, separation from ra/dec in degrees) of the
    Moon at an astropy Time (geocentric: a degree off at most) - its light
    raises the sky background (user's DY Peg test at full Moon, Oct 2026)."""
    import math
    import warnings
    from astropy.coordinates import SkyCoord, get_body
    import astropy.units as u
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        moon = get_body("moon", when_utc)
        sun = get_body("sun", when_utc)
        elongation = sun.separation(moon).rad
        separation = moon.separation(SkyCoord(ra * u.deg, dec * u.deg)).deg
    return (1 - math.cos(elongation)) / 2, float(separation)


def measure_star(data, wcs, ra, dec, **kwargs):
    """(peak, background, S/N) of the star at ra/dec, None when not found -
    see _star_measure()."""
    m = _star_measure(data, wcs, ra, dec, **kwargs)
    return None if m is None else (m[0], m[1], m[2] / m[3] if m[3] > 0 else 0.0)


def _star_measure(data, wcs, ra, dec, search_r=3, peak_r=3, aperture_r=4, annulus=(12, 20)):
    """(peak, background, flux, noise) in ADU of the star at ra/dec in a plate solved
    image (numpy array + astropy WCS), None when out of the field or not
    detected (peak under 5 sigma of the background, or a lone hot pixel). Measured here rather than
    through Siril's selection functions, whose pixel coordinates didn't match
    radec2pix's on a real test (Oct 2026). The star is the brightest pixel
    within search_r of its computed position - Siril's solution (SIP) put the
    stars of a real frame within 0.5 px, a wider search took a fainter
    comparison star's neighbour 9 px away instead; peak:
    the brightest pixel within peak_r of it (a fitted Gaussian is a third
    lower on these sharp stars); S/N of an aperture_r aperture, background
    from the annulus, a gain of 1 e-/ADU assumed for the star's own noise
    (an estimate)."""
    import numpy as np
    height, width = data.shape
    x, y = wcs.world_to_pixel_values(ra, dec)
    x, y = float(x), float(y)
    if not (0 <= x < width and 0 <= y < height):
        return None

    def _cut(cx, cy, r):
        x0, x1 = max(0, int(round(cx)) - r), min(width, int(round(cx)) + r + 1)
        y0, y1 = max(0, int(round(cy)) - r), min(height, int(round(cy)) + r + 1)
        return data[y0:y1, x0:x1], x0, y0

    box, x0, y0 = _cut(x, y, search_r)
    if box.size < 9:
        return None
    # Brightest 3x3 mean, so a hot pixel alone is not taken for the star
    padded = np.pad(box, 1, mode="edge")
    smooth = sum(padded[dy:dy + box.shape[0], dx:dx + box.shape[1]] for dy in range(3) for dx in range(3)) / 9.0
    iy, ix = np.unravel_index(np.argmax(smooth), smooth.shape)
    cx, cy = x0 + ix, y0 + iy

    r_out = annulus[1]
    cut, x0, y0 = _cut(cx, cy, r_out)
    gy, gx = np.mgrid[y0:y0 + cut.shape[0], x0:x0 + cut.shape[1]]
    dist = np.hypot(gx - cx, gy - cy)
    ring = cut[(dist >= annulus[0]) & (dist <= annulus[1])]
    if ring.size < 20:
        return None
    background = float(np.median(ring))
    sigma = float(1.4826 * np.median(np.abs(ring - background)))
    peak = float(cut[dist <= peak_r].max())
    # A star: several pixels well above the background, not a lone hot pixel
    if sigma <= 0 or peak - background < 5 * sigma or (cut[dist <= 1.5] > background + 3 * sigma).sum() < 3:
        return None
    aperture = cut[dist <= aperture_r]
    flux = float((aperture - background).sum())
    noise = (aperture.size * sigma ** 2 + max(flux, 0.0)) ** 0.5
    return peak, background, flux, noise


def simbad_name(name):
    """A star's name without SIMBAD's prefix ("V* DY Peg" -> "DY Peg", "* bet
    Per", "NAME Algol"): findcompstars writes SIMBAD's main identifier, so the
    same star was archived as V_DY_Peg here and DY_Peg there (user's DY Peg
    test, Oct 2026) - its sessions no longer put together."""
    return re.sub(r"^(V\*|\*\*?|NAME)\s+", "", (name or "").strip())


def read_compstars_csv(path):
    """The stars of a findcompstars CSV: list of dict (type, name, ra, dec,
    mag), the target first, its name without SIMBAD's prefix (simbad_name)."""
    stars = []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(line for line in f if line.strip() and not line.startswith("#")):
            row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
            try:
                stars.append({"type": row.get("type", ""), "name": simbad_name(row.get("name", "")),
                              "ra": float(row["ra"]), "dec": float(row["dec"]),
                              "mag": float(row["mag"]) if row.get("mag") else None})
            except (KeyError, ValueError):
                continue
    return sorted(stars, key=lambda st: st["type"].lower() != "target")


def _airmass(coord, when, observer):
    """The star's airmass at `when` from `observer` (Pickering 2002, good
    down to the horizon); None without a site, or below the horizon."""
    if observer is None:
        return None
    try:
        import math
        import warnings
        from astropy.coordinates import AltAz
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")   # UT1 from the bundled IERS values: arcseconds
            alt = float(coord.transform_to(AltAz(obstime=when, location=observer)).alt.deg)
    except Exception:
        return None
    if alt <= 0:
        return None
    return 1.0 / math.sin(math.radians(alt + 244.0 / (165.0 + 47.0 * alt ** 1.1)))


def differential_light_curve(files, stars, out_csv, aperture_r=5, saturation=None, utc_offset_h=0.0, progress=None,
                             site=None, session_name="", keep_saturated=False):
    """Differential photometry of the target over plate solved images (user-
    requested Oct 2026, instead of Siril's light_curve: in 1.4.0 - 1.4.2 its
    -autoring loses the reference's plate solve, its default min_val rejects
    dark-subtracted stars, a setphot without -dyn_ratio fixes its aperture,
    and its reference frame must match the others' orientation - one real
    test after another). Each image measured with its own plate solve, so no
    registration: the target and comparison stars at their coordinates
    (_star_measure), a zero point per image from the comparison stars
    (catalogue V - instrumental magnitude, weighted mean after a 3-sigma
    clip; the same comparison stars in every image when enough of them are
    measured in 90 % of the images), the target's magnitude and its error.
    Time: the middle of the
    exposure (DATE-OBS is its start once fix_dwarf_date_obs() ran), as JD
    UTC, HJD UTC and BJD TDB. utc_offset_h: DATE-OBS's UTC offset - the DWARF
    writes its local time there (user-checked Oct 2026: the last frame of a
    session at 04:10 by DATE-OBS, the next session started at 04:22 French
    summer time on the same DWARF 3). Writes out_csv; returns the summary
    lines. progress(done, total): called after each image (user-reported
    Oct 2026: Siril stopped on a 141-image session, nothing in its log while
    the measurement ran).
    site: (latitude, longitude[, name]) of the observation (the DWARF's FITS
    has none: the session's location in the archive) - each point's airmass;
    session_name, the instrument (first image's header) and the site in the
    CSV's header lines (user-requested Oct 2026: several sessions of a star
    put together later)."""
    import math
    import warnings
    import numpy as np
    from astropy.io import fits as _fits
    from astropy.wcs import WCS
    from astropy.time import Time
    from astropy.coordinates import SkyCoord, EarthLocation
    import astropy.units as u
    from astropy.utils import iers
    # No IERS download, and its bundled values accepted however old (user-
    # reported Oct 2026: "interpolating from IERS_Auto using predictive values
    # that are more than 30.0 days old" stopped the photometry). The times are
    # computed at the geocentre: the Earth's rotation (UT1) plays no part,
    # the light time and UTC -> TDB don't need these tables.
    iers.conf.auto_download = False
    iers.conf.auto_max_age = None
    iers.conf.iers_degraded_accuracy = "ignore"

    target, comps = stars[0], [st for st in stars[1:] if st["mag"] is not None]
    coord = SkyCoord(target["ra"] * u.deg, target["dec"] * u.deg)
    geocentre = EarthLocation.from_geocentric(0, 0, 0, unit=u.m)
    observer = None
    if site and site[0] is not None and site[1] is not None:
        observer = EarthLocation(lat=float(site[0]) * u.deg, lon=float(site[1]) * u.deg, height=0 * u.m)
    instrument = {}
    blended = None   # comparison stars with another star in their aperture (first image)
    # The target's place in each image (user's two DWARF 3 at once, Oct 2026: 0.04 mag
    # apart on one of them only - a dust shadow, no flat?): x, y in the CSV
    positions = {}
    rows, skipped, frames, frame_info = [], [], [], []
    for index, path in enumerate(files, 1):
        if progress is not None:
            progress(index - 1, len(files))
        name = os.path.basename(path)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                with _fits.open(path) as hdul:
                    header = hdul[0].header
                    data = hdul[0].data.astype("float32")   # half the memory of float64
                    wcs = WCS(header)
            if data.ndim == 3:
                data = data[0]
            if data.max() <= 1.5:   # 32-bit float image: 0..1
                data = data * 65535.0
            if not wcs.has_celestial:
                skipped.append(f"{name}: no plate solve")
                continue
            start = (Time(str(header["DATE-OBS"]).replace("Z", ""), format="isot", scale="utc")
                     - (utc_offset_h or 0.0) * u.hour)
            mid = start + float(header.get("EXPTIME", 0) or 0) / 2 * u.s
            if not instrument:
                instrument = {key: str(header.get(key, "")).strip()
                              for key in ("TELESCOP", "CAMERA", "FILTER", "EXPTIME", "GAIN")}
        except Exception as e:
            skipped.append(f"{name}: {e}")
            continue

        if blended is None:
            # Left out: a comparison star with another catalogue star (or the
            # target) within twice the aperture - both in its aperture, it is
            # measured too bright (user's HD 216964 test, Oct 2026: comparisons
            # 1 and 2, V 12.20, 4 px apart, each measured 0.7 mag brighter)
            xy = np.array([wcs.world_to_pixel_values(st["ra"], st["dec"]) for st in [target] + comps], dtype=float)
            blended = set()
            for i in range(len(comps)):
                others = np.delete(xy, i + 1, axis=0)
                if (np.hypot(*(others - xy[i + 1]).T) < 2 * aperture_r).any():
                    blended.add(i)
            if blended:
                skipped.append(f"comparison star(s) {', '.join(comps[i]['name'] for i in sorted(blended))}: "
                               f"another star within {2 * aperture_r} px, left out")
        t = _star_measure(data, wcs, target["ra"], target["dec"], aperture_r=aperture_r)
        positions[name] = tuple(float(v) for v in wcs.world_to_pixel_values(target["ra"], target["dec"]))
        if t is None or t[2] <= 0:
            skipped.append(f"{name}: target not measured")
            continue
        if saturation and t[0] >= saturation and not keep_saturated:
            skipped.append(f"{name}: target saturated (peak {t[0]:.0f})")
            continue
        # keep_saturated (user-asked Oct 2026: DY Peg at gain 110, saturated at its
        # maximum, compared with another software's curve that kept it): measured,
        # flagged - the comparison stars still left out above the level
        measured = {}
        for i, st in enumerate(comps):
            if i in blended:
                continue
            m = _star_measure(data, wcs, st["ra"], st["dec"], aperture_r=aperture_r)
            if m is not None and m[2] > 0 and not (saturation and m[0] >= saturation):
                measured[i] = m
        frames.append((name, mid, t, measured))
        del data
    if progress is not None:
        progress(len(files), len(files))

    # The same comparison stars in every image (user-reported Oct 2026: 19 to
    # 23 of them from one image to the next made the zero point jump): those
    # measured in at least 90 % of the images, else each image's own
    counts = [sum(1 for _, _, _, measured in frames if i in measured) for i in range(len(comps))]
    fixed = {i for i, n in enumerate(counts) if frames and n >= 0.9 * len(frames)}
    if len(fixed) < 3:
        fixed = None
    # Check star (as HD 218587 in V. Lecomte's DY Peg procedure, Oct 2026):
    # the comparison star closest to the target's magnitude among the most
    # measured ones, measured like the target and left out of the zero point -
    # flat, it shows the target's changes are real
    target_mag = target.get("mag")
    candidates = [i for i in (fixed or range(len(comps))) if counts[i] >= 0.9 * max(counts or [0]) and counts[i]]
    check = None
    if len(candidates) >= 4:
        check = min(candidates, key=lambda i: abs(comps[i]["mag"] - (target_mag if target_mag is not None else comps[i]["mag"])))

    for name, mid, t, measured in frames:
        used = {i: m for i, m in measured.items() if (fixed is None or i in fixed) and i != check}
        if len(used) < 2:
            skipped.append(f"{name}: fewer than 2 comparison stars measured")
            continue
        ids = list(used)
        zps = np.array([comps[i]["mag"] + 2.5 * math.log10(m[2]) for i, m in used.items()])
        weights = np.array([1.0 / max((1.0857 * m[3] / m[2]) ** 2, 1e-6) for m in used.values()])
        keep = np.abs(zps - np.median(zps)) <= 3 * max(np.std(zps), 1e-3)
        zps, weights = zps[keep], weights[keep]
        zp = float(np.average(zps, weights=weights))
        # Field survey: the zero point's terms kept, for each star's own
        # magnitude from the others (field_variability())
        zp_terms = {i: (z, w) for i, z, w in zip([i for i, k in zip(ids, keep) if k], zps, weights)}
        frame_info.append((mid, measured, zp_terms, float(weights.sum()), float((zps * weights).sum())))
        zp_err = float(np.std(zps) / math.sqrt(len(zps)))
        mag = -2.5 * math.log10(t[2]) + zp
        err = math.hypot(1.0857 * t[3] / t[2], zp_err)
        check_mag = check_err = None
        if check is not None and check in measured:
            cm = measured[check]
            check_mag = -2.5 * math.log10(cm[2]) + zp
            check_err = math.hypot(1.0857 * cm[3] / cm[2], zp_err)
        try:
            hjd = (mid + mid.light_travel_time(coord, "heliocentric", location=geocentre)).utc.jd
            bjd = (mid.tdb + mid.light_travel_time(coord, "barycentric", location=geocentre)).jd
        except Exception as e:   # astropy's time tables: the magnitudes are kept
            hjd = bjd = None
            if not any(line.startswith("HJD / BJD not computed") for line in skipped):
                skipped.append(f"HJD / BJD not computed: {str(e).splitlines()[0]}")
        rows.append((name, mid.utc.jd, hjd, bjd, mag, err, len(zps), t[0], check_mag, check_err,
                     _airmass(coord, mid, observer), positions.get(name),
                     bool(saturation and t[0] >= saturation)))
    rows.sort(key=lambda r: r[1])

    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([f"# {target['name']}: differential photometry, green channel (TG), "
                         f"{len(comps)} comparison stars (findcompstars), times at mid-exposure in UTC "
                         f"(DATE-OBS taken as UTC{utc_offset_h:+g} h)"])
        # One "# key: value" line each, for the sessions put together later
        meta = [("session", session_name),
                ("instrument", " ".join(v for v in (instrument.get("TELESCOP"), instrument.get("CAMERA")) if v)),
                ("filter", instrument.get("FILTER", "")),
                ("exposure_s", instrument.get("EXPTIME", "")), ("gain", instrument.get("GAIN", "")),
                ("site", "" if observer is None else
                 f"{float(site[0]):.5f} {float(site[1]):.5f}" + (f" {site[2]}" if len(site) > 2 and site[2] else "")),
                ("target", f"{target['name']} {target['ra']:.6f} {target['dec']:.6f}"),
                ("check_star", "" if check is None else
                 f"{comps[check]['name']} {comps[check]['ra']:.6f} {comps[check]['dec']:.6f} V {comps[check]['mag']}")]
        for key, value in meta:
            if value:
                writer.writerow([f"# {key}: {value}"])
        check_label = f"check_{comps[check]['name']}" if check is not None else "check"
        writer.writerow(["file", "JD_UTC", "HJD_UTC", "BJD_TDB", "mag", "err", "n_comp", "peak",
                         f"{check_label}_mag", f"{check_label}_err", "airmass", "x", "y", "target_saturated"])
        for name, jd, hjd, bjd, mag, err, n, peak, cmag, cerr, airmass, xy, sat in rows:
            writer.writerow([name, f"{jd:.6f}", "" if hjd is None else f"{hjd:.6f}", "" if bjd is None else f"{bjd:.6f}",
                             f"{mag:.4f}", f"{err:.4f}", n, f"{peak:.0f}",
                             "" if cmag is None else f"{cmag:.4f}", "" if cerr is None else f"{cerr:.4f}",
                             "" if airmass is None else f"{airmass:.3f}",
                             "" if xy is None else f"{xy[0]:.1f}", "" if xy is None else f"{xy[1]:.1f}",
                             "yes" if sat else ""])

    summary = [f"Light curve of {target['name']}: {len(rows)} of {len(files)} images measured -> {out_csv}",
               f"  DATE-OBS taken as UTC{utc_offset_h:+g} h (the DWARF's local time)"]
    if rows:
        unsaturated = [r for r in rows if not r[12]] or rows
        mags = np.array([r[4] for r in unsaturated])
        summary.append(f"  mag {mags.mean():.3f} (std {mags.std():.3f}, median error {np.median([r[5] for r in rows]):.3f}), "
                       f"{int(np.median([r[6] for r in rows]))} comparison stars per image"
                       + (f" (the same {len(fixed)} in every image)" if fixed else ""))
    if rows and check is not None:
        cmags = np.array([r[8] for r in rows if r[8] is not None])
        if cmags.size:
            summary.append(f"  check star (comparison {comps[check]['name']}, V {comps[check]['mag']:.2f}): "
                           f"std {cmags.std():.3f}")
    try:
        summary += field_variability(comps, frame_info, os.path.dirname(out_csv) or ".", target)
    except Exception as e:
        summary.append(f"  field survey not done: {e}")
    if rows:
        png = os.path.splitext(out_csv)[0] + ".png"
        try:
            plot_light_curve(rows, png, target["name"],
                             f"check: comparison {comps[check]['name']} (V {comps[check]['mag']:.2f})" if check is not None else None,
                             target_v=target.get("mag"), check_v=comps[check]["mag"] if check is not None else None)
            summary.append(f"  plot -> {png}")
        except Exception as e:
            summary.append(f"  plot not drawn: {e}")
    saturated = sum(1 for line in skipped if ": target saturated" in line) + sum(1 for r in rows if r[12])
    if keep_saturated and any(r[12] for r in rows):
        summary.append(f"  {sum(1 for r in rows if r[12])} saturated image(s) kept on request, flagged "
                       "(target_saturated): measured too faint, out of the mean")
    if files and saturated >= 0.3 * len(files):
        summary.append(f"  WARNING: the target saturated in {saturated} of {len(files)} images - its brightest phases "
                       + ("measured too faint (kept, flagged)" if keep_saturated else "left out")
                       + ": a lower gain or a shorter exposure next time (Check exposure)")
    summary += _skipped_summary(skipped)
    return summary


def _skipped_summary(skipped, examples=3):
    """The images left out, by reason: one line each with a few examples
    (user's 509-image DY Peg run, Oct 2026: 425 "target saturated" lines
    buried the summary) - a saturated target's peaks as their range."""
    import re as _re
    lines, groups = [], {}
    for line in skipped:
        if line.startswith("HJD") or ": " not in line:
            lines.append(f"  {line}")
            continue
        if line.startswith("comparison star"):   # not an image
            lines.append(f"  skipped {line}")
            continue
        name, reason = line.split(": ", 1)
        peak = _re.match(r"target saturated \(peak (\d+)\)", reason)
        key = "target saturated" if peak else reason
        group = groups.setdefault(key, {"names": [], "peaks": []})
        group["names"].append(name)
        if peak:
            group["peaks"].append(int(peak.group(1)))
    for reason, group in groups.items():
        names = group["names"]
        text = f"  skipped {len(names)} image(s): {reason}"
        if group["peaks"]:
            text += f" (peak {min(group['peaks'])} - {max(group['peaks'])})"
        text += " - " + ", ".join(names[:examples]) + (f"... (+{len(names) - examples})" if len(names) > examples else "")
        lines.append(text)
    return lines


def field_variability(comps, frame_info, folder, target, min_frames=10, flag_ratio=2.0, flag_chi2=2.0):
    """Variability survey of the field (user-requested Oct 2026: the stars
    found in a session measured too): each comparison star's magnitude in
    each image from the zero point of the others (leave-one-out), then its
    scatter against that of the stars of similar brightness (median within
    0.5 mag): a ratio of flag_ratio or more, and a scatter flag_chi2 times
    its own errors (chi2) - a faint star's noise alone isn't one -, makes it a
    candidate variable.
    Known variables are not in findcompstars' list, the candidates are
    uncatalogued ones (or a bad comparison star). Writes stars_variability.csv
    and .png in folder; returns the summary lines."""
    import math
    import numpy as np
    series = {}
    for mid, measured, zp_terms, w_sum, wz_sum in frame_info:
        for i, m in measured.items():
            if m[2] <= 0:
                continue
            if i in zp_terms:   # the star itself left out of its zero point
                z_i, w_i = zp_terms[i]
                if w_sum - w_i <= 0:
                    continue
                zp = (wz_sum - z_i * w_i) / (w_sum - w_i)
            else:
                zp = wz_sum / w_sum
            series.setdefault(i, []).append((-2.5 * math.log10(m[2]) + zp, 1.0857 * m[3] / m[2]))
    stats = []
    for i, values in series.items():
        if len(values) < min_frames:
            continue
        mags = np.array([v[0] for v in values])
        errs = np.array([v[1] for v in values])
        stats.append({"i": i, "n": len(mags), "mag": float(np.median(mags)), "std": float(np.std(mags)),
                      "err": float(np.median(errs)),
                      "chi2": float(np.mean(((mags - mags.mean()) / np.maximum(errs, 1e-4)) ** 2))})
    if len(stats) < 5:
        return ["  field survey: fewer than 5 stars measured in enough images"]
    for st in stats:   # the scatter expected at its brightness: the others'
        similar = [o["std"] for o in stats if o is not st and abs(o["mag"] - st["mag"]) <= 0.5]
        if len(similar) < 3:
            similar = sorted((o for o in stats if o is not st), key=lambda o: abs(o["mag"] - st["mag"]))[:5]
            similar = [o["std"] for o in similar]
        st["ratio"] = st["std"] / max(float(np.median(similar)), 1e-4)
    stats.sort(key=lambda st: st["ratio"], reverse=True)
    for st in stats:
        st["candidate"] = st["ratio"] >= flag_ratio and st["chi2"] >= flag_chi2

    out_csv = os.path.join(folder, "stars_variability.csv")
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([f"# Field of {target['name']}: comparison stars, each from the zero point of the others; "
                         f"ratio = its scatter / the median scatter of stars within 0.5 mag"])
        writer.writerow(["name", "ra", "dec", "V_catalogue", "n", "mag", "std", "median_err", "chi2", "ratio", "candidate"])
        for st in stats:
            c = comps[st["i"]]
            writer.writerow([c["name"], f"{c['ra']:.6f}", f"{c['dec']:.6f}", c["mag"], st["n"], f"{st['mag']:.4f}",
                             f"{st['std']:.4f}", f"{st['err']:.4f}", f"{st['chi2']:.2f}", f"{st['ratio']:.2f}",
                             "yes" if st["candidate"] else ""])
    candidates = [st for st in stats if st["candidate"]]
    lines = [f"Field survey: {len(stats)} stars -> {out_csv}",
             f"  {len(candidates)} candidate variable(s) (scatter {flag_ratio:g} x that of similar stars, chi2 >= {flag_chi2:g})"]
    for st in candidates[:5]:
        c = comps[st["i"]]
        lines.append(f"    star {c['name']}: RA {c['ra']:.5f} Dec {c['dec']:+.5f}, V {c['mag']}, "
                     f"std {st['std']:.3f} ({st['ratio']:.1f} x, chi2 {st['chi2']:.1f})")

    png = os.path.join(folder, "stars_variability.png")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(9, 5.5), dpi=110)
        mags = [st["mag"] for st in stats]
        ax.scatter(mags, [st["std"] for st in stats], s=18, color="#1f5fbf", label="comparison stars")
        ax.scatter([st["mag"] for st in candidates], [st["std"] for st in candidates], s=40, facecolors="none",
                   edgecolors="#c03030", linewidths=1.5, label=f"candidates ({flag_ratio:g} x the scatter)")
        for st in candidates[:10]:
            ax.annotate(comps[st["i"]]["name"], (st["mag"], st["std"]), textcoords="offset points", xytext=(4, 4),
                        fontsize=8, color="#c03030")
        ax.scatter([st["mag"] for st in stats], [st["err"] for st in stats], s=8, color="#999999", marker="_",
                   label="median error")
        ax.set_xlabel("Magnitude (TG)")
        ax.set_ylabel("Scatter over the session (mag)")
        ax.set_title(f"Field of {target['name']} - scatter against magnitude")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=9)
        fig.tight_layout()
        fig.savefig(png)
        plt.close(fig)
        lines.append(f"  plot -> {png}")
    except Exception as e:
        lines.append(f"  survey plot not drawn: {e}")
    return lines


# Where the photometry's results are archived with the session (user-requested
# Oct 2026: shown in Dwarfium Scope Archive's Explore, kept with the archive):
# _PHOTOMETRY/<star>/<session folder>/ at the root of the archive (by star,
# user-requested Oct 2026: a star's sessions side by side, to put together) -
# the backup's
# Astronomy folder, the level of RESTACKED, given by Scope Archive in
# siril_session.json ("astronomy_root") - the same convention as its
# api/photometry_results.py and api/archive_paths.py
PHOTOMETRY_DIR = "_PHOTOMETRY"   # api/archive_paths.py's


def archive_photometry(folder, seq_name, session_dir, target_name, extra=(), root="", failed=None):
    """The light curve, the field survey and the comparison stars copied from
    the process folder to _PHOTOMETRY/<star>/<session folder>/ at the archive's root
    (`root`; without it, the session's parent folder - its grandparent when
    that is RESTACKED, STARTRAILS or Archive, as Scope Archive's
    astronomy_root()), named after the target too. Returns the folder, None
    when the session folder isn't reachable; a file that can't be written
    (open in Excel or an image viewer on Windows, user-reported Oct 2026)
    is left as it was and added to `failed` (name, error), the others copied."""
    if not session_dir or not os.path.isdir(session_dir):
        return None
    session_dir = os.path.normpath(session_dir)
    name = re.sub(r"[^\w.-]+", "_", os.path.basename(session_dir)) or "session"
    if not root or not os.path.isdir(root):
        root = os.path.dirname(session_dir)
        if os.path.basename(root).upper() in ("RESTACKED", "STARTRAILS", "ARCHIVE"):
            root = os.path.dirname(root)
    star = re.sub(r"[^\w.-]+", "_", target_name) or "target"
    out = os.path.join(root, PHOTOMETRY_DIR, star, name)
    os.makedirs(out, exist_ok=True)
    copies = {
        f"light_curve_{seq_name}.csv": f"light_curve_{star}.csv",
        f"light_curve_{seq_name}.png": f"light_curve_{star}.png",
        "stars_variability.csv": f"stars_variability_{star}.csv",
        "stars_variability.png": f"stars_variability_{star}.png",
        "comparison_stars.csv": f"comparison_stars_{star}.csv",
    }
    pairs = [(os.path.join(folder, src), os.path.join(out, dst)) for src, dst in copies.items()]
    pairs += [(path, os.path.join(out, os.path.basename(path))) for path in extra if path]   # .ssf, build log
    for src, dst in pairs:
        if not os.path.isfile(src):
            continue
        try:
            shutil.copy2(src, dst)
        except OSError as e:
            if failed is not None:
                failed.append((os.path.basename(dst), e))
    return out


def _read_photometry_csv(path):
    """(meta {"key": "value"} of its "# key: value" lines, header, rows) of a
    light curve or field survey CSV."""
    meta, header, rows = {}, None, []
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.reader(f):
            if not row:
                continue
            if row[0].startswith("#"):
                key, sep, value = row[0][1:].partition(":")
                if sep and len(row) == 1 and " " not in key.strip():
                    meta[key.strip()] = value.strip()
                continue
            if header is None:
                header = row
            else:
                rows.append(dict(zip(header, row)))
    return meta, header or [], rows


def combine_star_sessions(star_dir, other_roots=(), max_sep_arcsec=3.0):
    """The sessions of one star (_PHOTOMETRY/<star>/<session>/, user-requested
    Oct 2026) put together in star_dir: each session's magnitudes shifted by
    its offset to the reference session (the one with most points) - the
    weighted mean difference of the comparison stars both measured, matched
    by position (findcompstars numbers them differently from one session to
    the next), 3-sigma clipped. Writes combined_light_curve.csv (every point,
    its session and the offset applied), combined_sessions.csv and
    combined_light_curve.png. other_roots: the other backup drives' Astronomy
    roots (user-requested Oct 2026: one DWARF, one drive) - their
    _PHOTOMETRY/<star>/ sessions taken too, the results written in each of
    these star folders (Explore shows the same curve from any of them); a
    session on two drives counted once (its newer copy). Returns the summary
    lines; [] with fewer than two sessions."""
    import math
    import numpy as np
    star_dir = os.path.normpath(star_dir)
    star = os.path.basename(star_dir)
    star_dirs, unreachable = [star_dir], []
    for root in other_roots:
        other = os.path.normpath(os.path.join(root, PHOTOMETRY_DIR, star))
        if not os.path.isdir(root):
            unreachable.append(root)
        elif os.path.isdir(other) and os.path.normcase(other) not in {os.path.normcase(d) for d in star_dirs}:
            star_dirs.append(other)
    found = {}
    for directory in star_dirs:
        for name in os.listdir(directory):
            curve = os.path.join(directory, name, f"light_curve_{star}.csv")
            if os.path.isfile(curve) and (name not in found or
                                          os.path.getmtime(curve) > os.path.getmtime(found[name][1])):
                found[name] = (directory, curve)
    sessions = []
    for name in sorted(found):
        directory, curve = found[name]
        folder = os.path.dirname(curve)
        meta, _, rows = _read_photometry_csv(curve)
        points = []
        for r in rows:
            try:
                t = float(r.get("HJD_UTC") or r["JD_UTC"])
                # A saturated target kept on request (target_saturated): drawn apart, out of the means
                points.append((t, float(r["mag"]), float(r["err"]), r.get("airmass", ""),
                               (r.get("target_saturated") or "").strip().lower() == "yes"))
            except (KeyError, ValueError):
                continue
        comps = []
        survey = os.path.join(folder, f"stars_variability_{star}.csv")
        if os.path.isfile(survey):
            for r in _read_photometry_csv(survey)[2]:
                try:
                    comps.append((float(r["ra"]), float(r["dec"]), float(r["mag"]), max(float(r["std"]), 1e-3)))
                except (KeyError, ValueError):
                    continue
        if points:
            sessions.append({"name": name, "meta": meta, "points": points, "comps": comps,
                             "drive": os.path.dirname(os.path.dirname(directory))})
    if len(sessions) < 2:
        return []

    ref = max(sessions, key=lambda s: len(s["points"]))
    ref_comps = np.array([c[:2] for c in ref["comps"]]) if ref["comps"] else np.zeros((0, 2))
    for s in sessions:
        s["offset"], s["n_common"] = 0.0, 0
        if s is ref:
            s["n_common"] = len(ref["comps"])
            continue
        diffs, weights = [], []
        for ra, dec, mag, std in s["comps"]:
            if not len(ref_comps):
                break
            sep = np.hypot((ref_comps[:, 0] - ra) * math.cos(math.radians(dec)), ref_comps[:, 1] - dec) * 3600
            i = int(np.argmin(sep))
            if sep[i] <= max_sep_arcsec:
                diffs.append(mag - ref["comps"][i][2])
                weights.append(1.0 / (std ** 2 + ref["comps"][i][3] ** 2))
        if len(diffs) >= 3:
            d, w = np.array(diffs), np.array(weights)
            keep = np.abs(d - np.median(d)) <= 3 * max(np.std(d), 1e-3)
            s["offset"] = float(np.average(d[keep], weights=w[keep]))
            s["n_common"] = int(keep.sum())

    def _label(s):
        date = s["name"].rsplit("_", 1)[-1][:16] if "_" in s["name"] else s["name"]
        return f"{s['meta'].get('instrument', '')} {date}".strip()

    out_csv = os.path.join(star_dir, "combined_light_curve.csv")
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([f"# {star.replace('_', ' ')}: {len(sessions)} sessions, magnitudes shifted to the "
                         f"reference session {ref['name']} by the comparison stars both measured"])
        writer.writerow(["session", "instrument", "HJD_UTC", "mag", "mag_raw", "err", "offset", "airmass",
                         "target_saturated"])
        for s in sessions:
            for t, mag, err, airmass, sat in s["points"]:
                writer.writerow([s["name"], s["meta"].get("instrument", ""), f"{t:.6f}", f"{mag - s['offset']:.4f}",
                                 f"{mag:.4f}", f"{err:.4f}", f"{s['offset']:+.4f}", airmass, "yes" if sat else ""])
    with open(os.path.join(star_dir, "combined_sessions.csv"), "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["session", "instrument", "filter", "exposure_s", "site", "points", "HJD_start", "HJD_end",
                         "mean_mag", "offset", "common_comparison_stars", "reference", "drive"])
        for s in sessions:
            times = [p[0] for p in s["points"]]
            mags = [p[1] for p in s["points"] if not p[4]] or [p[1] for p in s["points"]]
            writer.writerow([s["name"], s["meta"].get("instrument", ""), s["meta"].get("filter", ""),
                             s["meta"].get("exposure_s", ""), s["meta"].get("site", ""), len(times),
                             f"{min(times):.6f}", f"{max(times):.6f}", f"{np.mean(mags) - s['offset']:.4f}",
                             f"{s['offset']:+.4f}", s["n_common"], "yes" if s is ref else "", s["drive"]])

    summary = [f"Sessions of {star.replace('_', ' ')} put together: {len(sessions)} from {len(star_dirs)} drive(s) "
               f"-> {out_csv}"]
    if unreachable:   # one line: a user's database knew 10 drives, most unplugged (Oct 2026)
        summary.append(f"  {len(unreachable)} drive(s) not plugged in, their sessions not counted: "
                       + ", ".join(unreachable))
    for s in sessions:
        mags = np.array([p[1] for p in s["points"] if not p[4]] or [p[1] for p in s["points"]]) - s["offset"]
        n_sat = sum(1 for p in s["points"] if p[4])
        summary.append(f"  {_label(s)}: {len(s['points'])} points" + (f" ({n_sat} saturated)" if n_sat else "")
                       + f", mean {mags.mean():.3f}, "
                       + ("reference" if s is ref else
                          f"offset {s['offset']:+.3f} ({s['n_common']} comparison stars in common)"
                          if s["n_common"] >= 3 else "not aligned (fewer than 3 comparison stars in common)"))
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        origin = math.floor(min(p[0] for s in sessions for p in s["points"]))
        fig, ax = plt.subplots(figsize=(10, 5.5), dpi=110)
        colours = plt.rcParams["axes.prop_cycle"].by_key()["color"]
        all_mags = []
        for k, s in enumerate(sessions):
            t = np.array([p[0] for p in s["points"]]) - origin
            m = np.array([p[1] for p in s["points"]]) - s["offset"]
            e = np.array([p[2] for p in s["points"]])
            sat = np.array([p[4] for p in s["points"]], dtype=bool)
            all_mags.extend(m[~sat])
            colour = colours[k % len(colours)]
            ax.errorbar(t[~sat], m[~sat], yerr=e[~sat], fmt="o", ms=3, lw=0.7, alpha=0.6, color=colour,
                        label=f"{_label(s)} ({int((~sat).sum())} pts, offset {s['offset']:+.3f})")
            if sat.any():
                ax.errorbar(t[sat], m[sat], yerr=e[sat], fmt="o", ms=4, lw=0.5, alpha=0.6, mfc="none", color=colour,
                            label=f"{_label(s)}, saturated ({int(sat.sum())}: too faint)")
        all_mags = np.array(all_mags) if all_mags else np.array([p[1] for s in sessions for p in s["points"]])
        ax.axhline(all_mags.mean(), color="#444444", ls="--", lw=1, label=f"mean {all_mags.mean():.3f}")
        ax.invert_yaxis()
        ax.set_xlabel(f"HJD (UTC) - {origin}")
        ax.set_ylabel("Magnitude (TG, green channel)")
        ax.set_title(f"{star.replace('_', ' ')} - {len(sessions)} sessions combined\n"
                     f"{len(all_mags)} points  ·  mean {all_mags.mean():.3f}  ·  std {all_mags.std():.3f}  ·  "
                     f"range {all_mags.min():.3f} – {all_mags.max():.3f}", fontsize=10)
        ax.grid(alpha=0.3)
        ax.legend(loc="best", fontsize=8)
        fig.tight_layout()
        png = os.path.join(star_dir, "combined_light_curve.png")
        fig.savefig(png)
        plt.close(fig)
        summary.append(f"  plot -> {png}")
    except Exception as e:
        summary.append(f"  combined plot not drawn: {e}")
    # The same results in the star's folder of each other drive
    for other in star_dirs[1:]:
        for name in ("combined_light_curve.csv", "combined_sessions.csv", "combined_light_curve.png"):
            try:
                if os.path.isfile(os.path.join(star_dir, name)):
                    shutil.copy2(os.path.join(star_dir, name), os.path.join(other, name))
            except OSError as e:
                summary.append(f"  not copied to {other}: {e}")
                break
    return summary


def plot_light_curve(rows, png, target_name, check_label=None, bin_size=3, target_v=None, check_v=None):
    """The light curve as a PNG, as in V. Lecomte's DY Peg procedure (user-
    requested Oct 2026): the target's magnitude against HJD (JD when not
    computed) with its error bars, the check star's, magnitudes growing
    downwards; beyond 15 points, means of bin_size points over them. The
    mean magnitudes (weighted by the errors) as dashed lines, with the
    catalogue's V when known (target_v, check_v), and the target's scatter
    and range under the title (user-requested Oct 2026)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    times = np.array([r[2] if r[2] is not None else r[1] for r in rows])
    label_time = "HJD (UTC)" if all(r[2] is not None for r in rows) else "JD (UTC)"
    origin = float(np.floor(times.min()))
    x = times - origin
    mags, errs = np.array([r[4] for r in rows]), np.array([r[5] for r in rows])
    # Saturated target (kept on request): drawn apart, out of the mean and the statistics
    sat = np.array([bool(r[12]) if len(r) > 12 else False for r in rows])
    good = ~sat if (~sat).any() else np.ones(len(rows), dtype=bool)

    def _mean(values, errors):
        weights = 1.0 / np.maximum(errors, 1e-4) ** 2
        return float(np.average(values, weights=weights)), float(1.0 / np.sqrt(weights.sum()))

    def _v(value):
        return "" if value is None else f", V {float(value):.2f}"

    fig, ax = plt.subplots(figsize=(10, 5.5), dpi=110)
    ax.errorbar(x[good], mags[good], yerr=errs[good], fmt="o", ms=3, lw=0.8, color="#1f5fbf", alpha=0.55,
                label=target_name)
    if sat.any():
        ax.errorbar(x[sat], mags[sat], yerr=errs[sat], fmt="o", ms=4, lw=0.6, mfc="none", color="#e08a00",
                    alpha=0.8, label=f"{target_name}, saturated ({int(sat.sum())}: too faint)")
    mean, mean_err = _mean(mags[good], errs[good])
    ax.axhline(mean, color="#1f5fbf", ls="--", lw=1,
               label=f"{target_name} mean {mean:.3f} ± {mean_err:.3f}{_v(target_v)}")
    stats = [f"{int(good.sum())} points" + (f" + {int(sat.sum())} saturated" if sat.any() else ""),
             f"mean {mean:.3f}", f"std {mags[good].std():.3f}",
             f"range {mags[good].min():.3f} – {mags[good].max():.3f}"]
    if check_label:
        cx = np.array([xi for xi, r in zip(x, rows) if r[8] is not None])
        cm = np.array([r[8] for r in rows if r[8] is not None])
        ce = np.array([r[9] for r in rows if r[8] is not None])
        if cm.size:
            ax.errorbar(cx, cm, yerr=ce, fmt="s", ms=3, lw=0.8, color="#c03030", alpha=0.45, label=check_label)
            check_mean, _ = _mean(cm, ce)
            ax.axhline(check_mean, color="#c03030", ls="--", lw=1,
                       label=f"check mean {check_mean:.3f}{_v(check_v)}")
            stats.append(f"check std {cm.std():.3f}")
    if good.sum() > 15 and bin_size > 1:
        gx, gm = x[good], mags[good]
        n = len(gx) // bin_size * bin_size
        bx = gx[:n].reshape(-1, bin_size).mean(axis=1)
        bm = gm[:n].reshape(-1, bin_size).mean(axis=1)
        be = gm[:n].reshape(-1, bin_size).std(axis=1) / np.sqrt(bin_size)
        ax.errorbar(bx, bm, yerr=be, fmt="o", ms=5, lw=1.2, color="#0b2f6b", label=f"{target_name}, mean of {bin_size}")
    ax.invert_yaxis()
    ax.set_xlabel(f"{label_time} - {origin:.0f}")
    ax.set_ylabel("Magnitude (TG, green channel)")
    # The statistics under the title: in the plot they hid points
    ax.set_title(f"{target_name} - differential photometry\n" + "  ·  ".join(stats), fontsize=10)
    ax.grid(alpha=0.3)
    ax.legend(loc="best", fontsize=9)
    fig.tight_layout()
    fig.savefig(png)
    plt.close(fig)


def dwarf_platesolve_args(path):
    """platesolve's -focal= / -pixelsize= for the green-extracted image (half
    the size, pixels twice as large) when the FITS header has no FOCALLEN /
    XPIXSZ (DWARF II tele), else [] - Siril reads them from the header and
    doubles the pixel size itself when extracting the green channel."""
    cards = {key: value for _, key, value, _ in read_fits_cards(path)}
    if cards.get("FOCALLEN") and cards.get("XPIXSZ"):
        return []
    try:
        scale = _D2_PLATE_SCALE_BY_WIDTH.get(int(cards.get("NAXIS1", 0)))
    except ValueError:
        scale = None
    if not scale:
        return []
    pixel_um = 2 * scale * _D2_TELE_FOCAL_MM / 206.265
    return [f"-focal={_D2_TELE_FOCAL_MM:g}", f"-pixelsize={pixel_um:.3f}"]


def win_long_path(filepath):
    if os.name == 'nt': 
        filepath_str = str(filepath) 
        if filepath_str.startswith('\\\\?\\'): 
            return filepath_str # already in long path format 
        else: 
            return '\\\\?\\' + os.path.abspath(filepath_str)
    else: return str(filepath)

class Target:
    """Target Class contains the targets from the Dwarfium archives with their sessions"""

    def __init__(self, target):
        self.target = target
        self.sessions = []

    def add_session(self, session):
        self.sessions.append(session)

    def __repr__(self):
        return str(self)

    def __str__(self):
        return f"{self.target}: {len(self.sessions)} sessions"


class Session:
    """Session Class contains the information of the single session"""

    def __init__(self, path, cam, target, exp, gain, date):
        self.cam = cam
        self.target = target
        self.exposure = exp
        self.gain = gain
        self.date = date
        self.thumbnail = os.path.join(path, "stacked.jpg")
        self.ra = None
        self.dec = None
        self.min_temp = None
        self.max_temp = None
        try:
            self.prettydate = datetime.strptime(date, "%Y-%m-%d-%H-%M-%S-%f")
        except:
            self.siril.log(f"Invalid date format: {date}", LogColor.RED)
            return None

        self.calendardate = datetime(
            self.prettydate.year,
            self.prettydate.month,
            self.prettydate.day,
            self.prettydate.hour,
            self.prettydate.minute,
        )
        self.path = path
        self.ir = "unknown"
        self.taken = 0
        self.stacked = 0

    def __str__(self):
        return "'{}' with {}, {}s/{}g on {}".format(
            self.target, self.cam.lower(), self.exposure, self.gain, self.date
        )


class CopyMultiThread(QThread):
    """Copy files from multiple source→dest pairs in the background."""
    progress = pyqtSignal(int)
    done     = pyqtSignal(int)

    def __init__(self, pairs):
        """pairs: list of (src_path, dest) tuples.
        dest may be a directory OR a full destination file path (used to rename
        files on copy and avoid collisions between sessions)."""
        QThread.__init__(self, None)
        self.pairs = pairs

    def run(self):
        done = 0
        for src, dest in self.pairs:
            root, ext = os.path.splitext(dest)
            if ext:
                # dest is a full file path — create its parent dir
                os.makedirs(os.path.dirname(dest), exist_ok=True)
            else:
                # dest is a directory
                os.makedirs(dest, exist_ok=True)
            try:
                print(f"COPY:\n  {src}\n  -> {dest}")
                shutil.copy2(win_long_path(src), win_long_path(dest))
            except Exception as e:
                import traceback
                print(traceback.format_exc())
                raise
            done += 1
            self.progress.emit(done)
        self.done.emit(done)


class MosaicTileExtractThread(QThread):
    """Extract/copy already-stacked RESTACKED_ tile FITS files into a single
    working folder, ready for astrometric mosaic stitching in Siril.

    Each tile (a session whose name starts with "RESTACKED_") contributes
    either:
      - one stacked-16*.fits file directly in its session_dir, or
      - one or more stacked-16*.fits files packed inside a stacked-16*.zip
        at the root of its session_dir, if the session name contains
        "_MOSAIC_" (the session itself was a multi-panel mosaic capture
        that got pre-stacked panel by panel).
    Tiles are renamed with a session index prefix to avoid collisions.
    """
    progress = pyqtSignal(int)
    done     = pyqtSignal(int, list)  # (tile_count, error_messages)

    def __init__(self, sessions, dest_dir):
        QThread.__init__(self, None)
        self.sessions = sessions
        self.dest_dir = dest_dir

    def run(self):
        os.makedirs(self.dest_dir, exist_ok=True)
        tile_count = 0
        errors = []

        for s_idx, sess in enumerate(self.sessions, 1):
            session_dir  = sess.get("session_dir") or ""
            session_name = sess.get("session_name") or os.path.basename(session_dir)
            is_mosaic    = "_MOSAIC_" in session_name.upper()

            if not os.path.isdir(session_dir):
                errors.append(f"{session_name}: folder not found ({session_dir})")
                continue

            try:
                if is_mosaic:
                    zips = sorted(
                        f for f in os.listdir(session_dir)
                        if f.lower().startswith("stacked-16") and f.lower().endswith(".zip")
                    )
                    if not zips:
                        errors.append(f"{session_name}: no stacked-16*.zip found")
                        continue
                    zip_path = os.path.join(session_dir, zips[0])
                    with zipfile.ZipFile(zip_path, "r") as zf:
                        fits_members = [
                            m for m in zf.namelist()
                            if os.path.basename(m).lower().startswith("stacked-16")
                            and os.path.basename(m).lower().endswith((".fits", ".fit", ".fts"))
                        ]
                        if not fits_members:
                            errors.append(f"{session_name}: zip contains no stacked-16 FITS")
                            continue
                        for m_idx, member in enumerate(sorted(fits_members), 1):
                            ext = os.path.splitext(member)[1]
                            dest_name = f"tile{s_idx:02d}_{m_idx:02d}{ext}"
                            dest_path = os.path.join(self.dest_dir, dest_name)
                            with zf.open(member) as src_f, open(dest_path, "wb") as dst_f:
                                shutil.copyfileobj(src_f, dst_f)
                            tile_count += 1
                            self.progress.emit(tile_count)
                else:
                    fits_files = sorted(
                        f for f in os.listdir(session_dir)
                        if f.lower().startswith("stacked-16")
                        and f.lower().endswith((".fits", ".fit", ".fts"))
                    )
                    if not fits_files:
                        errors.append(f"{session_name}: no stacked-16*.fits found")
                        continue
                    src_path = os.path.join(session_dir, fits_files[0])
                    ext = os.path.splitext(fits_files[0])[1]
                    dest_name = f"tile{s_idx:02d}{ext}"
                    dest_path = os.path.join(self.dest_dir, dest_name)
                    shutil.copy2(win_long_path(src_path), win_long_path(dest_path))
                    tile_count += 1
                    self.progress.emit(tile_count)
            except Exception as e:
                errors.append(f"{session_name}: {e}")

        self.done.emit(tile_count, errors)


class CopyThread(QThread):
    """Thread to copy the files in the background, otherise the progress bar would not update"""

    progress = pyqtSignal(int)
    done = pyqtSignal(int)

    def __init__(self, files, dest):
        QThread.__init__(self, None)
        self.files = files
        self.dest = dest

    def run(self):
        done = 0
        for f in self.files:
            shutil.copy2(win_long_path(f), win_long_path(self.dest))
            done += 1
            self.progress.emit(done)
        self.done.emit(done)


def close_dialog(self):
    try:
        self.siril.disconnect()
    except Exception:
        pass  # Ignore disconnect errors
    self.close()


class PreprocessingInterface(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} - v{VERSION}")
        self.initialization_successful = False

        self.siril = s.SirilInterface()

        # declare internal members
        self.archive_dir = None
        self.targets = []
        self.target_list = []
        self.selected_target = None
        self.selected_sessions = []

        try:
            self.siril.connect()
            self.siril.log("Connected to Siril", LogColor.GREEN)
        except s.SirilConnectionError:
            self.siril.log("Failed to connect to Siril", LogColor.RED)
            self.close_dialog()
            return

        try:
            self.siril.cmd("requires", "1.3.6")
        except s.CommandError:
            self.close_dialog()
            return

        self.fits_extension = self.siril.get_siril_config("core", "extension")
        # home directory is unchanged
        self.home_directory = self.siril.get_siril_wd()
        self.current_working_directory = self.siril.get_siril_wd()
        self.cwd_label = self.current_working_directory

        # Assigns collected_lights directory to store all pp_lights files
        self.collected_lights_dir = os.path.join(
            self.current_working_directory, "collected_lights"
        )
        # Stores the last loaded siril_megastack.json data, so the mosaic
        # builder (RESTACKED tiles) can reuse it without reloading the file
        self._last_megastack_data = None
        # Stores the (ssf_path, lines) of the last generated stack/combine
        # scripts, so the "Build Sessions" button can run them directly
        # without re-reading the .ssf files from disk
        self._last_generated_scripts = []
        self._mosaic_include_stacks = []
        self._last_json_path = None
        # Stores the last loaded siril_session.json (single session), for
        # the optional photometry script generated after the copy
        self._last_session_data = None
        # defaults for presets
        self.load_presets()
        self.create_widgets()
        self.initialization_successful = True  # Flag to track successful initialization

    def create_path_widgets(self, main_layout):
        """create Path box widgets"""
        paths_group = QGroupBox("Current paths:")
        cwd_layout = QVBoxLayout()
        cwd_label = QLabel(f"Current working directory: {self.cwd_label}")
        cwd_layout.addWidget(cwd_label)

        # Label with Archive path
        archive_layout = QHBoxLayout()
        self.archive_label = QLabel(f"Selected archive directory: {self.archive_dir}")
        if self.archive_dir is None or not os.path.exists(self.archive_dir):
            self.archive_label.setStyleSheet("QLabel {color: #FF0000};")
        else:
            self.archive_label.setStyleSheet("QLabel {color: #00FF00};")
        archive_layout.addWidget(self.archive_label)

        # chose archive path button
        archive_choose_btn = QPushButton("Change")
        archive_choose_btn.setMinimumWidth(80)
        archive_choose_btn.setMaximumWidth(80)
        archive_choose_btn.setMinimumHeight(35)
        archive_choose_btn.clicked.connect(self.chose_archive)
        archive_layout.addWidget(archive_choose_btn)
        # Refresh button
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setMinimumWidth(80)
        refresh_btn.setMaximumWidth(80)
        refresh_btn.setMinimumHeight(35)
        refresh_btn.clicked.connect(lambda: self.scan_archive(self.archive_dir))
        archive_layout.addWidget(refresh_btn)

        cwd_layout.addLayout(archive_layout)
        paths_group.setLayout(cwd_layout)
        main_layout.addWidget(paths_group)

    def create_list_widgets(self, main_layout):
        """create widgets with the listboxes for targets and sessions"""
        files_layout = QVBoxLayout()
        list_group = QGroupBox("Targets and Session in Dwarf Archive:")
        list_layout = QHBoxLayout()
        # Listbox for targets (left)
        self.target_listbox = QListWidget()
        self.target_listbox.setMaximumWidth(300)
        self.target_listbox.itemSelectionChanged.connect(self.target_selected)
        list_layout.addWidget(self.target_listbox)

        right_layout = QVBoxLayout()
        right_info = QHBoxLayout()
        self.thumb = QLabel()
        self.thumb.setMinimumHeight(160)
        self.thumb.setMaximumHeight(160)
        self.thumb.setMinimumWidth(300)
        self.thumb.setMaximumWidth(300)
        right_info.addWidget(self.thumb)

        self.info_box = QTextEdit(readOnly=True)
        self.info_box.setMinimumHeight(self.thumb.height())
        self.info_box.setMaximumHeight(self.thumb.height())
        # self.info_box.setMaximumWidth(300)
        right_info.addWidget(self.info_box)

        right_layout.addLayout(right_info)
        # Listbox for sessions
        self.session_listbox = QListWidget()
        self.session_listbox.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.session_listbox.itemSelectionChanged.connect(self.session_selected)
        right_layout.addWidget(self.session_listbox)
        list_layout.addLayout(right_layout)

        list_group.setLayout(list_layout)
        files_layout.addWidget(list_group)
        main_layout.addWidget(list_group)

    def create_bottom_widgets(self, main_layout):
        """create the widgets for the bottom part - progress bar and action buttons"""
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(
            0, 15, 0, 0
        )  # Add top margin to separate from content
        # Second row: the mosaic options on the left, the variable star tools
        # on the right - on one row with the buttons, they overlapped
        # (user-reported Oct 2026: ~1500 px needed in a 750 px window)
        option_layout = QHBoxLayout()
        variable_layout = QHBoxLayout()

        help_btn = QPushButton("?")
        help_btn.setMinimumWidth(35)
        help_btn.setMaximumWidth(35)
        help_btn.setMinimumHeight(35)
        help_btn.clicked.connect(self.show_help)
        button_layout.addWidget(help_btn)

        # progressbar for copy operation
        self.progressbar = QProgressBar()
        self.progressbar.setTextVisible(False)
        self.progressbar.setMinimumHeight(35)
        self.progressbar.setMinimum(0)
        self.progressbar.setMaximum(1)
        self.progressbar.setValue(0)
        button_layout.addWidget(self.progressbar)

        # label showing number of files to copy
        self.progress_label = QLabel("0 / 0")
        self.progress_label.setMinimumWidth(100)
        self.progress_label.setMaximumWidth(100)
        self.progress_label.setMinimumHeight(35)
        self.progress_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        button_layout.addWidget(self.progress_label)

        # copy button
        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setMinimumHeight(35)
        self.copy_btn.setMinimumWidth(80)
        self.copy_btn.setMaximumWidth(80)
        self.copy_btn.setDisabled(True)
        self.copy_btn.clicked.connect(self.start_copy)
        button_layout.addWidget(self.copy_btn)

        # Load from Dwarfium JSON button
        self.json_btn = QPushButton("📡 Load Dwarfium JSON")
        self.json_btn.setMinimumHeight(35)
        self.json_btn.setMinimumWidth(160)
        self.json_btn.setToolTip(
            "Load a siril_session.json generated by Dwarfium Scope Archive\n"
            "to copy lights + darks + bias + flat into Siril working folders."
        )
        self.json_btn.clicked.connect(self.load_dwarfium_json)
        button_layout.addWidget(self.json_btn)

        # Photometry option (variable stars): with a single siril_session.json,
        # generate a light-curve script instead of stacking (see
        # _generate_photometry_script)
        self.photometry_checkbox = QCheckBox("📈 Photometry")
        self.photometry_checkbox.setToolTip(
            "Variable star photometry for a single siril_session.json:\n"
            "after the copy, a 01_photometry_*.ssf script is generated instead of\n"
            "stacking - calibration, green channel (AAVSO TG band), plate solve of\n"
            "every image, comparison stars (findcompstars), differential photometry.\n"
            "Run it with Build Sessions. Requires Siril 1.4.0+ and Internet."
        )
        variable_layout.addWidget(self.photometry_checkbox)

        # Exposure check: a few test frames of the variable star measured, to
        # choose the exposure / gain of the photometry session
        self.exposure_btn = QPushButton("🔆 Check exposure")
        self.exposure_btn.setMinimumHeight(35)
        self.exposure_btn.setToolTip(
            "Measure the variable star in a few test frames (raw FITS):\n"
            "its peak against the 12-bit saturation, its S/N, saturated comparison\n"
            "stars, and the longest exposure at that gain. Plate solve and\n"
            "findcompstars: Siril 1.4.0+ and Internet."
        )
        self.exposure_btn.clicked.connect(self.check_exposure)
        variable_layout.addWidget(self.exposure_btn)

        # Run the generated .ssf stack/combine scripts directly in Siril
        self.build_sessions_btn = QPushButton("🚀 Build Sessions")
        self.build_sessions_btn.setMinimumHeight(35)
        self.build_sessions_btn.setMinimumWidth(150)
        self.build_sessions_btn.setToolTip(
            "Run the generated 01_stack_*.ssf (and 02_combine_*.ssf if any)\n"
            "scripts directly in this Siril session, instead of having to\n"
            "open and run the .ssf file(s) manually."
        )
        self.build_sessions_btn.setDisabled(True)
        self.build_sessions_btn.clicked.connect(self.build_sessions_from_scripts)
        button_layout.addWidget(self.build_sessions_btn)

        # Build mosaic from RESTACKED tiles (astrometric stitching)
        self.mosaic_btn = QPushButton("🧩 Build Mosaic (RESTACKED)")
        self.mosaic_btn.setMinimumHeight(35)
        self.mosaic_btn.setMinimumWidth(180)
        self.mosaic_btn.setToolTip(
            "From the loaded siril_megastack.json, extract the already-stacked\n"
            "RESTACKED_ sessions (debayered FITS, single or _MOSAIC_ zip) and\n"
            "stitch them together using Siril's astrometric mosaic alignment\n"
            "(seqplatesolve + seqapplyreg -framing=max + stack -maximize)."
        )
        self.mosaic_btn.setDisabled(True)
        self.mosaic_btn.clicked.connect(self.build_mosaic_from_restacked)
        button_layout.addWidget(self.mosaic_btn)

        # Feathering option for the mosaic stack (smooths the seam between
        # overlapping tiles — see Siril's -feather=N stack option)
        self.feather_checkbox = QCheckBox("Feather edges")
        self.feather_checkbox.setToolTip(
            "Blend overlapping tile edges with a soft gradient instead of a\n"
            "hard cut, to hide visible seams caused by sky background or\n"
            "gradient differences between tiles. Usually not needed, but\n"
            "try it if you see a visible line where tiles meet."
        )
        self.feather_checkbox.stateChanged.connect(
            lambda state: self.feather_spinbox.setEnabled(state == Qt.CheckState.Checked.value)
        )
        option_layout.addWidget(self.feather_checkbox)

        self.feather_spinbox = QSpinBox()
        self.feather_spinbox.setRange(1, 2000)
        self.feather_spinbox.setValue(100)
        self.feather_spinbox.setSuffix(" px")
        self.feather_spinbox.setMinimumWidth(80)
        self.feather_spinbox.setMaximumWidth(80)
        self.feather_spinbox.setEnabled(False)
        self.feather_spinbox.setToolTip("Width (in pixels) of the feathered blend zone.")
        option_layout.addWidget(self.feather_spinbox)

        # HaRGB blend ratio — Ha weight in the R channel composition
        # R = Ha * ratio + astro_r * (1 - ratio)
        self.ha_blend_label = QLabel("Ha blend:")
        self.ha_blend_label.setToolTip(
            "Weight of the Ha channel in the HaRGB R channel.\n"
            "R = Ha × ratio + Astro_R × (1 − ratio)\n"
            "0.7 = 70% Ha, 30% natural star color from Astro."
        )
        option_layout.addWidget(self.ha_blend_label)

        self.ha_blend_spinbox = QDoubleSpinBox()
        self.ha_blend_spinbox.setRange(0.0, 1.0)
        self.ha_blend_spinbox.setSingleStep(0.05)
        self.ha_blend_spinbox.setValue(0.7)
        self.ha_blend_spinbox.setDecimals(2)
        self.ha_blend_spinbox.setMinimumWidth(70)
        self.ha_blend_spinbox.setMaximumWidth(70)
        self.ha_blend_spinbox.setToolTip(
            "Ha blend ratio for HaRGB combination (0.0 = pure Astro R, 1.0 = pure Ha)."
        )
        option_layout.addWidget(self.ha_blend_spinbox)

        # close button
        close_button = QPushButton("Close")
        close_button.setMinimumWidth(100)
        close_button.setMinimumHeight(35)
        close_button.clicked.connect(self.close_dialog)
        button_layout.addWidget(close_button)

        main_layout.addLayout(button_layout)

        option_layout.addStretch()
        variable_label = QLabel("Variable stars:")
        option_layout.addWidget(variable_label)
        option_layout.addLayout(variable_layout)
        main_layout.addLayout(option_layout)

    def create_widgets(self):
        """Creates the UI widgets using PyQt6."""

        # Main layout
        main_widget = QWidget()
        self.setMinimumSize(1000, 640)  # the two rows of buttons (was 750 x 600: they overlapped)
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(12, 6, 12, 12)
        main_layout.setSpacing(6)

        copyright = QLabel("(c) Stefan Schmidt-Bilkenroth, 2026")
        copyright.setStyleSheet("QLabel {font-size: 10px; color: grey}")
        copyright.setAlignment(Qt.AlignmentFlag.AlignRight)
        main_layout.addWidget(copyright)

        self.create_path_widgets(main_layout)

        self.create_list_widgets(main_layout)
        self.create_bottom_widgets(main_layout)
        self.scan_archive(self.archive_dir)

    def select_folder(self, start_dir):
        """folder selection for the Dwarfium archive"""
        if start_dir is None or not os.path.exists(start_dir):
            start_dir = self.current_working_directory
        selected_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Archive directory",
            start_dir,
        )
        return selected_dir

    def chose_archive(self):
        """function to chose Dwarfium archive"""
        archive_dir = self.select_folder(self.archive_dir)
        if archive_dir is None:
            # do not update if file selector has been cancelled
            return
        self.archive_dir = archive_dir
        self.archive_label.setText(self.archive_dir)
        self.archive_label.setStyleSheet("QLabel {color: #FF0000};")
        self.save_presets()
        self.scan_archive(self.archive_dir)
        return

    def scan_archive(self, archive_dir=None):
        """scan the archive path for subdirectories matching Dwarf naming scheme"""
        self.siril.log(
            f"Running script version {VERSION} with arguments:\n"
            f"archive_dir: {archive_dir}",
            LogColor.GREEN,
        )
        start_dir = archive_dir
        if archive_dir is None or not os.path.exists(archive_dir):
            archive_dir = None
            start_dir = self.current_working_directory

        if archive_dir is None:
            archive_dir = self.select_folder(start_dir)

        self.archive_dir = archive_dir
        sessions = self.parse_filetree(self.archive_dir)
        self.targets = self.get_targets(sessions)
        self.refresh_target_list()

        self.siril.cmd("close")

    def ask(self, title, msg):
        """helper displaying a Question Message Box"""
        reply = QMessageBox.question(
            self,
            title,
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return reply

    def progress_update(self, value):
        """callback for progress update emitted from Copy QThread"""
        self.progressbar.setValue(value)
        self.progress_label.setText(
            f"{self.progressbar.value()} / {self.progressbar.maximum()}"
        )

    def progress_done(self, value):
        """callback for progress completed emitted from Copy QThread"""
        self.copy_btn.setDisabled(False)
        self.progressbar.setValue(0)
        self.progressbar.setMaximum(1)
        self.progress_label.setText("completed")

        reply = QMessageBox.question(
            self,
            "File copy complete",
            f"{value} files have been copied to {os.path.join(self.current_working_directory, 'lights')}",
            buttons=QMessageBox.StandardButton(
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Close
            ),
            defaultButton=QMessageBox.StandardButton.Ok,
        )
        if reply == QMessageBox.StandardButton.Close:
            self.close_dialog()

    def start_copy(self):
        """action for copy button - clean current lights and start copy operation"""
        lights_dir = os.sep.join([self.current_working_directory, "lights"])
        process_dir = os.sep.join([self.current_working_directory, "process"])

        # check if lights dir contains files and ask for confirmation to delete them
        if os.path.exists(lights_dir):
            file_cnt = len(os.listdir(lights_dir))

            if file_cnt > 0:
                self.progressbar.setMaximum(0)
                self.progress_label.setText("cleanup")

                reply = self.ask(
                    "Delete existing lights?",
                    f'This operation will delete {file_cnt} files in\n"{lights_dir}".\nProceed?',
                )
                if reply != QMessageBox.StandardButton.Yes:
                    # abort procesing, when not confirmed
                    return
                shutil.rmtree(lights_dir)

        # create new lights dir and delete process dir, when there is one
        os.mkdir(lights_dir)
        if os.path.exists(process_dir):
            self._release_working_dir()
            shutil.rmtree(process_dir)

        # collect all the files that will get copied
        all_files = []
        for session in self.selected_sessions:
            src = session.path
            files = os.listdir(src)
            for f in files:
                if f.startswith(session.target) and f.endswith(".fits"):
                    all_files.append(os.sep.join([src, f]))
        # prepare progress bar
        self.progressbar.setMaximum(len(all_files))
        self.progressbar.setValue(0)
        self.progress_label.setText(f"0 / {len(all_files)}")
        # prepare and start background thread to actually copy the files
        # This need to be done in a backgrond thread, otherwise the progressbar does not update
        self.copyThread = CopyThread(files=all_files, dest=lights_dir)
        self.copyThread.progress.connect(self.progress_update)
        self.copyThread.done.connect(self.progress_done)
        self.copy_btn.setDisabled(True)
        self.copyThread.start()
        return

    def close_help(self):
        """action for close help button"""
        self.help_window.close()

    def show_help(self):
        """show help, which is provided in Markdown syntax in the beginning of the script"""
        self.help_window = QDialog(self)
        self.help_window.setModal(True)
        self.help_window.setWindowTitle("Dwarfium Archive Selector Help")
        self.help_window.setMinimumSize(750, 600)

        help_layout = QVBoxLayout()
        help_text = QTextEdit(readOnly=True)
        help_text.setMarkdown(HELP_MD)
        help_layout.addWidget(help_text)

        help_close = QPushButton("Close")
        help_close.setMinimumHeight(35)
        help_close.setMinimumWidth(80)
        help_close.setMaximumWidth(80)
        help_close.clicked.connect(self.close_help)
        help_layout.addWidget(help_close)
        self.help_window.setLayout(help_layout)
        self.help_window.exec()

    def load_dwarfium_json(self):
        """Load a siril_session.json or siril_megastack.json produced by Dwarfium Scope Archive."""
        json_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Dwarfium Session JSON",
            "",
            "JSON files (*.json);;All files (*.*)",
        )
        if not json_path:
            return

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not read JSON:\n{e}")
            return

        # ── Megastack JSON ─────────────────────────────────────────────────
        if data.get("type") == "megastack":
            self._last_json_path = json_path
            self._last_session_data = None
            self._load_megastack_json(data)
            return
        self._last_session_data = data

        # ── Single session JSON (original behaviour) ────────────────────────
        session  = data.get("session", {})
        lights   = data.get("lights", [])
        darks    = data.get("darks", {}).get("files", [])
        bias_dir = data.get("bias_dir")
        flat_dir = data.get("flat_dir")

        # Summary dialog
        dark_status = data.get("darks", {}).get("status", "none")
        temp_match  = data.get("darks", {}).get("temp_match", False)
        dark_info   = f"{len(darks)} dark(s) [{dark_status}{'  ✅ temp match' if temp_match else '  ⚠️ closest temp'}]"
        bias_info   = os.path.basename(data.get("bias_file") or bias_dir or "") or "❌ not found"
        flat_info   = os.path.basename(data.get("flat_file") or flat_dir or "") or "❌ not found"

        msg = (
            f"Session: {session.get('target', 'Unknown')}  —  {session.get('date', '')[:10]}\n"
            f"Dwarf: {session.get('dwarf', '')}  |  "
            f"exp={session.get('exp_s')}s  gain={session.get('gain')}  filter={session.get('ir_filter', '')}\n\n"
            f"Lights:  {len(lights)} file(s)\n"
            f"Darks:   {dark_info}\n"
            f"Bias:    {bias_info}\n"
            f"Flat:    {flat_info}\n\n"
            f"Siril home: {self.current_working_directory}\n\n"
            f"Files will be copied into:\n"
            f"  lights/  darks/  bias/  flat/"
        )

        # An earlier photometry run of this session stopped (user-reported Oct
        # 2026: at image 95 of 509): its lights and green images kept, the
        # script made again - the copy would delete process/ first
        if self.photometry_checkbox.isChecked() and self._earlier_photometry_run(len(lights)):
            box = QMessageBox(self)
            box.setWindowTitle("Load Dwarfium Session")
            box.setText(msg + "\n\nThe working directory already holds these lights and the green images of an "
                        "earlier photometry run (process/). Resume it, without copying again?")
            resume_btn = box.addButton("Resume (keep the files)", QMessageBox.ButtonRole.AcceptRole)
            copy_btn = box.addButton("Copy again", QMessageBox.ButtonRole.DestructiveRole)
            box.addButton(QMessageBox.StandardButton.Cancel)
            box.setDefaultButton(resume_btn)
            box.exec()
            if box.clickedButton() is resume_btn:
                self._resume_photometry = True   # its plate solve resumed without asking again
                try:
                    self._copy_from_json_done(0)
                finally:
                    self._resume_photometry = False
                return
            if box.clickedButton() is not copy_btn:
                return
        else:
            reply = QMessageBox.question(
                self, "Load Dwarfium Session", msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self._start_copy_from_json(
            lights, darks, bias_dir, flat_dir,
            bias_file=data.get("bias_file"),
            flat_file=data.get("flat_file"),
        )

    def _earlier_photometry_run(self, n_lights):
        """The working directory holds the lights of a session (at least
        n_lights) and as many green images in process/ - a photometry run to
        resume (_generate_photometry_script then offers the plate solve)."""
        cwd = self.current_working_directory
        lights_dir, proc = os.path.join(cwd, "lights"), os.path.join(cwd, "process")
        if not n_lights or not os.path.isdir(lights_dir) or not os.path.isdir(proc):
            return False
        fits_ext = (".fit", ".fits", ".fts")
        here = sum(1 for f in os.listdir(lights_dir) if f.lower().endswith(fits_ext))
        green = sum(1 for f in os.listdir(proc) if f.startswith("Green_") and f.lower().endswith(fits_ext))
        return here >= n_lights and green >= n_lights

    def _start_copy_from_json(self, lights, darks, bias_dir, flat_dir, bias_file=None, flat_file=None):
        """Copy lights, darks, bias and flat into Siril working directories."""
        cwd = self.current_working_directory
        self._release_working_dir()   # its folders are deleted below

        # Build (src, dest_dir) pairs
        pairs = []

        # Lights → lights/  (preserve panel subdirs for mosaics)
        lights_dir = os.path.join(cwd, "lights")
        if os.path.exists(lights_dir):
            file_cnt = sum(len(fs) for _, _, fs in os.walk(lights_dir))
            if file_cnt > 0:
                reply = self.ask(
                    "Delete existing lights?",
                    f"This will delete {file_cnt} file(s) in:\n{lights_dir}\nProceed?",
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return
                shutil.rmtree(lights_dir)
        os.makedirs(lights_dir, exist_ok=True)
        # Detect mosaic: files come from different parent directories
        parent_dirs = {os.path.basename(os.path.dirname(f)) for f in lights}
        is_mosaic = len(parent_dirs) > 1
        for f in lights:
            if is_mosaic:
                panel = os.path.basename(os.path.dirname(f))
                dest = os.path.join(lights_dir, panel)
            else:
                dest = lights_dir
            pairs.append((f, dest))
        # Darks → darks/
        darks_dir = os.path.join(cwd, "darks")
        if darks:
            if os.path.exists(darks_dir):
                shutil.rmtree(darks_dir)
            os.makedirs(darks_dir, exist_ok=True)
            for f in darks:
                pairs.append((f, darks_dir))

        # Bias → bias/
        # DwarfLab factory: single PNG file; user-captured: subfolder with FITS/PNG
        bias_dest = os.path.join(cwd, "bias")
        if bias_file and os.path.isfile(bias_file):
            if os.path.exists(bias_dest): shutil.rmtree(bias_dest)
            os.makedirs(bias_dest, exist_ok=True)
            pairs.append((bias_file, bias_dest))
        elif bias_dir and os.path.isdir(bias_dir):
            if os.path.exists(bias_dest): shutil.rmtree(bias_dest)
            os.makedirs(bias_dest, exist_ok=True)
            for f in os.listdir(bias_dir):
                if f.lower().endswith((".fits", ".fit", ".fts", ".png")):
                    pairs.append((os.path.join(bias_dir, f), bias_dest))

        # Flat → flat/
        flat_dest = os.path.join(cwd, "flat")
        if flat_file and os.path.isfile(flat_file):
            if os.path.exists(flat_dest): shutil.rmtree(flat_dest)
            os.makedirs(flat_dest, exist_ok=True)
            pairs.append((flat_file, flat_dest))
        elif flat_dir and os.path.isdir(flat_dir):
            if os.path.exists(flat_dest): shutil.rmtree(flat_dest)
            os.makedirs(flat_dest, exist_ok=True)
            for f in os.listdir(flat_dir):
                if f.lower().endswith((".fits", ".fit", ".fts", ".png")):
                    pairs.append((os.path.join(flat_dir, f), flat_dest))

        if not pairs:
            QMessageBox.information(self, "Nothing to copy", "No files to copy.")
            return

        # Delete process dir
        process_dir = os.path.join(cwd, "process")
        if os.path.exists(process_dir):
            self._release_working_dir()
            try:
                shutil.rmtree(process_dir)
            except OSError as e:
                QMessageBox.critical(
                    self, "process folder in use",
                    f"Could not delete {process_dir}:\n{e}\n\n"
                    "Close the image or sequence open in Siril (or a file open in another program) and try again.",
                )
                return

        self.progressbar.setMaximum(len(pairs))
        self.progressbar.setValue(0)
        self.progress_label.setText(f"0 / {len(pairs)}")

        self.json_btn.setDisabled(True)
        self.copy_btn.setDisabled(True)
        self.copyThread = CopyMultiThread(pairs=pairs)
        self.copyThread.progress.connect(self.progress_update)
        self.copyThread.done.connect(self._copy_from_json_done)
        self.copyThread.start()

    def _save_step(self, step: str):
        """Update the 'step' field in the loaded siril_megastack.json on disk.

        Called automatically after each major processing stage completes
        successfully, so the user can reload the JSON later and resume from
        where they left off without redoing earlier steps.

        Args:
            step: one of "copied", "stacked", "combined"
        """
        if not self._last_json_path or not self._last_megastack_data:
            return
        try:
            self._last_megastack_data["step"] = step
            with open(self._last_json_path, "w", encoding="utf-8") as f:
                json.dump(self._last_megastack_data, f, indent=2, ensure_ascii=False)
            self.siril.log(f"[step] JSON updated: step={step}", LogColor.BLUE)
        except Exception as e:
            self.siril.log(f"[step] Could not update JSON step: {e}", LogColor.SALMON)

    def _load_megastack_json(self, data: dict):
        """Handle a siril_megastack.json — multi-session, multi-filter."""
        self._last_megastack_data = data
        obj      = data.get("object", "Unknown")
        filters  = data.get("filters", [])
        single   = data.get("single_filter", True)
        hint     = data.get("combination_hint") or ("single" if single else "manual")
        groups   = data.get("sessions_by_filter", {})
        cwd      = self.current_working_directory
        step     = data.get("step")  # None | "copied" | "stacked" | "combined"

        # Enable the mosaic builder button only if at least one RESTACKED_
        # session is present in the loaded data
        has_restacked = any(
            str(sess.get("session_name", "")).startswith("RESTACKED_")
            for sessions in groups.values()
            for sess in sessions
        )
        self.mosaic_btn.setDisabled(not has_restacked)

        # Adapt Copy/Build buttons based on how far processing has already gone
        # so the user can skip steps already done and resume from where they left off
        STEP_ORDER = [None, "copied", "stacked", "combined"]
        step_idx = STEP_ORDER.index(step) if step in STEP_ORDER else 0

        self.copy_btn.setDisabled(step_idx >= 1)           # already copied
        self.build_sessions_btn.setDisabled(step_idx >= 2) # already stacked
        # mosaic_btn state is managed separately (depends on RESTACKED presence)

        # Build summary
        step_label = f"  [step: {step}]" if step else "  [step: not started]"
        stack_mode = data.get("stack_mode", "raw")
        mode_label = (
            "  [mosaic panels: already-stacked FITS, no darks]"
            if stack_mode == "stacked_panels" else ""
        )
        lines = [f"Megastack — {obj}{step_label}{mode_label}", ""]
        total_lights = 0
        for flt, sessions in groups.items():
            n_lights = sum(len(s.get("lights", [])) for s in sessions)
            n_darks  = sum(s.get("darks", {}).get("count", 0) for s in sessions)
            total_lights += n_lights
            lines.append(f"  [{flt}]  {len(sessions)} session(s)  ·  {n_lights} lights  ·  {n_darks} darks")
        lines += [
            "",
            f"Mode: {'single filter — simple Megastack' if single else f'multi-filter → {hint}'}",
            "",
            f"Siril home: {cwd}",
        ]
        if step:
            lines += [
                "",
                f"⚡ Already processed up to: {step}",
                "Buttons for completed steps are disabled.",
            ]
        else:
            lines += [
                "",
                "Lights will be copied to  lights_<filter>/",
                "Darks  will be copied to  darks_<filter>/",
            ]

        reply = QMessageBox.question(
            self, "Load Dwarfium Megastack", "\n".join(lines),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if step in ("copied", "stacked"):
            # Files already copied — just regenerate the scripts so
            # build_sessions_from_scripts has the lines it needs to resume
            # from the right step without recopying anything.
            cwd = self.current_working_directory
            self._last_generated_scripts = self._generate_megastack_scripts(data, cwd)
            # Only enable Build Sessions if there are scripts left to run
            self.build_sessions_btn.setDisabled(step == "stacked" and not any(
                os.path.basename(p).startswith("02_combine_")
                for p, _ in self._last_generated_scripts
            ))
        elif step == "combined":
            # Everything done — nothing left to run
            self._last_generated_scripts = []
            self.build_sessions_btn.setDisabled(True)
        else:
            # step is None — normal flow: copy files then generate scripts
            self._start_copy_megastack_json(data)

    def _start_copy_megastack_json(self, data: dict):
        """Copy lights and darks for each filter group, then generate .ssf scripts."""
        cwd    = self.current_working_directory
        self._release_working_dir()   # its folders are deleted below
        groups = data.get("sessions_by_filter", {})
        single = data.get("single_filter", True)
        hint   = data.get("combination_hint") or ("single" if single else "manual")
        obj    = data.get("object", "Unknown").replace(" ", "_")

        pairs = []

        for flt, sessions in groups.items():
            flt_safe   = flt.replace(" ", "_").replace("/", "_")
            lights_dir = os.path.join(cwd, f"lights_{flt_safe}")
            darks_dir  = os.path.join(cwd, f"darks_{flt_safe}")

            # Clear and recreate
            if os.path.exists(lights_dir):
                shutil.rmtree(lights_dir)
            os.makedirs(lights_dir, exist_ok=True)

            # Decide, same as _generate_megastack_scripts, whether this
            # group's pipeline will be the "pre-stacked" one (no
            # calibrate/debayer) or the "raw" one (calibrate/debayer).
            # Every session already carries an accurate pre_stacked flag
            # (RESTACKED_ sessions always have it set to True), so this is
            # simply "does every session in the group already have no raw
            # lights left to calibrate". Do NOT filter RESTACKED_ out of
            # this check first — a group made up only of RESTACKED_
            # session(s) must count as fully pre-stacked too, otherwise it
            # gets wrongly treated as "mixed" and every session in it is
            # skipped.
            all_pre_stacked = bool(sessions) and all(
                s.get("pre_stacked") for s in sessions
            )

            # Lights — prefix with session index to avoid name collisions
            # (Dwarf sessions all contain 0000.fits, 0001.fits, ... and mosaic
            #  panels reuse the same names too)
            skipped_pre_stacked = []
            for s_idx, sess in enumerate(sessions, 1):
                sess_pre_stacked = bool(sess.get("pre_stacked")) or str(
                    sess.get("session_name", "")
                ).startswith("RESTACKED_")
                if sess_pre_stacked and not all_pre_stacked:
                    # This group will run the raw calibrate/-debayer
                    # pipeline (because at least one other session in the
                    # group still has raw lights). Copying an already
                    # fully-processed FITS (RESTACKED_ or
                    # stack_mode="stacked_panels") into that same folder
                    # would get it re-debayered/re-calibrated and corrupted.
                    # Skip it instead, and tell the user.
                    if sess.get("lights"):
                        skipped_pre_stacked.append(sess.get("session_name", ""))
                    continue
                for f in sess.get("lights", []):
                    # For mosaic panels keep the panel name in the prefix
                    parent = os.path.basename(os.path.dirname(f))
                    sess_name = os.path.basename(sess.get("session_dir", "") or "")
                    if parent and sess_name and parent != sess_name:
                        new_name = f"s{s_idx:02d}_{parent}_{os.path.basename(f)}"
                    else:
                        new_name = f"s{s_idx:02d}_{os.path.basename(f)}"
                    pairs.append((f, os.path.join(lights_dir, new_name)))

            if skipped_pre_stacked:
                self.siril.log(
                    f"[{flt}] WARNING: already-stacked session(s) "
                    f"{skipped_pre_stacked} were NOT included — this group "
                    "still has raw (non-stacked) sessions and would run the "
                    "calibrate/debayer pipeline, which would corrupt an "
                    "already-processed FITS. Run the already-stacked "
                    "session(s) as a separate Megastack (or restack the "
                    "others too) to combine everything together.",
                    LogColor.SALMON,
                )

            # Darks — deduplicate by source path (sessions often share the
            # same dark-library files); keep original names.
            # Also exclude RESTACKED_ sessions from dark aggregation — they
            # carry no lights and no relevant darks.
            all_darks, seen = [], set()
            for sess in sessions:
                if str(sess.get("session_name", "")).startswith("RESTACKED_"):
                    continue
                for f in sess.get("darks", {}).get("files", []):
                    if f not in seen:
                        seen.add(f)
                        all_darks.append(f)

            n_darks   = len(all_darks)
            has_darks = n_darks > 0

            # Warn if sessions in this group have different exposures —
            # a single master dark would not match all of them.
            # RESTACKED_ and other pre_stacked sessions are excluded:
            # they're already-stacked results (darks already applied, or
            # not needed for stack_mode="stacked_panels"), and contribute
            # no lights to calibrate against a master dark anyway.
            exposures = {
                s.get("exp_s")
                for s in sessions
                if s.get("exp_s") is not None
                and not s.get("pre_stacked")
                and not str(s.get("session_name", "")).startswith("RESTACKED_")
            }
            if len(exposures) > 1:
                self.siril.log(
                    f"[{flt}] WARNING: mixed exposures {sorted(exposures)}s — "
                    "darks may not match all sessions",
                    LogColor.SALMON,
                )

            if all_darks:
                if os.path.exists(darks_dir):
                    shutil.rmtree(darks_dir)
                os.makedirs(darks_dir, exist_ok=True)
                for f in all_darks:
                    pairs.append((f, darks_dir))

        if not pairs:
            QMessageBox.information(self, "Nothing to copy", "No files to copy.")
            return

        # Generate .ssf scripts
        self._last_generated_scripts = self._generate_megastack_scripts(data, cwd)

        # Copy files
        self.progressbar.setMaximum(len(pairs))
        self.progressbar.setValue(0)
        self.progress_label.setText(f"0 / {len(pairs)}")
        self.json_btn.setDisabled(True)
        self.copy_btn.setDisabled(True)
        self.copyThread = CopyMultiThread(pairs=pairs)
        self.copyThread.progress.connect(self.progress_update)
        self.copyThread.done.connect(self._copy_from_json_done)
        self.copyThread.start()

    def _generate_megastack_scripts(self, data: dict, cwd: str):
        """Generate one .ssf per filter group + one combination script if needed.

        Uses official Siril script syntax (validated against Siril 1.2+ docs):
          - convert <seqname> operates on current directory → cd into folder first
          - dual-band extraction: seqextract_HaOIII on calibrated CFA sequence (before debayer/stack)
          - rgbcomp uses positional args: rgbcomp red green blue -out=...
          - LRGB: rgbcomp -lum=image rgb_image -out=...
        """
        groups = data.get("sessions_by_filter", {})
        single = data.get("single_filter", True)
        hint   = data.get("combination_hint") or ("single" if single else "manual")
        obj    = data.get("object", "Unknown").replace(" ", "_")

        generated_scripts = []  # list of (ssf_path, lines) in execution order

        def _is_dualband(flt: str) -> bool:
            return "dual" in flt.lower()

        # ── Per-filter stack scripts ──────────────────────────────────────────
        for flt, sessions in groups.items():
            flt_safe   = flt.replace(" ", "_").replace("/", "_")
            n_sessions = len(sessions)
            dualband   = _is_dualband(flt)

            # Exclude RESTACKED_ sessions from dark/light accounting — they
            # contribute no lights to calibrate and no relevant darks.
            normal_sessions = [
                s for s in sessions
                if not str(s.get("session_name", "")).startswith("RESTACKED_")
            ]
            # Count unique dark files across normal sessions
            dark_files_seen = set()
            for s in normal_sessions:
                for f in s.get("darks", {}).get("files", []):
                    dark_files_seen.add(f)
            n_darks   = len(dark_files_seen)
            has_darks = n_darks > 0

            # True when every session in this group is already fully
            # processed (calibrated + debayered + stacked) — e.g. mosaic
            # panels generated with stack_mode="stacked_panels",
            # RESTACKED_ sessions, or sessions from
            # generate_siril_megastack_json_manual. These must NOT be run
            # through calibrate/debayer again.
            # Checked across ALL sessions (not just normal_sessions): a
            # group made up entirely of RESTACKED_ session(s) must count as
            # fully pre-stacked too — excluding them here would make
            # `sessions` look empty/mixed and wrongly trigger the raw
            # pipeline (which then excludes them all with a warning).
            all_pre_stacked = bool(sessions) and all(
                s.get("pre_stacked") for s in sessions
            )
            mixed_pre_stacked = (
                not all_pre_stacked
                and any(s.get("pre_stacked") for s in sessions)
            )
            if mixed_pre_stacked:
                self.siril.log(
                    f"[{flt}] WARNING: mixes already-stacked sessions/panels with "
                    "raw ones — falling back to the raw pipeline for the whole "
                    "group. Consider running pre-stacked and raw sessions as "
                    "separate Megastacks.",
                    LogColor.SALMON,
                )

            proc = os.path.join(cwd, f"process_{flt_safe}")

            # True when the pre-stacked lights in this group actually come
            # from mosaic panels (different pointings covering a wider
            # field) rather than repeat sessions of the same framing —
            # these need astrometric mosaic alignment, not a plain
            # integration stack, or the result would be cropped down to
            # the overlap between panels instead of the full mosaic.
            has_mosaic_panels = any(s.get("is_mosaic") for s in sessions)

            if all_pre_stacked and dualband:
                self.siril.log(
                    f"[{flt}] WARNING: already-stacked panels/sessions in a "
                    "dual-band filter group aren't auto-split into Ha/OIII — "
                    "falling back to the standard pipeline. Verify the result "
                    "manually or split the Ha/OIII stacks before combining.",
                    LogColor.SALMON,
                )

            if all_pre_stacked and not dualband and has_mosaic_panels:
                # Already-stacked mosaic panels: astrometric plate solving
                # + max-framing registration, same approach as
                # build_mosaic_from_restacked, so the final canvas covers
                # the full mosaic footprint instead of just the overlap
                # between panels. Requires Siril 1.4.0+.
                stack_line = (
                    f"stack r_light rej 3 3 -norm=addscale -maximize "
                    f"-overlap_norm -output_norm -rgb_equal"
                )
                if self.feather_checkbox.isChecked():
                    stack_line += f" -feather={self.feather_spinbox.value()}"
                stack_line += f" -out=../stack_{flt_safe}"

                lines = [
                    f"# Dwarfium Megastack — {obj} — filter: {flt}",
                    f"# {n_sessions} session(s) — already-stacked mosaic panels: "
                    "astrometric mosaic alignment (plate solve + max framing), "
                    "no calibrate/debayer",
                    "requires 1.4.0",
                    "setext fit",
                    f'cd "{cwd}"',
                    "",
                    "# Convert already-stacked panel FITS (no debayer needed)",
                    f"cd lights_{flt_safe}",
                    f"convert light -out=../process_{flt_safe}",
                    "cd ..",
                    "",
                    f"cd process_{flt_safe}",
                    "# Plate-solve each panel (local Gaia DR3 catalogue) then",
                    "# register with max framing so the canvas grows to fit",
                    "# every panel instead of shrinking to their overlap",
                    "seqplatesolve light -catalog=localgaia",
                    "seqapplyreg light -framing=max",
                    "",
                    f"# PYTHON_CLEANUP {os.path.join(proc, 'light_*.fit')}",
                    "",
                    stack_line,
                    "",
                    f"# PYTHON_CLEANUP {os.path.join(proc, 'r_light_*.fit')}",
                    "cd ..",
                    "",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, f'process_{flt_safe}')}",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, f'lights_{flt_safe}')}",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, f'darks_{flt_safe}')}",
                ]
                ssf_path = os.path.join(cwd, f"01_stack_{flt_safe}.ssf")
                with open(ssf_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))
                self.siril.log(f"Script saved: {ssf_path}", LogColor.GREEN)
                generated_scripts.append((ssf_path, lines))
                continue

            if all_pre_stacked and not dualband and not has_mosaic_panels:
                # Already-stacked sessions of the same framing (not a
                # mosaic) — e.g. several nights each already stacked with
                # stack_mode="stacked_panels". A plain integration stack is
                # enough: just convert (no -debayer), register, and stack.
                lines = [
                    f"# Dwarfium Megastack — {obj} — filter: {flt}",
                    f"# {n_sessions} session(s) — already-stacked sessions: "
                    "convert + register + stack only (no calibrate/debayer)",
                    "requires 1.2.0",
                    "setext fit",
                    f'cd "{cwd}"',
                    "",
                    "# Convert already-stacked light frames (no debayer needed)",
                    f"cd lights_{flt_safe}",
                    f"convert light -out=../process_{flt_safe}",
                    "cd ..",
                    "",
                    f"cd process_{flt_safe}",
                    "register light",
                    "",
                    f"# PYTHON_CLEANUP {os.path.join(proc, 'light_*.fit')}",
                    "",
                    f"stack r_light rej 3 3 -norm=addscale -out=../stack_{flt_safe}",
                    "",
                    f"# PYTHON_CLEANUP {os.path.join(proc, 'r_light_*.fit')}",
                    "cd ..",
                    "",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, f'process_{flt_safe}')}",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, f'lights_{flt_safe}')}",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, f'darks_{flt_safe}')}",
                ]
                ssf_path = os.path.join(cwd, f"01_stack_{flt_safe}.ssf")
                with open(ssf_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))
                self.siril.log(f"Script saved: {ssf_path}", LogColor.GREEN)
                generated_scripts.append((ssf_path, lines))
                continue

            lines = [
                f"# Dwarfium Megastack — {obj} — filter: {flt}",
                f"# {n_sessions} session(s) — generated by Dwarfium Scope Archive",
                "requires 1.2.0",
                "setext fit",
                f'cd "{cwd}"',
                "",
                "# Convert light frames",
                f"cd lights_{flt_safe}",
                f"convert light -out=../process_{flt_safe}",
                f"cd ..",
                "",
            ]
            if has_darks:
                if n_darks >= 2:
                    lines += [
                        "# Convert and stack darks into master dark",
                        f"cd darks_{flt_safe}",
                        f"convert dark -out=../process_{flt_safe}",
                        "cd ..",
                        "",
                    ]
                else:
                    # Single dark file — it's already a pre-stacked master
                    # (e.g. dark_exp_45..._stack_8.fits from DwarfLab).
                    # Convert it to a .fit so calibrate can reference it by
                    # the fixed name master_dark.
                    lines += [
                        "# Single pre-stacked dark — convert and save as master dark",
                        f"cd darks_{flt_safe}",
                        f"convert dark -out=../process_{flt_safe}",
                        "cd ..",
                        "",
                    ]
            lines += [
                f"cd process_{flt_safe}",
                "",
            ]
            if has_darks:
                if n_darks >= 2:
                    lines += [
                        "# Stack darks into master dark",
                        "stack dark rej 3 3 -nonorm -out=master_dark",
                        "",
                    ]
                else:
                    # Single dark already converted — load and save as master_dark
                    lines += [
                        "# Rename single dark to master_dark",
                        "load dark_00001",
                        "save master_dark",
                        "",
                    ]

            if dualband:
                # Dual-Band: calibrate WITHOUT debayer, extract Ha/OIII per frame, stack each
                seq = "pp_light" if has_darks else "light"
                proc = os.path.join(cwd, f"process_{flt_safe}")
                lines += [
                    "# Calibrate (keep CFA — no debayer before Ha/OIII extraction)",
                    "calibrate light -dark=master_dark -cc=dark -cfa" if has_darks
                        else "# (no darks — skipping calibration)",
                    "",
                    f"# PYTHON_CLEANUP {os.path.join(proc, 'light_*.fit')}",
                    f"# PYTHON_CLEANUP {os.path.join(proc, 'dark_*.fit')}",
                    f"# PYTHON_CLEANUP {os.path.join(proc, 'master_dark.fit')}",
                    "",
                    "# Extract Ha and OIII from each calibrated frame",
                    f"seqextract_HaOIII {seq}",
                    "",
                    f"# PYTHON_CLEANUP {os.path.join(proc, 'pp_light_*.fit')}",
                    "",
                    "# Register and stack the Ha sequence",
                    f"register Ha_{seq}",
                    f"stack r_Ha_{seq} rej 3 3 -norm=addscale -out=../stack_{flt_safe}_Ha",
                    "",
                    f"# PYTHON_CLEANUP {os.path.join(proc, f'Ha_{seq}_*.fit')}",
                    f"# PYTHON_CLEANUP {os.path.join(proc, f'r_Ha_{seq}_*.fit')}",
                    "",
                    "# Register and stack the OIII sequence",
                    f"register OIII_{seq}",
                    f"stack r_OIII_{seq} rej 3 3 -norm=addscale -out=../stack_{flt_safe}_OIII",
                    "",
                    f"# PYTHON_CLEANUP {os.path.join(proc, f'OIII_{seq}_*.fit')}",
                    f"# PYTHON_CLEANUP {os.path.join(proc, f'r_OIII_{seq}_*.fit')}",
                    "cd ..",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, f'process_{flt_safe}')}",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, f'lights_{flt_safe}')}",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, f'darks_{flt_safe}')}",
                ]
            else:
                # Broadband
                proc = os.path.join(cwd, f"process_{flt_safe}")
                if has_darks:
                    lines += [
                        "# Calibrate with master dark and debayer",
                        "calibrate light -dark=master_dark -cc=dark -cfa -equalize_cfa -debayer",
                        "",
                        f"# PYTHON_CLEANUP {os.path.join(proc, 'light_*.fit')}",
                        f"# PYTHON_CLEANUP {os.path.join(proc, 'dark_*.fit')}",
                        f"# PYTHON_CLEANUP {os.path.join(proc, 'master_dark.fit')}",
                        "",
                        "register pp_light",
                        "",
                        f"# PYTHON_CLEANUP {os.path.join(proc, 'pp_light_*.fit')}",
                        "",
                        f"stack r_pp_light rej 3 3 -norm=addscale -out=../stack_{flt_safe}",
                        "",
                        f"# PYTHON_CLEANUP {os.path.join(proc, 'r_pp_light_*.fit')}",
                    ]
                else:
                    # No darks: calibrate requires a master frame, so debayer
                    # must happen at conversion time instead. Rebuild sequence.
                    lines = [
                        f"# Dwarfium Megastack — {obj} — filter: {flt}",
                        f"# {n_sessions} session(s) — no darks: debayer at convert",
                        "requires 1.2.0",
                        "setext fit",
                        f'cd "{cwd}"',
                        "",
                        f"cd lights_{flt_safe}",
                        f"convert light -debayer -out=../process_{flt_safe}",
                        "cd ..",
                        "",
                        f"cd process_{flt_safe}",
                        "register light",
                        "",
                        f"# PYTHON_CLEANUP {os.path.join(proc, 'light_*.fit')}",
                        "",
                        f"stack r_light rej 3 3 -norm=addscale -out=../stack_{flt_safe}",
                        "",
                        f"# PYTHON_CLEANUP {os.path.join(proc, 'r_light_*.fit')}",
                    ]
                lines.append("cd ..")
                lines += [
                    "",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, f'process_{flt_safe}')}",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, f'lights_{flt_safe}')}",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, f'darks_{flt_safe}')}",
                ]

            ssf_path = os.path.join(cwd, f"01_stack_{flt_safe}.ssf")
            with open(ssf_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            self.siril.log(f"Script saved: {ssf_path}", LogColor.GREEN)
            generated_scripts.append((ssf_path, lines))

        # ── Combination script ────────────────────────────────────────────────
        if not single and hint not in ("single", "manual"):
            filter_keys = list(groups.keys())
            lines = [
                f"# Dwarfium Megastack — {obj} — combination: {hint}",
                "# Run AFTER all 01_stack_*.ssf scripts",
                "requires 1.2.0",
                f'cd "{cwd}"',
                "",
            ]

            if hint == "HaRGB":
                dual  = next((k for k in filter_keys if _is_dualband(k)), filter_keys[0])
                astro = next((k for k in filter_keys if k != dual), filter_keys[-1])
                d_safe = dual.replace(" ", "_").replace("/", "_")
                a_safe = astro.replace(" ", "_").replace("/", "_")
                # Detect whether the Duo-Band stack script used seqextract_HaOIII
                # (producing stack_Duo-Band_Ha + _OIII mono files) or a normal
                # debayer pipeline (producing a single stack_Duo-Band.fit RGB).
                # Check the already-generated 01_stack script lines for this filter.
                dual_was_extracted = any(
                    "seqextract_HaOIII" in "\n".join(l)
                    for p, l in generated_scripts
                    if d_safe in os.path.basename(p)
                )
                # Retrieve the Ha blend ratio from the UI widget
                ha_ratio  = round(self.ha_blend_spinbox.value(), 2)
                rgb_ratio = round(1.0 - ha_ratio, 2)
                single_dwarf = data.get("single_dwarf", True)

                # ── Decide alignment strategy ─────────────────────────────
                # Use per-session RA/DEC if available to detect significant
                # field offsets (different pointings), which need astrometric
                # alignment regardless of whether it's the same Dwarf.
                # Fallback: use single_dwarf flag only.
                def _mean_radec(sessions):
                    ras  = [s["ra"]  for s in sessions if s.get("ra")  is not None]
                    decs = [s["dec"] for s in sessions if s.get("dec") is not None]
                    return (sum(ras)/len(ras)  if ras  else None,
                            sum(decs)/len(decs) if decs else None)

                ra_a, dec_a = _mean_radec(groups.get(astro, []))
                ra_d, dec_d = _mean_radec(groups.get(dual,  []))
                if ra_a is not None and ra_d is not None:
                    delta_ra  = abs(ra_a  - ra_d)
                    delta_dec = abs(dec_a - dec_d)
                    # > 0.5° offset → fields differ enough to need plate solving
                    needs_platesolve = delta_ra > 0.5 or delta_dec > 0.5
                else:
                    # No per-session coords — fall back to Dwarf comparison
                    needs_platesolve = not single_dwarf

                # ── Alignment step ────────────────────────────────────────
                # The two stacks must be aligned before combining.
                # - same Dwarf (single_dwarf) → star-based registration, fast
                # - different Dwarf(s)        → astrometric plate solving,
                #   handles different pixel scales / fields of view
                ha_stack  = f"stack_{d_safe}_Ha" if dual_was_extracted else f"stack_{d_safe}"
                lines += [
                    f"# ── Align {a_safe} and {d_safe} stacks before combining ──",
                ]
                # Create the alignment sub-folder now (at script generation time,
                # in Python) so it exists before any Siril command runs.
                # Wipe it first: if a previous attempt for this object failed
                # or was interrupted before its "# PYTHON_CLEANUP align_tmp"
                # ran, stale FITS files left over from that run would get
                # swept into "link align_" alongside img_1/img_2, producing
                # a sequence with more frames than expected and breaking
                # "register align_" (file-not-found on align_0000N.fit).
                align_tmp = os.path.join(cwd, "align_tmp")
                if os.path.isdir(align_tmp):
                    shutil.rmtree(align_tmp)
                os.makedirs(align_tmp, exist_ok=True)

                if not needs_platesolve:
                    lines += [
                        f"# Same Dwarf / close field — star-based registration (fast, no catalogue needed)",
                        f"# Work in a dedicated sub-folder so link/convert only sees these two stacks",
                        f'cd "{cwd}"',
                        f"load stack_{a_safe}",
                        f'save "align_tmp/img_1"',
                        f"load {ha_stack}",
                        f'save "align_tmp/img_2"',
                        f"cd align_tmp",
                        f"link align_",
                        f"register align_",
                        f"seqapplyreg align_",
                        f"",
                        f"# r_align_00001 = {a_safe}, r_align_00002 = {d_safe}",
                        f"# Split aligned Astro into R/G/B",
                        f"load r_align_00001",
                        f"split astro_r astro_g astro_b",
                        f"",
                    ]
                    if dual_was_extracted:
                        lines += [
                            f"# Aligned Duo-Band Ha mono — save back to CWD",
                            f"load r_align_00002",
                            f'save "aligned_ha"',
                            f'cd "{cwd}"',
                            f"",
                        ]
                        ha_src = "align_tmp/aligned_ha"
                    else:
                        lines += [
                            f"# Split aligned Duo-Band RGB to extract Ha (R channel)",
                            f"load r_align_00002",
                            f"split duoband_ha duoband_g duoband_b",
                            f'cd "{cwd}"',
                            f"",
                        ]
                        ha_src = "align_tmp/duoband_ha"
                else:
                    lines += [
                        f"# Different Dwarf / field offset > 0.5° — astrometric registration (requires Gaia local)",
                        f"requires 1.4.0",
                        f'cd "{cwd}"',
                        f"load stack_{a_safe}",
                        f'save "align_tmp/img_1"',
                        f"load {ha_stack}",
                        f'save "align_tmp/img_2"',
                        f"cd align_tmp",
                        f"link align_",
                        f"seqplatesolve align_ -catalog=localgaia",
                        f"seqapplyreg align_ -framing=max",
                        f"",
                        f"# r_align_00001 = {a_safe}, r_align_00002 = {d_safe}",
                        f"load r_align_00001",
                        f"split astro_r astro_g astro_b",
                        f"",
                    ]
                    if dual_was_extracted:
                        lines += [
                            f"load r_align_00002",
                            f'save "aligned_ha"',
                            f'cd "{cwd}"',
                            f"",
                        ]
                        ha_src = "align_tmp/aligned_ha"
                    else:
                        lines += [
                            f"load r_align_00002",
                            f"split duoband_ha duoband_g duoband_b",
                            f'cd "{cwd}"',
                            f"",
                        ]
                        ha_src = "align_tmp/duoband_ha"

                f_astro_r = "align_tmp/astro_r"
                lines += [
                    f"# Blend Ha with Astro R: R = Ha×{ha_ratio} + Astro_R×{rgb_ratio}",
                    f"# This preserves natural star colors while boosting nebula signal",
                    f'pm "${ha_src}$ * {ha_ratio} + ${f_astro_r}$ * {rgb_ratio}" -rescale',
                    f"save ha_blended",
                    "",
                    f"rgbcomp ha_blended ./align_tmp/astro_g ./align_tmp/astro_b",
                    f"# rgbcomp always outputs 'composed_rgb' — rename it",
                    f"load composed_rgb",
                    f"save final_{obj}_HaRGB",
                    "",
                    f"# Cleanup intermediate files — keep only stack_*.fit and final_*.fit",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, 'align_tmp')}",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, 'ha_blended.fit')}",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, 'composed_rgb.fit')}",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, 'astro_r.fit')}",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, 'astro_g.fit')}",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, 'astro_b.fit')}",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, 'duoband_ha.fit')}",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, 'duoband_g.fit')}",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, 'duoband_b.fit')}",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, 'aligned_ha.fit')}",
                    "",
                    f"load final_{obj}_HaRGB",
                    "autostretch",
                    f"savejpg final_{obj}_HaRGB 95",
                ]

            elif hint == "HOO_stars":
                dual = next((k for k in filter_keys if _is_dualband(k)), filter_keys[0])
                uvir = next((k for k in filter_keys if k != dual), filter_keys[-1])
                d_safe = dual.replace(" ", "_").replace("/", "_")
                u_safe = uvir.replace(" ", "_").replace("/", "_")
                lines += [
                    f"# HOO: R = Ha, G = OIII, B = OIII (both mono, from 01_stack_{d_safe}.ssf)",
                    f"rgbcomp stack_{d_safe}_Ha stack_{d_safe}_OIII stack_{d_safe}_OIII",
                    f"load composed_rgb",
                    f"save final_{obj}_HOO",
                    "",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, 'composed_rgb.fit')}",
                    "",
                    f"load final_{obj}_HOO",
                    "autostretch",
                    f"savejpg final_{obj}_HOO 95",
                    "",
                    f"# Optional star blend: stack_{u_safe} (UV/IR Cut) has natural star colors.",
                    f"# In Siril GUI use PixelMath, e.g.:  $final_{obj}_HOO$ * 0.85 + $stack_{u_safe}$ * 0.15",
                    f"# Or use StarNet to extract stars from stack_{u_safe} and screen-blend them.",
                ]

            elif hint == "RGB_combine":
                # Astro LP (color) + UV/IR Cut (color) → use UV/IR luminance via its green channel
                astro = next((k for k in filter_keys if "astro" in k.lower()), filter_keys[0])
                uvir  = next((k for k in filter_keys if k != astro), filter_keys[-1])
                a_safe = astro.replace(" ", "_").replace("/", "_")
                u_safe = uvir.replace(" ", "_").replace("/", "_")
                lines += [
                    f"# Extract a luminance from the UV/IR Cut stack (green channel ≈ luminance)",
                    f"load stack_{u_safe}",
                    f"split uvir_r uvir_g uvir_b",
                    "",
                    f"# LRGB: luminance from UV/IR Cut applied to the Astro color stack",
                    f"rgbcomp -lum=uvir_g stack_{a_safe}",
                    f"load composed_rgb",
                    f"save final_{obj}_LRGB",
                    "",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, 'composed_rgb.fit')}",
                    f"# PYTHON_CLEANUP {os.path.join(cwd, 'uvir_g.fit')}",
                    "",
                    f"load final_{obj}_LRGB",
                    "autostretch",
                    f"savejpg final_{obj}_LRGB 95",
                ]

            ssf_path = os.path.join(cwd, f"02_combine_{hint}.ssf")
            with open(ssf_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            self.siril.log(f"Combination script saved: {ssf_path}", LogColor.GREEN)
            generated_scripts.append((ssf_path, lines))

        elif hint == "manual":
            self.siril.log(
                "Manual combination — run the stack scripts then combine the stacked files in Siril GUI.",
                LogColor.SALMON,
            )

        return generated_scripts

    def build_sessions_from_scripts(self):
        """Run the generated 01_stack_*.ssf (and 02_combine_*.ssf, if any)
        scripts directly in this Siril session, reusing the exact same lines
        that were written to disk by _generate_megastack_scripts — so this
        always stays in sync with whatever script logic produces.
        """
        scripts = self._last_generated_scripts
        if not scripts:
            QMessageBox.warning(
                self, "No scripts available",
                "Load a Dwarfium JSON and copy files first to generate the scripts."
            )
            return

        # Filter out already-completed scripts based on current step
        current_step = (self._last_megastack_data or {}).get("step")
        if current_step == "stacked":
            # Stacks done — only run the combination script if present
            scripts_to_run = [(p, l) for p, l in scripts
                              if os.path.basename(p).startswith("02_combine_")]
            if not scripts_to_run:
                QMessageBox.information(self, "Nothing to do",
                    "Stacks already done and no combination script to run.")
                return
        else:
            scripts_to_run = scripts

        reply = QMessageBox.question(
            self, "Build Sessions",
            f"This will run {len(scripts_to_run)} script(s) directly in this Siril session:\n\n"
            + "\n".join(os.path.basename(p) for p, _ in scripts_to_run)
            + "\n\nProceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.build_sessions_btn.setDisabled(True)
        self.json_btn.setDisabled(True)
        self.copy_btn.setDisabled(True)
        self.mosaic_btn.setDisabled(True)

        ran_ok = True
        self._build_log_path = os.path.join(self.current_working_directory, "build_sessions.log")
        self._build_log(f"=== Build Sessions {datetime.now():%Y-%m-%d %H:%M:%S}: "
                        + ", ".join(os.path.basename(p) for p, _ in scripts_to_run), new=True)
        for ssf_path, lines in scripts_to_run:
            ssf_name = os.path.basename(ssf_path)
            self.siril.log(f"[build] Running {ssf_name}…", LogColor.BLUE)
            for raw_line in lines:
                line = raw_line.strip()
                if not line:
                    continue
                # A sequence's images deleted once the next step made its own:
                # # PYTHON_CLEANUP_SEQ <folder>|<prefix> - before PYTHON_CLEANUP
                # (paths / globs, the stacking scripts'), which took these lines
                # and found nothing (user's 509-image run, Oct 2026)
                if line.startswith("# PYTHON_CLEANUP_SEQ"):
                    folder, prefix = line[len("# PYTHON_CLEANUP_SEQ"):].strip().split("|")
                    self._build_log(line)
                    removed, size, failed = self._remove_sequence_files(folder, prefix)
                    self._build_log(f"  {removed} {prefix}* file(s) removed ({size / 1e9:.1f} GB)"
                                    + (f", {failed} still in use" if failed else ""))
                    continue
                # Python-side cleanup: # PYTHON_CLEANUP <path_or_glob>
                # Executed by Python (not sent to Siril) to free disk space
                # as processing progresses. Supports glob patterns (*) and
                # plain paths (files or directories).
                if line.startswith("# PYTHON_CLEANUP"):
                    cleanup_arg = line[len("# PYTHON_CLEANUP"):].strip()
                    if cleanup_arg:
                        import glob as _glob
                        targets = _glob.glob(cleanup_arg)
                        if not targets:
                            targets = [cleanup_arg]  # try as literal path
                        for target in targets:
                            try:
                                if os.path.isdir(target):
                                    shutil.rmtree(target)
                                    self.siril.log(f"[cleanup] Removed dir: {target}", LogColor.BLUE)
                                elif os.path.isfile(target):
                                    os.remove(target)
                                    self.siril.log(f"[cleanup] Removed: {target}", LogColor.BLUE)
                            except Exception as e:
                                self.siril.log(f"[cleanup] Could not remove {target}: {e}", LogColor.SALMON)
                    continue
                # Python-side photometry: # PYTHON_PHOTOMETRY <folder>|<sequence>|<saturation>
                # Python-side plate solve (the sequence, then image by image): # PYTHON_PLATESOLVE <folder>|<sequence>|<args>
                if line.startswith("# PYTHON_PLATESOLVE"):
                    self._build_log(line)
                    folder, seq_name, solve_args = line[len("# PYTHON_PLATESOLVE"):].strip().split("|")
                    if not self._platesolve_images(folder, seq_name, solve_args.split()):
                        ran_ok = False
                        break
                    continue
                if line.startswith("# PYTHON_PHOTOMETRY_OPTIONS"):   # {"keep_saturated": ...}
                    try:
                        self._photometry_options = json.loads(line[len("# PYTHON_PHOTOMETRY_OPTIONS"):].strip() or "{}")
                    except ValueError:
                        self._photometry_options = {}
                    continue
                if line.startswith("# PYTHON_PHOTOMETRY_ROOTS"):   # the other drives, for combine_star_sessions
                    try:
                        self._photometry_roots = json.loads(line[len("# PYTHON_PHOTOMETRY_ROOTS"):].strip() or "[]")
                    except ValueError:
                        self._photometry_roots = []
                    continue
                if line.startswith("# PYTHON_PHOTOMETRY"):
                    self._build_log(line)
                    fields = line[len("# PYTHON_PHOTOMETRY"):].strip().split("|")
                    folder, seq_name, saturation = fields[:3]
                    utc_offset = float(fields[3]) if len(fields) > 3 else 0.0
                    session_dir = fields[4] if len(fields) > 4 else ""
                    astronomy_root = fields[5] if len(fields) > 5 else ""
                    try:   # the session's site, for the airmass
                        site = (float(fields[6]), float(fields[7]), fields[8] if len(fields) > 8 else "")
                    except (IndexError, ValueError):
                        site = None
                    try:
                        s.ensure_installed(["astropy", "matplotlib"])
                        frames = sorted(
                            os.path.join(folder, f) for f in os.listdir(folder)
                            if f.startswith(seq_name + "_") and f.lower().endswith((".fit", ".fits", ".fts"))
                        )
                        def _progress(done, total):
                            # The script's window kept alive, and where it is in Siril's log
                            self.progressbar.setMaximum(max(total, 1))
                            self.progressbar.setValue(done)
                            self.progress_label.setText(f"{done} / {total}")
                            if done == total or done % 10 == 0:
                                self._build_log(f"photometry: {done} / {total} images measured")
                                self.siril.log(f"[photometry] {done} / {total} images measured", LogColor.BLUE)
                            QApplication.processEvents()

                        self.siril.log(f"[photometry] {len(frames)} images to measure", LogColor.BLUE)
                        summary = differential_light_curve(
                            frames, read_compstars_csv(os.path.join(folder, "comparison_stars.csv")),
                            os.path.join(folder, f"light_curve_{seq_name}.csv"),
                            saturation=float(saturation) or None, utc_offset_h=utc_offset,
                            progress=_progress, site=site,
                            keep_saturated=bool(getattr(self, "_photometry_options", {}).get("keep_saturated")),
                            session_name=os.path.basename(os.path.normpath(session_dir)) if session_dir else "",
                        )
                        stars = read_compstars_csv(os.path.join(folder, "comparison_stars.csv"))
                        self._build_log("\n".join(summary))
                        failed, archive_error = [], None
                        try:
                            archived = archive_photometry(folder, seq_name, session_dir,
                                                          stars[0]["name"] if stars else "target",
                                                          extra=(ssf_path, self._build_log_path),
                                                          root=astronomy_root, failed=failed)
                        except OSError as e:
                            archived, archive_error = None, e
                            summary.append(f"  results not archived: {e}")
                        for name, e in failed:
                            summary.append(f"  {name} not updated - open in another program (Excel, an image "
                                           f"viewer)? Close it and run again ({e})")
                        if archived:
                            summary.append(f"  archived with the session -> {archived}")
                            try:   # with the star's other sessions
                                summary += combine_star_sessions(os.path.dirname(archived),
                                                                 getattr(self, "_photometry_roots", []))
                            except OSError as e:
                                summary.append(f"  sessions not put together - a combined_* file open in another "
                                               f"program (Excel, an image viewer)? Close it and run again ({e})")
                            except Exception as e:
                                summary.append(f"  sessions not put together: {e}")
                        elif session_dir and archive_error is None:
                            summary.append(f"  not archived: session folder not reachable ({session_dir})")
                        for text in summary:
                            self.siril.log(text, LogColor.GREEN)
                        self._last_photometry_summary = summary
                    except Exception as e:
                        self.siril.log(f"[build] Photometry failed: {e}", LogColor.RED)
                        ran_ok = False
                        break
                    continue
                if line.startswith("#"):
                    continue
                try:
                    args = shlex.split(line)
                except ValueError as e:
                    self.siril.log(f"[build] Could not parse line '{line}': {e}", LogColor.RED)
                    ran_ok = False
                    break
                if not args:
                    continue
                # Siril's command parser re-tokenizes the reconstructed
                # command line and splits on whitespace, so any argument
                # containing a space (e.g. a path under "Test Siril") must
                # be re-quoted here, same as it was originally in the .ssf
                # text — shlex.split() above already stripped those quotes.
                quoted_args = [f'"{a}"' if " " in a else a for a in args]
                self._build_log(line)
                try:
                    self._siril_cmd(*quoted_args)
                except (s.CommandError, s.SirilError) as e:   # refused, or Siril no longer answering
                    self.siril.log(f"[build] Command '{line}' failed: {e}", LogColor.RED)
                    self._build_log(f"  failed: {e}")
                    ran_ok = False
                    break
            if not ran_ok:
                break
            # Update step after each script completes successfully
            if ssf_name.startswith("01_stack_"):
                self._save_step("stacked")
            elif ssf_name.startswith("02_combine_"):
                self._save_step("combined")

        if not ran_ok:
            # A script stopped before its own "cd ..": Siril back to the working directory
            self._release_working_dir()
        self.build_sessions_btn.setDisabled(False)
        self.json_btn.setDisabled(False)
        self.copy_btn.setDisabled(False)
        self.mosaic_btn.setDisabled(not bool(self._last_megastack_data))

        if ran_ok:
            self.siril.log("[build] All scripts completed successfully.", LogColor.GREEN)
            summary = getattr(self, "_last_photometry_summary", None)
            self._last_photometry_summary = None
            QMessageBox.information(self, "Build complete", "All scripts ran successfully."
                                    + ("\n\n" + "\n".join(summary) if summary else ""))
        else:
            QMessageBox.critical(
                self, "Build failed",
                "A command failed while running the scripts.\nCheck the Siril log for details."
            )

    def _build_log(self, text, new=False):
        """One line in build_sessions.log (Siril working directory), written
        and flushed before each command (user-reported Oct 2026: Siril closed
        on a 141-image session, its log gone with it): the last line is where
        it stopped."""
        path = getattr(self, "_build_log_path", None) or os.path.join(self.current_working_directory, "build_sessions.log")
        try:
            with open(path, "w" if new else "a", encoding="utf-8") as f:
                f.write(f"{datetime.now():%H:%M:%S} {text}\n")
                f.flush()
                os.fsync(f.fileno())
        except OSError:
            pass

    def _platesolve_images(self, folder, seq_name, solve_args):
        """platesolve of each image of the sequence, saved with its solution,
        the progress shown between images (Siril's log, build_sessions.log,
        the progress bar). An image that can't be solved is left as it is
        (the photometry skips it). The first solved image is left loaded, for
        findcompstars. False when none could be solved."""
        frames = sorted(
            f for f in os.listdir(folder)
            if f.startswith(seq_name + "_") and f.lower().endswith((".fit", ".fits", ".fts"))
        )
        solved, failed, first_solved = 0, [], None
        self.siril.cmd("cd", f'"{folder}"' if " " in folder else folder)
        # The whole sequence first, by Siril itself (user-tested Oct 2026: 509
        # images in 1 min 41 s, none failed - image by image took half an
        # hour, and Siril's window crashed at the 177th, redrawing each
        # image). It writes the solution in each image's header, read below:
        # what it left unsolved is then tried image by image.
        try:
            self._build_log(f"seqplatesolve {seq_name} {' '.join(solve_args)}")
            self._siril_cmd("seqplatesolve", seq_name, *solve_args)
        except s.SirilError as e:
            if _siril_gone(e):
                raise SirilGone("Plate solve of the sequence stopped.") from e
            self._build_log(f"  seqplatesolve: {e} - image by image")
            self.siril.log(f"[platesolve] seqplatesolve: {e} - image by image", LogColor.SALMON)
        self.siril.cmd("cd", f'"{folder}"' if " " in folder else folder)
        skipped = errors_in_a_row = 0
        for index, frame in enumerate(frames, 1):
            base = os.path.splitext(frame)[0]
            # Solved by an earlier run (resumed after a stop): kept as it is
            cards = {key for _, key, _, _ in read_fits_cards(os.path.join(folder, frame))}
            if "CTYPE1" in cards and ("CD1_1" in cards or "CDELT1" in cards):
                solved, skipped = solved + 1, skipped + 1
                first_solved = first_solved or base
                continue
            # Siril's image closed now and then (a 509-image run stopped at the 95th)
            if (index - skipped) % 25 == 0:
                try:
                    self.siril.cmd("close")
                except s.SirilError:
                    pass
            try:
                self.siril.cmd("load", base)
                self.siril.cmd("platesolve", *solve_args)
                self.siril.cmd("save", base)
                solved += 1
                first_solved = first_solved or base
                errors_in_a_row = 0
            except s.SirilError as e:
                if _siril_gone(e):
                    self._build_log(f"platesolve: Siril gone at image {index} / {len(frames)} "
                                    f"({solved} solved so far)")
                    raise SirilGone(f"Plate solve stopped at image {index} / {len(frames)}, "
                                    f"{solved} solved so far.") from e
                failed.append(frame)
                self.siril.log(f"[platesolve] {frame}: {e}", LogColor.SALMON)
            except Exception as e:   # not Siril's: an image left out, not the whole run
                failed.append(frame)
                errors_in_a_row += 1
                self._build_log(f"  {frame}: {type(e).__name__}: {e}")
                if errors_in_a_row >= 5:
                    self._build_log("platesolve stopped: 5 errors in a row")
                    break
            self.progressbar.setMaximum(max(len(frames), 1))
            self.progressbar.setValue(index)
            self.progress_label.setText(f"{index} / {len(frames)}")
            if index == len(frames) or index % 10 == 0:
                self._build_log(f"platesolve: {index} / {len(frames)} images ({len(failed)} failed"
                                + (f", {skipped} already solved" if skipped else "") + ")")
                self.siril.log(f"[platesolve] {index} / {len(frames)} images ({len(failed)} failed)", LogColor.BLUE)
            QApplication.processEvents()
        if failed:
            self.siril.log(f"[platesolve] not solved, left out: {', '.join(failed)}", LogColor.SALMON)
        if first_solved:
            # The next step (findcompstars) needs a plate solved image loaded
            self.siril.cmd("load", first_solved)
        return solved > 0

    def _remove_sequence_files(self, folder, prefix):
        """The images of the sequence `prefix` (prefix + number .fit/.fits/.fz;
        a link only removes the link) deleted from folder, its .seq kept -
        after the next step used them (Naztronomy's clean_up, user-shared Oct
        2026: 509 images took about 40 GB). Siril's sequence closed first, a
        file still held tried again. (removed, bytes freed, failed)."""
        import time
        try:
            self.siril.cmd("close")
        except s.SirilError:
            pass
        pattern = re.compile(re.escape(prefix) + r"\d+\.(fit|fits|fts)(\.fz)?$", re.IGNORECASE)
        removed = size = failed = 0
        for name in os.listdir(folder):
            if not pattern.match(name):
                continue
            path = os.path.join(folder, name)
            for attempt in range(3):
                try:
                    freed = 0 if os.path.islink(path) else os.path.getsize(path)
                    os.remove(path)
                    removed, size = removed + 1, size + freed
                    break
                except OSError:
                    time.sleep(0.3)
            else:
                failed += 1
        return removed, size, failed

    def _siril_cmd(self, *args):
        """self.siril.cmd(*args) in a background thread, this window kept alive
        meanwhile - the command and its elapsed time shown (user-reported Oct
        2026: on 509 images, calibrate ran for minutes with the window frozen,
        Windows calling it not responding, it looked crashed). Raises the
        command's error."""
        import threading
        import time
        outcome = {}

        def _run():
            try:
                self.siril.cmd(*args)
            except BaseException as e:   # given back to the caller
                outcome["error"] = e

        worker = threading.Thread(target=_run, daemon=True)
        start = time.monotonic()
        maximum, value = self.progressbar.maximum(), self.progressbar.value()
        worker.start()
        worker.join(0.3)
        if worker.is_alive():   # a long one: a busy bar and the time
            self.progressbar.setMaximum(0)
            while worker.is_alive():
                elapsed = int(time.monotonic() - start)
                self.progress_label.setText(f"{args[0]}: {elapsed // 60} min {elapsed % 60:02d} s"
                                            if elapsed >= 60 else f"{args[0]}: {elapsed} s")
                QApplication.processEvents()
                worker.join(0.1)
            self.progressbar.setMaximum(maximum)
            self.progressbar.setValue(value)
            elapsed = int(time.monotonic() - start)
            if elapsed >= 30:
                self._build_log(f"  ({args[0]}: {elapsed // 60} min {elapsed % 60:02d} s)")
        if "error" in outcome:
            raise outcome["error"]

    def _release_working_dir(self):
        """Siril out of its subfolders, its image / sequence closed, so that
        process/ can be deleted (user-reported Oct 2026, Windows: a script
        stopped on a failed command left Siril in process/ with its sequence
        open, and the next copy failed on os.rmdir)."""
        cwd = self.current_working_directory
        for args in (("close",), ("cd", f'"{cwd}"' if " " in cwd else cwd)):
            try:
                self.siril.cmd(*args)
            except s.SirilError:
                pass

    def _copy_from_json_done(self, count):
        """Called when JSON-based copy is complete."""
        photometry = None
        # _last_session_data: None after a megastack JSON
        if self.photometry_checkbox.isChecked() and self._last_session_data:
            photometry = self._generate_photometry_script(self._last_session_data, self.current_working_directory)
            if photometry:
                self._last_generated_scripts = [photometry]
        self.json_btn.setDisabled(False)
        self.copy_btn.setDisabled(False)
        self.build_sessions_btn.setDisabled(not self._last_generated_scripts)
        self.progressbar.setValue(0)
        self._save_step("copied")
        self.progressbar.setMaximum(1)
        self.progress_label.setText("completed")
        self.siril.log(f"Dwarfium JSON copy complete: {count} file(s) copied.", LogColor.GREEN)
        if photometry:
            QMessageBox.information(
                self,
                "Copy complete",
                f"{count} file(s) copied to Siril working directory.\n"
                f"Photometry script generated: {os.path.basename(photometry[0])}\n"
                f"Click Build Sessions to run it (the light curve is written in the\n"
                f"process folder: light_curve_*.csv).",
            )
            return
        QMessageBox.information(
            self,
            "Copy complete",
            f"{count} file(s) copied to Siril working directory.\n"
            f"You can now close this window and run your Siril script.",
        )

    def check_exposure(self):
        """Measures the variable star in a few test frames (the "🔆 Check
        exposure" button) - user-requested Oct 2026: set the exposure and gain
        of a photometry session from a few test frames. Each frame: green
        channel (as the photometry script), plate solve, the star and its
        comparison stars from findcompstars, Siril's PSF of the stars found.
        Reports the star's peak against the 12-bit saturation level, its S/N,
        the comparison stars saturated, the longest exposure at that gain
        (the signal is proportional to the exposure), the S/N at the faintest
        for its amplitude (VSX's by default) and the Moon."""
        files, _ = QFileDialog.getOpenFileNames(
            self, "Test frames of the variable star", "",
            "FITS files (*.fits *.fit *.fts);;All files (*.*)",
        )
        if not files:
            return
        # astropy reads the plate solved images (measure_star)
        s.ensure_installed(["astropy"])
        first = {key: value for _, key, value, _ in read_fits_cards(files[0])}
        star, ok = QInputDialog.getText(
            self, "Check exposure",
            "Variable star (name known to Siril / SIMBAD, e.g. RZ Cas):",
            text=(first.get("OBJECT") or "").strip(),
        )
        star = " ".join(star.split())
        if not ok or not star:
            return
        # Its amplitude from VSX when known (an eclipse depth or a pulsation's range)
        vsx_errors = []
        vsx = vsx_star(star, errors=vsx_errors)
        # Frames without a target (RA = DEC = 0): the plate solve starts at the star's
        self._check_center = (vsx["ra"], vsx["dec"]) if vsx and vsx.get("ra") is not None \
            and vsx.get("dec") is not None else None
        if vsx_errors:
            self.siril.log(f"[check exposure] VSX: {star}: {vsx_errors[0]}", LogColor.SALMON)
        default = round(vsx["amplitude"], 2) if vsx and vsx["amplitude"] else 1.0
        known = (f"VSX: {vsx['type']}, {vsx['max']:g} - {vsx['min']:g} mag\n" if vsx and vsx["amplitude"]
                 and vsx["max"] is not None and vsx["min"] is not None else
                 (f"VSX: {vsx['type']}\n" if vsx else f"Not found in VSX ({(vsx_errors or ['?'])[0]})\n"))
        depth, ok = QInputDialog.getDouble(
            self, "Check exposure",
            known + "Amplitude (mag) - eclipse depth or range of the variation - for the S/N at the faintest:",
            default, 0.0, 5.0, 2,
        )
        if not ok:
            return

        work = os.path.join(self.current_working_directory, "exposure_check")
        os.makedirs(work, exist_ok=True)
        margin_level = 0.8 * _DWARF_12BIT_PHOT_MAX
        kind = f" ({vsx['type']})" if vsx and vsx.get("type") else ""
        report = [f"Exposure check — {star}{kind} — amplitude {depth:.2f} mag",
                  f"Saturation level {_DWARF_12BIT_PHOT_MAX} ADU (12-bit data), longest exposure for a peak at 80 % of it"]
        report += self._moon_lines(first)
        report.append("")
        self.exposure_btn.setDisabled(True)
        longest_by_frame = []
        try:
            for path in files:
                lines, longest = self._check_exposure_frame(path, star, depth, work, margin_level)
                report += lines + [""]
                if longest:
                    longest_by_frame.append(longest)
            # The peak changes from frame to frame with the seeing (about 15 %
            # over 5 frames of a real test): the shortest of the longest
            # exposures is the safe one
            if len(longest_by_frame) > 1:
                report += [f"Over {len(longest_by_frame)} frames: {min(longest_by_frame):.0f} s at most "
                           f"(from {min(longest_by_frame):.0f} to {max(longest_by_frame):.0f} s - the seeing)", ""]
        finally:
            self.exposure_btn.setDisabled(False)
            # Siril's working directory back (each frame was measured in exposure_check/)
            cwd = self.current_working_directory
            try:
                self.siril.cmd("cd", f'"{cwd}"' if " " in cwd else cwd)
            except s.SirilError:
                pass

        text = "\n".join(report)
        with open(os.path.join(work, "exposure_check.txt"), "w", encoding="utf-8") as f:
            f.write(text)
        for line in report:
            if line.strip():   # Siril's log refuses an empty message ("unknown interface error")
                self.siril.log(line, LogColor.BLUE)
        QMessageBox.information(self, "Check exposure", text + f"\n\nSaved in {work}")

    @staticmethod
    def _moon_lines(cards):
        """The Moon at the first frame (its DATE-OBS, the DWARF's local time:
        an hour or two off, no matter here) seen from the target in its header."""
        try:
            from astropy.time import Time
            when = Time(str(cards["DATE-OBS"]).replace("Z", ""), format="isot", scale="utc")
            lit, sep = moon_at(when, float(cards["RA"]), float(cards["DEC"]))
        except Exception:
            return []
        line = f"Moon: {100 * lit:.0f} % lit, {sep:.0f}° from the star"
        if lit > 0.5 and sep < 60:
            line += " - a brighter sky: more noise; longer exposures, or a night without it"
        return [line]

    def _check_exposure_frame(self, path, star, depth, work, margin_level):
        """(report lines, longest exposure in s or None) of one test frame (see
        check_exposure())."""
        cards = {key: value for _, key, value, _ in read_fits_cards(path)}
        name = os.path.basename(path)
        try:
            exposure = float(cards.get("EXPTIME") or 0)
        except ValueError:
            exposure = 0.0
        title = f"{name}: {exposure:g} s, gain {cards.get('GAIN', '?')}"
        base = os.path.splitext(name)[0].replace(" ", "_")
        try:
            shutil.copy2(path, os.path.join(work, base + ".fits"))
            self.siril.cmd("cd", f'"{work}"' if " " in work else work)
            self.siril.cmd("load", base + ".fits")
            self.siril.cmd("extract_Green")
            self.siril.cmd("load", "Green_" + base)
            solve = dwarf_platesolve_args(path)
            center = getattr(self, "_check_center", None)
            if center and _header_center(cards) is None:
                solve.insert(0, f"{center[0]:.5f},{center[1]:+.5f}")
            self.siril.cmd("platesolve", *solve)
            csv_name = f"check_{base}.csv"
            self.siril.cmd("findcompstars", f'"{star}"' if " " in star else star, f"-out={csv_name}")
            # The plate solved green image, measured with astropy (measure_star)
            self.siril.cmd("save", "solved_" + base)
        except (s.SirilError, OSError) as e:
            if "platesolve" in str(e):   # Siril's "Generic error": no or too few stars found
                return [title, "  plate solve failed: no stars or too few found - clouds, mist, the focus?"], None
            return [title, f"  failed: {e}"], None
        solved = next((os.path.join(work, f) for f in sorted(os.listdir(work))
                       if os.path.splitext(f)[0] == "solved_" + base), None)
        if not solved:
            return [title, "  the plate solved image was not saved"], None
        try:
            import warnings
            from astropy.io import fits as _fits
            from astropy.wcs import WCS
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                with _fits.open(solved) as hdul:
                    hdu = hdul[0]
                    data = hdu.data.astype("float64")
                    wcs = WCS(hdu.header)
            if data.ndim == 3:
                data = data[0]
            if data.max() <= 1.5:   # 32-bit float image: 0..1
                data = data * 65535.0
            if not wcs.has_celestial:
                return [title, "  no plate solve in the saved image"], None
        except Exception as e:
            return [title, f"  the plate solved image was not read: {e}"], None

        targets, comps = [], []
        try:
            with open(os.path.join(work, csv_name), encoding="utf-8") as f:
                rows = csv.DictReader(line for line in f if line.strip() and not line.startswith("#"))
                for row in rows:
                    row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
                    try:
                        radec = (float(row["ra"]), float(row["dec"]))
                    except (KeyError, ValueError):
                        continue
                    (targets if row.get("type", "").lower() == "target" else comps).append(radec)
        except OSError as e:
            return [title, f"  comparison stars not read: {e}"], None
        if not targets:
            return [title, "  the star was not found by findcompstars (name, plate solve)"], None

        def _measure(ra, dec):
            try:
                return measure_star(data, wcs, ra, dec)
            except Exception:
                return None

        measured = _measure(*targets[0])
        if measured is None:
            return [title, "  the star was not detected in the frame (out of the field, too faint?)"], None
        peak, background, snr = measured
        lines = [title, f"  {star}: peak {peak:.0f} / {_DWARF_12BIT_PHOT_MAX} ADU ({100 * peak / _DWARF_12BIT_PHOT_MAX:.0f} %), "
                        f"background {background:.0f}, S/N about {snr:.0f}"]
        if peak >= _DWARF_12BIT_PHOT_MAX:
            lines.append("  SATURATED: shorter exposure or lower gain")
        elif exposure > 0 and peak > background:
            longest = exposure * (margin_level - background) / (peak - background)
            model = (cards.get("TELESCOP") or "").replace(" ", "").upper()
            model_max = _MAX_EXPOSURE_BY_TELESCOP.get(model)
            if model_max and longest > model_max:
                longest = model_max
                lines.append(f"  longest exposure at this gain: more than {model_max:g} s, the most on this model:"
                             " raise the gain for more signal")
            else:
                lines.append(f"  longest exposure at this gain: {longest:.0f} s")
        lines.append(f"  S/N at the faintest (-{depth:.2f} mag): about {snr * 10 ** (-0.4 * depth):.0f}")
        comp_peaks = [m for m in (_measure(ra, dec) for ra, dec in comps) if m]
        saturated = sum(1 for m in comp_peaks if m[0] >= _DWARF_12BIT_PHOT_MAX)
        lines.append(f"  comparison stars: {len(comps)} listed, {len(comp_peaks)} measured, {saturated} saturated")
        return lines, (longest if peak < _DWARF_12BIT_PHOT_MAX and exposure > 0 and peak > background else None)

    def _generate_photometry_script(self, data: dict, cwd: str):
        """Variable star photometry script for a single session (the
        "📈 Photometry" option): calibration with the master dark, green
        channel (AAVSO TG band of these colour sensors), plate solve of every
        image, comparison stars found by Siril (APASS), then the differential
        photometry in Python (differential_light_curve(), run by Build
        Sessions) - light_curve_<sequence>.csv in the process folder. Returns (ssf_path, lines), or None when cancelled
        or not possible. Requires Siril 1.4.0+ (findcompstars)."""
        lights_dir = os.path.join(cwd, "lights")
        lights = sorted(
            os.path.join(lights_dir, f) for f in os.listdir(lights_dir)
            if f.lower().endswith((".fits", ".fit", ".fts"))
        ) if os.path.isdir(lights_dir) else []
        if not lights:
            QMessageBox.warning(
                self, "Photometry",
                "No light FITS directly in lights/ (a mosaic session can't be measured).",
            )
            return None

        session = data.get("session", {})
        site = data.get("site") if isinstance(data.get("site"), dict) and data["site"].get("lat") is not None else None
        star, ok = QInputDialog.getText(
            self, "Photometry",
            "Variable star (name known to Siril / SIMBAD, e.g. RZ Cas):",
            text=session.get("target", ""),
        )
        star = " ".join(star.split())
        if not ok or not star:
            return None
        # The DWARF writes its local time in DATE-OBS: its UTC offset, this
        # PC's at the session's date by default (daylight saving included)
        first = {key: value for _, key, value, _ in read_fits_cards(lights[0])}
        pc_offset = local_utc_offset_hours(first.get("DATE-OBS", ""))
        utc_offset, ok = QInputDialog.getDouble(
            self, "Photometry",
            "The DWARF writes its local time in DATE-OBS.\n"
            f"UTC offset of that time, in hours (this PC on {str(first.get('DATE-OBS', ''))[:10]}: {pc_offset:+g}):",
            pc_offset, -14.0, 14.0, 2,
        )
        if not ok:
            return None

        fixed = sum(1 for f in lights if fix_dwarf_date_obs(f))
        if fixed:
            self.siril.log(
                f"[photometry] DATE-OBS of {fixed} light(s) moved back by EXPTIME "
                "(the DWARF writes the end of the exposure).", LogColor.BLUE,
            )

        darks_dir = os.path.join(cwd, "darks")
        n_darks = len([
            f for f in os.listdir(darks_dir) if f.lower().endswith((".fits", ".fit", ".fts"))
        ]) if os.path.isdir(darks_dir) else 0
        proc = os.path.join(cwd, "process")
        seq = "Green_pp_light" if n_darks else "Green_light"

        lines = [
            f"# Dwarfium photometry — {star} — {session.get('date', '')[:16]} — {session.get('dwarf', '')}",
            f"# {len(lights)} light(s), {n_darks} dark(s) — generated by Dwarfium Archive Selector",
            "requires 1.4.0",
            "setext fit",
            f'cd "{cwd}"',
            "",
            "# Convert light frames",
            "cd lights",
            # link, not convert: the lights not copied once more (Naztronomy's
            # Smart Telescope script, user-shared Oct 2026: 509 images took
            # about 40 GB) - Siril copies when it can't link
            "link light -out=../process",
            "cd ..",
            "",
        ]
        if n_darks:
            lines += [
                "# Convert darks",
                "cd darks",
                "convert dark -out=../process",
                "cd ..",
                "",
            ]
        lines += ["cd process", ""]
        if n_darks >= 2:
            lines += ["# Master dark", "stack dark rej 3 3 -nonorm -out=master_dark", ""]
        elif n_darks == 1:
            lines += ["# Single pre-stacked dark used as master dark", "load dark_00001", "save master_dark", ""]
        if n_darks:
            lines += [
                "# Dark calibration, kept as CFA",
                "calibrate light -dark=master_dark -cc=dark -cfa",
                f"# PYTHON_CLEANUP_SEQ {proc}|light_",
                "",
                "# Green channel of the CFA images (AAVSO TG band)",
                "seqextract_Green pp_light",
                f"# PYTHON_CLEANUP_SEQ {proc}|pp_light_",
                "",
            ]
        else:
            lines += [
                "# No dark found: green channel of the raw CFA images (AAVSO TG band)",
                "seqextract_Green light",
                f"# PYTHON_CLEANUP_SEQ {proc}|light_",
                "",
            ]
        # Resumed after a stop (user-reported Oct 2026: Siril closed at image 95
        # of 509, after 15 minutes of calibration and green channel): the
        # green images all there, those steps skipped - the plate solve skips
        # the images already solved
        green = [f for f in os.listdir(proc) if f.startswith("Green_pp_light_" if n_darks else "Green_light_")
                 and f.lower().endswith((".fit", ".fits"))] if os.path.isdir(proc) else []
        # Asked unless "Resume (keep the files)" was just chosen at the JSON's
        # load (user-reported Oct 2026: asked twice)
        if len(green) >= len(lights) and (getattr(self, "_resume_photometry", False) or QMessageBox.question(
                self, "Photometry",
                f"process/ already holds the {len(green)} green images of an earlier run.\n"
                "Resume from the plate solve (calibration and green channel not done again)?",
        ) == QMessageBox.StandardButton.Yes):
            start = lines.index("# Convert light frames")
            lines = lines[:start] + ["# Resumed: calibration and green channel of an earlier run kept",
                                     "cd process", ""]
        # From Python (# PYTHON_PLATESOLVE): seqplatesolve first, run by
        # _siril_cmd - the script's window kept alive, the time shown (it
        # stayed frozen through its minutes on a 141-image session, user-
        # reported Oct 2026) -, then image by image what it left unsolved.
        # -noflip: each image saved as it is, its solution with it
        solve_args = ["-noflip"] + dwarf_platesolve_args(lights[0])
        # A session without a target (manual pointing: "Unknown", RA = DEC = 0
        # in the header - the user's DY Peg data, Oct 2026): Siril starts its
        # plate solve from the header's coordinates, so the star's are given -
        # VSX's, in degrees (the archive's may be in hours)
        center = _header_center(first)
        if center is None:
            found = vsx_star(star) or {}
            ra, dec = found.get("ra"), found.get("dec")
            if ra is not None and dec is not None:
                solve_args.insert(0, f"{float(ra):.5f},{float(dec):+.5f}")
            else:
                QMessageBox.warning(
                    self, "Photometry",
                    f"No coordinates in the FITS header and {star} not found (VSX): the plate solve will "
                    "likely fail. Point the session at the star, or check its name.",
                )
        solve_args = " ".join(solve_args)
        data_max = fits_data_max(lights[0])
        saturation = _DWARF_12BIT_PHOT_MAX if data_max is not None and data_max <= _DWARF_12BIT_MAX else 0
        keep_saturated = bool(saturation) and QMessageBox.question(
            self, "Photometry",
            f"Keep the target's saturated images (peak above {saturation} ADU)?\n\n"
            "No (recommended): left out - a saturated star is measured too faint.\n"
            "Yes: kept and flagged (drawn apart, target_saturated in the CSV), e.g. to compare with "
            "another software's curve; the comparison stars are still left out above it.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes
        lines += [
            "# Plate solve of every image (saved with its solution): the sequence by",
            "# seqplatesolve, then one by one what it left unsolved - each image",
            "# measured with its own solution, no registration: the dithering doesn't matter",
            f"# PYTHON_PLATESOLVE {proc}|{seq}|{solve_args}",
            "",
            "# Comparison stars (APASS catalog, Internet), on the first solved image",
            "# (loaded by the plate solve step)",
            f'findcompstars "{star}" -out=comparison_stars.csv',
            "",
            "# Differential photometry in Python (not Siril's light_curve): the target",
            "# and comparison stars at their coordinates in each image, times at",
            "# mid-exposure in JD, HJD and BJD"
            + (f", stars above {saturation} ADU left out (12-bit data)" if saturation else ""),
            f"# DATE-OBS taken as UTC{utc_offset:+g} h (the DWARF's local time)",
            "# Results then archived at the archive's root: _PHOTOMETRY/<star>/<session folder>/,",
            "# and the star's sessions put together with those of the other drives:",
            f"# PYTHON_PHOTOMETRY_ROOTS {json.dumps(data.get('photometry_roots') or [])}",
            f"# PYTHON_PHOTOMETRY_OPTIONS {json.dumps({'keep_saturated': keep_saturated})}",
            f"# PYTHON_PHOTOMETRY {proc}|{seq}|{saturation}|{utc_offset:g}|{session.get('session_dir') or ''}"
            f"|{data.get('astronomy_root') or ''}"
            + (f"|{site['lat']}|{site['lon']}|{(site.get('name') or '').replace('|', ' ')}" if site else ""),
            "",
            f"# Result: {os.path.join(proc, 'light_curve_' + seq + '.csv')}",
            "cd ..",
        ]

        star_safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in star)
        ssf_path = os.path.join(cwd, f"01_photometry_{star_safe}.ssf")
        with open(ssf_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        self.siril.log(f"Photometry script saved: {ssf_path}", LogColor.GREEN)
        return ssf_path, lines

    def build_mosaic_from_restacked(self):
        """Collect RESTACKED_ tiles from the last loaded siril_megastack.json,
        extract their stacked-16 FITS (direct file, or from a stacked-16*.zip
        for _MOSAIC_ sessions), then stitch them with Siril's astrometric
        mosaic alignment (seqplatesolve + seqapplyreg -framing=max + stack
        -maximize -overlap_norm).
        """
        data = self._last_megastack_data
        if not data:
            QMessageBox.warning(self, "No Megastack loaded", "Load a siril_megastack.json first.")
            return

        groups = data.get("sessions_by_filter", {})
        restacked_sessions = [
            sess
            for sessions in groups.values()
            for sess in sessions
            if str(sess.get("session_name", "")).startswith("RESTACKED_")
        ]
        if len(restacked_sessions) < 2:
            QMessageBox.warning(
                self, "Not enough tiles",
                "At least 2 RESTACKED_ sessions are needed to build a mosaic."
            )
            return

        obj = data.get("object", "Unknown").replace(" ", "_")
        self.current_working_directory = self.siril.get_siril_wd()
        self._mosaic_tiles_dir = os.path.join(self.current_working_directory, f"mosaic_tiles_{obj}")
        self._mosaic_object = obj

        # Detect any stack_*.fit(s) produced by a previous Build Sessions run
        # in the current working directory — offer to include them as extra tiles
        existing_stacks = sorted(
            os.path.join(self.current_working_directory, f)
            for f in os.listdir(self.current_working_directory)
            if f.lower().startswith("stack_") and f.lower().endswith((".fit", ".fits"))
        )
        include_stacks = []
        if existing_stacks:
            stack_names = "\n".join(f"  • {os.path.basename(f)}" for f in existing_stacks)
            reply_stacks = QMessageBox.question(
                self, "Include Build Sessions stacks?",
                f"Found {len(existing_stacks)} stack(s) from a previous Build Sessions run:\n\n"
                f"{stack_names}\n\n"
                "Include them as extra tiles in the mosaic?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply_stacks == QMessageBox.StandardButton.Yes:
                include_stacks = existing_stacks

        total_tiles = len(restacked_sessions) + len(include_stacks)
        extra_info = (
            f" + {len(include_stacks)} Build Sessions stack(s)" if include_stacks else ""
        )
        reply = QMessageBox.question(
            self, "Build Mosaic",
            f"Found {len(restacked_sessions)} RESTACKED_ session(s){extra_info} for {obj}.\n"
            f"Total tiles: {total_tiles}\n\n"
            f"Tiles will be extracted to:\n{self._mosaic_tiles_dir}\n\n"
            "Proceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._mosaic_include_stacks = include_stacks

        self.mosaic_btn.setDisabled(True)
        self.json_btn.setDisabled(True)
        self.copy_btn.setDisabled(True)
        self.progressbar.setMaximum(0)  # indeterminate while extracting
        self.progress_label.setText("extracting…")

        self.mosaicExtractThread = MosaicTileExtractThread(restacked_sessions, self._mosaic_tiles_dir)
        self.mosaicExtractThread.progress.connect(self._mosaic_extract_progress)
        self.mosaicExtractThread.done.connect(self._mosaic_extract_done)
        self.mosaicExtractThread.start()

    def _mosaic_extract_progress(self, value):
        """Progress callback for tile extraction (indeterminate progress bar)."""
        self.progress_label.setText(f"extracting… {value} tile(s)")

    def _mosaic_extract_done(self, tile_count, errors):
        """Called when tile extraction finishes — runs the Siril astrometric
        mosaic pipeline on the extracted tiles."""
        self.json_btn.setDisabled(False)
        self.copy_btn.setDisabled(False)
        self.progressbar.setMaximum(1)
        self.progressbar.setValue(0)

        if errors:
            for msg in errors:
                self.siril.log(f"[mosaic] {msg}", LogColor.SALMON)

        if tile_count < 2:
            self.progress_label.setText("failed")
            self.mosaic_btn.setDisabled(False)
            QMessageBox.warning(
                self, "Mosaic build failed",
                f"Only {tile_count} usable tile(s) extracted — need at least 2.\n"
                "Check the Siril log for details."
            )
            return

        self.siril.log(f"[mosaic] {tile_count} tile(s) extracted to {self._mosaic_tiles_dir}", LogColor.GREEN)

        # Copy any Build Sessions stacks the user chose to include as extra tiles
        extra_stacks = getattr(self, "_mosaic_include_stacks", [])
        for stack_path in extra_stacks:
            ext = os.path.splitext(stack_path)[1]
            dest_name = f"tile_stack_{os.path.basename(stack_path)}"
            dest_path = os.path.join(self._mosaic_tiles_dir, dest_name)
            try:
                shutil.copy2(win_long_path(stack_path), win_long_path(dest_path))
                tile_count += 1
                self.siril.log(f"[mosaic] Added stack tile: {dest_name}", LogColor.GREEN)
            except Exception as e:
                self.siril.log(f"[mosaic] Could not copy {stack_path}: {e}", LogColor.SALMON)

        self.progress_label.setText("registering…")

        seq_basename = f"mosaic_{self._mosaic_object}_"
        try:
            # Siril's command parser re-tokenizes the reconstructed command
            # line and splits on whitespace, so paths containing spaces (like
            # this one, under "Test Siril") must be quoted, same as in a .ssf
            # script file.
            self.siril.cmd("cd", f'"{self._mosaic_tiles_dir}"')
            actual_wd = self.siril.get_siril_wd()
            self.siril.log(f"[mosaic] CWD after cd: {actual_wd}", LogColor.BLUE)
            # Astrometric mosaic alignment (seqplatesolve + seqapplyreg
            # -framing=max + stack -maximize) requires Siril 1.4.0+
            self.siril.cmd("requires", "1.4.0")
            self.siril.cmd("link", seq_basename)
            # Use the local Gaia DR3 catalogue explicitly: with a local
            # catalogue, Siril re-reads each image's own header coordinates
            # individually (rather than fetching one shared online catalogue
            # for the whole sequence), and also enables the automatic
            # "near solve" search cone if the initial solve fails — both of
            # which matter here since tiles come from different Dwarf
            # devices/sensors with different framing and pixel scale.
            self.siril.cmd("seqplatesolve", seq_basename, "-catalog=localgaia")
            self.siril.cmd("seqapplyreg", seq_basename, "-framing=max")
            stack_args = [
                "stack", f"r_{seq_basename}", "rej", "3", "3",
                "-norm=addscale", "-maximize", "-overlap_norm",
                "-output_norm", "-rgb_equal",
            ]
            if self.feather_checkbox.isChecked():
                stack_args.append(f"-feather={self.feather_spinbox.value()}")
            stack_args.append(f"-out={self._mosaic_object}_mosaic")
            self.siril.cmd(*stack_args)
        except s.CommandError as e:
            self.progress_label.setText("failed")
            self.mosaic_btn.setDisabled(False)
            self.siril.log(f"[mosaic] Siril command failed: {e}", LogColor.RED)
            if "null matrices" in str(e).lower():
                hint = (
                    "This usually means most tiles failed plate solving.\n\n"
                    "Make sure a local star catalogue (Gaia DR3 or KStars NOMAD) is "
                    "installed in Siril's preferences — without one, only a single "
                    "online star catalogue is fetched for the whole sequence, which "
                    "often fails for tiles from different Dwarf devices/sensors.\n\n"
                )
            else:
                hint = ""
            QMessageBox.critical(
                self, "Mosaic build failed",
                f"A Siril command failed while building the mosaic:\n{e}\n\n"
                f"{hint}Check the Siril log for details."
            )
            return
        finally:
            try:
                self.siril.cmd("cd", f'"{self.current_working_directory}"')
            except Exception:
                pass

        self.progress_label.setText("completed")
        self.mosaic_btn.setDisabled(False)
        result_path = os.path.join(self._mosaic_tiles_dir, f"{self._mosaic_object}_mosaic.fit")
        self.siril.log(f"[mosaic] Mosaic complete: {result_path}", LogColor.GREEN)
        QMessageBox.information(
            self, "Mosaic complete",
            f"Mosaic built from {tile_count} tile(s).\n\nResult saved as:\n{result_path}"
        )

    def close_dialog(self):
        try:
            self.siril.disconnect()
        except Exception:
            pass  # Ignore disconnect errors
        self.close()

    def print_footer(self):
        self.siril.log(
            f"Finished at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            LogColor.GREEN,
        )

    def save_presets(self):
        """Save current settings and session data to preset file"""
        # Collect settings
        presets = {
            "archive_dir": self.archive_dir,
        }

        # Create presets directory if it doesn't exist
        presets_file = os.path.join(self.siril.get_siril_configdir(), PRESET_FILE)

        try:
            with open(presets_file, "w") as f:
                json.dump(presets, f, indent=4)
            self.siril.log(f"Saved preset to {presets_file}", LogColor.GREEN)
        except Exception as e:
            self.siril.log(
                f"Failed to save presets to {presets_file}: {e}", LogColor.RED
            )

    def load_presets(self):
        """Load settings and session data from preset file"""
        presets_file = os.path.join(self.siril.get_siril_configdir(), PRESET_FILE)
        try:
            presets = None
            if os.path.exists(presets_file):
                self.siril.log(
                    f"Loading preset from {presets_file}",
                    LogColor.GREEN,
                )
                with open(presets_file) as f:
                    presets = json.load(f)
            else:
                # If default presets don't exist, use defaults
                presets = json.loads(PRESET_JSON)
                self.siril.log(
                    "No presets file found.",
                    LogColor.GREEN,
                )

            self.archive_dir = presets.get("archive_dir", None)

        except Exception as e:
            self.siril.log(
                f"Error loading presets from {presets_file}: {str(e)}", LogColor.RED
            )

    def session_selected(self):
        """collect the selected sessions"""
        selection = self.session_listbox.selectedItems()
        lights_count = 0
        self.selected_sessions = []
        if self.selected_target is None:
            return
        for item in selection:
            i = self.session_list.index(item.text())
            if self.selected_target.sessions is None:
                continue
            self.selected_sessions.append(self.selected_target.sessions[i])
            lights_count += self.selected_target.sessions[i].stacked
        self.progress_label.setText(f"0 / {lights_count}")
        if lights_count > 0:
            self.copy_btn.setDisabled(False)
        else:
            self.copy_btn.setDisabled(True)

    def target_selected(self):
        """chose the selected target and update the session list"""
        selection = self.target_listbox.selectedItems()
        self.session_listbox.clear()
        self.session_list = []
        self.selected_target = None
        self.info_box.clear()
        self.thumb.clear()
        if len(selection) == 1:
            i = self.target_list.index(selection[0].text())
            self.selected_target = self.targets[i]
            for s in self.selected_target.sessions:
                self.session_list.append(
                    f"{s.calendardate}: {s.stacked} x {s.exposure}s / {s.gain}g, {s.ir}"
                )
            self.session_listbox.addItems(self.session_list)
            first = self.selected_target.sessions[0]
            self.info_box.setText(f"RA: {first.ra:.2f}\nDEC:{first.dec:.2f}\n")
            thumb = QPixmap(first.thumbnail).scaledToHeight(self.thumb.height())
            self.thumb.setPixmap(thumb)

    def parse_foldername(self, path):
        """Helper function parsing folder names according to usualy Dwarf Lab naming scheme"""
        foldername = os.path.basename(path)
        parts = foldername.split("_")
        if "RESTACKED" in parts:
            # RESTACK sessions have a different format
            self.siril.log(
                f"skip MegaStack of {parts[3]} - {parts[4]} - {parts[5]}",
                LogColor.BLUE,
            )
        else:
            if len(parts) != 9:
                self.siril.log(
                    f"Path name '{os.path.basename(path)}' does not match the expected pattern",
                    LogColor.BLUE,
                )
            else:
                session = Session(
                    path, parts[2], parts[3], parts[5], parts[7], parts[8]
                )
                # add more info from shotsinfo.json if avaliable
                if os.path.isfile(os.path.join(path, "shotsinfo.json")):
                    with open(path + os.sep + "shotsinfo.json") as fp:
                        info = json.load(fp)
                        session.ir = info["ir"]
                        session.taken = info["shotsTaken"]
                        session.stacked = info["shotsStacked"]
                        session.ra = info["RA"]
                        session.dec = info["DEC"]
                        session.min_temp = info["minTemp"]
                        session.max_temp = info["maxTemp"]
                if not os.path.isfile(session.thumbnail):
                    session.thumbnail = ""
                return session
        return None

    def parse_filetree(self, path):
        """walk the archive path and collect dir names matching dwarf naming schema"""
        if path is None:
            return []
        path = os.path.abspath(path)
        self.siril.log(
            f"Parsing '{path}'",
            LogColor.BLUE,
        )
        skip_folders = ["Thumbnail", "", "Solving_Failed", "CALI_FRAME", "DWARF_DARK"]
        session_folders = []
        sessions = []

        for root, folders, _ in os.walk(path):
            for folder in list(folders):
                if folder in skip_folders:
                    folders.remove(folder)
                    continue
                if len(folder) == 0:
                    folders.remove(folder)
                    continue
                if "DWARF_RAW_" in folder and "_MOSAIC_" not in folder:
                    session_folders.append(os.path.join(root, folder))

        for f in session_folders:
            session = self.parse_foldername(f)
            if session is not None:
                sessions.append(session)
        return sessions

    def get_targets(self, sessions):
        """inspect the collected sessions and retrieve a list of targets"""
        targets = []

        sessions_by_target = sorted(sessions, key=lambda s: (s.target, s.cam, s.date))
        last = ""
        target = None
        for session in sessions_by_target:
            if session is None:
                continue
            if session.target != last:
                last = session.target
                target = Target(session.target)
                targets.append(target)
            if target is not None:
                target.add_session(session)

        return targets

    def refresh_target_list(self):
        """action for refresh button, rescan the archive"""
        self.target_listbox.clear()  # clear QListWidget instead of delete()
        self.target_list = []
        self.siril.log(f"Showing {self.archive_dir}", LogColor.BLUE)

        for t in self.targets:
            self.target_list.append(
                f"{t.target} ({len(t.sessions)}x {t.sessions[0].cam.capitalize()})"
            )
        self.target_listbox.addItems(self.target_list)


class SirilGone(Exception):
    """Siril closed the connection - closed, or crashed (user-reported Oct
    2026: Siril with its window gone at image 175 of a 509-image plate
    solve). Nothing more can be done from this script."""


def _siril_gone(error) -> bool:
    """error, or one of its causes, is Siril's connection lost."""
    while error is not None:
        if isinstance(error, (SirilGone, s.SirilConnectionError)):
            return True
        error = error.__cause__ or error.__context__
    return False


SIRIL_GONE_TEXT = (
    "Siril closed the connection: Siril was closed, or crashed.\n\n"
    "{where}The files made so far are kept. To pick up from there:\n"
    "1. close this window and start Siril again (long series: as last time, Siril started from the terminal),\n"
    "2. run this script, Load Dwarfium JSON, \"Resume (keep the files)\",\n"
    "3. Build Sessions: the images already plate solved are skipped.\n\n"
    "Details in build_sessions.log.")


def _install_excepthook(window):
    """An unhandled Python error in a button's handler written to Siril's
    log, build_sessions.log and a message, instead of PyQt6's default: qFatal,
    the script killed without a word (user-reported Oct 2026: a 509-image run
    stopped at image 95, Windows reporting python.exe / Qt6Core.dll,
    c0000409 code 7 - a fatal app exit). Setting sys.excepthook is what keeps
    PyQt6 from aborting."""
    import traceback

    def _hook(kind, value, tb):
        text = "".join(traceback.format_exception(kind, value, tb))
        try:
            window._build_log("UNEXPECTED ERROR\n" + text)
        except Exception:
            pass
        try:
            for line in text.rstrip().splitlines()[-12:]:
                window.siril.log(line[:400] or " ", LogColor.RED)
        except Exception:
            pass
        try:
            if _siril_gone(value):
                QMessageBox.critical(window, "Dwarfium Archive Selector",
                                     SIRIL_GONE_TEXT.format(where=f"{value}\n\n" if isinstance(value, SirilGone) else ""))
            else:
                QMessageBox.critical(window, "Dwarfium Archive Selector",
                                     f"Unexpected error - the script goes on:\n\n{kind.__name__}: {value}\n\n"
                                     "Details in Siril's log and build_sessions.log.")
        except Exception:
            pass

    sys.excepthook = _hook


def main():
    try:
        app = QApplication(sys.argv)
        window = PreprocessingInterface()
        _install_excepthook(window)
        # Only show window if initialization was successful
        if window.initialization_successful:
            window.show()
            sys.exit(app.exec())
        else:
            # User canceled during initialization - exit gracefully
            sys.exit(0)
    except Exception as e:
        print(f"Error initializing application: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()