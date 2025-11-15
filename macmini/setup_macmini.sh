#!/bin/bash
# Mac Mini Network Receiver Setup
# One-command installation for Mac Mini

set -e

echo "=== Mac Mini Tablo Network Receiver Setup ==="
echo "Installing on: $(hostname)"
echo "Time: $(date)"
echo

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    print_error "This script must be run on macOS"
    exit 1
fi

print_status "Detected macOS: $(sw_vers -productName) $(sw_vers -productVersion)"

# Check for admin privileges
if [[ $EUID -ne 0 ]]; then
    print_error "This script must be run with sudo privileges"
    exit 1
fi

# Install Homebrew if not present
if ! command -v brew &> /dev/null; then
    print_status "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

# Install required packages
print_status "Installing required packages..."
brew install python3 ffmpeg

# Install Python packages
print_status "Installing Python packages..."
pip3 install --user requests python-dateutil pyyaml

# Check for Ollama
if ! command -v ollama &> /dev/null; then
    print_warning "Ollama not found. Installing for AI processing..."
    curl -fsSL https://ollama.com/install.sh | sh
else
    print_status "✅ Ollama already installed"
fi

# Check for required Ollama model
if ollama list | grep -q "llama3:8b"; then
    print_status "✅ Ollama llama3:8b model already available"
else
    print_warning "Pulling Ollama llama3:8b model..."
    ollama pull llama3:8b
fi

# Create directories
print_status "Creating directories..."
mkdir -p /opt/tablo/{incoming,recordings,processing,logs,meta}
chown -R $(stat -f "%U" /dev/console):staff /opt/tablo
chmod -R 755 /opt/tablo

# Create symlink for easy access
if [[ ! -L "/Users/Shared/Plex/TV" ]]; then
    print_status "Creating Plex TV directory..."
    mkdir -p "/Users/Shared/Plex/TV"
    chown -R $(stat -f "%U" /dev/console):staff "/Users/Shared/Plex"
fi

# Install tablo source files
INSTALL_DIR="/opt/tablo"
CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."

print_status "Installing Tablo source files..."
cp -r "$CURRENT_DIR/src" "$INSTALL_DIR/"
cp "$CURRENT_DIR/config.yaml" "$INSTALL_DIR/"
cp "$CURRENT_DIR/requirements.txt" "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/src/*.py"

# Install network receiver
print_status "Installing network receiver..."
mkdir -p "$INSTALL_DIR/macmini"
cp "$CURRENT_DIR/macmini/network_receiver.py" "$INSTALL_DIR/macmini/"
chmod +x "$INSTALL_DIR/macmini/network_receiver.py"

# Create launchd service
print_status "Creating macOS launchd service..."
cat > ~/Library/LaunchAgents/com.tablo.network-receiver.plist << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.tablo.network-receiver</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>$INSTALL_DIR/macmini/network_receiver.py</string>
        <string>$INSTALL_DIR/config.yaml</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$INSTALL_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/opt/tablo/logs/network-receiver.out</string>
    <key>StandardErrorPath</key>
    <string>/opt/tablo/logs/network-receiver.err</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONPATH</key>
        <string>$INSTALL_DIR/src</string>
    </dict>
</dict>
</plist>
EOF

# Load the service
print_status "Loading launchd service..."
launchctl load ~/Library/LaunchAgents/com.tablo.network-receiver.plist

# Check if service is running
sleep 2
if launchctl list | grep -q "com.tablo.network-receiver"; then
    print_status "✅ Network receiver service is running"
else
    print_warning "⚠️ Network receiver service may not be running properly"
fi

# Update config for network mode
print_status "Updating configuration for network mode..."
CONFIG_FILE="$INSTALL_DIR/config.yaml"

# Add network configuration
if ! grep -q "network:" "$CONFIG_FILE"; then
    cat >> "$CONFIG_FILE" << 'EOF'

# Network configuration for RPi4 + Mac mini setup
network:
  sync_port: 2222
  rpi4_host: "auto-detect"  # Will accept connections from any RPi4
  max_concurrent_syncs: 3
  sync_timeout: 300

# Mac mini specific settings
mac_mini:
  plex_tv_root: "/Users/Shared/Plex/TV"
  incoming_dir: "/opt/tablo/incoming"
  processing_dir: "/opt/tablo/processing"
EOF
fi

# Update tablo mode for network processing
sed -i '' 's/mode: "direct_drive"/mode: "network"/' "$CONFIG_FILE"

# Set up SSH for RPi4 connections
print_status "Setting up SSH for RPi4 connections..."
if [[ ! -f ~/.ssh/id_rsa ]]; then
    print_status "Generating SSH key..."
    ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa -N ""
fi

print_status "SSH key generated. You'll need to copy this to your RPi4:"
print_status "ssh-copy-id pi@<RPi4_IP_ADDRESS>"

# Test external tools
print_status "Testing external tools..."

# Test ffmpeg
if ffmpeg -version >/dev/null 2>&1; then
    print_status "✅ ffmpeg is working"
else
    print_error "❌ ffmpeg is not working properly"
fi

# Test Python modules
if python3 -c "import requests, yaml" 2>/dev/null; then
    print_status "✅ Python modules are available"
else
    print_error "❌ Python modules are missing"
fi

# Test Ollama
if ollama list >/dev/null 2>&1; then
    print_status "✅ Ollama is running"
else
    print_warning "⚠️ Ollama may not be running properly"
fi

# Create status script
print_status "Creating status script..."
cat > /usr/local/bin/tablo-status << 'EOF'
#!/bin/bash
echo "=== Tablo Network Receiver Status ==="
echo

echo "Service Status:"
if launchctl list | grep -q "com.tablo.network-receiver"; then
    echo "✅ Network Receiver: Running"
else
    echo "❌ Network Receiver: Not running"
fi

echo
echo "Ollama Status:"
if ollama list >/dev/null 2>&1; then
    echo "✅ Ollama: Running"
    echo "Available models:"
    ollama list
else
    echo "❌ Ollama: Not running"
fi

echo
echo "Recent Logs:"
tail -10 /opt/tablo/logs/network-receiver.out 2>/dev/null || echo "No logs available"

echo
echo "Directory Sizes:"
echo "Incoming: $(du -sh /opt/tablo/incoming 2>/dev/null | cut -f1 || echo "0B")"
echo "Processing: $(du -sh /opt/tablo/processing 2>/dev/null | cut -f1 || echo "0B")"
echo "Recordings: $(du -sh /opt/tablo/recordings 2>/dev/null | cut -f1 || echo "0B")"
echo "Plex Library: $(du -sh /Users/Shared/Plex/TV 2>/dev/null | cut -f1 || echo "0B")"
EOF

chmod +x /usr/local/bin/tablo-status

# Create test script
print_status "Creating test script..."
cat > /usr/local/bin/tablo-test << 'EOF'
#!/bin/bash
echo "=== Testing Tablo Network Connection ==="
echo

CONFIG_FILE="/opt/tablo/config.yaml"
PORT=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG_FILE'))['network']['sync_port'])")

echo "Testing port $PORT availability..."

if lsof -i :$PORT >/dev/null 2>&1; then
    echo "✅ Port $PORT is in use (receiver should be listening)"
else
    echo "❌ Port $PORT is not in use (receiver may not be running)"
fi

echo
echo "Testing Python network receiver..."
if python3 /opt/tablo/macmini/network_receiver.py --test 2>/dev/null; then
    echo "✅ Network receiver script is functional"
else
    echo "❌ Network receiver script has issues"
fi

echo
echo "Testing EPG cache..."
if python3 -c "import sys; sys.path.append('/opt/tablo/src'); from epg_cache import TVMazeCache; cache = TVMazeCache('/opt/tablo/config.yaml'); print('✅ EPG cache working')" 2>/dev/null; then
    echo "✅ EPG cache is functional"
else
    echo "❌ EPG cache has issues"
fi

echo
echo "Configuration summary:"
echo "Sync Port: $PORT"
echo "Incoming Dir: /opt/tablo/incoming"
echo "Plex TV Dir: /Users/Shared/Plex/TV"
EOF

chmod +x /usr/local/bin/tablo-test

print_status "=== Installation Complete! ==="
echo
echo "Mac Mini Network Receiver is ready!"
echo
echo "Next steps:"
echo "1. Set up your RPi4 using: curl -fsSL https://raw.githubusercontent.com/Khamel83/tablo/main/rpi4/setup_rpi4.sh | bash"
echo "2. Configure SSH keys between RPi4 and Mac mini:"
echo "   ssh-copy-id pi@<RPi4_IP_ADDRESS>"
echo "3. Update RPi4 config with Mac mini IP address"
echo "4. Test connection: tablo-test"
echo "5. Check status: tablo-status"
echo
echo "Service commands:"
echo "  Start: launchctl load ~/Library/LaunchAgents/com.tablo.network-receiver.plist"
echo "  Stop: launchctl unload ~/Library/LaunchAgents/com.tablo.network-receiver.plist"
echo "  Restart: launchctl unload ~/Library/LaunchAgents/com.tablo.network-receiver.plist && launchctl load ~/Library/LaunchAgents/com.tablo.network-receiver.plist"
echo "  Logs: tail -f /opt/tablo/logs/network-receiver.out"
echo
echo "Configuration file: $CONFIG_FILE"
echo
print_status "🎉 Mac Mini Network Receiver is ready to receive recordings from RPi4!"