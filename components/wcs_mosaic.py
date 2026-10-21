"""Milky Way mosaic by astrometry (the Mosaic page's Milky Way tab -
user-requested Oct 2026): the tiles of a mosaic planned by Astro Dwarf
Session's Milky Way planner are sessions of their own ("MW Tile R1C1",
"MW Tile R1C2"...), so Explore's multi-selection - one object's sessions -
can't gather them.

The panel lists the mosaics found on the selected backup drive - its
sessions named alike (same prefix, R<row>C<col>), grouped by night - or
the FITS of a folder the user chooses; the tiles ticked are assembled by
api/mosaic_wcs.py (plate solved when their header has no WCS) into a
linear FITS and a preview, in a MOSAIC_WCS folder next to the sessions.
Explore's button on a tile's session opens it on that tile's mosaic.
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
NIGHT_HOURS = 18            # a gap longer than this between tiles: another night
OUTPUT_DIR = "MOSAIC_WCS"
FITS_GLOBS = ("*.fits", "*.fit", "*.fts")


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


def drive_tiles(conn, backup_drive_id) -> list[dict]:
    """The mosaic tiles among the drive's sessions: {entry_id, prefix, row,
    col, label, date, session, fits}, sorted by prefix then date."""
    rows = conn.execute("""
        SELECT be.id, be.session_date, be.session_dir, dd.target, dd.stacked_fits_path, dd.file_path, bd.location
        FROM BackupEntry be
        JOIN DwarfData dd ON be.dwarf_data_id = dd.id
        JOIN BackupDrive bd ON be.backup_drive_id = bd.id
        WHERE be.backup_drive_id = ?""", (backup_drive_id,)).fetchall()
    tiles = []
    for entry_id, date, session_dir, target, stacked_rel, file_rel, location in rows:
        k = tile_key(target, session_dir)
        if not k:
            continue
        m = TILE_RE.search(str(target or "").replace("_", " "))
        title = m.group("prefix").strip(" -") if m and m.group("prefix").strip(" -") else k[0]
        tiles.append({
            "entry_id": entry_id, "prefix": k[0], "title": title, "row": k[1], "col": k[2], "label": f"R{k[1]}C{k[2]}",
            "date": str(date or "")[:16], "session": os.path.basename(str(session_dir or "")),
            "fits": _stacked_fits(location, stacked_rel, file_rel),
        })
    tiles.sort(key=lambda d: (d["prefix"], d["date"], d["row"], d["col"]))
    return tiles


def group_mosaics(tiles) -> list[dict]:
    """The tiles grouped into mosaics: same prefix, a new one after a gap of
    more than NIGHT_HOURS. Each {key, prefix, start, tiles}, newest first."""
    groups = []
    for d in tiles:
        g = groups[-1] if groups else None
        when, last = _when(d["date"]), _when(g["tiles"][-1]["date"]) if g else None
        if g and g["prefix"] == d["prefix"] and when and last and when - last <= timedelta(hours=NIGHT_HOURS):
            g["tiles"].append(d)
        else:
            groups.append({"prefix": d["prefix"], "start": d["date"], "tiles": [d]})
    for g in groups:
        g["key"] = f"{g['prefix']}|{g['start']}"
    return sorted(groups, key=lambda g: g["start"], reverse=True)


def folder_tiles(folder) -> list[dict]:
    """The FITS of a folder chosen by hand - its own, and the stacked ones of
    its subfolders (one session per subfolder)."""
    base = Path(folder)
    found = []
    for pattern in FITS_GLOBS:
        found += sorted(base.glob(pattern))
    for sub in sorted(p for p in base.iterdir() if p.is_dir()):
        for pattern in FITS_GLOBS:
            found += sorted(sub.glob("stacked" + pattern))
    tiles = []
    for f in found:
        k = tile_key(f.stem, f.parent.name)
        tiles.append({"entry_id": str(f), "prefix": k[0] if k else "", "row": k[1] if k else 0,
                      "col": k[2] if k else 0, "label": f"R{k[1]}C{k[2]}" if k else "", "date": "",
                      "session": f.parent.name if f.parent != base else f.name, "fits": str(f)})
    return tiles


def default_output(tiles) -> str:
    """MOSAIC_WCS/<prefix>_<date>.fits next to the first tile's session."""
    first = next((d for d in tiles if d["fits"]), None)
    if not first:
        return ""
    session_folder = Path(first["fits"]).parent
    name = re.sub(r"[^\w.-]+", "_", first["prefix"].strip()) or "mosaic"
    date = re.sub(r"[^\d]", "", first["date"])[:12] or datetime.now().strftime("%Y%m%d%H%M")
    return str(session_folder.parent / OUTPUT_DIR / f"{name}_{date}.fits")


class MilkyWayPanel:
    """The Milky Way tab's content, built in the caller's UI context.
    refresh(backup_drive_id) lists that drive's mosaics; `preselect`
    (tile name, session date) picks the mosaic holding that tile."""

    def __init__(self, conn, client, preselect: tuple[str, str] | None = None):
        from api.mosaic_wcs import solver_settings
        self.conn = conn
        self.client = client
        self.preselect = preselect
        self.settings = solver_settings(conn)
        self.groups: list[dict] = []
        self.tiles: list[dict] = []
        self.checks: dict = {}
        self.state = {"fraction": 0.0, "message": ""}
        self._build()

    def _build(self):
        with ui.card().classes("w-full p-4 mt-1") as self.card:
            ui.label(t("wcs_mosaic_title")).classes("text-lg font-semibold")
            ui.label(t("wcs_mosaic_hint")).classes("text-xs text-gray-500")
            with ui.row().classes("w-full items-center gap-4"):
                self.mosaic_select = ui.select(options={}, label=t("wcs_mosaic_found"),
                                               on_change=self._on_mosaic_change) \
                    .props("stack-label outlined").classes("flex-grow min-w-[300px]")
                ui.button(t("wcs_mosaic_add_folder"), icon="folder_open", on_click=self._add_folder)
            self.empty_label = ui.label("").classes("text-sm text-orange-600")
            self.tile_box = ui.column().classes("w-full gap-0 max-h-80 overflow-auto")
            self.output = ui.input(t("wcs_mosaic_output")).classes("w-full")
            with ui.row().classes("w-full items-center"):
                self.run_btn = ui.button(t("wcs_mosaic_run"), icon="auto_awesome_mosaic", on_click=self._assemble)
                self.progress = ui.linear_progress(value=0, show_value=False).classes("flex-grow")
            self.status = ui.label("").classes("text-sm")
            self.result_box = ui.column().classes("w-full")
        self.timer = ui.timer(0.5, self._refresh_progress, active=False)

    def set_visibility(self, visible: bool):
        self.card.set_visibility(visible)

    async def refresh(self, backup_drive_id):
        """The drive's mosaics in the list - the preselected one, else the newest."""
        self.groups = group_mosaics(await run.io_bound(drive_tiles, self.conn, backup_drive_id)) if backup_drive_id else []
        options = {g["key"]: t("wcs_mosaic_group", name=g["tiles"][0].get("title") or g["prefix"] or "?",
                                date=g["start"], n=len(g["tiles"]))
                   for g in self.groups}
        value = None
        if self.preselect:
            k, when = tile_key(self.preselect[0]), _when(self.preselect[1])
            for g in self.groups:
                if k and g["prefix"] == k[0] and when and any(
                        abs((_when(d["date"]) or when) - when) <= timedelta(hours=1) for d in g["tiles"]):
                    value = g["key"]
                    break
        if value is None and self.groups:
            value = self.groups[0]["key"]
        self.mosaic_select.set_options(options, value=value)
        self.empty_label.text = "" if self.groups else t("wcs_mosaic_none_found")
        self._on_mosaic_change()

    def _on_mosaic_change(self, *_):
        group = next((g for g in self.groups if g["key"] == self.mosaic_select.value), None)
        self._show_tiles(group["tiles"] if group else [])

    def _show_tiles(self, tiles):
        self.tiles = tiles
        self.checks = {}
        self.tile_box.clear()
        with self.tile_box:
            for d in tiles:
                text = "  ·  ".join(x for x in (d["label"], d["date"], d["session"]) if x)
                if not d["fits"]:
                    text += f"  ·  {t('wcs_mosaic_no_fits')}"
                box = ui.checkbox(text, value=bool(d["fits"])).props("dense")
                if not d["fits"]:
                    box.disable()
                self.checks[d["entry_id"]] = box
        self.output.value = default_output(tiles)

    async def _add_folder(self):
        from components.folder_picker import choose_folder
        start = os.path.dirname(self.tiles[0]["fits"]) if self.tiles and self.tiles[0]["fits"] else None
        folder = await choose_folder(self.client, start)
        if not folder:
            return
        tiles = await run.io_bound(folder_tiles, folder)
        if not tiles:
            ui.notify(t("wcs_mosaic_folder_empty"), type="warning")
            return
        self.mosaic_select.set_value(None)
        self._show_tiles(tiles)

    def _refresh_progress(self):
        self.progress.value = self.state["fraction"]
        self.status.text = self.state["message"]

    async def _assemble(self):
        from api.mosaic_wcs import build_mosaic
        chosen = [d["fits"] for d in self.tiles if d["fits"] and self.checks[d["entry_id"]].value]
        if len(chosen) < 2:
            ui.notify(t("wcs_mosaic_min2"), type="warning")
            return
        out = (self.output.value or "").strip()
        if not out:
            ui.notify(t("wcs_mosaic_output"), type="warning")
            return
        self.run_btn.disable()
        self.state.update(fraction=0.0, message=t("wcs_mosaic_running"))
        self.timer.activate()
        self.result_box.clear()

        def on_progress(fraction, message):
            self.state["fraction"], self.state["message"] = fraction, message

        try:
            res = await run.io_bound(build_mosaic, chosen, out, self.settings, None, on_progress, True)
        except Exception as e:
            res = {"ok": False, "error": str(e), "skipped": [], "tiles": []}
        self.timer.deactivate()
        self._refresh_progress()
        self.run_btn.enable()
        with self.result_box:
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
