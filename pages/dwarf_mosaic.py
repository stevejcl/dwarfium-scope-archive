import webview
from nicegui import ui, app, run, Client

import os
import shutil
import asyncio
import tempfile
import traceback
from pathlib import Path

from components.menu import menu
from api.dwarf_backup_fct import get_local_dwarf_dir, print_log, win_long_path
from api.dwarf_backup_fct_mosaic import repair_mosaic_session, merge_mosaic
from api.dwarf_backup_db import DB_NAME, connect_db, close_db
from api.dwarf_backup_db_api import get_dwarf_Names, get_dwarf_detail, get_backupDrive_list_dwarfId, get_backupDrive_detail
from components.win_log import WinLog
from api.repair_session_manager import RepairSessionManager
from components.repair_history_dialog import check_and_show_history
from components.mosaic_restore_dialog import open_mosaic_restore_dialog

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

    menu("Mosaic Repair / Merge")
    await ui.context.client.connected()
    ui.context.mosaic_app = MosaicApp(client, DB_NAME, DwarfId=DwarfId, Session=session, BackUrl=back_url, BackupId=BackupId)


class MosaicApp:
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
        self.BackUrl = BackUrl

        # Directories
        self.primary_session_dir = ''   # Session to repair or merge INTO
        self.secondary_session_dir = '' # Session used as repair/merge source
        self.output_dir = ''            # Temporary output directory

        self.primary_main_dir = ''      # Root astro dir for primary picker
        self.secondary_main_dir = ''    # Root astro dir for secondary picker

        self.dwarf_astroDir = ''
        self.dwarf_ip_sta_mode = ''
        self.dwarf_type = None

        self.mode = "Repair"
        self.cancel_process = False

        # ── Repair/Merge session tracking ──────────────────────────────
        # RepairSessionManager is initialised lazily once output_dir is known
        self.repair_mgr: RepairSessionManager | None = None
        self._current_entry_id: str | None = None   # ID of the running action

        self.build_ui()

    # ------------------------------------------------------------------ #
    #  UI BUILD                                                            #
    # ------------------------------------------------------------------ #

    def build_ui(self):
        self.conn = connect_db(self.database)
        nbcol = 3 if self.BackUrl else 1

        # ── Header card ──────────────────────────────────────────────────
        with ui.card().classes("w-full p-4 mt-2 items-center") as self.main_ui:
            with ui.grid(columns=nbcol).classes("items-center"):
                if self.BackUrl:
                    ui.button("🔙 Back", on_click=lambda: ui.navigate.to(self.BackUrl)).classes("justify-self-start")
                self.mode_toggle = ui.toggle(
                    ['Repair', 'Merge'], value=self.mode, on_change=self.switch_mode
                ).classes("col-span-1 justify-self-center")

            self.main_label = ui.label(
                "Primary = reference mosaic (small but correct). Secondary = session to repair. Result goes to the work directory."
            ).classes("text-sm text-gray-500")

            # Dwarf + Backup selector row
            with ui.grid(columns=2):
                with ui.column():
                    ui.label("Select Dwarf:").classes("text-lg font-semibold")
                    self.dwarf_filter = ui.select(options=[], on_change=self.on_dwarf_filter_change).props('outlined')
                    self.usb_status_label = ui.label("").classes('pb-2')
                with ui.column():
                    ui.label("Backup Drive:").classes("text-lg font-semibold")
                    self.backup_filter = ui.select(options=[], on_change=self.on_backup_filter_change).props('outlined')
                    self.backup_status_label = ui.label("").classes('pb-2')

        # ── Primary session card ─────────────────────────────────────────
        with ui.card().classes("w-full p-4 mt-1 items-center"):
            self.primary_session_label = ui.label("📂 Primary Session (reference — correct mosaic)").classes("text-lg font-semibold")
            with ui.row().classes("items-center gap-2"):
                ui.label("Data source:").classes("text-sm text-gray-500")
                self.primary_source_toggle = ui.toggle(
                    ['Dwarf', 'Backup'], value='Dwarf',
                    on_change=self.on_primary_source_change,
                ).props('dense')
            self.input_primary_dir = (
                ui.select(
                    label="Primary Session Directory:",
                    value=self.primary_session_dir,
                    options=[self.primary_session_dir],
                    on_change=self.on_primary_dir_change,
                )
                .props('stack-label outlined')
                .classes("min-w-[600px] w-auto overflow-x-auto whitespace-nowrap")
            )
            ui.button("📁 Select Primary Session", on_click=self.select_primary_folder)

        # ── Secondary session card ───────────────────────────────────────
        with ui.card().classes("w-full p-4 mt-1 items-center"):
            self.secondary_session_label = ui.label("📂 Secondary Session (session to repair)").classes("text-lg font-semibold")
            with ui.row().classes("items-center gap-2"):
                ui.label("Data source:").classes("text-sm text-gray-500")
                self.secondary_source_toggle = ui.toggle(
                    ['Dwarf', 'Backup'], value='Dwarf',
                    on_change=self.on_secondary_source_change,
                ).props('dense')
            self.input_secondary_dir = (
                ui.select(
                    label="Secondary Session Directory:",
                    value=self.secondary_session_dir,
                    options=[self.secondary_session_dir],
                    on_change=self.on_secondary_dir_change,
                )
                .props('stack-label outlined')
                .classes("min-w-[600px] w-auto overflow-x-auto whitespace-nowrap")
            )
            ui.button("📁 Select Secondary Session", on_click=self.select_secondary_folder)

        # ── Output / temp directory card ─────────────────────────────────
        with ui.card().classes("w-full p-4 mt-1 items-center"):
            ui.label("📤 Output (Temporary) Directory").classes("text-lg font-semibold")
            self.input_output_dir = (
                ui.select(
                    label="Output Directory:",
                    value=self.output_dir,
                    options=[self.output_dir],
                    on_change=lambda: None,
                )
                .props('stack-label outlined')
                .classes("min-w-[600px] w-auto overflow-x-auto whitespace-nowrap")
            )
            with ui.row():
                ui.button("📁 Select Output Folder", on_click=self.select_output_folder)
                ui.button("🗂️ Create Temp Folder", on_click=self.create_temp_folder)

        # ── Action card ──────────────────────────────────────────────────
        with ui.card().classes("w-full p-4 mt-1 mb-8 items-center"):
            self.progress_label = ui.label("Idle…")
            self.progress = ui.circular_progress(max=100, show_value=True)

            with ui.row():
                self.cancel_btn = ui.button("❌ Cancel", on_click=self.cancel)
                self.cancel_btn.visible = False

                self.action_button = ui.button("🔧 Start Repair", on_click=self.start_process)

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
                ui.button("Later", on_click=self._copy_dlg.close).props("flat color=grey")
                ui.button(
                    "📁 Copy to Dwarf now",
                    on_click=self._on_copy_dlg_confirm,
                ).props("color=green")

    # ------------------------------------------------------------------ #
    #  MODE SWITCH                                                         #
    # ------------------------------------------------------------------ #

    def switch_mode(self):
        self.mode = self.mode_toggle.value
        if self.mode == "Repair":
            self.main_label.text = "Primary = reference mosaic (small but correct). Secondary = session to repair. Result goes to the work directory."
            self.action_button.text = "🔧 Start Repair"
            self.primary_session_label.text = "📂 Primary Session (reference — correct mosaic)"
            self.secondary_session_label.text = "📂 Secondary Session (session to repair)"
        else:
            self.main_label.text = "Primary = base mosaic. Secondary = session whose data will be merged into it. Result goes to the work directory."
            self.action_button.text = "🔀 Start Merge"
            self.primary_session_label.text = "📂 Primary Session (base mosaic)"
            self.secondary_session_label.text = "📂 Secondary Session (data to merge in)"

    # ------------------------------------------------------------------ #
    #  DWARF SELECTOR                                                      #
    # ------------------------------------------------------------------ #

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
                self.backup_status_label.text = "✅ Path detected."
            else:
                self.backup_status_label.text = "❌ Path not detected."
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

    def check_dir_dwarf(self):
        if self.dwarf_astroDir:
            if os.path.exists(self.dwarf_astroDir):
                self.usb_status_label.text = "✅ Path detected."
            else:
                self.usb_status_label.text = "❌ Path not detected."
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
            ui.notify(f"⚠️ No {label} directory available.", type="warning")
            return
        self.primary_session_dir = root
        self.primary_main_dir = root
        self.input_primary_dir.set_options([root], value=root)
        ui.notify(f"✅ Primary source → {self.primary_source}: {root}", type="positive")

    def on_secondary_source_change(self):
        self.secondary_source = self.secondary_source_toggle.value
        root = self._root_for_source(self.secondary_source)
        if not root:
            label = "Backup" if self.secondary_source == 'Backup' else "Dwarf"
            ui.notify(f"⚠️ No {label} directory available.", type="warning")
            return
        self.secondary_session_dir = root
        self.secondary_main_dir = root
        self.input_secondary_dir.set_options([root], value=root)
        ui.notify(f"✅ Secondary source → {self.secondary_source}: {root}", type="positive")

    # ------------------------------------------------------------------ #
    #  INPUT CHANGE HANDLERS                                               #
    # ------------------------------------------------------------------ #

    def on_primary_dir_change(self):
        self.primary_session_dir = self.input_primary_dir.value or ""
        if self.primary_session_dir != self._root_for_source(self.primary_source) and "MOSAIC" not in self.primary_session_dir:
            ui.notify("Directory does not contain MOSAIC", type="warning")

    def on_secondary_dir_change(self):
        self.secondary_session_dir = self.input_secondary_dir.value or ""
        if self.secondary_session_dir != self._root_for_source(self.secondary_source) and "MOSAIC" not in self.secondary_session_dir:
            ui.notify("Directory does not contain MOSAIC", type="warning")

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
            ui.notify(f"❌ Access denied: You cannot navigate outside {label_name}", type="negative")
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
            ui.notify(f"✅ Primary session: {chosen}", type="positive")

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
            ui.notify(f"✅ Secondary session: {chosen}", type="positive")

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
            ui.notify(f"✅ Output folder: {chosen}", type="positive")

    def create_temp_folder(self):
        """Create a system temp directory and pre-fill the output field."""
        tmp = tempfile.mkdtemp(prefix="dwarf_mosaic_")
        self.output_dir = tmp
        self.input_output_dir.set_options([tmp], value=tmp)
        self._init_repair_mgr(tmp)
        ui.notify(f"✅ Temp folder created: {tmp}", type="positive")

    def _init_repair_mgr(self, output_dir: str):
        """Initialise (or reinitialise) the RepairSessionManager for the chosen output dir."""
        self.repair_mgr = RepairSessionManager(output_dir)

    # ------------------------------------------------------------------ #
    #  PROCESS LAUNCH                                                      #
    # ------------------------------------------------------------------ #
    @ui.refreshable
    def notify_me(self, msg: str | None) -> None:
        if msg:
            ui.notify(msg)

    def cancel(self):
        self.cancel_process = True

    # ------------------------------------------------------------------ #
    #  PROCESS LAUNCH — with history check                                 #
    # ------------------------------------------------------------------ #

    async def start_process(self):
        primary   = self.input_primary_dir.value
        secondary = self.input_secondary_dir.value
        output    = self.input_output_dir.value

        if not primary:
            ui.notify("❌ Please select a Primary Session.", type="negative")
            return
        if not secondary:
            ui.notify("❌ Please select a Secondary Session.", type="negative")
            return
        if not output:
            ui.notify("❌ Please select or create an Output directory.", type="negative")
            return
        if primary == secondary:
            ui.notify("⚠️ Primary and Secondary sessions must be different.", type="warning")
            return
        if "MOSAIC" not in primary:
            ui.notify("⚠️ Primary does not contain MOSAIC.", type="warning")
            return
        if "MOSAIC" not in secondary:
            ui.notify("⚠️ Primary does not contain MOSAIC.", type="warning")
            return

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
            on_redo         = lambda: ui.timer(0, lambda: asyncio.ensure_future(self._run_process(primary, secondary, output, primary_name)), once=True),
            on_continue     = lambda: ui.timer(0, lambda: asyncio.ensure_future(self._run_process(primary, secondary, output, primary_name, True)), once=True),
            on_copy         = self._open_copy_dialog,
            on_proceed      = lambda: ui.timer(0, lambda: asyncio.ensure_future(self._run_process(primary, secondary, output, primary_name)), once=True),
            dwarf_id        = self.DwarfId,
            backup_id       = self.BackupId,
        )
        # If no history, on_proceed fires immediately via the timer above.
        # If history exists, the dialog handles routing — nothing more to do here.
        _ = already_shown

    async def _run_process(self, primary: str, secondary: str, output: str, primary_name: str, ignore_copy: bool = False ):
        """Core repair/merge logic, called both on first run and on Redo."""
        work_primary = os.path.join(output, primary_name)

        self.cancel_process = False
        self.cancel_btn.visible = True
        self.action_button.visible = False
        self.image_ui.set_source("")
        await self.client.run_javascript("document.body.style.cursor='wait'")
        self.progress.value = 0
        self.progress_label.set_text("📋 Copying primary session to work directory…")

        # ── Step 0: register action as "running" ─────────────────────────
        from datetime import datetime
        #output_subdir = f"{primary_name}_{self.mode.lower()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
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

        # ── Step 1: copy primary session into the work (output) directory ──
        try:
            if not ignore_copy :
                print_log(f"Copying '{primary}' → '{work_primary}'", self.log_ui)
                if self.mode == "Repair":
                    await run.io_bound(self._copy_session, primary, work_primary)
                else:
                    await run.io_bound(self._copy_all_session, primary, work_primary)
                self.progress.value = 20
                print_log("✅ Copy complete.", self.log_ui)
            else:
                self.progress.value = 20
                print_log("✅ Copy Primary skipped.", self.log_ui)
        except Exception as e:
            self.notify_me.refresh(f"❌ Copy failed: {e}", type="negative")
            traceback.print_exc()
            self.progress_label.set_text("❌ Copy failed.")
            self.cancel_btn.visible = False
            self.action_button.visible = True
            self.repair_mgr.update_action_status(self._current_entry_id, "failed", error=str(e))
            await self.client.run_javascript("document.body.style.cursor='default'")
            return

        # ── Step 2: run the repair / merge on the work copy ────────────────
        self.progress_label.set_text("🚀 Running Mosaic process on work directory…")
        result = None
        error  = None
        try:
            if self.mode == "Repair":
                print_log("Starting Repair…", self.log_ui)
                result = await repair_mosaic_session(secondary, work_primary, self.log_ui, self.progress)
            else:
                print_log("Starting Merge…", self.log_ui)
                result = await merge_mosaic(secondary, work_primary, self.log_ui, self.progress)
        except Exception as e:
            error = str(e)
            self.notify_me.refresh(f"❌ Error: {e}", type="negative")
            traceback.print_exc()

        self.cancel_btn.visible = False
        self.action_button.visible = True
        await self.client.run_javascript("document.body.style.cursor='default'")

        if result and Path(result).exists():
            self.progress.value = 100
            self.progress_label.set_text("✅ Process complete.")
            self.image_ui.set_source(str(result))
            self.image_ui.force_reload()
            self.notify_me.refresh("✅ Done! Result image displayed below.", type="positive")

            # ── Step 3: mark success and offer copy to Dwarf ───────────────
            self.repair_mgr.update_action_status(self._current_entry_id, "success")
            entry["status"] = "success"
            await self._offer_copy_after_process(entry)
        else:
            status = "failed" if error else "partial"
            self.repair_mgr.update_action_status(self._current_entry_id, status, error=error)
            self.progress_label.set_text("❌ Process failed or was cancelled.")
            self.notify_me.refresh("⚠️ Process finished but no result image was produced.", type="warning")

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
        self._copy_dlg_title.set_text(f"✅ {self.mode} successful!")
        self._copy_dlg_body.set_text(
            f"The {action_label} session is ready in the output directory. "
            "Do you want to copy the files back to the Dwarf now?"
        )
        self._copy_dlg.open()

    def _on_copy_dlg_confirm(self):
        self._copy_dlg.close()
        if self._copy_dlg_entry is not None:
            self._open_copy_dialog(self._copy_dlg_entry)

    @staticmethod
    def _copy_session(src: str, dest: str) -> None:
        """Prepare the work directory from the primary session:
        - Copy files in the root directory (ZIPs, JSONs, stacked.jpg, …)
        - Recreate subdirectory structure (panel folders) with only their stacked-16* files.
        """
        src_path = Path(win_long_path(src))
        dest_path = Path(win_long_path(dest))
 
        if dest_path.exists():
            shutil.rmtree(dest_path)
        dest_path.mkdir(parents=True)
 
        # Copy root-level files only
        for item in src_path.iterdir():
            if item.is_file():
                shutil.copy2(str(item), str(dest_path / item.name))
            elif item.is_dir():
                panel_dest = dest_path / item.name
                panel_dest.mkdir(parents=True, exist_ok=True)
                # Copy only stacked-16* files (used as name reference by repair/merge)
                for f in item.glob("stacked-16*"):
                    shutil.copy2(str(f), str(panel_dest / f.name))
                    
    @staticmethod
    def _copy_all_session(src: str, dest: str) -> None:
        """Blocking copy of a session directory into the work directory."""
        src = win_long_path(src)
        dest = win_long_path(dest)

        # remove existing
        if os.path.exists(dest):
            shutil.rmtree(dest)
        shutil.copytree(src, dest)            