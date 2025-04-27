# components/menu.py
from nicegui import ui

def menu():
    with ui.header().classes('bg-blue-700 text-white'):
        ui.button('Home', on_click=lambda: ui.navigate.to('/'))
        ui.button('Dwarfs Settings', on_click=lambda: ui.navigate.to('/Dwarf'))
        ui.button('Backup Setting', on_click=lambda: ui.navigate.to('/Backup'))
        ui.button('Explore', on_click=lambda: ui.navigate.to('/Explore'))
