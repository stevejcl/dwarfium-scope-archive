"""Open a page of this app in its own window, from another app (user-
requested Oct 2026: Astro Dwarf Session's "Archive" link opened
/ImportSession in a web browser, where the Transfer page's system folder
dialogs aren't available).

GET /api/open-in-app?path=/ImportSession?DwarfId=8&session=...
  -> {"opened": true}  the app's window loads that page and comes to front
  -> {"opened": false} no app window (browser / server mode): the caller
                       opens the page in a browser instead

Only this app's own pages: path must be a local path ("/..."), never
another site."""
from __future__ import annotations

import asyncio
from urllib.parse import quote, urlsplit

from fastapi.responses import JSONResponse
from nicegui import app


SAFE_URL_CHARS = "/?&=%+:;,'()!*~-._@$"


def _local_path(path: str) -> bool:
    parts = urlsplit(path or "")
    return bool(path) and path.startswith("/") and not path.startswith("//") and not parts.scheme and not parts.netloc


def register(port: int) -> None:
    @app.get("/api/open-in-app")
    async def open_in_app(path: str = ""):
        if not _local_path(path):
            return JSONResponse({"opened": False, "error": "path"}, status_code=400)
        window = getattr(app.native, "main_window", None)
        if window is None:
            return JSONResponse({"opened": False})
        try:
            # Spaces and the like encoded, what's already encoded kept
            window.load_url(f"http://127.0.0.1:{port}{quote(path, safe=SAFE_URL_CHARS)}")
            window.restore()
            window.show()
            # Brought to front: on top for a moment (Windows won't let a
            # background app simply take the focus)
            window.set_always_on_top(True)
            await asyncio.sleep(0.5)
            window.set_always_on_top(False)
        except Exception as e:  # window closing, pywebview error: browser fallback
            return JSONResponse({"opened": False, "error": str(e)})
        return JSONResponse({"opened": True})
