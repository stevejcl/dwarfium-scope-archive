"""Sessions hidden from the Sky Map, and a session's quality score cleared
(user-requested Oct 2026: "10 sessions of the Lion Nebula, only the best
one shown on the map").

Hidden: a SkyMapHidden row per session (entry_type 'backup' / 'manual',
entry_id) - its solution (SessionWCS) is kept, so the next astrometry scan
doesn't solve it again; shown again by deleting the row. Its own table, not
a SessionWCS column: a forced re-solve deletes and rewrites those rows.

Cleared score: SessionQuality's quality_score / score_a / score_c set to
NULL and score_cleared to 1 - its row is kept (it also holds the Storage
Report's sizes). The session then reads "no score", isn't proposed to the
astrometry scan (quality threshold), nor scored again automatically after
a backup drive's analysis (score_cleared): only Explore's Score button
scores it again.
"""
from __future__ import annotations

import sqlite3


def _ensure(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS SkyMapHidden (
            entry_type TEXT NOT NULL,
            entry_id   INTEGER NOT NULL,
            PRIMARY KEY (entry_type, entry_id)
        )
    """)


def hidden_entries(conn: sqlite3.Connection) -> set[tuple[str, int]]:
    _ensure(conn)
    return {(r[0], int(r[1])) for r in conn.execute("SELECT entry_type, entry_id FROM SkyMapHidden")}


def is_hidden(conn: sqlite3.Connection, entry_type: str, entry_id: int) -> bool:
    _ensure(conn)
    return conn.execute(
        "SELECT 1 FROM SkyMapHidden WHERE entry_type = ? AND entry_id = ?", (entry_type, int(entry_id))
    ).fetchone() is not None


def set_hidden(conn: sqlite3.Connection, entry_type: str, entry_id: int, hidden: bool) -> None:
    _ensure(conn)
    if hidden:
        conn.execute("INSERT OR IGNORE INTO SkyMapHidden (entry_type, entry_id) VALUES (?, ?)",
                     (entry_type, int(entry_id)))
    else:
        conn.execute("DELETE FROM SkyMapHidden WHERE entry_type = ? AND entry_id = ?",
                     (entry_type, int(entry_id)))
    conn.commit()


def is_solved(conn: sqlite3.Connection, entry_type: str, entry_id: int) -> bool:
    """On the Sky Map at all: its astrometry solved."""
    try:
        return conn.execute(
            "SELECT 1 FROM SessionWCS WHERE entry_type = ? AND entry_id = ? LIMIT 1", (entry_type, int(entry_id))
        ).fetchone() is not None
    except sqlite3.OperationalError:     # no astrometry solved yet: no table
        return False


def clear_quality_score(conn: sqlite3.Connection, backup_entry_id: int) -> bool:
    """True when a score was cleared."""
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(SessionQuality)")}
        if not cols:                     # no SessionQuality table yet
            return False
        if "score_cleared" not in cols:
            conn.execute("ALTER TABLE SessionQuality ADD COLUMN score_cleared INTEGER")
        cur = conn.execute(
            """UPDATE SessionQuality SET quality_score = NULL, score_a = NULL, score_c = NULL,
                                         score_cleared = 1
               WHERE backup_entry_id = ? AND quality_score IS NOT NULL""",
            (int(backup_entry_id),),
        )
    except sqlite3.OperationalError:
        return False
    conn.commit()
    return cur.rowcount > 0
