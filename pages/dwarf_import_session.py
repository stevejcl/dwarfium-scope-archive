"""Import one session from the Dwarf, then hand over to the Transfer page
(user-requested Oct 2026, link from Astro Dwarf Session's explorer and
View / Check dialogs).

/ImportSession?DwarfId=<id>&session=<session folder>[&DwarfIp=<ip>]

Same two steps as the Setup Dwarfs page's analysis, for this session
only: sync its stacked / shotsInfo files from the Dwarf (USB when its
astronomy folder is reachable, else - or not found there - FTP) into the
local Dwarf folder, then scan it into the database - the session is then registered. The
Transfer page opens next with it preselected (Archive mode); choosing
the backup drive and starting the copy stay with the user there.

Checked first (user-requested Oct 2026): a session already on a backup
drive (same rule as the Explore page) is shown with its drives, and the
import only starts when the user asks for it anyway.

DwarfIp (user-requested Oct 2026): the Dwarf's IP as Astro Dwarf Session
sees it, tried first for FTP before the Dwarf Configuration's IP and the
Dwarf's session IP (api/dwarf_session_ip.py), for this import and the
Transfer page that follows: a remote site's Astro Dwarf Session (Dwarf
reached through Tailscale) gives its own while the configured one stays
the local site's."""
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
from api.dwarf_session_ip import pick_ftp_ip
from api.dwarf_backup_fct_ftp import DWARF2_FTP_PATH, DWARF3_FTP_PATH, dwarf_ip_param, ftp_conn, ftp_sync_dwarf_sessions
from components.i18n import t
from components.menu import menu

# Dwarf.type in the database
_DWARF2_TYPE = 1


def _transfer_url(dwarf_id: int, session: str, dwarf_ip: str = "", via_ftp: bool = False) -> str:
    query = {"DwarfId": dwarf_id, "session": session, "mode": "Archive"}
    if dwarf_ip:
        query["DwarfIp"] = dwarf_ip
    if via_ftp:  # not on the USB drive: the copy by FTP too
        query["via"] = "FTP"
    return "/Transfer?" + urllib.parse.urlencode(query)


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


def _existing_backups(dwarf_id: int, session: str) -> list[dict]:
    """Backups already holding this session (same rule as the Explore
    page: a BackupEntry with this session_dir for this Dwarf), with each
    drive's name / location and whether the folder is still on it."""
    conn = connect_db(DB_NAME)
    if not conn:
        return []
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT bd.id, bd.name, bd.location, bd.astronomy_dir, be.session_dir, dd.file_path, be.id
            FROM BackupEntry be JOIN BackupDrive bd ON bd.id = be.backup_drive_id
            LEFT JOIN DwarfData dd ON dd.id = be.dwarf_data_id
            WHERE be.dwarf_id = ? AND (be.session_dir = ? OR be.session_dir LIKE ? OR be.session_dir LIKE ?)
            """,
            (dwarf_id, session, f"%/{session}", f"%\\{session}"),
        ).fetchall()
    except Exception:
        return []
    finally:
        close_db(conn)
    out = []
    seen = {}
    for drive_id, name, location, astro_dir, session_dir, file_path, entry_id in rows:
        # session_dir is the folder's name only: the session may sit in a
        # subfolder of the drive (user-reported Oct 2026: "folder not found
        # on the drive" for a session in a target's folder) - its stacked
        # image's path, relative to the drive (as api/session_move.py reads
        # it), gives the real folder
        folders = [os.path.join(location or "", astro_dir or "", session_dir or "")]
        if file_path:
            folders.insert(0, os.path.dirname(os.path.join(location or "", file_path)))
        present = bool(location) and any(os.path.isdir(f) for f in folders)
        if drive_id in seen:
            if present and not seen[drive_id]["present"]:
                seen[drive_id].update(present=True, entry_id=entry_id)
            continue
        seen[drive_id] = {
            "drive_id": drive_id,
            "name": name or location or "?",
            "location": location or "",
            "present": present,
            "entry_id": entry_id,
        }
        out.append(seen[drive_id])
    return out


def _import_session(dwarf_id: int, session: str, log, progress_cb, dwarf_ip: str = "") -> tuple[bool, str, bool]:
    """Blocking: sync + scan of one session. (ok, message key, read by FTP
    from a USB-plugged Dwarf - the Transfer page copies by FTP too). FTP
    goes to the first answering of dwarf_ip (the link's), the configured IP and
    the Dwarf's session IP."""
    conn = connect_db(DB_NAME)
    if not conn:
        return False, "import_session_db_error", False
    try:
        row = get_dwarf_detail(conn, dwarf_id)
        if not row:
            return False, "import_session_unknown_dwarf", False
        _name, _desc, usb_dir, dwarf_type, _scan_date, ip, _mtp = row
        local_main_dir = create_local_dwarf_dir(conn)
        if not local_main_dir:
            return False, "import_session_local_dir_error", False

        local_dwarf_dir = get_local_dwarf_dir(conn, dwarf_id)
        usb_dir = (usb_dir or "").strip()
        on_usb = bool(usb_dir) and os.path.isdir(usb_dir)
        if on_usb:
            log.push(f"🔌 USB: {usb_dir}")
            sync_dwarf_sessions(dwarf_id, usb_dir, local_main_dir, session, log, progress_cb)
        session_dir = _local_session_dir(local_dwarf_dir, session) if on_usb else None
        via_ftp = session_dir is None
        # Not on the USB drive: FTP too (user-seen Oct 2026: a megastack
        # made while plugged in - Windows still shows the drive as it was
        # when plugged, the new RESTACKED folder only after replugging,
        # FTP has it)
        if session_dir is None and (ftp_ip := pick_ftp_ip(dwarf_id, ip, dwarf_ip)):
            ftp_root = DWARF2_FTP_PATH if dwarf_type == _DWARF2_TYPE else DWARF3_FTP_PATH
            if on_usb:
                log.push(t("import_session_usb_missing"))
            log.push(f"🌐 FTP: {ftp_ip}{ftp_root}")
            with ftp_conn(ftp_ip) as ftp:
                if not ftp:
                    return False, "import_session_not_found" if on_usb else "import_session_not_connected", False
                ftp_sync_dwarf_sessions(ftp, dwarf_id, ftp_root, local_main_dir, session, log, progress_cb)
            session_dir = _local_session_dir(local_dwarf_dir, session)
        elif session_dir is None and not on_usb:
            return False, "import_session_not_connected", False
        if not session_dir:
            return False, "import_session_not_found", False
        scan_backup_folder(DB_NAME, local_dwarf_dir, None, dwarf_id, None, session_dir, log, progress_cb)
        return True, "import_session_done", on_usb and via_ftp
    finally:
        close_db(conn)


@ui.page('/ImportSession')
async def import_session_page(DwarfId: int = None, session: str = None, DwarfIp: str = None):
    menu(t("page_import_session"))
    dwarf_ip = dwarf_ip_param(DwarfIp)
    await ui.context.client.connected(timeout=10.0)

    with ui.column().classes("w-full max-w-4xl mx-auto p-4 gap-3"):
        if not DwarfId or not session:
            ui.label(t("import_session_missing_params")).classes("text-negative")
            return
        ui.label(t("import_session_title", session=session)).classes("text-lg font-medium")
        backup_box = ui.column().classes("w-full")
        spinner = ui.spinner(size="lg")
        progress_bar = ui.linear_progress(value=0, show_value=False).classes("w-full")
        progress_label = ui.label("").classes("text-sm text-gray-500")
        status_label = ui.label(t("import_session_running")).classes("text-sm")
        log = ui.log(max_lines=200).classes("w-full").style("height: 420px")
        with ui.row().classes("gap-2"):
            transfer_button = ui.button(
                t("import_session_open_transfer"),
                on_click=lambda: ui.navigate.to(_transfer_url(DwarfId, session, dwarf_ip)),
            ).props("color=primary")
            ui.button(t("page_dwarf"), on_click=lambda: ui.navigate.to(f"/Dwarf?DwarfId={DwarfId}")).props("flat")
        transfer_button.set_visibility(False)

    def _progress(current, done, total):
        try:
            progress_bar.set_value(done / total if total else 0)
            progress_label.set_text(f"[{done}/{total}] {current}")
        except Exception:
            pass

    def _show_progress(visible: bool) -> None:
        # Empty until an import starts (user-reported Oct 2026: shown
        # empty under the "already backed up" box, it looked broken)
        for element in (spinner, progress_bar, progress_label, status_label, log):
            element.set_visibility(visible)

    async def _run_import() -> None:
        _show_progress(True)
        status_label.set_text(t("import_session_running"))
        try:
            ok, key, via_ftp = await run.io_bound(_import_session, DwarfId, session, log, _progress, dwarf_ip)
        except Exception as e:  # FTP drop, copy error...: shown, never a blank page
            ok, key, via_ftp = False, "", False
            log.push(f"❌ {e}")
        spinner.set_visibility(False)
        progress_bar.set_value(1 if ok else 0)
        if ok:
            status_label.set_text(t(key))
            status_label.classes("text-positive")
            # The session is registered: on to the Transfer page, preselected
            ui.navigate.to(_transfer_url(DwarfId, session, dwarf_ip, via_ftp))
        else:
            status_label.set_text(t(key) if key else t("import_session_failed"))
            status_label.classes("text-negative")
            transfer_button.set_visibility(True)

    # Already backed up? Asked first, before reading anything on the Dwarf
    backups = await run.io_bound(_existing_backups, DwarfId, session)
    if not backups:
        await _run_import()
        return
    _show_progress(False)
    with backup_box:
        # Theme colours (readable in dark mode), an amber side border for the warning
        with ui.card().classes("w-full already-backed").style("border-left: 4px solid #f59e0b"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("inventory_2").classes("text-amber-600 text-xl")
                ui.label(t("import_session_already_backed")).classes("font-medium")
            for backup in backups:
                state = t("import_session_backup_present") if backup["present"] else t("import_session_backup_missing")
                ui.label(f"• {backup['name']} ({backup['location']}) - {state}").classes("text-sm")
            with ui.row().classes("gap-2 mt-1"):
                ui.button(
                    t("import_session_see_backups"),
                    # The session selected (user-reported Oct 2026: the
                    # Explorer opened without it) - on a drive holding it
                    on_click=lambda b=next((b for b in backups if b["present"]), backups[0]): ui.navigate.to(
                        f"/Explore/?BackupDriveId={b['drive_id']}&SessionId={b['entry_id']}&mode=backup"
                    ),
                ).props("flat color=primary")

                async def _anyway() -> None:
                    # Hidden, not cleared: this handler runs in its slot
                    backup_box.set_visibility(False)
                    await _run_import()

                ui.button(t("import_session_import_anyway"), on_click=_anyway).props("color=primary")
