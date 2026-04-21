# macOS packaging support
from multiprocessing import freeze_support  # noqa
freeze_support()  # noqa

# Repair corrupted storage BEFORE NiceGUI loads it
import pathlib, json as _json
_app_dir = pathlib.Path(__file__).parent
_storage_file = _app_dir / ".nicegui" / "storage-general.json"
if _storage_file.exists():
    try:
        _json.loads(_storage_file.read_text(encoding='utf-8'))
        print(f"[App] Storage file OK: {_storage_file}")
    except Exception as _e:
        print(f"[App] Corrupted storage file detected — deleting: {_e}")
        _storage_file.unlink()

from nicegui import native, app, ui, background_tasks

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

async def _on_app_shutdown():
    """Called on shutdown — log and clean up transfer state."""
    try:
        p = app.storage.general.get('transfer_progress', None)
        if p and p.get('status') in ('running', 'copy_done', 'scanning'):
            print("[App] Transfer in progress during shutdown — awaiting completion...")
        # Clean up ALL transfer keys to minimize storage size and prevent corruption
        for key in ('transfer_progress', 'transfer_copy_totals',
                    'transfer_last_src', 'transfer_last_dest'):
            app.storage.general.pop(key, None)
        print("[App] Storage cleanup complete.")
    except Exception as e:
        print(f"[App] Shutdown storage cleanup error: {e}")

app.on_shutdown(_on_app_shutdown)

try:
    ui.run( title="Dwarfium Scope Archive",
            storage_secret='Dwarfiumscopearchive key to secure the browser session cookie',
            native=True, 
            window_size=(1200, 1024),
            port=native.find_open_port(),
            reconnect_timeout=20,
            reload=False)

except (KeyboardInterrupt):
    print("Application closed by user.")

except Exception as e:
    print(f"Application closed error detected {e}.")
    
except (SystemExit):
    print("Application closed.")
    pass
finally:
    pass
