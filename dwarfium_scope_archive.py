# macOS packaging support
from multiprocessing import freeze_support  # noqa
freeze_support()  # noqa

from nicegui import native, app, ui

# Encoding changed to UTF-8
# Import page content (each file registers its own route)
import pages.home
import pages.dwarf_backup_ui_dwarf
import pages.dwarf_backup_ui_backup
import pages.dwarf_backup_ui_explore
import pages.dwarf_mtp_devices
import pages.dwarf_transfer
import pages.dwarf_transfer_usb
import pages.dwarf_dso_catalog

from api.image_preview import serve_preview
from api.dwarf_backup_db import DB_NAME, start_db, close_db
from api.dwarf_backup_db_api import insert_default_groups 

app.native.settings['ALLOW_DOWNLOADS'] = True

@app.get('/preview/{file_path:path}')
def preview_image(file_path: str):
    return serve_preview(file_path)

try:
    conn = start_db(DB_NAME)
    if not conn:
        print("❌ Application halted, fatal error Database.")
        exit
    else:
        #verify default data
        insert_default_groups(conn)
    close_db(conn)

    ui.run( title="Dwarfium Scope Archive",
            storage_secret='Dwarfiumscopearchive key to secure the browser session cookie',
            native=True, 
            window_size=(1200, 1024),
            port=native.find_open_port(),
            reload=False)

except (KeyboardInterrupt, SystemExit):
    print("🛑 Application closed by user.")