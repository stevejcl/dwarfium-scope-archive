#!/usr/bin/env python3
"""
tools/check_help.py — Audit tool for the help locale files.
Run from the project root:

    python tools/check_help.py              # checks all locales vs English
    python tools/check_help.py --lang fr    # checks only French
    python tools/check_help.py --lang de    # checks only German

Reports per locale:
  - Routes missing (content still needs translation)
  - Orphan routes (no longer exist in English reference)
  - Routes marked # TODO (untranslated template entries)
"""

import argparse
import importlib.util
import sys
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT            = Path(__file__).parent.parent
HELP_LOCALE_DIR = ROOT / "components" / "help_locales"

SEP  = "─" * 70
SEP2 = "═" * 70


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_help(path: Path) -> dict[str, dict[str, str]]:
    """Load a help locale file and return its HELP dict."""
    spec = importlib.util.spec_from_file_location("_help_tmp", path)
    mod  = importlib.util.module_from_spec(spec)   # type: ignore[arg-type]
    spec.loader.exec_module(mod)                   # type: ignore[union-attr]
    return mod.HELP


def section(title: str, items: list, note: str = "") -> None:
    status = "✅" if not items else "⚠️ "
    suffix = f"  — {note}" if note else ""
    print(f"\n{SEP}")
    print(f"{status}  {title}  ({len(items)}){suffix}")
    print(SEP)
    for item in items:
        print(f"  {item}")


def load_raw_source(path: Path) -> str:
    """Read locale source file as plain text (to detect # TODO markers)."""
    try:
        return path.read_text(errors="replace")
    except Exception:
        return ""


def audit_locale(ref: dict, loc: dict, lang: str, loc_path: Path) -> int:
    """
    Audit one locale against the English reference.
    Returns the number of actionable issues.
    """
    ref_routes = set(ref)
    loc_routes = set(loc)

    missing = sorted(ref_routes - loc_routes)
    orphans = sorted(loc_routes - ref_routes)

    # Detect # TODO markers in the raw source
    raw = load_raw_source(loc_path)
    todo_routes = sorted(
        route for route in loc_routes
        if f"{repr(route)}: {{  # TODO" in raw or f"{repr(route)}:  # TODO" in raw
    )

    section(f"[{lang}] Routes missing  (need translation)", missing)
    section(f"[{lang}] Orphan routes   (no longer in English)", orphans,
            note="safe to remove")
    section(f"[{lang}] Routes marked # TODO  (template — not yet translated)", todo_routes)

    return len(missing) + len(todo_routes)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Audit help locale files.")
    parser.add_argument("--lang", help="Only audit this language code, e.g. fr")
    args = parser.parse_args()

    ref_path = HELP_LOCALE_DIR / "en.py"
    if not ref_path.exists():
        print(f"Reference help locale not found: {ref_path}", file=sys.stderr)
        sys.exit(1)

    ref = load_help(ref_path)
    print(f"\nReference help locale : {ref_path}  ({len(ref)} routes)")

    total_issues = 0

    if args.lang:
        locale_files = [HELP_LOCALE_DIR / f"{args.lang}.py"]
    else:
        locale_files = sorted(
            p for p in HELP_LOCALE_DIR.glob("*.py")
            if p.stem != "en" and not p.name.startswith("_")
        )

    if not locale_files:
        print("\nNo help locale files found to audit (other than English).")
    else:
        for lf in locale_files:
            if not lf.exists():
                print(f"\n⚠️  Help locale file not found: {lf}")
                continue
            lang = lf.stem
            loc  = load_help(lf)
            print(f"\n{SEP2}")
            print(f"  Auditing: {lf.name}  ({len(loc)} routes)")
            print(SEP2)
            total_issues += audit_locale(ref, loc, lang, lf)

    print(f"\n{SEP}")
    if total_issues == 0:
        print("✅  All help locales are clean.")
    else:
        print(f"⚠️   {total_issues} issue(s) to fix across all audited help locales.")
    print(SEP)
    print()


if __name__ == "__main__":
    main()