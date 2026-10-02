#!/bin/bash
# Installs astrometry.net (solve-field) and the Tycho-2 index files.
# Launched in a terminal by the Settings page so that sudo can ask for the password.
echo "============================================"
echo "  Local Installation of Astrometry.net"
echo "============================================"

finish() {
    echo
    read -r -p "Press Enter to close this window..." _
    exit "$1"
}

if ! command -v apt-get >/dev/null 2>&1; then
    echo "apt-get not found. Please install astrometry.net with your package manager"
    echo "(e.g. 'sudo dnf install astrometry' or the AUR package 'astrometry.net'),"
    echo "plus index files covering 20' to 2000' fields (Tycho-2 4100 series)."
    finish 1
fi

# Tycho-2 index files cover 22' to 2000' fields — enough for all Dwarf lenses.
# Without index files solve-field runs but never finds a solution.
PACKAGES="astrometry.net astrometry-data-tycho2"

if command -v solve-field >/dev/null 2>&1; then
    echo "solve-field already installed — checking index files..."
fi

sudo apt-get update && sudo apt-get install -y $PACKAGES
rc=$?

if [ $rc -eq 0 ] && command -v solve-field >/dev/null 2>&1; then
    echo
    echo "Installation complete. Restart Dwarfium Scope Archive to use solve-field."
    finish 0
fi

echo
echo "Installation failed (code $rc)."
finish 1
