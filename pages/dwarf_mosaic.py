from components.i18n import t
import webview
from nicegui import ui, app, run, Client

import os
import shutil
import threading
import tempfile
import traceback
import asyncio
from pathlib import Path
from components.menu import menu
from api.dwarf_backup_fct import get_local_dwarf_dir, print_log, win_long_path, get_session_detail, safe_copy2
from api.dwarf_backup_fct_mosaic import repair_mosaic_session, merge_mosaic, safe_progress
from api.dwarf_mosaic_check import (
    read_shots_info,
    check_mosaic_json_compatibility,
    detect_inversion,
    reorder_panels,
    format_session_summary,
    get_thumbnail_path,
    orientation_confidence_label,
)
from api.dwarf_backup_db import DB_NAME, connect_db, close_db
from components.db_page_mixin import DbPageMixin
from api.dwarf_backup_db_api import get_dwarf_Names, get_dwarf_detail, get_backupDrive_list_dwarfId, get_backupDrive_detail, get_sessions_dwarf, get_sessions_backup, get_session_dwarf_details, get_session_backup_details
from api.dwarf_backup_db_api import get_dwarf_sessions_error
from components.win_log import WinLog
from api.repair_session_manager import RepairSessionManager
from components.repair_history_dialog import check_and_show_history
from components.mosaic_restore_dialog import open_mosaic_restore_dialog
from api.dwarf_backup_fct_mosaic import rebuild_mosaic_info, backup_merge_files, restore_merge_files, cleanup_backup
from components.stitch_params_editor import get_stitch_params

# =========================================================
# PAGE + APP CLASS
# =========================================================

@ui.page('/Mosaic')
async def mosaic_page(
    client: Client,
    DwarfId: int = None,
    session: str = None,
    mode: str = 'Repair',
    BackupId: int = None,
    back_url: str = None,
):

    menu(t("page_mosaic"))
    await ui.context.client.connected(timeout=10.0)
    ui.context.mosaic_app = MosaicApp(client, DB_NAME, DwarfId=DwarfId, Session=session, BackUrl=back_url, BackupId=BackupId)


class MosaicApp(DbPageMixin):
    def __init__(self, client: Client, database, DwarfId=None, Session=None, Mode="Repair", BackupId=None,  BackUrl=None):
        self.client = client
        self.database = database
        self.dwarfs = []

        self.DwarfId = DwarfId
        self.DwarfId_Init = DwarfId
        self.BackupId = BackupId
        self.BackupId_Init = BackupId
        self.dwarf_options = []
        self.backup_options = []
        self.backup_data = {}

        # Backup drive details
        self.backup_location = ''
        self.backup_astrodir = ''
        self.backup_path = ''

        # Source selection per picker: 'Dwarf' or 'Backup'
        self.primary_source = 'Dwarf'
        self.secondary_source = 'Dwarf'

        self.session = Session          # primary session (pre-filled if coming from Explore)
        import urllib.parse as _up
        self.BackUrl = _up.unquote(BackUrl) if BackUrl else BackUrl

        # Directories
        self.primary_session_dir = ''   # Session to repair or merge INTO
        self.secondary_session_dir = '' # Session used as repair/merge source
        self.output_dir = ''            # Temporary output directory

        self.primary_main_dir = ''      # Root astro dir for primary picker
        self.secondary_main_dir = ''    # Root astro dir for secondary picker

        self.detail_session_primary_name = ""
        self.detail_session_primary = ""
        self.session_select_thumbnail_primary = None
        self.session_select_image_primary = None

        self.detail_session_secondary_name = ""
        self.detail_session_secondary = ""
        self.session_select_thumbnail_secondary = None
        self.session_select_image_secondary = None

        self.dwarf_astroDir = ''
        self.dwarf_ip_sta_mode = ''
        self.dwarf_type = None

        self.mode = "Merge"
        self.cancel_process = threading.Event()
        self.cancel_process.clear()

        # ── Repair/Merge session tracking ──────────────────────────────
        # RepairSessionManager is initialised lazily once output_dir is known
        self.repair_mgr: RepairSessionManager | None = None
        self._current_entry_id: str | None = None   # ID of the running action
        # Error sessions (Mosaic only) — populated when Dwarf is selected in Repair mode
        self.error_sessions: list = []

        self.build_ui()

    # ------------------------------------------------------------------ #
    #  UI BUILD                                                            #
    # ------------------------------------------------------------------ #

    def build_ui(self):
        self.conn = connect_db(self.database)
        self.register_conn_close()
        sizeBTN='w-56'
        sizeBTN2='w-64'

        nbcol = 3 if self.BackUrl else 1
        # parameter for stitch params
        self.stitch_params = get_stitch_params(self.conn)

        # ── Header card ──────────────────────────────────────────────────
        with ui.card().classes("w-full p-4 mt-2 items-center") as self.main_ui:
            with ui.grid(columns=nbcol).classes("items-center"):
                if self.BackUrl:
                    ui.button(t("back_btn"), on_click=lambda: ui.navigate.to(self.BackUrl)).classes("justify-self-start")
                self.mode_toggle = ui.toggle(
                    {'Merge': t('merge_mode'), 'Repair': t('repair_mode')},
                    value=self.mode, on_change=self.switch_mode
                ).classes("col-span-1 justify-self-center")

            self.main_label = ui.label(
                t("mosaic_merge_desc")
            ).classes("text-sm text-gray-500")

            # Dwarf + Backup selector row
            with ui.grid(columns=2).classes("w-full gap-4"):
                with ui.row().classes('items-start gap-4'):
                    with ui.column().classes('gap-1'):
                        ui.label(t("select_dwarf")).classes("text-lg font-semibold")
                        self.dwarf_filter = ui.select(options=[], on_change=self.on_dwarf_filter_change).props('outlined')
                    with ui.column().classes('gap-1 justify-center pt-6'):
                        with ui.row().classes('items-center gap-2'):
                            self.usb_status_label = ui.label("").classes('')
                            self.refresh_btn = (
                                ui.button(icon='refresh', on_click=self.check_dir_dwarf)
                                .props('flat round dense')
                                .bind_visibility_from(self.usb_status_label, 'text', lambda v: (v == t("path_not_detected")))
                            )
                with ui.row().classes('items-start gap-4'):
                    with ui.column().classes('gap-1'):
                        ui.label(t("backup_drive")).classes("text-lg font-semibold")
                        self.backup_filter = ui.select(options=[], on_change=self.on_backup_filter_change).props('outlined')
                    with ui.column().classes('gap-1 justify-center pt-6'):
                        self.backup_status_label = ui.label("").classes('')

        # ── Primary session card ─────────────────────────────────────────
        with ui.card().classes("w-full p-4 mt-1 items-center"):
            self.primary_session_label = ui.label(t("primary_session")).classes("text-lg font-semibold")
            with ui.row().classes("items-center gap-2"):
                ui.label(t("data_source")).classes("text-sm text-gray-500")
                self.primary_source_toggle = ui.toggle(
                    {'Dwarf': t('dwarf_device'), 'Backup': t('menu_backup_settings')},
                    value='Dwarf', on_change=self.on_primary_source_change,
                ).props('dense')
            with ui.row().classes('w-full items-center gap-4'):
                self.input_primary_dir = (
                    ui.select(
                        label=t("primary_session_dir"),
                        value=self.primary_session_dir,
                        options=[self.primary_session_dir],
                        on_change=self.on_primary_dir_change,
                    )
                    .props('stack-label outlined')
                    .classes("flex-grow min-w-[300px] overflow-x-auto whitespace-nowrap")
                )
                ui.button(t("select_primary"), on_click=self.select_primary_folder).classes(sizeBTN2)

            with ui.row().classes('w-full items-start'):
                # LEFT COLUMN
                with ui.column().classes('w-2/3'):
                    self.detail_session_primary_name = ui.label("").classes('text-blue-800')
                    self.detail_session_primary = ui.label("").style('white-space: pre-line').classes('text-purple-600')

                # RIGHT COLUMN
                with ui.column().classes('w-1/4'):
                    self.thumbnail_primary = ui.image(self.session_select_thumbnail_primary) \
                                     .classes('w-40 h-auto rounded-lg cursor-pointer hover:opacity-80') \
                                     .on('click', lambda: self._show_full_image(self.session_select_image_primary))
        # ── Secondary session card ───────────────────────────────────────
        with ui.card().classes("w-full p-4 mt-1 items-center"):
            self.secondary_session_label = ui.label(t("secondary_session")).classes("text-lg font-semibold")
            with ui.row().classes("items-center gap-2"):
                ui.label(t("data_source")).classes("text-sm text-gray-500")
                self.secondary_source_toggle = ui.toggle(
                    {'Dwarf': t('dwarf_device'), 'Backup': t('menu_backup_settings')},
                    value='Dwarf', on_change=self.on_secondary_source_change,
                ).props('dense')
            with ui.row().classes('w-full items-center gap-4'):
                self.input_secondary_dir = (
                    ui.select(
                        label=t("secondary_session_dir"),
                        value=self.secondary_session_dir,
                        options=[self.secondary_session_dir],
                        on_change=self.on_secondary_dir_change,
                    )
                    .props('stack-label outlined')
                    .classes("flex-grow min-w-[300px] overflow-x-auto whitespace-nowrap")
                )
                ui.button(t("select_secondary"), on_click=self.select_secondary_folder).classes(sizeBTN2)

            with ui.row().classes('w-full items-start'):
                # LEFT COLUMN
                with ui.column().classes('w-2/3'):
                    self.detail_session_secondary_name = ui.label("").classes('text-blue-800')
                    self.detail_session_secondary = ui.label("").style('white-space: pre-line').classes('text-purple-600')

                # RIGHT COLUMN
                with ui.column().classes('w-1/4'):
                    self.thumbnail_secondary = ui.image(self.session_select_thumbnail_secondary) \
                                     .classes('w-40 h-auto rounded-lg cursor-pointer hover:opacity-80') \
                                     .on('click', lambda: self._show_full_image(self.session_select_image_secondary))

        # ── Error sessions card (Repair mode only) ──────────────────────
        with ui.card().classes("w-full p-4 mt-1 items-center") as self.error_sessions_card:
            with ui.row().classes("items-center gap-2"):
                ui.label(t("mosaic_in_error")).classes("text-lg font-semibold")
                ui.label(t("no_stacked")).classes("text-sm text-gray-500")
            self.error_session_select = (
                ui.select(
                    label=t("select_session_repair"),
                    options=[],
                    on_change=lambda: None,
                )
                .props("stack-label outlined")
                .classes("min-w-[600px] w-auto overflow-x-auto whitespace-nowrap")
            )
            ui.button(
                t("use_as_secondary"),
                on_click=self.use_error_session_as_secondary,
            ).classes("w-64")
        self.error_sessions_card.set_visibility(self.mode == "Repair")

        # ── Output / temp directory card ─────────────────────────────────
        with ui.card().classes("w-full p-4 mt-1 items-center"):
            ui.label(t("output_dir")).classes("text-lg font-semibold")
            self.input_output_dir = (
                ui.select(
                    label=t("output_directory"),
                    value=self.output_dir,
                    options=[self.output_dir],
                    on_change=lambda: None,
                )
                .props('stack-label outlined')
                .classes("min-w-[600px] w-auto overflow-x-auto whitespace-nowrap")
            )
            self.copy_intermediate_files = ui.checkbox(t("copy_fits_jpg"))
            with ui.row():
                ui.button(t("select_output"), on_click=self.select_output_folder).classes(sizeBTN)
                ui.button(t("create_temp_folder"), on_click=self.create_temp_folder).classes(sizeBTN)

        # ── Action card ──────────────────────────────────────────────────
        with ui.card().classes("w-full p-4 mt-1 mb-8 items-center"):
            self.progress_label = ui.label(t("idle"))
            self.progress = ui.circular_progress(max=100, show_value=True)

            with ui.row():
                self.cancel_btn = ui.button(t("cancel_x"), on_click=self.cancel).classes(sizeBTN)
                self.cancel_btn.visible = False

                self.action_button = ui.button(t("start_merge"), on_click=self.verify_process).classes(sizeBTN)

            ui.separator()
            self.log_ui = ui.log(max_lines=30).classes('w-full').style('height: 300px;')
            self.image_ui = ui.image("").classes("mt-4 max-w-full")

        self.populate_dwarf_filter()
        self.populate_backup_filter()

        self._build_copy_dialog()
 
    def _build_copy_dialog(self):
        """Pre-build the post-process copy dialog in UI context (called from build_ui)."""
        self._copy_dlg_entry: dict | None = None

        with ui.dialog().props("persistent") as self._copy_dlg, \
             ui.card().style("min-width: 420px"):

            self._copy_dlg_title = ui.label("").classes("text-lg font-bold text-green-700")
            self._copy_dlg_body  = ui.label("").classes("text-sm text-gray-600 pt-1 whitespace-pre-wrap")

            with ui.row().classes("gap-3 justify-end pt-3 w-full"):
                ui.button(t("later"), on_click=self._copy_dlg.close).props("flat color=grey")
                ui.button(
                    t("copy_to_dwarf"),
                    on_click=self._on_copy_dlg_confirm,
                ).props("color=green")

    # ------------------------------------------------------------------ #
    #  MODE SWITCH                                                         #
    # ------------------------------------------------------------------ #

    def switch_mode(self):
        self.mode = self.mode_toggle.value
        self.error_sessions_card.set_visibility(self.mode == "Repair")
        self.refresh_error_sessions()
        if self.mode == "Repair":
            self.main_label.text = t("mosaic_repair_desc")
            self.action_button.text = "🔧 Start Repair"
            self.primary_session_label.text = t("primary_session_repair")
            self.secondary_session_label.text = t("secondary_session_repair")
            self.copy_intermediate_files.visible = False
        else:
            self.main_label.text = t("mosaic_merge_desc")
            self.action_button.text = t("start_merge")
            self.primary_session_label.text = t("primary_session")
            self.secondary_session_label.text = t("secondary_session")
            self.copy_intermediate_files.visible = True

    # ------------------------------------------------------------------ #
    #  DWARF SELECTOR                                                      #
    # ------------------------------------------------------------------ #

    def refresh_error_sessions(self):
        """Reload DwarfSessionsError list for the selected Dwarf (Repair mode only)."""
        if not self.DwarfId or self.mode != "Repair":
            self.error_sessions = []
            self.error_session_select.set_options([], value=None)
            return
        rows = get_dwarf_sessions_error(self.conn, self.DwarfId, status="ERROR")
        self.error_sessions = rows
        options = [row[3] for row in rows]  # session_dir
        self.error_session_select.set_options(options, value=options[0] if options else None)

    def use_error_session_as_secondary(self):
        """Pre-fill the Secondary session field with the selected error session."""
        selected_dir = self.error_session_select.value
        if not selected_dir:
            ui.notify(t("no_error_session"), type="warning")
            return
        # Force source to Dwarf
        self.secondary_source_toggle.value = "Dwarf"
        self.on_secondary_source_change()
        # Build full path from dwarf astro dir
        full_path = os.path.join(self.dwarf_astroDir, selected_dir) if self.dwarf_astroDir else selected_dir
        self.secondary_session_dir = full_path
        self.input_secondary_dir.set_options([full_path], value=full_path)
        self.on_secondary_dir_change()
        ui.notify(t("secondary_session_set", name=selected_dir), type="positive")

    def populate_dwarf_filter(self):
        self.usb_status_label.text = ""
        self.dwarf_options = get_dwarf_Names(self.conn)
        names = [name for _, name in self.dwarf_options]

        initial_value = names[0] if names else None
        if self.DwarfId:
            match = next((name for did, name in self.dwarf_options if did == self.DwarfId), None)
            if match:
                initial_value = match

        self.dwarf_filter.set_options(names, value=initial_value)

    def populate_backup_filter(self):
        if self.DwarfId:
            self.backup_options = get_backupDrive_list_dwarfId(self.conn, self.DwarfId)
            self.backup_data = {
                backup[1]: (backup[0], backup[3], backup[4]) for backup in self.backup_options
            }
            names = list(self.backup_data.keys())
        else:
            names = []
            self.backup_data = {}

        initial_value = None
        for name, (id_, _, _) in self.backup_data.items():
            if id_ == self.BackupId_Init:
                initial_value = name
                break
        if not initial_value and names:
            initial_value = names[0]

        self.backup_filter.set_options(names, value=initial_value)

        if initial_value:
            self._apply_backup_details(initial_value)
        else:
            self.BackupId = None
            self.backup_location = ""
            self.backup_astrodir = ""
            self.backup_path = ""
            self.backup_status_label.text = ""

    def _apply_backup_details(self, selected_name: str):
        if selected_name in self.backup_data:
            self.BackupId, self.backup_location, self.backup_astrodir = self.backup_data[selected_name]
            self.backup_path = os.path.join(self.backup_location, self.backup_astrodir)
            if os.path.exists(self.backup_path):
                self.backup_status_label.text = t("path_detected")
                if self.usb_status_label.text != t("path_detected") and self.primary_source_toggle.value == "Dwarf": 
                    self.primary_source_toggle.value = "Backup"
                    self.secondary_source_toggle.value = "Backup"
            else:
                self.backup_status_label.text = t("path_not_detected")
                if self.usb_status_label.text == t("path_detected") and self.primary_source_toggle.value == "Backup": 
                    self.primary_source_toggle.value = "Dwarf"
                    self.secondary_source_toggle.value = "Dwarf"
        else:
            self.BackupId = None
            self.backup_location = ""
            self.backup_astrodir = ""
            self.backup_path = ""
            self.backup_status_label.text = ""
        # Refresh picker roots that are currently set to Backup
        self._refresh_source_dirs()

    def on_backup_filter_change(self):
        selected_name = self.backup_filter.value
        self._apply_backup_details(selected_name)

    async def on_dwarf_filter_change(self):
        self.usb_status_label.text = ""
        selected_name = self.dwarf_filter.value
        for did, name in self.dwarf_options:
            if name == selected_name:
                self.DwarfId = did
                break
        self.populate_backup_filter()
        await self.dwarf_data_update()

    async def dwarf_data_update(self):
        row = get_dwarf_detail(self.conn, self.DwarfId)
        if row:
            self.dwarf_astroDir = row[2] or ""
            self.dwarf_ip_sta_mode = row[5] or ""
            self.dwarf_type = row[3] or None
            self.check_dir_dwarf()
            self.update_session_directories()
            self.refresh_error_sessions()

    def check_dir_dwarf(self):
        if self.dwarf_astroDir:
            if os.path.exists(self.dwarf_astroDir):
                self.usb_status_label.text = t("path_detected")
            else:
                self.usb_status_label.text = t("path_not_detected")
        else:
            self.usb_status_label.text = ""

    def update_session_directories(self):
        """Reset both session pickers when Dwarf or Backup selection changes."""
        # ── Primary ──────────────────────────────────────────────────────
        primary_root = self._root_for_source(self.primary_source)
        if self.primary_source == 'Dwarf' and self.DwarfId_Init == self.DwarfId and self.session:
            if self.session.startswith("RESTACKED"):
                primary_path = os.path.join(self.dwarf_astroDir, "RESTACKED", self.session)
            else:
                primary_path = os.path.join(self.dwarf_astroDir, self.session)
            self.primary_session_dir = primary_path
            self.input_primary_dir.set_options([primary_path], value=primary_path)
        else:
            self.primary_session_dir = primary_root
            self.input_primary_dir.set_options([primary_root], value=primary_root)
        self.primary_main_dir = primary_root

        # ── Secondary ────────────────────────────────────────────────────
        secondary_root = self._root_for_source(self.secondary_source)
        self.secondary_session_dir = secondary_root
        self.input_secondary_dir.set_options([secondary_root], value=secondary_root)
        self.secondary_main_dir = secondary_root

    # ── Source toggle helpers ─────────────────────────────────────────────

    def _root_for_source(self, source: str) -> str:
        """Return the root astro dir for the chosen source (Dwarf or Backup)."""
        if source == 'Backup':
            return self.backup_path or ""
        return self.dwarf_astroDir or ""

    def _refresh_source_dirs(self):
        """Re-root primary/secondary pickers when backup details or source toggle changes."""
        primary_root = self._root_for_source(self.primary_source)
        secondary_root = self._root_for_source(self.secondary_source)

        # Only reset if user hasn't navigated away from root yet
        if not self.primary_session_dir or self.primary_session_dir == self.primary_main_dir:
            self.input_primary_dir.set_options([primary_root], value=primary_root)
            self.primary_session_dir = primary_root
        self.primary_main_dir = primary_root

        if not self.secondary_session_dir or self.secondary_session_dir == self.secondary_main_dir:
            self.input_secondary_dir.set_options([secondary_root], value=secondary_root)
            self.secondary_session_dir = secondary_root
        self.secondary_main_dir = secondary_root

    def on_primary_source_change(self):
        self.primary_source = self.primary_source_toggle.value
        root = self._root_for_source(self.primary_source)
        if not root:
            label = "Backup" if self.primary_source == 'Backup' else "Dwarf"
            ui.notify(t("no_dir_available", label=label), type="warning")
            return
        self.primary_session_dir = root
        self.primary_main_dir = root
        self.input_primary_dir.set_options([root], value=root)
        ui.notify(t("primary_source_set", source=self.primary_source, path=root), type="positive")

    def on_secondary_source_change(self):
        self.secondary_source = self.secondary_source_toggle.value
        root = self._root_for_source(self.secondary_source)
        if not root:
            label = "Backup" if self.secondary_source == 'Backup' else "Dwarf"
            ui.notify(t("no_dir_available", label=label), type="warning")
            return
        self.secondary_session_dir = root
        self.secondary_main_dir = root
        self.input_secondary_dir.set_options([root], value=root)
        ui.notify(t("secondary_source_set", source=self.secondary_source, path=root), type="positive")

    # ------------------------------------------------------------------ #
    #  INPUT CHANGE HANDLERS                                               #
    # ------------------------------------------------------------------ #

    def on_primary_dir_change(self):
        self.primary_session_dir = self.input_primary_dir.value or ""
        if self.primary_session_dir != self._root_for_source(self.primary_source) and "MOSAIC" not in self.primary_session_dir:
            ui.notify(t("no_mosaic_dir"), type="warning")

        details_session = []
        if self.primary_source == "Dwarf":
            sessions = get_sessions_dwarf(self.conn, self.DwarfId, Path(self.primary_session_dir).name)
            if len(sessions) == 1:
                session_id = sessions[0][0]
                details_session = get_session_dwarf_details(self.conn, session_id)
        else:
            sessions = get_sessions_backup(self.conn, self.BackupId, self.DwarfId, Path(self.primary_session_dir).name)
            if len(sessions) == 1:
                session_id = sessions[0][0]
                details_session = get_session_backup_details(self.conn, session_id)
        if len(details_session) == 1:
            print(details_session)
            self.detail_session_primary_name.text, self.detail_session_primary.text, thumbnail_path, image_path = get_session_detail(self.conn, details_session[0], self.DwarfId)
           
            if thumbnail_path:
                print(f"image_path: {image_path}")
                self.session_select_thumbnail_primary = thumbnail_path
                self.session_select_image_primary = image_path
                self.thumbnail_primary.set_source(thumbnail_path)
                self.thumbnail_primary.visible = True
            else:
                self.thumbnail_primary.visible = False
        else:
            self.detail_session_primary_name.text = ""
            self.detail_session_primary.text = ""
            self.thumbnail_primary.visible = False


    def on_secondary_dir_change(self):
        self.secondary_session_dir = self.input_secondary_dir.value or ""
        if self.secondary_session_dir != self._root_for_source(self.secondary_source) and "MOSAIC" not in self.secondary_session_dir:
            ui.notify(t("no_mosaic_dir"), type="warning")

        details_session = []
        if self.secondary_source == "Dwarf":
            sessions = get_sessions_dwarf(self.conn, self.DwarfId, Path(self.secondary_session_dir).name)
            if len(sessions) == 1:
                session_id = sessions[0][0]
                details_session = get_session_dwarf_details(self.conn, session_id)
        else:
            sessions = get_sessions_backup(self.conn, self.BackupId, self.DwarfId, Path(self.secondary_session_dir).name)
            if len(sessions) == 1:
                session_id = sessions[0][0]
                details_session = get_session_backup_details(self.conn, session_id)
        if len(details_session) == 1:
            print(details_session)
            self.detail_session_secondary_name.text, self.detail_session_secondary.text, thumbnail_path, image_path = get_session_detail(self.conn, details_session[0], self.DwarfId)
           
            if thumbnail_path:
                print(f"image_path: {image_path}")
                self.session_select_thumbnail_secondary = thumbnail_path
                self.session_select_image_secondary = image_path
                self.thumbnail_secondary.set_source(thumbnail_path)
                self.thumbnail_secondary.visible = True
            else:
                self.thumbnail_secondary.visible = False
        else:
            self.detail_session_secondary_name.text = ""
            self.detail_session_secondary.text = ""
            self.thumbnail_secondary.visible = False


    # ------------------------------------------------------------------ #
    #  FOLDER PICKERS                                                      #
    # ------------------------------------------------------------------ #

    async def _pick_folder(self, initial_path: str, root_dir: str, label_name: str) -> str | None:
        """Generic native folder picker with root restriction."""
        if hasattr(webview, 'FileDialog'):
            folder_mode = webview.FileDialog.FOLDER
        else:
            folder_mode = webview.FOLDER_DIALOG

        directory = os.path.abspath(initial_path) if initial_path else None
        if directory:
            folder = await app.native.main_window.create_file_dialog(folder_mode, allow_multiple=False, directory=directory)
        else:
            folder = await app.native.main_window.create_file_dialog(folder_mode, allow_multiple=False)

        if not folder:
            return None

        chosen = os.path.normpath(folder[0])

        if root_dir and not chosen.startswith(root_dir):
            ui.notify(t("access_denied_outside", path=label_name), type="negative")
            return None

        return chosen

    async def select_primary_folder(self):
        label = "the Backup directory!" if self.primary_source == 'Backup' else "the Dwarf astro directory!"
        chosen = await self._pick_folder(
            self.primary_session_dir or self.primary_main_dir,
            self.primary_main_dir,
            label,
        )
        if chosen:
            self.primary_session_dir = chosen
            self.input_primary_dir.set_options([chosen], value=chosen)
            ui.notify(t("primary_session_set", name=chosen), type="positive")

    async def select_secondary_folder(self):
        label = "the Backup directory!" if self.secondary_source == 'Backup' else "the Dwarf astro directory!"
        chosen = await self._pick_folder(
            self.secondary_session_dir or self.secondary_main_dir,
            self.secondary_main_dir,
            label,
        )
        if chosen:
            self.secondary_session_dir = chosen
            self.input_secondary_dir.set_options([chosen], value=chosen)
            ui.notify(t("secondary_session_set", name=chosen), type="positive")

    async def select_output_folder(self):
        chosen = await self._pick_folder(
            self.output_dir or self.primary_main_dir,
            "",   # no root restriction for output
            "",
        )
        if chosen:
            self.output_dir = chosen
            self.input_output_dir.set_options([chosen], value=chosen)
            self._init_repair_mgr(chosen)
            ui.notify(t("output_folder_selected", path=chosen), type="positive")

    def create_temp_folder(self):
        """Create a system temp directory and pre-fill the output field."""
        tmp = tempfile.mkdtemp(prefix="dwarf_mosaic_")
        self.output_dir = tmp
        self.input_output_dir.set_options([tmp], value=tmp)
        self._init_repair_mgr(tmp)
        ui.notify(t("temp_folder_created", path=tmp), type="positive")

    def _init_repair_mgr(self, output_dir: str):
        """Initialise (or reinitialise) the RepairSessionManager for the chosen output dir."""
        self.repair_mgr = RepairSessionManager(output_dir)

    # ------------------------------------------------------------------ #
    #  PROCESS LAUNCH                                                      #
    # ------------------------------------------------------------------ #
    @ui.refreshable
    def notify_me(self, msg: str | None, type: str = "info") -> None:
        if msg:
            ui.notify(msg, type=type)

    def cancel(self):
        self.cancel_btn.text = "Cancelling"
        self.cancel_process.set()

    # ------------------------------------------------------------------ #
    #  Verify before launching process                                   #
    # ------------------------------------------------------------------ #

    async def verify_process(self):
        primary   = self.input_primary_dir.value
        secondary = self.input_secondary_dir.value
        output    = self.input_output_dir.value
        self.cancel_btn.text = "❌ Cancel"

        # Mount the refreshable notify_me container once, so later
        # self.notify_me.refresh(...) calls have a container to update.
        self.notify_me(None)

        if not primary:
            ui.notify(t("no_primary"), type="negative")
            return
        if not secondary:
            ui.notify(t("no_secondary"), type="negative")
            return
        if not output:
            ui.notify(t("no_output_dir"), type="negative")
            return
        if primary == secondary:
            ui.notify(t("sessions_different"), type="warning")
            return
        if "MOSAIC" not in primary:
            ui.notify(t("primary_not_mosaic"), type="warning")
            return
        if "MOSAIC" not in secondary:
            ui.notify(t("primary_not_mosaic"), type="warning")
            return

        # ── Orientation check (Merge only) ─────────────────────────────────
        # In Repair mode the faulty session has no stacked.jpg and its files
        # are wiped anyway, so panel order does not matter.
        if self.mode == "Merge":
            info_a = read_shots_info(primary)
            info_b = read_shots_info(secondary)

            if info_a is None:
                rebuild_mosaic_info(primary)
            if info_b is None:
                rebuild_mosaic_info(secondary)

            info_a = read_shots_info(primary)
            info_b = read_shots_info(secondary)

            if info_a is None or info_b is None:
                missing = "Primary" if info_a is None else "Secondary"
                ui.notify(f"⚠️ shotsInfo.json missing in {missing} session.", type="warning")
                return

            compat = check_mosaic_json_compatibility(info_a, info_b)
            if not compat.ok:
                ui.notify(f"❌ Incompatible sessions: {compat.reason}", type="negative")
                return

            # Store panel order; may be overridden by the orientation dialog
            self._merge_panel_paths_b = list(info_b.mosaic.panel_paths)
            self._merge_inverted = False

            # Show orientation dialog then continue asynchronously
            self._show_orientation_dialog(
                info_a=info_a,
                info_b=info_b,
            )
            return  # dialog will call start_process when confirmed

        else:
            self.start_process()

    # ------------------------------------------------------------------ #
    #  ORIENTATION DIALOG (Merge only)                                    #
    # ------------------------------------------------------------------ #

    def _show_orientation_dialog(
        self,
        info_a,
        info_b,
    ):
        """
        Affiche un dialog de verification d'orientation avant le merge.
        Compare les stacked.jpg des deux sessions, propose la detection
        automatique et un toggle manuel, puis appelle start_process.
        """

        # Detection automatique si les deux thumbnails sont disponibles
        auto = detect_inversion(info_a, info_b)
        inverted_state = {"value": auto.inverted if auto is not None else False}

        with ui.dialog().props("persistent") as dlg,              ui.card().style("min-width: 680px; max-width: 900px"):

            ui.label(t("verify_orientation")).classes(
                "text-lg font-semibold text-blue-800 mb-2"
            )

            # ── Resumes + thumbnails cote a cote ─────────────────────────
            with ui.row().classes("w-full gap-4 items-start"):
                for label, info in [("Primary (reference)", info_a),
                                     ("Secondary (to merge)", info_b)]:
                    with ui.column().classes("flex-1"):
                        ui.label(label).classes(
                            "text-xs text-gray-500 uppercase tracking-wide mb-1"
                        )
                        ui.label(format_session_summary(info)).style(
                            "white-space: pre-line"
                        ).classes("text-purple-600 text-sm")

                        thumb = get_thumbnail_path(str(info.path))
                        if thumb:
                            with ui.card().classes("mt-2 p-0 cursor-pointer min-h-[250px] w-80").on(
                                "click",
                                lambda t=str(thumb): self._show_full_image(t),
                            ):
                                ui.image(str(thumb)).classes("w-full rounded")
                        else:
                            ui.label(t("no_thumbnail")).classes(
                                "text-gray-400 text-xs mt-2"
                            )

            ui.separator().classes("my-3")

            # ── Resultat detection automatique ───────────────────────────
            if auto is not None:
                conf_label = orientation_confidence_label(auto)
                color = (
                    "text-green-700" if auto.confidence > 0.05
                    else "text-amber-600" if auto.confidence > 0.01
                    else "text-gray-500"
                )
                with ui.row().classes("items-center gap-2"):
                    ui.icon("search").classes("text-gray-400").classes('text-5gl')
                    ui.label(f"Auto-detect: {conf_label}").classes(f"text-sm {color}")
            else:
                with ui.row().classes("items-center gap-2"):
                    ui.icon("info").classes("text-gray-400").classes('text-5gl')
                    ui.label(
                        t("no_thumbnail_check")
                    ).classes("text-sm text-gray-500")

            # ── Toggle manuel ─────────────────────────────────────────────
            toggle = ui.switch(
                "Secondary session is inverted (180° rotation)",
                value=inverted_state["value"],
            ).classes("text-sm mt-1")

            def on_toggle(e):
                inverted_state["value"] = e.value

            toggle.on_value_change(on_toggle)

            ui.separator().classes("my-3")

            # ── Boutons ───────────────────────────────────────────────────
            with ui.row().classes("gap-3 justify-end w-full"):
                ui.button(t("cancel"), on_click=dlg.close).props("flat color=grey")

                def on_confirm():
                    self._merge_inverted = inverted_state["value"]
                    self._merge_panel_paths_b = reorder_panels(
                        info_b.mosaic.panel_paths,
                        self._merge_inverted,
                    )
                    dlg.close()
                    self.start_process()

                ui.button(
                    t("confirm_continue"),
                    on_click=on_confirm,
                    icon="check_circle",
                ).classes("bg-blue-600 text-white")

        dlg.open()

    def _show_full_image(self, path: str):
        print(path)
        with ui.dialog() as d, ui.card().classes("w-full h-auto max-w-screen-xl"):
            ui.image(path).classes("w-full h-auto object-contain rounded-xl")
            ui.button(t("close"), on_click=d.close).props("flat")
        d.open()

    # ------------------------------------------------------------------ #
    #  PROCESS LAUNCH — with history check                                 #
    # ------------------------------------------------------------------ #

    def start_process(self):
        primary   = self.input_primary_dir.value
        secondary = self.input_secondary_dir.value
        output    = self.input_output_dir.value

        # Ensure manager is initialised (in case user typed the path manually)
        if self.repair_mgr is None:
            self._init_repair_mgr(output)

        primary_name = os.path.basename(os.path.normpath(primary))
        secondary_name = os.path.basename(os.path.normpath(secondary))
        if self.mode == "Repair":
            # Ignore the continue Button in this case
            # Set to empty the secondary_name to ignore this action
            secondary_name = ""

        # ── History check ────────────────────────────────────────────────
        # If this primary has been treated before, show the history dialog.
        # check_and_show_history is synchronous; it opens the dialog and
        # returns True, or calls on_proceed directly and returns False.
        already_shown = check_and_show_history(
            manager         = self.repair_mgr,
            primary_session = primary_name,
            secondary_session = secondary_name,
            backup_root     = self.output_dir,
            on_redo         = lambda: ui.timer(0, lambda: self._run_process(primary, secondary, output, primary_name), once=True),
            on_continue     = lambda: ui.timer(0, lambda: self._run_process(primary, secondary, output, primary_name, True), once=True),
            on_copy         = self._open_copy_dialog,
            on_proceed      = lambda: ui.timer(0, lambda: self._run_process(primary, secondary, output, primary_name), once=True),
            dwarf_id        = self.DwarfId,
            backup_id       = self.BackupId,
        )
        # If no history, on_proceed fires immediately via the timer above.
        # If history exists, the dialog handles routing — nothing more to do here.
        _ = already_shown

    async def _run_process(self, primary: str, secondary: str, output: str, primary_name: str, ignore_copy: bool = False ):
        """Core repair/merge logic, called both on first run and on Redo."""
        work_primary = os.path.join(output, primary_name)

        self.cancel_process.clear()
        self.cancel_btn.text = "❌ Cancel"
        self.cancel_btn.visible = True
        self.action_button.visible = False
        self.image_ui.set_source("")
        await self.client.run_javascript("document.body.style.cursor='wait'")
        self.log_ui.clear()
        self.progress.value = 0
        self.progress_label.set_text(t("mosaic_copying"))

        # ── Step 0: register action as "running" ─────────────────────────
        from datetime import datetime
        output_subdir = f"{primary_name}"
        entry = self.repair_mgr.write_action(
            action            = self.mode,
            primary_session   = primary_name,
            output_subdir     = output_subdir,
            status            = "running",
            secondary_session = os.path.basename(os.path.normpath(secondary)),
            dwarf_id          = self.DwarfId,
            backup_id         = self.BackupId,
        )
        self._current_entry_id = entry["id"]
        result = None
        error = None

        # ── Step 1: copy primary session into the work (output) directory ──
        if not self.cancel_process.is_set():
            try:
                if not ignore_copy :
                    print_log(f"Copying data, please wait...'", self.log_ui)
                    print_log(f"  '{primary}'", self.log_ui)
                    print_log(f" → ", self.log_ui)
                    print_log(f"  '{work_primary}'", self.log_ui)
                    if self.mode == "Repair":
                        await run.io_bound(self._copy_session, primary, work_primary, self.log_ui, progress_cb=lambda p: safe_progress(self.progress, p * 20))
                    else:
                        await run.io_bound(self._copy_all_session, primary, work_primary, self.copy_intermediate_files.value, self.log_ui, progress_cb=lambda p: safe_progress(self.progress, p * 20))
                    self.progress.value = 20
                    print_log("✅ Copy complete.", self.log_ui)
                else:
                    self.progress.value = 20
                    print_log("✅ Copy Primary skipped.", self.log_ui)
            except Exception as e:
                error = str(e)
                self.notify_me.refresh(t("mosaic_copy_failed_notify").format(e=e), type="negative")
                traceback.print_exc()
                self.progress_label.set_text(t("mosaic_copy_failed"))
                self.cancel_btn.visible = False
                self.action_button.visible = True
                self.repair_mgr.update_action_status(self._current_entry_id, "failed", error=str(e))
                if self.client:
                    await self.client.run_javascript("document.body.style.cursor='default'")
                return
        else:
            result = None

        if not self.cancel_process.is_set():
            # ── Step 2: run the repair / merge on the work copy ────────────────
            self.progress_label.set_text(t("mosaic_running"))
            try:
                if self.mode == "Repair":
                    print_log("Starting Repair…", self.log_ui)
                    result = await repair_mosaic_session(secondary, work_primary, self.log_ui, self.progress, self.cancel_process, stitch_params=self.stitch_params)
                else:
                    print_log("Starting Merge…", self.log_ui)
                    #result = await merge_mosaic(secondary, work_primary, self.copy_intermediate_files.value, self.log_ui, self.progress, self.cancel_process, panel_paths_b=self._merge_panel_paths_b)
                    result = await self.create_and_show_panorama(secondary, work_primary )
            except Exception as e:
                error = str(e)
                self.notify_me.refresh(t("mosaic_error_notify").format(e=e), type="negative")
                traceback.print_exc()
        else:
            result = None

        self.cancel_btn.visible = False
        self.action_button.visible = True
        if self.client:
            await self.client.run_javascript("document.body.style.cursor='default'")

        if result and Path(result).exists():
            self.progress.value = 100
            self.progress_label.set_text(t("mosaic_complete"))
            self.image_ui.set_source(str(result))
            self.image_ui.force_reload()
            self.notify_me.refresh(t("mosaic_done_result_shown"), type="positive")

            # ── Step 3: mark success and offer copy to Dwarf ───────────────
            self.repair_mgr.update_action_status(self._current_entry_id, "success")
            entry["status"] = "success"

            # ── Step 3b: write repairInfo.json + copy missing files ────────
            import json as _json
            done_transfer_dwarf = False

            if self.mode == "Repair":
                secondary_name_repair = os.path.basename(os.path.normpath(secondary))

                # repairInfo.json in work_primary → type=REPAIR so the Dwarf scan ignores
                # ignores Session_OK after transfer (already in DB as original session).

                repair_info_data = {
                    "type": "REPAIR",
                    "source_session": secondary_name_repair,
                }
                repair_info_path = os.path.join(work_primary, "repairInfo.json")
                try:
                    with open(repair_info_path, "w", encoding="utf-8") as f:
                        _json.dump(repair_info_data, f, indent=2)
                    print_log(f"✅ repairInfo.json (REPAIR) written in {work_primary}", self.log_ui)
                except Exception as e:
                    print_log(f"⚠️ Could not write repairInfo.json: {e}", self.log_ui)

                # Copy the missing files produced by repair into Session_Error on the Dwarf.
                # Session_Error = secondary (already on the Dwarf, path known).
                # Files to copy: stacked.jpg, stacked_thumbnail.jpg, stacked-16_*.zip
                # After this copy Session_Error will be visible to the next scan and
                # registered in DwarfData. DwarfSessionsError status is updated here.
                if os.path.exists(secondary):
                    import glob as _glob
                    files_to_copy = []
                    for name in ["stacked.jpg", "stacked_thumbnail.jpg"]:
                        src = os.path.join(work_primary, name)
                        if os.path.exists(src):
                            files_to_copy.append((src, os.path.join(secondary, name)))
                    for zip_src in _glob.glob(os.path.join(work_primary, "stacked-16_*.zip")):
                        files_to_copy.append((zip_src, os.path.join(secondary, os.path.basename(zip_src))))

                    copied = 0
                    for src, dst in files_to_copy:
                        try:
                            result_copy = safe_copy2(src, dst)
                            if not result_copy:
                                raise Exception(f"Copy failed without exception: {src}")
                            copied += 1
                        except Exception as e:
                            print_log(f"⚠️ Could not copy {os.path.basename(src)} to Session_Error: {e}", self.log_ui)
                    print_log(f"✅ {copied}/{len(files_to_copy)} file(s) copied to repaired session: {secondary_name_repair}", self.log_ui)
                    if (copied > 0 and copied == len(files_to_copy)) :
                        done_transfer_dwarf = True
                    # Update DwarfSessionsError status to REPAIRED
                    from api.dwarf_backup_db_api import update_dwarf_session_error_repaired
                    update_dwarf_session_error_repaired(self.conn, self.DwarfId, secondary_name_repair, primary_name)
                    print_log(f"✅ DwarfSessionsError status updated to REPAIRED for {secondary_name_repair}", self.log_ui)
                    self.refresh_error_sessions()
                    
                else:
                    print_log(f"⚠️ Secondary session path not found on Dwarf — missing files not copied: {secondary}", self.log_ui)

                    await self._offer_copy_after_process(entry)

            elif self.mode == "Merge":
                # repairInfo.json in work_primary → type=MERGE so the Dwarf scan
                # ignores this base session after transfer (the RESTACKED_ Megastack
                # is the real entry to register).
                # Accumulate sessions across multiple merges on the same primary.
                secondary_name_merge = os.path.basename(os.path.normpath(secondary))
                merge_info_path = os.path.join(work_primary, "repairInfo.json")

                # Read existing sessions if file already present
                existing_sessions = [primary_name]
                if os.path.exists(merge_info_path):
                    try:
                        with open(merge_info_path, "r", encoding="utf-8") as f:
                            existing = _json.load(f)
                            if existing.get("type") == "MERGE":
                                existing_sessions = existing.get("sessions", [primary_name])
                    except Exception:
                        pass

                # Append new secondary if not already listed
                if secondary_name_merge not in existing_sessions:
                    existing_sessions.append(secondary_name_merge)

                merge_info_data = {
                    "type": "MERGE",
                    "sessions": existing_sessions,
                }
                try:
                    with open(merge_info_path, "w", encoding="utf-8") as f:
                        _json.dump(merge_info_data, f, indent=2)
                    print_log(f"✅ repairInfo.json (MERGE) written — {len(existing_sessions)} session(s): {existing_sessions}", self.log_ui)
                except Exception as e:
                    print_log(f"⚠️ Could not write repairInfo.json for Merge: {e}", self.log_ui)

            if not done_transfer_dwarf:
                await self._offer_copy_after_process(entry)
            else:
                self.notify_me.refresh(t("mosaic_repair_back_to_dwarf"), type="positive")                
        
        else:
            status = "failed" if error else "partial"
            self.repair_mgr.update_action_status(self._current_entry_id, status, error=error)
            self.progress_label.set_text(t("mosaic_failed_cancelled"))
            self.notify_me.refresh(t("mosaic_no_result_produced"), type="warning")

    # ------------------------------------------------------------------ #
    #  POST-PROCESS DIALOGS                                                #
    # ------------------------------------------------------------------ #

    def _open_copy_dialog(self, entry: dict):
        """Navigate to the Transfer page using the existing output dir."""
        open_mosaic_restore_dialog(
            repaired_src_dir = str(self.repair_mgr.get_output_path(entry)),
            backup_root      = self.output_dir,
            dwarf_id         = self.DwarfId,
            session          = entry["primary_session"],
            mode             = self.mode,
            backup_id        = self.BackupId,
            back_url         = "/Mosaic",
        )
        
    async def _offer_copy_after_process(self, entry: dict):
        action_label = "repaired" if self.mode == "Repair" else "merged"
        self._copy_dlg_entry = entry
        self._copy_dlg_title.set_text(t("transfer_successful", mode=self.mode))
        self._copy_dlg_body.set_text(
            f"The {action_label} session is ready in the output directory. "
            "Do you want to copy the files back to the Dwarf now?"
        )
        self._copy_dlg.open()

    def _on_copy_dlg_confirm(self):
        self._copy_dlg.close()
        if self._copy_dlg_entry is not None:
            self._open_copy_dialog(self._copy_dlg_entry)

    async def create_and_show_panorama(self, secondary, work_primary):
        result_path = None
        work_primary_path = Path(work_primary)

        # ── Backup before merge ─────────────────────────────────────────────
        backed_up = await backup_merge_files(work_primary)
        if backed_up is None:
            ui.notify(t("merge_aborted"), type="negative")
            return None

        # Collect before/after pairs for comparison:
        # { "root": (backup_jpg, work_jpg),
        #   "panel_1": (backup_jpg, work_jpg), ... }
        print (backed_up)
        def build_comparison_pairs() -> dict:
            pairs = {}
            work_path = Path(work_primary)
            backup_dir = Path(list(backed_up.values())[0]).parent  # temp root

            # Root stacked.jpg
            root_before = backup_dir / "stacked.jpg"
            root_after  = work_path  / "stacked.jpg"

            if root_before.exists():
                pairs["🌅 Final Mosaic"] = (str(root_before), str(root_after))

            # Per-panel stacked.jpg
            for panel_dir in sorted(work_path.iterdir()):
                if not panel_dir.is_dir():
                    continue
                before = backup_dir / panel_dir.name / "stacked.jpg"
                after  = panel_dir / "stacked.jpg"
                if before.exists() and after.exists():
                    pairs[f"📦 {panel_dir.name}"] = (str(before), str(after))

            return pairs

        with ui.context.client.layout:
            # --- Progress dialog ---
            with ui.dialog().props('persistent') as progress_dialog, ui.card().classes("w-full max-w-screen-xl items-center gap-4 p-6"):
                ui.label(t("stitching")).classes("text-lg font-semibold")
                with ui.card().classes("w-full p-4 mt-1 mb-8 items-center"):
                    self.action_progress_label = ui.label(t("idle"))
                    self.action_progress = ui.circular_progress(max=100, show_value=True)
                    with ui.row():
                        self.cancel_action_btn = ui.button(t("cancel_x"), on_click=self.cancel)
                        self.cancel_action_btn.visible = False
                    ui.separator()
                    self.action_log = ui.log(max_lines=30).classes('w-full').style('height: 400px; overflow: hidden;')
    
            # --- Error dialog ---
            with ui.dialog().props('persistent') as error_dialog, ui.card().classes("p-6 gap-4 w-full max-w-2xl"):
                ui.label(t("stitching_failed")).classes("text-xl font-bold text-red-500")
                error_message = ui.label("").classes("text-sm text-gray-300 whitespace-pre-wrap")
                with ui.row().classes("justify-end gap-2 mt-4 w-full"):
                    def on_error_params():
                        self.open_stitch_params()
                    async def on_error_retry():
                        error_dialog.close()
                        await restore_merge_files(backed_up)
                        cleanup_backup(backed_up)
                        ui.timer(0, lambda: self.create_and_show_panorama(secondary, work_primary), once=True)
                    async def on_error_discard():
                        await restore_merge_files(backed_up)
                        cleanup_backup(backed_up)
                        error_dialog.close()
                        ui.notify(t("mosaic_discarded_restored"), type="warning")
                    ui.button(t("discard"), on_click=on_error_discard).props("flat color=negative")
                    ui.button(t("change_params"), on_click=on_error_params).props("flat")
                    ui.button(t("retry"), on_click=on_error_retry).props("color=positive")
    
            # --- Result dialog ---
            with ui.dialog().props('maximized') as result_dialog, ui.card().classes("w-full h-full p-4 gap-2 overflow-auto"):
    
                with ui.row().classes("w-full items-center justify-between mb-2"):
                    ui.label(t("mosaic_result")).classes("text-xl font-bold")
                    with ui.row().classes("gap-2"):
                        btn_discard = ui.button(t("discard")).props("flat color=negative")
                        btn_accept  = ui.button(t("accept_close")).props("color=positive")
    
                # Tabs: one per panel + final mosaic
                with ui.tabs().classes("w-full") as tabs:
                    tab_mosaic = ui.tab("🌅 Final Mosaic")
                    tab_panels = ui.tab("📦 Panels")
    
                with ui.tab_panels(tabs, value=tab_mosaic).classes("w-full"):
    
                    # ── Final mosaic before/after ──────────────────────────────
                    with ui.tab_panel(tab_mosaic):
                        with ui.row().classes("w-full gap-4 items-start"):
                            with ui.column().classes("flex-1 items-center"):
                                ui.label(t("before")).classes("text-sm font-semibold text-gray-400 mb-1")
                                before_mosaic = ui.image().classes("w-full h-auto object-contain rounded-xl cursor-pointer hover:opacity-80")
                            with ui.column().classes("flex-1 items-center"):
                                ui.label(t("after")).classes("text-sm font-semibold text-green-400 mb-1")
                                after_mosaic = ui.image().classes("w-full h-auto object-contain rounded-xl cursor-pointer hover:opacity-80")
    
                    # ── Per-panel before/after ─────────────────────────────────
                    with ui.tab_panel(tab_panels):
                        panel_before_images = []  # filled after merge
                        panel_after_images  = []
                        panels_container = ui.column().classes("w-full gap-6")
    
            # --- Run merge ---
        progress_dialog.open()
        try:
            result_path = await merge_mosaic(
                secondary, work_primary,
                self.copy_intermediate_files.value,
                self.action_log, self.action_progress,
                self.cancel_process,
                panel_paths_b=self._merge_panel_paths_b,
                stitch_params=self.stitch_params
            )
            progress_dialog.close()

            if result_path and Path(result_path).exists():
                # ── Build comparison pairs from backup ─────────────────
                pairs = build_comparison_pairs()

                # Final mosaic
                mosaic_pair = pairs.get("🌅 Final Mosaic")
                if mosaic_pair:
                    before_mosaic.set_source(mosaic_pair[0])
                    after_mosaic.set_source(str(result_path))
                    before_mosaic.on('click', lambda p=mosaic_pair[0]: self._show_full_image(p))
                    after_mosaic.on('click', lambda: self._show_full_image(str(result_path)))

                # Per-panel comparison
                with panels_container:
                    for label, (before_path, after_path) in pairs.items():
                        if label == "🌅 Final Mosaic":
                            continue
                        ui.label(label).classes("text-sm font-semibold text-gray-300 mt-2")
                        with ui.row().classes("w-full gap-4 items-start"):
                            with ui.column().classes("flex-1 items-center"):
                                ui.label(t("before")).classes("text-xs text-gray-400")
                                ui.image(before_path.replace("\\", "/")).classes("w-full h-auto object-contain rounded-xl cursor-pointer hover:opacity-80")\
                                  .on('click', lambda p=before_path.replace("\\", "/"): self._show_full_image(p))
                            with ui.column().classes("flex-1 items-center"):
                                ui.label(t("after")).classes("text-xs text-green-400")
                                ui.image(after_path.replace("\\", "/")).classes("w-full h-auto object-contain rounded-xl cursor-pointer hover:opacity-80")\
                                  .on('click', lambda p=after_path.replace("\\", "/"): self._show_full_image(p))

                result_dialog.open()
            else:
                error_message.text = "Merge returned no result.\nTry adjusting alignment parameters."
                error_dialog.open()
                return None

        except Exception as ex:
            progress_dialog.close()
            error_message.text = str(ex)
            error_dialog.open()
            return None

        # --- Button handlers ---
        accepted = False

        async def on_discard():
            nonlocal accepted
            await restore_merge_files(backed_up)
            cleanup_backup(backed_up)
            result_dialog.close()
            ui.notify(t("mosaic_discarded_restored"), type="warning")

        def on_accept():
            nonlocal accepted
            accepted = True
            cleanup_backup(backed_up)
            result_dialog.close()
            ui.notify(t("mosaic_accepted"), type="positive")

        btn_discard.on("click", on_discard)
        btn_accept.on("click", on_accept)

        while result_dialog.value:
            await asyncio.sleep(0.2)

        return result_path if accepted else None       

    @staticmethod
    def _copy_session(src: str, dest: str, log=None, progress_cb=None) -> None:
        src_path = Path(win_long_path(src))
        dest_path = Path(win_long_path(dest))

        if dest_path.exists():
            shutil.rmtree(dest_path)
        dest_path.mkdir(parents=True)

        # Count total files upfront for progress
        all_files = [i for i in src_path.iterdir() if i.is_file()]
        all_panel_files = [f for i in src_path.iterdir() if i.is_dir()
                             for f in i.glob("stacked-16*")]
        total = len(all_files) + len(all_panel_files)
        done = 0

        for item in src_path.iterdir():
            if item.is_file():
                result_copy = safe_copy2(str(item), str(dest_path / item.name))
                if not result_copy:
                    raise Exception(f"Copy failed without exception: {str(item)}")
                #print_log(f"  📄 {item.name}", log)
                done += 1
                if progress_cb and total > 0:
                    progress_cb(done / total)
            elif item.is_dir():
                panel_dest = dest_path / item.name
                panel_dest.mkdir(parents=True, exist_ok=True)
                files = list(item.glob("stacked-16*"))
                #print_log(f"  📁 {item.name} ({len(files)} files)", log)
                for f in files:
                    result_copy = safe_copy2(str(f), str(panel_dest / f.name))
                    if not result_copy:
                        raise Exception(f"Copy failed without exception: {str(f)}")
                    #print_log(f"    ✔️ {f.name}", log)
                    done += 1
                    if progress_cb and total > 0:
                        progress_cb(done / total)


    @staticmethod
    def _copy_all_session(src: str, dest: str, copy_intermediate_files=False, log=None, progress_cb=None) -> None:
        src_path_str = win_long_path(src)
        dest_path_str = win_long_path(dest)

        if not copy_intermediate_files :
            print_log( f"ℹ️ skipping copy Fits files", log)

        if os.path.exists(dest_path_str):
            print_log(f"  🗑️ Removing existing {dest_path_str}", log)
            shutil.rmtree(dest_path_str)

        # 🔎 Filter Function
        def ignore_func(dir, files):
            if copy_intermediate_files:
                return []
            ignored = []
            for f in files:
                # Ignore .fits files that don't start with "stacked-16"
                if f.lower().endswith(".fits"):
                    if not f.startswith("stacked-16"):
                        ignored.append(f)
                # Ignore .jpg files in "Thumbnail" subdirectory
                elif f.lower().endswith(".jpg") and os.path.basename(dir).lower() == "thumbnail":
                    ignored.append(f)
            return ignored

        # Count total files (depending of copy_intermediate_files value)
        all_files = [
            f for f in Path(src_path_str).rglob("*")
            if f.is_file() and (
                copy_intermediate_files or
                not (
                    (f.name.lower().endswith(".fits") and not f.name.lower().startswith("stacked-16")) or
                    (f.name.lower().endswith(".jpg") and f.parent.name.lower() == "thumbnail")
                )
            )
        ]
        total = len(all_files)
        done = 0
        print_log(f"  📋 Copying {total} files...", log)

        # copytree with custom copy function to track progress
        def copy_with_progress(src_f, dst_f):
            result_copy = safe_copy2(src_f, dst_f)
            if not result_copy:
                raise Exception(f"Copy failed without exception: {src_f}")
            nonlocal done
            done += 1
            print(f"  ✔️ {Path(src_f).name}")
            if progress_cb and total > 0:
                progress_cb(done / total)

        shutil.copytree(
            src_path_str,
            dest_path_str,
            copy_function=copy_with_progress,
            ignore=ignore_func
        )
     
        print_log(f"  ✔️ Copy complete", log)