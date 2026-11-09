"""Target altitude over a night - pure-Python, no astropy (user-requested
Oct 2026: "une fois l'objet selectionne on pourrait voir sa hauteur dans
le ciel pour choisir le meilleur creneau").

Low-precision formulas (Meeus / the Astronomical Almanac's "low
precision" Sun and Moon) - good to well under a degree, which is all a
"when is it high enough, and is it dark yet" planning curve needs, and
keeps the frozen .exe free of a heavy astronomy dependency.

All datetimes here are NAIVE wall-clock times in `tz` - both editors
pass the Dwarf's SITE timezone (components/site_time.py), the clock
program and native-schedule times are typed in and checked against, so
a slot picked on the chart is exactly what will run. tz=None means this
PC's local time. Converted to UTC internally, DST included."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone, tzinfo

_DEG = math.pi / 180.0

# Sun altitude below which the sky counts as "dark", per darkness choice.
DARKNESS_LEVELS = {"astronomical": -18.0, "nautical": -12.0, "civil": -6.0}


def _julian_date(dt_utc: datetime) -> float:
    return dt_utc.timestamp() / 86400.0 + 2440587.5


def _local_sidereal_deg(jd: float, longitude_deg: float) -> float:
    d = jd - 2451545.0
    gmst = 280.46061837 + 360.98564736629 * d
    return (gmst + longitude_deg) % 360.0


def _altitude_deg(ra_deg: float, dec_deg: float, lst_deg: float, lat_deg: float) -> float:
    ha = (lst_deg - ra_deg) * _DEG
    lat = lat_deg * _DEG
    dec = dec_deg * _DEG
    sin_alt = math.sin(lat) * math.sin(dec) + math.cos(lat) * math.cos(dec) * math.cos(ha)
    return math.degrees(math.asin(max(-1.0, min(1.0, sin_alt))))


def _azimuth_deg(ra_deg: float, dec_deg: float, lst_deg: float, lat_deg: float) -> float:
    """Azimuth measured from North through East (0=N, 90=E, 180=S, 270=W)."""
    ha = (lst_deg - ra_deg) * _DEG
    lat = lat_deg * _DEG
    dec = dec_deg * _DEG
    az = math.atan2(-math.sin(ha), math.tan(dec) * math.cos(lat) - math.sin(lat) * math.cos(ha))
    return math.degrees(az) % 360.0


# 8-point compass, in azimuth order (N, NE, E, ...) - index = round(az / 45) % 8.
COMPASS_POINTS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def compass_index(azimuth_deg: float) -> int:
    """Index into COMPASS_POINTS for an azimuth (0=N, clockwise)."""
    return int(round(azimuth_deg / 45.0)) % 8


def _ecliptic_to_equatorial(lon_deg: float, lat_deg: float, jd: float) -> tuple[float, float]:
    eps = (23.439 - 0.0000004 * (jd - 2451545.0)) * _DEG
    lon, lat = lon_deg * _DEG, lat_deg * _DEG
    ra = math.atan2(math.sin(lon) * math.cos(eps) - math.tan(lat) * math.sin(eps), math.cos(lon))
    dec = math.asin(math.sin(lat) * math.cos(eps) + math.cos(lat) * math.sin(eps) * math.sin(lon))
    return math.degrees(ra) % 360.0, math.degrees(dec)


def sun_radec(jd: float) -> tuple[float, float, float]:
    """(ra_deg, dec_deg, ecliptic_longitude_deg) of the Sun."""
    d = jd - 2451545.0
    g = (357.529 + 0.98560028 * d) * _DEG
    q = 280.459 + 0.98564736 * d
    lon = (q + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g)) % 360.0
    ra, dec = _ecliptic_to_equatorial(lon, 0.0, jd)
    return ra, dec, lon


def moon_radec(jd: float) -> tuple[float, float, float]:
    """(ra_deg, dec_deg, ecliptic_longitude_deg) of the Moon, geocentric
    (parallax ignored - under 1 deg, irrelevant for a planning chart)."""
    t = (jd - 2451545.0) / 36525.0
    lp = 218.32 + 481267.881 * t
    mp = (134.9 + 477198.85 * t) * _DEG
    m = (357.5 + 35999.05 * t) * _DEG
    f = (93.3 + 483202.03 * t) * _DEG
    d = (297.85 + 445267.11 * t) * _DEG
    lon = (lp + 6.29 * math.sin(mp) - 1.27 * math.sin(mp - 2 * d) + 0.66 * math.sin(2 * d)
           + 0.21 * math.sin(2 * mp) - 0.19 * math.sin(m) - 0.11 * math.sin(2 * f)) % 360.0
    lat = 5.13 * math.sin(f) + 0.28 * math.sin(mp + f) - 0.28 * math.sin(f - mp) - 0.17 * math.sin(f - 2 * d)
    ra, dec = _ecliptic_to_equatorial(lon, lat, jd)
    return ra, dec, lon


def angular_separation_deg(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    r1, d1, r2, d2 = ra1 * _DEG, dec1 * _DEG, ra2 * _DEG, dec2 * _DEG
    cos_sep = math.sin(d1) * math.sin(d2) + math.cos(d1) * math.cos(d2) * math.cos(r1 - r2)
    return math.degrees(math.acos(max(-1.0, min(1.0, cos_sep))))


@dataclass
class NightPlan:
    """One night's curves (noon of `night_of` to noon the next day) plus
    the derived slots - everything the program editor's chart needs."""
    times: list[datetime] = field(default_factory=list)
    target_alt: list[float] = field(default_factory=list)
    target_az: list[float] = field(default_factory=list)  # 0=N, 90=E, 180=S, 270=W
    sun_alt: list[float] = field(default_factory=list)
    moon_alt: list[float] = field(default_factory=list)
    dark_start: datetime | None = None
    dark_end: datetime | None = None
    transit_time: datetime | None = None
    max_altitude: float | None = None
    # Contiguous windows where the target is >= min_altitude AND the Sun
    # is below the chosen darkness level, longest first.
    slots: list[tuple[datetime, datetime]] = field(default_factory=list)
    moon_illumination: float = 0.0  # 0..1 at local midnight
    moon_separation: float | None = None  # deg, at local midnight

    @property
    def best_slot(self) -> tuple[datetime, datetime] | None:
        return self.slots[0] if self.slots else None


def to_utc(local_naive: datetime, tz: tzinfo | None = None) -> datetime:
    """Naive wall-clock time in `tz` (None = this PC's local time) -> UTC."""
    if tz is not None:
        local_naive = local_naive.replace(tzinfo=tz)
    return local_naive.astimezone(timezone.utc)


def compute_night_plan(
    ra_hours: float,
    dec_deg: float,
    latitude: float,
    longitude: float,
    night_of: datetime,
    *,
    min_altitude: float = 30.0,
    darkness: str = "astronomical",
    step_minutes: int = 5,
    tz: tzinfo | None = None,
) -> NightPlan:
    """night_of: any naive local datetime on the evening's DATE - the
    curve runs from 12:00 that day to 12:00 the next, so a night that
    crosses midnight stays on one chart. tz: the timezone night_of and
    every returned time are wall-clock times in (None = this PC's)."""
    sun_limit = DARKNESS_LEVELS.get(darkness, DARKNESS_LEVELS["astronomical"])
    ra_deg = (float(ra_hours) * 15.0) % 360.0
    dec_deg = float(dec_deg)
    start = night_of.replace(hour=12, minute=0, second=0, microsecond=0)

    plan = NightPlan()
    n_steps = (24 * 60) // step_minutes
    for i in range(n_steps + 1):
        local = start + timedelta(minutes=i * step_minutes)
        jd = _julian_date(to_utc(local, tz))
        lst = _local_sidereal_deg(jd, longitude)
        sra, sdec, _ = sun_radec(jd)
        mra, mdec, _ = moon_radec(jd)
        plan.times.append(local)
        plan.target_alt.append(_altitude_deg(ra_deg, dec_deg, lst, latitude))
        plan.target_az.append(_azimuth_deg(ra_deg, dec_deg, lst, latitude))
        plan.sun_alt.append(_altitude_deg(sra, sdec, lst, latitude))
        plan.moon_alt.append(_altitude_deg(mra, mdec, lst, latitude))

    # Darkness window (the first contiguous dark stretch of the night).
    dark = [s <= sun_limit for s in plan.sun_alt]
    if any(dark):
        first = dark.index(True)
        last = first
        while last + 1 < len(dark) and dark[last + 1]:
            last += 1
        plan.dark_start, plan.dark_end = plan.times[first], plan.times[last]

    # Highest point during the dark window (or the whole span if never dark).
    idx_range = range(len(plan.times))
    if plan.dark_start is not None:
        idx_range = [i for i in idx_range if dark[i]]
    best_i = max(idx_range, key=lambda i: plan.target_alt[i])
    plan.max_altitude = plan.target_alt[best_i]
    plan.transit_time = plan.times[best_i]

    # Usable slots: dark AND high enough.
    current: list[int] = []
    slots: list[tuple[datetime, datetime]] = []
    for i, ok in enumerate(d and a >= min_altitude for d, a in zip(dark, plan.target_alt)):
        if ok:
            current.append(i)
        elif current:
            slots.append((plan.times[current[0]], plan.times[current[-1]]))
            current = []
    if current:
        slots.append((plan.times[current[0]], plan.times[current[-1]]))
    plan.slots = sorted(slots, key=lambda s: s[1] - s[0], reverse=True)

    # Moon phase / distance to the target at local midnight.
    jd_mid = _julian_date(to_utc(start + timedelta(hours=12), tz))
    _, _, sun_lon = sun_radec(jd_mid)
    mra, mdec, moon_lon = moon_radec(jd_mid)
    elongation = (moon_lon - sun_lon) * _DEG
    plan.moon_illumination = (1 - math.cos(elongation)) / 2
    plan.moon_separation = angular_separation_deg(ra_deg, dec_deg, mra, mdec)
    return plan
