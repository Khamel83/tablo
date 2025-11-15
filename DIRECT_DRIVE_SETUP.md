# Tablo Direct Drive Setup Guide

**For 4th Generation Tablo devices with firmware 2.2.55+**

## Overview

This guide covers setting up the Tablo Auto-Renamer to work with 4th generation Tablo devices that have locked firmware blocking HTTP access. Instead of streaming over the network, we'll connect the Tablo's USB drive directly to your Mac mini.

## Why Direct Drive Mode?

- **Firmware 2.2.55+** blocks `/pvr/` HTTP access (403 Forbidden)
- **4th gen security** prevents network-based recording access
- **USB connection** provides direct access to recording files
- **Weekly manual process** - connect drive, run script, disconnect

## Setup Process

### 1. Hardware Requirements

- Tablo 4th generation device
- External USB drive connected to Tablo (250GB+ recommended)
- Mac mini with available USB port
- Sufficient local storage for processed files

### 2. Software Installation

```bash
# Clone the repository
git clone https://github.com/Khamel83/tablo.git
cd tablo

# Run installation
./install.sh
```

### 3. Configuration

Edit `config.yaml`:

```yaml
# Tablo device
tablo:
  ip: "192.168.7.123"  # Still needed for identification
  mode: "direct_drive" # CRITICAL: Use direct drive mode

# Direct drive settings
direct_drive:
  mount_point: "/Volumes/Tablo"  # Where drive will mount on Mac
  recordings_path: "recordings" # Usually "recordings" on Tablo drives
  auto_detect: true
  archive_processed: false      # Optional: archive on Tablo drive
```

### 4. Workflow

#### Weekly Process (recommended):

1. **Safely remove USB drive from Tablo**
   - Use Tablo app to "eject" external drive if available
   - Power down Tablo first (safest approach)

2. **Connect drive to Mac mini**
   ```bash
   # Drive should auto-mount at /Volumes/Tablo or similar
   # Verify it's visible:
   ls /Volumes/
   ```

3. **Run the pipeline**
   ```bash
   ./scripts/run_all_once.sh
   ```

4. **Monitor processing**
   - Scripts will automatically find new recordings
   - Process: copy → commercial removal → AI identification → Plex organization
   - Progress logged to `/opt/tablo/logs/`

5. **Return drive to Tablo**
   - Safely eject from Mac
   - Reconnect to Tablo
   - Power on Tablo

#### Automation Options:

**Weekly Cron Job:**
```bash
# Edit crontab
crontab -e

# Add weekly run (Sundays at 2 AM)
0 2 * * 0 cd /path/to/tablo && ./scripts/run_all_once.sh >> /opt/tablo/logs/weekly.log 2>&1
```

**Manual Trigger:**
```bash
# Quick test run
python3 src/pull_from_tablo_drive.py

# Full pipeline
./scripts/run_all_once.sh
```

## Expected Results

### File Structure After Processing:

```
/opt/tablo/
├── meta/           # Recording metadata JSON files
├── clean/          # Commercial-free MP4s (temporary)
├── epg/           # TV guide cache
└── logs/          # Processing logs

/Users/Shared/Plex/TV/
├── PBS Kids/
│   ├── Wild Kratts - S01E02 - Aardvark Town.mp4
│   └── Wild Kratts - S01E03 - Masked Bandits.mp4
├── Sesame Street/
│   └── Sesame Street - S52E01 - Building a Better Block.mp4
└── Arthur/
    └── Arthur - S25E01 - The Butler Did It.mp4
```

### Processing Status Tracking:

Each recording in `meta/<id>.json` tracks:
- `source: "direct_drive"` - USB drive source
- `status: "moved_to_plex"` - Successfully processed
- `start_time_local` - Recording timestamp
- `epg_match` - TV guide match data
- `final_path` - Final Plex file location

## Troubleshooting

### Drive Not Detected

```bash
# Check mounted drives
ls /Volumes/

# Test drive detection manually
python3 -c "
from src.tablo_drive_puller import TabloDrivePuller
puller = TabloDrivePuller()
path = puller._detect_tablo_drive()
print(f'Found Tablo drive: {path}')
"
```

### No Recordings Found

```bash
# Check drive structure
find /Volumes/Tablo -name "recordings" -type d 2>/dev/null

# Look for recording directories
find /Volumes/Tablo -name "[0-9]*" -type d 2>/dev/null | head -10
```

### Permission Issues

```bash
# Fix permissions if needed
sudo chown -R $USER:staff /opt/tablo/
chmod -R 755 /opt/tablo/
```

### Failed Processing

Check logs:
```bash
tail -f /opt/tablo/logs/*.log
```

Common issues:
- **Insufficient disk space** - Check storage on Mac mini
- **Corrupted recordings** - Skip and continue with others
- **Missing dependencies** - Run `./install.sh` again

## Best Practices

### For Weekly Operation:

1. **Schedule consistency** - Same day/time each week
2. **Drive handling** - Always safely eject drives
3. **Monitor storage** - Clean up old files periodically
4. **Backup Plex** - Keep your organized media backed up

### Performance Tips:

1. **SSD storage** - Use fast SSD for temporary processing files
2. **Network storage** - Consider network-attached storage for final Plex files
3. **Parallel processing** - Script processes recordings sequentially for reliability

### Safety Considerations:

1. **Drive health** - Monitor USB drive health
2. **Redundancy** - Keep backups of important recordings
3. **Tablo operation** - Ensure Tablo works normally when drive reconnected

## Configuration Options

### Advanced Settings:

```yaml
direct_drive:
  mount_point: "/Volumes/Tablo"        # Drive mount location
  recordings_path: "recordings"        # Path to recordings on drive
  auto_detect: true                    # Auto-detect drive structure
  archive_processed: true              # Move processed files on drive
  archive_path: "processed"            # Archive folder on Tablo drive

# Processing options
match:
  start_window: 300                    # ±5 minutes for time matching
  duration_window: 120                 # ±2 minutes for duration
  min_score: 0.75                      # Minimum match confidence
```

### Frequency Options:

- **Weekly** - Recommended for most users
- **Bi-weekly** - For light recording schedules
- **Monthly** - For occasional recording users
- **Manual** - Process as needed

## Migration from Streaming Mode

If you previously used streaming mode (older firmware):

1. **Backup existing data** - Save `/opt/tablo/` folder
2. **Update config** - Change `mode: "direct_drive"`
3. **Test with existing drive** - Verify drive detection works
4. **Process backlog** - Run once to catch up on unprocessed recordings

The metadata and state tracking will seamlessly carry over, so previously processed recordings won't be duplicated.