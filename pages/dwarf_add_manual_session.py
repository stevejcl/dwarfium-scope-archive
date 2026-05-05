from components.i18n import t
import webview
from nicegui import ui, app, Client
from components.session_notes import session_notes_widget

import os
import requests
import traceback
import asyncio
from datetime import datetime

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
    show_short_date_session, get_total_exposure, get_total_mosaic_exposure, parse_exposure, get_Backup_fullpath, check_files, create_thumbnail, get_session_detail,compute_md5, get_session_file_ref, safe_copy2
)
from api.dwarf_backup_db import DB_NAME, connect_db, close_db
from api.dwarf_backup_db_api import get_dwarf_Names, get_dwarf_detail, get_backupDrive_list_dwarfId, insert_astro_object, get_astro_object_description, get_sessions_backup, get_session_backup_details, get_setting_text, insert_ManualSession, insert_ManualSessionEntry, get_ManualSession_by_entry_id, get_or_create_ManualSessionDrive, update_manual_session
from api.astrometry_resolver import auto_resolve, get_fits_center_coordinates

from components.win_log import WinLog
from components.astro_object_associate import DwarfData, show_unknown_target_dialog

from api.dwarf_backup_fct import CATALOG_FILE, SKY_CATALOG_FILE, UNKNOWN, MOSAIC_UNKNOWN, MANUAL, TAKEN, RESTACK

client_apps = {}

@ui.page('/AddManualSession/')
async def manual_session_page(client: Client, DwarfId:int = None, session:str = None, BackupDriveId:int = None, ManualEntryId:int = None, back_url:str = None):

    menu(t("page_manual_add") if not ManualEntryId else t("page_manual_exit"))
    await ui.context.client.connected(timeout=10.0)
    # Launch the GUI - ManualEntryId triggers edit mode for an existing session
    ui.context.manual_session_app = AddManualSession(client, DB_NAME, DwarfId=DwarfId, Session=session, BackupDriveId=BackupDriveId, ManualEntryId=ManualEntryId, BackUrl=back_url)
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
    def __init__(self, client: Client, database, DwarfId=None, Session=None, BackupDriveId=None, ManualEntryId=None, BackUrl=None):
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
        self.selected_session_tag = ""
        self.selected_session_name = None
        self.session_select_status_label = ""
        self.session_select_tag_label = ""
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
            "astro_object_id": "",
            "session_ra": None,   # RA from the original linked session (fallback)
            "session_dec": None,  # DEC from the original linked session (fallback)
        }

        self.links = []
        self.main_meta_info = None
        self.meta_info = None

        # --- Edit mode ---
        # When ManualEntryId is set the page opens an existing ManualSession for update.
        # The existing files on disk are listed so the user can delete or replace them
        # before re-importing.
        import urllib.parse as _up
        self.BackUrl = _up.unquote(BackUrl) if BackUrl else BackUrl
        self.ManualEntryId = ManualEntryId
        self.edit_mode = ManualEntryId is not None
        self.existing_session_row = None   # row from get_ManualSession_by_entry_id
        self.existing_files_on_disk = []   # list of {path, name, ext} already in session_dir

        self.build_ui()

    # =========================================================================
    # Edit mode — load an existing ManualSession for update
    # =========================================================================

    def load_existing_session(self):
        """
        Called once after build_ui() when ManualEntryId is set.
        Fetches the existing ManualSession row, pre-fills all form fields, and
        populates the existing-files panel so the user can delete / replace files
        before re-importing.
        """
        rows = get_ManualSession_by_entry_id(self.conn, self.ManualEntryId)
        if not rows:
            ui.notify(t("session_not_found_db"), type="warning")
            return

        row = rows[0]
        self.existing_session_row = row
        manual_session_id = row[0]

        # --- Show notes widget in edit mode ---
        if hasattr(self, '_notes_container'):
            self._notes_container.clear()
            with self._notes_container:
                session_notes_widget(self.conn, manual_session_id=manual_session_id)

        # --- Unpack the row (same column layout as get_ObjectSelect_manual) ---
        session_name    = row[1]
        session_tag     = row[2]  # sub dir of the session or empty
        session_type    = row[3] or self.mode_stellar
        description     = row[6]
        dec             = row[7]
        ra              = row[8]
        exp_time        = row[9]
        ircut_filter    = row[10]
        max_temp        = row[11]
        session_dir     = row[16]   # physical folder already on backup drive
        astro_object_id = row[18]
        astro_display   = row[20]
        backup_drive_id = row[21]
        dwarf_id        = row[22]
        session_id      = row[23]

        # --- Pre-fill session name and tag inputs ---
        print(f"session name input: {session_name}")
        print(f"session dir input: {session_dir}")
        print(f"session tag input: {session_tag}")

        # In edit mode the session_dirname shows the base folder only;
        # the tag sub-folder is shown separately in the tag input.
        base_folder = os.path.basename(os.path.dirname(session_dir)) if (session_tag and session_dir) else (os.path.basename(session_dir) if session_dir else session_name)
        self.selected_session_name    = base_folder
        self.selected_session_dirname = base_folder
        self.session_dirname.set_value(base_folder)
        print(f"selected_session_dirname : {self.selected_session_dirname}")

        # Pre-fill the tag and trigger directory validation
        safe_tag = session_tag or ""
        self.selected_session_tag = safe_tag
        self.session_tag.set_value(safe_tag)

        # --- Pre-fill destination directory ---
        # session_dir is already the full effective path (base/tag or just base).
        # The dest_dir input should point to the parent of the base session folder,
        # not the parent of the tag sub-folder.
        if session_dir:
            if safe_tag:
                # session_dir = …/base/tag  → dest = …  (two levels up)
                dest_parent = os.path.dirname(os.path.dirname(session_dir))
            else:
                # session_dir = …/base      → dest = …  (one level up)
                dest_parent = os.path.dirname(session_dir)
            if dest_parent:
                self.input_dest_dir.value = dest_parent

        # --- Set mode toggle to match the stored session type ---
        if session_type in (self.mode_stellar, self.mode_manual):
            self.mode = session_type
            self.mode_toggle.set_value(session_type)

        # --- Reconstruct main_meta_info from the stored ManualSession columns ---
        self.main_meta_info = {
            'RA':      ra,
            'DEC':     dec,
            'OBJECT':  None,    # filled below from AstroObject
            'EXPTIME': float(exp_time) if exp_time else None,
            'FILTER':  ircut_filter,
            'TEMP':    max_temp,
        }

        # Fill OBJECT from the linked AstroObject name
        if astro_display:
            from api.dwarf_backup_fct import get_name_object as _gno
            obj_name, _ = _gno(astro_display)
            self.main_meta_info['OBJECT'] = obj_name

        self.meta_info = dict(self.main_meta_info)

        # Restore linked_data so the DB insert later uses the correct astro_object_id
        self.linked_data.update({
            "astro_object_id": astro_object_id,
            "session_id":      session_id,
            "session_full_name": session_name,
        })

        # select the session
        self.session_dropdown.value  = session_id

        # Show the session metadata panel
        self.refresh_info_session()

        # --- Populate the existing-files panel ---
        self._load_existing_files_panel(session_dir)

        ui.notify(t("edit_mode_loaded", name=session_name), type="info")

    def _load_existing_files_panel(self, session_dir: str):
        """
        Scan the session folder already on disk and display each file with a
        delete button, so the user can selectively remove files before uploading
        replacements.
        """
        self.existing_files_on_disk = []
        self.existing_files_list.clear()

        if not session_dir or not os.path.exists(session_dir):
            # Folder not accessible on this machine — hide the panel silently
            self.existing_files_card.visible = False
            return

        # Collect known image / FITS files in the session folder
        known_extensions = {'.jpg', '.jpeg', '.png', '.fits', '.fit', '.fts'}
        try:
            entries = sorted(os.listdir(session_dir))
        except PermissionError:
            self.existing_files_card.visible = False
            return

        for filename in entries:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in known_extensions:
                continue
            full_path = os.path.join(session_dir, filename)
            file_size = os.path.getsize(full_path) if os.path.exists(full_path) else 0
            self.existing_files_on_disk.append({
                "path": full_path,
                "name": filename,
                "ext":  ext,
                "size": file_size,
            })

        if not self.existing_files_on_disk:
            self.existing_files_card.visible = False
            return

        self.existing_files_card.visible = True
        self._render_existing_files_panel()

    @ui.refreshable
    def _render_existing_files_panel(self):
        """
        Render the list of existing files with individual delete buttons.
        Decorated with @ui.refreshable so it can be rebuilt after a deletion
        without rebuilding the whole page.
        """
        self.existing_files_list.clear()
        with self.existing_files_list:
            if not self.existing_files_on_disk:
                ui.item("No files remaining in session folder.").classes("text-gray-400 text-sm")
                return

            for file_info in list(self.existing_files_on_disk):
                size_kb = file_info["size"] // 1024
                with ui.item().classes("w-full"):
                    with ui.row().classes("items-center gap-2 w-full flex-nowrap"):
                        # File type icon
                        ext = file_info["ext"]
                        icon = "📷" if ext in ('.jpg', '.jpeg') else ("🖼️" if ext == '.png' else "🔭")
                        ui.label(f"{icon} {file_info['name']}").classes("flex-1 text-sm truncate")
                        ui.label(f"{size_kb} KB").classes("text-xs text-gray-400 shrink-0")
                        ui.button(
                            icon="delete",
                            on_click=lambda fi=file_info: self._delete_existing_file(fi),
                        ).props("flat round dense color=red").classes("shrink-0")

    def _delete_existing_file(self, file_info: dict):
        """
        Delete a single file from the session folder on disk and remove it from
        the tracking list, then refresh the panel.
        Also clears main_meta_info if the deleted file was the primary FITS source
        (i.e. its session_name is referenced in existing_session_row).
        """
        path = file_info.get("path", "")
        name = file_info.get("name", "")

        try:
            if os.path.exists(path):
                os.remove(path)
                ui.notify(t("item_deleted", name=name), type="positive")
            else:
                ui.notify(t("file_not_found_disk", name=name), type="warning")
        except Exception as e:
            ui.notify(t("file_delete_error", name=name, error=e), type="negative")
            return

        # Remove from tracking list
        self.existing_files_on_disk = [
            f for f in self.existing_files_on_disk if f["path"] != path
        ]

        # If the deleted file was the stacked FITS that feeds main_meta_info,
        # clear the metadata panel so the user knows they need to upload a new one.
        if self.existing_session_row:
            stored_fits = self.existing_session_row[14]  # stacked_fits_path
            if stored_fits and os.path.normpath(stored_fits) == os.path.normpath(path):
                self.main_meta_info = None
                self.meta_info = None
                self.details_files.clear()
                ui.notify(t("primary_fits_deleted"), type="info")

        # Refresh the panel
        self._render_existing_files_panel.refresh()

        # Hide the card entirely when no files remain
        if not self.existing_files_on_disk:
            self.existing_files_card.visible = False

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

        # If still no coordinates — propose the original session's RA/DEC as fallback
        if ra is None or dec is None:
            fallback_ra  = self.linked_data.get("session_ra")
            fallback_dec = self.linked_data.get("session_dec")
            if fallback_ra is not None and fallback_dec is not None:
                print(f"[ManualSession] No coordinates in FITS — proposing fallback from original session: RA={fallback_ra} DEC={fallback_dec}")
                ra  = fallback_ra
                dec = fallback_dec
                file_info['ra_from_fallback'] = True  # flag so UI can inform the user
            else:
                print("[ManualSession] No coordinates in FITS and no original session selected — coordinates will be empty.")

        file_info['ra'] = ra
        file_info['dec'] = dec

    def build_ui(self):
        self.conn = connect_db(self.database)
        nbcol = 3 if self.BackUrl else 1

        # Load the preprocessed catalog once at app start
        preprocess_dso_catalog_json(CATALOG_FILE, SKY_CATALOG_FILE)

        if os.path.exists(SKY_CATALOG_FILE): 
            with open(SKY_CATALOG_FILE  , "r", encoding="utf-8") as f:
                self.dso_catalog = json.load(f)

        with ui.card().classes("w-full p-4 mt-4 items-center") as self.main_ui:

            with ui.grid(columns=nbcol).classes("items-center"):
                if self.BackUrl:
                    # Back button — shown when navigating from ManualExplore in edit mode
                    if self.BackUrl:
                        import urllib.parse
                        decoded_back = urllib.parse.unquote(self.BackUrl) if self.BackUrl else "/"
                        ui.button(
                            "🔙 Back",
                            on_click=lambda: ui.navigate.to(decoded_back),
                        ).style('width: 160px').classes('mb-2')

                    self.mode_toggle = ui.toggle([self.mode_stellar, self.mode_manual], value=self.mode_stellar, on_change=self.switch_mode)

            with ui.grid(columns=2):
                with ui.column():
                    ui.label(t("select_dwarf")).classes("text-lg font-semibold")
                    self.dwarf_filter = ui.select(options=[], on_change=self.on_dwarf_filter_change).props('outlined')
                    self.usb_status_label = ui.label("").classes('pb-2')

                with ui.column():
                    ui.label(t("backup_drive")).classes("text-lg font-semibold")
                    self.backup_filter = ui.select(options=[], on_change=self.on_backup_filter_change).props('outlined')
                    self.backup_status_label = ui.label("").classes('pb-2')

            with ui.card().classes("w-full p-4").style("max-width: 2600px; margin: auto"):
                ui.label(f'Backup {self.mode} Files')

                # --- SESSION SELECTION ---
                with ui.row().classes("items-center mb-4"):
                    ui.label(t("select_backup_session"))
                    self.session_dropdown = ui.select(options=[], on_change=self.on_session_select).classes("w-auto min-w-[250px]")
                    ui.label(t("session_name"))
                    self.session_dirname = ui.input(self.session_select_status_label, value="", placeholder="Enter new session name", on_change=self.on_check_session_dirname).classes("min-w-[550px] w-auto overflow-x-auto whitespace-nowrap")
                    ui.label(t("tag")).tooltip("Tag is Optional. The files will be saved in a sub-folder: session_name / tag")
                    self.session_tag = (
                        ui.input(self.session_select_tag_label, value="", placeholder="optional — e.g. v2, Siril",
                                 on_change=self.on_check_session_tag)
                        .classes("min-w-[160px] w-auto overflow-x-auto whitespace-nowrap")
                    )
                    with ui.row().classes("items-center"):
                        ui.label("Help: " \
                            "Tag is Optional. Leave empty for a single version.\n" \
                            "Use a tag (e.g. 'v2', 'Siril') to keep multiple " \
                            "imports of the same session side by side.\n" \
                        ).style('color: grey')

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
                        ui.label(t("select_local_jpg")).classes("mt-2 font-medium")
                        self.file_picker_jpg = ui.upload(
                            label="Upload JPG",
                            auto_upload=True,
                            multiple=True,
                            on_upload=self.handle_upload,
                        ).props('accept="image/jpeg"').classes("mb-4")

                    with ui.column().classes("items-center justify-center text-center w-full"):
                        ui.label(t("select_local_png")).classes("mt-2 font-medium")
                        self.file_picker_png = ui.upload(
                            label="Upload PNG",
                            auto_upload=True,
                            multiple=True,
                            on_upload=self.handle_upload,
                        ).props('accept="image/png"').classes("mb-4")

                    with ui.column().classes("items-center justify-center text-center w-full"):
                        with ui.row().classes("items-center gap-1"):
                            ui.label(t("select_local_fits")).classes("mt-2 font-medium")
                            ui.icon("info").classes("text-gray-400 cursor-help mt-2").tooltip(
                                "First FITS → renamed to stacked-16_{session}.fits\n"
                                "Additional FITS → original filename kept\n"
                                "(e.g. Cave_Nebula_Starless.fits stays as-is)"
                            )
                        self.file_picker_fit = ui.upload(
                            label="Upload FITS",
                            auto_upload=True,
                            multiple=True,
                            on_upload=self.handle_upload,
                        ).props('accept=".fit,.fits,.fts"').classes("mb-4")
                self.file_picker_fit_id = self.file_picker_fit.id

                self.remove_button = ui.button(t("remove_all_files"), on_click=self.cleanup_temp_files).props("color=red")


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
                    ).props('clearable').classes("flex-1")
                    self.url_suffix_select = ui.select(
                        options=["", "Auto", "Denoise", "Starless"],
                        value="",
                        label="Type",
                    ).props('stack-label outlined').classes('w-32').tooltip(
                        "Suffix added to the filename for Stellar Studio files. "
                        "Leave empty for the first/main stack."
                    )
                    self.add_button = ui.button(t("add"), on_click=self.add_or_remove_file)

                with ui.card().tight().classes('w-full'):
                    # List on the side
                    ui.label(t("fits_files_list")).classes("ml-2 mt-2 font-medium")
                    self.details_fits_files = ui.list().classes('w-full h-50 overflow-y-auto')

                # --- EXISTING FILES (edit mode only) ---
                # This card is always created so the reference is valid, but it is hidden
                # in add mode and populated by load_existing_session() in edit mode.
                with ui.card().tight().classes('w-full') as self.existing_files_card:
                    ui.label(t("files_already_session")).classes("ml-2 mt-2 font-medium text-orange-600")
                    self.existing_files_list = ui.list().classes('w-full overflow-y-auto')
                self.existing_files_card.visible = False

                with ui.card().tight().classes('w-full'):
                    ui.label(t("main_file_info")).classes("ml-2 mt-2 mb-2 font-medium")
                    self.details_files = ui.list().classes('w-full h-50 overflow-y-auto')
 
                # --- Observations ---
                with ui.expansion("📋 Observations (optionnel)", icon="notes").classes("w-full mt-2"):
                    self._notes_manual_session_id = None  # filled after save
                    self._notes_container = ui.column().classes("w-full")
                    with self._notes_container:
                        ui.label("Les observations pourront être ajoutées après l'import de la session.") \
                            .classes("text-sm text-gray-400 italic")

                self.DestinationDirectory = ui.label(t("backup_destination")).classes("mt-2 font-medium")
                with ui.row().classes("w-full items-center gap-2"):
                    self.input_dest_dir = ui.input(t("destination_dir"), value = self.dest_dir).classes("w-[80%] overflow-x-auto whitespace-nowrap")
                    ui.button(t("select_destination"), on_click=lambda : self.select_destination_folder())

            # --- ACTION BUTTONS ---
            with ui.row().classes("mt-4 gap-4 items-center"):
                self.Import_Files = ui.button(
                    "Import Files" if not self.edit_mode else "Update Session Files",
                    on_click=self.start_import_files,
                ).classes("bg-green-600 text-white")
                self.view_session_button = ui.button(
                    "🔭 View Session in Explore",
                    on_click=lambda: None,
                ).props("color=teal")
                self.view_session_button.visible = False

        with ui.card().classes("w-full p-4 mt-4 items-center"):
            self.progress_label = ui.label(t("idle"))
            self.progress = ui.circular_progress(max=100, show_value=True)
            self.cancel_btn = ui.button(t("cancel_import"), on_click=lambda: self.cancel())
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

        self.set_mode_UI()
        if self.edit_mode:
            self.load_existing_session()

    def show_full_image(self, e):
        with ui.dialog() as dialog, ui.card().classes("w-full h-auto max-w-screen-xl"):
            ui.image(self.session_select_image).classes('w-full h-auto object-contain rounded-xl')
            ui.button(t("close"), on_click=dialog.close)

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
        self.session_tag.set_value("")
        self.selected_session_tag = ""
        self.detail_session_name.text = ""
        self.detail_session.text = ""
        self.session_select_status_label = ""
        self.session_dirname.label = self.session_select_status_label
        self.session_select_tag_label = ""
        self.session_tag.label = self.session_select_tag_label

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
            ui.notify(t("access_denied_outside", path=self.DestinationMainDir), type="negative")
        elif folder:
            ui.notify(t("folder_selected", path=folder[0]), type="positive")
            folder = os.path.normpath(folder[0])
            self.input_dest_dir.value = folder

    def sanitize_session_name(self, name: str) -> str:
        r"""
        Replace ':' with '-' and remove other invalid characters for directories.
        Forbidden chars on Windows: <>:"/\|?*
        Also strip known file extensions that should never appear in a session name.
        """
        if not name:
            return ""
        # Strip known file extensions (e.g. from Stellar Studio zip exports)
        for ext in (".zip", ".fits", ".fit", ".fts", ".jpg", ".jpeg", ".png"):
            if name.lower().endswith(ext):
                name = name[:-len(ext)]
                break
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
                self.detail_session_name.text, self.detail_session.text, thumbnail_path, image_path = get_session_detail(self.conn, details_session[0], self.DwarfId)
                if thumbnail_path:
                    self.session_select_thumbnail = thumbnail_path
                    self.session_select_image = image_path
                    self.thumbnail.set_source(thumbnail_path)
                    self.thumbnail.visible = True
                else:
                    self.thumbnail.visible = False
                # Store original session coordinates as fallback for FITS without RA/DEC
                self.linked_data["session_ra"]  = details_session[0][15]  # DwarfData.ra
                self.linked_data["session_dec"] = details_session[0][14]  # DwarfData.dec
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

    def on_check_session_dirname(self, e):
        """Called when the user edits the session name field."""
        safe_name = self.sanitize_session_name(e.value)
        self.session_dirname.set_value(safe_name)
        self.resize_input(self.session_dirname)
        self.check_exist_dir_session_name()

    def on_check_session_tag(self, e):
        """Called when the user edits the tag field.
        Sanitizes the value and re-evaluates the target directory status.
        """
        safe_tag = self.sanitize_session_name(e.value)
        # Only update the widget if we actually changed something, to avoid
        # moving the cursor while the user types
        if safe_tag != e.value:
            self.session_tag.set_value(safe_tag)
        self.selected_session_tag = safe_tag
        self.check_exist_dir_session_name()

    def _get_effective_dest_path(self, dest_dir: str = None) -> str:
        """
        Compute the effective destination path taking the optional tag into account.

        Without tag:  <dest_dir>/<session_dirname>
        With tag:     <dest_dir>/<session_dirname>/<tag>

        This is the single source of truth used by both check_exist_dir_session_name
        and start_import_files so the two are always in sync.
        """
        base = dest_dir or self.input_dest_dir.value
        dirname = (self.session_dirname.value or "").strip()
        tag     = (self.session_tag.value     or "").strip()
        if not dirname:
            return base
        path = os.path.join(base, dirname)
        if tag:
            path = os.path.join(path, tag)
        return path

    def check_exist_dir_session_name(self):
        """Update the session name label to reflect whether the target directory
        already exists, guiding the user on whether to add / change the tag.
        """
        dirname = (self.session_dirname.value or "").strip()
        if not dirname:
            self.session_dirname.label = ""
            return

        tag     = (self.session_tag.value or "").strip()
        effective = self._get_effective_dest_path()

        if os.path.exists(effective):
            if tag:
                # Directory with this exact tag exists — warn and ask for a new tag
                self.session_dirname.label = f"⚠️ '{dirname}/{tag}' already exists — choose a different tag or files will be added to the existing one"
                self.session_tag.label = "Change tag"
            else:
                # No tag, base directory already used — suggest using a tag
                self.session_dirname.label = "⚠️ Already exists — add a Tag to create a new version or files will be added to the existing one"
                self.session_tag.label ="Add a tag"
        else:
            self.session_tag.label = ""
            if tag:
                self.session_dirname.label = f"new {self.mode} session (tag: {tag})"
            else:
                self.session_dirname.label = f"new {self.mode} session"

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
        file_type = "fits" if suffix in (".fits", ".fit", ".fts") else "image"

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
                    ui.notify(t("fits_read_error", error=ex), type="negative")
                    os.remove(tmp_path)
                    dialog_fits.close()
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

        ui.notify(t("file_upload_ok", name=file.name), type="positive")

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
                ui.label(t("no_files_loaded")).classes("text-gray-400 text-sm")
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
            ui.notify(t("notif_cannot_remove_fits"), type='warning')
            return

        try:
            # Delete the temporary file if it still exists
            file_path = self.selected_file.get("path")
            if file_path and os.path.exists(file_path):
                print(f"🧹 Deleted temp file: {file_path}")
                os.remove(file_path)
            ui.notify(t("temp_file_deleted", path=file_path), type="info")
        except Exception as ex:
            ui.notify(t("temp_file_delete_error", error=ex), type="warning")

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
            ui.notify(t("not_fits_url"), type='warning')
            return

        ui.run_javascript("document.body.style.cursor='wait'")
        with ui.dialog().props('persistent') as dialog_fits:
            ui.label(t("downloading_fits"))
            try:
                dialog_fits.open()

                content = await run.io_bound(self.download_fits, url)

                with tempfile.NamedTemporaryFile(delete=False, suffix=".fits") as tmp:
                    tmp.write(content)
                    tmp_path = tmp.name
                    self.track_temp_file(tmp_path)

                ui.run_javascript("document.body.style.cursor='default'")

                # Analyse File — use suffix from selector to build a meaningful name
                _suffix = self.url_suffix_select.value.strip() if self.url_suffix_select.value else ""
                _url_name = Path(url).name  # original (usually meaningless)
                await self.analyse_fits(tmp_path, _url_name, dialog_fits, url_suffix=_suffix)

            except Exception as ex:
                # On error: restore cursor, close dialog, show message
                ui.run_javascript("document.body.style.cursor='default'")
                try:
                    dialog_fits.close()
                except Exception:
                    pass
                import requests as _req
                if isinstance(ex, _req.HTTPError) and ex.response is not None:
                    status = ex.response.status_code
                    if status == 403:
                        msg = "❌ Access forbidden (403) — the URL requires authentication or is not public."
                    elif status == 404:
                        msg = "❌ File not found (404) — check the URL."
                    else:
                        msg = f"❌ HTTP error {status}: {ex}"
                else:
                    msg = f"❌ Download failed: {ex}"
                ui.notify(msg, type='negative', timeout=8000)

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

    async def analyse_fits(self, tmp_path, name, dialog_fits, mode_upload_link=True, url_suffix=""):
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
                "dec": None,
                "url_suffix": url_suffix,
            })
            self.uploaded_fits_files.append(self.current_file_info)
            if len(self.uploaded_fits_files) == 1:
                # Snapshot the metadata of the first accepted FITS as the session master record
                self.main_meta_info = dict(self.meta_info) if self.meta_info else None
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
                ui.label(t("analyzing_fits"))

                # --- CASE 1: no FITS metadata yet ---
                if not self.meta_info:
                    ui.notify(t("no_info_fits"), type='negative')

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
                        ui.button(t("resolve_file"), on_click=resolve_and_refresh)
                        ui.button(t("ignore_file"), on_click=close_dialog_fits)

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
                        # Offer resolution when RA or DEC is missing from the FITS header
                        if not self.meta_info.get('RA') or not self.meta_info.get('DEC'):
                            ui.button(t("resolve_file"), on_click=resolve_and_refresh)
                        ui.button(t("confirm"), on_click=confirm)
                        ui.button(t("ignore"), on_click=close_dialog_fits)

        # first display
        await show_fits_dialog()

    def refresh_info_session(self):

        if self.meta_info:
            self.details_files.clear()
            if not self.meta_info.get('OBJECT'):
                self.meta_info['OBJECT'] = UNKNOWN
            # Keep main_meta_info in sync: it always reflects the first/primary FITS metadata.
            # If it was never set (e.g. after a resolution update), capture it now.
            if self.main_meta_info is None:
                self.main_meta_info = dict(self.meta_info)
            else:
                # Propagate any coordinate update back to main_meta_info (post-resolution)
                for key in ('RA', 'DEC', 'OBJECT', 'FILTER', 'EXPTIME', 'TEMP', 'DATE-OBS', 'CAMERA'):
                    if key in self.meta_info:
                        self.main_meta_info[key] = self.meta_info[key]

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
                        ui.button(t("identify_target"), on_click=lambda: self.on_identify_target_click(dwarf_data, ""))

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
                    ui.button(t("resolve_files"), on_click=self.resolve_files_action)

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
            ui.notify(t("nova_no_key"), type="warning")
            ui.notify(t("nova_go_settings"), type="info")
            # Still apply session fallback coordinates if available
            fits_files = [f for f in self.client.storage.uploaded_files if f["type"] == "fits"]
            for file_info in fits_files:
                if not file_info.get('ra') or not file_info.get('dec'):
                    fallback_ra  = self.linked_data.get("session_ra")
                    fallback_dec = self.linked_data.get("session_dec")
                    if fallback_ra is not None and fallback_dec is not None:
                        file_info['ra'] = fallback_ra
                        file_info['dec'] = fallback_dec
                        file_info['ra_from_fallback'] = True
                        if self.meta_info:
                            self.meta_info['RA'] = fallback_ra
                            self.meta_info['DEC'] = fallback_dec
            if any(f.get('ra_from_fallback') for f in fits_files):
                ui.notify(
                    "⚠️ Coordinates from the original linked session were used as fallback.",
                    type="warning", timeout=8000,
                )
            elif fits_files:
                ui.notify(t("no_coords"), type="negative", timeout=8000)
            self.refresh_info_session()
            return

        # Process only FITS files
        fits_files = [f for f in self.client.storage.uploaded_files if f["type"] == "fits"]
        if not fits_files:
            ui.notify(t("no_fits_resolve"), type="info")
            return

        with ui.dialog().props('persistent') as dialog:
            with ui.card().style('width: 800px; max-width: none'):
                error_label = ui.label().style('color: red')  # Empty label for future error messages
                close_button = ui.button(t("close"), on_click=dialog.close, color="secondary").props('visible')  # initially hidden
                ui.label(f"🔍 Resolving Image, please wait...")
                spiner = ui.spinner(size="lg")
                log = ui.log(max_lines=20).classes('w-full').style('height: 400px; overflow: hidden;')

        dialog.open()  # show the dialog
        spinner.set_visibility(True)

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

        spinner.set_visibility(False)

        # Check if any file used the fallback coordinates from the original session
        fallback_used = any(f.get('ra_from_fallback') for f in fits_files)
        if fallback_used:
            ui.notify(
                "⚠️ No coordinates found in the FITS file — "
                "coordinates from the original linked session were used as fallback.",
                type="warning",
                timeout=8000,
            )
        else:
            ui.notify(t("resolution_complete"))

        dialog.close()  # close dialog 

        self.refresh_info_session()

    async def resolve_file_action(self):
        if not self.current_file_info:
           return

        api_key = get_setting_text(self.conn, "NOVA_ASTRO_API")
        if not api_key:
            ui.notify(t("nova_no_key"), type="warning")
            ui.notify(t("nova_go_settings"), type="info")
            # Still apply session fallback if available
            file_info = self.current_file_info
            if not file_info.get('ra') or not file_info.get('dec'):
                fallback_ra  = self.linked_data.get("session_ra")
                fallback_dec = self.linked_data.get("session_dec")
                if fallback_ra is not None and fallback_dec is not None:
                    file_info['ra'] = fallback_ra
                    file_info['dec'] = fallback_dec
                    file_info['ra_from_fallback'] = True
                    if self.meta_info:
                        self.meta_info['RA'] = fallback_ra
                        self.meta_info['DEC'] = fallback_dec
                    ui.notify(
                        "⚠️ Coordinates from the original linked session were used as fallback.",
                        type="warning", timeout=8000,
                    )
                else:
                    ui.notify(t("no_coords"), type="negative", timeout=8000)
            self.refresh_info_session()
            return

        with ui.dialog().props('persistent') as dialog:
            with ui.card().style('width: 800px; max-width: none'):
                error_label = ui.label().style('color: red')  # Empty label for future error messages
                close_button = ui.button(t("close"), on_click=dialog.close, color="secondary").props('visible')  # initially hidden
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

        if self.current_file_info.get('ra_from_fallback'):
            ui.notify(
                "⚠️ No coordinates found in the FITS file — "
                "coordinates from the original linked session were used as fallback.",
                type="warning",
                timeout=8000,
            )
        else:
            ui.notify(t("resolution_complete"))

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
            ui.notify(t("please_session_name"), type="warning")
            return

        # _get_effective_dest_path includes the tag sub-folder when set
        session_dir = self._get_effective_dest_path(dest_dir)
        print(f" Session dest_dir (effective):  {session_dir}")

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
                ui.button(t("yes"), on_click=lambda: dialog.submit('Yes'))
                ui.button(t("no"), on_click=lambda: dialog.submit('No'))

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
        ui.notify(t("starting"))

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
        print(f"dest_path :  {dest_path}")
        self.cancel_backup = False
        verified_files = 0
        total_files = len(self.client.storage.uploaded_files)
        result = False

        if total_files == 0:
            self.error_execute("No files to backup.", type="info")
            return False

        # Mark the first file of each extension type so rename logic knows
        # which one gets the canonical stacked-16_* name.
        _seen_ext = set()
        for file_info in self.client.storage.uploaded_files:
            ext = os.path.splitext(file_info.get("name", ""))[1].lower()
            if ext in (".jpg", ".jpeg"):
                ext_key = ".jpg"
            elif ext == ".png":
                ext_key = ".png"
            elif ext in (".fits", ".fit", ".fts"):
                # URL files with a suffix are never "first" — they always use suffix name
                ext_key = ".fits" if not file_info.get("url_suffix") else None
            else:
                ext_key = None
            if ext_key and ext_key not in _seen_ext:
                file_info["is_first_of_type"] = True
                _seen_ext.add(ext_key)
            else:
                file_info["is_first_of_type"] = False

        try:
            for i, file_info in enumerate(self.client.storage.uploaded_files, start=1):
                if self.cancel_backup:
                    ui.notify(t("backup_cancelled"), type="warning")
                    break

                try:
                    src_path = file_info.get("path")
                    filename = file_info.get("name")
                    ext = os.path.splitext(filename)[1].lower()

                    # Rename rules:
                    #  • First JPG  → stacked.jpg
                    #  • First PNG  → stacked-16_{session}.png
                    #  • First FITS → stacked-16_{session}.fits
                    #  • URL FITS with suffix → stacked-16_{session}__{suffix}.fits
                    #  • Subsequent local FITS → keep original filename
                    url_suffix = file_info.get("url_suffix", "")
                    is_first = file_info.get("is_first_of_type", False)

                    if ext in (".jpg", ".jpeg"):
                        new_filename = "stacked.jpg"
                    elif ext == ".png":
                        if is_first:
                            new_filename = f"stacked-16_{self.selected_session_name}.png"
                        else:
                            new_filename = filename
                    elif ext in (".fits", ".fit", ".fts"):
                        if url_suffix:
                            # Stellar Studio URL download with chosen suffix
                            new_filename = f"stacked-16_{self.selected_session_name}__{url_suffix}.fits"
                        elif is_first:
                            new_filename = f"stacked-16_{self.selected_session_name}.fits"
                        else:
                            # Keep original filename — user already named it meaningfully
                            new_filename = filename
                    else:
                        new_filename = filename

                    # Avoid overwriting existing files
                    base_name, file_ext = os.path.splitext(new_filename)
                    dest_file_path = os.path.join(dest_path, new_filename)
                    counter = 1
                    while os.path.exists(dest_file_path):
                        dest_file_path = os.path.join(dest_path, f"{base_name}_{counter}{file_ext}")
                        counter += 1

                    # Copy the file to destination
                    result_copy = safe_copy2(src_path, dest_file_path)
                    if not result_copy:
                        raise Exception(f"Copy failed without exception: {src_path}")
                        
                    
                    #thumbnail for first jpeg
                    if (file_ext.lower() == ".jpg" or file_ext.lower() == ".jpeg" ) and counter == 1:
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
                ui.notify(t("backup_complete"), type="positive")
            elif not self.cancel_backup and verified_files > 0:
                result = True
                ui.notify(f"⚠️ Backup partially completed ({verified_files}/{total_files} files copied).", type="warning")

            # --- Register in database (as long as at least one file was copied) ---
            if not self.cancel_backup and verified_files > 0:
                try:
                    # Gather metadata from the first FITS file (if any)
                    meta = self.main_meta_info or {}
                    description  = meta.get('OBJECT')
                    dec          = meta.get('DEC')
                    ra           = meta.get('RA')
                    exp_time     = str(meta.get('EXPTIME', '')) or None
                    IR_filter  = meta.get('FILTER')
                    maxTemp      = meta.get('TEMP')
                    minTemp      = None

                    # Collect paths of copied files by extension
                    jpeg_path        = None
                    stacked_png_path = None
                    stacked_fits_path= None
                    stacked_fits_md5 = None
                    total_size       = 0
                    mtime            = None

                    for file_info in self.client.storage.uploaded_files:
                        print(file_info)
                        src = file_info.get("path", "")
                        orig_name = file_info.get("name", "")
                        ext = os.path.splitext(orig_name)[1].lower()
                        url_suffix = file_info.get("url_suffix", "")
                        is_first = file_info.get("is_first_of_type", False)

                        if ext in (".jpg", ".jpeg") and jpeg_path is None:
                            jpeg_path = os.path.join(dest_path, "stacked.jpg")
                        elif ext == ".png" and stacked_png_path is None and is_first:
                            stacked_png_path = os.path.join(dest_path, f"stacked-16_{self.selected_session_name}.png")
                        elif ext in (".fits", ".fit", ".fts") and stacked_fits_path is None:
                            if url_suffix:
                                _fname = f"stacked-16_{self.selected_session_name}__{url_suffix}.fits"
                            elif is_first:
                                _fname = f"stacked-16_{self.selected_session_name}.fits"
                            else:
                                _fname = orig_name
                            stacked_fits_path = os.path.join(dest_path, _fname)
                            if os.path.exists(stacked_fits_path):
                                stacked_fits_md5 = compute_md5(stacked_fits_path)
                        if os.path.exists(src):
                            total_size += os.path.getsize(src)
                            file_mtime = int(os.path.getmtime(src))
                            if mtime is None or file_mtime > mtime:
                                mtime = file_mtime

                    thumbnail_path = jpeg_path.replace("stacked.jpg", "stacked_thumbnail.jpg") if jpeg_path else None

                    # Fallback: no JPG was uploaded — check if stacked.jpg already exists
                    # in the destination (e.g. from a previous import or linked session copy)
                    if not jpeg_path:
                        for candidate in ("stacked.jpg", "stacked.jpeg", "stacked.png"):
                            candidate_path = os.path.join(dest_path, candidate)
                            if os.path.isfile(candidate_path):
                                jpeg_path = candidate_path
                                thumb_candidate = candidate_path.replace("stacked.jpg", "stacked_thumbnail.jpg").replace("stacked.jpeg", "stacked_thumbnail.jpg")
                                if os.path.isfile(thumb_candidate):
                                    thumbnail_path = thumb_candidate
                                print(f"[ManualSession] jpeg_path fallback from disk: {jpeg_path}")
                                break
                    session_name   = self.sanitize_session_name(self.selected_session_name or self.session_dirname.value.strip())
                    session_tag    = (self.session_tag.value or "").strip()
                    session_type   = self.mode
                    print("before insert/update")

                    # Build shared kwargs for insert or update
                    _db_kwargs = dict(
                        session_name      = session_name,
                        session_tag       = session_tag,
                        session_type      = session_type,
                        jpeg_path         = get_session_file_ref(dest_path, jpeg_path),
                        modification_time = mtime,
                        thumbnail_path    = get_session_file_ref(dest_path, thumbnail_path),
                        file_size         = total_size,
                        description       = description,
                        dec               = dec,
                        ra                = ra,
                        exp_time          = exp_time,
                        IR_filter         = IR_filter,
                        maxTemp           = maxTemp,
                        minTemp           = minTemp,
                        stacked_png_path  = get_session_file_ref(dest_path, stacked_png_path),
                        stacked_fits_path = get_session_file_ref(dest_path, stacked_fits_path),
                        stacked_fits_md5  = stacked_fits_md5,
                    )

                    # 1. In edit mode, UPDATE by id — avoids creating a duplicate when
                    #    session_name changed (e.g. .zip stripped from name).
                    #    In create mode, use the normal upsert by (name, tag, type).
                    if self.edit_mode and self.existing_session_row:
                        existing_id = self.existing_session_row[0]
                        ok = update_manual_session(self.conn, existing_id, **_db_kwargs)
                        manual_session_id = existing_id if ok else None
                    else:
                        manual_session_id, _ = insert_ManualSession(self.conn, **_db_kwargs)

                    if manual_session_id:
                        # 2. Determine astro_group_id (Manual group)
                        from api.dwarf_backup_db_api import get_astro_object_groupId, insert_astro_group
                        astro_group_id = get_astro_object_groupId(self.conn, MANUAL)
                        if not astro_group_id:
                            astro_group_id, _ = insert_astro_group(self.conn, MANUAL)

                        session_dt_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
                        astro_object_id = self.linked_data.get("astro_object_id")
                        session_id = self.linked_data.get("session_id")

                        # Get or create ManualSessionDrive.
                        # location = drive root (BackupDrive.location) — used as the
                        # UNIQUE key and prefix anchor for rebuild_manual_session_entries.
                        # manualsession_dir = actual destination folder chosen by the user.
                        manual_session_drive_id = get_or_create_ManualSessionDrive(
                            self.conn,
                            location          = self.backup_location,
                            manualsession_dir = self.input_dest_dir.value,
                            name              = self.backup_filter.value or self.backup_location,
                            backup_drive_id   = self.BackupDriveId,
                        )

                        # 3. Insert the ManualSessionEntry link record
                        insert_ManualSessionEntry(
                            self.conn,
                            manual_session_id = manual_session_id,
                            backup_drive_id   = self.BackupDriveId,
                            dwarf_id          = self.DwarfId,
                            astro_object_id   = astro_object_id,
                            backup_entry_id   = session_id,
                            session_dt_str    = session_dt_str,
                            session_dir       = dest_path,
                            astro_group_id    = astro_group_id,
                            manual_session_drive_id = manual_session_drive_id,
                        )
                        ui.notify(t("session_registered"), type="positive")

                        # Show "View Session" button linking to ManualExplore
                        import urllib.parse
                        _params = {"SessionId": manual_session_id}
                        if self.BackupDriveId:
                            _params["BackupDriveId"] = self.BackupDriveId
                        if self.DwarfId:
                            _params["DwarfId"] = self.DwarfId
                        _back = urllib.parse.quote(
                            f"/ManualSession?ManualEntryId={manual_session_id}", safe=""
                        )
                        _params["back_url"] = _back
                        _explore_url = "/ManualExplore/?" + urllib.parse.urlencode(_params)
                        self.view_session_button.set_text("🔭 View Session in Explore")
                        self.view_session_button.on("click", lambda u=_explore_url: ui.navigate.to(u))
                        self.view_session_button.visible = True

                        # In edit mode, refresh the existing-files panel to show the
                        # newly copied files alongside any that were kept.
                        if self.edit_mode and manual_session_id:
                            session_dir_for_refresh = dest_path
                            self._load_existing_files_panel(session_dir_for_refresh)
                    else:
                        ui.notify(t("db_saved_failed"), type="warning")

                except Exception as db_err:
                    ui.notify(f"⚠️ Database error: {db_err}", type="warning")
                    print(f"[DB ERROR] Manual session registration failed: {db_err}")

            elif not self.cancel_backup:
                ui.notify(t("backup_incomplete"), type="warning")

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

        self.client.storage.uploaded_files.clear()
        self.uploaded_fits_files = []
        self.refresh_fits_file_list_uploaded()
        self.selected_file = None

        # In edit mode, main_meta_info comes from the stored DB record, not from
        # the temp upload — keep it so the DB upsert can still read coordinates.
        if not self.edit_mode:
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