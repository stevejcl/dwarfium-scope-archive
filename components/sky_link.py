"""Opens a sky map link (Aladin, ESASky, the Sky Map page) in a browser tab
that is reused instead of adding a new one each time (user-requested Nov 2026).

Two mechanisms, because a named window alone was not enough:
  1. the window handle returned by the first window.open() is kept in the page
     (window.__dwarfiumTabs) and navigated on the next click;
  2. if that handle is gone (page reloaded, tab closed), window.open with the
     same tab name is tried, which reuses an existing tab of that name.
A console line says which path was taken (F12 > Console)."""
import json

from nicegui import ui

ALADIN_TAB = "dwarfium_aladin"      # Aladin / ESASky links
SKYMAP_TAB = "dwarfium_skymap"      # the app's own Sky Map page


def open_in_sky_tab(url: str, tab: str = ALADIN_TAB) -> None:
    """Call it from a click handler (it runs JavaScript in the page). The tab
    is brought to the front when the browser allows it."""
    js = f"""
(function() {{
  var url = {json.dumps(url)}, name = {json.dumps(tab)};
  window.__dwarfiumTabs = window.__dwarfiumTabs || {{}};
  var w = window.__dwarfiumTabs[name];
  var alive = false;
  try {{ alive = !!w && !w.closed; }} catch (e) {{ alive = false; }}
  if (alive) {{
    try {{
      w.location.href = url;
      w.focus();
      console.log('[sky tab] reused handle', name);
      return;
    }} catch (e) {{
      console.log('[sky tab] handle unusable, reopening', name, e);
    }}
  }}
  w = window.open(url, name);
  if (w) {{
    window.__dwarfiumTabs[name] = w;
    try {{ w.focus(); }} catch (e) {{}}
    console.log('[sky tab] window.open', name);
  }} else {{
    console.log('[sky tab] window.open blocked (popup blocker?)', name);
  }}
}})();
"""
    ui.run_javascript(js)