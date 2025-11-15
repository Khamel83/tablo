#!/bin/bash
# Tablo Auto-Renamer: Run complete pipeline once
# Usage: ./run_all_once.sh [config_file]

set -e  # Exit on any error

# Default config file
CONFIG="${1:-config.yaml}"

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$(dirname "$SCRIPT_DIR")/src"

echo "=== Tablo Auto-Renamer Pipeline ==="
echo "Config: $CONFIG"
echo "Time: $(date)"
echo

# Determine Tablo mode (streaming vs direct drive vs network)
TABLO_MODE=$(python3 -c "
import yaml
with open('$CONFIG') as f:
    cfg = yaml.safe_load(f)
    print(cfg.get('tablo', {}).get('mode', 'streaming'))
")

echo "Tablo Mode: $TABLO_MODE"
echo

# Step 1: Update EPG cache
echo "Step 1: Updating EPG cache..."
python3 "$SRC_DIR/epg_cache.py" "$CONFIG"
if [ $? -ne 0 ]; then
    echo "Error: EPG cache update failed"
    exit 1
fi
echo "EPG cache updated successfully"
echo

# Step 2: Pull new recordings from Tablo (mode-specific)
echo "Step 2: Pulling new recordings..."
case "$TABLO_MODE" in
    "direct_drive")
        echo "Using direct drive mode (USB connection)..."
        python3 "$SRC_DIR/pull_from_tablo_drive.py" "$CONFIG"
        PULL_EXIT_CODE=$?
        ;;
    "network")
        echo "Using network mode (RPi4 + Mac mini)..."
        echo "Network mode handles recording synchronization automatically"
        echo "Checking for incoming recordings..."
        if [ -d "/opt/tablo/incoming" ] && [ "$(ls -A /opt/tablo/incoming 2>/dev/null)" ]; then
            echo "Found incoming recordings - network receiver will process them"
        else
            echo "No incoming recordings found"
        fi
        PULL_EXIT_CODE=0
        ;;
    *)
        echo "Using streaming mode (network)..."
        python3 "$SRC_DIR/pull_from_tablo.py" "$CONFIG"
        PULL_EXIT_CODE=$?
        ;;
esac

if [ $PULL_EXIT_CODE -ne 0 ]; then
    if [ "$TABLO_MODE" = "direct_drive" ]; then
        echo "Warning: Tablo drive processing failed - make sure USB drive is connected"
        echo "Note: It's normal for this to fail when no Tablo drive is connected"
        echo "Continue with identification of existing recordings..."
    else
        echo "Error: Tablo pull failed"
        exit 1
    fi
else
    echo "Recording pull completed successfully"
    echo
fi

# Step 3: Identify and rename recordings
echo "Step 3: Identifying and renaming recordings..."
python3 "$SRC_DIR/identify_and_rename.py" "$CONFIG"
if [ $? -ne 0 ]; then
    echo "Error: Recording identification failed"
    exit 1
fi
echo "Recording identification completed successfully"
echo

echo "=== Pipeline completed successfully ==="
echo "Time: $(date)"

# Mode-specific notes
case "$TABLO_MODE" in
    "direct_drive")
        echo ""
        echo "Direct Drive Mode Notes:"
        echo "- Connect Tablo USB drive to Mac mini"
        echo "- Run this script when drive is connected (e.g., weekly)"
        echo "- Consider setting up a cron job to run weekly"
        ;;
    "network")
        echo ""
        echo "Network Mode Notes:"
        echo "- RPi4 automatically detects and syncs Tablo USB drives"
        echo "- Mac mini receives and processes synced recordings"
        echo "- No manual drive connection needed on Mac mini"
        echo "- Check status with: tablo-status"
        echo "- Test connection with: tablo-test"
        ;;
    *)
        echo ""
        echo "Streaming Mode Notes:"
        echo "- Tablo device must be accessible on network"
        echo "- Works with older Tablo firmware (pre-2.2.55)"
        ;;
esac