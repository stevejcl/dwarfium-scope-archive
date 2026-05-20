from nicegui import ui
from components.i18n import t
import inspect

class WinLog:
    def __init__(self):
        self.popup_title = ""
        self.popup_text = ""
        self.on_yes = None

        with ui.dialog() as self.popup_dialog, ui.card().style('width: 800px; max-width: none'):
            ui.label().bind_text_from(self, "popup_title").classes("text-lg font-bold")
            ui.label().bind_text_from(self, "popup_text").classes("text-md").style('white-space: pre-wrap') 
            with ui.row():
                ui.button(t("yes"), on_click=self._on_yes_clicked)
                ui.button(t("no"), on_click=lambda: self.popup_dialog.submit("No"))

    async def show(self, title: str, text: str, on_yes: callable = None):
        """Display the popup with a title and message. Optionally call `on_yes` if user confirms."""
        self.popup_title = title
        self.popup_text = text
        self.on_yes = on_yes
        result = await self.popup_dialog
        if result == "Yes" and self.on_yes:
            if inspect.iscoroutinefunction(self.on_yes):
                await self.on_yes()   # ? await async function
            else:
                self.on_yes()         # ? normal function

    def _on_yes_clicked(self):
        self.popup_dialog.submit("Yes")
