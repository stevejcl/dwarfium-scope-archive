# components/location_manager.py
"""
Dwarfium Scope Archive — ObservationLocation manager component.

Provides:
  - location_manager_widget()  : full manager (list + add/edit/delete + set default)
                                  used in Settings page
  - location_picker()          : compact inline dropdown + "Manage" button
                                  used in Session Notes dialog and anywhere
                                  a location needs to be selected
  - open_location_manager()    : open the full manager as a floating dialog
                                  callable from any page
"""

from __future__ import annotations

from nicegui import ui
from typing import Optional, Callable

from api.dwarf_location_api import (
    get_all_locations,
    get_location,
    insert_location,
    update_location,
    delete_location,
    set_default_location,
)
from components.i18n import t


# ─────────────────────────────────────────────────────────────────────────────
# i18n keys used in this component
# (add to locales/en.py and locales/fr.py)
# ─────────────────────────────────────────────────────────────────────────────
#
# "loc_title"          : "Observation Locations"       / "Lieux d'observation"
# "loc_add"            : "➕ Add Location"             / "➕ Ajouter un lieu"
# "loc_edit"           : "Edit Location"               / "Modifier le lieu"
# "loc_name"           : "Name"                        / "Nom"
# "loc_latitude"       : "Latitude"                    / "Latitude"
# "loc_longitude"      : "Longitude"                   / "Longitude"
# "loc_address"        : "Address"                     / "Adresse"
# "loc_comment"        : "Comment"                     / "Commentaire"
# "loc_set_default"    : "⭐ Set as default"           / "⭐ Définir par défaut"
# "loc_is_default"     : "⭐ Default"                  / "⭐ Par défaut"
# "loc_open_map"       : "🗺️ Map"                     / "🗺️ Carte"
# "loc_no_locations"   : "No observation locations yet." / "Aucun lieu enregistré."
# "loc_confirm_delete" : "Delete this location?"       / "Supprimer ce lieu ?"
# "loc_saved"          : "Location saved."             / "Lieu enregistré."
# "loc_deleted"        : "Location deleted."           / "Lieu supprimé."
# "loc_name_required"  : "Name is required."           / "Le nom est requis."
# "loc_apply_session"  : "📍 Apply to session"         / "📍 Appliquer à la session"
# "loc_manage"         : "Manage locations"            / "Gérer les lieux"
# "loc_none"           : "(no location)"               / "(aucun lieu)"


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _openstreetmap_url(lat: float, lon: float) -> str:
    return f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}&zoom=14"


def _location_label(loc: dict) -> str:
    label = loc["name"]
    if loc.get("is_default"):
        label = f"⭐ {label}"
    if loc.get("latitude") is not None and loc.get("longitude") is not None:
        label += f"  ({loc['latitude']:.4f}, {loc['longitude']:.4f})"
    return label


def _location_options(locations: list[dict]) -> dict[int, str]:
    """Build {id: label} dict for ui.select."""
    return {loc["id"]: _location_label(loc) for loc in locations}


# ─────────────────────────────────────────────────────────────────────────────
# Edit / Add dialog
# ─────────────────────────────────────────────────────────────────────────────

def _open_edit_dialog(conn,
                      location: Optional[dict],
                      on_saved: Callable) -> None:
    """
    Open a dialog to add or edit an ObservationLocation.
    Calls on_saved() after a successful save.
    """
    is_edit = location is not None
    title = t("loc_edit") if is_edit else t("loc_add")

    with ui.dialog() as dialog, ui.card().classes("w-[480px] gap-3"):
        ui.label(title).classes("text-lg font-bold")

        name_input = ui.input(
            label=t("loc_name"),
            value=location["name"] if is_edit else "",
        ).classes("w-full")

        with ui.row().classes("w-full gap-2"):
            lat_input = ui.number(
                label=t("loc_latitude"),
                value=location.get("latitude") if is_edit else None,
                format="%.6f",
            ).classes("flex-1")
            lon_input = ui.number(
                label=t("loc_longitude"),
                value=location.get("longitude") if is_edit else None,
                format="%.6f",
            ).classes("flex-1")

        address_input = ui.input(
            label=t("loc_address"),
            value=location.get("address", "") if is_edit else "",
        ).classes("w-full")

        comment_input = ui.textarea(
            label=t("loc_comment"),
            value=location.get("comment", "") if is_edit else "",
        ).classes("w-full")

        default_toggle = ui.checkbox(
            t("loc_is_default"),
            value=bool(location.get("is_default")) if is_edit else False,
        )

        # Detect my location via IP geolocation
        with ui.row().classes("w-full items-center gap-2"):
            detect_status = ui.label("").classes("text-xs text-gray-400 flex-1")

            def _detect_location():
                from api.dwarf_location_api import detect_location_by_ip
                detect_status.set_text("⏳ " + t("loc_detecting"))
                ip_lat, ip_lon, city = detect_location_by_ip()
                if ip_lat is not None:
                    lat_input.set_value(round(ip_lat, 6))
                    lon_input.set_value(round(ip_lon, 6))
                    city_label = f" — {city}" if city else ""
                    detect_status.set_text(f"🌐 IP{city_label} ({ip_lat:.4f}, {ip_lon:.4f})")
                    _refresh_map_link()
                else:
                    detect_status.set_text("❌ " + t("loc_detect_failed"))

            ui.button(f"📡 {t('loc_detect')}", on_click=_detect_location)               .props("outlined size=sm")

        # Map link (only when coordinates are already set)
        map_link = ui.html("")
        def _refresh_map_link():
            lat = lat_input.value
            lon = lon_input.value
            if lat is not None and lon is not None:
                url = _openstreetmap_url(float(lat), float(lon))
                map_link.set_content(
                    f'<a href="{url}" target="_blank" '
                    f'class="text-blue-500 underline text-sm">'
                    f'{t("loc_open_map")}</a>'
                )
            else:
                map_link.set_content("")
        lat_input.on("blur", lambda _: _refresh_map_link())
        lon_input.on("blur", lambda _: _refresh_map_link())
        if is_edit:
            _refresh_map_link()

        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button(t("cancel"), on_click=dialog.close).props("flat")

            def _save():
                name = name_input.value.strip()
                if not name:
                    ui.notify(t("loc_name_required"), type="warning")
                    return
                lat = float(lat_input.value) if lat_input.value is not None else None
                lon = float(lon_input.value) if lon_input.value is not None else None
                addr = address_input.value.strip()
                cmt  = comment_input.value.strip()
                dflt = default_toggle.value

                if is_edit:
                    update_location(conn, location["id"], name, lat, lon,
                                    addr, cmt, dflt)
                else:
                    insert_location(conn, name, lat, lon, addr, cmt, dflt)

                ui.notify(t("loc_saved"), type="positive")
                dialog.close()
                on_saved()

            ui.button(t("save"), on_click=_save).props("color=primary")

    dialog.open()


# ─────────────────────────────────────────────────────────────────────────────
# Location row (used inside the manager list)
# ─────────────────────────────────────────────────────────────────────────────

def _render_location_row(conn, loc: dict, container, on_changed: Callable):
    with ui.row().classes("w-full items-center gap-2 py-1 border-b border-gray-100"):

        # Default star
        if loc.get("is_default"):
            ui.label("⭐").classes("text-yellow-400 w-5")
        else:
            ui.button("☆", on_click=lambda l=loc: (
                set_default_location(conn, l["id"]),
                ui.notify(t("loc_is_default"), type="positive"),
                on_changed(),
            )).props("flat dense size=sm").classes("w-5 text-gray-400") \
              .tooltip(t("loc_set_default"))

        # Name + coords
        with ui.column().classes("flex-1 gap-0"):
            ui.label(loc["name"]).classes("font-medium text-sm")
            if loc.get("latitude") is not None:
                coord_str = f"{loc['latitude']:.4f}, {loc['longitude']:.4f}"
                if loc.get("address"):
                    coord_str += f" — {loc['address']}"
                ui.label(coord_str).classes("text-xs text-gray-500")
            elif loc.get("address"):
                ui.label(loc["address"]).classes("text-xs text-gray-500")

        # Map button
        if loc.get("latitude") is not None and loc.get("longitude") is not None:
            url = _openstreetmap_url(loc["latitude"], loc["longitude"])
            ui.link(t("loc_open_map"), url, new_tab=True) \
              .classes("text-xs text-blue-500")

        # Edit
        ui.button("✏️", on_click=lambda l=loc: _open_edit_dialog(
            conn, l, on_changed)
        ).props("flat dense size=sm").tooltip(t("loc_edit"))

        # Delete
        def _confirm_delete(l=loc):
            with ui.dialog() as dlg, ui.card():
                ui.label(t("loc_confirm_delete")).classes("font-medium")
                ui.label(l["name"]).classes("text-gray-600 text-sm")
                with ui.row().classes("gap-2 justify-end mt-3"):
                    ui.button(t("cancel"), on_click=dlg.close).props("flat")
                    def _do_delete(loc_id=l["id"]):
                        delete_location(conn, loc_id)
                        ui.notify(t("loc_deleted"), type="positive")
                        dlg.close()
                        on_changed()
                    ui.button(t("delete"), on_click=_do_delete) \
                      .props("color=negative flat")
            dlg.open()

        ui.button("🗑️", on_click=_confirm_delete) \
          .props("flat dense size=sm").tooltip(t("delete"))


# ─────────────────────────────────────────────────────────────────────────────
# Full manager widget (for Settings page)
# ─────────────────────────────────────────────────────────────────────────────

def location_manager_widget(conn) -> None:
    """
    Render the full ObservationLocation manager inline.
    Intended for the Settings page.
    """
    with ui.card().classes("w-full gap-2 p-4"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label(t("loc_title")).classes("text-lg font-bold")
            ui.button(
                t("loc_add"),
                on_click=lambda: _open_edit_dialog(conn, None, _refresh),
            ).props("color=primary size=sm")

        list_container = ui.column().classes("w-full gap-0")

        def _refresh():
            list_container.clear()
            locs = get_all_locations(conn)
            with list_container:
                if not locs:
                    ui.label(t("loc_no_locations")).classes("text-gray-400 text-sm")
                else:
                    for loc in locs:
                        _render_location_row(conn, loc, list_container, _refresh)

        _refresh()


# ─────────────────────────────────────────────────────────────────────────────
# Floating dialog (opened from Settings or Session Notes)
# ─────────────────────────────────────────────────────────────────────────────

def open_location_manager(conn, on_closed: Optional[Callable] = None) -> None:
    """
    Open the full location manager as a floating dialog.
    Optionally calls on_closed() when the dialog is dismissed.
    """
    with ui.dialog() as dialog, ui.card().classes("w-[560px]"):
        with ui.row().classes("w-full items-center justify-between mb-2"):
            ui.label(t("loc_title")).classes("text-lg font-bold")
            ui.button("✖", on_click=dialog.close).props("flat dense")

        with ui.column().classes("w-full gap-2"):
            with ui.row().classes("w-full justify-end"):
                ui.button(
                    t("loc_add"),
                    on_click=lambda: _open_edit_dialog(conn, None, _refresh),
                ).props("color=primary size=sm")

            list_container = ui.column().classes("w-full gap-0")

            def _refresh():
                list_container.clear()
                locs = get_all_locations(conn)
                with list_container:
                    if not locs:
                        ui.label(t("loc_no_locations")).classes("text-gray-400 text-sm")
                    else:
                        for loc in locs:
                            _render_location_row(conn, loc, list_container, _refresh)

            _refresh()

        ui.button(t("close"), on_click=dialog.close) \
          .props("flat").classes("self-end mt-2")

    if on_closed:
        dialog.on("hide", lambda _: on_closed())

    dialog.open()


# ─────────────────────────────────────────────────────────────────────────────
# Compact picker (for Session Notes dialog and similar)
# ─────────────────────────────────────────────────────────────────────────────

def location_picker(conn,
                    current_location_id: Optional[int] = None,
                    on_change: Optional[Callable[[Optional[int]], None]] = None,
                    show_apply_button: bool = False,
                    on_apply: Optional[Callable[[Optional[int]], None]] = None,
                    ) -> ui.row:
    """
    Render a compact location picker:
      [📍 dropdown ▼]  [Manage]  [Apply to session]  (optional)

    Parameters
    ----------
    conn                 : DB connection
    current_location_id  : pre-selected location id
    on_change            : called with new location_id when selection changes
    show_apply_button    : show an "Apply to session" button
    on_apply             : called with current location_id when Apply is clicked

    Returns the outer ui.row so the caller can reference it.
    """
    locs = get_all_locations(conn)
    options = {None: t("loc_none")}
    options.update(_location_options(locs))

    selected = [current_location_id]

    with ui.row().classes("w-full items-center gap-2 flex-wrap") as row:
        ui.label("📍").classes("text-lg")

        def _on_select(e):
            selected[0] = e.value
            if on_change:
                on_change(e.value)

        picker = ui.select(
            options=options,
            value=current_location_id,
            label=t("notes_location"),
            on_change=_on_select,
        ).classes("flex-1 min-w-[200px]")

        def _open_manager():
            def _on_manager_closed():
                # Refresh picker options after any changes
                new_locs = get_all_locations(conn)
                new_opts = {None: t("loc_none")}
                new_opts.update(_location_options(new_locs))
                picker.set_options(new_opts)
                picker.update()
            open_location_manager(conn, on_closed=_on_manager_closed)

        ui.button(t("loc_manage"), on_click=_open_manager) \
          .props("flat size=sm").classes("text-blue-500")

        if show_apply_button and on_apply:
            ui.button(
                t("loc_apply_session"),
                on_click=lambda: on_apply(selected[0]),
            ).props("flat size=sm color=primary")

    return row