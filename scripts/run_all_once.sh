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

# Step 1: Update EPG cache
echo "Step 1: Updating EPG cache..."
python3 "$SRC_DIR/epg_cache.py" "$CONFIG"
if [ $? -ne 0 ]; then
    echo "Error: EPG cache update failed"
    exit 1
fi
echo "EPG cache updated successfully"
echo

# Step 2: Pull new recordings from Tablo
echo "Step 2: Pulling new recordings..."
python3 "$SRC_DIR/pull_from_tablo.py" "$CONFIG"
if [ $? -ne 0 ]; then
    echo "Error: Tablo pull failed"
    exit 1
fi
echo "Recording pull completed successfully"
echo

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