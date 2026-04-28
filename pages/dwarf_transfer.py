import webview
import asyncio
from nicegui import ui, app, run, Client, background_tasks

import os
import shutil
import hashlib
import traceback
from pathlib import Path

from components.menu import menu
from api.dwarf_backup_fct_ftp import ftp_conn, check_ftp_connection, get_ftp_astroDir, list_ftp_subdirectories, ftp_path_exists, download_ftp_tree, ftp_download_file
from api.dwarf_backup_fct_sftp import asyncssh_sftp_session, async_sftp_upload, sftp_clean_subdir_files
from api.dwarf_backup_fct import safe_copy2, scan_backup_folder, win_long_path, sync_dwarf_sessions, create_local_dwarf_dir, get_local_dwarf_dir

from api.dwarf_backup_db import DB_NAME, connect_db, close_db
from api.dwarf_backup_db_api import get_dwarf_Names, get_dwarf_detail, get_backupDrive_list_dwarfId
from components.win_log import WinLog

MULTI_SESSION = " (Multi Sessions)"

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
    dest_override: str = None,  # force destination to this path (e.g. CALI_FRAME dir)
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
        DestOverride=dest_override,
    )
    #ui.context.client.on_disconnect(lambda: logger.removeHandler(handler))

class TransferApp:
    def __init__(self, client: Client, database, DwarfId=None, Session=None, Mode="Archive", BackupId=None, BackUrl=None, SrcOverride=None, SrcRoot=None, DestOverride=None):
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
        self.src_override  = SrcOverride   # e.g. "D:\Backup\temp_mosaic\SESSION_NAME"
        self.src_root      = SrcRoot       # e.g. "D:\Backup" — folder picker stays inside here
        # Dark library download: force destination to CALI_FRAME dir (locked)
        self.dest_override = DestOverride  # e.g. "X:\DWARF_MINI_NEW\CALI_FRAME"

        self.src_dir = '' # 'G:\\Astronomy\\DWARF_RAW_WIDE_C 20_EXP_15_GAIN_80_2025-04-28-04-21-24-416'
        self.dest_dir = '' # 'T:\\DWARFLAB_2\\DATA4\\DATA_OBJECTS\\NGC7000_North_American_Nebula'
        self.src_main_dir = '' # 'G:\\Astronomy\\DWARF_RAW_WIDE_C 20_EXP_15_GAIN_80_2025-04-28-04-21-24-416'
        self.dest_main_dir = '' # 'T:\\DWARFLAB_2\\DATA4\\DATA_OBJECTS\\NGC7000_North_American_Nebula'

        self.MultiSession = False
        self.ftp_dwarf_dir = None
        self.dwarf_ip_sta_mode = ""
        self.dwarf_type = None
        self.usb_available = False
        self.ftp_available = False
        self._client_id = client.id
        self.build_ui()
        self.set_mode_UI()

    def set_mode_UI(self):

        if self.mode == "Archive":
            if self.dest_override:
                if self.transfert_mode_select.value == "FTP":
                    self.SourceDirectory.set_text("Source: Dwarf CALI_FRAME (FTP)")
                else:
                    self.SourceDirectory.set_text("Source: Dwarf CALI_FRAME")
                self.DestinationDirectory.set_text(f"Destination: Backup Drive → {os.path.basename(self.dest_override)}")
            elif self.transfert_mode_select.value == "FTP":
                self.SourceDirectory.set_text(f"Source: Dwarf Drive (FTP){MULTI_SESSION if self.MultiSession else ''}")
                self.DestinationDirectory.set_text("Destination: Backup Drive")
            else:
                self.SourceDirectory.set_text(f"Source: Dwarf Drive{MULTI_SESSION if self.MultiSession else ''}")
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
                self.SourceDirectory.set_text(f"Source: Backup Drive{MULTI_SESSION if self.MultiSession else ''}")
                self.DestinationDirectory.set_text("Destination: Dwarf Drive (FTP)")
            else:
                self.SourceDirectory.set_text(f"Source: Backup Drive{MULTI_SESSION if self.MultiSession else ''}")
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
        sizeBTN='w-56'

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
                with ui.column().classes('w-50 items-center'):
                    ui.label("Select Dwarf:").classes("text-lg font-semibold")
                    self.dwarf_filter = ui.select(options=[], on_change=self.on_dwarf_filter_change).props('outlined')
                    with ui.row().classes('items-center gap-2'):
                        self.usb_status_label = ui.label("").classes('pb-2')
                        self.refresh_btn = (
                            ui.button(icon='refresh', on_click=self.check_status_dwarf)
                            .props('flat round dense')
                            .bind_visibility_from(self.usb_status_label, 'text', lambda v: (v == "❌ Path not detected."))
                        )
                    with ui.element('div').classes('pt-0 pb-0 relative w-fit h-fit'):
                        self.ftp_status_label = ui.label("").classes('pt-0 pb-2')
                        self.ftp_spinner = (
                            ui.spinner(size="2em")
                            .style('position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); z-index: 10')
                        )
                with ui.column().classes('w-50 items-center'):
                    ui.label("Backup Drive:").classes("text-lg font-semibold")
                    self.backup_filter = ui.select(options=[], on_change=self.on_backup_filter_change).props('outlined')
                    self.backup_status_label = ui.label("").classes('pb-2')

            self.transfert_mode_select = ui.select(label="Transfer Mode",options=[], on_change=self.change_transfert_mode).props('stack-label').props('outlined').classes('w-40').classes("min-w-[200px] w-auto overflow-x-auto whitespace-nowrap")

            self.SourceDirectory = ui.label("Source: Dwarf USB Drive").classes("text-lg font-semibold")
            self.input_src_dir = ui.select(label="Source Directory:", value = self.src_dir, options=[self.src_dir], on_change=lambda: self.resize_input()).props('stack-label').props('outlined').classes('w-40').classes("min-w-[600px] w-auto overflow-x-auto whitespace-nowrap")
            ui.button("Select Source", on_click=lambda : self.select_source_folder()).classes(sizeBTN)

        with ui.card().classes("w-full p-4 mt-1 items-center"):
            self.DestinationDirectory = ui.label("Destination: Backup Drive").classes("text-lg font-semibold")
            self.input_dest_dir = ui.select(label="Destination Directory:", value = self.dest_dir, options=[self.dest_dir], on_change=lambda: self.resize_input()).props('stack-label').props('outlined').classes('w-40').classes("min-w-[600px] w-auto overflow-x-auto whitespace-nowrap")
            ui.button("Select Destination", on_click=lambda : self.select_destination_folder()).classes(sizeBTN)

        with ui.card().classes("w-full p-4 mt-1 mb-8 items-center"):
            self.progress_label = ui.label("Idle...")
            self.progress = ui.circular_progress(max=100, show_value=True)
            self.CancelBackup = self.cancel_btn = ui.button('Cancel Backup', on_click=lambda: self.cancel()).classes(sizeBTN)
            self.cancel_btn.visible = False
            self.StartBackup = ui.button('Start Backup', on_click=lambda:self.start_backup()).classes(sizeBTN)
            self.cancel_backup = False
            ui.label(
                "⚠️ Do not close or navigate away from this window during a transfer — "
                "the copy may be incomplete if interrupted."
            ).classes("text-sm text-orange-500 mt-2")

            # Background task progress panel — shown when a transfer is running
            # and reconnects automatically when user returns to this page
            ui.separator()
            self.bg_status_label = ui.label("").classes("text-sm text-gray-500")
            self.bg_progress = ui.linear_progress(value=0).classes("w-full")
            self.bg_progress.visible = False
            self.bg_status_label.visible = False

            # Poll progress storage every second
            self._progress_timer = ui.timer(1.0, self._poll_transfer_progress)
            self._restore_transfer_state()

        self.populate_dwarf_filter()
        self.notify_me(None)

    def populate_dwarf_filter(self):
        self.ftp_spinner.set_visibility(False)
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
        self.ftp_spinner.set_visibility(False)
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
                        if session_name.startswith("STARTRAILS"):
                            initial_ftp_dir = "/".join([self.ftp_dwarf_dir, "STARTRAILS"])
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
                    if session_name.startswith("STARTRAILS"):
                        initial_dir = os.path.join(self.dwarf_astroDir, "STARTRAILS")
                if initial_dir:
                    self.input_dest_dir.set_options([self.dwarf_astroDir, initial_dir], value=initial_dir)
                else:
                    self.input_dest_dir.set_options([self.dwarf_astroDir], value=self.dwarf_astroDir)
                self.dest_main_dir = self.dwarf_astroDir
            return

        if self.mode == "Archive":
            # Dark download mode: force source to CALI_FRAME on the Dwarf
            if self.dest_override:
                if self.transfert_mode_select.value == "FTP" and self.dwarf_ip_sta_mode:
                    base_dir = get_ftp_astroDir(self.dwarf_ip_sta_mode)
                    if base_dir:
                        cali_ftp = "/".join([base_dir.rstrip("/"), "CALI_FRAME"])
                        self.ftp_dwarf_dir = cali_ftp
                        self.input_src_dir.set_options([cali_ftp], value=cali_ftp)
                        self.src_main_dir = cali_ftp
                else:
                    cali_usb = os.path.join(self.dwarf_astroDir, "CALI_FRAME")
                    self.input_src_dir.set_options([cali_usb], value=cali_usb)
                    self.src_main_dir = cali_usb
                return

            if self.transfert_mode_select.value == "FTP" and self.dwarf_ip_sta_mode:
                if self.DwarfId_Init == self.DwarfId and self.session:
                    base_dir = get_ftp_astroDir(self.dwarf_ip_sta_mode)
                    if not base_dir:
                        base_dir = ""
                    # Multi-session support: pipe-separated list
                    sessions = self.session.split("|") if "|" in self.session else [self.session]
                    self.MultiSession = (len(sessions) > 1)
                    if self.MultiSession:
                        ftp_dirs = []
                        for s in sessions:
                            if s.startswith("RESTACKED"):
                                ftp_dirs.append("/".join([base_dir, "RESTACKED", s]))
                            elif s.startswith("STARTRAILS"):
                                ftp_dirs.append("/".join([base_dir, "STARTRAILS", s]))
                            else:
                                ftp_dirs.append("/".join([base_dir, s]))
                        self.ftp_dwarf_dir = ftp_dirs[0]
                        self.input_src_dir.set_options(ftp_dirs, value=ftp_dirs[0])
                        self.src_main_dir = self.ftp_dwarf_dir
                    else:
                        if self.session.startswith("RESTACKED"):
                            self.ftp_dwarf_dir = "/".join([base_dir, "RESTACKED", self.session])
                        elif self.session.startswith("STARTRAILS"):
                            self.ftp_dwarf_dir = "/".join([base_dir, "STARTRAILS", self.session])
                        else:
                            self.ftp_dwarf_dir = "/".join([base_dir, self.session])
                        if self.ftp_dwarf_dir:
                            self.input_src_dir.set_options([self.ftp_dwarf_dir], value=self.ftp_dwarf_dir)
                            self.src_main_dir = self.ftp_dwarf_dir
                else:
                    self.ftp_dwarf_dir = get_ftp_astroDir(self.dwarf_ip_sta_mode)
                    if self.ftp_dwarf_dir:
                        self.input_src_dir.set_options([self.ftp_dwarf_dir], value=self.ftp_dwarf_dir)
                        self.src_main_dir = self.ftp_dwarf_dir
            else:
                if self.DwarfId_Init == self.DwarfId and self.session:
                    # Multi-session support: pipe-separated list
                    sessions = self.session.split("|") if "|" in self.session else [self.session]
                    self.MultiSession = (len(sessions) > 1)
                    if self.MultiSession:
                        dirs = []
                        for s in sessions:
                            if s.startswith("RESTACKED"):
                                dirs.append(os.path.join(self.dwarf_astroDir, "RESTACKED", s))
                            elif s.startswith("STARTRAILS"):
                                dirs.append(os.path.join(self.dwarf_astroDir, "STARTRAILS", s))
                            else:
                                dirs.append(os.path.join(self.dwarf_astroDir, s))
                        self.input_src_dir.set_options(dirs, value=dirs[0])
                    else:
                        if self.session.startswith("RESTACKED"):
                            restacked_session = os.path.join("RESTACKED", self.session)
                            self.input_src_dir.set_options([os.path.join(self.dwarf_astroDir, restacked_session)], value=os.path.join(self.dwarf_astroDir, restacked_session))
                        elif self.session.startswith("STARTRAILS"):
                            startrails_session = os.path.join("STARTRAILS", self.session)
                            self.input_src_dir.set_options([os.path.join(self.dwarf_astroDir, startrails_session)], value=os.path.join(self.dwarf_astroDir, startrails_session))
                        else:
                            self.input_src_dir.set_options([os.path.join(self.dwarf_astroDir, self.session)], value=os.path.join(self.dwarf_astroDir, self.session))
                else:
                    self.input_src_dir.set_options([self.dwarf_astroDir], value=self.dwarf_astroDir)
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
                        if session_name.startswith("STARTRAILS"):
                            initial_ftp_dir = "/".join([self.ftp_dwarf_dir, "STARTRAILS"])
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
                    if session_name.startswith("STARTRAILS"):
                        initial_dir = os.path.join(self.dwarf_astroDir, "STARTRAILS")
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
                self.ftp_spinner.set_visibility(True)
                status_text = await run.io_bound(check_ftp_connection, self.dwarf_ip_sta_mode)
                self.ftp_available = "Connected to" in status_text if status_text else False
        finally:
            # Update only if the IP has not changed
            if current_ip == self.dwarf_ip_sta_mode:
                self.ftp_spinner.set_visibility(False)
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
            if self.dest_override:
                # dest_override is the starting point (e.g. BackupDrive root for dark downloads)
                # user can still navigate freely within it
                self.input_dest_dir.set_options([self.dest_override], value=self.dest_override)
                self.dest_main_dir = self.dest_override
            else:
                self.input_dest_dir.set_options([self.backup_path], value=self.backup_path)
                self.dest_main_dir = self.backup_path
        else:
            # case self.BackupId_Init
            print(f"case self.BackupId_Init : {self.BackupId_Init}-{self.BackupId}-{self.session}")
            if self.BackupId_Init and self.BackupId_Init == self.BackupId and self.session:
                # Multi-session restore: pipe-separated full backup paths
                sessions = self.session.split("|") if "|" in self.session else [self.session]
                self.MultiSession = (len(sessions) > 1)
                if self.MultiSession:
                    self.input_src_dir.set_options(sessions, value=sessions[0])
                else:
                    self.input_src_dir.set_options([self.session], value=self.session)
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
                    elif self.session.startswith("STARTRAILS"):
                        subdirs = ["/".join([base_dir, "STARTRAILS", self.session])]
                    else:
                        subdirs = ["/".join([base_dir, self.session])]
                else:
                    subdirs = list_ftp_subdirectories(self.dwarf_ip_sta_mode)
                    restacked = list_ftp_subdirectories(self.dwarf_ip_sta_mode, subdir='RESTACKED')
                    startrails = list_ftp_subdirectories(self.dwarf_ip_sta_mode, subdir='STARTRAILS')
                    subdirs += [f"{s}" for s in restacked] + [f"{s}" for s in startrails]
            except Exception as e:
                ui.notify("No RESTACKED or STARTRAILS folder found on FTP or access failed")

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
        dest_dir = self.input_dest_dir.value
        print(f" Backup dest_dir:  {dest_dir}")
        if not src_dir:
            self.progress_label.set_text("Select a Source Directory.")
            return
        if not dest_dir:
            self.progress_label.set_text("Select a Destination Directory.")
            return

        # Multi-session: if the source dropdown lists several session folders (not the root dir)
        all_src_dirs = list(self.input_src_dir.options) if self.input_src_dir.options else [src_dir]
        is_multi = (
            len(all_src_dirs) > 1
            and all(d != self.src_main_dir for d in all_src_dirs)
            and (self.mode == "Archive" or self.mode == "Restore")
        )

        if is_multi:
            self.cancel_btn.visible = True
            self.StartBackup.visible = False
            total = len(all_src_dirs)
            result_backup = True
            for i, single_src in enumerate(all_src_dirs, 1):
                if self.cancel_backup:
                    ui.notify("Transfer cancelled.", type="warning")
                    result_backup = False
                    break
                session_name = os.path.basename(os.path.normpath(single_src))
                single_dest = os.path.join(dest_dir, session_name)
                self.progress_label.set_text(f"[{i}/{total}] Processing: {session_name}...")
                if os.path.exists(single_dest):
                    ui.notify(f"'{session_name}' already exists — overwriting.", type="warning")
                result = await self.execute_backup(single_src, single_dest, False, True)

                if not result:
                    result_backup = False
                    break
                
            if result_backup:
                local_Main_Dwarf_dir = create_local_dwarf_dir(self.conn)
                if not local_Main_Dwarf_dir:
                    self._safe_ui(lambda: ui.notify(f"❌ Error accessing local Dwarf Directory", type="negative"))
                else:
                    # Synchonization : only one dialog — created at root level
                    with ui.context.client.layout:
                        with ui.dialog().props('persistent') as dialog, ui.card().style('width: 800px; max-width: none'):
                            label = ui.label(self.ScanningMessage)
                            spinner = ui.spinner(size="lg")
                            log = ui.log(max_lines=40).classes('w-full').style('height: 600px')
                            ui.button('Close', on_click=dialog.close)
                    dialog.open()  # show the dialog

                    for i, single_src in enumerate(all_src_dirs, 1):
                        session_name = os.path.basename(os.path.normpath(single_src))
                        single_dest = os.path.join(dest_dir, session_name)

                        try:
                            # use sync_dwarf_sessions
                            await  self.execute_sync_dwarf_sessions(single_src, single_dest, local_Main_Dwarf_dir, False, label, log, spinner)
                        except Exception as e:
                            label.text = "Error while synchronizing sessions!"
                            spinner.set_visibility(False)
                            ui.notify(f"❌ Error: {str(e)}", type="negative")
                            break

            self.cancel_btn.visible = False
            self.StartBackup.visible = True

            # Write journal for multi-session transfer
            session_names = ', '.join(os.path.basename(os.path.normpath(s)) for s in all_src_dirs)
            self._write_transfer_journal_multi(dest_dir, session_names, result_backup, total_copied, total_files)

            return

        # Check is Full Backup : the Astro Directory is used only
        isFullBackup = (src_dir == self.src_main_dir)
        if self.transfert_mode_select.value == "FTP" and self.dwarf_ip_sta_mode:
            isFullBackup = (src_dir == get_ftp_astroDir(self.dwarf_ip_sta_mode))

        # Dark download mode: always non-full-backup so CALI_FRAME is created
        # as a subfolder inside the chosen destination.
        if self.dest_override:
            isFullBackup = False

        print(f" is Full Backup task:  {isFullBackup}")

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
                if ftp_path_exists(self.dwarf_ip_sta_mode, dest_path):
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

    async def execute_backup(self, src_dir, dest_path, isFullBackup, is_multi = False):

        list_files = await self.get_files(src_dir, dest_path, isFullBackup)
        total_files = 0
        if list_files:
            total_files = len(list_files)

        if total_files == 0:
            self._safe_ui(lambda: self.progress_label.set_text("No files to copy."))
            return True
        else:
            self._safe_ui(lambda: self.progress_label.set_text(f"{'Full Backup, ' if isFullBackup else ''}Starting copying {total_files} files..."))
        self._safe_ui(lambda: ui.notify("Starting..."))

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
            self._safe_ui(lambda: self.progress_label.set_text("End of Backup"))
            self._safe_ui(lambda: ui.notify("✅ Backup complete and verified!"))
            self._write_transfer_journal(dest_path, src_dir, result=True)

            # Dark download mode: just a file copy — no session scan needed
            if self.dest_override:
                return result

            if not is_multi:
                await self._execute_sync_with_optional_dialog(src_dir, dest_path, isFullBackup)
        else:
            self._safe_ui(lambda: self.progress_label.set_text("Backup interrupted!"))
            self._write_transfer_journal(dest_path, src_dir, result=False)

        return result

    async def _execute_sync_with_optional_dialog(self, src_dir, dest_path, isFullBackup):
        """Run the post-copy scan — with dialog if page is still open, silently if not."""
        local_Main_Dwarf_dir = create_local_dwarf_dir(self.conn)
        if not local_Main_Dwarf_dir:
            self._safe_ui(lambda: ui.notify("❌ Error accessing local Dwarf Directory", type="negative"))
            self._set_progress('error', 0, 0, error="No local Dwarf directory")
            return

        # Try to create the scan dialog at root level — survives page navigation
        try:
            with ui.context.client.layout:
                with ui.dialog().props('persistent') as dialog, ui.card().style('width: 800px; max-width: none'):
                    label   = ui.label(self.ScanningMessage)
                    spinner = ui.spinner(size="lg")
                    log     = ui.log(max_lines=25).classes('w-full').style('height: 450px;')
                    ui.button('Close', on_click=dialog.close)
            dialog.open()
            await self.execute_sync_dwarf_sessions(src_dir, dest_path, local_Main_Dwarf_dir, isFullBackup, label, log, spinner)
        except RuntimeError:
            # Page was navigated away — run scan silently without any UI
            print("[Transfer] Page gone — running post-copy scan silently")
            try:
                await self.execute_sync_dwarf_sessions(src_dir, dest_path, local_Main_Dwarf_dir, isFullBackup,
                                                       label=None, log=None, spinner=None)
            except Exception as e:
                print(f"[Transfer] Silent scan error: {e}")

    async def execute_sync_dwarf_sessions(self, src_dir, dest_path, local_Main_Dwarf_dir, isFullBackup, label, log, spinner):

        def _ui(fn):
            """Call UI function only if label/spinner exist (page may be gone)."""
            try:
                if fn: fn()
            except Exception:
                pass

        try:
            _ui(lambda: ui.notify("Starting Local Sync ..."))
            self._set_progress('scanning', 0, 0, current_file="🔄 Syncing session files...")
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

            _ui(lambda: ui.notify("Starting Analysis ..."))
            self._set_progress('scanning', 0, 0, current_file="🔍 Analysing backup drive...")

            local_Dwarf_dir = get_local_dwarf_dir(self.conn, self.DwarfId)
            local_Dwarf_session = ""
            if session_name:
               local_Dwarf_session = os.path.join(local_Dwarf_dir, session_name) 
            if session_name.startswith("RESTACKED"):
                restacked_session = os.path.join("RESTACKED", session_name)
                local_Dwarf_session = os.path.join(local_Dwarf_dir, restacked_session)
            if session_name.startswith("STARTRAILS"):
                startrails_session = os.path.join("STARTRAILS", session_name)
                local_Dwarf_session = os.path.join(local_Dwarf_dir, startrails_session)
            print(local_Dwarf_session)

            total_dwarf, deleted_dwarf, _ = await run.io_bound(scan_backup_folder, DB_NAME, local_Dwarf_dir, None, self.DwarfId, None, local_Dwarf_session, log)

            # In Repair mode the backup drive is unchanged — skip backup scan
            if self.mode != "Repair" and self.mode != "Merge" and dir_backup_session is not None:
                total_backup, deleted_backup, rebuild_result = await run.io_bound(scan_backup_folder, DB_NAME, self.backup_location, self.backup_astrodir, self.DwarfId, self.BackupId, dir_backup_session, log)
                _ui(lambda: ui.notify(f"✅ Analysis Complete: {total_backup} new sessions found on backup.", type="positive"))
                if rebuild_result["rebuilt"] > 0:
                    _ui(lambda: ui.notify(f"🔗 {rebuild_result['rebuilt']} manual session(s) re-linked.", type="positive"))
                if rebuild_result["skipped"] > 0:
                    _ui(lambda: ui.notify(f"⚠️ {rebuild_result['skipped']} manual session(s) could not be matched.", type="warning", timeout=8000))
            else:
                total_backup, deleted_backup, rebuild_result = 0, 0, {"rebuilt": 0, "skipped": 0, "errors": 0}

            _ui(lambda: spinner.set_visibility(False) if spinner else None)
            _ui(lambda: setattr(label, "text", self.EndScanningMessage) if label else None)
            _ui(lambda: ui.notify(f"✅ Analysis Complete: {total_dwarf} new sessions found on dwarf.", type="positive"))
            _ui(lambda: ui.notify(f"✅ Analysis Complete: {total_backup} new sessions found on backup.", type="positive"))
            # Retrieve copy totals saved separately (scanning status overwrites copied/total)
            totals = app.storage.general.get('transfer_copy_totals', {})
            prev_copied = totals.get('copied', 0)
            prev_total  = totals.get('total', 0)
            app.storage.general.pop('transfer_copy_totals', None)
            self._set_progress('done', prev_copied, prev_total,
                               current_file=f"✅ {prev_copied}/{prev_total} files — {total_dwarf} dwarf + {total_backup} backup sessions indexed")

        except Exception as e:
            _ui(lambda: spinner.set_visibility(False) if spinner else None)
            _ui(lambda: ui.notify(f"❌ Error: {str(e)}", type="negative"))
            self._set_progress('error', 0, 0, error=str(e))


    # ── Background transfer progress ──────────────────────────────────────────

    def _set_progress(self, status, copied, total, current_file="", error=""):
        """Write progress to general storage only — UI is updated by the polling timer."""
        data = {
            'status':       status,
            'copied':       copied,
            'total':        total,
            'current_file': current_file,
            'error':        error,
        }
        # Use fixed key — client_id changes on navigation so don't use it
        try:
            app.storage.general['transfer_progress'] = data
        except Exception as e:
            print(f"[Transfer] Storage write error: {e}")
        # UI updates are handled by the polling timer — no with self.client: needed
        # (entering client context triggers drawer JS requests which timeout)

    def _get_stored_progress(self):
        """Read last known progress from general storage."""
        try:
            return app.storage.general.get('transfer_progress', None)
        except Exception:
            return None

    def _safe_ui(self, fn):
        """Call a UI-updating lambda safely — swallow errors if page is gone."""
        try:
            fn()
        except Exception:
            pass

    def _restore_transfer_state(self):
        """Called on page load — restore last known transfer state."""
        p = self._get_stored_progress()
        if p:
            self._show_bg_progress(True)
            self._update_bg_progress_ui(p)
            # Clear final states after showing to user
            if p.get('status') in ('done', 'error', 'cancelled'):
                ui.timer(5.0, lambda: app.storage.general.pop('transfer_progress', None), once=True)

    def _poll_transfer_progress(self):
        """Called every second by ui.timer — syncs UI from storage on page return."""
        try:
            p = self._get_stored_progress()
            if p:
                self._show_bg_progress(True)
                self._update_bg_progress_ui(p)
                if p['status'] in ('done', 'error', 'cancelled'):
                    self._progress_timer.deactivate()
                elif p['status'] == 'copy_done':
                    pass  # keep timer running — sync phase still to come
        except Exception:
            self._progress_timer.cancel()

    def _write_transfer_journal_multi(self, dest_dir: str, session_names: str, result: bool, copied: int, total: int):
        """Write journal for a multi-session transfer — overrides progress-based counts."""
        import json as _json
        from datetime import datetime as _dt
        try:
            journal_dir = self.backup_path if self.backup_path and os.path.isdir(self.backup_path) else dest_dir
            if not journal_dir or not os.path.isdir(journal_dir):
                return
            journal_path = os.path.join(journal_dir, "transfer_journal.json")
            history = []
            if os.path.isfile(journal_path):
                try:
                    with open(journal_path, encoding='utf-8') as f:
                        data = _json.load(f)
                    history = data if isinstance(data, list) else [data]
                except Exception:
                    history = []
            dwarf_name  = next((name for did, name in self.dwarf_options  if did == self.DwarfId),  str(self.DwarfId))
            backup_name = next((name for bid, name, *_ in self.backup_options if bid == self.BackupId), str(self.BackupId))
            entry = {
                "timestamp":    _dt.now().isoformat(timespec='seconds'),
                "result":       "ok" if result else "interrupted",
                "session":      session_names,
                "src":          dest_dir,
                "dest":         dest_dir,
                "copied":       copied,
                "total":        total,
                "error":        "" if result else f"Interrupted after {copied}/{total} files",
                "mode":         f"{self.mode} (multi)",
                "dwarf_id":     self.DwarfId,
                "dwarf_name":   dwarf_name,
                "backup_id":    self.BackupId,
                "backup_name":  backup_name,
            }
            history.insert(0, entry)
            history = history[:50]
            with open(journal_path, 'w', encoding='utf-8') as f:
                _json.dump(history, f, indent=2)
            print(f"[Transfer] Multi journal updated: {journal_path}")
        except Exception as e:
            print(f"[Transfer] Multi journal write error: {e}")

    def _write_transfer_journal(self, dest_path: str, src_dir: str, result: bool):
        """Append to transfer_journal.json at the root of the backup drive.

        The journal is a list of the last 50 transfers — newest first.
        Always written to the backup drive:
          - Archive / Darks  : backup_path or dest_path
          - Restore / Merge  : backup_path or src_dir
        """
        import json as _json
        from datetime import datetime as _dt
        try:
            p = app.storage.general.get('transfer_progress', {}) or {}

            # Determine journal directory — always the backup root
            journal_dir = self.backup_path if self.backup_path and os.path.isdir(self.backup_path) else None
            if not journal_dir:
                if self.mode in ('Archive', 'Darks'):
                    journal_dir = dest_path
                else:
                    journal_dir = src_dir
            if not journal_dir or not os.path.isdir(journal_dir):
                print(f"[Transfer] Journal: no valid backup dir found, skipping.")
                return

            journal_path = os.path.join(journal_dir, "transfer_journal.json")

            # Load existing history
            history = []
            if os.path.isfile(journal_path):
                try:
                    with open(journal_path, encoding='utf-8') as f:
                        data = _json.load(f)
                        # Support both old single-entry format and new list format
                        history = data if isinstance(data, list) else [data]
                except Exception:
                    history = []

            # Prepend new entry
            dwarf_name  = next((name for did, name in self.dwarf_options  if did == self.DwarfId),  str(self.DwarfId))
            backup_name = next((name for bid, name, *_ in self.backup_options if bid == self.BackupId), str(self.BackupId))
            # Determine session name — more descriptive than just basename(src_dir)
            src_basename = os.path.basename(src_dir.rstrip('/\\'))
            if src_dir == self.src_main_dir or src_dir == self.dest_main_dir:
                session_name = f"(Full Backup — {src_basename})"
            elif src_basename:
                session_name = src_basename
            else:
                session_name = src_dir

            entry = {
                "timestamp":    _dt.now().isoformat(timespec='seconds'),
                "result":       "ok" if result else "interrupted",
                "session":      session_name,
                "src":          src_dir,
                "dest":         dest_path,
                "copied":       p.get('copied', 0),
                "total":        p.get('total', 0),
                "error":        p.get('error', '') if not result else '',
                "mode":         self.mode,
                "dwarf_id":     self.DwarfId,
                "dwarf_name":   dwarf_name,
                "backup_id":    self.BackupId,
                "backup_name":  backup_name,
            }
            history.insert(0, entry)

            # Keep only last 50
            history = history[:50]

            with open(journal_path, 'w', encoding='utf-8') as f:
                _json.dump(history, f, indent=2)
            print(f"[Transfer] Journal updated: {journal_path} ({len(history)} entries)")
        except Exception as e:
            print(f"[Transfer] Journal write error: {e}")

    def _show_bg_progress(self, visible):
        self.bg_progress.visible = visible
        self.bg_status_label.visible = visible

    def _update_bg_progress_ui(self, p):
        status  = p['status']
        copied  = p['copied']
        total   = p['total']
        current = p.get('current_file', '')
        error   = p.get('error', '')

        if total > 0:
            self.bg_progress.value = copied / total
        fname = os.path.basename(current) if current else ""
        if status == 'running':
            pct = f" ({round(copied/total*100)}%)" if total > 0 else ""
            self.bg_status_label.text = f"📦 Transferring: {copied}/{total}{pct} — {fname}"
            self._show_bg_progress(True)
            self.StartBackup.visible = False
            self.cancel_btn.visible = True
        elif status == 'copy_done':
            self.bg_status_label.text = f"🔄 Copy complete ({copied}/{total} files) — Syncing database..."
            self.bg_progress.value = 1.0
            self.StartBackup.visible = False
            self.cancel_btn.visible = False
        elif status == 'scanning':
            self.bg_status_label.text = current
            self._show_bg_progress(True)
            self.bg_progress.value = 0
            self.StartBackup.visible = False
            self.cancel_btn.visible = False
        elif status == 'done':
            self.bg_status_label.text = f"✅ Transfer complete: {copied}/{total} files copied successfully"
            self.bg_progress.value = 1.0
            self.StartBackup.visible = True
            self.cancel_btn.visible = False
        elif status == 'cancelled':
            self.bg_status_label.text = f"🚫 Transfer cancelled after {copied}/{total} files"
            self.StartBackup.visible = True
            self.cancel_btn.visible = False
        elif status == 'error':
            self.bg_status_label.text = f"❌ Error after {copied}/{total}: {error}"
            self.StartBackup.visible = True
            self.cancel_btn.visible = False

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
        total_files = len(all_files)
        self._set_progress('running', 0, total_files)
        self._show_bg_progress(True)
        self._progress_timer.activate()
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
                    self._safe_ui(lambda: self.notify_me.refresh("Backup cancelled."))
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
                    result_copy =await run.io_bound(safe_copy2, src_file, dest_file)
                    try:                 
                        if not result_copy:
                             raise Exception(f"Copy failed without exception: {src_file}")

                    except OSError as ose:
                        winerror = getattr(ose, 'winerror', None)
                        errno = getattr(ose, 'errno', None)
                        if winerror == 112 or errno == 28:  # 28 = ENOSPC (Linux)
                            msg = f"❌ Disk full — transfer stopped after {verified_files}/{total_files} files."
                            self._safe_ui(lambda m=msg: self.notify_me.refresh(m))
                            self._safe_ui(lambda m=msg: ui.notify(m, type="negative", timeout=0))
                            self._set_progress('error', verified_files, total_files, error="Disk full")
                            result = False
                            break
                        raise  # other OSError — let outer except handle it
                    except xception as e:
                        raise Exception(f"Error during copy: {src_file}") from e

                verified_files += 1
                self._safe_ui(lambda: setattr(progress_bar, "value", round(progress)))
                self._set_progress('running', verified_files, total_files, src_file)


            if self.cancel_backup:
                self._set_progress('cancelled', verified_files, total_files)
            elif verified_files == total_files:
                self._safe_ui(lambda: self.notify_me.refresh("✅ Backup complete and verified!"))
                self._set_progress('done', verified_files, total_files)
                result = True
            else:
                self._safe_ui(lambda: self.notify_me.refresh("⚠️ Backup incomplete due to verification failure."))
                self._set_progress('error', verified_files, total_files, error="Verification failure")

        except Exception as e:
            if isinstance(e, OSError) and getattr(e, 'winerror', None) == 112:
                error_msg = f"Disk full: {os.path.basename(src_file)}"
            else:
                error_msg = f"{os.path.basename(src_file)}: {e}"
            self._safe_ui(lambda: self.notify_me.refresh(f"❌ {error_msg}"))
            self._set_progress('error', verified_files, total_files, error=error_msg)
            traceback.print_exc()
            self._safe_ui(lambda: setattr(progress_bar, "value", 0))
            result = False

        finally:
            # Close FTP connection if it was opened
            if ftp_ctx:
                ftp_ctx.__exit__(None, None, None)      
            # Close SFTP connection if it was opened
            #if sftp_ctx:
            #   sftp_ctx.__exit__(None, None, None)      

        self._safe_ui(lambda: setattr(cancel_button, "visible", False))
        self._safe_ui(lambda: setattr(self.StartBackup, "visible", True))
        return result

    def get_explore_url(self):
        if self.BackUrl and self.BackUrl != "/Mosaic":
            # Generic back URL — decode if URL-encoded (e.g. from Explore)
            import urllib.parse
            decoded = urllib.parse.unquote(self.BackUrl)
            return decoded
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
            back_url = urllib.parse.quote(f"/Backup?BackupId=", safe='')
            if self.DwarfId:
                explore_url = f"/Explore?BackupDriveId={self.BackupDriveId}&DwarfId={self.DwarfId}&mode=backup&back_url={back_url}"
            else:
                explore_url = f"/Explore?BackupDriveId={self.BackupDriveId}&mode=backup&back_url={back_url}"
        elif self.DwarfId:
            back_url = urllib.parse.quote(f"/Dwarf?DwarfId=", safe='')
            explore_url = f"/Explore?DwarfId={self.DwarfId}&mode=dwarf&back_url={back_url}"
        else:
            explore_url = f"/Explore?mode=dwarf"
        print(explore_url)
        return explore_url