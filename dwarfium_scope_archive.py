# macOS packaging support
from multiprocessing import freeze_support  # noqa
freeze_support()  # noqa

# Repair corrupted or empty storage BEFORE NiceGUI loads it
import pathlib, json as _json
_app_dir = pathlib.Path(__file__).parent
_storage_file = _app_dir / ".nicegui" / "storage-general.json"
if _storage_file.exists():
    try:
        _raw = _storage_file.read_text(encoding='utf-8').strip()
        if not _raw:
            raise ValueError("Empty file")
        _json.loads(_raw)
        print(f"[App] Storage file OK: {_storage_file}")
    except Exception as _e:
        print(f"[App] Corrupted/empty storage file detected — deleting: {_e}")
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

# Transient keys that must never survive a restart
_TRANSFER_KEYS = {
    'transfer_progress', 'transfer_copy_totals',
    'transfer_last_src', 'transfer_last_dest',
}

def _safe_storage_write(snapshot: dict) -> None:
    """Write snapshot to storage file atomically using tmp+replace.

    Called at the END of _on_app_shutdown, while still inside NiceGUI's async
    shutdown sequence — the event loop is still running so the file lock has
    been released by storage.on_shutdown which runs before our handler.
    Using tmp+replace ensures no half-written file on crash.
    """
    try:
        _storage_file.parent.mkdir(exist_ok=True)
        _tmp = _storage_file.with_suffix('.tmp')
        _tmp.write_text(_json.dumps(snapshot), encoding='utf-8')
        _tmp.replace(_storage_file)
        print(f"[App] Safe storage write complete ({len(snapshot)} keys).")
    except Exception as e:
        print(f"[App] Safe storage write error: {e}")

async def _on_app_shutdown():
    """Called on shutdown — clean up transient transfer keys and write storage safely.

    Problem: each pop() on app.storage.general triggers create_lazy() individually.
    Multiple pops in quick succession discard each other, leaving the file empty.
    Fix: single clear()+update() — one create_lazy trigger — then an immediate
    synchronous write while still inside the async shutdown sequence (file unlocked).

    We do NOT use the finally block of ui.run() because _on_app_shutdown runs
    asynchronously and may complete AFTER finally has already executed.
    """
    try:
        p = app.storage.general.get('transfer_progress', None)
        if p and p.get('status') in ('running', 'copy_done', 'scanning'):
            print("[App] Transfer in progress during shutdown — state will be cleared.")

        # Capture cleaned snapshot in memory
        snapshot = {k: v for k, v in app.storage.general.items()
                    if k not in _TRANSFER_KEYS}

        # Single atomic dict replacement: one _handle_change -> one create_lazy trigger
        app.storage.general.clear()
        if snapshot:
            app.storage.general.update(snapshot)

        print("[App] Storage cleanup complete.")

        # Write synchronously NOW — we are still inside NiceGUI's shutdown sequence,
        # the event loop is running, and storage.on_shutdown (registered before us)
        # has already released the file handle.
        _safe_storage_write(snapshot)

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