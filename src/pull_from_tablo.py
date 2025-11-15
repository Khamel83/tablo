#!/usr/bin/env python3
"""
Pull from Tablo: discover new recordings, download HLS, remove commercials, write metadata.
"""

import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import urllib.parse

import requests
import yaml
from dateutil.tz import tzlocal

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TabloPuller:
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path) as f:
            self.cfg = yaml.safe_load(f)

        # Setup paths
        for path_key in ['raw_dir', 'clean_dir', 'meta_dir', 'epg_dir', 'logs_dir']:
            Path(self.cfg['paths'][path_key]).mkdir(parents=True, exist_ok=True)

        self.state = self._load_state()
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'TabloAutoRenamer/1.0'})

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

    def _discover_recordings(self) -> Set[str]:
        """Fetch recordings list from Tablo /pvr/ and extract recording IDs."""
        tablo_ip = self.cfg['tablo']['ip']
        url = f"http://{tablo_ip}/pvr/"

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            html = response.text
        except Exception as e:
            logger.error(f"Failed to fetch recordings from {url}: {e}")
            return set()

        # Extract recording IDs from href="/pvr/123456/" patterns
        pattern = r'href=["\']/pvr/(\d+)/["\']'
        found_ids = set(re.findall(pattern, html))

        logger.info(f"Discovered {len(found_ids)} recordings on Tablo")
        return found_ids

    def _get_segment_list(self, recording_id: str) -> Optional[List[str]]:
        """Get list of segment files for a recording."""
        tablo_ip = self.cfg['tablo']['ip']
        url = f"http://{tablo_ip}/pvr/{recording_id}/segs/"

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            html = response.text
        except Exception as e:
            logger.error(f"Failed to fetch segments for recording {recording_id}: {e}")
            return None

        # Extract segment filenames
        pattern = r'href=["\']([^"\']*\.ts)["\']'
        segments = re.findall(pattern, html)

        if not segments:
            logger.error(f"No segments found for recording {recording_id}")
            return None

        # Sort segments numerically
        segments.sort(key=lambda x: int(re.search(r'(\d+)', x).group(1)))
        return segments

    def _get_segment_timestamps(self, recording_id: str, segments: List[str]) -> Tuple[float, float]:
        """Get approximate start and end times from segment files."""
        tablo_ip = self.cfg['tablo']['ip']

        # Try to get timestamps from HTTP headers
        try:
            # Get first segment timestamp
            first_url = f"http://{tablo_ip}/pvr/{recording_id}/segs/{segments[0]}"
            first_response = self.session.head(first_url, timeout=10)
            first_time = datetime.fromtimestamp(
                time.mktime(time.strptime(first_response.headers.get('last-modified', ''),
                                         '%a, %d %b %Y %H:%M:%S %Z'))
            ).timestamp() if first_response.headers.get('last-modified') else time.time()

            # Get last segment timestamp
            last_url = f"http://{tablo_ip}/pvr/{recording_id}/segs/{segments[-1]}"
            last_response = self.session.head(last_url, timeout=10)
            last_time = datetime.fromtimestamp(
                time.mktime(time.strptime(last_response.headers.get('last-modified', ''),
                                        '%a, %d %b %Y %H:%M:%S %Z'))
            ).timestamp() if last_response.headers.get('last-modified') else time.time()

            return first_time, last_time
        except Exception as e:
            logger.warning(f"Could not get HTTP timestamps for {recording_id}: {e}")
            # Fallback: use current time for end, estimate start based on typical recording length
            end_time = time.time()
            start_time = end_time - (30 * 60)  # Assume 30 minutes
            return start_time, end_time

    def _download_hls(self, recording_id: str, segments: List[str]) -> Optional[str]:
        """Download HLS segments and concatenate to raw .ts file."""
        raw_dir = Path(self.cfg['paths']['raw_dir'])
        raw_file = raw_dir / f"{recording_id}.ts"

        if raw_file.exists():
            logger.info(f"Raw file already exists: {raw_file}")
            return str(raw_file)

        tablo_ip = self.cfg['tablo']['ip']
        segment_urls = [
            f"http://{tablo_ip}/pvr/{recording_id}/segs/{seg}"
            for seg in segments
        ]

        # Create ffmpeg input file list
        input_file = raw_dir / f"{recording_id}_segments.txt"
        with open(input_file, 'w') as f:
            for url in segment_urls:
                f.write(f"file '{url}'\n")

        # Use ffmpeg to concatenate
        cmd = [
            self.cfg['tools']['ffmpeg'],
            '-f', 'concat',
            '-safe', '0',
            '-i', str(input_file),
            '-c', 'copy',
            str(raw_file)
        ]

        try:
            logger.info(f"Downloading recording {recording_id} ({len(segments)} segments)")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            if result.returncode != 0:
                logger.error(f"ffmpeg failed: {result.stderr}")
                return None

            # Cleanup segment list file
            input_file.unlink()

            logger.info(f"Downloaded recording {recording_id} to {raw_file}")
            return str(raw_file)

        except subprocess.TimeoutExpired:
            logger.error(f"Download timeout for recording {recording_id}")
            return None
        except Exception as e:
            logger.error(f"Download failed for recording {recording_id}: {e}")
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

        # Run Comskip to generate commercial detection file
        comskip_cmd = [self.cfg['tools']['comskip'], raw_file]

        try:
            logger.info(f"Running Comskip on {recording_id}")
            result = subprocess.run(comskip_cmd, capture_output=True, text=True, timeout=1800)
            if result.returncode != 0:
                logger.warning(f"Comskip failed, using original file: {result.stderr}")
                # Copy original file as clean
                subprocess.run([
                    self.cfg['tools']['ffmpeg'],
                    '-i', raw_file,
                    '-c', 'copy',
                    str(clean_file)
                ], check=True)
                return str(clean_file)
        except subprocess.TimeoutExpired:
            logger.warning(f"Comskip timeout for recording {recording_id}, using original")
            # Copy original file as clean
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

        # Check for .edl file (commercial cut points)
        edl_file = Path(raw_file).with_suffix('.edl')
        if not edl_file.exists():
            logger.warning(f"No .edl file found, using original file")
            subprocess.run([
                self.cfg['tools']['ffmpeg'],
                '-i', raw_file,
                '-c', 'copy',
                str(clean_file)
            ], check=True)
            return str(clean_file)

        # Use ffmpeg with .edl file to remove commercials
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

        try:
            logger.info(f"Creating commercial-free version of {recording_id}")
            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=3600)
            if result.returncode != 0:
                logger.warning(f"ffmpeg with EDL failed: {result.stderr}")
                # Fallback: copy original
                subprocess.run([
                    self.cfg['tools']['ffmpeg'],
                    '-i', raw_file,
                    '-c', 'copy',
                    str(clean_file)
                ], check=True)

            # Cleanup .edl file
            edl_file.unlink()

            logger.info(f"Commercial removal complete: {clean_file}")
            return str(clean_file)

        except Exception as e:
            logger.error(f"Commercial removal failed: {e}")
            return None

    def _write_metadata(self, recording_id: str, raw_file: str, clean_file: str,
                       start_time: float, end_time: float, duration: float):
        """Write metadata JSON file for the recording."""
        meta_dir = Path(self.cfg['paths']['meta_dir'])
        meta_file = meta_dir / f"{recording_id}.json"

        # Convert timestamps to ISO format with timezone
        tz = self.cfg['timezone']
        start_iso = datetime.fromtimestamp(start_time, tz=tz).isoformat()
        end_iso = datetime.fromtimestamp(end_time, tz=tz).isoformat()

        metadata = {
            "id": recording_id,
            "raw_file": raw_file,
            "clean_file": clean_file,
            "start_time_utc": datetime.fromtimestamp(start_time, tz=timezone.utc).isoformat(),
            "end_time_utc": datetime.fromtimestamp(end_time, tz=timezone.utc).isoformat(),
            "start_time_local": start_iso,
            "end_time_local": end_iso,
            "duration_seconds": duration,
            "status": "clean",  # Initial status after commercial removal
            "final_path": None,
            "epg_match": None,
            "llm_choice": None,
            "created_at": datetime.now(tz=tz).isoformat()
        }

        with open(meta_file, 'w') as f:
            json.dump(metadata, f, indent=2)

        logger.info(f"Metadata written: {meta_file}")

    def process_new_recordings(self):
        """Main processing loop: discover and process new recordings."""
        discovered_ids = self._discover_recordings()
        processed_ids = set(self.state.get('processed_ids', []))
        new_ids = discovered_ids - processed_ids

        if not new_ids:
            logger.info("No new recordings found")
            return

        logger.info(f"Processing {len(new_ids)} new recordings")

        for recording_id in new_ids:
            try:
                logger.info(f"Processing recording {recording_id}")

                # Get segment list
                segments = self._get_segment_list(recording_id)
                if not segments:
                    logger.error(f"Skipping {recording_id}: no segments found")
                    continue

                # Get timestamps
                start_time, end_time = self._get_segment_timestamps(recording_id, segments)

                # Download HLS
                raw_file = self._download_hls(recording_id, segments)
                if not raw_file:
                    logger.error(f"Skipping {recording_id}: download failed")
                    continue

                # Get duration
                duration = self._get_duration(raw_file)
                if not duration:
                    logger.error(f"Skipping {recording_id}: could not determine duration")
                    continue

                # Remove commercials
                clean_file = self._remove_commercials(recording_id, raw_file)
                if not clean_file:
                    logger.error(f"Skipping {recording_id}: commercial removal failed")
                    continue

                # Write metadata
                self._write_metadata(recording_id, raw_file, clean_file, start_time, end_time, duration)

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

                logger.info(f"Successfully processed recording {recording_id}")

            except Exception as e:
                logger.error(f"Failed to process recording {recording_id}: {e}")
                continue

        logger.info(f"Processing complete. Processed {len(new_ids)} recordings.")


def main():
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
    else:
        config_path = "config.yaml"

    puller = TabloPuller(config_path)
    puller.process_new_recordings()


if __name__ == "__main__":
    main()