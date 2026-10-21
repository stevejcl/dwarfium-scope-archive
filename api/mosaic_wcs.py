"""
api/mosaic_wcs.py

Mosaic of plate-solved tiles (user-requested Oct 2026: a Milky Way mosaic
of wide-angle tiles - the image stitchers (Affinity) kept the roof and the
trees, bent the 70 degrees of sky, and could not level the tiles).

Each tile goes where its sky really is, from its astrometry:
1. its WCS - the FITS header's, else a solve (api/astrometry_resolver.py),
   then refit against the Bright Star Catalogue with a TAN-SIP distortion
   of order 4 (order 2 left 2-4 px at the edges of a 46 deg field, enough
   to double the stars in the overlaps);
2. the foreground (roof, trees, branches) masked out: areas without stars,
   or clearly darker than the sky;
3. resampled onto a common stereographic grid centred on the mosaic (its
   pixel mapping computed once per tile, on the area it covers);
4. levelled to its neighbours (gain + offset per channel, from the
   overlaps, propagated from the best connected tile);
5. blended with short transitions where the tile seen nearer its centre
   wins (a wide-angle tile's corners have stretched stars).

Output: a linear 32-bit float FITS with the mosaic's WCS (for Siril:
background extraction, photometric colour calibration, stretch) and a
stretched JPEG preview.

Pure functions only - no NiceGUI/UI code here.
"""

from __future__ import annotations

import os
import re
import warnings
from pathlib import Path

import numpy as np

from api.dwarf_backup_fct import print_log

CATALOG_FILE = Path(__file__).resolve().parent.parent / "assets" / "catalog" / "bsc5_radec.csv"

MARGIN_PX = 8          # trimmed on each tile edge (stacking / dither borders)
FEATHER_PX = 120       # a tile fades in over this many px from its edge / mask
EDGE_POWER = 4         # > 1: shorter hand-over between tiles
CENTRE_POWER = 8       # how strongly a tile's centre beats another one's edge
SIP_ORDER = 4
MIN_STARS_SIP4 = 50    # fewer catalogue stars: order 3 (4 runs wild outside them)
LEVEL_SCALE = 4        # levelling estimated on a grid this many times coarser
ROWS_PER_BLOCK = 256   # frame rows mapped to a tile's pixels at once


def _progress(cb, fraction, message, log=None):
    print_log(message, log)
    if cb:
        try:
            cb(fraction, message)
        except Exception:
            pass


def load_catalog():
    """The Bright Star Catalogue as a SkyCoord (about 9100 stars, V < 6.5)."""
    from astropy.coordinates import SkyCoord
    import astropy.units as u
    data = np.loadtxt(CATALOG_FILE, delimiter=",", comments="#", usecols=(0, 1))
    return SkyCoord(data[:, 0] * u.deg, data[:, 1] * u.deg)


# ---------------------------------------------------------------- tiles

def load_tile(path):
    """(data (C, H, W) float32, header) of a FITS tile; mono gives C = 1."""
    from astropy.io import fits
    with fits.open(path) as hdul:
        hdu = next(h for h in hdul if h.data is not None and h.data.ndim in (2, 3))
        data = hdu.data.astype(np.float32)
        header = hdu.header.copy()
    if data.ndim == 2:
        data = data[None]
    return data, header


def header_wcs(header):
    """The header's celestial WCS, or None."""
    from astropy.wcs import WCS
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            w = WCS(header, naxis=2)
        except Exception:
            return None
    return w if w.has_celestial and w.wcs.ctype[0].startswith("RA") else None


def solver_settings(conn) -> dict:
    """The solvers' settings (Nova API key, ASTAP database), read in the
    caller's thread - build_mosaic() runs in a worker one."""
    from api.dwarf_backup_db_api import get_setting_text
    return {"api_key": get_setting_text(conn, "NOVA_ASTRO_API") or "",
            "astap_db": get_setting_text(conn, "ASTAP_DB") or "D50"}


def solve_tile(path, settings=None, log=None):
    """Plate-solves a tile with the app's solvers (ASTAP, solve-field, Nova)
    - its green channel, like the astrometry scan - and returns its linear
    WCS, or None."""
    from astropy.wcs import WCS
    from api.astrometry_resolver import auto_resolve
    from tools.astrometry_scan import extract_mono_fits, extract_wcs_from_file, _cleanup_temp
    settings = settings or {}
    api_key, astap_db = settings.get("api_key", ""), settings.get("astap_db", "D50")
    mono = extract_mono_fits(Path(path))
    if not mono:
        return None
    try:
        wcs_file = auto_resolve(api_key, str(mono), log=log, astap_db=astap_db)
        # its whole header when it reads as one (ASTAP's .wcs, a solved
        # FITS): the distortion terms with it, a big help on a wide field
        try:
            from astropy.io import fits
            full = header_wcs(fits.getheader(wcs_file))
        except Exception:
            full = None
        if full is not None:
            return full
        d = extract_wcs_from_file(wcs_file)
    except Exception as e:
        print_log(f"Solve failed for {Path(path).name}: {e}", log)
        return None
    finally:
        if str(mono) != str(path):
            _cleanup_temp(mono)
    if not d or d.get("cd1_1") is None:
        return None
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [d["crval1"], d["crval2"]]
    w.wcs.crpix = [d["crpix1"], d["crpix2"]]
    w.wcs.cd = [[d["cd1_1"], d["cd1_2"]], [d["cd2_1"], d["cd2_2"]]]
    return w


def _detect_stars(lum, keep=500):
    """(x, y) centroids of the brightest stars, brightest first."""
    from scipy.ndimage import median_filter, maximum_filter
    hp = lum - median_filter(lum, 11)
    noise = 1.4826 * np.median(np.abs(hp - np.median(hp)))
    pk = (hp == maximum_filter(hp, 9)) & (hp > 10 * noise)
    pk[:6, :] = pk[-6:, :] = pk[:, :6] = pk[:, -6:] = False
    y, x = np.nonzero(pk)
    order = np.argsort(-hp[y, x])[:keep]
    y, x = y[order], x[order]
    gy, gx = np.mgrid[-2:3, -2:3]
    cx, cy = np.empty(len(x)), np.empty(len(x))
    for k, (xx, yy) in enumerate(zip(x, y)):
        box = np.clip(hp[yy - 2:yy + 3, xx - 2:xx + 3], 0, None)
        s = box.sum() or 1.0
        cx[k], cy[k] = xx + (gx * box).sum() / s, yy + (gy * box).sum() / s
    return cx, cy


# Refit passes: (part of the frame used, match radius px, SIP order -
# None: linear). A linear WCS of a 46 deg wide-angle tile is 20 px off on
# median and 100 px at the corners (the lens' distortion): the frame's
# centre first, where it holds, then wider with more distortion terms -
# each pass matching with the previous one's WCS.
REFIT_PASSES = ((0.4, 15, None), (0.7, 8, 2), (1.0, 5, 3), (1.0, 3, SIP_ORDER))


def _vote_offset(px, py, bx, by, reach=60, bin_px=2):
    """The shift (dx, dy) most catalogue / detected star pairs agree on,
    within `reach` px: a solver's linear WCS of a wide-angle tile is
    shifted by 20-25 px even at its centre."""
    dx = bx[None, :] - px[:, None]
    dy = by[None, :] - py[:, None]
    near = (np.abs(dx) < reach) & (np.abs(dy) < reach)
    if near.sum() < 10:
        return 0.0, 0.0
    dx, dy = dx[near], dy[near]
    hist, ex, ey = np.histogram2d(dx, dy, bins=int(2 * reach / bin_px), range=[[-reach, reach], [-reach, reach]])
    i, j = np.unravel_index(hist.argmax(), hist.shape)
    cx, cy = (ex[i] + ex[i + 1]) / 2, (ey[j] + ey[j + 1]) / 2
    close = np.hypot(dx - cx, dy - cy) < 3 * bin_px
    return float(np.median(dx[close])), float(np.median(dy[close]))


def _refit_passes(w, catalog, bx, by, shape, log, name):
    """REFIT_PASSES from the WCS `w`: (wcs, stars, rms px) of the last pass
    that worked - (w, 0, None) when none did."""
    from astropy.wcs.utils import fit_wcs_from_points
    ny, nx = shape
    stars, rms = 0, None
    for part, radius, order in REFIT_PASSES:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            px, py = w.world_to_pixel(catalog)
        inside = (np.isfinite(px) & np.isfinite(py) & (px > 5) & (px < nx - 5) & (py > 5) & (py < ny - 5)
                  & (np.abs(px - nx / 2) <= part * nx / 2) & (np.abs(py - ny / 2) <= part * ny / 2))
        px, py, cat = px[inside], py[inside], catalog[inside]
        if len(px) == 0 or len(bx) == 0:
            break
        d2 = (px[:, None] - bx[None, :]) ** 2 + (py[:, None] - by[None, :]) ** 2
        j = d2.argmin(axis=1)
        d = np.sqrt(d2[np.arange(len(j)), j])
        ok = d < radius
        uj, cnt = np.unique(j[ok], return_counts=True)
        ok &= ~np.isin(j, uj[cnt > 1])                 # one star claimed twice: ambiguous
        if ok.sum() < 12:
            continue
        mx, my, mcat = bx[j[ok]], by[j[ok]], cat[ok]
        if order is not None and order > 3 and len(mx) < MIN_STARS_SIP4:
            order = 3
        sel = np.ones(len(mx), bool)
        try:
            for _ in range(4):
                fitted = fit_wcs_from_points((mx[sel], my[sel]), mcat[sel], projection="TAN", sip_degree=order)
                res = np.hypot(*(np.array(fitted.world_to_pixel(mcat)) - np.array([mx, my])))
                if not np.isfinite(res[sel]).all():
                    raise ValueError("non-finite residuals")
                sel = res < max(3 * np.median(res[sel]), 1.0)
        except ValueError as e:
            print_log(f"{name}: refit pass ({part:.0%} of the frame, {radius} px, SIP {order}) failed ({e})", log)
            continue
        w = fitted
        stars, rms = int(sel.sum()), float(np.sqrt(np.mean(res[sel] ** 2)))
    return w, stars, rms


def refit_wcs(lum, wcs, catalog, log=None, name=""):
    """The tile's WCS refit on the catalogue stars it shows (TAN-SIP), in
    REFIT_PASSES - from the given WCS and from it shifted by the offset most
    star pairs agree on (_vote_offset), the one matching the most stars
    kept. Returns (wcs, stars, rms px); the given WCS when too few stars
    match."""
    ny, nx = lum.shape
    bx, by = _detect_stars(lum)
    # only the stars around the tile: a TAN projection also lands some from
    # the other side of the sky inside the frame
    centre = wcs.pixel_to_world(nx / 2, ny / 2)
    corner = wcs.pixel_to_world(0, 0)
    catalog = catalog[catalog.separation(centre) < centre.separation(corner) * 1.1]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        px, py = wcs.world_to_pixel(catalog)
    central = (np.isfinite(px) & np.isfinite(py)
               & (np.abs(px - nx / 2) <= 0.6 * nx / 2) & (np.abs(py - ny / 2) <= 0.6 * ny / 2))
    starts = [wcs]
    shift = _vote_offset(px[central], py[central], bx[:200], by[:200])
    if np.hypot(*shift) > 1:
        shifted = wcs.deepcopy()
        shifted.wcs.crpix = shifted.wcs.crpix + np.array(shift)
        starts.append(shifted)
    best = (wcs, 0, None)
    for start in starts:
        w, stars, rms = _refit_passes(start, catalog, bx, by, (ny, nx), log, name)
        if rms is not None and stars > best[1]:
            best = (w, stars, rms)
    w, stars, rms = best
    if rms is None:
        print_log(f"{name}: too few catalogue stars, the solver's WCS is kept", log)
        return wcs, 0, None
    print_log(f"{name}: {stars} catalogue stars, residual {rms:.2f} px", log)
    return w, stars, rms


FG_ISLAND_MAX = 0.02   # a foreground patch not touching the frame's edge is kept only above this part of it


def sky_mask(lum):
    """True where the sky shows stars - False on the foreground (roof,
    trees: no stars, or clearly darker than the sky)."""
    from scipy.ndimage import median_filter, uniform_filter, binary_opening, binary_closing, zoom, label
    small = lum[::2, ::2]
    hp = small - median_filter(small, size=9)
    noise = 1.4826 * np.median(np.abs(hp - np.median(hp)))
    stars = (hp > 5 * noise).astype(np.float32)
    density = uniform_filter(stars, size=40)
    # the starriest part sets the reference: on a tile mostly roof, the
    # median is the roof's noise
    sky = density > 0.15 * np.percentile(density, 90)
    # dark silhouettes still show stars through the leaves on linear data
    level = median_filter(small, size=31)
    if sky.any():
        ref = np.median(level[sky])
        spread = 1.4826 * np.median(np.abs(level[sky] - ref))
        sky &= level > ref - max(4 * spread, 0.04 * ref)
    sky = binary_opening(binary_closing(sky, iterations=6), iterations=10)
    # foreground comes into the frame from an edge (trees, a roof): an island
    # of it in the middle of the sky is a patch where fewer stars happened to
    # be detected (user-found Oct 2026: small holes in an open sky), unless
    # it's large
    fg, n = label(~sky)
    if n:
        sizes = np.bincount(fg.ravel())
        edge = np.unique(np.r_[fg[0], fg[-1], fg[:, 0], fg[:, -1]])
        island = np.ones(n + 1, bool)
        island[0] = False
        island[edge] = False
        island[sizes > FG_ISLAND_MAX * fg.size] = False
        sky |= island[fg]
    sky = zoom(sky.astype(np.uint8), 2, order=0).astype(bool)
    out = np.zeros(lum.shape, bool)
    out[:sky.shape[0], :sky.shape[1]] = sky[:lum.shape[0], :lum.shape[1]]
    return out


def tile_weights(good):
    """(blend weight, edge weight): the edge weight fades in from the tile's
    edge and mask; the blend weight also favours the tile's centre."""
    from scipy.ndimage import distance_transform_edt
    good = good.copy()
    good[0, :] = good[-1, :] = good[:, 0] = good[:, -1] = False
    edge = np.clip(distance_transform_edt(good) / FEATHER_PX, 0, 1).astype(np.float32) ** EDGE_POWER
    ny, nx = good.shape
    yy, xx = np.mgrid[0:ny, 0:nx].astype(np.float32)
    r = np.hypot((xx - nx / 2) / (nx / 2), (yy - ny / 2) / (ny / 2)) / np.sqrt(2)
    return edge * np.clip(1 - r, 0.02, 1) ** CENTRE_POWER, edge


# ---------------------------------------------------------------- mosaic frame

def mosaic_frame(tiles):
    """Stereographic WCS centred on the mean tile direction, north up, at
    the tiles' median scale, and its shape covering every tile."""
    from astropy.wcs import WCS
    from astropy.coordinates import SkyCoord
    vec = np.zeros(3)
    edges = []
    for t in tiles:
        ny, nx = t["shape"]
        vec += t["wcs"].pixel_to_world(nx / 2, ny / 2).cartesian.xyz.value
        s = np.linspace(0, 1, 40)
        xs = np.r_[s * (nx - 1), np.full(40, nx - 1), s * (nx - 1), np.zeros(40)]
        ys = np.r_[np.zeros(40), s * (ny - 1), np.full(40, ny - 1), s * (ny - 1)]
        edges.append(t["wcs"].pixel_to_world(xs, ys))
    centre = SkyCoord(x=vec[0], y=vec[1], z=vec[2], representation_type="cartesian").spherical
    scale = float(np.median([np.sqrt(abs(np.linalg.det(t["wcs"].pixel_scale_matrix))) for t in tiles]))
    ow = WCS(naxis=2)
    ow.wcs.ctype = ["RA---STG", "DEC--STG"]
    ow.wcs.crval = [centre.lon.deg, centre.lat.deg]
    ow.wcs.cdelt = [-scale, scale]
    ow.wcs.crpix = [0, 0]
    xs = np.concatenate([ow.world_to_pixel(e)[0] for e in edges])
    ys = np.concatenate([ow.world_to_pixel(e)[1] for e in edges])
    ow.wcs.crpix = [-xs.min() + 2, -ys.min() + 2]
    shape = (int(np.ceil(ys.max() - ys.min())) + 4, int(np.ceil(xs.max() - xs.min())) + 4)
    return ow, shape


def _coarse(ow, shape, k):
    """The same frame k times coarser."""
    cw = ow.deepcopy()
    cw.wcs.cdelt = ow.wcs.cdelt * k
    cw.wcs.crpix = (ow.wcs.crpix - 0.5) / k + 0.5
    return cw, (shape[0] // k + 1, shape[1] // k + 1)


def level_tiles(tiles, ow, shape, nch):
    """Gain + offset per tile and channel (25th / 75th percentiles of the
    shared sky matched), from the tile with the most overlap, on a coarse
    grid. Returns (gains, offsets) lists."""
    cw, cshape = _coarse(ow, shape, LEVEL_SCALE)
    proj, edge = [], []
    for t in tiles:            # full-resolution tiles sampled onto the coarse grid
        resample = TileResampler(t["wcs"], t["shape"], cw, cshape)
        win = resample.window()
        p = np.full((nch,) + cshape, np.nan, np.float32)
        for c in range(nch):
            p[c][win] = np.where(resample.inside, resample(t["data"][c]), np.nan)
        e = np.zeros(cshape, np.float32)
        e[win] = resample(t["edge"])
        proj.append(p)
        edge.append(e)
    n = len(tiles)
    overlap = np.zeros((n, n), int)
    for i in range(n):
        for j in range(i + 1, n):
            overlap[i, j] = overlap[j, i] = np.count_nonzero((edge[i] > 0.2) & (edge[j] > 0.2))
    ref = int(overlap.sum(1).argmax())
    gain, offs = {ref: np.ones(nch)}, {ref: np.zeros(nch)}
    while len(gain) < n:
        i, j = max(((i, j) for i in gain for j in range(n) if j not in gain), key=lambda p: overlap[p])
        g, o = np.ones(nch), np.zeros(nch)
        m = (edge[i] > 0.2) & (edge[j] > 0.2)
        if overlap[i, j] >= 200:
            for c in range(nch):
                a = proj[i][c][m] * gain[i][c] + offs[i][c]
                b = proj[j][c][m]
                (a1, a2), (b1, b2) = np.nanpercentile(a, [25, 75]), np.nanpercentile(b, [25, 75])
                if b2 > b1:
                    g[c] = (a2 - a1) / (b2 - b1)
                    o[c] = a1 - g[c] * b1
        gain[j], offs[j] = g, o
    return [gain[k] for k in range(n)], [offs[k] for k in range(n)]


class TileResampler:
    """A tile resampled onto the mosaic frame: the frame pixels it covers
    (its bounding box) mapped once to the tile's pixels through both WCS,
    then each array (channels, weights) interpolated with that mapping - a
    reproject call per array recomputed the whole frame's mapping each time
    (2 GB, several minutes for 5 tiles)."""

    def __init__(self, tile_wcs, tile_shape, frame_wcs, frame_shape):
        ny, nx = tile_shape
        s = np.linspace(0, 1, 60)
        xs = np.r_[s * (nx - 1), np.full(60, nx - 1), s * (nx - 1), np.zeros(60)]
        ys = np.r_[np.zeros(60), s * (ny - 1), np.full(60, ny - 1), s * (ny - 1)]
        fx, fy = frame_wcs.world_to_pixel(tile_wcs.pixel_to_world(xs, ys))
        self.x0 = max(int(np.floor(np.nanmin(fx))) - 2, 0)
        self.y0 = max(int(np.floor(np.nanmin(fy))) - 2, 0)
        x1 = min(int(np.ceil(np.nanmax(fx))) + 3, frame_shape[1])
        y1 = min(int(np.ceil(np.nanmax(fy))) + 3, frame_shape[0])
        self.shape = (max(y1 - self.y0, 0), max(x1 - self.x0, 0))
        self.coords = np.empty((2,) + self.shape, np.float32)
        xs = np.arange(self.x0, x1)
        for r0 in range(0, self.shape[0], ROWS_PER_BLOCK):        # by blocks: bounded memory
            rows = np.arange(self.y0 + r0, min(self.y0 + r0 + ROWS_PER_BLOCK, y1))
            gx, gy = np.meshgrid(xs, rows)
            tx, ty = tile_wcs.world_to_pixel(frame_wcs.pixel_to_world(gx.ravel(), gy.ravel()))
            self.coords[0, r0:r0 + len(rows)] = np.asarray(ty, np.float32).reshape(gx.shape)
            self.coords[1, r0:r0 + len(rows)] = np.asarray(tx, np.float32).reshape(gx.shape)
        self.inside = ((self.coords[0] >= -0.5) & (self.coords[0] <= ny - 0.5)
                       & (self.coords[1] >= -0.5) & (self.coords[1] <= nx - 0.5))

    def __call__(self, array):
        """`array` (the tile's shape) on the bounding box, 0 outside the tile."""
        from scipy.ndimage import map_coordinates
        out = map_coordinates(array, self.coords, order=1, mode="nearest", output=np.float32)
        out[~self.inside] = 0
        return out

    def window(self):
        return slice(self.y0, self.y0 + self.shape[0]), slice(self.x0, self.x0 + self.shape[1])


# ---------------------------------------------------------------- main

def build_mosaic(paths, out_fits, settings=None, log=None, progress=None, solve=True):
    """
    Assembles the FITS tiles `paths` into `out_fits` (linear float32, WCS
    in its header) and a stretched preview next to it (same name, .jpg).

    A tile without a celestial WCS in its header is plate-solved when
    `solve` (the app's solvers, `settings` from solver_settings()), else
    left out.
    progress(fraction 0-1, message) is called along the way.

    Also writes the sky alone, stretched, 16-bit with the foreground
    transparent (same name, _sky.tif), for blending over a foreground shot
    in an image editor.

    Returns {"ok", "fits", "preview", "tiff", "tiles": [{"name", "stars", "rms",
    "sky_pct"}], "skipped": [{"name", "reason"}], "error"}.
    """
    from astropy.io import fits

    result = {"ok": False, "fits": None, "preview": None, "tiff": None, "tiles": [], "skipped": [], "error": None}
    catalog = load_catalog()
    tiles = []
    n = len(paths)
    for k, path in enumerate(paths):
        name = Path(path).name
        _progress(progress, 0.4 * k / max(n, 1), f"Tile {k + 1}/{n}: {name}", log)
        try:
            data, header = load_tile(path)
        except Exception as e:
            result["skipped"].append({"name": name, "reason": f"unreadable: {e}"})
            continue
        w = header_wcs(header)
        if w is None and solve:
            _progress(progress, 0.4 * k / max(n, 1), f"Plate solving {name}...", log)
            w = solve_tile(path, settings, log)
        if w is None:
            result["skipped"].append({"name": name, "reason": "no astrometric solution"})
            continue
        lum = data.mean(axis=0)
        w, stars, rms = refit_wcs(lum, w, catalog, log, name)
        data = data[:, MARGIN_PX:-MARGIN_PX, MARGIN_PX:-MARGIN_PX]
        w = w[MARGIN_PX:-MARGIN_PX, MARGIN_PX:-MARGIN_PX]
        good = sky_mask(data.mean(axis=0))
        print_log(f"{name}: sky kept {100 * good.mean():.0f}% (foreground left out)", log)
        weight, edge = tile_weights(good)
        tiles.append({"name": name, "data": data, "wcs": w, "weight": weight, "edge": edge,
                      "shape": data.shape[1:]})
        result["tiles"].append({"name": name, "stars": stars, "rms": rms,
                                "sky_pct": round(100 * float(good.mean()))})
    if len(tiles) < 2:
        result["error"] = "need at least two solved tiles"
        return result
    nch = min(t["data"].shape[0] for t in tiles)

    ow, shape = mosaic_frame(tiles)
    _progress(progress, 0.45, f"Mosaic frame {shape[1]} x {shape[0]} px, levelling the tiles...", log)
    gains, offs = level_tiles(tiles, ow, shape, nch)
    for t, g in zip(tiles, gains):
        print_log(f"{t['name']}: levelled, gain {' / '.join(f'{x:.2f}' for x in g)}", log)

    acc = np.zeros((nch,) + shape, np.float32)
    wsum = np.zeros(shape, np.float32)
    esum = np.zeros(shape, np.float32)
    for k, t in enumerate(tiles):
        _progress(progress, 0.5 + 0.4 * k / len(tiles), f"Reprojecting {t['name']}...", log)
        resample = TileResampler(t["wcs"], t["shape"], ow, shape)
        win = resample.window()
        pw = resample(t["weight"])
        for c in range(nch):
            acc[c][win] += (resample(t["data"][c]) * gains[k][c] + offs[k][c]) * pw
        wsum[win] += pw
        esum[win] += resample(t["edge"])
        t["data"] = None                                  # free it as we go

    _progress(progress, 0.92, "Writing the mosaic...", log)
    covered = (esum > 1e-6) & (wsum > 0)
    del esum
    norm = np.maximum(wsum, 1e-30).astype(np.float32)   # a lone tile's corner: tiny but > 0
    del wsum
    mos = acc                                            # normalised in place, channel by channel
    for c in range(nch):
        mos[c] /= norm
        mos[c][~covered] = 0
    del norm
    sample = mos[:, covered][:, ::7]                     # black / white points from a sample
    lo, hi = np.percentile(sample, 0.05), np.percentile(sample, 99.995)
    del sample
    for c in range(nch):
        mos[c] -= lo
        mos[c] /= max(hi - lo, 1e-12)
        np.clip(mos[c], 0, 1, out=mos[c])
        mos[c][~covered] = 0

    header = ow.to_header()
    header["COMMENT"] = "Linear mosaic (Dwarfium Scope Archive) of: " + ", ".join(t["name"] for t in tiles)
    out_fits = str(out_fits)
    os.makedirs(os.path.dirname(out_fits) or ".", exist_ok=True)
    fits.PrimaryHDU(mos if nch > 1 else mos[0], header=header).writeto(out_fits, overwrite=True)

    base = re.sub(r"\.fits?$", "", out_fits, flags=re.IGNORECASE)
    preview = base + "_preview.jpg"
    write_preview(mos, covered, preview)
    _progress(progress, 0.96, "Writing the sky with a transparent foreground (TIFF)...", log)
    tiff = base + "_sky.tif"
    if not write_sky_tiff(mos, covered, tiff):
        tiff = None
    result.update(ok=True, fits=out_fits, preview=preview, tiff=tiff)
    _progress(progress, 1.0, f"Mosaic written: {out_fits}", log)
    return result


def _stretched(mos, covered):
    """The mosaic stretched for viewing (asinh, per channel), 0-1, 3 channels."""
    prev = np.empty_like(mos)
    for c in range(mos.shape[0]):
        v = mos[c][covered]
        if v.size == 0:
            prev[c] = 0
            continue
        b, t = np.percentile(v, 1), np.percentile(v, 99.8)
        prev[c] = np.arcsinh(10 * np.clip((mos[c] - b) / max(t - b, 1e-12), 0, 1)) / np.arcsinh(10)
    prev[:, ~covered] = 0
    if prev.shape[0] == 1:
        prev = np.repeat(prev, 3, axis=0)
    return prev


def write_preview(mos, covered, path, max_side=2000):
    """A stretched JPEG of the mosaic, north up."""
    from PIL import Image
    prev = _stretched(mos, covered)
    img = Image.fromarray((np.transpose(prev, (1, 2, 0))[::-1] * 255).astype(np.uint8))  # FITS y goes up
    img.thumbnail((max_side, max_side))
    img.save(path, quality=90)


TIFF_FEATHER_PX = 12   # the sky fades out over this many px towards the foreground


def write_sky_tiff(mos, covered, path):
    """The stretched mosaic as a 16-bit RGBA TIFF, north up, transparent
    where no sky was kept (foreground, outside the tiles) and fading in over
    TIFF_FEATHER_PX - the 4th channel tagged as unassociated alpha, as
    image editors expect (OpenCV leaves the tag out). False when it could
    not be written."""
    import tifffile
    from scipy.ndimage import distance_transform_edt
    prev = _stretched(mos, covered)
    rgba = np.empty(prev.shape[1:] + (4,), np.uint16)
    for c in range(3):
        rgba[..., c] = np.round(prev[c] * 65535)
    del prev
    rgba[..., 3] = np.round(np.clip(distance_transform_edt(covered) / TIFF_FEATHER_PX, 0, 1) * 65535)
    try:
        tifffile.imwrite(path, rgba[::-1], photometric="rgb", extrasamples=["unassalpha"],
                         compression="zlib")                    # FITS y goes up
    except (OSError, ValueError) as e:
        print_log(f"Sky TIFF not written: {e}")
        return False
    return True
