# components/i18n.py
"""
Dwarfium Scope Archive — Internationalization (i18n) engine.

Locale files live in components/locales/<lang>.py, each exporting:
    LANGUAGE_NAME = "🇩🇪 Deutsch"     # label shown in the language selector
    ENABLED       = True              # False while the translation is not ready
    TRANSLATIONS  = {...}             # dict[str, str]

Languages are discovered at startup from the locale files, so adding a
language only requires dropping a new file there with ENABLED = True —
no code change. Locale files are shipped next to the executable
(dist/components/locales/), so translators can work with the packaged
app: edit <lang>.py, set ENABLED = True and restart.

Usage:
    from components.i18n import t, set_language, get_language

    ui.label(t("save"))
    ui.button(t("cancel"))
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from nicegui import app

DEFAULT_LANGUAGE: str = "en"

# ── Locale file lookup ────────────────────────────────────────────────────────

def locale_dirs(subdir: str) -> list[Path]:
    """
    Candidate folders for components/<subdir>, in priority order.
    The folder next to the executable comes first so that locale files
    edited in the distribution override any copy bundled in the exe.
    """
    dirs = []
    if getattr(sys, "frozen", False):
        dirs.append(Path(sys.executable).parent / "components" / subdir)
        if hasattr(sys, "_MEIPASS"):
            dirs.append(Path(sys._MEIPASS) / "components" / subdir)
    dirs += [
        Path(__file__).parent / subdir,
        Path("components") / subdir,
        Path(subdir),
    ]
    return dirs


def find_locale_file(subdir: str, lang: str) -> Path | None:
    """Return the first existing components/<subdir>/<lang>.py, or None."""
    for d in locale_dirs(subdir):
        path = d / f"{lang}.py"
        if path.exists():
            return path
    return None


def load_locale_module(subdir: str, lang: str) -> ModuleType | None:
    """Execute components/<subdir>/<lang>.py and return it as a module, or None."""
    path = find_locale_file(subdir, lang)
    if path is None:
        print(f"[i18n] WARNING: {subdir}/{lang}.py not found. Tried:")
        for d in locale_dirs(subdir):
            print(f"  ❌  {(d / f'{lang}.py').resolve()}")
        return None
    try:
        spec = importlib.util.spec_from_file_location(f"{subdir}.{lang}", path)
        module = importlib.util.module_from_spec(spec)       # type: ignore[arg-type]
        spec.loader.exec_module(module)                      # type: ignore[union-attr]
        return module
    except Exception as e:
        print(f"[i18n] Failed to load {subdir}/{lang}.py from {path}: {e}")
        return None


# ── Locale cache ──────────────────────────────────────────────────────────────
_modules: dict[str, ModuleType | None] = {}


def _locale_module(lang: str) -> ModuleType | None:
    if lang not in _modules:
        _modules[lang] = load_locale_module("locales", lang)
    return _modules[lang]


def _load_locale(lang: str) -> dict[str, str]:
    """Return the TRANSLATIONS dict for *lang* (empty if unavailable)."""
    module = _locale_module(lang)
    return getattr(module, "TRANSLATIONS", {}) if module else {}


def _discover_languages() -> dict[str, str]:
    """
    Scan the locale folders and return {code: display name} for every
    enabled language. English is always available (fallback language).
    """
    codes = set()
    for d in locale_dirs("locales"):
        if d.is_dir():
            codes.update(p.stem for p in d.glob("*.py") if not p.stem.startswith("_"))

    languages: dict[str, str] = {}
    for code in sorted(codes | {DEFAULT_LANGUAGE}):
        module = _locale_module(code)
        if module is None:
            continue
        if code != DEFAULT_LANGUAGE and not getattr(module, "ENABLED", False):
            continue
        languages[code] = getattr(module, "LANGUAGE_NAME", code)
    return languages


# {code: display name} of the enabled languages, e.g. {"en": "🇬🇧 English", "fr": "🇫🇷 Français"}
AVAILABLE_LANGUAGES: dict[str, str] = _discover_languages()
SUPPORTED_LANGUAGES: list[str] = list(AVAILABLE_LANGUAGES)


# ── Public API ────────────────────────────────────────────────────────────────

def get_language() -> str:
    """Return the active language code (e.g. 'en', 'fr')."""
    try:
        lang = app.storage.general.get("language", DEFAULT_LANGUAGE)
        return lang if lang in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
    except Exception:
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
