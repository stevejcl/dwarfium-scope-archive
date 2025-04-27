from nicegui import ui, app

@ui.page('/')
def home_page():
    from components.menu import menu
    menu()
    ui.label('Welcome to the Home Page!')