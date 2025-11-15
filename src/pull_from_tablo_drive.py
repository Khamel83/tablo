#!/usr/bin/env python3
"""
Pull from Tablo USB Drive: process recordings directly from connected Tablo USB drive.
For 4th generation Tablo devices with locked firmware (2.2.55+).
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import yaml
from dateutil.tz import tzlocal

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TabloDrivePuller:
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path) as f:
            self.cfg = yaml.safe_load(f)

        # Setup paths
        for path_key in ['raw_dir', 'clean_dir', 'meta_dir', 'epg_dir', 'logs_dir']:
            Path(self.cfg['paths'][path_key]).mkdir(parents=True, exist_ok=True)

        self.state = self._load_state()
        self.tablo_drive_path = None

    def _load_state(self) -> Dict:
        state_file = self.cfg['paths']['state_file']
        if os.path.exists(state_file):
            with open(state_file) as f:
                return json.load(f)
        return {"processed_ids": set(), "last_epg_fetch": None}

    def _save_state(self):
        state_file = self.cfg['paths']['state_file']
        # Convert set to list for JSON serialization
        state_copy = self.state.copy()
        state_copy['processed_ids'] = list(self.state['processed_ids'])

        with open(state_file, 'w') as f:
            json.dump(state_copy, f, indent=2)

    def _detect_tablo_drive(self) -> Optional[str]:
        """Detect mounted Tablo USB drive."""
        mount_point = self.cfg['direct_drive']['mount_point']

        # Look for Tablo drive characteristics
        tablo_indicators = [
            'recordings',
            'system',
            'tablo',
            'TABS'
        ]

        # Check if the configured mount point exists
        if os.path.exists(mount_point):
            for item in os.listdir(mount_point):
                if any(indicator in item.lower() for indicator in tablo_indicators):
                    logger.info(f"Found potential Tablo drive at: {mount_point}")
                    return mount_point

        # Search common mount points for Tablo drives
        common_mounts = ['/Volumes', '/media', '/mnt']
        for base_path in common_mounts:
            if not os.path.exists(base_path):
                continue

            for item in os.listdir(base_path):
                item_path = os.path.join(base_path, item)
                if os.path.isdir(item_path):
                    # Check for Tablo drive indicators
                    try:
                        subitems = os.listdir(item_path)
                        if any(indicator in [s.lower() for s in subitems] for indicator in tablo_indicators):
                            logger.info(f"Found Tablo drive: {item_path}")
                            return item_path
                    except (PermissionError, OSError):
                        continue

        logger.error("No Tablo USB drive detected")
        return None

    def _find_recordings_on_drive(self) -> Dict[str, Dict]:
        """Find all recordings on the Tablo drive."""
        if not self.tablo_drive_path:
            return {}

        recordings = {}
        recordings_path = self.cfg['direct_drive'].get('recordings_path', 'recordings')
        full_recordings_path = os.path.join(self.tablo_drive_path, recordings_path)

        if not os.path.exists(full_recordings_path):
            logger.error(f"Recordings path not found: {full_recordings_path}")
            return {}

        logger.info(f"Scanning for recordings in: {full_recordings_path}")

        # Look for recording directories (numeric IDs)
        for item in os.listdir(full_recordings_path):
            item_path = os.path.join(full_recordings_path, item)

            if os.path.isdir(item_path) and item.isdigit():
                recording_id = item
                recording_info = self._analyze_recording(recording_id, item_path)
                if recording_info:
                    recordings[recording_id] = recording_info

        logger.info(f"Found {len(recordings)} recordings on Tablo drive")
        return recordings

    def _analyze_recording(self, recording_id: str, recording_path: str) -> Optional[Dict]:
        """Analyze a single recording directory."""
        try:
            info = {
                'id': recording_id,
                'path': recording_path,
                'playlist': None,
                'segments_dir': None,
                'segments': [],
                'size_bytes': 0,
                'modified_time': os.path.getmtime(recording_path)
            }

            # Look for playlist directory
            pl_path = os.path.join(recording_path, 'pl')
            if os.path.exists(pl_path):
                playlist_file = os.path.join(pl_path, 'playlist.m3u8')
                if os.path.exists(playlist_file):
                    info['playlist'] = playlist_file
                    info['size_bytes'] += os.path.getsize(playlist_file)

            # Look for segments directory
            segs_path = os.path.join(recording_path, 'segs')
            if os.path.exists(segs_path):
                info['segments_dir'] = segs_path

                # Count and size up segments
                for seg_file in os.listdir(segs_path):
                    if seg_file.endswith('.ts'):
                        seg_full_path = os.path.join(segs_path, seg_file)
                        info['segments'].append(seg_file)
                        info['size_bytes'] += os.path.getsize(seg_full_path)

                # Sort segments numerically
                info['segments'].sort(key=lambda x: int(x.split('.')[0]))

            # Check if this looks like a valid recording
            if info['playlist'] and info['segments']:
                logger.debug(f"Recording {recording_id}: {len(info['segments'])} segments, {info['size_bytes']} bytes")
                return info
            else:
                logger.warning(f"Recording {recording_id} appears incomplete (playlist: {bool(info['playlist'])}, segments: {len(info['segments'])})")
                return None

        except Exception as e:
            logger.error(f"Error analyzing recording {recording_id}: {e}")
            return None

    def _copy_recording(self, recording_id: str, recording_info: Dict) -> Optional[str]:
        """Copy recording from Tablo drive to local storage."""
        raw_dir = Path(self.cfg['paths']['raw_dir'])
        raw_file = raw_dir / f"{recording_id}.ts"

        if raw_file.exists():
            logger.info(f"Raw file already exists: {raw_file}")
            return str(raw_file)

        logger.info(f"Copying recording {recording_id} from Tablo drive...")

        if not recording_info.get('playlist'):
            logger.error(f"No playlist found for recording {recording_id}")
            return None

        try:
            # Use ffmpeg to convert from Tablo's format to a single .ts file
            cmd = [
                self.cfg['tools']['ffmpeg'],
                '-i', recording_info['playlist'],
                '-c', 'copy',
                '-y',  # Overwrite output file
                str(raw_file)
            ]

            logger.info(f"Running ffmpeg to process {recording_id}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

            if result.returncode != 0:
                logger.error(f"ffmpeg failed for recording {recording_id}: {result.stderr}")
                return None

            file_size = os.path.getsize(raw_file)
            logger.info(f"Successfully copied recording {recording_id}: {file_size} bytes")

            return str(raw_file)

        except subprocess.TimeoutExpired:
            logger.error(f"Copy timeout for recording {recording_id}")
            return None
        except Exception as e:
            logger.error(f"Copy failed for recording {recording_id}: {e}")
            return None

    def _get_duration(self, video_file: str) -> Optional[float]:
        """Get video duration using ffprobe."""
        cmd = [
            self.cfg['tools']['ffprobe'],
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            video_file
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                duration = float(result.stdout.strip())
                return duration
            else:
                logger.error(f"ffprobe failed: {result.stderr}")
                return None
        except Exception as e:
            logger.error(f"Failed to get duration: {e}")
            return None

    def _remove_commercials(self, recording_id: str, raw_file: str) -> Optional[str]:
        """Remove commercials using Comskip and return clean MP4 file."""
        clean_dir = Path(self.cfg['paths']['clean_dir'])
        clean_file = clean_dir / f"{recording_id}.mp4"

        if clean_file.exists():
            logger.info(f"Clean file already exists: {clean_file}")
            return str(clean_file)

        # Check if Comskip is available
        if not shutil.which(self.cfg['tools']['comskip']):
            logger.warning("Comskip not found, copying without commercial removal")
            # Just convert to MP4 without commercial removal
            try:
                cmd = [
                    self.cfg['tools']['ffmpeg'],
                    '-i', raw_file,
                    '-c', 'copy',
                    str(clean_file)
                ]
                subprocess.run(cmd, check=True)
                return str(clean_file)
            except Exception as e:
                logger.error(f"Failed to convert {raw_file}: {e}")
                return None

        # Run Comskip
        comskip_cmd = [self.cfg['tools']['comskip'], raw_file]

        try:
            logger.info(f"Running Comskip on {recording_id}")
            result = subprocess.run(comskip_cmd, capture_output=True, text=True, timeout=1800)
            if result.returncode != 0:
                logger.warning(f"Comskip failed, using original file: {result.stderr}")
                # Copy original as clean
                subprocess.run([
                    self.cfg['tools']['ffmpeg'],
                    '-i', raw_file,
                    '-c', 'copy',
                    str(clean_file)
                ], check=True)
                return str(clean_file)
        except subprocess.TimeoutExpired:
            logger.warning(f"Comskip timeout for recording {recording_id}, using original")
            # Copy original as clean
            subprocess.run([
                self.cfg['tools']['ffmpeg'],
                '-i', raw_file,
                '-c', 'copy',
                str(clean_file)
            ], check=True)
            return str(clean_file)
        except Exception as e:
            logger.error(f"Commercial removal failed: {e}")
            return None

        # Check for .edl file and use it if available
        edl_file = Path(raw_file).with_suffix('.edl')
        if edl_file.exists():
            logger.info(f"Using EDL file for commercial removal: {edl_file}")
            try:
                ffmpeg_cmd = [
                    self.cfg['tools']['ffmpeg'],
                    '-i', raw_file,
                    '-vf', f'edl={edl_file}',
                    '-c:a', 'copy',
                    '-c:v', 'libx264',
                    '-preset', 'medium',
                    '-crf', '23',
                    str(clean_file)
                ]
                result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=3600)
                if result.returncode == 0:
                    logger.info(f"Commercial removal complete: {clean_file}")
                    return str(clean_file)
            except Exception as e:
                logger.warning(f"EDL processing failed: {e}")

        # Fallback: simple copy without commercial removal
        try:
            subprocess.run([
                self.cfg['tools']['ffmpeg'],
                '-i', raw_file,
                '-c', 'copy',
                str(clean_file)
            ], check=True)
            return str(clean_file)
        except Exception as e:
            logger.error(f"Failed to create clean file: {e}")
            return None

    def _write_metadata(self, recording_id: str, raw_file: str, clean_file: str,
                       recording_info: Dict, duration: float):
        """Write metadata JSON file for the recording."""
        meta_dir = Path(self.cfg['paths']['meta_dir'])
        meta_file = meta_dir / f"{recording_id}.json"

        # Convert timestamps to ISO format with timezone
        tz = self.cfg['timezone']
        modified_time = recording_info['modified_time']
        start_time_utc = datetime.fromtimestamp(modified_time, tz=timezone.utc).isoformat()
        start_time_local = datetime.fromtimestamp(modified_time, tz=tz).isoformat()

        # Estimate end time based on duration
        end_time_utc = datetime.fromtimestamp(modified_time + duration, tz=timezone.utc).isoformat()
        end_time_local = datetime.fromtimestamp(modified_time + duration, tz=tz).isoformat()

        metadata = {
            "id": recording_id,
            "source": "direct_drive",
            "raw_file": raw_file,
            "clean_file": clean_file,
            "drive_path": recording_info['path'],
            "drive_modified_time": modified_time,
            "drive_size_bytes": recording_info['size_bytes'],
            "start_time_utc": start_time_utc,
            "end_time_utc": end_time_utc,
            "start_time_local": start_time_local,
            "end_time_local": end_time_local,
            "duration_seconds": duration,
            "status": "clean",
            "final_path": None,
            "epg_match": None,
            "llm_choice": None,
            "created_at": datetime.now(tz=tz).isoformat()
        }

        with open(meta_file, 'w') as f:
            json.dump(metadata, f, indent=2)

        logger.info(f"Metadata written: {meta_file}")

    def process_tablo_drive(self):
        """Main processing loop: process all recordings from Tablo USB drive."""
        logger.info("Starting Tablo drive processing")

        # Detect Tablo drive
        self.tablo_drive_path = self._detect_tablo_drive()
        if not self.tablo_drive_path:
            logger.error("No Tablo drive found. Please connect the Tablo USB drive.")
            return False

        # Find recordings on drive
        recordings = self._find_recordings_on_drive()
        if not recordings:
            logger.info("No recordings found on Tablo drive")
            return True

        # Get list of already processed recording IDs
        processed_ids = set(self.state.get('processed_ids', []))

        # Find new recordings to process
        new_recordings = {rid: info for rid, info in recordings.items()
                         if rid not in processed_ids}

        if not new_recordings:
            logger.info("No new recordings to process")
            return True

        logger.info(f"Processing {len(new_recordings)} new recordings")

        success_count = 0
        for recording_id, recording_info in new_recordings.items():
            try:
                logger.info(f"Processing recording {recording_id}")

                # Copy recording from Tablo drive
                raw_file = self._copy_recording(recording_id, recording_info)
                if not raw_file:
                    logger.error(f"Failed to copy recording {recording_id}")
                    continue

                # Get duration
                duration = self._get_duration(raw_file)
                if not duration:
                    logger.error(f"Failed to get duration for {recording_id}")
                    continue

                # Remove commercials
                clean_file = self._remove_commercials(recording_id, raw_file)
                if not clean_file:
                    logger.error(f"Failed to process commercials for {recording_id}")
                    continue

                # Write metadata
                self._write_metadata(recording_id, raw_file, clean_file, recording_info, duration)

                # Update state
                processed_ids.add(recording_id)
                self.state['processed_ids'] = list(processed_ids)
                self._save_state()

                # Cleanup raw file to save space
                try:
                    os.remove(raw_file)
                    logger.info(f"Cleaned up raw file: {raw_file}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup raw file {raw_file}: {e}")

                success_count += 1
                logger.info(f"Successfully processed recording {recording_id}")

            except Exception as e:
                logger.error(f"Failed to process recording {recording_id}: {e}")
                continue

        logger.info(f"Drive processing complete: {success_count}/{len(new_recordings)} recordings processed")
        return success_count > 0


def main():
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
    else:
        config_path = "config.yaml"

    puller = TabloDrivePuller(config_path)
    success = puller.process_tablo_drive()

    if success:
        logger.info("Tablo drive processing completed successfully")
        sys.exit(0)
    else:
        logger.error("Tablo drive processing failed")
        sys.exit(1)


if __name__ == "__main__":
    main()