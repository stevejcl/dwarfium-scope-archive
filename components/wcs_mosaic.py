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

An assembly belongs to the app, not to the page (user-asked Oct 2026: it
takes minutes, the user goes elsewhere): MOSAIC_JOB holds its state, steps
and result, one at a time; the tab shows it whenever it is open - a banner
while it runs, its steps, then its result - and every open page is told
when it ends.
"""
from __future__ import annotations

import base64
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import threading
import time

from nicegui import Client, background_tasks, run, ui

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


class _JobLog:
    """What api/mosaic_wcs.py (and the solvers) log: kept in the job's steps."""

    def push(self, message, classes=None):
        with MOSAIC_JOB["lock"]:
            MOSAIC_JOB["steps"].append(f"{time.strftime('%H:%M:%S')}  {message}")
            del MOSAIC_JOB["steps"][:-MAX_STEPS]


MAX_STEPS = 300
MOSAIC_JOB = {"lock": threading.Lock(), "running": False, "fraction": 0.0, "message": "",
              "steps": [], "result": None, "output": "", "started": None, "version": 0}


def start_job(paths, out, settings) -> bool:
    """Starts the assembly in the background, app-wide; False when one runs."""
    from api.mosaic_wcs import build_mosaic
    with MOSAIC_JOB["lock"]:
        if MOSAIC_JOB["running"]:
            return False
        MOSAIC_JOB.update(running=True, fraction=0.0, message=t("wcs_mosaic_running"), steps=[],
                          result=None, output=out, started=time.time())
        MOSAIC_JOB["version"] += 1

    def on_progress(fraction, message):
        MOSAIC_JOB["fraction"], MOSAIC_JOB["message"] = fraction, message

    async def job():
        try:
            res = await run.io_bound(build_mosaic, paths, out, settings, _JobLog(), on_progress, True)
        except Exception as e:
            res = {"ok": False, "error": str(e), "skipped": [], "tiles": []}
        with MOSAIC_JOB["lock"]:
            MOSAIC_JOB.update(running=False, result=res, fraction=1.0 if res.get("ok") else MOSAIC_JOB["fraction"])
            MOSAIC_JOB["version"] += 1
        _tell_every_page(res)

    background_tasks.create(job(), name="milky-way-mosaic")
    return True


def _tell_every_page(res):
    """The end of the assembly, on every open page of the app."""
    text = t("wcs_mosaic_done", path=res["fits"]) if res.get("ok") else t("wcs_mosaic_failed", error=res.get("error") or "")
    for client in list(Client.instances.values()):
        try:
            if client.has_socket_connection:
                with client:
                    ui.notify(text, type="positive" if res.get("ok") else "negative", multi_line=True, timeout=15000)
        except Exception:
            pass


class MilkyWayPanel:
    """The Milky Way tab's content, built in the caller's UI context.
    refresh(backup_drive_id) lists that drive's mosaics; `preselect`
    (tile name, session date) picks the mosaic holding that tile. Shows the
    app's assembly (MOSAIC_JOB) - running or done - whenever it is open."""

    def __init__(self, conn, client, preselect: tuple[str, str] | None = None):
        from api.mosaic_wcs import solver_settings
        self.conn = conn
        self.client = client
        self.preselect = preselect
        self.settings = solver_settings(conn)
        self.groups: list[dict] = []
        self.tiles: list[dict] = []
        self.checks: dict = {}
        self.shown_version = -1
        self.shown_steps = 0
        self._build()

    def _build(self):
        with ui.card().classes("w-full p-4 mt-1") as self.card:
            # stays while an assembly runs, whatever page it was started from
            with ui.row().classes("w-full items-center gap-3 p-3 rounded bg-amber-100 text-amber-900") as self.banner:
                ui.spinner(size="md")
                self.banner_text = ui.label("").classes("text-base font-semibold")
            self.banner.set_visibility(False)
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
            with ui.expansion(t("wcs_mosaic_steps"), icon="list", value=True).classes("w-full") as self.steps_box:
                self.steps_log = ui.log(max_lines=MAX_STEPS).classes("w-full").style("height: 220px")
            self.steps_box.set_visibility(False)
            self.result_box = ui.column().classes("w-full")
        self.timer = ui.timer(0.5, self._follow_job)

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

    def _assemble(self):
        chosen = [d["fits"] for d in self.tiles if d["fits"] and self.checks[d["entry_id"]].value]
        if len(chosen) < 2:
            ui.notify(t("wcs_mosaic_min2"), type="warning")
            return
        out = (self.output.value or "").strip()
        if not out:
            ui.notify(t("wcs_mosaic_output"), type="warning")
            return
        if not start_job(chosen, out, self.settings):
            ui.notify(t("wcs_mosaic_busy"), type="warning")
            return
        self._follow_job()

    def _follow_job(self):
        """The app's assembly on this tab: banner, progress, new steps, and
        its result once - each time the tab is open."""
        job = MOSAIC_JOB
        running = job["running"]
        self.banner.set_visibility(running)
        if running:
            elapsed = int(time.time() - (job["started"] or time.time()))
            self.banner_text.text = t("wcs_mosaic_banner", time=f"{elapsed // 60}:{elapsed % 60:02d}", step=job["message"])
        self.run_btn.set_enabled(not running)
        if job["started"] is None:
            return
        self.progress.value = job["fraction"]
        self.status.text = job["message"]
        self.steps_box.set_visibility(True)
        if self.shown_version != job["version"]:          # another assembly: its steps from the start
            self.steps_log.clear()
            self.shown_steps = 0
            self.result_box.clear()
            if running:
                self.output.value = job["output"]
        with job["lock"]:
            new = job["steps"][self.shown_steps:]
            self.shown_steps = len(job["steps"])
        for line in new:
            self.steps_log.push(line)
        if self.shown_version != job["version"] and job["result"] is not None:
            self._show_result(job["result"])
        self.shown_version = job["version"]

    def _show_result(self, res):
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
