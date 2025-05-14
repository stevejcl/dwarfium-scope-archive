from nicegui import ui

class WinLog:
    def __init__(self):
        self.popup_title = ""
        self.popup_text = ""
        self.on_yes = None

        with ui.dialog() as self.popup_dialog, ui.card():
            ui.label().bind_text_from(self, "popup_title").classes("text-lg font-bold")
            ui.label().bind_text_from(self, "popup_text").classes("text-md")
            with ui.row():
                ui.button("Yes", on_click=self._on_yes_clicked)
                ui.button("No", on_click=lambda: self.popup_dialog.submit("No"))

    async def show(self, title: str, text: str, on_yes: callable = None):
        """Display the popup with a title and message. Optionally call `on_yes` if user confirms."""
        self.popup_title = title
        self.popup_text = text
        self.on_yes = on_yes
        result = await self.popup_dialog
        if result == "Yes" and self.on_yes:
            self.on_yes()

    def _on_yes_clicked(self):
        self.popup_dialog.submit("Yes")
