from components.i18n import t
import urllib.parse
import webview
from nicegui import native, app, run, ui
import os
import subprocess
import re
from api.dwarf_backup_db import DB_NAME, connect_db, close_db
from components.db_page_mixin import DbPageMixin
from api.dwarf_backup_fct import create_local_dwarf_dir, get_local_dwarf_dir, sync_dwarf_sessions, scan_backup_folder, insert_or_get_backup_drive, get_directory_size_format, empty_local_archive_dwarf_dir, get_disk_space_info
from api.dwarf_backup_fct_ftp import ftp_conn, check_ftp_connection, connect_to_dwarf, ftp_sync_dwarf_sessions
from api.dwarf_backup_fct_ftp import DWARF2_FTP_PATH, DWARF3_FTP_PATH

from api.dwarf_backup_mtp_handler import MTPManager 
from api.dwarf_backup_db_api import get_dwarf_Names, get_dwarf_detail, set_dwarf_detail, add_dwarf_detail
from api.dwarf_backup_db_api import get_mtp_devices, device_exists_in_db, add_mtp_device_to_db
from api.dwarf_backup_db_api import has_related_dwarf_entries, delete_dwarf_entries_and_dwarf_data, del_dwarf
from api.dwarf_backup_db_api import get_dwarf_sessions_error

from components.win_log import WinLog
from components.menu import menu, setStyle
from components.help_system import open_help
from components.disk_space_widget import disk_space_widget


@ui.page('/Dwarf')
async def dwarf_settings(DwarfId:int = None, FirstInit=False):

    menu(t("page_dwarf"))
    await ui.context.client.connected(timeout=10.0)
    # Launch the GUI
    ConfigApp(DB_NAME, DwarfId=DwarfId, FirstInit=FirstInit)
    #ui.context.client.on_disconnect(lambda: logger.removeHandler(handler))
    

class ConfigApp(DbPageMixin):
    def __init__(self, database, DwarfId=None, FirstInit=False):
        self.FirstInit = FirstInit
        self.database = database
        self.dwarfs = []
        self.dwarf_id = DwarfId
        self.error_sessions_container = None
        self.btn_error_sessions = None
        self.dwarf_type_map = {
            1: "Dwarf2",
            2: "Dwarf3",
            4: "Dwarf Mini"
        }
        self.dwarf_status = None
        self.show_info_ftp = True
        self.dwarf_mtp_id = None
        self.mtp_select = {}
        self.mtp_visible = False
        self.mtp_devices = []
        self.device_path = None
        self.dwarf_scan_date = None
        self.mtp_status_label = None
        self.dwarf_data_size = None
        self.dwarf_archive_size = None
        self.dwarf_free_size = None
        self._dwarf_usb_disk_widget = None
        self.WinLog = WinLog()
        self.build_ui()

    def build_ui(self):
        self.conn = connect_db(self.database)
        self.register_conn_close()
        sizeBTN='w-56'

        self.dwarf_type_name_to_id = {v: k for k, v in self.dwarf_type_map.items()}

        with ui.card().classes("w-full max-w-3xl mx-auto"):
            #with ui.grid(columns=2).classes("w-full"):
            with ui.row().classes("w-full justify-between"):
                ui.button(t("show_dwarf_data"), on_click=lambda: ui.navigate.to(self.get_explore_url())).classes(sizeBTN)
                self.btn_error_sessions = ui.button(
                    t("sessions_in_error"),
                    on_click=self._toggle_error_sessions
                ).classes(sizeBTN).props("color=orange")
                self.btn_error_sessions.set_visibility(False)
                ui.button(t("analyze_dwarf_drive"), on_click=self.analyze_usb_drive).classes(sizeBTN)

            self.error_sessions_container = ui.column().classes("w-full")
            self.error_sessions_container.visible = False

            ui.separator()

            with ui.row().classes('w-full gap-8 items-start'):

                # Left: Add New button
                with ui.column().classes('items-start pt-8'):
                    ui.button(t("add_dwarf"), on_click=self.set_new_dwarf).classes(sizeBTN)

                # Right: form fields
                with ui.column().classes('items-start flex-1'):
                    ui.label(t("select_existing_dwarf")).classes("text-lg font-semibold")

                    # Dwarf Selection
                    self.dwarf_selector = ui.select(
                        options=[],
                        on_change=self.load_selected_dwarf,
                        label=t("please_select")
                    ).props('stack-label').props('outlined').classes('w-60')

                    with ui.row().classes('items-center gap-4'):
                        self.dwarf_name = ui.input(t("dwarf_name_label")).classes('w-55')
                        ui.button(t("delete_dwarf"),
                                  on_click=self.confirm_and_delete_Dwarf).props("color=red").classes(sizeBTN)

                    self.dwarf_desc = ui.input(t("description")).classes('w-55')

                    # Dwarf Type selection
                    self.dwarf_type_var = ui.select(
                        options=list(self.dwarf_type_map.values()),
                        value="Dwarf3",
                        label=t("type_label"),
                        on_change=self.modif_dwarf_type
                    ).props('stack-label').props('outlined').classes('w-60')

                    with ui.row().classes('items-center gap-4'):
                        self.dwarf_astroDir = ui.input(t("astronomy_dir")).classes('w-55')
                        ui.button(t("select_usb_folder"), on_click=self.select_dwarf_folder).classes(sizeBTN)

                    with ui.row().classes('items-center mt-1 gap-2'):
                        self.usb_status_label = ui.label("").classes('text-sm')
                        self.refresh_btn = (
                            ui.button(icon='refresh', on_click=self.check_dir_dwarf).classes('text-sm')
                            .props('flat round dense')
                            .bind_visibility_from(self.usb_status_label, 'text', lambda v: (v == t("path_not_detected")))
                        )

                    with ui.grid(columns=2) as self.mtp_column:
                        self.render_mtp_section()
                    self.mtp_column.visible = False

                    self.mtp_status_label = ui.label("").classes('text-sm')
                    self.mtp_status_label.visible = False

                    with ui.grid(columns=2):
                        self.dwarf_ip_sta_mode = ui.input(
                            t("ip_sta_mode"),
                            validation={'Invalid IP address': lambda value: self.is_valid_ip(value)}
                        ).classes('w-55')
                        with ui.row().classes("gap-4 mt-4"):
                            self.ftp_spinner = ui.spinner(size="1em")
                            self.ftp_status_label = ui.label("").classes('pt-4')

                    with ui.grid(columns=2):
                        with ui.card().tight():
                            ui.colors(brand='#A1A0A1')
                            ui.item_label(t("last_scan")).props('stack-label').classes('pl-3 pr-3 pt-2').classes('text-brand')
                            self.dwarf_scan_date = ui.label("").classes("pl-3 pr-3 pb-2")
                        # Disk space of the Dwarf device itself (USB only)
                        self._dwarf_usb_disk_widget = disk_space_widget(None)

            # ── Bottom: action buttons ────────────────────────────────────────
            ui.separator()
            with ui.row().classes("w-full mt-2 mb-2 justify-between"):
                ui.button(t("save_update_dwarf"), on_click=self.save_or_update_dwarf).classes(sizeBTN)
                ui.button(t("delete_dwarf_entries"),
                          on_click=self.confirm_and_delete_dwarf_entries).props("color=red").classes(sizeBTN)

            ui.separator()

            with ui.row().classes('w-full gap-8 items-center') as self.local_info: 
                with ui.column().classes('justify-center'):
                    ui.button(t("empty_archive"), on_click=self.confirm_and_delete_dwarf_archive).props("color=red").classes(sizeBTN)

                with ui.column().classes('flex-1'):
                    with ui.card().tight().classes('w-full'):
                        ui.colors(brand='#A1A0A1')
                        with ui.grid(columns=3).classes('w-full text-center gap-y-1'):
                            ui.item_label(t('local_data_size')).props('stack-label').classes('pl-2 pr-1 pt-0 pb-1').classes('text-brand text-sm')
                            ui.item_label(t('local_archive_size')).props('stack-label').classes('pl-2 pr-1 pt-0 pb-1').classes('text-brand text-sm')
                            ui.item_label(t('local_free_size')).props('stack-label').classes('pl-2 pr-1 pt-0 pb-1').classes('text-brand text-sm')

                            self.dwarf_data_size = ui.label("").classes('text-base')
                            self.dwarf_archive_size = ui.label("").classes('text-base')
                            self.dwarf_free_size = ui.label("").classes('text-base')

        # need this button don't change if not
        setStyle()
        self.local_info.visible = False
        self.refresh_dwarf_list()

    def is_valid_ip(self, value):
        if not value:
            return True
        if self.show_info_ftp:
            ui.notify(t("dwarf_ip_long"), type="info")
            self.show_info_ftp = False
        ip_pattern = r'^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
        return re.match(ip_pattern, value) is not None

    def check_dir_dwarf(self):
        if self.dwarf_astroDir.value:
           if os.path.exists(self.dwarf_astroDir.value):
               self.dwarf_status = "USB"
               self.usb_status_label.text = t("path_detected")
               # Show USB drive space immediately
               if self._dwarf_usb_disk_widget:
                   ui.timer(0, lambda: ui.timer(0, lambda: self._dwarf_usb_disk_widget.refresh(self.dwarf_astroDir.value.strip()), once=True), once=True)
           else:
               self.usb_status_label.text = t("path_not_detected")

    def refresh_dwarf_list(self):
        """Refresh the list of dwarfs and update the selection dropdown."""
        self.dwarf_status = None
        self.ftp_spinner.set_visibility(False)
        self.ftp_status_label.text = ""
        self.usb_status_label.text = ""
        self.dwarfs = get_dwarf_Names(self.conn)

        # Create a list of tuples: (id, name)
        display_names = [f"{id} - {name}" for id, name in self.dwarfs]

        # Update the select options AND set a default value if needed
        print(f"initial:{self.dwarf_selector.value}")
        print(f"dwarf_id:{self.dwarf_id}")
        if display_names:
            # Auto-select if only one dwarf or if dwarf_id is set
            if len(self.dwarfs) == 1 and not self.dwarf_selector.value:
                self.dwarf_selector.set_options(display_names, value=display_names[0])
                self.dwarf_id = self.dwarfs[0][0]
            elif self.dwarf_id and not self.dwarf_selector.value:
                selected_value = next((name for id, name in self.dwarfs if id == self.dwarf_id), None)
                print(selected_value)
                selected_display = f"{self.dwarf_id} - {selected_value}" if selected_value else display_names[0]
                self.dwarf_selector.set_options(display_names, value=selected_display)
            elif self.dwarf_id and self.dwarf_selector.value and self.dwarf_id != int(self.dwarf_selector.value.split(" - ")[0]):
                selected_value = next((name for id, name in self.dwarfs if id == self.dwarf_id), None)
                selected_display = f"{self.dwarf_id} - {selected_value}" if selected_value else display_names[0]
                self.dwarf_selector.set_options(display_names, value=selected_display)
            else:
                value = self.dwarf_selector.value
                self.dwarf_selector.set_options(display_names, value=None)
                self.dwarf_selector.set_options(display_names, value=value)
        else:
            self.dwarf_selector.set_options([], value=None)
            self.FirstInit = True

        if self.FirstInit:
            ui.notify(t("first_run"), type="info")
            ui.timer(1.5, lambda: open_help(True), once=True)

        # Update the dictionary mapping
        self.dwarf_name_to_id = {f"{id} - {name}": id for id, name in self.dwarfs}

    async def check_status_dwarf(self):
        self.check_dir_dwarf()
        if not self.dwarf_ip_sta_mode.value:
            return
        current_ip = self.dwarf_ip_sta_mode.value
        status_text = "❌ Unable to check status."  # valeur par défaut
        try:
            self.ftp_spinner.set_visibility(True)
            status_text = await run.io_bound(check_ftp_connection, self.dwarf_ip_sta_mode.value)
        finally:
            # Update only if the IP has not changed
            if current_ip == self.dwarf_ip_sta_mode.value:
                self.ftp_spinner.set_visibility(False)
                self.ftp_status_label.text = status_text  # Show the result
                if not self.dwarf_status and status_text and status_text.startswith("✅ Connected"):
                    self.dwarf_status = "FTP"

    async def load_selected_dwarf(self, event):
        """Load data when a dwarf is selected from the dropdown."""
        await self.detect_mtp_devices()

        self.dwarf_status = None
        self.ftp_status_label.text = ""
        self.usb_status_label.text = ""
        value = self.dwarf_selector.value
        print(f"value {value}")
        if not value:
            return
        try:
            self.dwarf_id = int(value.split(" - ")[0])  # Extracts "1" from "1 - Dwarf3"
        except (IndexError, ValueError):
            ui.notify(t("invalid_dwarf"), type="negative")
            return

        row = get_dwarf_detail(self.conn, self.dwarf_id)
        if row:
            self.dwarf_name.value = row[0]
            self.dwarf_desc.value = row[1] or ""
            self.dwarf_astroDir.value = row[2] or ""
            self.dwarf_type_var.value = self.dwarf_type_map[int(row[3])]
            self.dwarf_scan_date.text = row[4]
            self.dwarf_ip_sta_mode.value = row[5]
            self.dwarf_mtp_id = row[6]
            self.modif_dwarf_type()
            self.refresh_error_sessions_btn()
            await self.show_local_data()
            await self.check_status_dwarf()


    def _toggle_error_sessions(self):
        """Show/hide the error sessions panel."""
        self.error_sessions_container.visible = not self.error_sessions_container.visible
        if self.error_sessions_container.visible:
            self._load_error_sessions()

    def _load_error_sessions(self):
        """Render error sessions list inside the container."""
        self.error_sessions_container.clear()
        if not self.dwarf_id:
            return
        rows = get_dwarf_sessions_error(self.conn, self.dwarf_id)
        with self.error_sessions_container:
            if not rows:
                ui.label(t("no_sessions_error")).classes("text-green-600")
                return
            with ui.card().classes("w-full p-3"):
                ui.label(t("sessions_error_title")).classes("text-base font-semibold mb-1")
                for row in rows:
                    # row: id, dwarf_id, session_date, session_dir, session_dir_master, status
                    _, _, session_date, session_dir, session_dir_master, status = row
                    status_color = "text-green-600" if status == "REPAIRED" else "text-orange-500"
                    status_icon  = "✅" if status == "REPAIRED" else "⚠️"
                    with ui.row().classes("items-center gap-2 w-full py-1 border-b"):
                        ui.label(f"{status_icon}").classes("text-base")
                        with ui.column().classes("gap-0 flex-1"):
                            ui.label(session_dir).classes("font-mono text-sm")
                            if session_date:
                                ui.label(f"📅 {session_date}").classes("text-xs text-gray-500")
                            ui.label(f"Status: {status}").classes(f"text-xs {status_color}")
                            if session_dir_master:
                                ui.label(f"Repaired from: {session_dir_master}").classes("text-xs text-gray-400")
                        sd = session_dir  # capture for lambda
                        ui.button("📂", on_click=lambda s=sd: self._open_session_folder(s))                             .props("flat dense").tooltip("Open folder in explorer")

    def _open_session_folder(self, session_dir: str):
        """Open the session folder in the OS file explorer (same logic as explore open_folder)."""
        base = self.dwarf_astroDir.value.strip() if self.dwarf_astroDir.value else ""
        full_path = os.path.normpath(os.path.join(base, session_dir) if base else session_dir)
        if not os.path.exists(full_path):
            ui.notify(t("folder_not_found", path=full_path), type="warning")
            return
        if os.name == "nt":  # Windows
            subprocess.Popen(f'explorer "{full_path}"')
        elif os.name == "posix":  # macOS or Linux
            subprocess.Popen(["open", full_path])

    def refresh_error_sessions_btn(self):
        """Show/hide the error sessions button depending on whether errors exist."""
        if not self.dwarf_id or not self.btn_error_sessions:
            return
        rows = get_dwarf_sessions_error(self.conn, self.dwarf_id)
        self.btn_error_sessions.set_visibility(len(rows) > 0)
        if self.error_sessions_container.visible:
            self._load_error_sessions()

    def modif_dwarf_type(self):
        # Set mtp_visible based on the selected type
        self.mtp_visible = (self.dwarf_type_var.value == self.dwarf_type_map[1])
        print(f" MTP Visible : {self.mtp_visible}")
        self.render_mtp_section()  # Refresh MTP section

    def render_mtp_section(self):
        self.mtp_column.clear()

        if not self.mtp_visible:
            self.mtp_column.visible = False
            if self.mtp_status_label:
                self.refesh_mtp_status()
            return

        self.mtp_column.visible = True

        mtp_device_details = get_mtp_devices(self.conn)

        if mtp_device_details:
            # Extracting MTP options and name correctly
            mtp_options = [f"{device[0]} - {device[1]}" for device in mtp_device_details]  # Example: "DWARF 1"
            device_map = {f"{device[0]} - {device[1]}": device[2] for device in mtp_device_details}

            print("Options:", mtp_options)
            print("Device Map:", device_map)
            print("Dwarf_mtp_id:", self.dwarf_mtp_id)

            self.device_path = None
            if self.dwarf_mtp_id:
                mtp_name = next(
                   (option for option in mtp_options if option.split(' - ')[0].strip() == str(self.dwarf_mtp_id).strip()), 
                   None
                )
                if mtp_name:
                   self.device_path = device_map.get(mtp_name)
            else:
                mtp_name = None

            print("mtp_name:", mtp_name)
            print("Device Path:", self.device_path)

            # Now create the UI select with friendly names
            with self.mtp_column:
                self.dwarf_mtpdevice = ui.select(
                    label=t("mtp_device"),
                    options=mtp_options,
                    value=mtp_name,
                    on_change=lambda: self.on_mtp_selected(device_map)
                ).props('stack-label').props('outlined').classes('w-40')
                with ui.row().classes("w-full pt-4"):
                    ui.button(t("detect_mtp"), on_click=self.detect_mtp_devices)

            self.refesh_mtp_status(self.device_path)

    def on_mtp_selected(self, device_map):
        selected = self.dwarf_mtpdevice.value
        if selected:
            self.dwarf_mtp_id = int(selected.split(' - ')[0].strip())
            self.device_path = device_map.get(selected, None)
            self.refesh_mtp_status(self.device_path)
            print(f"Selected MTP Device: {selected} {self.dwarf_mtp_id}-> {self.device_path}")

    def refesh_mtp_status(self, device_path = None):
        if self.mtp_visible and device_path and any(path == device_path for _, path in self.mtp_devices):
            self.mtp_status_label.visible = True
            self.mtp_status_label.text = "✅ MTP Connected"
            if not self.dwarf_status:
                self.dwarf_status = "MTP"
        elif self.mtp_visible:
            self.mtp_status_label.visible = True
            self.mtp_status_label.text = "❌ MTP not Connected"

        else:
            self.mtp_status_label.visible = False
            self.mtp_status_label.text = ""

    async def detect_mtp_devices(self):
        add_new = False
        mtp = MTPManager()

        available = await run.io_bound(
                mtp.is_MTP_available
            )

        if available:
            self.mtp_devices = mtp.list_mtp_devices()
            print(f"detect_mtp_devices {len(self.mtp_devices)}")
        
            for name, path in self.mtp_devices:
                print(f" device: {name}-{path}")
                is_in_db = device_exists_in_db(self.conn, path)
                print(f" in db: {is_in_db}")
                if not is_in_db:
                    add_new = add_mtp_device_to_db(self.conn, name, path)

            if add_new:
                self.render_mtp_section()
            self.refesh_mtp_status(self.device_path)
        else:
            print("MTP is not available.")

    async def set_new_dwarf(self):
        """Reset the form for adding a new dwarf."""
        self.dwarf_selector.value = ""
        self.local_info.visible = False
        self.dwarf_id = None
        self.dwarf_name.value = ""
        self.dwarf_desc.value = ""
        self.dwarf_astroDir.value = ""
        self.dwarf_type_var.value = self.dwarf_type_map[2]  # Default to Dwarf3
        self.dwarf_ip_sta_mode.value = ""
        self.dwarf_scan_date.text = ""
        self.dwarf_status = None
        self.ftp_spinner.set_visibility(False)
        self.ftp_status_label.text = ""
        self.usb_status_label.text = ""
        await self.detect_mtp_devices()

    async def select_dwarf_folder(self):
        """Open folder selection dialog."""
        ui.notify(t("please_astro_dir"), type="info")
        dwarf_location = self.dwarf_astroDir.value
        if hasattr(webview, 'FileDialog'):
            folder_mode = webview.FileDialog.FOLDER
        else:
            folder_mode = webview.FOLDER_DIALOG

        if dwarf_location:
            folder = await app.native.main_window.create_file_dialog(folder_mode, allow_multiple=False,directory=dwarf_location)
        else:
            folder = await app.native.main_window.create_file_dialog(folder_mode, allow_multiple=False)
        if folder:
            ui.notify(folder[0])
            folder = os.path.normpath(folder[0])
            self.set_folder_path(folder)

    def set_folder_path(self, folder_path):
        """Set folder path."""
        self.dwarf_astroDir.value = folder_path
        self.check_dir_dwarf()

    def connect_ftp(self):
        with ui.dialog().props('persistent')  as dialog, ui.card():
            # Create the GUI with NiceGUI
            with ui.card().style('width: 400px; padding: 20px;'):
                ui.label(t("dwarf_ip")).style('font-size: 16px; margin-bottom: 10px;')
                ip_input = ui.input().style('width: 100%; margin-bottom: 20px; padding: 10px; font-size: 14px;')

                connect_button = ui.button(t("connect"), on_click=lambda: connect_to_dwarf(ip_input.value.strip(), status_label))

                status_label = ui.label().style('font-size: 14px; color: #FF5722; margin-top: 20px;')
                ui.button(t("close"), on_click=dialog.close)
        dialog.open()

    async def save_or_update_dwarf(self):
        """Save or update the dwarf data in the database."""
        name = self.dwarf_name.value
        desc = self.dwarf_desc.value
        usb_astronomy_dir = self.dwarf_astroDir.value
        selected_type = self.dwarf_type_var.value
        dtype = self.dwarf_type_name_to_id.get(selected_type, 1)
        ip_sta_mode = self.dwarf_ip_sta_mode.value
        mtp_id = self.dwarf_mtp_id

        if not name:
            ui.notify(t("name_required"), type="negative")
            return

        if self.dwarf_id:  # Update
            set_dwarf_detail(self.conn, name, desc, usb_astronomy_dir, dtype, ip_sta_mode, mtp_id, self.dwarf_id)
            ui.notify(t("dwarf_updated", name=name), type="positive")
        else:  # Insert
            self.dwarf_id = add_dwarf_detail(self.conn, name, desc, usb_astronomy_dir, dtype, ip_sta_mode, mtp_id)
            ui.notify(t("dwarf_created", name=name, id=self.dwarf_id), type="positive")

        self.refresh_dwarf_list()

    async def analyze_usb_drive(self):
        """Analyze the Dwarf drive and scan files."""
        if not self.dwarf_id:
            ui.notify(t("no_dwarf_selected"), type="negative")
            return

        if not self.dwarf_status:
            ui.notify(t("dwarf_not_connected"), type="negative")
            return

        ftp = None
        if self.dwarf_status == "USB":
            dwarf_location = self.dwarf_astroDir.value.strip()
            if not dwarf_location:
                ui.notify(t("no_usb_location"), type="negative")
                return
            if not os.path.isdir(dwarf_location):
                ui.notify(t("usb_inaccessible"), type="negative")
                return
        elif self.dwarf_status == "FTP":
            if str(self.dwarf_type_var.value) == "Dwarf2":
                dwarf_location = DWARF2_FTP_PATH
            elif str(self.dwarf_type_var.value) == "Dwarf3":
                dwarf_location = DWARF3_FTP_PATH
            elif str(self.dwarf_type_var.value) == "Dwarf Mini":
                dwarf_location = DWARF3_FTP_PATH
            else:
                ui.notify(t("unsupported_device"), type="negative")
                return
            ftp_ctx = ftp_conn(self.dwarf_ip_sta_mode.value) if self.dwarf_ip_sta_mode.value else None
            ftp = ftp_ctx.__enter__() if ftp_ctx else None
            if not ftp:
                ui.notify(t("ftp_disconnected"), type="negative")
                return
        else:
            ui.notify(t("unsupported_conn"), type="negative")
            return

        # Dialog to block interaction and show progress
        with ui.dialog().props('persistent')  as dialog, ui.card().classes("w-full p-4").style("max-width: 1200px; height: 800px; margin: auto"):
            error_label = ui.label().style('color: red')  # Empty label for future error messages
            close_button = ui.button(t("close"), on_click=dialog.close, color="secondary").props('visible')  # initially hidden
            ui.label(t("scanning_dwarf"))
            spinner = ui.spinner(size="lg")
            scan_progress_bar   = ui.linear_progress(value=0, show_value=False).classes("w-full")
            scan_progress_label = ui.label("").classes("text-sm text-gray-500")
            log = ui.log(max_lines=100).classes('w-full').style('height: 560px; overflow: hidden;')

        dialog.open()  # show the dialog
        spinner.set_visibility(True)

        def _on_scan_progress(current_dir, done, total):
            """Called from the io_bound thread for each top-level folder scanned."""
            try:
                scan_progress_bar.set_value(done / total if total else 0)
                scan_progress_label.set_text(f"[{done}/{total}] 🔍 {current_dir}")
            except Exception:
                pass

        try:
            local_Main_Dwarf_dir = create_local_dwarf_dir(self.conn)
            if local_Main_Dwarf_dir:
                ui.notify(t("starting_sync"))

                # ── Shared progress state: sync sessions + scan dirs ──────────
                _skip_dirs = {"Archive", "CALI_FRAME", "Solving_Failed", "DWARF_DARK", "RESTACKED", "STARTRAILS"}

                def _count_sessions(root):
                    """Count top-level session dirs (excluding special folders)."""
                    if not root or not os.path.exists(root):
                        return 0
                    count = sum(
                        1 for d in os.listdir(root)
                        if d not in _skip_dirs and os.path.isdir(os.path.join(root, d))
                    )
                    for sub in ("RESTACKED", "STARTRAILS"):
                        sub_path = os.path.join(root, sub)
                        if os.path.isdir(sub_path):
                            count += sum(
                                1 for d in os.listdir(sub_path)
                                if os.path.isdir(os.path.join(sub_path, d))
                            )
                    return count

                def _count_scan_dirs(root):
                    if not root or not os.path.exists(root):
                        return 0
                    return sum(
                        1 for d in os.listdir(root)
                        if d not in _skip_dirs and os.path.isdir(os.path.join(root, d))
                    )

                sync_total = _count_sessions(dwarf_location) if self.dwarf_status == "USB" else 0
                # scan total is not yet known (local dir built after sync) — estimated from source
                scan_total_estimate = _count_scan_dirs(dwarf_location) if self.dwarf_status == "USB" else 0
                grand_total = sync_total + scan_total_estimate or 1

                progress_state = {"offset": 0}

                def _make_progress_cb(phase_label=""):
                    def _cb(current_dir, done, phase_total):
                        grand_done = progress_state["offset"] + done
                        grand_ttl  = max(grand_total, progress_state["offset"] + phase_total)
                        pct = round(grand_done / grand_ttl * 100) if grand_ttl else 0
                        try:
                            scan_progress_bar.set_value(grand_done / grand_ttl if grand_ttl else 0)
                            scan_progress_label.set_text(
                                f"[{grand_done}/{grand_ttl}] ({pct}%) {phase_label}{current_dir}"
                            )
                        except Exception:
                            pass
                    return _cb

                if self.dwarf_status == "USB":
                    await run.io_bound(sync_dwarf_sessions, self.dwarf_id, dwarf_location, local_Main_Dwarf_dir, None, log, _make_progress_cb("🔄 "))
                if self.dwarf_status == "FTP":
                    await run.io_bound(ftp_sync_dwarf_sessions, ftp, self.dwarf_id, dwarf_location, local_Main_Dwarf_dir, None, log, _make_progress_cb("🔄 "))

                # Advance offset to sync_total before scan phase
                progress_state["offset"] = sync_total

                local_Dwarf_dir = get_local_dwarf_dir(self.conn, self.dwarf_id)
                print(local_Dwarf_dir)
                ui.notify(t("starting_analysis"))
                total, deleted, _ = await run.io_bound(scan_backup_folder, DB_NAME, local_Dwarf_dir, None, self.dwarf_id, None, None, log, _make_progress_cb("🔍 "))
                scan_progress_bar.set_value(1)
                scan_progress_label.set_text(t("analysis_complete", total=total, deleted=deleted))
                ui.notify(t("analysis_complete", total=total, deleted=deleted), type="positive")
            else:
               ui.notify(t("dwarf_local_dir_create_error"), type="negative")
            spinner.set_visibility(False)

        except Exception as e:
            spinner.set_visibility(False)
            msg = f"❌ Error: {str(e)}"
            ui.notify(msg, type="negative")
            error_label.text = msg 
            close_button.visible = True
        else:
            ui.timer(5, lambda: self.end_analyze_usb_drive(dialog), once=True)

    async def end_analyze_usb_drive(self, dialog):
        dialog.close()
        await self.load_selected_dwarf(None)
        self.refresh_error_sessions_btn()


    async def confirm_and_delete_Dwarf(self):
        if self.dwarf_id is None:
            ui.notify(t("no_dwarf_selected"), type="negative")
            return

        if has_related_dwarf_entries(self.conn, self.dwarf_id):
            ui.notify(
                "Cannot delete: this Dwarf is still linked to one or more backup entries. Please remove them first.",
                type="negative")
            return

        await self.WinLog.show(
            "Confirm Deletion",
            "Are you sure you want to delete this Dwarf?",
            self.ok_confirm_and_delete_dwarf
        )

    async def ok_confirm_and_delete_dwarf(self):
        # Delete the Dwarf
        del_dwarf(self.conn, self.dwarf_id)

        print(f"Deleted Dwarf {self.dwarf_id}.")
        self.refresh_dwarf_list()
        await self.set_new_dwarf()
        ui.notify(t("dwarf_deleted"), type="positive")

    async def confirm_and_delete_dwarf_entries(self):
        if self.dwarf_id is None:
            ui.notify(t("no_dwarf_selected"), type="negative")
            return

        await self.WinLog.show(
            "Confirm Deletion",
            "Are you sure you want to reset to defaults?",
            self.ok_confirm_and_delete_dwarf_entries
        )

    def ok_confirm_and_delete_dwarf_entries(self):
        delete_dwarf_entries_and_dwarf_data(self.conn, self.dwarf_id)
        self.dwarf_scan_date.text = ""
        ui.notify(t("dwarf_data_deleted"), type="positive")
 
    def get_explore_url(self):
        if self.dwarf_id:
            if self.FirstInit:
                mode_dwarf = "dwarf&only_on_dwarf=1"
            else:
                mode_dwarf = "dwarf"
            back_url = urllib.parse.quote(f"/Dwarf?DwarfId=", safe='')
            explore_url = f"/Explore?DwarfId={self.dwarf_id}&mode={mode_dwarf}&back_url={back_url}"
        else:
            explore_url = f"/Explore?mode=dwarf"
        print(explore_url)
        return explore_url

    async def show_local_data(self):
        if self.dwarf_id:
            self.local_info.visible = True

            local_Dwarf_dir = get_local_dwarf_dir(self.conn, self.dwarf_id)
            self.dwarf_data_size.text = get_directory_size_format(local_Dwarf_dir)

            local_Dwarf_dir_archive = os.path.join(local_Dwarf_dir, "Archive")
            self.dwarf_archive_size.text = get_directory_size_format(local_Dwarf_dir_archive)

            # Free space on the local drive
            if self.dwarf_free_size:
                info = await run.io_bound(get_disk_space_info, local_Dwarf_dir)
                if info["online"]:
                    color = "text-red-500" if info["critical"] else ("text-orange-400" if info["warning"] else "text-green-500")
                    self.dwarf_free_size.set_text(f"{info['free_str']}")
                    self.dwarf_free_size.classes(replace=f"text-base font-semibold {color}")
                else:
                    self.dwarf_free_size.set_text("—")
                    self.dwarf_free_size.classes(replace="text-base text-gray-400")

            # Disk space of the Dwarf device itself (USB only)
            if self._dwarf_usb_disk_widget:
                usb_path = self.dwarf_astroDir.value.strip() if self.dwarf_astroDir.value else None
                if usb_path and os.path.exists(usb_path) and self.dwarf_status == "USB":
                    await self._dwarf_usb_disk_widget.refresh(usb_path)
                else:
                    await self._dwarf_usb_disk_widget.refresh(None)
        else:
            self.local_info.visible = False

    async def confirm_and_delete_dwarf_archive(self):

        if self.dwarf_id is None:
            ui.notify(t("no_dwarf_selected"), type="negative")
            return

        await self.WinLog.show(
            "Confirm Deletion",
            "Are you sure you want to delete the old Dwarf archive data from your local drive?\n(These files are no longer present on your Dwarf device.)",
            self.ok_confirm_and_delete_dwarf_archive
        )

    async def ok_confirm_and_delete_dwarf_archive(self):
        # Delete the Archive
        local_Dwarf_dir = get_local_dwarf_dir(self.conn, self.dwarf_id)
        await run.io_bound(empty_local_archive_dwarf_dir, local_Dwarf_dir)
        await self.show_local_data()
        ui.notify(t("notify_archive_cleaned"), type="positive")