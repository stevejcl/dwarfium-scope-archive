#!/usr/bin/env python3
"""
tools/check_i18n.py — Audit tool for the i18n locale files.
Run from the project root:

    python tools/check_i18n.py                 # checks all locales vs English
    python tools/check_i18n.py --lang fr        # checks only French
    python tools/check_i18n.py --lang de        # checks only German

Reports per locale:
  - Keys missing (need translation)
  - Orphan keys  (no longer exist in English — safe to remove)
  - Untranslated entries (value still equals English, excluding whitelist)

Global report:
  - Keys used in source code but absent from the English reference locale
"""

import argparse
import importlib.util
import re
import sys
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT       = Path(__file__).parent.parent
LOCALE_DIR = ROOT / "components" / "locales"
SCAN_DIRS  = [ROOT / "pages", ROOT / "components", ROOT / "api", ROOT / "cli"]

# Keys intentionally identical across all languages (technical terms / proper nouns)
WHITELIST_SAME: set[str] = {
    "DWARF_LOCAL_PATH", "api_key", "session", "session_date", "original",
    "lang_label", "description", "gain_label", "date_label", "notes_label",
    "type_label", "restack", "archive_mode", "col_type", "col_mag",
    "temp_label", "dwarf_label", "session_label", "settings_version", "type_exact",
}

SEP = "─" * 70


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_locale(path: Path) -> dict[str, str]:
    """Load a locale file and return its TRANSLATIONS dict."""
    spec = importlib.util.spec_from_file_location("_locale_tmp", path)
    mod  = importlib.util.module_from_spec(spec)   # type: ignore[arg-type]
    spec.loader.exec_module(mod)                   # type: ignore[union-attr]
    return mod.TRANSLATIONS


def section(title: str, items: list, note: str = "") -> None:
    status = "✅" if not items else "⚠️ "
    suffix = f"  — {note}" if note else ""
    print(f"\n{SEP}")
    print(f"{status}  {title}  ({len(items)}){suffix}")
    print(SEP)
    for item in items:
        if isinstance(item, tuple):
            k, v = item
            print(f"  {k:<45s}  {repr(v[:70])}")
        else:
            print(f"  {item}")


def scan_source_usage() -> tuple[set[str], str]:
    """
    Scan all source .py files for literal t("key") calls.
    Returns (set_of_keys_found, concatenated_source_text).
    """
    pattern = re.compile(r'\bt\(\s*["\']([^"\']+)["\']\s*[),]')
    used: set[str] = set()
    all_source = ""

    for d in SCAN_DIRS:
        if d.exists():
            for f in d.rglob("*.py"):
                try:
                    text = f.read_text(errors="replace")
                    all_source += text + "\n"
                    for m in pattern.finditer(text):
                        used.add(m.group(1))
                except Exception:
                    pass
    return used, all_source


def audit_locale(ref: dict[str, str], loc: dict[str, str], lang: str) -> int:
    """
    Audit one locale against the English reference.
    Returns the number of actionable issues (missing + untranslated).
    """
    ref_keys = set(ref)
    loc_keys = set(loc)

    missing = sorted(ref_keys - loc_keys)
    orphans = sorted(loc_keys - ref_keys)
    untrans = sorted(
        (k, loc[k])
        for k in (ref_keys & loc_keys)
        if loc[k] == ref[k] and k not in WHITELIST_SAME
    )

    section(f"[{lang}] Missing keys  (need translation)", missing)
    section(f"[{lang}] Orphan keys   (no longer in English reference)", orphans,
            note="safe to remove")
    section(f"[{lang}] Untranslated  (still equals English, excl. whitelist)", untrans)

    return len(missing) + len(untrans)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Audit i18n locale files.")
    parser.add_argument("--lang", help="Only audit this language code, e.g. fr")
    args = parser.parse_args()

    ref_path = LOCALE_DIR / "en.py"
    if not ref_path.exists():
        print(f"Reference locale not found: {ref_path}", file=sys.stderr)
        sys.exit(1)

    ref = load_locale(ref_path)
    print(f"\nReference locale : {ref_path}  ({len(ref)} keys)")

    # ── Global check: keys used in code but missing from English ──────────────
    used_in_code, _ = scan_source_usage()
    missing_from_ref = sorted(used_in_code - set(ref))
    section("Keys used in source code but MISSING from en.py  ← fix first!",
            missing_from_ref)
    total_issues = len(missing_from_ref)

    # ── Per-locale audit ──────────────────────────────────────────────────────
    if args.lang:
        locale_files = [LOCALE_DIR / f"{args.lang}.py"]
    else:
        locale_files = sorted(
            p for p in LOCALE_DIR.glob("*.py")
            if p.stem != "en" and not p.name.startswith("_")
        )

    if not locale_files:
        print("\nNo locale files found to audit (other than English).")
    else:
        for lf in locale_files:
            if not lf.exists():
                print(f"\n⚠️  Locale file not found: {lf}")
                continue
            lang = lf.stem
            loc  = load_locale(lf)
            print(f"\n{'═' * 70}")
            print(f"  Auditing: {lf.name}  ({len(loc)} keys)")
            print(f"{'═' * 70}")
            total_issues += audit_locale(ref, loc, lang)

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{SEP}")
    if total_issues == 0:
        print("✅  All locales are clean.")
    else:
        print(f"⚠️   {total_issues} issue(s) to fix across all audited locales.")
    print(SEP)
    print()


if __name__ == "__main__":
    main()
