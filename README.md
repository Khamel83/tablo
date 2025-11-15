# Tablo Auto-Renamer

Automated pipeline for Tablo OTA recordings: pulls, removes commercials, identifies episodes using AI, and organizes for Plex.

## Features

- **Tablo Integration**: Discovers and downloads recordings from any Tablo device on your network
- **Commercial Removal**: Uses Comskip to automatically detect and remove commercials
- **AI-Powered Identification**: Transcribes audio with Whisper and matches to TVMaze guide data
- **Plex Integration**: Organizes files with proper naming for Plex libraries
- **EPG Caching**: Local caching of TVMaze schedule data for fast offline matching
- **Robust Fallbacks**: Works even if some components fail (no Comskip, no LLM, etc.)

## Requirements

### Core Dependencies
- Python 3.8+
- ffmpeg, ffprobe (required)
- A Tablo device on your network

### Optional Components
- **comskip**: Commercial detection (recommended)
- **whisper**: Audio transcription for AI matching (recommended)
- **ollama**: Local LLM for disambiguation (recommended)
  - Pull model: `ollama pull llama3:8b`

### Installation

```bash
# Clone the repository
git clone https://github.com/Khamel83/tablo.git
cd tablo

# Run the installation script
./install.sh
```

## Configuration

Edit `config.yaml` with your settings:

```yaml
# Tablo device
tablo:
  ip: "192.168.1.123"  # Your Tablo's IP

# Paths (customize as needed)
paths:
  plex_tv_root: /Users/Shared/Plex/TV/  # Your Plex TV library
  timezone: "America/New_York"          # Your timezone

# TV networks to monitor
epg:
  country: "US"
  networks:
    - PBS
    - CBS
    - NBC
    - ABC
    - FOX
```

## Usage

### Manual Run
```bash
# Run complete pipeline once
./scripts/run_all_once.sh

# Or with custom config
./scripts/run_all_once.sh /path/to/config.yaml
```

### Individual Steps
```bash
# Update EPG cache
python3 src/epg_cache.py

# Pull new recordings
python3 src/pull_from_tablo.py

# Identify and rename files
python3 src/identify_and_rename.py
```

## Automation

### Cron (Linux/macOS)
Add to crontab (`crontab -e`):
```bash
# Run every hour
0 * * * * cd /path/to/tablo && ./scripts/run_all_once.sh
```

### macOS LaunchD
Create `~/Library/LaunchAgents/com.tablo.autorenamer.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.tablo.autorenamer</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/tablo/scripts/run_all_once.sh</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/path/to/tablo</string>
    <key>StartInterval</key>
    <integer>3600</integer>  <!-- Run every hour -->
</dict>
</plist>
```

Load with: `launchctl load ~/Library/LaunchAgents/com.tablo.autorenamer.plist`

## Pipeline Stages

### 1. Pull from Tablo (`pull_from_tablo.py`)
- Discovers new recordings via Tablo's web interface
- Downloads HLS segments and concatenates to raw .ts files
- Runs Comskip for commercial detection
- Creates clean MP4 files with commercials removed
- Writes metadata JSON with timing info

### 2. EPG Cache (`epg_cache.py`)
- Fetches TV schedule from TVMaze API
- Filters by configured networks and date range
- Caches locally for fast offline access
- Updates automatically (6-hour refresh)

### 3. Identify and Rename (`identify_and_rename.py`)
- Matches recordings to EPG data using time/duration
- For ambiguous cases, transcribes audio with Whisper
- Uses Ollama LLM to choose best match from candidates
- Creates Plex-compatible filenames
- Moves files to appropriate show directories

## File Structure

```
tablo/
├── config.yaml              # Main configuration
├── src/
│   ├── pull_from_tablo.py   # Stage 1: Tablo discovery and download
│   ├── epg_cache.py         # Stage 2: TVMaze schedule caching
│   └── identify_and_rename.py  # Stage 3: AI matching and file organization
├── scripts/
│   └── run_all_once.sh      # Complete pipeline runner
├── install.sh              # Installation script
└── README.md               # This file
```

## Data Flow

```
Tablo Device → HLS Download → Commercial Removal → EPG Matching → AI Disambiguation → Plex Library
```

### Metadata Storage
- `/opt/tablo/meta/<id>.json`: Per-recording metadata
- `/opt/tablo/epg/schedule.json`: Cached TV guide data
- `/opt/tablo/state.json`: Processing state

### Status Tracking
Each recording tracks its status through the pipeline:
- `pulled`: Downloaded from Tablo
- `clean`: Commercial removal complete
- `identified`: Matched to EPG data
- `moved_to_plex`: Final file in Plex library
- `unidentified`: No match found (manual review needed)

## Troubleshooting

### Common Issues

1. **"Tablo not found"**
   - Verify Tablo IP in config.yaml
   - Check network connectivity
   - Ensure Tablo is powered and connected

2. **"No segments found"**
   - Recording may still be in progress
   - Check Tablo storage availability
   - Verify Tablo firmware version

3. **"Comskip failed"**
   - Install Comskip: `brew install comskip` (macOS)
   - Falls back to original file if Comskip unavailable

4. **"Whisper failed"**
   - Install Whisper: `pip install openai-whisper`
   - System falls back to time-based matching

5. **"Ollama not responding"**
   - Install Ollama: `curl -fsSL https://ollama.com/install.sh | sh`
   - Pull model: `ollama pull llama3:8b`
   - Falls back to first EPG candidate

### Debug Mode
Enable detailed logging by modifying the logging level in each Python script:
```python
logging.basicConfig(level=logging.DEBUG)
```

## Contributing

This project follows the specifications from the detailed design document. Feel free to submit issues and enhancement requests.

## License

MIT License - see LICENSE file for details.