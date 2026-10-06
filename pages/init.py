"""Relay page for /api/open-in-app (user-found Oct 2026): navigating the
app's window straight to the requested page froze the interface (seen
from the home page, then on every page); going through this small page
first, which then navigates to the target itself, doesn't.

/Init?Target=<url-encoded local path, query included>
Only this app's own pages: anything else goes to the home page."""
from __future__ import annotations

from nicegui import ui

from api.open_in_app import local_path
from components.menu import menu


@ui.page('/Init')
async def init_page(Target: str = None):
    menu("Init")
    await ui.context.client.connected(timeout=10.0)
    ui.spinner(size="lg").classes("mx-auto mt-8")
    ui.navigate.to(Target if Target and local_path(Target) else "/")
