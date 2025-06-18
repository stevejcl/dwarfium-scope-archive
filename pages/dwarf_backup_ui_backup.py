import webview
import sqlite3
import os

from nicegui import native, app, run, ui

from api.dwarf_backup_db import DB_NAME, connect_db, close_db, init_db
from api.dwarf_backup_fct import scan_backup_folder, insert_or_get_backup_drive 

from api.dwarf_backup_db_api import get_dwarf_Names
from api.dwarf_backup_db_api import get_backupDrive_detail, set_backupDrive_detail, get_backupDrive_list, get_backupDrive_id_from_location, add_backupDrive_detail, del_backupDrive
from api.dwarf_backup_db_api import get_session_present_in_backupDrive
from api.dwarf_backup_db_api import has_related_backup_entries, delete_backup_entries_and_dwarf_data

from components.win_log import WinLog
from components.menu import menu, setStyle

@ui.page('/Backup')
def backup_settings():

    menu("Backup Backup Configuration")

    # Launch the GUI
    ConfigApp(DB_NAME)
    #ui.context.client.on_disconnect(lambda: logger.removeHandler(handler))

class ConfigApp:
    def __init__(self, database):
        self.database = database
        self.dwarfs = []

        self.dwarf_id = None
        self.backupDrives = []
        self.backupDrive_id = None
        self.backup_scan_date = None

        self.WinLog = WinLog()
        self.build_ui()

    def build_ui(self):
        self.conn = connect_db(self.database)

        with ui.card().classes("w-full max-w-3xl mx-auto"):
            with ui.grid(columns=2):
                ui.button("Show All Current Backup Data", on_click=lambda: ui.navigate.to(self.get_explore_url()))
                ui.button("Analyze Current Drive", on_click=self.analyze_drive)

            ui.separator()

            with ui.row().classes('w-full gap-8 items-start'):
                with ui.column():
                    ui.button("Add New BackupDrive", on_click=self.set_new_BackupDrive)

                with ui.column():
                    ui.label("Select Existing BackupDrive").classes("text-lg font-semibold")

                    # BackupDrive Selection
                    self.backupDrive_selector = ui.select(
                        options=[],
                        on_change=self.load_selected_backupDrive,
                        label="Please select"
                    ).props('stack-label').props('outlined').classes('w-40')

                    with ui.grid(columns=2).classes("items-center gap-4"):
                        self.backupDrive_name = ui.input("Backup Drive Name")

                        with ui.row().classes("w-full items-center"):
                            ui.button("🗑️ Delete Backup Drive", on_click=self.confirm_and_delete_BackupDrive).props("color=red")
 
                    self.backupDrive_desc = ui.input("Drive Description")

                    with ui.grid(columns='auto 1fr').classes("items-center gap-4"):
                        self.backupDrive_location = ui.input("Location")

                        with ui.row().classes("w-full items-center"):
                            ui.button("Select Folder", on_click=self.select_folder)

                    with ui.grid(columns='auto 1fr').classes("items-center gap-4"):
                        self.backupDrive_astroDir = ui.input("Astronomy Directory") or ""

                        with ui.row().classes("w-full items-center"):
                            ui.button("Select Sub Folder", on_click=self.select_subfolder)

                    # Dwarf selection
                    self.dwarf_list = get_dwarf_Names(self.conn)
                    self.dwarf_name_to_id = {name: id_ for id_, name in self.dwarf_list}
                    self.dwarf_id_to_name = {id_: name for id_, name in self.dwarf_list}

                    self.dwarf_selector = ui.select(
                        options=list(self.dwarf_name_to_id.keys()),
                        label="Select Dwarf"
                    ).props('stack-label').props('outlined').classes('w-40')

                    with ui.card().tight():
                        ui.colors(brand='#A1A0A1')
                        ui.item_label('Last Scan on:').props('stack-label').classes('pl-3 pr-3 pt-2').classes('text-brand')
                        self.backup_scan_date = ui.label("").classes("pl-3 pr-3 pb-2")

                    with ui.row().classes("gap-4 mt-4"):
                         ui.button("Save / Update Backup Drive", on_click=self.save_or_update_backup_drive)
                         ui.button("🗑️ Delete Backup Entries", on_click=self.confirm_and_delete_entries).props("color=red")

        # need this button don't change if not
        setStyle()
        self.refresh_backupDrive_list()

    def refresh_backupDrive_list(self):
        self.backupDrives = get_backupDrive_list(self.conn)

        # Create a list of tuples: (id, name)
        options = [f"{id} - {name}" for id, name, description, location, astroDir, dwarf_id, last_backup_scan_date in self.backupDrives]

        self.backupDrive_selector.set_options(options)
        self.backupDrive_map = {
            f"{id} - {name}": (id, location)
            for id, name, _, location, _, _, _ in self.backupDrives
        }

        # Update the select options AND set a default value if needed
        if options:
            selected_id = None
            try:
                if self.backupDrive_selector.value:
                    selected_id = int(str(self.backupDrive_selector.value).split(" - ")[0])
            except (ValueError, IndexError):
                selected_id = None

            if self.backupDrive_id and selected_id != self.backupDrive_id:
                selected_value = next((name for id, name, *_ in self.backupDrives if id == self.backupDrive_id), None)
                selected_display = f"{self.backupDrive_id} - {selected_value}" if selected_value else options[0]
                self.backupDrive_selector.set_options(options, value=selected_display)
            else:
                self.backupDrive_selector.set_options(options)
        else:
            self.backupDrive_selector.set_options([], value=None)

    def load_selected_backupDrive(self, _):
        value = self.backupDrive_selector.value
        if not value:
            return
        if value in self.backupDrive_map:
            self.backupDrive_id, path = self.backupDrive_map[value]
        else:
            ui.notify("Invalid backup Drive selection.", type="negative")
            return

        row = get_backupDrive_detail(self.conn, self.backupDrive_id)

        if row:
            self.backupDrive_name.value = row[0]
            self.backupDrive_desc.value = row[1]
            self.backupDrive_location.value = row[2]
            self.backupDrive_astroDir.value = row[3]
            self.dwarf_selector.value = row[4]
            self.backup_scan_date.text = row[5]

    def set_new_BackupDrive(self):
        self.backupDrive_id = None
        self.backupDrive_name.value = ""
        self.backupDrive_desc.value = ""
        self.backupDrive_location.value = ""
        self.backupDrive_astroDir.value = ""
        self.backup_scan_date.text = ""
        if self.dwarfs:
            self.backupDrive_dwarf.value = self.dwarfs[0][1]

    async def select_folder(self):
        ui.notify("Please choose the main backup directory for your Dwarf astrophotography images or dark files.", type="info")
        location = self.backupDrive_location.value
        if location:
            folder = await app.native.main_window.create_file_dialog(webview.FOLDER_DIALOG, allow_multiple=False,directory=location)
        else:
            folder = await app.native.main_window.create_file_dialog(webview.FOLDER_DIALOG, allow_multiple=False)
        if folder:
            ui.notify(folder[0])
            folder = os.path.normpath(folder[0])
            self.backupDrive_location.value = folder

    async def select_subfolder(self, location_entry):
        ui.notify("You can select a specific subfolder where your astrophotography session images are stored.", type="info")
        location = self.backupDrive_location.value
        if not location:
            ui.notify("Fill Location first.", type="negative")
            return

        base_path = os.path.normpath(location)
        subfolder = await app.native.main_window.create_file_dialog(webview.FOLDER_DIALOG, allow_multiple=False,directory=base_path)

        if subfolder:
            ui.notify(subfolder[0])
            subfolder = os.path.normpath(subfolder[0])

            if subfolder and subfolder.startswith(location):
                # Get relative path
                astroDir = os.path.relpath(subfolder, location)
                self.backupDrive_astroDir.value = astroDir
            elif subfolder:
                ui.notify("Selected folder is not inside the Location folder.", type="negative")

    def get_selected_dwarf_id(self):
        print(f"selector: {self.dwarf_selector.value}")
        selected_name = self.dwarf_selector.value
        print(f"id: {self.dwarf_name_to_id.get(selected_name)}")
        return self.dwarf_name_to_id.get(selected_name)

    async def save_or_update_backup_drive(self):
        name = self.backupDrive_name.value
        desc = self.backupDrive_desc.value
        location = self.backupDrive_location.value
        astroDir = self.backupDrive_astroDir.value
        dwarf_id = self.get_selected_dwarf_id()

        if not (name and location and dwarf_id):
            ui.notify("Fill all fields and save a Dwarf first.", type="negative")
            return

        existing = get_backupDrive_id_from_location(self.conn, location)

        if existing:
            # Ask user for confirmation before updating
            await self.WinLog.show(
                 "Confirm Update",
                 "This location already exists. Do you want to update its data?",
                 self.ok_confirm_and_update_backup_data
            )
        else:
            try:
                self.backupDrive_id = add_backupDrive_detail(self.conn, name, desc, location, astroDir, dwarf_id)
                self.refresh_backupDrive_list()
                ui.notify("Backup drive saved.", type="positive")
            except sqlite3.IntegrityError:
                ui.notify("This folder is already registered.", type="negative")

    def ok_confirm_and_update_backup_data(self):
        name = self.backupDrive_name.value
        desc = self.backupDrive_desc.value
        location = self.backupDrive_location.value
        astroDir = self.backupDrive_astroDir.value or ""
        dwarf_id = self.get_selected_dwarf_id()

        set_backupDrive_detail(self.conn, name, desc, astroDir, dwarf_id, location)
        self.refresh_backupDrive_list()
        ui.notify("BackupDrive info updated.", type="positive")

    def save_backup_drive(self):
        name = self.backupDrive_name.value
        desc = self.backupDrive_desc.value
        location = self.backupDrive_location.value
        astroDir = self.backupDrive_astroDir.value
        dwarf_id = self.get_selected_dwarf_id()

        if not (name and location and dwarf_id):
            ui.notify("Fill all fields and save a Dwarf first.", type="negative")
            return

        cursor = self.conn.cursor()
        try:
            add_backupDrive_detail(self.conn, name, desc, location, astroDir, dwarf_id)
            self.refresh_backupDrive_list()
            ui.notify("Backup drive saved.", type="positive")
        except sqlite3.IntegrityError:
            ui.notify("This folder is already registered.", type="negative")

    def update_backup_drive(self):
        location = self.backupDrive_location.value
        name = self.backupDrive_name.value
        desc = self.backupDrive_desc.value
        astroDir = self.backupDrive_astroDir.value
        dwarf_id = self.get_selected_dwarf_id()

        if not location:
            ui.notify("No location selected.", type="negative")
            return

        existing = get_backupDrive_id_from_location(self.conn, location)
        if not existing:
            ui.notify("No BackupDrive registered at this location.", type="negative")
            return

        set_backupDrive_detail(self.conn, name, desc, astroDir, dwarf_id, location)
        self.refresh_backupDrive_list()
        ui.notify("BackupDrive info updated", type="positive")

    async def analyze_drive(self):
        location = self.backupDrive_location.value
        if not location:
            ui.notify("No location selected.", type="negative")
            return
        try:
            astroDir = self.backupDrive_astroDir.value or ""
            backup_drive_id, dwarf_id = insert_or_get_backup_drive(self.conn, location)

            # Dialog to block interaction and show progress
            with ui.dialog().props('persistent')  as dialog, ui.card().style('width: 800px; max-width: none'):
                ui.label(f"🔍 Scanning: {location}-{astroDir}, please wait...")
                ui.spinner(size="lg")
                log = ui.log(max_lines=20).classes('w-full').style('height: 400px; overflow: hidden;')

            dialog.open()  # show the dialog

            ui.notify(f"🔍 Scanning: {location}-{astroDir}")
            total, deleted = await run.io_bound (scan_backup_folder,DB_NAME, location, astroDir, dwarf_id, backup_drive_id, None, log)
            ui.notify(f"✅ Analysis Complete: {total} new sessions found, {deleted} sessions deleted.", type="positive")

        except Exception as e:
            ui.notify(f"❌ Error: {str(e)}", type="negative")

        finally:
            dialog.close()  # close dialog even if error occurs
            self.load_selected_backupDrive(None)

    async def confirm_and_delete_BackupDrive(self):
        if self.backupDrive_id is None:
            ui.notify("No Backup Drive selected", type="negative")
            return

        if has_related_backup_entries(self.conn, self.backupDrive_id):
            ui.notify(
                "This Backup Drive is still in use by one or more backup entries. Please remove them first.",
                type="negative")
            return

        await self.WinLog.show(
            "Confirm Deletion",
            "Are you sure you want to delete this Backup Drive?",
            self.ok_confirm_and_delete_backup_drive
        )

    def ok_confirm_and_delete_backup_drive(self):
        # Delete the BackupDrive
        del_backupDrive(self.conn, self.backupDrive_id)

        print(f"Deleted BackupDrive {self.backupDrive_id}.")
        self.refresh_backupDrive_list()
        self.set_new_BackupDrive()
        ui.notify("BackupDrive deleted.", type="positive")

    async def confirm_and_delete_entries(self):
        if self.backupDrive_id is None:
            ui.notify("No Backup Drive selected", type="negative")
            return

        await self.WinLog.show(
            "Confirm Deletion",
            "This will delete all backup entries and associated DwarfData for the selected BackupDrive.\nAre you sure?",
            self.ok_confirm_and_delete_backup_entries
        )

    def ok_confirm_and_delete_backup_entries(self):
        delete_backup_entries_and_dwarf_data(self.conn, self.backupDrive_id)
        self.backup_scan_date.text = ""
        ui.notify("Backup entries and DwarfData deleted.", type="positive")

    def get_explore_url(self):
        ui.notify("Showing Backup Data...")  # Simulate showing data
        if self.backupDrive_id is None:
            explore_url = f"/Explore?mode=backup"
        else:
            explore_url = f"/Explore?BackupDriveId={self.backupDrive_id}&mode=backup"
        return explore_url
