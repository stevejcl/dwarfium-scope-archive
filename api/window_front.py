"""Brings the app's window to the front on Windows (user-requested Oct
2026: after /api/open-in-app navigates it, the window stayed behind the
app that asked; pywebview's own show() / always-on-top blocked the app).

Plain Win32 through ctypes, no extra dependency. The window is the
visible top-level window of one of this process's children - NiceGUI
runs pywebview in a child process - so a browser tab titled "Dwarfium
Scope Archive" is never picked; by its title (ending with the app's
name, as in "⚠️ TRANSFER RUNNING — Dwarfium Scope Archive") only when no
child window is found. Windows lets a background process take the foreground only
when it shares the foreground window's input: this thread is attached to
the foreground window's thread for the call (AttachThreadInput). An Alt
press / release did it before, but the window received the Alt release
and went into menu mode: it looked frozen until clicked (user-reported
Oct 2026). Other systems: nothing (returns False)."""
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
        length = user32.GetWindowTextLengthW(hwnd)
        if not length:
            return True
        title = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title, length + 1)
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
        user32.ShowWindow(hwnd, sw_restore)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    this_thread = kernel32.GetCurrentThreadId()
    user32.GetForegroundWindow.restype = wintypes.HWND
    foreground = user32.GetForegroundWindow()
    foreground_thread = user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
    attached = bool(foreground_thread) and foreground_thread != this_thread and bool(
        user32.AttachThreadInput(this_thread, foreground_thread, True)
    )
    try:
        user32.BringWindowToTop(hwnd)
        return bool(user32.SetForegroundWindow(hwnd))
    finally:
        if attached:
            user32.AttachThreadInput(this_thread, foreground_thread, False)
