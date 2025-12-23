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
from glob import glob
from nicegui import app, ui
from api.dwarf_backup_db import DB_NAME, connect_db
from api.dwarf_backup_db_api import (
    get_dwarf_Names, get_dwarf_detail, get_Objects_dwarf, get_countObjects_dwarf, get_ObjectSelect_dwarf,
    get_backupDrive_Names, get_backupDrive_dwarfId, get_backupDrive_dwarfNames, get_astro_object_description,
    get_Objects_backup, get_countObjects_backup, get_ObjectSelect_backup, delete_backup_entry_and_dwarf_data,
    get_Objects_duplicate_backup, get_countObjects_duplicate_backup, get_ObjectSelect_duplicate_backup,
    get_session_present_in_Dwarf, get_session_present_in_backupDrive, toggle_favorite
)
from api.dwarf_backup_fct import (
    get_Backup_fullpath, get_extension, check_files, get_file_path, generate_fits_preview, show_date_session, show_short_date_session,
    get_directory_size, count_fits_files, count_failed_fits_files, count_tiff_files, count_failed_tiff_files,
    hours_to_hms, deg_to_dms, is_path_local_dwarf_dir, get_total_exposure, get_total_mosaic_exposure, format_seconds_hms, 
    preprocess_dso_catalog_json, is_Restacked, get_name_object, parse_exposure
)
from api.image_preview import set_base_folder, build_preview_url
from components.win_log import WinLog
from components.menu import menu
from components.astro_object_associate import DwarfData, show_unknown_target_dialog

from api.dwarf_backup_fct import CATALOG_FILE, SKY_CATALOG_FILE, UNKNOWN, MOSAIC_UNKNOWN, MANUAL, TAKEN, RESTACK

ALL_BACKUPS = "(All Backups)"
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
def dwarf_explore(BackupDriveId:int = None, DwarfId:int = None, mode:str = 'backup', back_url:str = None):

    menu("Explore")
    print(f" BackupDriveId: {BackupDriveId}")
    print(f" DwarfId: {DwarfId}")
    print(f" mode: {mode}")

    # Launch the GUI with the parameters
    ui.context.explore_app =  ExploreApp(DB_NAME, BackupDriveId=BackupDriveId, DwarfId=DwarfId, mode=mode, BackUrl=back_url)
    #ui.context.client.on_disconnect(lambda: logger.removeHandler(handler))

class ExploreApp:
    def __init__(self, database, BackupDriveId=None, DwarfId=None, mode='backup', BackUrl=None):
        self.database = database
        self.BackupDriveId = BackupDriveId
        self.BackupDriveId_Init = BackupDriveId
        self.DwarfId = DwarfId
        self.mode = mode
        self.BackUrl = BackUrl
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
        self.open_folder_icon = {}
        self.preview_icons = {}
        self.fullscreen_icon = {}
        self.backup_session_icon = {}
        self.delete_session_icon = {}
        self.image_dialog = {}
        self.selected_path = ""
        self.selected_DeleteEntryInfo = None
        self.classified_label = None
        self.expanded_nodes = set()
        self.dso_catalog = False
        self.label_to_index = {}
        self.WinLog = WinLog()
        self.build_ui()

    def build_ui(self):
        self.conn = connect_db(self.database)
        # Load the preprocessed catalog once at app start
        preprocess_dso_catalog_json(CATALOG_FILE, SKY_CATALOG_FILE)

        if os.path.exists(SKY_CATALOG_FILE): 
            with open(SKY_CATALOG_FILE  , "r", encoding="utf-8") as f:
                self.dso_catalog = json.load(f)

        with ui.row().classes('w-full h-screen items-center justify-center'):
            with ui.grid(columns='1fr 2fr'):
                with ui.column().classes('w-full'):
                    if self.mode == "backup":
                        nbcolumns = 3 if self.BackUrl else 2
                        with ui.grid(columns=nbcolumns):
                            if self.BackUrl:
                                ui.button("🔙 Back", on_click=lambda: ui.navigate.to(f"{self.BackUrl}{self.BackupDriveId if self.BackupDriveId else self.BackupDriveId_Init}")).style('width: 100px')
                            with ui.column():
                                ui.label("Backup Drive:")
                                self.backup_filter = ui.select(options=[], on_change=self.on_backup_filter_change).props('outlined')

                            with ui.column():
                                ui.label("Dwarf:")
                                self.dwarf_filter = ui.select(options=[], on_change=self.load_objects).props('outlined')

                        with ui.card().tight().classes('pr-3').bind_visibility_from(self.dwarf_filter, "value", lambda value: value != ALL_DWARFS):
                            self.only_on_dwarf = ui.checkbox("Only show backed up sessions present on selected Dwarf ",on_change = self.on_change_only_on_dwarf)
                            self.only_on_backup = ui.checkbox("Only show backed up sessions but deleted on selected Dwarf ",on_change = self.on_change_only_on_backup)
                            self.only_duplicates_backup = ui.checkbox("Only show duplicates backed up sessions",on_change = self.load_objects)
                    else:
                        if self.BackUrl:
                            with ui.grid(columns=2):
                                ui.button("🔙 Back", on_click=lambda: ui.navigate.to(f"{self.BackUrl}{self.get_selected_dwarf_id() if self.get_selected_dwarf_id() else self.DwarfId}")).style('width: 100px')

                                with ui.row().classes('w-full'):
                                    ui.label("Dwarf:")
                                    self.dwarf_filter = ui.select(options=[], on_change=self.load_objects).props('outlined')

                        else:

                            with ui.row().classes('w-full'):
                                ui.label("Dwarf:")
                                self.dwarf_filter = ui.select(options=[], on_change=self.load_objects).props('outlined')

                        with ui.row().classes('w-full'):
                            with ui.card().tight().bind_visibility_from(self.dwarf_filter, "value", lambda value: value != ALL_DWARFS):
                                ui.label("")
                                self.only_on_dwarf = ui.checkbox("Only show sessions not yet backed up on selected Dwarf ",on_change = self.on_change_only_on_dwarf)
                                ui.label("")
                                self.only_on_backup = ui.checkbox("Only show sessions already backed up on selected Dwarf ",on_change = self.on_change_only_on_backup)

                    self.count_label = ui.label("Total matching sessions: 0")
                    with ui.card().tight().classes('w-full'):
                        self.object_filter = ui.input(placeholder='🔍 Filter objects...', on_change=lambda e: self.load_objects_ui() ).classes('m-4').props('clearable')
                        self.object_list = ui.list().classes('h-150 overflow-y-auto')

                with ui.column().classes('w-full'):
                    # Create the dialog that simulates fullscreen
                    with ui.dialog().props('maximized') as self.image_dialog, ui.card().classes("w-full h-full no-padding"):
                        self.fullscreen_image = ui.image().classes('w-full h-full object-contain')

                    with ui.row().classes('w-full'):
                        with ui.column().classes('w-full'):
                            ui.label('Session List')
                            self.file_list = ui.select(options=[], on_change=self.on_file_selected).props('outlined').style('overflow-x: auto;')
                            self.file_list.style('overflow: hidden; text-overflow: ellipsis;')

                        with ui.row().classes('items-center gap-4') as self.icon_row:
                            self.open_folder_icon = ui.button("🗁 Open", on_click=lambda: self.open_folder()).classes('h-16')
                            self.fullscreen_icon = ui.button("Show Fullscreen Image", on_click=self.show_fullscreen_image).classes('h-16')
                            self.backup_session_icon = ui.button("Backup Session", on_click=lambda: ui.navigate.to(self.get_backup_url())).classes('h-16')
                            self.backup_session_icon.visible = False
                            self.delete_session_icon = ui.button("🗑️ Delete Session", on_click=lambda: self.delete_directory()).classes('h-16')
                            self.delete_session_icon.visible = False
                            self.update_preview_icons()  # populate icons

                            #self.preview_icons['jpg'] = ui.image('image/image-jpg.png').classes('w-16 h-16 cursor-pointer hover:opacity-80').tooltip('JPG File')
                            #self.preview_icons['png'] = ui.image('image/image-png.png').classes('w-16 h-16 cursor-pointer hover:opacity-80').tooltip('PNG File')
                            #self.preview_icons['fits'] = ui.image('image/image-fits.png').classes('w-16 h-16 cursor-pointer hover:opacity-80').tooltip('FITS File')

                            #Optional: Add click behavior
                            #self.preview_icons['jpg'].on('click', lambda e: ui.notify('JPG icon clicked'))
                            #self.preview_icons['png'].on('click', lambda e: ui.notify('PNG icon clicked'))
                            #self.preview_icons['fits'].on('click', lambda e: ui.notify('FITS icon clicked'))

                    with ui.row().classes('w-full'):
                        with ui.card().tight().classes('w-full'):
                            # List on the side
                            self.details_files = ui.list().classes('h-50 overflow-y-auto')
                            self.details_preview = ui.list().classes('h-50 overflow-y-auto')

                    with ui.row().classes('w-full'):
                        self.preview_image = ui.image().classes('w-full h-auto').props('fit=contain')

        self.fullscreen_image.visible = False
        self.preview_image.visible = False

        if self.mode == "backup":
            self.populate_backup_filter()
        else:
            self.populate_dwarf_filter()

        self.selected_path = ""

    def show_fullscreen_image(self):
        if self.fullscreen_image.visible: 
            self.image_dialog.open()
            ui.notify("Press ESC to close the image", position="top", type="info")

    def populate_backup_filter(self):
        print(f"backup_filter: {self.BackupDriveId}")
        self.backup_options = get_backupDrive_Names(self.conn)
        names = [ALL_BACKUPS] + [name for _, name in self.backup_options]

        # Set initial value
        initial_value = names[0] if names else None

        # If self.BackupDriveId is set, try to find corresponding name
        if self.BackupDriveId:
            match = next((name for did, name in self.backup_options if did == self.BackupDriveId), None)
            if match:
                initial_value = match

        self.backup_filter.set_options(names, value=initial_value)

    def on_backup_filter_change(self):
        current_dwarf_id = self.get_selected_dwarf_id()
        print(f"on_backup_filter_change: {self.BackupDriveId}-{current_dwarf_id}")
        current_backup_id = self.BackupDriveId
        selected_name = self.backup_filter.value
        if selected_name == ALL_BACKUPS:
            self.BackupDriveId = None
        else:
            for bid, name in self.backup_options:
                if name == selected_name:
                    self.BackupDriveId = bid
                    break
        self.populate_dwarf_filter()

        # reload objects if neccessary : new BackupDriveId and same dwarf_id
        if current_backup_id != self.BackupDriveId and current_dwarf_id == self.get_selected_dwarf_id():
            self.load_objects()

    def populate_dwarf_filter(self):
        current_dwarf_id = self.get_selected_dwarf_id()
        print(f"dwarf_filter: {self.BackupDriveId}-{current_dwarf_id}")
        if self.BackupDriveId:
            new_dwarf_id = get_backupDrive_dwarfId(self.conn, self.BackupDriveId)
            self.dwarf_options = get_backupDrive_dwarfNames(self.conn, self.BackupDriveId)
            names = [name for _, name in self.dwarf_options]
        else:
            self.dwarf_options = get_dwarf_Names(self.conn)
            names = [ALL_DWARFS] + [name for _, name in self.dwarf_options]
        print(names)
        # Set initial value
        initial_value = names[0] if names else None

        # If current_dwarf_id or self.DwarfId is set, try to find corresponding name
        matching_value = current_dwarf_id or self.DwarfId
        if not self.BackupDriveId and matching_value:
            match = next((name for did, name in self.dwarf_options if did == matching_value), None)
            if match:
                initial_value = match

        self.dwarf_filter.set_options(names, value=initial_value)

    def get_selected_dwarf_id(self):
        value = self.dwarf_filter.value
        if self.BackupDriveId is None:
            if value == ALL_DWARFS:
                return None
            return next((id_ for id_, name in self.dwarf_options if name == value), None)
        else:
            return next((id_ for id_, name in self.dwarf_options if name == value), None)

    def on_change_only_on_dwarf(self):
        if self.only_on_dwarf.value and self.only_on_backup.value:
            self.only_on_backup.value = False
        self.load_objects()

    def on_change_only_on_backup(self):
        if self.only_on_dwarf.value and self.only_on_backup.value:
            self.only_on_dwarf.value = False
        self.load_objects()
      
    def load_objects(self):
        dwarf_id = self.get_selected_dwarf_id()
        self.clear_selected_object()

        if self.mode == "backup":
            show_only_dwarf = self.only_on_dwarf.value if self.only_on_dwarf else False
            show_only_backup = self.only_on_backup.value if self.only_on_backup else False
            show_only_duplicates = self.only_duplicates_backup.value if self.only_duplicates_backup else False
            if show_only_duplicates:
                self.objects = get_Objects_duplicate_backup(self.conn, self.BackupDriveId, dwarf_id, show_only_dwarf, show_only_backup)
                count = get_countObjects_duplicate_backup(self.conn, self.BackupDriveId, dwarf_id, show_only_dwarf, show_only_backup)
            else: 
                self.objects = get_Objects_backup(self.conn, self.BackupDriveId, dwarf_id, show_only_dwarf, show_only_backup)
                count = get_countObjects_backup(self.conn, self.BackupDriveId, dwarf_id, show_only_dwarf, show_only_backup)
        else:
            show_only_dwarf = self.only_on_dwarf.value if self.only_on_dwarf else False
            show_only_backup = self.only_on_backup.value if self.only_on_backup else False
            self.objects = get_Objects_dwarf(self.conn, dwarf_id, show_only_dwarf, show_only_backup)
            count = get_countObjects_dwarf(self.conn, dwarf_id, show_only_dwarf, show_only_backup)

        self.count_label.text = f"Total matching sessions: {count}"
        print (f"Total matching sessions: {count}")
        print (f"Total objects: {len(self.objects)}")
        print (f"Total objects: {[f'{oid} - {name} {dso_id} {"G" if is_group else ""}' for oid, name, dso_id, is_group in self.objects]}")
        self.selected_object = None
        self.selected_object_description = None
        self.selected_object_is_group = False
        self.load_objects_ui()

    def load_objects_ui_old(self, init_view = True):

        self.object_list.clear()
        filter_dso = set()
        visible_names = []

        dso_id_counts = defaultdict(int)
        for _, name, dso_id,_ in self.objects:
            name_object, main_part = get_name_object(name)
            # Apply filter
            if self.object_filter.value and self.object_filter.value.lower() not in name_object.lower():
                if dso_id is not None:
                    filter_dso.add(dso_id)
                continue

            if dso_id is not None:
                dso_id_counts[dso_id] += 1

        # Step 2 – Track if [ALL] line was already shown
        shown_all_for_dso = set()

        with self.object_list:
            ui.item_label('List Objects').props('header').classes('text-bold')
            ui.separator()
            for oid, name, dso_id, is_group in self.objects:
                name_object, main_part = get_name_object(name)

                # Apply filter
                if self.object_filter.value and self.object_filter.value.lower() not in name_object.lower():
                    continue

                visible_names.append(name_object)

                # Insert the [ALL] line if needed
                if dso_id is not None and dso_id_counts[dso_id] > 1 and dso_id not in shown_all_for_dso and dso_id not in filter_dso :
                    all_name = f"{main_part} [ALL]"
                    visible_names.append(all_name)  # 👈 ADD [ALL] entry to visible_names
                    item_all = ui.item(all_name, on_click=lambda dso_id=dso_id, name=all_name, desc=name, is_group=is_group : self._handle_object_click(None, name, desc, dso_id, is_group))
                    item_all.classes('font-bold text-blue-600')  # Optional styling
                    if all_name == self.selected_object:
                        item_all.classes('bg-primary text-white')
                    else:
                        item_all.classes('bg-transparent')
                    shown_all_for_dso.add(dso_id)

                # Add the actual object
                item = ui.item(f"{'🌌 ' if is_group else ''}{name_object}", on_click=lambda oid=oid, name=name_object, desc=name, is_group=is_group : self._handle_object_click(oid, name, desc, None, is_group))

                # Highlight if selected
                if name_object == self.selected_object:
                    item.classes('bg-primary text-white')  # Change background and text color
                else:
                    item.classes('bg-transparent')  # Normal background

        # ❗ Clear selection if it's no longer in the filtered results
        if self.selected_object not in visible_names:
            self.selected_object = None
            self.clear_selected_object()
 
        # Force UI update after setting selected_object
        self.object_list.update()  # Refresh the list
        ui.update()  # Refresh the UI

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
            "[ALL SESSIONS]": 0,
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
                    all_name = f"{name_object.split(" [")[0]} [ALL]"
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
                label = f"{'✨ ' if is_group else ''}{name_object}"
                data = {
                    "oid": oid,
                    "name": name_object,
                    "desc": full_name,
                    "dso_id": dso_id,
                    "is_group": is_group,
                }
                display_items.append({
                    "type": "item",
                    "label": name_object,
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
            ui.item_label('List Objects').props('header').classes('text-bold')
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

    def _handle_object_click(self, oid, name, desc, dso_id, is_group):
        self.selected_object = name 
        self.selected_object_description = desc 
        self.selected_object_is_group = is_group
        self.select_object(oid, dso_id, is_group)
        self.load_objects_ui()

    def clear_selected_object(self):
        self.fullscreen_image.visible = False
        self.preview_image.visible = False

        self.details_files.clear()
        self.details_preview.clear()
        self.reset_preview_icons()
        self.file_list.set_options([])

    def select_object(self, object_id, dso_id, is_group):
        dwarf_id = self.get_selected_dwarf_id()
        details = []
        self.clear_selected_object()

        if self.mode == "backup":
            show_only_duplicates = self.only_duplicates_backup.value if self.only_duplicates_backup else False
            if show_only_duplicates:
                files = get_ObjectSelect_duplicate_backup(self.conn, object_id, dso_id, self.BackupDriveId, dwarf_id, self.only_on_dwarf.value, self.only_on_backup.value, is_group)
            else:
                files = get_ObjectSelect_backup(self.conn, object_id, dso_id, self.BackupDriveId, dwarf_id, self.only_on_dwarf.value, self.only_on_backup.value, is_group)
        else:
            files = get_ObjectSelect_dwarf(self.conn, object_id, dso_id, dwarf_id, self.only_on_dwarf.value, self.only_on_backup.value, is_group)

        # Store all rows globally so we can access them later
        self.all_files_rows = [list(row) for row in files]
        self.selected_DeleteEntryInfo = None
    
        if len(files) == 0:
     
            self.label_to_index = {}
            self.file_list.set_options([])
            with self.details_files:
                ui.item_label('No Session found.').props('header').classes('text-bold')

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
            select_file = [f'Select a session for {self.selected_object}']
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
                filter  = row[4]
                stacks = row[5]
                backup_path = row[6]  # location from BackupDrive or USB Dwarf
                session_date = row[7]
                session_dir = row[8]
                dwarf_name = row[9]
                minTemp = row[10]
                maxTemp = row[11]
                is_favorite = row[12]  # The favorite column (0 or 1)
                init_target = row[13]
                declination = row[14]
                right_ascencion = row[15]
                astro_object_id = row[16]
                astro_group_id = row[17]
                descriptionDB = row[18]

                # display Values
                session_date = show_short_date_session(session_date)
                lens = "(W) " if ("_WIDE_") in session_dir else ""
                exp = f"{exp_time}s" if exp_time is not None else "N/A"
                gain = gainDB if gainDB is not None else "N/A"
                astro_filter = f"{filter}" if filter else "No Filter"
                stackeds += stacks
                if exp_time:
                    total_time_exp += stacks * parse_exposure(f"{exp_time}s")

                # Displaying star icon based on favorite status only in backup mode
                star_icon = '⭐ ' if is_favorite else '☆ '
                bad_icon = '❗ ' if int(stacks) < 50 else ''
                info_stack = RESTACK if is_Restacked(session_dir) else TAKEN
                target = init_target[:10]
                description,_ =  get_name_object(descriptionDB)
                # Building the details string with the star icon
                label_text = f"{info_stack} with {dwarf_name} {lens}| {session_date}, Exp {exp}, Gain {gain}, {astro_filter}, Stacks {stacks} | {description}"

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

            self.file_list.set_options(select_file, value=f'Select a session for {self.selected_object}')

            with self.details_files:
                ui.item_label(f"{len(files)} sessions were found, totaling {stackeds} stacks and a total exposure time of {format_seconds_hms(total_time_exp)}.").props('header').classes('text-bold')
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

                # "Select all / Deselect all" toggle
                checkboxes = []
                # future improvement : use checkboxes to Archive / Restore multi sessions
                use_checkboxes = False
                if use_checkboxes:
                    with ui.row():
                        select_all_cb = ui.checkbox('Select All', on_change=lambda e: toggle_select_all(e.value))
                        ui.button('Deselect All', on_click=lambda: toggle_select_all(False))

                    # Checkboxes for each detail
                    for data_detail in details:
                        def on_check_change(e, label=data_detail):
                            if e.value:
                                selected_sessions.add(label)
                            else:
                                selected_sessions.discard(label)
                            update_buttons()

                        with ui.row().classes('items-center gap-2'):
                            cb = ui.checkbox(on_change=on_check_change)
                            checkboxes.append(cb)

                            # clickable label to still select single session for detail view
                            ui.label(data_detail).on('click', lambda e, i=data_detail: self.file_list.set_value(i)).props('clickable').classes('cursor-pointer')

                else:

                    def clean_label(text: str) -> str:
                        # remove star and bad icons
                        return re.sub(r"[⭐☆❗]", "", text).strip()

                    for data_detail in details:
                        #ui.item(data_detail, on_click=lambda i=clean_label(data_detail).strip(): self.file_list.set_value(i)).props('clickable').classes('cursor-pointer')
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
            ui.notify("No folder selected!", color="negative")
            return

        folder_path = os.path.normpath(folder_path)

        if not os.path.exists(folder_path):
            ui.notify(f"Folder does not exist:\n{folder_path}", color="negative")
            return

        def ok_confirm_delete_session():
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
                self.load_objects()

        # Ask for confirmation
        await self.WinLog.show(
            "Confirm Deletion",
            f"⚠️ Are you sure you want to delete this session?\n\nThe following folder will be completely removed!\n\n{folder_path}",
            ok_confirm_delete_session
        )

    def get_mosaic_panels(self, mosaic_dir: str) -> list[tuple[str, str]]:
        """Return list of (panel_name, stacked.jpg full path) for a mosaic directory."""
        panels = []
        try :
            for subdir in sorted(os.listdir(mosaic_dir)):
                panel_path = os.path.join(mosaic_dir, subdir)
                stacked_img = os.path.join(panel_path, "stacked.jpg")
                if os.path.isdir(panel_path) and os.path.isfile(stacked_img):
                    panels.append((subdir, stacked_img))

        except FileNotFoundError as e:
            print(f"Mosaic Directory not found: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")
        
        return panels

    def show_full_image(self, path):
        with ui.dialog().props('maximized') as full_dialog:
            with ui.card().classes("w-full h-full justify-center items-center bg-black"):
                ui.image(path).classes('w-full max-h-full object-contain')
        full_dialog.open()
        ui.notify("Press ESC to close the image", position="top", type="info")

    def open_gallery_dialog(self, mosaic_dir: str, panels):

        with ui.dialog() as dialog:
            with ui.card().classes("w-full p-4").style("max-width: 2600px; margin: auto"):
                with ui.row().classes('w-full justify-center'):
                    ui.label('🧩 Mosaic Gallery').classes("text-center mt-2 text-lg font-semibold mr-auto")
                    ui.label(Path(mosaic_dir).name).classes("text-center mt-4 text-md font-medium")
                    ui.button("Close", on_click=dialog.close).classes("mt-4 ml-auto")

                with ui.row().classes("justify-center mx-auto"):
                    if len(panels) == 2:
                        with ui.column().classes("gap-2 items-center mx-auto"):
                            for i, (panel_name, image_path) in enumerate(panels, start=1):
                                with ui.column().classes("items-center p-1 border rounded shadow-md"):
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
                                        ui.label(f"Panel {i}").classes("text-sm")

        dialog.open()

    def on_file_selected(self):
        selection_index = None
        selected_value = self.file_list.value
        #safe_print(f"Selected value: {selected_value}")
        details = []

        if not selected_value or selected_value.startswith('Select a session'):
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
            # extract DB Values
            dwarf_data_id = row[0]
            file_path = row[1]
            exp_time = row[2]
            gainDB = row[3]
            filter  = row[4]
            stacks = row[5]
            backup_path = row[6]  # location from BackupDrive or USB Dwarf
            session_date = row[7]
            session_dir = row[8]
            dwarf_name = row[9]
            minTemp = row[10]
            maxTemp = row[11]
            is_favorite = row[12]  # The favorite column (0 or 1)
            init_target = row[13]
            declination = row[14]
            right_ascencion = row[15]
            astro_object_id = row[16]
            astro_group_id = row[17]
            descriptionDB = row[18]

            # display Values
            info_stack = RESTACK if is_Restacked(session_dir) else TAKEN
            star_icon = '⭐ ' if is_favorite else '☆ '
            full_path = get_Backup_fullpath (self.conn, backup_path, "", file_path, self.get_selected_dwarf_id())
            self.selected_path = os.path.dirname(full_path)

            # Store the base folder once
            self.base_folder = full_path.replace("\\", "/").rsplit(file_path.replace("\\", "/"), 1)[0]
            set_base_folder(full_path.replace("\\", "/").rsplit(file_path.replace("\\", "/"), 1)[0])
            lens = "(Wide)" if ("_WIDE_") in session_dir else "(Tele)"

            details_files_text = f"{star_icon}{info_stack} with {dwarf_name} {lens} on {show_date_session(session_date)}"

            # details

            #details.append(f"Session: {session_dir}")
            details.append(f"Dwarf Target: {init_target}")

            classified_text, descriptiondb = self.update_classified_label(astro_object_id, init_target, "", True)
            if classified_text:
                details.append(classified_text)
            details.append(f"RA: {hours_to_hms(right_ascencion)} | Dec: {deg_to_dms(declination)}")

            lens = "Wide" if ("_WIDE_") in session_dir else "Tele"
            exp = f"{exp_time}s" if exp_time is not None else "N/A"
            gain = gainDB if gainDB is not None else "N/A"

            details.append(f"Lens : {lens} | Exposure: {exp} | Gain: {gain} | Filter: {filter}")
            if minTemp and maxTemp:
                details.append(f"MinTemp: {minTemp} | MaxTemp: {maxTemp}")
            bad_icon = '❗ ' if int(stacks) < 50 else ''
            details.append(f"Stacks: {bad_icon}{stacks}")

            self.astro_files = check_files(full_path)
            self.update_preview_icons()

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
                    ui.item(f"Dwarf Target: {init_target}").classes('text-green-600')
                    if self.dso_catalog:
                        ui.button("🖼️ Identify Target", on_click=lambda: self.on_identify_target_click(DwarfData.from_row(row), descriptiondb))

                self.classified_label = ui.label().classes('text-gray-500').classes("m-4")
                self.update_classified_label(astro_object_id, init_target, descriptiondb)

                ui.item(f"RA: {hours_to_hms(right_ascencion)} | Dec: {deg_to_dms(declination)}").classes('text-purple-600')

                lens = "Wide" if ("_WIDE_") in session_dir else "Tele"
                exp = f"{exp_time}s" if exp_time is not None else "N/A"
                exp_value = parse_exposure(exp) if exp != "N/A" else 0
                gain = gainDB if gainDB is not None else "N/A"
                with ui.row().classes('w-full gap-8 items-start'):
                    ui.item(f"Lens : {lens} | Exposure: {exp} | Gain: {gain} | Filter: {filter}").classes('text-yellow-700')

                    if minTemp and maxTemp:
                        ui.item(f"MinTemp: {minTemp} | MaxTemp: {maxTemp}").classes('text-sky-700')

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

                ui.item(f"{stacks} stacked shots for a total exposure time of {exposure_time}").classes(color)

                # add Mosaic Panel Info
                #for data_detail in details:
                #   ui.item(data_detail)

            self.preview_image_path = full_path
            self.update_preview(full_path)

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
            classified_text = f"Classified as: {classified}"

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

    def update_preview(self, preview_image_path ):
        details_preview = []
        self.details_preview.clear()
        self.preview_image_type = get_extension(preview_image_path)
        self.preview_image_path = preview_image_path

        # convert Fits for preview
        preview_image_path = self.set_preview(self.preview_image_path)
        file_path = get_file_path(preview_image_path, self.base_folder)
        print(file_path)

        size_dir_kb = None
        size_dir_mb = None
        size_kb = None
        size_mb = None
        nb_fits_files = None
        nb_failed_fits_files = None
        nb_tiff_files = None
        nb_failed_tiff_files = None
        restacked_session = False
        try:
            directory = os.path.dirname(self.preview_image_path)
            restacked_session = is_Restacked(os.path.basename(directory))
            size_dir_kb = get_directory_size(directory) / 1024
            size_dir_mb = size_dir_kb / 1024
            size_kb = os.path.getsize(self.preview_image_path) / 1024
            size_mb = size_kb / 1024
            nb_fits_files = count_fits_files(directory)
            nb_failed_fits_files = count_failed_fits_files(directory)
            nb_tiff_files = count_tiff_files(directory)
            nb_failed_tiff_files = count_failed_tiff_files(directory)

        except FileNotFoundError:
            print("File not found")
            pass
        except Exception as e:
            print(f"Unexpected error: {e}")
            size_dir_kb = None
            size_dir_mb = None
            size_kb = None
            size_mb = None

        if nb_fits_files is not None and nb_fits_files == 1:
            details_preview.append(f"Found one fits image on the disk")
        if nb_fits_files is not None and nb_fits_files > 1:
            details_preview.append(f"Found {nb_fits_files} fits images on the disk")
        if nb_failed_fits_files is not None and nb_failed_fits_files == 1:
            details_preview.append(f"Found one failed image on the disk")
        if nb_failed_fits_files is not None and nb_failed_fits_files > 1:
            details_preview.append(f"Found {nb_failed_fits_files} failed images on the disk")

        if nb_tiff_files is not None and nb_tiff_files == 1:
            details_preview.append(f"Found one tiff image on the disk")
        if nb_tiff_files is not None and nb_tiff_files > 1:
            details_preview.append(f"Found {nb_tiff_files} tiff images on the disk")
        if nb_failed_tiff_files is not None and nb_failed_tiff_files == 1:
            details_preview.append(f"Found one failed image on the disk")
        if nb_failed_tiff_files is not None and nb_failed_tiff_files > 1:
            details_preview.append(f"Found {nb_failed_tiff_files} failed images on the disk")

        if size_dir_kb is not None and size_dir_mb < 2:
            details_preview.append(f"Directory Size: {size_dir_kb:.2f} KB")
        if size_dir_kb is not None and size_dir_mb >= 2:
            details_preview.append(f"Directory Size: {size_dir_mb:.2f} MB")
        details_preview.append(f"Filename: {self.preview_image_path}")
        if size_kb is not None and size_mb < 2:
            details_preview.append(f"Size: {size_kb:.2f} KB")
        if size_kb is not None and size_mb >= 2:
            details_preview.append(f"Size: {size_mb:.2f} MB")

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

            toggle = ui.toggle({True:'Show Details', False:'Hide Details'}, value=True).classes("m-4")

            with ui.column().classes('gap-1').bind_visibility_from(toggle, 'value'):

                if "_MOSAIC_" in file_path:
                    panels = self.get_mosaic_panels(os.path.dirname(self.preview_image_path))
                    if len(panels) > 1:
                        ui.label(f'📦 {len(panels)} panel(s) found').classes('text-lg m-4')
                        ui.button("🖼️ Show Mosaic Gallery", on_click=lambda: self.open_gallery_dialog(os.path.dirname(self.preview_image_path),panels)).classes("m-4")

                for data_detail in details_preview:
                    ui.item(data_detail).classes('text-sm')

            if not restacked_session and (nb_fits_files is None or nb_fits_files == 0):
                ui.item_label(f"No sub-exposure fits files were found on the disk").classes("text-red-600").classes("pl-4 pr-4 pb-4").props('header').classes('text-bold')
            self.get_details_presence_label(self.preview_image_path, file_path)

    def get_details_presence_label(self, preview_image_path: str, file_path):
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
                    return { 
                        ui.item_label(f"Backup Available on:").classes("text-green-600").classes("pl-4 pr-4").props('header').classes('text-bold'),
                        ui.label(f"{os.path.dirname(backup_full_path)}") \
                        .on('click', lambda: self.open_folder(os.path.dirname(backup_full_path))) \
                        .classes("text-green-600 pl-4 pr-4 pb-4 cursor-pointer hover:underline")
                    }
        return ui.item_label("")

    def reset_preview_icons(self):
        self.open_folder_icon.disable()
        self.fullscreen_icon.disable()
        self.backup_session_icon.disable()
        self.delete_session_icon.disable()

        # Delete old icons from UI
        for icon in self.preview_icons.values():
            icon.delete()
        self.preview_icons.clear()

    def update_preview_icons(self):
        with self.icon_row:
            if not self.open_folder_icon:
                self.open_folder_icon = ui.button("🗁 Open", on_click=lambda: self.open_folder()).classes('h-16')
            elif self.selected_path and os.path.isdir(self.selected_path):
                self.open_folder_icon.enable()
            else:
                self.open_folder_icon.disable()

            if not self.fullscreen_icon:
                self.fullscreen_icon =  ui.button("Show Fullscreen Image", on_click=self.image_dialog.open).classes('h-16')
            elif self.selected_path and os.path.isdir(self.selected_path):
                self.fullscreen_icon.enable()
            else:
                self.fullscreen_icon.disable()

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

                #self.icon_row.add(icon)  # Add icon to the row

            if not self.backup_session_icon:
                self.backup_session_icon = ui.button("Backup Session", on_click=lambda: ui.navigate.to(self.get_backup_url())).classes('h-16')
            elif self.mode != "backup" and self.only_on_dwarf.value and self.selected_path:
                self.backup_session_icon.set_text("Backup Session")
                self.backup_session_icon.visible = True
                self.backup_session_icon.enable()
            elif self.mode == "backup" and self.only_on_backup.value and self.selected_path:
                self.backup_session_icon.set_text("Restore Session")
                self.backup_session_icon.visible = True
                self.backup_session_icon.enable()
            else:
                self.backup_session_icon.visible = False
                self.backup_session_icon.disable()

            if not self.delete_session_icon:
                self.delete_session_icon = ui.button("🗑️ Delete Session", on_click=lambda: self.delete_directory()).classes('h-16')
            elif self.mode == "backup" and self.selected_path and os.path.isdir(self.selected_path):
                self.delete_session_icon.visible = True
                self.delete_session_icon.enable()
            else:
                self.delete_session_icon.visible = False
                self.delete_session_icon.disable()

    def set_preview(self, path: str):
        if path.lower().endswith('.fits'):
            path = generate_fits_preview(path)
        return path

    def get_backup_url(self):
        ui.notify("Launch Backup Dwarf Data...")  # Simulate showing data
        explore_url = None
        if self.mode != "backup":
            Dwarf_id = self.get_selected_dwarf_id()
            if Dwarf_id != ALL_DWARFS:
                if self.selected_path:
                    session = os.path.basename(self.selected_path)
                    explore_url = f"/Transfer?DwarfId={Dwarf_id}&session={session}&mode=Archive&back_url=1"
                else:
                    explore_url = f"/Transfer?DwarfId={Dwarf_id}&mode=Archive&back_url=1"
        elif self.mode == "backup" and self.BackupDriveId:
            print(f"session:{self.selected_path}")
            print(f"session folder:{self.base_folder}")
            Dwarf_id = self.get_selected_dwarf_id()
            if Dwarf_id != ALL_DWARFS:
                if self.selected_path:
                    session = self.selected_path
                    explore_url = f"/Transfer?DwarfId={Dwarf_id}&session={session}&mode=Restore&BackupId={self.BackupDriveId}&back_url=1"
                else:
                    explore_url = f"/Transfer?DwarfId={Dwarf_id}&mode=Restore&BackupId={self.BackupDriveId}&back_url=1"
        else:
            explore_url = None
        print(explore_url)
        return explore_url
