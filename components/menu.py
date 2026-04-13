# components/menu.py
from nicegui import ui, app

from components.help_system import register_drawer, open_help

def setStyle(color_primary = '#00ae83'):

    ui.colors(
        primary=color_primary
    )

def menu(title):

    dark = ui.dark_mode()
    if app.storage.user.get('ui_mode',0) == 'dark' :
        dark.enable()
        ui.query('body').style(f'background-color: {'#262608'}')
    else:
        dark.disable()
        ui.query('body').style(f'background-color: {'#f5f5e6'}')

    register_drawer()

    with ui.row().classes('w-full items-center'):
        ui.label(title).classes("text-2xl font-bold my-2 mr-auto")

        #ui.button('Dwarf Connect').classes('text-sm')

        with ui.button(icon='menu').classes('text-sm ml-auto'):
            with ui.menu():
                ui.menu_item('Home', on_click=lambda: ui.navigate.to('/'))
                ui.menu_item('Dwarfs Settings', on_click=lambda: ui.navigate.to('/Dwarf'))
                ui.menu_item('Backup Setting', on_click=lambda: ui.navigate.to('/Backup'))
                ui.menu_item('Explore', on_click=lambda: ui.navigate.to('/Explore'))
                ui.menu_item('Transfer', on_click=lambda: ui.navigate.to('/Transfer'))
#                ui.menu_item('USB Transfer', on_click=lambda: ui.navigate.to('/TransferUSB'))
                ui.menu_item('Mosaics', on_click=lambda: ui.navigate.to('/Mosaic'))
                ui.menu_item('Add Session', on_click=lambda: ui.navigate.to('/AddManualSession'))
                ui.menu_item('Show Session', on_click=lambda: ui.navigate.to('/ManualExplore'))
                ui.menu_item('MtpDevice', on_click=lambda: ui.navigate.to('/MtpDevice'))
                ui.menu_item('Catalog', on_click=lambda: ui.navigate.to('/Catalog'))
                ui.menu_item('Settings', on_click=lambda: ui.navigate.to('/Settings'))
                ui.menu_item('Dark Mode', on_click=lambda: dark_mode())
                ui.menu_item('Light Mode', on_click=lambda: light_mode())
                ui.menu_item('Help', on_click=open_help)
    setStyle()

def dark_mode():
    dark = ui.dark_mode()
    dark.enable()
    app.storage.user['ui_mode'] = 'dark'
    ui.navigate.reload()

def light_mode():
    dark = ui.dark_mode()
    dark.disable()
    app.storage.user['ui_mode'] = 'light'
    ui.navigate.reload()
