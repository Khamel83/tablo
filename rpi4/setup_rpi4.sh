#!/bin/bash
# RPi4 Tablo Auto-Processor Setup
# One-command installation for Raspberry Pi 4

set -e

echo "=== RPi4 Tablo Auto-Processor Setup ==="
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

# Check if running on Raspberry Pi
if ! grep -q "Raspberry Pi" /proc/cpuinfo; then
    print_error "This script must be run on a Raspberry Pi"
    exit 1
fi

print_status "Detected Raspberry Pi: $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2 | xargs)"

# Update system
print_status "Updating system packages..."
sudo apt-get update
sudo apt-get upgrade -y

# Install required packages
print_status "Installing required packages..."
sudo apt-get install -y \
    python3 \
    python3-pip \
    python3-yaml \
    rsync \
    curl \
    tar \
    jq \
    udev

# Install Python dependencies
print_status "Installing Python dependencies..."
pip3 install --user pyyaml

# Create tablo user if not exists
if ! id "tablo" &>/dev/null; then
    print_status "Creating tablo user..."
    sudo useradd -r -s /bin/false -d /opt/tablo tablo
fi

# Create directories
print_status "Creating directories..."
sudo mkdir -p /opt/tablo/{recordings,temp,logs,incoming}
sudo chown -R pi:pi /opt/tablo
sudo chmod -R 755 /opt/tablo

# Create log directory
sudo mkdir -p /var/log
sudo touch /var/log/tablo_processor.log
sudo chown pi:pi /var/log/tablo_processor.log

# Create udev rule for auto-mounting
print_status "Creating USB auto-mount rules..."
sudo tee /etc/udev/rules.d/99-tablo-usb.rules > /dev/null << 'EOF'
# Tablo USB Drive Auto-Mount Rules
ACTION=="add", SUBSYSTEM=="block", KERNEL=="sd[b-z][1-9]", TAG+="systemd", ENV{SYSTEMD_WANTS}="tablo-usb-mount@%k.service"
EOF

# Create mount service
sudo tee /etc/systemd/system/tablo-usb-mount@.service > /dev/null << 'EOF'
[Unit]
Description=Mount Tablo USB Drive
After=local-fs.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/tablo-mount %I
RemainAfterExit=yes
EOF

# Create mount script
sudo tee /usr/local/bin/tablo-mount > /dev/null << 'EOF'
#!/bin/bash
DEVICE=$1
MOUNT_POINT="/media/tablo-$(basename $DEVICE)"

# Create mount point
sudo mkdir -p "$MOUNT_POINT"

# Try to mount (common filesystems)
for fs in ext4 ext3 ext2 ntfs vfat exfat; do
    if sudo mount -t $fs "/dev/$DEVICE" "$MOUNT_POINT" 2>/dev/null; then
        echo "Mounted /dev/$DEVICE at $MOUNT_POINT ($fs)"
        exit 0
    fi
done

echo "Failed to mount /dev/$DEVICE"
EOF

sudo chmod +x /usr/local/bin/tablo-mount

# Reload systemd and udev
print_status "Reloading systemd and udev..."
sudo systemctl daemon-reload
sudo udevadm control --reload-rules

# Install Tablo processor script
print_status "Installing Tablo processor..."
INSTALL_DIR="/opt/tablo"

# Download from GitHub (replace with actual URL when pushed)
if [ ! -f "$INSTALL_DIR/auto_tablo_processor.py" ]; then
    print_warning "Downloading from GitHub repository..."
    # This would be: curl -fsSL https://raw.githubusercontent.com/Khamel83/tablo/main/rpi4/auto_tablo_processor.py -o $INSTALL_DIR/auto_tablo_processor.py
    print_warning "Please copy auto_tablo_processor.py manually to $INSTALL_DIR/"
fi

# Make executable
chmod +x $INSTALL_DIR/auto_tablo_processor.py

# Install systemd service
print_status "Installing systemd service..."
sudo cp tablo_monitor.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable and start service
print_status "Enabling Tablo USB monitor service..."
sudo systemctl enable tablo-usb-monitor.service

print_status "Starting Tablo USB monitor service..."
sudo systemctl start tablo-usb-monitor.service

# Check service status
if systemctl is-active --quiet tablo-usb-monitor; then
    print_status "✅ Tablo USB monitor service is running"
else
    print_error "❌ Tablo USB monitor service failed to start"
    sudo systemctl status tablo-usb-monitor
    exit 1
fi

# Create network sync directory
print_status "Setting up network sync directory..."
sudo mkdir -p /opt/tablo/sync_out
sudo chown -R pi:pi /opt/tablo/sync_out

# Test connectivity to Mac mini
print_status "Testing network connectivity..."
read -p "Enter Mac mini IP address: " MAC_IP
if ping -c 1 "$MAC_IP" &>/dev/null; then
    print_status "✅ Network connectivity to Mac mini confirmed"
else
    print_warning "⚠️  Cannot reach Mac mini at $MAC_IP"
fi

# Create config template
print_status "Creating configuration template..."
cat > /opt/tablo/config.yaml << EOF
# RPi4 Tablo Processor Configuration
network:
  mac_mini_host: "$MAC_IP"  # Update with your Mac mini IP
  sync_port: 2222

# Processing settings
processing:
  max_concurrent_copies: 3
  sync_timeout: 300  # 5 minutes
  retry_attempts: 3

# Storage settings
storage:
  local_recordings: "/opt/tablo/recordings"
  temp_dir: "/opt/tablo/temp"
  log_file: "/var/log/tablo_processor.log"
EOF

chown pi:pi /opt/tablo/config.yaml

print_status "=== Installation Complete! ==="
echo
echo "Next steps:"
echo "1. Edit /opt/tablo/config.yaml with your Mac mini IP"
echo "2. Set up SSH key authentication to Mac mini:"
echo "   ssh-keygen -t rsa -b 4096"
echo "   ssh-copy-id pi@$MAC_IP"
echo "3. Connect Tablo USB drive to test"
echo "4. Monitor logs: sudo journalctl -u tablo-usb-monitor -f"
echo
echo "Service commands:"
echo "  Start: sudo systemctl start tablo-usb-monitor"
echo "  Stop: sudo systemctl stop tablo-usb-monitor"
echo "  Restart: sudo systemctl restart tablo-usb-monitor"
echo "  Status: sudo systemctl status tablo-usb-monitor"
echo
print_status "🎉 RPi4 Tablo Auto-Processor is ready!"