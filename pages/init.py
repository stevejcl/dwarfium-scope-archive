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
from components.i18n import t


@ui.page('/Init')
async def init_page(Target: str = None):
    menu(t("loading"))
    await ui.context.client.connected(timeout=10.0)

    InitApp(Target)


class InitApp():
    def __init__(self, Target=None):
        self.target = Target
        self.build_ui()

    def build_ui(self):

        ui.navigate.to(self.target if self.target and local_path(self.target) else "/")
