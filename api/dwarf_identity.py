"""Which physical Dwarf this is: the last 6 hex digits of its MAC address.

They are printed on the Dwarf (with its MAC address) and end its Bluetooth
name too (e.g. DWARF3_A1B2C3) - the name Dwarfium Lite (Astro Dwarf
Session) keeps as the Dwarf's UID. Stored as Dwarf.ble_id, they let
Dwarfium-Hub tell for sure that a Dwarf of this app and one of Dwarfium
Lite are the same device.

Typed from the label (MAC address or its end), or read from the Dwarf
itself when it is on the network: POST http://<ip>:8082/deviceInfo gives
its name (deviceName, the Bluetooth name) and model (deviceId: the Dwarf
type id itself, 1 = Dwarf II / 2 = Dwarf 3 / 4 = Mini - no offset, confirmed
on a real Dwarf 3 and Mini, see dwarf_python_api's
DEVICE_INFO_HTTP_MODEL_MAP). That answer also holds the Dwarf's and the Wi-Fi's
passwords in clear text: only the name and the model are kept, and the
answer is never logged.
"""
from __future__ import annotations

import re

import requests

DEVICE_INFO_PORT = 8082

_HEX6 = re.compile(r"[0-9A-Fa-f]{6}")
_HEX12 = re.compile(r"[0-9A-Fa-f]{12}")


def normalize_ble_id(text: str | None) -> str:
    """The 6 hex digits (upper case), "" when the text doesn't give them:
    - a Bluetooth name (DWARF3_3C2E2A, DWARF_mini_19A608): what follows
      its last "_", exactly 6 hex digits;
    - the 6 digits themselves ("DDEEFF", "DD:EE:FF");
    - a whole MAC address ("AA:BB:CC:DD:EE:FF", "AA-BB-..", "AABBCCDDEEFF").
    Nothing is guessed from anything else (a 5-digit end stays "")."""
    text = (text or "").strip()
    if "_" in text:
        tail = text.rsplit("_", 1)[1]
        return tail.upper() if _HEX6.fullmatch(tail) else ""
    compact = re.sub(r"[\s:.\-]", "", text)
    if _HEX6.fullmatch(compact):
        return compact.upper()
    if _HEX12.fullmatch(compact):
        return compact[-6:].upper()
    return ""


def ble_id_from_bluetooth_name(text: str | None) -> str:
    """The identifier when the whole text is a Dwarf Bluetooth name
    (DWARF..._XXXXXX), else "" - for the descriptions where the name was
    noted by hand."""
    text = (text or "").strip()
    return normalize_ble_id(text) if re.fullmatch(r"DWARF\w*_[0-9A-Fa-f]{6}", text, flags=re.IGNORECASE) else ""


def identify_through_lite(lite_url: str, ip: str, timeout: float = 40) -> str:
    """Blocking. Asks Dwarfium Lite (Astro Dwarf Session 3.2.4+, at
    lite_url) to flash the ring light of the Dwarf at ip - only it talks to
    a Dwarf's controls. Its answer (ok, busy, no_answer, occupied,
    failed), or "lite_old" when that version can't, "lite_unreachable"."""
    try:
        response = requests.get(f"{lite_url.rstrip('/')}/api/identify", params={"ip": ip}, timeout=timeout)
    except requests.RequestException:
        return "lite_unreachable"
    if response.status_code == 404:
        return "lite_old"
    try:
        return str(response.json().get("result") or "failed")
    except (ValueError, AttributeError):
        return "failed"


def read_device_identity(ip: str, timeout: float = 4) -> dict | None:
    """Blocking. {"name": Bluetooth name, "ble_id": 6 hex digits,
    "type": Dwarf type id or None} of the Dwarf answering at ip, or None
    when it doesn't answer."""
    try:
        response = requests.post(f"http://{ip}:{DEVICE_INFO_PORT}/deviceInfo", timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        return None
    data = payload.get("data") if isinstance(payload, dict) and isinstance(payload.get("data"), dict) else payload
    if not isinstance(data, dict):
        return None
    name = str(data.get("deviceName") or "")
    device_id = data.get("deviceId")
    return {
        "name": name,
        "ble_id": normalize_ble_id(name),
        "type": int(device_id) if str(device_id).isdigit() else None,     # = Dwarf.type, no offset
    }


def lite_ble_id_for_ip(lite_url: str, ip: str, timeout: float = 5) -> str:
    """Blocking. The identifier Dwarfium Lite has for its Dwarf at ip (from
    its Bluetooth name, its UID), "" when none or Lite doesn't answer.
    Preferred to the HTTP deviceName (user-reported Oct 2026: a DWARF 3
    answers DWARF3_3AD246 over HTTP while its Bluetooth name - Lite's UID -
    is DWARF3_3AD946: Dwarfium-Hub saw two Dwarfs)."""
    try:
        response = requests.get(f"{lite_url.rstrip('/')}/api/dwarfs", timeout=timeout)
        devices = response.json().get("devices") or []
    except (requests.RequestException, ValueError, AttributeError):
        return ""
    for device in devices:
        uid = str(device.get("dwarfUid") or "")
        if not uid.startswith("auto:") and str(device.get("ip") or "").strip() == ip.strip():
            return normalize_ble_id(uid)
    return ""

