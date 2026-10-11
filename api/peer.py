"""Presence of Astro Dwarf Session (user-requested Oct 2026).

Astro Dwarf Session knows this app's address (its Settings page) and says
hello every 30 s:

POST /api/peer/hello  {"app": "astro_dwarf_session", "version": "3.2.3", "port": 8080}
  -> {"app": "dwarfium_scope_archive", "version": "V3.4.2"}

so this app learns its address - the request's IP and the port it gives -
and whether it is running (heard from in the last 75 s: two missed hellos
allowed). Pages read peer_url() to offer actions done in Astro Dwarf
Session. Kept in memory only, nothing else is done here (no UI, no
database): the request is answered at once.
"""
from __future__ import annotations

import ipaddress
import time

from fastapi import Request
from fastapi.responses import JSONResponse
from nicegui import app

PEER_TIMEOUT_S = 75

# Last hello from Astro Dwarf Session: url, version, seen (time.monotonic())
_peer: dict = {}


def _url(host: str, port: int) -> str:
    try:
        if ipaddress.ip_address(host).version == 6:
            host = f"[{host}]"
    except ValueError:
        pass
    return f"http://{host}:{port}"


def peer_url() -> str | None:
    """Astro Dwarf Session's address when it is running, else None."""
    if _peer and time.monotonic() - _peer["seen"] <= PEER_TIMEOUT_S:
        return _peer["url"]
    return None


def peer_version() -> str:
    return _peer.get("version", "") if peer_url() else ""


def register() -> None:
    @app.post("/api/peer/hello")
    async def peer_hello(request: Request):
        try:
            body = await request.json()
            port = int(body.get("port"))
        except (ValueError, TypeError, AttributeError):
            return JSONResponse({"error": "port is required"}, status_code=400)
        if body.get("app") != "astro_dwarf_session" or not 0 < port < 65536 or not request.client:
            return JSONResponse({"error": "unknown peer"}, status_code=400)
        url = _url(request.client.host, port)
        if _peer.get("url") != url or not peer_url():
            print(f"[peer] Astro Dwarf Session {body.get('version', '')} at {url}")
        _peer.update(url=url, version=str(body.get("version", ""))[:20], seen=time.monotonic())
        from pages.astro_settings import _get_app_version
        return {"app": "dwarfium_scope_archive", "version": _get_app_version()}

    @app.get("/api/peer/status")
    def peer_status():
        return {"astroDwarfSession": {"url": peer_url(), "version": peer_version()}}
