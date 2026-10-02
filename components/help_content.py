# components/help_content.py
"""
Dwarfium Scope Archive — Inline help engine.

Help content lives in components/help_locales/<lang>.py, each exporting a
HELP dict[str, dict[str, str]] keyed by route path.

The help language follows the UI language (see components/i18n.py):
help_locales/<code>.py is used when that language is enabled in
locales/<code>.py. Routes missing from it fall back to English.

Adding a new language:
  1. Copy help_locales/en.py to help_locales/<code>.py
  2. Translate each 'title' and 'content' value

Usage (unchanged from before):
    from components.help_content import get_help
    entry = get_help('/Dwarf')   # {'title': ..., 'content': ...}
"""

from components.i18n import get_language, load_locale_module

DEFAULT_HELP_LANGUAGE: str = "en"

# ── Locale cache ──────────────────────────────────────────────────────────────
_help_cache: dict[str, dict[str, dict[str, str]]] = {}


def _load_help_locale(lang: str) -> dict[str, dict[str, str]]:
    """Load and cache the HELP dict for *lang*."""
    if lang not in _help_cache:
        module = load_locale_module("help_locales", lang)
        _help_cache[lang] = getattr(module, "HELP", {}) if module else {}
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
    lang = get_language()

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
