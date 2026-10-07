"""Session IP of a Dwarf (user-requested Oct 2026): a second FTP IP, next
to the one in the Dwarf table, for a Dwarf also reached from a remote
site (Astro Dwarf Session there, the Dwarf through Tailscale).

Kept in NiceGUI's general storage per DwarfId (never in the database),
set on the Dwarf Configuration page - by hand, or from the IP Astro Dwarf
Session gives in its link (DwarfIp). The pages using FTP (Dwarf
Configuration, Transfer, ImportSession) try the IPs they know and use
the one answering: the link's own, then the configured one, then the
session one."""
from __future__ import annotations

import socket

from nicegui import app

FTP_PORT = 21
_PROBE_TIMEOUT_S = 3
_STORAGE_KEY = "dwarf_session_ip"


def get_session_ip(dwarf_id) -> str:
    if not dwarf_id:
        return ""
    try:
        return (app.storage.general.get(_STORAGE_KEY, {}) or {}).get(str(dwarf_id), "") or ""
    except Exception:
        return ""


def set_session_ip(dwarf_id, ip: str) -> None:
    """Saves (or clears, with "") this Dwarf's session IP."""
    if not dwarf_id:
        return
    ips = dict(app.storage.general.get(_STORAGE_KEY, {}) or {})
    ip = (ip or "").strip()
    if ip:
        ips[str(dwarf_id)] = ip
    else:
        ips.pop(str(dwarf_id), None)
    app.storage.general[_STORAGE_KEY] = ips


def ftp_reachable(ip: str) -> bool:
    """Something answers on the FTP port (a few seconds at most)."""
    try:
        with socket.create_connection((ip, FTP_PORT), timeout=_PROBE_TIMEOUT_S):
            return True
    except OSError:
        return False


def pick_ftp_ip(dwarf_id, configured: str, preferred: str = "") -> str:
    """Blocking: the IP to use for this Dwarf's FTP - the first answering
    of `preferred` (the link's DwarfIp), `configured` (Dwarf table) and the
    session IP. With a single one known it's used without a test; when none
    answers, the first one (the page then says FTP isn't connected)."""
    candidates = []
    for ip in (preferred, configured, get_session_ip(dwarf_id)):
        ip = (ip or "").strip()
        if ip and ip not in candidates:
            candidates.append(ip)
    if len(candidates) <= 1:
        return candidates[0] if candidates else ""
    for ip in candidates:
        if ftp_reachable(ip):
            return ip
    return candidates[0]
