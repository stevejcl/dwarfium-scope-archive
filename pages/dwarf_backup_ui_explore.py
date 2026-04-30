from components.i18n import t
import os
import mimetypes
from astropy.io import fits
from datetime import datetime
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import subprocess
import json
import shutil
import re
import sys
import asyncio
import urllib.parse
from glob import glob
from nicegui import app, run, ui
from api.dwarf_backup_db import DB_NAME, connect_db
from components.session_notes import session_notes_widget
from api.dwarf_backup_db_api import get_backup_entry_id_by_dwarf_data
from api.dwarf_backup_db_api import (
    get_dwarf_Names, get_dwarf_detail, get_Objects_dwarf, get_countObjects_dwarf, get_ObjectSelect_dwarf,
    get_backupDrive_Names, get_backupDrive_dwarfId, get_backupDrive_dwarfNames, get_astro_object_description,
    get_Objects_backup, get_countObjects_backup, get_ObjectSelect_backup, delete_backup_entry_and_dwarf_data,
    get_Objects_duplicate_backup, get_countObjects_duplicate_backup, get_ObjectSelect_duplicate_backup,
    get_session_present_in_Dwarf, get_session_present_in_backupDrive, get_sessions_backup, toggle_favorite,
    has_related_manual_sessions, get_ManualSession_by_backup_entry_id,
    find_matching_darks, generate_siril_session_json,
    get_dwarf_session_error_by_dir,
)
from api.dwarf_backup_fct import (
    get_Backup_fullpath, get_extension, check_files, get_file_path, generate_fits_preview, show_date_session, show_short_date_session,
    get_directory_size, count_fits_files, count_failed_fits_files, count_tiff_files, count_failed_tiff_files, get_png_name_from_zip, get_fits_name_from_zip,
    hours_to_hms, deg_to_dms, is_path_local_dwarf_dir, get_total_exposure, get_total_mosaic_exposure, format_seconds_hms, 
    preprocess_dso_catalog_json, is_Restacked, get_name_object, parse_exposure, cleanup_fits_files, restore_fits_files, win_long_path
)
from api.dwarf_backup_fct_mosaic import (load_image, generate_panorama, create_thumbnail_mosaic, get_mosaic_panels)
from api.dwarf_backup_fct_mosaic_fits import (stitch_fits_from_transforms)

from api.image_preview import set_base_folder, build_preview_url
from components.win_log import WinLog
from components.menu import menu
from components.astro_object_associate import DwarfData, show_unknown_target_dialog

from api.dwarf_backup_fct import CATALOG_FILE, SKY_CATALOG_FILE, UNKNOWN, MOSAIC_UNKNOWN, MANUAL, TAKEN, RESTACK
from components.stitch_params_editor import StitchParamsEditor, get_stitch_params

ALL_BACKUPS = "(All Backups)"  # internal key — translated in UI
ALL_DWARFS = "(All Dwarfs)"
ALL_SESSIONS = "[ALL SESSIONS]"

@dataclass
class BackupEntryData:
    backup_drive_id: int
    dwarf_id: int
    dwarf_data_id: int

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode(sys.stdout.encoding, errors='replace').decode())

@ui.page('/Explore/')
async def dwarf_explore(BackupDriveId:int = None, DwarfId:int = None, mode:str = 'backup', back_url:str = None, SessionId: int = None, only_on_dwarf: int = 0):

    menu(t("page_explore"))
    await ui.context.client.connected(timeout=10.0)

    print(f" BackupDriveId: {BackupDriveId}")
    print(f" DwarfId: {DwarfId}")
    print(f" mode: {mode}")

    # Launch the GUI with the parameters
    try:
        ui.context.explore_app = ExploreApp(DB_NAME, BackupDriveId=BackupDriveId, DwarfId=DwarfId, mode=mode, BackUrl=back_url, SessionId=SessionId, OnlyOnDwarf=bool(only_on_dwarf))
    except Exception as e:
        print(f"[Explore] Failed to initialize page (client may have disconnected): {e}")
        return
    #ui.context.client.on_disconnect(lambda: logger.removeHandler(handler))

class ExploreApp:
    def __init__(self, database, BackupDriveId=None, DwarfId=None, mode='backup', BackUrl=None, SessionId=None, OnlyOnDwarf=False):
        self.database = database
        self.BackupDriveId = BackupDriveId
        self.BackupDriveId_Init = BackupDriveId
        self.DwarfId = DwarfId
        self.mode = mode
        self.OnlyOnDwarf = OnlyOnDwarf
        import urllib.parse as _up
        self.BackUrl = _up.unquote(BackUrl) if BackUrl else BackUrl
        self.SessionId = SessionId
        self.AutoSelection_done = False
        self.only_on_dwarf = False
        self.only_on_backup = False
        self.dwarf_options = []
        self.backup_options = []
        self.all_files_rows = []
        self.objects = []
        self.base_folder = None
        self.selected_object = None
        self.selected_object_description = None
        self.selected_object_is_group = False
        self.preview_image_type = "jpg"
        self.astro_files = {}
        self.slideshow_image_data = []
        self.slideshow_timer_anim = None
        self.slideshow_timer = None
        self.show_gallery_icon = {}
        self.open_folder_icon = {}
        self.preview_icons = {}
        self.fullscreen_icon = {}
        self.backup_session_icon = {}
        self.linked_manual_session_icon = None  # button to jump to linked ManualSession
        self.delete_session_icon = {}
        self.siril_json_icon = {}
        self.action_fits_files_icon = {}
        self.cleanup_fits_files_action  = True
        self.nb_fits_files = None
        self.nb_failed_fits_files = None
        self.nb_tiff_files = None
        self.nb_failed_tiff_files = None
        self.cancel_restore = False
        self.result_on_dwarf = None
        self.result_on_backupDrive = None
        self.selected_sessions_multi = set()  # labels selected for multi-transfer
        self.transfer_multi_btn = None  # button shown when multi-selection active
        self.image_dialog = {}
        self.selected_path = ""
        self.selected_DeleteEntryInfo = None
        self.current_session_row = None
        self.current_backup_location = None
        self.classified_label = None
        self.expanded_nodes = set()
        self.dso_catalog = False
        self.label_to_index = {}
        self.WinLog = WinLog()
        self.mobile_panel = 0  # 0=left, 1=right — used for mobile navigation
        self.mobile_left_col = None
        self.mobile_right_col = None
        self.build_ui()

    def build_ui(self):
        self.conn = connect_db(self.database)
        # Load the preprocessed catalog once at app start
        preprocess_dso_catalog_json(CATALOG_FILE, SKY_CATALOG_FILE)

        if os.path.exists(SKY_CATALOG_FILE): 
            with open(SKY_CATALOG_FILE  , "r", encoding="utf-8") as f:
                self.dso_catalog = json.load(f)
        # parameter for stitch params
        self.stitch_params = get_stitch_params(self.conn)

        # Mobile nav bar - hidden initially, shown when on right panel
        with ui.row().classes('w-full items-center gap-2 mobile-nav-bar') as self.mobile_nav:
            self.mobile_back_btn = ui.button(t("back"), on_click=self._mobile_go_left) \
                .props('flat dense').classes('text-sm')

        # Force initial mobile layout
        ui.run_javascript('''
            function initMobileLayout() {
                if (window.innerWidth <= 768) {
                    document.querySelectorAll(".mobile-right-col").forEach(e => e.style.display="none");
                    document.querySelectorAll(".mobile-left-col").forEach(e => e.style.display="flex");
                    document.querySelectorAll(".mobile-nav-bar").forEach(e => e.style.display="none");
                }
            }
            if (document.readyState === "complete") {
                initMobileLayout();
            } else {
                window.addEventListener("load", initMobileLayout);
            }
            setTimeout(initMobileLayout, 300);
            setTimeout(initMobileLayout, 1000);
        ''')

        with ui.row().classes('w-full items-start'):
            with ui.grid(columns='1fr 2fr').classes('w-full items-start mobile-explore-grid'):
                with ui.column().classes('w-full mobile-left-col') as self.mobile_left_col:
                    if self.mode == "backup":
                        nbcolumns = 3 if self.BackUrl else 2
                        with ui.grid(columns=nbcolumns):
                            if self.BackUrl:
                                ui.button(t("back_btn"), on_click=lambda: ui.navigate.to(f"{self.BackUrl}{self.BackupDriveId if self.BackupDriveId else self.BackupDriveId_Init}")).style('width: 100px')
                            with ui.column() as self.backup_filter_col:
                                ui.label(t("backup_drive"))
                                self.backup_filter = ui.select(options=[], on_change=self.on_backup_filter_change).props('outlined')

                            with ui.column() as self.dwarf_filter_col:
                                ui.label(t("dwarf_device"))
                                self.dwarf_filter = ui.select(options=[], on_change=self.load_objects).props('outlined')

                        with ui.card().tight().classes('pr-3').bind_visibility_from(self.dwarf_filter, "value", lambda value: value != t("all_dwarfs")):
                            self.only_on_dwarf = ui.checkbox(t("only_backed_up"),on_change = self.on_change_only_on_dwarf)
                            self.only_on_backup = ui.checkbox(t("only_backed_not_dwarf"),on_change = self.on_change_only_on_backup)
                            self.only_duplicates_backup = ui.checkbox(t("only_duplicates"),on_change = self.load_objects)
                    else:
                        if self.BackUrl:
                            with ui.grid(columns=2):
                                ui.button(t("back_btn"), on_click=lambda: ui.navigate.to(f"{self.BackUrl}{self.get_selected_dwarf_id() if self.get_selected_dwarf_id() else self.DwarfId}")).style('width: 100px')

                                with ui.row().classes('w-full') as self.dwarf_filter_col:
                                    ui.label(t("dwarf_device"))
                                    self.dwarf_filter = ui.select(options=[], on_change=self.load_objects).props('outlined')

                        else:

                            with ui.row().classes('w-full') as self.dwarf_filter_col:
                                ui.label(t("dwarf_device"))
                                self.dwarf_filter = ui.select(options=[], on_change=self.load_objects).props('outlined')

                        with ui.row().classes('w-full'):
                            with ui.card().tight().bind_visibility_from(self.dwarf_filter, "value", lambda value: value != t("all_dwarfs")):
                                ui.label("")
                                self.only_on_dwarf = ui.checkbox(t("only_not_backed"), value=self.OnlyOnDwarf, on_change = self.on_change_only_on_dwarf)
                                ui.label("")
                                self.only_on_backup = ui.checkbox(t("only_already_backed"),on_change = self.on_change_only_on_backup)

                    self.count_label = ui.label(t("total_sessions_zero"))
                    with ui.card().tight().classes('w-full'):
                        with ui.row().classes('items-center m-4 gap-2'):
                            self.object_filter = (
                                ui.input(placeholder=t('filter_objects'), on_change=lambda e: self.load_objects_ui() if e.value else self.load_objects())
                                .classes('flex-1')
                                .props('clearable')
                            )
                            self.refresh_btn = (
                                ui.button(icon='refresh', on_click=self.load_objects)
                                .props('flat round dense')
                                .bind_visibility_from(self.object_filter, 'value', lambda v: bool(v))
                            )
                            self.object_spinner = ui.spinner(size="lg")

                        self.object_list = ui.list().classes('w-full max-h-400 overflow-y-auto')

                with ui.column().classes('w-full mobile-right-col') as self.mobile_right_col:
                    # Create the dialog that simulates fullscreen
                    with ui.dialog().props('maximized') as self.image_dialog, ui.card().classes("w-full h-full no-padding"):
                        self.fullscreen_image = ui.image().classes('w-full h-auto object-contain')
                        ui.button('✕', on_click=self.image_dialog.close) \
                            .props('round flat') \
                            .classes('absolute top-2 right-2 z-10 bg-black text-white opacity-70')

                    with ui.row().classes('w-full'):
                        with ui.column().classes('w-full'):
                            ui.label(t("session_list"))
                            self.file_list = ui.select(options=[], on_change=self.on_file_selected).props('outlined').style('overflow-x: auto;')
                            self.file_list.style('overflow: hidden; text-overflow: ellipsis;')

                        with ui.row().classes('items-center gap-4') as self.icon_row:
                            self.show_gallery_icon = ui.button(t("show_gallery"), on_click=lambda: self.show_gallery()).classes('h-16')
                            self.show_gallery_icon.visible = False
                            self.open_folder_icon = ui.button(t("open_folder_icon"), on_click=lambda: self.open_folder()).classes('h-16')
                            self.fullscreen_icon = ui.button(t("show_fullscreen_img"), on_click=self.show_fullscreen_image).classes('h-16')
                            self.backup_session_icon = ui.button(t("backup_session"), on_click=lambda: self._navigate_backup()).classes('h-16')
                            self.backup_session_icon.visible = False
                            self.transfer_multi_btn = ui.button(t("backup_selected"), on_click=lambda: ui.navigate.to(self.get_multi_transfer_url())).classes('h-16')
                            self.transfer_multi_btn.visible = False
                            self.delete_session_icon = ui.button(t("delete_session"), on_click=lambda: self.delete_directory()).classes('h-16')
                            self.delete_session_icon.visible = False
                            # Link to the ManualSession that was imported alongside this BackupEntry
                            self.linked_manual_session_icon = ui.button(
                                t("view_linked_manual"),
                                on_click=self.navigate_to_linked_manual_session,
                            ).classes('h-16')
                            self.linked_manual_session_icon.visible = False
                            self.action_fits_files_icon = ui.button("", on_click=lambda: self.action_cleanup_restore_fits()).classes('h-16')
                            self.action_fits_files_icon.visible = False
                            self.siril_json_icon = ui.button(
                                t("prepare_siril"),
                                on_click=self.prepare_siril_json
                            ).classes('h-16')
                            self.siril_json_icon.visible = False
                            self.update_preview_icons()  # populate icons

                            #self.preview_icons['jpg'] = ui.image('image/image-jpg.png').classes('w-16 h-16 cursor-pointer hover:opacity-80').tooltip('JPG File')
                            #self.preview_icons['png'] = ui.image('image/image-png.png').classes('w-16 h-16 cursor-pointer hover:opacity-80').tooltip('PNG File')
                            #self.preview_icons['fits'] = ui.image('image/image-fits.png').classes('w-16 h-16 cursor-pointer hover:opacity-80').tooltip('FITS File')

                            #Optional: Add click behavior
                            #self.preview_icons['jpg'].on('click', lambda e: ui.notify(t("jpg_icon_clicked")))
                            #self.preview_icons['png'].on('click', lambda e: ui.notify(t("png_icon_clicked")))
                            #self.preview_icons['fits'].on('click', lambda e: ui.notify(t("fits_icon_clicked")))

                    with ui.row().classes('w-full'):
                        with ui.card().tight().classes('w-full'):
                            # List on the side
                            self.details_files = ui.list().classes('w-full overflow-y-auto')
                            self.details_preview = ui.list().classes('w-full overflow-y-auto')

                    with ui.row().classes('w-full'):
                        self.preview_image = ui.image().classes('w-full h-auto mb-4').props('fit=contain').on('click', self.show_fullscreen_image)

        self.fullscreen_image.visible = False
        self.preview_image.visible = False
        self.object_spinner.set_visibility(False)

        if self.mode == "backup":
            self.populate_backup_filter()
        else:
            self.populate_dwarf_filter()

        self.selected_path = ""

    def show_fullscreen_image(self):
        if self.fullscreen_image.visible: 
            self.image_dialog.open()
            ui.notify(t("press_esc"), position="top", type="info")

    def populate_backup_filter(self):
        print(f"backup_filter: {self.BackupDriveId}")
        self.backup_options = get_backupDrive_Names(self.conn)

        # Only add ALL_BACKUPS when there are multiple backup drives
        if len(self.backup_options) > 1:
            names = [t("all_backups")] + [name for _, name in self.backup_options]
        else:
            names = [name for _, name in self.backup_options]
        initial_value = names[0] if names else None
        if self.BackupDriveId:
            match = next((name for did, name in self.backup_options if did == self.BackupDriveId), None)
            if match:
                initial_value = match
        self.backup_filter.set_options(names, value=initial_value)

    async def on_backup_filter_change(self):
        current_dwarf_id = self.get_selected_dwarf_id()
        print(f"on_backup_filter_change: {self.BackupDriveId}-{current_dwarf_id}")
        current_backup_id = self.BackupDriveId
        selected_name = self.backup_filter.value
        if selected_name == t('all_backups'):
            self.BackupDriveId = None
        else:
            for bid, name in self.backup_options:
                if name == selected_name:
                    self.BackupDriveId = bid
                    break
        self.populate_dwarf_filter()

        # reload objects if neccessary : new BackupDriveId and same dwarf_id
        if current_backup_id != self.BackupDriveId and current_dwarf_id == self.get_selected_dwarf_id():
            await self.load_objects()

    def populate_dwarf_filter(self):
        current_dwarf_id = self.get_selected_dwarf_id()
        print(f"dwarf_filter: {self.BackupDriveId}-{current_dwarf_id}")
        if self.BackupDriveId:
            self.dwarf_options = get_backupDrive_dwarfNames(self.conn, self.BackupDriveId)
            names = [name for _, name in self.dwarf_options]
        else:
            self.dwarf_options = get_dwarf_Names(self.conn)
            names = [name for _, name in self.dwarf_options]

        print(names)

        # Only add ALL_DWARFS when there are multiple dwarfs
        if not self.BackupDriveId and len(self.dwarf_options) > 1:
            names = [t("all_dwarfs")] + names
        initial_value = names[0] if names else None
        matching_value = current_dwarf_id or self.DwarfId
        if matching_value:
            match = next((name for did, name in self.dwarf_options if did == matching_value), None)
            if match:
                initial_value = match
        self.dwarf_filter.set_options(names, value=initial_value)

    def get_selected_dwarf_id(self):
        value = self.dwarf_filter.value
        if self.BackupDriveId is None:
            if value == t('all_dwarfs'):
                return None
            return next((id_ for id_, name in self.dwarf_options if name == value), None)
        else:
            return next((id_ for id_, name in self.dwarf_options if name == value), None)

    async def on_change_only_on_dwarf(self):
        if self.only_on_dwarf.value and self.only_on_backup.value:
            self.only_on_backup.value = False
        await self.load_objects()

    async def on_change_only_on_backup(self):
        if self.only_on_dwarf.value and self.only_on_backup.value:
            self.only_on_dwarf.value = False
        await self.load_objects()
      
    async def load_objects(self):

        self.object_spinner.set_visibility(True)
        dwarf_id = self.get_selected_dwarf_id()
        # Save current selection — restore it after reload if still in list
        saved_object      = self.selected_object
        saved_description = self.selected_object_description
        saved_is_group    = self.selected_object_is_group
        self.clear_selected_object()
        await asyncio.sleep(0.1)
        if self.mode == "backup":
            show_only_dwarf = self.only_on_dwarf.value if self.only_on_dwarf else False
            show_only_backup = self.only_on_backup.value if self.only_on_backup else False
            show_only_duplicates = self.only_duplicates_backup.value if self.only_duplicates_backup else False
            if show_only_duplicates:
                self.objects = get_Objects_duplicate_backup(self.conn, self.BackupDriveId, dwarf_id, show_only_dwarf, show_only_backup, self.object_filter.value)
                count = get_countObjects_duplicate_backup(self.conn, self.BackupDriveId, dwarf_id, show_only_dwarf, show_only_backup, self.object_filter.value)
            else: 
                self.objects = get_Objects_backup(self.conn, self.BackupDriveId, dwarf_id, show_only_dwarf, show_only_backup, self.object_filter.value)
                count = get_countObjects_backup(self.conn, self.BackupDriveId, dwarf_id, show_only_dwarf, show_only_backup, self.object_filter.value)
        else:
            show_only_dwarf = self.only_on_dwarf.value if self.only_on_dwarf else False
            show_only_backup = self.only_on_backup.value if self.only_on_backup else False
            self.objects = get_Objects_dwarf(self.conn, dwarf_id, show_only_dwarf, show_only_backup, self.object_filter.value)
            count = get_countObjects_dwarf(self.conn, dwarf_id, show_only_dwarf, show_only_backup, self.object_filter.value)

        self.count_label.text = f"{t('total_matching')} {count}"
        print (f"Total matching sessions: {count}")
        print (f"Total objects: {len(self.objects)}")
        print (f"Total objects: {[f'{oid} - {name} {dso_id} {"G" if is_group else ""}' for oid, name, dso_id, is_group in self.objects]}")

        # Restore previous selection if it still exists in the new list
        visible_names = [name for _, name, _, _ in self.objects]
        if saved_object == ALL_SESSIONS:
            # ALL_SESSIONS is always available — restore and re-trigger
            self.selected_object             = saved_object
            self.selected_object_description = saved_description
            self.selected_object_is_group    = saved_is_group
            self.load_objects_ui()
            ui.timer(0.1, lambda: self._handle_object_click_work(None, None, True), once=True)
        elif saved_object and saved_object in visible_names:
            self.selected_object             = saved_object
            self.selected_object_description = saved_description
            self.selected_object_is_group    = saved_is_group
            for oid, name, dso_id, is_group in self.objects:
                if name == saved_object:
                    self.load_objects_ui()
                    ui.timer(0.1, lambda o=oid, d=dso_id, g=is_group: self._handle_object_click_work(o, d, g), once=True)
                    break
        else:
            self.selected_object = None
            self.selected_object_description = None
            self.selected_object_is_group = False
            self.load_objects_ui()
        self.object_spinner.set_visibility(False)

        # ✅ Auto-select session if provided and at first
        if not self.AutoSelection_done and self.SessionId:
            self.AutoSelection_done = True
            self.object_spinner.set_visibility(True)
            await self.auto_select_session()
 
    async def auto_select_session(self):
        print(f"Auto-select session: {self.SessionId}")

        if not self.SessionId:
            return

        # Search by session_id alone — BackupEntry.id is globally unique
        sessions = get_sessions_backup(self.conn, session_id=self.SessionId)

        if not sessions:
            print("No session found for auto-selection")
            return

        session = sessions[0]
        # session[0]=id, cols include backup_drive_id via JOIN
        # Ensure the correct backup drive is selected
        try:
            cursor = self.conn.cursor()
            row = cursor.execute(
                "SELECT backup_drive_id FROM BackupEntry WHERE id=?", (self.SessionId,)
            ).fetchone()
            if row and row[0]:
                self.BackupDriveId = row[0]
                # Update the backup filter to match
                for bid, name in self.backup_options:
                    if bid == self.BackupDriveId:
                        self.backup_filter.set_value(name)
                        break
        except Exception as e:
            print(f"[auto_select] could not set BackupDriveId: {e}")

        print("Auto-selecting session via ALL_SESSIONS")
        await self._handle_object_click(None, ALL_SESSIONS, ALL_SESSIONS, None, True, self.SessionId)

    def _update_expanded_nodes(self, expanded_keys: list[str]):
        self.expanded_nodes = set(expanded_keys)

    def load_objects_ui(self, init_view=True):
        from collections import defaultdict

        self.object_list.clear()
        filter_dso = set()
        visible_names = []
        dso_id_counts = defaultdict(int)
        self.tree_data_lookup = {}
        node_selected = None

        # Step 1: Count how many times each dso_id appears after filtering
        for _, name, dso_id, _ in self.objects:
            name_object, _ = get_name_object(name)
            if self.object_filter.value and self.object_filter.value.lower() not in name_object.lower():
                if dso_id is not None:
                    filter_dso.add(dso_id)
                continue
            if dso_id is not None:
                dso_id_counts[dso_id] += 1

        shown_all_for_dso = set()
        grouped_objects = defaultdict(list)
        priority_order = {
            ALL_SESSIONS: 0,
            "Manual": 1,
            "MOSAIC_Unknown": 2,
            "Unknown": 3,
        }

        def sort_key(name_object):
            return (priority_order.get(name_object, 4), name_object.casefold())

        def base_name_equals(name1: str, name2: str) -> bool:
            def get_base(name):
                if name:
                    return name.rsplit(" _ ", 1)[0].strip()
                else:
                    return None

            return get_base(name1) == get_base(name2)

        # Step 2: Group objects by display name
        for oid, name, dso_id, is_group in self.objects:
            name_object, _ = get_name_object(name)
            if self.object_filter.value and self.object_filter.value.lower() not in name_object.lower():
                continue
            grouped_objects[name_object].append((oid, name, dso_id, is_group))

        display_items = []

        all_sessions_name = ALL_SESSIONS
        all_sessions_display = t("all_sessions_display")
        grouped_objects[all_sessions_name].append((None, all_sessions_name, None, True))

        for name_object in sorted(grouped_objects.keys(), key=sort_key):
            entries = grouped_objects[name_object]
            visible_names.append(name_object)

            if len(entries) == 1:
                oid, full_name, dso_id, is_group = entries[0]

                # Add [ALL] if applicable
                if (
                    dso_id is not None and
                    dso_id_counts[dso_id] > 1 and
                    dso_id not in shown_all_for_dso and
                    dso_id not in filter_dso
                ):
                    all_name = f"{name_object.split(' [')[0]} [ALL]"
                    visible_names.append(all_name)
                    label = f"{'✨ ' if is_group else ''}{all_name}"
                    data = {
                        "oid": None,
                        "name": all_name,
                        "desc": full_name,
                        "dso_id": dso_id,
                        "is_group": is_group,
                    }
                    display_items.append({
                        "type": "item",
                        "label": all_name,
                        "label_full": label,
                        "data": data,
                    })
                    shown_all_for_dso.add(dso_id)

                # Single object -> flat item
                oid, full_name, dso_id, is_group = entries[0]
                display_name = t('all_sessions_display') if name_object == ALL_SESSIONS else name_object
                label = f"{'✨ ' if is_group else ''}{display_name}"
                data = {
                    "oid": oid,
                    "name": name_object,
                    "desc": full_name,
                    "dso_id": dso_id,
                    "is_group": is_group,
                }
                display_items.append({
                    "type": "item",
                    "label": display_name,
                    "label_full": label,
                    "data": data,
                })

            else:
                # Multiple entries -> tree node
                children = []
                for index, (oid, full_name, dso_id, is_group) in enumerate(entries, start=1):
                    name_item = f"{name_object} .{index}"
                    label = f"{'✨ ' if is_group else ''}{name_item}"
                    node_id = f"obj_{oid}"
                    data = {
                        "oid": oid,
                        "name": name_item,
                        "desc": full_name,
                        "dso_id": dso_id,
                        "is_group": is_group,
                    }
                    is_selected = self.selected_object == name_item
                    if is_selected:
                        node_selected = node_id
                    visible_names.append(name_item)
                    children.append({
                        "id": node_id,
                        "label": label,
                        "data": data,
#                        "style": "background-color: var(--q-primary); color: white;" if is_selected else "",
                        "icon": "check" if is_selected else None,  # optional icon
                    })
                    self.tree_data_lookup[node_id] = data

                # Add [ALL] if applicable
                dso_id = entries[0][2]  # dso_id from first item
                full_name = entries[0][1]
                is_group = entries[0][3]
                if (
                    dso_id is not None and
                    dso_id_counts[dso_id] > 1 and
                    dso_id not in shown_all_for_dso and
                    dso_id not in filter_dso
                ):
                    all_name = f"{name_object} [ALL]"
                    all_node_id = f"all_{dso_id}"
                    visible_names.append(all_name)
                    is_selected = self.selected_object == all_name
                    if is_selected:
                        node_selected = all_node_id
                    children.insert(0, {
                        "id": all_node_id,
                        "label": all_name,
                        "data": {
                            "oid": None,
                            "name": all_name,
                            "desc": full_name,
                            "dso_id": None,
                            "is_group": is_group,
                        },
                        "icon": "check" if is_selected else None,  # optional icon
#                        "style": "background-color: var(--q-primary); color: white;" if is_selected else "",                        "icon": "check" if is_selected else None,  # optional icon
                    })
                    self.tree_data_lookup[all_node_id] = {
                        "oid": None,
                        "name": all_name,
                        "desc": full_name,
                        "dso_id": dso_id,
                        "is_group": is_group,
                    }
                    shown_all_for_dso.add(dso_id)

                children.sort(key=lambda c: c["label"].lower())
                display_items.append({
                    "type": "tree",
                    "label": name_object,
                    "node": {
                        "id": name_object,
                        "label": f"{name_object} ({len(entries)})",
                        "children": children,
                    }
                })

        # Step 3: Render UI
        with self.object_list:
            ui.item_label(t('list_objects')).props('header').classes('text-bold')
            ui.separator()

            def handle_click(data):
                self.selected_object = data["name"]
                self._handle_object_click(data["oid"], data["name"], data["desc"], data["dso_id"], data["is_group"])

            def handle_select(event):
                node_id = event.value
                if not node_id:
                    return
                data = self.tree_data_lookup.get(node_id)
                if data:
                    handle_click(data)

            # Highlight selected in nodes
            def customize_tree_nodes(nodes, selected_name):
                for node in nodes:
                    if node.get("data", {}).get("name") == selected_name:
#                        node["style"] = "background-color: var(--q-primary); color: white;" if is_selected else "",
                        node["icon"] = "check"
                    else:
                        node["style"] = ""
                    # Recursively apply to children if needed
                    if "children" in node:
                        customize_tree_nodes(node["children"], selected_name)

            for entry in display_items:
                treeview = None
                if entry["type"] == "item":
                    data = entry["data"]
                    item = ui.item(
                        entry["label_full"],
                        on_click=lambda d=data: handle_click(d),
                    )
                    if data["name"] == self.selected_object:
                        item.classes('bg-primary text-white')
                    else:
                        item.classes('bg-transparent')

                elif entry["type"] == "tree":
                    node = entry["node"]
                    #customize_tree_nodes([node], self.selected_object)
                    treeview = ui.tree(
                        nodes=[node],
                        node_key='id',
                        label_key='label',
                        children_key='children',
                        on_select=handle_select,
                        on_expand=lambda e: self._update_expanded_nodes(e.value),
                    ).expand()

                if node_selected and treeview:
                    treeview.props(add=f"selected={node_selected}")

        if self.selected_object not in visible_names:
            self.selected_object = None
            self.clear_selected_object()

        self.object_list.update()
        ui.update()
        self.object_spinner.set_visibility(False)

    def _handle_object_click(self, oid, name, desc, dso_id, is_group, session_id = None):
        self.object_spinner.set_visibility(True)
        self.selected_object = name 
        self.selected_object_description = desc 
        self.selected_object_is_group = is_group
        ui.timer(0.05, lambda: self._handle_object_click_work(oid, dso_id, is_group, session_id), once=True)

    def _handle_object_click_work(self, oid, dso_id, is_group, session_id = None):
        self.select_object(oid, dso_id, is_group, session_id)
        self.load_objects_ui()
        self.object_spinner.set_visibility(False)

    def clear_selected_object(self):
        self.fullscreen_image.visible = False
        self.preview_image.visible = False

        self.details_files.clear()
        self.details_preview.clear()
        self.reset_preview_icons()
        self.file_list.set_options([])
        self.all_files_rows = []
        self.selected_sessions_multi.clear()
        if self.transfer_multi_btn:
            self.transfer_multi_btn.visible = False

    def _is_mobile(self):
        """Returns True if screen width <= 768px (evaluated client-side via JS)."""
        # We rely on the mobile_back_btn visibility as proxy —
        # on desktop the CSS hides the nav bar anyway so no visual impact.
        return True  # always call, CSS on desktop hides the nav bar

    def _mobile_go_right(self):
        """On mobile only: hide left column, show right column."""
        if self.mobile_left_col and self.mobile_right_col:
            ui.run_javascript('''
                if (window.innerWidth <= 768) {
                    document.querySelectorAll(".mobile-left-col").forEach(e => e.style.display="none");
                    document.querySelectorAll(".mobile-right-col").forEach(e => e.style.display="flex");
                    document.querySelectorAll(".mobile-nav-bar").forEach(e => e.style.display="flex");
                }
            ''')

    def _mobile_go_left(self):
        """On mobile only: show left column, hide right column."""
        if self.mobile_left_col and self.mobile_right_col:
            ui.run_javascript('''
                if (window.innerWidth <= 768) {
                    document.querySelectorAll(".mobile-left-col").forEach(e => e.style.display="flex");
                    document.querySelectorAll(".mobile-right-col").forEach(e => e.style.display="none");
                    document.querySelectorAll(".mobile-nav-bar").forEach(e => e.style.display="none");
                }
            ''')

    def select_object(self, object_id, dso_id, is_group, session_id = None):
        dwarf_id = self.get_selected_dwarf_id()
        details = []
        self.clear_selected_object()
        self._mobile_go_right()  # slide to right panel on mobile

        if self.mode == "backup":
            show_only_duplicates = self.only_duplicates_backup.value if self.only_duplicates_backup else False
            if show_only_duplicates:
                files = get_ObjectSelect_duplicate_backup(self.conn, object_id, dso_id, self.BackupDriveId, dwarf_id, self.only_on_dwarf.value, self.only_on_backup.value, is_group, self.object_filter.value, session_id)
            else:
                files = get_ObjectSelect_backup(self.conn, object_id, dso_id, self.BackupDriveId, dwarf_id, self.only_on_dwarf.value, self.only_on_backup.value, is_group, self.object_filter.value, session_id)
        else:
            files = get_ObjectSelect_dwarf(self.conn, object_id, dso_id, dwarf_id, self.only_on_dwarf.value, self.only_on_backup.value, is_group, self.object_filter.value, session_id)

        # Store all rows globally so we can access them later
        self.all_files_rows = [list(row) for row in files]
        self.selected_DeleteEntryInfo = None
        self.update_gallery_icon()
    
        if len(files) == 0:
     
            self.label_to_index = {}
            self.file_list.set_options([])
            with self.details_files:
                ui.item_label(t('no_session_found')).props('header').classes('text-bold')

        if len(files) == 1:
            self.selected_DeleteEntryInfo = BackupEntryData(
                backup_drive_id=files[0][19],
                dwarf_id=files[0][20],
                dwarf_data_id=files[0][0]
            )
            # If only one file, put it in the ComboBox and display it directly
            file_path = files[0][1]
            backup_path = files[0][6]  # location from BackupDrive or USB Dwarf

            full_path = get_Backup_fullpath (self.conn, backup_path, "", file_path)
            
            select_file = [file_path]
            self.label_to_index[file_path] = 0
            self.file_list.set_options(select_file, value=select_file[0])

        else:
            # Populate combobox with readable file names
            details = []
            value_select = f"{t('select_session_for')} {self.selected_object}"
            if self.selected_object == ALL_SESSIONS:
                value_select = f"{t('select_session_for')} {t("all_sessions")}"
            select_file = [value_select]
            stackeds = 0
            total_time_exp = 0
            self.label_to_index = {}

            for idx, row in enumerate(files):
                # Extracting values for clarity
                self.selected_DeleteEntryInfo = BackupEntryData(
                    backup_drive_id=row[19],
                    dwarf_id=row[20],
                    dwarf_data_id=row[0]
                )
                # extract DB Values
                dwarf_data_id = row[0]
                file_path = row[1]
                exp_time = row[2]
                gainDB = row[3]
                IR_filter  = row[4]
                stacks = row[5] if row[5] is not None else 0
                backup_path = row[6]  # location from BackupDrive or USB Dwarf
                session_date = row[7]
                session_dir = row[8]
                dwarf_name = row[9]
                minTemp = row[10]
                maxTemp = row[11]
                is_favorite = row[12]  # The favorite column (0 or 1)
                init_target = row[13] if row[13] is not None else UNKNOWN
                declination = row[14]
                right_ascencion = row[15]
                astro_object_id = row[16]
                astro_group_id = row[17]
                descriptionDB = row[18]

                # display Values
                session_date = show_short_date_session(session_date)
                lens = "(W)" if ("_WIDE_") in session_dir else ""
                exp = f"{exp_time}s" if exp_time is not None else "N/A"
                gain = gainDB if gainDB is not None else "N/A"
                astro_filter = f"{IR_filter}" if IR_filter else "No Filter"
                stackeds += stacks
                if exp_time:
                    total_time_exp += stacks * parse_exposure(f"{exp_time}s")

                # Displaying star icon based on favorite status only in backup mode
                star_icon = '⭐ ' if is_favorite else '☆ '
                bad_icon = '❗ ' if int(stacks) < 50 else ''
                info_stack = t("restack") if is_Restacked(session_dir) else t("taken")
                target = init_target[:10]
                description,_ =  get_name_object(descriptionDB)
                # Building the details string with the star icon
                label_text = f"{info_stack} {t('with_label')} 🔭 {dwarf_name}{lens} 📅 {session_date} ⚙️ Exp {exp}, Gain {gain}, {astro_filter} 📊 Stacks {stacks} 🛰️ {description}"

                # If label already exists (duplicate), append a small invisible suffix
                count = 0
                base_label = f"{star_icon}{bad_icon}{label_text}"
                details_text = base_label
                while details_text in self.label_to_index:
                    # Add zero-width character to make it unique
                    count += 1
                    details_text = details_text + ("\u200b" * count)
                details.append(
                    details_text
                )
                self.label_to_index[details_text] = idx
                select_file.append(
                    details_text
                )

            self.file_list.set_options(select_file, value=value_select)

            with self.details_files:
                ui.item_label(f"{len(files)} {t('sessions_found')} {stackeds} {t('stacks_exp')} {format_seconds_hms(total_time_exp)}.").props('header').classes('text-bold')
                ui.separator()

                selected_sessions = set()  # will store selected labels

                def update_buttons():
                    # Enable/disable buttons depending on selection
                    has_selection = len(selected_sessions) > 0
                    restore_button.enabled = has_selection
                    archive_button.enabled = has_selection
                    delete_button.enabled = has_selection

                def toggle_select_all(state: bool):
                    for cb in checkboxes:
                        cb.value = state
                    selected_sessions.clear()
                    if state:
                        for lbl in details:
                            selected_sessions.add(lbl)
                    update_buttons()

                # Enable multi-selection in dwarf mode to allow multi-session transfer
                checkboxes = []
                use_checkboxes = (len(files) > 1) and (
                    (
                        self.mode != "backup"
                        and bool(self.only_on_dwarf and self.only_on_dwarf.value)
                        and bool(self.get_selected_dwarf_id())
                    ) or (
                        self.mode == "backup"
                        and bool(self.only_on_backup and self.only_on_backup.value)
                        and bool(self.BackupDriveId)
                        and bool(self.get_selected_dwarf_id())
                    )
                )

                def on_multi_selection_change():
                    has_sel = (
                        len(self.selected_sessions_multi) > 0
                        and (
                            (
                                self.mode != "backup"
                                and bool(self.only_on_dwarf and self.only_on_dwarf.value)
                                and bool(self.get_selected_dwarf_id())
                            ) or (
                                self.mode == "backup"
                                and bool(self.only_on_backup and self.only_on_backup.value)
                                and bool(self.BackupDriveId)
                                and bool(self.get_selected_dwarf_id())
                            )
                        )
                    )
                    if self.transfer_multi_btn:
                        self.transfer_multi_btn.visible = has_sel
                        if has_sel:
                            self.transfer_multi_btn.set_text(
                                t("restore_selected") if self.mode == "backup"
                                else t("backup_selected")
                            )
                            self.transfer_multi_btn.enable()
                        else:
                            self.transfer_multi_btn.disable()
                    # Keep backup_session_icon mutually exclusive with transfer_multi_btn
                    if self.backup_session_icon:
                        if has_sel:
                            self.backup_session_icon.visible = False
                            self.backup_session_icon.disable()
                        else:
                            # Re-evaluate correct state based on current selection/mode
                            self.update_preview_icons()

                if use_checkboxes:
                    self.selected_sessions_multi.clear()
                    on_multi_selection_change()

                    with ui.row().classes('items-center gap-4 m-2'):
                        select_all_cb = ui.checkbox(t("select_all"), on_change=lambda e: toggle_select_all(e.value))
                        ui.button(t("deselect_all"), on_click=lambda: toggle_select_all(False)).props('flat dense')

                    # Checkboxes for each detail
                    for data_detail in details:
                        def on_check_change(e, label=data_detail):
                            if e.value:
                                self.selected_sessions_multi.add(label)
                            else:
                                self.selected_sessions_multi.discard(label)
                            on_multi_selection_change()

                        with ui.row().classes('items-center gap-2 flex-nowrap'):
                            cb = ui.checkbox(on_change=on_check_change).classes('shrink-0')
                            checkboxes.append(cb)
                            # clickable label still selects single session for detail view
                            ui.label(data_detail).on('click', lambda e, i=data_detail: self.select_single_session(i, checkboxes)).props('clickable').classes('cursor-pointer break-all')

                else:

                    def clean_label(text: str) -> str:
                        # remove star and bad icons
                        return re.sub(r"[⭐☆❗]", "", text).strip()

                    for data_detail in details:
                        ui.item(data_detail, on_click=lambda i=data_detail: self.file_list.set_value(i)).props('clickable').classes('cursor-pointer')

    def open_folder(self, directory = None):
        if not self.selected_path and not directory:
            print("No folder selected!")
            return

        # Normalize the path
        if directory:
            folder_path = os.path.normpath(directory)
        else:
            folder_path = os.path.normpath(self.selected_path)
        if folder_path and os.path.exists(folder_path):
            if os.name == 'nt':  # Windows
                subprocess.Popen(f'explorer "{folder_path}"')
            elif os.name == 'posix':  # macOS or Linux
                subprocess.Popen(['open', folder_path])  # macOS
                # or 'xdg-open' for Linux
        else:
            print("Folder does not exist!")

    async def delete_directory(self, directory=None):
        folder_path = directory or self.selected_path
        if not folder_path:
            ui.notify(t("no_folder_selected"), color="negative")
            return

        folder_path = os.path.normpath(folder_path)

        if not os.path.exists(folder_path):
            ui.notify(f"Folder does not exist:\n{folder_path}", color="negative")
            return

        async def ok_confirm_delete_session():
            try:
                shutil.rmtree(folder_path)
                ui.notify(f"Folder deleted:\n{folder_path}", color="positive")
                # delete data
                if self.selected_DeleteEntryInfo:
                    delete_backup_entry_and_dwarf_data( self.conn, 
                                                        self.selected_DeleteEntryInfo.backup_drive_id,
                                                        self.selected_DeleteEntryInfo.dwarf_id,
                                                        self.selected_DeleteEntryInfo.dwarf_data_id)

            except Exception as e:
                ui.notify(f"Error deleting folder:\n{e}", color="negative")
            finally:
                await self.load_objects()

        # Ask for confirmation
        await self.WinLog.show(
            "Confirm Deletion",
            f"⚠️ Are you sure you want to delete this session?\n\nThe following folder will be completely removed!\n\n{folder_path}",
            ok_confirm_delete_session
        )

    async def action_cleanup_restore_fits(self, directory=None):
        if self.cleanup_fits_files_action:
            await self.cleanup_fits(directory=None)
        else:
            await self.restore_fits(directory=None)

    async def cleanup_fits(self, directory=None):
        folder_path = directory or self.selected_path
        if not folder_path:
            ui.notify(t("no_folder_selected"), color="negative")
            return

        folder_path = os.path.normpath(folder_path)

        if not os.path.exists(folder_path):
            ui.notify(f"Folder does not exist:\n{folder_path}", color="negative")
            return

        async def ok_confirm_cleanup_fits():
            ui.notify(t("clean_fits"))
            try:
                ui.notify(f"Running cleanup on Dwarf Dir: '{folder_path}'", color="positive")
                deleted_count = await run.io_bound(cleanup_fits_files, folder_path)
                if deleted_count > 1:
                    ui.notify(f"{deleted_count} Fits Files on Dwarf have been deleted.", color="positive")
                elif deleted_count == 1:
                    ui.notify(f"One Fits File on Dwarf has been deleted.", color="positive")
                else:
                    ui.notify(f"No Fits Files on Dwarf have been deleted.", color="positive")

            except Exception as e:
                ui.notify(f"Error cleanup folder:\n{e}", color="negative")
            finally:
                await self.load_objects()

        # Ask for confirmation
        await self.WinLog.show(
            "Confirm FITS Cleanup on Dwarf",
            f"⚠️ Are you sure you want to clean up FITS files on the Dwarf for this session?\n\n"
            "All raw FITS files will be permanently removed.\n"
            "The final stacked FITS file will be kept.\n\n",
            ok_confirm_cleanup_fits
        )

    async def restore_fits(self, directory=None):
        dwarf_folder_path = directory or self.selected_path
        print(f"dwarf_folder_path: {dwarf_folder_path}")
        print(f"path_result_on_backupDrive: {self.path_result_on_backupDrive}")
        if not dwarf_folder_path:
            ui.notify(t("no_folder_selected"), color="negative")
            return

        dwarf_folder_path = os.path.normpath(dwarf_folder_path)

        if not os.path.exists(dwarf_folder_path):
            ui.notify(f"Folder does not exist:\n{dwarf_folder_path}", color="negative")
            return

        if not self.path_result_on_backupDrive or not os.path.exists(self.path_result_on_backupDrive):
            ui.notify(f"Folder does not exist:\n{self.path_result_on_backupDrive}", color="negative")
            return

        async def ok_confirm_restore_fits():
            self.cancel_restore = False  # reset cancel flag

            with ui.context.client.layout:
                with ui.dialog().props('persistent') as progress_dialog, ui.card():
                    ui.label(t("restoring_fits"))
                    self.progress = ui.circular_progress(max=100, show_value=True)
                    with ui.row():
                        self.cancel_button = ui.button(t("cancel"), on_click=lambda: setattr(self, "cancel_restore", True))
    
            progress_dialog.open()
            ui.notify(t("restoring_fits"))
            try:
                restored_count, skipped_count, total_fits_files = await run.io_bound(restore_fits_files, self.path_result_on_backupDrive, dwarf_folder_path, self, None)
                if self.cancel_restore:
                    ui.notify(f"Restore cancelled at {restored_count} restored on {total_fits_files} total files, {skipped_count} skipped", color="warning")
                else:
                    ui.notify(f"Restore completed ✅ {restored_count} restored on {total_fits_files} total files, {skipped_count} skipped", color="positive")

            except Exception as e:
                ui.notify(f"Error restoring files:\n{e}", color="negative")
            finally:
                progress_dialog.close()
                await self.load_objects()

        # Ask for confirmation
        await self.WinLog.show(
            "Confirm FITS Restore on Dwarf",
            f"⚠️ Are you sure you want to restore FITS files on the Dwarf for this session?\n\n",
            ok_confirm_restore_fits
        )

    def show_full_image(self, path):
        with ui.dialog().props('maximized') as full_dialog:
            with ui.card().classes("w-full h-full justify-center items-center bg-black"):
                ui.image(path).classes('w-full max-h-full object-contain')
        full_dialog.open()
        ui.notify(t("press_esc"), position="top", type="info")

    def open_gallery_dialog(self, mosaic_dir: str, panels):

        with ui.dialog() as dialog:
            with ui.card().classes("w-full p-4").style("max-width: 2600px; margin: auto"):
                with ui.row().classes('w-full justify-center'):
                    ui.label(t("mosaic_gallery")).classes("text-center mt-2 text-lg font-semibold mr-auto")
                    ui.label(Path(mosaic_dir).name).classes("text-center mt-4 text-md font-medium")
                    ui.button(t("close"), on_click=dialog.close).classes("mt-4 ml-auto")

                with ui.row().classes("justify-center mx-auto"):
                    if len(panels) == 2:
                        with ui.column().classes("gap-2 items-center mx-auto"):
                            for i, (panel_name, image_path) in enumerate(panels, start=1):
                                with ui.column().classes("items-center p-1 border rounded shadow-md"):
                                    print(image_path)
                                    ui.image(image_path).classes('w-[90vw] max-w-[2460px] h-auto rounded mx-auto').props('fit=contain').on('click', lambda path=image_path: self.show_full_image(path))
                                    ui.label(f"Panel {i}").classes("text-sm")
                    
                    elif len(panels) == 4:
                        reordered = [panels[0], panels[1], panels[3], panels[2]]
                        with ui.grid(columns = 2):
                            with ui.column().classes("gap-2 items-center mx-auto"):
                                for i, (panel_name, image_path) in enumerate(reordered[:2], start=1):
                                    with ui.column().classes("items-center p-1 border rounded shadow-md"):
                                        ui.image(image_path).classes('w-[45vw] max-w-[1280px] h-auto rounded mx-auto').props('fit=contain').on('click', lambda path=image_path: self.show_full_image(path))
                                        ui.label(f"Panel {i}").classes("text-sm")
                            with ui.column().classes("gap-2 items-center mx-auto"):
                                for i, (panel_name, image_path) in enumerate(reordered[2:], start=3):
                                    with ui.column().classes("items-center p-1 border rounded shadow-md"):
                                        ui.image(image_path).classes('w-[45vw] max-w-[1280px] h-auto rounded mx-auto').props('fit=contain').on('click', lambda path=image_path: self.show_full_image(path))
                                        ui.label(f"Panel {3-int(i) + 4}").classes("text-sm")

        dialog.open()

    async def on_file_selected(self):
        selection_index = None
        selected_value = self.file_list.value
        details = []

        if not selected_value or selected_value.startswith(t('select_session_for').split(' {')[0]):
            return

        self.details_files.clear()
        self.details_preview.clear()
        self.reset_preview_icons()
        self.selected_DeleteEntryInfo = None

        details_files_text = ""
        if selected_value and len(self.all_files_rows) == 1:
            selection_index = 0

        # Try to find the selected value in the options and get the corresponding index
        try:

            # Map the selected label back to the correct row index
            # remove icons
            selection_index = self.label_to_index.get(selected_value)

        except ValueError:
            print("Selected value not found")

        if selection_index is not None:

            row = self.all_files_rows[selection_index]

            self.selected_DeleteEntryInfo = BackupEntryData(
                backup_drive_id=row[19],
                dwarf_id=row[20],
                dwarf_data_id=row[0]
            )
            self.current_session_row = row
            self.current_backup_location = row[6] if row[6] else ""
            # extract DB Values
            dwarf_data_id = row[0]
            file_path = row[1]
            exp_time = row[2]
            gainDB = row[3]
            IR_filter  = row[4]
            stacks = row[5] if row[5] is not None else 0
            backup_path = row[6]  # location from BackupDrive or USB Dwarf
            session_date = row[7]
            session_dir = row[8]
            dwarf_name = row[9]
            minTemp = row[10]
            maxTemp = row[11]
            is_favorite = row[12]  # The favorite column (0 or 1)
            init_target = row[13] if row[13] is not None else UNKNOWN
            declination = row[14]
            right_ascencion = row[15]
            astro_object_id = row[16]
            astro_group_id = row[17]
            descriptionDB = row[18]
            # row[19]=backup_drive_id  row[20]=dwarf_id  row[21]=binning
            dwarf_id = row[20]
            _binning_raw = row[21] if len(row) > 21 else None
            try:
                binning = int(str(_binning_raw).split("*")[0]) if _binning_raw else 1
            except Exception:
                binning = 1

            # display Values
            info_stack = t("restack") if is_Restacked(session_dir) else t("taken")
            star_icon = '⭐ ' if is_favorite else '☆ '
            full_path = get_Backup_fullpath (self.conn, backup_path, "", file_path, self.get_selected_dwarf_id())
            self.selected_path = os.path.dirname(full_path)
            self.current_session_full_dir = self.selected_path

            # Store the base folder once
            self.base_folder = full_path.replace("\\", "/").rsplit(file_path.replace("\\", "/"), 1)[0]
            set_base_folder(full_path.replace("\\", "/").rsplit(file_path.replace("\\", "/"), 1)[0])
            lens = "(Wide)" if ("_WIDE_") in session_dir else "(Tele)"

            details_files_text = f"{star_icon}{info_stack} {t('with_label')} 🔭 {dwarf_name} {lens} {t("on_label")} 📅 {show_date_session(session_date)}"

            # details

            #details.append(f"Session: {session_dir}")
            details.append(f"🛰️ {t('dwarf_target')}: {init_target}")

            classified_text, descriptiondb = self.update_classified_label(astro_object_id, init_target, "", True)
            if classified_text:
                details.append(classified_text)
            details.append(f"RA: {hours_to_hms(right_ascencion)} | Dec: {deg_to_dms(declination)}")

            lens = "Wide" if ("_WIDE_") in session_dir else "Tele"
            exp = f"️{exp_time}s" if exp_time is not None else "N/A"
            gain = gainDB if gainDB is not None else "N/A"

            details.append(f"⚙️ {t('lens_label')}: {lens} | {t('exposure_label')}: {exp} | {t('gain_label')}: {gain} | {t('filter_label')}: {IR_filter}")
            if minTemp and maxTemp:
                details.append(f"{t('min_temp')}: {minTemp} | {t('max_temp')}: {maxTemp}")
            bad_icon = '❗ ' if int(stacks) < 50 else ''
            details.append(f"📊 Stacks: {bad_icon}{stacks}")

            self.astro_files = check_files(full_path)

            with self.details_files:
                label = ui.item_label(f"{details_files_text}").props('header').classes('text-bold').props('clickable').classes(f'cursor-pointer {self.get_hover_class()} transition-colors duration-200 rounded')
                # Set the tooltip text based on the favorite state
                tooltip_text = "Click to Remove from Favorites" if is_favorite else "Click to Add to Favorites"
                # Add tooltip
                label.props(f'title="{tooltip_text}"')
                # Make the label clickable to toggle favorite
                label.on('click', lambda _, eid=dwarf_data_id, lbl=label, mode=self.mode: self.toggle_favorite_ui(eid, lbl, mode))
                ui.separator()

                # Add colored details
                ui.item(f"Session: {session_dir}").classes('text-blue-800')
                with ui.row().classes('w-full gap-8 items-start'):
                    ui.item(f"🛰️ {t('dwarf_target')}: {init_target}").classes('text-green-600')
                    if self.dso_catalog:
                        ui.button(t("identify_target"), on_click=lambda: self.on_identify_target_click(DwarfData.from_row(row), descriptiondb))

                self.classified_label = ui.label().classes('text-gray-500').classes("m-4")
                self.update_classified_label(astro_object_id, init_target, descriptiondb)

                ui.item(f"RA: {hours_to_hms(right_ascencion)} | Dec: {deg_to_dms(declination)}").classes('text-purple-600')

                lens = "Wide" if ("_WIDE_") in session_dir else "Tele"
                exp = f"{exp_time}s" if exp_time is not None else "N/A"
                exp_value = parse_exposure(exp) if exp != "N/A" else 0
                gain = gainDB if gainDB is not None else "N/A"
                with ui.row().classes('w-full gap-8 items-start'):
                    ui.item(f"⚙️ {t('lens_label')}: {lens} | {t('exposure_label')}: {exp} | {t('gain_label')}: {gain} | {t('filter_label')}: {IR_filter}").classes('text-yellow-700')

                    if minTemp and maxTemp:
                        ui.item(f"{t('min_temp')}: {minTemp} | {t('max_temp')}: {maxTemp}").classes('text-sky-700')

                color = 'text-red-600' if stacks < 100 else 'text-indigo-600'
                
                # get exposure for Restacked session
                exposure_time = format_seconds_hms(exp_value * stacks)
                if is_Restacked(session_dir):
                    if "_MOSAIC_" in full_path:
                        exposure_time = format_seconds_hms(get_total_mosaic_exposure(os.path.dirname(full_path)))
                    else:
                        fits_path = self.astro_files.get('fits')
                        if fits_path and os.path.isfile(fits_path):
                            exposure_time = format_seconds_hms(get_total_exposure(fits_path))

                ui.item(f"📊 {stacks} {t('stacked_shots')} {exposure_time}").classes(color)

                # --- Dark match badge ---
                if dwarf_id and exp_time and gainDB:
                    try:
                        _dark = find_matching_darks(
                            self.conn,
                            dwarf_id = dwarf_id,
                            exp_s    = float(exp_time),
                            gain     = int(gainDB),
                            binning  = binning,
                            min_temp = int(minTemp) if minTemp is not None else None,
                            max_temp = int(maxTemp) if maxTemp is not None else None,
                        )
                        if _dark["status"] == "matched":
                            ui.item(f"🎯 {_dark['count']} {t('darks_matched_range')}").classes('text-green-600')
                        elif _dark["status"] == "partial":
                            ui.item(f"🎯 {_dark['count']} {t('darks_matched_closest')}").classes('text-orange-500')
                        else:
                            ui.item(t("no_darks_found")).classes('text-red-500')
                    except Exception as _e:
                        print(f"[dark match] {_e}")

                # --- Repair badge ---
                if dwarf_id:
                    repair_row = get_dwarf_session_error_by_dir(self.conn, dwarf_id, session_dir)
                    if repair_row and repair_row["status"] == "REPAIRED":
                        with ui.item():
                            with ui.row().classes("items-center gap-2"):
                                ui.badge("🔧 REPAIRED", color="green").classes("text-sm")
                                if repair_row["session_dir_master"]:
                                    ui.item(f"Repaired from: {repair_row['session_dir_master']}").classes("text-xs text-gray-500")

                # --- Merge in progress badge (from repairInfo.json on disk) ---
                repair_info_path = os.path.join(os.path.dirname(full_path), "repairInfo.json")
                if os.path.exists(repair_info_path):
                    try:
                        import json as _json
                        with open(repair_info_path, "r", encoding="utf-8") as _f:
                            repair_info = _json.load(_f)
                        if repair_info.get("type") == "MERGE":
                            sessions_list = repair_info.get("sessions", [])
                            with ui.item():
                                with ui.row().classes("items-center gap-2"):
                                    ui.badge("🔀 MERGE IN PROGRESS", color="orange").classes("text-sm")
                                with ui.column().classes("gap-0 ml-2"):
                                    ui.label(t("sessions_merged")).classes("text-xs text-gray-500")
                                    for s in sessions_list:
                                        ui.label(f"  • {s}").classes("text-xs font-mono text-gray-600")
                    except Exception:
                        pass

                # add Mosaic Panel Info
                #for data_detail in details:
                #   ui.item(data_detail)

                # --- Session Notes ---
                _be_id = get_backup_entry_id_by_dwarf_data(self.conn, dwarf_data_id)
                if _be_id:
                    with ui.item():
                        session_notes_widget(self.conn, backup_entry_id=_be_id)

            self.preview_image_path = full_path
            await self.update_preview(full_path)
            self.update_preview_icons()

    def on_identify_target_click(self, dwarf_data: DwarfData, descriptiondb):
        #dwarf_data = DwarfData.from_row(row)
        #dwarf_data_id = row[0]
        #target = row[13]
        #dec = row[14]
        #ra = row[15]
        #astro_object_id = row[16]
        #astro_group_id = row[17]

        on_done = lambda: self.update_classified_label(dwarf_data.astro_object_id, dwarf_data.target, "")
        show_unknown_target_dialog(self.conn, dwarf_data, self.dso_catalog, False, on_done)

    # Function to update classified label
    def update_classified_label(self, object_id, target, descriptiondb = "", text_only = False):
        classified = ""
        classified_text = ""
        print(f"object_id: {object_id} target: {target} descriptiondb: {descriptiondb}")
        if not descriptiondb:
            descriptiondb = get_astro_object_description(self.conn, object_id)
        if descriptiondb and descriptiondb != self.selected_object_description and descriptiondb != target:
            classified = descriptiondb
        elif self.selected_object_description and self.selected_object_description != target and self.selected_object_description != ALL_SESSIONS:
            classified = self.selected_object_description.rsplit(" [")[0]

        # Update the label text or text
        if classified:
            classified_text = f"{t('classified_as')} {classified}"

        if not text_only and self.classified_label:
            self.classified_label.set_text(classified_text)

        return classified_text, descriptiondb

    def get_hover_class(self):
        return 'hover:bg-gray-700' if app.storage.user.get('ui_mode', 0) == 'dark' else 'hover:bg-gray-300'

    def toggle_favorite_ui_label(self, entry_id, label_element, mode, select_index, update = False):

        # Call the API function directly
        new_favorite = toggle_favorite(self.conn, entry_id, mode)
        
        # Update the favorite data row_file UI based on the new state
        self.all_files_rows[select_index][12] = new_favorite
        # Update the UI based on the new state
        star_icon = '⭐ ' if new_favorite else '☆ '
        label_text = label_element.text.split(' ', 1)[1]  # Remove existing star
        label_element.set_text(f"{star_icon}{label_text}")
        # Set the tooltip text based on the favorite state
        tooltip_text = "Click to Remove from Favorites" if new_favorite else "Click to Add to Favorites"
        # Add tooltip
        label_element.props(f'title="{tooltip_text}"')
        #label_element.classes('text-yellow-500' if new_favorite else 'text-gray-400')
        if update:
            label_element.update()
        ui.notify(t("favorite_updated"), type="positive")

        return new_favorite

    def toggle_favorite_ui(self, entry_id, label_element, mode):
        selected_value = self.file_list.value

        if not selected_value:
            return

        # Do update only the label if only one option
        if len(self.file_list.options) <= 1:
            self.toggle_favorite_ui_label(entry_id, label_element, mode, 0, True)
            return

        # Get the selected Index on the list
        # the index begin at 0, but "Select a session" use it 
        selection_index = self.label_to_index.get(selected_value)

        # Call the API function directly
        new_favorite = self.toggle_favorite_ui_label(entry_id, label_element, mode, selection_index, True)

        # Build new label with star icon
        star_icon = '⭐ ' if new_favorite else '☆ '
        select_text = selected_value.split(' ', 1)[-1]  # Remove old star if any
        new_select_text = f"{star_icon}{select_text}"

        # Update mapping
        options = list(self.file_list.options)
        if selection_index is not None:
            # Add zero-width suffix if needed
            count = 0
            while new_select_text in self.label_to_index:
                count += 1
                new_select_text = new_select_text + ("\u200b" * count)

            self.label_to_index[new_select_text] = selection_index

            # Update the options list
            # need to add +1 to the selected Index
            # the index begin at 0, but not included "Select a session"
            options[selection_index+1] = new_select_text
            self.file_list.set_options(options, value=new_select_text)

    async def update_preview(self, preview_image_path ):
        details_preview = []
        self.details_preview.clear()
        self.preview_image_type = get_extension(preview_image_path)
        self.preview_image_path = preview_image_path

        # convert Fits for preview
        preview_image_path = await self.set_preview(self.preview_image_path)
        file_path = get_file_path(preview_image_path, self.base_folder)

        size_dir_kb = None
        size_dir_mb = None
        size_kb = None
        size_mb = None
        self.nb_fits_files = None
        self.nb_failed_fits_files = None
        self.nb_tiff_files = None
        self.nb_failed_tiff_files = None
        restacked_session = False
        try:
            directory = os.path.dirname(self.preview_image_path)
            restacked_session = is_Restacked(os.path.basename(directory))
            size_dir_kb = get_directory_size(directory) / 1024
            size_dir_mb = size_dir_kb / 1024
            size_kb = os.path.getsize(self.preview_image_path) / 1024
            size_mb = size_kb / 1024
            self.nb_fits_files = count_fits_files(directory)
            self.nb_failed_fits_files = count_failed_fits_files(directory)
            self.nb_tiff_files = count_tiff_files(directory)
            self.nb_failed_tiff_files = count_failed_tiff_files(directory)

        except FileNotFoundError:
            print("File not found")
            pass
        except Exception as e:
            print(f"Unexpected error: {e}")
            size_dir_kb = None
            size_dir_mb = None
            size_kb = None
            size_mb = None

        if self.nb_fits_files is not None and self.nb_fits_files == 1:
            details_preview.append(t("found_one_fits"))
        if self.nb_fits_files is not None and self.nb_fits_files > 1:
            details_preview.append(f"{self.nb_fits_files} {t('found_fits_images')}")
        if self.nb_failed_fits_files is not None and self.nb_failed_fits_files == 1:
            details_preview.append(f"Found one failed image on the disk")
        if self.nb_failed_fits_files is not None and self.nb_failed_fits_files > 1:
            details_preview.append(f"{self.nb_failed_fits_files} {t('found_failed_images')}")

        if self.nb_tiff_files is not None and self.nb_tiff_files == 1:
            details_preview.append(f"Found one tiff image on the disk")
        if self.nb_tiff_files is not None and self.nb_tiff_files > 1:
            details_preview.append(f"Found {self.nb_tiff_files} tiff images on the disk")
        if self.nb_failed_tiff_files is not None and self.nb_failed_tiff_files == 1:
            details_preview.append(f"Found one failed image on the disk")
        if self.nb_failed_tiff_files is not None and self.nb_failed_tiff_files > 1:
            details_preview.append(f"Found {self.nb_failed_tiff_files} failed images on the disk")

        if size_dir_kb is not None and size_dir_mb < 2:
            details_preview.append(f"{t('directory_size')}: {size_dir_kb:.2f} KB")
        if size_dir_kb is not None and size_dir_mb >= 2:
            details_preview.append(f"{t('directory_size')}: {size_dir_mb:.2f} MB")
        details_preview.append(f"{t('filename')}: {self.preview_image_path}")
        if size_kb is not None and size_mb < 2:
            details_preview.append(f"{t('size_label')}: {size_kb:.2f} KB")
        if size_kb is not None and size_mb >= 2:
            details_preview.append(f"{t('size_label')}: {size_mb:.2f} MB")

        print(self.preview_image_path)

        # Check if the file is an image
        if not self.preview_image_path:
            self.fullscreen_image.visible = False
            self.preview_image.visible = False
            details_preview.append(f"Image File Path is empty - Preview is disable")

        elif not os.path.isfile(self.preview_image_path):
            self.fullscreen_image.visible = False
            self.preview_image.visible = False
            details_preview.append(f"Image File is not reachable - Preview is disable")

        elif file_path.lower().endswith(('.jpg', '.jpeg', '.png', '.tiff')):
            # To show a local file, we need to serve it. Quick way:
            #url_path = f'/preview/{quote(file_path.replace("\\", "/"))}'
            url_path = build_preview_url(file_path)
            self.preview_image.visible = True
            self.preview_image.source = url_path
            self.fullscreen_image.visible = True
            self.fullscreen_image.source = url_path

        else:
            self.preview_image.visible = False

        with self.details_preview:
            if not self.mode == "backup" and is_path_local_dwarf_dir(preview_image_path):
                ui.item(f"DWARF device not connected. Using offline session archive").props('header').classes('text-bold').classes('text-red-600')

            toggle = ui.toggle({True: t('show_details'), False: t('hide_details')}, value=True).classes("m-4")

            with ui.column().classes('gap-1').bind_visibility_from(toggle, 'value'):

                with ui.row().classes("justify-center mx-auto"):
                    if "_MOSAIC_" in file_path:
                        panels = get_mosaic_panels(os.path.dirname(self.preview_image_path))
                        if len(panels) > 1:
                            ui.label(f'📦 {len(panels)} {t("panels_found")}').classes('text-lg m-4')
                            ui.button(t("show_mosaic_gallery"), on_click=lambda: self.open_gallery_dialog(os.path.dirname(self.preview_image_path),panels)).classes("m-4")

                        panels_png = get_mosaic_panels(os.path.dirname(self.preview_image_path), img_type="png")
                        panels_fits = get_mosaic_panels(os.path.dirname(self.preview_image_path), img_type="fits")
                        if len(panels_png) > 1:
                            ui.button(t("create_mosaic"), on_click=lambda: self.create_and_show_panorama(os.path.dirname(self.preview_image_path),panels, panels_png, panels_fits)).classes("m-4")

                for data_detail in details_preview:
                    ui.item(data_detail).classes('text-sm')

            if not restacked_session and (self.nb_fits_files is None or self.nb_fits_files == 0):
                ui.item_label(t("no_fits_on_disk")).classes("text-red-600").classes("pl-4 pr-4 pb-4").props('header').classes('text-bold')
            self.get_details_presence_label(self.preview_image_path, file_path)

    def get_details_presence_label(self, preview_image_path: str, file_path):
        self.path_result_on_dwarf = None
        self.path_result_on_backupDrive = None
        if preview_image_path:
            session_dir = os.path.basename(os.path.dirname(preview_image_path))

            if self.mode == "backup":
                result_on_Dwarf = get_session_present_in_Dwarf(self.conn, session_dir)
                print(f"result_on_Dwarf: {result_on_Dwarf}")
                if result_on_Dwarf:
                    dwarf_full_path = get_Backup_fullpath (self.conn, result_on_Dwarf[2], "", result_on_Dwarf[3], self.get_selected_dwarf_id())
                    print(f"dwarf_full_path: {dwarf_full_path}")
                    if is_path_local_dwarf_dir(dwarf_full_path):
                        return {
                            ui.item_label(f"DWARF device not connected. Actually available on offline session archive for {result_on_Dwarf[1]}").classes("text-green-600").classes("pl-4 pr-4 pb-4").props('header').classes('text-bold'),
                            ui.label(f"{os.path.dirname(dwarf_full_path)}") \
                            .on('click', lambda: self.open_folder(os.path.dirname(dwarf_full_path))) \
                            .classes("text-green-600 pl-4 pr-4 pb-4 cursor-pointer hover:underline")
                        }
                    elif os.path.isdir(os.path.dirname(dwarf_full_path)):
                        self.path_result_on_dwarf = os.path.dirname(dwarf_full_path)
                        return {
                            ui.item_label(f"Actually available on {result_on_Dwarf[1]}").classes("text-green-600").classes("pl-4 pr-4 pb-4").props('header').classes('text-bold'),
                            ui.label(f"{os.path.dirname(dwarf_full_path)}") \
                            .on('click', lambda: self.open_folder(os.path.dirname(dwarf_full_path))) \
                            .classes("text-green-600 pl-4 pr-4 pb-4 cursor-pointer hover:underline")
                        }
                    else:
                        return {
                            ui.item_label(f"Actually available on {result_on_Dwarf[1]}").classes("text-green-600").classes("pl-4 pr-4 pb-4").props('header').classes('text-bold')
                        }
            else:
                result_on_backupDrive = get_session_present_in_backupDrive(self.conn, session_dir)

                if result_on_backupDrive:
                    backup_full_path = get_Backup_fullpath(
                        self.conn, 
                        result_on_backupDrive[2],
                        "",
                        result_on_backupDrive[4]
                    )
                    if os.path.isdir(os.path.dirname(backup_full_path)):
                        self.path_result_on_backupDrive = os.path.dirname(backup_full_path)
                    return {
                        ui.item_label(t("backup_available_on")).classes("text-green-600").classes("pl-4 pr-4").props('header').classes('text-bold'),
                        ui.label(f"{os.path.dirname(backup_full_path)}") \
                        .on('click', lambda: self.open_folder(os.path.dirname(backup_full_path))) \
                        .classes("text-green-600 pl-4 pr-4 pb-4 cursor-pointer hover:underline")
                    }
        return ui.item_label("")

    def reset_preview_icons(self):
        self.show_gallery_icon.disable()
        self.show_gallery_icon.visible = False
        self.open_folder_icon.disable()
        self.fullscreen_icon.disable()
        self.backup_session_icon.disable()
        self.backup_session_icon.visible = False
        self.delete_session_icon.disable()
        self.delete_session_icon.visible = False
        self.siril_json_icon.visible = False
        self.action_fits_files_icon.disable()
        if self.linked_manual_session_icon:
            self.linked_manual_session_icon.visible = False
        self.selected_path = ""

        # Delete old icons from UI
        for icon in self.preview_icons.values():
            icon.delete()
        self.preview_icons.clear()

    def update_gallery_icon(self):
        with self.icon_row:
            if not self.show_gallery_icon:
                self.show_gallery_icon = ui.button(t("show_gallery"), on_click=lambda: self._navigate_backup()).classes('h-16')
            elif len(self.all_files_rows) > 1 and not self.selected_path and self.get_slideshow_image_data():
                self.show_gallery_icon.visible = True
                self.show_gallery_icon.enable()
            else:
                self.show_gallery_icon.visible = False
                self.show_gallery_icon.disable()

    def update_preview_icons(self):
        with self.icon_row:
            if not self.open_folder_icon:
                self.open_folder_icon = ui.button(t("open_folder_icon"), on_click=lambda: self.open_folder()).classes('h-16')
            elif self.selected_path and os.path.isdir(self.selected_path):
                self.open_folder_icon.enable()
            else:
                self.open_folder_icon.disable()

            if not self.fullscreen_icon:
                self.fullscreen_icon =  ui.button(t("show_fullscreen_img"), on_click=self.image_dialog.open).classes('h-16')
            elif self.selected_path and os.path.isdir(self.selected_path):
                self.fullscreen_icon.enable()
            else:
                self.fullscreen_icon.disable()

            # Delete any existing format icons before recreating them
            for icon in self.preview_icons.values():
                icon.delete()
            self.preview_icons.clear()

            for fmt, path in self.astro_files.items():
                using = (
                    fmt not in {"thumbnail", "zip"} 
                )
                exists = (
                    path is not None 
                    and os.path.isfile(path)
                )
                if using:
                    icon = ui.image(f'image/image-{fmt}.png').classes(
                        'w-16 h-16 cursor-pointer hover:opacity-80' if exists else 'w-16 h-16 opacity-30'
                    ).tooltip(f"{fmt.upper()} {'available' if exists else 'missing'}")

                    if exists:
                        icon.on('click', lambda e, p=path: self.update_preview(p))
                    self.preview_icons[fmt] = icon

            if not self.backup_session_icon:
                self.backup_session_icon = ui.button(t("backup_session"), on_click=lambda: self._navigate_backup()).classes('h-16')

            # If multi-sessions are checked AND conditions match
            has_multi = (
                bool(self.selected_sessions_multi)
                and (
                    (
                        self.mode != "backup"
                        and bool(self.only_on_dwarf and self.only_on_dwarf.value)
                        and bool(self.get_selected_dwarf_id())
                    ) or (
                        self.mode == "backup"
                        and bool(self.only_on_backup and self.only_on_backup.value)
                        and bool(self.BackupDriveId)
                        and bool(self.get_selected_dwarf_id())
                    )
                )
            )
            if has_multi:
                self.backup_session_icon.visible = False
                self.backup_session_icon.disable()
                if self.transfer_multi_btn:
                    self.transfer_multi_btn.visible = True
                    self.transfer_multi_btn.enable()
            else:
                if self.transfer_multi_btn:
                    self.transfer_multi_btn.visible = False
                    self.transfer_multi_btn.disable()
                # Refresh from DB so newly added drives are detected
                self.backup_options = get_backupDrive_Names(self.conn)
                has_backup_drives = bool(self.backup_options)
                if self.mode != "backup" and self.only_on_dwarf.value and self.selected_path:
                    if has_backup_drives:
                        self.backup_session_icon.set_text("Backup Session")
                        self.backup_session_icon.visible = True
                        self.backup_session_icon.enable()
                    else:
                        # No backup drive configured — show hint button instead
                        self.backup_session_icon.set_text("⚠️ Create a Backup Drive first")
                        self.backup_session_icon.visible = True
                        self.backup_session_icon.enable()
                elif self.mode == "backup" and self.BackupDriveId and self.only_on_backup.value and self.selected_path:
                    self.backup_session_icon.set_text("Restore Session")
                    self.backup_session_icon.visible = True
                    self.backup_session_icon.enable()
                else:
                    self.backup_session_icon.visible = False
                    self.backup_session_icon.disable()

            if not self.delete_session_icon:
                self.delete_session_icon = ui.button(t("delete_session"), on_click=lambda: self.delete_directory()).classes('h-16')
            elif self.mode == "backup" and self.selected_path and os.path.isdir(self.selected_path):
                self.delete_session_icon.visible = True
                self.delete_session_icon.enable()
            else:
                self.delete_session_icon.visible = False
                self.delete_session_icon.disable()

            # Show the "View linked Manual session" button only in backup mode when
            # at least one ManualSessionEntry references the current BackupEntry.
            if not self.linked_manual_session_icon:
                self.linked_manual_session_icon = ui.button(
                    t("view_linked_manual"),
                    on_click=self.navigate_to_linked_manual_session,
                ).classes('h-16')

            if (
                self.mode == "backup"
                and self.selected_path
                and self.selected_DeleteEntryInfo
                and self.selected_DeleteEntryInfo.backup_drive_id
                and self.selected_DeleteEntryInfo.dwarf_id
                and self.selected_DeleteEntryInfo.dwarf_data_id
                and has_related_manual_sessions(
                    self.conn,
                    self.selected_DeleteEntryInfo.backup_drive_id,
                    self.selected_DeleteEntryInfo.dwarf_id,
                    self.selected_DeleteEntryInfo.dwarf_data_id,
                )
            ):
                self.linked_manual_session_icon.visible = True
                self.linked_manual_session_icon.enable()
                # Disabel delete also
                self.delete_session_icon.visible = False
                self.delete_session_icon.disable()
            else:
                self.linked_manual_session_icon.visible = False
                self.linked_manual_session_icon.disable()

            # Siril JSON button — shown in backup mode when a session is selected
            if hasattr(self, 'siril_json_icon') and self.siril_json_icon:
                if (self.mode == "backup"
                        and self.current_session_row is not None
                        and self.selected_path and os.path.isdir(self.selected_path)
                        and not self.selected_sessions_multi):  # hidden on multi-selection
                    self.siril_json_icon.visible = True
                    self.siril_json_icon.enable()
                else:
                    self.siril_json_icon.visible = False
                    self.siril_json_icon.disable()

            if not self.action_fits_files_icon:
                self.action_fits_files_icon = ui.button("", on_click=lambda: self.cleanup_fits()).classes('h-16')
            elif self.mode != "backup" and self.only_on_backup.value and self.selected_path and os.path.isdir(self.selected_path):
                print(f"nb fits files: {self.nb_fits_files}")
                print(f"nb_failed fits files: {self.nb_failed_fits_files}")
                if (self.nb_fits_files and self.nb_fits_files > 0) or (self.nb_failed_fits_files and self.nb_failed_fits_files > 0):
                    print(f"Clean UP FITS files")
                    # FITS exist → allow cleanup
                    self.cleanup_fits_files_action = True
                    self.action_fits_files_icon.text = "🧹 Cleanup FITS"
                    self.action_fits_files_icon.visible = True
                    self.action_fits_files_icon.enable()
                else:
                    print(f"Restore UP FITS files")
                    # No FITS → allow restore from backup
                    self.cleanup_fits_files_action = False
                    self.action_fits_files_icon.text = "♻️ Restore FITS"
                    self.action_fits_files_icon.visible = True
                    self.action_fits_files_icon.enable()
            else:
                self.action_fits_files_icon.visible = False
                self.action_fits_files_icon.disable()

    async def set_preview(self, path: str):
        if path.lower().endswith('.fits'):
            path = await run.io_bound(generate_fits_preview,path)
        return path

    def get_slideshow_image_data(self):

        # --- slideshow ---
        self.first_image = True
        self.current_file_index = 0
        self.slideshow_image_data = []

        for idx, row in enumerate(self.all_files_rows):
            # extract DB Values
            file_path = row[1]
            exp_time = row[2]
            gainDB = row[3]
            IR_filter  = row[4]
            stacks = row[5] if row[5] is not None else 0
            backup_path = row[6]  # location from BackupDrive or USB Dwarf
            session_date = row[7]
            session_dir = row[8]
            dwarf_name = row[9]
            descriptionDB = row[18]

            lens = "(W) " if ("_WIDE_") in session_dir else ""
            exp = f"{exp_time}s" if exp_time is not None else "N/A"
            exp_value = parse_exposure(exp) if exp != "N/A" else 0
            gain = gainDB if gainDB is not None else "N/A"
            astro_filter = f"{IR_filter}" if IR_filter else "No Filter"

            info_stack = t("restack") if is_Restacked(session_dir) else t("taken")
            details_session = f"⚙️ Exp {exp}, Gain {gain}, {astro_filter} 📊 Stacks {stacks}"

            full_path = get_Backup_fullpath (self.conn, backup_path, "", file_path, self.get_selected_dwarf_id())
            base_folder = full_path.replace("\\", "/").rsplit(file_path.replace("\\", "/"), 1)[0]
            object_name,_ =  get_name_object(descriptionDB)

            url_path = build_preview_url(file_path)
            if os.path.exists(full_path):
                self.slideshow_image_data.append({
                    "url": url_path,
                    "object_name": object_name or "Unknown Object",
                    "dwarf_name": dwarf_name or "Unknown Device",
                    "session_date": show_date_session(session_date),
                    "type_session": info_stack,
                    "details_session": details_session,
                    "file_path": full_path,
                    "base_folder": base_folder,
                    "row_index": idx,
                })

        print (f"slideshow found {len(self.slideshow_image_data)} images")

        if not self.slideshow_image_data or len(self.slideshow_image_data) == 0:
            return False
        else:
            return True

    def show_gallery(self):

        if not self.slideshow_image_data or len(self.slideshow_image_data) == 0:
            return False

        # --- Stop previous timers ---
        if getattr(self, "slideshow_timer", None):
            self.slideshow_timer.cancel()
            self.slideshow_timer = None
        if getattr(self, "slideshow_timer_anim", None):
            self.slideshow_timer_anim.cancel()
            self.slideshow_timer_anim = None
        
        with ui.dialog() as dialog:
            with ui.card().classes("w-full p-4").style("max-width: 2600px; margin: auto"):
                with ui.row().classes('w-full justify-center'):
                    ui.label(t("astro_gallery2")).classes("text-center mt-2 text-lg font-semibold")
                    ui.button(t("close"), on_click=dialog.close).classes("mt-4 ml-auto")

                with ui.column().classes("w-full").classes("items-center"):
#                    ui.label(t("astro_gallery")).classes("text-center text-lg font-semibold")

                    if self.slideshow_image_data:
                        slideshow_image = ui.image("") \
                            .classes("w-full h-auto max-w-screen-xl rounded-lg shadow-md transition-opacity duration-1000 opacity-100")

                        image_info = ui.label("").classes("text-center mt-2 text-sm")
                        image_detail = ui.label("").classes("text-center text-xs text-gray-400")

                        def show_image():
                            # Crossfade effect
                            slideshow_image.classes('opacity-5').update()
                            self.slideshow_timer_anim = ui.timer(0.2, lambda: update_image(), once=True)

                        def update_image():
                            #print(f"Update Image: n°{self.current_file_index}")
                            set_base_folder(self.slideshow_image_data[self.current_file_index]['base_folder'])
                            slideshow_image.source = self.slideshow_image_data[self.current_file_index]['url']
                            slideshow_image.classes('opacity-95').update()

                            info_text = (
                                f"🛰️ {self.slideshow_image_data[self.current_file_index]['object_name']} "
                                f"🔭 {self.slideshow_image_data[self.current_file_index]['type_session']} on {self.slideshow_image_data[self.current_file_index]['dwarf_name']} "
                                f"{self.slideshow_image_data[self.current_file_index]['details_session']} "
                                f"📅 {self.slideshow_image_data[self.current_file_index]['session_date']}"
                            )
                            image_info.text = info_text

                            image_detail.text = f"{self.slideshow_image_data[self.current_file_index]['file_path']}"

                        def reaactive_timer():
                            if self.slideshow_timer:
                                    self.slideshow_timer.cancel()
                            self.slideshow_timer = ui.timer(10, next_image, immediate=False, once=False)

                        def next_image():
                            if self.first_image:
                                self.current_file_index = (self.current_file_index) % len(self.slideshow_image_data)
                                self.first_image = False
                            else:
                                self.current_file_index = (self.current_file_index + 1) % len(self.slideshow_image_data)
                            show_image()

                        def next_image_click():
                            reaactive_timer()
                            next_image()

                        def prev_image():
                            self.current_file_index = (self.current_file_index - 1) % len(self.slideshow_image_data)
                            show_image()

                        def prev_image_click():
                            reaactive_timer()
                            prev_image()

                        def select_from_gallery():
                            current = self.slideshow_image_data[self.current_file_index]
                            row_index = current["row_index"]

                            if self.all_files_rows: 
                                options = list(self.file_list.options)
                                self.file_list.value = options[row_index+1]
                                dialog.close()

                        # Controls
                        with ui.row().classes("gap-4 mt-2 mb-4"):
                            ui.button(t("previous_arrow"), on_click=prev_image_click)
                            ui.button(t("select"), on_click=select_from_gallery)
                            ui.button(t("next_arrow"), on_click=next_image_click)

                        # Automatic slideshow with 5s interval
                        self.slideshow_timer = ui.timer(interval=10, callback=next_image)

                    else:
                        ui.label(t("no_images"))

            # Stop timer when dialog closes
            def on_close():
                if self.slideshow_timer:
                    self.slideshow_timer.cancel()
                    self.slideshow_timer = None

                if self.slideshow_timer_anim:
                    self.slideshow_timer_anim.cancel()
                    self.slideshow_timer_anim = None

            dialog.on('hide', on_close)

        dialog.open()

    def open_stitch_params(self):
        with ui.dialog() as d, ui.card():
            StitchParamsEditor(
                self.conn,
                on_change=lambda p: setattr(self, 'stitch_params', p)
            )
            # Apply closes dialog
        d.open()

    async def create_and_show_panorama(self, directory: str, panels: list, panels_png: list, panels_fits: list):
        pano_tmp_path_jpg = os.path.join(directory, "_mosaic_tmp.jpg")
        pano_tmp_path_png = os.path.join(directory, "_mosaic_tmp.png")
        pano_final_path_jpg = os.path.join(directory, "stacked.jpg")
        pano_final_path_thumbnail = os.path.join(directory, "stacked_thumbnail.jpg")
        pano_final_path_png = os.path.join(directory, get_png_name_from_zip(directory))
        pano_existing_jpg = pano_final_path_jpg  # original before save
        has_existing = os.path.isfile(pano_existing_jpg)
        mosaic_image = None

        with ui.context.client.layout:
            # --- Progress dialog ---
            with ui.dialog().props('persistent') as progress_dialog, ui.card().classes("w-full max-w-screen-xl items-center gap-4 p-6"):
                ui.label(t("stitching")).classes("text-lg font-semibold")
                ui.spinner(size="lg")
                main_log = ui.log(max_lines=6).classes('w-full').style('height: 100px; overflow: hidden;')
                log = ui.log(max_lines=20).classes('w-full').style('height: 400px; overflow: hidden;')
    
            # --- FITS progress dialog ---
            with ui.dialog().props('persistent') as fits_progress_dialog, ui.card().classes("items-center gap-4 p-6"):
                ui.label(t("creating_fits")).classes("text-lg font-semibold")
                ui.spinner(size="lg")
    
            # --- Error dialog ---
            with ui.dialog().props('persistent') as error_dialog, ui.card().classes("p-6 gap-4 w-full max-w-2xl"):
                ui.label(t("stitching_failed")).classes("text-xl font-bold text-red-500")
                error_message = ui.label("").classes("text-sm text-gray-300 whitespace-pre-wrap")
    
                with ui.row().classes("justify-end gap-2 mt-4 w-full"):
                    def on_error_params():
                        self.open_stitch_params()  # reuse the same params dialog
    
                    def on_error_retry():
                        error_dialog.close()
                        # re-trigger stitching — user changed params and wants to retry
                        ui.timer(
                            0,
                            lambda: self.create_and_show_panorama(directory, panels, panels_png, panels_fits),
                            once=True,
                        )
    
                    ui.button(t("discard"), on_click=error_dialog.close).props("flat color=negative")
                    ui.button(t("change_params"), on_click=on_error_params).props("flat")
                    ui.button(t("retry"), on_click=on_error_retry).props("color=positive")
    
            # --- Result dialog ---
            with ui.dialog().props('maximized') as result_dialog, ui.card().classes("w-full h-full p-4 gap-2"):
    
                # Title row
                with ui.row().classes("w-full items-center justify-between mb-2"):
                    ui.label(t("mosaic_result")).classes("text-xl font-bold")
                    with ui.row().classes("gap-2"):
                        btn_show_panels = ui.button(
                            t("show_panels"),
                            on_click=lambda: self.open_gallery_dialog(directory, panels)
                        ).props("flat")
                        btn_discard = ui.button(t("discard")).props("flat color=negative")
                        btn_save    = ui.button(t("save")).props("color=positive")
                        btn_fits    = ui.button(t("create_fits_close")).props("color=primary").classes("hidden")
                        btn_close   = ui.button(t("close_x")).props("flat").classes("hidden")
    
                # Images — side by side if original exists, full width otherwise
                if has_existing:
                    with ui.row().classes("w-full gap-4 items-start"):
                        with ui.column().classes("flex-1 items-center"):
                            ui.label(t("original")).classes("text-sm font-semibold text-gray-400 mb-1")
                            ui.image(pano_existing_jpg) \
                                .classes("w-full h-auto object-contain rounded-xl cursor-pointer hover:opacity-80") \
                                .on('click', lambda: self.show_full_image(pano_existing_jpg))
                        with ui.column().classes("flex-1 items-center"):
                            ui.label(t("new_stitch")).classes("text-sm font-semibold text-green-400 mb-1")
                            result_mosaic_image = ui.image() \
                                .classes("w-full h-auto object-contain rounded-xl cursor-pointer hover:opacity-80") \
                                .on('click', lambda: self.show_full_image(pano_tmp_path_jpg))
                else:
                    with ui.column().classes("w-full items-center"):
                        ui.label(t("new_stitch")).classes("text-sm font-semibold text-green-400 mb-1")
                        result_mosaic_image = ui.image() \
                            .classes("w-full h-auto object-contain rounded-xl cursor-pointer hover:opacity-80") \
                            .on('click', lambda: self.show_full_image(pano_tmp_path_jpg))
    
            # Run stitching
        progress_dialog.open()
        try:
            png_images_path = [path for _, path in panels_png]
            fits_images_path = [path for _, path in panels_fits]
            png_images = [load_image(win_long_path(path)) for _, path in panels_png]
            result, mosaic_image, _ = await generate_panorama(
                png_images_path, png_images,
                pano_tmp_path_png, pano_tmp_path_jpg,
                main_log=main_log, log=log,
                stitch_params=self.stitch_params
            )
            failed = not result
            progress_dialog.close()
            if result:
                result_mosaic_image.source = pano_tmp_path_jpg
                result_dialog.open()
            else:
                ui.notify(t("mosaic_stitch_failed"), type="negative")
                error_message.text = "Stitching returned no result.\nTry adjusting alignment parameters (lower detection sigma, increase padding)."
                error_dialog.open()

        except Exception as ex:
            progress_dialog.close()
            ui.notify(f"Mosaic failed: {ex}", type="negative")
            return

        def switch_to_post_save_buttons():
            btn_discard.classes(add="hidden")
            btn_save.classes(add="hidden")
            btn_fits.classes(remove="hidden")
            btn_close.classes(remove="hidden")

        def on_discard():
            try:
                actual_png = _err_path(pano_tmp_path_png) if failed else pano_tmp_path_png
                actual_jpg = _err_path(pano_tmp_path_jpg) if failed else pano_tmp_path_jpg
                os.remove(actual_png)
                os.remove(actual_jpg)
            except Exception:
                pass
            finally:
                result_dialog.close()
                ui.notify(t("mosaic_discarded"), type="warning")

        def on_save():
            try:
                shutil.move(pano_tmp_path_jpg, pano_final_path_jpg)
                shutil.move(pano_tmp_path_png, pano_final_path_png)
                create_thumbnail_mosaic(pano_final_path_thumbnail, mosaic_image)

                self.astro_files = check_files(pano_final_path_thumbnail)
                preview_image_path = self.preview_image_path
                url_path = build_preview_url(preview_image_path)
                self.preview_image.source = url_path
                save_selected_path = self.selected_path
                self.reset_preview_icons()
                self.selected_path = save_selected_path
                self.update_preview_icons()
                ui.notify(t("mosaic_saved"), type="positive")
                if len(panels_fits) > 0:
                    switch_to_post_save_buttons()
                else:
                    result_dialog.close()
            except Exception as ex:
                ui.notify(f"Save failed: {ex}", type="negative")

        async def on_create_fits():
            fits_progress_dialog.open()
            try:
                pano_final_path_fits = os.path.join(directory, get_fits_name_from_zip(directory))
                await run.io_bound(
                    stitch_fits_from_transforms,
                    fits_images_path,
                    pano_final_path_fits,
                    normalise=True,
                    crop=True,
                )
                # Refresh astro_files so the new FITS icon appears
                self.astro_files = check_files(pano_final_path_fits)
                preview_image_path = self.preview_image_path
                url_path = build_preview_url(preview_image_path)
                self.preview_image.source = url_path
                save_selected_path = self.selected_path
                self.reset_preview_icons()
                self.selected_path = save_selected_path
                self.update_preview_icons()
                ui.notify(t("mosaic_fits_created"), type="positive")
            except Exception as ex:
                ui.notify(f"FITS creation failed: {ex}", type="negative")
            finally:
                fits_progress_dialog.close()
                result_dialog.close()

        def on_close():
            result_dialog.close()

        btn_discard.on("click", on_discard)
        btn_save.on("click", on_save)
        btn_fits.on("click", on_create_fits)
        btn_close.on("click", on_close)

    def select_single_session(self, label: str, checkboxes: list):
        """Select a single session for detail view, clearing any multi-selection."""
        # Uncheck all checkboxes
        for cb in checkboxes:
            cb.value = False
        # Clear multi-selection set and hide transfer button
        self.selected_sessions_multi.clear()
        if self.transfer_multi_btn:
            self.transfer_multi_btn.visible = False
            self.transfer_multi_btn.disable()
        # Now display the selected session detail
        self.file_list.set_value(label)

    async def prepare_siril_json(self):
        """Generate siril_session.json and offer it as a download."""
        if self.current_session_row is None:
            ui.notify(t("no_session_selected"), type="warning")
            return

        import json, webview, os
        from pathlib import Path

        self.object_spinner.set_visibility(True)
        try:
            data = await generate_siril_session_json(
                self.conn,
                self.current_session_row,
                self.current_backup_location or "",
                session_full_dir=self.current_session_full_dir or "",
            )
        except Exception as e:
            ui.notify(f"❌ Failed to generate JSON: {e}", type="negative")
            self.object_spinner.set_visibility(False)
            return
        self.object_spinner.set_visibility(False)

        json_str = json.dumps(data, indent=2, ensure_ascii=False)

        # Suggest a filename
        target = data["session"].get("target", "session").replace(" ", "_")
        date   = data["session"].get("date", "")[:10].replace("-", "")
        default_name = f"siril_{target}_{date}.json"

        # Ask user where to save
        if hasattr(webview, 'FileDialog'):
            save_mode = webview.FileDialog.SAVE
        else:
            save_mode = webview.SAVE_DIALOG

        try:
            dest = await app.native.main_window.create_file_dialog(
                save_mode,
                save_filename=default_name,
                file_types=("JSON files (*.json)",),
            )
            if dest:
                out_path = dest[0] if isinstance(dest, (list, tuple)) else dest
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(json_str)
                ui.notify(f"✅ Saved: {os.path.basename(out_path)}", type="positive")

                # Summary notification
                lights = len(data.get("lights", []))
                darks  = data["darks"]["count"]
                status = data["darks"]["status"]
                bias   = "✅" if data.get("bias_dir") else "❌"
                flat   = "✅" if data.get("flat_dir") else "❌"
                ui.notify(
                    f"📋 {lights} lights · 🎯 {darks} darks ({status}) · "
                    f"bias {bias} · flat {flat}",
                    type="info", timeout=8000
                )
        except Exception as e:
            ui.notify(f"❌ Save failed: {e}", type="negative")

    def navigate_to_linked_manual_session(self):
        """
        Navigate to /ManualExplore/ and auto-select the ManualSessionEntry that
        was imported alongside the currently displayed BackupEntry.
        When exactly one manual session is linked, navigate directly.
        When several are linked (same backup session imported multiple times, e.g.
        different session types), show a small picker dialog so the user can choose
        which one to open.
        """
        if not self.selected_DeleteEntryInfo:
            return

        rows = get_ManualSession_by_backup_entry_id(
            self.conn,
            self.selected_DeleteEntryInfo.backup_drive_id,
            self.selected_DeleteEntryInfo.dwarf_id,
            self.selected_DeleteEntryInfo.dwarf_data_id
        )
        if not rows:
            ui.notify(t("no_linked_manual"), type="info")
            return

        def _go(entry_id, backup_entry_id):
            back=f"/Explore/?BackupDriveId={self.selected_DeleteEntryInfo.backup_drive_id}&SessionId={backup_entry_id}&mode=backup"
            back_encoded = urllib.parse.quote(back)

            url = f"/ManualExplore/?BackupDriveId={self.selected_DeleteEntryInfo.backup_drive_id}&SessionId={entry_id}"
            if self.selected_DeleteEntryInfo.dwarf_id:
                url += f"&DwarfId={self.selected_DeleteEntryInfo.dwarf_id}"
            url += f"&back_url={back_encoded}"
            ui.navigate.to(url)

        if len(rows) == 1:
            # Single linked session — navigate directly
            # col[0]=ManualSessionEntry.id, col[23]=backup_entry_id (FK to BackupEntry)
            _go(rows[0][0], rows[0][23])
            return

        # Multiple linked sessions — show a picker dialog
        # col [0] = ManualSessionEntry.id, [1] = session_name, [2] = session_type, [14] = session_date, col [22] is backup_entry_id
        with ui.dialog() as dialog, ui.card().classes("p-4 gap-3").style("min-width: 60%;"):
            ui.label(f"🔗 {len(rows)} linked Manual sessions — choose one:").classes("font-semibold")
            ui.separator()
            for row in rows:
                entry_id   = row[0]
                name       = row[1] or "—"
                stype      = row[2] or ""
                backup_entry_id = row[23] or ""  # col[23]=backup_entry_id
                date_str   = show_short_date_session(row[14])
                label      = f"📁 {name}  |  {stype}  |  📅 {date_str}"
                ui.button(
                    label,
                    on_click=lambda eid=entry_id, bid=backup_entry_id: (dialog.close(), _go(eid, bid)),
                ).props("flat align=left").classes("w-full text-left")
            ui.separator()
            ui.button(t("cancel"), on_click=dialog.close).props("flat color=grey")
        dialog.open()

    def _navigate_backup(self):
        # Reload fresh from DB in case user just added a drive
        self.backup_options = get_backupDrive_Names(self.conn)
        if not self.backup_options:
            with ui.dialog() as dlg, ui.card():
                ui.label(t("no_backup_drive")).classes("text-lg font-bold")
                ui.label(t("need_backup_drive")).classes("text-gray-600 mt-2")
                with ui.row().classes("mt-4 gap-4"):
                    ui.button(t("go_backup_settings"), on_click=lambda: (dlg.close(), ui.navigate.to("/Backup")))
                    ui.button(t("cancel"), on_click=dlg.close)
            dlg.open()
            return
        url = self.get_backup_url()
        if url:
            ui.navigate.to(url)

    def get_backup_url(self):
        ui.notify(t("launch_backup"))
        explore_url = ""
        if self.mode != "backup":
            dwarf_id = self.get_selected_dwarf_id()

            if dwarf_id == t('all_dwarfs'):
                ui.notify(t("please_select_dwarf"), color="warning")

            elif self.selected_path:
                session = os.path.basename(self.selected_path)
                back = urllib.parse.quote(f"/Explore?DwarfId={dwarf_id}&mode=dwarf", safe='')
                explore_url = f"/Transfer?DwarfId={dwarf_id}&session={session}&mode=Archive&back_url={back}"
            else:
                back = urllib.parse.quote(f"/Explore?DwarfId={dwarf_id}&mode=dwarf", safe='')
                explore_url = f"/Transfer?DwarfId={dwarf_id}&mode=Archive&back_url={back}"

        elif self.mode == "backup":
            if not self.BackupDriveId:
                ui.notify(t("no_backup_drive_sel2"), color="warning")

            else:
                dwarf_id = self.get_selected_dwarf_id()

                if dwarf_id == t('all_dwarfs'):
                    ui.notify(t("please_select_dwarf"), color="warning")

                elif self.selected_path:
                    session = self.selected_path
                    back = urllib.parse.quote(f"/Explore?BackupDriveId={self.BackupDriveId}&DwarfId={dwarf_id}&mode=backup", safe='')
                    explore_url = f"/Transfer?DwarfId={dwarf_id}&session={session}&mode=Restore&BackupId={self.BackupDriveId}&back_url={back}"
                else:
                    back = urllib.parse.quote(f"/Explore?BackupDriveId={self.BackupDriveId}&DwarfId={dwarf_id}&mode=backup", safe='')
                    explore_url = f"/Transfer?DwarfId={dwarf_id}&mode=Restore&BackupId={self.BackupDriveId}&back_url={back}"

        print(explore_url)
        return explore_url if explore_url else None

    def get_multi_transfer_url(self):
        """Build a Transfer URL with all selected sessions (multi-selection mode)."""
        import urllib.parse

        if not self.selected_sessions_multi:
            ui.notify(t("no_sessions_selected"), color="warning")
            return ""

        dwarf_id = self.get_selected_dwarf_id()
        if not dwarf_id or dwarf_id == t('all_dwarfs'):
            ui.notify(t("please_select_dwarf"), color="warning")
            return ""

        # Resolve each selected label to its row and extract the session path
        session_names = []
        for label in self.selected_sessions_multi:
            idx = self.label_to_index.get(label)
            if idx is not None and idx < len(self.all_files_rows):
                row = self.all_files_rows[idx]
                if self.mode == "backup":
                    # Restore: pass the full backup path of the session directory
                    file_path = row[1]
                    backup_path = row[6]
                    full_path = get_Backup_fullpath(self.conn, backup_path, "", file_path, dwarf_id)
                    session_path = os.path.dirname(full_path)
                    if session_path and session_path not in session_names:
                        session_names.append(session_path)
                else:
                    # Archive: pass the session dir name only
                    session_dir = row[8]
                    if session_dir and session_dir not in session_names:
                        session_names.append(session_dir)

        if not session_names:
            ui.notify(t("could_not_resolve"), color="warning")
            return ""

        ui.notify(f"Launching restore for {len(session_names)} session(s)..." if self.mode == "backup"
                  else f"Launching transfer for {len(session_names)} session(s)...", color="positive")

        sessions_param = urllib.parse.quote("|".join(session_names))

        if self.mode == "backup":
            back = urllib.parse.quote(f"/Explore?BackupDriveId={self.BackupDriveId}&DwarfId={dwarf_id}&mode=backup", safe='')
            explore_url = f"/Transfer?DwarfId={dwarf_id}&session={sessions_param}&mode=Restore&BackupId={self.BackupDriveId}&back_url={back}"
        else:
            back = urllib.parse.quote(f"/Explore?DwarfId={dwarf_id}&mode=dwarf", safe='')
            explore_url = f"/Transfer?DwarfId={dwarf_id}&session={sessions_param}&mode=Archive&back_url={back}"

        print(explore_url)
        return explore_url