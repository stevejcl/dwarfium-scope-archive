"""
components/dso_association_wizard.py

Catalog Edition — step-by-step association of AstroObjects without DSO.

For each unlinked AstroObject: take the RA/DEC of one of its sessions,
propose the nearest catalog object, show the session's stacked image for a
visual check, and let the user accept (yes) or skip (no) before moving on.
"""

from nicegui import ui, run, background_tasks

from api.dwarf_backup_db import connect_db, close_db
from api.dwarf_backup_db_api import update_astro_object_dso, DEFAULT_GROUP_NAMES
from api.dwarf_backup_fct import hours_to_hms, deg_to_dms, show_short_date_session
from api.dso_association import (
    load_catalog_index, get_unlinked_astro_objects, get_object_sessions,
    find_dso_candidates, make_thumbnail_data_url,
)
from components.astro_object_associate import show_assign_dialog
from components.i18n import t


_SOURCE_ICONS = {"backup": "💾", "dwarf": "🔭", "manual": "📷"}


def _session_date(value):
    if not value:
        return ""
    text = show_short_date_session(value)
    return value if text == "N/A" else text


def _position_label(session):
    if session.get("position_source") == "solved":
        label = t("position_solved")
        offset = session.get("goto_offset_deg")
        if offset is not None and offset > 1.0:
            label += " " + t("position_goto_offset", offset=f"{offset:.1f}")
        return label
    return t("position_goto")


def render_session(session, thumb, nav=None):
    """Session line (source, date, target, RA/DEC, Aladin link) and its
    thumbnail. nav: optional (label, on_prev, on_next) to browse sessions."""
    ra_txt = hours_to_hms(session["ra_deg"] / 15.0)
    dec_txt = deg_to_dms(session["dec_deg"])
    with ui.row().classes("w-full items-center gap-2"):
        ui.label(
            f"{_SOURCE_ICONS.get(session['source'], '')} "
            f"{_session_date(session['session_date'])} · {session['target'] or ''} · "
            f"RA {ra_txt} · DEC {dec_txt} · {_position_label(session)}"
        ).classes("text-sm")
        aladin = (f"https://aladin.cds.unistra.fr/AladinLite/?target="
                  f"{session['ra_deg']:.5f}+{session['dec_deg']:+.5f}"
                  f"&fov=3&survey=P%2FDSS2%2Fcolor")
        ui.button("Aladin", icon="public",
                  on_click=lambda u=aladin: ui.navigate.to(u, new_tab=True)
                  ).props("flat dense size=sm")
    if session.get("session_dir"):
        ui.label(f"📁 {session['session_dir']}").classes("text-xs text-gray-500")
    if nav:
        # On its own line: the session line above is often long
        label, on_prev, on_next = nav
        with ui.row().classes("w-full items-center justify-center gap-2"):
            ui.button(icon="chevron_left", on_click=on_prev).props("flat dense round")
            ui.label(label).classes("text-sm")
            ui.button(icon="chevron_right", on_click=on_next).props("flat dense round")

    if thumb:
        ui.image(thumb).classes("w-full rounded").style("max-height: 420px; object-fit: contain")
    else:
        ui.label(t("dso_wizard_no_image")).classes("text-sm text-orange-600")


def object_title(ao_id, ao_name):
    """Unknown / MOSAIC_Unknown / Manual objects share their name (one per
    position): add the id to tell them apart."""
    return f"{ao_name} #{ao_id}" if ao_name in DEFAULT_GROUP_NAMES else ao_name


def candidate_label(c):
    label = (f"{c['designation']} — {c['name']} ({c['type']}, "
             f"{c['constellation']}) · {c['separation_deg']:.2f}°")
    if c["by_name"]:
        label += f" · {t('dso_wizard_name_match')}"
    return label


class DsoAssociationWizard:
    def __init__(self, database, on_linked=None):
        """on_linked(astro_object_id) is called after each association."""
        self.database = database
        self.on_linked = on_linked
        self.index = None
        self.objects = []        # [((id, name, description), sessions)]
        self.pos = 0             # index in self.objects
        self.sessions = []       # sessions of the current object
        self.session_pos = 0
        self.candidates = []
        self.linked = 0
        self.skipped = 0
        self.no_coords = 0

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def open(self):
        with ui.dialog().props("persistent") as self.dialog, \
                ui.card().style("width: 760px; max-width: 95vw"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label(t("dso_wizard_title")).classes("text-xl font-semibold")
                self.progress_label = ui.label("").classes("text-sm text-gray-500")
            self.body = ui.column().classes("w-full")
        self.dialog.open()

        with self.body:
            ui.spinner(size="lg").classes("m-4")
            ui.label(t("dso_wizard_loading"))

        def _load():
            conn = connect_db(self.database)
            try:
                index = load_catalog_index(conn)
                # Keep only objects having at least one session with RA/DEC
                objects, no_coords = [], 0
                for ao in get_unlinked_astro_objects(conn):
                    sessions = get_object_sessions(conn, ao[0])
                    if sessions:
                        objects.append((ao, sessions))
                    else:
                        no_coords += 1
                return index, objects, no_coords
            finally:
                close_db(conn)
        try:
            self.index, self.objects, self.no_coords = await run.io_bound(_load)
        except Exception as e:
            print(f"[DsoWizard] load error: {e}")
            self._show_message(t("dso_wizard_load_error", error=e))
            return
        await self._show_current()

    def _close(self):
        self.dialog.close()
        self.dialog.clear()

    def _show_message(self, text):
        self.body.clear()
        with self.body:
            ui.label(text)
            with ui.row().classes("w-full justify-end"):
                ui.button(t("close"), on_click=self._close)

    # ── Navigation ───────────────────────────────────────────────────────────

    async def _show_current(self):
        if self.pos >= len(self.objects):
            self._show_summary()
            return
        self.sessions = self.objects[self.pos][1]
        self.session_pos = 0
        await self._render()

    async def _next_object(self):
        self.pos += 1
        await self._show_current()

    async def _skip(self):
        self.skipped += 1
        await self._next_object()

    async def _change_session(self, delta):
        self.session_pos = (self.session_pos + delta) % len(self.sessions)
        await self._render()

    def _show_summary(self):
        self.progress_label.text = ""
        self._show_message(t("dso_wizard_summary",
                             linked=self.linked, skipped=self.skipped,
                             no_coords=self.no_coords))

    # ── Rendering ────────────────────────────────────────────────────────────

    async def _render(self):
        ao_id, ao_name, ao_desc = self.objects[self.pos][0]
        session = self.sessions[self.session_pos]
        proposal, self.candidates = find_dso_candidates(
            session["ra_deg"], session["dec_deg"], self.index, ao_name)
        thumb = await run.io_bound(make_thumbnail_data_url, session["image_path"])

        self.progress_label.text = t("dso_wizard_progress",
                                     current=self.pos + 1, total=len(self.objects))
        self.body.clear()
        with self.body:
            ui.label(f"⭐ {object_title(ao_id, ao_name)}").classes("text-lg font-bold")
            if ao_desc:
                ui.label(ao_desc).classes("text-sm text-gray-500")

            # Session info + navigation between the object's sessions
            nav = None
            if len(self.sessions) > 1:
                nav = (t("dso_wizard_session_n", current=self.session_pos + 1,
                         total=len(self.sessions)),
                       lambda: self._change_session(-1), lambda: self._change_session(1))
            render_session(session, thumb, nav)

            # Proposal + alternatives
            if proposal:
                ui.label(t("dso_wizard_proposal",
                           designation=proposal["designation"], name=proposal["name"],
                           sep=f"{proposal['separation_deg']:.2f}")).classes("font-semibold")
            else:
                ui.label(t("dso_wizard_no_proposal")).classes("text-orange-600")

            options = {c["dso_id"]: candidate_label(c) for c in self.candidates}
            choice = ui.select(options, label=t("dso_wizard_candidate"),
                               value=proposal["dso_id"] if proposal else None
                               ).classes("w-full")
            if not options:
                choice.disable()
            # An existing (user) description is kept unless asked otherwise
            update_desc = ui.checkbox(t("dso_wizard_update_desc"), value=False)
            update_desc.set_visibility(bool(ao_desc))

            with ui.row().classes("w-full justify-between mt-2"):
                with ui.row().classes("gap-2"):
                    ui.button(t("dso_wizard_yes"), icon="check", color="positive",
                              on_click=lambda: self._accept(ao_id, choice.value, update_desc.value))
                    ui.button(t("dso_wizard_no"), icon="close", color="warning",
                              on_click=self._skip)
                    ui.button(t("dso_wizard_manual"), icon="search",
                              on_click=self._manual).props("flat")
                ui.button(t("dso_wizard_stop"), on_click=self._show_summary).props("flat")

    # ── Actions ──────────────────────────────────────────────────────────────

    async def _accept(self, ao_id, dso_id, update_desc):
        if not dso_id:
            ui.notify(t("notif_select_dso_first"), color="red")
            return
        ao_desc = self.objects[self.pos][0][2]

        def _save():
            conn = connect_db(self.database)
            try:
                # Empty description → update_astro_object_dso builds it from the catalog
                update_astro_object_dso(conn, ao_id, int(dso_id),
                                        "" if update_desc else (ao_desc or ""))
            finally:
                close_db(conn)
        await run.io_bound(_save)
        self.linked += 1
        ui.notify(t("dso_assigned"), type="positive")
        if self.on_linked:
            self.on_linked(ao_id)
        await self._next_object()

    def _manual(self):
        """Fall back to the regular assign dialog (catalog search)."""
        ao_id, ao_name, ao_desc = self.objects[self.pos][0]

        async def _done():
            self.linked += 1
            if self.on_linked:
                self.on_linked(ao_id)
            await self._next_object()
        # show_assign_dialog calls on_done synchronously
        show_assign_dialog(self.database, (ao_id, ao_name, ao_desc, None),
                           on_done=lambda: background_tasks.create(_done()))
