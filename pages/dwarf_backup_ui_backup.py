from components.i18n import t
import urllib.parse
import webview
import sqlite3
import os

from nicegui import native, app, run, ui, background_tasks

from api.dwarf_backup_db import DB_NAME, connect_db, close_db
from components.db_page_mixin import DbPageMixin
from api.dwarf_backup_fct import scan_backup_folder, insert_or_get_backup_drive, list_error_integrity  

from api.dwarf_backup_db_api import get_dwarf_Names, get_sessions_backup
from api.dwarf_backup_db_api import get_backupDrive_detail, set_backupDrive_detail, get_backupDrive_list, get_backupDrive_id_from_location, add_backupDrive_detail, del_backupDrive
from api.dwarf_backup_db_api import get_session_present_in_backupDrive
from api.dwarf_backup_db_api import has_related_backup_entries, has_related_manual_entries, delete_backup_entries_and_dwarf_data, delete_manual_entries
from tools.quality_scan import get_sessions_to_score, score_entry_ids

from components.win_log import WinLog
from components.menu import menu, setStyle
from components.disk_space_widget import disk_space_widget

@ui.page('/Backup')
async def backup_settings(BackupId:int = None):

    menu(t("page_backup"))
    await ui.context.client.connected(timeout=10.0)
    # Launch the GUI
    ConfigApp(DB_NAME, BackupId=BackupId)
    #ui.context.client.on_disconnect(lambda: logger.removeHandler(handler))

class ConfigApp(DbPageMixin):
    def __init__(self, database, BackupId=None):
        self.database = database
        self.dwarfs = []

        self.dwarf_id = None
        self.backupDrives = []
        self.backupDrive_id = BackupId
        self.backup_scan_date = None
        self.history_log = None
        self.backup_integrity_done = False
        self.backup_integrity_list = None
        self.errors = None
        self.selected_error = {"value": None}
        self._disk_widget = None
        self.WinLog = WinLog()
        self.build_ui()

    def build_ui(self):
        self.conn = connect_db(self.database)
        self.register_conn_close()
        sizeBTN='w-56'
        sizeBTN2='w-58'

        with ui.card().classes("w-full max-w-3xl mx-auto"):
            with ui.row().classes("w-full mt-2 mb-2 justify-between gap-8"):
                ui.button(t("show_backup_data"), on_click=lambda: ui.navigate.to(self.get_explore_url())).classes(sizeBTN)
                self.history_log = ui.button(t("transfer_history_log"), on_click=self._toggle_history).classes(sizeBTN)
                ui.button(t("analyze_drive"), on_click=self.analyze_drive).classes(sizeBTN)
            with ui.grid(columns=2):
                ui.button(t("check_integrity"), on_click=self.check_integrity_drive).classes(sizeBTN)
                self.button_explore_session = ui.button(t("open_in_explorer"), on_click=self.open_in_explore).classes(sizeBTN)
            with ui.row().classes('col-span-2 items-start gap-4'):  
               self.results_container = ui.column().classes('flex-1')
            # Transfer history — hidden by default, shown on demand
            self.history_container = ui.column().classes('w-full')
            self.history_container.visible = False
            ui.separator()

            with ui.row().classes('w-full gap-8 items-start'):

                # Left: Add New button aligned with form top
                with ui.column().classes('items-start pt-8'):
                    ui.button(t("add_backup_drive"), on_click=self.set_new_BackupDrive).classes(sizeBTN)

                # Right: form fields
                with ui.column().classes('items-start flex-1'):
                    ui.label(t("select_existing_drive")).classes("text-lg font-semibold")

                    # BackupDrive Selection
                    self.backupDrive_selector = ui.select(
                        options=[],
                        on_change=self.load_selected_backupDrive,
                        label=t("please_select")
                    ).props('stack-label').props('outlined').classes('w-60')

                    with ui.row().classes('items-center gap-4'):
                        self.backupDrive_name = ui.input(t("backup_drive_name")).classes('w-55')
                        ui.button(t("delete_backup_drive"),
                                  on_click=self.confirm_and_delete_BackupDrive).props("color=red").classes(sizeBTN)

                    self.backupDrive_desc = ui.input(t("drive_description")).classes('w-55')

                    with ui.row().classes('items-center gap-4'):
                        self.backupDrive_location = (
                            ui.input(t("location_label"))
                            .classes("overflow-x-auto whitespace-nowrap")
                            .style("min-width: 260px; max-width: 400px;")
                        )
                        ui.button(t("select_folder"), on_click=self.select_folder).classes('w-46')

                    # Disk space info — updated when a drive is selected
                    self._disk_widget = disk_space_widget(None, drive_type="backup")

                    with ui.row().classes('items-center gap-4'):
                        self.backupDrive_astroDir = ui.input(t("astronomy_dir")).classes('w-55') or ""
                        ui.button(t("select_sub_folder"), on_click=self.select_subfolder).classes(sizeBTN)

                    # Dwarf selection
                    self.dwarf_list = get_dwarf_Names(self.conn)
                    self.dwarf_name_to_id = {name: id_ for id_, name in self.dwarf_list}
                    self.dwarf_id_to_name = {id_: name for id_, name in self.dwarf_list}

                    self.dwarf_selector = ui.select(
                        options=list(self.dwarf_name_to_id.keys()),
                        label=t("select_dwarf_label")
                    ).props('stack-label').props('outlined').classes('w-60')

                    with ui.card().tight():
                        ui.colors(brand='#A1A0A1')
                        ui.item_label('Last Scan on:').props('stack-label').classes('pl-3 pr-3 pt-2').classes('text-brand')
                        self.backup_scan_date = ui.label("").classes("pl-3 pr-3 pb-2")

            # ── Bottom: action buttons centered ───────────────────────────────
            ui.separator()
            with ui.row().classes("w-full mt-2 mb-2 justify-between"):
                ui.button(t("save_update_drive"),
                          on_click=self.save_or_update_backup_drive).classes(sizeBTN2)
                ui.button(t("delete_backup_entries"),
                          on_click=self.confirm_and_delete_entries).props("color=red").classes(sizeBTN2)
                ui.button(t("delete_manual_entries"),
                          on_click=self.confirm_and_delete_manual_entries).props("color=red").classes(sizeBTN2)

        # need this button don't change if not
        setStyle()
        self.history_log.visible = False
        self.resetIntegrity()
        self.refresh_backupDrive_list()

    def refresh_backupDrive_list(self):
        self.backupDrives = get_backupDrive_list(self.conn)

        # Create a list of tuples: (id, name)
        options = [f"{id} - {name}" for id, name, description, location, astroDir, dwarf_id, last_backup_scan_date in self.backupDrives]

        self.backupDrive_selector.set_options(options)
        self.backupDrive_map = {
            f"{id} - {name}": (id, location)
            for id, name, _, location, _, _, _ in self.backupDrives
        }

        # Update the select options AND set a default value if needed
        if options:
            # Auto-select if only one backup drive
            if len(self.backupDrives) == 1 and not self.backupDrive_selector.value:
                self.backupDrive_selector.set_options(options, value=options[0])
                self.backupDrive_id = self.backupDrives[0][0]
                return

            selected_id = None
            try:
                if self.backupDrive_selector.value:
                    selected_id = int(str(self.backupDrive_selector.value).split(" - ")[0])
            except (ValueError, IndexError):
                selected_id = None

            if self.backupDrive_id and not self.backupDrive_selector.value:
                selected_value = next((name for id, name, *_  in self.backupDrives if id == self.backupDrive_id), None)
                print(selected_value)
                selected_display = f"{self.backupDrive_id} - {selected_value}" if selected_value else options[0]
                self.backupDrive_selector.set_options(options, value=selected_display)
            elif self.backupDrive_id and selected_id != self.backupDrive_id:
                selected_value = next((name for id, name, *_ in self.backupDrives if id == self.backupDrive_id), None)
                selected_display = f"{self.backupDrive_id} - {selected_value}" if selected_value else options[0]
                self.backupDrive_selector.set_options(options, value=selected_display)
            else:
                self.backupDrive_selector.set_options(options)
        else:
            self.backupDrive_selector.set_options([], value=None)

    def _toggle_history(self):
        """Show/hide transfer history panel."""
        self.history_container.visible = not self.history_container.visible

    def _load_transfer_history(self, backup_path: str):
        """Read transfer_journal.json and display history in history_container."""
        import json as _json
        self.history_container.clear()
        self.history_container.visible = False  # reset visibility on drive change

        journal_path = os.path.join(backup_path, "transfer_journal.json")
        if not os.path.isfile(journal_path):
            return

        try:
            with open(journal_path, encoding='utf-8') as f:
                data = _json.load(f)
            history = data if isinstance(data, list) else [data]
        except Exception as e:
            with self.history_container:
                ui.label(f"⚠️ Could not read transfer journal: {e}").classes("text-red-500")
            return

        if not history:
            return

        with self.history_container:
            ui.label(t("transfer_history")).classes("text-base font-bold mt-2 mb-1")
            for entry in history:
                ok      = entry.get('result', '') == 'ok'
                ts      = entry.get('timestamp', '')[:16].replace('T', ' ')
                mode    = entry.get('mode', '')
                dwarf   = entry.get('dwarf_name') or f"Dwarf #{entry.get('dwarf_id','?')}"
                backup  = entry.get('backup_name') or f"Backup #{entry.get('backup_id','?')}"
                session = entry.get('session', '')
                copied  = entry.get('copied', 0)
                total   = entry.get('total', 0)
                card_color = 'border-l-4 border-green-500 bg-green-50' if ok else 'border-l-4 border-red-400 bg-red-50'
                with ui.card().classes(f'w-full {card_color} mb-1 py-1'):
                    with ui.row().classes('w-full items-center gap-2 flex-wrap'):
                        ui.label('✅' if ok else '⚠️').classes('text-sm')
                        ui.label(ts).classes('text-sm text-gray-600')
                        ui.label(mode).classes('text-sm font-semibold')
                        ui.label(f"🔭 {dwarf}").classes('text-sm')
                        ui.label(f"💾 {backup}").classes('text-sm')
                        ui.label(f"{copied}/{total} files").classes(
                            'text-sm font-bold ml-auto ' + ('text-green-700' if ok else 'text-red-600')
                        )
                    ui.label(session).classes('text-xs text-gray-500 truncate w-full')
                    error = entry.get('error', '')
                    if error:
                        ui.label(f"❌ {error}").classes('text-xs text-red-600 font-semibold')

    def resetIntegrity(self):
        # reset Integrity 
        self.errors = None
        self.selected_error = {"value": None}
        self.button_explore_session.visible=False
        self.results_container.clear()

    async def load_selected_backupDrive(self, _):
        value = self.backupDrive_selector.value
        if not value:
            self.history_log.visible = False
            if self._disk_widget:
                await self._disk_widget.refresh(None)
            return
        if value in self.backupDrive_map:
            self.backupDrive_id, path = self.backupDrive_map[value]
            self.resetIntegrity()
            self.history_log.visible = True
        else:
            ui.notify(t("invalid_backup_drive"), type="negative")
            self.history_log.visible = False
            return

        row = get_backupDrive_detail(self.conn, self.backupDrive_id)

        if row:
            self.backupDrive_name.value = row[0]
            self.backupDrive_desc.value = row[1]
            self.backupDrive_location.value = row[2]
            self.backupDrive_astroDir.value = row[3]
            self.dwarf_selector.value = row[4]
            self.backup_scan_date.text = row[5]
            self._resize_location_input()
            # Load transfer history from journal file
            backup_path = os.path.join(row[2], row[3]) if row[3] else row[2]
            self._load_transfer_history(backup_path)
            # Refresh disk space info
            if self._disk_widget:
                await self._disk_widget.refresh(
                    row[2],
                    drive_type="backup",
                    drive_id=self.backupDrive_id,
                    name=row[0],
                )

    def _resize_location_input(self):
        """Auto-resize the location input to fit its content."""
        ui.run_javascript(f"""
            const el = document.getElementById('{self.backupDrive_location.id}');
            if (!el) return;
            const span = document.createElement('span');
            span.style.visibility = 'hidden';
            span.style.whiteSpace = 'nowrap';
            span.style.font = window.getComputedStyle(el).font;
            span.innerText = el.value || el.placeholder || '';
            document.body.appendChild(span);
            let w = span.offsetWidth + 48;
            document.body.removeChild(span);
            w = Math.min(Math.max(w, 320), 460);
            el.style.width = w + 'px';
        """)

    def set_new_BackupDrive(self):
        self.resetIntegrity()
        self.backupDrive_selector.value = ""
        self.backupDrive_id = None
        self.backupDrive_name.value = ""
        self.backupDrive_desc.value = ""
        self.backupDrive_location.value = ""
        self.backupDrive_astroDir.value = ""
        self.backup_scan_date.text = ""
        if self.dwarfs:
            self.backupDrive_dwarf.value = self.dwarfs[0][1]

    async def select_folder(self):
        ui.notify(t("please_backup_dir"), type="info")
        location = self.backupDrive_location.value
        if hasattr(webview, 'FileDialog'):
            folder_mode = webview.FileDialog.FOLDER
        else:
            folder_mode = webview.FOLDER_DIALOG

        if location:
            folder = await app.native.main_window.create_file_dialog(folder_mode, allow_multiple=False,directory=location)
        else:
            folder = await app.native.main_window.create_file_dialog(folder_mode, allow_multiple=False)
        if folder:
            ui.notify(folder[0])
            folder = os.path.normpath(folder[0])
            self.backupDrive_location.value = folder

    async def select_subfolder(self, location_entry):
        ui.notify(t("select_astro_info"), type="info")
        location = self.backupDrive_location.value
        if not location:
            ui.notify(t("fill_location"), type="negative")
            return
        if hasattr(webview, 'FileDialog'):
            folder_mode = webview.FileDialog.FOLDER
        else:
            folder_mode = webview.FOLDER_DIALOG

        base_path = os.path.normpath(location)
        subfolder = await app.native.main_window.create_file_dialog(folder_mode, allow_multiple=False,directory=base_path)

        if subfolder:
            ui.notify(subfolder[0])
            subfolder = os.path.normpath(subfolder[0])

            if subfolder and subfolder.startswith(location):
                # Get relative path
                astroDir = os.path.relpath(subfolder, location)
                self.backupDrive_astroDir.value = astroDir
            elif subfolder:
                ui.notify(t("folder_not_in_loc"), type="negative")

    def get_selected_dwarf_id(self):
        print(f"selector: {self.dwarf_selector.value}")
        selected_name = self.dwarf_selector.value
        print(f"id: {self.dwarf_name_to_id.get(selected_name)}")
        return self.dwarf_name_to_id.get(selected_name)

    def _offer_backup_now(self, dwarf_id, backup_drive_id):
        """After saving a new backup drive, offer to go straight to Explore."""
        with ui.dialog() as dlg, ui.card().classes("p-4 gap-4"):
            ui.label(t("backup_drive_saved2")).classes("text-lg font-bold")
            ui.label(t("offer_backup_msg")).classes("text-gray-600")
            with ui.row().classes("gap-4 mt-2"):
                def go_explore():
                    dlg.close()
                    url = f"/Explore?DwarfId={dwarf_id}&BackupDriveId={backup_drive_id}&mode=dwarf&only_on_dwarf=1"
                    ui.navigate.to(url)
                ui.button(t("go_explore"), on_click=go_explore)
                ui.button(t("stay_here"), on_click=dlg.close)
        dlg.open()

    async def save_or_update_backup_drive(self):
        name = self.backupDrive_name.value
        desc = self.backupDrive_desc.value
        location = self.backupDrive_location.value
        astroDir = self.backupDrive_astroDir.value
        dwarf_id = self.get_selected_dwarf_id()

        if not (name and location and dwarf_id):
            ui.notify(t("fill_fields_save_dwarf"), type="negative")
            return

        existing = get_backupDrive_id_from_location(self.conn, location)

        if existing:
            # Ask user for confirmation before updating
            await self.WinLog.show(
                 t("confirm_update"),
                 t("confirm_update_location"),
                 self.ok_confirm_and_update_backup_data
            )
        else:
            try:
                self.backupDrive_id = add_backupDrive_detail(self.conn, name, desc, location, astroDir, dwarf_id)
                self.refresh_backupDrive_list()
                ui.notify(t("backup_drive_saved"), type="positive")
                self._offer_backup_now(dwarf_id, self.backupDrive_id)
            except sqlite3.IntegrityError:
                ui.notify(t("this_folder_registered"), type="negative")

    def ok_confirm_and_update_backup_data(self):
        name = self.backupDrive_name.value
        desc = self.backupDrive_desc.value
        location = self.backupDrive_location.value
        astroDir = self.backupDrive_astroDir.value or ""
        dwarf_id = self.get_selected_dwarf_id()

        set_backupDrive_detail(self.conn, name, desc, astroDir, dwarf_id, location)
        self.refresh_backupDrive_list()
        ui.notify(t("backup_info_updated"), type="positive")

    def save_backup_drive(self):
        name = self.backupDrive_name.value
        desc = self.backupDrive_desc.value
        location = self.backupDrive_location.value
        astroDir = self.backupDrive_astroDir.value
        dwarf_id = self.get_selected_dwarf_id()

        if not (name and location and dwarf_id):
            ui.notify(t("fill_fields_save_dwarf"), type="negative")
            return

        cursor = self.conn.cursor()
        try:
            add_backupDrive_detail(self.conn, name, desc, location, astroDir, dwarf_id)
            self.refresh_backupDrive_list()
            ui.notify(t("backup_drive_saved"), type="positive")
        except sqlite3.IntegrityError:
            ui.notify(t("this_folder_registered"), type="negative")

    def update_backup_drive(self):
        location = self.backupDrive_location.value
        name = self.backupDrive_name.value
        desc = self.backupDrive_desc.value
        astroDir = self.backupDrive_astroDir.value
        dwarf_id = self.get_selected_dwarf_id()

        if not location:
            ui.notify(t("no_location"), type="negative")
            return

        existing = get_backupDrive_id_from_location(self.conn, location)
        if not existing:
            ui.notify(t("no_backup_drive_loc"), type="negative")
            return

        set_backupDrive_detail(self.conn, name, desc, astroDir, dwarf_id, location)
        self.refresh_backupDrive_list()
        ui.notify(t("backup_info_updated"), type="positive")

    async def analyze_drive(self):
        location = self.backupDrive_location.value
        if not location:
            ui.notify(t("no_location"), type="negative")
            return

        astroDir = self.backupDrive_astroDir.value or ""

        # Dialog to block interaction and show progress
        with ui.dialog().props('persistent')  as dialog, ui.card().style('width: 800px; max-width: none'):
            error_label = ui.label().style('color: red')  # Empty label for future error messages
            close_button = ui.button(t("close"), on_click=dialog.close, color="secondary").props('visible')  # initially hidden
            ui.label(t("scanning_backup_location", location=f"{location}-{astroDir}"))
            spinner = ui.spinner(size="lg")
            scan_progress_bar   = ui.linear_progress(value=0, show_value=False).classes("w-full")
            scan_progress_label = ui.label("").classes("text-sm text-gray-500")
            log = ui.log(max_lines=20).classes('w-full').style('height: 400px; overflow: hidden;')

        dialog.open()  # show the dialog
        spinner.set_visibility(True)

        def _on_scan_progress(current_dir, done, total):
            """Called from the io_bound thread for each top-level folder scanned."""
            try:
                scan_progress_bar.set_value(done / total if total else 0)
                scan_progress_label.set_text(f"[{done}/{total}] 🔍 {current_dir}")
            except Exception:
                pass

        try:
            backup_drive_id, dwarf_id = insert_or_get_backup_drive(self.conn, location)

            ui.notify(t("scanning_location", location=f"{location}-{astroDir}"))
            total, deleted, rebuild_result = await run.io_bound(scan_backup_folder, DB_NAME, location, astroDir, dwarf_id, backup_drive_id, None, log, _on_scan_progress)
            scan_progress_bar.set_value(1)
            scan_progress_label.set_text(t("analysis_complete", total=total, deleted=deleted))
            ui.notify(t("analysis_complete", total=total, deleted=deleted), type="positive")
            spinner.set_visibility(False)

            # Auto-score new sessions in background
            if total >= 0:
                async def _auto_score():
                    def _get_and_score():
                        conn2 = connect_db(self.database)
                        sessions = get_sessions_to_score(conn2, None, None, False, backup_drive_id)
                        close_db(conn2)
                        entry_ids = [s["id"] for s in sessions]
                        if entry_ids:
                            return score_entry_ids(self.database, entry_ids)
                        return 0
                    scored = await run.io_bound(_get_and_score)
                    print(f"[AutoScore] {scored} new session(s) scored after backup scan.")
                background_tasks.create(_auto_score())

            # Report manual session re-linking that happened during the scan
            if rebuild_result["rebuilt"] > 0:
                ui.notify(
                    f"🔗 {rebuild_result['rebuilt']} manual session(s) re-linked.",
                    type="positive",
                )
            if rebuild_result["skipped"] > 0:
                ui.notify(
                    f"⚠️ {rebuild_result['skipped']} manual session(s) could not be matched — "
                    f"check that the backup drive is connected.",
                    type="warning",
                    timeout=8000,
                )
        except Exception as e:
            spinner.set_visibility(False)
            msg = f"❌ Error: {str(e)}"
            ui.notify(msg, type="negative")
            error_label.text = msg 
            close_button.visible = True
        else:
            ui.timer(5, lambda: self.end_analyze_drive(dialog), once=True)

    async def end_analyze_drive(self, dialog):
        dialog.close()
        await self.load_selected_backupDrive(None)


    async def check_integrity_drive(self):
        location = self.backupDrive_location.value
        if not location:
            ui.notify(t("no_location"), type="negative")
            return

        astroDir = self.backupDrive_astroDir.value or ""

        # Dialog to block interaction and show progress
        with ui.dialog().props('persistent')  as dialog, ui.card().classes("w-full p-4").style("max-width: 1200px; height: 800px; margin: auto"):
            error_label = ui.label().style('color: red')  # Empty label for future error messages
            close_button = ui.button(t("close"), on_click=dialog.close, color="secondary").props('visible')  # initially hidden
            ui.label(t("scanning_backup_location", location=location))
            spinner = ui.spinner(size="lg")
            log = ui.log(max_lines=100).classes('w-full').style('height: 786px; overflow: hidden;')

        dialog.open()  # show the dialog
        spinner.set_visibility(True)
        error_found = False

        try:
            backup_drive_id, dwarf_id = insert_or_get_backup_drive(self.conn, location)
            session_list = get_sessions_backup(self.conn, self.backupDrive_id)
            print(f"session_list: {len(session_list)} found")
            ui.notify(t("scanning_location", location=f"{location}-{astroDir}"))
            self.errors = await run.io_bound (list_error_integrity, self.conn, backup_drive_id, self.backupDrive_location.value, session_list, log)
            ui.notify(t("analysis_errors_found", count=len(self.errors)), type="positive")
            spinner.set_visibility(False)
            self.results_container.clear()
            if len(self.errors) > 0:
                error_found = True
                close_button.text = t("button_end_analysis_errors")
                # Store selected error
                self.selected_error = {"value": None}

                with self.results_container:
                    ui.separator()
                    ui.label(t("sessions_in_error")).classes("text-bold")

                    self.backup_integrity_list = ui.select(
                        options={
                            e["session_id"]: f"{e['session_dir']} → {e.get('reason') or e.get('status')}"
                            for e in self.errors
                        },
                        label=t("select_a_session"),
                        on_change=lambda e: self.selected_error.update({"value": e.value})
                    ).classes("w-full")
        except Exception as e:
            spinner.set_visibility(False)
            msg = f"❌ Error: {str(e)}"
            ui.notify(msg, type="negative")
            error_label.text = msg 
            close_button.visible = True

        if self.button_explore_session and error_found:
            self.button_explore_session.visible = True
        elif self.button_explore_session and not error_found:
            self.button_explore_session.visible = False

    def open_in_explore(self):
        if not self.selected_error["value"]:
            ui.notify(t("please_select_session"), type="warning")
            return

        # retrieve session from label
        selected = next(
            (e for e in self.errors if e["session_id"] == self.selected_error["value"]),
            None
        )

        if not selected:
            ui.notify(t("session_not_found"), type="negative")
            return

        session_id = selected["session_id"]

        ui.navigate.to(self.get_explore_url(session_id))

            
    async def confirm_and_delete_BackupDrive(self):
        if self.backupDrive_id is None:
            ui.notify(t("no_backup_drive_sel"), type="negative")
            return

        if has_related_manual_entries(self.conn, self.backupDrive_id):
            ui.notify(
                "This Backup Drive is still in use by one or more manual entries. Please remove them first.",
                type="negative")
            return

        if has_related_backup_entries(self.conn, self.backupDrive_id):
            ui.notify(
                "This Backup Drive is still in use by one or more backup entries. Please remove them first.",
                type="negative")
            return

        await self.WinLog.show(
            t("confirm_deletion"),
            t("confirm_delete_backup_drive"),
            self.ok_confirm_and_delete_backup_drive
        )

    def ok_confirm_and_delete_backup_drive(self):
        # Delete the BackupDrive
        del_backupDrive(self.conn, self.backupDrive_id)

        print(f"Deleted BackupDrive {self.backupDrive_id}.")
        self.refresh_backupDrive_list()
        self.set_new_BackupDrive()
        self.resetIntegrity()
        ui.notify(t("backup_drive_deleted"), type="positive")

    async def confirm_and_delete_entries(self):
        if self.backupDrive_id is None:
            ui.notify(t("no_backup_drive_sel"), type="negative")
            return

        await self.WinLog.show(
            t("confirm_deletion"),
            t("confirm_delete_backup_entries"),
            self.ok_confirm_and_delete_backup_entries
        )

    def ok_confirm_and_delete_backup_entries(self):
        delete_backup_entries_and_dwarf_data(self.conn, self.backupDrive_id)
        self.backup_scan_date.text = ""
        ui.notify(t("backup_entries_deleted"), type="positive")

    async def confirm_and_delete_manual_entries(self):
        if self.backupDrive_id is None:
            ui.notify(t("no_backup_selected"), type="negative")
            return

        if not has_related_manual_entries(self.conn, self.backupDrive_id):
            ui.notify(t("no_manual_entries"), type="info")
            return

        # First confirmation — warn about ManualSession records
        await self.WinLog.show(
            t("confirm_delete_manual_entries"),
            t("confirm_delete_manual_entries_msg"),
            self._ask_delete_manual_sessions_too,
        )

    async def _ask_delete_manual_sessions_too(self):
        """Second check: offer to also delete orphaned ManualSession records."""
        with ui.dialog().props('persistent') as dialog, ui.card().classes("p-4 gap-3"):
            ui.label(t("also_delete_manual")).classes("font-semibold")
            ui.separator()
            ui.label(t("confirm_delete_manual_sessions_msg"))
            ui.separator()
            with ui.row().classes("gap-4"):
                ui.button(
                    t("delete_entries_only"),
                    on_click=lambda: (dialog.close(),
                                      self._do_delete_manual_entries(also_sessions=False))
                ).props("color=orange")
                ui.button(
                    t("delete_entries_sessions"),
                    on_click=lambda: (dialog.close(),
                                      self._do_delete_manual_entries(also_sessions=True))
                ).props("color=red")
                ui.button(t("cancel"), on_click=dialog.close).props("flat color=grey")
        dialog.open()

    def _do_delete_manual_entries(self, also_sessions: bool):
        delete_manual_entries(self.conn, self.backupDrive_id)
        msg = "Manual entries deleted."
        if also_sessions:
            # delete_manual_entries already removes orphaned ManualSession rows
            # so nothing extra needed — just notify
            msg = "Manual entries and orphaned ManualSession records deleted."
        ui.notify(msg, type="positive")

    def get_explore_url(self, session_id = None):
        ui.notify(t("showing_backup"))  # Simulate showing data
        if self.backupDrive_id is None:
            explore_url = f"/Explore?mode=backup"
        else:
            back_url = urllib.parse.quote(f"/Backup?BackupId=", safe='')
            explore_url = f"/Explore?BackupDriveId={self.backupDrive_id}&mode=backup&back_url={back_url}"
        if session_id:
            explore_url += f"&SessionId={session_id}"
        print(explore_url)
        return explore_url