from components.i18n import t
"""
dwarf_backup_ui_manual_explore.py
----------------------------------
Dedicated explore page for manually-imported sessions (ManualSession /
ManualSessionEntry tables).  The layout intentionally mirrors ExploreApp
(dwarf_backup_ui_explore.py) so the two pages feel consistent to the user,
but this page is simpler:

  - No backup / dwarf-presence checkboxes (not applicable to manual sessions).
  - The session detail panel shows session_type, filter, exp_time instead of
    stacks / gain / ircut.
  - A t("view_linked_dwarf") button navigates to /Explore/ when
    backup_entry_id is set on the ManualSessionEntry row.
  - Favorite toggling and folder deletion are fully supported.
"""

import os
import shutil
import sys
import re
import json
import subprocess
import asyncio
import urllib.parse
from dataclasses import dataclass
from collections import defaultdict
from datetime import datetime

from nicegui import ui, app, run
from components.i18n import t
from components.session_notes import session_notes_widget
from api.dwarf_backup_db import DB_NAME, connect_db
from components.db_page_mixin import DbPageMixin
from api.dwarf_backup_db_api import (
    get_dwarf_Names,
    get_backupDrive_Names,
    get_backupDrive_dwarfId,
    get_backupDrive_dwarfNames,
    get_astro_object_description,
    get_Objects_manual,
    get_countObjects_manual,
    get_ObjectSelect_manual,
    toggle_favorite_manual,
    delete_manual_session_entry,
)
from api.dwarf_backup_fct import (
    show_short_date_session,
    preprocess_dso_catalog_json,
    hours_to_hms,
    deg_to_dms,
    format_seconds_hms,
    check_files,
    get_name_object,
    count_session_fits_files,
    get_relative_file_path
)
from api.image_preview import set_base_folder, build_preview_url
from components.win_log import WinLog
from components.menu import menu
from components.astro_object_associate import DwarfData, show_unknown_target_dialog

from api.dwarf_backup_fct import CATALOG_FILE, SKY_CATALOG_FILE, UNKNOWN, MOSAIC_UNKNOWN, MANUAL

# ---------------------------------------------------------------------------
# Constants shared with ExploreApp
# ---------------------------------------------------------------------------
ALL_BACKUPS  = "(All Backups)"
ALL_DWARFS   = "(All Dwarfs)"
ALL_SESSIONS = "[ALL SESSIONS]"


# ---------------------------------------------------------------------------
# Small helper dataclass – stores the row keys needed for delete / favorite
# ---------------------------------------------------------------------------
@dataclass
class ManualEntryData:
    entry_id: int          # ManualSessionEntry.id  (PK of the link row)
    session_dir: str       # physical folder path on disk
    sub_dir_tag: str       # sub directorory it tag not empty
    backup_entry_id: int   # ManualSessionEntry.backup_entry_id (may be None)
    backup_drive_id: int   # ManualSessionEntry.backup_drive_id (may be None)
    dwarf_id: int          # ManualSessionEntry.dwarf_id (may be None)


# ===========================================================================
# NiceGUI page route
# ===========================================================================

@ui.page('/ManualExplore/')
async def manual_explore_page(
    BackupDriveId: int = None,
    DwarfId: int = None,
    back_url: str = None,
    SessionId: int = None,
):
    menu(t("page_manual_explore"))
    await ui.context.client.connected(timeout=10.0)

    # Guard: if the client was already disconnected during connection (fast navigation,
    # drawer JS timeout), abort page construction to avoid "client deleted" warnings.
    if not ui.context.client.id in ui.context.client.__class__.instances:
        return

    print(f" [ManualExplore] BackupDriveId={BackupDriveId}  DwarfId={DwarfId}  SessionId={SessionId}")

    try:
        app_instance = ManualExploreApp(
            DB_NAME,
            BackupDriveId=BackupDriveId,
            DwarfId=DwarfId,
            BackUrl=back_url,
            SessionId=SessionId,
        )
    except Exception as e:
        print(f"[ManualExplore] Failed to initialize page (client may have disconnected): {e}")
        return

    ui.context.manual_explore_app = app_instance

    # Cancel any running timers when the client disconnects
    async def on_disconnect():
        for timer in app_instance.pending_timers:
            try:
                timer.cancel(
                    with_current_invocation=True
                )
            except:
                pass

        app_instance.pending_timers.clear()

        if app_instance.gallery_timer:
            app_instance.gallery_timer.cancel()
            app_instance.gallery_timer = None
        if app_instance.gallery_timer_anim:
            app_instance.gallery_timer_anim.active = False
        if app_instance.multi_gallery_timer:
            app_instance.multi_gallery_timer.cancel()
            app_instance.multi_gallery_timer = None
        if app_instance.multi_gallery_timer_anim:
            app_instance.multi_gallery_timer_anim.active = False

    ui.context.client.on_disconnect(on_disconnect)


# ===========================================================================
# Main application class
# ===========================================================================

class ManualExploreApp(DbPageMixin):
    """
    Explore page for ManualSession / ManualSessionEntry records.

    The object-list on the left mirrors ExploreApp's tree/item layout (same
    grouping logic, same sort order).  The detail panel on the right is
    simplified: it shows the data available in ManualSession rather than
    DwarfData columns.
    """

    def __init__(self, database, BackupDriveId=None, DwarfId=None, BackUrl=None, SessionId=None):
        self.database          = database
        self.BackupDriveId     = BackupDriveId
        self.BackupDriveId_Init= BackupDriveId
        self.DwarfId           = DwarfId
        import urllib.parse as _up
        self.BackUrl = _up.unquote(BackUrl) if BackUrl else BackUrl
        self.SessionId         = SessionId

        self.AutoSelection_done = False
        self.dwarf_options      = []
        self.backup_options     = []
        self.objects            = []          # list of (id, display_name, dso_id, is_group)
        self._initializing      = True        # Prevent on_change load_objects during init
        self.all_files_rows     = []          # raw rows from get_ObjectSelect_manual
        self.label_to_index     = {}          # session label -> index in all_files_rows

        self.selected_object             = None
        self.selected_object_id          = None
        self.selected_object_description = None
        self.selected_object_is_group    = False
        self.selected_entry_data         = None   # ManualEntryData for the currently shown row
        self.selected_path               = ""     # physical folder path (session_dir/session_tag)

        self.astro_files   = {}
        self.dso_catalog   = False
        self.tree_data_lookup = {}
        self.expanded_nodes   = set()

        # UI element references filled in build_ui()
        self.backup_filter  = None
        self.dwarf_filter   = None
        self.count_label    = None
        self.object_list    = None
        self.object_filter  = None
        self.file_list      = None
        self.details_files  = None
        self.details_preview= None
        self.preview_image  = None
        self.fullscreen_image = None
        self.image_dialog   = None
        self.open_folder_icon      = None
        self.fullscreen_icon       = None
        self.linked_session_icon   = None
        self.edit_session_icon     = None
        self.delete_session_icon   = None
        self.classified_label      = None

        # Gallery / slideshow state (single-session: images within one session)
        self.gallery_image_data    = []
        self.gallery_current_index = 0
        self.gallery_timer         = None
        self.gallery_timer_anim    = None
        self.gallery_dialog        = None   # persistent dialog
        self.gallery_img           = None   # persistent UI elements
        self.gallery_caption       = None
        self.gallery_path_label    = None

        # Multi-session gallery state (one image per session, like ExploreApp)
        self.multi_gallery_image_data    = []
        self.multi_gallery_image_full    = False
        self.multi_gallery_timer         = None
        self.multi_gallery_timer_anim    = None
        self.show_gallery_icon           = None
        self.multi_gallery_dialog        = None   # persistent dialog
        self.multi_gallery_img           = None
        self.multi_gallery_caption       = None
        self.multi_gallery_path_label    = None
        self.multi_gallery_spinner       = None
        self.multi_current_index         = 0
 
        self.pending_timers = []
 
        self.WinLog = WinLog()
        self.mobile_panel = 0
        self.mobile_left_col = None
        self.mobile_right_col = None
        self.build_ui()


    # -----------------------------------------------------------------------
    # Timer Protections
    # -----------------------------------------------------------------------
    def add_timer(self, delay, callback, **kwargs):
        try:
            timer = ui.timer(
                delay,
                callback,
                **kwargs
            )

            self.pending_timers.append(timer)
            return timer
        
        except Exception as e:
            print(f"Timer exception: {e}")
            pass
    
    # -----------------------------------------------------------------------
    # UI construction
    # -----------------------------------------------------------------------

    def build_ui(self):
        self.conn = connect_db(self.database)
        self.register_conn_close()

        # Pre-process DSO catalog for target identification
        preprocess_dso_catalog_json(CATALOG_FILE, SKY_CATALOG_FILE)
        if os.path.exists(SKY_CATALOG_FILE):
            with open(SKY_CATALOG_FILE, "r", encoding="utf-8") as f:
                self.dso_catalog = json.load(f)

        # Mobile nav bar
        with ui.row().classes('w-full items-center gap-2 mobile-nav-bar'):
            self.mobile_back_btn = ui.button(t("back"), on_click=self._mobile_go_left) \
                .classes('text-sm')

        # Force initial mobile layout
        ui.run_javascript('''
            function initMobileLayout() {
                if (window.innerWidth <= 768) {
                    document.querySelectorAll(".mobile-right-col").forEach(e => e.style.display="none");
                    document.querySelectorAll(".mobile-left-col").forEach(e => e.style.display="flex");
                    document.querySelectorAll(".mobile-nav-bar").forEach(e => e.style.display="none");
                }
            }
            if (document.readyState === "complete") { initMobileLayout(); }
            else { window.addEventListener("load", initMobileLayout); }
            setTimeout(initMobileLayout, 300);
            setTimeout(initMobileLayout, 1000);
        ''')

        with ui.row().classes('w-full items-start'):
            with ui.grid(columns='1fr 2fr').classes('w-full items-start mobile-explore-grid').style('height: calc(100vh - 100px)'):

                # ---- LEFT COLUMN: filters + object list -------------------
                with ui.column().classes('w-full min-w-[300px] h-full flex flex-col min-h-0 mobile-left-col') as self.mobile_left_col:
                    with ui.grid(columns=12).classes('w-full items-end gap-2'):
                        # back button
                        if self.BackUrl:
                            ui.button(
                                t("back_btn"),
                                icon='arrow_back',
                                on_click=lambda: ui.navigate.to(self.BackUrl)
                            ).classes(
                                '''
                                col-span-12 sm:col-span-2 md:col-span-2
                                w-full sm:w-auto
                                '''
                            )

                        # backup drive
                        with ui.column().classes(
                            'col-span-12 sm:col-span-5 md:col-span-5'
                        ) as self.backup_filter_col:

                            ui.label(t("backup_drive"))

                            self.backup_filter = ui.select(
                                options=[],
                                on_change=self.on_backup_filter_change
                            ).props('outlined').classes('w-full')

                        # dwarf device
                        with ui.column().classes(
                            'col-span-12 sm:col-span-5 md:col-span-5'
                        ) as self.dwarf_filter_col:

                            ui.label(t("dwarf_device"))

                            self.dwarf_filter = ui.select(
                                options=[],
                                on_change=self.load_objects
                            ).props('outlined').classes('w-full')

                    self.count_label = ui.label(t("total_sessions_zero"))

                    with ui.card().tight().classes('w-full flex flex-col overflow-hidden flex-1'):
                        with ui.row().classes('items-center m-4 gap-2'):
                            self.object_filter = (
                                ui.input(
                                    placeholder=t('filter_objects'),
                                    on_change=lambda e: self.load_objects_ui() if e.value else self.load_objects(),
                                )
                                .classes('flex-1')
                                .props('clearable')
                            )
                            (
                                ui.button(icon='refresh', on_click=self.load_objects)
                                .props('flat round dense')
                                .bind_visibility_from(self.object_filter, 'value', lambda v: bool(v))
                            )
                            self.loading_spinner = ui.spinner(size='lg').classes('m-4')
                        self.object_list = ui.list().classes('w-full flex-1 overflow-y-scroll min-h-0 object-list-scroll').style(
    'scrollbar-width: thin; scrollbar-gutter: stable;'
)
                        ui.button(icon='keyboard_arrow_up',
                            on_click=lambda: ui.run_javascript(
                                'document.querySelector(".object-list-scroll").scrollTo({top: 0, behavior: "smooth"})'
                            )
                        ).props('round dense flat color=primary') \
                         .classes('sticky bottom-2 left-full z-10 opacity-60 hover:opacity-100') \
                         .tooltip(t('top'))

                # ---- RIGHT COLUMN: session selector + detail panel --------
                with ui.column().classes('w-full mobile-right-col') as self.mobile_right_col:

                    # Fullscreen dialog (maximised image viewer)
                    with ui.dialog().props('maximized') as self.image_dialog, \
                            ui.card().classes("w-full h-full no-padding"):
                        self.fullscreen_image = ui.image().classes('w-full h-auto object-contain')
                        ui.button('✕', on_click=self.image_dialog.close) \
                            .props('round flat') \
                            .classes('absolute top-2 right-2 z-10 bg-black text-white opacity-70')

                    with ui.row().classes('w-full'):
                        with ui.column().classes('w-full'):
                            with ui.row().classes('items-center gap-2'):
                                ui.label(t("session_list"))
                                self.fav_filter_btn = (
                                    ui.button(icon='star', on_click=self._toggle_fav_filter)
                                    .props('flat round dense')
                                    .tooltip(t("filter_favorites_only"))
                                )
                                self.fav_filter_active = False
                                self._update_fav_filter_icon()
                            self.file_list = (
                                ui.select(options=[], on_change=self.on_file_selected)
                                .props('outlined')
                                .style('overflow-x: auto;')
                            )
                            self.file_list.style('overflow: hidden; text-overflow: ellipsis;')

                        # Action buttons (shown/hidden depending on selection)
                        with ui.row().classes('items-center gap-4') as self.icon_row:
                            self.show_gallery_icon = ui.button(
                                t("show_gallery"), on_click=lambda: self.show_gallery()
                            ).classes('h-16')
                            self.show_gallery_icon.visible = False

                            self.open_folder_icon = ui.button(
                                t("open_folder_btn"), on_click=self.open_folder
                            ).classes('h-16')
                            self.open_folder_icon.visible = False

                            self.fullscreen_icon = ui.button(
                                t("show_fullscreen_btn"), on_click=self.show_fullscreen_image
                            ).classes('h-16')
                            self.fullscreen_icon.visible = False

                            # Navigates to /Explore/ to view the linked BackupEntry session
                            self.linked_session_icon = ui.button(
                                t("view_linked_dwarf"),
                                on_click=self.navigate_to_linked_session,
                            ).classes('h-16')
                            self.linked_session_icon.visible = False

                            # Edit session — open AddManualSession in update mode
                            self.edit_session_icon = ui.button(
                                t("edit_session"),
                                on_click=self.navigate_to_edit_session,
                            ).classes('h-16')
                            self.edit_session_icon.visible = False

                            self.delete_session_icon = ui.button(
                                t("delete_session_btn"), on_click=self.delete_directory
                            ).classes('h-16')
                            self.delete_session_icon.visible = False

                    with ui.row().classes('w-full'):
                        with ui.card().tight().classes('w-full flex flex-col overflow-hidden flex-1'):
                            self.details_files   = ui.list().classes('w-full overflow-y-auto')
                            self.details_preview = ui.list().classes('w-full overflow-y-auto')

                    with ui.row().classes('w-full'):
                        self.preview_image = (
                            ui.image()
                            .classes('w-full h-auto mb-4')
                            .props('fit=contain')
                            .on('click', self.show_fullscreen_image)
                        )

        self.fullscreen_image.visible = False
        self.preview_image.visible    = False
        self.loading_spinner.set_visibility(False)

        self._initializing = False  # Allow load_objects now

        self.populate_backup_filter()

        self.selected_path = ""

        # Persistent dialogs created once in the main page context
        self._build_persistent_dialogs()

    # -----------------------------------------------------------------------
    # Filter helpers
    # -----------------------------------------------------------------------

    def populate_backup_filter(self):
        self.backup_options = get_backupDrive_Names(self.conn)
        names = [t('all_backups')] + [name for _, name in self.backup_options]
        initial_value = names[0]

        if self.BackupDriveId:
            match = next((name for bid, name in self.backup_options if bid == self.BackupDriveId), None)
            if match:
                initial_value = match

        self.backup_filter.set_options(names, value=initial_value)

    async def on_backup_filter_change(self):
        prev_backup_id = self.BackupDriveId
        selected = self.backup_filter.value

        if selected == t('all_backups'):
            self.BackupDriveId = None
        else:
            for bid, name in self.backup_options:
                if name == selected:
                    self.BackupDriveId = bid
                    break

        self.populate_dwarf_filter()

        # Reload only when the backup changed but the dwarf stayed the same
        if prev_backup_id != self.BackupDriveId and self.get_selected_dwarf_id() == self.get_selected_dwarf_id():
            await self.load_objects()

    def populate_dwarf_filter(self):
        if self.BackupDriveId:
            self.dwarf_options = get_backupDrive_dwarfNames(self.conn, self.BackupDriveId)
            names = [name for _, name in self.dwarf_options]
        else:
            self.dwarf_options = get_dwarf_Names(self.conn)
            names = [t('all_dwarfs')] + [name for _, name in self.dwarf_options]

        initial_value = names[0] if names else None

        # Preserve current dwarf selection when possible
        matching = self.get_selected_dwarf_id() or self.DwarfId
        if not self.BackupDriveId and matching:
            match = next((n for did, n in self.dwarf_options if did == matching), None)
            if match:
                initial_value = match

        self.dwarf_filter.set_options(names, value=initial_value)

    def get_selected_dwarf_id(self):
        value = self.dwarf_filter.value if self.dwarf_filter else None
        if value == t('all_dwarfs'):
            return None
        return next((did for did, name in self.dwarf_options if name == value), None)

    # -----------------------------------------------------------------------
    # Object list loading  (mirrors ExploreApp.load_objects / load_objects_ui)
    # -----------------------------------------------------------------------

    async def load_objects(self):
        if self._initializing:
            return
        self.loading_spinner.set_visibility(True)
        await asyncio.sleep(0.15)
        self.add_timer(0.05, self._load_objects_work, once=True)

    def _load_objects_work(self):
        dwarf_id = self.get_selected_dwarf_id()
        self.clear_selected_object()

        self.objects = get_Objects_manual(
            self.conn,
            backup_drive_id=self.BackupDriveId,
            dwarf_id=dwarf_id,
            filter_object=self.object_filter.value,
        )
        count = get_countObjects_manual(
            self.conn,
            backup_drive_id=self.BackupDriveId,
            dwarf_id=dwarf_id,
            filter_object=self.object_filter.value,
        )

        self.count_label.text = f"{t('total_matching')} {count}"
        self.selected_object             = None
        self.selected_object_id          = None
        self.selected_object_description = None
        self.selected_object_is_group    = False
        self.load_objects_ui()

        if self.loading_spinner:
            self.loading_spinner.set_visibility(False)

        # Auto-select a specific session if SessionId was passed in the URL
        if not self.AutoSelection_done and self.SessionId:
            self.AutoSelection_done = True
            self.loading_spinner.set_visibility(True)
            self.add_timer(0.2, lambda: self.auto_select_session(), once=True)

    def _update_fav_filter_icon(self):
        if not hasattr(self, 'fav_filter_btn'):
            return
        if self.fav_filter_active:
            self.fav_filter_btn.props('color=warning')
        else:
            self.fav_filter_btn.props('color=grey')

    def _toggle_fav_filter(self):
        self.fav_filter_active = not self.fav_filter_active
        self._update_fav_filter_icon()
        # Reload current object with new filter
        if self.selected_object == ALL_SESSIONS:
            self._handle_object_click(None, ALL_SESSIONS, ALL_SESSIONS, None, True)
        else:
            for oid, name, dso_id, is_group in self.objects:
                if oid == self.selected_object_id:
                    self._handle_object_click(
                        oid,
                        name,
                        self.selected_object_description,
                        dso_id,
                        is_group
                    )
                    break

    def auto_select_session(self):
        """Directly select the ALL SESSIONS node and let on_file_selected pick the right row."""
        print(f"[ManualExplore] auto_select_session SessionId={self.SessionId}")
        self._handle_object_click(None, ALL_SESSIONS, ALL_SESSIONS, None, True, self.SessionId)

    def _update_expanded_nodes(self, expanded_keys):
        self.expanded_nodes = set(expanded_keys)

    def load_objects_ui(self):
        self.object_list.clear()
        filter_dso     = set()
        visible_names  = []
        dso_id_counts  = defaultdict(int)
        self.tree_data_lookup = {}
        node_selected  = None

        # --- Step 1: count how many times each dso_id appears after filtering ---
        for _, name, dso_id, _ in self.objects:
            name_object, _ = get_name_object(name)
            if self.object_filter.value and self.object_filter.value.lower() not in name_object.lower():
                if dso_id is not None:
                    filter_dso.add(dso_id)
                continue
            if dso_id is not None:
                dso_id_counts[dso_id] += 1

        shown_all_for_dso = set()
        grouped_objects   = defaultdict(list)
        priority_order    = {
            ALL_SESSIONS: 0,
            "Manual":       1,
            "MOSAIC_Unknown": 2,
            "Unknown":      3,
        }

        def sort_key(name_object):
            return (priority_order.get(name_object, 4), name_object.casefold())

        # --- Step 2: group objects by display name ---
        for oid, name, dso_id, is_group in self.objects:
            name_object, _ = get_name_object(name)
            if self.object_filter.value and self.object_filter.value.lower() not in name_object.lower():
                continue
            grouped_objects[name_object].append((oid, name, dso_id, is_group))

        # Always add the catch-all "All sessions" entry at the top
        grouped_objects[ALL_SESSIONS].append((None, ALL_SESSIONS, None, True))

        display_items = []

        for name_object in sorted(grouped_objects.keys(), key=sort_key):
            entries = grouped_objects[name_object]
            visible_names.append(name_object)

            if len(entries) == 1:
                oid, full_name, dso_id, is_group = entries[0]

                # Insert an [ALL] entry when multiple AstroObjects share the same DSO
                if (
                    dso_id is not None
                    and dso_id_counts[dso_id] > 1
                    and dso_id not in shown_all_for_dso
                    and dso_id not in filter_dso
                ):
                    all_name = f"{name_object.split(' [')[0]} [ALL]"
                    visible_names.append(all_name)
                    display_items.append({
                        "type": "item",
                        "label": all_name,
                        "label_full": all_name,
                        "data": {
                            "oid": None, "name": all_name, "desc": full_name,
                            "dso_id": dso_id, "is_group": is_group,
                        },
                    })
                    shown_all_for_dso.add(dso_id)

                display_name = t('all_sessions_display') if name_object == ALL_SESSIONS else name_object
                label = f"{'✨ ' if is_group else ''}{display_name}"
                display_items.append({
                    "type": "item",
                    "label": display_name,
                    "label_full": label,
                    "data": {
                        "oid": oid, "name": name_object, "desc": full_name,
                        "dso_id": dso_id, "is_group": is_group,
                    },
                })

            else:
                # Multiple objects with the same display name → tree node
                children = []
                for index, (oid, full_name, dso_id, is_group) in enumerate(entries, start=1):
                    name_item = f"{name_object} .{index}"
                    node_id   = f"obj_{oid}"
                    is_selected = self.selected_object == name_item
                    if is_selected:
                        node_selected = node_id
                    visible_names.append(name_item)
                    data = {
                        "oid": oid, "name": name_item, "desc": full_name,
                        "dso_id": dso_id, "is_group": is_group,
                    }
                    children.append({
                        "id": node_id, "label": f"{'✨ ' if is_group else ''}{name_item}",
                        "data": data,
                        "icon": "check" if is_selected else None,
                    })
                    self.tree_data_lookup[node_id] = data

                # [ALL] node for DSO group
                dso_id   = entries[0][2]
                full_name= entries[0][1]
                is_group = entries[0][3]
                if (
                    dso_id is not None
                    and dso_id_counts[dso_id] > 1
                    and dso_id not in shown_all_for_dso
                    and dso_id not in filter_dso
                ):
                    all_name    = f"{name_object} [ALL]"
                    all_node_id = f"all_{dso_id}"
                    visible_names.append(all_name)
                    is_selected = self.selected_object == all_name
                    if is_selected:
                        node_selected = all_node_id
                    all_data = {
                        "oid": None, "name": all_name, "desc": full_name,
                        "dso_id": dso_id, "is_group": is_group,
                    }
                    children.insert(0, {
                        "id": all_node_id, "label": all_name,
                        "data": all_data,
                        "icon": "check" if is_selected else None,
                    })
                    self.tree_data_lookup[all_node_id] = all_data
                    shown_all_for_dso.add(dso_id)

                children.sort(key=lambda c: c["label"].lower())
                display_items.append({
                    "type": "tree",
                    "label": name_object,
                    "node": {
                        "id": name_object,
                        "label": f"{name_object} ({len(entries)})",
                        "children": children,
                    },
                })

        # --- Step 3: render UI ---
        with self.object_list:
            ui.item_label(t('list_objects')).props('header').classes('text-bold')
            ui.separator()

            def handle_click(data):
                self.selected_object = data["name"]
                self.selected_object_id = data["oid"]
                self.selected_object_description = data["desc"]
                self._handle_object_click(
                    data["oid"], data["name"], data["desc"], data["dso_id"], data["is_group"]
                )

            def handle_select(event):
                node_id = event.value
                if not node_id:
                    return
                data = self.tree_data_lookup.get(node_id)
                if data:
                    handle_click(data)

            for entry in display_items:
                treeview = None
                if entry["type"] == "item":
                    data = entry["data"]
                    item = ui.item(
                        entry["label_full"],
                        on_click=lambda d=data: handle_click(d),
                    )
                    item.classes('bg-primary text-white' if data["name"] == self.selected_object else 'bg-transparent')

                elif entry["type"] == "tree":
                    node = entry["node"]
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
            self.selected_object_id = None
            self.clear_selected_object()

        self.object_list.update()
        ui.update()

    def _build_persistent_dialogs(self):
        """Persistent dialogs created once in the page context"""

        # ── Session gallery (images d'une session) ───────────────────────────
        with ui.dialog() as self.gallery_dialog:
            with ui.card().classes("w-full p-4").style("max-width: 2600px; margin: auto"):
                with ui.row().classes('w-full items-center justify-between mb-2'):
                    self._gallery_title = ui.label("").classes("text-lg font-semibold")
                    ui.button(t("close"), on_click=self.gallery_dialog.close).classes("ml-auto")
                with ui.column().classes("w-full items-center"):
                    self.gallery_img = ui.image("").classes(
                        "w-full h-auto max-w-screen-xl rounded-lg shadow-md "
                        "transition-opacity duration-500 opacity-100"
                    )
                    self.gallery_caption     = ui.label("").classes("text-center mt-2 text-sm")
                    self.gallery_path_label  = ui.label("").classes("text-center text-xs text-gray-400 mb-2")
                    with ui.row().classes("gap-4 mt-2 mb-4 items-center"):
                        self._gallery_btn_prev = ui.button(t("previous_arrow"), on_click=self._gallery_on_prev)
                        self._gallery_btn_next = ui.button(t("next_arrow"),     on_click=self._gallery_on_next)

        self.gallery_timer = ui.timer(10,   self._gallery_next_auto, active=False, immediate=False, once=False)
        self.gallery_timer_anim = ui.timer(0.15, self._gallery_do_update, active=False, immediate=False, once=False)

        # ── Multi-session gallery (une image par session) ────────────────────
        with ui.dialog() as self.multi_gallery_dialog:
            with ui.card().classes("w-full p-4").style("max-width: 2600px; margin: auto"):
                with ui.row().classes('w-full justify-center'):
                    ui.label(t("astro_gallery2")).classes("text-center mt-2 text-lg font-semibold")
                    ui.button(t("close"), on_click=self.multi_gallery_dialog.close).classes("mt-4 ml-auto")
                with ui.column().classes("w-full items-center"):
                    self.multi_gallery_spinner  = ui.spinner(size="lg")
                    self.multi_gallery_img      = ui.image("").classes(
                        "w-full h-auto max-w-screen-xl rounded-lg shadow-md "
                        "transition-opacity duration-500 opacity-100"
                    )
                    self.multi_gallery_caption  = ui.label("").classes("text-center mt-2 text-sm")
                    self.multi_gallery_path_label = ui.label("").classes("text-center text-xs text-gray-400 mb-2")
                    with ui.row().classes("gap-4 mt-2 mb-4 items-center"):
                        self._multi_gallery_btn_prev   = ui.button(t("previous_arrow"), on_click=self._multi_gallery_on_prev)
                        self._multi_gallery_btn_select = ui.button(t("select"),         on_click=self._multi_gallery_select)
                        self._multi_gallery_btn_next   = ui.button(t("next_arrow"),     on_click=self._multi_gallery_on_next)

        self.multi_gallery_timer = ui.timer(10,   self._multi_gallery_next_auto, active=False, immediate=False, once=False)
        self.multi_gallery_timer_anim = ui.timer(0.15, self._multi_gallery_do_update, active=False, immediate=False, once=False)

    def _handle_object_click(self, oid, name, desc, dso_id, is_group, session_id=None):
        self.loading_spinner.set_visibility(True)
        self.selected_object             = name
        self.selected_object_id          = oid
        self.selected_object_description = desc
        self.selected_object_is_group    = is_group
        fn = lambda: self._handle_object_click_work(oid, dso_id, is_group, session_id)
        _client = getattr(self, '_ui_client', None)
        if _client:
            with _client:
                self.add_timer(0.05, fn, once=True)
        else:
            self.add_timer(0.05, fn, once=True)

    def _handle_object_click_work(self, oid, dso_id, is_group, session_id=None):
        print(f'[click_work] oid={oid} is_group={is_group} session_id={session_id}', flush=True)
        self.select_object(oid, dso_id, is_group, session_id)
        self.load_objects_ui()
        self.loading_spinner.set_visibility(False)

    # -----------------------------------------------------------------------
    # Session selection
    # -----------------------------------------------------------------------

    def clear_selected_object(self):
        self.fullscreen_image.visible = False
        self.preview_image.visible    = False
        self.details_files.clear()
        self.details_preview.clear()
        self._hide_action_buttons()
        self.file_list.set_options([])
        self.all_files_rows  = []
        self.label_to_index  = {}
        self.selected_path   = ""
        self.selected_entry_data = None

    def _hide_action_buttons(self):
        if self.show_gallery_icon:
            self.show_gallery_icon.visible   = False
        if self.open_folder_icon:
            self.open_folder_icon.visible    = False
        if self.fullscreen_icon:
            self.fullscreen_icon.visible     = False
        if self.linked_session_icon:
            self.linked_session_icon.visible = False
        if self.edit_session_icon:
            self.edit_session_icon.visible   = False
        if self.delete_session_icon:
            self.delete_session_icon.visible = False

    def _mobile_go_right(self):
        if self.mobile_left_col and self.mobile_right_col:
            ui.run_javascript('''
                if (window.innerWidth <= 768) {
                    document.querySelectorAll(".mobile-left-col").forEach(e => e.style.display="none");
                    document.querySelectorAll(".mobile-right-col").forEach(e => e.style.display="flex");
                    document.querySelectorAll(".mobile-nav-bar").forEach(e => e.style.display="flex");
                }
            ''')

    def _mobile_go_left(self):
        if self.mobile_left_col and self.mobile_right_col:
            ui.run_javascript('''
                if (window.innerWidth <= 768) {
                    document.querySelectorAll(".mobile-left-col").forEach(e => e.style.display="flex");
                    document.querySelectorAll(".mobile-right-col").forEach(e => e.style.display="none");
                    document.querySelectorAll(".mobile-nav-bar").forEach(e => e.style.display="none");
                }
            ''')

    def select_object(self, object_id, dso_id, is_group, session_id=None):
        """Load session rows for the selected AstroObject and populate the file list."""
        dwarf_id = self.get_selected_dwarf_id()
        self.clear_selected_object()
        self._mobile_go_right()  # slide to right panel on mobile

        files = get_ObjectSelect_manual(
            self.conn,
            object_id=object_id,
            dso_id=dso_id,
            backup_drive_id=self.BackupDriveId,
            dwarf_id=dwarf_id,
            is_group=is_group,
            filter_object=self.object_filter.value,
            session_id=session_id,
        )

        self.all_files_rows = [list(row) for row in files]

        # Reset multi-session gallery state for the new object
        self.multi_gallery_image_data = []
        self.multi_gallery_image_full = False

        if not files:
            self.label_to_index = {}
            self.file_list.set_options([])
            with self.details_files:
                ui.item_label(t('no_session_found')).props('header').classes('text-bold')
            return

        if len(files) == 1:
            # Single result: show immediately without requiring a combobox selection
            label = files[0][1]   # session_name
            self.label_to_index[label] = 0
            self.file_list.set_options([label], value=label)
            if self.show_gallery_icon:
                self.show_gallery_icon.visible = False
        else:
            labels = [f"{t('select_session_for')} {t(self.selected_object)}"]
            value_select = f"{t('select_session_for')} {self.selected_object}"
            if self.selected_object == ALL_SESSIONS:
                value_select = f"{t('select_session_for')} {t("all_sessions")}"
            labels = [value_select]

            self.label_to_index = {}

            for idx, row in enumerate(files):
                session_name  = row[1]
                session_tag   = row[2]  or ""
                session_type  = row[3]  or ""
                session_date  = show_short_date_session(row[15])
                exp_time      = row[9]
                ircut_filter  = row[10] or "No filter"
                dwarf_name    = row[25] or "?"
                is_favorite   = row[17]
                descriptionDB = row[20]

                exp          = f"{format_seconds_hms(exp_time)}" if exp_time else "N/A"
                description, _ = get_name_object(descriptionDB)
                star_icon    = '⭐ ' if is_favorite else '☆ '
                tag_part     = f" [{session_tag}]" if session_tag else ""
                label_text   = (
                    f"📁 {session_type}{tag_part} | 🔭 {dwarf_name} | "
                    f"📅 {session_date} | ⚙️ Exp {exp}, {ircut_filter} | "
                    f"🛰️ {description}"
                )

                # Skip non-favorites when filter is active
                if getattr(self, 'fav_filter_active', False) and not is_favorite:
                    continue

                # Make duplicate labels unique with invisible characters
                base   = f"{star_icon}{label_text}"
                detail = base
                count  = 0
                while detail in self.label_to_index:
                    count  += 1
                    detail  = base + ("\u200b" * count)

                self.label_to_index[detail] = idx
                labels.append(detail)

            self.file_list.set_options(labels, value=labels[0])

            # Show the multi-session gallery button and kick off background data load
            if self.show_gallery_icon:
                self.show_gallery_icon.visible = True
                self.show_gallery_icon.enable()
            if self._test_first_multi_gallery_image():
                self.add_timer(0.1, self._load_multi_gallery_bg, once=True)

            with self.details_files:
                ui.item_label(f"{len(files)} {t('manual_sessions_found')}").props('header').classes('text-bold')
                ui.separator()
                for data_detail in labels[1:]:
                    ui.item(
                        data_detail,
                        on_click=lambda i=data_detail: self.file_list.set_value(i),
                    ).props('clickable').classes('cursor-pointer')

    def on_file_selected(self, event):
        """Triggered when the user picks a session in the dropdown."""
        label = event.value if hasattr(event, 'value') else self.file_list.value
        if not label:
            return

        idx = self.label_to_index.get(label)
        if idx is None:
            return

        self._display_session(idx)

    def get_full_path(self, session_dir, session_tag):
        """Return the effective physical path: session_dir/tag if tag set, else session_dir."""
        return os.path.join(session_dir, session_tag) if session_tag else session_dir

    def get_hover_class(self):
        return 'hover:bg-gray-700' if app.storage.user.get('ui_mode', 0) == 'dark' else 'hover:bg-gray-300'

    def toggle_favorite_ui_label(self, label_element):

        # Call the API function directly
        new_favorite = toggle_favorite_manual(self.conn, self.selected_entry_data.entry_id)
        
        # Update the favorite data row_file UI based on the new state
        self.all_files_rows[0][17] = new_favorite
        # Update the UI based on the new state
        star_icon = '⭐ ' if new_favorite else '☆ '
        label_text = label_element.text.split(' ', 1)[1]  # Remove existing star
        label_element.set_text(f"{star_icon}{label_text}")
        # Set the tooltip text based on the favorite state
        tooltip_text = "Click to Remove from Favorites" if new_favorite else "Click to Add to Favorites"
        # Add tooltip
        label_element.props(f'title="{tooltip_text}"')
        #label_element.classes('text-yellow-500' if new_favorite else 'text-gray-400')
        label_element.update()
        ui.notify(t("favorite_updated"), type="positive")

        return new_favorite

    def toggle_favorite_ui(self, label_element):
        selected_value = self.file_list.value

        if not selected_value:
            return

        # Do update only the label if only one option
        if len(self.file_list.options) <= 1:
            self.toggle_favorite_ui_label(label_element)
            return

        # Get the selected Index on the list
        # the index begin at 0, but "Select a session" use it 
        selection_index = self.label_to_index.get(selected_value)

        # Call the API function directly
        new_favorite = self.toggle_favorite_ui_label(label_element)

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

    def _display_session(self, idx: int):
        """Render the detail panel for the ManualSession row at all_files_rows[idx]."""
        row = self.all_files_rows[idx]

        # --- Unpack row columns (see get_ObjectSelect_manual docstring) ---
        manual_session_id   = row[0]
        session_name        = row[1]
        session_tag         = row[2]   or ""
        session_type        = row[3]   or ""
        jpeg_path           = row[4]
        thumbnail_path      = row[5]
        description         = row[6]
        dec                 = row[7]
        ra                  = row[8]
        exp_time            = row[9]
        ircut_filter        = row[10]
        max_temp            = row[11]
        min_temp            = row[12]
        stacked_png_path    = row[13]
        stacked_fits_path   = row[14]
        session_date        = row[15]
        session_dir         = row[16]
        is_favorite         = row[17]
        astro_object_id     = row[18]
        astro_group_id      = row[19]
        description_db      = row[20]
        backup_drive_id     = row[21]
        dwarf_id            = row[22]
        backup_entry_id     = row[23]   # FK to BackupEntry – may be None
        entry_id            = row[24]   # ManualSessionEntry.id
        dwarf_name          = row[25]   or "N/A"
        backup_drive_name   = row[26]   or "N/A"
        manualdrive_dir     = row[27]
        manualdrive_location = row[28]

        star_icon    = '⭐ ' if is_favorite else '☆ '
        details_files_text = f"{star_icon}{session_type} {t("with_label")} 🔭 {dwarf_name} {t("on_label")} 📅 {show_short_date_session(session_date)}"

        # Keep a reference for the action buttons
        self.selected_entry_data = ManualEntryData(
            entry_id=entry_id,
            session_dir=session_dir or "",
            sub_dir_tag=session_tag or "",
            backup_entry_id=backup_entry_id,
            backup_drive_id=backup_drive_id,
            dwarf_id=dwarf_id,
        )
        self.selected_path = session_dir
        print(self.selected_path)
        preview_path = jpeg_path or stacked_png_path or thumbnail_path 

        self._build_session_gallery_data(idx)
        print(f"build_session_gallery_data: {len(self.gallery_image_data)} images found")
        
        # --- Detail panel ---
        self.details_files.clear()
        self.details_preview.clear()

        with self.details_files:
            label = ui.item_label(f"{details_files_text}").props('header').classes('text-bold').props('clickable').classes(f'cursor-pointer {self.get_hover_class()} transition-colors duration-200 rounded')
            # Set the tooltip text based on the favorite state
            tooltip_text = "Click to Remove from Favorites" if is_favorite else "Click to Add to Favorites"
            # Add tooltip
            label.props(f'title="{tooltip_text}"')
            # Make the label clickable to toggle favorite
            label.on('click', lambda _, lbl=label: self.toggle_favorite_ui(lbl))
            ui.separator()

            # Target / classification row
            description, _ = get_name_object(description_db)
            tag_display = f"  [{session_tag}]" if session_tag else ""
            ui.item(f"{t('session_label')}: {session_name}{tag_display}").classes('text-blue-650')
            with ui.row().classes('w-full gap-8 items-start'):
                ui.item(f"{t('target_label')}: {description}").classes('text-green-600')
                if self.dso_catalog and astro_object_id:
                    dwarf_data_obj = DwarfData(
                        target=description_db,
                        dec=dec,
                        ra=ra,
                        astro_object_id=astro_object_id,
                    )
                    ui.button(
                        t("identify_target_btn"),
                        on_click=lambda: show_unknown_target_dialog(
                            self.conn, dwarf_data_obj, self.dso_catalog, False,
                            lambda: None,
                        ),
                    )

            self.classified_label = ui.label("").classes('text-gray-500 m-4')
            if astro_object_id:
                descdb = get_astro_object_description(self.conn, astro_object_id)
                if descdb and descdb != description_db:
                    self.classified_label.set_text(f"{t('classified_as')} {descdb}")

            # Coordinates
            if ra or dec:
                ui.item(
                    f"RA: {hours_to_hms(ra)}  |  Dec: {deg_to_dms(dec)}"
                ).classes('text-purple-600')

            # Session metadata
            date_str = show_short_date_session(session_date)
            ui.item(f"📅 {t('date_label')}: {date_str}").classes('text-indigo-600')
            ui.item(f"📁 {t('type_label')}: {session_type}").classes('text-yellow-700')
            ui.item(f"⚙️  {t('exposure_label')}: {format_seconds_hms(exp_time) or 'N/A'}  |  {t('filter_label')}: {ircut_filter or t('no_filter')}").classes('text-yellow-700')

            if max_temp is not None:
                temp_str = f"🌡 {t('temp_label')}: {min_temp}°C – {max_temp}°C" if min_temp is not None else f"🌡 {t('temp_label')}: {max_temp}°C"
                ui.item(temp_str).classes('text-sky-700')

            # --- Session Notes ---
            with ui.item():
                session_notes_widget(self.conn, manual_session_id=manual_session_id)

            ui.separator()
            # --- FITS file count for this session ---
            if session_dir and os.path.isdir(session_dir):
                fits_count = count_session_fits_files(session_dir)
                if fits_count > 0:
                    ui.item(f"🔭 {fits_count} {t('fits_files_in_folder')}").classes('text-indigo-500')

            # --- Gallery: scan the whole current object for images (not just this session) ---
            if len(self.gallery_image_data) > 1:
                ui.label(f'📦 {len(self.gallery_image_data)} {t("images_found")}').classes('text-lg m-4')
                ui.button(t("show_gallery"), on_click=self.show_session_gallery).classes("m-4")

            ui.item(f"🔭 {t('dwarf_label')}: {dwarf_name}").classes('text-gray-600')
            ui.item(f"💾 {t('drive_label')}: {backup_drive_name}").classes('text-gray-600')

            if session_dir:
                ui.item(f"📂 {t('folder_label')}: {session_dir}").classes('text-gray-400 text-xs')

        # --- Preview image ---
        preview_path = jpeg_path or stacked_png_path or thumbnail_path

        # Fallback: DB has no image path — scan the session folder on disk
        if not preview_path and session_dir and os.path.isdir(session_dir):
            for candidate in ("stacked.jpg", "stacked.jpeg", "stacked.png"):
                candidate_path = os.path.join(session_dir, candidate)
                if os.path.isfile(candidate_path):
                    preview_path = candidate_path
                    break
            if not preview_path:
                # Last resort: first JPG or PNG found in the folder
                for fname in os.listdir(session_dir):
                    if fname.lower().endswith((".jpg", ".jpeg", ".png")):
                        preview_path = os.path.join(session_dir, fname)
                        break

        self._update_preview(manualdrive_location, preview_path)

        # --- Action buttons ---
        self._update_action_buttons(is_favorite, backup_entry_id, backup_drive_id, session_dir, session_tag)

    def _update_preview(self, manualdrive_location: str, image_path: str | None):
        """Display the preview image if the file exists."""
        self.preview_image.visible    = False
        self.fullscreen_image.visible = False

        if not image_path:
            self.details_preview.append("No preview image available for this session.")
            return

        full_path = os.path.join(self.selected_path, os.path.basename(image_path))
        print(f"full image_path : {full_path}")

        # Check if the file is an image
        if not full_path:
            self.fullscreen_image.visible = False
            self.preview_image.visible = False
            self.details_preview.append(f"Image File Path is empty - Preview is disable")

        elif not os.path.isfile(full_path):
            self.fullscreen_image.visible = False
            self.preview_image.visible = False
            self.details_preview.append(f"Image File is not reachable - Preview is disable")

        try:
            # ser parent name of session_dir/session_tag for preview
            base_folder_path = manualdrive_location
            set_base_folder(base_folder_path)
            url = build_preview_url(get_relative_file_path( manualdrive_location, full_path))
            self.preview_image.visible = True
            self.preview_image.source = url
            self.fullscreen_image.visible = True
            self.fullscreen_image.source  = url
            if self.fullscreen_icon:
                self.fullscreen_icon.visible = True
        except Exception as e:
            print(f"[ManualExplore] Preview error: {e}")

    def _update_action_buttons(self, is_favorite, backup_entry_id, backup_drive_id, session_dir, session_tag):
        """Show / hide and label the action buttons for the current session."""
        # Open-folder button (only when directory exists on this machine)
        has_dir = bool(session_dir) and os.path.exists(session_dir)
        if self.open_folder_icon:
            self.open_folder_icon.visible = has_dir

        # Edit session — navigate back to AddManualSession in edit mode
        if self.edit_session_icon:
            self.edit_session_icon.visible = True

        # Delete
        if self.delete_session_icon:
            self.delete_session_icon.visible = True

        # Link to the associated BackupEntry session in /Explore/
        if self.linked_session_icon:
            self.linked_session_icon.visible = bool(backup_entry_id and backup_drive_id)

    # -----------------------------------------------------------------------
    # Action handlers
    # -----------------------------------------------------------------------

    def _build_session_gallery_data(self, idx):
        """
        Scan all rows in self.all_files_rows and collect every jpg/png image that
        exists on disk.  Prefers jpeg_path, falls back to stacked_png_path, then
        thumbnail_path.  One entry per session row (row_index mirrors the dropdown).
 
        Populates self.gallery_image_data — each entry is a dict:
            url         : preview URL (via build_preview_url)
            path        : absolute path on disk
            label       : short human-readable caption shown in the gallery
            session_dir : folder path (used by "Select" to jump to that session)
            session_tag : subdirectory if not empty
            row_index   : index into all_files_rows / file_list options
        """
        self.gallery_image_data    = []
        self.gallery_current_index = 0
 
        row = self.all_files_rows[idx]
        # Column layout from get_ObjectSelect_manual — see docstring there
        session_tag         = row[2]  or ""
        jpeg_path           = row[4]
        thumbnail_path      = row[5]
        stacked_png_path    = row[13]
        session_date        = row[15]
        session_dir         = row[16]
        description_db      = row[20]
        dwarf_name          = row[25] or "?"
        dwarf_name          = row[25] or "?"
        manual_session_dir  = row[27]
        manual_location     = row[28]
        
        obj_name, _ = get_name_object(description_db)
        date_str     = show_short_date_session(session_date)
        label        = f"🛰️ {obj_name or '?'}  🔭 {dwarf_name}  📅 {date_str}"

        set_base_folder(manual_location)

        full_path = session_dir
        # Pick the available image files
        if full_path and os.path.isdir(full_path):
            for fname in sorted(os.listdir(full_path)):
                ext = os.path.splitext(fname)[1].lower()
                if ext in ('.jpg', '.jpeg', '.png'):
                    parent_dir = os.path.dirname(session_dir)
                    candidate = os.path.join(full_path, fname)
                    print(f"candidate: {candidate}")

                    if not candidate or not os.path.isfile(candidate) or fname == "stacked_thumbnail.jpg":
                        continue   # no image found for this session
 
                    try:
                        url = build_preview_url(get_relative_file_path(manual_location, candidate))
                        print(f"url: {url}")
                    except Exception:
                        continue
 
                    self.gallery_image_data.append({
                        "url":         url,
                        "path":        candidate,
                        "label":       label,
                        "session_dir": session_dir or "",
                        "row_index":   idx,
                        "base_folder": manual_location
                    })
 
    # -----------------------------------------------------------------------
    # Multi-session gallery (one representative image per session row)
    # Mirrors the lazy-load pattern used in ExploreApp.show_gallery()
    # -----------------------------------------------------------------------

    def _test_first_multi_gallery_image(self) -> bool:
        """
        Find the first session row that has a usable image on disk and store it
        as the single entry in self.multi_gallery_image_data.  Returns True if
        at least one image was found so the caller can decide whether to show the
        gallery button and trigger background loading.
        """
        self.multi_gallery_image_data = []
        self.multi_gallery_image_full = False

        for idx, row in enumerate(self.all_files_rows):
            session_tag         = row[2]  or ""
            jpeg_path           = row[4]
            thumbnail_path      = row[5]
            description_db      = row[20]
            session_date        = row[15]
            session_dir         = row[16]
            stacked_png_path    = row[13]
            dwarf_name          = row[25] or "?"
            manual_location     = row[28]

            preview_path = jpeg_path or stacked_png_path or thumbnail_path
            if not preview_path:
                continue

            if os.path.isabs(preview_path):
                full_path = preview_path
            else:
                full_path = os.path.join(session_dir, os.path.basename(preview_path)) if session_dir else preview_path

            if not os.path.exists(full_path):
                continue

            obj_name, _ = get_name_object(description_db)
            date_str     = show_short_date_session(session_date)
            label        = f"🛰️ {obj_name or '?'}  🔭 {dwarf_name}  📅 {date_str}"

            set_base_folder(manual_location)
            try:
                rel = get_relative_file_path(manual_location, full_path)
                url = build_preview_url(rel)
            except Exception:
                continue

            self.multi_gallery_image_data.append({
                "url":         url,
                "path":        full_path,
                "label":       label,
                "session_dir": session_dir or "",
                "row_index":   idx,
                "base_folder": manual_location,
            })
            return True

        return False

    def _collect_multi_gallery_data(self) -> list:
        """
        Blocking I/O — collect one representative image per session row.
        Intended to run via run.io_bound().
        Returns the complete list of image-data dicts.
        """
        result = []
        for idx, row in enumerate(self.all_files_rows):
            session_tag         = row[2]  or ""
            jpeg_path           = row[4]
            thumbnail_path      = row[5]
            description_db      = row[20]
            session_date        = row[15]
            session_dir         = row[16]
            stacked_png_path    = row[13]
            dwarf_name          = row[25] or "?"
            manual_location     = row[28]

            preview_path = jpeg_path or stacked_png_path or thumbnail_path
            if not preview_path:
                continue

            if os.path.isabs(preview_path):
                full_path = preview_path
            else:
                full_path = os.path.join(session_dir, os.path.basename(preview_path)) if session_dir else preview_path

            if not os.path.exists(full_path):
                continue

            obj_name, _ = get_name_object(description_db)
            date_str     = show_short_date_session(session_date)
            label        = f"🛰️ {obj_name or '?'}  🔭 {dwarf_name}  📅 {date_str}"

            set_base_folder(manual_location)
            try:
                rel = get_relative_file_path(manual_location, full_path)
                url = build_preview_url(rel)
            except Exception:
                continue

            result.append({
                "url":         url,
                "path":        full_path,
                "label":       label,
                "session_dir": session_dir or "",
                "row_index":   idx,
                "base_folder": manual_location,
            })

        print(f"[ManualExplore] multi-gallery: {len(result)} images loaded")
        return result

    async def _load_multi_gallery_bg(self):
        """Timer callback — loads all multi-gallery images in the background."""
        all_data = await run.io_bound(self._collect_multi_gallery_data)

        if not ui.context.client.connected:
            return

        if all_data:
            print("End - _collect_multi_gallery_data")
            self.multi_gallery_image_data = all_data
            self.multi_gallery_image_full = True

    # -----------------------------------------------------------------------
    # Session gallery — class-level methods (persistent dialog)
    # -----------------------------------------------------------------------

    def _gallery_do_update(self):
        self.gallery_timer_anim.active = False
        if not self.gallery_image_data:
            return
        entry = self.gallery_image_data[self.gallery_current_index]
        set_base_folder(entry['base_folder'])
        self.gallery_img.source = entry["url"]
        self.gallery_img.classes(remove="opacity-5", add="opacity-100").update()
        self.gallery_caption.set_text(
            f"[{self.gallery_current_index+1}/{len(self.gallery_image_data)}]  {entry['label']}"
        )
        self.gallery_path_label.set_text(entry["path"])

    def _gallery_show_with_fade(self):
        self.gallery_img.classes(remove="opacity-100", add="opacity-5").update()
        self.gallery_timer_anim.active = True

    def _gallery_next_auto(self):
        if not self.gallery_image_data:
            return
        self.gallery_current_index = (self.gallery_current_index + 1) % len(self.gallery_image_data)
        self._gallery_show_with_fade()

    def _gallery_reset_auto(self):
        self.gallery_timer_anim.active = False
        if self.gallery_timer:
            self.gallery_timer.cancel()
            self.gallery_timer = None
        self.gallery_timer = ui.timer(10, self._gallery_next_auto, active=True, immediate=False, once=False)

    def _gallery_on_next(self):
        if getattr(self, '_gallery_nav_lock', False):
            return
        self._gallery_nav_lock = True
        self._gallery_reset_auto()
        self.gallery_current_index = (self.gallery_current_index + 1) % len(self.gallery_image_data)
        self._gallery_show_with_fade()
        ui.timer(0.5, lambda: setattr(self, '_gallery_nav_lock', False), once=True)

    def _gallery_on_prev(self):
        if getattr(self, '_gallery_nav_lock', False):
            return
        self._gallery_nav_lock = True
        self._gallery_reset_auto()
        self.gallery_current_index = (self.gallery_current_index - 1) % len(self.gallery_image_data)
        self._gallery_show_with_fade()
        ui.timer(0.5, lambda: setattr(self, '_gallery_nav_lock', False), once=True)

    def show_session_gallery(self):
        if not self.gallery_image_data:
            return
        if len(self.gallery_image_data) <= 1:
            return
        self.gallery_current_index = 0
        self._gallery_title.set_text(f"🖼️ Gallery — {len(self.gallery_image_data)} image(s)")
        self.gallery_timer_anim.active = False
        if self.gallery_timer:
            self.gallery_timer.cancel()
            self.gallery_timer = None
        self._gallery_do_update()
        self.gallery_timer = ui.timer(10, self._gallery_next_auto, active=True, immediate=False, once=False)
        self.gallery_dialog.open()

    # -----------------------------------------------------------------------
    # Multi-session gallery — class-level methods (persistent dialog)
    # -----------------------------------------------------------------------

    def _multi_gallery_do_update(self):
        self.multi_gallery_timer_anim.active = False
        if not self.multi_gallery_image_data:
            return
        entry = self.multi_gallery_image_data[self.multi_current_index]
        set_base_folder(entry['base_folder'])
        self.multi_gallery_img.source = entry["url"]
        self.multi_gallery_img.classes(remove="opacity-5", add="opacity-100").update()
        self.multi_gallery_caption.set_text(
            f"[{self.multi_current_index + 1}/{len(self.multi_gallery_image_data)}]  {entry['label']}"
        )
        self.multi_gallery_path_label.set_text(entry["path"])

    def _multi_gallery_show_with_fade(self):
        self.multi_gallery_img.classes(remove="opacity-100", add="opacity-5").update()
        self.multi_gallery_timer_anim.active = True

    def _multi_gallery_next_auto(self):
        if not self.multi_gallery_image_data:
            return
        self.multi_current_index = (self.multi_current_index + 1) % len(self.multi_gallery_image_data)
        self._multi_gallery_show_with_fade()

    def _multi_gallery_reset_auto(self):
        self.multi_gallery_timer_anim.active = False
        if self.multi_gallery_timer:
            self.multi_gallery_timer.cancel()
            self.multi_gallery_timer = None
        self.multi_gallery_timer = ui.timer(10, self._multi_gallery_next_auto, active=True, immediate=False, once=False)

    def _multi_gallery_on_next(self):
        if getattr(self, '_multi_gallery_nav_lock', False):
            return
        self._multi_gallery_nav_lock = True
        self._multi_gallery_reset_auto()
        self.multi_current_index = (self.multi_current_index + 1) % len(self.multi_gallery_image_data)
        self._multi_gallery_show_with_fade()
        ui.timer(0.5, lambda: setattr(self, '_multi_gallery_nav_lock', False), once=True)

    def _multi_gallery_on_prev(self):
        if getattr(self, '_multi_gallery_nav_lock', False):
            return
        self._multi_gallery_nav_lock = True
        self._multi_gallery_reset_auto()
        self.multi_current_index = (self.multi_current_index - 1) % len(self.multi_gallery_image_data)
        self._multi_gallery_show_with_fade()
        ui.timer(0.5, lambda: setattr(self, '_multi_gallery_nav_lock', False), once=True)

    def _multi_gallery_select(self):
        if not self.multi_gallery_image_data:
            return
        entry = self.multi_gallery_image_data[self.multi_current_index]
        row_index = entry["row_index"]
        options = list(self.file_list.options)
        if row_index + 1 < len(options):
            self.file_list.set_value(options[row_index + 1])
        self.multi_gallery_dialog.close()

    async def show_gallery(self):
        if not self.multi_gallery_image_data:
            ui.notify(t("no_images_object"), type="info")
            return
        self.multi_current_index = 0
        self.multi_gallery_timer_anim.active = False
        if self.multi_gallery_timer:
            self.multi_gallery_timer.cancel()
            self.multi_gallery_timer = None
        self.multi_gallery_spinner.set_visibility(not self.multi_gallery_image_full)
        self._multi_gallery_do_update()
        self.multi_gallery_timer = ui.timer(10, self._multi_gallery_next_auto, active=True, immediate=False, once=False)
        self.multi_gallery_dialog.open()

        if not self.multi_gallery_image_full:
            all_data = await run.io_bound(self._collect_multi_gallery_data)
            self.multi_gallery_image_data = all_data
            self.multi_gallery_image_full = True
            self.multi_gallery_spinner.set_visibility(False)
            self._multi_gallery_do_update()

    async def show_fullscreen_image(self):
        if self.fullscreen_image.visible:
            self.image_dialog.open()
            width = await ui.run_javascript('window.innerWidth')

            if width >= 768:  # pas mobile
                ui.notify(t("press_esc"), position="top", type="info")

    def open_folder(self):
        folder = self.selected_path
        if not folder or not os.path.exists(folder):
            ui.notify(t("folder_not_found"), color="negative")
            return
        folder = os.path.normpath(folder)
        if os.name == 'nt':
            subprocess.Popen(f'explorer "{folder}"')
        elif os.name == 'posix':
            subprocess.Popen(['open', folder])

    def navigate_to_linked_session(self):
        """
        Navigate to /Explore/ pre-selecting the BackupEntry session that was
        recorded alongside this manual import.  Uses the existing SessionId
        parameter mechanism already present in ExploreApp.auto_select_session.
        """
        if not self.selected_entry_data:
            return
        bid = self.selected_entry_data.backup_drive_id
        eid = self.selected_entry_data.backup_entry_id
        did = self.selected_entry_data.dwarf_id or ""
        sid = self.selected_entry_data.entry_id
        # back_url lets AddManualSession add a Back button pointing here
        back = f"/ManualExplore/?BackupDriveId={bid}&DwarfId={did}&SessionId={sid}&NotUse="
        back_encoded = urllib.parse.quote(back)
        if bid and eid:
            #ui.navigate.to(f"/Explore/?BackupDriveId={bid}&SessionId={eid}&mode=backup")
            url=f"/Explore/?BackupDriveId={bid}&SessionId={eid}&mode=backup"
            url += f"&back_url={back_encoded}"
            print(f"URL: {url}")
            ui.navigate.to(url)
        else:
            ui.notify(t("no_linked_dwarf"), type="info")

    def navigate_to_edit_session(self):
        """
        Navigate to /AddManualSession/ in edit mode, passing the ManualSessionEntry PK
        so the page can load the existing session data and file list.
        The DwarfId and BackupDriveId are forwarded so the form selectors are pre-set.
        """
        if not self.selected_entry_data:
            ui.notify(t("no_session_selected"), type="warning")
            return
        eid = self.selected_entry_data.entry_id
        bid = self.selected_entry_data.backup_drive_id or ""
        did = self.selected_entry_data.dwarf_id or ""
        # back_url lets AddManualSession add a Back button pointing here
        back = f"/ManualExplore/?BackupDriveId={bid}&DwarfId={did}&SessionId={eid}"
        back_encoded = urllib.parse.quote(back)
        url = f"/AddManualSession/?ManualEntryId={eid}"
        if bid:
            url += f"&BackupDriveId={bid}"
        if did:
            url += f"&DwarfId={did}"
        url += f"&back_url={back_encoded}"
        print(f"URL: {url}")
        ui.navigate.to(url)

    async def delete_directory(self):
        """
        Delete the physical session folder from disk, then remove the
        ManualSessionEntry (and ManualSession if it becomes orphaned).
        """
        if not self.selected_entry_data:
            ui.notify(t("no_session_selected"), color="negative")
            return

        # Use the effective path (base/tag) for the physical deletion already in database
        folder = self.selected_entry_data.session_dir
        entry_id = self.selected_entry_data.entry_id

        if folder and not os.path.exists(folder):
            # Folder already gone – just remove the DB record
            folder = None

        async def confirm_delete():
            # 1. Remove files from disk (if present)
            if folder:
                try:
                    shutil.rmtree(folder)
                    ui.notify(t("folder_deleted", path=folder), color="positive")
                except Exception as e:
                    ui.notify(t("file_delete_error", name=folder, error=e), color="negative")

            # 2. Remove the DB entry (and parent ManualSession if orphaned)
            ok = delete_manual_session_entry(self.conn, entry_id)
            if ok:
                ui.notify(t("session_removed"), type="positive")
            else:
                ui.notify(t("db_removal_failed"), type="warning")

            # 3. Reload the object list
            await self.load_objects()

        msg = (
            f"⚠️ Are you sure you want to delete this session?\n\n"
            + (f"The following folder will be permanently removed:\n{folder}\n\n" if folder else "")
            + "The database record will also be deleted."
        )
        await self.WinLog.show("Confirm deletion", msg, confirm_delete)