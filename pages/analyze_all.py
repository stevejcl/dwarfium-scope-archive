"""Analyze everything (tools/full_rescan.py): every Dwarf's local copy and
every backup drive of the database, ticked ones only, one after the
other - a line per folder with its result, and the analyses' log."""
from __future__ import annotations

from nicegui import run, ui

from api.dwarf_backup_db import DB_NAME, connect_db
from components.db_page_mixin import DbPageMixin
from components.i18n import t
from components.menu import menu
from tools import full_rescan as R


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
        self.build_ui()

    def build_ui(self):
        self.conn = connect_db(self.database)
        self.register_conn_close()
        self.targets = R.list_targets(self.conn)
        self.selected = {x.key: x.reachable for x in self.targets}
        with ui.card().classes("w-full max-w-3xl mx-auto gap-3"):
            ui.label(t("analyze_all_intro")).classes("text-sm text-gray-600")
            self.list_view()
            with ui.row().classes("items-center gap-3"):
                self.start_btn = ui.button(t("analyze_all_start"), icon="manage_search",
                                           on_click=self.start).props("no-caps")
                self.summary = ui.label("").classes("text-sm")
            self.log = ui.log(max_lines=200).classes("w-full").style("height: 300px")

    @ui.refreshable_method
    def list_view(self):
        for kind, title in ((R.DWARF, t("analyze_all_dwarfs")), (R.BACKUP, t("analyze_all_backups"))):
            items = [x for x in self.targets if x.kind == kind]
            if not items:
                continue
            ui.label(title).classes("text-xs font-semibold text-gray-500 mt-2")
            for x in items:
                with ui.row().classes("w-full items-center gap-2 no-wrap border-b py-1"):
                    box = ui.checkbox(value=self.selected.get(x.key, False),
                                      on_change=lambda e, k=x.key: self.selected.__setitem__(k, e.value)) \
                        .props("dense")
                    box.set_enabled(x.reachable and not self.running)
                    with ui.column().classes("gap-0 flex-1 min-w-0"):
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
        self.start_btn.disable()
        self.results = {}
        found = removed = 0
        for i, x in enumerate(chosen, 1):
            self.results[x.key] = "running"
            self.summary.set_text(t("analyze_all_progress", i=i, n=len(chosen), name=x.name))
            self.list_view.refresh()
            self.log.push(f"── {x.name} ({x.path})")
            try:
                total, deleted = await run.io_bound(R.analyze, self.database, x, self.log)
                self.results[x.key] = f"+{total} -{deleted}"
                found += total
                removed += deleted
            except Exception as e:
                self.results[x.key] = f"error: {e}"
                self.log.push(f"❌ {e}")
        self.running = False
        self.start_btn.enable()
        # The new scan dates
        self.ensure_conn()
        dates = {x.key: x.last_scan for x in R.list_targets(self.conn)}
        for x in self.targets:
            x.last_scan = dates.get(x.key, x.last_scan)
        self.summary.set_text(t("analyze_all_done", n=len(chosen), total=found, deleted=removed))
        self.list_view.refresh()
        ui.notify(t("analyze_all_done", n=len(chosen), total=found, deleted=removed), type="positive")
