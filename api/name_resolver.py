"""SIMBAD with its mirror, VSX as a last resort (user-reported Oct 2026: the
CDS at Strasbourg down two days - "RT And not found on SIMBAD", VizieR's
findcompstars failing too).

SIMBAD answers from Strasbourg (simbad.cds.unistra.fr) and from Harvard
(simbad.harvard.edu): each query goes to the first one answering. A name
neither knows (or both down) is asked to the AAVSO's VSX - variable stars,
hosted in the US."""
from __future__ import annotations
SIMBAD_MIRRORS = ("simbad.cds.unistra.fr", "simbad.harvard.edu", "simbad.cfa.harvard.edu")
_VSX_URL = "https://www.aavso.org/vsx/index.php"


# Mirrors found down, kept in mind for a while: the next queries try the
# others first instead of waiting again for the dead one's time-out
_simbad_down: dict[str, float] = {}
_SIMBAD_DOWN_S = 900
_QUERY_METHODS = ("query_object", "query_objects", "query_region", "query_criteria", "query_tap")
_CONNECTION_WORDS = ("connection", "timed out", "timeout", "capabilities endpoint", "name or service",
                     "unreachable", "temporarily unavailable", "502", "503", "504")


def _is_connection_error(error: Exception) -> bool:
    import requests
    return isinstance(error, (requests.RequestException, OSError)) or \
        any(word in str(error).lower() for word in _CONNECTION_WORDS)


def _tracked(client, server):
    """The client's query methods tell _simbad_down how the mirror answers:
    a connection failure sets it down for a few minutes, an answer clears it."""
    import time

    def wrap(method):
        def call(*args, **kwargs):
            try:
                result = method(*args, **kwargs)
            except Exception as e:
                if _is_connection_error(e):
                    _simbad_down[server] = time.time() + _SIMBAD_DOWN_S
                raise
            _simbad_down.pop(server, None)
            return result
        return call

    for name in _QUERY_METHODS:
        if hasattr(client, name):
            setattr(client, name, wrap(getattr(client, name)))
    return client


def simbad_clients(**settings):
    """A Simbad client per mirror, configured with `settings` (attributes:
    TIMEOUT, ROW_LIMIT...). The mirrors that failed to connect in the last
    few minutes come last (never left out: all may be back)."""
    import time
    from astroquery.simbad import Simbad
    now = time.time()
    order = sorted(SIMBAD_MIRRORS, key=lambda server: _simbad_down.get(server, 0) > now)  # stable
    for server in order:
        client = Simbad()
        try:
            client.server = server
        except Exception:       # an astroquery without mirrors: the default one only
            if server != SIMBAD_MIRRORS[0]:
                continue
        for key, value in settings.items():
            setattr(client, key, value)
        yield server, _tracked(client, server)


def vsx_position(name: str, timeout: float = 15) -> dict | None:
    """{"label", "ra_deg", "dec_deg"} of a variable star from VSX, None when
    unknown or unreachable."""
    import requests
    try:
        response = requests.get(_VSX_URL, params={"view": "api.object", "format": "json", "ident": name},
                                headers={"User-Agent": "Dwarfium Scope Archive"}, timeout=timeout)
        response.raise_for_status()
        obj = (response.json() or {}).get("VSXObject") or {}
        return {"label": obj.get("Name") or name, "ra_deg": float(obj["RA2000"]),
                "dec_deg": float(obj["Declination2000"])}
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError):
        return None


ALADIN_SERVERS = (
    "https://aladin.cds.unistra.fr/AladinLite/",
    "https://virtualadin.cds.unistra.fr/AladinLite/",
    "https://novlba.cds.unistra.fr/AladinLite/",
)

ESA_SKY = "https://sky.esa.int/esasky/"

# (server, valid until): a working server is kept an hour, the ESASky fallback
# only 15 minutes - the CDS may be back, and a server that goes down is dropped
_aladin_server_cache = None
_ALADIN_OK_S, _ALADIN_FALLBACK_S = 3600, 900


def get_aladin_server(timeout=2):
    """Return the first available Aladin Lite server (blocking, up to
    timeout seconds per server - call it from run.io_bound in a page)."""
    global _aladin_server_cache
    import time
    import requests

    now = time.time()
    if _aladin_server_cache and _aladin_server_cache[1] > now:
        return _aladin_server_cache[0]

    for server in ALADIN_SERVERS:
        try:
            response = requests.get(server, timeout=timeout, allow_redirects=True)
            if response.status_code == 200:
                _aladin_server_cache = (server, now + _ALADIN_OK_S)
                return server
        except requests.RequestException:
            continue

    _aladin_server_cache = (ESA_SKY, now + _ALADIN_FALLBACK_S)
    return ESA_SKY

_last_logged_server = None

def get_aladin_url(ra, dec, fov=3):
    """Build a sky map URL using an available server."""
    global _last_logged_server
    from urllib.parse import urlencode

    server = get_aladin_server()
    if server != _last_logged_server:
        print(f"Aladin Server : {server}")
        _last_logged_server = server

    if server == ESA_SKY:
        params = {
            "target": f"{ra:.5f} {dec:+.5f}",
            "fov": fov,
            "hips": "DSS2 color",
        }
    else:
        params = {
            "target": f"{ra:.5f} {dec:+.5f}",
            "fov": fov,
            "survey": "P/DSS2/color",
        }

    return f"{server}?{urlencode(params)}"

