"""
api/foreground_fix.py

A wide session's foreground fixed (user-requested Oct 2026: on older
firmwares the Dwarf's stack, aligned on the stars, smears the trees and the
roof - the ground turns 15 deg an hour against the sky).

From the session's raw subs:
1. plate solved once (api/mosaic_wcs.solve_catalog, on the mean of the subs:
   EQ tracking keeps the stars still), each sub registered on the stars to
   the first one (the Dwarf dithers);
2. the foreground stacked on the ground: the ground turns about the celestial
   pole at the sidereal rate, so a bit of ground seen at the first sub's time
   in a direction is, in sub k, where that direction's RA moved on by the
   time elapsed is (median of the subs);
3. its mask, on that sharp stack (darker than the sky once vignetting is
   divided out);
4. the sky stacked on the stars, each sub counting only where its own
   foreground wasn't (the mask moved the same way), sigma-clipped mean;
5. both blended in the first sub's geometry, the borders not every sub saw
   cropped.

Output, in a FIXED_FOREGROUND folder next to the sessions: a linear FITS with
its WCS, a preview, and two stretched 16-bit TIFFs with transparency - the
sky alone and the foreground alone - for an image editor.

Alt-az sessions (the sky turns in the frame, the ground stays) aren't handled
yet. Memory: the subs kept as 16-bit (MAX_SUBS of them, evenly spread), the
stacks computed by blocks of rows.

Pure functions only - no NiceGUI/UI code here.
"""

from __future__ import annotations

import datetime as dt
import re
import warnings
from pathlib import Path

import numpy as np

from api.dwarf_backup_fct import print_log

OUTPUT_DIR = "FIXED_FOREGROUND"
MAX_SUBS = 40           # subs used, evenly spread over the session
MIN_SUBS = 5
BLOCK_ROWS = 96         # rows stacked at once
SIDEREAL = 15.0410686 / 3600  # deg of RA per second
FG_HALO_PX = 12         # foreground grown by this much before the sky stack
BLEND_PX = 3            # foreground edge softened over this much
GRID = (55, 97)         # rows, cols of the grid the ground's shift is computed on
BAYER_CODES = {"RGGB": "COLOR_BayerBG2RGB", "BGGR": "COLOR_BayerRG2RGB",
               "GRBG": "COLOR_BayerGB2RGB", "GBRG": "COLOR_BayerGR2RGB"}


def _progress(cb, fraction, message, log=None):
    print_log(message, log)
    if cb:
        try:
            cb(fraction, message)
        except Exception:
            pass


def raw_subs(session_dir) -> list[Path]:
    """The session's raw frames: single-plane FITS with a Bayer pattern, not
    the Dwarf's stacks nor its rejected frames, oldest first."""
    from astropy.io import fits
    subs = []
    for f in Path(session_dir).iterdir():
        name = f.name.lower()
        if f.suffix.lower() not in (".fits", ".fit") or name.startswith(("stacked", "failed_")):
            continue
        try:
            h = fits.getheader(f)
        except Exception:
            continue
        if h.get("NAXIS") == 2 and h.get("BAYERPAT") and h.get("DATE-OBS"):
            subs.append((str(h["DATE-OBS"]), f))
    return [f for _, f in sorted(subs)]


# The first firmware that freezes the foreground itself (user-found Oct 2026,
# DWARFLAB beta of September 1st: "fixed foreground support for Milky Way
# imaging") - a session shot with it has nothing to repair.
FIXED_FOREGROUND_FIRMWARE = {"dwarf3": (1, 5, 3, 9), "dwarfmini": (1, 1, 4, 4)}


def _version(text):
    nums = re.findall(r"\d+", str(text or ""))
    return tuple(int(x) for x in nums) if nums else None


def foreground_already_fixed(header) -> bool:
    """True when the Dwarf and firmware that shot it freeze the foreground."""
    model = re.sub(r"[^a-z0-9]", "", str(header.get("TELESCOP") or header.get("INSTRUME") or "").lower())
    first = FIXED_FOREGROUND_FIRMWARE.get(model)
    fw = _version(header.get("FIRMWARE"))
    return bool(first and fw and fw >= first)


def can_repair(session_dir) -> bool:
    """A wide session with raw subs, shot before its Dwarf froze the
    foreground itself - reads one sub's header."""
    from astropy.io import fits
    session_dir = Path(session_dir)
    if not session_dir.is_dir():
        return False
    for f in session_dir.iterdir():
        name = f.name.lower()
        if f.suffix.lower() not in (".fits", ".fit") or name.startswith(("stacked", "failed_")):
            continue
        try:
            h = fits.getheader(f)
        except Exception:
            continue
        if h.get("NAXIS") != 2 or not h.get("BAYERPAT"):
            continue
        wide = "WIDE" in str(h.get("CAMERA", "")).upper() or "_WIDE_" in session_dir.name.upper()
        return wide and not foreground_already_fixed(h)
    return False


def default_output(session_dir) -> Path:
    """FIXED_FOREGROUND/<session folder>_fixed.fits next to the session."""
    session_dir = Path(session_dir)
    name = re.sub(r"[^\w.-]+", "_", session_dir.name) or "session"
    return session_dir.parent / OUTPUT_DIR / f"{name}_fixed.fits"


def _load(path):
    """(RGB uint16 (H, W, 3), header) of a raw sub."""
    import cv2
    from astropy.io import fits
    with fits.open(path) as hdul:
        h = hdul[0].header.copy()
        raw = np.asarray(hdul[0].data)
    raw = np.clip(raw, 0, 65535).astype(np.uint16)
    code = getattr(cv2, BAYER_CODES.get(str(h.get("BAYERPAT", "RGGB")).strip().upper(), "COLOR_BayerBG2RGB"))
    return cv2.cvtColor(raw, code), h


def _when(header):
    return dt.datetime.fromisoformat(str(header["DATE-OBS"]).replace("Z", ""))


def _hits(xy, ref_xy, T, tol=2.0):
    """How many of the stars `xy`, moved by T, land each on its own
    reference star."""
    p = (T[:2, :2] @ xy.T).T + T[:2, 2]
    d = np.hypot(p[:, None, 0] - ref_xy[None, :, 0], p[:, None, 1] - ref_xy[None, :, 1])
    j = d.argmin(axis=1)
    near = d[np.arange(len(j)), j] < tol
    return len(np.unique(j[near]))


def _quick_stars(lum, keep=80):
    """(N, 2) x, y of the `keep` stars with the most light, quickly (once a
    sub: a median background took 9 s a frame): a smooth background, local
    peaks, ranked by their light over a box - a hot pixel is one bright
    pixel, a star a few."""
    import cv2
    lum = np.asarray(lum, np.float32)
    hp = lum - cv2.GaussianBlur(lum, (0, 0), 8)
    sample = hp[::4, ::4]
    noise = 1.4826 * np.median(np.abs(sample - np.median(sample))) + 1e-6
    peaks = (hp == cv2.dilate(hp, np.ones((9, 9), np.uint8))) & (hp > 8 * noise)
    peaks[:8, :] = peaks[-8:, :] = peaks[:, :8] = peaks[:, -8:] = False
    y, x = np.nonzero(peaks)
    flux = cv2.boxFilter(np.clip(hp, 0, None), -1, (7, 7))[y, x]
    order = np.argsort(-flux)[:keep]
    return np.c_[x[order], y[order]].astype(float)


def _star_transform(lum, ref_xy, keep=80):
    """3x3 matrix taking this sub's pixels to the reference sub's: astroalign
    on the brightest stars, kept only when more stars land on the reference
    ones than without moving the sub (EQ tracking keeps them nearly still;
    a symmetric pattern can fool the triangles - a 900 px "dither" seen).
    None when the stars don't match either way."""
    import astroalign as aa
    xy = _quick_stars(lum, keep)
    if len(xy) < 10:
        return None
    best, score = np.eye(3), _hits(xy, ref_xy, np.eye(3))
    try:
        T, _ = aa.find_transform(xy, ref_xy, max_control_points=60)
        # same lens, same scale: a degenerate fit (all stars onto one point) is out
        if abs(T.scale - 1) < 0.01 and _hits(xy, ref_xy, T.params) > score:
            best, score = T.params, _hits(xy, ref_xy, T.params)
    except Exception:
        pass
    return best if score >= max(8, len(xy) // 5) else None


ALTAZ_TURN_DEG = 0.3      # stars turning more than this in the frame: alt-az tracking
STARS_SPAN_S = 180        # the first subs within this span show stars and ground both sharp
FG_ISLAND_MAX = 0.02      # foreground away from the frame's edge kept only above this part of it
STARRY_MAX = 0.6          # a dark patch with stars over more of it than this is sky


def _foreground(ground, valid, starry=None):
    """The foreground on the ground stack: darker than the sky (Otsu), stars
    and noise smoothed out, vignetting divided out first (a dark corner of
    sky passed for a tree) - and without stars where `starry` (the first
    subs, stars sharp) shows some: on a session with little foreground the
    darker half of the sky's own gradient passed for it (user-found Oct
    2026: a disc of sky, starless, in the middle of the frame). Foreground
    comes in from the frame's edge: a patch of it away from the edge is sky
    unless it's large."""
    import cv2
    from scipy.ndimage import gaussian_filter, binary_dilation, binary_opening, binary_closing
    gl = ground.mean(axis=2)
    ok = valid & np.isfinite(gl)
    ok &= gl > 0.9 * np.median(gl[ok])           # not the borders no sub saw

    def split(img):
        s = gaussian_filter(np.where(ok, img, np.median(img[ok])), 3)
        lo, hi = np.percentile(s[ok], [5, 95])    # trees and sky can be a few ADU apart
        u8 = np.clip((s - lo) / max(hi - lo, 1e-6) * 255, 0, 255).astype(np.uint8)
        thr, _ = cv2.threshold(u8[ok], 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return (u8 < thr) & ok

    dark = split(gl)
    h, w = gl.shape
    yy, xx = np.mgrid[0:h, 0:w] / np.array([h, w], float)[:, None, None]
    sel = ok & ~binary_dilation(dark, iterations=10)
    if sel.sum() > 1000:
        A = np.stack([np.ones(sel.sum()), xx[sel], yy[sel], xx[sel] ** 2, yy[sel] ** 2, xx[sel] * yy[sel]], 1)
        pedestal = np.percentile(gl[ok], 0.5)
        coef = np.linalg.lstsq(A, gl[sel] - pedestal, rcond=None)[0]
        level = coef[0] + coef[1] * xx + coef[2] * yy + coef[3] * xx ** 2 + coef[4] * yy ** 2 + coef[5] * xx * yy
        dark = split((gl - pedestal) / np.maximum(level, 1e-3))
    fg = binary_opening(binary_closing(dark, iterations=2), iterations=2)
    from scipy.ndimage import label
    lab, n = label(fg)
    if n:
        sizes = np.bincount(lab.ravel(), minlength=n + 1)
        keep = np.zeros(n + 1, bool)
        keep[np.unique(np.r_[lab[0], lab[-1], lab[:, 0], lab[:, -1]])] = True
        keep[sizes > FG_ISLAND_MAX * fg.size] = True
        sky_like = np.zeros(n + 1, bool)
        if starry is not None:
            # a dark patch mostly full of stars is sky - patch by patch: the star
            # density is too coarse at a tree's edge to cut there
            stars_in = np.bincount(lab.ravel(), weights=starry.ravel().astype(float), minlength=n + 1)
            sky_like = stars_in >= STARRY_MAX * np.maximum(sizes, 1)
        keep[0] = sky_like[0] = False
        fg = keep[lab] & ~sky_like[lab]
        if sky_like.any():
            # from such a patch, its starless part - a real foreground the sky's
            # gradient was joined to - if it comes in from the edge or is large
            rest = sky_like[lab] & ~starry
            lab2, n2 = label(rest)
            if n2:
                sizes2 = np.bincount(lab2.ravel(), minlength=n2 + 1)
                keep2 = np.zeros(n2 + 1, bool)
                keep2[np.unique(np.r_[lab2[0], lab2[-1], lab2[:, 0], lab2[:, -1]])] = True
                keep2[sizes2 > FG_ISLAND_MAX * fg.size] = True
                keep2[0] = False
                fg |= keep2[lab2]
    return fg, ok


def repair_session(session_dir, out_fits=None, log=None, progress=None, max_subs=MAX_SUBS):
    """
    The session `session_dir`'s foreground fixed, from its raw subs, into
    `out_fits` (default_output()) and next to it a preview (_preview.jpg),
    the sky alone (_sky.tif) and the foreground alone (_ground.tif).
    progress(fraction 0-1, message) is called along the way.

    Returns {"ok", "fits", "preview", "sky_tif", "ground_tif", "subs",
    "foreground_pct", "error"}.
    """
    import cv2
    from astropy.io import fits
    from astropy.coordinates import SkyCoord
    import astropy.units as u
    from scipy.interpolate import RectBivariateSpline
    from scipy.ndimage import binary_dilation, distance_transform_edt
    from api.mosaic_wcs import solve_catalog, _stretched, write_rgba_tiff, write_preview

    result = {"ok": False, "fits": None, "preview": None, "sky_tif": None, "ground_tif": None,
              "subs": 0, "foreground_pct": None, "error": None}
    session_dir = Path(session_dir)
    out_fits = Path(out_fits) if out_fits else default_output(session_dir)
    paths = raw_subs(session_dir)
    if len(paths) < MIN_SUBS:
        result["error"] = f"{len(paths)} raw frames found in the session, at least {MIN_SUBS} needed"
        return result
    if len(paths) > max_subs:
        paths = [paths[i] for i in np.linspace(0, len(paths) - 1, max_subs).round().astype(int)]

    # 1. the subs, and the sky's geometry
    subs, headers = [], []
    for k, p in enumerate(paths):
        _progress(progress, 0.15 * k / len(paths), f"Reading sub {k + 1}/{len(paths)}: {p.name}", log)
        try:
            rgb, h = _load(p)
        except Exception as e:
            print_log(f"{p.name}: unreadable ({e}), left out", log)
            continue
        if subs and rgb.shape != subs[0].shape:
            print_log(f"{p.name}: another size, left out", log)
            continue
        subs.append(rgb)
        headers.append(h)
    if len(subs) < MIN_SUBS:
        result["error"] = "too few readable raw frames"
        return result
    if str(headers[0].get("EQMODE", 1)).strip() in ("0", "False", "F"):
        result["error"] = "alt-az session (EQMODE = 0): not handled yet - only equatorial ones"
        return result
    H, W = subs[0].shape[:2]
    times = [_when(h) for h in headers]

    _progress(progress, 0.17, "Plate solving (catalogue)...", log)
    mean_lum = np.mean([s.mean(axis=2, dtype=np.float32) for s in subs], axis=0)
    wcs = solve_catalog(mean_lum, headers[0], str(paths[0]), log, session_dir.name)
    if wcs is None:
        result["error"] = "plate solving failed (no pointing in the header, or too few stars)"
        return result

    # each sub on the first one's stars (dithering, tracking drift)
    _progress(progress, 0.25, "Registering the subs on the stars...", log)
    ref_xy = _quick_stars(subs[0].mean(axis=2, dtype=np.float32), 80)
    to_sub = [np.eye(3)]                       # reference pixel -> sub pixel
    keep = [0]
    turns = [0.0]
    for k in range(1, len(subs)):
        T = _star_transform(subs[k].mean(axis=2, dtype=np.float32), ref_xy)
        if T is None:
            print_log(f"Sub {k + 1}: not registered on the stars, left out", log)
            continue
        to_sub.append(np.linalg.inv(T))
        keep.append(k)
        shift, turn = np.hypot(*T[:2, 2]), np.degrees(np.arctan2(T[1, 0], T[0, 0]))
        turns.append(turn)
        if shift > 2 or abs(turn) > 0.05:
            print_log(f"Sub {k + 1}: {shift:.1f} px, {turn:+.2f} deg off the first one", log)
    # EQ tracking keeps the frame still on the stars (dithering shifts it);
    # alt-az turns it (field rotation) - EQMODE isn't in every firmware's frames
    if max(abs(x) for x in turns) > ALTAZ_TURN_DEG:
        result["error"] = (f"the stars turn {max(abs(x) for x in turns):.1f} deg in the frame over the session: "
                           "alt-az tracking - only equatorial sessions are handled yet")
        return result
    subs = [subs[k] for k in keep]
    times = [times[k] for k in keep]
    n = len(subs)
    if n < MIN_SUBS:
        result["error"] = "too few subs registered on the stars"
        return result
    result["subs"] = n

    # the ground's shift (reference pixel -> where that bit of ground was in
    # the reference geometry at sub k's time), on a grid, splined
    gy, gx = np.meshgrid(np.linspace(0, H - 1, GRID[0]), np.linspace(0, W - 1, GRID[1]), indexing="ij")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        world = wcs.pixel_to_world(gx.ravel(), gy.ravel())
        bx0, by0 = wcs.world_to_pixel(world)          # the round trip's own error, taken out
        splines = []
        for t in times:
            dra = SIDEREAL * (t - times[0]).total_seconds()
            mx, my = wcs.world_to_pixel(SkyCoord((world.ra.deg + dra) * u.deg, world.dec))
            splines.append((RectBivariateSpline(gy[:, 0], gx[0], (mx - bx0).reshape(gx.shape)),
                            RectBivariateSpline(gy[:, 0], gx[0], (my - by0).reshape(gy.shape))))
    last = splines[-1]
    print_log(f"The ground moved {float(last[0].ev(H / 2, W / 2)):.0f}, {float(last[1].ev(H / 2, W / 2)):.0f} px "
              f"against the stars over {(times[-1] - times[0]).total_seconds() / 60:.0f} min", log)
    cols = np.arange(W, dtype=np.float32)

    def maps(k, r0, r1, ground):
        """Where, in sub k, the reference block's pixels are - on the ground,
        or on the sky."""
        rows = np.arange(r0, r1, dtype=np.float32)
        fx, fy = np.meshgrid(cols, rows)
        if ground:
            fx = fx + splines[k][0](rows, cols).astype(np.float32)
            fy = fy + splines[k][1](rows, cols).astype(np.float32)
        A = to_sub[k]
        return ((A[0, 0] * fx + A[0, 1] * fy + A[0, 2]).astype(np.float32),
                (A[1, 0] * fx + A[1, 1] * fy + A[1, 2]).astype(np.float32))

    def sample(img, mx, my):
        out = cv2.remap(img, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0).astype(np.float32)
        out[(mx < 0) | (mx > W - 1) | (my < 0) | (my > H - 1)] = np.nan
        return out

    # 2. the foreground, stacked on the ground
    ground = np.empty((H, W, 3), np.float32)
    seen_by = np.zeros((H, W), np.int16)       # subs that saw each bit of ground
    for r0 in range(0, H, BLOCK_ROWS):
        r1 = min(r0 + BLOCK_ROWS, H)
        _progress(progress, 0.3 + 0.3 * r0 / H, f"Foreground stack, rows {r0}-{r1}", None)
        block = np.stack([sample(subs[k], *maps(k, r0, r1, True)) for k in range(n)])
        seen_by[r0:r1] = np.isfinite(block[..., 1]).sum(axis=0)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ground[r0:r1] = np.nanmedian(block, axis=0)
    _progress(progress, 0.6, "Foreground stacked on the ground", log)

    # 3. its mask - where the first subs, registered on the stars, show stars is sky
    from api.mosaic_wcs import sky_mask
    first = [k for k in range(n) if (times[k] - times[0]).total_seconds() <= STARS_SPAN_S][:6]
    early = np.zeros((H, W), np.float32)
    for k in first:
        lum = subs[k].mean(axis=2, dtype=np.float32)
        early += cv2.warpAffine(lum, to_sub[k][:2].astype(np.float32), (W, H),
                                flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REPLICATE)
    starry = sky_mask(early / len(first))
    fg, _ = _foreground(ground, np.isfinite(ground).all(axis=2), starry)
    result["foreground_pct"] = round(100 * float(fg.mean()))
    print_log(f"Foreground: {result['foreground_pct']}% of the frame", log)
    halo = binary_dilation(fg, iterations=FG_HALO_PX).astype(np.uint8)

    # 4. the sky, stacked on the stars, each sub where its own foreground wasn't
    sky = np.empty((H, W, 3), np.float32)
    nsky = np.zeros((H, W), np.int16)
    for r0 in range(0, H, BLOCK_ROWS):
        r1 = min(r0 + BLOCK_ROWS, H)
        _progress(progress, 0.62 + 0.3 * r0 / H, f"Sky stack, rows {r0}-{r1}", None)
        vals = []
        for k in range(n):
            mx, my = maps(k, r0, r1, False)
            v = sample(subs[k], mx, my)
            # the halo moved to where sub k saw that ground: ground map's inverse,
            # near enough as the reference grid shifted back
            rows = np.arange(r0, r1, dtype=np.float32)
            hx, hy = np.meshgrid(cols, rows)
            hx = hx - splines[k][0](rows, cols).astype(np.float32)
            hy = hy - splines[k][1](rows, cols).astype(np.float32)
            hidden = cv2.remap(halo, hx, hy, cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT, borderValue=1) > 0
            v[hidden] = np.nan
            vals.append(v)
        V = np.stack(vals)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            med = np.nanmedian(V, axis=0)
            mad = 1.4826 * np.nanmedian(np.abs(V - med), axis=0) + 1e-3
            V[np.abs(V - med) > 3 * mad] = np.nan       # satellites, planes, outliers
            sky[r0:r1] = np.nanmean(V, axis=0)
        nsky[r0:r1] = np.isfinite(V[..., 1]).sum(axis=0)
    _progress(progress, 0.93, "Sky stacked on the stars", log)

    # 5. blend in the reference geometry, crop what not every sub saw
    alpha = np.clip(distance_transform_edt(fg) / BLEND_PX, 0, 1)
    alpha = np.where(nsky == 0, 1.0, alpha)[..., None].astype(np.float32)
    out = np.nan_to_num(sky) * (1 - alpha) + np.nan_to_num(ground) * alpha
    # the result's frame: sky seen by some sub, foreground by most of them
    seen = np.where(alpha[..., 0] > 0, seen_by >= max(n // 2, 1), nsky > 0)
    cols_ok = np.where(seen.mean(axis=0) > 0.97)[0]
    rows_ok = np.where(seen[:, cols_ok[0]:cols_ok[-1] + 1].mean(axis=1) > 0.97)[0] if len(cols_ok) else []
    if len(cols_ok) and len(rows_ok):
        crop = (slice(rows_ok[0], rows_ok[-1] + 1), slice(cols_ok[0], cols_ok[-1] + 1))
    else:
        crop = (slice(0, H), slice(0, W))
    out, fg = out[crop], fg[crop]
    wcs = wcs[crop]

    _progress(progress, 0.95, "Writing...", log)
    out_fits.parent.mkdir(parents=True, exist_ok=True)
    chw = np.ascontiguousarray(np.moveaxis(out, -1, 0), dtype=np.float32)
    header = wcs.to_header(relax=True)
    header["COMMENT"] = (f"Foreground fixed by Dwarfium Scope Archive from {n} raw subs of {session_dir.name}: "
                         "sky stacked on the stars, foreground on the ground")
    for key in ("TELESCOP", "INSTRUME", "CAMERA", "FIRMWARE", "EXPTIME", "GAIN", "OBJECT", "FOCALLEN", "XPIXSZ"):
        if key in headers[0]:
            header[key] = headers[0][key]
    header["DATE-OBS"] = headers[0]["DATE-OBS"]
    header["STACKCNT"] = n
    fits.PrimaryHDU(chw, header=header).writeto(out_fits, overwrite=True)
    base = re.sub(r"\.fits?$", "", str(out_fits), flags=re.IGNORECASE)
    # the preview and the TIFFs the way round the Dwarf and the app show its
    # frames (rows as stored - write_preview turns a mosaic north up);
    # one stretch for both TIFFs: they lay back together in an image editor
    write_preview(chw[:, ::-1], np.ones(fg.shape, bool), base + "_preview.jpg")
    stretched = _stretched(chw, ~fg)
    sky_tif, ground_tif = base + "_sky.tif", base + "_ground.tif"
    soft = np.clip(distance_transform_edt(fg) / BLEND_PX, 0, 1)
    ok_sky = write_rgba_tiff(stretched, 1 - soft, sky_tif, flip=False)
    ok_ground = write_rgba_tiff(stretched, soft, ground_tif, flip=False)
    result.update(ok=True, fits=str(out_fits), preview=base + "_preview.jpg",
                  sky_tif=sky_tif if ok_sky else None, ground_tif=ground_tif if ok_ground else None)
    _progress(progress, 1.0, f"Foreground fixed: {out_fits}", log)
    return result
