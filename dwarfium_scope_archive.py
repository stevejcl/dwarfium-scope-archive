from multiprocessing import freeze_support
import sys, pathlib as _pl, os as _os

# ── Windows build: redirect stdout/stderr to log file ────────────────────────
def _setup_logging():
    """Redirect print() and exceptions to a log file when running as PyInstaller exe."""
    if not getattr(sys, "frozen", False):
        return  # dev mode — keep console output as-is

    # Log file next to the exe: DwarfiumScopeArchive.log
    exe_dir = _pl.Path(sys.executable).parent
    log_path = exe_dir / "DwarfiumScopeArchive.log"

    import logging
    logging.basicConfig(
        filename=str(log_path),
        filemode="a",
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        encoding="utf-8",
    )

    # Redirect stdout / stderr to the log file
    import io
    class _LogWriter(io.TextIOBase):
        def __init__(self, level):
            self._level = level
        def write(self, msg):
            msg = msg.rstrip("\n")
            if msg:
                logging.log(self._level, msg)
            return len(msg)
        def flush(self):
            pass

    sys.stdout = _LogWriter(logging.INFO)
    sys.stderr = _LogWriter(logging.ERROR)

    # Catch unhandled exceptions
    def _excepthook(exc_type, exc_value, exc_tb):
        logging.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_tb))
    sys.excepthook = _excepthook

    logging.info(f"=== DwarfiumScopeArchive started (exe: {sys.executable}) ===")
    logging.info(f"Log file: {log_path}")

_setup_logging()

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
import argparse

# -------------------------
# CLI CONFIG
# -------------------------
parser = argparse.ArgumentParser()
parser.add_argument('--lan', action='store_true', help='Enable LAN access (binds to 0.0.0.0)')
parser.add_argument('--port', type=int, default=None, help='Port (default: auto in local, 8080 in LAN)')
args, _ = parser.parse_known_args()

LAN_MODE = args.lan
HOST = "0.0.0.0" if LAN_MODE else "127.0.0.1"
PORT = args.port if args.port else native.find_open_port()

# Global flag for app mode
ON_AIR = False
app.storage.general['ON_AIR'] = ON_AIR
app.storage.general['LAN_MODE'] = LAN_MODE
app.storage.general['LAN_PORT'] = PORT

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
import pages.page_sky_map

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
    """Called on shutdown — write cleaned storage directly to disk.

    We bypass app.storage.general modifications entirely to avoid triggering
    NiceGUI's async create_lazy() which would overwrite our file with an empty one.
    Instead we read the current state, filter transient keys, and write directly.
    """
    try:
        p = app.storage.general.get('transfer_progress', None)
        if p and p.get('status') in ('running', 'copy_done', 'scanning'):
            print("[App] Transfer in progress during shutdown — state will be cleared.")

        # Capture cleaned snapshot WITHOUT touching app.storage.general
        # (any modification triggers NiceGUI async write that races with ours)
        snapshot = {k: v for k, v in app.storage.general.items()
                    if k not in _TRANSFER_KEYS}

        print("[App] Storage cleanup complete.")

        # Write directly to disk — do NOT call clear()/update() on storage
        _safe_storage_write(snapshot)

    except Exception as e:
        print(f"[App] Shutdown storage cleanup error: {e}")

app.on_shutdown(_on_app_shutdown)

# Mobile responsive
ui.add_css('''
    /* Landscape mobile only — reduce font size */
    @media (max-width: 768px) and (orientation: landscape) {
        * { font-size: 85% !important; }
        .q-btn { min-height: 36px !important; }
    }
    /* Desktop: always show both columns, hide mobile nav bar */
    @media (min-width: 769px) {
        .mobile-nav-bar { display: none !important; }
        .mobile-left-col { display: flex !important; flex: 1 !important; }
        .mobile-right-col { display: flex !important; flex: 2 !important; }
    }
    /* Mobile: full width single column layout */
    @media (max-width: 768px) {
        .mobile-explore-grid {
            grid-template-columns: 1fr !important;
        }
        .mobile-left-col, .mobile-right-col {
            width: 100% !important;
            max-width: 100% !important;
            min-width: 0;
            grid-column: 1 / -1 !important;
            overflow-x: hidden !important;
        }
        /* Text overflow prevention */
        * { 
            word-break: break-word;
            overflow-wrap: break-word;
        }
        /* Fixed-width elements → full width on mobile */
        .w-32, .w-40, .w-46, .w-50, .w-55,
        .w-56, .w-58, .w-60, .w-64, .w-80, .w-96,
        .w-500, .w-700,
        [class*="min-w-["] {
            min-width: 0 !important;
            width: 100% !important;
            max-width: 100% !important;
        }
    }
''', shared=True)

if __name__ == '__main__':
    freeze_support()  # must be first statement in main guard
    try:
        ui.run( title="Dwarfium Scope Archive",
                storage_secret='Dwarfiumscopearchive key to secure the browser session cookie',
                native=True,
                window_size=(1200, 1024),
                host=HOST,
                port=PORT,
                reconnect_timeout=20,
                reload=False)

    except (KeyboardInterrupt):
        print("Application closed by user.")

    except SystemExit:
        print("Application closed.")

    except Exception as e:
        print(f"Application closed error detected {e}.")