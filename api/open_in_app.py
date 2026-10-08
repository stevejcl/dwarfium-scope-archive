"""Open a page of this app in its own window, from another app (user-
requested Oct 2026: Astro Dwarf Session's "Archive" link opened
/ImportSession in a web browser, where the Transfer page's system folder
dialogs aren't available).

GET /api/open-in-app?path=/ImportSession?DwarfId=8&session=...
  -> {"opened": true}  the app's window loads that page and comes to front
  -> {"opened": false} no app window (browser / server mode): the caller
                       opens the page in a browser instead

Only this app's own pages: path must be a local path ("/..."), never
another site.

The page is opened like a click in the app (user-reported Oct 2026:
reloading the whole window with load_url() froze the interface): the
NiceGUI page shown in the app's window - known from window.pywebview,
which only pywebview's window has - navigates with ui.navigate.to(), and
nothing else (show / always-on-top on top of it blocked the app). The
window is only reloaded and brought to front when no page of it is
connected yet."""
from __future__ import annotations

import asyncio
import time
from urllib.parse import quote, urlencode, urlsplit

from fastapi.responses import JSONResponse
from nicegui import Client, app, background_tasks, run, ui

from api.window_front import bring_to_front


SAFE_URL_CHARS = "/?&=%+:;,'()!*~-._@$"


def local_path(path: str) -> bool:
    parts = urlsplit(path or "")
    return bool(path) and path.startswith("/") and not path.startswith("//") and not parts.scheme and not parts.netloc


# Ids of the connected pages shown in the app's window (not in a browser)
_window_client_ids: list[str] = []
# When each of them connected (time.monotonic())
_connected_at: dict[str, float] = {}

# A page of the window connected less than this ago is left to finish
# loading before it is navigated, and a request arriving before the
# window's page has reported itself waits for it (user-reported Oct 2026:
# once, on the first start of the day, the window froze; never when the
# app had been open a while)
_SETTLE_S = 3.0
_MAX_WAIT_S = 3.5

# Per page (client id): what to stop before this route navigates it away
_before_leave: dict[str, list] = {}


def on_before_open(client: Client, callback) -> None:
    """Called by a page with background work (the home page's slideshow
    timers and favorites loading): `callback` runs right before this
    route navigates that page to another one (user-requested Oct 2026:
    the home page's timers kept running then and blocked the app)."""
    _before_leave.setdefault(client.id, []).append(callback)

# not used not working
def _run_before_leave(client: Client) -> None:
    for callback in _before_leave.pop(client.id, []):
        try:
            callback()
        except Exception as e:
            print(f"[open-in-app] before-open callback error: {e}")


async def _note_window_client(client: Client) -> None:
    connected_at = time.monotonic()
    try:
        in_window = bool(await client.run_javascript("!!window.pywebview", timeout=3.0))
    except Exception:
        return
    if in_window and client.id not in _window_client_ids:
        _window_client_ids.append(client.id)
        _connected_at[client.id] = connected_at


def _forget_client(client: Client) -> None:
    _before_leave.pop(client.id, None)
    _connected_at.pop(client.id, None)
    if client.id in _window_client_ids:
        _window_client_ids.remove(client.id)


def _window_client() -> Client | None:
    """The most recently connected page of the app's window, still alive."""
    for client_id in reversed(_window_client_ids):
        client = Client.instances.get(client_id)
        if client is not None and client.has_socket_connection:
            return client
    return None


async def _settled_window_client() -> Client | None:
    """The window's page to navigate, once it has settled (see _SETTLE_S),
    waiting for it when the app has just started: until its page has
    reported being in the window, there is none, and the reload fallback
    below (load_url / show / always-on-top) is what blocked the app. Waits
    at most _MAX_WAIT_S, under Astro Dwarf Session's 5 s request timeout."""
    deadline = time.monotonic() + _MAX_WAIT_S
    client = _window_client()
    while client is None and time.monotonic() < deadline:
        await asyncio.sleep(0.2)
        client = _window_client()
    if client is None:
        return None
    age = time.monotonic() - _connected_at.get(client.id, 0.0)
    wait = min(_SETTLE_S - age, deadline - time.monotonic())
    if wait > 0:
        await asyncio.sleep(wait)
        if not client.has_socket_connection:
            client = _window_client()
    return client


def register(port: int) -> None:
    app.on_connect(lambda client: background_tasks.create(_note_window_client(client)))
    app.on_disconnect(_forget_client)

    @app.get("/api/open-in-app")
    async def open_in_app(path: str = ""):
        if not local_path(path):
            return JSONResponse({"opened": False, "error": "path"}, status_code=400)
        window = getattr(app.native, "main_window", None)
        if window is None:
            return JSONResponse({"opened": False})
        # Spaces and the like encoded, what's already encoded kept
        target = quote(path, safe=SAFE_URL_CHARS)
        try:
            client = await _settled_window_client()
            if client is not None:
                # Through the /Init relay page (pages/init.py): straight to
                # the target froze the interface (user-found Oct 2026).
                # Target encoded whole, its own ? and & included
                with client:
                    ui.navigate.to("/Init?" + urlencode({"Target": target}))
                # Front through Win32 in a thread (window_front.py), not
                # pywebview's own calls, which blocked the app
                try:
                    await run.io_bound(bring_to_front)
                except Exception:
                    pass
            else:
                window.load_url(f"http://127.0.0.1:{port}{target}")
                window.show()
                # Brought to front: on top for a moment (Windows won't let a
                # background app simply take the focus)
                window.set_always_on_top(True)
                await asyncio.sleep(0.5)
                window.set_always_on_top(False)
        except Exception as e:  # window closing, pywebview error: browser fallback
            return JSONResponse({"opened": False, "error": str(e)})
        return JSONResponse({"opened": True})
