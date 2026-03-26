from nicegui import ui, app

help_content = {
    '/': {
        'title': 'Home',
        'content': '''
## Welcome

This application allows you to manage your Dwarf telescope sessions.

## Main features
- Import sessions
- Manage Dwarfs
- Explore data
'''
    },
    '/Dwarf': {
        'title': 'Dwarf Configuration',
        'content': '''
## Purpose
Manage your Dwarf devices.

## Actions
- Add a new Dwarf
- Select an existing one
- Configure storage directory

## Tips
Make sure your USB folder is accessible.
'''
    },
}

