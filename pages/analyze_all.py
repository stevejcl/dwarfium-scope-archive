"""Analyze everything (tools/full_rescan.py): every Dwarf's local copy and
every backup drive of the database, ticked ones only, one after the
other - a line per folder with its result, and the analyses' log.

The analysis belongs to the server, not to the page that started it
(user-asked Oct 2026: another page opened meanwhile, the analysis went on
unseen - back on this page, no progress, no Stop, and Start could run a
second one over the same drives): one at a time (JOB), every page open
on it (this PC, a phone) shows it and can stop it."""
from __future__ import annotations

import threading
import traceback
from collections import deque

from nicegui import background_tasks, run, ui

from api.dwarf_backup_db import DB_NAME, close_db, connect_db
from components.db_page_mixin import DbPageMixin
from components.i18n import t
from components.menu import menu
from tools import full_rescan as R
from components.folder_picker import on_this_pc

_KEPT_LINES = 200       # the log lines a page opened during the analysis gets


class _Job:
    """The analysis running or last run, shared by the pages."""

    def __init__(self):
        self.running = False
        self.stop = threading.Event()    # Stop: at the next object's folder (R.AnalysisStopped)
        self.results: dict[str, str] = {}   # key -> "running" / "+12 -3" / "error: ..." / "stopped"
        self.chosen: set[str] = set()
        self.summary = ""
        self.log_path = ""
        self.lines: deque = deque(maxlen=_KEPT_LINES)
        self.line_count = 0     # lines ever added: a page's cursor
        self.version = 0        # +1 at each change of results / summary / state
        self.finished = 0       # +1 at each end: the pages open notify it
        self.final_kind = "positive"
        self.tee: R.TeeLog | None = None

    def changed(self):
        self.version += 1

    def drain(self):
        """The analysis' lines (R.TeeLog) into the lines the pages read."""
        if self.tee is None:
            return
        lines, skipped = self.tee.drain()
        if skipped:
            lines = [t("analyze_all_lines_skipped", n=skipped)] + lines
        for line in lines:
            self.lines.append(line)
            self.line_count += 1

    async def run(self, database: str, chosen: list[R.Target], targets: list[R.Target]):
        self.running = True
        self.stop.clear()
        self.results = {}
        self.chosen = {x.key for x in chosen}
        found = removed = done = 0
        stopped = False
        log = None
        self.lines.clear()
        try:
            log = R.TeeLog()        # every line in a file, the pages fed by drain()
            self.tee = log
            self.log_path = log.path
            self.changed()
            log.push(f"Scope Archive - {t('page_analyze_all')} - {len(chosen)} folder(s)")
            for x in targets:
                log.push(f"  [{'x' if x in chosen else ' '}] {x.kind} {x.name}: {x.path}"
                         + ("" if x.reachable else " (not reachable)"))
            for i, x in enumerate(chosen, 1):
                if self.stop.is_set():
                    stopped = True
                    break
                self.results[x.key] = "running"
                self.summary = t("analyze_all_progress", i=i, n=len(chosen), name=x.name)
                self.changed()
                log.push(f"── {x.name} ({x.path})")
                try:
                    total, deleted = await run.io_bound(R.analyze, database, x, log, None, self.stop)
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
                self.changed()
            key = "analyze_all_stopped" if stopped else "analyze_all_done"
            self.summary = t(key, n=len(chosen), done=done, total=found, deleted=removed)
            self.final_kind = "warning" if stopped else "positive"
            log.push(self.summary)
        except BaseException as e:      # whatever ends it, the job back to idle
            traceback.print_exc()
            self.summary = t("error_generic", error=e)
            self.final_kind = "negative"
        finally:
            if log is not None:
                log.close()
                self.drain()        # the last lines
            self.tee = None
            # Back to idle in any case - a failure reading the new dates left
            # the spinner and "Analyzing 9/9" (user-reported)
            for key, value in list(self.results.items()):
                if value == "running":
                    self.results.pop(key)
            self.running = False
            self.finished += 1
            self.changed()


JOB = _Job()


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
        self.seen_version = -1
        self.seen_finished = JOB.finished
        self.seen_lines = max(0, JOB.line_count - len(JOB.lines))   # the lines still kept
        self.build_ui()

    def build_ui(self):
        self.conn = connect_db(self.database)
        self.register_conn_close()
        self.targets = R.list_targets(self.conn)
        # The folders of a running analysis ticked as they were
        self.selected = {x.key: (x.key in JOB.chosen if JOB.running else x.reachable) for x in self.targets}
        with ui.card().classes("w-full max-w-5xl mx-auto gap-3"):
            ui.label(t("analyze_all_intro")).classes("text-sm text-gray-600")
            self.list_view()
            with ui.row().classes("items-center gap-3"):
                self.start_btn = ui.button(t("analyze_all_start"), icon="manage_search",
                                           on_click=self.start).props("no-caps")
                self.stop_btn = ui.button(t("analyze_all_stop"), icon="stop", color="negative",
                                          on_click=self._ask_stop).props("no-caps")
                self.summary = ui.label("").classes("text-sm")
            self.log = ui.log(max_lines=_KEPT_LINES).classes("w-full").style("height: 300px")
            with ui.row().classes("items-center gap-2 text-xs text-gray-500") as self.log_row:
                ui.icon("description", size="xs")
                self.log_path = ui.label("").classes("font-mono break-all")
                ui.button(t("analyze_all_open_log"), icon="open_in_new",
                          on_click=lambda: on_this_pc() and R.open_path(self.log_path.text)).props("flat dense no-caps size=sm")
                ui.button(t("analyze_all_open_folder"), icon="folder",
                          on_click=lambda: on_this_pc() and R.show_in_folder(self.log_path.text)) \
                    .props("flat dense no-caps size=sm")
        self._sync()
        # The analysis' lines and state reach the page in batches (see R.TeeLog)
        ui.timer(0.5, self._sync)

    def _sync(self):
        """This page shown as the job is: its lines since the last time, its
        results, buttons and summary when they changed, its end notified."""
        if JOB.running:
            JOB.drain()
        first = JOB.line_count - len(JOB.lines)
        if JOB.line_count > self.seen_lines:
            start = max(self.seen_lines, first) - first
            for line in list(JOB.lines)[start:]:   # all sent together: one update for the browsers
                self.log.push(line)
            self.seen_lines = JOB.line_count
        if self.seen_version != JOB.version:
            self.seen_version = JOB.version
            self.start_btn.set_enabled(not JOB.running)
            self.stop_btn.set_visibility(JOB.running)
            if JOB.running and not JOB.stop.is_set():
                self.stop_btn.enable()
                self.stop_btn.set_text(t("analyze_all_stop"))
            elif JOB.running:
                self.stop_btn.disable()
                self.stop_btn.set_text(t("analyze_all_stopping"))
            self.summary.set_text(JOB.summary)
            self.log_path.set_text(JOB.log_path)
            self.log_row.set_visibility(bool(JOB.log_path))
            self.list_view.refresh()
        if self.seen_finished != JOB.finished:
            self.seen_finished = JOB.finished
            ui.notify(JOB.summary, type=JOB.final_kind)
            background_tasks.create(self._refresh_dates(), name="analyze_all_dates")

    def _ask_stop(self):
        """The folder being read stops at its next object's folder (what was
        found kept, nothing removed), the next ones are not started."""
        if not JOB.running:
            return
        JOB.stop.set()
        if JOB.tee:
            JOB.tee.push(t("analyze_all_stopping"))
        JOB.changed()

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
                    box.set_enabled(x.reachable and not JOB.running)
                    with ui.column().classes("gap-0 flex-1").style("min-width: 200px"):
                        ui.label(x.name).classes("text-sm font-medium truncate")
                        ui.label(x.path or "—").classes("text-xs text-gray-500 font-mono break-all")
                    if not x.reachable:
                        ui.label(t("analyze_all_unreachable")).classes("text-xs text-orange-700 shrink-0")
                    else:
                        ui.label(t("analyze_all_last", date=x.last_scan or "—")).classes("text-xs text-gray-500 shrink-0")
                    self._result_cell(JOB.results.get(x.key, ""))

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
        if JOB.running:     # started meanwhile from another page
            ui.notify(t("analyze_all_running"), type="warning")
            return
        chosen = [x for x in self.targets if self.selected.get(x.key) and x.reachable]
        if not chosen:
            ui.notify(t("analyze_all_none"), type="warning")
            return
        self.log.clear()
        self.seen_lines = JOB.line_count
        # The server's task, not this page's: it goes on with the page closed
        JOB.running = True      # at once: a second click sees it
        background_tasks.create(JOB.run(self.database, chosen, self.targets), name="analyze_all")
        self._sync()

    async def _refresh_dates(self):
        """The new scan dates in the list (on its own connection: the page's
        may have been closed by a disconnect during a long analysis)."""
        try:
            dates = await run.io_bound(self._read_dates)
            for x in self.targets:
                x.last_scan = dates.get(x.key, x.last_scan)
            self.list_view.refresh()
        except Exception as e:
            traceback.print_exc()
            ui.notify(t("error_generic", error=e), type="warning", multi_line=True)

    def _read_dates(self) -> dict[str, str]:
        conn = connect_db(self.database)
        try:
            return {x.key: x.last_scan for x in R.list_targets(conn)}
        finally:
            close_db(conn)
