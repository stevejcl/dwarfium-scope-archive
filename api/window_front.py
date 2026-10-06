"""Brings the app's window to the front on Windows (user-requested Oct
2026: after /api/open-in-app navigates it, the window stayed behind the
app that asked; pywebview's own show() / always-on-top blocked the app).

Plain Win32 through ctypes, no extra dependency. The window is the
visible top-level window of one of this process's children - NiceGUI
runs pywebview in a child process - so a browser tab titled "Dwarfium
Scope Archive" is never picked; by its title (ending with the app's
name, as in "⚠️ TRANSFER RUNNING — Dwarfium Scope Archive") only when no
child window is found.

Nothing here simulates input or waits on another window's thread
(user-reported Oct 2026: the earlier Alt-key trick froze the app's
interface after each open-in-app): titles are read with
InternalGetWindowText (no message sent), a minimized window is restored
with ShowWindowAsync, and when Windows refuses SetForegroundWindow (a
background process usually may not take the focus) the window flashes in
the taskbar instead. Other systems: nothing (returns False)."""
from __future__ import annotations

import multiprocessing
import os
import sys

APP_TITLE = "Dwarfium Scope Archive"


def bring_to_front(title_part: str = APP_TITLE) -> bool:
    """True when the window was found and brought to front (Windows)."""
    if not sys.platform.startswith("win"):
        return False
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    child_pids = {child.pid for child in multiprocessing.active_children()}
    by_child: list[int] = []
    by_self: list[int] = []
    by_title: list[int] = []

    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _visit(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        title = ctypes.create_unicode_buffer(512)
        if not user32.InternalGetWindowText(hwnd, title, 512):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in child_pids:
            by_child.append(hwnd)
        elif pid.value == os.getpid():
            by_self.append(hwnd)
        elif title.value.endswith(title_part):  # not "... - Google Chrome"
            by_title.append(hwnd)
        return True

    user32.EnumWindows(enum_proc(_visit), 0)
    candidates = by_child or by_self or by_title
    if not candidates:
        return False
    hwnd = candidates[0]

    sw_restore = 9
    if user32.IsIconic(hwnd):
        user32.ShowWindowAsync(hwnd, sw_restore)
    if user32.SetForegroundWindow(hwnd):
        return True
    _flash(user32, hwnd)
    return False


def _flash(user32, hwnd) -> None:
    """Taskbar flash until the window comes to front (FlashWindowEx)."""
    import ctypes
    from ctypes import wintypes

    class FLASHWINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.UINT),
            ("hwnd", wintypes.HWND),
            ("dwFlags", wintypes.DWORD),
            ("uCount", wintypes.UINT),
            ("dwTimeout", wintypes.DWORD),
        ]

    flashw_all, flashw_timernofg = 0x3, 0xC
    info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, flashw_all | flashw_timernofg, 0, 0)
    user32.FlashWindowEx(ctypes.byref(info))
