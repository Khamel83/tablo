#!/usr/bin/env python3
"""
Mac Mini Network Receiver
Receives synced recordings from RPi4 and processes them
"""

import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import yaml

# Import our processing modules
sys.path.append('/opt/tablo/src')
from epg_cache import TVMazeCache
from identify_and_rename import RecordingIdentifier

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/opt/tablo/logs/network_receiver.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class MacMiniReceiver:
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path) as f:
            self.cfg = yaml.safe_load(f)

        # Setup paths
        self.setup_paths()

        # Network config
        self.listen_port = self.cfg['network'].get('sync_port', 2222)
        self.rpi_host = self.cfg['network'].get('rpi4_host', 'auto-detect')

        # Processing modules
        self.epg_cache = TVMazeCache(config_path)
        self.identifier = RecordingIdentifier(config_path)

        # Queue for incoming recordings
        self.processing_queue = []

    def setup_paths(self):
        """Create required directories"""
        paths = [
            '/opt/tablo/incoming',    # RPi4 syncs here
            '/opt/tablo/recordings',  # Extracted recordings
            '/opt/tablo/processing',  # Currently processing
            '/opt/tablo/logs'
        ]

        for path in paths:
            Path(path).mkdir(parents=True, exist_ok=True)

    def start_network_listener(self):
        """Start listening for RPi4 connections"""
        logger.info(f"Starting network listener on port {self.listen_port}")

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(('', self.listen_port))
                sock.listen(5)

                logger.info(f"Listening for RPi4 connections on port {self.listen_port}")

                while True:
                    try:
                        conn, addr = sock.accept()
                        logger.info(f"Received connection from {addr}")

                        # Handle connection in separate thread
                        client_thread = threading.Thread(
                            target=self.handle_client_connection,
                            args=(conn, addr)
                        )
                        client_thread.daemon = True
                        client_thread.start()

                    except KeyboardInterrupt:
                        logger.info("Shutting down network listener")
                        break
                    except Exception as e:
                        logger.error(f"Error accepting connection: {e}")

        except Exception as e:
            logger.error(f"Failed to start network listener: {e}")

    def handle_client_connection(self, conn: socket.socket, addr: tuple):
        """Handle incoming connection from RPi4"""
        try:
            # Receive data
            data = conn.recv(1024).decode()
            if not data:
                return

            message = json.loads(data)
            logger.info(f"Received message from {addr}: {message}")

            # Handle different message types
            if message.get('action') == 'new_recording':
                recording_id = message.get('recording_id')
                self.process_new_recording(recording_id)
            elif message.get('action') == 'heartbeat':
                logger.debug(f"Heartbeat from {addr}")

        except Exception as e:
            logger.error(f"Error handling connection from {addr}: {e}")
        finally:
            conn.close()

    def process_new_recording(self, recording_id: str):
        """Process a newly synced recording"""
        logger.info(f"Processing new recording: {recording_id}")

        # Look for incoming tarball
        incoming_dir = Path('/opt/tablo/incoming')
        tarball_path = incoming_dir / f"{recording_id}.tar.gz"

        if not tarball_path.exists():
            logger.warning(f"Tarball not found for recording {recording_id}")
            return False

        try:
            # Extract tarball
            recordings_dir = Path('/opt/tablo/recordings')
            extract_path = recordings_dir / recording_id

            logger.info(f"Extracting {tarball_path} to {extract_path}")
            subprocess.run([
                'tar', '-xzf', str(tarball_path), '-C', str(recordings_dir)
            ], check=True)

            # Remove tarball to save space
            tarball_path.unlink()
            logger.info(f"Removed tarball for {recording_id}")

            # Verify extraction
            if not extract_path.exists():
                logger.error(f"Failed to extract recording {recording_id}")
                return False

            # Add to processing queue
            self.processing_queue.append(recording_id)
            logger.info(f"Added recording {recording_id} to processing queue")

            # Process immediately (or could be batched)
            self.process_recording_queue()

            return True

        except Exception as e:
            logger.error(f"Failed to process recording {recording_id}: {e}")
            return False

    def process_recording_queue(self):
        """Process all recordings in the queue"""
        if not self.processing_queue:
            return

        logger.info(f"Processing {len(self.processing_queue)} recordings from queue")

        # Clone current queue and clear it
        current_queue = self.processing_queue.copy()
        self.processing_queue.clear()

        for recording_id in current_queue:
            try:
                self.process_single_recording(recording_id)
            except Exception as e:
                logger.error(f"Failed to process {recording_id}: {e}")

    def process_single_recording(self, recording_id: str):
        """Process a single recording"""
        logger.info(f"Processing recording {recording_id}")

        recording_path = Path('/opt/tablo/recordings') / recording_id
        if not recording_path.exists():
            logger.error(f"Recording path not found: {recording_path}")
            return False

        # Find the main recording file (look for largest .ts or .mp4)
        main_file = self.find_main_recording_file(recording_path)
        if not main_file:
            logger.error(f"No main recording file found for {recording_id}")
            return False

        logger.info(f"Main recording file: {main_file}")

        # Create metadata for network-sourced recording
        metadata = self.create_network_metadata(recording_id, main_file, recording_path)

        # Save metadata
        meta_dir = Path('/opt/tablo/meta')
        meta_file = meta_dir / f"{recording_id}.json"
        meta_dir.mkdir(parents=True, exist_ok=True)

        with open(meta_file, 'w') as f:
            json.dump(metadata, f, indent=2)

        logger.info(f"Created metadata for {recording_id}")

        # Add to normal processing pipeline
        # This will trigger commercial removal, AI identification, etc.
        try:
            # Use the existing identification pipeline
            self.identifier.process_recordings()
            logger.info(f"Completed processing for {recording_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to identify recording {recording_id}: {e}")
            return False

    def find_main_recording_file(self, recording_path: Path) -> Optional[Path]:
        """Find the main recording file (largest .ts/.mp4)"""
        largest_file = None
        largest_size = 0

        for file_path in recording_path.rglob('*'):
            if file_path.is_file() and file_path.suffix in ['.ts', '.mp4', '.m3u8']:
                try:
                    size = file_path.stat().st_size
                    if size > largest_size:
                        largest_size = size
                        largest_file = file_path
                except:
                    continue

        return largest_file

    def create_network_metadata(self, recording_id: str, main_file: Path, recording_path: Path) -> Dict:
        """Create metadata for network-sourced recording"""
        # Get file stats
        stat = main_file.stat()
        modified_time = stat.st_mtime

        # Get duration using ffprobe
        duration = self.get_video_duration(str(main_file))

        # Convert timestamps
        from dateutil.tz import tzlocal
        tz = self.cfg.get('timezone', 'America/New_York')
        start_time_local = datetime.fromtimestamp(modified_time, tz=tz).isoformat()
        start_time_utc = datetime.fromtimestamp(modified_time).isoformat()

        return {
            "id": recording_id,
            "source": "network_sync",
            "original_file": str(main_file),
            "recording_path": str(recording_path),
            "start_time_utc": start_time_utc,
            "end_time_utc": datetime.fromtimestamp(modified_time + duration).isoformat(),
            "start_time_local": start_time_local,
            "end_time_local": datetime.fromtimestamp(modified_time + duration, tz=tz).isoformat(),
            "duration_seconds": duration,
            "size_bytes": stat.st_size,
            "status": "synced_ready",
            "final_path": None,
            "epg_match": None,
            "llm_choice": None,
            "created_at": datetime.now(tz=tz).isoformat(),
            "sync_source": "rpi4",
            "rpi4_timestamp": datetime.now().isoformat()
        }

    def get_video_duration(self, video_file: str) -> float:
        """Get video duration using ffprobe"""
        try:
            cmd = [
                'ffprobe',
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                video_file
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                duration_str = result.stdout.strip()
                return float(duration_str) if duration_str else 0.0

        except Exception as e:
            logger.warning(f"Failed to get duration for {video_file}: {e}")

        # Default to 30 minutes if we can't determine duration
        return 30 * 60

    def monitor_incoming_directory(self):
        """Monitor incoming directory for new files (fallback method)"""
        incoming_dir = Path('/opt/tablo/incoming')

        logger.info("Monitoring incoming directory for new files...")

        processed_files = set()

        while True:
            try:
                for tarball in incoming_dir.glob('*.tar.gz'):
                    if tarball.name not in processed_files:
                        recording_id = tarball.stem  # Remove .tar.gz extension
                        logger.info(f"Found new tarball: {tarball.name}")

                        if self.process_new_recording(recording_id):
                            processed_files.add(tarball.name)
                        else:
                            logger.warning(f"Failed to process {tarball.name}")

                time.sleep(5)  # Check every 5 seconds

            except KeyboardInterrupt:
                logger.info("Stopping directory monitor")
                break
            except Exception as e:
                logger.error(f"Error in directory monitor: {e}")
                time.sleep(10)

    def run(self):
        """Main run method - start both network listener and directory monitor"""
        logger.info("Starting Mac Mini Network Receiver")

        # Start network listener in background thread
        listener_thread = threading.Thread(target=self.start_network_listener)
        listener_thread.daemon = True
        listener_thread.start()

        # Also monitor incoming directory as fallback
        self.monitor_incoming_directory()


def main():
    try:
        receiver = MacMiniReceiver()
        receiver.run()

    except KeyboardInterrupt:
        logger.info("Shutting down Mac Mini receiver")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()