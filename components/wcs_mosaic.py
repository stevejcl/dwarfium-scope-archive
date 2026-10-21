"""Mosaic by astrometry (Explore, a tile's session - user-requested Oct
2026): the tiles of a mosaic planned by Astro Dwarf Session's Milky Way
planner are sessions of their own ("MW Tile R1C1", "MW Tile R1C2"...), so
Explore's multi-selection - one object's sessions - can't gather them.

From one tile's session, the dialog lists the sessions of the same backup
drive named alike (same prefix, R<row>C<col>), the ones of the same night
ticked; their stacked FITS are assembled by api/mosaic_wcs.py (plate
solved when their header has no WCS) into a linear FITS and a preview,
in a MOSAIC_WCS folder next to the sessions.
"""
from __future__ import annotations

import base64
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

from nicegui import run, ui

from components.i18n import t

TILE_RE = re.compile(r"^(?P<prefix>.*?)[\s_-]*R(?P<row>\d+)[\s_-]*C(?P<col>\d+)(?:\b|_|$)", re.IGNORECASE)
NIGHT_HOURS = 18            # sessions this close to the chosen one: the same night
OUTPUT_DIR = "MOSAIC_WCS"


def tile_key(*names) -> tuple[str, int, int] | None:
    """(prefix, row, col) of a tile's name ("MW Tile R1C2", a session folder
    "..._MW_Tile_R1C2_..."), the prefix normalised; None when not a tile."""
    for name in names:
        if not name:
            continue
        base = os.path.basename(str(name).rstrip("/\\"))
        for candidate in (str(name), base):
            m = TILE_RE.search(candidate.replace("_", " "))
            if m:
                prefix = re.sub(r"\s+", " ", m.group("prefix")).strip(" -").lower()
                # a session folder starts with its date or the Dwarf's own words
                prefix = re.sub(r"^([\d\s:.-]+|dwarf raw( wide| tele)?\b|restacked\b|stacked-\d+\b)+", "", prefix).strip()
                return prefix, int(m.group("row")), int(m.group("col"))
    return None


def _when(value):
    try:
        return datetime.fromisoformat(str(value)[:19])
    except ValueError:
        return None


def _stacked_fits(location, stacked_rel, file_rel):
    """The session's stacked FITS on its drive: the recorded one, else a
    stacked*.fits in its folder."""
    if location and stacked_rel:
        p = Path(location) / stacked_rel
        if p.is_file():
            return str(p)
    if location and file_rel:
        folder = Path(location) / Path(file_rel).parent
        if folder.is_dir():
            found = sorted(folder.glob("stacked*.fits")) + sorted(folder.glob("stacked*.fit"))
            if found:
                return str(found[0])
    return None


def find_tiles(conn, backup_drive_id, key, session_date) -> list[dict]:
    """The sessions of the drive named like the tile `key` (same prefix),
    each {entry_id, label, row, col, date, fits, night}; night: within
    NIGHT_HOURS of session_date. Sorted by date, then row / column."""
    prefix = key[0]
    ref = _when(session_date)
    rows = conn.execute("""
        SELECT be.id, be.session_date, be.session_dir, dd.target, dd.stacked_fits_path, dd.file_path, bd.location
        FROM BackupEntry be
        JOIN DwarfData dd ON be.dwarf_data_id = dd.id
        JOIN BackupDrive bd ON be.backup_drive_id = bd.id
        WHERE be.backup_drive_id = ?""", (backup_drive_id,)).fetchall()
    tiles = []
    for entry_id, date, session_dir, target, stacked_rel, file_rel, location in rows:
        k = tile_key(target, session_dir)
        if not k or k[0] != prefix:
            continue
        when = _when(date)
        tiles.append({
            "entry_id": entry_id, "row": k[1], "col": k[2], "date": str(date or "")[:16],
            "label": f"R{k[1]}C{k[2]}", "session": os.path.basename(str(session_dir or "")),
            "fits": _stacked_fits(location, stacked_rel, file_rel),
            "night": bool(ref and when and abs(when - ref) <= timedelta(hours=NIGHT_HOURS)),
        })
    tiles.sort(key=lambda d: (d["date"], d["row"], d["col"]))
    return tiles


def default_output(tiles, key) -> str:
    """MOSAIC_WCS/<prefix>_<date>.fits next to the first ticked tile's session."""
    first = next((d for d in tiles if d["night"] and d["fits"]), None) or next((d for d in tiles if d["fits"]), None)
    if not first:
        return ""
    session_folder = Path(first["fits"]).parent
    base = session_folder.parent
    name = re.sub(r"[^\w.-]+", "_", key[0].strip()) or "mosaic"
    date = re.sub(r"[^\d]", "", first["date"])[:12]
    return str(base / OUTPUT_DIR / f"{name}_{date}.fits")


async def open_dialog(conn, row) -> None:
    """The dialog for the session `row` (Explore's row: [8] session_dir,
    [13] target, [7] date, [20] backup drive)."""
    from api.mosaic_wcs import build_mosaic, solver_settings

    key = tile_key(row[13], row[8])
    if not key:
        ui.notify(t("wcs_mosaic_not_tile"), type="warning")
        return
    tiles = await run.io_bound(find_tiles, conn, row[20], key, row[7])
    settings = solver_settings(conn)
    checks = {}
    state = {"fraction": 0.0, "message": "", "running": False, "result": None}

    with ui.dialog() as dialog, ui.card().classes("w-full max-w-4xl"):
        ui.label(t("wcs_mosaic_title")).classes("text-lg font-semibold")
        ui.label(t("wcs_mosaic_hint")).classes("text-xs text-gray-500")
        with ui.column().classes("w-full gap-0 max-h-80 overflow-auto"):
            for d in tiles:
                text = f"{d['label']}  ·  {d['date']}  ·  {d['session']}"
                if not d["fits"]:
                    text += f"  ·  {t('wcs_mosaic_no_fits')}"
                checks[d["entry_id"]] = ui.checkbox(text, value=d["night"] and bool(d["fits"])).props("dense")
                if not d["fits"]:
                    checks[d["entry_id"]].disable()
        output = ui.input(t("wcs_mosaic_output"), value=default_output(tiles, key)).classes("w-full")
        progress = ui.linear_progress(value=0, show_value=False).classes("w-full")
        status = ui.label("").classes("text-sm")
        result_box = ui.column().classes("w-full")

        def refresh():
            progress.value = state["fraction"]
            status.text = state["message"]

        timer = ui.timer(0.5, refresh, active=False)

        async def assemble():
            chosen = [d["fits"] for d in tiles if d["fits"] and checks[d["entry_id"]].value]
            if len(chosen) < 2:
                ui.notify(t("wcs_mosaic_min2"), type="warning")
                return
            out = (output.value or "").strip()
            if not out:
                ui.notify(t("wcs_mosaic_output"), type="warning")
                return
            run_btn.disable()
            state.update(fraction=0.0, message=t("wcs_mosaic_running"), running=True)
            timer.activate()
            result_box.clear()

            def on_progress(fraction, message):
                state["fraction"], state["message"] = fraction, message

            try:
                res = await run.io_bound(build_mosaic, chosen, out, settings, None, on_progress, True)
            except Exception as e:
                res = {"ok": False, "error": str(e), "skipped": [], "tiles": []}
            timer.deactivate()
            refresh()
            run_btn.enable()
            with result_box:
                for s in res.get("skipped", []):
                    ui.label(t("wcs_mosaic_skipped", name=s["name"], reason=s["reason"])).classes("text-orange-600 text-sm")
                if not res.get("ok"):
                    ui.label(t("wcs_mosaic_failed", error=res.get("error") or "")).classes("text-red-600")
                    return
                for s in res["tiles"]:
                    rms = f"{s['rms']:.2f} px" if s["rms"] is not None else "-"
                    ui.label(t("wcs_mosaic_tile_line", name=s["name"], stars=s["stars"], rms=rms, sky=s["sky_pct"])).classes("text-xs text-gray-600")
                ui.label(t("wcs_mosaic_done", path=res["fits"])).classes("text-green-700 text-sm")
                try:
                    data = base64.b64encode(Path(res["preview"]).read_bytes()).decode()
                    ui.image(f"data:image/jpeg;base64,{data}").classes("w-full")
                except OSError:
                    pass

        with ui.row().classes("w-full justify-end"):
            ui.button(t("close"), on_click=dialog.close).props("flat")
            run_btn = ui.button(t("wcs_mosaic_run"), icon="auto_awesome_mosaic", on_click=assemble)
    dialog.open()
