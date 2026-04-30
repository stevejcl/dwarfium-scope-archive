# components/session_notes.py
"""
Reusable SessionNotes widget.
Shows a summary line (moon + seeing + text) when a note exists,
or an "Add observations" button when none exists.
Clicking opens a dialog to create/edit.
"""

from nicegui import ui
from api.dwarf_backup_db_api import get_session_note, save_session_note, delete_session_note
from api.dwarf_location_api import get_location as _get_location, set_dwarfdata_location
from api.dwarf_location_api import set_manual_session_location
from components.location_manager import location_picker
from components.i18n import t

# Moon phase icons + labels
MOON_PHASES = [
    ("🌑", t("moon_new")),
    ("🌒", t("moon_waxing_crescent")),
    ("🌓", t("moon_first_quarter")),
    ("🌔", t("moon_waxing_gibbous")),
    ("🌕", t("moon_full")),
    ("🌖", t("moon_waning_gibbous")),
    ("🌗", t("moon_last_quarter")),
    ("🌘", t("moon_waning_crescent")),
]

SEEING_STARS = ["⭐", "⭐⭐", "⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐⭐⭐"]


def session_notes_widget(conn, backup_entry_id=None, manual_session_id=None):
    """
    Render the session notes widget inline.
    Call inside a ui.column() or ui.card().
    """
    note = get_session_note(conn,
                            backup_entry_id=backup_entry_id,
                            manual_session_id=manual_session_id)

    with ui.card().tight().classes("border border-gray-200 m-2"):
        container = ui.column().classes("w-full gap-1 m-2")
        with container:
            _render_widget(conn, container, note,
                           backup_entry_id, manual_session_id)

    return container


def _render_widget(conn, container, note, backup_entry_id, manual_session_id):
    """Render the summary line or the 'Add' button."""
    container.clear()
    with container:
        if note:
            # Summary line — note columns:
            # [0]=id [1]=backup_entry_id [2]=manual_session_id
            # [3]=summary [4]=note [5]=location_id [6]=moon_phase [7]=seeing
            moon       = note[6] or ""
            seeing_val = int(note[7]) if (note[7] is not None) else 0
            stars      = SEEING_STARS[seeing_val - 1] if 1 <= seeing_val <= 5 else ""
            summary    = note[3] or ""

            # Resolve location name from FK
            location_id = note[5]
            if location_id:
                _loc_row = _get_location(conn, location_id)
                location = _loc_row["name"] if _loc_row else ""
            else:
                location = ""

            with ui.row().classes("w-full items-center gap-2 flex-wrap"):
                ui.button("✏️", on_click=lambda: _open_dialog(
                    conn, container, note, backup_entry_id, manual_session_id)
                ).props("flat dense round").tooltip(t("notes_edit_tooltip"))
                if moon:
                    ui.label(moon).classes("text-xl")
                if stars:
                    ui.label(stars).classes("text-sm")
                if summary:
                    ui.label(summary).classes("text-sm flex-1 text-gray-700 italic")

            if location:
                ui.label(f"📍 {location}").classes("text-xs text-gray-500")
        else:
            ui.button(
                t("notes_add_btn"),
                on_click=lambda: _open_dialog(
                    conn, container, None, backup_entry_id, manual_session_id)
            ).props("flat").classes("text-sm text-gray-400")


def _open_dialog(conn, container, note, backup_entry_id, manual_session_id):
    """Open the create/edit dialog."""
    note_id        = note[0] if note else None
    summary_val    = note[3] if note else ""
    note_val       = note[4] if note else ""
    location_id_val = note[5] if note else None
    moon_val       = note[6] if note else ""
    seeing_val     = int(note[7]) if (note and note[7] is not None) else 0

    selected_moon        = [moon_val]
    selected_seeing      = [seeing_val]
    selected_location_id = [location_id_val]

    with ui.dialog() as dialog, ui.card().classes("w-full max-w-lg"):
        ui.label(t("notes_title")).classes("text-lg font-bold mb-2")

        # Moon phase selector
        ui.label(t("notes_moon")).classes("text-sm font-semibold mt-2")
        with ui.row().classes("gap-1 flex-wrap"):
            moon_btns = {}
            def make_moon_click(phase_icon):
                def click():
                    selected_moon[0] = phase_icon
                    for icon, btn in moon_btns.items():
                        btn.props(
                            "color=primary" if icon == phase_icon
                            else "color=grey-4"
                        )
                return click
            for icon, label in MOON_PHASES:
                btn = ui.button(icon, on_click=make_moon_click(icon)) \
                    .props("round").tooltip(label)
                if icon == moon_val:
                    btn.props("color=primary")
                else:
                    btn.props("color=grey-4")
                moon_btns[icon] = btn

        # Seeing selector
        ui.label(t("notes_seeing")).classes("text-sm font-semibold mt-2")
        with ui.row().classes("gap-1"):
            seeing_btns = {}
            def make_seeing_click(val):
                def click():
                    selected_seeing[0] = val
                    for v, btn in seeing_btns.items():
                        btn.props(
                            "color=primary" if v <= val
                            else "color=grey-4"
                        )
                return click
            for i in range(1, 6):
                btn = ui.button("⭐", on_click=make_seeing_click(i)) \
                    .props("round dense")
                if i <= seeing_val:
                    btn.props("color=primary")
                else:
                    btn.props("color=grey-4")
                seeing_btns[i] = btn

        # Location picker (FK → ObservationLocation)
        # "Apply to session" propagates location_id to DwarfData or ManualSession
        def _on_location_change(loc_id):
            selected_location_id[0] = loc_id

        def _on_apply_to_session(loc_id):
            """Propagate selected location to DwarfData or ManualSession."""
            if loc_id is None:
                return
            if backup_entry_id:
                from api.dwarf_backup_db_api import get_backup_entry
                entry = get_backup_entry(conn, backup_entry_id)
                if entry and entry.get("dwarf_data_id"):
                    set_dwarfdata_location(conn, entry["dwarf_data_id"], loc_id)
                    ui.notify(t("loc_saved"), type="positive")
            elif manual_session_id:
                set_manual_session_location(conn, manual_session_id, loc_id)
                ui.notify(t("loc_saved"), type="positive")

        with ui.column().classes("w-full mt-2 gap-0"):
            ui.label(t("notes_location")).classes("text-sm font-semibold")
            location_picker(
                conn,
                current_location_id=location_id_val,
                on_change=_on_location_change,
                show_apply_button=bool(backup_entry_id or manual_session_id),
                on_apply=_on_apply_to_session,
            )

        # Summary
        summary_input = ui.input(
            label=t("notes_summary"),
            value=summary_val,
            placeholder=t("notes_summary_ph")
        ).classes("w-full mt-2") \
         .props("maxlength=140 counter")

        # Note
        note_input = ui.textarea(
            label=t("notes_detail"),
            value=note_val,
            placeholder=t("notes_detail_ph")
        ).classes("w-full mt-2").props("rows=4 autogrow")

        # Buttons
        with ui.row().classes("w-full justify-between mt-4"):
            if note_id:
                def delete_note():
                    delete_session_note(conn, note_id)
                    dialog.close()
                    _render_widget(conn, container, None,
                                   backup_entry_id, manual_session_id)
                ui.button(t("delete"), on_click=delete_note) \
                    .props("flat color=negative")
            else:
                ui.label("")

            with ui.row().classes("gap-2"):
                ui.button(t("cancel"), on_click=dialog.close).props("flat")
                def save():
                    new_id = save_session_note(
                        conn,
                        summary=summary_input.value.strip(),
                        note=note_input.value.strip(),
                        location_id=selected_location_id[0],
                        moon_phase=selected_moon[0],
                        seeing=selected_seeing[0] or None,
                        backup_entry_id=backup_entry_id,
                        manual_session_id=manual_session_id,
                        note_id=note_id,
                    )
                    ui.notify(t("notes_saved"), type="positive")
                    dialog.close()
                    updated = get_session_note(
                        conn,
                        backup_entry_id=backup_entry_id,
                        manual_session_id=manual_session_id
                    )
                    _render_widget(conn, container, updated,
                                   backup_entry_id, manual_session_id)

                ui.button(t("save"), on_click=save).props("color=primary")

    dialog.open()
