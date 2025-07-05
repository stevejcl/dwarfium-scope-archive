import os
import mimetypes
from astropy.io import fits
from datetime import datetime
from collections import defaultdict
from pathlib import Path
import subprocess

from nicegui import app, ui
from api.dwarf_backup_db import DB_NAME, connect_db
from api.dwarf_backup_db_api import (
    get_dwarf_Names, get_dwarf_detail, get_Objects_dwarf, get_countObjects_dwarf, get_ObjectSelect_dwarf,
    get_backupDrive_Names, get_backupDrive_dwarfId, get_backupDrive_dwarfNames,
    get_Objects_backup, get_countObjects_backup, get_ObjectSelect_backup,
    get_Objects_duplicate_backup, get_countObjects_duplicate_backup, get_ObjectSelect_duplicate_backup,
    get_session_present_in_Dwarf, get_session_present_in_backupDrive, toggle_favorite
)
from api.dwarf_backup_fct import (
    get_Backup_fullpath, get_extension, check_files, get_file_path, generate_fits_preview, show_date_session,
    get_directory_size, count_fits_files, count_failed_fits_files, count_tiff_files, count_failed_tiff_files,
    hours_to_hms, deg_to_dms, is_path_local_dwarf_dir, get_total_exposure
)
from api.image_preview import set_base_folder, build_preview_url
from components.menu import menu

ALL_BACKUPS = "(All Backups)"
ALL_DWARFS = "(All Dwarfs)"
TAKEN = "Taken"
RESTACK = "Restack"
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
        self.preview_image_type = "jpg"
        self.astro_files = {}
        self.open_folder_icon = {}
        self.preview_icons = {}
        self.fullscreen_icon = {}
        self.backup_session_icon = {}
        self.image_dialog = {}
        self.selected_path = ""
        self.build_ui()

    def build_ui(self):
        self.conn = connect_db(self.database)

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
        print (f"Total objects: {[f"{oid} - {name} {dso_id}" for oid, name, dso_id in self.objects]}")
        self.selected_object = None
        self.selected_object_description = None
        self.load_objects_ui()

    def get_name_object(self, name):
        name_object = name #name.split(" (")[0]
        # Get before " (" if present
        main_part = name.split(" (")[0]

        # Get the last part that begins with " ["
        bracket_pos = name.rfind(" [")
        suffix = name[bracket_pos:] if bracket_pos != -1 else ""

        name_object = (f"{main_part} {suffix}").strip()

        return name_object, main_part

    def load_objects_ui(self, init_view = True):

        self.object_list.clear()
        filter_dso = set()
        visible_names = []

        dso_id_counts = defaultdict(int)
        for _, name, dso_id in self.objects:
            name_object, main_part = self.get_name_object(name)
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
            for oid, name, dso_id in self.objects:
                name_object, main_part = self.get_name_object(name)

                # Apply filter
                if self.object_filter.value and self.object_filter.value.lower() not in name_object.lower():
                    continue

                visible_names.append(name_object)

                # Insert the [ALL] line if needed
                if dso_id is not None and dso_id_counts[dso_id] > 1 and dso_id not in shown_all_for_dso and dso_id not in filter_dso :
                    all_name = f"{main_part} [ALL]"
                    visible_names.append(all_name)  # 👈 ADD [ALL] entry to visible_names
                    item_all = ui.item(all_name, on_click=lambda dso_id=dso_id, name=all_name, desc=name : self._handle_object_click(None, name, desc, dso_id))
                    item_all.classes('font-bold text-blue-600')  # Optional styling
                    if all_name == self.selected_object:
                        item_all.classes('bg-primary text-white')
                    else:
                        item_all.classes('bg-transparent')
                    shown_all_for_dso.add(dso_id)

                # Add the actual object
                item = ui.item(name_object, on_click=lambda oid=oid, name=name_object, desc=name : self._handle_object_click(oid, name, desc, None))

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

    def _handle_object_click(self, oid, name, desc, dso_id):
        self.selected_object = name 
        self.selected_object_description = desc 
        self.select_object(oid, dso_id)
        self.load_objects_ui()

    def clear_selected_object(self):
        self.fullscreen_image.visible = False
        self.preview_image.visible = False

        self.details_files.clear()
        self.details_preview.clear()
        self.reset_preview_icons()
        self.file_list.set_options([])

    def select_object(self, object_id, dso_id):
        dwarf_id = self.get_selected_dwarf_id()
        details = []
        self.clear_selected_object()

        if self.mode == "backup":
            show_only_duplicates = self.only_duplicates_backup.value if self.only_duplicates_backup else False
            if show_only_duplicates:
                files = get_ObjectSelect_duplicate_backup(self.conn, object_id, dso_id, self.BackupDriveId, dwarf_id, self.only_on_dwarf.value, self.only_on_backup.value)
            else:
                files = get_ObjectSelect_backup(self.conn, object_id, dso_id, self.BackupDriveId, dwarf_id, self.only_on_dwarf.value, self.only_on_backup.value)
        else:
            files = get_ObjectSelect_dwarf(self.conn, object_id, dso_id, dwarf_id, self.only_on_dwarf.value, self.only_on_backup.value)

        # Store all rows globally so we can access them later
        self.all_files_rows = files
    
        if len(files) == 0:
     
            self.file_list.set_options([])
            with self.details_files:
                ui.item_label('No Session found.').props('header').classes('text-bold')

        if len(files) == 1:
            # If only one file, put it in the ComboBox and display it directly
            file_path = files[0][1]
            backup_path = files[0][6]  # location from BackupDrive or USB Dwarf

            full_path = get_Backup_fullpath (backup_path, "", file_path)
            
            select_file = [file_path]
            self.file_list.set_options(select_file, value=select_file[0])

        else:
            # Populate combobox with readable file names
            self.all_files_rows = files
            details = []
            select_file = [f'Select a session for {self.selected_object}']
            stackeds = 0
            total_time_exp = 0

            for row in files:
                # Extracting values for clarity
                device = row[9]
                session_date = show_date_session(row[7])
                lens = "(W) " if ("_WIDE_") in row[8] else ""
                exp = f"{row[2]}s" if row[2] is not None else "N/A"
                gain = row[3] if row[3] is not None else "N/A"
                astro_filter = row[4]
                stacks = row[5]
                is_favorite = row[12]  # The favorite column (0 or 1)
                stackeds += stacks
                if row[2]:
                    total_time_exp += stacks * self.parse_exposure(f"{row[2]}s")

                # Displaying star icon based on favorite status only in backup mode
                star_icon = '⭐ ' if is_favorite else '☆ '
                info_stack = RESTACK if self.is_Restacked(row[8]) else TAKEN
                # Building the details string with the star icon
                details.append(
                    f"{star_icon}{info_stack} with {device} {lens}| {session_date}, exp {exp}, gain {gain}, filter {astro_filter}, stacks {stacks}"
                )

                select_file.append(
                    f"{info_stack} with {device} {lens}| {session_date}, exp {exp}, gain {gain}, filter {astro_filter}, stacks {stacks}"
                )

            self.file_list.set_options(select_file, value=f'Select a session for {self.selected_object}')

            with self.details_files:
                ui.item_label(f"{len(files)} sessions were found, totaling {stackeds} stacks and a total exposure time of {self.format_seconds_hms(total_time_exp)}.").props('header').classes('text-bold')
                ui.separator()

                for data_detail in details:
                   ui.item(data_detail, on_click=lambda i=data_detail.lstrip('⭐').lstrip('☆').strip(): self.file_list.set_value(i)).props('clickable').classes('cursor-pointer')

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

    def parse_exposure(self, exp_str):
        """
        Convert exposure string like '30s' or '1/250s' to seconds as float.
        """
        if not exp_str or not exp_str.endswith('s'):
            return 0.0
        value = exp_str[:-1]  # Remove trailing 's'
        if '/' in value:
            # Handle fractional exposure: e.g., '1/250'
            try:
                numerator, denominator = value.split('/')
                return float(numerator) / float(denominator)
            except:
                return 0.0
        else:
            try:
                return float(value)
            except:
                return 0.0

    def format_seconds_hms(self, total_seconds):
        total_seconds = int(total_seconds)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        parts = []
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        if seconds or not parts:
            parts.append(f"{seconds}s")
        return ' '.join(parts)

    def is_Restacked(sel, session_name):
        return session_name.startswith("RESTACKED_")

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
        print(f"Selected value: {selected_value}")
        details = []

        if not selected_value or selected_value.startswith('Select a session'):
            return

        self.details_files.clear()
        self.details_preview.clear()
        self.reset_preview_icons()

        details_files_text = ""
        if selected_value and len(self.all_files_rows) == 1:
            selection_index = 0

        # Try to find the selected value in the options and get the corresponding index
        try:

            if  selection_index is None:

                # Map the selected value back to the corresponding row
                for idx, row in enumerate(self.all_files_rows):
                    # Build the label that matches the options shown
                    #label = f"{row[1]} (Taken with {row[9]} | {show_date_session(row[7])}, exp {row[2]}s, gain {row[3]}, filter {row[4]}, stacks {row[5]})"
                    lens = "(W) " if ("_WIDE_") in row[8] else ""
                    exp = f"{row[2]}s" if row[2] is not None else "N/A"
                    gain = row[3] if row[3] is not None else "N/A"
                    is_favorite = row[12]  # The favorite column (0 or 1)
                    star_icon = '⭐ ' if is_favorite else '☆ '
                    info_stack = RESTACK if self.is_Restacked(row[8]) else TAKEN
                    label = f"{info_stack} with {row[9]} {lens}| {show_date_session(row[7])}, exp {exp}, gain {gain}, filter {row[4]}, stacks {row[5]}"
                    # Strip out the star icon to compare only the text portion
                    comparison_label = label.lstrip('⭐').lstrip('☆').strip()
                    # Strip the star icon from the selected value for comparison
                    selected_value_stripped = selected_value.lstrip('⭐').lstrip('☆').strip()
                
                    # Check if this label matches the selected value
                    if selected_value_stripped == label:
                        selection_index = idx
                        lens = "(Wide)" if ("_WIDE_") in row[8] else "(Tele)"

                        details_files_text = f"{star_icon}{info_stack} with {row[9]} {lens} on {show_date_session(row[7])}"
                        break

        except ValueError:
            print("Selected value not found")

        if selection_index is not None:

            row = self.all_files_rows[selection_index]

            file_path = row[1]
            backup_path = row[6]  # location from BackupDrive or USB Dwarf
            is_favorite = row[12]  # The favorite column (0 or 1)
            info_stack = RESTACK if self.is_Restacked(row[8]) else TAKEN
            star_icon = '⭐ ' if is_favorite else '☆ '
            full_path = get_Backup_fullpath (backup_path, "", file_path, self.get_selected_dwarf_id())
            self.selected_path = os.path.dirname(full_path)

            # Store the base folder once
            self.base_folder = full_path.replace("\\", "/").rsplit(file_path.replace("\\", "/"), 1)[0]
            set_base_folder(full_path.replace("\\", "/").rsplit(file_path.replace("\\", "/"), 1)[0])
            lens = "(Wide)" if ("_WIDE_") in row[8] else "(Tele)"

            details_files_text = f"{star_icon}{info_stack} with {row[9]} {lens} on {show_date_session(row[7])}"

            # details

            #details.append(f"{show_date_session(row[7])}")
            session_dir = row[8]
            #details.append(f"Session: {session_dir}")
            init_target = row[13]
            details.append(f"Dwarf Target: {init_target}")
            if self.selected_object_description != init_target:
                details.append(f"Classified as: {self.selected_object_description.rsplit(" [")[0]}")
            declination = row[14]
            right_ascencion = row[15]
            details.append(f"RA: {hours_to_hms(right_ascencion)} | Dec: {deg_to_dms(declination)}")

            lens = "Wide" if ("_WIDE_") in row[8] else "Tele"
            exp = f"{row[2]}s" if row[2] is not None else "N/A"
            gain = row[3] if row[3] is not None else "N/A"

            details.append(f"Lens : {lens} | Exposure: {exp} | Gain: {gain} | Filter: {row[4]}")
            if row[10] and row[11]:
                details.append(f"MinTemp: {row[10]} | MaxTemp: {row[11]}")
            details.append(f"Stacks: {row[5]}")

            self.astro_files = check_files(full_path)
            self.update_preview_icons()

            with self.details_files:
                label = ui.item_label(f"{details_files_text}").props('header').classes('text-bold').props('clickable').classes(f'cursor-pointer {self.get_hover_class()} transition-colors duration-200 rounded')
                # Set the tooltip text based on the favorite state
                tooltip_text = "Click to Remove from Favorites" if is_favorite else "Click to Add to Favorites"
                # Add tooltip
                label.props(f'title="{tooltip_text}"')
                # Make the label clickable to toggle favorite
                label.on('click', lambda _, eid=row[0], lbl=label, mode=self.mode: self.toggle_favorite_ui(eid, lbl, mode))
                ui.separator()

                # Add colored details
                ui.item(f"Session: {session_dir}").classes('text-blue-800')
                ui.item(f"Dwarf Target: {init_target}").classes('text-green-600')

                if self.selected_object_description != init_target:
                    classified = self.selected_object_description.rsplit(" [")[0]
                    ui.item(f"Classified as: {classified}").classes('text-gray-500')

                ui.item(f"RA: {hours_to_hms(right_ascencion)} | Dec: {deg_to_dms(declination)}").classes('text-purple-600')

                lens = "Wide" if ("_WIDE_") in row[8] else "Tele"
                exp = f"{row[2]}s" if row[2] is not None else "N/A"
                exp_value = self.parse_exposure(exp) if exp != "N/A" else 0
                gain = row[3] if row[3] is not None else "N/A"
                with ui.row().classes('w-full gap-8 items-start'):
                    ui.item(f"Lens : {lens} | Exposure: {exp} | Gain: {gain} | Filter: {row[4]}").classes('text-yellow-700')

                    if row[10] and row[11]:
                        ui.item(f"MinTemp: {row[10]} | MaxTemp: {row[11]}").classes('text-sky-700')

                stacks = row[5]
                color = 'text-red-600' if stacks < 100 else 'text-indigo-600'
                
                # get exposure for Restacked session
                exposure_time = self.format_seconds_hms(exp_value * stacks)
                if self.is_Restacked(row[8]):
                    fits_path = self.astro_files.get('fits')
                    if fits_path and os.path.isfile(fits_path):
                        exposure_time = self.format_seconds_hms(get_total_exposure(fits_path))

                ui.item(f"{stacks} stacked shots for a total exposure time of {exposure_time}").classes(color)

                # add Mosaic Panel Info
                #for data_detail in details:
                #   ui.item(data_detail)

            self.preview_image_path = full_path
            self.update_preview(full_path)

    def get_hover_class(self):
        return 'hover:bg-gray-700' if app.storage.user.get('ui_mode', 0) == 'dark' else 'hover:bg-gray-300'

    def toggle_favorite_ui(self, entry_id, label_element, mode):
        # Call the API function directly
        new_favorite = toggle_favorite(self.conn, entry_id, label_element, mode)
    
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
            restacked_session = self.is_Restacked(os.path.basename(directory))
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
                    dwarf_full_path = get_Backup_fullpath (result_on_Dwarf[2], "", result_on_Dwarf[3], self.get_selected_dwarf_id())
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
                exists = path and os.path.isfile(path)
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
                self.backup_session_icon.visible = True
                self.backup_session_icon.enable()
            else:
                self.backup_session_icon.visible = False
                self.backup_session_icon.disable()

    def set_preview(self, path: str):
        if path.lower().endswith('.fits'):
            path = generate_fits_preview(path)
        return path

    def get_backup_url(self):
        ui.notify("Launch Backup Dwarf Data...")  # Simulate showing data
        Dwarf_id = self.get_selected_dwarf_id()
        if Dwarf_id != ALL_DWARFS:
            if self.selected_path:
                session = os.path.basename(self.selected_path)
                explore_url = f"/Transfer?DwarfId={Dwarf_id}&session={session}&mode=Archive"
            else:
                explore_url = f"/Transfer?DwarfId={Dwarf_id}&mode=Archive"
        else:
            explore_url = None
        print(explore_url)
        return explore_url
