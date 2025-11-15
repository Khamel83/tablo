#!/usr/bin/env python3
"""
RPi4 Tablo USB Auto-Processor
Detects Tablo USB drive, copies recordings, and syncs to Mac mini
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set
import socket

import yaml

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/tablo_processor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class TabloRPi4Processor:
    def __init__(self, config_path: str = "/opt/tablo/config.yaml"):
        with open(config_path) as f:
            self.cfg = yaml.safe_load(f)

        # Setup paths
        self.setup_paths()

        # Load state
        self.state = self._load_state()

        # Network config
        self.mac_host = self.cfg['network']['mac_mini_host']
        self.sync_port = self.cfg['network'].get('sync_port', 2222)

    def setup_paths(self):
        """Create required directories on RPi4"""
        paths = [
            '/opt/tablo',
            '/opt/tablo/recordings',
            '/opt/tablo/temp',
            '/opt/tablo/logs',
            '/var/log'
        ]

        for path in paths:
            Path(path).mkdir(parents=True, exist_ok=True)

        # Set permissions
        subprocess.run(['chmod', '755', '/opt/tablo'], check=True)

    def _load_state(self) -> Dict:
        state_file = '/opt/tablo/processor_state.json'
        if os.path.exists(state_file):
            with open(state_file) as f:
                return json.load(f)
        return {
            "processed_recordings": set(),
            "last_sync": None,
            "drive_info": {}
        }

    def _save_state(self):
        state_file = '/opt/tablo/processor_state.json'
        # Convert set to list for JSON
        state_copy = self.state.copy()
        state_copy['processed_recordings'] = list(self.state['processed_recordings'])

        with open(state_file, 'w') as f:
            json.dump(state_copy, f, indent=2)

    def detect_tablo_drive(self) -> Optional[str]:
        """Auto-detect Tablo USB drive when plugged in"""
        logger.info("Scanning for Tablo USB drives...")

        # Common USB mount points on RPi4
        mount_points = [
            '/media/tablo',
            '/media/usb',
            '/mnt/usb',
            '/mnt/tablo',
            '/media/pi',
            '/tmp/tablo'
        ]

        # Also check /media for dynamic mounts
        try:
            media_items = os.listdir('/media')
            for item in media_items:
                mount_points.append(f'/media/{item}')
        except:
            pass

        tablo_indicators = [
            'recordings',
            'system',
            'tablo',
            'TABS',
            'tablo_data'
        ]

        for mount_point in mount_points:
            if not os.path.exists(mount_point):
                continue

            try:
                contents = os.listdir(mount_point)
                for content in contents:
                    content_path = os.path.join(mount_point, content)
                    if os.path.isdir(content_path):
                        try:
                            subcontents = os.listdir(content_path)
                            if any(indicator.lower() in [s.lower() for s in subcontents]
                                  for indicator in tablo_indicators):
                                logger.info(f"Found Tablo drive at: {content_path}")
                                return content_path
                        except (PermissionError, OSError):
                            continue

            except (PermissionError, OSError):
                continue

        logger.info("No Tablo drive detected")
        return None

    def scan_recordings(self, drive_path: str) -> Dict[str, Dict]:
        """Scan Tablo drive for recordings"""
        recordings = {}

        # Look for recordings in common patterns
        recording_patterns = [
            'recordings',  # Most common
            'Recordings',
            'TABS',
            'tablo_recordings',
            'data'
        ]

        for pattern in recording_patterns:
            recordings_path = os.path.join(drive_path, pattern)
            if os.path.exists(recordings_path):
                logger.info(f"Scanning recordings in: {recordings_path}")
                recordings.update(self._scan_recordings_directory(recordings_path))

        logger.info(f"Found {len(recordings)} recordings on Tablo drive")
        return recordings

    def _scan_recordings_directory(self, recordings_path: str) -> Dict[str, Dict]:
        """Scan a specific recordings directory"""
        recordings = {}

        try:
            for item in os.listdir(recordings_path):
                item_path = os.path.join(recordings_path, item)

                # Look for numeric recording IDs
                if item.isdigit() and os.path.isdir(item_path):
                    recording_info = self._analyze_recording(item, item_path)
                    if recording_info:
                        recordings[item] = recording_info

        except (PermissionError, OSError) as e:
            logger.warning(f"Cannot access {recordings_path}: {e}")

        return recordings

    def _analyze_recording(self, recording_id: str, recording_path: str) -> Optional[Dict]:
        """Analyze a single recording directory"""
        try:
            info = {
                'id': recording_id,
                'path': recording_path,
                'playlist': None,
                'segments_dir': None,
                'segments': [],
                'size_bytes': 0,
                'modified_time': os.path.getmtime(recording_path),
                'recording_files': []
            }

            # Look for playlist
            for root, dirs, files in os.walk(recording_path):
                for file in files:
                    file_path = os.path.join(root, file)

                    if file == 'playlist.m3u8':
                        info['playlist'] = file_path
                        info['recording_files'].append(file_path)
                    elif file.endswith('.ts'):
                        info['segments'].append(file)
                        info['recording_files'].append(file_path)

                    # Calculate size
                    try:
                        info['size_bytes'] += os.path.getsize(file_path)
                    except:
                        pass

            # Sort segments
            info['segments'].sort(key=lambda x: int(x.split('.')[0]) if '.' in x else 0)

            # Validate this looks like a complete recording
            if info['recording_files']:
                logger.debug(f"Recording {recording_id}: {len(info['recording_files'])} files, {info['size_bytes']} bytes")
                return info
            else:
                logger.warning(f"Recording {recording_id} appears empty")
                return None

        except Exception as e:
            logger.error(f"Error analyzing recording {recording_id}: {e}")
            return None

    def copy_recording_to_rpi4(self, recording_id: str, recording_info: Dict) -> Optional[str]:
        """Copy recording from Tablo drive to RPi4 storage"""
        local_path = f"/opt/tablo/recordings/{recording_id}"

        if os.path.exists(local_path):
            logger.info(f"Recording {recording_id} already copied locally")
            return local_path

        logger.info(f"Copying recording {recording_id} to RPi4...")

        try:
            os.makedirs(local_path, exist_ok=True)

            # Copy all recording files
            for file_path in recording_info['recording_files']:
                rel_path = os.path.relpath(file_path, recording_info['path'])
                dest_path = os.path.join(local_path, rel_path)

                # Create directory structure
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)

                # Copy file
                logger.info(f"  Copying: {os.path.basename(file_path)}")
                shutil.copy2(file_path, dest_path)

            logger.info(f"Successfully copied recording {recording_id}")
            return local_path

        except Exception as e:
            logger.error(f"Failed to copy recording {recording_id}: {e}")
            return None

    def sync_to_mac_mini(self, recording_id: str, local_path: str):
        """Sync recording to Mac mini via network"""
        logger.info(f"Syncing recording {recording_id} to Mac mini...")

        try:
            # Create tarball for efficient transfer
            tarball_path = f"/opt/tablo/temp/{recording_id}.tar.gz"
            subprocess.run([
                'tar', '-czf', tarball_path, '-C', '/opt/tablo/recordings', recording_id
            ], check=True)

            # Transfer to Mac mini using scp/rsync
            remote_path = f"/opt/tablo/incoming/{recording_id}.tar.gz"

            # Try rsync first (more efficient for large files)
            rsync_cmd = [
                'rsync', '-avz', '--progress',
                tarball_path,
                f"pi@{self.mac_host}:{remote_path}"
            ]

            result = subprocess.run(rsync_cmd, capture_output=True, text=True)

            if result.returncode == 0:
                logger.info(f"Successfully synced {recording_id} to Mac mini")
                # Clean up local tarball
                os.remove(tarball_path)
                return True
            else:
                logger.error(f"rsync failed: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"Failed to sync {recording_id}: {e}")
            return False

    def notify_mac_mini(self, recording_id: str):
        """Notify Mac mini that new recording is ready"""
        try:
            import socket

            # Send notification to Mac mini
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)

            message = json.dumps({
                'action': 'new_recording',
                'recording_id': recording_id,
                'timestamp': datetime.now().isoformat()
            })

            sock.connect((self.mac_host, self.sync_port))
            sock.sendall(message.encode())
            sock.close()

            logger.info(f"Notified Mac mini about recording {recording_id}")

        except Exception as e:
            logger.warning(f"Failed to notify Mac mini: {e}")

    def process_tablo_drive(self):
        """Main processing loop for Tablo drive"""
        logger.info("Starting Tablo drive processing...")

        # Detect drive
        drive_path = self.detect_tablo_drive()
        if not drive_path:
            logger.info("No Tablo drive detected, exiting")
            return False

        logger.info(f"Processing Tablo drive: {drive_path}")

        # Scan for recordings
        recordings = self.scan_recordings(drive_path)
        if not recordings:
            logger.info("No recordings found on drive")
            return True

        # Find new recordings to process
        processed_recordings = set(self.state.get('processed_recordings', []))
        new_recordings = {rid: info for rid, info in recordings.items()
                         if rid not in processed_recordings}

        if not new_recordings:
            logger.info("No new recordings to process")
            return True

        logger.info(f"Processing {len(new_recordings)} new recordings")

        success_count = 0
        for recording_id, recording_info in new_recordings.items():
            try:
                logger.info(f"Processing recording {recording_id}")

                # Copy to RPi4
                local_path = self.copy_recording_to_rpi4(recording_id, recording_info)
                if not local_path:
                    logger.error(f"Failed to copy recording {recording_id}")
                    continue

                # Sync to Mac mini
                if self.sync_to_mac_mini(recording_id, local_path):
                    # Notify Mac mini
                    self.notify_mac_mini(recording_id)

                    # Update state
                    processed_recordings.add(recording_id)
                    self.state['processed_recordings'] = list(processed_recordings)
                    self.state['last_sync'] = datetime.now().isoformat()
                    self._save_state()

                    success_count += 1
                    logger.info(f"Successfully processed recording {recording_id}")
                else:
                    logger.error(f"Failed to sync recording {recording_id}")

            except Exception as e:
                logger.error(f"Failed to process recording {recording_id}: {e}")
                continue

        logger.info(f"Drive processing complete: {success_count}/{len(new_recordings)} successful")
        return success_count > 0


def main():
    processor = TabloRPi4Processor()

    try:
        success = processor.process_tablo_drive()
        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        logger.info("Processing interrupted")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()