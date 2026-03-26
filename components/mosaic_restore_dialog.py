"""
components/mosaic_restore_dialog.py
------------------------------------
Navigates to the Transfer page pre-configured for copying a repaired
Mosaic temp directory back to the Dwarf telescope.
"""

from urllib.parse import urlencode
from nicegui import ui


def open_mosaic_restore_dialog(
    repaired_src_dir: str,
    backup_root: str,
    dwarf_id: int,
    session: str,
    mode: str,
    backup_id: int | None = None,
    back_url: str | None = None,
):
    """
    Navigate to /Transfer in Repair mode with all parameters pre-filled.
    """
    params: dict = {
        "mode":         mode,
        "session":      session,
        "src_override": repaired_src_dir,
        "src_root":     backup_root,
        "back_url":     back_url or "/Mosaic",
    }
    if dwarf_id is not None:
        params["DwarfId"] = dwarf_id
    if backup_id is not None:
        params["BackupId"] = backup_id

    url = "/Transfer?" + urlencode(params)
    ui.navigate.to(url)