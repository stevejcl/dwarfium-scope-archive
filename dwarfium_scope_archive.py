# macOS packaging support
from multiprocessing import freeze_support  # noqa
freeze_support()  # noqa

from nicegui import native, app, ui

import sys

# Global flag for app mode
ON_AIR = False

# Make it accessible everywhere
app.storage.general['ON_AIR'] = ON_AIR

# Encoding changed to UTF-8
# Import page content (each file registers its own route)
import pages.dwarf_backup_ui_dwarf
import pages.home
import pages.dwarf_backup_ui_backup
import pages.dwarf_backup_ui_explore
import pages.dwarf_mtp_devices
import pages.dwarf_transfer
import pages.dwarf_transfer_usb
import pages.dwarf_mosaic
import pages.dwarf_add_manual_session
import pages.dwarf_backup_ui_manual_explore
import pages.dwarf_dso_catalog
import pages.astro_settings

from api.image_preview import serve_preview
from api.dwarf_backup_db import DB_NAME, start_db, close_db
from api.dwarf_backup_db_api import insert_default_groups 

app.native.settings['ALLOW_DOWNLOADS'] = True

import asyncio
import logging

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Suppress the noisy ConnectionResetError from ProactorEventLoop
logging.getLogger("asyncio").setLevel(logging.CRITICAL)

@app.get('/preview/{file_path:path}')
def preview_image(file_path: str):
    return serve_preview(file_path)

try:
    conn = start_db(DB_NAME)
    if not conn:
        print("[FAIL] Application halted, fatal error Database.")
        sys.exit(1)
    else:
        #verify default data
        insert_default_groups(conn)
    close_db(conn)

    ui.run( title="Dwarfium Scope Archive",
            storage_secret='Dwarfiumscopearchive key to secure the browser session cookie',
            native=True, 
            window_size=(1200, 1024),
            port=native.find_open_port(),
            reconnect_timeout=20,
#            host="0.0.0.0",
            reload=False)

except (KeyboardInterrupt):
    print("Application closed by user.")
    pass

except Exception as e:
    print(f"Application closed error detected {e}.")
    
except (SystemExit):
    print("Application closed.")
    pass

    pass