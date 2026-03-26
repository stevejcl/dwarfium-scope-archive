import webview
from nicegui import ui, app, run, Client

import os
import requests
import traceback
import asyncio

from pathlib import Path
import tempfile
import shutil
import json
import re

from astropy.io import fits
from astropy.wcs import WCS

from components.menu import menu
from api.dwarf_backup_fct import ( 
    hours_to_hms, deg_to_dms, format_seconds_hms, read_fits_metadata, preprocess_dso_catalog_json, transform_session_name, extract_core_name, extract_datetime_from_session_name, is_Restacked, get_name_object,
    show_short_date_session, get_total_exposure, get_total_mosaic_exposure, parse_exposure, get_Backup_fullpath, check_files, create_thumbnail
)
from api.dwarf_backup_db import DB_NAME, connect_db, close_db
from api.dwarf_backup_db_api import get_dwarf_Names, get_dwarf_detail, get_backupDrive_list_dwarfId, insert_astro_object, get_astro_object_description, get_sessions_backup, get_session_backup_details, get_setting_text
from api.astrometry_resolver import auto_resolve, get_fits_center_coordinates

from components.win_log import WinLog
from components.astro_object_associate import DwarfData, show_unknown_target_dialog

from api.dwarf_backup_fct import CATALOG_FILE, SKY_CATALOG_FILE, UNKNOWN, MOSAIC_UNKNOWN, MANUAL, TAKEN, RESTACK

client_apps = {}

@ui.page('/AddManualSession/')
async def manual_session_page(client: Client, DwarfId:int = None, session:str = None, BackupDriveId:int = None):

    menu("Add Manual Session")
    await ui.context.client.connected()
    # Launch the GUI
    ui.context.manual_session_app =  AddManualSession(client, DB_NAME, DwarfId=DwarfId, Session=session, BackupDriveId=BackupDriveId)
    #ui.context.client.on_disconnect(lambda: logger.removeHandler(handler))

    def final_cleanup_temp_files():
        storage = getattr(client, 'storage', None)
        if storage is None:
            print("No storage object found")
            return

        files = getattr(storage, 'uploaded_files', [])

        for file_info in files:
            if file_info.get("is_temp") and os.path.exists(file_info.get("path")):
                try:
                    print(f"Remove temp file {file_info.get('path')}")
                    os.remove(file_info.get('path'))
                except Exception as e:
                    print(f"Failed to remove temp file {file_info.get('path')}: {e}")

        client.storage.uploaded_files = [f for f in files if not f.get("is_temp")]
        print(f"Keep {len(client.storage.uploaded_files)}")

    # Register cleanup on disconnect
    client.on_disconnect(lambda: final_cleanup_temp_files())


class AddManualSession:
    def __init__(self, client: Client, database, DwarfId=None, Session=None, BackupDriveId=None):
        self.client = client
        self.mode_stellar = "Stellar Studio" # Default mode
        self.mode_manual = "Manual"
        self.mode_darks = "Darks"
        self.mode = self.mode_stellar
        self.database = database
        self.dwarfs = []

        self.DwarfId = DwarfId
        self.dwarf_options = []
        self.BackupDriveId = BackupDriveId
        self.backup_options = []

        self.DwarfId_Init = DwarfId
        self.BackupDriveId_Init = BackupDriveId
        self.session = Session
        self.backup_StellarStudio = "STELLAR_SESSION"
        self.dso_catalog = False

        self.dest_dir = '' # 'T:\\DWARFLAB_2\\DATA4\\DATA_OBJECTS\\NGC7000_North_American_Nebula'
        self.dest_main_dir = '' # 'T:\\DWARFLAB_2\\DATA4\\DATA_OBJECTS\\NGC7000_North_American_Nebula'

        # Initialize per-client storage
        if not hasattr(client.storage, 'uploaded_files'):
            client.storage.uploaded_files = []

        self.uploaded_fits_files = []
        self._accepted_files_data = {}  # name -> bytes, files confirmed good
        self._pending_reset = False

        self.sessions_list = []
        self.session_lookup = []
        self.session_name_lookup = {}
        self.label_session_dir="Directory:"
        self.selected_session_dirname = None
        self.selected_session_name = None
        self.session_select_status_label = ""
        self.session_select_thumbnail = None
        self.session_select_image = None
        
        self.fits_file_list = None
        self.details_fits_files = None

        self.selected_object_description = None
        self.selected_file = None

        self.current_tmpfile = None

        self.linked_data = {
            "session_id": None,
            "session_full_name": "",
            "astro_object_id": ""
        }

        self.links = []
        self.main_meta_info = None
        self.meta_info = None
        self.build_ui()
        self.set_mode_UI()

    def set_mode_UI(self):

        self.DestinationDirectory.set_text("Destination: Backup Drive")
        self.DestinationMainDir = "the backup directory!"
        self.ScanningMessage = "🔍 Scanning Dwarf drive, please wait..."
        self.EndScanningMessage = "End of Scanning Dwarf drive"

    def switch_mode(self):
        self.mode = self.mode_toggle.value
        print(self.mode)

        self.set_mode_UI()
        self.main_ui.update()

    # ----------------- UTILITAIRES -----------------
    def fetch_fits_from_url(self, url: str) -> Path:
        """Downloads the FITS from the URL and returns the temporary path"""
        response = requests.get(url, stream=True)
        response.raise_for_status()
        temp_file = Path(tempfile.mktemp(suffix=".fits"))
        with open(temp_file, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return temp_file

    def resolve_file(self, api_key, file_info, log):
        """Astrometric resolution of a FITS file"""
        path = file_info.get("path","")
        # convert RA deg value in Hours
        ra, dec = get_fits_center_coordinates(path, True)
        print(f"RA: {ra}")
        print(f"DEC: {dec}")
        if ra is None or dec is None:
            try:
                solved_file = auto_resolve(api_key, path, log)
                # Quick check: is it really a FITS file?
                try:
                    with fits.open(solved_file) as hdul:
                        ra, dec = get_fits_center_coordinates(solved_file, True)
                        print(f"RA: {ra}")
                        print(f"DEC: {dec}")
                        # Updates the original FITS
                        if solved_file != path:
                            with fits.open(path, mode='update') as hdul:
                                hdul[0].header['CRVAL1'] = ra
                                hdul[0].header['CRVAL2'] = dec
                                hdul.flush()
                except Exception:
                    print(f"❌ {solved_file} is not a valid FITS file (server may have failed).")
                    ra = dec = None

            except Exception as e:
                print(f"⚠️ Error resolution {path}: {e}")
                ra, dec = None, None
        file_info['ra'] = ra
        file_info['dec'] = dec

    def build_ui(self):
        self.conn = connect_db(self.database)
        # Load the preprocessed catalog once at app start
        preprocess_dso_catalog_json(CATALOG_FILE, SKY_CATALOG_FILE)

        if os.path.exists(SKY_CATALOG_FILE): 
            with open(SKY_CATALOG_FILE  , "r", encoding="utf-8") as f:
                self.dso_catalog = json.load(f)

        with ui.card().classes("w-full p-4 mt-4 items-center") as self.main_ui:
            self.mode_toggle = ui.toggle([self.mode_stellar, self.mode_manual], value=self.mode_stellar, on_change=self.switch_mode)

            with ui.grid(columns=2):
                with ui.column():
                    ui.label("Select Dwarf:").classes("text-lg font-semibold")
                    self.dwarf_filter = ui.select(options=[], on_change=self.on_dwarf_filter_change).props('outlined')
                    self.usb_status_label = ui.label("").classes('pb-2')

                with ui.column():
                    ui.label("Backup Drive:").classes("text-lg font-semibold")
                    self.backup_filter = ui.select(options=[], on_change=self.on_backup_filter_change).props('outlined')
                    self.backup_status_label = ui.label("").classes('pb-2')

            with ui.card().classes("w-full p-4").style("max-width: 2600px; margin: auto"):
                ui.label(f'Backup {self.mode} Files')

                # --- SESSION SELECTION ---
                with ui.row().classes("items-center mb-4"):
                    ui.label("Select Backup Session:")
                    self.session_dropdown = ui.select(options=[], on_change=self.on_session_select).classes("w-auto min-w-[300px]")
                    ui.label("Session:")
                    self.session_dirname = ui.input(self.session_select_status_label, placeholder="Enter new session name", on_change=self.on_check_session_dirname).classes("min-w-[500px] w-auto overflow-x-auto whitespace-nowrap")

                with ui.row().classes('w-full items-start'):
                    # LEFT COLUMN
                    with ui.column().classes('w-2/3'):
                        self.detail_session_name = ui.label("").classes('text-blue-800')
                        self.detail_session = ui.label("").style('white-space: pre-line').classes('text-purple-600')

                    # RIGHT COLUMN
                    with ui.column().classes('w-1/4'):
                        self.thumbnail = ui.image(self.session_select_thumbnail) \
	                                     .classes('w-40 h-auto rounded-lg cursor-pointer hover:opacity-80') \
                                         .on('click', self.show_full_image)

                # --- LOCAL FILES SELECTION ---
                with ui.grid(columns=3).classes("w-full"):
                    with ui.column().classes("items-center justify-center text-center w-full"):
                        ui.label("Select Local JPG Files (optional)").classes("mt-2 font-medium")
                        self.file_picker_jpg = ui.upload(
                            label="Upload JPG",
                            auto_upload=True,
                            multiple=True,
                            on_upload=self.handle_upload,
                        ).props('accept="image/jpeg"').classes("mb-4")

                    with ui.column().classes("items-center justify-center text-center w-full"):
                        ui.label("Select Local PNG Files (optional)").classes("mt-2 font-medium")
                        self.file_picker_png = ui.upload(
                            label="Upload PNG",
                            auto_upload=True,
                            multiple=True,
                            on_upload=self.handle_upload,
                        ).props('accept="image/png"').classes("mb-4")

                    with ui.column().classes("items-center justify-center text-center w-full"):
                        ui.label("Select Local FITS Files (optional)").classes("mt-2 font-medium")
                        self.file_picker_fit = ui.upload(
                            label="Upload FITS",
                            auto_upload=True,
                            multiple=True,
                            on_upload=self.handle_upload,
                        ).props('accept=".fit,.fits,.fts"').classes("mb-4")
                self.file_picker_fit_id = self.file_picker_fit.id

                self.remove_button = ui.button("🗑️ Remove all files", on_click=self.cleanup_temp_files).props("color=red")


                # Use on_rejected + validation BEFORE the file hits the queue
                #self.file_picker_fit2 = (
                #    ui.upload(
                #        label="Upload FITS",
                #        auto_upload=True,
                #        multiple=True,
                #        on_upload=self.handle_upload,
                #        on_rejected=self.handle_rejected,  # fires for wrong extensions
                #    )
                #    .props('accept=".fit,.fits,.fts"')
                #    .props('filter="checkFitsTarget"')  # custom Quasar filter fn
                #    .classes("mb-4")
                #)
                
                ui.label(f"Select {self.mode} FITS file(s)").classes("mt-2 font-medium")

                with ui.row().classes("w-full items-center gap-2"):
                    self.link_input = ui.input(
                        placeholder="Enter FITS file URL (https://...)",
                        on_change=self.on_fits_file_change
                    ).props('clearable').classes("w-[80%]")
                    self.add_button = ui.button("Add", on_click=self.add_or_remove_file)

                with ui.card().tight().classes('w-full'):
                    # List on the side
                    ui.label("Added FITS files list").classes("ml-2 mt-2 font-medium")
                    self.details_fits_files = ui.list().classes('w-full h-50 overflow-y-auto')

                with ui.card().tight().classes('w-full'):
                    ui.label("Main File Session Information (From First Fits file uploaded)").classes("ml-2 mt-2 mb-2 font-medium")
                    self.details_files = ui.list().classes('w-full h-50 overflow-y-auto')
 
                self.DestinationDirectory = ui.label("Destination: Backup Drive").classes("mt-2 font-medium")
                with ui.row().classes("w-full items-center gap-2"):
                    self.input_dest_dir = ui.input("Destination Directory:", value = self.dest_dir).classes("w-[80%] overflow-x-auto whitespace-nowrap")
                    ui.button("Select Destination", on_click=lambda : self.select_destination_folder())

            # --- ACTION BUTTON ---
            with ui.row().classes("mt-4 gap-2"):
                self.Import_Files = ui.button("Import Files", on_click=self.start_import_files).classes("mt-4 bg-green-600 text-white")

        with ui.card().classes("w-full p-4 mt-4 items-center"):
            self.progress_label = ui.label("Idle...")
            self.progress = ui.circular_progress(max=100, show_value=True)
            self.cancel_btn = ui.button('Cancel Import', on_click=lambda: self.cancel())
            self.cancel_btn.visible = False
            self.cancel_backup = False

        # Inject a custom Quasar filter function via JS
        #await ui.run_javascript(f"""
        #    window.checkFitsTarget = function(files) {{
        #        // Return only files that pass — rejected ones never enter the queue
        #        return files;  // refine this with your target logic if readable client-side
        #    }};
        #""")

        self.thumbnail.visible = False
        self.remove_button.disable()
        self.populate_dwarf_filter()
        self.notify_me(None)

    def show_full_image(self, e):
        with ui.dialog() as dialog, ui.card().classes("w-full h-auto max-w-screen-xl"):
            ui.image(self.session_select_image).classes('w-full h-auto rounded-xl')
            ui.button('Close', on_click=dialog.close)

        dialog.open()

    def populate_dwarf_filter(self):
        self.dwarf_options = get_dwarf_Names(self.conn)
        names = [name for _, name in self.dwarf_options]

        # Set initial value
        initial_value = names[0] if names else None

        # If self.DwarfId is set, try to find corresponding name
        if self.DwarfId:
            match = next((name for did, name in self.dwarf_options if did == self.DwarfId), None)
            if match:
                initial_value = match

        self.dwarf_filter.set_options(names, value=initial_value)

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
            if id_ == self.BackupDriveId_Init:
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
            self.BackupDriveId = None
            self.backup_location = ""
            self.backup_astrodir = ""
            self.backup_path = ""
            self.backup_status_label.text = ""

    def on_backup_filter_change(self):
        print("on_backup_filter_change")
        selected_name = self.backup_filter.value
        for bid, name, *_ in self.backup_options:
            if name == selected_name:
                self.BackupDriveId = bid
                break
        self.update_backup_details(selected_name)

    def on_dwarf_filter_change(self):
        print("on_dwarf_filter_change")
        selected_name = self.dwarf_filter.value
        print(f"selected_name: {selected_name}")
        for did, name in self.dwarf_options:
            if name == selected_name:
                self.DwarfId = did
                break
        print(f"DwarfId: {self.DwarfId}")
        self.populate_backup_filter()

    def update_backup_details(self, selected_name):
        if selected_name in self.backup_data:
            self.BackupDriveId, self.backup_location, self.backup_astrodir = self.backup_data[selected_name]
            self.backup_path = os.path.join(self.backup_location, self.backup_StellarStudio)
            print(f"Backup Entry ID: {self.BackupDriveId}, Backup Location: {self.backup_location}, Astro Directory: {self.backup_astrodir}")
            self.check_status_backup()
        else:
            self.BackupDriveId = None
            self.backup_location = ""
            self.backup_astrodir = ""
            self.backup_path = ""
            self.backup_status_label.text = ""

        self.input_dest_dir.value = self.backup_path
        self.dest_main_dir = self.backup_path
        self.get_sessions_list()
        self.session_dropdown.set_options(self.session_lookup)

    def check_status_backup(self):
        if self.backup_path:
           if os.path.exists(self.backup_path):
               self.backup_status_label.text = "✅ Path detected."
           else:
               self.backup_status_label.text = "❌ Path not detected."

    def get_sessions_list(self):
        print("get_sessions_list")
        sessions_list_db = get_sessions_backup(self.conn, self.BackupDriveId, self.DwarfId)

        self.sessions_list = {}
        self.session_lookup = {}  # reverse lookup: id -> name
        self.session_name_lookup = {}  # reverse lookup: id -> full name
        self.session_dirname.set_value("")
        self.detail_session_name.text = ""
        self.detail_session.text = ""
        self.session_select_status_label = ""
        self.session_dirname.label = self.session_select_status_label

        for row in sessions_list_db:
            session_id = row[0]
            session_dir = row[1]
            session_fits_path = row[5]
            session_final_name = session_fits_path
            session_data = transform_session_name(session_dir)
            if session_data:
                self.sessions_list[session_data] = session_id  # shown name -> id
                self.session_lookup[session_id] = session_data  # id -> name
                if session_final_name:
                    self.session_name_lookup[session_id] = (session_dir, extract_core_name(session_final_name))  # id -> name
                else:
                    self.session_name_lookup[session_id] = (session_dir, session_data)  # id -> name

    def get_session_detail(self, row):
        label_title = ""
        label_text = ""
        thumbnail_path = None
        image_path = None

        if len(row) > 0:
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
            exp_value = parse_exposure(exp) if exp != "N/A" else 0
            gain = gainDB if gainDB is not None else "N/A"
            astro_filter = f"{filter}" if filter else "No Filter"

            info_stack = RESTACK if is_Restacked(session_dir) else TAKEN
            target = init_target[:10]
            description,_ =  get_name_object(descriptionDB)
            # Building the details string with the star icon
            label_text = f"{description}\n"
            label_text = label_text + f"{info_stack} with 🔭 {dwarf_name}{lens} 📅 {session_date} ⚙️ Exp {exp}, Gain {gain}, {astro_filter} 📊 Stacks {stacks}\n"
            label_text = label_text + f" RA: {hours_to_hms(right_ascencion)} | Dec: {deg_to_dms(declination)}\n"

            full_path = get_Backup_fullpath (self.conn, backup_path, "", file_path, self.DwarfId)
            astro_files = check_files(full_path)

            # get exposure for Restacked session
            exposure_time = format_seconds_hms(exp_value * stacks)
            if is_Restacked(session_dir):
                if "_MOSAIC_" in full_path:
                    exposure_time = format_seconds_hms(get_total_mosaic_exposure(os.path.dirname(full_path)))
                else:
                    fits_path = astro_files.get('fits')
                    if fits_path and os.path.isfile(fits_path):
                        exposure_time = format_seconds_hms(get_total_exposure(fits_path))

            label_title = f"Session: {session_dir}"
            label_text = label_text + f"{stacks} stacked shots for a total exposure time of {exposure_time}"
            thumbnail_path = astro_files.get('thumbnail')
            image_path = astro_files.get('jpg') or astro_files.get('png')
            print(thumbnail_path)
        return label_title, label_text, thumbnail_path, image_path

    async def select_destination_folder(self):
        """Open folder selection dialog."""
        if hasattr(webview, 'FileDialog'):
            folder_mode = webview.FileDialog.FOLDER
        else:
            folder_mode = webview.FOLDER_DIALOG

        if self.input_dest_dir.value:
            full_path = os.path.abspath(self.input_dest_dir.value)
            folder = await app.native.main_window.create_file_dialog(folder_mode, allow_multiple=False,directory=full_path)
        else:
            folder = await app.native.main_window.create_file_dialog(folder_mode, allow_multiple=False)
        
        if folder and not folder[0].startswith(self.dest_main_dir):
            ui.notify(f"❌ Access denied: You cannot navigate outside {self.DestinationMainDir}")
        elif folder:
            ui.notify(f"✅ Selected Folder: {folder[0]}")
            folder = os.path.normpath(folder[0])
            self.input_dest_dir.value = folder

    def sanitize_session_name(self, name: str) -> str:
        r"""
        Replace ':' with '-' and remove other invalid characters for directories.
        Forbidden chars on Windows: <>:"/\|?*
        """
        if not name:
            return ""
        # Replace colon with dash
        name = name.replace(":", "-")
        # Remove other invalid characters
        name = re.sub(r'[<>"/\\|?*]', '', name)
        return name

    def resize_input(self, component):
        ui.run_javascript(f"""
            const el = document.getElementById('{component.id}');
            if (!el) return;

            const span = document.createElement('span');
            span.style.visibility = 'hidden';
            span.style.whiteSpace = 'nowrap';
            span.innerText = el.value || el.placeholder || '';
            document.body.appendChild(span);

            let width = span.offsetWidth + 40;  // padding
            document.body.removeChild(span);

            // Clamp limits
            width = Math.min(width, 600);   // max-w-[600px]
            width = Math.max(width, 350);   // min-w-[350px]

            el.style.width = width + 'px';
        """)

    def on_session_select(self, e):
        session_id = e.value  # The selected session ID
        session_dir = None
        session_name = None

        # Find the name corresponding to this ID
        if session_id in self.session_name_lookup:
            session_dir, session_name = self.session_name_lookup[session_id]
            details_session = get_session_backup_details(self.conn, session_id)
            if len(details_session) == 1:
                print(details_session)
                self.detail_session_name.text, self.detail_session.text, thumbnail_path, image_path = self.get_session_detail(details_session[0])
                if thumbnail_path:
                    self.session_select_thumbnail = thumbnail_path
                    self.session_select_image = image_path
                    self.thumbnail.set_source(thumbnail_path)
                    self.thumbnail.visible = True
                else:
                    self.thumbnail.visible = False
            else:
                self.detail_session_name.text = ""
                self.detail_session.text = ""
                self.thumbnail.visible = False


        if session_dir and session_name:
            self.selected_session_dirname = session_dir
            print(f"Session Dir: {self.selected_session_dirname}")
            self.session_dirname.set_value(self.selected_session_dirname)
            self.resize_input(self.session_dirname)
            self.selected_session_name = self.sanitize_session_name(session_name)
            print(f"Session Name: {self.selected_session_name}")
            self.linked_data.update({
                "session_id": session_id,
                "session_full_name": session_name
            })
            self.check_exist_dir_session_name()
        else:
            self.linked_data.update({
                "session_id": None,
                "session_full_name": ""
            })

    def on_check_session_dirname (self, e):
        safe_name = self.sanitize_session_name(e.value)
        self.session_dirname.set_value(safe_name)
        self.resize_input(self.session_dirname)
        self.check_exist_dir_session_name()

    def check_exist_dir_session_name(self):
        # Check if destination path exists
        dest_dir = self.input_dest_dir.value
        session_dir = os.path.join(dest_dir, self.selected_session_dirname)
        if os.path.exists(session_dir):
            self.session_select_status_label = "⚠️ Session already exists."
        else:
            self.session_select_status_label = f"new {self.mode} session"
        self.session_dirname.label = self.session_select_status_label

    def update_remove_button(self):
        self.remove_button.enable() if self.client.storage.uploaded_files  and len(self.client.storage.uploaded_files) > 0 else self.remove_button.disable()

    async def handle_upload(self, e):
        import tempfile
        from pathlib import Path
        file = e.file
        suffix = Path(file.name).suffix.lower()        

        file_bytes = await file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
            self.track_temp_file(tmp_path)
        
        # Append to uploaded_files (keep for later resolution)
        file_type = "fits" if suffix == ".fits" or suffix == ".fit" or suffix == ".fts" else "image"

        # To DO - Add Astro Resolution - Ignore File => delete from the widget (not working yet) 
        if file_type == "fits":

            ui.run_javascript("document.body.style.cursor='wait'")
            with ui.dialog().props('persistent') as dialog_fits:

                try:
                    dialog_fits.open()

                    ui.run_javascript("document.body.style.cursor='default'")

                    # Analyse File
                    print(f"Temp: {tmp_path}")
                    print(f"Name: {file.name}")
                    await self.analyse_fits(tmp_path, file.name, dialog_fits, False)

                except Exception as ex:
                    ui.notify(f"Error reading FITS: {ex}", type='negative')
                    os.remove(tmp_path)
                    await asyncio.sleep(0.5)
                    await self._reset_and_restore(rejected_name=file.name)
                    return

        else :
            self.client.storage.uploaded_files.append({
                "path": tmp_path,
                "name": file.name,
                "type": file_type,   # 👈 mark it
                "is_temp": True,
                "ra": None,
               "dec": None,
            })
            self.update_remove_button()

        ui.notify(f"✅ Uploaded {file.name}")

    async def _reset_and_restore(self, rejected_name: str):

        # 1. Reset the uploader widget visually
        self.file_picker_fit.run_method('reset')

        # Small yield to let reset propagate to browser
        await asyncio.sleep(0.1)

        # 2. List files still accepted (in Python storage — source of truth)
        kept_files = [
            f["name"] for f in self.client.storage.uploaded_files
            if f["name"] != rejected_name
        ]

        # 3. Notify user what's still in the session
        if kept_files:
            kept_list = ", ".join(kept_files)
            ui.notify(
                f"⚠️ Upload widget was reset. Still loaded in session: {kept_list}",
                type='warning',
                timeout=8000,
                close_button=True,
            )
        else:
            ui.notify(
                "⚠️ Upload widget was reset. No files remaining in session.",
                type='warning',
            )

    def refresh_fits_file_list(self):
        """This is your source of truth display — not the Quasar widget"""
        if self.fits_file_list :
            self.fits_file_list.clear()
        with self.fits_file_list:
            if not self.client.storage.uploaded_files:
                ui.label("No files loaded").classes("text-gray-400 text-sm")
                return
            for f in self.client.storage.uploaded_files:
                meta = f.get("meta", {}) or {}
                target = meta.get("OBJECT") or f.get("target") or "Unknown target"
                with ui.row().classes("items-center gap-2 w-full"):
                    ui.icon("done").classes("text-green-500")
                    ui.label(f["name"]).classes("text-sm flex-1 truncate")
                    ui.badge(target, color="blue").classes("text-xs")
                    ui.button(
                        icon="close",
                        on_click=lambda fn=f["name"]: self.remove_single_file(fn)
                    ).props("flat round dense color=red")

###############################################
# To DO - Ignore File => delete from the widget (not working yet
###############################################
    async def remove_uploaded_file(self, filename: str):
        # Javascript to find and remove the file inside the Quasar q-uploader
        js = f"""
            const uploader = getElement('{self.file_picker_fit_id}').__vueParentComponent;
            if (uploader && uploader.files) {{
                const file = uploader.files.find(f => f.name === "{filename}");
                if (file) {{
                    uploader.removeFile(file);
                }}
            }}
        """
        ui.run_javascript(js)
###############################################

    def remove_selected_file(self):
        if not self.selected_file:
            return

        # Prevent removing the main file while others exist
        if self.selected_file == self.uploaded_fits_files[0] and len(self.uploaded_fits_files) > 1:
            ui.notify("Cannot remove main FITS while others are present!", type='warning')
            return

        try:
            # Delete the temporary file if it still exists
            file_path = self.selected_file.get("path")
            if file_path and os.path.exists(file_path):
                print(f"🧹 Deleted temp file: {file_path}")
                os.remove(file_path)
            ui.notify(f"🧹 Deleted temp file: {file_path}", type='info')
        except Exception as ex:
            ui.notify(f"Error deleting temp file: {ex}", type='warning')

        # Remove from list
        self.uploaded_fits_files.remove(self.selected_file)

        if not self.uploaded_fits_files:
            self.main_meta_info = None
            self.meta_info = None
            self.details_files.clear()

        # --- Remove from the global storage list too ---
        for f in list(self.client.storage.uploaded_files):  # make a copy to iterate safely
            if f.get("file_path") == file_path:
                try:
                    self.client.storage.uploaded_files.remove(f)
                except ValueError:
                    pass  # already removed or not found
                break

        ui.notify(f"Removed {self.selected_file['name']}", type='info')

        # Reset state
        self.selected_file = None
        self.refresh_fits_file_list_uploaded()
        self.add_button.text = "Add"

    def download_fits(self, url):
        """Run requests.get in a background thread."""
        import requests
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        return r.content

    async def add_or_remove_file(self):
        if self.selected_file:  # remove mode
            self.remove_selected_file()
            return

        url = self.link_input.value.strip()
        if not url or not url.lower().endswith((".fits", ".fit", ".fts")):
            ui.notify("Not a FITS file URL", type='warning')
            return

        ui.run_javascript("document.body.style.cursor='wait'")
        with ui.dialog().props('persistent') as dialog_fits:
            ui.notify("Downloading FITS file...", type='info')

            try:
                dialog_fits.open()

                content = await run.io_bound(self.download_fits, url)

                with tempfile.NamedTemporaryFile(delete=False, suffix=".fits") as tmp:
                    tmp.write(content)
                    tmp_path = tmp.name
                    self.track_temp_file(tmp_path)

                ui.run_javascript("document.body.style.cursor='default'")

                # Analyse File
                await self.analyse_fits(tmp_path, Path(url).name, dialog_fits)

            except Exception as ex:
               ui.notify(f"Error reading FITS: {ex}", type='negative')

    def on_fits_file_change(self, e):
        self.selected_file = None
        self.add_button.text = "Add"
        return

    def on_fits_file_selected(self, selected_name):
        if not selected_name:
            self.selected_file = None
            self.add_button.text = "Add"
            return

        self.selected_file = next((f for f in self.uploaded_fits_files if f["name"] == selected_name), None)
        self.add_button.text = "Remove"

    def refresh_fits_file_list_uploaded(self):
        if self.details_fits_files:
            self.details_fits_files.clear()
        with self.details_fits_files:
            for data_detail in self.uploaded_fits_files:
                ui.item(data_detail["name"], on_click=lambda i=data_detail["name"]: self.on_fits_file_selected(i)).props('clickable').classes('cursor-pointer')

    async def analyse_fits(self, tmp_path, name, dialog_fits, mode_upload_link = True):
        card_dialog = ui.card().style('width: 800px; max-width: none')

        print(f"Downloading OF for {tmp_path} - {name}")
        self.meta_info = read_fits_metadata(tmp_path, True)

        async def close_dialog_fits(result = False):
            if result == False:
                print(f"Deleted temp file: {tmp_path}")
                os.remove(tmp_path)
                # close dialog before call javascript in _reset_and_restore
                dialog_fits.close()
                if not mode_upload_link:
                    print(f"Rejected file: {name}")
                    await asyncio.sleep(0.5)
                    await self._reset_and_restore(rejected_name=name)
                    
            else:
                if not mode_upload_link:
                    print(f"Accepted file: {name}")
                    self._accepted_files_data[name] = tmp_path 
                dialog_fits.close()
            print(f"close_dialog_fits with result: {result}")
            return    

        async def resolve_and_refresh():
            """Call nova resolution then refresh metadata"""

            await self.resolve_file_action()
            # meta_info has been refreshed after resolution
            # self.meta_info = read_fits_metadata(tmp_path, True)
            await show_fits_dialog()  # reopen with updated info

        async def confirm():
            await close_dialog_fits(True)

            self.client.storage.uploaded_files.append({
                "path": tmp_path,
                "name": name,
                "type": "fits",
                "is_temp": True,
                "ra": None,
                "dec": None
            })
            self.uploaded_fits_files.append(self.current_file_info)
            if len(self.uploaded_fits_files) == 1:
                self.refresh_info_session()

            self.refresh_fits_file_list_uploaded()
            self.update_remove_button()

            if self.meta_info:
                ui.notify(f"✅ Added: {self.meta_info.get('OBJECT')} (RA={self.meta_info.get('RA')}, DEC={self.meta_info.get('DEC')})")
            self.link_input.value = ""

        async def show_fits_dialog():
            nonlocal card_dialog

            card_dialog.clear()

            with card_dialog:
                ui.label("🔍 Analysing Fits Image...")

                # --- CASE 1: no FITS metadata yet ---
                if not self.meta_info:
                    ui.notify("No info found in FITS file!", type='negative')

                    self.current_file_info = {
                        "path": tmp_path,
                        "name": name,
                        "type": "fits",
                        "meta": None,
                        "is_temp": True,
                    }

                    # try to extract date from filename
                    date_extract = extract_datetime_from_session_name(name)
                    date_obs = date_extract.strftime("%B %d, %Y at %I:%M:%S %p") if date_extract else "N/A"

                    ui.item(f"Session taken on {date_obs}").classes('text-indigo-600')
                    ui.item("Dwarf Target: UNRESOLVED").classes('text-green-600')

                    with ui.row():
                        ui.button("🪐 Resolve File", on_click=resolve_and_refresh)
                        ui.button('Ignore File', on_click=close_dialog_fits)

                # --- CASE 2: FITS metadata available ---
                else:
                    ui.notify(f"✅ FITS read: {self.meta_info.get('OBJECT')} (RA={self.meta_info.get('RA')}, DEC={self.meta_info.get('DEC')})")

                    self.current_file_info = {
                        "path": tmp_path,
                        "name": name,
                        "type": "fits",
                        "meta": self.meta_info,
                        "is_temp": True,
                    }

                    ui.item(f"Dwarf Target: {self.meta_info.get('OBJECT')}").classes('text-green-600')
                    ui.item(f"RA: {hours_to_hms(self.meta_info.get('RA'))} | Dec: {deg_to_dms(self.meta_info.get('DEC'))}").classes('text-purple-600')

                    lens = self.meta_info.get('CAMERA', 'N/A')
                    exposure_time = format_seconds_hms(self.meta_info.get('EXPTIME', None))
                    date_obs = (self.meta_info.get('DATE-OBS') or '')

                    if date_obs:
                        date_obs = date_obs.replace("T", " at ")
                        date_obs = re.sub(r'\.\d+$', '', date_obs)
                    else:
                        # get from file name
                        date_extract = extract_datetime_from_session_name(name)
                        date_obs = date_extract.strftime("%B %d, %Y at %I:%M:%S %p") if date_extract else "N/A"

                    with ui.row().classes('w-full gap-8 items-start'):
                        ui.item(f"Lens : {lens} | Filter: {self.meta_info.get('FILTER', 'N/A')}").classes('text-yellow-700')
                        if self.meta_info.get('TEMP', ''):
                            ui.item(f"Temp: {self.meta_info.get('TEMP','N/A')}").classes('text-sky-700')

                    ui.item(f"Session taken on {date_obs} for a total exposure time of {exposure_time}").classes('text-indigo-600')

                    with ui.row():
                        ui.button('Confirm', on_click=confirm)
                        ui.button('Ignore', on_click=close_dialog_fits)

        # first display
        await show_fits_dialog()

    def refresh_info_session(self):

        if self.meta_info:
            self.details_files.clear()
            if not self.meta_info.get('OBJECT'):
                self.meta_info['OBJECT'] = UNKNOWN

            print(f"Dwarf Target: {self.meta_info.get('OBJECT')} RA: {hours_to_hms(self.meta_info.get('RA'))} | Dec: {deg_to_dms(self.meta_info.get('DEC'))}")
            astro_name = self.meta_info.get('OBJECT')
            find_unknown = False
            if astro_name and (astro_name.lower() == UNKNOWN or astro_name.lower() == MOSAIC_UNKNOWN or astro_name.lower() == MANUAL):
                find_unknown = True
            astro_object_id, new = insert_astro_object(self.conn, self.meta_info.get('OBJECT'), find_unknown, self.meta_info.get('DEC'), self.meta_info.get('RA'))
            self.linked_data.update({ "astro_object_id": astro_object_id})
            dwarf_data = DwarfData(
                target=self.meta_info.get('OBJECT'),
                dec=self.meta_info.get('DEC'),
                ra=self.meta_info.get('RA'),
                astro_object_id = astro_object_id
            )

            with self.details_files:

                with ui.row().classes('w-full gap-8 items-start'):
                    ui.item(f"Dwarf Target: {self.meta_info.get('OBJECT')}").classes('text-green-600')
                    if self.dso_catalog:
                        ui.button("🖼️ Identify Target", on_click=lambda: self.on_identify_target_click(dwarf_data, ""))

                self.classified_label = ui.label().classes('text-gray-500').classes("m-4")
                classified_text, descriptiondb = self.update_classified_label(dwarf_data.astro_object_id, dwarf_data.target, "", True)
                if classified_text:
                    self.classified_label.set_text(classified_text)

                ui.item(f"RA: {hours_to_hms(self.meta_info.get('RA'))} | Dec: {deg_to_dms(self.meta_info.get('DEC'))}").classes('text-purple-600')

                lens = self.meta_info.get('CAMERA', 'N/A')
                exposure_time = format_seconds_hms(self.meta_info.get('EXPTIME', None))
                date_obs = (self.meta_info.get('DATE-OBS') or '')

                if date_obs:
                    # Replace "T" with " at "
                    date_obs = date_obs.replace("T", " at ")
                    # Remove milliseconds if present (e.g. .931, .12, etc.)
                    date_obs = re.sub(r'\.\d+$', '', date_obs)

                with ui.row().classes('w-full gap-8 items-start'):
                    ui.item(f"Lens : {lens} | Filter: {self.meta_info.get('FILTER', 'N/A')}").classes('text-yellow-700')

                    if self.meta_info.get('TEMP', ''):
                        ui.item(f"Temp: {self.meta_info.get('TEMP','N/A')}").classes('text-sky-700')

                ui.item(f"Session taken on {date_obs} for a total exposure time of {exposure_time}").classes('text-indigo-600')

        else:
            self.linked_data.update({ "astro_object_id": None})

            with self.details_files:
                with ui.row().classes('w-full gap-8 items-start'):
                    ui.item(f"Dwarf Target: UNRESOLVED").classes('text-green-600')
                    ui.button("🪐 Resolve Files", on_click=self.resolve_files_action)

        self.details_files.update();

    def on_identify_target_click(self, dwarf_data: DwarfData, descriptiondb):
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
        elif self.selected_object_description and self.selected_object_description != target:
            classified = self.selected_object_description.rsplit(" [")[0]

        # Update the label text or text
        if classified:
            classified_text = f"Classified as: {classified}"

        if not text_only and self.classified_label:
            self.classified_label.set_text(classified_text)

        return classified_text, descriptiondb

# ----------------- ACTIONS -----------------
    async def resolve_files_action(self):
        # --- Add files from links ---
        api_key = get_setting_text(self.conn, "NOVA_ASTRO_API")
        if not api_key:
            ui.notify("No API key found. Register a NOVA_ASTRO_API key in the database.", type="warning")
            ui.notify("Go to the Settings Tab to register one.", type="info")
            return

        # Process only FITS files
        fits_files = [f for f in self.client.storage.uploaded_files if f["type"] == "fits"]
        if not fits_files:
            ui.notify("No FITS files to resolve.", type="info")
            return

        with ui.dialog().props('persistent') as dialog:
            with ui.card().style('width: 800px; max-width: none'):
                error_label = ui.label().style('color: red')  # Empty label for future error messages
                close_button = ui.button("Close", on_click=dialog.close, color="secondary").props('visible')  # initially hidden
                ui.label(f"🔍 Resolving Image, please wait...")
                ui.spinner(size="lg")
                log = ui.log(max_lines=20).classes('w-full').style('height: 400px; overflow: hidden;')

        dialog.open()  # show the dialog

        # --- Resolving for fits files only.
        for file_info in fits_files:
            await run.io_bound(self.resolve_file, api_key, file_info, log)
            if self.meta_info:
                if file_info.get('ra'):
                   self.meta_info['RA'] = file_info['ra']
                if file_info.get('dec'):
                   self.meta_info['DEC'] = file_info['dec']
            else :
                self.meta_info = {
                    'OBJECT': "UNKNOWN",
                    'RA': file_info.get('ra',''),
                    'DEC': file_info.get('dec',''),
                }

        ui.notify("✅ Resolution completed")

        dialog.close()  # close dialog 

        self.refresh_info_session()

    async def resolve_file_action(self):
        if not self.current_file_info:
           return

        api_key = get_setting_text(self.conn, "NOVA_ASTRO_API")
        if not api_key:
            ui.notify("No API key found. Register a NOVA_ASTRO_API key in the database.", type="warning")
            ui.notify("Go to the Settings Tab to register one.", type="info")
            return

        with ui.dialog().props('persistent') as dialog:
            with ui.card().style('width: 800px; max-width: none'):
                error_label = ui.label().style('color: red')  # Empty label for future error messages
                close_button = ui.button("Close", on_click=dialog.close, color="secondary").props('visible')  # initially hidden
                ui.label(f"🔍 Resolving Image, please wait...")
                ui.spinner(size="lg")
                log = ui.log(max_lines=20).classes('w-full').style('height: 400px; overflow: hidden;')

        dialog.open()  # show the dialog

        # --- Resolving for fits files only.
        await run.io_bound(self.resolve_file, api_key, self.current_file_info, log)
        if self.meta_info:
            if self.current_file_info.get('ra'):
               self.meta_info['RA'] = self.current_file_info['ra']
            if self.current_file_info.get('dec'):
               self.meta_info['DEC'] = self.current_file_info['dec']
        else :
            self.meta_info = {
                'OBJECT': "UNKNOWN",
                'RA': self.current_file_info.get('ra',''),
                'DEC': self.current_file_info.get('dec',''),
            }
        self.current_file_info['meta'] = self.meta_info

        ui.notify("✅ Resolution completed")

        dialog.close()  # close dialog 


    async def start_import_files(self):
        self.progress.value = 0
        dest_dir = self.input_dest_dir.value
        print(f" Backup dest_dir:  {dest_dir}")
        if not dest_dir:
            self.progress_label.set_text("Select a Destination Directory.")
            return

        session_dirname = self.session_dirname.value.strip()
        if not session_dirname:
            ui.notify("Please provide or select a session name.", type="warning")
            return

        session_dir = os.path.join(dest_dir, session_dirname)
        print(f" Session dest_dir:  {session_dir}")

        self.cancel_btn.visible = True
        self.Import_Files.visible = False

        # Check if destination path exists
        if os.path.exists(session_dir):
            await self.confirm_overwrite(session_dir)
        else:
            await self.execute_import_files(session_dir)

    async def confirm_overwrite(self, dest_path):

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
            await self.execute_import_files(dest_path)
        else:
            self.progress_label.set_text("Backup canceled.")

    def error_execute(self, message, type):
        ui.notify(message, type=type)
        self.cancel_btn.visible = False
        self.Import_Files.visible =  True
        return

    async def execute_import_files(self, dest_path):
        try:
            os.makedirs(dest_path, exist_ok=True)
        except FileNotFoundError:
            self.error_execute(f"❌ Destination path not found: {dest_path}", type="error")
            return
        except PermissionError:
            self.error_execute(f"❌ No permission to create: {dest_path}", type="error")
            return
        except OSError as e:
            self.error_execute(f"❌ OS error while creating {dest_path}: {e}", type="error")
            return

        list_files = self.client.storage.uploaded_files
        total_files = 0
        if list_files:
            total_files = len(list_files)

        if total_files == 0:
            self.error_execute("No files to copy.", type="info")
            return
        else:
            self.progress_label.set_text(f"Starting copying {total_files} files...")
        ui.notify("Starting...")

        result = await self.import_files(dest_path, self.progress, self.cancel_btn)

        if result:
            self.progress_label.set_text(f"End of Backup")
            ui.notify(f"✅ All files saved in: {dest_path}", type="positive")

        else:
            self.progress_label.set_text(f"Backup interrupted!")

    async def import_files(self, dest_path, progress_bar, cancel_btn):
        """
        Copy all uploaded files (local or downloaded from links) to destination folder.
        Uses self.client.storage.uploaded_files, which contains dicts:
        { "path", "name", "type", "is_temp", "ra", "dec" }.
        """
        self.cancel_backup = False
        verified_files = 0
        total_files = len(self.client.storage.uploaded_files)
        result = False

        if total_files == 0:
            self.error_execute("No files to backup.", type="info")
            return False

        try:
            for i, file_info in enumerate(self.client.storage.uploaded_files, start=1):
                if self.cancel_backup:
                    ui.notify("❌ Backup cancelled by user.", type="warning")
                    break

                try:
                    src_path = file_info.get("path")
                    filename = file_info.get("name")
                    ext = os.path.splitext(filename)[1].lower()

                    # replace file name:
                    # jpeg -> stacked.jpg
                    # png -> self.selected_session_name.png
                    # fits -> self.selected_session_name.fits
                    # Compute the new filename depending on the extension
                    if ext == ".jpg":
                        new_filename = "stacked.jpg"

                    elif ext == ".png":
                        new_filename = f"stacked-16_{self.selected_session_name}.png"

                    elif ext == ".fits":
                        new_filename = f"stacked-16_{self.selected_session_name}.fits"

                    else:
                        # Keep original name for unknown types
                        new_filename = filename

                    # Avoid overwriting existing files
                    base_name, file_ext = os.path.splitext(new_filename)
                    dest_file_path = os.path.join(dest_path, new_filename)
                    counter = 1
                    while os.path.exists(dest_file_path):
                        dest_file_path = os.path.join(dest_path, f"{base_name}_{counter}{file_ext}")
                        counter += 1

                    # Copy the file to destination
                    shutil.copy2(src_path, dest_file_path)
                    
                    #thumbnail for first jpeg
                    if file_ext.lower() == ".jpg" and counter == 1:
                        thumbnail_path = dest_file_path.replace("stacked.jpg", "stacked_thumbnail.jpg")
                        create_thumbnail (dest_file_path , thumbnail_path)

                    verified_files += 1
                    progress = round((i / total_files) * 100)
                    progress_bar.value = progress
                    ui.notify(f"✅ Copied: {filename}")

                except Exception as e:
                    ui.notify(f"⚠️ Failed to copy {filename}: {e}", type="warning")

            # --- Final result ---
            if not self.cancel_backup and verified_files == total_files:
                result = True
                ui.notify("✅ Backup completed successfully!", type="positive")

                # add to database - TO DO
                #insert_ManualSessionEntry(self.conn ,  BackupDriveId, DwarfId, astro_object_id, backup_entry_id, session_dt_str, session_dir, astro_group_id)

            elif not self.cancel_backup:
                ui.notify("⚠️ Backup incomplete due to failures.", type="warning")

        except Exception as e:
            ui.notify(f"❌ Unexpected error during backup: {e}", type="error")

        finally:
            progress_bar.value = 100 if result else progress_bar.value
            cancel_btn.visible = False
            self.Import_Files.visible = True
            # Cleanup temp files
            self.cleanup_temp_files()

        return result

    def track_temp_file(self, file_path):
        """Add a temp file to the cleanup list."""
        if not hasattr(self, "_temp_files_to_cleanup"):
            self._temp_files_to_cleanup = set()
        self._temp_files_to_cleanup.add(file_path)

    def cleanup_temp_files(self):
        for file_info in self.client.storage.uploaded_files:
            if file_info.get("is_temp") and os.path.exists(file_info.get("path")):
                try:
                    print(f"Remove temp file {file_info.get('path')}")
                    os.remove(file_info.get("path"))
                except Exception as e:
                    print(f"Failed to remove temp file {file_info.get('path')}: {e}")

        if self.file_picker_jpg:
            self.file_picker_jpg.reset()
        if self.file_picker_png:
            self.file_picker_png.reset()
        if self.file_picker_fit:
            self.file_picker_fit.reset()

        self.client.storage.uploaded_files.clear();
        self.uploaded_fits_files = []
        self.refresh_fits_file_list_uploaded()
        self.selected_file = None
        self.main_meta_info = None
        self.meta_info = None
        self.details_files.clear()
        
        if self.remove_button:
            self.update_remove_button()

    @ui.refreshable
    def notify_me(self, msg: str | None) -> None:
        if msg:
            ui.notify(msg)

    def cancel(self):
        self.cancel_backup = True

