#!/bin/bash
# dgmt Linux Installer
# Installs dgmt and configures it as a systemd user service

set -e

echo "============================================"
echo " dgmt - Linux Installation"
echo "============================================"
echo

INSTALL_DIR="$HOME/.dgmt"
SYSTEMD_DIR="$HOME/.config/systemd/user"

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: python3 not found"
    echo "Please install Python 3 and try again"
    exit 1
fi

# Create installation directory
echo "Installing to $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
cp dgmt.py "$INSTALL_DIR/dgmt.py"
cp requirements.txt "$INSTALL_DIR/requirements.txt"
chmod +x "$INSTALL_DIR/dgmt.py"

# Install dependencies
echo
echo "Installing Python dependencies..."
pip3 install --user -r "$INSTALL_DIR/requirements.txt" --quiet

# Create symlink in ~/.local/bin
echo
echo "Creating symlink..."
mkdir -p "$HOME/.local/bin"
ln -sf "$INSTALL_DIR/dgmt.py" "$HOME/.local/bin/dgmt"

# Initialize config
echo
echo "Initializing config..."
python3 "$INSTALL_DIR/dgmt.py" init

# Create systemd user service
echo
echo "Creating systemd user service..."
mkdir -p "$SYSTEMD_DIR"

cat > "$SYSTEMD_DIR/dgmt.service" << EOF
[Unit]
Description=dgmt - Dylan's Google Drive Management Tool
After=network-online.target syncthing.service
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 $INSTALL_DIR/dgmt.py
Restart=on-failure
RestartSec=10

# Environment
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
EOF

# Reload systemd and enable service
echo "Enabling service..."
systemctl --user daemon-reload
systemctl --user enable dgmt.service

echo
echo "============================================"
echo " Installation complete!"
echo "============================================"
echo
echo "Config file: $INSTALL_DIR/config.json"
echo "Log file:    $INSTALL_DIR/dgmt.log"
echo
echo "Commands:"
echo "  dgmt                           # Run in foreground"
echo "  systemctl --user start dgmt    # Start as service"
echo "  systemctl --user stop dgmt     # Stop service"
echo "  systemctl --user status dgmt   # Check status"
echo "  journalctl --user -u dgmt -f   # View logs"
echo
echo "Next steps:"
echo "  1. Edit $INSTALL_DIR/config.json"
echo "  2. Set your watch_paths"
echo "  3. Run 'systemctl --user start dgmt'"
echo
