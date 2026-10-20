"""Review a session's frames (Explore, its Frames button - user-requested
Oct 2026): the Dwarf writes a JPG of each frame in the session's Thumbnail
subfolder, named like its FITS (M 16_..._32C.fits ->
Thumbnail/M 16_..._32C.jpg); the frames it rejected while stacking carry a
failed_ prefix, both. A gallery of them, enlarged with previous / next;
the bad ones ticked are deleted - their FITS and JPG - so a megastack or a
restack only takes the good ones. The rejected ones can be deleted at once.

On the Dwarf, only plugged in USB: its local copy (Dwarf_Local) isn't the
Dwarf, and its FTP is read-only. On a backup drive too. A mosaic's frames
are in its panels' subfolders. Deleted for good (a USB drive often has no
recycle bin), after a confirmation.

Its images are served by /frame_review/{token}: only the files of an open
review, not any path asked for (the page can be opened over the LAN).
"""
from __future__ import annotations

import os
import secrets
from typing import Awaitable, Callable

from fastapi import HTTPException
from fastapi.responses import FileResponse
from nicegui import app, run, ui

from api.dwarf_backup_fct import win_long_path
from components.i18n import t

THUMBNAIL_DIR = "Thumbnail"
FAILED_PREFIX = "failed_"

_served: dict[str, str] = {}        # token -> a frame's JPG


@app.get("/frame_review/{token}", include_in_schema=False)
def _serve(token: str):
    path = _served.get(token)
    if not path or not os.path.isfile(path):
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="image/jpeg")


def _is_frame_fits(name: str) -> bool:
    return name.lower().endswith(".fits") and not name.startswith("stacked")


def _folders(session_path: str) -> list[str]:
    """The session's folder, and a mosaic's panels (its subfolders)."""
    out = [session_path]
    try:
        for entry in sorted(os.scandir(session_path), key=lambda e: e.name):
            if entry.is_dir() and entry.name != THUMBNAIL_DIR:
                out.append(entry.path)
    except OSError:
        pass
    return out


def list_frames(session_path: str) -> list[dict]:
    """Blocking. The session's frames: {name, folder, panel, fits, jpg,
    failed} - fits / jpg None when missing (the FITS cleaned by Cleanup
    FITS, an older Dwarf without thumbnails). By panel, then by name (their
    capture time, the rejected ones among them)."""
    frames: list[dict] = []
    for folder in _folders(session_path):
        found: dict[str, dict] = {}
        try:
            names = os.listdir(folder)
        except OSError:
            continue
        for name in names:
            if _is_frame_fits(name):
                stem = name[:-5]
                found.setdefault(stem, {})["fits"] = os.path.join(folder, name)
        thumb_dir = os.path.join(folder, THUMBNAIL_DIR)
        try:
            thumbs = os.listdir(thumb_dir)
        except OSError:
            thumbs = []
        for name in thumbs:
            if name.lower().endswith(".jpg"):
                found.setdefault(name[:-4], {})["jpg"] = os.path.join(thumb_dir, name)
        panel = "" if folder == session_path else os.path.basename(folder)
        for stem in sorted(found, key=lambda n: n.removeprefix(FAILED_PREFIX)):
            frames.append({
                "name": stem, "folder": folder, "panel": panel,
                "fits": found[stem].get("fits"), "jpg": found[stem].get("jpg"),
                "failed": stem.startswith(FAILED_PREFIX),
            })
    return frames


def has_frames(session_path: str) -> bool:
    """Blocking, cheap: a Thumbnail subfolder or a rejected FITS (in the
    session or a mosaic's panel)."""
    for folder in _folders(session_path):
        if os.path.isdir(os.path.join(folder, THUMBNAIL_DIR)):
            return True
        try:
            if any(n.startswith(FAILED_PREFIX) and _is_frame_fits(n) for n in os.listdir(folder)):
                return True
        except OSError:
            pass
    return False


def delete_frames(frames: list[dict]) -> tuple[int, list[str]]:
    """Blocking. Deletes their FITS and JPG: (frames deleted, errors)."""
    deleted, errors = 0, []
    for frame in frames:
        ok = True
        for path in (frame.get("fits"), frame.get("jpg")):
            if not path:
                continue
            try:
                os.remove(win_long_path(path))
            except FileNotFoundError:
                pass
            except OSError as e:
                ok = False
                errors.append(f"{os.path.basename(path)}: {e}")
        deleted += ok
    return deleted, errors


async def _confirm(title: str, message: str) -> bool:
    with ui.dialog() as dialog, ui.card().classes("p-4 gap-3"):
        ui.label(title).classes("text-base font-medium")
        ui.label(message).classes("text-sm").style("white-space: pre-line")
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button(t("cancel"), on_click=lambda: dialog.submit(False)).props("flat color=grey")
            ui.button(t("frames_delete"), icon="delete", on_click=lambda: dialog.submit(True)).props("color=negative")
    result = await dialog
    dialog.delete()
    return bool(result)


async def open_review(session_path: str, on_deleted: Callable[[], Awaitable[None]] | None = None) -> None:
    """The review dialog of the session in session_path. on_deleted: called
    after frames were deleted (Explore refreshes the session's sizes)."""
    frames = await run.io_bound(list_frames, session_path)
    if not frames:
        ui.notify(t("frames_none"), type="info")
        return

    tokens: list[str] = []
    for frame in frames:
        frame["url"] = None
        if frame["jpg"]:
            token = secrets.token_urlsafe(12)
            _served[token] = frame["jpg"]
            tokens.append(token)
            frame["url"] = f"/frame_review/{token}"

    selected: set[int] = set()
    checkboxes: dict[int, ui.checkbox] = {}
    tiles: dict[int, ui.element] = {}
    changed = {"deleted": False}
    current = {"index": 0}

    with ui.dialog().props("maximized") as dialog, ui.card().classes("w-full h-full p-4 gap-2 no-wrap"):
        with ui.row().classes("w-full items-center gap-2 no-wrap"):
            ui.label(t("frames_title")).classes("text-base font-medium")
            counts = ui.label("").classes("text-sm text-grey-7")
            ui.space()
            ui.button(icon="close", on_click=dialog.close).props("flat round dense")
        ui.label(t("frames_hint")).classes("text-xs text-grey-7")

        with ui.scroll_area().classes("w-full grow"):
            panel = None
            grid = None
            for i, frame in enumerate(frames):
                if grid is None or frame["panel"] != panel:
                    panel = frame["panel"]
                    if panel:
                        ui.label(panel).classes("text-sm font-medium mt-2")
                    grid = ui.row().classes("w-full gap-2")
                with grid:
                    with ui.column().classes("w-36 gap-0 rounded p-1") as tile:
                        if frame["url"]:
                            ui.element("img").props(f'src="{frame["url"]}" loading="lazy"') \
                                .classes("w-full aspect-square object-cover rounded cursor-zoom-in") \
                                .on("click", lambda _e, i=i: show(i))
                        else:
                            ui.icon("image_not_supported").classes("w-full text-5xl text-grey-5 text-center py-6")
                        with ui.row().classes("w-full items-center gap-0 no-wrap"):
                            box = ui.checkbox(on_change=lambda e, i=i: mark(i, e.value)).props("dense size=xs")
                            # Its date and time, the end of its name (the target, exposure and
                            # filter are the session's)
                            ui.label("_".join(frame["name"].split("_")[-2:])).classes("text-[10px] truncate") \
                                .tooltip(frame["name"])
                        tags = []
                        if frame["failed"]:
                            tags.append(t("frames_rejected"))
                        if not frame["fits"]:
                            tags.append(t("frames_no_fits"))
                        if tags:
                            ui.label(" · ".join(tags)).classes(
                                "text-[10px] " + ("text-negative" if frame["failed"] else "text-grey-6"))
                    if frame["failed"]:
                        tile.classes("bg-red-1")
                    checkboxes[i] = box
                    tiles[i] = tile

        with ui.row().classes("w-full items-center gap-2"):
            reject_btn = ui.button("", icon="delete_sweep", on_click=lambda: delete_rejected()) \
                .props("outline color=negative")
            ui.space()
            ui.button(t("frames_clear_selection"), on_click=lambda: clear_selection()).props("flat color=grey")
            delete_btn = ui.button("", icon="delete", on_click=lambda: delete_selected()).props("color=negative")

    # The enlarged frame: previous / next, ticked from there too
    with ui.dialog() as viewer, ui.card().classes("p-2 gap-2 items-center").style("max-width: 95vw"):
        big = ui.image().classes("rounded").style("width: min(90vw, 1200px); max-height: 80vh").props("fit=contain")
        big_name = ui.label("").classes("text-xs text-center")
        with ui.row().classes("items-center gap-2"):
            ui.button(icon="chevron_left", on_click=lambda: step(-1)).props("flat round")
            big_mark = ui.checkbox(t("frames_mark"), on_change=lambda e: mark(current["index"], e.value))
            ui.button(icon="chevron_right", on_click=lambda: step(1)).props("flat round")
            ui.button(icon="close", on_click=viewer.close).props("flat round")

    def on_key(e) -> None:
        if not viewer.value or not e.action.keydown:
            return
        if e.key.arrow_left:
            step(-1)
        elif e.key.arrow_right:
            step(1)
        elif e.key.name in (" ", "x", "Delete"):
            big_mark.value = not big_mark.value

    keyboard = ui.keyboard(on_key=on_key, ignore=["input", "select", "button", "textarea"])

    def refresh() -> None:
        alive = [i for i in range(len(frames)) if not frames[i].get("gone")]
        rejected = [i for i in alive if frames[i]["failed"]]
        counts.set_text(t("frames_counts", count=len(alive), rejected=len(rejected)))
        reject_btn.set_text(t("frames_delete_rejected", count=len(rejected)))
        reject_btn.set_visibility(bool(rejected))
        delete_btn.set_text(t("frames_delete_selected", count=len(selected)))
        delete_btn.set_enabled(bool(selected))

    def mark(i: int, on: bool) -> None:
        if frames[i].get("gone"):
            return
        if on:
            selected.add(i)
            tiles[i].classes(add="ring-4 ring-red-500")
        else:
            selected.discard(i)
            tiles[i].classes(remove="ring-4 ring-red-500")
        if checkboxes[i].value != on:
            checkboxes[i].value = on
        if viewer.value and current["index"] == i and big_mark.value != on:
            big_mark.value = on
        refresh()

    def clear_selection() -> None:
        for i in list(selected):
            mark(i, False)

    def show(i: int) -> None:
        current["index"] = i
        frame = frames[i]
        big.set_source(frame["url"] or "")
        tags = [t("frames_rejected")] if frame["failed"] else []
        big_name.set_text(" · ".join([frame["panel"], frame["name"], *tags]).strip(" ·"))
        big_mark.value = i in selected
        viewer.open()

    def step(delta: int) -> None:
        i = current["index"]
        for _ in range(len(frames)):
            i = (i + delta) % len(frames)
            if frames[i]["url"] and not frames[i].get("gone"):
                show(i)
                return

    async def delete(indexes: list[int], title: str) -> None:
        if not indexes:
            return
        if not await _confirm(title, t("frames_delete_confirm", count=len(indexes))):
            return
        deleted, errors = await run.io_bound(delete_frames, [frames[i] for i in indexes])
        for i in indexes:
            frames[i]["gone"] = True
            selected.discard(i)
            tiles[i].set_visibility(False)
        changed["deleted"] = changed["deleted"] or deleted > 0
        if errors:
            ui.notify(t("frames_delete_errors", count=len(errors), first=errors[0]), type="negative", multi_line=True)
        ui.notify(t("frames_deleted", count=deleted), type="positive")
        if viewer.value:
            viewer.close()
        refresh()

    async def delete_selected() -> None:
        await delete(sorted(selected), t("frames_delete_selected", count=len(selected)))

    async def delete_rejected() -> None:
        rejected = [i for i, f in enumerate(frames) if f["failed"] and not f.get("gone")]
        await delete(rejected, t("frames_delete_rejected", count=len(rejected)))

    async def closed(e) -> None:
        if e.value:
            return
        for token in tokens:
            _served.pop(token, None)
        for element in (keyboard, viewer, dialog):
            element.delete()
        if changed["deleted"] and on_deleted:
            await on_deleted()

    dialog.on_value_change(closed)
    refresh()
    dialog.open()
