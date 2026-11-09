"""Site time - the wall clock of an observation location (user-requested
Nov 2026: Dwarfium Scope Archive runs on the PC at home, the Dwarf may be
anywhere - a remote site's DATE-OBS and nights are not in this PC's time).

The DWARF's FITS files carry no timezone and no site: DATE-OBS is a naive
local time. The zone comes from the location the session is linked to
(ObservationLocation.timezone, an IANA name such as "Pacific/Auckland" -
the same field as Astro Dwarf Session's sites). An empty or unknown zone
means "this PC's", i.e. the behaviour before the field existed.

zoneinfo needs the `tzdata` package on Windows (requirements.txt)."""
from __future__ import annotations

import logging
import zoneinfo
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from typing import Optional

_warned: set[str] = set()
_finder = None


def zone_for(name) -> Optional[tzinfo]:
    """ZoneInfo of an IANA name, None when it is empty or unknown (callers
    then use this PC's time). ZoneInfo("") raises ValueError, not
    ZoneInfoNotFoundError - both are caught, a bad value never breaks a page."""
    name = (name or "").strip() if isinstance(name, str) else ""
    if not name:
        return None
    try:
        return zoneinfo.ZoneInfo(name)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError, OSError) as e:
        if name not in _warned:
            _warned.add(name)
            logging.getLogger(__name__).warning(
                f"Unknown timezone {name!r} ({e}) - using this PC's local timezone.")
        return None


def available_zone_names() -> list[str]:
    """Every IANA zone name the system knows (the `tzdata` package on
    Windows), sorted - [] when there is none, the UI then takes free text."""
    try:
        return sorted(zoneinfo.available_timezones())
    except Exception:
        return []


def is_valid_timezone(name) -> bool:
    return zone_for(name) is not None


def guess_timezone(latitude, longitude) -> str:
    """IANA name of the zone containing these coordinates, '' when it can't
    be told. Offline, with the optional `timezonefinder` package (not
    installed: '' - the user types the zone)."""
    global _finder
    if latitude is None or longitude is None:
        return ""
    try:
        from timezonefinder import TimezoneFinder
    except ImportError:
        return ""
    try:
        if _finder is None:
            _finder = TimezoneFinder()
        name = _finder.timezone_at(lat=float(latitude), lng=float(longitude))
    except Exception:
        return ""
    return name if name and zone_for(name) is not None else ""


def location_zone(location) -> Optional[tzinfo]:
    """Zone of a location dict (its "timezone" or "tz" key), None = this PC's."""
    if not location:
        return None
    return zone_for(location.get("timezone") or location.get("tz") or "")


def utc_offset_hours(date_obs, name) -> Optional[float]:
    """UTC offset in hours, daylight saving time included, of the zone `name`
    at the naive wall-clock time date_obs (an ISO string, as in the FITS
    DATE-OBS). None when the zone is unknown or the date unreadable - the
    caller then falls back to this PC's offset."""
    zone = zone_for(name)
    if zone is None:
        return None
    try:
        local = datetime.fromisoformat(str(date_obs).strip().replace("Z", ""))
    except ValueError:
        return None
    return local.replace(tzinfo=zone).utcoffset().total_seconds() / 3600.0


def local_noon_window_utc(night: date, zone: Optional[tzinfo]) -> tuple[datetime, datetime]:
    """(start, end) of the night of `night` as tz-aware UTC datetimes: from
    12:00 that day to 12:00 the next day, in `zone` (None = this PC's). A
    night anywhere on Earth then sits whole inside the window."""
    def noon(day: date) -> datetime:
        naive = datetime.combine(day, time(12))
        local = naive.replace(tzinfo=zone) if zone is not None else naive.astimezone()
        return local.astimezone(timezone.utc)
    return noon(night), noon(night + timedelta(days=1))
