# macOS packaging support
from multiprocessing import freeze_support  # noqa

from nicegui import native, app, ui

import sys
import asyncio
import logging

# Global flag for app mode
ON_AIR = False
app.storage.general['ON_AIR'] = ON_AIR

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
import pages.dwarf_backup_ui_dark_library

from api.image_preview import serve_preview

app.native.settings['ALLOW_DOWNLOADS'] = True

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Suppress the noisy ConnectionResetError from ProactorEventLoop
logging.getLogger("asyncio").setLevel(logging.CRITICAL)

@app.get('/preview/{file_path:path}')
def preview_image(file_path: str):
    return serve_preview(file_path)

if __name__ == '__main__':
    freeze_support()   # must be first statement in main guard
    try:
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

    except (SystemExit):
        print("Application closed.")

    except Exception as e:
        print(f"Application closed error detected {e}.")