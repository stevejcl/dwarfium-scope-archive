import webview
from nicegui import native, app, run, ui
import os
import re
from api.dwarf_backup_db import DB_NAME, connect_db, close_db, init_db
from api.dwarf_backup_fct import scan_backup_folder, insert_or_get_backup_drive, check_ftp_connection, connect_to_dwarf, list_mtp_devices

from api.dwarf_backup_db_api import get_dwarf_Names, get_dwarf_detail, set_dwarf_detail, add_dwarf_detail
from api.dwarf_backup_db_api import get_session_present_in_Dwarf, get_mtp_devices, get_mtp_device, set_dwarf_mtp_id, device_exists_in_db, add_mtp_device_to_db
from api.dwarf_backup_db_api import has_related_dwarf_entries, delete_dwarf_entries_and_dwarf_data, del_dwarf

from components.win_log import WinLog
from components.menu import menu, setStyle

@ui.page('/Dwarf')
def dwarf_settings():

    menu("Dwarf Configuration")

    # Launch the GUI
    ConfigApp(DB_NAME)
    #ui.context.client.on_disconnect(lambda: logger.removeHandler(handler))
    

class ConfigApp:
    def __init__(self, database):
        self.database = database
        self.dwarfs = []
        self.dwarf_id = None
        self.dwarf_type_map = {
            1: "Dwarf2",
            2: "Dwarf3"
        }
        self.show_info_ftp = True
        self.dwarf_mtp_id = None
        self.mtp_select = {}
        self.mtp_visible = False
        self.mtp_devices = []
        self.device_path = None
        self.dwarf_scan_date = None
        self.mtp_status_label = None
        self.WinLog = WinLog()
        self.build_ui()

    def build_ui(self):
        self.conn = connect_db(self.database)

        self.dwarf_type_name_to_id = {v: k for k, v in self.dwarf_type_map.items()}

        with ui.card().classes("w-full max-w-3xl mx-auto"):
            with ui.grid(columns=2):
                ui.button("Show All Current Dwarf Data", on_click=lambda: ui.navigate.to(self.get_explore_url()))
                ui.button("Analyze Dwarf Drive", on_click=self.analyze_usb_drive)

            ui.separator()

            with ui.row().classes('w-full gap-8 items-start'):
                with ui.column():
                    ui.button("➕ Add New Dwarf", on_click=self.set_new_dwarf)

                with ui.column():
                    ui.label("Select Existing Dwarf").classes("text-lg font-semibold")

                    # Dwarf Selection
                    self.dwarf_selector = ui.select(
                        options=[],
                        on_change=self.load_selected_dwarf,
                        label="Please select"
                    ).props('stack-label').props('outlined').classes('w-40')

                    with ui.grid(columns=2):
                        self.dwarf_name = ui.input("Dwarf Name")

                        with ui.row().classes("w-full  pt-4 justify-end"):
                            ui.button("🗑️ Delete Dwarf", on_click=self.confirm_and_delete_Dwarf).props("color=red")

                    self.dwarf_desc = ui.input("Description")

                    # Dwarf Type selection
                    self.dwarf_type_var = ui.select(
                        options=list(self.dwarf_type_map.values()),
                        value="Dwarf3",
                        label="Type",
                        on_change=self.modif_dwarf_type
                    ).props('stack-label').props('outlined').classes('w-40')

                    with ui.grid(columns=2):
                        self.dwarf_astroDir = ui.input("Astronomy Directory")

                        with ui.row().classes("w-full pt-4"):
                            ui.button("Select USB Folder", on_click=self.select_dwarf_folder)

                    self.usb_status_label = ui.label("").classes('pb-2')

                    with ui.grid(columns=2) as self.mtp_column:
                       self.render_mtp_section()

                    self.mtp_status_label = ui.label("").classes('pb-2')
                    self.mtp_status_label.visible = False

                    with ui.grid(columns=2):
                        self.dwarf_ip_sta_mode = ui.input("Ip Address STA Mode", validation={'Invalid IP address': lambda value: self.is_valid_ip(value)})
                        with ui.row().classes("gap-4 mt-4"):
                            self.ftp_spinner = ui.spinner(size="2em")
                            self.ftp_status_label = ui.label("").classes('pt-6')

                    with ui.card().tight():
                        ui.colors(brand='#A1A0A1')
                        ui.item_label('Last Scan on:').props('stack-label').classes('pl-3 pr-3 pt-2').classes('text-brand')
                        self.dwarf_scan_date = ui.label("").classes("pl-3 pr-3 pb-2")

                    with ui.row().classes("gap-4 mt-4"):
                         ui.button("Save / Update Dwarf", on_click=self.save_or_update_dwarf)
                         ui.button("🗑️ Delete Dwarf Entries", on_click=self.confirm_and_delete_dwarf_entries).props("color=red")

        # need this button don't change if not
        setStyle()
        self.refresh_dwarf_list()

    def is_valid_ip(self, value):
        if not value:
            return True
        if self.show_info_ftp:
            ui.notify("Enter the Dwarf IP Address , you can found it on the My Device Page on the Dwarflab App.", type="info")
            self.show_info_ftp = False
        ip_pattern = r'^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
        return re.match(ip_pattern, value) is not None

    def check_dir_dwarf(self):
        if self.dwarf_astroDir.value:
           if os.path.exists(self.dwarf_astroDir.value):
               self.usb_status_label.text = "✅ Path detected."
           else:
               self.usb_status_label.text = "❌ Path not detected."

    def refresh_dwarf_list(self):
        """Refresh the list of dwarfs and update the selection dropdown."""
        self.ftp_spinner.visible = False
        self.ftp_status_label.text = ""
        self.usb_status_label.text = ""
        self.dwarfs = get_dwarf_Names(self.conn)

        # Create a list of tuples: (id, name)
        display_names = [f"{id} - {name}" for id, name in self.dwarfs]

        # Update the select options AND set a default value if needed
        if display_names:
            if self.dwarf_id and self.dwarf_selector.value and self.dwarf_id != int(self.dwarf_selector.value.split(" - ")[0]):
                # Find the display name that matches self.dwarf_id
                selected_value = next((name for id, name in self.dwarfs if id == self.dwarf_id), None)
                selected_display = f"{self.dwarf_id} - {selected_value}" if selected_value else display_names[0]
                self.dwarf_selector.set_options(display_names, value=selected_display)
            else:
                value = self.dwarf_selector.value
                # force recharge
                self.dwarf_selector.set_options(display_names, value=None)
                self.dwarf_selector.set_options(display_names, value=value)
        else:
            self.dwarf_selector.set_options([], value=None)

        # Update the dictionary mapping
        self.dwarf_name_to_id = {f"{id} - {name}": id for id, name in self.dwarfs}

    async def check_status_dwarf(self):
        self.check_dir_dwarf()
        if not self.dwarf_ip_sta_mode.value:
            return
        try:
            self.ftp_spinner.visible = True
            status_text = await run.io_bound(check_ftp_connection, self.dwarf_ip_sta_mode.value)
        finally:
            self.ftp_spinner.visible = False
            self.ftp_status_label.text = status_text  # Show the result

    async def load_selected_dwarf(self, event):
        """Load data when a dwarf is selected from the dropdown."""
        await self.detect_mtp_devices()

        self.ftp_status_label.text = ""
        self.usb_status_label.text = ""
        value = self.dwarf_selector.value
        print(f"value {value}")
        if not value:
            return
        try:
            self.dwarf_id = int(value.split(" - ")[0])  # Extracts "1" from "1 - Dwarf3"
        except (IndexError, ValueError):
            ui.notify("Invalid dwarf selection", type="negative")
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
            await self.check_status_dwarf()


    def modif_dwarf_type(self):
        # Set mtp_visible based on the selected type
        self.mtp_visible = (self.dwarf_type_var.value == self.dwarf_type_map[1])
        print(f" MTP Visible : {self.mtp_visible}")
        self.render_mtp_section()  # Refresh MTP section

    def render_mtp_section(self):
        self.mtp_column.clear()

        if not self.mtp_visible:
            if self.mtp_status_label:
                self.refesh_mtp_status()
            return

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
                    label="MTP Device",
                    options=mtp_options,
                    value=mtp_name,
                    on_change=lambda: self.on_mtp_selected(device_map)
                ).props('stack-label').props('outlined').classes('w-40')
                with ui.row().classes("w-full pt-4"):
                    ui.button("Detect MTP Dwarf", on_click=self.detect_mtp_devices)

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

        elif self.mtp_visible:
            self.mtp_status_label.visible = True
            self.mtp_status_label.text = "❌ MTP not Connected"

        else:
            self.mtp_status_label.visible = False
            self.mtp_status_label.text = ""

    async def detect_mtp_devices(self):
        add_new = False
        self.mtp_devices = list_mtp_devices()
        print(f"detect_mtp_devices {len(self.mtp_devices)}")
        
        for name, path in self.mtp_devices:
            print(f" device: {name}-{path}")
            is_in_db = device_exists_in_db(self.conn, path)
            print(f" in db: {is_in_db}")
            if not is_in_db:
                add_new = add_mtp_device_to_db(self.conn, name, path)

        if add_new:
            self.render_mtp_section()

    async def check_status_mtp(self):
        self.check_dir_dwarf()
        if self.dwarf_ip_sta_mode.value:
            self.ftp_status_label.text = await run.io_bound(check_ftp_connection, self.dwarf_ip_sta_mode.value)

    def set_new_dwarf(self):
        """Reset the form for adding a new dwarf."""
        self.dwarf_id = None
        self.dwarf_name.value = ""
        self.dwarf_desc.value = ""
        self.dwarf_astroDir.value = ""
        self.dwarf_type_var.value = self.dwarf_type_map[2]  # Default to Dwarf3
        self.dwarf_ip_sta_mode.value = ""
        self.dwarf_scan_date.text = ""

    async def select_dwarf_folder(self):
        """Open folder selection dialog."""
        ui.notify("Please select the Astronomy directory within the mapped USB drive.", type="info")
        dwarf_location = self.dwarf_astroDir.value
        if dwarf_location:
            folder = await app.native.main_window.create_file_dialog(webview.FOLDER_DIALOG, allow_multiple=False,directory=dwarf_location)
        else:
            folder = await app.native.main_window.create_file_dialog(webview.FOLDER_DIALOG, allow_multiple=False)
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
                ui.label("Enter Dwarf IP Address:").style('font-size: 16px; margin-bottom: 10px;')
                ip_input = ui.input().style('width: 100%; margin-bottom: 20px; padding: 10px; font-size: 14px;')

                connect_button = ui.button('Connect', on_click=lambda: connect_to_dwarf(ip_input.value.strip(), status_label))

                status_label = ui.label().style('font-size: 14px; color: #FF5722; margin-top: 20px;')
                ui.button('Close', on_click=dialog.close)
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
            ui.notify("Name is required", type="negative")
            return

        if self.dwarf_id:  # Update
            set_dwarf_detail(self.conn, name, desc, usb_astronomy_dir, dtype, ip_sta_mode, mtp_id, self.dwarf_id)
            ui.notify(f"Dwarf '{name}' updated.", type="positive")
        else:  # Insert
            self.dwarf_id = add_dwarf_detail(self.conn, name, desc, usb_astronomy_dir, dtype, ip_sta_mode, mtp_id)
            ui.notify(f"Dwarf '{name}' created with ID {self.dwarf_id}", type="positive")

        self.refresh_dwarf_list()

    async def analyze_usb_drive(self):
        """Analyze the Dwarf drive and scan files."""
        if not self.dwarf_id:
            ui.notify("No Dwarf selected", type="negative")
            return

        dwarf_location = self.dwarf_astroDir.value.strip()
        if not dwarf_location:
            ui.notify("No USB location selected", type="negative")
            return

        # Dialog to block interaction and show progress
        with ui.dialog().props('persistent')  as dialog, ui.card().style('width: 800px; max-width: none'):
            ui.label("🔍 Scanning Dwarf drive, please wait...")
            ui.spinner(size="lg")
            log = ui.log(max_lines=15).classes('w-full').style('height: 250px; overflow: hidden;')

        dialog.open()  # show the dialog

        try:
            ui.notify("Starting Analysis ...")
            total, deleted = await run.io_bound (scan_backup_folder, DB_NAME, dwarf_location, None, self.dwarf_id, None,  None, log)
            ui.notify(f"✅ Analysis Complete: {total} new sessions found, {deleted} sessions deleted.", type="positive")

        except Exception as e:
            ui.notify(f"❌ Error: {str(e)}", type="negative")

        finally:
            dialog.close()  # close dialog even if error occurs
            await self.load_selected_dwarf(None)

    async def confirm_and_delete_Dwarf(self):
        if self.dwarf_id is None:
            ui.notify("No Dwarf selected", type="negative")
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

    def ok_confirm_and_delete_dwarf(self):
        # Delete the Dwarf
        del_dwarf(self.conn, self.dwarf_id)

        print(f"Deleted Dwarf {self.dwarf_id}.")
        self.refresh_dwarf_list()
        self.set_new_dwarf()
        ui.notify("Dwarf deleted.", type="positive")

    async def confirm_and_delete_dwarf_entries(self):
        if self.dwarf_id is None:
            ui.notify("No Dwarf selected", type="negative")
            return

        await self.WinLog.show(
            "Confirm Deletion",
            "Are you sure you want to reset to defaults?",
            self.ok_confirm_and_delete_dwarf_entries
        )

    def ok_confirm_and_delete_dwarf_entries(self):
        delete_dwarf_entries_and_dwarf_data(self.conn, self.dwarf_id)
        self.dwarf_scan_date.text = ""
        ui.notify("DwarfData entries deleted.", type="positive")
 
    def get_explore_url(self):
        ui.notify("Showing Dwarf Data...")  # Simulate showing data
        if self.dwarf_id:
            explore_url = f"/Explore?DwarfId={self.dwarf_id}&mode=dwarf"
        else:
            explore_url = f"/Explore?mode=dwarf"
        print(explore_url)
        return explore_url
