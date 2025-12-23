#!/bin/bash
echo "============================================"
echo "  Local Installation of Astrometry.net"
echo "============================================"

# Check if the package is already installed
if command -v solve-field >/dev/null 2>&1; then
    echo "solve-field already installed!"
    exit 0
fi

# Check if apt is available
if command -v apt >/dev/null 2>&1; then
    echo "Installation via apt..."
    sudo apt update
    sudo apt install -y astrometry.net
else
    echo "apt not found. Manual installation from extern/linux/astrometry/"
    INSTALL_DIR="/usr/local/astrometry"
    sudo mkdir -p "$INSTALL_DIR"
    sudo cp -r "$(dirname "$0")/astrometry/"* "$INSTALL_DIR"
    sudo ln -s "$INSTALL_DIR/bin/solve-field" /usr/local/bin/solve-field
fi

echo "Installation complete."
