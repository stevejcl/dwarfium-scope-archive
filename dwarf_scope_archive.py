from nicegui import native, ui

# Import page content (each file registers its own route)
import pages.home
import pages.dwarf_backup_ui_dwarf
import pages.dwarf_backup_ui_backup
import pages.dwarf_backup_ui_explore

ui.run(native=True,port=native.find_open_port())