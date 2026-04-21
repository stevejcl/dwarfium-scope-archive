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
from api.dwarf_backup_fct import scan_backup_folder, win_long_path, sync_dwarf_sessions, create_local_dwarf_dir, get_local_dwarf_dir

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
        nbcol = 3 if self.BackUrl else 1
        self._restore_transfer_state_1()

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
            self.progress = ui.linear_progress(value=0, show_value=False).classes("w-full")
            self.CancelBackup = self.cancel_btn = ui.button('Cancel Backup', on_click=lambda: self.cancel())
            self.cancel_btn.visible = False
            self.StartBackup = ui.button('Start Backup', on_click=lambda:self.start_backup())
            self.cancel_backup = False
            ui.label(
                "💡 Transfer runs in the background — you can navigate away and return. "
                "Progress is shown in the menu badge."
            ).classes("text-sm text-blue-500 mt-2")

            # Background task progress panel — shown when a transfer is running
            # and reconnects automatically when user returns to this page
            ui.separator()
            self.bg_status_label = self.progress_label  # reuse same label
            self.bg_progress = self.progress              # reuse same bar
            # Persistent banner shown when a transfer is running in background
            with ui.element('div').classes('w-full') as self._running_banner:
                ui.label("🔄 A transfer is running in the background — you can navigate away but cannot start a new transfer until it completes.").classes("text-sm text-orange-500 bg-orange-50 rounded p-2 w-full text-center")
            self._running_banner.visible = False

            # Emergency reset button — shown when transfer appears stuck
            self._reset_btn = ui.button(
                "⚠️ Force Reset Transfer State",
                on_click=self._force_reset_transfer
            ).props("flat color=negative").classes("text-xs mt-2")
            self._reset_btn.visible = False

            # Poll progress storage every second
            self._progress_timer = ui.timer(1.0, self._poll_transfer_progress)

        self.populate_dwarf_filter()
        self._restore_transfer_state_2()
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
        # Prevent starting a new transfer while one is active
        try:
            p = app.storage.general.get('transfer_progress', None)
        except Exception:
            p = None
        if p and p.get('status') in ('running', 'copy_done', 'scanning'):
            status = p.get('status')
            copied = p.get('copied', 0)
            total  = p.get('total', 0)
            if status == 'running':
                msg = f"A transfer is already running ({copied}/{total} files copied)."
            elif status == 'copy_done':
                msg = f"Copy complete ({copied}/{total} files) — database sync in progress."
            else:
                msg = "Database sync in progress."
            with ui.dialog().props('persistent') as dlg, ui.card().classes('p-6 gap-4'):
                ui.label("⚠️ Transfer in progress").classes("text-lg font-bold text-orange-500")
                ui.label(f"{msg} Please wait for it to complete before starting a new one.").classes("text-gray-600")
                ui.button("OK", on_click=dlg.close).props("color=primary")
            dlg.open()
            return

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
            background_tasks.create(self._run_multi_backup(all_src_dirs, dest_dir))
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
                    background_tasks.create(self.execute_backup(src_dir, dest_path, isFullBackup))
                    return
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
                # Launch as background task — user can navigate away
                background_tasks.create(self.execute_backup(src_dir, dest_path, isFullBackup))
                return  # don't reset buttons — background task manages them

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
            background_tasks.create(self.execute_backup(self.input_src_dir.value, dest_path, isFullBackup))
        else:
            self._safe_ui(lambda: self.progress_label.set_text("Backup canceled."))
            self.cancel_btn.visible = False
            self.StartBackup.visible = True

    @background_tasks.await_on_shutdown
    async def _run_multi_backup(self, all_src_dirs, dest_dir):
        """Background task for multi-session transfer."""
        self._safe_ui(lambda: setattr(self.cancel_btn, 'visible', True))
        self._safe_ui(lambda: setattr(self.StartBackup, 'visible', False))
        total = len(all_src_dirs)
        result_backup = True
        total_copied = 0
        total_files  = 0

        for i, single_src in enumerate(all_src_dirs, 1):
            if self.cancel_backup:
                self._set_progress('cancelled', total_copied, total_files)
                result_backup = False
                break
            session_name = os.path.basename(os.path.normpath(single_src))
            single_dest  = os.path.join(dest_dir, session_name)
            self._set_progress('running', total_copied, total_files,
                               current_file=f"[{i}/{total}] {session_name}")
            result = await self.execute_backup(single_src, single_dest, False, True)
            # Accumulate totals from storage after each session
            p = app.storage.general.get('transfer_progress', {})
            total_copied += p.get('copied', 0)
            total_files  += p.get('total',  0)
            if not result:
                result_backup = False
                break

        if result_backup:
            local_Main_Dwarf_dir = create_local_dwarf_dir(self.conn)
            if not local_Main_Dwarf_dir:
                self._safe_ui(lambda: ui.notify("❌ Error accessing local Dwarf Directory", type="negative"))
            else:
                label = spinner = log = dialog = None
                try:
                    if self.client.id in [c.id for c in Client.instances.values()]:
                        with self.client:
                            with ui.context.client.layout:
                                with ui.dialog().props('persistent') as dialog, ui.card().style('width: 800px; max-width: none'):
                                    label   = ui.label(self.ScanningMessage)
                                    spinner = ui.spinner(size="lg")
                                    log     = ui.log(max_lines=40).classes('w-full').style('height: 600px')
                                    ui.button('Close', on_click=dialog.close)
                                dialog.open()
                except Exception:
                    pass

                for i, single_src in enumerate(all_src_dirs, 1):
                    session_name = os.path.basename(os.path.normpath(single_src))
                    single_dest  = os.path.join(dest_dir, session_name)
                    try:
                        await self.execute_sync_dwarf_sessions(single_src, single_dest, local_Main_Dwarf_dir, False, label, log, spinner)
                    except Exception as e:
                        print(f"[Multi sync error] {e}")
                        break

        self._set_progress('done', total_copied, total_files,
                           current_file=f"✅ {total} sessions transferred")
        self._safe_ui(lambda: setattr(self.cancel_btn, 'visible', False))
        self._safe_ui(lambda: setattr(self.StartBackup, 'visible', True))
        self._safe_ui(lambda: setattr(self._running_banner, 'visible', False))

    @background_tasks.await_on_shutdown
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
        # Save current dropdown values so Transfer page can restore them after reload
        try:
            app.storage.general['dwarfId']  = self.DwarfId
            app.storage.general['backupId']  = self.BackupId
            app.storage.general['mode']  = self.mode
            app.storage.general['session']  = self.session
            app.storage.general['dest_override']  = self.dest_override
            if self.mode == "Archive":
                app.storage.general['transfer_last_dest'] = self.input_dest_dir.value
            else:
                app.storage.general['transfer_last_src']  = self.input_src_dir.value or src_dir
        except Exception:
            pass

        # Create copy as a separate task and shield it from cancellation
        _copy_task = asyncio.ensure_future(self.copy_with_progress_async(list_files, self.progress, self.cancel_btn))
        try:
            result = await asyncio.shield(_copy_task)
        except asyncio.CancelledError:
            print("[Transfer] Shielded copy from cancellation — waiting for completion...")
            result = await _copy_task  # wait for the already-running task

        if result:
            self._safe_ui(lambda: self.progress_label.set_text("End of Backup"))
            self._safe_ui(lambda: ui.notify("✅ Backup complete and verified!"))

            # Dark download mode: just a file copy — no session scan needed
            if self.dest_override:
                return result

            if not is_multi:
                await self._execute_sync_with_optional_dialog(src_dir, dest_path, isFullBackup)
        else:
            self._safe_ui(lambda: self.progress_label.set_text("Backup interrupted!"))

        return result

    async def _execute_sync_with_optional_dialog(self, src_dir, dest_path, isFullBackup):
        """Run the post-copy scan — with dialog if page is still open, silently if not."""
        local_Main_Dwarf_dir = create_local_dwarf_dir(self.conn)
        if not local_Main_Dwarf_dir:
            self._safe_ui(lambda: ui.notify("❌ Error accessing local Dwarf Directory", type="negative"))
            self._set_progress('error', 0, 0, error="No local Dwarf directory")
            return

        # Try to show scan dialog — run silently if client is gone
        label = spinner = log = dialog = None
        try:
            if self.client.id in [c.id for c in Client.instances.values()]:
                with self.client:
                    with ui.context.client.layout:
                        with ui.dialog().props('persistent') as dialog, ui.card().style('width: 800px; max-width: none'):
                            label   = ui.label(self.ScanningMessage)
                            spinner = ui.spinner(size="lg")
                            log     = ui.log(max_lines=25).classes('w-full').style('height: 450px;')
                            ui.button('Close', on_click=dialog.close)
                        dialog.open()
        except Exception:
            print("[Transfer] Client gone — running post-copy scan silently")
            label = spinner = log = dialog = None

        # Shield sync from cancellation — must complete even on shutdown
        try:
            await asyncio.shield(self.execute_sync_dwarf_sessions(src_dir, dest_path, local_Main_Dwarf_dir, isFullBackup, label, log, spinner))
        except asyncio.CancelledError:
            # Shielded — wait for it to finish anyway
            await self.execute_sync_dwarf_sessions(src_dir, dest_path, local_Main_Dwarf_dir, isFullBackup, label, log, spinner)
        
        if dialog:
            try:
                with self.client:
                    spinner.set_visibility(False)
            except Exception:
                pass

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
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, sync_dwarf_sessions, self.DwarfId, dir_parent_session, local_Main_Dwarf_dir, session_name, log)

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

            total_dwarf, deleted_dwarf, _ = await loop.run_in_executor(None, scan_backup_folder, DB_NAME, local_Dwarf_dir, None, self.DwarfId, None, local_Dwarf_session, log)

            # In Repair mode the backup drive is unchanged — skip backup scan
            if self.mode != "Repair" and self.mode != "Merge" and dir_backup_session is not None:
                total_backup, deleted_backup, rebuild_result = await loop.run_in_executor(None, scan_backup_folder, DB_NAME, self.backup_location, self.backup_astrodir, self.DwarfId, self.BackupId, dir_backup_session, log)
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
        """Write progress to general storage AND push to UI via client context."""
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

    def _restore_transfer_state_1(self):
        """Called before UI build — restore DwarfId/BackupId/mode/session from storage."""
        try:
            mode = app.storage.general.get('mode', '')
            if not mode:
                return
            else:
                self.mode = mode
                
                dwarfId = app.storage.general.get('dwarfId', None)
                if dwarfId:
                    self.DwarfId = dwarfId
                    self.DwarfId_Init = dwarfId
                backupId = app.storage.general.get('backupId', None)
                if backupId:
                    self.BackupId = backupId
                    self.BackupId_Init = backupId
                session = app.storage.general.get('session', '')
                if session:
                    self.session = session

                if self.mode == "Merge" or self.mode == "Repair" :
                    # Transfert Mosaic
                    last_src  = app.storage.general.get('transfer_last_src', '')
                    self.src_override = last_src
                    print(f"[Restore1] DwarfId={self.DwarfId} BackupId={self.BackupId} mode={self.mode} session={self.session} src_override={self.src_override}")
                else: 
                    # Transfert Dark Library
                    dest_override  = app.storage.general.get('dest_override', '')
                    if dest_override:
                        self.dest_override = dest_override
                        print(f"[Restore1] DwarfId={self.DwarfId} BackupId={self.BackupId} mode={self.mode} session={self.session} dest_override={self.dest_override}")
                    else:
                       # Normal Mode
                       print(f"[Restore1] DwarfId={self.DwarfId} BackupId={self.BackupId} mode={self.mode} session={self.session}")
        except Exception as e:
            print(f"[Restore1] Error: {e}")

    def _restore_transfer_state_2(self):
        """Called after UI build — restore src/dest dropdowns and progress."""
        try:
            mode = app.storage.general.get('mode', '')
            if not mode:
                return
            else:
                last_src  = app.storage.general.get('transfer_last_src', '')
                last_dest = app.storage.general.get('transfer_last_dest', '')
                dest_override  = app.storage.general.get('dest_override', '')
                if self.mode == "Archive" and not dest_override:
                    if last_dest and not self.input_dest_dir.value:
                        self.input_dest_dir.set_options([last_dest], value=last_dest)
                        print(f"[Restore2] dest restored: {last_dest}")
                elif self.mode == "Restore":
                    if last_src and not self.input_src_dir.value:
                        self.input_src_dir.set_options([last_src], value=last_src)
                        self.src_main_dir = os.path.dirname(last_src)
                        print(f"[Restore2] src restored: {last_src}")
                elif self.mode == "Merge" or self.mode == "Repair" :
                    if last_src and not self.input_src_dir.value:
                        self.input_src_dir.set_options([last_src], value=last_src)
                        self.src_main_dir = os.path.dirname(last_src)
                        print(f"[Restore2] src restored: {last_src}")
        except Exception as e:
            print(f"[Restore2] Error: {e}")

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

    def _force_reset_transfer(self):
        """Emergency reset — clears stuck transfer state."""
        app.storage.general.pop('transfer_progress', None)
        app.storage.general.pop('transfer_copy_totals', None)
        self._reset_btn.visible = False
        self._reset_progress_ui()
        ui.notify("Transfer state reset — you can start a new transfer.", type="warning")

    def _reset_progress_ui(self, clear_paths=True):
        """Reset progress UI to idle state and clear storage so badge disappears."""
        self.bg_status_label.text = "Idle..."
        self.bg_progress.value = 0
        self._show_bg_progress(False)
        app.storage.general.pop('transfer_progress', None)
        if clear_paths:
            app.storage.general.pop('transfer_last_src', None)
            app.storage.general.pop('transfer_last_dest', None)
            app.storage.general.pop('dwarfId', None)
            app.storage.general.pop('backupId', None)
            app.storage.general.pop('mode', None)
            app.storage.general.pop('session', None)
            app.storage.general.pop('dest_override', None)

    def _set_close_warning(self, active: bool):
        pass  # Native mode — close warning handled by app window closing event

    def _show_bg_progress(self, visible):
        pass  # progress and label are always visible — nothing to toggle

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
            self._running_banner.visible = True
        elif status == 'copy_done':
            self.bg_status_label.text = f"🔄 Copy complete ({copied}/{total} files) — Syncing database..."
            self.bg_progress.value = 1.0
            self.StartBackup.visible = False
            self.cancel_btn.visible = False
            self._running_banner.visible = True
        elif status == 'scanning':
            self.bg_status_label.text = current
            self._show_bg_progress(True)
            self.bg_progress.value = 0
            self.StartBackup.visible = False
            self.cancel_btn.visible = False
            self._reset_btn.visible = True
        elif status == 'done':
            self._reset_btn.visible = False
            self.bg_status_label.text = f"✅ Transfer complete: {copied}/{total} files copied successfully"
            self.bg_progress.value = 1.0
            self.StartBackup.visible = True
            self.cancel_btn.visible = False
            self._running_banner.visible = False
            self._set_close_warning(False)
            ui.timer(5.0, lambda: self._reset_progress_ui(clear_paths=True), once=True)
        elif status == 'cancelled':
            self.bg_status_label.text = f"🚫 Transfer cancelled after {copied}/{total} files"
            self.StartBackup.visible = True
            self.cancel_btn.visible = False
            self._running_banner.visible = False
            self._set_close_warning(False)
            ui.timer(5.0, lambda: self._reset_progress_ui(clear_paths=False), once=True)
        elif status == 'error':
            last = os.path.basename(current) if current else ""
            last_info = f" — last: {last}" if last else ""
            src  = app.storage.general.get('transfer_last_src', '')
            dest = app.storage.general.get('transfer_last_dest', '')
            path_info = f" | 📂 {src} → {dest}" if src and dest else ""
            self.bg_status_label.text = f"❌ Error after {copied}/{total}: {error}{last_info}{path_info}"
            self.StartBackup.visible = True
            self.cancel_btn.visible = False
            self._running_banner.visible = False
            # Keep paths in storage for retry — don't clear them

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
        self._safe_ui(lambda: self._set_close_warning(True))
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
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, ftp_download_file, ftp, src_file, dest_file)

                # --- LOCAL ➜ FTP (RESTORE) ---
                elif mode_use_ssh and is_restore:
                    await async_sftp_upload(self.dwarf_ip_sta_mode, src_file, dest_file, created_dirs_cache)

                # --- LOCAL ➜ LOCAL ---
                else:
                    os.makedirs(os.path.dirname(dest_file), exist_ok=True)
                    # Use run_in_executor directly — survives NiceGUI shutdown cancellation
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, shutil.copy2, src_file, dest_file)
                    # Skip size check if file missing — copy was interrupted (shutdown)
                    if os.path.exists(dest_file):
                        if os.path.getsize(src_file) != os.path.getsize(dest_file):
                            raise Exception("Size mismatch after copy")

                    # 🔒 Step 2 (Optional): Check hash for sensitive files
                    #if os.path.splitext(src_file)[1] in ['.fits', '.json', '.jpg']:
                    #    if file_hash(src_file) != file_hash(dest_file):
                    #        ui.notify.refresh(f"Checksum mismatch: {src_file}")
                    #        break

                verified_files += 1
                self._safe_ui(lambda p=progress: setattr(progress_bar, "value", round(p) / 100))
                self._set_progress('running', verified_files, total_files, src_file)


            if self.cancel_backup:
                self._set_progress('cancelled', verified_files, total_files)
            elif verified_files == total_files:
                # end task
                if (self.dest_override) :
                    self._safe_ui(lambda: self.notify_me.refresh("✅ Backup complete and verified!"))
                    self._set_progress('done', verified_files, total_files,
                               current_file=f"✅ {verified_files}/{total_files} files")
                else:
                    self._safe_ui(lambda: self.notify_me.refresh("✅ Backup complete and verified!"))
                    self._set_progress('copy_done', verified_files, total_files)
                    # Save copy totals separately — scanning status will overwrite copied/total
                    app.storage.general['transfer_copy_totals'] = {'copied': verified_files, 'total': total_files}
                result = True
            else:
                self._safe_ui(lambda: self.notify_me.refresh("⚠️ Backup incomplete due to verification failure."))
                self._set_progress('error', verified_files, total_files, error="Verification failure")

        except asyncio.CancelledError:
            # Task was cancelled — save progress so it can be resumed
            print(f"[Transfer] Copy cancelled after {verified_files}/{total_files} files")
            self._set_progress('error', verified_files, total_files, current_file=src_file if verified_files > 0 else '', error=f"Cancelled after {verified_files}/{total_files} files")
            raise  # re-raise so asyncio knows the task was cancelled
        except Exception as e:
            if isinstance(e, OSError) and getattr(e, 'winerror', None) == 112:
                error_msg = f"Disk full: {os.path.basename(src_file)}"
            else:
                error_msg = f"{os.path.basename(src_file)}: {e}"
            self._safe_ui(lambda: self.notify_me.refresh(f"❌ {error_msg}"))
            self._set_progress('error', verified_files, total_files, error=error_msg)
            traceback.print_exc()
            self._safe_ui(lambda: setattr(progress_bar, "value", 0.0))
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