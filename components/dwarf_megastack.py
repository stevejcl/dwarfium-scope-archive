"""Megastack on the Dwarf (Explore, Dwarf mode, its Megastack button): the
Dwarf stacks its own sessions of a target together - or restacks a single
one - into Astronomy/RESTACKED/, like the official app's megastack - asked to Dwarfium Lite (Astro Dwarf
Session 3.2.6+, POST /api/megastack), which talks to the Dwarf, runs it as a
program and follows it (its device page, then its Results tab).

Its picker (open_picker) offers the object's sessions that can be: not a
megastack result, their FITS not known to be gone (cleaned by CleanFits) -
read on the Dwarf by USB, else the Storage Report's measure; Dwarfium Lite
checks them again over FTP. Then Dwarfium Lite must be running and know
this Dwarf, connected. The Dwarf checks the rest itself (filter, binning,
dark frames)."""
from __future__ import annotations

import os

import requests
from nicegui import run, ui

from api.dwarf_backup_db_api import get_dwarf_ble_id, get_dwarf_detail
from api.dwarf_backup_fct import count_fits_files, is_Restacked
from api.peer import peer_url
from components.i18n import t

_TIMEOUT_S = 15


def lite_dwarf_uid(lite: str, ble_id: str, ip: str) -> tuple[str | None, str]:
    """Blocking. (Dwarfium Lite's dwarfUid for this Dwarf, "" or the reason
    it can't be used: "unreachable", "unknown", "offline"). Matched by the
    Dwarf ID (its UID ends with it, e.g. DWARF_mini_19A608), else by IP."""
    try:
        devices = requests.get(f"{lite.rstrip('/')}/api/dwarfs", timeout=_TIMEOUT_S).json().get("devices") or []
    except (requests.RequestException, ValueError, AttributeError):
        return None, "unreachable"
    devices = [d for d in devices if not str(d.get("dwarfUid", "")).startswith("auto:")]
    match = None
    if ble_id:
        match = next((d for d in devices if str(d.get("dwarfUid", "")).upper().endswith("_" + ble_id.upper())), None)
    if match is None and ip:
        match = next((d for d in devices if d.get("ip") == ip), None)
    if match is None:
        return None, "unknown"
    if not match.get("connected"):
        return None, "offline"
    return match["dwarfUid"], ""


def post_megastack(lite: str, dwarf_uid: str, sessions: list[str], target: str) -> tuple[bool, str]:
    """Blocking. (started, Dwarfium Lite's error or "lite_old")."""
    try:
        response = requests.post(
            f"{lite.rstrip('/')}/api/megastack",
            json={"dwarfUid": dwarf_uid, "sessions": sessions, "target": target},
            timeout=_TIMEOUT_S,
        )
    except requests.RequestException as e:
        return False, str(e)
    if response.status_code == 404 and "unknown dwarfUid" not in response.text:
        return False, "lite_old"
    try:
        body = response.json()
    except ValueError:
        return False, response.text[:200]
    return bool(body.get("ok")), str(body.get("error") or "")


# Explore's Dwarf rows (get_ObjectSelect_dwarf): their columns used here
_EXP, _FILTER, _SHOTS, _USB_DIR, _DATE, _SESSION_DIR, _TARGET = 2, 4, 5, 6, 7, 8, 13


def is_mosaic(row: list) -> bool:
    return "_MOSAIC_" in str(row[_SESSION_DIR] or "")


def _measured_fits(conn, dwarf_id, session_dir: str) -> bool | None:
    """The Storage Report's measure (Measure the Dwarf): raw FITS still on
    the Dwarf, None when never measured."""
    try:
        row = conn.execute(
            """
            SELECT MAX(q.dwarf_size_bytes > q.dwarf_size_no_fits_bytes)
            FROM BackupEntry b JOIN SessionQuality q ON q.backup_entry_id = b.id
            WHERE b.session_dir = ? AND b.dwarf_id = ? AND q.dwarf_size_bytes IS NOT NULL
            """,
            (session_dir, dwarf_id),
        ).fetchone()
    except Exception:  # an older database without the measure's columns
        return None
    return None if not row or row[0] is None else bool(row[0])


def fits_state(conn, dwarf_id, row: list, session_path: str) -> bool | None:
    """Blocking. The session's raw FITS on the Dwarf: read in its folder when
    the Dwarf is plugged in USB (a mosaic's in its panels' subfolders), else
    the Storage Report's measure - the local copy (Dwarf_Local) has none.
    None: not known - offered, Dwarfium Lite checks them again over FTP."""
    usb = os.path.normpath(str(row[_USB_DIR] or "")) if row[_USB_DIR] else ""
    if usb and session_path and os.path.normpath(session_path).startswith(usb) and os.path.isdir(session_path):
        return bool(count_fits_files(session_path))
    return _measured_fits(conn, dwarf_id, str(row[_SESSION_DIR] or ""))


def _thumbnail(session_path: str) -> str | None:
    for name in ("stacked_thumbnail.jpg", "stacked.jpg", "stacked.jpeg"):
        path = os.path.join(session_path, name)
        if session_path and os.path.isfile(path):
            return path
    return None


def _candidates(conn, dwarf_id, rows: list[list], paths: list[str]) -> tuple[list[dict], int]:
    """Blocking. (the sessions that can be megastacked - not a megastack
    result, their FITS not known to be gone - sorted by target A-Z then
    newest first, the number left out)."""
    out, skipped = [], 0
    for row, path in zip(rows, paths):
        session_dir = str(row[_SESSION_DIR] or "")
        folder = os.path.dirname(path) if path else ""
        if is_Restacked(session_dir):
            skipped += 1
            continue
        fits = fits_state(conn, dwarf_id, row, folder)
        if fits is False:
            skipped += 1
            continue
        out.append({
            "row": row, "name": session_dir, "target": str(row[_TARGET] or "").strip() or "?",
            "date": str(row[_DATE] or ""), "shots": int(row[_SHOTS] or 0), "fits": fits,
            "exp": str(row[_EXP] or ""), "filter": str(row[_FILTER] or ""),
            "mosaic": is_mosaic(row), "thumbnail": _thumbnail(folder),
        })
    out.sort(key=lambda c: c["date"], reverse=True)
    out.sort(key=lambda c: c["target"].casefold())
    return out, skipped


async def open_picker(conn, dwarf_id, rows: list[list], paths: list[str]) -> None:
    """Explore's Megastack button (user-requested Oct 2026, like Dwarfium
    Lite's Explorer): the selected object's sessions that can be
    megastacked - not a megastack result, nor one whose FITS are gone -
    grouped by target with their thumbnails; a click selects one (of a
    single target, single captures or mosaics - not mixed; one alone: the
    Dwarf restacks it), then Megastack asks Dwarfium Lite for it."""
    candidates, skipped = await run.io_bound(_candidates, conn, dwarf_id, rows, paths)
    selected: dict[str, dict] = {}
    tiles: dict[str, ui.element] = {}

    with ui.dialog() as dialog, ui.card().classes("p-4 gap-3 w-full max-w-screen-lg").style("min-height: 60vh"):
        ui.label(t("megastack_title_short")).classes("text-base font-medium")
        if not candidates:
            ui.label(t("megastack_pick_none")).classes("text-sm")
        else:
            ui.label(t("megastack_pick_hint")).classes("text-sm text-grey-7")
        if skipped:
            ui.label(t("megastack_pick_skipped", count=skipped)).classes("text-xs text-grey-6")

        with ui.scroll_area().classes("w-full").style("max-height: 60vh; min-height: 300px"):
            target = None
            row_box = None
            for cand in candidates:
                if cand["target"] != target:
                    target = cand["target"]
                    count = sum(1 for c in candidates if c["target"] == target)
                    ui.label(f"{target} ({count})").classes("text-sm font-medium mt-2")
                    row_box = ui.row().classes("w-full gap-3")
                with row_box:
                    with ui.column().classes("w-32 gap-1 cursor-pointer rounded p-1") as tile:
                        if cand["thumbnail"]:
                            ui.image(cand["thumbnail"]).classes("w-full aspect-square rounded").props("fit=cover")
                        else:
                            ui.icon("image_not_supported").classes("w-full text-5xl text-grey-5 text-center")
                        ui.label(cand["date"][:16]).classes("text-xs text-center w-full truncate")
                        # Its images, exposure and filter (user-requested Oct 2026:
                        # "20 img" unclear; the Dwarf refuses mixed filters)
                        ui.label(t("megastack_pick_stacked", count=cand["shots"])).classes(
                            "text-xs text-center w-full truncate"
                        )
                        bits = [f"{cand['exp']}s"] if cand["exp"] else []
                        if cand["filter"]:
                            bits.append(cand["filter"])
                        ui.label(" · ".join(bits)).classes("text-xs text-center text-grey-6 w-full truncate")
                    tile.tooltip(cand["name"])
                    tiles[cand["name"]] = tile
                    tile.on("click", lambda _e, c=cand: toggle(c))

        summary = ui.label("").classes("text-sm").style("white-space: pre-line")
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button(t("cancel"), on_click=dialog.close).props("flat color=grey")
            go = ui.button(t("megastack_start"), icon="auto_awesome_motion").props("color=primary")

    def refresh() -> None:
        go.set_enabled(bool(selected))
        if not selected:
            summary.set_text("")
            return
        first = next(iter(selected.values()))
        shots = sum(c["shots"] for c in selected.values())
        summary.set_text(t("megastack_confirm", count=len(selected), shots=shots, target=first["target"]))

    def toggle(cand: dict) -> None:
        name = cand["name"]
        if name in selected:
            del selected[name]
            tiles[name].classes(remove="ring-4 ring-primary")
        else:
            first = next(iter(selected.values()), None)
            if first and first["target"] != cand["target"]:
                ui.notify(t("megastack_one_target", targets=f"{first['target']}, {cand['target']}"), type="warning")
                return
            if first and first["mosaic"] != cand["mosaic"]:
                ui.notify(t("megastack_mixed"), type="warning")
                return
            selected[name] = cand
            tiles[name].classes(add="ring-4 ring-primary")
        refresh()

    async def confirmed() -> None:
        go.disable()
        ok = await start(conn, dwarf_id, [c["row"] for c in selected.values()])
        if ok:
            dialog.close()
        else:
            go.enable()

    go.on_click(confirmed)
    refresh()
    dialog.open()


async def start(conn, dwarf_id, rows: list[list]) -> bool:
    """Asks Dwarfium Lite for the megastack of these sessions (one target,
    checked by the picker). True when started."""
    lite = peer_url()
    if not lite:
        ui.notify(t("megastack_lite_not_running"), type="warning")
        return False

    detail = get_dwarf_detail(conn, dwarf_id) or []
    ip = (detail[5] if len(detail) > 5 else "") or ""
    dwarf_uid, why = await run.io_bound(lite_dwarf_uid, lite, get_dwarf_ble_id(conn, dwarf_id), ip)
    if dwarf_uid is None:
        ui.notify(t(f"megastack_dwarf_{why}"), type="warning")
        return False

    target = str(rows[0][_TARGET] or "").strip()
    names = [str(r[_SESSION_DIR]) for r in rows]
    ok, error = await run.io_bound(post_megastack, lite, dwarf_uid, names, target)
    if ok:
        ui.notify(t("megastack_started", count=len(names), target=target), type="positive", multi_line=True)
    elif error == "lite_old":
        ui.notify(t("megastack_lite_old"), type="warning")
    else:
        ui.notify(t("megastack_refused", error=error), type="negative", multi_line=True)
    return ok
