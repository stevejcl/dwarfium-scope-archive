import webview
from nicegui import native, app, run, ui
import os

#from tkinter import filedialog, messagebox

from dwarf_backup_db import DB_NAME, connect_db, close_db, init_db
from dwarf_backup_fct import scan_backup_folder, insert_or_get_backup_drive 

from dwarf_backup_db_api import get_dwarf_Names, get_dwarf_detail, set_dwarf_detail, add_dwarf_detail
from dwarf_backup_db_api import get_session_present_in_Dwarf
from dwarf_backup_db_api import has_related_dwarf_entries, delete_dwarf_entries_and_dwarf_data, del_dwarf


@ui.page('/Dwarf')
def dwarf_settings():
    from components.menu import menu
    menu()

    # Launch the GUI
    ConfigApp(DB_NAME)
    #ui.context.client.on_disconnect(lambda: logger.removeHandler(handler))
    

class ConfigApp:
    def __init__(self, database):
        self.database = database
        self.dwarfs = []
        self.dwarf_id = None
        self.dwarf_type_map = {
            1: "Dwarf2",
            2: "Dwarf3"
        }

        dark = ui.dark_mode()
        dark.enable()
        self.build_ui()
        self.popup_title = "Title"
        self.popup_text = "Are you sure?"

        # Define a single yes/no dialog that gets re-used for all the popups.
        with ui.dialog() as self.popup_dialog, ui.card():
            # Bind the text for the question, so that when `self.popup_text`
            # gets updated by `show_popup`, the text in the dialog also gets
            # updated.
            ui.label().bind_text_from(self, "popup_title").classes("text-lg font-bold")
            ui.label().bind_text_from(self, "popup_text")
            with ui.row():
                ui.button("Yes", on_click=lambda: self.popup_dialog.submit("Yes"))
                ui.button("No", on_click=lambda: self.popup_dialog.submit("No"))

    async def show_popup(self, _popup_title: str, _popup_text: str, func):
        """Call this function to trigger the popup.

        The functon `func` is only called if "Yes" is clicked in the dialog.
        """
        self.popup_title = _popup_title
        self.popup_text = _popup_text
        result = await self.popup_dialog
        if result == "Yes":
            func()

    def build_ui(self):
        self.conn = connect_db(self.database)

        self.dwarf_type_name_to_id = {v: k for k, v in self.dwarf_type_map.items()}

        ui.label("Dwarf Config Page").classes("text-2xl font-bold my-4")

        with ui.card().classes("w-full max-w-3xl mx-auto"):
            with ui.grid(columns=2):
                ui.button("Show All Current Dwarf Data", on_click=lambda: ui.navigate.to(self.get_explore_url()))
                ui.button("Analyze USB Drive", on_click=self.analyze_usb_drive)

            ui.separator()

            with ui.row().classes('w-full gap-8 items-start'):
                with ui.column():
                    ui.button("➕ Add New Dwarf", on_click=self.set_new_dwarf)

                with ui.column():
                    ui.label("Select Existing Dwarf").classes("text-lg font-semibold")

                    # Dwarf Selection
                    self.dwarf_selector = ui.select(
                        options=[],
                        on_change=self.load_selected_dwarf,
                        label="Please select"
                    ).props('stack-label').props('outlined').classes('w-40')

                    with ui.grid(columns=2):
                        self.dwarf_name = ui.input("Dwarf Name")

                        ui.button("🗑️ Delete Fwarf", on_click=self.confirm_and_delete_Dwarf).props("color=red")

                    self.dwarf_desc = ui.input("Description")
                    with ui.grid(columns=2):
                        self.dwarf_astroDir = ui.input("Astronomy Directory")

                        ui.button("Select USB Folder", on_click=self.select_dwarf_folder)

                    # Dwarf Type selection
                    self.dwarf_type_var = ui.select(
                        options=list(self.dwarf_type_map.values()),
                        value="Dwarf3",
                        label="Type"
                    ).props('stack-label').props('outlined').classes('w-40')

                    with ui.row().classes("gap-4 mt-4"):
                         ui.button("Save / Update Dwarf", on_click=self.save_or_update_dwarf)
                         ui.button("🗑️ Delete Dwarf Entries", on_click=self.confirm_and_delete_dwarf_entries).props("color=red")

        self.refresh_dwarf_list()

    def refresh_dwarf_list(self):
        """Refresh the list of dwarfs and update the selection dropdown."""
        self.dwarfs = get_dwarf_Names(self.conn)

        # Create a list of tuples: (id, name)
        display_names = [f"{id} - {name}" for id, name in self.dwarfs]

        # Update the select options AND set a default value if needed
        if display_names:
            if self.dwarf_id and self.dwarf_selector.value and self.dwarf_id != int(self.dwarf_selector.value.split(" - ")[0]):
                # Find the display name that matches self.dwarf_id
                selected_value = next((name for id, name in self.dwarfs if id == self.dwarf_id), None)
                selected_display = f"{self.dwarf_id} - {selected_value}" if selected_value else display_names[0]
                self.dwarf_selector.set_options(display_names, value=selected_display)
            else:
                self.dwarf_selector.set_options(display_names)
        else:
            self.dwarf_selector.set_options([], value=None)

        # Update the dictionary mapping
        self.dwarf_name_to_id = {f"{id} - {name}": id for id, name in self.dwarfs}


    def load_selected_dwarf(self, event):
        """Load data when a dwarf is selected from the dropdown."""
        value = self.dwarf_selector.value
        print(f"value {value}")
        if not value:
            return
        try:
            self.dwarf_id = int(value.split(" - ")[0])  # Extracts "1" from "1 - Dwarf3"
        except (IndexError, ValueError):
            ui.notify("Invalid dwarf selection", type="negative")
            return

        row = get_dwarf_detail(self.conn, self.dwarf_id)
        if row:
            self.dwarf_name.value = row[0]
            self.dwarf_desc.value = row[1] or ""
            self.dwarf_astroDir.value = row[2] or ""
            self.dwarf_type_var.value = self.dwarf_type_map[int(row[3])]

    def set_new_dwarf(self):
        """Reset the form for adding a new dwarf."""
        self.dwarf_id = None
        self.dwarf_name.value = ""
        self.dwarf_desc.value = ""
        self.dwarf_astroDir.value = ""
        self.dwarf_type_var.value = self.dwarf_type_map[2]  # Default to Dwarf3

    async def select_dwarf_folder(self):
        """Open folder selection dialog."""
        dwarf_location = self.dwarf_astroDir.value
        if dwarf_location:
            folder = await app.native.main_window.create_file_dialog(webview.FOLDER_DIALOG, allow_multiple=False,directory=dwarf_location)
        else:
            folder = await app.native.main_window.create_file_dialog(webview.FOLDER_DIALOG, allow_multiple=False)
        if folder:
            ui.notify(folder[0])
            folder = os.path.normpath(folder[0])
            self.set_folder_path(folder)

    def set_folder_path(self, folder_path):
        """Set folder path."""
        self.dwarf_astroDir.value = folder_path

    def save_or_update_dwarf(self):
        """Save or update the dwarf data in the database."""
        name = self.dwarf_name.value
        desc = self.dwarf_desc.value
        usb_astronomy_dir = self.dwarf_astroDir.value
        selected_type = self.dwarf_type_var.value
        dtype = self.dwarf_type_name_to_id.get(selected_type, 1)

        if not name:
            ui.notify("Name is required", type="negative")
            return

        if self.dwarf_id:  # Update
            set_dwarf_detail(self.conn, name, desc, usb_astronomy_dir, dtype, self.dwarf_id)
            ui.notify(f"Dwarf '{name}' updated.", type="positive")
        else:  # Insert
            self.dwarf_id = add_dwarf_detail(self.conn, name, desc, usb_astronomy_dir, dtype)
            ui.notify(f"Dwarf '{name}' created with ID {self.dwarf_id}", type="positive")

        self.refresh_dwarf_list()

    async def analyze_usb_drive(self):
        """Analyze the USB drive and scan files."""
        if not self.dwarf_id:
            ui.notify("No Dwarf selected", type="negative")
            return

        dwarf_location = self.dwarf_astroDir.value.strip()
        if not dwarf_location:
            ui.notify("No USB location selected", type="negative")
            return

        # Dialog to block interaction and show progress
        with ui.dialog() as dialog, ui.card():
            ui.label("🔍 Scanning USB drive, please wait...")
            ui.spinner(size="lg")
            log = ui.log(max_lines=10).classes('w-full').style('height: 150px; overflow: hidden;')

        dialog.open()  # show the dialog

        try:
            ui.notify("Starting Analysis ...")
            total = await run.io_bound (scan_backup_folder, DB_NAME, dwarf_location, None, self.dwarf_id, None, log)
            ui.notify(f"✅ Analysis Complete:: {total} new files found.", type="positive")

        except Exception as e:
            ui.notify(f"❌ Error: {str(e)}", type="negative")

        finally:
            dialog.close()  # close dialog even if error occurs

    async def confirm_and_delete_Dwarf(self):
        if self.dwarf_id is None:
            ui.notify("No Dwarf selected", type="negative")
            return

        if has_related_dwarf_entries(self.conn, self.dwarf_id):
            ui.notify(
                "Cannot delete: this Dwarf is still linked to one or more backup entries. Please remove them first.",
                type="negative")
            return

        await self.show_popup(
            "Confirm Deletion",
            "Are you sure you want to delete this Dwarf?",
            self.ok_confirm_and_delete_dwarf
        )

    def ok_confirm_and_delete_dwarf(self):
        # Delete the Dwarf
        del_dwarf(self.conn, self.dwarf_id)

        print(f"Deleted Dwarf {self.dwarf_id}.")
        self.refresh_dwarf_list()
        self.set_new_dwarf()
        ui.notify("Dwarf deleted.", type="positive")

    async def confirm_and_delete_dwarf_entries(self):
        if self.dwarf_id is None:
            ui.notify("No Dwarf selected", type="negative")
            return

        await self.show_popup(
            "Confirm Deletion",
            "Are you sure you want to reset to defaults?",
            self.ok_confirm_and_delete_dwarf_entries
        )

    def ok_confirm_and_delete_dwarf_entries(self):
        delete_dwarf_entries_and_dwarf_data(self.conn, self.dwarf_id)
        ui.notify("DwarfData entries deleted.", type="positive")
 
    def get_explore_url(self):
        ui.notify("Showing Dwarf Data...")  # Simulate showing data
        if self.dwarf_id:
            explore_url = f"/Explore?DwarfId={self.dwarf_id}&mode=dwarf"
        else:
            explore_url = f"/Explore?mode=dwarf"
        print(explore_url)
        return explore_url
