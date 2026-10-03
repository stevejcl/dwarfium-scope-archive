"""
components/session_move_dialog.py

Catalog Edition — move a session folder inside the archives of its Dwarf
(root, existing sub-folder or new sub-folder, same or other archive). The
folder is never renamed; the database is updated by the backup scan run on
the moved folder only (see api/session_move.py).
"""

from nicegui import ui, run

from api.dwarf_backup_db import connect_db, close_db
from api.session_move import (
    get_backup_session, get_object_backup_sessions, get_dwarf_archives,
    list_subfolders, suggested_subfolders, count_attached_data,
    validate_subfolder_name, move_backup_session,
)
from components.i18n import t


def _location_label(session):
    return f"📁 {session['subfolder']}" if session["subfolder"] else t("move_root")


async def show_object_sessions_dialog(database, astro_object_id, title, on_done=None):
    """Archive sessions of an object (or group), each with a Move button."""
    def _load():
        conn = connect_db(database)
        try:
            return get_object_backup_sessions(conn, astro_object_id)
        finally:
            close_db(conn)
    sessions = await run.io_bound(_load)

    with ui.dialog() as dialog, ui.card().style("width: 860px; max-width: 95vw"):
        ui.label(t("move_sessions_title", name=title)).classes("text-xl font-semibold")
        if not sessions:
            ui.label(t("move_no_session"))
        for s in sessions:
            with ui.row().classes("w-full items-center justify-between no-wrap"):
                with ui.column().classes("gap-0"):
                    ui.label(s["session_name"]).classes("text-sm font-medium break-all")
                    ui.label(f"💾 {s['drive_name']} · {_location_label(s)} · "
                             f"⭐ {s['object_name'] or ''}").classes("text-xs text-gray-500")

                async def _move(entry_id=s["entry_id"]):
                    async def _moved():
                        dialog.close()
                        if on_done:
                            on_done()
                    await show_move_session_dialog(database, entry_id, on_done=_moved)
                ui.button(t("move_button"), icon="drive_file_move", on_click=_move).props("flat dense")
        with ui.row().classes("w-full justify-end"):
            ui.button(t("close"), on_click=dialog.close).props("flat")
    dialog.open()


async def show_move_session_dialog(database, backup_entry_id, on_done=None):
    """Choose the destination of one archive session and move it."""
    def _load():
        conn = connect_db(database)
        try:
            session = get_backup_session(conn, backup_entry_id)
            if not session:
                return None, [], {}, {}
            archives = get_dwarf_archives(conn, session["dwarf_id"])
            folders = {}
            for a in archives:
                existing = list_subfolders(a["data_root"]) if a["available"] else []
                suggested = suggested_subfolders(conn, a["id"], session["astro_object_id"],
                                                 exclude_entry_id=backup_entry_id)
                folders[a["id"]] = (existing, [f for f in suggested if f in existing])
            return session, archives, folders, count_attached_data(conn, backup_entry_id)
        finally:
            close_db(conn)
    session, archives, folders, attached = await run.io_bound(_load)
    if not session:
        ui.notify(t("move_err_not_found"), type="negative")
        return

    with ui.dialog().props("persistent") as dialog, ui.card().style("width: 720px; max-width: 95vw"):
        ui.label(t("move_title")).classes("text-xl font-semibold")
        ui.label(session["session_name"]).classes("text-sm font-medium break-all")
        ui.label(t("move_current", drive=session["drive_name"],
                   location=_location_label(session))).classes("text-sm text-gray-500")

        archive_options = {
            a["id"]: a["name"] + ("" if a["available"] else f" — {t('move_unavailable')}")
            for a in archives}
        archive = ui.select(archive_options, label=t("move_archive"),
                            value=session["backup_drive_id"]).classes("w-full")

        mode = ui.radio({"root": t("move_root"), "existing": t("move_existing"),
                         "new": t("move_new")}, value="existing").props("inline")
        existing = ui.select({}, label=t("move_existing_folder"), with_input=True).classes("w-full")
        new_name = ui.input(t("move_new_folder"), value=session["object_name"] or "").classes("w-full")

        def _refresh_folders():
            all_folders, suggested = folders.get(archive.value, ([], []))
            opts = {f: f"★ {f}" for f in suggested}
            opts.update({f: f for f in all_folders if f not in opts})
            # The current folder is not a destination
            if archive.value == session["backup_drive_id"] and session["subfolder"]:
                opts.pop(session["subfolder"], None)
            existing.set_options(opts, value=next(iter(opts), None))
            if not opts and mode.value == "existing":
                mode.value = "new"

        def _refresh_mode():
            existing.set_visibility(mode.value == "existing")
            new_name.set_visibility(mode.value == "new")

        archive.on_value_change(lambda e: _refresh_folders())
        mode.on_value_change(lambda e: _refresh_mode())
        _refresh_folders()
        _refresh_mode()

        if attached["notes"] or attached["wcs"]:
            ui.label(t("move_attached_warning", notes=attached["notes"], wcs=attached["wcs"])
                     ).classes("text-sm text-gray-600")
        ui.label(t("move_scan_info")).classes("text-xs text-gray-500")
        log = ui.log(max_lines=200).classes("w-full h-32")
        log.set_visibility(False)

        async def _do_move():
            if mode.value == "root":
                sub = None
            elif mode.value == "existing":
                sub = existing.value
                if not sub:
                    ui.notify(t("move_err_name"), type="negative")
                    return
            else:
                sub = (new_name.value or "").strip()
                err = validate_subfolder_name(sub)
                if err:
                    ui.notify(t(err), type="negative")
                    return
            drive = next((a for a in archives if a["id"] == archive.value), None)
            if not drive or not drive["available"]:
                ui.notify(t("move_err_dst_missing"), type="negative")
                return
            move_btn.disable()
            cancel_btn.disable()
            log.set_visibility(True)
            result = await run.io_bound(move_backup_session, database, backup_entry_id,
                                        archive.value, sub, log)
            cancel_btn.enable()
            if result["ok"]:
                ui.notify(t("move_done", path=result["dst_path"]), type="positive")
                dialog.close()
                if on_done:
                    res = on_done()
                    if hasattr(res, "__await__"):
                        await res
            else:
                ui.notify(t(result["error"] or "move_err_io"), type="negative", timeout=8000)
                if result["error"] != "move_err_scan":
                    move_btn.enable()

        with ui.row().classes("w-full justify-end gap-2"):
            cancel_btn = ui.button(t("cancel"), on_click=dialog.close).props("flat")
            move_btn = ui.button(t("move_button"), icon="drive_file_move", color="positive",
                                 on_click=_do_move)
    dialog.open()
