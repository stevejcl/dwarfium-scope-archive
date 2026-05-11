"""
pages/dwarf_sky_map.py — Sky Map page.
"""
import asyncio
from nicegui import ui

from components.sky_map_wcs import show_sky_map_wcs
from components.menu import menu
from components.i18n import t


@ui.page('/SkyMap')
async def page_sky_map():
    menu(t('sky_map_menu'))

    with ui.column().classes('w-full p-4 gap-4'):
        ui.separator()
        with ui.card().classes('w-full p-4'):
            show_sky_map_wcs()

        await ui.context.client.connected()