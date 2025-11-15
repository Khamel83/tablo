# Tablo Auto-Renamer v1.1

**Complete automation pipeline for Tablo OTA recordings - now with dual mode support!**

**Works with both legacy Tablo devices AND 4th generation Tablo with locked firmware (2.2.55+)**

---

## 🎯 **What It Does**

Connect your Tablo USB drive to your Mac mini and get perfectly organized, commercial-free TV shows in your Plex library with accurate metadata and naming.

### **Input → Output**
```
Tablo USB Drive (raw recordings)
    ↓
[Automated Pipeline]
    ↓
Plex Library: Show Name - S01E02 - Episode Title.mp4
```

---

## 🆕 **v1.1 - Direct Drive Mode**

**For 4th Generation Tablo devices with firmware 2.2.55+**

- **Problem**: 4th gen Tablo firmware blocks HTTP access (403 Forbidden)
- **Solution**: Direct USB drive connection instead of network streaming
- **Workflow**: Weekly drive connection → automated processing → return to Tablo

---

## 🚀 **Quick Start**

### 1. Installation
```bash
git clone https://github.com/Khamel83/tablo.git
cd tablo
./install.sh
```

### 2. Configuration
Edit `config.yaml`:
```yaml
tablo:
  mode: "direct_drive"  # Use USB drive mode

direct_drive:
  mount_point: "/Volumes/Tablo"  # Where USB drive will mount
```

### 3. Weekly Workflow
```bash
# 1. Remove USB drive from Tablo
# 2. Connect to Mac mini (auto-mounts)
# 3. Run pipeline
./scripts/run_all_once.sh

# 4. Check your Plex library!
```

---

## 📋 **Complete Features**

### **Core Pipeline**
- ✅ **Recording Discovery**: Automatically finds new recordings on Tablo drive
- ✅ **Commercial Removal**: Comskip integration with intelligent fallback
- ✅ **AI Identification**: Whisper transcription + Ollama LLM matching
- ✅ **Plex Integration**: Perfect naming and folder structure
- ✅ **Metadata Tracking**: Complete recording lifecycle management

### **Dual Mode Support**
- 🔄 **Streaming Mode**: Legacy Tablo devices with open `/pvr/` access
- 💾 **Direct Drive Mode**: 4th gen Tablo with locked firmware
- 🔄 **Auto-Switching**: Automatically detects and uses appropriate mode

### **Smart Features**
- 🧠 **AI Disambiguation**: When multiple EPG matches, uses AI to pick the right one
- ⏰ **Time Matching**: Intelligent matching using recording timestamps
- 📺 **EPG Integration**: TVMaze schedule caching for accurate metadata
- 🔄 **State Tracking**: Never process the same recording twice
- 🛡️ **Error Recovery**: Graceful handling of corrupted or incomplete recordings

---

## 📁 **File Structure**

### **After Processing:**
```
/Users/Shared/Plex/TV/
├── PBS Kids/
│   ├── Wild Kratts - S01E02 - Aardvark Town.mp4
│   └── Wild Kratts - S01E03 - Masked Bandits.mp4
├── Sesame Street/
│   └── Sesame Street - S52E01 - Building a Better Block.mp4
└── Arthur/
    └── Arthur - S25E01 - The Butler Did It.mp4
```

### **Metadata Tracking:**
Each recording gets a `meta/<id>.json` file with:
- Recording source (direct drive vs streaming)
- Start/end times and duration
- EPG match data
- AI disambiguation results
- Final Plex file location
- Processing status history

---

## ⚙️ **Configuration Options**

### **Basic Setup**
```yaml
# Tablo device (4th gen)
tablo:
  mode: "direct_drive"        # "streaming" or "direct_drive"
  ip: "192.168.7.123"        # Still used for identification

# Direct drive settings
direct_drive:
  mount_point: "/Volumes/Tablo"
  recordings_path: "recordings"
  auto_detect: true
```

### **Advanced Options**
```yaml
# Matching precision
match:
  start_window: 300          # ±5 minutes for time matching
  duration_window: 120       # ±2 minutes for duration
  min_score: 0.75           # Minimum AI confidence

# TV Networks to monitor
epg:
  networks:
    - PBS
    - CBS
    - NBC
    - ABC
    - FOX
```

---

## 🔧 **Automation**

### **Weekly Automation**
```bash
# Add to crontab for weekly processing
crontab -e

# Run every Sunday at 2 AM
0 2 * * 0 cd /path/to/tablo && ./scripts/run_all_once.sh >> /opt/tablo/logs/weekly.log 2>&1
```

### **macOS LaunchD**
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
    <integer>604800</integer>  <!-- 1 week -->
</dict>
</plist>
```

---

## 📚 **Documentation**

- **[Direct Drive Setup Guide](DIRECT_DRIVE_SETUP.md)** - Complete setup for 4th gen Tablo
- **[Configuration Reference](config.yaml)** - All configuration options
- **[Troubleshooting Guide](docs/TROUBLESHOOTING.md)** - Common issues and solutions

---

## 🔍 **What You Get**

### **Final Output Files:**
- **Format**: MP4 (H.264 + AAC)
- **Quality**: Original Tablo quality preserved
- **Commercials**: Automatically removed when possible
- **Metadata**: Complete show, season, episode info
- **Naming**: Plex-compatible format
- **Searchable**: Full text search in Plex

### **Example Output:**
```
File: /Users/Shared/Plex/TV/Wild Kratts/Wild Kratts - S01E02 - Aardvark Town.mp4
Metadata:
  - Show: Wild Kratts
  - Season: 1
  - Episode: 2
  - Title: Aardvark Town
  - Network: PBS Kids
  - Air Date: 2025-11-15
  - Duration: 28:30
  - Source: Tablo USB Drive
  - Processed: Commercial removal + AI identification
```

---

## 🛠️ **Requirements**

### **Core Dependencies**
- Python 3.8+
- macOS (for direct drive mode)
- External USB drive connected to Tablo

### **Optional Components**
- **Comskip**: Commercial detection (`brew install comskip`)
- **Whisper**: Audio transcription (`pip install openai-whisper`)
- **Ollama**: Local AI for disambiguation (`curl -fsSL https://ollama.com/install.sh | sh`)
  - Model: `ollama pull llama3:8b`

### **Hardware**
- Tablo 4th generation device
- External USB drive (250GB+ recommended)
- Mac mini with sufficient storage
- Reliable internet (for EPG data)

---

## 🚨 **Important Notes**

### **4th Generation Tablo**
- Firmware 2.2.55+ blocks HTTP access to recordings
- Direct drive mode is required for these devices
- Weekly USB drive connection is the workflow
- All processing happens locally on your Mac

### **Data Safety**
- Tablo drive is never modified
- Processed files are copied to local storage
- Original recordings remain on Tablo drive
- Safe to disconnect and return to Tablo

### **Performance**
- Processing time: ~2-5 minutes per 30-minute recording
- Commercial removal: Optional but recommended
- AI matching: Used only when needed for disambiguation
- Storage: Temporary files cleaned up automatically

---

## 🎉 **Success Stories**

### **Typical Weekly Workflow:**
1. **Sunday Evening**: Safely remove USB drive from Tablo
2. **Connect to Mac**: Drive auto-mounts at `/Volumes/Tablo`
3. **Run Pipeline**: `./scripts/run_all_once.sh`
4. **Go to Bed**: Processing happens automatically
5. **Monday Morning**: Check Plex - perfectly organized shows ready!

### **What You'll See:**
- **15 new recordings** processed automatically
- **12 commercial-free** episodes in Plex
- **3 identified** with AI assistance
- **0 manual work** required
- **Perfect metadata** for every episode

---

## 🔗 **Links**

- **GitHub Repository**: https://github.com/Khamel83/tablo
- **Issues & Support**: https://github.com/Khamel83/tablo/issues
- **Tablo Official**: https://tablotv.com/

---

## 📄 **License**

MIT License - see LICENSE file for details.

---

**Ready to automate your Tablo recordings?** 🚀

1. Clone the repository
2. Run `./install.sh`
3. Configure `config.yaml`
4. Connect your Tablo USB drive
5. Run `./scripts/run_all_once.sh`

**Your perfectly organized Plex library awaits!** ✨