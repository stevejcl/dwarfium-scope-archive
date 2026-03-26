import webview
from nicegui import ui, app, run, Client

import os
import shutil
import asyncio
import hashlib
import traceback
from pathlib import Path

from components.menu import menu
from api.dwarf_backup_fct_ftp import ftp_conn, check_ftp_connection, get_ftp_astroDir, list_ftp_subdirectories, ftp_path_exists, download_ftp_tree, ftp_download_file
from api.dwarf_backup_fct_sftp import asyncssh_sftp_session, async_sftp_upload, sftp_clean_subdir_files
from api.dwarf_backup_fct import scan_backup_folder, win_long_path, sync_dwarf_sessions, create_local_dwarf_dir, get_local_dwarf_dir

from api.dwarf_backup_db import DB_NAME, connect_db, close_db
from api.dwarf_backup_db_api import get_dwarf_Names, get_dwarf_detail, get_backupDrive_list_dwarfId
from components.win_log import WinLog

@ui.page('/Transfer')
async def transfer_page(
    client: Client,
    DwarfId: int = None,
    session: str = None,
    mode: str = 'Archive',
    BackupId: int = None,
    back_url: str = None,
    src_override: str = None,   # pre-filled source dir (e.g. repaired Mosaic temp dir)
    src_root: str = None,       # browsing constraint root (must be inside backup dir)
):
    menu("Session Transfer")
    await ui.context.client.connected()
    # Launch the GUI
    ui.context.transfert_app = TransferApp(
        client,
        DB_NAME,
        DwarfId=DwarfId,
        Session=session,
        Mode=mode,
        BackupId=BackupId,
        BackUrl=back_url,
        SrcOverride=src_override,
        SrcRoot=src_root,
    )
    #ui.context.client.on_disconnect(lambda: logger.removeHandler(handler))

class TransferApp:
    def __init__(self, client: Client, database, DwarfId=None, Session=None, Mode="Archive", BackupId=None, BackUrl=None, SrcOverride=None, SrcRoot=None):
        self.client = client
        self.mode = Mode  # "Archive" | "Restore" | "Repair" | "Merge"
        self.database = database
        self.dwarfs = []

        self.DwarfId = DwarfId
        self.dwarf_options = []
        self.BackupId = BackupId
        self.backup_options = []

        self.DwarfId_Init = DwarfId
        self.BackupId_Init = BackupId
        self.session = Session
        self.BackUrl = BackUrl

        # Repair mode: pre-filled source and browsing constraint
        self.src_override = SrcOverride  # e.g. "D:\Backup\temp_mosaic\SESSION_NAME"
        self.src_root     = SrcRoot      # e.g. "D:\Backup" — folder picker stays inside here

        self.src_dir = '' # 'G:\\Astronomy\\DWARF_RAW_WIDE_C 20_EXP_15_GAIN_80_2025-04-28-04-21-24-416'
        self.dest_dir = '' # 'T:\\DWARFLAB_2\\DATA4\\DATA_OBJECTS\\NGC7000_North_American_Nebula'
        self.src_main_dir = '' # 'G:\\Astronomy\\DWARF_RAW_WIDE_C 20_EXP_15_GAIN_80_2025-04-28-04-21-24-416'
        self.dest_main_dir = '' # 'T:\\DWARFLAB_2\\DATA4\\DATA_OBJECTS\\NGC7000_North_American_Nebula'

        self.ftp_dwarf_dir = None
        self.dwarf_ip_sta_mode = ""
        self.dwarf_type = None
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

        elif self.mode == "Repair" or self.mode == "Merge":
            # Repair: copy from temp/repaired dir → back to Dwarf (USB or FTP)
            if self.mode == "Repair":
                self.SourceDirectory.set_text("Source: Repaired Mosaic Temp Directory")
            else:
                self.SourceDirectory.set_text("Source: Merged Mosaic Temp Directory")
            if self.transfert_mode_select.value == "FTP":
                self.DestinationDirectory.set_text("Destination: Dwarf Drive (FTP)")
            else:
                self.DestinationDirectory.set_text("Destination: Dwarf Drive")
            self.SourceMainDir = self.src_root or "the backup directory!"
            self.DestinationMainDir = "the Dwarf directory!"
            self.ScanningMessage = "🔍 Scanning Dwarf drive, please wait..."
            self.EndScanningMessage = "End of Scanning Dwarf drive"
            if self.mode == "Repair":
                self.StartBackup.set_text("Start Repair Mosaic Transfer")
            else:
                self.StartBackup.set_text("Start Merge Mosaic Transfer")
            self.CancelBackup.set_text("Cancel Transfer")

        else:  # Restore
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
        if self.mode == "Repair" or self.mode == "Merge":
            return  # Repair / Merge mode direction is fixed, toggle is hidden
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
        nbcol = 3 if self.BackUrl else 1

        with ui.card().classes("w-full p-4 mt-2 items-center") as self.main_ui:
            with ui.grid(columns=nbcol).classes("items-center"):
                if self.BackUrl:
                    ui.button("🔙 Back", on_click=lambda: ui.navigate.to(self.get_explore_url())).classes("justify-self-start")
                # In Repair / Merge mode the direction is fixed — hide the Archive/Restore toggle
                if self.mode != "Repair" and self.mode != "Merge" :
                    self.mode_toggle = ui.toggle(['Archive', 'Restore'], value=self.mode, on_change=self.switch_mode).classes("col-span-1 justify-self-center")
                elif self.mode == "Repair":
                    self.mode_toggle = None
                    ui.label("🔧 Repair Transfer (Temp → Dwarf)").classes("col-span-1 justify-self-center text-base font-semibold text-orange-600")
                else:
                    self.mode_toggle = None
                    ui.label("🔧 Merge Transfer (Temp → Dwarf)").classes("col-span-1 justify-self-center text-base font-semibold text-orange-600")

            with ui.grid(columns=2):
                with ui.column():
                    ui.label("Select Dwarf:").classes("text-lg font-semibold")
                    self.dwarf_filter = ui.select(options=[], on_change=self.on_dwarf_filter_change).props('outlined')
                    self.usb_status_label = ui.label("").classes('pb-2')
                    with ui.element('div').classes('pt-0 pb-0 relative w-fit h-fit'):
                        self.ftp_status_label = ui.label("").classes('pt-0 pb-2')
                        self.ftp_spinner = (
                            ui.spinner(size="2em")
                            .style('position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); z-index: 10')
                        )
                with ui.column():
                    ui.label("Backup Drive:").classes("text-lg font-semibold")
                    self.backup_filter = ui.select(options=[], on_change=self.on_backup_filter_change).props('outlined')
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

        # Set initial value
        initial_value = names[0] if names else None

        # If self.DwarfId is set, try to find corresponding name
        if self.DwarfId:
            match = next((name for did, name in self.dwarf_options if did == self.DwarfId), None)
            if match:
                initial_value = match

        self.dwarf_filter.set_options(names, value = initial_value)

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
        
        # Find the name corresponding to the ID
        initial_value = None
        for name, (id_, _, _) in self.backup_data.items():
            if id_ == self.BackupId_Init:
                initial_value = name
                break
        print(initial_value)

        # Fallback if not found
        if not initial_value and names:
            initial_value = names[0]

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

    def on_backup_filter_change(self):
        print("on_backup_filter_change")
        selected_name = self.backup_filter.value
        for bid, name, *_ in self.backup_options:
            if name == selected_name:
                self.BackupDriveId = bid
                break
        self.update_backup_details(selected_name)

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
            self.dwarf_type = row[3] or None
            print(f"dwarf_ip_sta_mode: {self.dwarf_ip_sta_mode}")
            print(f"dwarf_type: {int(self.dwarf_type)+1}")
            if self.mode == "Archive":
                self.input_src_dir.set_options([], value = "")
                self.src_main_dir = ""
            elif self.mode == "Repair" or self.mode == "Merge":
                # Keep source pre-filled; reset destination (Dwarf side)
                self.input_dest_dir.set_options([], value="")
                self.dest_main_dir = ""
            else:  # Restore
                self.input_dest_dir.set_options([], value = "")
                self.dest_main_dir = ""

            await self.check_status_dwarf()

    def update_dwarf_directory(self):
        if self.mode == "Repair" or self.mode == "Merge":
            # Source: pre-filled with the repaired temp dir, constrained to src_root
            src = self.src_override or ""
            root = self.src_root or (os.path.dirname(src) if src else "")
            options = [src] if src else []
            self.input_src_dir.set_options(options, value=src)
            self.src_main_dir = root  # folder picker stays inside backup dir

            # Destination: same logic as Restore — point to Dwarf session dir
            if self.transfert_mode_select.value == "FTP" and self.dwarf_ip_sta_mode:
                initial_ftp_dir = None
                self.ftp_dwarf_dir = get_ftp_astroDir(self.dwarf_ip_sta_mode)
                if self.ftp_dwarf_dir:
                    if self.DwarfId_Init == self.DwarfId and self.session:
                        session_name = os.path.basename(self.session)
                        if session_name.startswith("RESTACKED"):
                            initial_ftp_dir = "/".join([self.ftp_dwarf_dir, "RESTACKED"])
                    if initial_ftp_dir:
                        self.input_dest_dir.set_options([self.ftp_dwarf_dir, initial_ftp_dir], value=initial_ftp_dir)
                    else:
                        self.input_dest_dir.set_options([self.ftp_dwarf_dir], value=self.ftp_dwarf_dir)
                    self.dest_main_dir = self.ftp_dwarf_dir
            else:
                initial_dir = None
                if self.DwarfId_Init == self.DwarfId and self.session:
                    session_name = os.path.basename(self.session)
                    if session_name.startswith("RESTACKED"):
                        initial_dir = os.path.join(self.dwarf_astroDir, "RESTACKED")
                if initial_dir:
                    self.input_dest_dir.set_options([self.dwarf_astroDir, initial_dir], value=initial_dir)
                else:
                    self.input_dest_dir.set_options([self.dwarf_astroDir], value=self.dwarf_astroDir)
                self.dest_main_dir = self.dwarf_astroDir
            return

        if self.mode == "Archive":
            if self.transfert_mode_select.value == "FTP" and self.dwarf_ip_sta_mode:
                if self.DwarfId_Init == self.DwarfId and self.session:
                    base_dir = get_ftp_astroDir(self.dwarf_ip_sta_mode)
                    if not base_dir:
                        base_dir = "" 
                    if self.session.startswith("RESTACKED"):
                        self.ftp_dwarf_dir = "/".join([base_dir, "RESTACKED", self.session])
                    else:
                        self.ftp_dwarf_dir = "/".join([base_dir, self.session])
                else:
                    self.ftp_dwarf_dir = get_ftp_astroDir(self.dwarf_ip_sta_mode)
                if self.ftp_dwarf_dir:
                    self.input_src_dir.set_options([self.ftp_dwarf_dir], value = self.ftp_dwarf_dir)
                    self.src_main_dir = self.ftp_dwarf_dir
            else:
                if self.DwarfId_Init == self.DwarfId and self.session:
                    if self.session.startswith("RESTACKED"):
                        restacked_session = os.path.join("RESTACKED", self.session)
                        self.input_src_dir.set_options([os.path.join(self.dwarf_astroDir, restacked_session)], value = os.path.join(self.dwarf_astroDir, restacked_session))
                    else:
                        self.input_src_dir.set_options([os.path.join(self.dwarf_astroDir, self.session)], value = os.path.join(self.dwarf_astroDir, self.session))
                else:
                    self.input_src_dir.set_options([self.dwarf_astroDir], value = self.dwarf_astroDir)
                self.src_main_dir = self.dwarf_astroDir
        else:
            if self.transfert_mode_select.value == "FTP" and self.dwarf_ip_sta_mode:
                initial_ftp_dir = None
                self.ftp_dwarf_dir = get_ftp_astroDir(self.dwarf_ip_sta_mode)

                if self.ftp_dwarf_dir:
                    if self.DwarfId_Init == self.DwarfId and self.session:
                        session_name = os.path.basename(self.session)
                        if session_name.startswith("RESTACKED"):
                            initial_ftp_dir = "/".join([self.ftp_dwarf_dir, "RESTACKED"])
                    if initial_ftp_dir:
                        self.input_dest_dir.set_options([self.ftp_dwarf_dir, initial_ftp_dir], value = initial_ftp_dir)
                    else:
                        self.input_dest_dir.set_options([self.ftp_dwarf_dir], value = self.ftp_dwarf_dir)
                    self.dest_main_dir = self.ftp_dwarf_dir
            else:
                initial_dir = None
                if self.DwarfId_Init == self.DwarfId and self.session:
                    session_name = os.path.basename(self.session)
                    if session_name.startswith("RESTACKED"):
                        initial_dir = os.path.join(self.dwarf_astroDir, "RESTACKED")
                if initial_dir:
                    self.input_dest_dir.set_options([self.dwarf_astroDir, initial_dir], value = initial_dir)
                else:
                    self.input_dest_dir.set_options([self.dwarf_astroDir], value = self.dwarf_astroDir)
                self.dest_main_dir = self.dwarf_astroDir

    def ftp_to_local_path(self, ftp_path: str) -> str:
        """
        Convert an FTP path (starting with self.ftp_dwarf_dir) to a local path
        (starting with self.dwarf_astroDir).
        """
        if not ftp_path or not self.ftp_dwarf_dir or not self.dwarf_astroDir:
            return ""

        # Ensure consistent separators
        ftp_base = self.ftp_dwarf_dir.replace("\\", "/").rstrip("/")
        ftp_path = ftp_path.replace("\\", "/")

        if ftp_path.startswith(ftp_base):
            relative_path = ftp_path[len(ftp_base):].lstrip("/\\")
            return os.path.normpath(os.path.join(self.dwarf_astroDir, relative_path))
        else:
            # fallback: assume full ftp_path is relative
            return os.path.normpath(os.path.join(self.dwarf_astroDir, ftp_path))

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
        status_text = ""
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
            # case self.BackupId_Init
            print(f"case self.BackupId_Init : {self.BackupId_Init}-{self.BackupId}-{self.session}")
            if self.BackupId_Init and self.BackupId_Init == self.BackupId and self.session:
                print("case self.BackupId_Init")
                self.input_src_dir.set_options([self.session], value = self.session)
            else:
                self.input_src_dir.set_options([self.backup_path], value = self.backup_path)
            self.src_main_dir = self.backup_path

    def check_status_backup(self):
        if self.backup_path:
           if os.path.exists(self.backup_path):
               self.backup_status_label.text = "✅ Path detected."
           else:
               self.backup_status_label.text = "❌ Path not detected."

    async def open_source_select(self):
        await self.client.run_javascript(f"document.querySelector('[aria-label=\"{self.input_src_dir.label}\"]').click();")

    async def open_destination_select(self):
        await self.client.run_javascript(f"document.querySelector('[aria-label=\"{self.input_dest_dir.label}\"]').click();")

    async def select_source_folder(self):
        # Repair mode: local folder picker constrained to src_root (backup directory)
        if self.mode == "Repair" or self.mode == "Merge":
            if hasattr(webview, 'FileDialog'):
                folder_mode = webview.FileDialog.FOLDER
            else:
                folder_mode = webview.FOLDER_DIALOG

            start_dir = os.path.abspath(self.input_src_dir.value or self.src_root or "")
            folder = await app.native.main_window.create_file_dialog(folder_mode, allow_multiple=False, directory=start_dir)

            if folder:
                selected = folder[0]
                constraint = self.src_root or ""
                if constraint and not selected.startswith(constraint):
                    ui.notify(f"❌ Access denied: source must be inside the backup directory ({constraint})", type="negative")
                else:
                    folder_norm = os.path.normpath(selected)
                    self.input_src_dir.set_options([folder_norm], value=folder_norm)
            return

        if self.mode == "Archive" and self.transfert_mode_select.value == "FTP" and self.dwarf_ip_sta_mode:
            try:
                if self.DwarfId_Init == self.DwarfId and self.session:
                    base_dir = get_ftp_astroDir(self.dwarf_ip_sta_mode)
                    if not base_dir:
                        base_dir = "" 
                    if self.session.startswith("RESTACKED"):
                        subdirs = ["/".join([base_dir, "RESTACKED", self.session])]
                    else:
                        subdirs = ["/".join([base_dir, self.session])]
                else:
                    subdirs = list_ftp_subdirectories(self.dwarf_ip_sta_mode)
                    restacked = list_ftp_subdirectories(self.dwarf_ip_sta_mode, subdir='RESTACKED')
                    subdirs += [f"{s}" for s in restacked]
            except Exception as e:
                ui.notify("No RESTACKED folder found on FTP or access failed")

            # Optionally remove duplicates
            subdirs = sorted(set(subdirs))

            if subdirs:
                selected_value = self.ftp_dwarf_dir
                if len(subdirs) == 1:
                   selected_value = subdirs[0]
                print(f"selected_value: {selected_value}")
                if self.ftp_dwarf_dir and self.ftp_dwarf_dir not in subdirs:
                    subdirs.append(self.ftp_dwarf_dir)
                self.input_src_dir.set_options(subdirs, value = selected_value)
                await self.open_source_select()

        else:

            """Open folder selection dialog."""
            if hasattr(webview, 'FileDialog'):
                folder_mode = webview.FileDialog.FOLDER
            else:
                folder_mode = webview.FOLDER_DIALOG

            if self.input_src_dir.value:
                full_path = os.path.abspath(self.input_src_dir.value)
                folder = await app.native.main_window.create_file_dialog(folder_mode, allow_multiple=False,directory=full_path)
            else:
                folder = await app.native.main_window.create_file_dialog(folder_mode, allow_multiple=False)

            if folder and not folder[0].startswith(self.src_main_dir):
                ui.notify(f"❌ Access denied: You cannot navigate outside {self.SourceMainDir}")
            elif folder:
                ui.notify(folder[0])
                folder = os.path.normpath(folder[0])
                self.input_src_dir.set_options([folder], value = folder)

    async def resize_input(self):
        await self.client.run_javascript(f'''
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
                await self.open_destination_select()

        else:

            """Open folder selection dialog."""
            if hasattr(webview, 'FileDialog'):
                folder_mode = webview.FileDialog.FOLDER
            else:
                folder_mode = webview.FOLDER_DIALOG

            if self.input_dest_dir.value:
                full_path = os.path.abspath(self.dest_main_dir) # self.input_dest_dir.value
                folder = await app.native.main_window.create_file_dialog(folder_mode, allow_multiple=False,directory=full_path)
            else:
                folder = await app.native.main_window.create_file_dialog(folder_mode, allow_multiple=False)
        
            if folder and not folder[0].startswith(self.dest_main_dir):
                ui.notify(f"❌ Access denied: You cannot navigate outside {self.DestinationMainDir}")
            elif folder:
                ui.notify(f"✅ Selected Folder: {folder[0]}")
                folder = os.path.normpath(folder[0])
                self.input_dest_dir.set_options([folder], value = folder)

    async def start_backup(self):
        self.progress.value = 0
        src_dir = self.input_src_dir.value
        print(f" Backup src_dir:  {src_dir}")
        # Check is Full Backup : the Astro Directory is used only
        isFullBackup = (src_dir == self.src_main_dir)
        if self.transfert_mode_select.value == "FTP" and self.dwarf_ip_sta_mode: 
            isFullBackup = (src_dir == get_ftp_astroDir(self.dwarf_ip_sta_mode))
        print(f" is Full Backup task:  {isFullBackup}")
        dest_dir = self.input_dest_dir.value
        print(f" Backup dest_dir:  {dest_dir}")
        if not src_dir:
            self.progress_label.set_text("Select a Source Directory.")
            return
        if not dest_dir:
            self.progress_label.set_text("Select a Destination Directory.")
            return

        if self.mode != "Archive" and self.transfert_mode_select.value == "FTP":
            if int(self.dwarf_type) != 1: #only D2 is not read-only
                self.notify_me.refresh("FTP is read-only: Restore not allowed.")
                self.progress_label.set_text("FTP is read-only.")
                return
            else:
                self.cancel_btn.visible = True
                self.StartBackup.visible = False
                # FTP paths: simple string manipulation
                src_basename = os.path.basename(os.path.normpath(src_dir))
                if not isFullBackup:
                    dest_path = f"{dest_dir.rstrip('/')}/{src_basename}"
                else:
                    dest_path = dest_dir.rstrip('/')
                # You would need to check existence via FTP
                if ftp_path_exists(self.dwarf_ip_sta_mode, dest_path):  # Implement this check
                    base_path = "/mnt/sdcard" # use ssh
                    await self.confirm_overwrite(dest_path, isFullBackup)
                else:
                    await self.execute_backup(src_dir, dest_path, isFullBackup)
        else:
            self.cancel_btn.visible = True
            self.StartBackup.visible = False

            # Local USB path
            if not isFullBackup:
                dest_path = os.path.join(dest_dir, os.path.basename(src_dir))
            else:
                dest_path = dest_dir

            # Check if destination path exists
            if os.path.exists(dest_path):
                await self.confirm_overwrite(dest_path, isFullBackup)
            else:
                await self.execute_backup(src_dir, dest_path, isFullBackup)

        self.cancel_btn.visible = False
        self.StartBackup.visible = True

    async def confirm_overwrite(self, dest_path, isFullBackup):

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
            await self.execute_backup(self.input_src_dir.value, dest_path, isFullBackup)
        else:
            self.progress_label.set_text("Backup canceled.")
            self.cancel_btn.visible = False
            self.StartBackup.visible = True

    async def execute_backup(self, src_dir, dest_path, isFullBackup):

        list_files = await self.get_files(src_dir, dest_path, isFullBackup)
        total_files = 0
        if list_files:
            total_files = len(list_files)

        if total_files == 0:
            self.progress_label.set_text("No files to copy.")
            return
        else:
            self.progress_label.set_text(f"{'Full Backup, ' if isFullBackup else ''}Starting copying {total_files} files...")
        ui.notify("Starting...")

        if self.mode == "Repair":
            transfer_mode = self.transfert_mode_select.value
            use_ftp = transfer_mode == "FTP"
            mode_use_ssh = True if use_ftp else False

            if mode_use_ssh:  
                await sftp_clean_subdir_files(self.dwarf_ip, dest_path)
            else:
                await run.io_bound(self._clean_dwarf_dest_subdir_files, dest_path)

        #print ( list_files)
        #result = await run.io_bound(self.copy_with_progress_async, list_files, self.progress, self.cancel_btn)
        result = await self.copy_with_progress_async(list_files, self.progress, self.cancel_btn)

        if result:
            self.progress_label.set_text(f"End of Backup")
            ui.notify("✅ Backup complete and verified!")

            with ui.dialog().props('persistent')  as dialog, ui.card().style('width: 800px; max-width: none'):
                label = ui.label(self.ScanningMessage)
                spinner = ui.spinner(size="lg")
                log = ui.log(max_lines=20).classes('w-full').style('height: 400px; overflow: hidden;')
                ui.button('Close', on_click=dialog.close)
            dialog.open()  # show the dialog

            try:
                # use sync_dwarf_sessions
                local_Main_Dwarf_dir = create_local_dwarf_dir(self.conn)
                if not local_Main_Dwarf_dir:
                    spinner.visible = False
                    ui.notify(f"❌ Error accessing local Dwarf Directory : {local_Main_Dwarf_dir}", type="negative")
                else:
                    ui.notify("Starting Local Sync ...")
                    session_name = ""
                    dir_parent_session = ""
                    dir_backup_session = ""
                    if self.mode == "Archive":
                        if isFullBackup:
                            dir_parent_session = dest_path
                        else: 
                            session_name = os.path.basename(dest_path)
                            dir_parent_session = os.path.dirname(dest_path)
                            dir_backup_session = dest_path
                    elif self.mode == "Repair" or self.mode == "Merge":
                        # Source is the repaired temp dir; dest is the Dwarf dir.
                        # Sync only the Dwarf local dir (not a backup scan — repair
                        # does not change the backup drive content).
                        if isFullBackup:
                            dir_parent_session = dest_path
                        else:
                            session_name = os.path.basename(dest_path)
                            dir_parent_session = os.path.dirname(dest_path)
                            dir_backup_session = ""   # no backup-side scan for Repair
                    else:  # Restore
                        if isFullBackup:
                            dir_parent_session = src_dir
                        else: 
                            session_name = os.path.basename(src_dir)
                            dir_parent_session = os.path.dirname(src_dir)
                            dir_backup_session = src_dir

                    print(f"session_name: {session_name}")
                    print(f"dir_parent_session: {dir_parent_session}")
                    print(f"dir_backup_session: {dir_backup_session}")
                    # if session is a RESTACKED one will be copied in RESTACKED dir by sync_dwarf_sessions
                    await run.io_bound (sync_dwarf_sessions, self.DwarfId, dir_parent_session, local_Main_Dwarf_dir,session_name,log)

                    ui.notify("Starting Analysis ...")

                    local_Dwarf_dir = get_local_dwarf_dir(self.conn, self.DwarfId)
                    local_Dwarf_session = ""
                    if session_name:
                       local_Dwarf_session = os.path.join(local_Dwarf_dir, session_name) 
                    if session_name.startswith("RESTACKED"):
                        restacked_session = os.path.join("RESTACKED", session_name)
                        local_Dwarf_session = os.path.join(local_Dwarf_dir, restacked_session)
                    print(local_Dwarf_session)

                    total_dwarf, deleted_dwarf = await run.io_bound (scan_backup_folder, DB_NAME, local_Dwarf_dir, None, self.DwarfId, None, local_Dwarf_session, log)

                    # In Repair mode the backup drive is unchanged — skip backup scan
                    if self.mode != "Repair" and self.mode != "Merge" and dir_backup_session is not None:
                        total_backup, deleted_backup = await run.io_bound (scan_backup_folder, DB_NAME, self.backup_location, self.backup_astrodir, self.DwarfId, self.BackupId, dir_backup_session, log)
                        ui.notify(f"✅ Analysis Complete: {total_backup} new sessions found on backup.", type="positive")
                    else:
                        total_backup, deleted_backup = 0, 0

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

    async def get_files_old(self, src_dir, dest_dir, isFullBackup):
        all_files = []
        for root, _, files in os.walk(src_dir):
            for file in files:
                src_path = os.path.join(root, file)
                rel_path = os.path.relpath(src_path, src_dir)
                dest_path = os.path.join(dest_dir, rel_path)
                # in case of Full Backup don't overwrite files
                if not isFullBackup or not os.path.isfile(dest_path):
                    all_files.append((src_path, dest_path))

        return all_files

    async def get_files(self, src_dir, dest_dir, isFullBackup):
        all_files = []

        if self.transfert_mode_select.value == "FTP" and self.mode == "Archive":
            # FTP → USB
            all_files = await run.io_bound(download_ftp_tree, self.dwarf_ip_sta_mode,src_dir, dest_dir, isFullBackup)

        elif self.transfert_mode_select.value == "FTP" and self.mode == "Restore":
            # USB → FTP : Not Possible Read Only system for D3
            print(f"dest_dir: {dest_dir}")
            base_path = "/mnt/sdcard" # ssh
            for root, _, files in os.walk(src_dir):
                for file in files:
                    src_path = os.path.join(root, file)
                    rel_path = os.path.relpath(src_path, src_dir)
                    ftp_rel_path = rel_path.replace("\\", "/")
                    #dest_path = f'{dest_dir.rstrip("/")}/{ftp_rel_path}'
                    dest_path = f'{base_path}{dest_dir.rstrip("/")}/{ftp_rel_path}'
                    all_files.append((src_path, dest_path))

        else:
            # USB → USB
            for root, _, files in os.walk(src_dir):
                for file in files:
                    src_path = os.path.join(root, file)
                    rel_path = os.path.relpath(src_path, src_dir)
                    dest_path = os.path.join(dest_dir, rel_path)
                    # in case of Full Backup don't overwrite files
                    if not isFullBackup or not os.path.isfile(dest_path):
                        all_files.append((src_path, dest_path))

        return all_files

    # Optional: compute a SHA256 hash for data integrity
    def file_hash(self, path):
        hash = hashlib.sha256()
        with open(path, 'rb') as f:
            while chunk := f.read(8192):
               hash.update(chunk)
        return hash.hexdigest()

    def _clean_dwarf_dest_subdir_files(self, dest_dir: str) -> None:
        dest = Path(dest_dir)
        if not dest.exists():
            return
        for subdir in dest.iterdir():
            if subdir.is_dir():
                for item in subdir.iterdir():
                    try:
                        if item.is_file():
                            item.unlink()
                        elif item.is_dir():
                            for f in item.iterdir():
                                if f.is_file():
                                    try:
                                        f.unlink()
                                    except Exception as e:
                                        print(f"Could not delete {f}: {e}")
                    except Exception as e:
                        print(f"Could not delete {item}: {e}")

    async def copy_with_progress_async(self, all_files, progress_bar, cancel_button):
        self.cancel_backup = False
        verified_files = 0
        result = False
        try:
            total_files = len(all_files)
            #print (total_files)
            transfer_mode = self.transfert_mode_select.value
            is_archive = self.mode == "Archive"
            is_restore = self.mode == "Restore"
            use_ftp = transfer_mode == "FTP"
            mode_use_ssh = True if use_ftp and is_restore else False
            print(f"mode_use_ssh: {mode_use_ssh}")
            # Conditional FTP connection block
            ftp = None
            ftp_ctx = ftp_conn(self.dwarf_ip_sta_mode) if use_ftp and self.dwarf_ip_sta_mode and not mode_use_ssh else None
            ftp = ftp_ctx.__enter__() if ftp_ctx else None

            created_dirs_cache = set()

            for i, (src_file, dest_file) in enumerate(all_files):
                dest_file = win_long_path(dest_file)
                if self.cancel_backup:
                    self.notify_me.refresh("Backup cancelled.")
                    result = False
                    break

                progress = round((i + 1) / total_files * 100)

                # --- FTP ➜ LOCAL (ARCHIVE) ---
                if use_ftp and is_archive:
                    await run.io_bound(ftp_download_file, ftp, src_file, dest_file)

                # --- LOCAL ➜ FTP (RESTORE) ---
                elif mode_use_ssh and is_restore:
                    await async_sftp_upload(self.dwarf_ip_sta_mode, src_file, dest_file, created_dirs_cache)

                # --- LOCAL ➜ LOCAL ---
                else:
                    os.makedirs(os.path.dirname(dest_file), exist_ok=True)
                    await run.io_bound(shutil.copy2, src_file, dest_file)
                    if os.path.getsize(src_file) != os.path.getsize(dest_file):
                        raise Exception("Size mismatch after copy")

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

        except Exception as e:
            if isinstance(e, OSError) and getattr(e, 'winerror', None) == 112:
                error_msg = f"❌ Disk full, failed to copy {src_file} → {dest_file}: {e}"
            else:
                error_msg = f"❌ Failed to copy {src_file} → {dest_file}: {e}"
            self.notify_me.refresh(error_msg)
            traceback.print_exc()
            progress_bar.value = 0
            result = False

        finally:
            # Close FTP connection if it was opened
            if ftp_ctx:
                ftp_ctx.__exit__(None, None, None)      
            # Close SFTP connection if it was opened
            #if sftp_ctx:
            #   sftp_ctx.__exit__(None, None, None)      

        cancel_button.visible = False
        self.StartBackup.visible = True
        return result

    def get_explore_url(self):
        if self.BackUrl == "/Mosaic":
            explore_url = f"{self.BackUrl}?"
            explore_url_data = ""
            if self.DwarfId:
                explore_url_data = f"DwarfId={self.DwarfId}"
            if self.BackupDriveId:
                if explore_url_data:
                    explore_url_data = explore_url_data + "&"
                
                explore_url_data = explore_url_data + f"BackupId={self.BackupDriveId}"
            if explore_url_data:
                explore_url = explore_url + explore_url_data + f"&Mode={self.mode}"
            else:
                explore_url = explore_url + f"Mode={self.mode}"
        elif self.BackupId_Init:
            back_url = f"/Backup?BackupId="
            if self.DwarfId:
                explore_url = f"/Explore?BackupDriveId={self.BackupDriveId}&DwarfId={self.DwarfId}&mode=backup&back_url={back_url}"
            else:
                explore_url = f"/Explore?BackupDriveId={self.BackupDriveId}&mode=backup&back_url={back_url}"
        elif self.DwarfId:
            back_url = f"/Dwarf?DwarfId="
            explore_url = f"/Explore?DwarfId={self.DwarfId}&mode=dwarf&back_url={back_url}"
        else:
            explore_url = f"/Explore?mode=dwarf"
        print(explore_url)
        return explore_url
