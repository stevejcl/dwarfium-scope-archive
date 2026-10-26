"""Analyze everything (tools/full_rescan.py): every Dwarf's local copy and
every backup drive of the database, ticked ones only, one after the
other - a line per folder with its result, and the analyses' log."""
from __future__ import annotations

import threading
import traceback

from nicegui import run, ui

from api.dwarf_backup_db import DB_NAME, close_db, connect_db
from components.db_page_mixin import DbPageMixin
from components.i18n import t
from components.menu import menu
from tools import full_rescan as R
from components.folder_picker import on_this_pc


@ui.page('/AnalyzeAll')
async def analyze_all_page():
    menu(t("page_analyze_all"))
    await ui.context.client.connected(timeout=10.0)
    AnalyzeAllApp(DB_NAME)


class AnalyzeAllApp(DbPageMixin):
    def __init__(self, database):
        self.database = database
        self.targets: list[R.Target] = []
        self.selected: dict[str, bool] = {}
        self.results: dict[str, str] = {}      # key -> "running" / "+12 -3" / "error: ..."
        self.running = False
        self.stop = threading.Event()    # Stop: at the next object's folder (R.AnalysisStopped)
        self.tee: R.TeeLog | None = None
        self.build_ui()

    def build_ui(self):
        self.conn = connect_db(self.database)
        self.register_conn_close()
        self.targets = R.list_targets(self.conn)
        self.selected = {x.key: x.reachable for x in self.targets}
        with ui.card().classes("w-full max-w-5xl mx-auto gap-3"):
            ui.label(t("analyze_all_intro")).classes("text-sm text-gray-600")
            self.list_view()
            with ui.row().classes("items-center gap-3"):
                self.start_btn = ui.button(t("analyze_all_start"), icon="manage_search",
                                           on_click=self.start).props("no-caps")
                self.stop_btn = ui.button(t("analyze_all_stop"), icon="stop", color="negative",
                                          on_click=self._ask_stop).props("no-caps")
                self.stop_btn.set_visibility(False)
                self.summary = ui.label("").classes("text-sm")
            self.log = ui.log(max_lines=200).classes("w-full").style("height: 300px")
            with ui.row().classes("items-center gap-2 text-xs text-gray-500") as self.log_row:
                ui.icon("description", size="xs")
                self.log_path = ui.label("").classes("font-mono break-all")
                ui.button(t("analyze_all_open_log"), icon="open_in_new",
                          on_click=lambda: on_this_pc() and R.open_path(self.log_path.text)).props("flat dense no-caps size=sm")
                ui.button(t("analyze_all_open_folder"), icon="folder",
                          on_click=lambda: on_this_pc() and R.show_in_folder(self.log_path.text)) \
                    .props("flat dense no-caps size=sm")
            self.log_row.set_visibility(False)
        # The analyses' lines reach the screen in batches (see R.TeeLog)
        ui.timer(0.5, self._drain_log)

    def _ask_stop(self):
        """The folder being read stops at its next object's folder (what was
        found kept, nothing removed), the next ones are not started."""
        self.stop.set()
        self.stop_btn.disable()
        self.stop_btn.set_text(t("analyze_all_stopping"))
        if self.tee:
            self.tee.push(t("analyze_all_stopping"))

    def _drain_log(self):
        if self.tee is None:
            return
        lines, skipped = self.tee.drain()
        if skipped:
            self.log.push(t("analyze_all_lines_skipped", n=skipped))
        for line in lines:      # all sent together: one update for the browsers
            self.log.push(line)

    @ui.refreshable_method
    def list_view(self):
        for kind, title in ((R.DWARF, t("analyze_all_dwarfs")), (R.BACKUP, t("analyze_all_backups"))):
            items = [x for x in self.targets if x.kind == kind]
            if not items:
                continue
            ui.label(title).classes("text-xs font-semibold text-gray-500 mt-2")
            for x in items:
                # on a phone the date and the result go under the path
                with ui.row().classes("w-full items-center gap-x-6 gap-y-1 flex-wrap sm:flex-nowrap border-b py-1"):
                    box = ui.checkbox(value=self.selected.get(x.key, False),
                                      on_change=lambda e, k=x.key: self.selected.__setitem__(k, e.value)) \
                        .props("dense")
                    box.set_enabled(x.reachable and not self.running)
                    with ui.column().classes("gap-0 flex-1").style("min-width: 200px"):
                        ui.label(x.name).classes("text-sm font-medium truncate")
                        ui.label(x.path or "—").classes("text-xs text-gray-500 font-mono break-all")
                    if not x.reachable:
                        ui.label(t("analyze_all_unreachable")).classes("text-xs text-orange-700 shrink-0")
                    else:
                        ui.label(t("analyze_all_last", date=x.last_scan or "—")).classes("text-xs text-gray-500 shrink-0")
                    self._result_cell(self.results.get(x.key, ""))

    @staticmethod
    def _result_cell(result: str):
        with ui.element("div").classes("w-24 shrink-0 text-right text-xs"):
            if result == "running":
                ui.spinner(size="sm")
            elif result == "stopped":
                ui.icon("stop_circle", color="warning").tooltip(t("analyze_all_stopped_folder"))
            elif result.startswith("error"):
                ui.icon("error", color="negative").tooltip(result)
            elif result:
                ui.label(result).classes("text-green-700 font-medium")

    async def start(self):
        chosen = [x for x in self.targets if self.selected.get(x.key) and x.reachable]
        if not chosen:
            ui.notify(t("analyze_all_none"), type="warning")
            return
        self.running = True
        self.stop.clear()
        self.start_btn.disable()
        self.stop_btn.set_text(t("analyze_all_stop"))
        self.stop_btn.enable()
        self.stop_btn.set_visibility(True)
        stopped, done = False, 0
        self.results = {}
        found = removed = 0
        log = R.TeeLog()        # every line in a file, the screen fed by _drain_log
        self.tee = log
        self.log_path.set_text(log.path)
        self.log_row.set_visibility(True)
        log.push(f"Scope Archive - {t('page_analyze_all')} - {len(chosen)} folder(s)")
        for x in self.targets:
            log.push(f"  [{'x' if x in chosen else ' '}] {x.kind} {x.name}: {x.path}"
                     + ("" if x.reachable else " (not reachable)"))
        try:
            for i, x in enumerate(chosen, 1):
                if self.stop.is_set():
                    stopped = True
                    break
                self.results[x.key] = "running"
                self.summary.set_text(t("analyze_all_progress", i=i, n=len(chosen), name=x.name))
                self.list_view.refresh()
                log.push(f"── {x.name} ({x.path})")
                try:
                    total, deleted = await run.io_bound(R.analyze, self.database, x, log, None, self.stop)
                    self.results[x.key] = f"+{total} -{deleted}"
                    log.push(f"   => {x.name}: +{total} new, -{deleted} removed")
                    found += total
                    removed += deleted
                    done += 1
                except R.AnalysisStopped:
                    stopped = True
                    self.results[x.key] = "stopped"
                    log.push(f"⏹ {x.name}: {t('analyze_all_stopped_folder')}")
                    break
                except Exception as e:
                    self.results[x.key] = f"error: {e}"
                    log.push(f"❌ {x.name}: {e}")
                    done += 1
            log.push(t("analyze_all_stopped" if stopped else "analyze_all_done",
                       n=len(chosen), done=done, total=found, deleted=removed))
        finally:
            log.close()
            self._drain_log()       # the last lines
            # The page always back to its idle state - a failure reading the
            # new dates left the spinner and "Analyzing 9/9" (user-reported)
            self.running = False
            self.start_btn.enable()
            self.stop_btn.set_visibility(False)
            if self.results.get(chosen[-1].key) == "running":
                self.results.pop(chosen[-1].key)
        done_key = "analyze_all_stopped" if stopped else "analyze_all_done"
        self.summary.set_text(t(done_key, n=len(chosen), done=done, total=found, deleted=removed))
        try:
            dates = await run.io_bound(self._read_dates)     # the new scan dates
            for x in self.targets:
                x.last_scan = dates.get(x.key, x.last_scan)
        except Exception as e:
            traceback.print_exc()
            ui.notify(t("error_generic", error=e), type="warning", multi_line=True)
        self.list_view.refresh()
        ui.notify(t(done_key, n=len(chosen), done=done, total=found, deleted=removed),
                  type="warning" if stopped else "positive")

    def _read_dates(self) -> dict[str, str]:
        """Blocking, on its own connection (the page's may have been closed
        by a disconnect during a long analysis)."""
        conn = connect_db(self.database)
        try:
            return {x.key: x.last_scan for x in R.list_targets(conn)}
        finally:
            close_db(conn)
