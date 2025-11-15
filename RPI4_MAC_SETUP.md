# RPi4 + Mac Mini Setup Guide

**Complete two-device architecture for Tablo 4th gen with firmware 2.2.55+**

---

## 🎯 **Overview**

This setup uses a **two-device architecture** that solves the Tablo filesystem compatibility issue:

- **RPi4**: USB drive handling + lightweight processing
- **Mac Mini**: Heavy processing + AI + Plex integration
- **Network sync**: Automatic transfer between devices

---

## 🚀 **Quick Start**

### **1. Set Up RPi4**
```bash
# SSH into your RPi4
ssh pi@<rpi4_ip>

# Run automated setup
curl -fsSL https://raw.githubusercontent.com/Khamel83/tablo/main/rpi4/setup_rpi4.sh | bash

# Configure with your Mac mini IP
sudo nano /opt/tablo/config.yaml
```

### **2. Set Up Mac Mini**
```bash
# On your Mac mini
curl -fsSL https://raw.githubusercontent.com/Khamel83/tablo/main/macmini/setup_macmini.sh | bash

# Enter your RPi4 IP when prompted
```

### **3. Configure SSH Key**
```bash
# From Mac mini to RPi4
ssh-keygen -t rsa -b 4096
ssh-copy-id pi@<rpi4_ip>

# Test connection
ssh pi@<rpi4_ip> 'echo "SSH connection successful"'
```

### **4. Test the Setup**
```bash
# On Mac mini
tablo-test
tablo-status

# Connect Tablo USB drive to RPi4 and watch it work!
```

---

## 📋 **Architecture Diagram**

```
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│   Tablo     │      │    RPi4     │      │  Mac Mini   │
│  (4th gen)  │      │   (USB)     │      │  (AI/Plex)  │
│             │      │             │      │             │
│ USB Drive ◄┼──────►│ Auto-Detect │◄─────►│ Heavy       │
│             │      │ Copy Files  │      │ Processing  │
│             │      │ Network Sync│      │ AI Identify │
└─────────────┘      └─────────────┘      │ Plex Org    │
                                         └─────────────┘
```

---

## 🔧 **Configuration**

### **RPi4 Configuration (`/opt/tablo/config.yaml`)**
```yaml
network:
  mac_mini_host: "192.168.1.100"  # Your Mac mini IP
  sync_port: 2222

processing:
  max_concurrent_copies: 3
  sync_timeout: 300
```

### **Mac Mini Configuration (`/opt/tablo/config.yaml`)**
```yaml
tablo:
  mode: "network"  # RPi4 + Mac mini mode

paths:
  plex_tv_root: "/Users/Shared/Plex/TV"

network:
  sync_port: 2222
  rpi4_host: "auto-detect"

# EPG and AI settings remain the same
epg:
  networks:
    - PBS
    - CBS
    - NBC
    - ABC
    - FOX

llm:
  model: llama3:8b
```

---

## 🔄 **Workflow**

### **Weekly Process:**

1. **Unplug USB drive** from Tablo
2. **Connect to RPi4** (auto-detected)
3. **Automatic Processing:**
   - RPi4 copies recordings (1 hour)
   - Network sync to Mac mini
   - Mac mini processes with AI (background)
4. **Return drive** to Tablo
5. **Enjoy organized shows** in Plex

### **What Happens Automatically:**

**RPi4 (≈1 hour):**
- ✅ Auto-detects Tablo USB drive
- ✅ Scans for new recordings
- ✅ Copies to RPi4 storage
- ✅ Creates compressed tarballs
- ✅ Network syncs to Mac mini
- ✅ Sends completion notification

**Mac Mini (background):**
- ✅ Receives network sync
- ✅ Extracts recordings
- ✅ Commercial removal (Comskip)
- ✅ AI identification (Whisper + Ollama)
- ✅ Plex organization
- ✅ Metadata tracking

---

## 📁 **File Distribution**

### **RPi4 Storage:**
```
/opt/tablo/
├── recordings/          # Tablo recordings (temporary)
├── temp/               # Processing artifacts
└── logs/               # RPi4 logs
```

### **Mac Mini Storage:**
```
/opt/tablo/
├── incoming/           # RPi4 sync destination
├── recordings/         # Extracted recordings
├── meta/              # Metadata JSON files
├── logs/              # Processing logs
└── ...

/Users/Shared/Plex/TV/
├── PBS Kids/
├── Sesame Street/
└── [Organized Shows]
```

---

## 🔧 **Service Management**

### **RPi4 Services:**
```bash
# Check status
sudo systemctl status tablo-usb-monitor

# View logs
sudo journalctl -u tablo-usb-monitor -f

# Restart service
sudo systemctl restart tablo-usb-monitor

# Enable auto-start
sudo systemctl enable tablo-usb-monitor
```

### **Mac Mini Services:**
```bash
# Check status
launchctl list | grep tablo

# View logs
tail -f /opt/tablo/logs/network-receiver.out

# Restart service
launchctl unload ~/Library/LaunchAgents/com.tablo.network-receiver.plist
launchctl load ~/Library/LaunchAgents/com.tablo.network-receiver.plist
```

---

## 🧪 **Testing**

### **Test Network Connection:**
```bash
# On Mac mini
tablo-test

# Manual sync test
rsync -avz test_file.txt pi@<rpi4_ip>:/tmp/
```

### **Test USB Detection:**
```bash
# On RPi4
sudo udevadm monitor

# Connect USB drive and watch events
```

### **Test Processing:**
```bash
# On Mac mini
./scripts/run_all_once.sh

# Check logs
tail -f /opt/tablo/logs/network_receiver.log
```

---

## 🚨 **Troubleshooting**

### **Common Issues:**

**1. USB Drive Not Detected:**
```bash
# Check connected devices
lsblk
sudo fdisk -l

# Check mounts
mount | grep media

# Check logs
sudo journalctl -u tablo-usb-monitor -n 50
```

**2. Network Sync Fails:**
```bash
# Test connectivity
ping <mac_mini_ip>

# Test SSH
ssh pi@<rpi4_ip> 'echo SSH OK'

# Test rsync
rsync -avz /tmp/test pi@<rpi4_ip>:/tmp/
```

**3. Mac Mini Not Receiving:**
```bash
# Check if port is listening
lsof -i :2222

# Test port from RPi4
nc -zv <mac_mini_ip> 2222

# Check firewall
sudo ufw status  # Linux
sudo pfctl -sr  # macOS
```

**4. Processing Issues:**
```bash
# Check logs
tail -f /opt/tablo/logs/*.log

# Check disk space
df -h

# Check Ollama
ollama list
ollama run llama3:8b "test"
```

---

## 📊 **Performance**

### **Expected Timing:**
- **USB Detection**: < 30 seconds
- **Recording Copy**: 2-5 minutes per 30-minute show
- **Network Sync**: 1-3 minutes per show
- **AI Processing**: 5-10 minutes per show (background)
- **Total Drive Time**: ~1 hour for 10-15 shows

### **Storage Requirements:**
- **RPi4**: 50GB for temporary processing
- **Mac Mini**: 500GB+ for processed media
- **Tablo Drive**: Unchanged (only read from)

---

## 🔄 **Automation**

### **Weekly Automation (RPi4):**
```bash
# Already automated via systemd service
# Runs whenever USB drive is connected
```

### **Daily Automation (Mac Mini):**
```bash
# Process any pending recordings daily
crontab -e
0 2 * * * /opt/tablo/scripts/run_all_once.sh >> /opt/tablo/logs/daily.log 2>&1
```

### **Status Monitoring:**
```bash
# Custom monitoring script
cat > /usr/local/bin/tablo-monitor << 'EOF'
#!/bin/bash
echo "=== Tablo System Status ==="
echo "RPi4: $(ssh pi@<rpi4_ip> 'systemctl is-active tablo-usb-monitor')"
echo "Mac Mini: $(launchctl list | grep -c tablo)"
echo "Queue: $(ls /opt/tablo/incoming/*.tar.gz 2>/dev/null | wc -l)"
echo "Recent: $(find /Users/Shared/Plex/TV -name "*.mp4" -mtime -7 | wc -l)"
EOF
```

---

## 🎉 **Success Indicators**

### **When It's Working:**

**RPi4:**
- ✅ USB drive auto-mounts when connected
- ✅ Service logs show "Found Tablo drive"
- ✅ Recording files appear in `/opt/tablo/recordings/`
- ✅ Network sync shows progress

**Mac Mini:**
- ✅ Network receiver listening on port 2222
- ✅ Incoming tarballs appear in `/opt/tablo/incoming/`
- ✅ Processing creates metadata in `/opt/tablo/meta/`
- ✅ Final files appear in Plex with proper naming

**Plex:**
- ✅ New shows appear automatically
- ✅ Perfect metadata and episode information
- ✅ Commercial-free content
- ✅ Searchable and organized

---

## 📚 **Documentation Links**

- **Main README**: https://github.com/Khamel83/tablo
- **Direct Drive Guide**: DIRECT_DRIVE_SETUP.md
- **Configuration**: config.yaml
- **Issue Tracking**: https://github.com/Khamel83/tablo/issues

---

## 🔗 **Quick Setup Commands**

**One-command setup for both devices:**

```bash
# RPi4
curl -fsSL https://raw.githubusercontent.com/Khamel83/tablo/main/rpi4/setup_rpi4.sh | bash

# Mac Mini
curl -fsSL https://raw.githubusercontent.com/Khamel83/tablo/main/macmini/setup_macmini.sh | bash
```

**Your RPi4 + Mac mini Tablo automation is ready!** 🚀

Just connect the Tablo USB drive to the RPi4 and watch the magic happen! ✨