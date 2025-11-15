#!/bin/bash
# Tablo Auto-Renamer Installation Script
# Sets up Python environment, dependencies, and default config

set -e

echo "=== Tablo Auto-Renamer Installation ==="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if we're in the right directory
if [ ! -f "config.yaml" ]; then
    print_error "config.yaml not found. Please run this script from the project root directory."
    exit 1
fi

# Check Python 3
print_status "Checking Python 3..."
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is not installed or not in PATH"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
print_status "Found Python $PYTHON_VERSION"

# Check required external tools
print_status "Checking external tools..."

TOOLS=("ffmpeg" "ffprobe")
for tool in "${TOOLS[@]}"; do
    if ! command -v "$tool" &> /dev/null; then
        print_error "$tool is not installed or not in PATH"
        print_error "Please install $tool before continuing"
        exit 1
    fi
    print_status "Found $tool"
done

# Optional tools with warnings
OPTIONAL_TOOLS=("comskip" "whisper" "ollama")
for tool in "${OPTIONAL_TOOLS[@]}"; do
    if ! command -v "$tool" &> /dev/null; then
        print_warning "$tool is not installed. Some features may not work."
        print_warning "Install $tool for full functionality:"
        case $tool in
            "comskip")
                echo "  - macOS: brew install comskip"
                echo "  - Ubuntu: sudo apt-get install comskip"
                ;;
            "whisper")
                echo "  - pip install openai-whisper"
                ;;
            "ollama")
                echo "  - curl -fsSL https://ollama.com/install.sh | sh"
                ;;
        esac
    else
        print_status "Found $tool"
    fi
done

# Create Python virtual environment
print_status "Setting up Python virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    print_status "Created virtual environment"
else
    print_status "Virtual environment already exists"
fi

# Activate virtual environment and install dependencies
print_status "Installing Python dependencies..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Create necessary directories
print_status "Creating directories..."
DIRS=("raw" "clean" "meta" "epg" "logs")
for dir in "${DIRS[@]}"; do
    mkdir -p "/opt/tablo/$dir"
    print_status "Created /opt/tablo/$dir"
done

# Set ownership and permissions
print_status "Setting permissions..."
chmod 755 scripts/*.sh
chmod +x src/*.py

# Test the installation
print_status "Testing installation..."

# Test Python imports
python3 -c "
import yaml
import requests
from dateutil import parser
print('Python dependencies: OK')
"

if [ $? -eq 0 ]; then
    print_status "Python dependencies: OK"
else
    print_error "Python dependency test failed"
    exit 1
fi

# Create a sample state file if it doesn't exist
if [ ! -f "/opt/tablo/state.json" ]; then
    print_status "Creating initial state file..."
    cat > /opt/tablo/state.json << EOF
{
  "processed_ids": [],
  "last_epg_fetch": null
}
EOF
fi

# Installation complete
print_status "Installation completed successfully!"
echo
print_status "Next steps:"
echo "1. Edit config.yaml with your settings:"
echo "   - Tablo IP address"
echo "   - Your local timezone"
echo "   - Plex TV library path"
echo "   - Preferred TV networks"
echo
print_status "To run the pipeline:"
echo "  ./scripts/run_all_once.sh"
echo
print_status "To automate (choose one):"
echo
echo "  cron (runs every hour):"
echo "    0 * * * * cd $(pwd) && ./scripts/run_all_once.sh"
echo
echo "  macOS launchd (runs every hour):"
echo "    # Create ~/Library/LaunchAgents/com.tablo.autorenamer.plist"
echo "    # Load with: launchctl load ~/Library/LaunchAgents/com.tablo.autorenamer.plist"
echo
print_warning "Remember to:"
echo "  - Configure your Tablo IP in config.yaml"
echo "  - Install comskip for commercial removal"
echo "  - Install ollama and pull llama3:8b for AI matching"
echo "  - Set up your Plex library path"
echo
print_status "Happy recording!"