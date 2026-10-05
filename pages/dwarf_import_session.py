"""Import one session from the Dwarf, then hand over to the Transfer page
(user-requested Oct 2026, link from Astro Dwarf Session's explorer and
View / Check dialogs).

/ImportSession?DwarfId=<id>&session=<session folder>

Same two steps as the Setup Dwarfs page's analysis, for this session
only: sync its stacked / shotsInfo files from the Dwarf (USB when its
astronomy folder is reachable, else FTP) into the local Dwarf folder,
then scan it into the database - the session is then registered. The
Transfer page opens next with it preselected (Archive mode); choosing
the backup drive and starting the copy stay with the user there."""
from __future__ import annotations

import os
import urllib.parse

from nicegui import run, ui

from api.dwarf_backup_db import DB_NAME, connect_db, close_db
from api.dwarf_backup_db_api import get_dwarf_detail
from api.dwarf_backup_fct import (
    create_local_dwarf_dir,
    get_local_dwarf_dir,
    scan_backup_folder,
    sync_dwarf_sessions,
)
from api.dwarf_backup_fct_ftp import DWARF2_FTP_PATH, DWARF3_FTP_PATH, ftp_conn, ftp_sync_dwarf_sessions
from components.i18n import t
from components.menu import menu

# Dwarf.type in the database
_DWARF2_TYPE = 1


def _transfer_url(dwarf_id: int, session: str) -> str:
    return "/Transfer?" + urllib.parse.urlencode({"DwarfId": dwarf_id, "session": session, "mode": "Archive"})


def _local_session_dir(local_dwarf_dir: str, session: str) -> str | None:
    """Where the sync put the session: under RESTACKED / STARTRAILS or at
    the top of the local Dwarf folder."""
    for candidate in (
        os.path.join(local_dwarf_dir, "RESTACKED", session),
        os.path.join(local_dwarf_dir, "STARTRAILS", session),
        os.path.join(local_dwarf_dir, session),
    ):
        if os.path.isdir(candidate):
            return candidate
    return None


def _import_session(dwarf_id: int, session: str, log, progress_cb) -> tuple[bool, str]:
    """Blocking: sync + scan of one session. (ok, message key)."""
    conn = connect_db(DB_NAME)
    if not conn:
        return False, "import_session_db_error"
    try:
        row = get_dwarf_detail(conn, dwarf_id)
        if not row:
            return False, "import_session_unknown_dwarf"
        _name, _desc, usb_dir, dwarf_type, _scan_date, ip, _mtp = row
        local_main_dir = create_local_dwarf_dir(conn)
        if not local_main_dir:
            return False, "import_session_local_dir_error"

        usb_dir = (usb_dir or "").strip()
        if usb_dir and os.path.isdir(usb_dir):
            log.push(f"🔌 USB: {usb_dir}")
            sync_dwarf_sessions(dwarf_id, usb_dir, local_main_dir, session, log, progress_cb)
        elif ip:
            ftp_root = DWARF2_FTP_PATH if dwarf_type == _DWARF2_TYPE else DWARF3_FTP_PATH
            log.push(f"🌐 FTP: {ip}{ftp_root}")
            with ftp_conn(ip) as ftp:
                if not ftp:
                    return False, "import_session_not_connected"
                ftp_sync_dwarf_sessions(ftp, dwarf_id, ftp_root, local_main_dir, session, log, progress_cb)
        else:
            return False, "import_session_not_connected"

        local_dwarf_dir = get_local_dwarf_dir(conn, dwarf_id)
        session_dir = _local_session_dir(local_dwarf_dir, session)
        if not session_dir:
            return False, "import_session_not_found"
        scan_backup_folder(DB_NAME, local_dwarf_dir, None, dwarf_id, None, session_dir, log, progress_cb)
        return True, "import_session_done"
    finally:
        close_db(conn)


@ui.page('/ImportSession')
async def import_session_page(DwarfId: int = None, session: str = None):
    menu(t("page_import_session"))
    await ui.context.client.connected(timeout=10.0)

    with ui.column().classes("w-full max-w-4xl mx-auto p-4 gap-3"):
        if not DwarfId or not session:
            ui.label(t("import_session_missing_params")).classes("text-negative")
            return
        ui.label(t("import_session_title", session=session)).classes("text-lg font-medium")
        spinner = ui.spinner(size="lg")
        progress_bar = ui.linear_progress(value=0, show_value=False).classes("w-full")
        progress_label = ui.label("").classes("text-sm text-gray-500")
        status_label = ui.label(t("import_session_running")).classes("text-sm")
        log = ui.log(max_lines=200).classes("w-full").style("height: 420px")
        with ui.row().classes("gap-2"):
            transfer_button = ui.button(
                t("import_session_open_transfer"),
                on_click=lambda: ui.navigate.to(_transfer_url(DwarfId, session)),
            ).props("color=primary")
            ui.button(t("page_dwarf"), on_click=lambda: ui.navigate.to(f"/Dwarf?DwarfId={DwarfId}")).props("flat")
        transfer_button.set_visibility(False)

    def _progress(current, done, total):
        try:
            progress_bar.set_value(done / total if total else 0)
            progress_label.set_text(f"[{done}/{total}] {current}")
        except Exception:
            pass

    try:
        ok, key = await run.io_bound(_import_session, DwarfId, session, log, _progress)
    except Exception as e:  # FTP drop, copy error...: shown, never a blank page
        ok, key = False, ""
        log.push(f"❌ {e}")
    spinner.set_visibility(False)
    progress_bar.set_value(1 if ok else 0)
    if ok:
        status_label.set_text(t(key))
        status_label.classes("text-positive")
        # The session is registered: on to the Transfer page, preselected
        ui.navigate.to(_transfer_url(DwarfId, session))
    else:
        status_label.set_text(t(key) if key else t("import_session_failed"))
        status_label.classes("text-negative")
        transfer_button.set_visibility(True)
