import webview
import os

from nicegui import app, run, ui

from api.dwarf_backup_db import DB_NAME, connect_db, close_db
from api.dwarf_backup_db_api import (
    get_dwarf_Names,
    get_backupDrive_list_dwarfId,
    get_DarkLibrary_list,
    get_or_create_DarkLibrary,
    delete_DarkLibrary,
    scan_dark_library,
)
from components.win_log import WinLog
from components.menu import menu, setStyle


@ui.page('/DarkLibrary')
async def dark_library_page(LibraryId: int = None):
    menu("Dark Library")
    await ui.context.client.connected()
    DarkLibraryApp(DB_NAME, LibraryId=LibraryId)


class DarkLibraryApp:
    def __init__(self, database, LibraryId=None):
        self.database  = database
        self.library_id = LibraryId   # pre-selected library id from URL
        self.WinLog    = WinLog()
        self.current_location = None
        self.current_backupId = None
        self.build_ui()

    # =========================================================================
    # UI
    # =========================================================================

    def build_ui(self):
        self.conn = connect_db(self.database)

        with ui.card().classes("w-full max-w-3xl mx-auto"):

            # ── Top buttons ──────────────────────────────────────────────────
            with ui.row().classes('items-start gap-4'):
                ui.button("📋 Show All Libraries",
                          on_click=self.refresh_library_list)

            ui.separator()

            # ── Main content: Add New (left) + form (right) ──────────────────
            with ui.row().classes('w-full gap-8 items-start'):

                with ui.column().classes('items-start pt-8'):
                    ui.button("➕ Add New Library",
                              on_click=self.set_new_library)

                with ui.column().classes('items-start flex-1'):
                    ui.label("Select Existing Dark Library").classes(
                        "text-lg font-semibold")

                    self.library_selector = ui.select(
                        options=[],
                        on_change=self.load_selected_library,
                        label="Please select",
                    ).props('stack-label outlined').classes('w-60')

                    with ui.row().classes('items-center gap-4'):
                        self.library_name = ui.input("Library Name").classes('w-55')
                        ui.button("🗑️ Delete Library",
                                  on_click=self.confirm_and_delete_library).props("color=red")

                    # Dwarf selector — filters which BackupDrives are shown
                    self.dwarf_list = get_dwarf_Names(self.conn)
                    self.dwarf_name_to_id = {name: id_ for id_, name in self.dwarf_list}

                    self.dwarf_selector = ui.select(
                        options=list(self.dwarf_name_to_id.keys()),
                        label="Dwarf",
                        on_change=self.on_dwarf_change,
                    ).props('stack-label outlined').classes('w-60')

                    # BackupDrive selector — populated after Dwarf is chosen
                    self.backup_data = {}
                    self.backup_selector = ui.select(
                        options=[],
                        label="Backup Drive",
                    ).props('stack-label outlined').classes('w-60')
                    self.backup_selector.on_value_change(self.on_backup_change)

                    with ui.row().classes('items-center gap-4'):
                        self.location_input = (
                            ui.input("CALI_FRAME Location")
                            .classes("overflow-x-auto whitespace-nowrap")
                            .style("min-width: 260px; max-width: 400px;")
                        )
                        ui.button("Select Folder",
                                  on_click=self.select_folder)

                    with ui.card().tight():
                        ui.colors(brand='#A1A0A1')
                        ui.item_label('Last Scan on:').props('stack-label').classes(
                            'pl-3 pr-3 pt-2 text-brand')
                        self.last_scan_label = ui.label("").classes("pl-3 pr-3 pb-2")

            # ── Bottom buttons ───────────────────────────────────────────────
            ui.separator()
            with ui.row().classes("w-full mt-2 mb-2 justify-between"):
                ui.button("Save / Update Library",
                          on_click=self.save_or_update_library)
                with ui.row().classes("gap-4"):
                    ui.button("📥 Download Darks",
                              on_click=self.navigate_to_download).props("color=indigo")
                    ui.button("🔍 Scan Library",
                              on_click=self.scan_library).props("color=teal")

        # ── Inventory card (shown after scan) ────────────────────────────────
        with ui.card().classes("w-full max-w-3xl mx-auto mt-4") as self.inventory_card:
            ui.label("Dark Inventory").classes("text-lg font-semibold mb-2")
            self.inventory_container = ui.column().classes('w-full')
        self.inventory_card.visible = False

        setStyle()
        self.refresh_library_list()

    # =========================================================================
    # Helpers
    # =========================================================================

    def _library_label(self, row):
        """Build dropdown label from a get_DarkLibrary_list row."""
        lib_id    = row[0]
        lib_name  = row[1] or row[2]   # name or location
        dwarf_nm  = row[7] or "?"
        bd_nm     = row[5] or "?"
        return f"{lib_id} - {lib_name} ({dwarf_nm} / {bd_nm})"

    # =========================================================================
    # List refresh
    # =========================================================================

    def refresh_library_list(self):
        self.libraries = get_DarkLibrary_list(self.conn)
        self.library_map = {}

        options = []
        for row in self.libraries:
            label = self._library_label(row)
            options.append(label)
            self.library_map[label] = row

        self.library_selector.set_options(options)

        # Auto-select if LibraryId was passed
        if self.library_id:
            for label, row in self.library_map.items():
                if row[0] == self.library_id:
                    self.library_selector.set_value(label)
                    self._fill_form(row)
                    break

    # =========================================================================
    # Form fill / clear
    # =========================================================================

    def _fill_form(self, row):
        """Populate form fields from a get_DarkLibrary_list row."""
        self.library_id      = row[0]
        self.library_name.value  = row[1] or ""
        self.last_scan_label.text = row[4] or ""

        # Set Dwarf selector then populate BackupDrives
        dwarf_name = row[7]
        self.current_backupId = row[3]
        self.current_location  = row[2] or ""
        self.location_input.value = self.current_location 
        print(self.current_location)

        if dwarf_name and dwarf_name in self.dwarf_name_to_id:
            self.dwarf_selector.set_value(dwarf_name)
            self._populate_backup_drives(self.dwarf_name_to_id[dwarf_name],
                                          preselect_bd_id=self.current_backupId )


    def set_new_library(self):
        self.library_id = None
        self.library_name.value   = ""
        self.location_input.value = ""
        self.last_scan_label.text = ""
        self.inventory_card.visible = False

    def load_selected_library(self, _):
        label = self.library_selector.value
        if label and label in self.library_map:
            self._fill_form(self.library_map[label])

    # =========================================================================
    # Dwarf / BackupDrive cascade
    # =========================================================================

    def on_dwarf_change(self, _):
        name = self.dwarf_selector.value
        dwarf_id = self.dwarf_name_to_id.get(name)
        if dwarf_id:
            self._populate_backup_drives(dwarf_id)

    def _populate_backup_drives(self, dwarf_id, preselect_bd_id=None):
        rows = get_backupDrive_list_dwarfId(self.conn, dwarf_id)
        # rows: (id, name, description, location, astronomy_dir, dwarf_id)
        self.backup_data = {
            f"{r[0]} - {r[1]}": (r[0], r[3])   # label → (id, location)
            for r in rows
        }
        options = list(self.backup_data.keys())
        self.backup_selector.set_options(options)

        if preselect_bd_id:
            for label, (bid, _) in self.backup_data.items():
                if bid == preselect_bd_id:
                    self.backup_selector.set_value(label)
                    self.location_input.set_value(self.current_location)
                    break
        elif options:
            self.backup_selector.set_value(options[0])
            bid, location = self.backup_data[options[0]]
            if (bid == self.current_backupId):
                self.location_input.set_value(self.current_location)
            else:
                self.location_input.set_value(location or "")

    def on_backup_change(self, e):
        label = e.value
        if label in self.backup_data:
            bid, location = self.backup_data[label]
            if bid == self.current_backupId:
                # original db value
                self.location_input.set_value(self.current_location or location or "")
            else: 
                self.location_input.set_value(location or "")
        
    def _get_selected_backup(self):
        """Return (backup_drive_id, backup_location) or (None, None)."""
        label = self.backup_selector.value
        if label and label in self.backup_data:
            return self.backup_data[label]
        return None, None

    # =========================================================================
    # Folder selection
    # =========================================================================

    async def select_folder(self):
        if hasattr(webview, 'FileDialog'):
            folder_mode = webview.FileDialog.FOLDER
        else:
            folder_mode = webview.FOLDER_DIALOG

        # Start from the BackupDrive root so the user is one click away from
        # CALI_FRAME — fall back to any existing location value, then no hint.
        _, bd_location = self._get_selected_backup()
        start_dir = None
        if bd_location and os.path.exists(bd_location):
            start_dir = bd_location
        elif self.location_input.value and os.path.exists(self.location_input.value):
            start_dir = self.location_input.value

        if start_dir:
            folder = await app.native.main_window.create_file_dialog(
                folder_mode, allow_multiple=False, directory=start_dir)
        else:
            folder = await app.native.main_window.create_file_dialog(
                folder_mode, allow_multiple=False)

        if folder:
            self.location_input.value = os.path.normpath(folder[0])

    # =========================================================================
    # Save / Delete
    # =========================================================================

    def save_or_update_library(self):
        location = self.location_input.value.strip()
        if not location:
            ui.notify("Please set a CALI_FRAME location.", type="warning")
            return

        backup_drive_id, _ = self._get_selected_backup()
        if not backup_drive_id:
            ui.notify("Please select a Backup Drive.", type="warning")
            return

        name = self.library_name.value.strip() or os.path.basename(location)

        lib_id = get_or_create_DarkLibrary(
            self.conn, location, backup_drive_id, name=name
        )
        if lib_id:
            self.library_id = lib_id
            ui.notify("✅ Dark Library saved.", type="positive")
            self.refresh_library_list()
        else:
            ui.notify("❌ Failed to save library.", type="negative")

    async def confirm_and_delete_library(self):
        if not self.library_id:
            ui.notify("No library selected.", type="warning")
            return
        await self.WinLog.show(
            "Confirm Delete",
            "Delete this Dark Library record?\n"
            "(Dark files on disk are NOT deleted.)",
            self._do_delete_library,
        )

    def _do_delete_library(self):
        if delete_DarkLibrary(self.conn, self.library_id):
            ui.notify("Dark Library deleted.", type="positive")
            self.set_new_library()
            self.refresh_library_list()
        else:
            ui.notify("❌ Delete failed.", type="negative")

    # =========================================================================
    # Download (navigate to Transfer page with forced CALI_FRAME destination)
    # =========================================================================

    def navigate_to_download(self):
        location = self.location_input.value.strip()
        if not location or not self.library_id:
            ui.notify("Save the library first to set the CALI_FRAME location.", type="warning")
            return

        backup_drive_id, _ = self._get_selected_backup()
        dwarf_name = self.dwarf_selector.value
        dwarf_id   = self.dwarf_name_to_id.get(dwarf_name)

        # Build Transfer URL: Archive mode, correct Dwarf + BackupDrive.
        # dest_override sets the starting point for the destination picker
        # (the BackupDrive root) — user then navigates into CALI_FRAME themselves.
        import urllib.parse
        _, bd_location = self._get_selected_backup()
        # Destination starts at BackupDrive root — user picks where to copy.
        # The transfer will create CALI_FRAME as a subfolder (non-full-backup mode).
        params = {
            "mode":          "Archive",
            "dest_override":location or bd_location,
        }
        if dwarf_id:
            params["DwarfId"] = dwarf_id
        if backup_drive_id:
            params["BackupId"] = backup_drive_id

        # Add back URL so user can return to DarkLibrary
        back = f"/DarkLibrary?LibraryId={self.library_id}" if self.library_id else "/DarkLibrary"
        params["back_url"] = back

        url = "/Transfer?" + urllib.parse.urlencode(params)
        ui.navigate.to(url)

    # =========================================================================
    # Scan
    # =========================================================================

    def scan_library(self):
        location = self.location_input.value.strip()
        if not location or not self.library_id:
            ui.notify("Please set a CALI_FRAME location first.", type="warning")
            return
        if not os.path.isdir(location):
            ui.notify(f"❌ Folder not found: {location}", type="negative")
            return

        ui.run_javascript("document.body.style.cursor='wait'")
        result = scan_dark_library(location)
        ui.run_javascript("document.body.style.cursor='default'")

        # Update scan date if library is already saved
        if self.library_id:
            backup_drive_id, _ = self._get_selected_backup()
            get_or_create_DarkLibrary(self.conn, location, backup_drive_id)
            self.refresh_library_list()

        self._show_inventory(result)

    def _show_inventory(self, result: dict):
        self.inventory_card.visible = True
        self.inventory_container.clear()

        total = result["total"]
        errors = result["errors"]
        by_cam = result["by_cam"]

        with self.inventory_container:
            if total == 0:
                ui.label("⚠️ No dark files found matching the naming convention.").classes(
                    "text-orange-600")
                ui.label(
                    "Expected format: dark_exp_15.0_gain_80_bin_1_14C.fits"
                ).classes("text-xs text-gray-500 mt-1")
            else:
                ui.label(f"✅ {total} dark file(s) found.").classes("text-green-700 font-semibold")

            for cam_name, entries in by_cam.items():
                cam_label = "📷 Tele (cam_0)" if cam_name == "cam_0" else "📷 Wide (cam_1)"
                ui.label(cam_label).classes("font-semibold mt-3")
                ui.separator()

                # Group by exp/gain/binning for a clean summary
                groups: dict = {}
                for e in entries:
                    key = (e["exp_s"], e["gain"], e["binning"])
                    groups.setdefault(key, []).append(e["temp_c"])

                for (exp, gain, binning), temps in sorted(groups.items()):
                    temps_str = ", ".join(f"{t}°C" for t in sorted(temps))
                    ui.label(
                        f"  exp={exp}s  gain={gain}  bin={binning}  "
                        f"→  {len(temps)} file(s)  temps: {temps_str}"
                    ).classes("text-sm text-gray-700 ml-4")

            if errors:
                ui.separator()
                ui.label(f"⚠️ {len(errors)} file(s) with unrecognised names:").classes(
                    "text-orange-600 mt-2")
                for err in errors[:10]:
                    ui.label(f"  • {os.path.basename(err)}").classes(
                        "text-xs text-gray-500 ml-4")
                if len(errors) > 10:
                    ui.label(f"  … and {len(errors)-10} more").classes(
                        "text-xs text-gray-400 ml-4")