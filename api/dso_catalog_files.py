"""The two DSO catalog files read at startup.

- db/dso_catalog.json: the shared catalog produced by Dwarfium's
  notebook (notebooks/5_create_catalogues.ipynb), never modified here.
- db/catalog_add_on.json: objects added on top of it, today by Astro
  Dwarf Session (targets sent from its /catalog page, when the user ticks
  "keep these targets in the catalog" - see astro_dwarf_session's
  components/catalog_add_on.py). Same schema, plus "source" and "addedAt",
  which are ignored here. Optional.

The shared catalog wins: an add-on object whose designation is already
in dso_catalog.json is skipped."""
import json
import os

CATALOG_FILE = os.path.join("db", "dso_catalog.json")
ADD_ON_CATALOG_FILE = os.path.join("db", "catalog_add_on.json")


def _read_json_list(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        return []
    return data if isinstance(data, list) else []


def add_on_path_for(catalog_path):
    """catalog_add_on.json in the same folder as `catalog_path`."""
    return os.path.join(os.path.dirname(catalog_path), os.path.basename(ADD_ON_CATALOG_FILE))


def load_catalog_entries(catalog_path=CATALOG_FILE):
    """dso_catalog.json's entries followed by catalog_add_on.json's new
    ones (next to it). Raises like json.load if dso_catalog.json itself
    is missing or invalid, as before."""
    with open(catalog_path, 'r', encoding='utf-8') as f:
        base = json.load(f)
    known = {obj.get('designation') for obj in base}
    add_on = [
        obj for obj in _read_json_list(add_on_path_for(catalog_path))
        if isinstance(obj, dict) and obj.get('designation') and obj.get('designation') not in known
    ]
    return base + add_on


def latest_mtime(catalog_path=CATALOG_FILE):
    """Most recent modification time of the two files (0 if neither)."""
    times = [
        os.path.getmtime(p)
        for p in (catalog_path, add_on_path_for(catalog_path))
        if os.path.exists(p)
    ]
    return max(times, default=0)
