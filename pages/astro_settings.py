import sqlite3
import platform
import shutil
import subprocess
import os

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

    async def choose_folder(self):
        """Open folder selection dialog."""
        if hasattr(webview, 'FileDialog'):
            folder_mode = webview.FileDialog.FOLDER
        else:
            folder_mode = webview.FOLDER_DIALOG

        if self.path_input.value:
            full_path = os.path.abspath(self.path_input.value)
            folder = await app.native.main_window.create_file_dialog(folder_mode, allow_multiple=False,directory=full_path)
            if folder:
                folder = os.path.normpath(folder[0])
                self.path_input.set_value(folder)
            else:
                self.path_input.set_value("Not Defined")

    def build_ui(self):
        self.conn = connect_db(self.database)

        with ui.column().classes("w-full max-w-2xl mx-auto gap-4 mt-4"):

         ui.label("🔭 Configuration of Dwarf Local Parent directory").classes("text-xl font-bold")

         with ui.card().classes("w-full p-4") as info_dwarf_local:
            current_path  = get_setting_text(self.conn, "DWARF_LOCAL_PATH") or "Not Defined"
            self.path_input = ui.input("DWARF_LOCAL_PATH", value=current_path).props("readonly").classes("min-w-[600px] overflow-x-auto whitespace-nowrap")
            if current_path == "Not Defined":
                ui.notify('Select a directory to store Dwarf data locally for offline use.', type='warning')
                current_path = "."

            ui.button("Browse...", on_click=self.choose_folder).classes("mt-2")

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
                      on_click=lambda: ui.open('https://nova.astrometry.net/api_help'))
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
            ui.notify(f"Configured path not found", type='warning')
            with ui.dialog().props('persistent')  as dialog, ui.card():
                # Create the GUI with NiceGUI
                with ui.card().style('width: 400px; padding: 20px;'):
                    ui.label("Select a directory to store Dwarf data locally for offline use:").style('font-size: 16px; margin-bottom: 10px;')
                    path_input = ui.input("DWARF_LOCAL_PATH", value=current_path).props("readonly").classes("min-w-[600px] overflow-x-auto whitespace-nowrap")

                    ui.button("Browse...", on_click=self.choose_folder).classes("mt-2")

                    ui.button('Close', on_click=dialog.close)
            dialog.open()
            info_dwarf_local.update()

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

