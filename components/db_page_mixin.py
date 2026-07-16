# components/db_page_mixin.py
"""
Mixin for NiceGUI page classes that open a self.conn SQLite connection.
Automatically closes the connection when the client disconnects.

Usage:
    class MyApp(DbPageMixin):
        def build_ui(self):
            self.conn = connect_db(self.database)
            self.register_conn_close()  # call after self.conn is set
"""
from nicegui import ui
from api.dwarf_backup_db import close_db


class DbPageMixin:
    """Mixin that closes self.conn on client disconnect."""

    def register_conn_close(self):
        """Call once after self.conn is opened in build_ui."""
        try:
            ui.context.client.on_disconnect(self._close_conn)
        except Exception:
            pass  # no client context (e.g. background task)

    def _close_conn(self):
        conn = getattr(self, "conn", None)
        if conn is not None:
            try:
                close_db(conn)
            except Exception:
                pass
            self.conn = None

    def ensure_conn(self):
        """
        Make sure self.conn is usable. A transient client disconnect during a
        long-running operation (e.g. mosaic stitching) can trigger on_disconnect
        and close the connection even though the page/client reconnects right
        after. Call this before any DB access that may run after a long await.
        """
        if getattr(self, "conn", None) is None:
            self.conn = connect_db(self.database)
        return self.conn