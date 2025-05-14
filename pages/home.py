from nicegui import ui, app

import os
import subprocess

from api.dwarf_backup_db import DB_NAME, connect_db, close_db, init_db
from api.dwarf_backup_db_api import get_dwarf_favorites, get_backup_favorites

from api.dwarf_backup_fct import get_Backup_fullpath, show_date_session

from api.image_preview import set_base_folder, build_preview_url

from components.menu import menu

@ui.page('/')
def home_page():

    menu("Dwarfium Scope Archive")

    # Launch the GUI
    HomeApp(DB_NAME)

class HomeApp:
    def __init__(self, database):
        self.database = database
        self.image_detail_click_set = False
        self.build_ui()

    def build_ui(self):
        self.conn = connect_db(self.database)

        # Fetch favorite images
        files = get_backup_favorites(self.conn)
        image_data = []

        for row in files:
            file_path = row[3]
            backup_path = row[6]  # Backup location

            # Generate the full path and URL for the image
            full_path = get_Backup_fullpath(backup_path, "", file_path)
            set_base_folder(full_path.replace("\\", "/").rsplit(file_path.replace("\\", "/"), 1)[0])

            url_path = build_preview_url(file_path)
            if os.path.exists(full_path):
                image_data.append({
                    "url": url_path,
                    "object_name": row[2] if row[2] else "Unknown Object",
                    "dwarf_name": row[4] if row[4] else "Unknown Device",
                    "session_date": show_date_session(row[1]),
                    "file_path": full_path
                })
        close_db(self.conn)

        # UI - Slideshow
        self.current_index = 0  # Index for slideshow

        with ui.column().classes("w-full").classes("items-center"):
            ui.label("⭐ My Favorite images ⭐ ").classes("text-center mt-2 text-lg font-semibold")
            if image_data:
                slideshow_image = ui.image(image_data[self.current_index]['url']).classes("w-full h-auto max-w-screen-lg rounded-lg shadow-md transition-opacity duration-1000 opacity-100")
                image_info = ui.label("").classes("text-center mt-2 text-lg font-semibold")
                image_detail = ui.label("").classes("text-center mt-2 text-md")

                def show_image():
                    # Crossfade effect
                    slideshow_image.classes('opacity-5').update()
                    ui.timer(0.2, lambda: update_image())

                def update_image():
                    slideshow_image.source = image_data[self.current_index]['url']
                    slideshow_image.classes('opacity-95').update()

                    # Update image info
                    info_text = (
                        f"Object: {image_data[self.current_index]['object_name']} | "
                        f"Taken on {image_data[self.current_index]['dwarf_name']} | "
                        f"Date: {image_data[self.current_index]['session_date']}"
                    )
                    image_info.text = info_text
                    image_detail.text = f"{image_data[self.current_index]['file_path']}"
                    if not self.image_detail_click_set:
                        image_detail.on(
                            'click', 
                            lambda: self.open_folder(os.path.dirname(image_data[self.current_index]['file_path']))
                        ).classes("text-green-600 pl-4 pr-4 pb-4 cursor-pointer hover:underline")
                        self.image_detail_click_set = True
                def next_image():
                    self.current_index = (self.current_index + 1) % len(image_data)
                    show_image()

                def prev_image():
                    self.current_index = (self.current_index - 1) % len(image_data)
                    show_image()

                # Automatic slideshow with 5s interval
                ui.timer(interval=5, callback=next_image)

                with ui.row().classes("gap-4 mt-4"):
                    ui.button("Previous", on_click=prev_image)
                    ui.button("Next", on_click=next_image)
            else:
                ui.label("No favorite images found.")

    def open_folder(self, directory = None):
        if not directory:
            print("No folder selected!")
            return

        # Normalize the path
        if directory:
            folder_path = os.path.normpath(directory)
        if folder_path and os.path.exists(folder_path):
            if os.name == 'nt':  # Windows
                subprocess.Popen(f'explorer "{folder_path}"')
            elif os.name == 'posix':  # macOS or Linux
                subprocess.Popen(['open', folder_path])  # macOS
                # or 'xdg-open' for Linux
        else:
            print("Folder does not exist!")
