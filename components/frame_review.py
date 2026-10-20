"""Review a session's frames (Explore, its Frames button - user-requested
Oct 2026): the Dwarf writes a JPG of each frame in the session's Thumbnail
subfolder, named like its FITS (M 16_..._32C.fits ->
Thumbnail/M 16_..._32C.jpg); the frames it rejected while stacking carry a
failed_ prefix, both. A gallery of them, enlarged with previous / next;
the bad ones ticked are deleted - their FITS and JPG - so a megastack or a
restack only takes the good ones. The rejected ones can be deleted at once.

Where they go:
- a backup copy: into its trash, FRAME_TRASH_DIR in the frame's folder
  (FITS, JPG in its Thumbnail) - restored or deleted for good later
  (open_trash, Explore's "in the trash" line);
- the Dwarf, plugged in USB (its local copy Dwarf_Local isn't the Dwarf, its
  FTP is read-only): deleted for good there - a session backed up has them
  moved into its backup copy's trash at the same time (its drive
  connected), one not backed up loses them, said before.
A mosaic's frames are in its panels' subfolders, its trash in each panel.

Restored from the trash: back into the backup copy; the Dwarf plugged in
USB with the session on it, they can be copied back onto it too - else the
session's own restore (Restore FITS, Transfer) takes them later.

Its images are served by /frame_review/{token}: only the files of an open
review, not any path asked for (the page can be opened over the LAN).
"""
from __future__ import annotations

import os
import secrets
import shutil
from typing import Awaitable, Callable

from fastapi import HTTPException
from fastapi.responses import FileResponse
from nicegui import app, run, ui

from api.dwarf_backup_fct import FRAME_TRASH_DIR, safe_copy2, win_long_path
from components.i18n import t

THUMBNAIL_DIR = "Thumbnail"
FAILED_PREFIX = "failed_"

_served: dict[str, str] = {}        # token -> a frame's JPG

WHEEL_STEP_PX = 100                 # the wheel: a frame per notch (100 px in Chrome / Edge)
PRELOAD = 3                         # frames loaded ahead on each side of the one enlarged


@app.get("/frame_review/{token}", include_in_schema=False)
def _serve(token: str):
    path = _served.get(token)
    if not path or not os.path.isfile(path):
        raise HTTPException(status_code=404)
    return FileResponse(path)


def serve_file(path: str) -> str:
    """The URL serving this image file - only it (Explore's gallery too: its
    sessions' thumbnails, each in its own folder)."""
    token = secrets.token_urlsafe(12)
    _served[token] = path
    return f"/frame_review/{token}"


# ── Files (blocking) ──────────────────────────────────────────────────────────

def _is_frame_fits(name: str) -> bool:
    return name.lower().endswith(".fits") and not name.startswith("stacked")


def _folders(session_path: str) -> list[str]:
    """The session's folder, and a mosaic's panels (its subfolders)."""
    out = [session_path]
    try:
        for entry in sorted(os.scandir(session_path), key=lambda e: e.name):
            if entry.is_dir() and entry.name not in (THUMBNAIL_DIR, FRAME_TRASH_DIR):
                out.append(entry.path)
    except OSError:
        pass
    return out


def _frame(session_path: str, folder: str, name: str, fits: str | None, jpg: str | None) -> dict:
    rel = os.path.relpath(folder, session_path)
    return {
        "name": name, "folder": folder, "rel": "" if rel == "." else rel,
        "panel": "" if folder == session_path else os.path.basename(folder),
        "fits": fits, "jpg": jpg, "failed": name.startswith(FAILED_PREFIX),
    }


def list_frames(session_path: str, in_trash: bool = False) -> list[dict]:
    """Blocking. The session's frames - or its trash's: {name, folder (its
    folder in the session), rel (that folder in the session, "" its root),
    panel, fits, jpg, failed} - fits / jpg None when missing (the FITS
    cleaned by Cleanup FITS, an older Dwarf without thumbnails). By panel,
    then by name (their capture time, the rejected ones among them)."""
    frames: list[dict] = []
    for folder in _folders(session_path):
        base = os.path.join(folder, FRAME_TRASH_DIR) if in_trash else folder
        found: dict[str, dict] = {}
        try:
            names = os.listdir(base)
        except OSError:
            continue
        for name in names:
            if _is_frame_fits(name):
                found.setdefault(name[:-5], {})["fits"] = os.path.join(base, name)
        thumb_dir = os.path.join(base, THUMBNAIL_DIR)
        try:
            thumbs = os.listdir(thumb_dir)
        except OSError:
            thumbs = []
        for name in thumbs:
            if name.lower().endswith(".jpg"):
                found.setdefault(name[:-4], {})["jpg"] = os.path.join(thumb_dir, name)
        for stem in sorted(found, key=lambda n: n.removeprefix(FAILED_PREFIX)):
            frames.append(_frame(session_path, folder, stem, found[stem].get("fits"), found[stem].get("jpg")))
    return frames


def frames_at(session_path: str, frames: list[dict]) -> list[dict]:
    """Blocking. The same frames in another copy of the session (the Dwarf's
    / a backup's): the files found there."""
    out = []
    for frame in frames:
        folder = os.path.join(session_path, frame["rel"]) if frame["rel"] else session_path
        fits = os.path.join(folder, frame["name"] + ".fits")
        jpg = os.path.join(folder, THUMBNAIL_DIR, frame["name"] + ".jpg")
        fits = fits if os.path.isfile(win_long_path(fits)) else None
        jpg = jpg if os.path.isfile(win_long_path(jpg)) else None
        if fits or jpg:
            out.append(_frame(session_path, folder, frame["name"], fits, jpg))
    return out


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


def trash_count(session_path: str) -> int:
    """Blocking. The frames in the session's trash."""
    if not any(os.path.isdir(os.path.join(f, FRAME_TRASH_DIR)) for f in _folders(session_path)):
        return 0
    return len(list_frames(session_path, in_trash=True))


def _move(frames: list[dict], to_trash: bool) -> tuple[int, list[str]]:
    done, errors = 0, []
    for frame in frames:
        base = os.path.join(frame["folder"], FRAME_TRASH_DIR) if to_trash else frame["folder"]
        ok = True
        for path, sub in ((frame.get("fits"), ""), (frame.get("jpg"), THUMBNAIL_DIR)):
            if not path:
                continue
            dst_dir = os.path.join(base, sub) if sub else base
            try:
                os.makedirs(win_long_path(dst_dir), exist_ok=True)
                os.replace(win_long_path(path), win_long_path(os.path.join(dst_dir, os.path.basename(path))))
            except FileNotFoundError:
                pass
            except OSError as e:
                ok = False
                errors.append(f"{os.path.basename(path)}: {e}")
        done += ok
    return done, errors


def move_to_trash(frames: list[dict]) -> tuple[int, list[str]]:
    """Blocking. Into their folder's trash: (frames moved, errors)."""
    return _move(frames, to_trash=True)


def restore_from_trash(frames: list[dict]) -> tuple[int, list[str]]:
    """Blocking. Trash frames (list_frames(in_trash=True)) back into their
    folder: (frames restored, errors)."""
    return _move(frames, to_trash=False)


def delete_frames(frames: list[dict]) -> tuple[int, list[str]]:
    """Blocking. Deletes their FITS and JPG for good: (frames deleted, errors)."""
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


def copy_frames(frames: list[dict], session_path: str) -> tuple[int, list[str]]:
    """Blocking. Copies them into another copy of the session (the Dwarf's),
    an existing file kept: (frames copied, errors)."""
    copied, errors = 0, []
    for frame in frames:
        folder = os.path.join(session_path, frame["rel"]) if frame["rel"] else session_path
        ok = True
        for path, sub in ((frame.get("fits"), ""), (frame.get("jpg"), THUMBNAIL_DIR)):
            if not path:
                continue
            dst_dir = os.path.join(folder, sub) if sub else folder
            dst = os.path.join(dst_dir, os.path.basename(path))
            try:
                if os.path.exists(win_long_path(dst)):
                    continue
                os.makedirs(win_long_path(dst_dir), exist_ok=True)
                if not safe_copy2(win_long_path(path), win_long_path(dst)):
                    raise OSError("copy failed")
            except OSError as e:
                ok = False
                errors.append(f"{os.path.basename(path)}: {e}")
        copied += ok
    return copied, errors


def empty_trash(session_path: str) -> int:
    """Blocking. Deletes the session's trash for good: the frames it held."""
    count = trash_count(session_path)
    for folder in _folders(session_path):
        trash = os.path.join(folder, FRAME_TRASH_DIR)
        if os.path.isdir(trash):
            shutil.rmtree(win_long_path(trash), ignore_errors=True)
    return count


# ── Dialogs ───────────────────────────────────────────────────────────────────

async def ask(title: str, message: str, buttons: list[tuple[str, str, str, object]],
              option: str | None = None) -> object:
    """A question: buttons (label, icon, color, value); None when closed.
    option: a checkbox's label, unticked - then (value, ticked)."""
    with ui.dialog() as dialog, ui.card().classes("p-4 gap-3").style("max-width: 640px"):
        ui.label(title).classes("text-base font-medium")
        ui.label(message).classes("text-sm").style("white-space: pre-line")
        box = ui.checkbox(option).classes("text-sm") if option else None
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button(t("cancel"), on_click=lambda: dialog.submit(None)).props("flat color=grey")
            for label, icon, color, value in buttons:
                ui.button(label, icon=icon or None, on_click=lambda v=value: dialog.submit(v)).props(f"color={color}")
    result = await dialog
    ticked = bool(box and box.value)
    dialog.delete()
    if option:
        return (result, ticked) if result is not None else None
    return result


def _notify_result(key: str, count: int, errors: list[str]) -> None:
    if errors:
        ui.notify(t("frames_errors", count=len(errors), first=errors[0]), type="negative", multi_line=True)
    ui.notify(t(key, count=count), type="positive", multi_line=True)


class _Gallery:
    """The frames' grid and their enlarged view, each frame marked with one
    of choices [(state, icon, color, label, key)] or none (key: its
    keyboard key in the enlarged view; the first one also takes the space
    bar). The caller adds its buttons to footer and acts on marked()."""

    def __init__(self, frames: list[dict], title: str, hint: str, choices: list[tuple], on_close) -> None:
        self.frames = frames
        self.choices = {c[0]: c for c in choices}
        self.first = choices[0][0]
        self.state: dict[int, str] = {}
        self.listeners: list[Callable[[], None]] = []
        self.current = 0
        self.tokens: list[str] = []
        for frame in frames:
            frame["url"] = None
            if frame["jpg"]:
                token = secrets.token_urlsafe(12)
                _served[token] = frame["jpg"]
                self.tokens.append(token)
                frame["url"] = f"/frame_review/{token}"
        self.tiles: dict[int, ui.element] = {}
        self.tile_buttons: dict[int, dict[str, ui.button]] = {}

        # persistent: closed by its X only, which asks first when it must (on_close)
        with ui.dialog().props("maximized persistent") as self.dialog, \
                ui.card().classes("w-full h-full p-4 gap-2 no-wrap"):
            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                ui.label(title).classes("text-base font-medium")
                self.counts = ui.label("").classes("text-sm text-grey-7")
                ui.space()
                ui.button(icon="close", on_click=on_close).props("flat round dense")
            ui.label(hint).classes("text-xs text-grey-7")
            with ui.scroll_area().classes("w-full grow"):
                self._grid()
            self.footer = ui.row().classes("w-full items-center gap-2")

        # The enlarged view. The mouse wheel goes through the frames (user-
        # requested Oct 2026, a session of hundreds): a notch one frame, spun
        # faster several. A plain <img> (a q-img fades in each one) and its
        # neighbours loaded ahead, hidden, so going through them doesn't flicker.
        self._wheel = 0.0
        with ui.dialog() as self.viewer, ui.card().classes("p-2 gap-2 items-center").style("max-width: 95vw") \
                .on("wheel.prevent", self._on_wheel, ["deltaY", "deltaMode"]):
            self.big = ui.element("img").classes("rounded") \
                .style("width: min(90vw, 1200px); max-height: 80vh; object-fit: contain")
            with ui.row().classes("items-center gap-2"):
                self.big_pos = ui.label("").classes("text-xs text-grey-7")
                self.big_name = ui.label("").classes("text-xs text-center")
            with ui.element("div").classes("hidden"):
                self.preload = [ui.element("img") for _ in range(PRELOAD * 2)]
            with ui.row().classes("items-center gap-2"):
                ui.button(icon="chevron_left", on_click=lambda: self.step(-1)).props("flat round")
                self.big_buttons = {
                    state: ui.button(label, icon=icon, on_click=lambda s=state: self.toggle(self.current, s))
                    .props(f"outline color={color} no-caps")
                    for state, icon, color, label, _key in choices
                }
                ui.button(icon="chevron_right", on_click=lambda: self.step(1)).props("flat round")
                ui.button(icon="close", on_click=self.viewer.close).props("flat round")
        self.keyboard = ui.keyboard(on_key=self._on_key, ignore=["input", "select", "button", "textarea"])

    def _grid(self) -> None:
        panel, grid = None, None
        for i, frame in enumerate(self.frames):
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
                            .on("click", lambda _e, i=i: self.show(i))
                    else:
                        ui.icon("image_not_supported").classes("w-full text-5xl text-grey-5 text-center py-6")
                    with ui.row().classes("w-full items-center gap-0 no-wrap"):
                        buttons = {}
                        for state, (_s, icon, color, label, _key) in self.choices.items():
                            buttons[state] = ui.button(icon=icon, on_click=lambda i=i, s=state: self.toggle(i, s)) \
                                .props(f"flat dense round size=sm color=grey-6").tooltip(label)
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
                self.tiles[i] = tile
                self.tile_buttons[i] = buttons

    def _on_key(self, e) -> None:
        if not self.viewer.value or not e.action.keydown:
            return
        if e.key.arrow_left:
            self.step(-1)
        elif e.key.arrow_right:
            self.step(1)
        elif e.key.name == " ":
            self.toggle(self.current, self.first)
        else:
            for state, (_s, _icon, _color, _label, key) in self.choices.items():
                if key and e.key.name.lower() == key:
                    self.toggle(self.current, state)

    # The marks
    def alive(self) -> list[int]:
        return [i for i in range(len(self.frames)) if not self.frames[i].get("gone")]

    def marked(self, state: str) -> list[int]:
        return sorted(i for i, s in self.state.items() if s == state)

    def set_state(self, i: int, state: str | None) -> None:
        if self.frames[i].get("gone"):
            return
        old = self.state.get(i)
        if old:
            self.tiles[i].classes(remove=f"ring-4 ring-{self._ring(old)}")
        if state:
            self.state[i] = state
            self.tiles[i].classes(add=f"ring-4 ring-{self._ring(state)}")
        else:
            self.state.pop(i, None)
        for s, button in self.tile_buttons[i].items():
            button.props(f"color={self.choices[s][2] if s == state else 'grey-6'}")
        if self.viewer.value and self.current == i:
            self._big_marks()
        for listener in self.listeners:
            listener()

    def _ring(self, state: str) -> str:
        return {"negative": "red-500", "positive": "green-600"}.get(self.choices[state][2], "blue-500")

    def toggle(self, i: int, state: str) -> None:
        self.set_state(i, None if self.state.get(i) == state else state)

    def clear(self) -> None:
        for i in list(self.state):
            self.set_state(i, None)

    def remove(self, indexes: list[int]) -> None:
        for i in indexes:
            self.set_state(i, None)
            self.frames[i]["gone"] = True
            self.tiles[i].set_visibility(False)
        if self.viewer.value:
            self.viewer.close()
        for listener in self.listeners:
            listener()

    # The enlarged view
    def _big_marks(self) -> None:
        for state, button in self.big_buttons.items():
            if self.state.get(self.current) == state:
                button.props(remove="outline")
            else:
                button.props("outline")

    def _shown(self) -> list[int]:
        """The frames the enlarged view goes through: an image, not deleted."""
        return [i for i, f in enumerate(self.frames) if f["url"] and not f.get("gone")]

    def show(self, i: int) -> None:
        self.current = i
        frame = self.frames[i]
        self.big.props(f'src="{frame["url"] or ""}"')
        tags = [t("frames_rejected")] if frame["failed"] else []
        self.big_name.set_text(" · ".join([frame["panel"], frame["name"], *tags]).strip(" ·"))
        shown = self._shown()
        if i in shown:
            k = shown.index(i)
            self.big_pos.set_text(f"{k + 1} / {len(shown)}")
            ahead = shown[k + 1:k + 1 + PRELOAD] + shown[max(0, k - PRELOAD):k]
            for img, j in zip(self.preload, ahead):
                img.props(f'src="{self.frames[j]["url"]}"')
        self._big_marks()
        self.viewer.open()

    def step(self, delta: int) -> None:
        """delta frames on (back when < 0), round from the last to the first."""
        shown = self._shown()
        if not shown:
            return
        k = shown.index(self.current) if self.current in shown else 0
        self.show(shown[(k + delta) % len(shown)])

    def _on_wheel(self, e) -> None:
        """The wheel: a notch (100 px) a frame, faster turned more frames per
        event; stops at the first and the last."""
        dy = float(e.args.get("deltaY") or 0)
        if e.args.get("deltaMode") == 1:        # lines (Firefox): ~33 px each
            dy *= 33
        self._wheel += dy
        frames = int(self._wheel / WHEEL_STEP_PX)
        if not frames:
            return
        self._wheel -= frames * WHEEL_STEP_PX
        shown = self._shown()
        if not shown:
            return
        k = shown.index(self.current) if self.current in shown else 0
        target = min(max(k + frames, 0), len(shown) - 1)
        if target != k:
            self.show(shown[target])

    def open(self) -> None:
        for listener in self.listeners:
            listener()
        self.dialog.open()

    def close(self) -> None:
        for token in self.tokens:
            _served.pop(token, None)
        for element in (self.keyboard, self.viewer, self.dialog):
            element.delete()


async def open_review(session_path: str, on_changed: Callable[[], Awaitable[None]] | None = None, *,
                      on_dwarf: bool = False, backed_up: bool = False, backup_path: str | None = None,
                      dwarf_path: str | None = None) -> None:
    """The review of the session in session_path: its frames ticked deleted
    - a backup copy's into its trash; on_dwarf: the Dwarf's, deleted for good,
    and moved into the trash of its backup copy in backup_path (backed_up:
    there is one, backup_path None when its drive isn't connected).
    dwarf_path: a backup copy's session also on the Dwarf plugged in USB -
    its confirmation offers to delete them from the Dwarf too (for good,
    unticked: else a later backup of the session brings them back).
    on_changed: called once frames were deleted (Explore refreshes the
    session)."""
    frames = await run.io_bound(list_frames, session_path)
    if not frames:
        ui.notify(t("frames_none"), type="info")
        return
    changed = {"any": False}

    async def close() -> None:
        gallery.close()
        if changed["any"] and on_changed:
            await on_changed()

    gallery = _Gallery(frames, t("frames_title"), t("frames_hint"),
                       [("delete", "delete", "negative", t("frames_mark"), "d")], close)
    with gallery.footer:
        reject_btn = ui.button("", icon="delete_sweep", on_click=lambda: delete_rejected()) \
            .props("outline color=negative")
        ui.space()
        ui.button(t("frames_clear_selection"), on_click=gallery.clear).props("flat color=grey")
        delete_btn = ui.button("", icon="delete", on_click=lambda: delete_selected()).props("color=negative")

    def refresh() -> None:
        alive = gallery.alive()
        rejected = [i for i in alive if frames[i]["failed"]]
        selected = gallery.marked("delete")
        gallery.counts.set_text(t("frames_counts", count=len(alive), rejected=len(rejected)))
        reject_btn.set_text(t("frames_delete_rejected", count=len(rejected)))
        reject_btn.set_visibility(bool(rejected))
        delete_btn.set_text(t("frames_delete_selected", count=len(selected)))
        delete_btn.set_enabled(bool(selected))

    gallery.listeners.append(refresh)

    def confirm_text(count: int) -> str:
        if not on_dwarf:
            return t("frames_confirm_to_trash", count=count)
        if not backed_up:
            return t("frames_confirm_dwarf_not_backed", count=count)
        if not backup_path:
            return t("frames_confirm_dwarf_backup_offline", count=count)
        return t("frames_confirm_dwarf_backed", count=count, path=backup_path)

    async def delete(indexes: list[int], title: str) -> None:
        if not indexes:
            return
        label = t("frames_delete") if on_dwarf else t("frames_to_trash")
        also_dwarf = False
        if not on_dwarf and dwarf_path:
            answer = await ask(title, confirm_text(len(indexes)), [(label, "delete", "negative", True)],
                               option=t("frames_also_dwarf", path=dwarf_path))
            if not answer:
                return
            also_dwarf = answer[1]
        elif not await ask(title, confirm_text(len(indexes)), [(label, "delete", "negative", True)]):
            return
        chosen = [frames[i] for i in indexes]
        if on_dwarf:
            if backup_path:
                copies = await run.io_bound(frames_at, backup_path, chosen)
                moved, errors = await run.io_bound(move_to_trash, copies)
                if errors:
                    ui.notify(t("frames_errors", count=len(errors), first=errors[0]), type="negative",
                              multi_line=True)
                if moved:
                    ui.notify(t("frames_backup_trashed", count=moved), type="info", multi_line=True)
            done, errors = await run.io_bound(delete_frames, chosen)
            _notify_result("frames_deleted", done, errors)
        else:
            done, errors = await run.io_bound(move_to_trash, chosen)
            _notify_result("frames_trashed", done, errors)
            if also_dwarf:
                copies = await run.io_bound(frames_at, dwarf_path, chosen)
                deleted, errors = await run.io_bound(delete_frames, copies)
                _notify_result("frames_dwarf_deleted", deleted, errors)
        changed["any"] = changed["any"] or done > 0
        gallery.remove(indexes)

    async def delete_selected() -> None:
        selected = gallery.marked("delete")
        await delete(selected, t("frames_delete_selected", count=len(selected)))

    async def delete_rejected() -> None:
        rejected = [i for i in gallery.alive() if frames[i]["failed"]]
        await delete(rejected, t("frames_delete_rejected", count=len(rejected)))

    gallery.open()


async def open_trash(session_path: str, on_changed: Callable[[], Awaitable[None]] | None = None, *,
                     dwarf_path: str | None = None) -> None:
    """The trash of the backup copy in session_path: each frame marked
    Restore or Delete, done when leaving (or Apply); Empty the trash.
    dwarf_path: the session on the Dwarf plugged in USB - the frames
    restored can be copied back onto it too."""
    frames = await run.io_bound(list_frames, session_path, True)
    if not frames:
        ui.notify(t("trash_empty"), type="info")
        return
    changed = {"any": False, "closed": False}

    async def finish() -> None:
        if changed["closed"]:
            return
        changed["closed"] = True
        gallery.close()
        if changed["any"] and on_changed:
            await on_changed()

    async def leave() -> None:
        restore, delete = gallery.marked("restore"), gallery.marked("delete")
        if restore or delete:
            choice = await ask(t("trash_title"), t("trash_leave", restore=len(restore), delete=len(delete)),
                                [(t("trash_leave_discard"), "", "grey", "discard"),
                                 (t("trash_apply"), "check", "primary", "apply")])
            if choice is None:
                return
            if choice == "apply":
                await apply()
        await finish()

    gallery = _Gallery(frames, t("trash_title"), t("trash_hint"),
                       [("restore", "restore_from_trash", "positive", t("trash_restore"), "r"),
                        ("delete", "delete_forever", "negative", t("trash_delete"), "d")], leave)
    with gallery.footer:
        ui.button(t("trash_empty_btn"), icon="delete_forever", on_click=lambda: empty()) \
            .props("outline color=negative")
        ui.space()
        ui.button(t("trash_all_restore"), on_click=lambda: [gallery.set_state(i, "restore") for i in gallery.alive()]) \
            .props("flat color=positive")
        ui.button(t("frames_clear_selection"), on_click=gallery.clear).props("flat color=grey")
        apply_btn = ui.button("", icon="check", on_click=lambda: apply_clicked()).props("color=primary")

    def refresh() -> None:
        restore, delete = gallery.marked("restore"), gallery.marked("delete")
        gallery.counts.set_text(t("trash_counts", count=len(gallery.alive())))
        apply_btn.set_text(t("trash_apply_counts", restore=len(restore), delete=len(delete)))
        apply_btn.set_enabled(bool(restore or delete))

    gallery.listeners.append(refresh)

    async def apply() -> None:
        restore, delete = gallery.marked("restore"), gallery.marked("delete")
        if delete:
            done, errors = await run.io_bound(delete_frames, [frames[i] for i in delete])
            _notify_result("frames_deleted", done, errors)
            changed["any"] = True
            gallery.remove(delete)
        if restore:
            chosen = [frames[i] for i in restore]
            done, errors = await run.io_bound(restore_from_trash, chosen)
            _notify_result("trash_restored", done, errors)
            changed["any"] = True
            gallery.remove(restore)
            if dwarf_path and done and await ask(
                    t("trash_title"), t("trash_restore_dwarf", count=done, path=dwarf_path),
                    [(t("trash_restore_dwarf_btn"), "usb", "primary", True)]):
                copies = await run.io_bound(frames_at, session_path, chosen)
                copied, errors = await run.io_bound(copy_frames, copies, dwarf_path)
                _notify_result("trash_copied_dwarf", copied, errors)

    async def apply_clicked() -> None:
        await apply()
        if not gallery.alive():
            await finish()

    async def empty() -> None:
        count = len(gallery.alive())
        if not await ask(t("trash_empty_btn"), t("trash_empty_confirm", count=count),
                          [(t("trash_empty_btn"), "delete_forever", "negative", True)]):
            return
        done = await run.io_bound(empty_trash, session_path)
        ui.notify(t("frames_deleted", count=done), type="positive")
        changed["any"] = True
        gallery.remove(gallery.alive())
        await finish()

    gallery.open()
