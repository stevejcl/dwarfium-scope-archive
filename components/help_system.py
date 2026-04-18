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

    # Try exact match first, then strip/add trailing slash
    data = help_content.get(path) or help_content.get(path.rstrip('/')) or help_content.get(path + '/') or {
        'title': 'Help',
        'content': 'No help available for this page.'
    }

    help_drawer.clear()
    with help_drawer:
        ui.label(data['title']).classes('text-subtitle1 font-bold')
        ui.separator()
        ui.markdown(data['content']).style('font-size: 1.5rem; line-height: 1.5;').classes('help-content')

    ui.add_css("""
        .help-content h1, .help-content h2 { font-size: 1rem !important; font-weight: 600; margin: 0.6rem 0 0.3rem; }
        .help-content h3 { font-size: 0.9rem !important; font-weight: 600; margin: 0.5rem 0 0.2rem; }
        .help-content p, .help-content li { font-size: 0.85rem; }
        .help-content ul, .help-content ol { padding-left: 1.2rem; }
        .help-content pre, .help-content code { white-space: pre-wrap; word-break: break-all; font-size: 0.78rem; }
    """)

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