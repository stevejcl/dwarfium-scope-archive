import webview
from nicegui import ui, app, run

import os
import shutil
import asyncio
import hashlib

from components.menu import menu
from api.dwarf_backup_fct import scan_backup_folder
from api.dwarf_backup_db import DB_NAME, connect_db, close_db, init_db
from api.dwarf_backup_db_api import get_dwarf_Names, get_dwarf_detail, get_backupDrive_list_dwarfId
from components.win_log import WinLog

@ui.page('/Transfer/')
def transfer_page(DwarfId:int = None, session:str = None, mode:str = 'Archive'):

    menu("Session Transfer")

    # Launch the GUI
    ui.context.transfert_app =  TransferApp(DB_NAME, DwarfId=DwarfId, Session=session, Mode=mode)
    #ui.context.client.on_disconnect(lambda: logger.removeHandler(handler))

class TransferApp:
    def __init__(self, database, DwarfId=None, Session=None, Mode="Archive"):
        self.mode = Mode # "Archive"  Default mode
        self.database = database
        self.dwarfs = []

        self.DwarfId = DwarfId
        self.dwarf_options = []
        self.BackupId = None
        self.backup_options = []

        self.DwarfId_Init = DwarfId
        self.session = Session

        self.src_dir = '' # 'G:\\Astronomy\\DWARF_RAW_WIDE_C 20_EXP_15_GAIN_80_2025-04-28-04-21-24-416'
        self.dest_dir = '' # 'T:\\DWARFLAB_2\\DATA4\\DATA_OBJECTS\\NGC7000_North_American_Nebula'
        self.src_main_dir = '' # 'G:\\Astronomy\\DWARF_RAW_WIDE_C 20_EXP_15_GAIN_80_2025-04-28-04-21-24-416'
        self.dest_main_dir = '' # 'T:\\DWARFLAB_2\\DATA4\\DATA_OBJECTS\\NGC7000_North_American_Nebula'

        self.build_ui()
        self.set_mode_UI()

    def set_mode_UI(self):

        if self.mode == "Archive":
            self.SourceDirectory.set_text("Source: Dwarf USB Drive")
            self.DestinationDirectory.set_text("Destination: Backup Drive")
            self.SourceMainDir = "the Dwarf directory!"
            self.DestinationMainDir = "the backup directory!"
            self.ScanningMessage = "🔍 Scanning Backup drive, please wait..."
            self.EndScanningMessage = "End of Scanning Backup drive"
        else:
            self.SourceDirectory.set_text("Source: Backup Drive")
            self.DestinationDirectory.set_text("Destination: Dwarf USB Drive")
            self.SourceMainDir = "the backup directory!"
            self.DestinationMainDir = "the Dwarf directory!"
            self.ScanningMessage = "🔍 Scanning Dwarf drive, please wait..."
            self.EndScanningMessage = "End of Scanning Dwarf drive"

    def switch_mode(self):
        self.mode = self.mode_toggle.value
        print(self.mode)

        input_src_value = self.input_src_dir.value
        input_dest_value = self.input_dest_dir.value

        self.input_src_dir.value = input_dest_value
        self.src_main_dir = input_dest_value

        self.input_dest_dir.value = input_src_value
        self.dest_main_dir = input_src_value

        self.set_mode_UI()
        self.main_ui.update()

    def build_ui(self):
        self.conn = connect_db(self.database)

        with ui.card().classes("w-full p-4 mt-4 items-center") as self.main_ui:
            self.mode_toggle = ui.toggle(['Archive', 'Restore'], value='Archive', on_change=self.switch_mode)

            with ui.grid(columns=2):
                with ui.column():
                    ui.label("Select Dwarf:").classes("text-lg font-semibold")
                    self.dwarf_filter = ui.select(options=[], on_change=self.on_dwarf_filter_change).props('outlined')
                    self.usb_status_label = ui.label("").classes('pb-2')

                with ui.column():
                    ui.label("Backup Drive:").classes("text-lg font-semibold")
                    self.backup_filter = ui.select(options=[], on_change=self.on_backup_filter_change).props('outlined')
                    self.backup_status_label = ui.label("").classes('pb-2')

            self.SourceDirectory = ui.label("Source: Dwarf USB Drive")
            self.input_src_dir = ui.input("Source Directory:", value = self.src_dir).classes("min-w-[600px] overflow-x-auto whitespace-nowrap")
            ui.button("Select Source", on_click=lambda : self.select_source_folder())

        with ui.card().classes("w-full p-4 mt-4 items-center"):
            self.DestinationDirectory = ui.label("Destination: Backup Drive")
            self.input_dest_dir = ui.input("Destination Directory:", value = self.dest_dir).classes("min-w-[600px] overflow-x-auto whitespace-nowrap")
            ui.button("Select Destination", on_click=lambda : self.select_destination_folder())

        with ui.card().classes("w-full p-4 mt-4 items-center"):
            self.progress_label = ui.label("Idle...")
            self.progress = ui.circular_progress(max=100, show_value=True)
            self.cancel_btn = ui.button('Cancel Backup', on_click=lambda: self.cancel())
            self.cancel_btn.visible = False
            ui.button('Start Backup', on_click=lambda:self.start_backup())
            self.cancel_backup = False

        self.populate_dwarf_filter()
        self.notify_me(None)

    def populate_dwarf_filter(self):
        self.dwarf_options = get_dwarf_Names(self.conn)
        names = [name for _, name in self.dwarf_options]

        # Set initial value
        initial_value = names[0] if names else None

        # If self.DwarfId is set, try to find corresponding name
        if self.DwarfId:
            match = next((name for did, name in self.dwarf_options if did == self.DwarfId), None)
            if match:
                initial_value = match

        self.dwarf_filter.set_options(names, value=initial_value)

    def populate_backup_filter(self):
        print(f"populate_backup_filter (DwarfId) : {self.DwarfId}")
        if self.DwarfId:
            self.backup_options = get_backupDrive_list_dwarfId(self.conn, self.DwarfId)
            self.backup_data = {
                backup[1]: (backup[0], backup[3], backup[4]) for backup in self.backup_options
            }
            names = list(self.backup_data.keys())
        else:
            names = []
            self.backup_data = {}  # Clear if no options

        print(names)
        
        # Set initial value
        initial_value = names[0] if names else None
        self.backup_filter.set_options(names, value=initial_value)
        
        # Set initial backup location and astrodir if available
        if initial_value:
            self.update_backup_details(initial_value)

    def on_backup_filter_change(self):
        print("on_backup_filter_change")
        selected_name = self.backup_filter.value
        for bid, name, *_ in self.backup_options:
            if name == selected_name:
                self.BackupDriveId = bid
                break
        self.update_backup_details(selected_name)

    def on_dwarf_filter_change(self):
        print("on_dwarf_filter_change")
        selected_name = self.dwarf_filter.value
        print(f"selected_name: {selected_name}")
        for did, name in self.dwarf_options:
            if name == selected_name:
                self.DwarfId = did
                break
        print(f"DwarfId: {self.DwarfId}")
        self.populate_backup_filter()
        self.dwarf_data_update()

    def dwarf_data_update(self):
        row = get_dwarf_detail(self.conn, self.DwarfId)
        if row:
            self.dwarf_astroDir = row[2] or ""
            if self.mode == "Archive":
                if self.DwarfId_Init == self.DwarfId and self.session:
                    self.input_src_dir.value = os.path.join(self.dwarf_astroDir, self.session)
                else:
                    self.input_src_dir.value = self.dwarf_astroDir
                self.src_main_dir = self.dwarf_astroDir
            else:
                self.input_dest_dir.value = self.dwarf_astroDir
                self.dest_main_dir = self.dwarf_astroDir
            self.check_status_dwarf()

    def check_status_dwarf(self):
        if self.dwarf_astroDir:
           if os.path.exists(self.dwarf_astroDir):
               self.usb_status_label.text = "✅ Path detected."
           else:
               self.usb_status_label.text = "❌ Path not detected."
        else:
            self.usb_status_label.text = ""

    def update_backup_details(self, selected_name):
        if selected_name in self.backup_data:
            self.BackupId, self.backup_location, self.backup_astrodir = self.backup_data[selected_name]
            self.backup_path = os.path.join(self.backup_location, self.backup_astrodir)
            print(f"Backup ID: {self.BackupId}, Backup Location: {self.backup_location}, Astro Directory: {self.backup_astrodir}")
            self.check_status_backup()
        else:
            self.BackupId = None
            self.backup_location = ""
            self.backup_astrodir = ""
            self.backup_path = ""
            self.backup_status_label.text = ""

        if self.mode == "Archive":
            self.input_dest_dir.value = self.backup_path
            self.dest_main_dir = self.backup_path
        else:
            self.input_src_dir.value = self.backup_path
            self.src_main_dir = self.backup_path

    def check_status_backup(self):
        if self.backup_path:
           if os.path.exists(self.backup_path):
               self.backup_status_label.text = "✅ Path detected."
           else:
               self.backup_status_label.text = "❌ Path not detected."

    async def select_source_folder(self):
        """Open folder selection dialog."""
        if self.input_src_dir.value:
            full_path = os.path.abspath(self.input_src_dir.value)
            folder = await app.native.main_window.create_file_dialog(webview.FOLDER_DIALOG, allow_multiple=False,directory=full_path)
        else:
            folder = await app.native.main_window.create_file_dialog(webview.FOLDER_DIALOG, allow_multiple=False)
        if folder and not folder[0].startswith(self.src_main_dir):
            ui.notify(f"❌ Access denied: You cannot navigate outside {self.SourceMainDir}")
        elif folder:
            ui.notify(folder[0])
            folder = os.path.normpath(folder[0])
            self.input_src_dir.value = folder

    async def select_destination_folder(self):
        """Open folder selection dialog."""
        if self.input_dest_dir.value:
            full_path = os.path.abspath(self.input_dest_dir.value)
            folder = await app.native.main_window.create_file_dialog(webview.FOLDER_DIALOG, allow_multiple=False,directory=full_path)
        else:
            folder = await app.native.main_window.create_file_dialog(webview.FOLDER_DIALOG, allow_multiple=False)
        
        if folder and not folder[0].startswith(self.dest_main_dir):
            ui.notify(f"❌ Access denied: You cannot navigate outside {self.DestinationMainDir}")
        elif folder:
            ui.notify(f"✅ Selected Folder: {folder[0]}")
            folder = os.path.normpath(folder[0])
            self.input_dest_dir.value = folder

    async def start_backup(self):
        self.progress.value = 0
        src_dir = self.input_src_dir.value
        dest_dir = self.input_dest_dir.value
        if not src_dir:
            self.progress_label.set_text("Select a Source Directory.")
            return
        if not dest_dir:
            self.progress_label.set_text("Select a Destination Directory.")
            return

        self.cancel_btn.visible = True
        dest_path = os.path.join(dest_dir, os.path.basename(src_dir))

        # Check if destination path exists
        if os.path.exists(dest_path):
            await self.confirm_overwrite(dest_path)
        else:
            await self.execute_backup(src_dir, dest_path)

    async def confirm_overwrite(self, dest_path):

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
            await self.execute_backup(self.input_src_dir.value, dest_path)
        else:
            self.progress_label.set_text("Backup canceled.")
            self.cancel_btn.visible = False

    async def execute_backup(self, src_dir, dest_path):

        list_files = await self.get_files(src_dir, dest_path)
        total_files = 0
        if list_files:
            total_files = len(list_files)

        if total_files == 0:
            self.progress_label.set_text("No files to copy.")
            return
        else:
            self.progress_label.set_text(f"Starting copying {total_files} files...")
        ui.notify("Starting...")

        result = await run.io_bound(self.copy_with_progress_async, list_files, self.progress, self.cancel_btn)

        if result:
            self.progress_label.set_text(f"End of Backup")
            ui.notify("✅ Backup complete and verified!")

            with ui.dialog().props('persistent')  as dialog, ui.card().style('width: 800px; max-width: none'):
                label = ui.label(self.ScanningMessage)
                spinner = ui.spinner(size="lg")
                log = ui.log(max_lines=15).classes('w-full').style('height: 250px; overflow: hidden;')
                ui.button('Close', on_click=dialog.close)
            dialog.open()  # show the dialog

            try:
                ui.notify("Starting Analysis ...")
                if self.mode == "Archive":
                    total_dwarf, deleted_dwarf = await run.io_bound (scan_backup_folder, DB_NAME, self.dwarf_astroDir, None, self.DwarfId, None, src_dir, log)
                    total_backup, deleted_backup = await run.io_bound (scan_backup_folder, DB_NAME, self.backup_location, self.backup_astrodir, self.DwarfId, self.BackupId, dest_path, log)
                else:
                    total_backup, deleted_backup = await run.io_bound (scan_backup_folder, DB_NAME, self.backup_location, self.backup_astrodir, self.DwarfId, self.BackupId, src_dir, log)
                    total_dwarf, deleted_dwarf = await run.io_bound (scan_backup_folder, DB_NAME, self.dwarf_astroDir, None, self.DwarfId, None, dest_path, log)
                spinner.visible = False
                label.text = self.EndScanningMessage
                ui.notify(f"✅ Analysis Complete: {total_dwarf} new sessions found on dwarf.", type="positive")
                ui.notify(f"✅ Analysis Complete: {total_backup} new sessions found on backup.", type="positive")

            except Exception as e:
                ui.notify(f"❌ Error: {str(e)}", type="negative")
        else:
            self.progress_label.set_text(f"Backup interrupted!")

    @ui.refreshable
    def notify_me(self, msg: str | None) -> None:
        if msg:
            ui.notify(msg)

    def cancel(self):
        self.cancel_backup = True

    async def get_files(self, src_dir, dest_dir):
        all_files = []
        for root, _, files in os.walk(src_dir):
            for file in files:
                src_path = os.path.join(root, file)
                rel_path = os.path.relpath(src_path, src_dir)
                dest_path = os.path.join(dest_dir, rel_path)
                all_files.append((src_path, dest_path))
        return all_files

    # Optional: compute a SHA256 hash for data integrity
    def file_hash(self, path):
        hash = hashlib.sha256()
        with open(path, 'rb') as f:
            while chunk := f.read(8192):
               hash.update(chunk)
        return hash.hexdigest()

    def copy_with_progress_async(self, all_files, progress_bar, cancel_button):
        self.cancel_backup = False
        verified_files = 0
        result = False

        total_files = len(all_files)
        print (total_files)
        for i, (src_file, dest_file) in enumerate(all_files):
            if self.cancel_backup:
                self.notify_me.refresh("Backup cancelled.")
                break

            progress = round((i + 1) / total_files * 100)

            os.makedirs(os.path.dirname(dest_file), exist_ok=True)
            shutil.copy2(src_file, dest_file)

            # 🔎 Step 1: Size check
            if os.path.getsize(src_file) != os.path.getsize(dest_file):
                self.notify_me.refresh(f"Size mismatch: {src_file}")
                break

            # 🔒 Step 2 (Optional): Check hash for sensitive files
            #if os.path.splitext(src_file)[1] in ['.fits', '.json', '.jpg']:
            #    if file_hash(src_file) != file_hash(dest_file):
            #        ui.notify.refresh(f"Checksum mismatch: {src_file}")
            #        break

            verified_files += 1
            progress_bar.value = round(progress)

        if not self.cancel_backup and verified_files == total_files:
            self.notify_me.refresh("✅ Backup complete and verified!")
            result = True

        elif not self.cancel_backup:
            self.notify_me.refresh("⚠️ Backup incomplete due to verification failure.")

        cancel_button.visible = False
        return result

