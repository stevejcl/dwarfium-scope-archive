"""
components/dso_consistency_wizard.py

Catalog Edition — sessions inconsistent with their AstroObject.

Lists the sessions whose RA/DEC is far from the catalog position of the
DSO linked to their AstroObject (object named after a sub-folder instead of
the real target, session filed under the wrong object, ...). For each one
the user can move the session to a more representative existing object,
create a new object linked to the right DSO, or skip it.
"""

from nicegui import ui, run

from api.dwarf_backup_db import connect_db, close_db
from api.dso_association import (
    load_catalog_index, find_inconsistent_sessions, find_dso_candidates,
    get_astro_objects_by_dso, reassign_session, create_astro_object_for_dso,
    resolve_session_image, make_thumbnail_data_url, INCONSISTENT_DEFAULT_DEG,
)
from components.dso_association_wizard import render_session, candidate_label
from components.i18n import t


class DsoConsistencyWizard:
    def __init__(self, database, on_done=None):
        """on_done() is called when the wizard closes after changes."""
        self.database = database
        self.on_done = on_done
        self.index = None
        self.issues = []
        self.all_objects = []    # [(id, name)] for the manual choice
        self.pos = 0
        self.reassigned = 0
        self.created = 0
        self.skipped = 0

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def open(self):
        with ui.dialog().props("persistent") as self.dialog, \
                ui.card().style("width: 760px; max-width: 95vw"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label(t("dso_check_title")).classes("text-xl font-semibold")
                self.progress_label = ui.label("").classes("text-sm text-gray-500")
            self.body = ui.column().classes("w-full")
        self.dialog.open()
        self._show_settings()

    def _close(self):
        self.dialog.close()
        if self.on_done and (self.reassigned or self.created):
            self.on_done()

    def _show_message(self, text):
        self.body.clear()
        with self.body:
            ui.label(text)
            with ui.row().classes("w-full justify-end"):
                ui.button(t("close"), on_click=self._close)

    def _show_settings(self):
        self.body.clear()
        with self.body:
            ui.label(t("dso_check_intro")).classes("text-sm")
            threshold = ui.number(t("dso_check_threshold"), value=INCONSISTENT_DEFAULT_DEG,
                                  min=0.1, max=90, step=0.5, format="%.1f").classes("w-48")
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button(t("cancel"), on_click=self._close).props("flat")
                ui.button(t("dso_check_run"), icon="search",
                          on_click=lambda: self._analyse(threshold.value or INCONSISTENT_DEFAULT_DEG))

    async def _analyse(self, threshold):
        self.body.clear()
        with self.body:
            ui.spinner(size="lg").classes("m-4")
            ui.label(t("dso_wizard_loading"))

        def _load():
            conn = connect_db(self.database)
            try:
                index = load_catalog_index(conn)
                issues = find_inconsistent_sessions(conn, index, float(threshold))
                objects = conn.execute(
                    "SELECT id, name FROM AstroObject WHERE COALESCE(is_group, 0) = 0 "
                    "ORDER BY name COLLATE NOCASE").fetchall()
                return index, issues, objects
            finally:
                close_db(conn)
        try:
            self.index, self.issues, self.all_objects = await run.io_bound(_load)
        except Exception as e:
            print(f"[DsoCheck] load error: {e}")
            self._show_message(t("dso_wizard_load_error", error=e))
            return
        if not self.issues:
            self._show_message(t("dso_check_none"))
            return
        self.pos = 0
        await self._render()

    # ── Navigation ───────────────────────────────────────────────────────────

    async def _next(self):
        self.pos += 1
        if self.pos >= len(self.issues):
            self._show_summary()
        else:
            await self._render()

    async def _skip(self):
        self.skipped += 1
        await self._next()

    def _show_summary(self):
        self.progress_label.text = ""
        self._show_message(t("dso_check_summary", reassigned=self.reassigned,
                             created=self.created, skipped=self.skipped))

    # ── Rendering ────────────────────────────────────────────────────────────

    async def _render(self):
        issue = self.issues[self.pos]
        ao_id, ao_name, ao_desc = issue["astro_object"]
        session = issue["session"]
        proposal, candidates = find_dso_candidates(
            session["ra_deg"], session["dec_deg"], self.index, session["target"])

        def _fetch():
            conn = connect_db(self.database)
            try:
                image_path = resolve_session_image(conn, session)
                by_dso = get_astro_objects_by_dso(conn, [c["dso_id"] for c in candidates])
            finally:
                close_db(conn)
            return make_thumbnail_data_url(image_path), by_dso
        thumb, by_dso = await run.io_bound(_fetch)

        self.progress_label.text = t("dso_check_progress",
                                     current=self.pos + 1, total=len(self.issues))
        self.body.clear()
        with self.body:
            ui.label(f"⭐ {ao_name} → {issue['designation']}").classes("text-lg font-bold")
            ui.label(t("dso_check_separation", sep=f"{issue['separation_deg']:.1f}",
                       designation=issue["designation"])).classes("text-orange-600")
            render_session(session, thumb)

            if proposal:
                ui.label(t("dso_wizard_proposal",
                           designation=proposal["designation"], name=proposal["name"],
                           sep=f"{proposal['separation_deg']:.2f}")).classes("font-semibold")
            else:
                ui.label(t("dso_wizard_no_proposal")).classes("text-orange-600")

            # A — move to an existing object: nearby ones first, then all
            existing = {}
            for c in candidates:
                for obj_id, obj_name in by_dso.get(c["dso_id"], []):
                    if obj_id != ao_id and obj_id not in existing:
                        existing[obj_id] = (f"★ {obj_name} — {c['designation']} · "
                                            f"{c['separation_deg']:.2f}°")
            nearby_default = next(iter(existing), None)
            for obj_id, obj_name in self.all_objects:
                if obj_id != ao_id and obj_id not in existing:
                    existing[obj_id] = obj_name

            with ui.card().classes("w-full").props("flat bordered"):
                ui.label(t("dso_check_reassign_title")).classes("font-semibold")
                target_obj = ui.select(existing, label=t("dso_check_existing_object"),
                                       value=nearby_default, with_input=True).classes("w-full")
                ui.button(t("dso_check_reassign"), icon="move_down", color="positive",
                          on_click=lambda: self._reassign(target_obj.value))

            # B — create a new object linked to the right DSO
            dso_options = {c["dso_id"]: candidate_label(c) for c in candidates}
            default_dso = proposal or (candidates[0] if candidates else None)
            with ui.card().classes("w-full").props("flat bordered"):
                ui.label(t("dso_check_create_title")).classes("font-semibold")
                new_dso = ui.select(dso_options, label=t("dso_wizard_candidate"),
                                    value=default_dso["dso_id"] if default_dso else None
                                    ).classes("w-full")
                new_name = ui.input(t("dso_check_new_name"),
                                    value=default_dso["designation"] if default_dso else ""
                                    ).classes("w-full")

                def _dso_changed(e):
                    c = next((c for c in candidates if c["dso_id"] == e.value), None)
                    if c:
                        new_name.value = c["designation"]
                new_dso.on_value_change(_dso_changed)
                create_btn = ui.button(t("dso_check_create"), icon="add", color="positive",
                                       on_click=lambda: self._create(new_name.value, new_dso.value))
                if not dso_options:
                    new_dso.disable()
                    create_btn.disable()

            if session["source"] != "manual":
                ui.label(t("dso_check_rescan_warning")).classes("text-xs text-gray-500")

            with ui.row().classes("w-full justify-between mt-2"):
                ui.button(t("dso_wizard_no"), icon="close", color="warning", on_click=self._skip)
                ui.button(t("dso_wizard_stop"), on_click=self._show_summary).props("flat")

    # ── Actions ──────────────────────────────────────────────────────────────

    async def _reassign(self, to_ao_id):
        if not to_ao_id:
            ui.notify(t("dso_check_select_object"), color="red")
            return
        issue = self.issues[self.pos]

        def _save():
            conn = connect_db(self.database)
            try:
                return reassign_session(conn, issue["session"], issue["astro_object"][0], int(to_ao_id))
            finally:
                close_db(conn)
        if await run.io_bound(_save):
            self.reassigned += 1
            ui.notify(t("dso_check_reassigned"), type="positive")
        else:
            ui.notify(t("dso_check_not_updated"), type="warning")
        await self._next()

    async def _create(self, name, dso_id):
        if not dso_id or not (name or "").strip():
            ui.notify(t("dso_check_name_required"), color="red")
            return
        issue = self.issues[self.pos]

        def _save():
            conn = connect_db(self.database)
            try:
                new_id, created = create_astro_object_for_dso(conn, name, int(dso_id))
                if not new_id:
                    return None, False, 0
                updated = reassign_session(conn, issue["session"], issue["astro_object"][0], new_id)
                return new_id, created, updated
            finally:
                close_db(conn)
        new_id, created, updated = await run.io_bound(_save)
        if not new_id:
            ui.notify(t("dso_check_not_updated"), type="warning")
            return
        if created:
            self.created += 1
            self.all_objects.append((new_id, name.strip()))
        else:
            ui.notify(t("dso_check_object_reused", name=name.strip()), type="info")
        if updated:
            self.reassigned += 1
            ui.notify(t("dso_check_reassigned"), type="positive")
        await self._next()
