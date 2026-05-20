from components.i18n import t
# components/menu.py
from nicegui import ui, app
from components.help_system import register_drawer, open_help



def setStyle(color_primary = '#00ae83'):

    ui.colors(
        primary=color_primary
    )

def menu(title):

    # Thin window scrollbar — applied globally on all pages
    ui.add_head_html("""
    <style>
        html::-webkit-scrollbar { width: 6px; }
        html::-webkit-scrollbar-track { background: transparent; }
        html::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.2); border-radius: 3px; }
        html::-webkit-scrollbar-thumb:hover { background: rgba(0,0,0,0.4); }
        html { scrollbar-width: thin; scrollbar-color: rgba(0,0,0,0.2) transparent; }
    </style>
    """)

    dark = ui.dark_mode()
    if app.storage.user.get('ui_mode',0) == 'dark' :
        dark.enable()
        ui.query('body').style(f'background-color: {"#262608"}')
    else:
        dark.disable()
        ui.query('body').style(f'background-color: {"#f5f5e6"}')

    ui.button(t("top"), on_click=lambda: ui.run_javascript('window.scrollTo({top: 0, behavior: "smooth"})')) \
        .props('round color=primary') \
        .classes('fixed bottom-4 right-4 z-[9999] shadow-lg')

    register_drawer()

    with ui.row().classes('relative w-full items-center'):
        ui.label(title).classes("text-2xl font-bold my-2")

        # Transfer progress badge — shown on any page when a transfer is running
        # Centered badge
        badge = ui.label("").classes(
            "text-sm font-semibold px-2 py-1 rounded bg-green-100 text-green-800 cursor-pointer "
            "absolute left-1/2 -translate-x-1/2 animate-pulse"
        ).on('click', lambda: ui.navigate.to('/Transfer'))
        badge.visible = False

        def _check_transfer():
            try:
                p = app.storage.general.get('transfer_progress', None)
                is_active = p and p['status'] in ('running', 'copy_done', 'scanning')
                if p and p['status'] == 'running':
                    total  = p.get('total', 0)
                    copied = p.get('copied', 0)
                    badge.text = f"📦 {copied}/{total}"
                    badge.visible = True
                elif p and p['status'] == 'copy_done':
                    badge.text = t("syncing_db")
                    badge.visible = True
                elif p and p['status'] == 'scanning':
                    badge.text = p.get('current_file', '🔍 Scanning...')
                    badge.visible = True
                elif p and p['status'] == 'done':
                    badge.text = t("transfer_done")
                    badge.visible = True
                elif p and p['status'] == 'error':
                    badge.text = t("transfer_error")
                    badge.visible = True
                else:
                    badge.visible = False
                    is_active = False
                close_warning.visible = bool(is_active)
            except Exception:
                _badge_timer.cancel()

        _badge_timer = ui.timer(2.0, _check_transfer)
        ui.context.client.on_disconnect(lambda: _badge_timer.cancel())

        #ui.button(t("dwarf_connect")).classes('text-sm')

        with ui.button(icon='menu').classes('text-sm ml-auto'):
            with ui.menu().classes('max-h-none'):
                ui.menu_item(t("menu_home"), on_click=lambda: ui.navigate.to('/'))
                ui.separator()
                ui.menu_item(t("menu_dwarf_settings"), on_click=lambda: ui.navigate.to('/Dwarf')).classes('whitespace-nowrap')
                ui.menu_item(t("menu_backup_settings"), on_click=lambda: ui.navigate.to('/Backup')).classes('whitespace-nowrap')
                ui.menu_item(t("menu_darks"), on_click=lambda: ui.navigate.to('/DarkLibrary')).classes('whitespace-nowrap')
                ui.separator()
                ui.menu_item(t("menu_explore"), on_click=lambda: ui.navigate.to('/Explore'))
                ui.menu_item(t("menu_manual_sessions"), on_click=lambda: ui.navigate.to('/ManualExplore')).classes('whitespace-nowrap')
                ui.separator()
                ui.menu_item(t("menu_transfer"), on_click=lambda: ui.navigate.to('/Transfer'))
                ui.menu_item(t("menu_add_session"), on_click=lambda: ui.navigate.to('/AddManualSession')).classes('whitespace-nowrap')
                ui.menu_item(t("menu_mosaic"), on_click=lambda: ui.navigate.to('/Mosaic'))
                ui.separator()
                ui.menu_item(t("menu_catalog"), on_click=lambda: ui.navigate.to('/Catalog'))
                ui.menu_item(t('sky_map_menu'), on_click=lambda: ui.navigate.to('/SkyMap'))
                ui.menu_item(t("menu_report"), on_click=lambda: ui.navigate.to('/Report')).classes('whitespace-nowrap')
                ui.separator()
                ui.menu_item(t("menu_mtp"), on_click=lambda: ui.navigate.to('/MtpDevice'))
                ui.menu_item(t("menu_settings"), on_click=lambda: ui.navigate.to('/Settings'))
                ui.separator()
                ui.menu_item(t("menu_dark_mode"), on_click=lambda: dark_mode()).classes('whitespace-nowrap')
                ui.menu_item(t("menu_light_mode"), on_click=lambda: light_mode()).classes('whitespace-nowrap')
                ui.menu_item(t("menu_help"), on_click=open_help)

    # Warning banner — visible on ALL pages when a transfer is running
    def _stop_transfer():
        app.storage.general['transfer_cancel_requested'] = True
        ui.notify(t("transfer_cancellation"), type="warning")

    with ui.element('div').classes('w-full') as close_warning:
        with ui.row().classes("relative w-full items-center bg-red-50 border border-red-300 rounded px-3 py-1"):
            # Centered button (absolute)
            ui.button(t("stop_transfer"), on_click=_stop_transfer) \
                .props("flat dense color=negative") \
                .classes("text-xs absolute left-1/2 -translate-x-1/2")
            # Right-aligned text
            ui.label(t("transfer_close_warn")) \
                .classes("ml-auto text-sm font-semibold text-red-600 text-right")
    close_warning.visible = False
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