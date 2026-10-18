"""Megastack on the Dwarf (Explore, Dwarf mode, several sessions ticked): the
Dwarf stacks its own sessions of a target together into Astronomy/RESTACKED/,
like the official app's megastack - asked to Dwarfium Lite (Astro Dwarf
Session 3.2.6+, POST /api/megastack), which talks to the Dwarf, runs it as a
program and follows it (its device page, then its Results tab).

Checked here first: the sessions are of one target and still have their FITS
(not cleaned by CleanFits), Dwarfium Lite is running and knows this Dwarf,
connected. The Dwarf checks the rest itself (filter, binning, dark frames)."""
from __future__ import annotations

import os

import requests
from nicegui import run, ui

from api.dwarf_backup_db_api import get_dwarf_ble_id, get_dwarf_detail
from api.dwarf_backup_fct import count_fits_files
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


async def start(conn, dwarf_id, rows: list[list], session_dirs: list[str]) -> None:
    """rows: the ticked sessions' Explore rows; session_dirs: their local
    folders (to see their FITS). Asks for confirmation, then for the megastack."""
    if len(rows) < 2:
        ui.notify(t("megastack_need_two"), type="warning")
        return
    targets = {str(r[13] or "").strip() for r in rows}
    if len(targets) > 1:
        ui.notify(t("megastack_one_target", targets=", ".join(sorted(targets))), type="warning")
        return
    cleaned = [os.path.basename(d.rstrip("/\\")) for d in session_dirs if not d or not count_fits_files(d)]  # None: not readable
    if cleaned:
        ui.notify(t("megastack_no_fits", sessions=", ".join(cleaned)), type="warning", multi_line=True)
        return
    lite = peer_url()
    if not lite:
        ui.notify(t("megastack_lite_not_running"), type="warning")
        return

    detail = get_dwarf_detail(conn, dwarf_id) or []
    ip = (detail[5] if len(detail) > 5 else "") or ""
    dwarf_uid, why = await run.io_bound(lite_dwarf_uid, lite, get_dwarf_ble_id(conn, dwarf_id), ip)
    if dwarf_uid is None:
        ui.notify(t(f"megastack_dwarf_{why}"), type="warning")
        return

    target = targets.pop()
    names = [str(r[8]) for r in rows]
    shots = sum(int(r[5] or 0) for r in rows)  # their images stacked

    with ui.dialog() as dialog, ui.card().classes("w-[min(90vw,480px)]"):
        ui.label(t("megastack_title", target=target)).classes("text-base font-medium")
        ui.label(t("megastack_confirm", count=len(names), shots=shots, dwarf=dwarf_uid)).classes("text-sm") \
            .style("white-space: pre-line")
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button(t("cancel"), on_click=dialog.close).props("flat")
            go = ui.button(t("megastack_start"), icon="auto_awesome_motion")

    async def confirmed() -> None:
        go.disable()
        ok, error = await run.io_bound(post_megastack, lite, dwarf_uid, names, target)
        dialog.close()
        if ok:
            ui.notify(t("megastack_started", count=len(names), target=target), type="positive", multi_line=True)
        elif error == "lite_old":
            ui.notify(t("megastack_lite_old"), type="warning")
        else:
            ui.notify(t("megastack_refused", error=error), type="negative", multi_line=True)

    go.on_click(confirmed)
    dialog.open()
