#!/usr/bin/env python3
"""
Identify and Rename: match clean recordings to EPG, use LLM for disambiguation, move to Plex.
"""

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
import yaml
from dateutil import parser as date_parser
from dateutil.tz import tzlocal

# Import our other modules
from epg_cache import TVMazeCache

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RecordingIdentifier:
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path) as f:
            self.cfg = yaml.safe_load(f)

        # Setup paths
        for path_key in ['meta_dir', 'epg_dir', 'logs_dir']:
            Path(self.cfg['paths'][path_key]).mkdir(parents=True, exist_ok=True)

        Path(self.cfg['paths']['plex_tv_root']).mkdir(parents=True, exist_ok=True)

        self.epg_cache = TVMazeCache(config_path)
        self.session = requests.Session()

    def _load_metadata(self) -> List[Dict]:
        """Load all metadata files for clean recordings."""
        meta_dir = Path(self.cfg['paths']['meta_dir'])
        metadata_list = []

        for meta_file in meta_dir.glob("*.json"):
            try:
                with open(meta_file) as f:
                    metadata = json.load(f)

                # Only process recordings that are clean but not yet identified
                if metadata.get('status') == 'clean' and not metadata.get('final_path'):
                    metadata_list.append(metadata)

            except Exception as e:
                logger.error(f"Failed to load metadata from {meta_file}: {e}")

        logger.info(f"Found {len(metadata_list)} recordings ready for identification")
        return metadata_list

    def _save_metadata(self, metadata: Dict):
        """Save updated metadata."""
        meta_file = Path(self.cfg['paths']['meta_dir']) / f"{metadata['id']}.json"
        with open(meta_file, 'w') as f:
            json.dump(metadata, f, indent=2)

    def _transcribe_audio(self, video_file: str) -> Optional[str]:
        """Transcribe audio using Whisper."""
        logger.info(f"Transcribing audio from {video_file}")

        cmd = [
            self.cfg['tools']['whisper'],
            video_file,
            '--model', 'base',  # Use base model for speed
            '--language', 'en',
            '--output_format', 'json',
            '--output_dir', os.path.dirname(video_file)
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                logger.error(f"Whisper failed: {result.stderr}")
                return None

            # Load the generated JSON transcript
            json_file = Path(video_file).with_suffix('.json')
            if json_file.exists():
                with open(json_file) as f:
                    transcript_data = json.load(f)

                # Cleanup transcript file
                json_file.unlink()

                # Extract text from segments
                text_segments = [seg.get('text', '') for seg in transcript_data.get('segments', [])]
                transcript = ' '.join(text_segments).strip()

                logger.info(f"Transcription complete: {len(transcript)} characters")
                return transcript

        except subprocess.TimeoutExpired:
            logger.error(f"Whisper timeout for {video_file}")
            return None
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return None

    def _query_llm(self, candidates: List[Dict], transcript: str) -> Optional[str]:
        """Query Ollama LLM to choose the best match."""
        if not candidates:
            return None

        # If only one candidate, use it
        if len(candidates) == 1:
            return candidates[0]['id']

        logger.info(f"Querying LLM to disambiguate {len(candidates)} candidates")

        # Build prompt
        candidate_descriptions = []
        for i, candidate in enumerate(candidates):
            desc = f"{i+1}. {candidate['title']} on {candidate['network']} at {candidate['air_utc']}"
            candidate_descriptions.append(desc)

        prompt = f"""You are helping identify a TV recording from a transcript.

Here are the possible candidates:
{chr(10).join(candidate_descriptions)}

Transcript excerpt (first 500 characters):
{transcript[:500]}...

Which candidate (1-{len(candidates)}) most likely matches this transcript? Respond with just the number.

If none are a clear match, respond with "0"."""

        # Query Ollama
        max_attempts = self.cfg['llm']['max_attempts']

        for attempt in range(max_attempts):
            try:
                response = self.session.post(
                    self.cfg['llm']['url'],
                    json={
                        "model": self.cfg['llm']['model'],
                        "prompt": prompt,
                        "stream": False
                    },
                    timeout=60
                )
                response.raise_for_status()

                result = response.json()
                llm_response = result.get('response', '').strip()

                # Extract number from response
                match = re.search(r'\b([1-9]0?)\b', llm_response)
                if match:
                    choice_num = int(match.group(1))
                    if 1 <= choice_num <= len(candidates):
                        logger.info(f"LLM chose candidate {choice_num}: {candidates[choice_num-1]['title']}")
                        return candidates[choice_num-1]['id']
                    elif choice_num == 0:
                        logger.info("LLM indicated no clear match")
                        return None

                logger.warning(f"Could not parse LLM response: {llm_response}")

            except Exception as e:
                logger.error(f"LLM query attempt {attempt+1} failed: {e}")
                if attempt < max_attempts - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff

        logger.error("All LLM query attempts failed")
        return None

    def _build_plex_filename(self, metadata: Dict, episode: Dict) -> str:
        """Build Plex-style filename."""
        show_name = episode['show']
        season = episode.get('season')
        episode_num = episode.get('episode')
        episode_title = episode.get('episode_title', 'Untitled')

        # Clean show name (remove invalid characters)
        show_clean = re.sub(r'[<>:"/\\|?*]', '', show_name).strip()

        # Clean episode title
        title_clean = re.sub(r'[<>:"/\\|?*]', '', episode_title).strip()

        if season and episode_num:
            filename = f"{show_clean} - S{season:02d}E{episode_num:02d} - {title_clean}.mp4"
        else:
            filename = f"{show_clean} - {title_clean}.mp4"

        return filename

    def _get_plex_show_path(self, show_name: str) -> Path:
        """Get or create Plex show directory."""
        plex_root = Path(self.cfg['paths']['plex_tv_root'])
        show_clean = re.sub(r'[<>:"/\\|?*]', '', show_name).strip()
        show_path = plex_root / show_clean
        show_path.mkdir(parents=True, exist_ok=True)
        return show_path

    def _move_to_plex(self, metadata: Dict, episode: Dict) -> Optional[str]:
        """Move file to Plex library and return final path."""
        clean_file = Path(metadata['clean_file'])
        if not clean_file.exists():
            logger.error(f"Clean file not found: {clean_file}")
            return None

        # Build destination
        show_path = self._get_plex_show_path(episode['show'])
        filename = self._build_plex_filename(metadata, episode)
        dest_file = show_path / filename

        # Handle filename conflicts
        counter = 1
        original_dest = dest_file
        while dest_file.exists():
            stem = original_dest.stem
            suffix = original_dest.suffix
            dest_file = show_path / f"{stem}_{counter}{suffix}"
            counter += 1

        try:
            logger.info(f"Moving {clean_file} to {dest_file}")
            shutil.move(str(clean_file), str(dest_file))

            # Update metadata
            metadata['final_path'] = str(dest_file)
            metadata['status'] = 'moved_to_plex'
            metadata['moved_at'] = datetime.now().isoformat()

            logger.info(f"Successfully moved to Plex: {dest_file}")
            return str(dest_file)

        except Exception as e:
            logger.error(f"Failed to move file to Plex: {e}")
            return None

    def _identify_recording(self, metadata: Dict) -> bool:
        """Identify a single recording and move to Plex if successful."""
        recording_id = metadata['id']
        start_time_utc = metadata['start_time_utc']
        end_time_utc = metadata['end_time_utc']
        duration_seconds = metadata['duration_seconds']

        logger.info(f"Identifying recording {recording_id}")

        # Find EPG matches
        candidates = self.epg_cache.find_matches(start_time_utc, end_time_utc, duration_seconds)

        if not candidates:
            logger.warning(f"No EPG matches found for recording {recording_id}")
            metadata['status'] = 'unidentified'
            metadata['identification_attempt'] = datetime.now().isoformat()
            return False

        logger.info(f"Found {len(candidates)} EPG candidates for recording {recording_id}")

        # If multiple candidates, use LLM to disambiguate
        if len(candidates) > 1:
            # Transcribe audio
            clean_file = metadata['clean_file']
            transcript = self._transcribe_audio(clean_file)

            if not transcript:
                logger.warning(f"Failed to transcribe {recording_id}, using first candidate")
                chosen_episode = candidates[0]
            else:
                # Use LLM to choose
                chosen_id = self._query_llm(candidates, transcript)
                if chosen_id:
                    chosen_episode = next(c for c in candidates if c['id'] == chosen_id)
                else:
                    logger.warning(f"LLM couldn't decide, using first candidate for {recording_id}")
                    chosen_episode = candidates[0]
        else:
            chosen_episode = candidates[0]

        # Update metadata
        metadata['epg_match'] = chosen_episode
        metadata['status'] = 'identified'

        # Move to Plex
        final_path = self._move_to_plex(metadata, chosen_episode)
        if final_path:
            metadata['final_path'] = final_path
            metadata['status'] = 'moved_to_plex'
            logger.info(f"Successfully identified and moved recording {recording_id}")
            return True
        else:
            metadata['status'] = 'identification_failed'
            logger.error(f"Failed to move recording {recording_id} to Plex")
            return False

    def process_recordings(self):
        """Main processing: identify and rename all clean recordings."""
        metadata_list = self._load_metadata()

        if not metadata_list:
            logger.info("No recordings ready for identification")
            return

        success_count = 0
        total_count = len(metadata_list)

        for metadata in metadata_list:
            try:
                if self._identify_recording(metadata):
                    success_count += 1

                # Save updated metadata
                self._save_metadata(metadata)

            except Exception as e:
                logger.error(f"Failed to process recording {metadata.get('id', 'unknown')}: {e}")
                continue

        logger.info(f"Processing complete: {success_count}/{total_count} recordings successfully identified and moved")


def main():
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
    else:
        config_path = "config.yaml"

    identifier = RecordingIdentifier(config_path)
    identifier.process_recordings()


if __name__ == "__main__":
    main()