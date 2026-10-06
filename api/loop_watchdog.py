"""Diagnostic (user-reported Oct 2026: the app's interface froze after
pages opened from Astro Dwarf Session, only Ctrl+C got out). Enabled
with the environment variable DWARFIUM_WATCHDOG=1.

An asyncio task beats every second; a separate thread checks the beat.
When the event loop hasn't beaten for 5 s (something blocks it), the
stacks of all threads are printed once - showing where it blocks - then
again only after it recovered and blocked anew. Nothing printed while
the interface is frozen means the event loop is fine and the freeze is
on the window's side."""
from __future__ import annotations

import asyncio
import faulthandler
import os
import sys
import threading
import time

from nicegui import app

_STALL_S = 5.0
_last_beat = time.monotonic()


async def _beat() -> None:
    global _last_beat
    while True:
        _last_beat = time.monotonic()
        await asyncio.sleep(1.0)


def _watch() -> None:
    reported = False
    while True:
        time.sleep(1.0)
        stalled = time.monotonic() - _last_beat
        if stalled > _STALL_S and not reported:
            print(f"[watchdog] event loop blocked for {stalled:.0f} s - thread stacks:", file=sys.stderr, flush=True)
            faulthandler.dump_traceback(file=sys.stderr, all_threads=True)
            reported = True
        elif stalled <= _STALL_S and reported:
            print("[watchdog] event loop running again", file=sys.stderr, flush=True)
            reported = False


def register() -> None:
    if os.environ.get("DWARFIUM_WATCHDOG") != "1":
        return

    async def _start() -> None:
        asyncio.get_running_loop().create_task(_beat())
        threading.Thread(target=_watch, name="loop-watchdog", daemon=True).start()
        print("[watchdog] enabled", flush=True)

    app.on_startup(_start)
