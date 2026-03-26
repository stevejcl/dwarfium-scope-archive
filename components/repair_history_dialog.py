"""
components/repair_history_dialog.py
-------------------------------------
NiceGUI dialog shown when the user selects a primary session that already
has one or more recorded Repair or Merge actions.

Displays the full action history for that primary session and offers:
  • [🔄 Redo]        → discard previous output, run action again
  • [📁 Copy to Dwarf] → skip to transfer, using the existing output dir
  • [🗑 Delete entry]  → remove the entry from the index (keeps files)
  • [❌ Cancel]        → close without doing anything

Usage
-----
    from components.repair_history_dialog import RepairHistoryDialog

    dialog = RepairHistoryDialog(
        manager=mgr,                        # RepairSessionManager instance
        primary_session="DWARF_RAW_...",
        dwarf_id=1,
        backup_id=3,
        backup_root="D:\\Backup",
        on_redo=lambda: my_repair_func(),
        on_copy=lambda entry: open_mosaic_restore_dialog(
            repaired_src_dir=str(mgr.get_output_path(entry)),
            backup_root="D:\\Backup",
            dwarf_id=1,
            session=entry["primary_session"],
            backup_id=3,
            back_url="/MosaicRepair",
        ),
    )
    dialog.open()
"""
from __future__ import annotations

from typing import Callable
from nicegui import ui

import asyncio

from api.repair_session_manager import (
    RepairSessionManager,
    status_icon,
    status_color,
    format_timestamp,
)


class RepairHistoryDialog:
    """
    Dialog that shows the repair/merge history for a given primary session
    and lets the user decide what to do next.

    Parameters
    ----------
    manager : RepairSessionManager
        The manager instance for the current temp root.
    primary_session : str
        The session name/path the user just selected.
    dwarf_id : int | None
        Passed through to the Copy-to-Dwarf callback.
    backup_id : int | None
        Passed through to the Copy-to-Dwarf callback.
    backup_root : str
        Root backup directory (for display and transfer constraint).
    on_redo : Callable[[], None]
        Called when the user clicks "Redo" on any entry.
        The caller is responsible for deleting / overwriting the old output.
    on_copy : Callable[[dict], None]
        Called with the selected ActionEntry dict when the user clicks
        "Copy to Dwarf".  The caller typically opens MosaicRestoreDialog.
    on_cancel : Callable[[], None] | None
        Optional callback when the dialog is dismissed with no action.
    """

    def __init__(
        self,
        manager: RepairSessionManager,
        primary_session: str,
        backup_root: str,
        on_redo:   Callable[[], None],
        on_copy:   Callable[[dict], None],
        dwarf_id:  int | None = None,
        backup_id: int | None = None,
        on_cancel: Callable[[], None] | None = None,
    ):
        self.manager          = manager
        self.primary_session  = primary_session
        self.backup_root      = backup_root
        self.dwarf_id         = dwarf_id
        self.backup_id        = backup_id
        self._on_redo         = on_redo
        self._on_copy         = on_copy
        self._on_cancel       = on_cancel

        self._dialog: ui.dialog | None = None
        self._selected_entry: dict | None = None

        self._build()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def open(self):
        if self._dialog:
            self._dialog.open()

    def close(self):
        if self._dialog:
            self._dialog.close()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build(self):
        history = self.manager.get_history_for_primary(self.primary_session)

        with ui.dialog().props("persistent").style("z-index: 9999") as self._dialog:
            with ui.card().style("min-width: 700px; max-width: 900px;"):

                # ── Header ──────────────────────────────────────────────
                with ui.row().classes("w-full items-center gap-3 pb-2 border-b border-gray-200"):
                    ui.icon("history", color="orange", size="2rem")
                    with ui.column().classes("gap-0"):
                        ui.label("Previous actions found").classes("text-lg font-bold")
                        session_display = self.primary_session
                        if len(session_display) > 60:
                            session_display = "…" + session_display[-57:]
                        ui.label(session_display).classes("text-sm text-gray-500 font-mono")

                ui.separator()

                # ── History list ─────────────────────────────────────────
                if not history:
                    ui.label("No previous actions found for this session.").classes(
                        "text-gray-500 italic py-4"
                    )
                else:
                    ui.label(
                        f"{len(history)} action(s) recorded — select one to act on it:"
                    ).classes("text-sm text-gray-600 py-1")

                    self._entry_cards = {}

                    with ui.scroll_area().style("max-height: 400px; width: 100%;"):
                        for entry in history:
                            self._build_entry_card(entry)

                ui.separator()

                # ── Bottom action bar ────────────────────────────────────
                with ui.row().classes("w-full justify-between items-center pt-2"):

                    # Left: selection hint
                    self._action_hint = ui.label(
                        "👆 Select an entry above to enable actions"
                    ).classes("text-sm text-gray-400 italic")

                    # Right: action buttons (disabled until an entry is selected)
                    with ui.row().classes("gap-2"):

                        self._btn_redo = ui.button(
                            "🔄 Redo",
                            on_click=self._handle_redo,
                        ).props("outline color=orange").tooltip(
                            "Discard this output and run the action again"
                        )
                        self._btn_redo.disable()

                        self._btn_copy = ui.button(
                            "📁 Copy to Dwarf",
                            on_click=self._handle_copy,
                        ).props("color=green").tooltip(
                            "Skip repair — copy this existing output to the Dwarf"
                        )
                        self._btn_copy.disable()

                        self._btn_delete = ui.button(
                            "🗑",
                            on_click=self._handle_delete,
                        ).props("outline color=red").tooltip(
                            "Remove this entry from the history (files are kept)"
                        )
                        self._btn_delete.disable()

                        ui.button(
                            "❌ Cancel",
                            on_click=self._handle_cancel,
                        ).props("flat color=grey")

        # ── Pre-built delete confirmation dialog ─────────────────────
        with ui.dialog().props("persistent").style("z-index: 10000") as self._confirm_dlg, \
             ui.card().style("min-width: 400px"):
            ui.label("Remove this entry from history?").classes("font-semibold")
            ui.label(
                "The output folder and its files are NOT deleted."
            ).classes("text-sm text-gray-500")
            with ui.row().classes("gap-2 justify-end w-full pt-2"):
                ui.button("Cancel", on_click=self._confirm_dlg.close).props("flat")
                ui.button(
                    "Remove",
                    on_click=self._confirm_delete_selected,
                ).props("color=red")

    def _build_entry_card(self, entry: dict):
        """Render a single history entry as a clickable card."""
        eid    = entry["id"]
        status = entry.get("status", "")
        action = entry.get("action", "")
        ts     = format_timestamp(entry.get("timestamp", ""))
        icon   = status_icon(status)
        color  = status_color(status)

        tiles_str = ""
        if entry.get("tiles_repaired") is not None and entry.get("tiles_total"):
            tiles_str = f"  •  {entry['tiles_repaired']}/{entry['tiles_total']} tiles"

        secondary = entry.get("secondary_session")
        secondary_str = f"\nSecondary: {secondary}" if secondary else ""

        sessions = entry.get("sessions")
        sessions_str = ""
        if sessions:
            sessions_str = "\nInputs: " + ", ".join(sessions)

        output_dir = entry.get("output_subdir", "—")

        error_str = ""
        if entry.get("error"):
            err = entry["error"]
            if len(err) > 120:
                err = err[:117] + "…"
            error_str = f"\n❌ Error: {err}"

        card_classes = (
            "w-full p-3 mb-2 cursor-pointer border-2 rounded-lg "
            "transition-all hover:border-orange-400"
        )

        with ui.card().classes(card_classes).on(
            "click", lambda e, eid=eid, entry=entry: self._select_entry(eid, entry)
        ) as card:
            self._entry_cards[eid] = card

            with ui.row().classes("items-start gap-3 w-full"):
                # Status badge
                with ui.column().classes("items-center gap-1 min-w-[60px]"):
                    ui.label(icon).classes("text-2xl")
                    ui.badge(status.upper(), color=color).classes("text-xs")

                # Details
                with ui.column().classes("flex-1 gap-0"):
                    with ui.row().classes("items-center gap-3"):
                        ui.label(f"{action}").classes("font-bold text-base")
                        ui.label(ts).classes("text-sm text-gray-500")
                        ui.label(f"#{eid}").classes("text-xs text-gray-400 font-mono")

                    ui.label(
                        f"Output: {output_dir}{tiles_str}"
                        f"{secondary_str}{sessions_str}{error_str}"
                    ).classes("text-sm text-gray-600 font-mono whitespace-pre-wrap")

    def _select_entry(self, entry_id: str, entry: dict):
        """Highlight the selected card and enable action buttons."""
        # Reset all cards
        for eid, card in self._entry_cards.items():
            if eid == entry_id:
                card.classes(remove="border-gray-200", add="border-orange-500 bg-orange-50")
            else:
                card.classes(remove="border-orange-500 bg-orange-50", add="border-gray-200")

        self._selected_entry = entry
        self._action_hint.set_text("✅ Entry selected — choose an action below")
        self._action_hint.classes(remove="text-gray-400", add="text-green-600")

        # Enable buttons — Copy only if status is success/partial
        self._btn_redo.enable()
        self._btn_delete.enable()
        status = entry.get("status", "")
        if status in ("success", "partial"):
            self._btn_copy.enable()
        else:
            self._btn_copy.disable()

    def _handle_redo(self):
        self.close()
        self._on_redo()

    def _handle_copy(self):
        if self._selected_entry is None:
            ui.notify("Please select an entry first.", type="warning")
            return
        self.close()
        self._on_copy(self._selected_entry)

    def _handle_delete(self):
        if self._selected_entry is None:
            ui.notify("Please select an entry first.", type="warning")
            return
        self._confirm_dlg.open()

    def _confirm_delete_selected(self):
        self._confirm_dlg.close()
        if self._selected_entry is None:
            return
        entry_id = self._selected_entry["id"]
        removed = self.manager.delete_action(entry_id)
        if removed:
            ui.notify("✅ Entry removed from history.", type="positive")
            if entry_id in self._entry_cards:
                self._entry_cards[entry_id].delete()
                del self._entry_cards[entry_id]
            self._selected_entry = None
            self._btn_redo.disable()
            self._btn_copy.disable()
            self._btn_delete.disable()
            self._action_hint.set_text("👆 Select an entry above to enable actions")
            self._action_hint.classes(remove="text-green-600", add="text-gray-400")
        else:
            ui.notify("❌ Entry not found.", type="negative")

    def _handle_cancel(self):
        self.close()
        if self._on_cancel:
            self._on_cancel()


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------

def check_and_show_history(
    manager: RepairSessionManager,
    primary_session: str,
    backup_root: str,
    on_redo:   Callable[[], None],
    on_copy:   Callable[[dict], None],
    on_proceed: Callable[[], None],
    dwarf_id:  int | None = None,
    backup_id: int | None = None,
    on_cancel: Callable[[], None] | None = None,
) -> bool:
    """
    Check if ``primary_session`` has any previous actions.

    • If YES  → open the RepairHistoryDialog and return True.
    • If NO   → call ``on_proceed()`` immediately and return False.

    This is the single call-site in your repair page:

    .. code-block:: python

        check_and_show_history(
            manager          = self.repair_mgr,
            primary_session  = self.selected_session,
            backup_root      = self.backup_root,
            on_redo          = self.run_repair,
            on_copy          = lambda entry: open_mosaic_restore_dialog(...),
            on_proceed       = self.run_repair,   # first-time path
            dwarf_id         = self.DwarfId,
            backup_id        = self.BackupId,
        )
    """
    history = manager.get_history_for_primary(primary_session)

    if history:
        dlg = RepairHistoryDialog(
            manager         = manager,
            primary_session = primary_session,
            backup_root     = backup_root,
            on_redo         = on_redo,
            on_copy         = on_copy,
            dwarf_id        = dwarf_id,
            backup_id       = backup_id,
            on_cancel       = on_cancel,
        )
        dlg.open()
        return True
    else:
        on_proceed()
        return False
