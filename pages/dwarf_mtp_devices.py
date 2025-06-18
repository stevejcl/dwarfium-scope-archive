import webview
from nicegui import ui, run, app

import os

from api.dwarf_backup_db import DB_NAME, connect_db, close_db, init_db
from api.dwarf_backup_db_api import device_exists_in_db, get_mtp_devices, add_mtp_device_to_db, get_dwarf_mtp_drive

from api.dwarf_backup_mtp_handler import MTPManager 

from components.menu import menu

@ui.page("/MtpDevice")
def mtp_page():

    menu("DWARF II MTP Device Manager")

    # Launch the GUI
    TransferApp(DB_NAME)

class TransferApp:
    def __init__(self, database):
        self.database = database

        self.destination_dir = "./MTP_Downloads"
        self.destination_input = {}
        self.notification_label = {}
        self.mtp = MTPManager()
        self.dwarf_select = []
        self.build_ui()

    def build_ui(self):
        if not self.mtp.is_MTP_available():
            ui.label("MTP functions are not available! Can't use this page")
            return

        self.conn = connect_db(self.database)

        with ui.card().classes("w-full p-4 mt-4 items-center"):
            ui.label("Connected MTP Devices:")
            self.dwarf_select = []
            devices = self.mtp.list_mtp_devices()
            for name, path in devices:
                print(f" device: {name}-{path}")
                is_in_db = device_exists_in_db(self.conn, path)
                with ui.row().classes("items-center"):
                    ui.label(name).classes("text-blue-600").classes('text-bold')
                    if is_in_db:
                        ui.icon("check_circle", color="green")
                        dwarf_options = get_dwarf_mtp_drive(self.conn, path)
                        print(dwarf_options)
                        if dwarf_options:
                            ui.label("Dwarf:")
                            names = [name for _, name, _ in dwarf_options]
                            self.dwarf_select.append(names[0])
                            ui.select(options=names,value=names[0]).props('outlined')
                    else:
                        ui.button("Save", on_click=lambda n=name, p=path: add_mtp_device_to_db(self.conn, n, p))

        with ui.card().classes("w-full p-4 mt-4 items-center"):
            ui.label("Destination Directory")
            self.destination_input = ui.input(placeholder="Enter Subdirectory Name", value=self.destination_dir).classes("min-w-[300px] overflow-x-auto whitespace-nowrap")
            ui.button("Select Destination", on_click=lambda : self.select_local_folder())

        with ui.card().classes("w-full p-4 mt-4 items-center"):
            ui.label("Saved MTP Devices:")
            devices = get_mtp_devices(self.conn)
            progress_bar = ui.circular_progress(max=100)
            self.notification_label = ui.label("Idle...")

            for device in devices:
                is_visible = False
                with ui.row().classes("items-center"):
                    dwarf_options = get_dwarf_mtp_drive(self.conn, device[2])
                    if dwarf_options:
                        names = [name for _, name, _ in dwarf_options]
                        # visible if connected
                        if names[0] in self.dwarf_select:
                            is_visible = True
                            ui.label(f"{device[1]}")
                            ui.select(options=names,value=names[0]).props('outlined')
                if is_visible:
                    subdirs = self.mtp.list_subdirectories(device[2])
                    if subdirs:
                        ui.label("Select Directory")
                        selected_subdir = ui.select(label="Please select", options=subdirs, on_change=lambda: self.resize_input()).props('stack-label').props('outlined').classes('w-40').classes("min-w-[300px] w-auto overflow-x-auto whitespace-nowrap")
                        progress_label = ui.label("Idle...")
                        ui.button(f"Copy from {device[1]}", on_click=lambda d=device[2], sd = selected_subdir, pb=progress_bar, pl=progress_label: self.start_copy(d, sd.value, pb, pl))
                    else:
                        ui.label("No subdirectories found in Astronomy folder.")

    def resize_input(self):
        ui.run_javascript(f'''
        const input = document.querySelector('input');
        input.style.width = ((input.value.length + 1) * 8) + 'px';
        ''')

    async def select_local_folder(self):
        """Open folder selection dialog."""
        if self.destination_input.value:
            full_path = os.path.abspath(self.destination_input.value)
            folder = await app.native.main_window.create_file_dialog(webview.FOLDER_DIALOG, allow_multiple=False,directory=full_path)
        else:
            folder = await app.native.main_window.create_file_dialog(webview.FOLDER_DIALOG, allow_multiple=False)
        if folder:
            ui.notify(folder[0])
            folder = os.path.normpath(folder[0])
            self.destination_input.value = folder


    async def start_copy(self, device_id, subdir_name, progress_bar, progress_label):

        self.destination_dir = self.destination_input.value
        if not self.destination_dir:
            progress_label.set_text("Select a destination Directory.")
            ui.notify("No destination Directory selected.", type='warning')
            return

        if not subdir_name:
            progress_label.set_text("Select a source directory.")
            ui.notify("No source Directory selected.", type='warning')
            return

        # Check if destination path exists
        destination_path = os.path.join(self.destination_dir, subdir_name)
        if os.path.exists(destination_path):
            await self.confirm_overwrite(destination_path, device_id, subdir_name, progress_bar, progress_label)
        else:
            await self.execute_backup(device_id, subdir_name, progress_bar, progress_label)

    async def confirm_overwrite(self, dest_path, device_id, subdir_name, progress_bar, progress_label):

        print("confirm_overwrite")
        ui.notify(f"The destination '{dest_path}' already exists.!", type='warning')

        # Display confirmation dialog
        with ui.dialog().props('persistent') as dialog, ui.card().style('width: 800px; max-width: none'):
            ui.label(f"The destination:\n'{dest_path}' already exists.\nAre you sure you want to continue?")
            with ui.row():
                ui.button("Yes", on_click=lambda: dialog.submit('Yes'))
                ui.button("No", on_click=lambda: dialog.submit('No'))

        result = await dialog
        if result == 'Yes':
            await self.execute_backup(device_id, subdir_name, progress_bar, progress_label)
        else:
            progress_label.set_text("Backup canceled.")

    async def execute_backup(self, device_id, subdir_name, progress_bar, progress_label):

        self.notification_label.set_text("Check Files...")

        list_files = await self.mtp.get_files_from_mtp(
            device_id,
            subdir_name,
            progress_label
        )
        total_files = 0
        if list_files:
            total_files = len(list_files)

        if total_files == 0:
            progress_label.set_text("No files to copy.")
            self.notification_label.set_text("Idle...")
            return

        self.notification_label.set_text("Starting...")
        destination_path = os.path.join(self.destination_dir, subdir_name)

        dest_folder = await self.mtp.get_folder_from_mtp(destination_path)
        ui.notify(f"Starting the copy to {os.path.abspath(destination_path)}")

        # Find the specific file 
        await run.io_bound(self.copy_files_with_progress, list_files, dest_folder, total_files, progress_bar, progress_label)
        return

    def copy_files_with_progress(self, list_files, dest_folder, total_files, progress_bar, progress_label):
        self.notification_label.set_text("Copy...")
        for i, item in enumerate(list_files):
            print(f"Copying: {item.Name}")
            self.mtp.copy_file_from_mtp(item.Name, dest_folder)
            progress = round((i + 1) / total_files * 100)
            self.update_progress(progress_bar, progress_label, progress, i + 1, total_files)

        self.notification_label.set_text("End...")

    # Function to update the UI from the main thread
    def update_progress(self, progress_bar, progress_label, progress, copied, total):
        progress_bar.value = progress
        progress_label.set_text(f"Copied {copied}/{total} files")
