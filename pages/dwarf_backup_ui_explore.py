import os
import mimetypes
from astropy.io import fits
from datetime import datetime
import subprocess

from nicegui import app, ui
from api.dwarf_backup_db import DB_NAME, connect_db
from api.dwarf_backup_db_api import (
    get_dwarf_Names, get_dwarf_detail, get_Objects_dwarf, get_countObjects_dwarf, get_ObjectSelect_dwarf,
    get_backupDrive_Names, get_backupDrive_dwarfId, get_backupDrive_dwarfNames,
    get_Objects_backup, get_countObjects_backup, get_ObjectSelect_backup,
    get_session_present_in_Dwarf, get_session_present_in_backupDrive, toggle_favorite
)
from api.dwarf_backup_fct import (
    get_Backup_fullpath, get_extension, check_files, get_file_path, generate_fits_preview, show_date_session,
    get_directory_size, count_fits_files, count_failed_fits_files, count_tiff_files, count_failed_tiff_files,
	hours_to_hms, deg_to_dms
)
from api.image_preview import set_base_folder, build_preview_url
from components.menu import menu

@ui.page('/Explore/')
def dwarf_explore(BackupDriveId:int = None, DwarfId:int = None, mode:str = 'backup'):

    menu("Explore")

    # Launch the GUI with the parameters
    ui.context.explore_app =  ExploreApp(DB_NAME, BackupDriveId=BackupDriveId, DwarfId=DwarfId, mode=mode)
    #ui.context.client.on_disconnect(lambda: logger.removeHandler(handler))

class ExploreApp:
    def __init__(self, database, BackupDriveId=None, DwarfId=None, mode='backup'):
        self.database = database
        self.BackupDriveId = BackupDriveId
        self.DwarfId = DwarfId
        self.mode = mode
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
        self.image_dialog = {}
        self.selected_path = ""
        self.build_ui()

    def build_ui(self):
        self.conn = connect_db(self.database)

        with ui.row().classes('w-full h-screen items-center justify-center'):
            with ui.grid(columns='1fr 2fr'):
                with ui.column().classes('w-full'):
                    if self.mode == "backup":
                        with ui.grid(columns=2):
                            with ui.column():
                                ui.label("Backup Drive:")
                                self.backup_filter = ui.select(options=[], on_change=self.on_backup_filter_change).props('outlined')

                            with ui.column():
                                ui.label("Dwarf:")
                                self.dwarf_filter = ui.select(options=[], on_change=self.load_objects).props('outlined')

                        with ui.card().tight().classes('pr-3'):
                            self.only_on_dwarf = ui.checkbox("Only show sessions present on selected Dwarf ",on_change = self.load_objects)
                            self.only_on_backup = ui.checkbox("Only show backed up sessions of selected Dwarf ",on_change = self.load_objects)
                    else:
                        with ui.row().classes('w-full'):
                            ui.label("Dwarf:")
                            self.dwarf_filter = ui.select(options=[], on_change=self.load_objects).props('outlined')

                        with ui.row().classes('w-full'):
                            with ui.card().tight():
                                ui.label("")
                                self.only_on_dwarf = ui.checkbox("Only show sessions on selected Dwarf",on_change = self.load_objects)
                                ui.label("")
                                self.only_on_backup = ui.checkbox("Only show backed up sessions of selected Dwarf",on_change = self.load_objects)

                    self.count_label = ui.label("Total matching sessions: 0")
                    with ui.card().tight().classes('w-full'):
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
        self.backup_options = get_backupDrive_Names(self.conn)
        names = ["(All Backups)"] + [name for _, name in self.backup_options]
        self.backup_filter.set_options(names, value = "(All Backups)")

    def on_backup_filter_change(self):
        print("on_backup_filter_change")
        selected_name = self.backup_filter.value
        if selected_name == "(All Backups)":
            self.BackupDriveId = None
        else:
            for bid, name in self.backup_options:
                if name == selected_name:
                    self.BackupDriveId = bid
                    break
        self.populate_dwarf_filter()

    def populate_dwarf_filter(self):
        print(f"dwarf_filter: {self.BackupDriveId}-{self.DwarfId}")
        if self.BackupDriveId:
            current_dwarf_id = get_backupDrive_dwarfId(self.conn, self.BackupDriveId)
            self.dwarf_options = get_backupDrive_dwarfNames(self.conn, self.BackupDriveId)
            names = [name for _, name in self.dwarf_options]
        else:
            self.dwarf_options = get_dwarf_Names(self.conn)
            names = ["(All Dwarfs)"] + [name for _, name in self.dwarf_options]
        print(names)
        # Set initial value
        initial_value = names[0] if names else None

        # If self.DwarfId is set, try to find corresponding name
        if self.DwarfId:
            match = next((name for did, name in self.dwarf_options if did == self.DwarfId), None)
            if match:
                initial_value = match

        self.dwarf_filter.set_options(names, value=initial_value)

    def get_selected_dwarf_id(self):
        value = self.dwarf_filter.value
        if self.BackupDriveId is None:
            if value == "(All Dwarfs)":
                return None
            return next((id_ for id_, name in self.dwarf_options if name == value), None)
        else:
            return next((id_ for id_, name in self.dwarf_options if name == value), None)

    def load_objects(self):
        dwarf_id = self.get_selected_dwarf_id()
        self.fullscreen_image.visible = False
        self.preview_image.visible = False
        self.file_list.set_options([])
        self.details_files.clear()
        self.details_preview.clear()
        self.reset_preview_icons()
        if self.mode == "backup":
            show_only_dwarf = self.only_on_dwarf.value if self.only_on_dwarf else False
            show_only_backup = self.only_on_backup.value if self.only_on_backup else False
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
        print (f"Total objects: {[f"{oid} - {name}" for oid, name in self.objects]}")
        self.selected_object = None
        self.selected_object_description = None
        self.load_objects_ui()

    def load_objects_ui(self, init_view = True):
        self.object_list.clear()

        with self.object_list:
            ui.item_label('List Objects').props('header').classes('text-bold')
            ui.separator()
            for oid, name in self.objects:
                name_object = name #name.split(" (")[0]
                # Get before " (" if present
                main_part = name.split(" (")[0]

                # Get the last part that begins with " ["
                bracket_pos = name.rfind(" [")
                suffix = name[bracket_pos:] if bracket_pos != -1 else ""

                name_object = (f"{main_part} {suffix}").strip()
 
                item = ui.item(name_object, on_click=lambda oid=oid, name=name_object, desc=name : self._handle_object_click(oid, name, desc))

                # Highlight if selected
                if name_object == self.selected_object:
                    item.classes('bg-primary text-white')  # Change background and text color
                else:
                    item.classes('bg-transparent')  # Normal background

        # Force UI update after setting selected_object
        self.object_list.update()  # Refresh the list
        ui.update()  # Refresh the UI

    def _handle_object_click(self, oid, name, desc):
        self.selected_object = name 
        self.selected_object_description = desc 
        self.select_object(oid)
        self.load_objects_ui()

    def select_object(self, object_id):

        self.fullscreen_image.visible = False
        self.preview_image.visible = False
        dwarf_id = self.get_selected_dwarf_id()
        self.details_files.clear()
        self.details_preview.clear()
        self.reset_preview_icons()
        details = []

        if self.mode == "backup":
            files = get_ObjectSelect_backup(self.conn, object_id, self.BackupDriveId, dwarf_id, self.only_on_dwarf.value, self.only_on_backup.value)
        else:
            files = get_ObjectSelect_dwarf(self.conn, object_id, dwarf_id, self.only_on_dwarf.value, self.only_on_backup.value)

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
            select_file = ['Select a session']

            for row in files:
                # Extracting values for clarity
                device = row[9]
                session_date = show_date_session(row[7])
                exp = f"{row[2]}s" if row[2] is not None else "N/A"
                gain = row[3] if row[3] is not None else "N/A"
                astro_filter = row[4]
                stacks = row[5]
                is_favorite = row[12]  # The favorite column (0 or 1)

                # Displaying star icon based on favorite status only in backup mode
                star_icon = '⭐ ' if is_favorite else '☆ '

                # Building the details string with the star icon
                details.append(
                    f"{star_icon}Taken with {device} | {session_date}, exp {exp}, gain {gain}, filter {astro_filter}, stacks {stacks}"
                )

                select_file.append(
                    f"Taken with {device} | {session_date}, exp {exp}, gain {gain}, filter {astro_filter}, stacks {stacks}"
                )

            self.file_list.set_options(select_file, value='Select a session')

            with self.details_files:
                ui.item_label(f"{len(files)} sessions found.").props('header').classes('text-bold')
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

    def on_file_selected(self):
        selection_index = None
        selected_value = self.file_list.value
        print(f"Selected value: {selected_value}")
        details = []

        if not selected_value or selected_value=='Select a session':
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
                    exp = f"{row[2]}s" if row[2] is not None else "N/A"
                    gain = row[3] if row[3] is not None else "N/A"
                    is_favorite = row[12]  # The favorite column (0 or 1)
                    star_icon = '⭐ ' if is_favorite else '☆ '
                    label = f"Taken with {row[9]} | {show_date_session(row[7])}, exp {exp}, gain {gain}, filter {row[4]}, stacks {row[5]}"
                    # Strip out the star icon to compare only the text portion
                    comparison_label = label.lstrip('⭐').lstrip('☆').strip()
                    # Strip the star icon from the selected value for comparison
                    selected_value_stripped = selected_value.lstrip('⭐').lstrip('☆').strip()
                
                    # Check if this label matches the selected value
                    if selected_value_stripped == label:
                        selection_index = idx
                        details_files_text = f"{star_icon}Taken with {row[9]} on {show_date_session(row[7])}"
                        break

        except ValueError:
            print("Selected value not found")

        if selection_index is not None:

            row = self.all_files_rows[selection_index]

            file_path = row[1]
            backup_path = row[6]  # location from BackupDrive or USB Dwarf
            is_favorite = row[12]  # The favorite column (0 or 1)
            star_icon = '⭐ ' if is_favorite else '☆ '
            full_path = get_Backup_fullpath (backup_path, "", file_path)
            self.selected_path = os.path.dirname(full_path)

            # Store the base folder once
            self.base_folder = full_path.replace("\\", "/").rsplit(file_path.replace("\\", "/"), 1)[0]
            set_base_folder(full_path.replace("\\", "/").rsplit(file_path.replace("\\", "/"), 1)[0])

            details_files_text = f"{star_icon}Taken with {row[9]} on {show_date_session(row[7])}"

            # details

            #details.append(f"{show_date_session(row[7])}")
            session_dir = row[8]
            details.append(f"Session: {session_dir}")
            init_target = row[13]
            details.append(f"Dwarf Target: {init_target}")
            if self.selected_object_description != init_target:
                details.append(f"Classified as: {self.selected_object_description.rsplit(" [")[0]}")
            declination = row[14]
            right_ascencion = row[15]
            details.append(f"RA: {hours_to_hms(right_ascencion)} | Dec: {deg_to_dms(declination)}")

            exp = f"{row[2]}s" if row[2] is not None else "N/A"
            gain = row[3] if row[3] is not None else "N/A"

            details.append(f"Exposure: {exp} | Gain: {gain} | Filter: {row[4]}")
            if row[10] and row[11]:
                details.append(f"MinTemp: {row[10]} | MaxTemp: {row[11]}")
            details.append(f"Stacks: {row[5]}")

            with self.details_files:
                label = ui.item_label(f"{details_files_text}").props('header').classes('text-bold').props('clickable').classes(f'cursor-pointer {self.get_hover_class()} transition-colors duration-200 rounded')
                # Set the tooltip text based on the favorite state
                tooltip_text = "Click to Remove from Favorites" if is_favorite else "Click to Add to Favorites"
                # Add tooltip
                label.props(f'title="{tooltip_text}"')
                # Make the label clickable to toggle favorite
                label.on('click', lambda _, eid=row[0], lbl=label, mode=self.mode: self.toggle_favorite_ui(eid, lbl, mode))
                ui.separator()
                for data_detail in details:
                   ui.item(data_detail)

            self.astro_files = check_files(full_path)
            self.update_preview_icons()
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
        try:
            directory = os.path.dirname(self.preview_image_path)
            size_dir_kb = get_directory_size(directory) / 1024
            size_dir_mb = size_dir_kb / 1024
            size_kb = os.path.getsize(self.preview_image_path) / 1024
            size_mb = size_kb / 1024
            nb_fits_files = count_fits_files(directory)
            nb_failed_fits_files = count_failed_fits_files(directory)
            nb_tiff_files = count_tiff_files(directory)
            nb_failed_tiff_files = count_failed_tiff_files(directory)
        except FileNotFoundError:
            print("File2 not found")
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
        if size_dir_kb is not None and size_dir_mb >= 1:
            details_preview.append(f"Directory Size: {size_dir_mb:.2f} MB")
        details_preview.append(f"Filename: {self.preview_image_path}")
        if size_kb is not None and size_mb < 2:
            details_preview.append(f"Size: {size_kb:.2f} KB")
        if size_kb is not None and size_mb >= 1:
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
            for data_detail in details_preview:
               ui.item(data_detail)
            if nb_fits_files is None or nb_fits_files == 0:
                ui.item_label(f"No fits image Found on the disk").classes("text-red-600").classes("pl-4 pr-4 pb-4").props('header').classes('text-bold')
            self.get_details_presence_label(self.preview_image_path, file_path)

    def get_details_presence_label(self, preview_image_path: str, file_path):
        if preview_image_path:
            session_dir = os.path.basename(os.path.dirname(preview_image_path))

            if self.mode == "backup":
                result_on_Dwarf = get_session_present_in_Dwarf(self.conn, session_dir)
                print(f"result_on_Dwarf: {result_on_Dwarf}")
                if result_on_Dwarf:
                    dwarf_full_path = get_Backup_fullpath (result_on_Dwarf[2], "", result_on_Dwarf[3])
                    print(f"dwarf_full_path: {dwarf_full_path}")
                    if os.path.isdir(os.path.dirname(dwarf_full_path)):
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

    def set_preview(self, path: str):
        if path.lower().endswith('.fits'):
            path = generate_fits_preview(path)
        return path