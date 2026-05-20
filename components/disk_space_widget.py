"""
disk_space_widget.py
--------------------
Reusable NiceGUI component that displays disk space for a given path.

When the drive is ONLINE  : queries shutil.disk_usage, shows live values,
                            and persists them to db/diskinfo.json.
When the drive is OFFLINE : reads last-known values from db/diskinfo.json
                            and shows them with a "last seen" timestamp.

Usage:
    from components.disk_space_widget import disk_space_widget

    widget = disk_space_widget(location, drive_type="backup", drive_id=1, name="My Drive")
    # later:
    await widget.refresh(new_location, drive_type="backup", drive_id=new_id, name="Other")
""""""
disk_space_widget.py
--------------------
Reusable NiceGUI component that displays disk space for a given path.

When the drive is ONLINE  : queries shutil.disk_usage, shows live values,
                            and persists them to db/diskinfo.json.
When the drive is OFFLINE : reads last-known values from db/diskinfo.json
                            and shows them with a "last seen" timestamp.

Usage:
    from components.disk_space_widget import disk_space_widget

    widget = disk_space_widget(location, drive_type="backup", drive_id=1, name="My Drive")
    # later:
    await widget.refresh(new_location, drive_type="backup", drive_id=new_id, name="Other")
"""

from nicegui import ui, run
from api.dwarf_backup_fct import get_disk_space_info
from api.diskinfo import save_disk_info, load_disk_info
from components.i18n import t


def _bar_color(free_pct: float) -> str:
    if free_pct < 5:
        return "bg-red-500"
    if free_pct < 15:
        return "bg-orange-400"
    if free_pct < 30:
        return "bg-yellow-400"
    return "bg-green-500"


def _text_color_cls(info: dict) -> str:
    if not info.get("online"):
        return "text-gray-400"
    if info.get("critical"):
        return "text-red-500"
    if info.get("warning"):
        return "text-orange-400"
    return "text-green-500"


class DiskSpaceWidget:
    def __init__(
        self,
        location:   str | None = None,
        drive_type: str | None = None,   # "backup" or "dwarf"
        drive_id:   int | None = None,
        name:       str        = "",
    ):
        self._location   = location or ""
        self._drive_type = drive_type
        self._drive_id   = drive_id
        self._name       = name
        self._bar        = None
        self._label      = None
        self._detail     = None
        self._container  = None
        self._build()
        if location:
            ui.timer(0.05, lambda: ui.timer(0, self._async_load, once=True), once=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def refresh(
        self,
        new_location:   str | None = None,
        drive_type:     str | None = None,
        drive_id:       int | None = None,
        name:           str        = "",
    ):
        self._location   = new_location or ""
        if drive_type is not None:
            self._drive_type = drive_type
        if drive_id is not None:
            self._drive_id = drive_id
        if name:
            self._name = name
        await self._async_load()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build(self):
        with ui.card().tight().classes("w-full px-3 py-2 gap-1") as self._container:
            with ui.row().classes("w-full items-center justify-between gap-2"):
                self._label  = ui.label("").classes("text-sm font-semibold")
                self._detail = ui.label("").classes("text-xs text-gray-400")
            with ui.element("div").classes("w-full h-2 rounded bg-gray-700"):
                self._bar = ui.element("div").classes("h-2 rounded transition-all duration-500")
        self._set_hidden()

    def _set_hidden(self):
        self._container.visible = False
        self._container.classes(remove="mt-1")

    def _set_offline(self, cached: dict | None = None):
        self._container.visible = True
        self._container.classes(add="mt-1")
        self._container.visible = True
        if cached:
            free_pct  = cached.get("free_pct", 0)
            used_pct  = max(0, min(100, 100 - free_pct))
            updated   = cached.get("updated_at", "")[:16].replace("T", " ")
            self._label.set_text(
                f"📴 {cached.get('free_str','?')} {t('disk_free')} / {cached.get('total_str','?')}"
                f"  ({t('disk_offline_cached')} {updated})"
            )
            self._label.classes(replace="text-sm font-semibold text-gray-400")
            self._detail.set_text(
                f"{t('disk_used')}: {cached.get('used_str','?')}  "
                f"({free_pct}% {t('disk_free_short')})"
            )
            self._bar.style(f"width: {used_pct:.1f}%")
            self._bar.classes(replace=f"h-2 rounded transition-all duration-500 {_bar_color(free_pct)}")
        else:
            self._label.set_text(t("disk_offline"))
            self._label.classes(replace="text-sm font-semibold text-gray-400")
            self._detail.set_text(self._location or "")
            self._bar.style("width: 0%")
            self._bar.classes(replace="h-2 rounded transition-all duration-500 bg-gray-600")

    def _apply_online(self, info: dict):
        self._container.visible = True
        self._container.classes(add="mt-1")
        free_pct  = info["free_pct"]
        used_pct  = max(0, min(100, 100 - free_pct))
        txt_cls   = _text_color_cls(info)
        bar_cls   = _bar_color(free_pct)
        icon      = "🔴 " if info.get("critical") else ("⚠️ " if info.get("warning") else "💾 ")

        self._label.set_text(
            f"{icon}{info['free_str']} {t('disk_free')} / {info['total_str']}"
        )
        self._label.classes(replace=f"text-sm font-semibold {txt_cls}")
        self._detail.set_text(
            f"{t('disk_used')}: {info['used_str']}  ({free_pct}% {t('disk_free_short')})"
        )
        self._bar.style(f"width: {used_pct:.1f}%")
        self._bar.classes(replace=f"h-2 rounded transition-all duration-500 {bar_cls}")

    async def _async_load(self):
        if not self._location:
            self._set_hidden()
            return

        info = await run.io_bound(get_disk_space_info, self._location)

        if info["online"]:
            if self._drive_type and self._drive_id is not None:
                info["location"] = self._location
                await run.io_bound(
                    save_disk_info,
                    self._drive_type, self._drive_id, info, self._name
                )
            self._apply_online(info)
        else:
            cached = None
            if self._drive_type and self._drive_id is not None:
                cached = await run.io_bound(
                    load_disk_info, self._drive_type, self._drive_id
                )
            self._set_offline(cached)


def disk_space_widget(
    location:   str | None = None,
    drive_type: str | None = None,
    drive_id:   int | None = None,
    name:       str        = "",
) -> DiskSpaceWidget:
    """Drop-in factory — creates the widget at the current NiceGUI context position."""
    return DiskSpaceWidget(location, drive_type=drive_type, drive_id=drive_id, name=name)

from nicegui import ui, run
from api.dwarf_backup_fct import get_disk_space_info
from api.diskinfo import save_disk_info, load_disk_info
from components.i18n import t


def _bar_color(free_pct: float) -> str:
    if free_pct < 5:
        return "bg-red-500"
    if free_pct < 15:
        return "bg-orange-400"
    if free_pct < 30:
        return "bg-yellow-400"
    return "bg-green-500"


def _text_color_cls(info: dict) -> str:
    if not info.get("online"):
        return "text-gray-400"
    if info.get("critical"):
        return "text-red-500"
    if info.get("warning"):
        return "text-orange-400"
    return "text-green-500"


class DiskSpaceWidget:
    def __init__(
        self,
        location:   str | None = None,
        drive_type: str | None = None,   # "backup" or "dwarf"
        drive_id:   int | None = None,
        name:       str        = "",
    ):
        self._location   = location or ""
        self._drive_type = drive_type
        self._drive_id   = drive_id
        self._name       = name
        self._bar        = None
        self._label      = None
        self._detail     = None
        self._container  = None
        self._build()
        if location:
            ui.timer(0.05, lambda: ui.timer(0, self._async_load, once=True), once=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def refresh(
        self,
        new_location:   str | None = None,
        drive_type:     str | None = None,
        drive_id:       int | None = None,
        name:           str        = "",
    ):
        self._location   = new_location or ""
        if drive_type is not None:
            self._drive_type = drive_type
        if drive_id is not None:
            self._drive_id = drive_id
        if name:
            self._name = name
        await self._async_load()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build(self):
        with ui.card().tight().classes("w-full mt-1 px-3 py-2 gap-1") as self._container:
            with ui.row().classes("w-full items-center justify-between gap-2"):
                self._label  = ui.label("").classes("text-sm font-semibold")
                self._detail = ui.label("").classes("text-xs text-gray-400")
            with ui.element("div").classes("w-full h-2 rounded bg-gray-700"):
                self._bar = ui.element("div").classes("h-2 rounded transition-all duration-500")
        self._set_hidden()

    def _set_hidden(self):
        self._container.visible = False

    def _set_offline(self, cached: dict | None = None):
        self._container.visible = True
        if cached:
            free_pct  = cached.get("free_pct", 0)
            used_pct  = max(0, min(100, 100 - free_pct))
            updated   = cached.get("updated_at", "")[:16].replace("T", " ")
            self._label.set_text(
                f"📴 {cached.get('free_str','?')} {t('disk_free')} / {cached.get('total_str','?')}"
                f"  ({t('disk_offline_cached')} {updated})"
            )
            self._label.classes(replace="text-sm font-semibold text-gray-400")
            self._detail.set_text(
                f"{t('disk_used')}: {cached.get('used_str','?')}  "
                f"({free_pct}% {t('disk_free_short')})"
            )
            self._bar.style(f"width: {used_pct:.1f}%")
            self._bar.classes(replace=f"h-2 rounded transition-all duration-500 {_bar_color(free_pct)}")
        else:
            self._label.set_text(t("disk_offline"))
            self._label.classes(replace="text-sm font-semibold text-gray-400")
            self._detail.set_text(self._location or "")
            self._bar.style("width: 0%")
            self._bar.classes(replace="h-2 rounded transition-all duration-500 bg-gray-600")

    def _apply_online(self, info: dict):
        self._container.visible = True
        free_pct  = info["free_pct"]
        used_pct  = max(0, min(100, 100 - free_pct))
        txt_cls   = _text_color_cls(info)
        bar_cls   = _bar_color(free_pct)
        icon      = "🔴 " if info.get("critical") else ("⚠️ " if info.get("warning") else "💾 ")

        self._label.set_text(
            f"{icon}{info['free_str']} {t('disk_free')} / {info['total_str']}"
        )
        self._label.classes(replace=f"text-sm font-semibold {txt_cls}")
        self._detail.set_text(
            f"{t('disk_used')}: {info['used_str']}  ({free_pct}% {t('disk_free_short')})"
        )
        self._bar.style(f"width: {used_pct:.1f}%")
        self._bar.classes(replace=f"h-2 rounded transition-all duration-500 {bar_cls}")

    async def _async_load(self):
        if not self._location:
            self._set_hidden()
            return

        info = await run.io_bound(get_disk_space_info, self._location)

        if info["online"]:
            if self._drive_type and self._drive_id is not None:
                info["location"] = self._location
                await run.io_bound(
                    save_disk_info,
                    self._drive_type, self._drive_id, info, self._name
                )
            self._apply_online(info)
        else:
            cached = None
            if self._drive_type and self._drive_id is not None:
                cached = await run.io_bound(
                    load_disk_info, self._drive_type, self._drive_id
                )
            self._set_offline(cached)


def disk_space_widget(
    location:   str | None = None,
    drive_type: str | None = None,
    drive_id:   int | None = None,
    name:       str        = "",
) -> DiskSpaceWidget:
    """Drop-in factory — creates the widget at the current NiceGUI context position."""
    return DiskSpaceWidget(location, drive_type=drive_type, drive_id=drive_id, name=name)
