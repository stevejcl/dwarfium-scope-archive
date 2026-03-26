from nicegui import ui, app

from components.help_content import help_content

help_drawer = None
timer_drawer = None

def register_drawer():
    global help_drawer, timer_drawer

    help_drawer = ui.right_drawer().classes('w-96')

    help_drawer.value = app.storage.user.get('help_open', False)

    timer_drawer =  ui.timer(0.3, lambda: refresh_if_open(), once=True)

def refresh_if_open():
    global help_drawer, timer_drawer

    if help_drawer and help_drawer.value:
        build_help()

def build_help():
    global help_drawer

    path = ui.context.client.page.path

    data = help_content.get(path, {
        'title': 'Help',
        'content': 'No help available for this page.'
    })

    help_drawer.clear()
    with help_drawer:
        ui.label(data['title']).classes('text-h6')
        ui.separator()
        ui.markdown(data['content'])

def open_help():
    global help_drawer

    if help_drawer is None:
        return

    # toggle state
    new_state = not help_drawer.value
    app.storage.user['help_open'] = new_state

    if new_state:
        build_help()
        help_drawer.value = True
    else:
        help_drawer.value = False