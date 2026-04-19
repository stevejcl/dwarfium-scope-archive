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

    ui.button('↑ Top', on_click=lambda: ui.run_javascript('window.scrollTo({top: 0, behavior: "smooth"})')) \
        .props('round color=primary') \
        .classes('fixed bottom-4 right-4 z-[9999] shadow-lg')

    register_drawer()

    with ui.row().classes('w-full items-center'):
        ui.label(title).classes("text-2xl font-bold my-2 mr-auto")

        # Transfer progress badge — shown on any page when a transfer is running
        badge = ui.label("").classes(
            "text-sm font-semibold px-2 py-1 rounded bg-green-100 text-green-800 cursor-pointer"
        ).on('click', lambda: ui.navigate.to('/Transfer'))
        badge.visible = False

        def _check_transfer():
            try:
                # Scan general storage for any transfer keyed by this client
                client_id = ui.context.client.id
                key = f'transfer_progress_{client_id}'
                p = app.storage.general.get(key, None)
                if p and p['status'] == 'running':
                    total  = p.get('total', 0)
                    copied = p.get('copied', 0)
                    badge.text = f"📦 {copied}/{total}"
                    badge.visible = True
                elif p and p['status'] == 'scanning':
                    badge.text = p.get('current_file', '🔍 Scanning...')
                    badge.visible = True
                elif p and p['status'] == 'done':
                    badge.text = "✅ Transfer done"
                    badge.visible = True
                elif p and p['status'] == 'error':
                    badge.text = "❌ Transfer error"
                    badge.visible = True
                else:
                    badge.visible = False
            except Exception:
                _badge_timer.cancel()

        _badge_timer = ui.timer(2.0, _check_transfer)
        ui.context.client.on_disconnect(lambda: _badge_timer.cancel())

        #ui.button('Dwarf Connect').classes('text-sm')

        with ui.button(icon='menu').classes('text-sm ml-auto'):
            with ui.menu().classes('max-h-none'):
                ui.menu_item('Home', on_click=lambda: ui.navigate.to('/'))
                ui.separator()
                ui.menu_item('Dwarfs Settings', on_click=lambda: ui.navigate.to('/Dwarf')).classes('whitespace-nowrap')
                ui.menu_item('Backup Setting', on_click=lambda: ui.navigate.to('/Backup')).classes('whitespace-nowrap')
                ui.menu_item('Dark Library', on_click=lambda: ui.navigate.to('/DarkLibrary')).classes('whitespace-nowrap')
                ui.separator()
                ui.menu_item('Explore', on_click=lambda: ui.navigate.to('/Explore'))
                ui.menu_item('Manual Sessions', on_click=lambda: ui.navigate.to('/ManualExplore')).classes('whitespace-nowrap')
                ui.separator()
                ui.menu_item('Transfer', on_click=lambda: ui.navigate.to('/Transfer'))
                ui.menu_item('Add Session', on_click=lambda: ui.navigate.to('/AddManualSession')).classes('whitespace-nowrap')
                ui.menu_item('Mosaics', on_click=lambda: ui.navigate.to('/Mosaic'))
                ui.separator()
                ui.menu_item('MtpDevice', on_click=lambda: ui.navigate.to('/MtpDevice'))
                ui.menu_item('Catalog', on_click=lambda: ui.navigate.to('/Catalog'))
                ui.menu_item('Settings', on_click=lambda: ui.navigate.to('/Settings'))
                ui.separator()
                ui.menu_item('🌙 Dark Mode', on_click=lambda: dark_mode()).classes('whitespace-nowrap')
                ui.menu_item('☀️ Light Mode', on_click=lambda: light_mode()).classes('whitespace-nowrap')
                ui.menu_item('❓ Help', on_click=open_help)
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