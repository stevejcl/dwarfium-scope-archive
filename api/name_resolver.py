"""SIMBAD with its mirror, VSX as a last resort (user-reported Oct 2026: the
CDS at Strasbourg down two days - "RT And not found on SIMBAD", VizieR's
findcompstars failing too).

SIMBAD answers from Strasbourg (simbad.cds.unistra.fr) and from Harvard
(simbad.harvard.edu): each query goes to the first one answering. A name
neither knows (or both down) is asked to the AAVSO's VSX - variable stars,
hosted in the US."""
from __future__ import annotations

SIMBAD_MIRRORS = ("simbad.cds.unistra.fr", "simbad.harvard.edu")
_VSX_URL = "https://www.aavso.org/vsx/index.php"


def simbad_clients(**settings):
    """A Simbad client per mirror, configured with `settings` (attributes:
    TIMEOUT, ROW_LIMIT...)."""
    from astroquery.simbad import Simbad
    for server in SIMBAD_MIRRORS:
        client = Simbad()
        try:
            client.server = server
        except Exception:       # an astroquery without mirrors: the default one only
            if server != SIMBAD_MIRRORS[0]:
                continue
        for key, value in settings.items():
            setattr(client, key, value)
        yield server, client


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
