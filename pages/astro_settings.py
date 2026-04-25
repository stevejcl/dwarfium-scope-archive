import sqlite3
import platform
import shutil
import subprocess
import os
import re

def _get_app_version():
    """Read version from version.py (built executable) or CHANGELOG.md (dev mode)."""
    # Production: version.py generated at build time
    try:
        from version import APP_VERSION
        return APP_VERSION
    except ImportError:
        pass
    # Dev mode: read directly from CHANGELOG.md
    try:
        changelog = os.path.join(os.path.dirname(os.path.dirname(__file__)), "CHANGELOG.md")
        with open(changelog, "r", encoding="utf-8") as f:
            for line in f:
                m = re.search(r"\[V?([\d.]+[a-z]?)\]", line)
                if m:
                    return m.group(1)
    except Exception:
        pass
    return "Unknown"


import webview
from nicegui import ui, app

from components.menu import menu
from api.dwarf_backup_db import DB_NAME, connect_db, close_db
from api.dwarf_backup_db_api import set_setting_text, get_setting_text
from components.stitch_params_editor import StitchParamsEditor, get_stitch_params

@ui.page('/Settings/')
def astro_settings(InitDwarfLocal = True):

    menu("Settings")

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
                ui.label("ℹ️ Application Info").classes("text-xl font-bold mb-2")
                ui.label(f"Version : {_get_app_version()}").classes("text-sm text-gray-600")

            ui.label("🔭 Configuration of Dwarf Local Parent directory").classes("text-xl font-bold")

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

                ui.button("Save", on_click=save_path).classes("mt-4")
         
            ui.label("🔭 Configuration of NOVA Astrometry").classes("text-xl font-bold")

            ui.label(f"Detected System : {platform.system()}")

            with ui.card().classes("w-full"):
                ui.label("🌐 Online mode (Astrometry.net)")
                ui.button("Create an API key on Astrometry.net",
                          on_click=lambda:ui.navigate.to('https://nova.astrometry.net/api_help', new_tab=True))
                api_key = get_setting_text(self.conn, "NOVA_ASTRO_API") or ""
                api_input = ui.input("API key", value=api_key, password=True)

                def save_api_key():
                    set_setting_text(self.conn, "NOVA_ASTRO_API", api_input.value.strip())
                    ui.notify("API key saved successfully!", type='positive')

                ui.button("💾 Save key", on_click=save_api_key)

            with ui.card().classes("w-full"):
                ui.label("💻 Local Mode (solve-field)")

                if self.check_solve_field():
                    ui.label("✅ solve-field is not available on this system.")
                else:
                    ui.label("❌ solve-field not found.")
                    ui.button("Install solve-field localy", on_click=self.install_local_astrometry)

            with ui.card().classes("w-full"):
                ui.label("🔭 Mosaic & Stitch Parameters").classes("text-xl font-bold")
                StitchParamsEditor(self.conn)  # no on_change → Save button

        if not self.InitDwarfLocal:
            with ui.dialog().props('persistent') as dialog, ui.card().classes("w-[500px] p-6"):

                ui.label("🚀 First Setup Required").classes("text-xl font-bold")

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

                    ui.notify("Path saved successfully!", type="positive")
                    dialog.close()

                    # redirect
                    ui.timer(0.5, lambda: ui.navigate.to("/Dwarf?FirstInit=True"), once=True)

                ui.button("✅ Save and continue", on_click=validate_and_continue)\
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