"""Altitude-over-the-night chart for one target (ported from Astro Dwarf
Session's target planner, components/target_planner.py).

Draws the target's altitude with its compass direction, the Moon and the
Sun, the dark window, the best slot (dark AND above the minimum altitude)
and the minimum-altitude line. The maths is components/sky_altitude.py.

Times are wall-clock times of the location's timezone, this PC's when the
location has none (api/site_time.py).
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Optional

from nicegui import ui

from api.site_time import location_zone
from components.i18n import t
from components.sky_altitude import NightPlan, compass_index, compute_night_plan


def _compass_names() -> list[str]:
    """Localized 8-point compass, in sky_altitude.COMPASS_POINTS order."""
    names = [n.strip() for n in t("tonight_chart_compass").split(",")]
    return names if len(names) == 8 else ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def _fmt(dt: Optional[datetime]) -> str:
    return dt.strftime("%H:%M") if dt else "-"


def render_altitude_chart(
    ra_deg: float,
    dec_deg: float,
    location: dict,
    night: date,
    *,
    min_altitude: float = 30.0,
    darkness: str = "astronomical",
) -> NightPlan:
    """Builds the chart (and its one-line summary) in the current NiceGUI
    context. night: the evening's date. Every time on the chart is the wall
    clock of the location's timezone (api/site_time.py), this PC's when it
    has none. Returns the computed plan."""
    zone = location_zone(location)
    plan = compute_night_plan(
        ra_deg / 15.0,
        dec_deg,
        float(location["lat"]),
        float(location["lon"]),
        datetime(night.year, night.month, night.day),
        min_altitude=float(min_altitude),
        darkness=darkness,
        tz=zone,
    )

    labels = [ts.strftime("%H:%M") for ts in plan.times]
    mark_areas = []
    if plan.dark_start and plan.dark_end:
        mark_areas.append([
            {"name": t("tonight_chart_night"), "xAxis": _fmt(plan.dark_start),
             "itemStyle": {"color": "rgba(60,80,140,0.18)"}},
            {"xAxis": _fmt(plan.dark_end)},
        ])
    if plan.best_slot:
        mark_areas.append([
            {"name": t("tonight_chart_best"), "xAxis": _fmt(plan.best_slot[0]),
             "itemStyle": {"color": "rgba(56,200,112,0.22)"}},
            {"xAxis": _fmt(plan.best_slot[1])},
        ])

    # Compass direction of the target: labelled on the curve wherever it
    # changes while above the horizon, and in the tooltip for every point.
    compass = _compass_names()
    directions = [compass[compass_index(az)] for az in plan.target_az]
    target_points: list = []
    previous = None
    for alt, direction in zip(plan.target_alt, directions):
        value = round(alt, 1)
        if alt > 0 and direction != previous:
            target_points.append({
                "value": value,
                "symbolSize": 8,
                "label": {"show": True, "formatter": direction, "position": "top",
                          "fontWeight": "bold", "fontSize": 11},
            })
        else:
            target_points.append(value)
        previous = direction if alt > 0 else None

    target_name = t("tonight_chart_target")
    tooltip_dirs = json.dumps([f"{d} ({round(az)}°)" for d, az in zip(directions, plan.target_az)])

    if zone is None:
        night_label = t("tonight_chart_night_of", date=night.strftime("%Y-%m-%d"))
    else:
        night_label = t("tonight_chart_night_of_tz", date=night.strftime("%Y-%m-%d"), tz=str(zone))
    ui.label(night_label).classes("text-xs text-grey-6")
    ui.echart({
        "animation": False,
        "tooltip": {
            "trigger": "axis",
            ":formatter": (
                "params => { const dirs = " + tooltip_dirs + "; "
                "let html = params.length ? params[0].axisValueLabel : ''; "
                "for (const p of params) { "
                "html += '<br/>' + p.marker + p.seriesName + ' : <b>' + p.value + '°</b>'; "
                "if (p.seriesName === " + json.dumps(target_name) + ") html += ' · ' + dirs[p.dataIndex]; } "
                "return html; }"
            ),
        },
        "legend": {"top": 0},
        "grid": {"left": 40, "right": 32, "top": 30, "bottom": 30},
        "xAxis": {"type": "category", "data": labels},
        "yAxis": {"type": "value", "min": -10, "max": 90, "name": "°"},
        "series": [
            {
                "name": target_name,
                "type": "line",
                "symbol": "circle",
                "symbolSize": 5,
                # Every point drawn: with "auto" ECharts skips symbols when
                # they're dense - and the compass labels with them.
                "showAllSymbol": True,
                "data": target_points,
                "lineStyle": {"width": 3},
                "markArea": {"silent": True, "data": mark_areas, "label": {"show": False}},
                "markLine": {
                    "silent": True,
                    "symbol": "none",
                    "lineStyle": {"type": "dashed", "color": "#f0a030"},
                    "data": [{"yAxis": float(min_altitude)}],
                },
            },
            {
                "name": t("tonight_chart_moon", pct=round(plan.moon_illumination * 100)),
                "type": "line",
                "showSymbol": False,
                "data": [round(a, 1) for a in plan.moon_alt],
                "lineStyle": {"type": "dotted", "color": "#9e9e9e"},
                "itemStyle": {"color": "#9e9e9e"},
            },
            {
                "name": t("tonight_chart_sun"),
                "type": "line",
                "showSymbol": False,
                "data": [round(a, 1) for a in plan.sun_alt],
                "lineStyle": {"width": 1, "color": "#f0b840"},
                "itemStyle": {"color": "#f0b840"},
            },
        ],
    }).classes("w-full h-64")

    bits = []
    if plan.transit_time is not None:
        transit_i = plan.times.index(plan.transit_time)
        bits.append(t(
            "tonight_chart_culmination",
            time=_fmt(plan.transit_time),
            alt=round(plan.max_altitude or 0),
            direction=directions[transit_i],
        ))
    if plan.dark_start:
        bits.append(t("tonight_chart_dark_window", start=_fmt(plan.dark_start), end=_fmt(plan.dark_end)))
    else:
        bits.append(t("tonight_chart_never_dark"))
    if plan.best_slot:
        bits.append(t("tonight_chart_best_slot", start=_fmt(plan.best_slot[0]), end=_fmt(plan.best_slot[1])))
    else:
        bits.append(t("tonight_chart_no_slot", alt=round(min_altitude)))
    bits.append(t(
        "tonight_chart_moon_info",
        pct=round(plan.moon_illumination * 100),
        sep=round(plan.moon_separation or 0),
    ))
    ui.label(" · ".join(bits)).classes("text-sm")
    return plan
