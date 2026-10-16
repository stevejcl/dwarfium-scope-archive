"""The warning of the Dwarf and Backup pages when another Scope Archive
installation changed the files of the folder shown (api/shared_changes.py):
this database is behind until it is analyzed again."""
from __future__ import annotations

from nicegui import ui

from api import shared_changes as SC
from components.i18n import t


def refresh(container, root: str | None, button_text: str, on_analyze) -> None:
    """Fills `container` (a ui.column) with the warning, or empties it."""
    container.clear()
    changes = SC.changes_by_others(root) if root else []
    container.set_visibility(bool(changes))
    if not changes:
        return
    latest = changes[0]
    names = ", ".join(dict.fromkeys(c["name"] for c in changes))
    with container:
        with ui.row().classes("w-full items-center gap-3 p-3 rounded bg-orange-50 text-orange-900 no-wrap"):
            ui.icon("sync_problem", color="orange", size="md").classes("shrink-0")
            with ui.column().classes("gap-0 flex-1 min-w-0"):
                ui.label(t("shared_changed_title")).classes("font-semibold")
                ui.label(t("shared_changed_text", names=names, at=latest["at"])).classes("text-sm")
            # a label that has its own emoji (🔍 ...) needs no icon
            icon = None if button_text[:1] and not button_text[:1].isalnum() else "manage_search"
            ui.button(button_text, icon=icon, on_click=on_analyze).props("color=orange no-caps")
