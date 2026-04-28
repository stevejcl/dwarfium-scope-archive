from nicegui import ui, events
import sqlite3

from astroquery.simbad import Simbad
from astropy.coordinates import SkyCoord
from astropy import units as u

from api.dwarf_backup_db_api import get_dso_filtered, get_dso_registered, get_dso_description, get_dso_registered_by_designation
from api.dwarf_backup_db_api import get_astro_object_description, update_astro_object_dso, update_astro_object_description
from api.dwarf_backup_fct import preprocess_dso_catalog_json, hms_to_hours, dms_to_degrees, hours_to_hms, deg_to_dms

import webbrowser
from typing import Dict

from dataclasses import dataclass
from typing import Optional

@dataclass
class DwarfData:
    dwarf_data_id: Optional[int] = None
    target: Optional[str] = None
    dec: Optional[str] = None
    ra: Optional[str] = None
    astro_object_id: Optional[int] = None
    astro_group_id: Optional[int] = None

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
                astro_object_id=row[16],
                astro_group_id=row[17],
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

def show_unknown_target_dialog(conn: sqlite3.Connection, dwarf_data: DwarfData, dso_catalog, only_unknown=True, on_done = None):
    ra = hms_to_hours(dwarf_data.ra) * 15  # convert hours to degrees
    dec = dms_to_degrees(dwarf_data.dec)
    target = dwarf_data.target
    astro_object_id = dwarf_data.astro_object_id
    astro_group_id = dwarf_data.astro_group_id
    dwarf_data_id = dwarf_data.dwarf_data_id

    if only_unknown and target.lower() != "unknown" and target.lower() != "mosaic_unknown" and target.lower() != "manual":
        ui.notify("⚠️ Target is already known: {target}", type="warning")
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
                ui.notify('DSO assigned/updated!')
                if on_done:
                    on_done()
            else:
                ui.notify("❌ Failed to update object", type='negative')

    def on_add_dso( msg: Dict):
        print(msg.args)
        target, name, designation, astro_object_id, astro_group_id = msg.args
        handle_add(conn, target, name, designation, astro_object_id, astro_group_id)

    if error:
        ui.label(error).classes('text-red-600')
    elif not objects:
        ui.label("❌ No nearby DSO found in your catalog").classes('text-red-600')
        show_dso_dialog(target, ra, dec, objects, conn, astro_object_id, astro_group_id, old_description, on_add_dso, on_done)
    else:
        show_dso_dialog(target, ra, dec, objects, conn, astro_object_id, astro_group_id, old_description, on_add_dso, on_done)

def show_dso_dialog(target, ra, dec, objects, conn, astro_object_id, astro_group_id, old_description, on_add_dso, on_done = None):
    with ui.dialog() as dialog:
        with ui.card().classes("w-full p-4").style("max-width: 2600px; margin: auto"):
            ui.label(f'🔭 Target: {target} - RA: {hours_to_hms(ra/15)}, DEC: {deg_to_dms(dec)}').classes('text-lg font-bold')

            if not objects:
                ui.label("❌ No nearby DSO found in your catalog").classes('text-red-600')
            else:
                columns = [
                    {'name': 'name', 'label': 'Object', 'field': 'name'},
                    {'name': 'type', 'label': 'Type', 'field': 'type'},
                    {'name': 'ra', 'label': 'RA (H)', 'field': 'ra'},
                    {'name': 'dec', 'label': 'DEC (°)', 'field': 'dec'},
                    {'name': 'separation_deg', 'label': 'Δθ (°)', 'field': 'separation_deg'},
                    {'name': 'actions', 'label': 'Actions'},
                ]

                table = ui.table(columns=columns, rows=[], row_key='name').classes('w-full')

                ui.button('🌌 Open in Aladin', on_click=lambda: open_aladin_sky_map(ra, dec, fov=3.0)).props('flat color=primary')

            def save_custom_name():
                description = custom_name.value.strip()
                if description:
                    update_astro_object_description(conn, astro_object_id, description)
                    #shared['custom_name'] = description 
                    ui.notify(f"✅ Saved as: {description}", type="positive")
                    if on_done:
                        on_done()
                else:
                    ui.notify("⚠️ Please enter a description", type="warning")

            with ui.row().classes("justify-end mt-4"):
                custom_name = ui.input(label='🔤 Enter a custom description', value=old_description).bind_value(shared, 'custom_name').classes('mt-2').style('width: 600px; ; max-width: none')
                ui.button('💾 Save', on_click=save_custom_name).props('color=primary').classes("mt-4")

            if objects:
                reload( table, target, objects, astro_object_id, astro_group_id)
                        
                ui.update() 

                # Bind the action
                table.on('add_dso', on_add_dso)

            ui.button('Close', on_click=dialog.close).props('color=primary')

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
            ui.button('Confirm', on_click=confirm)
            ui.button('Cancel', on_click=dialog.close)

    dialog.open()

def show_dso_dialog_old(target, ra, dec, objects, conn, astro_object_id, astro_group_id, old_description, on_add_dso, on_done = None):

    if error:
        ui.label(error).classes('text-red-600')
    elif not objects:
        ui.label("❌ No nearby DSO found in your catalog").classes('text-red-600')
        with ui.dialog() as dialog:
            with ui.card().classes("w-full p-4").style("max-width: 600px; margin: auto"):
                ui.label(f'🔭 Target: {target} - RA: {hours_to_hms(ra/15)}, DEC: {deg_to_dms(dec)}').classes('text-lg font-bold')
                ui.label("❌ No nearby DSO found in your catalog").classes('text-red-600')
                ui.button('🌌 Open in Aladin', on_click=lambda: open_aladin_sky_map(ra, dec, fov=3.0)).props('flat color=primary')

                custom_name = ui.input(label='🔤 Enter a custom description', value=old_description).classes("w-full mt-4")

                def save_custom_name():
                    description = custom_name.value.strip()
                    if description:
                        # Your logic to store/save the description
                        update_astro_object_description(conn, astro_object_id, description)
                        ui.notify(f"✅ Saved as: {description}", type="positive")
                    else:
                        ui.notify("⚠️ Please enter a description", type="warning")

                with ui.row().classes("justify-end mt-4"):
                    ui.button('💾 Save', on_click=save_custom_name).props('color=primary')
                    ui.button('Close', on_click=dialog.close).props('flat')
        dialog.open()
    else:
        with ui.dialog() as dialog:
            with ui.card().classes("w-full p-4").style("max-width: 2600px; margin: auto"):
                ui.label(f'🔭 Target: {target} - RA: {hours_to_hms(ra/15)}, DEC: {deg_to_dms(dec)}').classes('text-lg font-bold')

                if not objects:
                    ui.label("❌ No nearby DSO found in your catalog").classes('text-red-600')
                else:
                    columns=[
                        {'name': 'name', 'label': 'Object', 'field': 'name'},
                        {'name': 'type', 'label': 'Type', 'field': 'type'},
                        {'name': 'ra', 'label': 'RA (H)', 'field': 'ra'},
                        {'name': 'dec', 'label': 'DEC (°)', 'field': 'dec'},
                        {'name': 'separation_deg', 'label': 'Δθ (°)', 'field': 'separation_deg'},
                        {'name': 'actions', 'label': 'Actions'},
                    ]

                    table = ui.table(columns=columns, rows=[], row_key='name').classes('w-full')

                    ui.button('🌌 Open in Aladin', on_click=lambda: open_aladin_sky_map(ra, dec, fov=3.0)).props('flat color=primary')

                custom_name = ui.input(label='🔤 Enter a custom description').classes("w-full mt-4")

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
                        ui.notify("⚠️ Please enter a description", type="warning")

                with ui.row().classes("justify-end mt-4"):
                    ui.button('💾 Save', on_click=save_custom_name).props('color=primary')
                    ui.button('Close', on_click=dialog.close).props('flat')

        dialog.open()

