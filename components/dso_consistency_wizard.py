"""
components/dso_consistency_wizard.py

Catalog Edition — objects whose sessions do not match their DSO.

Lists the AstroObjects having sessions whose RA/DEC is far from the
catalog position of the linked DSO (wrong DSO chosen, Unknown object linked
to the wrong neighbour, ...). The object of a session comes from its folder
name and is never changed here: the fix is to link the object to the right
DSO, which is kept by the next rescan.
"""

from nicegui import ui, run

from api.dwarf_backup_db import connect_db, close_db
from api.dwarf_backup_db_api import update_astro_object_dso
from api.dso_association import (
    load_catalog_index, find_inconsistent_objects, find_dso_candidates,
    resolve_session_image, make_thumbnail_data_url, INCONSISTENT_DEFAULT_DEG,
)
from components.dso_association_wizard import render_session, candidate_label, object_title
from components.i18n import t


class DsoConsistencyWizard:
    def __init__(self, database, on_done=None):
        """on_done() is called when the wizard closes after changes."""
        self.database = database
        self.on_done = on_done
        self.index = None
        self.issues = []
        self.pos = 0
        self.session_pos = 0
        self.relinked = 0
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
        if self.on_done and self.relinked:
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
                return index, find_inconsistent_objects(conn, index, float(threshold))
            finally:
                close_db(conn)
        try:
            self.index, self.issues = await run.io_bound(_load)
        except Exception as e:
            print(f"[DsoCheck] load error: {e}")
            self._show_message(t("dso_wizard_load_error", error=e))
            return
        if not self.issues:
            self._show_message(t("dso_check_none"))
            return
        self.pos = 0
        self.session_pos = 0
        await self._render()

    # ── Navigation ───────────────────────────────────────────────────────────

    async def _next(self):
        self.pos += 1
        self.session_pos = 0
        if self.pos >= len(self.issues):
            self._show_summary()
        else:
            await self._render()

    async def _skip(self):
        self.skipped += 1
        await self._next()

    async def _change_session(self, delta):
        sessions = self.issues[self.pos]["sessions"]
        self.session_pos = (self.session_pos + delta) % len(sessions)
        await self._render()

    def _show_summary(self):
        self.progress_label.text = ""
        self._show_message(t("dso_check_summary", relinked=self.relinked, skipped=self.skipped))

    # ── Rendering ────────────────────────────────────────────────────────────

    async def _render(self):
        issue = self.issues[self.pos]
        ao_id, ao_name, ao_desc = issue["astro_object"]
        sessions = issue["sessions"]
        session, sep = sessions[self.session_pos]
        proposal, candidates = find_dso_candidates(
            session["ra_deg"], session["dec_deg"], self.index, session["target"])
        candidates = [c for c in candidates if c["dso_id"] != issue["dso_id"]]
        if proposal and proposal["dso_id"] == issue["dso_id"]:
            proposal = None

        def _thumb():
            conn = connect_db(self.database)
            try:
                image_path = resolve_session_image(conn, session)
            finally:
                close_db(conn)
            return make_thumbnail_data_url(image_path)
        thumb = await run.io_bound(_thumb)

        self.progress_label.text = t("dso_check_progress",
                                     current=self.pos + 1, total=len(self.issues))
        self.body.clear()
        with self.body:
            ui.label(f"⭐ {object_title(ao_id, ao_name)} → {issue['designation']}"
                     ).classes("text-lg font-bold")
            if ao_desc:
                ui.label(ao_desc).classes("text-sm text-gray-500")
            ui.label(t("dso_check_separation", sep=f"{sep:.1f}",
                       designation=issue["designation"])).classes("text-orange-600")
            consistent = issue["total_sessions"] - len(sessions)
            if consistent:
                ui.label(t("dso_check_other_sessions", count=consistent,
                           designation=issue["designation"])).classes("text-sm text-orange-600")

            nav = None
            if len(sessions) > 1:
                nav = (t("dso_wizard_session_n", current=self.session_pos + 1,
                         total=len(sessions)),
                       lambda: self._change_session(-1), lambda: self._change_session(1))
            render_session(session, thumb, nav)

            if proposal:
                ui.label(t("dso_wizard_proposal",
                           designation=proposal["designation"], name=proposal["name"],
                           sep=f"{proposal['separation_deg']:.2f}")).classes("font-semibold")
            else:
                ui.label(t("dso_wizard_no_proposal")).classes("text-orange-600")

            options = {c["dso_id"]: candidate_label(c) for c in candidates}
            choice = ui.select(options, label=t("dso_wizard_candidate"),
                               value=proposal["dso_id"] if proposal else None
                               ).classes("w-full")
            if not options:
                choice.disable()

            with ui.row().classes("w-full justify-between mt-2"):
                with ui.row().classes("gap-2"):
                    ui.button(t("dso_check_relink"), icon="link", color="positive",
                              on_click=lambda: self._relink(ao_id, choice.value))
                    ui.button(t("dso_wizard_no"), icon="close", color="warning",
                              on_click=self._skip)
                ui.button(t("dso_wizard_stop"), on_click=self._show_summary).props("flat")

    # ── Actions ──────────────────────────────────────────────────────────────

    async def _relink(self, ao_id, dso_id):
        if not dso_id:
            ui.notify(t("notif_select_dso_first"), color="red")
            return

        def _save():
            conn = connect_db(self.database)
            try:
                # Empty description → rebuilt from the new DSO
                update_astro_object_dso(conn, ao_id, int(dso_id), "")
            finally:
                close_db(conn)
        await run.io_bound(_save)
        self.relinked += 1
        ui.notify(t("dso_assigned"), type="positive")
        await self._next()
