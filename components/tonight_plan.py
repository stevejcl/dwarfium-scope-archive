"""Tonight's plan: targets to send to a Dwarf through Astro Dwarf Session
(user-requested Oct 2026).

A page creates one TonightPlan, puts its panel() where the list should
show, and calls choose(target) from a target's button: a small dialog
offers "Plan this target tonight" (Astro Dwarf Session's /plan-target page
with that target alone) or "Add to tonight's plan" - a list of up to
MAX_TARGETS targets, each with its window tonight, sent together with
"Plan these targets" (the targets chained over the night there). When the
list is full, adding offers to replace one of them.

The list is kept by the app (app.storage.general), not by the page: it
survives a page change and any page using this component shares it. It
belongs to one night and site; adding a target for another night or site
offers to start a new list.

A target without its window (e.g. from a page that doesn't compute
visibility) gets it here, for the night and site given (see window_for()).
Astro Dwarf Session's address comes from its hellos (api/peer.py).
"""
from __future__ import annotations

import json
import webbrowser
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from typing import Optional
from urllib.parse import urlencode

from nicegui import app, run, ui

from api.peer import peer_url
from components.i18n import t

MAX_TARGETS = 5
_STORE_KEY = "tonight_plan"


@dataclass
class PlanTarget:
    name: str
    catalog_id: str
    ra_deg: float
    dec_deg: float
    start_utc: Optional[str] = None   # ISO "YYYY-MM-DDTHH:MM:SSZ", window above the minimum altitude
    end_utc: Optional[str] = None


def iso_utc(d: Optional[datetime]) -> Optional[str]:
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if d else None


# Night contexts (dark window, Moon) by site and night: the costly part,
# computed once; a target's visibility in it takes a few milliseconds.
_night_cache: dict = {}


def tonight() -> date:
    """Tonight's date as Recommended tonight takes it by default (today):
    the same list key from every page."""
    return date.today()


def visibility_for(ra_deg: float, dec_deg: float, location: dict, night: date):
    """(window start, window end, max altitude) of a target that night at
    that site: its stretch above the minimum altitude around its best time
    in the dark window (Recommended tonight's computation). Blocking."""
    from pages.recommend_tonight import compute_night_context, compute_visibility_fast
    key = (round(float(location["lat"]), 4), round(float(location["lon"]), 4), night)
    if key not in _night_cache:
        _night_cache.clear()   # one night / site at a time is enough
        _night_cache[key] = compute_night_context(location, night)
    vis = compute_visibility_fast(ra_deg, dec_deg, _night_cache[key])
    return iso_utc(vis.window_start_utc), iso_utc(vis.window_end_utc), vis.max_altitude_deg


def window_for(ra_deg: float, dec_deg: float, location: dict, night: date) -> tuple[Optional[str], Optional[str]]:
    start, end, _max_alt = visibility_for(ra_deg, dec_deg, location, night)
    return start, end


def _hhmm(iso: Optional[str]) -> str:
    if not iso:
        return "—"
    return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).astimezone().strftime("%H:%M")


class TonightPlan:
    def __init__(self):
        self._panel = None

    # ── stored list ────────────────────────────────────────────────────────
    @staticmethod
    def _load() -> dict:
        data = app.storage.general.get(_STORE_KEY) or {}
        return {"night": data.get("night"), "site": data.get("site") or {}, "targets": list(data.get("targets") or [])}

    def _save(self, data: dict) -> None:
        app.storage.general[_STORE_KEY] = data
        if self._panel:
            self._panel.refresh()

    # ── sending ────────────────────────────────────────────────────────────
    @staticmethod
    def _open(targets: list[dict], site: dict) -> None:
        base = peer_url()
        if not base:
            ui.notify(t("tonight_ads_not_running"), type="warning")
            return
        params: dict = {}
        if len(targets) == 1:
            tg = targets[0]
            params.update(name=tg["name"], id=tg["catalog_id"], ra=f"{tg['ra_deg'] / 15:.6f}", dec=f"{tg['dec_deg']:.6f}")
            if tg.get("start_utc") and tg.get("end_utc"):
                params.update(start=tg["start_utc"], end=tg["end_utc"])
        else:
            params["targets"] = json.dumps([
                {"name": tg["name"], "id": tg["catalog_id"], "ra": round(tg["ra_deg"] / 15, 6), "dec": round(tg["dec_deg"], 6),
                 "start": tg.get("start_utc"), "end": tg.get("end_utc")}
                for tg in targets
            ], separators=(",", ":"))
        if site.get("lat") is not None and site.get("lon") is not None:
            params.update(site=site.get("name", ""), lat=site["lat"], lon=site["lon"])
        webbrowser.open(f"{base}/plan-target?{urlencode(params)}")

    # ── actions ────────────────────────────────────────────────────────────
    async def choose_computed(self, target: PlanTarget, location: Optional[dict], night: Optional[date] = None) -> None:
        """choose() for a page that doesn't compute visibility (Explore):
        the window tonight at that site is computed first, in a worker
        thread; said so when the target never gets high enough."""
        if not location or location.get("lat") is None or location.get("lon") is None:
            ui.notify(t("tonight_plan_no_location"), type="warning")
            return
        night = night or tonight()
        note = ui.notification(t("tonight_plan_computing"), spinner=True, timeout=None)
        try:
            start, end, max_alt = await run.io_bound(visibility_for, target.ra_deg, target.dec_deg, location, night)
        except Exception as e:
            ui.notify(t("error_generic", error=str(e)), type="negative")
            return
        finally:
            note.dismiss()
        target.start_utc, target.end_utc = start, end
        self.choose(target, location, night, max_alt=max_alt)

    def choose(self, target: PlanTarget, location: dict, night: date, max_alt: Optional[float] = None) -> None:
        """The target button: plan it alone, or add it to the list."""
        site = {"name": location.get("name", ""), "lat": location.get("lat"), "lon": location.get("lon")}
        with ui.dialog() as dialog, ui.card().classes("min-w-[320px]"):
            ui.label(target.name).classes("text-lg font-semibold")
            alt = f" (max {max_alt:.0f}°)" if max_alt is not None else ""
            if target.start_utc and target.end_utc:
                ui.label(f"{t('tonight_plan_window')}: {_hhmm(target.start_utc)} – {_hhmm(target.end_utc)}{alt}"
                         f" · {site['name']}").classes("text-sm text-gray-500")
            else:
                ui.label(t("tonight_plan_not_visible", alt=alt.strip(" ()"), site=site["name"])).classes("text-sm text-amber-600")
            with ui.column().classes("w-full gap-2 mt-2"):
                ui.button(t("tonight_plan_this"), icon="send",
                          on_click=lambda: (dialog.close(), self._open([asdict(target)], site))).classes("w-full")
                ui.button(t("tonight_plan_add"), icon="playlist_add",
                          on_click=lambda: (dialog.close(), self.add(target, site, night))).props("outline").classes("w-full")
                ui.button(t("cancel"), on_click=dialog.close).props("flat").classes("w-full")
        dialog.open()

    def add(self, target: PlanTarget, site: dict, night: date) -> None:
        data = self._load()
        same_night = data["night"] == night.isoformat() and data["site"].get("name") == site.get("name")
        if data["targets"] and not same_night:
            with ui.dialog() as dialog, ui.card():
                ui.label(t("tonight_plan_other_night", night=data["night"] or "?", site=data["site"].get("name", "?")))
                with ui.row().classes("justify-end w-full"):
                    ui.button(t("tonight_plan_new_list"), on_click=lambda: (dialog.close(), self._save(
                        {"night": night.isoformat(), "site": site, "targets": [asdict(target)]})))
                    ui.button(t("cancel"), on_click=dialog.close).props("flat")
            dialog.open()
            return
        data["night"], data["site"] = night.isoformat(), site
        if any(tg["catalog_id"] == target.catalog_id for tg in data["targets"]):
            ui.notify(t("tonight_plan_already", name=target.name))
            return
        if len(data["targets"]) < MAX_TARGETS:
            data["targets"].append(asdict(target))
            self._save(data)
            if len(data["targets"]) == MAX_TARGETS:
                ui.notify(t("tonight_plan_full_send", n=MAX_TARGETS), type="info")
            return
        # Full: replace one of them
        with ui.dialog() as dialog, ui.card().classes("min-w-[340px]"):
            ui.label(t("tonight_plan_replace", n=MAX_TARGETS, name=target.name)).classes("font-medium")
            for i, tg in enumerate(data["targets"]):
                def replace(i=i):
                    data["targets"][i] = asdict(target)
                    self._save(data)
                    dialog.close()
                ui.button(f"{tg['name']}  ({_hhmm(tg.get('start_utc'))} – {_hhmm(tg.get('end_utc'))})",
                          icon="swap_horiz", on_click=replace).props("flat no-caps align=left").classes("w-full")
            ui.button(t("cancel"), on_click=dialog.close).props("flat")
        dialog.open()

    def remove(self, catalog_id: str) -> None:
        data = self._load()
        data["targets"] = [tg for tg in data["targets"] if tg["catalog_id"] != catalog_id]
        self._save(data)

    def clear(self) -> None:
        self._save({"night": None, "site": {}, "targets": []})

    # ── list ───────────────────────────────────────────────────────────────
    def panel(self) -> None:
        """The list, floating at the bottom of the window so it stays in
        view while scrolling the targets (refreshed on every change); the
        page leaves room for it under its content."""
        self._panel = ui.refreshable(self._render)
        self._panel()

    def _render(self) -> None:
        data = self._load()
        targets = data["targets"]
        if not targets:
            return
        with ui.card().classes("fixed bottom-3 left-1/2 -translate-x-1/2 z-50 w-[min(94vw,760px)] p-3 shadow-xl "
                               "max-h-[45vh] overflow-auto"):
            with ui.row().classes("items-center justify-between w-full"):
                ui.label(f"📅 {t('tonight_plan_title')} ({len(targets)}/{MAX_TARGETS})"
                         f" · {data['night'] or ''} · {data['site'].get('name', '')}").classes("font-semibold")
                with ui.row().classes("gap-2"):
                    ui.button(t("tonight_plan_send"), icon="send",
                              on_click=lambda: self._open(self._load()["targets"], self._load()["site"])).props("dense")
                    ui.button(t("tonight_plan_clear"), icon="delete_sweep", on_click=self.clear).props("dense flat")
            if len(targets) == MAX_TARGETS:
                ui.label(t("tonight_plan_full_send", n=MAX_TARGETS)).classes("text-sm text-amber-600")
            for tg in targets:
                with ui.row().classes("items-center gap-3 w-full"):
                    ui.label(tg["name"]).classes("min-w-[140px]")
                    ui.label(f"{_hhmm(tg.get('start_utc'))} – {_hhmm(tg.get('end_utc'))}").classes("text-sm text-gray-500")
                    ui.button(icon="close", on_click=lambda cid=tg["catalog_id"]: self.remove(cid)) \
                        .props("flat dense round size=sm").tooltip(t("tonight_plan_remove"))
