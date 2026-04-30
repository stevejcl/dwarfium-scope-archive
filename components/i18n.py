# components/i18n.py
"""
Dwarfium Scope Archive — Internationalization (i18n) engine.

Locale files live in components/locales/<lang>.py, each exporting a
TRANSLATIONS dict[str, str].  Adding a new language is as simple as
dropping a new file there and adding the code to SUPPORTED_LANGUAGES.

Usage:
    from components.i18n import t, set_language, get_language

    ui.label(t("save"))
    ui.button(t("cancel"))
"""

import importlib.util
from pathlib import Path
from nicegui import app

# ── Supported languages ───────────────────────────────────────────────────────
# Add a new language code here once its locales/<code>.py file is ready.
SUPPORTED_LANGUAGES: list[str] = ["en", "fr"]
DEFAULT_LANGUAGE: str = "en"

# ── Locale cache ──────────────────────────────────────────────────────────────
_cache: dict[str, dict[str, str]] = {}


def _load_locale(lang: str) -> dict[str, str]:
    """Load and cache the TRANSLATIONS dict for *lang*."""
    if lang in _cache:
        return _cache[lang]
    # Try multiple base paths to support running as script, frozen exe, or
    # from a working directory different from the project root (Windows .exe).
    candidates = [
        Path(__file__).parent / "locales" / f"{lang}.py",          # normal: components/locales/
        Path(__file__).parent.parent / "components" / "locales" / f"{lang}.py",  # one level up
        Path("components") / "locales" / f"{lang}.py",              # relative to CWD
        Path("locales") / f"{lang}.py",                             # flat layout
    ]
    for locale_path in candidates:
        if not locale_path.exists():
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"locales.{lang}", locale_path)
            module = importlib.util.module_from_spec(spec)       # type: ignore[arg-type]
            spec.loader.exec_module(module)                      # type: ignore[union-attr]
            _cache[lang] = module.TRANSLATIONS
            return _cache[lang]
        except Exception as e:
            print(f"[i18n] Failed to load locale '{lang}' from {locale_path}: {e}")

    print(f"[i18n] WARNING: locale '{lang}' not found in any candidate path:")
    for p in candidates:
        print(f"  {'✅' if p.exists() else '❌'}  {p.resolve()}")
    _cache[lang] = {}
    return _cache[lang]


# ── Public API ────────────────────────────────────────────────────────────────

def get_language() -> str:
    """Return the active language code (e.g. 'en', 'fr')."""
    try:
        lang = app.storage.general.get("language", DEFAULT_LANGUAGE)
        return lang if lang in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
    except Exception:
        # app.storage not yet available (module import time or frozen exe startup)
        return DEFAULT_LANGUAGE


def set_language(lang: str) -> None:
    """Persist the language choice. Locales are already cached at first use."""
    if lang in SUPPORTED_LANGUAGES:
        app.storage.general["language"] = lang


def t(key: str, **kwargs) -> str:
    """
    Translate *key* to the active language.

    Falls back to English, then returns the raw key if still not found.
    Supports str.format()-style placeholders:  t("save")  or  t("target_known", target="M42")
    """
    lang = get_language()
    locale = _load_locale(lang)
    text = locale.get(key)
    if text is None:
        # Fall back to English
        en_locale = _load_locale(DEFAULT_LANGUAGE)
        text = en_locale.get(key, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, ValueError):
            pass
    return text


def t_list(keys: list[str]) -> list[str]:
    """Translate a list of keys."""
    return [t(k) for k in keys]
