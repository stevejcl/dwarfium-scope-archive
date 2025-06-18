import webview
from nicegui import ui, app, run

import os
import shutil
import asyncio
import hashlib

from components.menu import menu
from api.dwarf_backup_fct_ftp import ftp_conn, check_ftp_connection, get_ftp_astroDir, list_ftp_subdirectories, ftp_path_exists, download_ftp_tree, ftp_download_file, ftp_upload_file
from api.dwarf_backup_fct import scan_backup_folder
from api.dwarf_backup_db import DB_NAME, connect_db, close_db, init_db
from api.dwarf_backup_db_api import get_dwarf_Names, get_dwarf_detail, get_backupDrive_list_dwarfId
from components.win_log import WinLog

@ui.page('/TransferFtp')
def transfer_page():

    menu("Session Transfer")

    # Launch the GUI
    TransferAppFTP(DB_NAME)
    #ui.context.client.on_disconnect(lambda: logger.removeHandler(handler))

class TransferAppFTP:
    def __init__(self, database):
        self.mode = "Archive"  # Default mode
        self.database = database
        self.dwarfs = []

        self.DwarfId = None
        self.dwarf_options = []
        self.BackupId = None
        self.backup_options = []

        self.src_dir = '' # 'G:\\Astronomy\\DWARF_RAW_WIDE_C 20_EXP_15_GAIN_80_2025-04-28-04-21-24-416'
        self.dest_dir = '' # 'T:\\DWARFLAB_2\\DATA4\\DATA_OBJECTS\\NGC7000_North_American_Nebula'
        self.src_main_dir = '' # 'G:\\Astronomy\\DWARF_RAW_WIDE_C 20_EXP_15_GAIN_80_2025-04-28-04-21-24-416'
        self.dest_main_dir = '' # 'T:\\DWARFLAB_2\\DATA4\\DATA_OBJECTS\\NGC7000_North_American_Nebula'

        self.ftp_dwarf_dir = None
        self.dwarf_ip_sta_mode = ""
        self.usb_available = False
        self.ftp_available = False
        self.build_ui()
        self.set_mode_UI()

    def set_mode_UI(self):

        if self.mode == "Archive":
            if self.transfert_mode_select.value == "FTP":
                self.SourceDirectory.set_text("Source: Dwarf Drive (FTP)")
                self.DestinationDirectory.set_text("Destination: Backup Drive")
            else:
                self.SourceDirectory.set_text("Source: Dwarf Drive")
                self.DestinationDirectory.set_text("Destination: Backup Drive")
            self.SourceMainDir = "the Dwarf directory!"
            self.DestinationMainDir = "the backup directory!"
            self.ScanningMessage = "🔍 Scanning Backup drive, please wait..."
            self.EndScanningMessage = "End of Scanning Backup drive"
            self.StartBackup.set_text("Start Backup")
            self.CancelBackup.set_text("Cancel Backup")
        else:
            if self.transfert_mode_select.value == "FTP":
                self.SourceDirectory.set_text("Source: Backup Drive")
                self.DestinationDirectory.set_text("Destination: Dwarf Drive (FTP)")
            else:
                self.SourceDirectory.set_text("Source: Backup Drive")
                self.DestinationDirectory.set_text("Destination: Dwarf Drive")
            self.SourceMainDir = "the backup directory!"
            self.DestinationMainDir = "the Dwarf directory!"
            self.ScanningMessage = "🔍 Scanning Dwarf drive, please wait..."
            self.EndScanningMessage = "End of Scanning Dwarf drive"
            self.StartBackup.set_text("Start Restore")
            self.CancelBackup.set_text("Cancel Restore")

    def switch_mode(self):
        self.mode = self.mode_toggle.value
        print(self.mode)

        input_src_value = self.input_src_dir.value
        input_src_options = self.input_src_dir.options
        src_main_dir = self.src_main_dir

        input_dest_value = self.input_dest_dir.value
        input_dest_options = self.input_dest_dir.options
        dest_main_dir = self.dest_main_dir

        self.input_src_dir.set_options(input_dest_options, value = input_dest_value)
        self.src_main_dir = dest_main_dir

        self.input_dest_dir.set_options(input_src_options, value = input_src_value)
        self.dest_main_dir = src_main_dir

        self.set_mode_UI()
        self.main_ui.update()

    def build_ui(self):
        self.conn = connect_db(self.database)

        with ui.card().classes("w-full p-4 mt-2 items-center") as self.main_ui:
            self.mode_toggle = ui.toggle(['Archive', 'Restore'], value='Archive', on_change=self.switch_mode)

            with ui.grid(columns=2):
                with ui.column():
                    ui.label("Select Dwarf:").classes("text-lg font-semibold")
                    self.dwarf_filter = ui.select(options=[], on_change=self.on_dwarf_filter_change).props('outlined')
                    self.usb_status_label = ui.label("").classes('pb-2')
                    self.ftp_spinner = ui.spinner(size="2em")
                    self.ftp_status_label = ui.label("").classes('pb-6')

                with ui.column():
                    ui.label("Backup Drive:").classes("text-lg font-semibold")
                    self.backup_filter = ui.select(options=[]).props('outlined')
                    self.backup_status_label = ui.label("").classes('pb-2')

            self.transfert_mode_select = ui.select(label="Transfer Mode",options=[], on_change=self.change_transfert_mode).props('stack-label').props('outlined').classes('w-40').classes("min-w-[200px] w-auto overflow-x-auto whitespace-nowrap")

            self.SourceDirectory = ui.label("Source: Dwarf USB Drive").classes("text-lg font-semibold")
            self.input_src_dir = ui.select(label="Source Directory:", value = self.src_dir, options=[self.src_dir], on_change=lambda: self.resize_input()).props('stack-label').props('outlined').classes('w-40').classes("min-w-[600px] w-auto overflow-x-auto whitespace-nowrap")
            ui.button("Select Source", on_click=lambda : self.select_source_folder())

        with ui.card().classes("w-full p-4 mt-1 items-center"):
            self.DestinationDirectory = ui.label("Destination: Backup Drive").classes("text-lg font-semibold")
            self.input_dest_dir = ui.select(label="Destination Directory:", value = self.dest_dir, options=[self.dest_dir], on_change=lambda: self.resize_input()).props('stack-label').props('outlined').classes('w-40').classes("min-w-[600px] w-auto overflow-x-auto whitespace-nowrap")
            ui.button("Select Destination", on_click=lambda : self.select_destination_folder())

        with ui.card().classes("w-full p-4 mt-1 mb-8 items-center"):
            self.progress_label = ui.label("Idle...")
            self.progress = ui.circular_progress(max=100, show_value=True)
            self.CancelBackup = self.cancel_btn = ui.button('Cancel Backup', on_click=lambda: self.cancel())
            self.cancel_btn.visible = False
            self.StartBackup = ui.button('Start Backup', on_click=lambda:self.start_backup())
            self.cancel_backup = False

        self.populate_dwarf_filter()
        self.notify_me(None)

    def populate_dwarf_filter(self):
        self.ftp_spinner.visible = False
        self.ftp_status_label.text = ""
        self.usb_status_label.text = ""
        self.dwarf_options = get_dwarf_Names(self.conn)
        names = [name for _, name in self.dwarf_options]
        self.dwarf_filter.set_options(names, value = names[0])

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
        else:
            self.BackupId = None
            self.backup_location = ""
            self.backup_astrodir = ""
            self.backup_path = ""
            self.backup_status_label.text = ""

            if self.mode == "Archive":
                self.input_dest_dir.set_options([], value = "")
                self.dest_main_dir = self.backup_path
            else:
                self.input_src_dir.set_options([], value = "")
                self.src_main_dir = self.backup_path

    async def on_dwarf_filter_change(self):
        print("on_dwarf_filter_change")
        self.ftp_spinner.visible = False
        self.ftp_status_label.text = ""
        self.usb_status_label.text = ""
        selected_name = self.dwarf_filter.value
        print(f"selected_name: {selected_name}")
        for did, name in self.dwarf_options:
            if name == selected_name:
                self.DwarfId = did
                break
        print(f"DwarfId: {self.DwarfId}")
        self.populate_backup_filter()
        await self.dwarf_data_update()

    async def dwarf_data_update(self):
        row = get_dwarf_detail(self.conn, self.DwarfId)
        if row:
            self.dwarf_astroDir = row[2] or ""
            self.dwarf_ip_sta_mode = row[5] or ""
            print(f"dwarf_ip_sta_mode: {self.dwarf_ip_sta_mode}")
            if self.mode == "Archive":
                self.input_src_dir.set_options([], value = "")
                self.src_main_dir = ""
            else:
                self.input_dest_dir.set_options([], value = "")
                self.dest_main_dir = ""

            await self.check_status_dwarf()

    def update_dwarf_directory(self):
        if self.mode == "Archive":
            if self.transfert_mode_select.value == "FTP" and self.dwarf_ip_sta_mode:
                self.ftp_dwarf_dir = get_ftp_astroDir(self.dwarf_ip_sta_mode)
                if self.ftp_dwarf_dir:
                    self.input_src_dir.set_options([self.ftp_dwarf_dir], value = self.ftp_dwarf_dir)
                    self.src_main_dir = self.ftp_dwarf_dir
            else:
                self.input_src_dir.set_options([self.dwarf_astroDir], value = self.dwarf_astroDir)
                self.src_main_dir = self.dwarf_astroDir
        else:
            if self.transfert_mode_select.value == "FTP" and self.dwarf_ip_sta_mode:
                self.ftp_dwarf_dir = get_ftp_astroDir(self.dwarf_ip_sta_mode)
                if self.ftp_dwarf_dir:
                    self.input_dest_dir.set_options([self.ftp_dwarf_dir], value = self.ftp_dwarf_dir)
                    self.dest_main_dir = self.ftp_dwarf_dir
            else:
                self.input_dest_dir.set_options([self.dwarf_astroDir], value = self.dwarf_astroDir)
                self.dest_main_dir = self.dwarf_astroDir

    def check_dir_dwarf(self):
        if self.dwarf_astroDir:
           if os.path.exists(self.dwarf_astroDir):
               self.usb_status_label.text = "✅ Path detected."
               self.usb_available = True
           else:
               self.usb_status_label.text = "❌ Path not detected."
               self.usb_available = False
        else:
            self.usb_status_label.text = ""
            self.usb_available = False

    async def check_status_dwarf(self):
        self.usb_available = False
        self.ftp_available = False
        self.check_dir_dwarf()
        self.update_transfert_mode()
        current_ip = self.dwarf_ip_sta_mode
        try:
            if self.dwarf_ip_sta_mode:
                self.ftp_spinner.visible = True
                status_text = await run.io_bound(check_ftp_connection, self.dwarf_ip_sta_mode)
                self.ftp_available = "Connected to" in status_text if status_text else False
        finally:
            # Update only if the IP has not changed
            if current_ip == self.dwarf_ip_sta_mode:
                self.ftp_spinner.visible = False
                self.ftp_status_label.text = status_text  # Show the result

                self.update_transfert_mode()

    def update_transfert_mode(self):
        available_modes = []
        if self.usb_available:
            available_modes.append("USB")
            print(f"available_modes USB")
        if self.ftp_available:
            available_modes.append("FTP")
            print(f"available_modes FTP")
        if not available_modes:
            available_modes = ["No connection available"]
            print(f"no available_modes")

        # Update the select options dynamically
        self.transfert_mode_select.set_options(available_modes, value=available_modes[0])
        self.update_dwarf_directory()

    def change_transfert_mode(self):
        self.update_dwarf_directory()
        self.set_mode_UI()

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
            self.input_dest_dir.set_options([self.backup_path], value = self.backup_path)
            self.dest_main_dir = self.backup_path
        else:
            self.input_src_dir.set_options([self.backup_path], value = self.backup_path)
            self.src_main_dir = self.backup_path

    def check_status_backup(self):
        if self.backup_path:
           if os.path.exists(self.backup_path):
               self.backup_status_label.text = "✅ Path detected."
           else:
               self.backup_status_label.text = "❌ Path not detected."

    def open_source_select(self):
        ui.run_javascript(f"document.querySelector('[aria-label=\"{self.input_src_dir.label}\"]').click();")

    def open_destination_select(self):
        ui.run_javascript(f"document.querySelector('[aria-label=\"{self.input_dest_dir.label}\"]').click();")

    async def select_source_folder(self):
        if self.mode == "Archive" and self.transfert_mode_select.value == "FTP" and self.dwarf_ip_sta_mode:
            subdirs = list_ftp_subdirectories(self.dwarf_ip_sta_mode)

            if subdirs:
                if self.ftp_dwarf_dir and self.ftp_dwarf_dir not in subdirs:
                    subdirs.append(self.ftp_dwarf_dir)
                self.input_src_dir.set_options(subdirs, value = self.ftp_dwarf_dir)
                self.open_source_select()

        else:

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
                self.input_src_dir.set_options([folder], value = folder)

    def resize_input(self):
        ui.run_javascript(f'''
        const input = document.querySelector('input');
        input.style.width = ((input.value.length + 1) * 8) + 'px';
        ''')

    async def select_destination_folder(self):
        if self.mode == "Restore" and self.transfert_mode_select.value == "FTP" and self.dwarf_ip_sta_mode:
            subdirs = list_ftp_subdirectories(self.dwarf_ip_sta_mode)

            if subdirs:
                if self.ftp_dwarf_dir and self.ftp_dwarf_dir not in subdirs:
                    subdirs.append(self.ftp_dwarf_dir)
                self.input_dest_dir.set_options(subdirs, value = self.ftp_dwarf_dir)
                self.open_destination_select()

        else:

            """Open folder selection dialog."""
            if self.input_dest_dir.value:
                full_path = os.path.abspath(self.dest_main_dir) # self.input_dest_dir.value
                folder = await app.native.main_window.create_file_dialog(webview.FOLDER_DIALOG, allow_multiple=False,directory=full_path)
            else:
                folder = await app.native.main_window.create_file_dialog(webview.FOLDER_DIALOG, allow_multiple=False)
        
            if folder and not folder[0].startswith(self.dest_main_dir):
                ui.notify(f"❌ Access denied: You cannot navigate outside {self.DestinationMainDir}")
            elif folder:
                ui.notify(f"✅ Selected Folder: {folder[0]}")
                folder = os.path.normpath(folder[0])
                self.input_dest_dir.set_options([folder], value = folder)

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

        if self.mode == "Restore" and self.transfert_mode_select.value == "FTP":
            self.notify_me.refresh("FTP is read-only: Restore not allowed.")
            self.progress_label.set_text("FTP is read-only.")
            return

            # FTP paths: simple string manipulation
            #src_basename = os.path.basename(os.path.normpath(src_dir))
            #dest_path = f"{dest_dir.rstrip('/')}/{src_basename}"

            # You would need to check existence via FTP
            #if ftp_path_exists(self.dwarf_ip_sta_mode, dest_path):  # Implement this check
            #    await self.confirm_overwrite(dest_path)
            #else:
            #    await self.execute_backup(src_dir, dest_path)
        else:
            self.cancel_btn.visible = True
 
            # Local USB path
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

        print ( list_files)
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

    async def get_files_old(self, src_dir, dest_dir):
        all_files = []
        for root, _, files in os.walk(src_dir):
            for file in files:
                src_path = os.path.join(root, file)
                rel_path = os.path.relpath(src_path, src_dir)
                dest_path = os.path.join(dest_dir, rel_path)
                all_files.append((src_path, dest_path))
        return all_files

    async def get_files(self, src_dir, dest_dir):
        all_files = []

        if self.transfert_mode_select.value == "FTP" and self.mode == "Archive":
            # FTP → USB
            all_files = await run.io_bound(download_ftp_tree, self.dwarf_ip_sta_mode,src_dir, dest_dir)

        elif self.transfert_mode_select.value == "FTP" and self.mode == "Restore":
            # USB → FTP : Not Possible Read Only system
            print(f"dest_dir: {dest_dir}")
            for root, _, files in os.walk(src_dir):
                for file in files:
                    src_path = os.path.join(root, file)
                    rel_path = os.path.relpath(src_path, src_dir)
                    ftp_rel_path = rel_path.replace("\\", "/")
                    dest_path = f'{dest_dir.rstrip("/")}/{ftp_rel_path}'
                    all_files.append((src_path, dest_path))

        else:
            # USB → USB
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
        result = True

        total_files = len(all_files)
        print (total_files)

        transfer_mode = self.transfert_mode_select.value
        is_archive = self.mode == "Archive"
        is_restore = self.mode == "Restore"
        use_ftp = transfer_mode == "FTP"

        # Conditional FTP connection block
        ftp = None
        ftp_ctx = ftp_conn(self.dwarf_ip_sta_mode) if use_ftp and self.dwarf_ip_sta_mode else None
        ftp = ftp_ctx.__enter__() if ftp_ctx else None
        created_dirs_cache = set()

        try:
            for i, (src_file, dest_file) in enumerate(all_files):
                if self.cancel_backup:
                    self.notify_me.refresh("Backup cancelled.")
                    result = False
                    break

                try:
                    # --- FTP ➜ LOCAL (ARCHIVE) ---
                    if use_ftp and is_archive:
                        ftp_download_file(ftp, src_file, dest_file)

                    # --- LOCAL ➜ FTP (RESTORE) ---
                    elif use_ftp and is_restore:
                        ftp_upload_file(ftp, src_file, dest_file, created_dirs_cache)

                    # --- LOCAL ➜ LOCAL ---
                    else:
                        Path(dest_file).parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src_file, dest_file)
                        if os.path.getsize(src_file) != os.path.getsize(dest_file):
                            raise Exception("Size mismatch after copy")

                        # 🔒 Step 2 (Optional): Check hash for sensitive files
                        #if os.path.splitext(src_file)[1] in ['.fits', '.json', '.jpg']:
                        #    if file_hash(src_file) != file_hash(dest_file):
                        #        ui.notify.refresh(f"Checksum mismatch: {src_file}")
                        #        break

                    verified_files += 1

                except Exception as e:
                    self.notify_me.refresh(f"❌ Error on file {src_file}: {e}")
                    result = False
                    break

                progress_bar.value = round((i + 1) / total_files * 100)

        finally:
            # Close FTP connection if it was opened
            if ftp_ctx:
                ftp_ctx.__exit__(None, None, None)      

        if not self.cancel_backup and verified_files == total_files:
            self.notify_me.refresh("✅ Backup complete and verified!")
            result = True

        elif not self.cancel_backup:
            self.notify_me.refresh("⚠️ Backup incomplete due to verification failure.")

        cancel_button.visible = False
        return result

