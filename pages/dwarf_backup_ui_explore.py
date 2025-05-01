import os
import mimetypes
from astropy.io import fits
from datetime import datetime
import subprocess
from urllib.parse import quote
from fastapi.responses import FileResponse

from nicegui import app, ui
from dwarf_backup_db import DB_NAME, connect_db
from dwarf_backup_db_api import (
    get_dwarf_Names, get_dwarf_detail, get_Objects_dwarf, get_countObjects_dwarf, get_ObjectSelect_dwarf,
    get_backupDrive_Names, get_backupDrive_dwarfId, get_backupDrive_dwarfNames,
    get_Objects_backup, get_countObjects_backup, get_ObjectSelect_backup
)
from dwarf_backup_fct import get_Backup_fullpath

BASE_FOLDER = None

@app.get('/preview/{file_path:path}')
def serve_preview(file_path: str):
    global BASE_FOLDER
    if BASE_FOLDER is None:
        return {"error": "Base folder not set"}
    full_path = os.path.join(BASE_FOLDER, file_path.replace("\\", "/"))
    if os.path.exists(full_path):
        return FileResponse(full_path)
    else:
        return {"error": "File not found"}


@ui.page('/Explore/')
def dwarf_explore(BackupDriveId:int = None, DwarfId:int = None, mode:str = 'backup'):
    from components.menu import menu
    menu()

    # Call your menu function (assuming it's a predefined menu setup)
    menu()

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
        self.build_ui()

    def build_ui(self):
        self.conn = connect_db(self.database)

        with ui.row().classes('w-full h-screen items-center justify-center'):
            with ui.grid(columns=2):
                with ui.column().classes('w-full'):
                    if self.mode == "backup":
                        with ui.grid(columns=2):
                            with ui.column():
                                ui.label("Backup Drive:")
                                self.backup_filter = ui.select(options=[], on_change=self.on_backup_filter_change).props('outlined')

                            with ui.column():
                                ui.label("Dwarf:")
                                self.dwarf_filter = ui.select(options=[], on_change=self.load_objects).props('outlined')

                        self.only_on_dwarf = ui.checkbox("Only show sessions on selected Dwarf",on_change = self.load_objects)
                    else:
                        with ui.row():
                            ui.label("Dwarf:")
                            self.dwarf_filter = ui.select(options=[], on_change=self.load_objects).props('outlined')

                        with ui.row():
                            ui.label("")
                            self.only_on_backup = ui.checkbox("Only show backed up sessions of selected Dwarf",on_change = self.load_objects)

                    self.count_label = ui.label("Total matching sessions: 0")
                    with ui.card():
                        self.object_list = ui.list().classes('h-150 overflow-y-auto')

                with ui.column().classes('w-full items-start'):
                    with ui.row().classes('w-full'):
                        with ui.column().classes('w-full'):
                            ui.label('Files List')
                            self.file_list = ui.select(options=[], on_change=self.on_file_selected).props('outlined').style('overflow-x: auto;')

                        with ui.row().classes('justify-around'):
                            ui.button("🗁 Open", on_click=lambda: self.open_folder())
                            self.file_list.style('overflow: hidden; text-overflow: ellipsis;')
                            
                            self.jpg_icon = ui.icon('image').classes('text-6xl text-green-500')  # Example JPG icon
                            self.png_icon = ui.icon('image').classes('text-6xl text-blue-500')  # Example PNG icon
                            self.fits_icon = ui.icon('image').classes('text-6xl text-purple-500')  # Example FITS icon

                    with ui.row().classes('w-full'):
                        with ui.card():
                            with ui.column().classes('w-full'):
                                with ui.row():
                                    # List on the side
                                    self.details_files = ui.list().classes('h-50 overflow-y-auto')

                    with ui.row().classes('w-full'):
                        self.preview_image = ui.image().classes('w-full h-auto').props('fit=contain')

        self.preview_image.visible = False

        if self.mode == "backup":
            self.populate_backup_filter()
        else:
            self.populate_dwarf_filter()

        self.selected_path = ""

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
        self.preview_image.visible = False
        self.file_list.set_options([])
        self.details_files.clear()
        if self.mode == "backup":
            show_only = self.only_on_dwarf.value if self.only_on_dwarf else False
            self.objects = get_Objects_backup(self.conn, self.BackupDriveId, dwarf_id, show_only)
            count = get_countObjects_backup(self.conn, self.BackupDriveId, dwarf_id, show_only)
        else:
            show_only = self.only_on_backup.value if self.only_on_backup else False
            self.objects = get_Objects_dwarf(self.conn, dwarf_id, show_only)
            count = get_countObjects_dwarf(self.conn, dwarf_id, show_only)

        self.count_label.text = f"Total matching sessions: {count}"
        print (f"Total matching sessions: {count}")
        print (f"Total objects: {len(self.objects)}")
        print (f"Total objects: {[f"{oid} - {name}" for oid, name in self.objects]}")
        #self.selected_object = None
        self.load_objects_ui()

    def load_objects_ui(self, init_view = True):
        self.object_list.clear()

        with self.object_list:
            ui.item_label('List Objects').props('header').classes('text-bold')
            ui.separator()
            for oid, name in self.objects:
                item = ui.item(name, on_click=lambda oid=oid, name=name: self._handle_object_click(oid, name))

                # Highlight if selected
                if name == self.selected_object:
                    item.classes('bg-primary text-white')  # Change background and text color
                else:
                    item.classes('bg-transparent')  # Normal background

        # Force UI update after setting selected_object
        self.object_list.update()  # Refresh the list
        ui.update()  # Refresh the UI

    def _handle_object_click(self, oid, name):
        self.selected_object = name 
        self.select_object(oid)
        self.load_objects_ui()

    def show_date_session(self,date_db):
        dt = datetime.strptime(date_db, "%Y-%m-%d %H:%M:%S.%f")
        date_session = dt.strftime("%B %d, %Y at %I:%M:%S %p")
        return date_session

    def select_object(self, object_id):

        self.preview_image.visible = False
        dwarf_id = self.get_selected_dwarf_id()
        self.details_files.clear()
        details = []

        if self.mode == "backup":
            files = get_ObjectSelect_backup(self.conn, object_id, self.BackupDriveId, dwarf_id, self.only_on_dwarf.value)
        else:
            files = get_ObjectSelect_dwarf(self.conn, object_id, dwarf_id, self.only_on_backup.value)

        # Store all rows globally so we can access them later
        self.all_files_rows = files
    
        if len(files) == 0:
     
            self.file_list.set_options([])
            with self.details_files:
                ui.item_label('No files found.').props('header').classes('text-bold')

        if len(files) == 1:
            # If only one file, put it in the ComboBox and display it directly
            file_path = files[0][1]
            backup_path = files[0][6]  # location from BackupDrive or USB Dwarf

            full_path = get_Backup_fullpath (backup_path, "", file_path)
            
            select_file = [file_path]
            self.file_list.set_options(select_file, value=select_file[0])

            details_text = f"Taken with {files[0][9]} on {self.show_date_session(files[0][7])}"

            # details
            size_kb = os.path.getsize(full_path) / 1024
            size_mb = size_kb / 1024
            details.append(f"{self.show_date_session(files[0][7])}")
            details.append(f"Session: {files[0][8]}")
            details.append(f"Filename: {full_path}")
            if size_mb < 2:
                details.append(f"Size: {size_kb:.2f} KB")
            if size_mb >= 1:
                details.append(f"Size: {size_mb:.2f} MB")
            details.append(f"Exposure: {files[0][2]}s | Gain: {files[0][3]} | Filter: {files[0][4]}")
            if files[0][10] and files[0][11]:
                details.append(f"MinTemp: {files[0][10]} | MaxTemp: {files[0][11]}")
            details.append(f"Stacks: {files[0][5]}")
            
            self.selected_path = os.path.dirname(full_path)
            #with self.details_files:
            #    ui.item_label('One file found.').props('header').classes('text-bold')
            #    ui.separator()
            #    ui.item_label(details_text).props('header').classes('text-bold')
            #    for data_detail in details:
            #      ui.item(data_detail)

        else:
            # Populate combobox with readable file names
            self.all_files_rows = files
            #select_file = ['Select a file'] + [f"{row[1]} (Taken with {row[9]} | {self.show_date_session(row[7])}, exp {row[2]}s, gain {row[3]}, filter {row[4]}, stacks {row[5]})" for row in files]
            select_file = ['Select a file'] + [f"Taken with {row[9]} | {self.show_date_session(row[7])}, exp {row[2]}s, gain {row[3]}, filter {row[4]}, stacks {row[5]}" for row in files]
            self.file_list.set_options(select_file, value='Select a file')

            details.append(f"{len(files)} files(s) available(s) for this object.")

            with self.details_files:
                ui.item_label(f"{len(files)} files found.").props('header').classes('text-bold')
                ui.separator()
                for data_detail in details:
                   ui.item(data_detail)

    def open_folder(self):
        if not self.selected_path:
            print("No folder selected!")
            return

        # Normalize the path
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

        if not selected_value or selected_value=='Select a file':
            return

        self.details_files.clear()
        details_files_text = ""
        if selected_value and len(self.all_files_rows) == 1:
            selection_index = 0

        # Try to find the selected value in the options and get the corresponding index
        try:

            if  selection_index is None:

                # Map the selected value back to the corresponding row
                for idx, row in enumerate(self.all_files_rows):
                    # Build the label that matches the options shown
                    #label = f"{row[1]} (Taken with {row[9]} | {self.show_date_session(row[7])}, exp {row[2]}s, gain {row[3]}, filter {row[4]}, stacks {row[5]})"
                    label = f"Taken with {row[9]} | {self.show_date_session(row[7])}, exp {row[2]}s, gain {row[3]}, filter {row[4]}, stacks {row[5]}"
                
                    # Check if this label matches the selected value
                    if selected_value == label:
                        selection_index = idx
                        details_files_text = f"Taken with {row[9]} on {self.show_date_session(row[7])}"
                        break

        except ValueError:
            print("Selected value not found")

        if selection_index is not None:

            row = self.all_files_rows[selection_index]
            print(f"Selected row: {row}")

            file_path = row[1]
            backup_path = row[6]  # location from BackupDrive or USB Dwarf

            full_path = get_Backup_fullpath (backup_path, "", file_path)
            self.selected_path = os.path.dirname(full_path)

            if not full_path:
                self.preview_image.visible = False
                return

            if not os.path.isfile(full_path):
                self.preview_image.visible = False
                return

            # Store the base folder once
            global BASE_FOLDER
            BASE_FOLDER = BASE_FOLDER = full_path.replace("\\", "/").rsplit(file_path.replace("\\", "/"), 1)[0]

            print(f"BASE_FOLDER: {BASE_FOLDER}")
            details_files_text = f"Taken with {row[9]} on {self.show_date_session(row[7])}"

            # details
            size_kb = os.path.getsize(full_path) / 1024
            size_mb = size_kb / 1024
            details.append(f"{self.show_date_session(row[7])}")
            details.append(f"Session: {row[8]}")
            details.append(f"Filename: {full_path}")
            if size_mb < 2:
                details.append(f"Size: {size_kb:.2f} KB")
            if size_mb >= 1:
                details.append(f"Size: {size_mb:.2f} MB")
            details.append(f"Exposure: {row[2]}s | Gain: {row[3]} | Filter: {row[4]}")
            if row[10] and row[11]:
                details.append(f"MinTemp: {row[10]} | MaxTemp: {row[11]}")
            details.append(f"Stacks: {row[5]}")

            with self.details_files:
                ui.item_label(f"{details_files_text}").props('header').classes('text-bold')

                ui.separator()
                for data_detail in details:
                   ui.item(data_detail)

            # Check if the file is an image
            if file_path.lower().endswith(('.jpg', '.jpeg', '.png')):
                # To show a local file, we need to serve it. Quick way:
                url_path = f'/preview/{quote(file_path.replace("\\", "/"))}'

                self.preview_image.visible = True
                self.preview_image.source = url_path
            else:
                self.preview_image.visible = False

