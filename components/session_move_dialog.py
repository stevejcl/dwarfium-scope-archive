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
    session_image_path, get_backup_session, get_object_backup_sessions, get_dwarf_archives,
    list_subfolders, suggested_subfolders, count_attached_data,
    validate_subfolder_name, move_backup_session,
)
from api.dso_association import (
    load_catalog_index, check_sessions, parse_coords, make_thumbnail_data_url,
    INCONSISTENT_DEFAULT_DEG,
)
from components.i18n import t


def _location_label(session):
    return f"📁 {session['subfolder']}" if session["subfolder"] else t("move_root")


async def show_object_sessions_dialog(database, astro_object_id, title, on_done=None):
    """Archive sessions of an object (or group), each with a Move button.
    "Check consistency" only annotates the list: catalog object detected at
    each session's RA/DEC, sessions too far from the object / group."""
    def _load():
        conn = connect_db(database)
        try:
            return get_object_backup_sessions(conn, astro_object_id)
        finally:
            close_db(conn)
    sessions = await run.io_bound(_load)
    state = {"check": None}

    with ui.dialog() as dialog, ui.card().style("width: 900px; max-width: 95vw"):
        ui.label(t("move_sessions_title", name=title)).classes("text-xl font-semibold")
        with ui.row().classes("w-full items-end gap-4"):
            threshold = ui.number(t("dso_check_threshold"), value=INCONSISTENT_DEFAULT_DEG,
                                  min=0.1, max=90, step=0.5, format="%.1f").classes("w-40")
            check_btn = ui.button(t("dso_check_open"), icon="rule").props("flat")
            summary = ui.label("").classes("text-sm")

        @ui.refreshable
        def session_list():
            if not sessions:
                ui.label(t("move_no_session"))
            check = state["check"]
            for s in sessions:
                info = check["sessions"].get(s["entry_id"]) if check else None
                with ui.row().classes("w-full items-center justify-between no-wrap"):
                    with ui.column().classes("gap-0"):
                        ui.label(s["session_name"]).classes("text-sm font-medium break-all")
                        ui.label(f"🔭 {s['dwarf_name'] or '?'} · 💾 {s['drive_name']} · "
                                 f"{_location_label(s)} · ⭐ {s['object_name'] or ''}"
                                 ).classes("text-xs text-gray-500")
                        if info:
                            _check_label(info, check["reference"])

                    async def _move(entry_id=s["entry_id"]):
                        async def _moved():
                            dialog.close()
                            if on_done:
                                on_done()
                        await show_move_session_dialog(database, entry_id, on_done=_moved)
                    with ui.row().classes("gap-1 no-wrap"):
                        ui.button(icon="image", on_click=lambda s=s, info=info: show_session_image(s, info)
                                  ).props("flat dense").tooltip(t("preview_image"))
                        ui.button(t("move_button"), icon="drive_file_move", on_click=_move).props("flat dense")

        with ui.column().classes("w-full gap-2").style("max-height: 65vh; overflow-y: auto"):
            session_list()

        async def _check():
            def _run():
                conn = connect_db(database)
                try:
                    index = load_catalog_index(conn)
                    return check_sessions(conn, index, astro_object_id, sessions,
                                          float(threshold.value or INCONSISTENT_DEFAULT_DEG))
                finally:
                    close_db(conn)
            check_btn.disable()
            try:
                state["check"] = await run.io_bound(_run)
            finally:
                check_btn.enable()
            bad = sum(1 for i in state["check"]["sessions"].values() if i["inconsistent"])
            ref = state["check"]["reference"]
            if not ref:
                summary.text = t("check_no_reference")
                summary.classes(replace="text-sm text-gray-500")
            else:
                ref_txt = ref[1] if ref[0] == "dso" else t("check_ref_medoid")
                summary.text = t("check_summary", count=bad, reference=ref_txt)
                summary.classes(replace="text-sm " + ("text-orange-600" if bad else "text-green-700"))
            session_list.refresh()
        check_btn.on_click(_check)

        with ui.row().classes("w-full justify-end"):
            ui.button(t("close"), on_click=dialog.close).props("flat")
    dialog.open()


def _is_wide_field(session):
    name = (session.get("session_name") or "").upper()
    return "_WIDE_" in name or "_MOSAIC_" in name


async def show_session_image(session, info=None):
    """Larger view of the session's stacked image, to check a wide-angle or
    mosaic field when several catalog objects are close."""
    path = await run.io_bound(session_image_path, session)
    image = await run.io_bound(make_thumbnail_data_url, path, 1600) if path else None
    with ui.dialog() as dialog, ui.card().style("width: 1100px; max-width: 95vw"):
        ui.label(session["session_name"]).classes("text-sm font-medium break-all")
        ui.label(f"🔭 {session.get('dwarf_name') or '?'} · 💾 {session['drive_name']} · "
                 f"{_location_label(session)} · ⭐ {session.get('object_name') or ''}"
                 ).classes("text-xs text-gray-500")
        if info:
            _check_label(info, None)
        if image:
            ui.image(image).classes("w-full rounded").style("max-height: 75vh; object-fit: contain")
        else:
            ui.label(t("dso_wizard_no_image")).classes("text-sm text-orange-600")
        with ui.row().classes("w-full justify-end gap-2"):
            coords = parse_coords(session.get("ra"), session.get("dec"))
            if coords:
                fov = 10 if _is_wide_field(session) else 3
                url = (f"https://aladin.cds.unistra.fr/AladinLite/?target="
                       f"{coords[0]:.5f}+{coords[1]:+.5f}&fov={fov}&survey=P%2FDSS2%2Fcolor")
                ui.button("Aladin", icon="public",
                          on_click=lambda u=url: ui.navigate.to(u, new_tab=True)).props("flat")
            ui.button(t("close"), on_click=dialog.close).props("flat")
    dialog.open()


def _check_label(info, reference):
    if info["no_coords"]:
        ui.label(t("check_no_coords")).classes("text-xs text-gray-500")
        return
    d = info["detected"]
    if d:
        # First common name only, and not when it repeats the designation
        name = (d["name"] or "").split(",")[0].strip()
        detected = d["designation"] + (f" — {name}" if name and name != d["designation"] else "")
    else:
        detected = t("check_nothing_nearby")
    text = t("check_detected", detected=detected)
    if info["separation_deg"] is not None:
        text += " · " + t("check_distance", sep=f"{info['separation_deg']:.1f}")
    if info["inconsistent"]:
        ui.label(f"⚠️ {text}").classes("text-xs font-semibold text-orange-600")
    else:
        ui.label(text).classes("text-xs text-gray-600")


async def show_move_session_dialog(database, backup_entry_id, on_done=None):
    """Choose the destination of one archive session and move it."""
    def _load():
        conn = connect_db(database)
        try:
            session = get_backup_session(conn, backup_entry_id)
            if not session:
                return None, [], {}, {}, None
            archives = get_dwarf_archives(conn, session["dwarf_id"])
            folders = {}
            for a in archives:
                existing = list_subfolders(a["data_root"]) if a["available"] else []
                suggested = suggested_subfolders(conn, a["id"], session["astro_object_id"],
                                                 exclude_entry_id=backup_entry_id)
                folders[a["id"]] = (existing, [f for f in suggested if f in existing])
            thumb = make_thumbnail_data_url(session_image_path(session), 480)
            return session, archives, folders, count_attached_data(conn, backup_entry_id), thumb
        finally:
            close_db(conn)
    session, archives, folders, attached, thumb = await run.io_bound(_load)
    if not session:
        ui.notify(t("move_err_not_found"), type="negative")
        return

    with ui.dialog().props("persistent") as dialog, ui.card().style("width: 720px; max-width: 95vw"):
        ui.label(t("move_title")).classes("text-xl font-semibold")
        ui.label(session["session_name"]).classes("text-sm font-medium break-all")
        ui.label(t("move_current", drive=f"🔭 {session['dwarf_name'] or '?'} · {session['drive_name']}",
                   location=_location_label(session))).classes("text-sm text-gray-500")
        if thumb:
            # Click to check the field in a larger view
            ui.image(thumb).classes("w-full rounded cursor-pointer").style(
                "max-height: 220px; object-fit: contain").on(
                "click", lambda: show_session_image(session)).tooltip(t("preview_image"))

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
