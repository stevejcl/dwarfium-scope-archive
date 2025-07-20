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

def show_unknown_target_dialog(conn: sqlite3.Connection, dwarf_data_row, dso_catalog, only_unknown=True, on_done = None):
    ra = hms_to_hours(dwarf_data_row[15]) * 15  # convert hours to degrees
    dec = dms_to_degrees(dwarf_data_row[14])
    target = dwarf_data_row[13]
    astro_id = dwarf_data_row[16]
    astro_group_id = dwarf_data_row[17]
    dwarf_data_id = dwarf_data_row[0]

    if only_unknown and target.lower() != "unknown":
        ui.notify("⚠️ Target is already known: {target}", type="warning")
        return None, f"Target is already known: {target}"

    old_description = get_astro_object_description(conn, astro_id)
    shared['custom_name'] = old_description 
    # Use your local catalog
    objects, error = find_nearby_dso_from_json(ra, dec, dso_catalog)

    def handle_add(conn, target: str, name: str, designation: str, astro_id, astro_group_id):
        print(f"try update: {target} to {name}")
        if astro_id:
            # get DSO
            dso_id = get_dso_registered_by_designation(conn, designation)
            if dso_id:
                update_astro_object_dso(conn, astro_id, int(dso_id), "")
                new_description = get_astro_object_description(conn, astro_id)
                shared['custom_name'] = new_description 
                ui.notify('DSO assigned/updated!')
                if on_done:
                    on_done()
            else:
                ui.notify("❌ Failed to update object", type='negative')

    def on_add_dso( msg: Dict):
        print(msg.args)
        target, name, designation, astro_id, astro_group_id = msg.args
        handle_add(conn, target, name, designation, astro_id, astro_group_id)

    if error:
        ui.label(error).classes('text-red-600')
    elif not objects:
        ui.label("❌ No nearby DSO found in your catalog").classes('text-red-600')
        show_dso_dialog(target, ra, dec, objects, conn, astro_id, astro_group_id, old_description, on_add_dso, on_done)
    else:
        show_dso_dialog(target, ra, dec, objects, conn, astro_id, astro_group_id, old_description, on_add_dso, on_done)

def show_dso_dialog(target, ra, dec, objects, conn, astro_id, astro_group_id, old_description, on_add_dso, on_done = None):
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
                    update_astro_object_description(conn, astro_id, description)
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
                reload( table, target, objects, astro_id, astro_group_id)
                        
                ui.update() 

                # Bind the action
                table.on('add_dso', on_add_dso)

            ui.button('Close', on_click=dialog.close).props('color=primary')

    dialog.open()

# Load data into the table
@ui.refreshable
def reload(table, target, objects, astro_id, astro_group_id):
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
            'astro_id': astro_id,
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
                @click="$parent.$emit('add_dso', props.row.target, props.row.name, props.row.designation, props.row.astro_id, props.row.astro_group_id)"
              />
            </q-td>
          </q-tr>
        ''')

        ui.update() 

def show_assign_dialog(conn: sqlite3.Connection , astro_object_row, on_done=None):
    with ui.dialog() as dialog, ui.card().style('width: 600px; max-width: none'):
        ui.label(f"Assign DSO to AstroObject ID {astro_object_row[1]}")

        # Filters & Search Inputs
        current_dso_assign = str(astro_object_row[3])
        search_input = ui.input(label='Search (designation, name, constellation, type)', on_change=lambda e: update_dso_list()).classes('w-full')
        constellation_filter = ui.input(label='Constellation (exact)', on_change=lambda e: update_dso_list()).classes('w-full')
        type_filter = ui.input(label='Type (exact)', on_change=lambda e: update_dso_list()).classes('w-full')

        dso_select = ui.select({}, label='Select DSO', on_change=lambda e: update_dso_value(current_dso_assign)).classes('w-full')
        # Allow user to enter custom DSO
        custom_dso_input = ui.input(label='Edit or enter custom description', value=astro_object_row[2]).classes('w-full')

        def update_dso_value(current_dso_assign):
            if dso_select.value and dso_select.value != current_dso_assign:
                print(f"description updated")
                custom_dso_input.value = get_dso_description(conn, dso_select.value)
                current_dso_assign = dso_select.value

        def update_dso_list():
            filtered = get_dso_filtered(
                conn,
                search=search_input.value,
                constellation=constellation_filter.value or None,
                dso_type=type_filter.value or None
            )
            options = {str(dso[0]): f"{dso[2]} ({dso[3]}, {dso[4]})" for dso in filtered}
            dso_select.set_options(options)

        def update_dso_data():
            registered = get_dso_registered(
                conn,
                astro_object_row[3],
            )
            if registered:
                options = {str(registered[0]): f"{registered[2]} ({registered[3]}, {registered[4]})"}
                dso_select.set_options(options)
                dso_select.value = str(registered[0])
            else:
               update_dso_list()

        update_dso_data()

        def confirm():
            if dso_select.value:
                dso_id = int(dso_select.value)

                # Génère la description automatiquement
                dso = get_dso_registered(conn, dso_id)
                if dso:
                    auto_description = f"{dso[2].split(',')[0].strip()} ({dso[3]}) in {dso[4]}, size: {dso[5] or 'N/A'}, mag: {dso[6] or 'N/A'}"
                else:
                    auto_description = ''

                # Compare avec l'input de l'utilisateur
                final_description = custom_dso_input.value.strip()
                if final_description == auto_description:
                    final_description = auto_description  # pas changé

                update_astro_object_dso(conn, astro_object_row[0], int(dso_select.value), final_description)

                ui.notify('DSO assigned/updated!')
                close()
            else:
                ui.notify('Please select a DSO first.', color='red')


        def close():
                dialog.close()
                # back to parent function!
                if on_done:
                    on_done()

        with ui.row():
            ui.button('Confirm', on_click=confirm)
            ui.button('Cancel', on_click=dialog.close)

    dialog.open()

def show_dso_dialog_old(target, ra, dec, objects, conn, astro_id, astro_group_id, old_description, on_add_dso, on_done = None):

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
                        update_astro_object_description(conn, astro_id, description)
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
                    reload( table, target, objects, astro_id, astro_group_id, custom_name)
                        
                    ui.update() 

                    # Bind the action
                    table.on('add_dso', on_add_dso)

                def save_custom_name():
                    description = custom_name.value.strip()
                    if description:
                        # Your logic to store/save the description
                        update_astro_object_description(conn, astro_id, description)
                        ui.notify(f"✅ Saved as: {description}", type="positive")
                    else:
                        ui.notify("⚠️ Please enter a description", type="warning")

                with ui.row().classes("justify-end mt-4"):
                    ui.button('💾 Save', on_click=save_custom_name).props('color=primary')
                    ui.button('Close', on_click=dialog.close).props('flat')

        dialog.open()

