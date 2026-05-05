# components/sky_search_dialog.py
"""
Dwarfium Scope Archive — Sky Position Search Dialog.

Opens a dialog that lets the user:
  1. Pick an object from the DSO catalog (filtered by constellation / type / name)
  2. Search Simbad online for objects not in the local catalog
  3. Choose a search radius via a slider

Then calls on_result(ra_deg, dec_deg, label, radius_deg) with the chosen
coordinates so the caller can filter sessions spatially.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Callable, Optional

from nicegui import ui, run

from components.i18n import t
from api.dwarf_backup_db_api import count_sessions_by_sky_position
from api.dwarf_backup_db import DB_NAME, connect_db

# ── DSO catalog ───────────────────────────────────────────────────────────────
_dso_cache: Optional[list[dict]] = None

def _load_dso_catalog() -> list[dict]:
    """
    Load the DSO catalog, preferring the preprocessed version (with ra_deg/dec_deg).
    If only the raw catalog is available, convert ra/dec on the fly.
    """
    global _dso_cache
    if _dso_cache is not None:
        return _dso_cache

    for path in [
        Path("db") / "dso_sky_search_catalog.json",
        Path("db") / "dso_catalog.json",
    ]:
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)

        # If entries already have ra_deg/dec_deg, use as-is
        if data and data[0].get("ra_deg") is not None:
            _dso_cache = data
            return _dso_cache

        # Raw catalog — convert ra/dec strings to degrees on the fly
        converted = []
        for entry in data:
            ra_str  = entry.get("ra",  "")
            dec_str = entry.get("dec", "")
            if not ra_str or not dec_str:
                continue
            try:
                # Parse HMS ra (e.g. "2h 51m 10.59s") → degrees
                parts = ra_str.replace("h", " ").replace("m", " ").replace("s", "").split()
                h, m, s = float(parts[0]), float(parts[1]), float(parts[2])
                ra_deg = (h + m / 60 + s / 3600) * 15.0

                # Parse DMS dec (e.g. "+60° 24' 08.9"") → degrees
                dec_clean = dec_str.replace("°", " ").replace("'", " ").replace('"', "").replace("′", " ").replace("″", " ")
                sign = -1 if dec_clean.strip().startswith("-") else 1
                dparts = dec_clean.strip().lstrip("+-").split()
                d, dm, ds = float(dparts[0]), float(dparts[1]), float(dparts[2])
                dec_deg = sign * (d + dm / 60 + ds / 3600)

                e2 = dict(entry)
                e2["ra_deg"]  = ra_deg
                e2["dec_deg"] = dec_deg
                converted.append(e2)
            except Exception:
                pass  # skip malformed entries

        _dso_cache = converted
        return _dso_cache

    _dso_cache = []
    return _dso_cache


# ── Coordinate formatting ─────────────────────────────────────────────────────
def _ra_to_hms(ra_deg: float) -> str:
    """Convert RA in degrees to h m s string (e.g. 10.685° → 0h 42m 44s)."""
    h_total = ra_deg / 15.0
    h = int(h_total)
    m_total = (h_total - h) * 60
    m = int(m_total)
    s = int((m_total - m) * 60)
    return f"{h}h {m:02d}m {s:02d}s"

def _dec_to_dms(dec_deg: float) -> str:
    """Convert Dec in degrees to ±d° m′ s″ string (e.g. 41.269° → +41° 16′ 8″)."""
    sign = "+" if dec_deg >= 0 else "-"
    d = int(abs(dec_deg))
    m_total = (abs(dec_deg) - d) * 60
    m = int(m_total)
    s = int((m_total - m) * 60)
    return f"{sign}{d}° {m:02d}′ {s:02d}″"


# ── Angular distance (fast, no astropy needed for catalog browsing) ────────────
def _angular_sep_deg(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    """Haversine angular separation in degrees."""
    r = math.pi / 180
    d_dec = (dec2 - dec1) * r
    d_ra  = (ra2  - ra1)  * r
    a = math.sin(d_dec / 2) ** 2 + \
        math.cos(dec1 * r) * math.cos(dec2 * r) * math.sin(d_ra / 2) ** 2
    return 2 * math.asin(math.sqrt(min(a, 1.0))) / r


# ── Simbad query (run in thread pool to avoid blocking UI) ────────────────────
def _simbad_resolve(name: str) -> Optional[dict]:
    """
    Resolve an object name via Simbad. Returns dict with ra_deg, dec_deg, label
    or None on failure.
    Uses ra(d)/dec(d) votable fields to get coordinates directly in degrees.
    """
    try:
        from astroquery.simbad import Simbad
        custom_simbad = Simbad()
        custom_simbad.reset_votable_fields()
        custom_simbad.add_votable_fields("ra(d)", "dec(d)")
        result = custom_simbad.query_object(name)
        if result is None or len(result) == 0:
            return None
        # Columns are named RA_d and DEC_d when using ra(d)/dec(d) fields
        ra_col  = next((c for c in result.colnames if c.upper().startswith("RA")),  None)
        dec_col = next((c for c in result.colnames if c.upper().startswith("DEC")), None)
        if ra_col is None or dec_col is None:
            print(f"[Simbad] unexpected columns: {result.colnames}")
            return None
        ra_deg  = float(result[ra_col][0])
        dec_deg = float(result[dec_col][0])
        return {
            "label":   name,
            "ra_deg":  ra_deg,
            "dec_deg": dec_deg,
        }
    except Exception as e:
        print(f"[Simbad] query failed for '{name}': {e}")
        return None


# ── Public entry point ────────────────────────────────────────────────────────
def open_sky_search_dialog(
    on_result: Callable[[float, float, str, float], None],
    conn=None,
) -> None:
    """
    Open the sky-position search dialog.

    on_result(ra_deg, dec_deg, label, radius_deg) is called when the user
    clicks "Show sessions". The caller is responsible for filtering sessions.
    conn: optional DB connection — if provided, used directly instead of
          opening a new one (avoids slot-stack issues in NiceGUI).
    """
    catalog = _load_dso_catalog()

    # Collect unique constellations and types for filter dropdowns
    constellations = sorted({e.get("constellation", "") for e in catalog if e.get("constellation")})
    types          = sorted({e.get("type", "")          for e in catalog if e.get("type")})

    # State
    selected_ra:   Optional[float] = None
    selected_dec:  Optional[float] = None
    selected_label: str = ""
    found_count:    int = 0

    with ui.dialog() as dialog, ui.card().classes("w-[580px] gap-3"):

        # ── Header ────────────────────────────────────────────────────────────
        ui.label(f"🔭 {t('sky_search_title')}").classes("text-lg font-bold")

        # ── Mode toggle ───────────────────────────────────────────────────────
        mode = ui.toggle(
            {0: f"📚 {t('sky_search_catalog')}", 1: f"🌐 {t('sky_search_online')}"},
            value=0,
        ).classes("w-full")

        # ── CATALOG panel ─────────────────────────────────────────────────────
        with ui.column().classes("w-full gap-2").bind_visibility_from(mode, "value", lambda v: v == 0) as cat_panel:

            with ui.row().classes("w-full gap-2 flex-wrap"):
                const_filter = ui.select(
                    options=[""] + constellations,
                    value="",
                    label=t("sky_search_constellation"),
                ).classes("flex-1 min-w-[140px]")
                type_filter = ui.select(
                    options=[""] + types,
                    value="",
                    label=t("sky_search_type"),
                ).classes("flex-1 min-w-[120px]")
                name_filter = ui.input(
                    placeholder=t("sky_search_name"),
                ).classes("flex-1 min-w-[140px]")

            # Filtered catalog list
            cat_list_container = ui.column().classes("w-full max-h-48 overflow-y-auto border rounded p-1 gap-0")

            def _rebuild_catalog_list():
                cat_list_container.clear()
                cf = const_filter.value or ""
                tf = type_filter.value  or ""
                nf = name_filter.value.lower() if name_filter.value else ""
                filtered = [
                    e for e in catalog
                    if (not cf or e.get("constellation") == cf)
                    and (not tf or e.get("type") == tf)
                    and (not nf or nf in (e.get("displayName") or e.get("designation") or "").lower()
                         or nf in (e.get("alternateNames") or "").lower())
                    and e.get("ra_deg") is not None
                    and e.get("dec_deg") is not None
                ][:200]  # cap for performance

                with cat_list_container:
                    if not filtered:
                        ui.label(t("no_data")).classes("text-gray-400 text-sm p-2")
                    for entry in filtered:
                        label = entry.get("displayName") or entry.get("designation") or "?"
                        sub   = f"{entry.get('type','')}  {entry.get('constellation','')}"
                        with ui.row().classes("w-full items-center py-1 px-2 hover:bg-gray-100 cursor-pointer rounded gap-2") \
                                .on("click", lambda _, e=entry, l=label: _select_catalog_entry(e, l)):
                            with ui.column().classes("flex-1 gap-0"):
                                ui.label(label).classes("text-sm font-medium")
                                ui.label(sub).classes("text-xs text-gray-400")

            def _select_catalog_entry(entry: dict, label: str):
                nonlocal selected_ra, selected_dec, selected_label
                selected_ra    = entry["ra_deg"]
                selected_dec   = entry["dec_deg"]
                selected_label = label
                selection_label.set_text(f"✅ {label}  (RA {_ra_to_hms(selected_ra)}  Dec {_dec_to_dms(selected_dec)})")
                _update_count()

            const_filter.on("update:model-value", lambda _: _rebuild_catalog_list())
            type_filter.on("update:model-value",  lambda _: _rebuild_catalog_list())
            name_filter.on("update:model-value",  lambda _: _rebuild_catalog_list())
            _rebuild_catalog_list()

        # ── SIMBAD panel ──────────────────────────────────────────────────────
        with ui.column().classes("w-full gap-2").bind_visibility_from(mode, "value", lambda v: v == 1) as sim_panel:

            with ui.row().classes("w-full items-center gap-2"):
                simbad_input = ui.input(
                    placeholder=t("sky_search_simbad_ph"),
                ).classes("flex-1")
                simbad_btn   = ui.button(t("search")).props("outlined size=sm")
                simbad_spinner = ui.spinner().classes("hidden")

            simbad_result = ui.label("").classes("text-sm text-gray-500")

            async def _simbad_search():
                nonlocal selected_ra, selected_dec, selected_label
                name = simbad_input.value.strip()
                if not name:
                    return
                simbad_spinner.classes(remove="hidden")
                simbad_btn.props("disabled")
                simbad_result.set_text(f"⏳ {t('loading')}…")
                result = await run.io_bound(_simbad_resolve, name)
                simbad_spinner.classes("hidden")
                simbad_btn.props(remove="disabled")
                if result:
                    selected_ra    = result["ra_deg"]
                    selected_dec   = result["dec_deg"]
                    selected_label = result["label"]
                    simbad_result.set_text(
                        f"✅ {result['label']}  (RA {_ra_to_hms(selected_ra)}  Dec {_dec_to_dms(selected_dec)})"
                    )
                    selection_label.set_text(simbad_result.text)
                    _update_count()
                else:
                    selected_ra = selected_dec = None
                    simbad_result.set_text(f"❌ {t('sky_search_not_found')}")
                    selection_label.set_text("")

            simbad_btn.on("click", _simbad_search)
            simbad_input.on("keydown.enter", _simbad_search)

        # ── Selection summary ─────────────────────────────────────────────────
        selection_label = ui.label("").classes("text-sm text-blue-600 font-medium")

        # ── Radius slider ─────────────────────────────────────────────────────
        ui.separator()
        with ui.row().classes("w-full items-center gap-3"):
            ui.label(t("sky_search_radius")).classes("text-sm font-semibold w-20")
            radius_slider = ui.slider(min=0.5, max=15.0, step=0.5, value=3.0).classes("flex-1")
            radius_label  = ui.label("3.0°").classes("text-sm font-medium w-12 text-right")

        # ── Result count ──────────────────────────────────────────────────────
        ui.separator()
        count_label = ui.label("").classes("text-sm text-gray-500")

        def _update_count():
            nonlocal found_count
            if selected_ra is None or selected_dec is None:
                count_label.set_text("")
                show_btn.props("disabled")
                return
            try:
                _conn = conn
                if _conn is None:
                    _conn = connect_db(DB_NAME)
                r = radius_slider.value
                n = count_sessions_by_sky_position(_conn, selected_ra, selected_dec, r)
                found_count = n
                if n > 0:
                    count_label.set_text(f"✅ {t('sky_search_found').format(n=n, r=r, label=selected_label)}")
                    show_btn.props(remove="disabled")
                else:
                    count_label.set_text(f"❌ {t('sky_search_none').format(r=r, label=selected_label)}")
                    show_btn.props("disabled")
            except Exception as e:
                count_label.set_text(f"⚠ {e}")

        def _on_radius_change(e):
            radius_label.set_text(f"{e.args:.1f}°")
            _update_count()

        radius_slider.on("update:model-value", _on_radius_change)

        # ── Buttons ───────────────────────────────────────────────────────────
        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button(t("cancel"), on_click=dialog.close).props("flat")
            show_btn = ui.button(
                t("sky_search_show"),
                on_click=lambda: _confirm(),
            ).props("color=primary disabled")

        def _confirm():
            if selected_ra is None or selected_dec is None:
                return
            dialog.close()
            on_result(selected_ra, selected_dec, selected_label, radius_slider.value)

    dialog.open()