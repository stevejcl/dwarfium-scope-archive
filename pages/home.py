from components.i18n import t
from nicegui import ui, app

import os
import subprocess
import asyncio

from api.dwarf_backup_db import DB_NAME, start_db, connect_db, close_db
from components.db_page_mixin import DbPageMixin
from api.dwarf_backup_db_api import insert_default_groups 
from api.dwarf_backup_db_api import ensure_dwarf_local_path, get_dwarf_favorites, get_backup_favorites, get_manual_favorites

from api.dwarf_backup_fct import get_Backup_fullpath, show_date_session, get_root_manual_session_dir

from api.image_preview import set_base_folder, build_preview_url

from components.menu import menu

init_task = None
is_app_started = False

def init_db():
    conn = start_db(DB_NAME)
    if not conn:
        raise RuntimeError('Database init failed')
    insert_default_groups(conn)
    close_db(conn)

async def ensure_init():
    global init_task, is_app_started

    if is_app_started:
        return

    if init_task is None:
        # first caller launches init
        init_task = asyncio.create_task(asyncio.to_thread(init_db))

    await init_task
    is_app_started = True


@ui.page('/')
async def home_page():
    status = None
    curent_init = is_app_started
    if not is_app_started:
        status = ui.label(t("starting"))
    spinner = ui.spinner(size='md')

    await ui.context.client.connected(timeout=10.0)

    # 👇 laisse le temps au rendu UI
    await asyncio.sleep(0)

    if not is_app_started and status:
        status.set_text(t('initializing_db'))
    await ensure_init()

    await ui.context.client.connected(timeout=10.0)

    # Check settings and handle directory setup
    conn = connect_db(DB_NAME)
    if not ensure_dwarf_local_path(conn):
        spinner.delete()
        if status:
            status.set_text('Redirecting to settings...')
        ui.timer(0.1, lambda: ui.navigate.to("/Settings?InitDwarfLocal=False"), once=True)
        return

    spinner.delete()
    if not curent_init and status:
        status.set_text(t('ready'))
        ui.timer(3.0, lambda: status.delete(), once=True)

    ON_AIR = app.storage.general.get('ON_AIR', False)
    title = "Dwarfium Scope Archive"

    if not ON_AIR:
        menu(title)
    else:
        with ui.row().classes('w-full items-center'):
            ui.label(title).classes("text-2xl font-bold my-2 mr-auto")

    # Launch the GUI
    home = HomeApp(DB_NAME, ON_AIR)

    # Cancel the slideshow timer when the client discon nects
    # (browser tab closed, page navigated away, window closed)
    ui.context.client.on_disconnect(home.cancel_timer)
  
class HomeApp(DbPageMixin):
    def __init__(self, database, ON_AIR):
        self.database = database
        self.ON_AIR = ON_AIR
        self.image_detail_click_set = False
        self.conn = connect_db(self.database)
        self.register_conn_close()
        self.gallery_timer = None
        self.build_ui()

    def get_name_object(self, name, desc):
        name_object = name 

        if desc is not None and desc.strip() != '':
            name_object = f"{desc.strip()} [{name}]"

        # Start by removing anything after the last ' [' (suffix)
        main_part = name_object.split(" [")[0]

        # Then optionally remove anything after ' (' inside main_part
        main_part = main_part.split(" (")[0]

        # Now detect the suffix from the original name
        bracket_pos = name_object.rfind(" [")
        suffix = name_object[bracket_pos:] if bracket_pos != -1 else ""

        # Only re-add suffix if it's not already included
        name_object = (f"{main_part} {suffix}").strip() if suffix and suffix not in main_part else main_part.strip()

        return main_part

    def build_ui(self):
        # Fetch favorite images
        files = get_backup_favorites(self.conn)
        image_data = []

        for row in files:
            session_date = row[1]  # session_date
            astro_object_name = row[2]  # astro_object_name
            file_path = row[3] # image path
            dwarf_name = row[4]  # Dwarf Name
            backup_path = row[6]  # Backup location
            astro_object_description = row[7]  # astro_object_description

            # Generate the full path and URL for the image
            full_path = get_Backup_fullpath(self.conn, backup_path, "", file_path)
            base_folder = full_path.replace("\\", "/").rsplit(file_path.replace("\\", "/"), 1)[0]
            object_name = self.get_name_object(astro_object_name, astro_object_description)

            url_path = build_preview_url(file_path)
            if os.path.exists(full_path):
                image_data.append({
                    "url": url_path,
                    "object_name": f"🛰️ {object_name}" if object_name else "Unknown Object",
                    "dwarf_name": f"🔭 {dwarf_name}" if dwarf_name else "Unknown Device",
                    "session_date": f"📅 {show_date_session(session_date)}",
                    "file_path": full_path,
                    "base_folder": base_folder
                })
        
        # ── Manual Session favorites ──────────────────────────────────────────
        for row in get_manual_favorites(self.conn):
            # [0]id [1]date [2]session_name [3]jpeg_path [4]dwarf [5]drive_name
            # [6]location [7]description [8]session_dir [9]session_type
            session_date = row[1]
            session_name = row[2]
            jpeg_path    = row[3]
            dwarf_name   = row[4]
            location     = row[6]
            description  = row[7]
            session_dir  = row[8]
            session_type = row[9]

            if not jpeg_path:
                continue
            # Resolve full path
            if os.path.isabs(jpeg_path):
                full_path = jpeg_path
            else:
                full_path = os.path.join(session_dir, jpeg_path) if session_dir else jpeg_path
            if not os.path.exists(full_path) and location:
                full_path = os.path.join(location, jpeg_path)
            if not os.path.exists(full_path):
                continue

            # Use same logic as ManualExplore: base_folder via get_root_manual_session_dir
            # jpeg_path may be relative (e.g. "stacked.jpg") or absolute
            if os.path.isabs(jpeg_path):
                image_path_for_url = os.path.basename(jpeg_path)
                base_folder = get_root_manual_session_dir(os.path.dirname(full_path), image_path_for_url)
            else:
                image_path_for_url = jpeg_path
                base_folder = get_root_manual_session_dir(session_dir or os.path.dirname(full_path), jpeg_path)

            url_path = build_preview_url(image_path_for_url)
            label = description or session_name or "Manual Session"
            type_icon = "🖼️" if session_type else "📷"
            image_data.append({
                "url":          url_path,
                "object_name":  f"{type_icon} {label}",
                "dwarf_name":   f"🔭 {dwarf_name}" if dwarf_name else "Manual",
                "session_date": f"📅 {show_date_session(session_date)}" if session_date else "",
                "file_path":    full_path,
                "base_folder":  str(base_folder),
                "source":       "manual",
            })

        close_db(self.conn)
        self.conn = None

        # display Sample if no image yet
        if len(image_data) == 0 :
            base_folder = os.getcwd() 
            image_path = "image/sample_favorite.jpg"
            full_path = os.path.join(base_folder, image_path)
            url_path = build_preview_url("image/sample_favorite.jpg")
            image_data.append({
                "url": url_path,
                "object_name": "🛰️ Rosette Nebula",
                "dwarf_name": f"🔭 Dwarf3",
                "session_date": f"📅 2025.11.21 07:47",
                "file_path": full_path,
                "base_folder": base_folder
            })

        # UI - Slideshow
        self.first_image = True
        self.current_index = 0  # Index for slideshow
        if self.gallery_timer:
            self.gallery_timer.cancel()
            self.gallery_timer = None

        with ui.column().classes("w-full").classes("items-center"):
            ui.label(t("favorites_gallery")).classes("text-center mt-0 text-lg font-semibold")
            if image_data:
                slideshow_image = ui.image("").classes("w-full h-auto max-w-screen-xl rounded-lg shadow-md transition-opacity duration-1000 opacity-100")
                image_info = ui.label("").classes("text-center mt-2 text-lg font-semibold")
                image_detail = ui.label("").classes("text-center mt-0 text-md")

                def show_image():
                    if not ui.context.client.connected:
                        return

                    # Crossfade effect
                    slideshow_image.classes('opacity-5').update()
                    ui.timer(0.2, lambda: update_image(), once=True)

                def update_image():
                    set_base_folder(image_data[self.current_index]['base_folder'])
                    slideshow_image.source = image_data[self.current_index]['url']
                    slideshow_image.classes('opacity-95').update()

                    # Update image info
                    info_text = (
                        f"{image_data[self.current_index]['object_name']} "
                        f"{image_data[self.current_index]['dwarf_name']} "
                        f"{image_data[self.current_index]['session_date']}"
                    )
                    image_info.text = info_text
                    if not self.ON_AIR:
                        image_detail.text = f"{image_data[self.current_index]['file_path']}"
                        if not self.image_detail_click_set:
                            image_detail.on(
                                'click', 
                                lambda: self.open_folder(os.path.dirname(image_data[self.current_index]['file_path']))
                            ).classes("text-green-600 pl-4 pr-4 pb-2 cursor-pointer hover:underline")
                            self.image_detail_click_set = True
                def next_image():
                    if not ui.context.client.connected:
                        return

                    if self.first_image:
                        self.current_index = (self.current_index) % len(image_data)
                        self.first_image = False
                    else:
                        self.current_index = (self.current_index + 1) % len(image_data)
                    show_image()

                def prev_image():
                    self.current_index = (self.current_index - 1) % len(image_data)
                    show_image()

                # Automatic slideshow with 10s interval
                self.gallery_timer = ui.timer(interval=10, callback=next_image)

                with ui.row().classes("gap-4 mb-0"):
                    ui.button(t("previous"), on_click=prev_image)
                    ui.button(t("next"), on_click=next_image)
            else:
                ui.label(t("no_fav_images"))

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

    def cancel_timer(self):
        if self.gallery_timer:
            self.gallery_timer.cancel()
            self.gallery_timer = None