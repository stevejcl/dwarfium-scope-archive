from nicegui import ui, events
import sqlite3

from astroquery.simbad import Simbad
from astropy.coordinates import SkyCoord
from astropy import units as u

from api.dwarf_backup_db_api import get_dso_filtered, get_dso_registered, get_dso_description, get_dso_registered_by_designation
from api.dwarf_backup_db_api import get_astro_object_description, update_astro_object_dso, update_astro_object_description
from api.dwarf_backup_fct import preprocess_dso_catalog_json, hms_to_hours, dms_to_degrees, hours_to_hms, deg_to_dms
from api.dso_matching import angular_sep_deg

import webbrowser
from typing import Dict

from dataclasses import dataclass
from typing import Optional

from components.i18n import t

@dataclass
class DwarfData:
    dwarf_data_id: Optional[int] = None
    target: Optional[str] = None
    dec: Optional[str] = None
    ra: Optional[str] = None
    astro_object_id: Optional[int] = None
    astro_group_id: Optional[int] = None
    session_date: Optional[str] = None  # ISO datetime string e.g. "2025-01-15 20:00:00"

    @classmethod
    def from_row(cls, row):
        """Create from tuple, list, dict, or sqlite3.Row."""
        if isinstance(row, dict):
            return cls(**row)
        elif isinstance(row, (tuple, list)):
            # Map fields by position
            return cls(
                dwarf_data_id=row[0],
                target=row[13],
                dec=row[14],
                ra=row[15],
                astro_object_id=row[17],
                astro_group_id=row[18],
                session_date=row[7] if len(row) > 7 else None,
            )
        else:
            raise TypeError(f"Unsupported row type: {type(row)}")


# used for sharing description field
shared = {'custom_name': ''}

def open_aladin_sky_map(ra, dec, fov=3):
    url = f"https://aladin.u-strasbg.fr/AladinLite/?target={ra}+{dec}&fov={fov}&survey=P%2FDSS2%2Fcolor"
    webbrowser.open(url)

def find_nearby_objects(dwarf_data_row, only_unknown=True, radius_deg=1.5, max_results=10):
    ra = float(dwarf_data_row[15])*15
    dec = float(dwarf_data_row[14])
    target = dwarf_data_row[13]

    if only_unknown and target.lower() != "unknown":
        return None, f"Target is already known: {target}"

    coord = SkyCoord(ra=ra*u.deg, dec=dec*u.deg, frame='icrs')

    custom_simbad = Simbad()
    custom_simbad.TIMEOUT = 30
    custom_simbad.ROW_LIMIT = max_results
    custom_simbad.add_votable_fields('otype', 'flux(V)', 'ra(d)', 'dec(d)')

    result_table = custom_simbad.query_region(coord, radius=radius_deg*u.deg)
    if result_table is None:
        return [], "❌ No objects found nearby."

    objects = []
    print (result_table)
    for row in result_table:
        objects.append({
            "Main ID": row["main_id"].decode("utf-8") if isinstance(row["main_id"], bytes) else row["main_id"],
            "Object Type": row["otype"].decode("utf-8") if isinstance(row["otype"], bytes) else row["otype"],
            "RA": round(row["ra"], 5),
            "DEC": round(row["dec"], 5),
            "Mag(V)": row["V"]
        })

    return objects, None

def find_nearby_dso_from_json(target_ra_deg, target_dec_deg, processed_catalog, radius_deg=3.0, max_results=10):
    results = []
    for obj in processed_catalog:
        try:
            sep = angular_sep_deg(target_ra_deg, target_dec_deg, obj["ra_deg"], obj["dec_deg"])
            if sep <= radius_deg:
                results.append({
                    "name": obj.get("displayName", obj.get("designation", "Unknown")),
                    "designation": obj.get("designation", "Unknown"),
                    "type": obj.get("type", ""),
                    "ra": obj.get("ra"),
                    "dec": obj.get("dec"),
                    "ra_deg": obj.get("ra_deg"),
                    "dec_deg": obj.get("dec_deg"),
                    "separation_deg": round(sep, 4)
                })
        except Exception as e:
            print(f"[WARN] Error comparing to {obj.get('name')}: {e}")
            return [], "❌ No objects found nearby."

    results.sort(key=lambda x: x["separation_deg"])
    return results[:max_results], None


def find_nearby_dso_from_json_old(target_ra_deg, target_dec_deg, processed_catalog, radius_deg=3.0, max_results=10):

    target_coord = SkyCoord(ra=target_ra_deg * u.deg, dec=target_dec_deg * u.deg, frame='icrs')

    results = []
    for obj in processed_catalog:
        try:
            dso_coord = SkyCoord(ra=obj["ra_deg"] * u.deg, dec=obj["dec_deg"] * u.deg, frame='icrs')
            sep = target_coord.separation(dso_coord).degree
            if sep <= radius_deg:
                results.append({
                    "name": obj.get("displayName", obj.get("designation", "Unknown")),
                    "designation": obj.get("designation", "Unknown"),
                    "type": obj.get("type", ""),
                    "ra": obj.get("ra"),
                    "dec": obj.get("dec"),
                    "ra_deg": obj.get("ra_deg"),
                    "dec_deg": obj.get("dec_deg"),
                    "separation_deg": round(sep, 4)
                })
        except Exception as e:
            print(f"[WARN] Error comparing to {obj.get('name')}: {e}")
            return [], "❌ No objects found nearby."

    results.sort(key=lambda x: x["separation_deg"])
    return results[:max_results], None

def _skybot_query(ra_deg, dec_deg, session_date, radius_deg, find_comets, find_asteroids):
    """Single SkyBot pass — called via run.io_bound."""
    from astroquery.imcce import Skybot
    from astropy.coordinates import SkyCoord
    from astropy.time import Time
    import astropy.units as apu
    import re

    def qty_to_float(val, default=0.0):
        if hasattr(val, "value"):
            return float(val.value)
        if isinstance(val, (int, float)):
            return float(val)
        s = str(val).strip()
        if s in ("", ".", "--", "N/A", "nan", "None"):
            return default
        m = re.search(r"[+-]?[\d.]+", s)
        return float(m.group()) if m else default

    def qty_to_str(val):
        s = str(val).strip()
        return "?" if s in ("", ".", "--", "N/A", "nan", "None") else s

    date_str = str(session_date).replace("T", " ").split(".")[0]
    epoch  = Time(date_str, format="iso")
    field  = SkyCoord(ra=ra_deg * apu.deg, dec=dec_deg * apu.deg, frame="icrs")
    radius = radius_deg * apu.deg

    try:
        table = Skybot.cone_search(field, radius, epoch,
                                   find_comets=find_comets,
                                   find_asteroids=find_asteroids,
                                   find_planets=False)
    except Exception as exc:
        msg = str(exc)
        if "No object found" in msg or "No solar system" in msg or "TableParseError" in msg:
            return [], None
        if "ConnectionError" in msg or "RemoteServiceError" in msg or "timed out" in msg.lower():
            return [], "Cannot reach SkyBot (IMCCE) — check your internet connection."
        return [], f"SkyBot error: {exc}"

    results = []
    for row in table:
        try:
            obj_ra_deg  = qty_to_float(row["RA"])
            obj_dec_deg = qty_to_float(row["DEC"])
            sep_deg     = qty_to_float(row["centerdist"]) / 3600.0
            results.append({
                "name":           str(row["Name"]),
                "type":           str(row["Type"]),
                "ra":             hours_to_hms(obj_ra_deg / 15.0),
                "dec":            deg_to_dms(obj_dec_deg),
                "ra_deg":         obj_ra_deg,
                "dec_deg":        obj_dec_deg,
                "separation_deg": round(sep_deg, 4),
                "magnitude":      qty_to_str(row["V"]),
            })
        except Exception as row_exc:
            print(f"[SkyBot] parse error: {row_exc}")
            continue
    return results, None


def find_nearby_comets_skybot(ra_deg, dec_deg, session_date, radius_deg=4.0):
    """Kept for compatibility — runs both passes sequentially."""
    comets,    err1 = _skybot_query(ra_deg, dec_deg, session_date, radius_deg, find_comets=True,  find_asteroids=False)
    asteroids, err2 = _skybot_query(ra_deg, dec_deg, session_date, radius_deg, find_comets=False, find_asteroids=True)
    err = err1 or err2
    results = sorted(comets + asteroids, key=lambda x: x["separation_deg"])
    return results, err

def show_unknown_target_dialog(conn: sqlite3.Connection, dwarf_data: DwarfData, dso_catalog, only_unknown=True, on_done = None):
    ra = hms_to_hours(dwarf_data.ra) * 15  # convert hours to degrees
    dec = dms_to_degrees(dwarf_data.dec)
    target = dwarf_data.target
    astro_object_id = dwarf_data.astro_object_id
    astro_group_id = dwarf_data.astro_group_id
    dwarf_data_id = dwarf_data.dwarf_data_id
    session_date = dwarf_data.session_date  # may be None for old sessions

    if only_unknown and target.lower() != "unknown" and target.lower() != "mosaic_unknown" and target.lower() != "manual":
        ui.notify(t("target_known_short").format(target=target), type="warning")
        return None, f"Target is already known: {target}"

    old_description = get_astro_object_description(conn, astro_object_id)
    shared['custom_name'] = old_description 
    # Use your local catalog
    objects, error = find_nearby_dso_from_json(ra, dec, dso_catalog)

    def handle_add(conn, target: str, name: str, designation: str, astro_object_id, astro_group_id):
        print(f"try update: {target} to {name}")
        if astro_object_id:
            # get DSO
            dso_id = get_dso_registered_by_designation(conn, designation)
            if dso_id:
                update_astro_object_dso(conn, astro_object_id, int(dso_id), "")
                new_description = get_astro_object_description(conn, astro_object_id)
                shared['custom_name'] = new_description 
                ui.notify(t("dso_assigned"))
                if on_done:
                    on_done()
            else:
                ui.notify(t("failed_update_object"), type="negative")

    def on_add_dso( msg: Dict):
        print(msg.args)
        target, name, designation, astro_object_id, astro_group_id = msg.args
        handle_add(conn, target, name, designation, astro_object_id, astro_group_id)

    if error:
        ui.label(error).classes('text-red-600')
    elif not objects:
        ui.label(t("no_nearby_dso")).classes('text-red-600').classes("mt-2")
        show_dso_dialog(target, ra, dec, objects, conn, astro_object_id, astro_group_id, old_description, on_add_dso, on_done, session_date=session_date)
    else:
        show_dso_dialog(target, ra, dec, objects, conn, astro_object_id, astro_group_id, old_description, on_add_dso, on_done, session_date=session_date)

def show_dso_dialog(target, ra, dec, objects, conn, astro_object_id, astro_group_id, old_description, on_add_dso, on_done = None, session_date = None):
    with ui.dialog() as dialog:
        with ui.card().classes("w-full p-4").style("max-width: 2600px; margin: auto"):
            ui.label(f'🔭 Target: {target} - RA: {hours_to_hms(ra/15)}, DEC: {deg_to_dms(dec)}').classes('text-lg font-bold')

            if not objects:
                ui.label(t("no_nearby_dso")).classes('text-red-600')
            else:
                columns = [
                    {'name': 'name', 'label': 'Object', 'field': 'name'},
                    {'name': 'type', 'label': t('col_type'), 'field': 'type'},
                    {'name': 'ra', 'label': 'RA (H)', 'field': 'ra'},
                    {'name': 'dec', 'label': 'DEC (°)', 'field': 'dec'},
                    {'name': 'separation_deg', 'label': 'Δθ (°)', 'field': 'separation_deg'},
                    {'name': 'actions', 'label': 'Actions'},
                ]

                table = ui.table(columns=columns, rows=[], row_key='name').classes('w-full')

            def save_custom_name():
                description = custom_name.value.strip()
                if description:
                    update_astro_object_description(conn, astro_object_id, description)
                    #shared['custom_name'] = description 
                    ui.notify(f"✅ Saved as: {description}", type="positive")
                    if on_done:
                        on_done()
                else:
                    ui.notify(t("please_description"), type="warning")

            if objects:
                reload( table, target, objects, astro_object_id, astro_group_id)
                        
                ui.update() 

                # Bind the action
                table.on('add_dso', on_add_dso)

            # ── ☄️ Comet search via SkyBot (IMCCE) ────────────────────────────
            ui.separator().classes('my-3')
            with ui.expansion(t('comet_expansion_title'), icon='travel_explore', value=False).classes('w-full') as comet_expansion:
                comet_expansion.on('update:model-value', lambda e: search_comets() if e.args else None)
                comet_status  = ui.label('').classes('text-sm text-gray-500 italic')
                comet_columns = [
                    {'name': 'name',          'label': 'Object',  'field': 'name',           'sortable': True},
                    {'name': 'type',          'label': 'Type',    'field': 'type'},
                    {'name': 'ra',            'label': 'RA (H)',  'field': 'ra'},
                    {'name': 'dec',           'label': 'DEC (°)', 'field': 'dec'},
                    {'name': 'separation_deg','label': 'Δθ (°)',  'field': 'separation_deg',  'sortable': True},
                    {'name': 'magnitude',     'label': 'Mag (V)', 'field': 'magnitude'},
                    {'name': 'actions',       'label': ''},
                ]
                comet_table = ui.table(columns=comet_columns, rows=[], row_key='name').classes('w-full')
                comet_table.add_slot('no-data', '<div class="text-gray-400 p-4">' + t("no_data") + '</div>')

                comet_table.add_slot('body', '''
                  <q-tr :props="props">
                    <q-td key="name"          :props="props">{{ props.row.name }}</q-td>
                    <q-td key="type"          :props="props">{{ props.row.type }}</q-td>
                    <q-td key="ra"            :props="props">{{ props.row.ra }}</q-td>
                    <q-td key="dec"           :props="props">{{ props.row.dec }}</q-td>
                    <q-td key="separation_deg":props="props">{{ props.row.separation_deg }}</q-td>
                    <q-td key="magnitude"     :props="props">{{ props.row.magnitude }}</q-td>
                    <q-td key="actions"       :props="props">
                      <q-btn
                        size="sm"
                        :icon="props.row.type === 'Comet' ? 'emergency' : 'stars'"
                        :color="props.row.type === 'Comet' ? 'deep-orange' : 'primary'"
                        round dense
                        @click="$parent.$emit('use_comet', props.row.name)"
                      />
                    </q-td>
                  </q-tr>
                ''')

                def on_use_comet(msg):
                    name = msg.args if isinstance(msg.args, str) else (msg.args[0] if msg.args else '')
                    if name:
                        custom_name.set_value(name)
                        ui.notify(f'☄️ "{name}" {t("comet_copied")}', type='positive')

                comet_table.on('use_comet', on_use_comet)

                # Cache of raw SkyBot results — filter applied without re-querying
                skybot_results = {'comets': [], 'error': None, 'mag_limit': 15.0}

                def apply_mag_filter():
                    comets = skybot_results['comets']
                    if not comets:
                        return
                    limit = skybot_results['mag_limit']

                    def passes_mag(c):
                        # Always show comets regardless of magnitude
                        t = c['type']
                        if t in ('Comet', 'comet') or t.startswith('C/') or t.startswith('P/'):
                            return True
                        if c['magnitude'] == '?':
                            return True   # unknown magnitude → include
                        try:
                            # magnitude scale: smaller = brighter, larger = fainter
                            # keep objects BRIGHTER than limit (mag <= limit)
                            return float(c['magnitude']) <= limit
                        except (ValueError, TypeError):
                            return True

                    filtered = [c for c in comets if passes_mag(c)]
                    hidden   = len(comets) - len(filtered)
                    hidden_str = f' ({hidden} filtered out, mag > {limit:.1f})' if hidden else ''

                    if not filtered:
                        comet_status.set_text(
                            f'⚠️ {len(comets)} {t("objects_fainter").format(limit=limit)}'
                        )
                        comet_table.rows = []
                    else:
                        comet_status.set_text(f'✅ {len(filtered)} {t("objects_shown")}{hidden_str} — {t("click_to_use")}')
                        comet_table.rows = [
                            {
                                'name':           c['name'],
                                'type':           c['type'],
                                'ra':             c['ra'],
                                'dec':            c['dec'],
                                'separation_deg': c['separation_deg'],
                                'magnitude':      c['magnitude'],
                            }
                            for c in filtered
                        ]
                    ui.update()

                async def search_comets():
                    comet_status.set_text(t('searching_comets'))
                    comet_table.rows = []
                    skybot_results['comets'] = []
                    ui.update()
                    from nicegui import run
                    if not session_date:
                        comet_status.set_text(t('no_session_date_skybot'))
                        return

                    # --- Pass 1: comets only — display immediately ---
                    try:
                        comets, err = await run.io_bound(
                            _skybot_query, ra, dec, session_date, 4.0, True, False
                        )
                    except Exception as exc:
                        comet_status.set_text(f'{t("comet_error")} {exc}')
                        return
                    if err:
                        comet_status.set_text(err)
                        return
                    skybot_results['comets'] = comets
                    if comets:
                        comet_status.set_text(f'☄️ {len(comets)} {t("comets_found_searching")}')
                        apply_mag_filter()
                    else:
                        comet_status.set_text(t('no_comets_searching'))
                    ui.update()

                    # --- Pass 2: asteroids — append and refresh ---
                    try:
                        asteroids, err2 = await run.io_bound(
                            _skybot_query, ra, dec, session_date, 4.0, False, True
                        )
                    except Exception as exc:
                        comet_status.set_text(f'{t("comet_error")} {exc}')
                        return
                    if err2:
                        comet_status.set_text(err2)
                        return
                    all_results = sorted(comets + asteroids, key=lambda x: x["separation_deg"])
                    skybot_results['comets'] = all_results
                    if not all_results:
                        comet_status.set_text(t('no_comets_asteroids'))
                        ui.update()
                        return
                    apply_mag_filter()

                with ui.row().classes('items-center gap-4 mt-2'):
                    date_display = str(session_date)[:19] if session_date else 'unknown'
                    ui.button(
                        f'🔄 {t("refresh_label")} ({date_display})',
                        on_click=search_comets
                    ).props('flat color=deep-orange').classes('mt-2')

                    def on_mag_change(e):
                        try:
                            skybot_results['mag_limit'] = float(e.value) if e.value not in (None, '') else 15.0
                        except (ValueError, TypeError):
                            skybot_results['mag_limit'] = 15.0

                    mag_limit = ui.number(
                        label=t('max_magnitude'), value=15.0, min=0.0, max=25.0, step=0.5,
                        format='%.1f', on_change=on_mag_change
                    ).classes('w-36').tooltip(t('mag_tooltip'))
                    ui.button(t('apply_filter'), icon='filter_alt',
                              on_click=lambda: apply_mag_filter()).props('flat color=deep-orange').classes('mt-2')

                if session_date:
                    pass  # search triggered by expansion open event


            # ── end comet section ──────────────────────────────────────────────
            ui.button(t('open_in_aladin'), on_click=lambda: open_aladin_sky_map(ra, dec, fov=3.0)).props('flat color=primary')

            with ui.row().classes("justify-end mt-4"):
                custom_name = ui.input(label=t('custom_description2'), value=old_description).bind_value(shared, 'custom_name').classes('mt-2').style('width: 600px; ; max-width: none')
                ui.button(t('save'), on_click=save_custom_name).props('color=primary').classes("mt-4")

            ui.button(t('close'), on_click=dialog.close).props('color=primary')

    dialog.open()

# Load data into the table
@ui.refreshable
def reload(table, target, objects, astro_object_id, astro_group_id):
    table.rows.clear()

    for obj in objects:
        table.rows = [{
            'name' : obj["name"],
            'designation' : obj["designation"],
            'type' : obj["type"],
            'ra' : obj["ra"],
            'dec' : obj["dec"],
            'separation_deg' : obj["separation_deg"],
            'target': target,
            'astro_object_id': astro_object_id,
            'astro_group_id': astro_group_id,
            'icon': 'edit' if target.lower() != "unknown" else 'add',
            'actions' : '',
        }
        for obj in objects
    ]
        icon= 'edit' if target.lower() != "unknown" else 'add'

        # Define JS template slot for the 'actions' column
        table.add_slot('body', '''
          <q-tr :props="props">
            <q-td key="name" :props="props">{{ props.row.name }}</q-td>
            <q-td key="type" :props="props">{{ props.row.type }}</q-td>
            <q-td key="ra" :props="props">{{ props.row.ra }}</q-td>
            <q-td key="dec" :props="props">{{ props.row.dec }}</q-td>
            <q-td key="separation_deg" :props="props">{{ props.row.separation_deg }}</q-td>
            <q-td key="actions" :props="props">
              <q-btn
                size="sm"
                :icon="props.row.icon"
                color="primary"
                round
                dense
                @click="$parent.$emit('add_dso', props.row.target, props.row.name, props.row.designation, props.row.astro_object_id, props.row.astro_group_id)"
              />
            </q-td>
          </q-tr>
        ''')

        ui.update() 

def show_assign_dialog(db_path_or_conn, astro_object_row, on_done=None):
    """
    db_path_or_conn: either a db path string OR a sqlite3.Connection.
    Opens its own connection per query to avoid SQLite thread issues.
    """
    from nicegui import run
    import sqlite3 as _sqlite3

    if isinstance(db_path_or_conn, str):
        db_path = db_path_or_conn
    else:
        db_path = db_path_or_conn.execute("PRAGMA database_list").fetchone()[2]

    def _open():
        c = _sqlite3.connect(db_path)
        c.execute("PRAGMA foreign_keys = ON")
        return c

    with ui.dialog() as dialog, ui.card().style('width: 600px; max-width: none'):
        ui.label(f"Assign DSO to AstroObject ID {astro_object_row[1]}")

        search_input = ui.input(label='Search (designation, name, constellation, type)', on_change=lambda e: update_dso_list()).classes('w-full')
        constellation_filter = ui.input(label='Constellation (exact)', on_change=lambda e: update_dso_list()).classes('w-full')
        type_filter = ui.input(label='Type (exact)', on_change=lambda e: update_dso_list()).classes('w-full')
        dso_select = ui.select({}, label='Select DSO').classes('w-full')
        custom_dso_input     = ui.input(label="custom_description",
                                        value=astro_object_row[2] or '').classes('w-full')

        _user_is_searching = [False]

        async def update_dso_list(auto_select=False):
            def _fetch():
                c = _open()
                result = get_dso_filtered(c,
                    search=search_input.value,
                    constellation=constellation_filter.value or None,
                    dso_type=type_filter.value or None)
                c.close()
                return result
            filtered = await run.io_bound(_fetch)
            options = {str(d[0]): f"{d[2]} ({d[3]}, {d[4]})" for d in filtered}
            dso_select.set_options(options)
            # Auto-select first result only when user typed something
            if auto_select and options:
                dso_select.value = next(iter(options))
                await update_dso_value()

        async def update_dso_value():
            if not dso_select.value:
                return
            def _fetch():
                c = _open()
                desc = get_dso_description(c, dso_select.value)
                c.close()
                return desc
            desc = await run.io_bound(_fetch)
            if desc:
                custom_dso_input.value = desc

        async def update_dso_data():
            def _fetch():
                c = _open()
                r = get_dso_registered(c, astro_object_row[3])
                c.close()
                return r
            registered = await run.io_bound(_fetch)
            if registered:
                dso_select.set_options(                        
                    {str(registered[0]): f"{registered[2]} ({registered[3]}, {registered[4]})"})
                dso_select.value = str(registered[0])
            else:
                await update_dso_list(auto_select=False)

        search_input.on('update:model-value',         lambda e: update_dso_list(auto_select=True))
        constellation_filter.on('update:model-value', lambda e: update_dso_list(auto_select=True))
        type_filter.on('update:model-value',          lambda e: update_dso_list(auto_select=True))
        dso_select.on('update:model-value',           lambda e: update_dso_value())

        ui.timer(0, update_dso_data, once=True)

        async def confirm():
            if not dso_select.value:
                ui.notify(t("notif_select_dso_first"), color='red')
                return
            dso_id = int(dso_select.value)
            def _save():
                c = _open()
                dso = get_dso_registered(c, dso_id)
                if dso:
                    auto_desc = f"{dso[2].split(',')[0].strip()} ({dso[3]}) in {dso[4]}, size: {dso[5] or 'N/A'}, mag: {dso[6] or 'N/A'}"
                else:
                    auto_desc = ''
                final_desc = custom_dso_input.value.strip() or auto_desc
                update_astro_object_dso(c, astro_object_row[0], dso_id, final_desc)
                c.close()
                return dso_id
            await run.io_bound(_save)
            ui.notify("DSO assigned/updated!")
            dialog.close()
            if on_done:
                on_done()

        with ui.row():
            ui.button(t("confirm"), on_click=confirm)
            ui.button(t("cancel"), on_click=dialog.close)

    dialog.open()

def show_dso_dialog_old(target, ra, dec, objects, conn, astro_object_id, astro_group_id, old_description, on_add_dso, on_done = None):

    if error:
        ui.label(error).classes('text-red-600')
    elif not objects:
        ui.label(t("no_nearby_dso")).classes('text-red-600')
        with ui.dialog() as dialog:
            with ui.card().classes("w-full p-4").style("max-width: 600px; margin: auto"):
                ui.label(f'🔭 Target: {target} - RA: {hours_to_hms(ra/15)}, DEC: {deg_to_dms(dec)}').classes('text-lg font-bold')
                ui.label(t("no_nearby_dso")).classes('text-red-600')
                ui.button(t('open_in_aladin'), on_click=lambda: open_aladin_sky_map(ra, dec, fov=3.0)).props('flat color=primary')

                custom_name = ui.input(label=t('custom_description2'), value=old_description).classes("w-full mt-4")

                def save_custom_name():
                    description = custom_name.value.strip()
                    if description:
                        # Your logic to store/save the description
                        update_astro_object_description(conn, astro_object_id, description)
                        ui.notify(f"✅ Saved as: {description}", type="positive")
                    else:
                        ui.notify(t("please_description"), type="warning")

                with ui.row().classes("justify-end mt-4"):
                    ui.button(t('save'), on_click=save_custom_name).props('color=primary')
                    ui.button(t('close'), on_click=dialog.close).props('flat')
        dialog.open()
    else:
        with ui.dialog() as dialog:
            with ui.card().classes("w-full p-4").style("max-width: 2600px; margin: auto"):
                ui.label(f'🔭 Target: {target} - RA: {hours_to_hms(ra/15)}, DEC: {deg_to_dms(dec)}').classes('text-lg font-bold')

                if not objects:
                    ui.label(t("no_nearby_dso")).classes('text-red-600')
                else:
                    columns=[
                        {'name': 'name', 'label': 'Object', 'field': 'name'},
                        {'name': 'type', 'label': t('col_type'), 'field': 'type'},
                        {'name': 'ra', 'label': 'RA (H)', 'field': 'ra'},
                        {'name': 'dec', 'label': 'DEC (°)', 'field': 'dec'},
                        {'name': 'separation_deg', 'label': 'Δθ (°)', 'field': 'separation_deg'},
                        {'name': 'actions', 'label': 'Actions'},
                    ]

                    table = ui.table(columns=columns, rows=[], row_key='name').classes('w-full')

                    ui.button(t('open_in_aladin'), on_click=lambda: open_aladin_sky_map(ra, dec, fov=3.0)).props('flat color=primary')

                custom_name = ui.input(label=t('custom_description2')).classes("w-full mt-4")

                if objects:
                    reload( table, target, objects, astro_object_id, astro_group_id, custom_name)
                        
                    ui.update() 

                    # Bind the action
                    table.on('add_dso', on_add_dso)

                def save_custom_name():
                    description = custom_name.value.strip()
                    if description:
                        # Your logic to store/save the description
                        update_astro_object_description(conn, astro_object_id, description)
                        ui.notify(f"✅ Saved as: {description}", type="positive")
                    else:
                        ui.notify(t("please_description"), type="warning")

                with ui.row().classes("justify-end mt-4"):
                    ui.button(t('save'), on_click=save_custom_name).props('color=primary')
                    ui.button(t('close'), on_click=dialog.close).props('flat')

        dialog.open()