"""
components/foreground_repair.py

Explore's "Fix the foreground" on a wide session (user-requested Oct 2026:
on firmwares older than DWARF 3 V1.5.3.9 / DWARF mini V1.1.4.4 the Dwarf's
stack smears the trees and the roof): a dialog over api/foreground_fix.py.

The repair takes a minute or more: like the Milky Way mosaic it belongs to
the app (REPAIR_JOB) - the dialog can be closed and the page left, every open
page is told when it ends, and opening the dialog again shows it running or
its result. One at a time.
"""

from __future__ import annotations

import base64
import threading
import time
from pathlib import Path

from nicegui import Client, background_tasks, run, ui

from components.i18n import t
from components.wcs_mosaic import open_dir

MAX_STEPS = 300
REPAIR_JOB = {"lock": threading.Lock(), "running": False, "fraction": 0.0, "message": "", "steps": [],
              "result": None, "session": "", "output": "", "started": None, "version": 0}


class _JobLog:
    """What api/foreground_fix.py logs: kept in the job's steps."""

    def push(self, message, classes=None):
        with REPAIR_JOB["lock"]:
            REPAIR_JOB["steps"].append(f"{time.strftime('%H:%M:%S')}  {message}")
            del REPAIR_JOB["steps"][:-MAX_STEPS]


def start_repair(session_dir: str) -> bool:
    """Starts the repair of `session_dir` in the background, app-wide; False
    when one runs."""
    from api.foreground_fix import repair_session, default_output
    with REPAIR_JOB["lock"]:
        if REPAIR_JOB["running"]:
            return False
        REPAIR_JOB.update(running=True, fraction=0.0, message=t("fg_fix_running"), steps=[], result=None,
                          session=str(session_dir), output=str(default_output(session_dir)), started=time.time())
        REPAIR_JOB["version"] += 1

    def on_progress(fraction, message):
        REPAIR_JOB["fraction"], REPAIR_JOB["message"] = fraction, message

    async def job():
        try:
            res = await run.io_bound(repair_session, session_dir, None, _JobLog(), on_progress)
        except Exception as e:
            res = {"ok": False, "error": str(e)}
        with REPAIR_JOB["lock"]:
            REPAIR_JOB.update(running=False, result=res, fraction=1.0 if res.get("ok") else REPAIR_JOB["fraction"])
            REPAIR_JOB["version"] += 1
        _tell_every_page(res)

    background_tasks.create(job(), name="foreground-repair")
    return True


def _tell_every_page(res):
    text = t("fg_fix_done", path=res["fits"]) if res.get("ok") else t("fg_fix_failed", error=res.get("error") or "")
    for client in list(Client.instances.values()):
        try:
            if client.has_socket_connection:
                with client:
                    ui.notify(text, type="positive" if res.get("ok") else "negative", multi_line=True, timeout=15000)
        except Exception:
            pass


def open_repair_dialog(session_dir: str):
    """The dialog: what the repair does, Start, then its progress, steps and
    result - the app's repair whatever session it is on."""
    from api.foreground_fix import default_output, raw_subs
    state = {"version": -1, "steps": 0}
    with ui.dialog() as dialog, ui.card().classes("w-[760px] max-w-full"):
        ui.label(t("fg_fix_title")).classes("text-lg font-semibold")
        ui.label(t("fg_fix_hint")).classes("text-sm text-gray-600")
        ui.label(t("fg_fix_session", name=Path(session_dir).name,
                   n=len(raw_subs(session_dir)))).classes("text-sm")
        ui.label(t("fg_fix_output", path=str(default_output(session_dir)))).classes("text-xs text-gray-500")
        with ui.row().classes("w-full items-center gap-3 p-2 rounded bg-amber-100 text-amber-900") as banner:
            ui.spinner(size="sm")
            banner_text = ui.label("").classes("text-sm font-semibold")
        banner.set_visibility(False)
        with ui.row().classes("w-full items-center"):
            start_btn = ui.button(t("fg_fix_start"), icon="park", on_click=lambda: _start())
            progress = ui.linear_progress(value=0, show_value=False).classes("flex-grow")
        status = ui.label("").classes("text-sm")
        with ui.expansion(t("wcs_mosaic_steps"), icon="list", value=True).classes("w-full") as steps_box:
            steps_log = ui.log(max_lines=MAX_STEPS).classes("w-full").style("height: 180px")
        steps_box.set_visibility(False)
        result_box = ui.column().classes("w-full")
        with ui.row().classes("w-full justify-end"):
            ui.button(t("close"), on_click=dialog.close).props("flat")

    def _start():
        if not start_repair(session_dir):
            ui.notify(t("fg_fix_busy"), color="warning")

    def _show_result(res):
        result_box.clear()
        with result_box:
            if not res.get("ok"):
                ui.label(t("fg_fix_failed", error=res.get("error") or "")).classes("text-red-600")
                return
            with ui.row().classes("items-center gap-2"):
                ui.label(t("fg_fix_done", path=res["fits"])).classes("text-green-700 text-sm")
                ui.button(t("wcs_mosaic_open_folder"), icon="folder_open",
                          on_click=lambda p=res["fits"]: open_dir(Path(p).parent)).props("flat dense no-caps")
            ui.label(t("fg_fix_files", subs=res.get("subs"), fg=res.get("foreground_pct"))).classes("text-xs text-gray-600")
            try:
                data = base64.b64encode(Path(res["preview"]).read_bytes()).decode()
                ui.image(f"data:image/jpeg;base64,{data}").classes("w-full")
            except OSError:
                pass

    def _follow():
        job = REPAIR_JOB
        running = job["running"]
        banner.set_visibility(running)
        start_btn.set_enabled(not running)
        if running:
            elapsed = int(time.time() - (job["started"] or time.time()))
            banner_text.text = t("fg_fix_banner", name=Path(job["session"]).name,
                                 time=f"{elapsed // 60}:{elapsed % 60:02d}")
        if job["started"] is None:
            return
        progress.value = job["fraction"]
        status.text = job["message"]
        steps_box.set_visibility(True)
        if state["version"] != job["version"]:
            steps_log.clear()
            state["steps"] = 0
            result_box.clear()
        with job["lock"]:
            new = job["steps"][state["steps"]:]
            state["steps"] = len(job["steps"])
        for line in new:
            steps_log.push(line)
        if state["version"] != job["version"] and job["result"] is not None:
            _show_result(job["result"])
        state["version"] = job["version"]

    timer = ui.timer(0.5, _follow)

    def _closed():
        timer.delete()                         # the repair itself goes on
        dialog.delete()

    dialog.on("hide", _closed)
    dialog.open()
