"""A ui.log fed in batches (user-reported Oct 2026): analyses push
thousands of lines a minute from their worker thread, and each one pushed
straight to the page was a message to every browser open - the server fell
behind with the browsers' pings and a phone open at the same time kept
losing its connection.

BatchedLog has ui.log's push(): lines go to a bounded, thread-safe queue
that a timer drains into the real ui.log twice a second (at most
`batch` lines each, all sent together; a line says how many were left out).
Create it where the ui.log is (the timer lives and dies with that context).
"""
from __future__ import annotations

import threading
from collections import deque

from nicegui import ui

from components.i18n import t


class BatchedLog:
    def __init__(self, ui_log, interval: float = 0.5, batch: int = 50):
        self.ui_log = ui_log
        self._queue: deque = deque(maxlen=batch)
        self._skipped = 0
        self._lock = threading.Lock()
        self.timer = ui.timer(interval, self.drain)

    def push(self, message, classes: str | None = None, **kwargs) -> None:
        """As ui.log.push, from any thread."""
        with self._lock:
            if len(self._queue) == self._queue.maxlen:
                self._skipped += 1
            self._queue.append((str(message), classes))

    def drain(self) -> None:
        with self._lock:
            lines, skipped = list(self._queue), self._skipped
            self._queue.clear()
            self._skipped = 0
        try:
            if skipped:
                self.ui_log.push(t("log_lines_skipped", n=skipped))
            for message, classes in lines:     # all sent together: one update
                if classes:
                    self.ui_log.push(message, classes=classes)
                else:
                    self.ui_log.push(message)
        except Exception:
            pass        # the dialog / page is gone

    def clear(self) -> None:
        with self._lock:
            self._queue.clear()
            self._skipped = 0
        self.ui_log.clear()
