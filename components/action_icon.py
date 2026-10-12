"""Action buttons as large icons (user-requested Oct 2026: in Explore the
text buttons took several lines, or ran past the window).

ActionIcon is a ui.button showing its icon only, its text in a tooltip; on
a small screen (no hover: phone / tablet over the LAN) a short caption is
shown under the icon (CSS in dwarfium_scope_archive.py, .action-icon). A
leading emoji of the text (the labels carry one) is dropped. Changing the
text (button.text = / set_text) updates the tooltip and the caption, so
the pages keep using them as before.
"""
from __future__ import annotations

import re

from nicegui import ui

# Leading symbols / emoji and spaces of a label ("🗁 Ouvrir" -> "Ouvrir")
_LEADING_SYMBOLS = re.compile(r"^[^\w(]+")


def _clean(text: str) -> str:
    return _LEADING_SYMBOLS.sub("", str(text or "")).strip()


class ActionIcon(ui.button):
    def __init__(self, text: str, icon: str, on_click=None, *, danger: bool = False) -> None:
        super().__init__(text, icon=icon, on_click=on_click, color="negative" if danger else "primary")
        self.props("stack no-caps unelevated").classes("action-icon")
        with self:
            self._tip = ui.tooltip(_clean(text))

    def _text_to_model_text(self, text: str) -> None:
        super()._text_to_model_text(_clean(text))
        tip = getattr(self, "_tip", None)
        if tip is not None:
            tip.text = _clean(text)
