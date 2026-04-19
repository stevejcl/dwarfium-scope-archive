from nicegui import native,ui,app,events
import sqlite3
from typing import Dict

from api.dwarf_backup_db import DB_NAME, connect_db, close_db, commit_db
from api.dwarf_backup_db_api import get_astro_objects, get_dso_name, get_dso_filtered, get_dso_registered, get_dso_description, update_astro_object_dso, export_associations, delete_unused_astro_objects, insert_default_groups

from components.menu import menu
from components.astro_object_associate import show_assign_dialog
from components.win_log import WinLog

@ui.page('/Catalog/')
async def dwarf_catalog():

    menu("Catalog Edition")
    await ui.context.client.connected()
    ui.context.catalog_app = CatalogApp(DB_NAME)
    # Defer load after page is fully connected — avoids drawer JS timeout
    ui.timer(0.5, ui.context.catalog_app.load_data, once=True)
    #ui.context.client.on_disconnect(lambda: logger.removeHandler(handler))

def _fetch_catalog_data(database):
    """Module-level function — safe for run.io_bound (no self, no conn to pickle)."""
    from api.dwarf_backup_db import connect_db, close_db
    from api.dwarf_backup_db_api import get_astro_objects
    conn = connect_db(database)
    try:
        return get_astro_objects(conn)
    finally:
        close_db(conn)


class CatalogApp:
    def __init__(self, database):
        self.database = database
        self.data = []
        self.build_ui()
        self.current_dso_assign = None

    def build_ui(self):
        self.conn = connect_db(self.database)

        # UI Components
        with ui.column().classes('w-full p-4'):
            ui.label('🔭 AstroObject to DSO Association').classes('text-2xl')
            with ui.row().classes('gap-4'):
                ui.button('Export Associations to CSV', on_click=self.on_export_click)
                ui.button('Delete Astro Objects not used anymore', on_click=self.on_delete_click)
            self.loading_spinner = ui.spinner(size='lg').classes('m-4')

            columns=[
                {'name': 'id', 'label': 'ID', 'field': 'id', 'sortable': True},
                {'name': 'name', 'label': 'Name', 'field': 'name', 'sortable': True},
                {'name': 'description', 'label': 'Description', 'field': 'description', 'sortable': True},
                {'name': 'dso', 'label': 'DSO', 'field': 'dso', 'sortable': True},
                {'name': 'actions', 'label': 'Actions', 'field': 'actions'},
            ]

            # Create the table
            self.table = ui.table(columns=columns, rows=[], row_key='id').classes('w-full')
            self.table.on('assign_dso', self.on_assign_dso)

    async def load_data(self):
        """Load catalog data in a thread so spinner renders first."""
        from nicegui import run
        db = self.database
        self.data = await run.io_bound(_fetch_catalog_data, db)
        self.reload()
        if hasattr(self, 'loading_spinner'):
            self.loading_spinner.set_visibility(False)

    # Export Button
    def on_export_click(self):
        csv_data = export_associations(self.conn)
        ui.download.content(csv_data, 'astroobject_dso_associations.csv')

    # Delete Button
    async def on_delete_click(self):

        await WinLog().show(
            "Confirm Deletion",
            "Are you sure you want to delete all the data?",
            self.ok_confirm_and_delete
        )

    def ok_confirm_and_delete(self):
        if delete_unused_astro_objects(self.conn):
            ui.notify('AstroObject data have been purged!')
        else:
            ui.notify('Error occurs during AstroObject purge!')
        # recreate default if need
        insert_default_groups(self.conn)

        self.reload()
        ui.update()  # refresh page/table

    def get_row_by_id(self, ao_id):
        for ao in self.data:
            if ao[0] == ao_id:
                return ao
        return None

    # Load data into the table
    @ui.refreshable
    def reload(self):
        self.table.rows.clear()
        if not self.data:
            self.data = get_astro_objects(self.conn)

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
        self.table.update()

        # Use full row slot
        if not self.table.slots.get('body'):
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
            show_assign_dialog(self.conn, ao, on_done=lambda: (self.reload(),ui.update()))

    def show_assign_dialog_local(self, astro_object_row):
        with ui.dialog() as dialog, ui.card().style('width: 600px; max-width: none'):
            ui.label(f"Assign DSO to AstroObject ID {astro_object_row[1]}")

            # Filters & Search Inputs
            self.current_dso_assign = str(astro_object_row[3])
            search_input = ui.input(label='Search (designation, name, constellation, type)', on_change=lambda e: update_dso_list()).classes('w-full')
            constellation_filter = ui.input(label='Constellation (exact)', on_change=lambda e: update_dso_list()).classes('w-full')
            type_filter = ui.input(label='Type (exact)', on_change=lambda e: update_dso_list()).classes('w-full')

            dso_select = ui.select({}, label='Select DSO', on_change=lambda e: update_dso_value()).classes('w-full')
            # Allow user to enter custom DSO
            custom_dso_input = ui.input(label='Edit or enter custom description', value=astro_object_row[2]).classes('w-full')

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
                    dso = get_dso_registered(self.conn, dso_id)
                    if dso:
                        auto_description = f"{dso[2].split(',')[0].strip()} ({dso[3]}) in {dso[4]}, size: {dso[5] or 'N/A'}, mag: {dso[6] or 'N/A'}"
                    else:
                        auto_description = ''

                    # Compare avec l'input de l'utilisateur
                    final_description = custom_dso_input.value.strip()
                    if final_description == auto_description:
                        final_description = auto_description  # pas changé

                    update_astro_object_dso(self.conn, astro_object_row[0], int(dso_select.value), final_description)

                    ui.notify('DSO assigned/updated!')
                    dialog.close()
                    self.reload()

                else:
                    ui.notify('Please select a DSO first.', color='red')


            def confirm():
                if dso_select.value:
                    update_astro_object_dso(self.conn, astro_object_row[0], int(dso_select.value), custom_dso_input.value)
                    ui.notify('DSO assigned/updated!')
                    dialog.close()
                    self.reload()

                else:
                    ui.notify('Please select a DSO first.', color='red')

            with ui.row():
                ui.button('Confirm', on_click=confirm)
                ui.button('Cancel', on_click=dialog.close)

        dialog.open()