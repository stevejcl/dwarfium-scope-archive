from nicegui import native,ui,app,events
import sqlite3
from typing import Dict

from api.dwarf_backup_db import DB_NAME, connect_db, close_db, init_db, commit_db
from api.dwarf_backup_db_api import get_astro_objects, get_dso_name, get_dso_filtered, get_dso_registered, get_dso_description, update_astro_object, export_associations

from components.menu import menu

@ui.page('/Catalog/')
def dwarf_catalog():

    menu("Catalog Edition")

    # Launch the GUI with the parameters
    ui.context.catalog_app =  CatalogApp(DB_NAME)
    #ui.context.client.on_disconnect(lambda: logger.removeHandler(handler))

class CatalogApp:
    def __init__(self, database):
        self.database = database
        self.data = []
        self.build_ui()
        self.current_dso_assign = None

    def build_ui(self):
        self.conn = connect_db(self.database)

        # UI Components
        with ui.row().classes('w-full h-screen items-center justify-center'):
            ui.label('🔭 AstroObject to DSO Association').classes('text-2xl')
            ui.button('Export Associations to CSV', on_click=self.on_export_click).classes('my-4')

            columns=[
                {'name': 'id', 'label': 'ID', 'field': 'id', 'sortable': True},
                {'name': 'name', 'label': 'Name', 'field': 'name', 'sortable': True},
                {'name': 'description', 'label': 'Description', 'field': 'description', 'sortable': True},
                {'name': 'dso', 'label': 'DSO', 'field': 'dso', 'sortable': True},
                {'name': 'actions', 'label': 'Actions', 'field': 'actions'},
            ]

            # Create the table
            self.table = ui.table(columns=columns, rows=[], row_key='id').classes('w-full')

            self.reload()

            # Bind the action
            self.table.on('assign_dso', self.on_assign_dso)

    # Export Button
    def on_export_click(self):
        csv_data = export_associations(self.conn)
        ui.download.content(csv_data, 'astroobject_dso_associations.csv')

    def get_row_by_id(self, ao_id):
        for ao in self.data:
            if ao[0] == ao_id:
                return ao
        return None

    # Load data into the table
    @ui.refreshable
    def reload(self):
        self.table.rows.clear()
        self.data = get_astro_objects(self.conn)  # reload from source

        for ao in self.data:
            self.table.rows = [{
                'id': ao[0],
                'name': ao[1],
                'description': ao[2],
                'dso': get_dso_name(self.conn, ao[3]),
                'actions': '',
            }
            for ao in self.data
        ]

        # Use full row slot
        self.table.add_slot('body', r'''
          <q-tr :props="props">
            <q-td key="id" :props="props">
              {{ props.row.id }}
            </q-td>
            <q-td key="name" :props="props">
              {{ props.row.name }}
            </q-td>
            <q-td key="description" :props="props">
              {{ props.row.description }}
            </q-td>
            <q-td key="dso" :props="props">
              {{ props.row.dso }}
            </q-td>
            <q-td key="actions" :props="props">
              <q-btn
                dense
                size="sm"
                label="Assign/Change DSO"
                @click="$parent.$emit('assign_dso', props.row.id)"
              />
            </q-td>
          </q-tr>
        ''')

        ui.update() 


    def on_assign_dso(self, msg: Dict):
        ao_id = msg.args
        ao = self.get_row_by_id(ao_id)
        print(ao)
        if ao:
            self.show_assign_dialog(ao)

    def show_assign_dialog(self, astro_id):
        with ui.dialog() as dialog, ui.card().style('width: 600px; max-width: none'):
            ui.label(f"Assign DSO to AstroObject ID {astro_id[1]}")

            # Filters & Search Inputs
            self.current_dso_assign = str(astro_id[3])
            search_input = ui.input(label='Search (designation, name, constellation, type)', on_change=lambda e: update_dso_list()).classes('w-full')
            constellation_filter = ui.input(label='Constellation (exact)', on_change=lambda e: update_dso_list()).classes('w-full')
            type_filter = ui.input(label='Type (exact)', on_change=lambda e: update_dso_list()).classes('w-full')

            dso_select = ui.select({}, label='Select DSO', on_change=lambda e: update_dso_value()).classes('w-full')
            # Allow user to enter custom DSO
            custom_dso_input = ui.input(label='Edit or enter custom description', value=astro_id[2]).classes('w-full')

            def update_dso_value():
                if dso_select.value and dso_select.value != self.current_dso_assign:
                    print(f"description updated")
                    custom_dso_input.value = get_dso_description(self.conn, dso_select.value)
                    self.current_dso_assign = dso_select.value

            def update_dso_list():
                filtered = get_dso_filtered(
                    self.conn,
                    search=search_input.value,
                    constellation=constellation_filter.value or None,
                    dso_type=type_filter.value or None
                )
                options = {str(dso[0]): f"{dso[2]} ({dso[3]}, {dso[4]})" for dso in filtered}
                dso_select.set_options(options)

            def update_dso_data():
                registered = get_dso_registered(
                    self.conn,
                    astro_id[3],
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
                    dso = get_dso_registered(self.conn, dso_id)
                    if dso:
                        auto_description = f"{dso[2].split(',')[0].strip()} ({dso[3]}) in {dso[4]}, size: {dso[5] or 'N/A'}, mag: {dso[6] or 'N/A'}"
                    else:
                        auto_description = ''

                    # Compare avec l'input de l'utilisateur
                    final_description = custom_dso_input.value.strip()
                    if final_description == auto_description:
                        final_description = auto_description  # pas changé

                    update_astro_object(self.conn, astro_id[0], int(dso_select.value))

                    ui.notify('DSO assigned/updated!')
                    dialog.close()
                    self.reload()
                    ui.update()  # refresh page/table

                else:
                    ui.notify('Please select a DSO first.', color='red')


            def confirm():
                if dso_select.value:
                    update_astro_object(self.conn, astro_id[0], int(dso_select.value), custom_dso_input.value)
                    ui.notify('DSO assigned/updated!')
                    dialog.close()
                    self.reload()
                    ui.update()  # refresh page/table

                else:
                    ui.notify('Please select a DSO first.', color='red')

            with ui.row():
                ui.button('Confirm', on_click=confirm)
                ui.button('Cancel', on_click=dialog.close)

        dialog.open()

