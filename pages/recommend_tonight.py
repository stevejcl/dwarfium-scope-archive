"""
pages/recommend_tonight.py — "What to shoot tonight!" for Dwarfium Scope Archive.

Cross-references the DSO catalog, session and mosaic history, the
observation location (ObservationLocation) and the selected date to
suggest observable targets for tonight, classified as
NEW / INCOMPLETE / WELL_COVERED.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional

from nicegui import ui, run

from components.i18n import t
from components.menu import menu
from components.db_page_mixin import DbPageMixin
from api.dwarf_backup_db import DB_NAME, connect_db, close_db

from api.dso_matching import (
    load_dso_catalog,
    build_catalog_name_index,
    resolve_catalog_id,
    angular_sep_deg,
)
# ── Config / Thresholds ──────────────────────────────────────────────────────────

MIN_ALTITUDE_DEG = 25
MIN_MINUTES_ABOVE = 30
MIN_INTEGRATION_MINUTES = 60
MIN_PANEL_INTEGRATION_MINUTES = 20
MOON_SEPARATION_WARN_DEG = 30
SAMPLES_PER_NIGHT = 48

COMBINABLE_FOV_DEG = 2.0  # safe margin under the ~3° Dwarf TELE FOV

MAX_MATCH_SEPARATION_DEG = 3.0  # max angular distance for a "nearest object" match


class Category(str, Enum):
    NEW = "NEW"
    INCOMPLETE = "INCOMPLETE"
    WELL_COVERED = "WELL_COVERED"


# ── Data structures ─────────────────────────────────────────────────────────

@dataclass
class VisibilityResult:
    max_altitude_deg: float
    minutes_above_threshold: float
    best_time_utc: datetime
    moon_separation_deg: float
    moon_phase_pct: float


@dataclass
class SessionInfo:
    session_count: int
    total_integration_minutes: float
    filters_used: list[str]
    last_session_date: Optional[date]


@dataclass
class MosaicInfo:
    project_id: int
    session_count: int
    panel_integration_minutes: dict[str, float]

    @property
    def weakest_panel_minutes(self) -> float:
        if not self.panel_integration_minutes:
            return 0.0
        return min(self.panel_integration_minutes.values())


@dataclass
class TargetRecommendation:
    catalog_id: str
    display_name: str
    ra_deg: float
    dec_deg: float
    object_type: str
    magnitude: Optional[float]
    category: Category
    score: float
    visibility: VisibilityResult
    session_info: Optional[SessionInfo] = None
    mosaic_info: Optional[MosaicInfo] = None
    detail: str = ""

# ── Catalog matching helpers ─────────────────────────────────────────────────
# Not every session in the DB is linked to a DsoCatalog entry via
# AstroObject.dso_id (many were imported/scanned before catalog assignment,
# or the target was never manually identified). To still credit that
# integration time toward the right tonight's-target recommendation, we try,
# in order:
#   1. AstroObject.dso_id -> DsoCatalog.designation (already linked)
#   2. Name match: AstroObject.name / description against catalog names
#   3. Nearest catalog object by RA/Dec, within a tolerance


# ── Wide-field clustering ─────────────────────────────────────────────────────
# Two catalog objects close enough to fit in a single wide-field frame can be
# shot together in one session. We surface this as a bonus hint attached to
# the top-scoring object of each cluster rather than a separate entity, to
# keep the results list simple.

def _cluster_nearby_targets(
    results: list[TargetRecommendation], max_sep_deg: float = COMBINABLE_FOV_DEG
) -> list[TargetRecommendation]:
    """
    Group recommendations that are close enough on sky to be captured in a
    single wide-field frame. Uses the fast haversine separation (not
    astropy SkyCoord) and a declination-sorted sweep to avoid O(n²) full
    pairwise comparisons — with 200+ results, naive pairwise astropy
    comparison was taking 30+ seconds.
    """
    from api.dso_matching import angular_sep_deg_fast

    # Sort by score descending so each cluster anchors on its best member,
    # but keep a separate dec-sorted view for fast neighbor lookup.
    by_score = sorted(results, key=lambda r: r.score, reverse=True)
    by_dec = sorted(results, key=lambda r: r.dec_deg)
    decs = [r.dec_deg for r in by_dec]

    used_ids: set[str] = set()
    clustered: list[TargetRecommendation] = []

    import bisect
    for anchor in by_score:
        if anchor.catalog_id in used_ids:
            continue

        lo = bisect.bisect_left(decs, anchor.dec_deg - max_sep_deg)
        hi = bisect.bisect_right(decs, anchor.dec_deg + max_sep_deg)

        companions = []
        for other in by_dec[lo:hi]:
            if other.catalog_id == anchor.catalog_id or other.catalog_id in used_ids:
                continue
            if other.category == Category.WELL_COVERED:
                continue
            sep = angular_sep_deg_fast(anchor.ra_deg, anchor.dec_deg, other.ra_deg, other.dec_deg)
            if sep <= max_sep_deg:
                companions.append((other, sep))

        used_ids.add(anchor.catalog_id)

        if companions:
            names = ", ".join(f"{c.display_name} ({sep:.1f}°)" for c, sep in companions)
            anchor.detail = f"{anchor.detail} — {t('tonight_combinable_with')}: {names}"
            for c, _ in companions:
                used_ids.add(c.catalog_id)

        clustered.append(anchor)

    return clustered


# ── Access to existing data ───────────────────────────────────────────────────
# ── Catalog types excluded from recommendations ──────────────────────────────
# Simple/double stars aren't relevant "shoot tonight" targets and make up a
# large chunk of the catalog → filter them out early to drastically reduce
# the number of skyfield calls.

EXCLUDED_CATALOG_TYPES = {
    "star", "double_star", "double star", "carbon_star", "carbon star",
    "variable_star", "variable star",
}


def load_catalog(exclude_stars: bool = True) -> list[dict]:
    """Return the shared DSO catalog, normalized to the fields this page
    uses, with star-type entries excluded by default (not relevant for
    tonight's-target recommendations and they bloat the catalog size)."""
    raw = load_dso_catalog()
    catalog = []
    for entry in raw:
        if entry.get("ra_deg") is None or entry.get("dec_deg") is None:
            continue
        obj_type = (entry.get("type") or "").strip().lower()
        if exclude_stars and obj_type in EXCLUDED_CATALOG_TYPES:
            continue
        catalog.append({
            "id": entry.get("designation") or entry.get("displayName"),
            "name": entry.get("displayName") or entry.get("designation"),
            "ra_deg": entry["ra_deg"],
            "dec_deg": entry["dec_deg"],
            "type": entry.get("type", "?"),
            "magnitude": entry.get("magnitude"),
        })
    return catalog
    
def get_all_locations_simple(conn) -> list[dict]:
    from api.dwarf_location_api import get_all_locations as _get_all_locations
    locs = _get_all_locations(conn)
    return [
        {
            "name": l["name"],
            "lat": l["latitude"],
            "lon": l["longitude"],
            "elevation_m": 0,
            "is_default": bool(l.get("is_default")),
        }
        for l in locs
        if l.get("latitude") is not None and l.get("longitude") is not None
    ]


def get_default_location_simple(conn) -> Optional[dict]:
    from api.dwarf_location_api import get_default_location as _get_default_location
    loc = _get_default_location(conn)
    if not loc or loc.get("latitude") is None:
        return None
    return {"name": loc["name"], "lat": loc["latitude"], "lon": loc["longitude"], "elevation_m": 0}


def get_sessions_grouped_by_catalog_id(conn, catalog, catalog_sorted, catalog_decs) -> dict[str, SessionInfo]:
    """
    Aggregate BackupEntry/DwarfData integration time per catalog object.

    Sessions are matched to a catalog_id via resolve_catalog_id():
    dso_id link first, then name match, then nearest object by RA/Dec.
    Sessions that still can't be matched (no coordinates, nothing close
    enough) are skipped — they simply won't influence any recommendation.
    """
    from api.dwarf_backup_fct import parse_exposure

    rows = conn.execute("""
        SELECT
            DC.designation,
            AO.name,
            AO.description,
            DD.ra,
            DD.dec,
            BE.id,
            DD.exp_time,
            DD.shotsStacked,
            DD.ircut,
            BE.session_date
        FROM BackupEntry BE
        JOIN DwarfData   DD ON BE.dwarf_data_id = DD.id
        JOIN AstroObject AO ON BE.astro_object_id = AO.id
        LEFT JOIN DsoCatalog DC ON AO.dso_id = DC.id
        WHERE DD.exp_time IS NOT NULL AND DD.shotsStacked IS NOT NULL
          AND BE.session_dir NOT LIKE '%MOSAIC%'
    """).fetchall()

    name_index = build_catalog_name_index(catalog)

    agg: dict[str, dict] = {}
    unmatched_count = 0

    for (designation, ao_name, ao_desc, ra_hours, dec_deg, be_id,
         exp_time, shots, ircut, session_date) in rows:

        catalog_id = resolve_catalog_id(
            designation, ao_name, ao_desc, ra_hours, dec_deg,
            name_index, catalog_sorted, catalog_decs,
            max_sep_deg=MAX_MATCH_SEPARATION_DEG,
        )
        if catalog_id is None:
            unmatched_count += 1
            continue

        a = agg.setdefault(catalog_id, {
            "session_ids": set(), "minutes": 0.0, "filters": set(), "last_date": None,
        })
        a["session_ids"].add(be_id)
        exp_seconds = parse_exposure(f"{exp_time}s") if exp_time is not None else 0.0
        a["minutes"] += (exp_seconds * (shots or 0)) / 60.0
        if ircut:
            a["filters"].add(ircut)
        if session_date:
            d = datetime.fromisoformat(str(session_date).split(" ")[0]).date()
            if a["last_date"] is None or d > a["last_date"]:
                a["last_date"] = d

    if unmatched_count:
        print(f"[recommend_tonight] {unmatched_count} session(s) could not be matched to any catalog object")

    return {
        catalog_id: SessionInfo(
            session_count=len(a["session_ids"]),
            total_integration_minutes=a["minutes"],
            filters_used=sorted(a["filters"]),
            last_session_date=a["last_date"],
        )
        for catalog_id, a in agg.items()
    }

def get_mosaic_projects_with_panels(conn, catalog, catalog_sorted, catalog_decs) -> dict[str, MosaicInfo]:
    """
    Best-effort: the current schema has no dedicated "mosaic project" table
    with per-panel integration tracking. Sessions whose session_dir contains
    MOSAIC are grouped by resolved catalog object (dso_id, name match, or
    nearest RA/Dec — see resolve_catalog_id), and SessionWCS.panel_num
    (one resolved panel = one panel) is used as a proxy for per-panel
    integration. Replace this if a proper per-panel mosaic tracking table
    is added later.
    """
    from api.dwarf_backup_fct import parse_exposure

    rows = conn.execute("""
        SELECT
            DC.designation,
            AO.name,
            AO.description,
            DD.ra,
            DD.dec,
            BE.id,
            DD.exp_time,
            DD.shotsStacked,
            SW.panel_num
        FROM BackupEntry BE
        JOIN DwarfData   DD ON BE.dwarf_data_id = DD.id
        JOIN AstroObject AO ON BE.astro_object_id = AO.id
        LEFT JOIN DsoCatalog DC ON AO.dso_id = DC.id
        LEFT JOIN SessionWCS SW
               ON SW.entry_type = 'backup' AND SW.entry_id = BE.id AND SW.panel_num > 0
        WHERE BE.session_dir LIKE '%MOSAIC%'
    """).fetchall()

    name_index = build_catalog_name_index(catalog)

    projects: dict[str, MosaicInfo] = {}
    sessions_seen: dict[str, set] = {}
    unmatched_count = 0

    for (designation, ao_name, ao_desc, ra_hours, dec_deg, entry_id,
         exp_time, shots, panel_num) in rows:

        catalog_id = resolve_catalog_id(
            designation, ao_name, ao_desc, ra_hours, dec_deg,
            name_index, catalog_sorted, catalog_decs,
            max_sep_deg=MAX_MATCH_SEPARATION_DEG,
        )
        if catalog_id is None:
            unmatched_count += 1
            continue

        proj = projects.setdefault(
            catalog_id,
            MosaicInfo(project_id=0, session_count=0, panel_integration_minutes={}),
        )
        sessions_seen.setdefault(catalog_id, set()).add(entry_id)

        exp_seconds = parse_exposure(f"{exp_time}s") if exp_time is not None else 0.0
        minutes = (exp_seconds * (shots or 0)) / 60.0
        key = str(panel_num) if panel_num is not None else "0"
        proj.panel_integration_minutes[key] = proj.panel_integration_minutes.get(key, 0.0) + minutes

    if unmatched_count:
        print(f"[recommend_tonight] {unmatched_count} mosaic session row(s) could not be matched to any catalog object")

    for catalog_id, proj in projects.items():
        proj.session_count = len(sessions_seen.get(catalog_id, set()))

    return projects


# ── Visibility calculation ────────────────────────────────────────────────────

_ts = None
_eph = None

# Same "db" folder as DB_NAME / CATALOG_FILE / SKY_CATALOG_FILE — keeps the
# ephemeris cached next to the rest of the app data instead of wherever the
# process happens to be launched from (cwd), which may not be writable once
# packaged.
EPHEMERIS_DIR = os.path.dirname(DB_NAME) or "db"
EPHEMERIS_FILE = "de421.bsp"


def _get_skyfield_context():
    global _ts, _eph
    if _ts is None:
        from skyfield.api import Loader

        os.makedirs(EPHEMERIS_DIR, exist_ok=True)
        loader = Loader(EPHEMERIS_DIR)
        _ts = loader.timescale()
        try:
            _eph = loader(EPHEMERIS_FILE)
        except Exception as e:
            # No cached copy and no network (e.g. at a dark-sky site with no
            # signal): surface a clear error instead of a raw urllib traceback.
            raise RuntimeError(t("tonight_ephemeris_unavailable")) from e
    return _ts, _eph


def astro_twilight_window(observer, target_date: date):
    from skyfield import almanac

    ts, eph = _get_skyfield_context()
    t0 = ts.utc(target_date.year, target_date.month, target_date.day, 12)
    t1 = ts.utc(target_date.year, target_date.month, target_date.day + 1, 12)

    f = almanac.dark_twilight_day(eph, observer)
    times, events = almanac.find_discrete(t0, t1, f)

    dark_periods = []
    for i in range(len(events) - 1):
        if events[i] == 0:
            dark_periods.append((times[i], times[i + 1]))
    if not dark_periods:
        return t0, t1
    dark_periods.sort(key=lambda p: p[1] - p[0], reverse=True)
    return dark_periods[0]


def compute_night_context(location: dict, target_date: date):
    """
    Computes once the astronomical night window + the sampled time array
    for a given location/date. Reused for every catalog object in the same
    pass — avoids redoing the (expensive) almanac calculation for each
    target.
    """
    from skyfield.api import wgs84

    ts, eph = _get_skyfield_context()
    observer_topo = wgs84.latlon(location["lat"], location["lon"], elevation_m=location.get("elevation_m", 0))
    observer = eph["earth"] + observer_topo

    t0, t1 = astro_twilight_window(observer_topo, target_date)
    times = ts.linspace(t0, t1, SAMPLES_PER_NIGHT)
    minutes_per_sample = (t1 - t0) * 24 * 60 / SAMPLES_PER_NIGHT

    moon = eph["moon"]
    moon_positions = observer.at(times).observe(moon).apparent()

    return {
        "observer": observer,
        "times": times,
        "minutes_per_sample": minutes_per_sample,
        "moon_positions": moon_positions,
        "eph": eph,
    }


def compute_visibility_fast(ra_deg: float, dec_deg: float, night_ctx: dict) -> VisibilityResult:
    """Version optimisée : réutilise la fenêtre de nuit et les positions
    lunaires précalculées par compute_night_context() au lieu de tout
    recalculer par objet."""
    import math
    from skyfield.api import Star
    from skyfield import almanac

    observer = night_ctx["observer"]
    times = night_ctx["times"]
    minutes_per_sample = night_ctx["minutes_per_sample"]
    moon_positions = night_ctx["moon_positions"]
    eph = night_ctx["eph"]

    target = Star(ra_hours=ra_deg / 15.0, dec_degrees=dec_deg)
    astrometric = observer.at(times).observe(target)
    alt, az, _ = astrometric.apparent().altaz()
    alt_deg = alt.degrees

    max_alt = float(alt_deg.max())
    idx_best = int(alt_deg.argmax())
    best_time = times[idx_best].utc_datetime()

    minutes_above = float((alt_deg >= MIN_ALTITUDE_DEG).sum() * minutes_per_sample)

    sep_deg = astrometric.apparent()[idx_best].separation_from(moon_positions[idx_best]).degrees

    phase_angle = almanac.moon_phase(eph, times[idx_best]).degrees
    moon_phase_pct = 50 * (1 - math.cos(math.radians(phase_angle)))

    return VisibilityResult(
        max_altitude_deg=max_alt,
        minutes_above_threshold=minutes_above,
        best_time_utc=best_time,
        moon_separation_deg=float(sep_deg),
        moon_phase_pct=float(moon_phase_pct),
    )


# ── Classification / scoring ─────────────────────────────────────────────────

def classify_simple_target(session_info: Optional[SessionInfo]) -> tuple[Category, str]:
    if session_info is None:
        return Category.NEW, t("tonight_never_shot")
    if session_info.total_integration_minutes < MIN_INTEGRATION_MINUTES:
        return (
            Category.INCOMPLETE,
            t("tonight_integration_cumulated").format(
                minutes=round(session_info.total_integration_minutes),
                count=session_info.session_count,
            ),
        )
    return Category.WELL_COVERED, t("tonight_integration_cumulated_short").format(
        minutes=round(session_info.total_integration_minutes)
    )


def classify_mosaic_target(mosaic_info: Optional[MosaicInfo]) -> tuple[Category, str]:
    if mosaic_info is None or mosaic_info.session_count == 0:
        return Category.NEW, t("tonight_mosaic_never_shot")
    weakest = mosaic_info.weakest_panel_minutes
    if weakest < MIN_PANEL_INTEGRATION_MINUTES:
        return (
            Category.INCOMPLETE,
            t("tonight_weakest_panel").format(
                minutes=round(weakest), count=mosaic_info.session_count
            ),
        )
    return Category.WELL_COVERED, t("tonight_weakest_panel_short").format(minutes=round(weakest))


def moon_penalty(vis: VisibilityResult, surface_brightness_sensitive: bool) -> float:
    if vis.moon_separation_deg >= MOON_SEPARATION_WARN_DEG:
        return 0.0
    closeness = (MOON_SEPARATION_WARN_DEG - vis.moon_separation_deg) / MOON_SEPARATION_WARN_DEG
    weight = 1.0 if surface_brightness_sensitive else 0.4
    return closeness * (vis.moon_phase_pct / 100) * 50 * weight


def score_target(vis: VisibilityResult, category: Category, is_faint_nebula: bool) -> float:
    altitude_bonus = max(0.0, vis.max_altitude_deg - MIN_ALTITUDE_DEG)
    base = vis.minutes_above_threshold + altitude_bonus * 2
    category_bonus = {Category.NEW: 100, Category.INCOMPLETE: 60, Category.WELL_COVERED: 0}[category]
    return base + category_bonus - moon_penalty(vis, is_faint_nebula)


# ── Main pipeline (blocking — call via run.io_bound) ─────────────────────────

def _compute_recommendations(database: str, location: dict, target_date: date) -> list[TargetRecommendation]:
    import time
    t_start = time.perf_counter()

    conn = connect_db(database)
    try:
        catalog = load_catalog()  # stars already excluded

        # Pre-sort once by declination for fast windowed matching —
        # avoids an O(catalog_size) scan per unlinked session.
        catalog_sorted = sorted(catalog, key=lambda o: o["dec_deg"])
        catalog_decs = [o["dec_deg"] for o in catalog_sorted]

        sessions_by_id = get_sessions_grouped_by_catalog_id(
            conn, catalog, catalog_sorted, catalog_decs
        )
        mosaics_by_id = get_mosaic_projects_with_panels(
            conn, catalog, catalog_sorted, catalog_decs
        )
    finally:
        close_db(conn)

    t_matching = time.perf_counter()
    print(f"[recommend_tonight] matching phase: {t_matching - t_start:.2f}s, catalog size: {len(catalog)}")

    night_ctx = compute_night_context(location, target_date)
    t_night = time.perf_counter()
    print(f"[recommend_tonight] night context: {t_night - t_matching:.2f}s")

    results: list[TargetRecommendation] = []
    for obj in catalog:
        catalog_id = obj["id"]
        ra, dec = obj["ra_deg"], obj["dec_deg"]

        max_alt_possible = 90 - abs(location["lat"] - dec)
        if max_alt_possible < MIN_ALTITUDE_DEG:
            continue

        try:
            vis = compute_visibility_fast(ra, dec, night_ctx)
        except Exception as e:
            print(f"[recommend_tonight] visibility error for {catalog_id}: {e}")
            continue

        if vis.max_altitude_deg < MIN_ALTITUDE_DEG or vis.minutes_above_threshold < MIN_MINUTES_ABOVE:
            continue

        mosaic_info = mosaics_by_id.get(catalog_id)
        if mosaic_info is not None:
            category, detail = classify_mosaic_target(mosaic_info)
            session_info = None
        else:
            session_info = sessions_by_id.get(catalog_id)
            category, detail = classify_simple_target(session_info)

        is_faint_nebula = obj.get("type") in ("nebula", "emission_nebula", "planetary_nebula")
        score = score_target(vis, category, is_faint_nebula)

        results.append(TargetRecommendation(
            catalog_id=catalog_id,
            display_name=obj.get("name", catalog_id),
            ra_deg=ra,
            dec_deg=dec,
            object_type=obj.get("type", "?"),
            magnitude=obj.get("magnitude"),
            category=category,
            score=score,
            visibility=vis,
            session_info=session_info,
            mosaic_info=mosaic_info,
            detail=detail,
        ))

    t_visibility = time.perf_counter()
    print(f"[recommend_tonight] visibility loop: {t_visibility - t_night:.2f}s for {len(catalog)} objects")

    results.sort(key=lambda r: r.score, reverse=True)
    results = _cluster_nearby_targets(results)

    t_cluster = time.perf_counter()
    print(f"[recommend_tonight] clustering: {t_cluster - t_visibility:.2f}s for {len(results)} results")
    print(f"[recommend_tonight] TOTAL: {t_cluster - t_start:.2f}s")
    
    return results


# ──  NiceGUI Page ──────────────────────────────────────────────────────────────

@ui.page('/RecommendTonight')
async def recommend_tonight_page():
    menu(f"🔭 {t('page_recommend_tonight')}")
    await ui.context.client.connected(timeout=10.0)
    RecommendTonightApp(DB_NAME)


class RecommendTonightApp(DbPageMixin):
    def __init__(self, database: str):
        self.database = database
        self.location: Optional[dict] = None
        self.target_date: date = date.today()
        self.results: list[TargetRecommendation] = []
        self.build_ui()

    def build_ui(self):
        self.conn = connect_db(self.database)
        self.register_conn_close()

        #with ui.row().classes("items-center gap-4 w-full"):
        #    ui.label(f"🔭 {t('tonight_title')}").classes("text-2xl font-bold")

        with ui.card().classes("w-full p-4 mt-2"):
            with ui.row().classes("items-center gap-4 w-full flex-wrap"):
                self.location_select = ui.select(
                    options={}, label=t("tonight_location")
                ).classes("w-64")

                with ui.input(t("tonight_date"), value=self.target_date.isoformat()) \
                        .classes("w-48") as self.date_input:
                    with self.date_input.add_slot("append"):
                        ui.icon("event").classes("cursor-pointer").on(
                            "click", lambda: date_menu.open()
                        )
                    with ui.menu() as date_menu:
                        date_picker = ui.date(value=self.target_date.isoformat())
                        date_picker.on_value_change(lambda e: (
                            self.date_input.set_value(e.value),
                            self._on_date_change(e),
                            date_menu.close(),
                        ))

                self.refresh_btn = ui.button(
                    t("tonight_refresh"), on_click=self.refresh_results
                ).props("icon=refresh")

                self.loading_spinner = ui.spinner(size="md")
                self.loading_spinner.set_visibility(False)

            with ui.row().classes("items-center gap-4 w-full flex-wrap mt-2"):
                self.magnitude_filter = ui.number(
                    label=t("tonight_max_magnitude"), value=12
                ).classes("w-40")
                self.type_filter = ui.select(
                    options=["All", "nebula", "galaxy", "cluster"],
                    value="All", label=t("tonight_type")
                ).classes("w-40")
                self.hide_well_covered = ui.checkbox(
                    t("tonight_hide_covered"), value=True,
                    on_change=lambda: self.render_results.refresh(),
                )
                self.magnitude_filter.on("blur", lambda: self.render_results.refresh())
                self.type_filter.on_value_change(lambda: self.render_results.refresh())

        self.results_container = ui.column().classes("w-full mt-4")
        with self.results_container:
            self.render_results()

        self._init_locations()

    def _init_locations(self):
        locs = get_all_locations_simple(self.conn)
        if not locs:
            ui.notify(t("tonight_no_locations"), type="warning")
            return
        options = {l["name"]: l["name"] for l in locs}
        self.location_select.set_options(options)

        default = get_default_location_simple(self.conn)
        match = next((l for l in locs if default and l["name"] == default["name"]), locs[0])
        self.location_select.value = match["name"]
        self.location = match
        self.location_select.on_value_change(self._on_location_change)

        ui.timer(0.1, self.refresh_results, once=True)

    def _on_location_change(self, e):
        locs = get_all_locations_simple(self.conn)
        self.location = next((l for l in locs if l["name"] == e.value), None)

    def _on_date_change(self, e):
        try:
            self.target_date = date.fromisoformat(e.value)
        except Exception:
            pass

    async def refresh_results(self):
        if self.location is None:
            ui.notify(t("tonight_select_location"), type="warning")
            return

        self.loading_spinner.set_visibility(True)
        self.refresh_btn.disable()
        try:
            self.results = await run.io_bound(
                _compute_recommendations, self.database, self.location, self.target_date
            )
        except Exception as e:
            ui.notify(t("error_generic", error=str(e)), type="negative")
            self.results = []
        finally:
            self.loading_spinner.set_visibility(False)
            self.refresh_btn.enable()

        self.render_results.refresh()

    @ui.refreshable
    def render_results(self):
        if not self.results:
            ui.label(t("tonight_no_results")).classes("text-gray-500")
            return

        by_category: dict[Category, list[TargetRecommendation]] = {c: [] for c in Category}
        for r in self.results:
            if self.magnitude_filter.value and r.magnitude and r.magnitude > self.magnitude_filter.value:
                continue
            if self.type_filter.value != "All" and r.object_type != self.type_filter.value:
                continue
            by_category[r.category].append(r)

        section_labels = {
            Category.NEW: (f"✨ {t('tonight_new_targets')}", True),
            Category.INCOMPLETE: (f"🔧 {t('tonight_incomplete_targets')}", True),
            Category.WELL_COVERED: (f"✅ {t('tonight_well_covered_targets')}", not self.hide_well_covered.value),
        }

        any_shown = False
        for cat, (label, expanded_default) in section_labels.items():
            items = by_category[cat]
            if not items:
                continue
            any_shown = True
            with ui.expansion(f"{label} ({len(items)})", value=expanded_default).classes("w-full"):
                for r in items:
                    self._render_target_card(r)

        if not any_shown:
            ui.label(t("tonight_no_results_filtered")).classes("text-gray-500")

    def _open_aladin(self, r: TargetRecommendation):
        """Open the target in Aladin Lite (external browser)."""
        from components.astro_object_associate import open_aladin_sky_map
        open_aladin_sky_map(r.ra_deg, r.dec_deg)

    def _render_target_card(self, r: TargetRecommendation):
        with ui.card().classes("w-full mb-2"):
            with ui.row().classes("items-center justify-between w-full"):
                ui.label(r.display_name).classes("text-lg font-semibold")
                with ui.row().classes("items-center gap-2"):
                    ui.label(r.object_type).classes("text-gray-400 text-sm")
                    ui.button(icon="travel_explore", on_click=lambda r=r: self._open_aladin(r)) \
                        .props("flat dense round size=sm") \
                        .tooltip(t("tonight_view_aladin"))
            ui.label(r.detail).classes("text-sm text-gray-600")
            with ui.row().classes("gap-4 text-sm flex-wrap"):
                ui.label(f"{t('tonight_max_alt')}: {r.visibility.max_altitude_deg:.0f}°")
                ui.label(f"{t('tonight_visible_for')}: {r.visibility.minutes_above_threshold:.0f} min")
                ui.label(f"{t('tonight_best_time')}: {r.visibility.best_time_utc.strftime('%H:%M UTC')}")
                ui.label(f"🌙 {r.visibility.moon_separation_deg:.0f}° / {r.visibility.moon_phase_pct:.0f}%")