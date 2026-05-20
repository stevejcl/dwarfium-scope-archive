"""
pages/report.py — Storage Report page
--------------------------------------
Shows disk usage by drive (backup or Dwarf local copy) and lists sessions
sorted by size or by date, with links back to Explore.

Route: /Report
"""

import os
import urllib.parse
from nicegui import ui, app, run, background_tasks

from api.dwarf_backup_db import DB_NAME, connect_db, close_db
from api.dwarf_backup_db_api import (
    get_backupDrive_list,
    get_dwarf_Names,
    get_backupDrive_detail,
)
from api.dwarf_backup_fct import (
    get_local_dwarf_dir,
    format_size,
    show_date_session,
)
from api.diskinfo import load_disk_info, load_all_disk_info
from components.i18n import t
from components.menu import menu
from components.db_page_mixin import DbPageMixin
from components.disk_space_widget import disk_space_widget
from tools.quality_scan import get_sessions_with_sizes, scan_folder_sizes, scan_dwarf_session_sizes


# ── Page route ────────────────────────────────────────────────────────────────

@ui.page('/Report')
async def report_page(BackupDriveId: int = None, DwarfId: int = None,
                      DriveType: str = None, OrderBy: str = None, Limit: int = None):
    print(f"[report] BackupDriveId={BackupDriveId} DwarfId={DwarfId} DriveType={DriveType} OrderBy={OrderBy} Limit={Limit}")
    menu(t("page_report"))
    await ui.context.client.connected(timeout=10.0)

    app_instance = ReportApp(DB_NAME,
                             init_backup_id=BackupDriveId,
                             init_dwarf_id=DwarfId,
                             init_drive_type=DriveType,
                             init_order_by=OrderBy,
                             init_limit=Limit)
    ui.context.client.on_disconnect(app_instance.cancel_tasks)


# ── App class ─────────────────────────────────────────────────────────────────

class ReportApp(DbPageMixin):

    def __init__(self, database, init_backup_id=None, init_dwarf_id=None,
                 init_drive_type=None, init_order_by=None, init_limit=None):
        self.database       = database
        self.conn           = connect_db(database)
        self.register_conn_close()

        self._init_backup_id  = init_backup_id
        self._init_dwarf_id   = init_dwarf_id

        self._drive_type = init_drive_type or ("dwarf" if init_dwarf_id and not init_backup_id else "backup")
        self._backup_id  = init_backup_id
        self._dwarf_id   = init_dwarf_id
        self._order_by   = init_order_by or "size"
        self._limit      = init_limit if init_limit is not None else 50
        self._initializing = True  # block _on_drive_changed during build

        # UI refs
        self._disk_widget   = None
        self._table_area    = None
        self._calc_btn      = None
        self._scan_running  = False

        self._build_ui()

    def cancel_tasks(self):
        pass  # no timers to cancel on this page

    # ------------------------------------------------------------------
    # UI build
    # ------------------------------------------------------------------

    def _build_ui(self):
        with ui.column().classes("w-full mx-auto gap-4 p-4"):

            # ── Drive selector row ────────────────────────────────────
            with ui.card().classes("w-full p-4"):
                ui.label(t("report_drive_info")).classes("text-lg font-semibold mb-2")

                with ui.row().classes("w-full items-start gap-6 flex-wrap"):
                    with ui.row().classes("gap-2"):
                        self._btn_backup = ui.button(
                            t("menu_backup"),
                            on_click=lambda: self._switch_type("backup")
                        ).props("flat")
                        self._btn_dwarf = ui.button(
                            "Dwarf",
                            on_click=lambda: self._switch_type("dwarf")
                        ).props("flat")

                with ui.row().classes("w-full items-start gap-6 flex-wrap"):
                    # Left: drive type tabs + selector
                    with ui.column().classes("gap-2 flex-1 min-w-64"):
                        self._drive_select = ui.select(
                            options=[],
                            on_change=self._on_drive_changed,
                            label=t("report_select_drive"),
                        ).props("outlined").classes("w-full")

                    # Right: disk space widget — aligned with the selector
                    with ui.column().classes("flex-1 min-w-64 justify-end"):
                        self._disk_widget = disk_space_widget(None)

            # ── Options row ───────────────────────────────────────────
            with ui.row().classes("w-full items-center gap-4 flex-wrap"):
                with ui.row().classes("items-center gap-2"):
                    ui.label(t("report_show")).classes("text-sm")
                    self._limit_options = {"20": 20, "50": 50, "100": 100, t("report_all"): 0}
                    _limit_label = next((k for k, v in self._limit_options.items() if v == self._limit), "50")
                    self._limit_select = ui.select(
                        options=list(self._limit_options.keys()),
                        value=_limit_label,
                        on_change=lambda e: self._set_limit(self._limit_options.get(e.value, 50)),
                    ).classes("w-24")

                with ui.row().classes("items-center gap-2"):
                    self._btn_size = ui.button(
                        t("report_biggest"),
                        on_click=lambda: self._set_order("size")
                    ).props("flat")
                    self._btn_date = ui.button(
                        t("report_latest"),
                        on_click=lambda: self._set_order("date")
                    ).props("flat")

                with ui.row().classes("items-center gap-1"):
                    self._calc_btn = ui.button(
                        t("report_calc_sizes"),
                        on_click=self._start_size_scan,
                    ).props("color=primary")
                    self._calc_force_btn = ui.button(
                        icon="refresh",
                        on_click=self._confirm_size_scan_force,
                    ).props("color=primary flat round dense size=sm").tooltip(t("report_calc_sizes_force"))

                with ui.row().classes("items-center gap-1"):
                    self._calc_dwarf_btn = ui.button(
                        t("report_calc_dwarf_sizes"),
                        on_click=self._start_dwarf_size_scan,
                    ).props("color=primary")
                    self._calc_dwarf_force_btn = ui.button(
                        icon="refresh",
                        on_click=self._confirm_dwarf_size_scan_force,
                    ).props("color=primary flat round dense size=sm").tooltip(t("report_calc_sizes_force"))

                self._calc_progress = ui.label("").classes("text-sm text-gray-400")

            # ── Table ─────────────────────────────────────────────────
            self._table_area = ui.column().classes("w-full gap-0")

        # Populate lists and pre-select if URL params given
        self._populate_drive_list()
        self._refresh_tab_styles()
        self._refresh_order_styles()

        # Pre-select from URL params
        if self._init_backup_id or self._init_dwarf_id:
            if self._init_dwarf_id and not self._init_backup_id:
                self._drive_type = "dwarf"
                self._populate_drive_list()
                self._refresh_tab_styles()
            self._select_drive_in_list()
            # Restore limit selector — find the label for the current limit value
            _label = next((k for k, v in self._limit_options.items() if v == self._limit), "50")
            self._limit_select.set_value(_label)
            self._initializing = False
            self._trigger_disk_widget()
            ui.timer(0.1, self._load_table_async, once=True)
        else:
            self._initializing = False
            if self._drive_options:
                first_key = list(self._drive_options.keys())[0]
                self._drive_select.set_value(first_key)
                self._trigger_disk_widget()
                ui.timer(0.1, self._load_table_async, once=True)

    def _trigger_disk_widget(self):
        """Refresh the disk widget for the currently selected drive."""
        current_label = self._drive_select.value
        if not current_label or current_label not in self._drive_options:
            return
        did, loc, name = self._drive_options[current_label]

        async def _refresh():
            await self._disk_widget.refresh(
                loc or None,
                drive_type=self._drive_type,
                drive_id=did,
                name=name,
            )
        ui.timer(0.05, _refresh, once=True)

    def _make_back_url(self) -> str:
        """Build the /Report URL that restores current state (for back_url in Explore).
        We append &_= so that Explore's back button can append its drive id
        without breaking the URL (it becomes &_=<id> which is ignored by Report)."""
        params = {"DriveType": self._drive_type,
                  "OrderBy":   self._order_by,
                  "Limit":     self._limit}
        if self._drive_type == "backup" and self._backup_id:
            params["BackupDriveId"] = self._backup_id
        elif self._drive_type == "dwarf" and self._dwarf_id:
            params["DwarfId"] = self._dwarf_id
        base = "/Report?" + urllib.parse.urlencode(params)
        return base + "&_="  # absorbs the id appended by Explore's back button

    # ------------------------------------------------------------------
    # Drive list helpers
    # ------------------------------------------------------------------

    def _populate_drive_list(self):
        self._drive_options = {}  # label -> (id, location, name)

        if self._drive_type == "backup":
            drives = get_backupDrive_list(self.conn)
            # Build dwarf_id -> name lookup
            dwarf_names = {did: name for did, name in get_dwarf_Names(self.conn)}
            # (id, name, description, location, astroDir, dwarf_id, last_scan)
            for did, name, _desc, loc, _astro, dwarf_id, _scan in drives:
                cached = load_disk_info("backup", did)
                suffix = ""
                if cached:
                    pct = cached.get("free_pct", 0)
                    suffix = f"  ({cached['free_str']} free)"
                    if pct < 5:
                        suffix = f"  🔴 {cached['free_str']} free"
                    elif pct < 15:
                        suffix = f"  ⚠️ {cached['free_str']} free"
                dwarf_suffix = f" ({dwarf_names[dwarf_id]})" if dwarf_id and dwarf_id in dwarf_names else ""
                label = f"{name}{dwarf_suffix}{suffix}"
                self._drive_options[label] = (did, loc or "", name)
        else:
            # Dwarf local copies
            dwarfs = get_dwarf_Names(self.conn)
            for did, name in dwarfs:
                loc = get_local_dwarf_dir(self.conn, did)
                cached = load_disk_info("dwarf", did)
                suffix = ""
                if cached:
                    pct = cached.get("free_pct", 0)
                    suffix = f"  ({cached['free_str']} free)"
                    if pct < 5:
                        suffix = f"  🔴 {cached['free_str']} free"
                    elif pct < 15:
                        suffix = f"  ⚠️ {cached['free_str']} free"
                label = f"{name}{suffix}"
                self._drive_options[label] = (did, loc or "", name)

        options = list(self._drive_options.keys())
        self._drive_select.set_options(options, value=options[0] if options else None)

    def _select_drive_in_list(self):
        target_id = self._backup_id if self._drive_type == "backup" else self._dwarf_id
        for label, (did, loc, name) in self._drive_options.items():
            if did == target_id:
                self._drive_select.set_value(label)
                print(f"[report] selected: {label!r}")
                break

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _switch_type(self, drive_type: str):
        self._drive_type = drive_type
        self._backup_id  = None
        self._dwarf_id   = None
        self._populate_drive_list()
        self._refresh_tab_styles()
        self._table_area.clear()

    def _on_drive_changed(self, event):
        if getattr(self, '_initializing', False):
            return
        label = event.value
        if not label or label not in self._drive_options:
            return
        did, loc, name = self._drive_options[label]
        if self._drive_type == "backup":
            self._backup_id = did
        else:
            self._dwarf_id  = did

        # Refresh disk widget
        async def _refresh():
            await self._disk_widget.refresh(
                loc or None,
                drive_type=self._drive_type,
                drive_id=did,
                name=name,
            )
        ui.timer(0, _refresh, once=True)

        # Reload table
        ui.timer(0.05, self._load_table_async, once=True)

    def _set_order(self, order: str):
        self._order_by = order
        self._refresh_order_styles()
        ui.timer(0, self._load_table_async, once=True)

    def _set_limit(self, limit: int):
        self._limit = limit
        ui.timer(0, self._load_table_async, once=True)

    def _refresh_tab_styles(self):
        backup_active = self._drive_type == "backup"
        self._btn_backup.props(
            f"{'color=primary' if backup_active else 'flat'}"
        )
        self._btn_dwarf.props(
            f"{'color=primary' if not backup_active else 'flat'}"
        )

    def _refresh_order_styles(self):
        self._btn_size.props(
            f"{'color=primary' if self._order_by == 'size' else 'flat'}"
        )
        self._btn_date.props(
            f"{'color=primary' if self._order_by == 'date' else 'flat'}"
        )

    # ------------------------------------------------------------------
    # Table loading
    # ------------------------------------------------------------------

    async def _load_table_async(self):
        backup_id = self._backup_id if self._drive_type == "backup" else None
        dwarf_id  = self._dwarf_id  if self._drive_type == "dwarf"  else None
        limit     = self._limit if self._limit > 0 else 9999

        rows = await run.io_bound(
            get_sessions_with_sizes,
            self.database,
            backup_id,
            dwarf_id,
            self._order_by,
            limit,
        )
        self._current_rows = rows
        self._render_table(rows)

    def _render_table(self, rows: list[dict]):
        self._table_area.clear()

        if not rows:
            with self._table_area:
                ui.label(t("no_session_found")).classes("p-4")
            return

        has_sizes = any(r.get("folder_size_bytes") for r in rows)
        if not has_sizes and self._order_by == "size":
            with self._table_area:
                ui.label(t("report_no_sizes")).classes("text-orange-500 p-4")

        columns = [
            {"name": "date",           "label": t("report_date"),           "field": "date",           "align": "left",  "sortable": True, "style": "width: 100px"},
            {"name": "object",         "label": t("report_object"),         "field": "object",         "align": "left",  "style": ""},
            {"name": "size",           "label": t("report_size"),           "field": "size",           "align": "right", "sortable": True, "style": "width: 90px"},
            {"name": "dwarf_size",     "label": t("report_dwarf_size"),     "field": "dwarf_size",     "align": "right", "sortable": True, "style": "width: 90px"},
            {"name": "dwarf_no_fits",  "label": t("report_dwarf_no_fits"),  "field": "dwarf_no_fits",  "align": "right", "sortable": True, "style": "width: 90px"},
            {"name": "quality",        "label": t("report_quality"),        "field": "quality",        "align": "right", "sortable": True, "style": "width: 70px"},
            {"name": "action",         "label": "",                         "field": "action",         "align": "center","style": "width: 80px"},
        ]

        table_rows = []
        for row in rows:
            sz        = row.get("folder_size_bytes")
            size_str  = row.get("folder_size_str", "—")
            score     = row.get("quality_score")
            entry_id       = row.get("backup_entry_id")
            backup_id      = row.get("backup_drive_id")
            dwarf_id       = row.get("dwarf_id")
            dwarf_entry_id = row.get("dwarf_entry_id")

            back_url = urllib.parse.quote(self._make_back_url(), safe='')

            if self._drive_type == "dwarf" and dwarf_entry_id:
                url = f"/Explore?DwarfId={dwarf_id}&mode=dwarf&SessionId={dwarf_entry_id}&only_already_backed=1&back_url={back_url}"
            else:
                url = f"/Explore?BackupDriveId={backup_id}&DwarfId={dwarf_id}&SessionId={entry_id}&back_url={back_url}"

            table_rows.append({
                "id":                  entry_id,
                "date":                str(row.get("session_date", ""))[:10],
                "object":              row.get("object_name").split(',', 1)[0] or "?",
                "session":             row.get("session_dir", ""),
                "size":                size_str,
                "size_bytes":          sz or 0,
                "dwarf_size":          row.get("dwarf_size_str", "—"),
                "dwarf_size_bytes":    row.get("dwarf_size_bytes") or 0,
                "dwarf_no_fits":       row.get("dwarf_size_no_fits_str", "—"),
                "dwarf_no_fits_bytes": row.get("dwarf_size_no_fits_bytes") or 0,
                "quality":             round(score) if score is not None else None,
                "backup_id":           backup_id,
                "dwarf_id":            dwarf_id,
                "url":                 url,
            })

        with self._table_area:
            table = ui.table(
                columns=columns,
                rows=table_rows,
                row_key="id",
            ).classes("w-full").style("table-layout: fixed")

            table.add_slot("body", r"""
                <q-tr :props="props">
                    <q-td key="date" :props="props">
                        <span class="text-sm">{{ props.row.date }}</span>
                    </q-td>
                    <q-td key="object" :props="props" style="overflow: hidden">
                        <div class="text-sm font-medium" style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap" :title="props.row.object">{{ props.row.object }}</div>
                        <div class="text-xs opacity-50" style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap" :title="props.row.session">{{ props.row.session }}</div>
                    </q-td>
                    <q-td key="size" :props="props">
                        <span class="text-sm font-semibold"
                              :class="{
                                'text-orange-500': props.row.size_bytes > 5368709120,
                                'text-yellow-600': props.row.size_bytes > 2147483648 && props.row.size_bytes <= 5368709120,
                              }">
                            {{ props.row.size }}
                        </span>
                    </q-td>
                    <q-td key="dwarf_size" :props="props">
                        <span class="text-sm"
                              :class="{
                                'text-orange-500': props.row.dwarf_size_bytes > 5368709120,
                                'text-yellow-600': props.row.dwarf_size_bytes > 2147483648 && props.row.dwarf_size_bytes <= 5368709120,
                              }">
                            {{ props.row.dwarf_size }}
                        </span>
                    </q-td>
                    <q-td key="dwarf_no_fits" :props="props">
                        <span class="text-sm text-green-600"
                              v-if="props.row.dwarf_no_fits !== '—'">
                            {{ props.row.dwarf_no_fits }}
                        </span>
                        <span class="text-sm opacity-40" v-else>—</span>
                    </q-td>
                    <q-td key="quality" :props="props">
                        <span v-if="props.row.quality !== null" class="text-sm font-semibold"
                              :class="{
                                'text-green-600':  props.row.quality >= 65,
                                'text-yellow-600': props.row.quality >= 40 && props.row.quality < 65,
                                'text-red-500':    props.row.quality < 40,
                              }">
                            {{ props.row.quality }}
                        </span>
                        <span v-else class="text-sm opacity-40">—</span>
                    </q-td>
                    <q-td key="action" :props="props">
                        <q-btn flat dense size="sm" label="Explore"
                               @click="$parent.$emit('explore', props.row.url)" />
                    </q-td>
                </q-tr>
            """)
            table.on("explore", lambda e: ui.navigate.to(
                e.args if isinstance(e.args, str) else
                e.args[0] if isinstance(e.args, list) else
                e.args.get("url", "")
            ))

    # ------------------------------------------------------------------
    # Folder size scan
    # ------------------------------------------------------------------

    def _start_dwarf_size_scan(self):
        if self._scan_running:
            return
        self._scan_running = True
        self._calc_dwarf_btn.props("loading")
        self._calc_progress.set_text(t("report_calc_running"))
        background_tasks.create(self._run_dwarf_size_scan())

    async def _run_dwarf_size_scan(self, force=False):
        backup_id = self._backup_id if self._drive_type == "backup" else None
        dwarf_id  = self._dwarf_id  if self._drive_type == "dwarf"  else None

        # force always recalculates all sessions for the current drive
        entry_ids = None

        def _progress(current_dir, done, total):
            try:
                self._calc_progress.set_text(f"[{done}/{total}] 🔍 {current_dir}")
            except Exception:
                pass

        measured = await run.io_bound(
            scan_dwarf_session_sizes,
            self.database,
            backup_id,
            dwarf_id,
            force,
            _progress,
            entry_ids,
        )

        self._scan_running = False
        try:
            self._calc_dwarf_btn.props(remove="loading")
            self._calc_dwarf_force_btn.props(remove="loading")
            self._calc_progress.set_text(t("report_sized").format(n=measured))
        except Exception:
            pass

        await self._load_table_async()

    def _confirm_size_scan_force(self):
        async def _do():
            with ui.dialog() as dlg, ui.card():
                ui.label(t("report_force_warning")).classes("text-sm")
                with ui.row().classes("gap-2 mt-2"):
                    ui.button(t("confirm"), on_click=lambda: (dlg.close(), self._start_size_scan_force())).props("color=negative")
                    ui.button(t("cancel"),  on_click=dlg.close).props("flat")
            dlg.open()
        ui.timer(0, _do, once=True)

    def _confirm_dwarf_size_scan_force(self):
        async def _do():
            with ui.dialog() as dlg, ui.card():
                ui.label(t("report_force_warning")).classes("text-sm")
                with ui.row().classes("gap-2 mt-2"):
                    ui.button(t("confirm"), on_click=lambda: (dlg.close(), self._start_dwarf_size_scan_force())).props("color=negative")
                    ui.button(t("cancel"),  on_click=dlg.close).props("flat")
            dlg.open()
        ui.timer(0, _do, once=True)

    def _start_size_scan_force(self):
        if self._scan_running:
            return
        self._scan_running = True
        self._calc_force_btn.props("loading")
        self._calc_progress.set_text(t("report_calc_running"))
        background_tasks.create(self._run_size_scan(force=True))

    def _start_dwarf_size_scan_force(self):
        if self._scan_running:
            return
        self._scan_running = True
        self._calc_dwarf_force_btn.props("loading")
        self._calc_progress.set_text(t("report_calc_running"))
        background_tasks.create(self._run_dwarf_size_scan(force=True))

    def _start_size_scan(self):
        if self._scan_running:
            return
        self._scan_running = True
        self._calc_btn.props("loading")
        self._calc_progress.set_text(t("report_calc_running"))
        background_tasks.create(self._run_size_scan())

    async def _run_size_scan(self, force=False):
        backup_id = self._backup_id if self._drive_type == "backup" else None

        # entry_ids only used for normal scan (unused — force always scans full drive)
        entry_ids = None

        scan_state = {"done": 0, "total": 0}

        def _progress(current_dir, done, total):
            scan_state["done"]  = done
            scan_state["total"] = total
            try:
                self._calc_progress.set_text(
                    f"[{done}/{total}] 🔍 {current_dir}"
                )
            except Exception:
                pass

        measured = await run.io_bound(
            scan_folder_sizes,
            self.database,
            entry_ids,     # None = all, or list of ids for force
            backup_id,
            force,
            _progress,
        )

        self._scan_running = False
        try:
            self._calc_btn.props(remove="loading")
            self._calc_force_btn.props(remove="loading")
            self._calc_progress.set_text(
                t("report_sized").format(n=measured)
            )
        except Exception:
            pass

        # Reload table with fresh sizes
        await self._load_table_async()