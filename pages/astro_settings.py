import sqlite3
import platform
import shutil
import subprocess
import os
import re
import socket
from components.i18n import t, set_language, get_language, SUPPORTED_LANGUAGES

def _get_app_version():
    """Read version from version.py (built executable) or CHANGELOG.md (dev mode)."""
    try:
        from version import APP_VERSION
        return APP_VERSION
    except ImportError:
        pass
    try:
        import pathlib
        changelog = pathlib.Path(__file__).parent.parent / "CHANGELOG.md"
        with open(changelog, "r", encoding="utf-8") as f:
            for line in f:
                m = re.search(r"\[V?([\d.]+[a-z]?)\]", line)
                if m:
                    return m.group(1)
    except Exception:
        pass
    return "Unknown"

def _get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


import webview
from nicegui import ui, app

from components.menu import menu
from api.dwarf_backup_db import DB_NAME, connect_db, close_db
from api.dwarf_backup_db_api import set_setting_text, get_setting_text
from components.stitch_params_editor import StitchParamsEditor, get_stitch_params

@ui.page('/Settings/')
def astro_settings(InitDwarfLocal = True):

    menu(t("page_settings"))

    # Launch the GUI with the parameters
    ui.context.settings_app =  SettingsApp(DB_NAME, InitDwarfLocal=InitDwarfLocal)
    #ui.context.client.on_disconnect(lambda: logger.removeHandler(handler))

class SettingsApp:
    def __init__(self, database, InitDwarfLocal = True):
        self.database = database
        self.InitDwarfLocal = InitDwarfLocal
        self.path_input = None
        self.build_ui()

    async def choose_folder(self, target_input=None):
        """Open folder selection dialog."""
        if hasattr(webview, 'FileDialog'):
            folder_mode = webview.FileDialog.FOLDER
        else:
            folder_mode = webview.FOLDER_DIALOG

        # Use current value as starting dir only if it's a real existing directory
        current = target_input.value.strip()
        if current and current != "Not Defined" and os.path.isdir(current):
            start_dir = current
        else:
            # Fallback: create a dedicated subfolder in the user's home
            default_dir = os.path.join(os.path.expanduser("~"), "DwarfiumArchive")
            os.makedirs(default_dir, exist_ok=True)
            start_dir = default_dir

        folder = await app.native.main_window.create_file_dialog(
            folder_mode, allow_multiple=False, directory=start_dir
        )
        if folder:
            target_input.set_value(os.path.normpath(folder[0]))
        # If cancelled, leave current value unchanged

    def build_ui(self):
        self.conn = connect_db(self.database)
        current_path = None

        with ui.column().classes("w-full max-w-2xl mx-auto gap-4 mt-4"):

            with ui.card().classes("w-full p-4"):
                from nicegui import app as nicegui_app
                ui.label(t("settings_app_info")).classes("text-xl font-bold mb-2")
                ui.label(f"Version : {_get_app_version()}").classes("text-sm text-gray-600")
                with ui.row().classes("items-center gap-2 mt-2"):
                    ui.label(t("lang_label")).classes("text-sm text-gray-600")
                    ui.select(
                        {"en": "🇬🇧 English", "fr": "🇫🇷 Français"},
                        value=get_language(),
                        on_change=lambda e: (set_language(e.value), ui.navigate.reload())
                    ).classes("w-40")
                if nicegui_app.storage.general.get('LAN_MODE', False):
                    ip = _get_local_ip()
                    port = nicegui_app.storage.general.get('LAN_PORT', 8080)
                    ui.label(f"📡 LAN access: http://{ip}:{port}").classes("text-sm text-blue-600 mt-1")
                else:
                    ui.label(t("settings_lan_disabled")).classes("text-sm text-gray-400 mt-1")
                ui.separator().classes("my-2")
                self._last_report_path = None
                export_status = ui.label("").classes("text-sm text-gray-500 mt-1")

                def open_report():
                    if not self._last_report_path or not os.path.exists(self._last_report_path):
                        ui.notify(t("no_report"), type="warning")
                        return
                    try:
                        import subprocess, platform
                        if platform.system() == "Windows":
                            os.startfile(self._last_report_path)
                        elif platform.system() == "Darwin":
                            subprocess.Popen(["open", self._last_report_path])
                        else:
                            subprocess.Popen(["xdg-open", self._last_report_path])
                    except Exception as e:
                        ui.notify(f"Cannot open file: {e}", type="negative")

                def export_pdf_report():
                    try:
                        import sys
                        tools_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tools")
                        if tools_path not in sys.path:
                            sys.path.insert(0, tools_path)
                        from db_report_pdf import generate_report
                        out = generate_report(self.database)
                        self._last_report_path = out
                        export_status.set_text(f"✅ {os.path.basename(out)}")
                        open_btn.visible = True
                        ui.notify(f"Report saved: {os.path.basename(out)}", type="positive")
                    except Exception as e:
                        export_status.set_text(f"❌ Error: {e}")
                        ui.notify(f"Export failed: {e}", type="negative")

                with ui.row().classes("mt-2 gap-2 items-center"):
                    ui.button(t("settings_export_pdf"), on_click=export_pdf_report) \
                        .props("outlined")
                    open_btn = ui.button(t("settings_open_report"), on_click=open_report) \
                        .props("outlined")
                    open_btn.visible = False

            ui.label(t("dwarf_config")).classes("text-xl font-bold")

            with ui.card().classes("w-full p-4") as info_dwarf_local:
                current_path  = get_setting_text(self.conn, "DWARF_LOCAL_PATH") or "Not Defined"
                self.path_input = ui.input("DWARF_LOCAL_PATH", value=current_path).props("readonly").classes("min-w-[600px] overflow-x-auto whitespace-nowrap")
                ui.label(
                    "⚠️ This folder stores a local index of your sessions\n"
                    "— stacked results only (FITS, PNG, JPG) not the individual raw frames.\n"
                    "Depending on the number of sessions this can still reach 10 GB or more.\n"
                    "Choose a drive with enough free space."
                ).classes("text-sm text-orange-600 mt-2").style('white-space: pre-wrap;')
                if current_path == "Not Defined":
                    self.InitDwarfLocal = False
                    ui.notify('Select a directory to store Dwarf data locally for offline use.', type='warning')
                    current_path = "."

                ui.button("📂 Browse", on_click= lambda: self.choose_folder(target_input=self.path_input)).classes("mt-2")

                def save_path():
                    new_path = self.path_input.value.strip()

                    if not new_path or not os.path.isdir(new_path):
                        ui.notify("Please select a valid existing directory.", type='warning')
                        return

                    set_setting_text(self.conn, "DWARF_LOCAL_PATH", new_path)

                    ui.notify(f"Dwarf Local Parent path saved: {new_path}", type='positive', position='top')

                ui.button(t("save"), on_click=save_path).classes("mt-4")
         
            ui.label(t("nova_config")).classes("text-xl font-bold")

            ui.label(f"Detected System : {platform.system()}")

            with ui.card().classes("w-full"):
                ui.label(t("nova_online"))
                ui.button(t("nova_create_key"),
                          on_click=lambda:ui.navigate.to('https://nova.astrometry.net/api_help', new_tab=True))
                api_key = get_setting_text(self.conn, "NOVA_ASTRO_API") or ""
                api_input = ui.input("API key", value=api_key, password=True)

                def save_api_key():
                    set_setting_text(self.conn, "NOVA_ASTRO_API", api_input.value.strip())
                    ui.notify(t("notif_api_key_saved"), type='positive')

                ui.button(t("save_key"), on_click=save_api_key)

            with ui.card().classes("w-full"):
                ui.label(t("nova_local"))

                if self.check_solve_field():
                    ui.label("✅ solve-field is not available on this system.")
                else:
                    ui.label("❌ solve-field not found.")
                    ui.button(t("nova_install"), on_click=self.install_local_astrometry)

            with ui.card().classes("w-full"):
                ui.label(t("mosaic_params")).classes("text-xl font-bold")
                StitchParamsEditor(self.conn)  # no on_change → Save button

        if not self.InitDwarfLocal:
            with ui.dialog().props('persistent') as dialog, ui.card().classes("w-[500px] p-6"):

                ui.label(t("first_setup")).classes("text-xl font-bold")

                ui.label(
                    "Before using Dwarfium Scope Archive, you need to select a folder to store your local session index.\n"
                    "This folder will contain processed images (FITS, JPG, PNG) and metadata.\n"
                    "Make sure you choose a location with enough free space (can exceed 10GB)."
                ).classes("text-sm text-gray-600").style('white-space: pre-wrap;')

                self.first_path_input = ui.input(
                    "Select a folder",
                    placeholder="Choose a directory..."
                ).props("readonly").classes("w-full")

                ui.button("📂 Browse", on_click=lambda: self.choose_folder(target_input=self.first_path_input)).classes("mt-2")

                def validate_and_continue():
                    path = (self.first_path_input.value or "").strip()

                    if not path or not os.path.isdir(path):
                        ui.notify("Please select a valid directory.", type="warning")
                        return

                    set_setting_text(self.conn, "DWARF_LOCAL_PATH", path)
                    self.InitDwarfLocal = True

                    ui.notify(t("path_saved"), type="positive")
                    dialog.close()

                    # redirect
                    ui.timer(0.5, lambda: ui.navigate.to("/Dwarf?FirstInit=True"), once=True)

                ui.button(t("save_continue"), on_click=validate_and_continue)\
                    .classes("mt-4 w-full")

            dialog.open()  

    def check_solve_field(self):
        return shutil.which("solve-field") is not None

    def install_local_astrometry(self):
        system = platform.system()
        if system == "Windows":
            # Exemple : exécution d’un installeur dans extern/windows/
            subprocess.Popen(["extern\\windows\\astrometry\\install_astrometry.bat"], shell=True)
        elif system == "Linux":
            subprocess.Popen(["bash", "extern/linux/astrometry/install_astrometry.sh"])
        else:
            ui.notify("Installation automatique non supportée pour ce système.", type='warning')