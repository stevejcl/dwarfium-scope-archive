"""
components/aladin_view.py - "Open in Aladin": the real sky around one target,
in the self-hosted Aladin Lite (the same build as the Sky Map, served at
/aladin), no session overlay. Replaces the external Aladin / ESASky link, which
depended on the CDS servers (down Oct-Nov 2026).

    open_aladin_view(ra_deg, dec_deg, fov=3, name="")   # from a click handler

The page is /aladin_view?ra=..&dec=..&fov=..&name=.., registered on the first
call. If the Aladin Lite files are missing on the server, the browser is sent to
the first sky server that answers (api/name_resolver.get_aladin_url: the CDS's
own Aladin Lite, else ESASky), else a page says so; if Aladin Lite fails to start in the
browser, the page says so too (its ESASky link stays in the bar - ESASky can be
down as well, so there is no automatic redirect). The tab is reused
(components/sky_link.py).
"""
import json
from urllib.parse import urlencode

from fastapi import Response, Query
from fastapi.responses import RedirectResponse
from nicegui import app

from components.sky_link import open_in_sky_tab, ALADIN_TAB, aladin_dir

VIEW_URL = "/aladin_view"


def _answers(url: str, timeout: float = 3) -> bool:
    """Blocking: does the server answer (not an error such as 503)?"""
    import requests
    try:
        r = requests.get(url, timeout=timeout, stream=True)
        r.close()
        return r.status_code < 400
    except Exception:
        return False


def _unavailable_html(ra: float, dec: float) -> str:
    return ("<!DOCTYPE html><meta charset='utf-8'><title>Dwarfium - Aladin</title>"
            "<body style='font-family:sans-serif;background:#111;color:#ddd;padding:2em'>"
            "<h3>Sky viewer unavailable</h3>"
            "<p>The Aladin Lite files (assets/aladin) are missing and the external sky servers "
            "(CDS, ESASky) do not answer.</p>"
            f"<p>Target: RA {ra:.5f}, Dec {dec:+.5f}</p></body>")


def _build_html() -> str:
    # Imported here: sky_map_wcs is heavy and imports sky_link as well
    from components.sky_map_wcs import ALADIN_LOCAL_JS, ALADIN_LOCAL_CSS, HIPS_DSS_COLOR

    js = f"""
var P = new URLSearchParams(location.search);
var RA = parseFloat(P.get("ra")), DEC = parseFloat(P.get("dec"));
var FOV = parseFloat(P.get("fov") || "3"), NAME = P.get("name") || "";
var HIPS = {json.dumps(list(HIPS_DSS_COLOR))};
function esaSky() {{
  var t = RA.toFixed(5) + " " + (DEC >= 0 ? "+" : "") + DEC.toFixed(5);
  return "https://sky.esa.int/esasky/?target=" + encodeURIComponent(t) +
         "&fov=" + FOV + "&hips=" + encodeURIComponent("DSS2 color");
}}
function _probe(u) {{
  var c = new AbortController(), t = setTimeout(function() {{ c.abort(); }}, 4000);
  return fetch(u.replace(/\\/$/, "") + "/properties", {{signal: c.signal}})
    .then(function(r) {{ clearTimeout(t); return r.ok ? u : null; }})
    .catch(function() {{ clearTimeout(t); return null; }});
}}
// the first of the list that answers, without waiting for the dead ones
function _pickSurvey() {{
  return new Promise(function(resolve) {{
    var res = new Array(HIPS.length);
    function check() {{
      for (var i = 0; i < HIPS.length; i++) {{
        if (res[i] === undefined) return;
        if (res[i]) return resolve(res[i]);
      }}
      resolve(HIPS[0]);
    }}
    HIPS.forEach(function(u, i) {{ _probe(u).then(function(r) {{ res[i] = r || false; check(); }}); }});
  }});
}}
var info = document.getElementById("info");
info.textContent = (NAME ? NAME + " - " : "") + "RA " + RA.toFixed(4) + "  Dec " + DEC.toFixed(4);
document.getElementById("esa").href = esaSky();
if (isNaN(RA) || isNaN(DEC)) {{
  info.textContent = "ra / dec missing";
}} else {{
  import({json.dumps(ALADIN_LOCAL_JS)}).then(function(m) {{
    window.A = m.default;
    return A.init;
  }}).then(_pickSurvey).then(function(SURVEY) {{
    var al = A.aladin("#aladin-lite-div", {{
      survey: SURVEY, fov: FOV, target: RA + " " + DEC,
      showReticle: true, showZoomControl: true,
      showFullscreenControl: true, showLayersControl: true,
      backgroundColor: "#111111"
    }});
    al.gotoRaDec(RA, DEC);
  }}).catch(function(e) {{
    // Aladin Lite failed to start (WebGL2? WebAssembly?): said here, the
    // ESASky link stays in the bar - no redirect, ESASky may be down too
    info.textContent = "Aladin Lite could not start: " + (e && e.message ? e.message : e);
  }});
}}
"""
    return (
        '<!DOCTYPE html>\n<html>\n<head>\n<meta charset="utf-8"/>\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1"/>\n'
        '<title>Dwarfium - Aladin</title>\n'
        f'<link rel="stylesheet" href="{ALADIN_LOCAL_CSS}"/>\n'
        '<style>html,body{margin:0;height:100%;background:#111;color:#ddd;font-family:sans-serif}'
        '#bar{position:absolute;top:8px;left:50px;z-index:1000;background:rgba(20,20,40,.85);'
        'padding:4px 10px;border-radius:6px;font-size:13px;display:flex;gap:12px;align-items:center}'
        '#bar a{color:#8cf;text-decoration:none}</style>\n'
        '</head>\n<body>\n'
        '<div id="bar"><span id="info">Loading...</span>'
        '<a id="esa" target="_blank" rel="noopener">ESASky &#8599;</a></div>\n'
        '<div id="aladin-lite-div" style="width:100vw;height:100vh;"></div>\n'
        f'<script>{js}</script>\n</body>\n</html>\n'
    )


def ensure_aladin_view_route() -> None:
    """Registers /aladin_view (once) and the /aladin static files (unless the
    app already serves them)."""
    from components.sky_map_wcs import _ensure_aladin_static
    _ensure_aladin_static()
    if any(getattr(r, "path", "") == VIEW_URL for r in app.routes):
        return
    html = _build_html()

    @app.get(VIEW_URL, include_in_schema=False)
    async def aladin_view(ra: float = Query(None), dec: float = Query(None), fov: float = Query(3)):
        if aladin_dir() is None and ra is not None and dec is not None:
            # Aladin Lite not installed here: the CDS's, else ESASky - the one
            # chosen is checked, get_aladin_url falls back to ESASky unchecked
            import asyncio
            from api.name_resolver import get_aladin_url
            url = await asyncio.to_thread(get_aladin_url, ra, dec, fov)
            if await asyncio.to_thread(_answers, url):
                return RedirectResponse(url)
            return Response(content=_unavailable_html(ra, dec), media_type="text/html",
                            status_code=503)
        return Response(content=html, media_type="text/html",
                        headers={"Cache-Control": "no-store"})


def open_aladin_view(ra_deg: float, dec_deg: float, fov: float = 3, name: str = "") -> None:
    """Opens the target in the (reused) Aladin tab. Call it from a click handler."""
    ensure_aladin_view_route()
    params = {"ra": f"{float(ra_deg):.5f}", "dec": f"{float(dec_deg):+.5f}", "fov": fov}
    if name:
        params["name"] = name
    open_in_sky_tab(f"{VIEW_URL}?{urlencode(params)}", ALADIN_TAB)
