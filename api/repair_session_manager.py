"""
api/repair_session_manager.py
------------------------------
Manages the audit trail for Repair and Merge actions performed on Mosaic sessions.

Structure on disk
-----------------
<temp_root>/
├── actions.json                          ← fast-lookup index (list of all actions)
├── <output_subdir_1>/
│   ├── repair_session.json               ← authoritative record for this action
│   └── *.fits / *.jpg / ...
└── <output_subdir_2>/
    ├── repair_session.json
    └── ...

The index (actions.json) is the quick-lookup layer.
Each per-subdir repair_session.json is the authoritative record.
If actions.json is lost/corrupt it can be rebuilt by scanning subdirs.

Usage
-----
    from api.repair_session_manager import RepairSessionManager

    mgr = RepairSessionManager(temp_root="D:\\Backup\\temp_mosaic_repair")

    # --- Writing (at end of a repair/merge action) ---
    entry = mgr.write_action(
        action="Repair",
        primary_session="DWARF_RAW_..._SESSION_A",
        output_subdir="DWARF_RAW_..._repair_20250428_042124",
        dwarf_id=1,
        backup_id=3,
        status="success",
        secondary_session="DWARF_RAW_..._SESSION_B",   # optional
        tiles_repaired=42,
        tiles_total=48,
    )

    # --- Reading ---
    history = mgr.get_history_for_primary("DWARF_RAW_..._SESSION_A")
    # → list of ActionEntry dicts, most-recent first

    # --- Rebuilding index from subdirs (recovery) ---
    mgr.rebuild_index()
"""

from __future__ import annotations

import json
import os
import portalocker
from datetime import datetime
from pathlib import Path
from typing import Literal


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

ActionStatus = Literal["success", "failed", "partial", "running"]
ActionType   = Literal["Repair", "Merge"]


# ---------------------------------------------------------------------------
# ActionEntry  (plain dict schema — no dataclass so it's JSON-serialisable)
# ---------------------------------------------------------------------------
#
#  id               str   — unique ID, e.g. "repair_20250428_042124"
#  action           str   — "Repair" | "Merge"
#  status           str   — "success" | "failed" | "partial" | "running"
#  timestamp        str   — ISO-8601 with seconds
#  primary_session  str   — basename of the primary session folder
#  secondary_session str | None
#  sessions         list[str] | None  — for Merge with N inputs
#  output_subdir    str   — relative path inside temp_root
#  dwarf_id         int | None
#  backup_id        int | None
#  tiles_repaired   int | None
#  tiles_total      int | None
#  error            str | None


INDEX_FILE    = "actions.json"
ENTRY_FILE    = "repair_session.json"
INDEX_VERSION = 1


class RepairSessionManager:
    """
    Manages the repair/merge action history stored in a temp directory.

    Parameters
    ----------
    temp_root : str | Path
        Root temp directory, e.g. ``D:\\Backup\\temp_mosaic_repair``.
        Created automatically if it does not exist.
    """

    def __init__(self, temp_root: str | Path):
        self.temp_root = Path(temp_root)
        self.temp_root.mkdir(parents=True, exist_ok=True)
        self._index_path = self.temp_root / INDEX_FILE

    # ------------------------------------------------------------------
    # Public write API
    # ------------------------------------------------------------------

    def write_action(
        self,
        action: ActionType,
        primary_session: str,
        output_subdir: str,
        *,
        status: ActionStatus = "success",
        secondary_session: str | None = None,
        sessions: list[str] | None = None,
        dwarf_id: int | None = None,
        backup_id: int | None = None,
        tiles_repaired: int | None = None,
        tiles_total: int | None = None,
        error: str | None = None,
    ) -> dict:
        """
        Record a completed (or failed) repair/merge action.

        Writes both the per-subdir ``repair_session.json`` and updates
        the root ``actions.json`` index atomically (file lock).

        Returns the entry dict that was written.
        """
        timestamp = datetime.now().isoformat(timespec="seconds")
        entry_id = f"{action.lower()}_{primary_session}"

        entry: dict = {
            "id":                entry_id,
            "action":            action,
            "status":            status,
            "timestamp":         timestamp,
            "primary_session":   primary_session,
            "secondary_session": secondary_session,
            "sessions":          sessions,
            "output_subdir":     output_subdir,
            "dwarf_id":          dwarf_id,
            "backup_id":         backup_id,
            "tiles_repaired":    tiles_repaired,
            "tiles_total":       tiles_total,
            "error":             str(error) if error else None,
        }

        # 1. Write authoritative per-subdir file
        subdir_path = self.temp_root / output_subdir
        subdir_path.mkdir(parents=True, exist_ok=True)
        entry_path  = subdir_path / ENTRY_FILE
        entry_path.write_text(json.dumps(entry, indent=2, ensure_ascii=False))

        # 2. Update index (with file lock to avoid concurrent corruption)
        self._update_index(entry)

        return entry

    def update_action_status(
        self,
        entry_id: str,
        status: ActionStatus,
        error: str | None = None,
        tiles_repaired: int | None = None,
    ) -> bool:
        """
        Update the status of an existing action (e.g. mark running → success/failed).

        Returns True if the entry was found and updated, False otherwise.
        """
        index = self._load_index()
        updated = False

        for entry in index["actions"]:
            if entry["id"] == entry_id:
                entry["status"] = status
                if error is not None:
                    entry["error"] = str(error)
                if tiles_repaired is not None:
                    entry["tiles_repaired"] = tiles_repaired
                updated = True

                # Mirror to per-subdir file
                subdir_path = self.temp_root / entry["output_subdir"]
                entry_file  = subdir_path / ENTRY_FILE
                if entry_file.exists():
                    entry_file.write_text(json.dumps(entry, indent=2, ensure_ascii=False))
                break

        if updated:
            self._save_index(index)

        return updated

    def delete_action(self, entry_id: str) -> bool:
        """
        Remove an action entry from the index (does NOT delete the output folder).

        Returns True if found and removed.
        """
        index   = self._load_index()
        before  = len(index["actions"])
        index["actions"] = [e for e in index["actions"] if e["id"] != entry_id]
        changed = len(index["actions"]) < before

        if changed:
            self._save_index(index)

        return changed

    # ------------------------------------------------------------------
    # Public read API
    # ------------------------------------------------------------------

    def get_history_for_primary(self, primary_session: str) -> list[dict]:
        """
        Return all actions whose ``primary_session`` matches, most-recent first.
        """
        index = self._load_index()
        matches = [
            e for e in index["actions"]
            if e.get("primary_session") == primary_session
        ]
        return sorted(matches, key=lambda e: e.get("timestamp", ""), reverse=True)

    def get_all_actions(self) -> list[dict]:
        """Return all recorded actions, most-recent first."""
        index = self._load_index()
        return sorted(
            index["actions"],
            key=lambda e: e.get("timestamp", ""),
            reverse=True,
        )

    def get_action_by_id(self, entry_id: str) -> dict | None:
        """Return a single action by ID, or None if not found."""
        index = self._load_index()
        return next(
            (e for e in index["actions"] if e["id"] == entry_id),
            None,
        )

    def get_output_path(self, entry: dict) -> Path:
        """Return the absolute path to an action's output folder."""
        return self.temp_root / entry["output_subdir"]

    def has_successful_action(self, primary_session: str, action: ActionType | None = None) -> bool:
        """
        Return True if primary_session has at least one successful past action.
        Optionally filter by action type.
        """
        history = self.get_history_for_primary(primary_session)
        for e in history:
            if e.get("status") == "success":
                if action is None or e.get("action") == action:
                    return True
        return False

    # ------------------------------------------------------------------
    # Index recovery
    # ------------------------------------------------------------------

    def rebuild_index(self) -> int:
        """
        Scan all subdirectories for ``repair_session.json`` files and
        rebuild ``actions.json`` from scratch.

        Returns the number of entries recovered.
        """
        recovered = []
        for subdir in sorted(self.temp_root.iterdir()):
            if not subdir.is_dir():
                continue
            entry_file = subdir / ENTRY_FILE
            if entry_file.exists():
                try:
                    entry = json.loads(entry_file.read_text(encoding="utf-8"))
                    # Ensure output_subdir is relative
                    entry["output_subdir"] = subdir.name
                    recovered.append(entry)
                except (json.JSONDecodeError, OSError):
                    pass  # corrupted file — skip

        index = self._empty_index()
        index["actions"] = recovered
        self._save_index(index)
        return len(recovered)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_index(self) -> dict:
        if not self._index_path.exists():
            return self._empty_index()
        try:
            return json.loads(self._index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # Corrupt index — try to rebuild from subdirs
            self.rebuild_index()
            return json.loads(self._index_path.read_text(encoding="utf-8"))

    def _save_index(self, index: dict) -> None:
        self._index_path.write_text(
            json.dumps(index, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _update_index(self, entry: dict) -> None:
        """Append or replace an entry in the index, guarded by a file lock."""
        lock_path = self._index_path.with_suffix(".lock")
        with open(lock_path, "w") as lock_file:
            try:
                portalocker.lock(lock_file, portalocker.LockFlags.EXCLUSIVE)
                index = self._load_index()
                # Replace if same id exists, otherwise append
                ids = [e["id"] for e in index["actions"]]
                if entry["id"] in ids:
                    index["actions"] = [
                        entry if e["id"] == entry["id"] else e
                        for e in index["actions"]
                    ]
                else:
                    index["actions"].append(entry)
                self._save_index(index)
            finally:
                portalocker.unlock(lock_file)

    @staticmethod
    def _empty_index() -> dict:
        return {"version": INDEX_VERSION, "actions": []}


# ---------------------------------------------------------------------------
# Convenience helpers used by the UI layer
# ---------------------------------------------------------------------------

def status_icon(status: str) -> str:
    return {
        "success": "✅",
        "failed":  "❌",
        "partial": "⚠️",
        "running": "⏳",
    }.get(status, "❓")


def status_color(status: str) -> str:
    return {
        "success": "positive",
        "failed":  "negative",
        "partial": "warning",
        "running": "info",
    }.get(status, "grey")


def format_timestamp(ts: str) -> str:
    """Convert ISO timestamp to human-readable, e.g. '2025-04-28 04:21'."""
    try:
        return datetime.fromisoformat(ts).strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return ts or "—"
