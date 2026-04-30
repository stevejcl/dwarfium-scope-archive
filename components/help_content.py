# components/help_content.py
"""
Dwarfium Scope Archive — Inline help engine.

Help content lives in components/help_locales/<lang>.py, each exporting a
HELP dict[str, dict[str, str]] keyed by route path.

Adding a new language:
  1. Copy help_locales/en.py to help_locales/<code>.py
  2. Translate each 'title' and 'content' value
  3. Add the code to SUPPORTED_HELP_LANGUAGES below

Usage (unchanged from before):
    from components.help_content import get_help
    entry = get_help('/Dwarf')   # {'title': ..., 'content': ...}
"""

import importlib.util
from pathlib import Path

from nicegui import app

# ── Supported languages ───────────────────────────────────────────────────────
# Add a new code here once its help_locales/<code>.py file is ready.
SUPPORTED_HELP_LANGUAGES: list[str] = ["en", "fr"]
DEFAULT_HELP_LANGUAGE: str = "en"

# ── Locale cache ──────────────────────────────────────────────────────────────
_help_cache: dict[str, dict[str, dict[str, str]]] = {}


def _load_help_locale(lang: str) -> dict[str, dict[str, str]]:
    """Load and cache the HELP dict for *lang*."""
    if lang in _help_cache:
        return _help_cache[lang]
    try:
        locale_path = Path(__file__).parent / "help_locales" / f"{lang}.py"
        spec = importlib.util.spec_from_file_location(f"help_locales.{lang}", locale_path)
        module = importlib.util.module_from_spec(spec)       # type: ignore[arg-type]
        spec.loader.exec_module(module)                      # type: ignore[union-attr]
        _help_cache[lang] = module.HELP
    except Exception:
        _help_cache[lang] = {}
    return _help_cache[lang]


# ── Public API ────────────────────────────────────────────────────────────────

def _resolve(entry: dict[str, str], lang: str) -> dict[str, str]:
    """
    Replace {t:key} placeholders in help content with translated strings.
    This allows help text to reference UI button labels without duplication:
        **{t:add_dwarf}**  →  **➕ Add New Dwarf**  (EN)
                           →  **➕ Ajouter un Dwarf**  (FR)
    """
    import re
    from components.i18n import t as _t

    def _sub(m: re.Match) -> str:
        return _t(m.group(1))

    pattern = re.compile(r'\{t:([^}]+)\}')
    return {
        k: pattern.sub(_sub, v) if isinstance(v, str) else v
        for k, v in entry.items()
    }


def get_help(route: str) -> dict[str, str]:
    """
    Return {'title': ..., 'content': ...} for *route* in the active language.
    Falls back to English if the route is not translated yet.
    Returns an empty dict if the route is unknown in both languages.
    """
    try:
        lang = app.storage.general.get("language", DEFAULT_HELP_LANGUAGE)
        if lang not in SUPPORTED_HELP_LANGUAGES:
            lang = DEFAULT_HELP_LANGUAGE
    except Exception:
        lang = DEFAULT_HELP_LANGUAGE

    if lang != DEFAULT_HELP_LANGUAGE:
        locale = _load_help_locale(lang)
        entry = locale.get(route)
        if entry:
            return _resolve(entry, lang)

    # Fall back to English
    en_locale = _load_help_locale(DEFAULT_HELP_LANGUAGE)
    entry = en_locale.get(route, {})
    return _resolve(entry, DEFAULT_HELP_LANGUAGE) if entry else {}


# Keep backward compatibility for any code that imports help_content directly
help_content = _load_help_locale(DEFAULT_HELP_LANGUAGE)
