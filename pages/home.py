from components.i18n import t
from nicegui import ui, app, run, Client

import os, datetime
import subprocess
import asyncio
from pathlib import Path

from api.dwarf_backup_db import DB_NAME, start_db, connect_db, close_db
from components.db_page_mixin import DbPageMixin
from api.dwarf_backup_db_api import insert_default_groups, toggle_favorite, toggle_favorite, toggle_favorite_manual
from api.dwarf_backup_db_api import ensure_dwarf_local_path, get_dwarf_favorites, get_backup_favorites, get_manual_favorites

from api.dwarf_backup_fct import get_Backup_fullpath, show_date_session, get_relative_file_path
from api.dwarf_backup_fct import format_seconds_hms, parse_exposure, is_Restacked, get_total_exposure, get_total_mosaic_exposure

from api.image_preview import set_base_folder, build_preview_url

from components.menu import menu
from tools.video_export import VideoExportConfig, export_video, list_fonts, VIDEO_RESOLUTIONS, FONT_SIZES, get_music_files

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
async def home_page(client: Client):
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
    home = HomeApp(client, DB_NAME, ON_AIR)

    # Cancel the slideshow timer when the client discon nects
    # (browser tab closed, page navigated away, window closed)
    ui.context.client.on_disconnect(home.on_disconnect)
  
class HomeApp(DbPageMixin):
    def __init__(self, client: Client, database, ON_AIR):
        self.client = client
        self.database = database
        self.ON_AIR = ON_AIR
        self.image_detail_click_set = False
        self.gallery_timer = None
        self.button_cancel_generate = None
        self.end_background_task = False
        self.build_ui()

    def on_disconnect(self):
        self.end_background_task = True
        self.cancel_timer()
        
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

    def _sample_image(self):
        """Return the placeholder image entry shown while real favorites are loading."""
        base_folder = os.getcwd()
        full_path = os.path.join(base_folder, "image/sample_favorite.jpg")
        return {
            "url":          build_preview_url("image/sample_favorite.jpg"),
            "object_name":  "🛰️ Rosette Nebula",
            "dwarf_name":   "🔭 Dwarf3",
            "session_date": "📅 2025.11.21 07:47",
            "file_path":    full_path,
            "base_folder":  base_folder,
            "_is_sample":   True,
        }

    def _collect_all_favorites(self):
        """
        Blocking I/O — intended to run via run.io_bound().
        Returns a list of image-data dicts for all backup + manual favorites.
        """
        conn = connect_db(self.database)
        result = []
        print("_collect_all_favorites")

        # ── Backup favorites ─────────────────────────────────────────────────
        for row in get_backup_favorites(conn):
            session_date          = row[1]
            astro_object_name     = row[2]
            file_path             = row[3]
            dwarf_name            = row[4]
            backup_path           = row[6]
            astro_object_description = row[7]
            exp_time   = row[8]  if len(row) > 8  else None
            gain       = row[9]  if len(row) > 9  else None
            ir_filter  = row[10] if len(row) > 10 else None
            shots      = row[11] if len(row) > 11 and row[11] is not None else None
            backup_data_entry = row[12] if len(row) > 12 else None
            fits_path  = row[13] if len(row) > 13 else None

            full_fits_path = get_Backup_fullpath(conn, backup_path, "", fits_path) if fits_path else None
            full_path = get_Backup_fullpath(conn, backup_path, "", file_path)
            base_folder = full_path.replace("\\", "/").rsplit(file_path.replace("\\", "/"), 1)[0]
            object_name = self.get_name_object(astro_object_name, astro_object_description)

            exp = f"{exp_time}s" if exp_time is not None else "N/A"
            exp_value = parse_exposure(exp) if exp != "N/A" else 0
            exposure_time = format_seconds_hms(exp_value * shots) if shots else ""

            # get exposure for Restacked session
            if "RESTACKED" in full_path:
                if "_MOSAIC_" in full_path:
                    exposure_time = format_seconds_hms(get_total_mosaic_exposure(os.path.dirname(full_path)))
                elif full_fits_path and os.path.isfile(full_fits_path):
                    exposure_time = format_seconds_hms(get_total_exposure(full_fits_path))

            url_path = build_preview_url(file_path)
            if os.path.exists(full_path):
                result.append({
                    "url":            url_path,
                    "object_name":    f"🛰️ {object_name}" if object_name else "Unknown Object",
                    "dwarf_name":     f"🔭 {dwarf_name}" if dwarf_name else "Unknown Device",
                    "session_date":   f"📅 {show_date_session(session_date)}",
                    "file_path":      full_path,
                    "base_folder":    base_folder,
                    "exp_time":       str(exp_time) if exp_time else "",
                    "gain":           str(gain) if gain else "",
                    "filter":         str(ir_filter) if ir_filter else "",
                    "total_exposure": exposure_time,
                    "entry":          backup_data_entry,
                })

        # ── Manual Session favorites ──────────────────────────────────────────
        for row in get_manual_favorites(conn):
            manual_entry        = row[0]
            session_date        = row[1]
            session_name        = row[2]
            jpeg_path           = row[3]
            dwarf_name          = row[4]
            location            = row[6]
            description         = row[7]
            session_dir         = row[8]
            session_type        = row[9]
            session_tag         = row[10]
            manual_session_dir  = row[11]
            manual_location     = row[12]

            if not jpeg_path:
                print(f"[home] error jpg path: {jpeg_path}")
                continue
            # Resolve full path
            if os.path.isabs(jpeg_path):
                full_path = jpeg_path
            else:
                full_path = os.path.join(session_dir, os.path.basename(jpeg_path)) if session_dir else jpeg_path
            if not os.path.exists(full_path) and location:
                full_path = os.path.join(location, jpeg_path)
            if not os.path.exists(full_path):
                print(f"[home] error full path: {full_path}")
                continue

            set_base_folder(manual_location)
            url_path = build_preview_url(get_relative_file_path(manual_location, jpeg_path))
            label = description or session_name or "Manual Session"
            type_icon = "🖼️" if session_type == "Stellar Studio" else "📷"
            result.append({
                "url":          url_path,
                "object_name":  f"{type_icon} {label}",
                "dwarf_name":   f"🔭 {dwarf_name}" if dwarf_name else "Manual",
                "session_date": f"📅 {show_date_session(session_date)}" if session_date else "",
                "file_path":    full_path,
                "base_folder":  manual_location,
                "source":       "manual",
                "entry":        manual_entry,
            })

        close_db(conn)
        print(f"[home] favorites loaded: {len(result)}")
        return result

    def build_ui(self):
        """Build the slideshow UI — starts immediately with the sample image,
        then loads all real favorites in the background via run.io_bound."""

        # ── Slideshow state ──────────────────────────────────────────────────
        self.current_index = 0
        if self.gallery_timer:
            self.gallery_timer.cancel(with_current_invocation=True)
            self.gallery_timer = None

        # Start with the sample placeholder so the UI renders immediately
        image_data = [self._sample_image()]

        # ── UI build ─────────────────────────────────────────────────────────
        with ui.column().classes("w-full items-center"):
            ui.label(t("favorites_gallery")).classes("text-center mt-0 text-lg font-semibold")

            slideshow_image = ui.image("").classes(
                "w-full h-auto max-w-screen-xl rounded-lg shadow-md "
                "transition-opacity duration-1000 opacity-100"
            )
            image_info   = ui.label("").classes("text-center mt-2 text-lg font-semibold")
            image_detail = ui.label("").classes("text-center mt-0 text-md")

            # ── Slideshow helpers ────────────────────────────────────────────
            def show_image():
                if not self.client:
                    return
                slideshow_image.classes('opacity-5').update()
                ui.timer(0.2, update_image, once=True)

            def update_image():
                entry = image_data[self.current_index]
                set_base_folder(entry['base_folder'])
                slideshow_image.source = entry['url']
                slideshow_image.classes('opacity-95').update()

                info_text = (
                    f"{entry['object_name']} "
                    f"{entry['dwarf_name']} "
                    f"{entry['session_date']}"
                )
                image_info.text = info_text

                if not self.ON_AIR:
                    image_detail.text = entry['file_path']
                    if not self.image_detail_click_set:
                        image_detail.on(
                            'click',
                            lambda: self.open_folder(
                                os.path.dirname(image_data[self.current_index]['file_path'])
                            )
                        ).classes("text-green-600 pl-4 pr-4 pb-2 cursor-pointer hover:underline")
                        self.image_detail_click_set = True

            def reaactive_timer():
                if self.gallery_timer:
                    self.gallery_timer.cancel(with_current_invocation=True)
                self.gallery_timer = ui.timer(10, next_image, immediate=False, once=False)

            def next_image():
                try: 
                    if not self.client:
                        return
                    self.current_index = (self.current_index + 1) % len(image_data)
                    show_image()
                except Exception:
                    print("exception in next_image") 
                    pass
 
            def next_image_click():
                reaactive_timer()
                next_image()

            def prev_image():
                self.current_index = (self.current_index - 1) % len(image_data)
                show_image()

            def prev_image_click():
                reaactive_timer()
                prev_image()

            async def remove_favorite():
                if self.current_index and 'entry' in image_data[self.current_index]:
                    self.cancel_timer()
                    with ui.dialog().props('persistent') as dialog, ui.card().style('width: 400px; max-width: none'):
                        ui.label(t('confirm_favorite_remove'))
                        with ui.row():
                            ui.button(t("yes"), on_click=lambda: dialog.submit('Yes'))
                            ui.button(t("no"), on_click=lambda: dialog.submit('No'))

                    result = await dialog
                    if result == 'Yes':
                        conn = connect_db(self.database)
                        entry = image_data[self.current_index]
                        if entry.get('source') == "manual":
                            print(f"Manual Entry:  {entry['entry']}")
                            toggle_favorite_manual(conn, entry['entry'])
                        else:
                            print(f"Backup Data Entry:  {entry['entry']}")
                            toggle_favorite(conn, entry['entry'], "backup")
                        close_db(conn)

                        del image_data[self.current_index]
                        if self.current_index >= len(image_data):
                            self.current_index = max(0, len(image_data) - 1)

                    show_image()
                    reaactive_timer()

            # Automatic slideshow — starts immediately on the sample image
            show_image()

            with ui.row().classes("gap-4 mb-0 items-center"):
                ui.button('⭐', on_click=remove_favorite).tooltip(t("favorite_remove"))
                ui.button(t("previous"), on_click=prev_image_click)
                ui.button(t("next"), on_click=next_image_click)
                ui.button("🎬 " + t("export_video"), on_click=lambda: self._open_video_dialog(image_data))

        # ── Background loading ───────────────────────────────────────────────
        async def _load_favorites_bg():
            print("_load_favorites_bg")
            favorites = await run.io_bound(self._collect_all_favorites)
            if not favorites:
                # No real favorites — keep the sample image as-is
                return
            if self.end_background_task:
                print("no more client!") 
                return
            print("continue..._load_favorites_bg") 

            # Replace sample with real data, preserving current position
            was_on_sample = image_data[self.current_index].get('_is_sample', False)
            image_data.clear()
            image_data.extend(favorites)

            # If we were still on the placeholder, jump to the first real image
            if was_on_sample:
                self.current_index = 0
                show_image()
                reaactive_timer()

        ui.timer(0.1, _load_favorites_bg, once=True)

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

    def _open_video_dialog(self, image_data: list):
        """Open video export configuration dialog."""
        from tools.video_export import VideoExportConfig, export_video, list_fonts, VIDEO_RESOLUTIONS, FONT_SIZES, get_music_files
        import threading

        with ui.dialog() as dialog, ui.card().classes("w-[500px] p-6"):
            ui.label("🎬 " + t("export_video")).classes("text-xl font-bold mb-4")

            # Restore saved settings
            _vs = app.storage.general.get("video_export_settings", {})

            name_input = ui.input(t("signature_name"), placeholder=t("your_name"),
                value=_vs.get("user_name", "")).classes("w-full")
            text_input = ui.input(t("signature_text"), placeholder=t("optional_text"),
                value=_vs.get("free_text", "")).classes("w-full")

            extra_info = ui.checkbox(t("video_extra_info"),
                value=_vs.get("extra_info", False)).classes("w-full")

            with ui.row().classes("w-full gap-4"):
                font_select = ui.select(
                    label=t("font_choice"),
                    options=list_fonts(),
                    value=_vs.get("font_preset", "Sans-serif")
                ).classes("flex-1")
                fontsize_select = ui.select(
                    label=t("font_size"),
                    options=list(FONT_SIZES.keys()),
                    value=_vs.get("font_size_label", "Medium")
                ).classes("flex-1")

            with ui.row().classes("w-full gap-4"):
                duration_input = ui.number(t("duration_per_photo"),
                    value=_vs.get("duration", 8), min=3, max=30, step=1).classes("flex-1")
                resolution_select = ui.select(
                    label=t("video_resolution"),
                    options=list(VIDEO_RESOLUTIONS.keys()),
                    value=_vs.get("resolution", "FHD (1920×1080)")
                ).classes("flex-1")

            # Music selection — only if ffmpeg is available
            from tools.video_export import has_ffmpeg, get_music_files
            _has_ffmpeg = has_ffmpeg()
            ui.separator().classes("my-2")

            if not _has_ffmpeg:
                ui.label(f"🎵 {t('ffmpeg_needed_for_music')}").classes("text-sm text-orange-500")
                ui.link(t("menu_settings"), "/Settings", new_tab=False).classes("text-sm text-blue-600")

            # Default music folder = assets/music/
            _default_music_dir = str(Path(__file__).resolve().parent.parent / "assets" / "music")
            _saved_music_dir   = _vs.get("music_dir",  _default_music_dir)
            _saved_music_file  = _vs.get("music_file", "")

            def _list_music(folder: str) -> dict:
                import glob as _glob
                opts = {"": t("no_music")}
                if folder and os.path.isdir(folder):
                    for ext in ["mp3","MP3","wav","WAV","ogg","OGG","m4a","M4A"]:
                        for p in sorted(_glob.glob(f"{folder}/*.{ext}")):
                            opts[p] = Path(p).stem.replace("_"," ").title()
                return opts

            with ui.column().classes("w-full gap-2").bind_visibility_from(
                    ui.label("").style("display:none"), 'visible', lambda _: _has_ffmpeg):
                pass

            # Row 1: music folder input
            music_dir_input = ui.input(
                label=t("music_folder"),
                value=_saved_music_dir,
            ).classes("w-full")
            music_dir_input.visible = _has_ffmpeg

            # Row 2: file select
            _music_opts = _list_music(_saved_music_dir)
            music_file_select = ui.select(
                label=t("background_music"),
                options=_music_opts,
                value=_saved_music_file if _saved_music_file in _music_opts else "",
            ).classes("w-full")
            music_file_select.visible = _has_ffmpeg

            def _refresh_music():
                opts = _list_music(music_dir_input.value.strip())
                cur  = music_file_select.value
                music_file_select.set_options(opts, value=cur if cur in opts else "")

            music_dir_input.on("blur", lambda _: _refresh_music())

            # Row 3: upload to copy into current folder
            async def handle_upload(e):
                dest_dir = music_dir_input.value.strip() or _default_music_dir
                os.makedirs(dest_dir, exist_ok=True)
                file = e.file
                print(file.name)

                file_bytes = await file.read()
                dest_path = os.path.join(dest_dir, file.name)
                print(dest_path)
                with open(dest_path, "wb") as fout:
                    fout.write(file_bytes)

                _refresh_music()
                opts = _list_music(dest_dir)
                if dest_path in opts:
                    music_file_select.set_value(dest_path)
                ui.notify(f"✅ {file.name} {t('music_uploaded')}", type="positive")

            with ui.row().classes("w-full items-center gap-2"):
                ui.upload(
                    label=t("upload_music"),
                    on_upload=handle_upload,
                    auto_upload=True,
                ).props("accept=.mp3,.wav,.ogg,.m4a flat dense").classes("flex-1")
                ui.label(f"⚠️ {t('music_copyright_warning')}")                     .classes("text-xs text-orange-400 flex-1")
            progress_label = ui.label("").classes("text-sm text-gray-500 mt-2")
            progress_bar = ui.linear_progress(value=0, show_value=False).classes("w-full")
            progress_bar.visible = False

            def start_export():
                name_input.props("disable")
                text_input.props("disable")
                progress_bar.visible = True
                progress_label.set_text(t("video_generating"))

                # Build output path in user's home
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                out_dir = os.path.join(os.path.expanduser("~"), "DwarfiumVideos")
                os.makedirs(out_dir, exist_ok=True)
                out_path = os.path.join(out_dir, f"DwarfiumGallery_{ts}.mp4")

                progress_state = {"i": 0, "total": len(image_data), "name": ""}

                def _progress(i, total, name):
                    progress_state["i"] = i
                    progress_state["total"] = total
                    progress_state["name"] = name[:40]

                def _update_progress():
                    if result["status"] is None:
                        i = progress_state["i"]
                        total = progress_state["total"]
                        if total > 0:
                            progress_bar.value = i / total
                        if progress_state["name"]:
                            progress_label.set_text(f"[{i}/{total}] {progress_state['name']}")

                _progress_timer = ui.timer(0.3, _update_progress)

                # Resolve music path
                final_music = music_file_select.value if _has_ffmpeg else ""

                # Save settings for next time
                app.storage.general["video_export_settings"] = {
                    "user_name":       name_input.value,
                    "free_text":       text_input.value,
                    "extra_info":      extra_info.value,
                    "font_preset":     font_select.value,
                    "font_size_label": fontsize_select.value,
                    "duration":        float(duration_input.value),
                    "resolution":      resolution_select.value,
                    "music_dir":       music_dir_input.value if _has_ffmpeg else _default_music_dir,
                    "music_file":      final_music,
                }

                config = VideoExportConfig(
                    images=image_data,
                    output_path=out_path,
                    user_name=name_input.value,
                    free_text=text_input.value,
                    extra_info=extra_info.value,
                    font_preset=font_select.value,
                    font_size_label=fontsize_select.value,
                    duration_per_image=float(duration_input.value),
                    resolution=resolution_select.value,
                    music_path=final_music,                       
                    progress_callback=_progress,
                )

                result = {"status": None, "msg": ""}

                def _run():
                    try:
                        export_video(config)
                        result["status"] = "ok"
                        result["msg"] = os.path.basename(out_path)
                    except Exception as e:
                        result["status"] = "error"
                        result["msg"] = str(e)

                threading.Thread(target=_run, daemon=True).start()

                def _check_done():
                    if result["status"] == "ok":
                        if self.button_cancel_generate:
                            self.button_cancel_generate.text = t('close')
                        progress_label.set_text(f"✅ {t('video_saved')}: {out_path}")
                        progress_bar.value = 1.0
                        ui.notify(f"✅ {t('video_saved')}: {result['msg']}", type="positive")
                        _done_timer.cancel()
                        # Show open folder button
                        def _open_video_folder():
                            folder = str(Path(out_path).parent)
                            self.open_folder(folder)
                        ui.button(icon="folder_open", on_click=_open_video_folder) \
                            .props("flat round color=primary") \
                            .tooltip(t("open_folder"))
                    elif result["status"] == "error":
                        progress_label.set_text(f"❌ {result['msg']}")
                        ui.notify(result["msg"], type="negative")
                        _done_timer.cancel()
                        _progress_timer.cancel()
                    if result["status"] == "ok":
                        _progress_timer.cancel()

                _done_timer = ui.timer(0.5, _check_done)

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                self.button_cancel_generate = ui.button(t("cancel"), on_click=dialog.close).props("flat")
                ui.button("🎬 " + t("generate"), on_click=start_export).props("color=primary")

        dialog.open()

    def cancel_timer(self):
        print("cancel_timer")
        if self.gallery_timer:
            self.gallery_timer.cancel(with_current_invocation=True)
            self.gallery_timer = None