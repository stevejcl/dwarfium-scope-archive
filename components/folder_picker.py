"""Folder selection that works in the app's window and in a web browser
(user-reported Oct 2026: the Transfer page, opened in a browser from Astro
Dwarf Session's "Archive" link, did nothing on its folder buttons).

app.native.main_window.create_file_dialog() opens the system dialog in the
app's own window (pywebview) - from a page shown in a browser it opens
there, out of sight, or not at all. choose_folder() keeps that dialog in
the app's window (pywebview exposes window.pywebview to its pages, a
browser doesn't) and otherwise shows a folder picker in the page: the
folders are listed by this backend, on the same PC, from a start folder,
never above an optional root."""
from __future__ import annotations

import os

from nicegui import app, run, ui

from components.i18n import t


async def _in_app_window(client) -> bool:
    if getattr(app.native, "main_window", None) is None:
        return False
    try:
        return bool(await client.run_javascript("!!window.pywebview", timeout=2.0))
    except Exception:
        return False


async def _native_folder(start_dir: str | None) -> str | None:
    import webview  # only with the native window

    folder_mode = webview.FileDialog.FOLDER if hasattr(webview, "FileDialog") else webview.FOLDER_DIALOG
    if start_dir:
        folder = await app.native.main_window.create_file_dialog(folder_mode, allow_multiple=False, directory=start_dir)
    else:
        folder = await app.native.main_window.create_file_dialog(folder_mode, allow_multiple=False)
    return folder[0] if folder else None


def _subfolders(path: str) -> list[str]:
    try:
        return sorted(
            (entry.name for entry in os.scandir(path) if entry.is_dir(follow_symlinks=False)),
            key=str.lower,
        )
    except OSError:
        return []


def _inside(path: str, root: str | None) -> bool:
    if not root:
        return True
    path, root = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(root))
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


async def _page_folder(start_dir: str | None, root: str | None) -> str | None:
    current = os.path.abspath(start_dir or root or os.path.expanduser("~"))
    if not os.path.isdir(current) or not _inside(current, root):
        current = os.path.abspath(root) if root else os.path.expanduser("~")
    state = {"path": current}

    with ui.dialog() as dialog, ui.card().classes("w-[min(92vw,640px)]"):
        ui.label(t("folder_picker_title")).classes("text-base font-medium")
        path_label = ui.label("").classes("text-sm break-all")
        listing = ui.column().classes("w-full gap-0").style("max-height: 50vh; overflow-y: auto")
        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button(t("cancel"), on_click=lambda: dialog.submit(None)).props("flat")
            ui.button(t("folder_picker_choose"), on_click=lambda: dialog.submit(state["path"])).props("color=primary")

    async def show(path: str) -> None:
        state["path"] = path
        path_label.set_text(path)
        names = await run.io_bound(_subfolders, path)
        listing.clear()
        with listing:
            parent = os.path.dirname(path.rstrip(os.sep)) or path
            if parent != path and _inside(parent, root):
                ui.button("..", icon="arrow_upward", on_click=lambda p=parent: show(p)).props(
                    "flat dense no-caps align=left"
                ).classes("w-full")
            if not names:
                ui.label(t("folder_picker_empty")).classes("text-sm text-gray-500 p-2")
            for name in names:
                child = os.path.join(path, name)
                ui.button(name, icon="folder", on_click=lambda p=child: show(p)).props(
                    "flat dense no-caps align=left"
                ).classes("w-full")

    await show(current)
    return await dialog


async def choose_folder(client, start_dir: str | None = None, root: str | None = None) -> str | None:
    """A folder chosen by the user, or None (cancelled). The system dialog
    in the app's window, the in-page picker in a browser (never above
    root there; the caller still checks the native dialog's choice)."""
    if await _in_app_window(client):
        return await _native_folder(start_dir)
    return await _page_folder(start_dir, root)
