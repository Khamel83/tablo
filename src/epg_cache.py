#!/usr/bin/env python3
"""
EPG Cache: fetch TVMaze schedule and cache locally for matching.
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import requests
import yaml
from dateutil import parser as date_parser

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TVMazeCache:
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path) as f:
            self.cfg = yaml.safe_load(f)

        # Setup paths
        Path(self.cfg['paths']['epg_dir']).mkdir(parents=True, exist_ok=True)
        Path(self.cfg['paths']['logs_dir']).mkdir(parents=True, exist_ok=True)

        self.state = self._load_state()
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'TabloAutoRenamer/1.0'})

    def _load_state(self) -> Dict:
        state_file = self.cfg['paths']['state_file']
        if os.path.exists(state_file):
            with open(state_file) as f:
                return json.load(f)
        return {"processed_ids": [], "last_epg_fetch": None}

    def _save_state(self):
        state_file = self.cfg['paths']['state_file']
        with open(state_file, 'w') as f:
            json.dump(self.state, f, indent=2)

    def _fetch_schedule(self, start_date: datetime, end_date: datetime) -> List[Dict]:
        """Fetch TV schedule from TVMaze API."""
        base_url = "https://api.tvmaze.com/schedule"
        country = self.cfg['epg']['country']
        networks = self.cfg['epg']['networks']

        schedule_data = []
        current_date = start_date

        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            url = f"{base_url}?country={country}&date={date_str}"

            try:
                logger.info(f"Fetching schedule for {date_str}")
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                day_schedule = response.json()

                # Filter by configured networks
                filtered_schedule = [
                    item for item in day_schedule
                    if item.get('show', {}).get('network', {}).get('name') in networks
                ]

                schedule_data.extend(filtered_schedule)
                logger.info(f"Found {len(filtered_schedule)} matching episodes for {date_str}")

            except Exception as e:
                logger.error(f"Failed to fetch schedule for {date_str}: {e}")

            current_date += timedelta(days=1)
            time.sleep(1)  # Rate limiting

        return schedule_data

    def _normalize_episode(self, item: Dict) -> Optional[Dict]:
        """Normalize TVMaze episode data to our standard format."""
        try:
            show = item.get('show', {})
            network = show.get('network', {})
            episode = item.get('episode', {})

            # Parse airstamp
            airstamp = episode.get('airstamp')
            if not airstamp:
                return None

            air_datetime = date_parser.parse(airstamp)
            air_utc = air_datetime.isoformat()

            # Extract season/episode info
            season = episode.get('season')
            episode_number = episode.get('number')

            # Build title
            show_name = show.get('name', 'Unknown Show')
            episode_title = episode.get('name', 'Untitled Episode')

            if season and episode_number:
                title = f"{show_name} - S{season:02d}E{episode_number:02d} - {episode_title}"
            else:
                title = f"{show_name} - {episode_title}"

            return {
                "id": f"{show_name}_{air_utc.replace(':', '-')}",  # Unique ID
                "title": title,
                "show": show_name,
                "season": season,
                "episode": episode_number,
                "episode_title": episode_title,
                "network": network.get('name'),
                "air_utc": air_utc,
                "runtime_min": episode.get('runtime', 30),  # Default to 30 minutes
                "summary": episode.get('summary', '').strip(),
                "tvmaze_id": episode.get('id'),
                "show_id": show.get('id')
            }

        except Exception as e:
            logger.warning(f"Failed to normalize episode data: {e}")
            return None

    def _save_schedule(self, schedule_data: List[Dict]):
        """Save schedule data to local cache files."""
        epg_dir = Path(self.cfg['paths']['epg_dir'])

        # Save full schedule
        full_schedule_file = epg_dir / "schedule.json"
        with open(full_schedule_file, 'w') as f:
            json.dump(schedule_data, f, indent=2)

        # Save by network
        network_schedules = {}
        for item in schedule_data:
            network = item.get('network', 'Unknown')
            if network not in network_schedules:
                network_schedules[network] = []
            network_schedules[network].append(item)

        for network, items in network_schedules.items():
            network_file = epg_dir / f"schedule_{network.lower().replace(' ', '_')}.json"
            with open(network_file, 'w') as f:
                json.dump(items, f, indent=2)

        # Save by date
        date_schedules = {}
        for item in schedule_data:
            air_date = item.get('air_utc', '')[:10]  # YYYY-MM-DD
            if air_date not in date_schedules:
                date_schedules[air_date] = []
            date_schedules[air_date].append(item)

        for date, items in date_schedules.items():
            date_file = epg_dir / f"schedule_{date}.json"
            with open(date_file, 'w') as f:
                json.dump(items, f, indent=2)

        logger.info(f"Saved {len(schedule_data)} episodes to cache")

    def _is_cache_fresh(self) -> bool:
        """Check if cached EPG data is still fresh."""
        last_fetch = self.state.get('last_epg_fetch')
        if not last_fetch:
            return False

        try:
            last_fetch_dt = date_parser.parse(last_fetch)
            # Cache is fresh if less than 6 hours old
            fresh_threshold = datetime.now() - timedelta(hours=6)
            return last_fetch_dt > fresh_threshold
        except:
            return False

    def update_cache(self, force: bool = False):
        """Update EPG cache from TVMaze API."""
        if not force and self._is_cache_fresh():
            logger.info("EPG cache is fresh, skipping update")
            return

        logger.info("Updating EPG cache from TVMaze")

        # Calculate date range
        days_back = self.cfg['epg']['days_back']
        days_forward = self.cfg['epg']['days_forward']
        start_date = datetime.now() - timedelta(days=days_back)
        end_date = datetime.now() + timedelta(days=days_forward)

        # Fetch schedule
        raw_schedule = self._fetch_schedule(start_date, end_date)

        if not raw_schedule:
            logger.error("No schedule data fetched")
            return

        # Normalize data
        normalized_schedule = []
        for item in raw_schedule:
            normalized = self._normalize_episode(item)
            if normalized:
                normalized_schedule.append(normalized)

        if not normalized_schedule:
            logger.error("No valid episodes after normalization")
            return

        # Save to cache
        self._save_schedule(normalized_schedule)

        # Update state
        self.state['last_epg_fetch'] = datetime.now().isoformat()
        self._save_state()

        logger.info(f"EPG cache updated successfully with {len(normalized_schedule)} episodes")

    def get_schedule(self) -> List[Dict]:
        """Load schedule from cache."""
        epg_dir = Path(self.cfg['paths']['epg_dir'])
        schedule_file = epg_dir / "schedule.json"

        if not schedule_file.exists():
            logger.warning("No cached schedule found, updating cache first")
            self.update_cache()

        if not schedule_file.exists():
            logger.error("Still no cached schedule after update")
            return []

        try:
            with open(schedule_file) as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load cached schedule: {e}")
            return []

    def find_matches(self, start_time_utc: str, end_time_utc: str, duration_seconds: float) -> List[Dict]:
        """Find potential EPG matches for a recording."""
        schedule = self.get_schedule()
        if not schedule:
            return []

        # Convert times to datetime objects for comparison
        start_dt = date_parser.parse(start_time_utc)
        end_dt = date_parser.parse(end_time_utc)
        duration_min = duration_seconds / 60

        matches = []
        start_window = self.cfg['match']['start_window']
        duration_window = self.cfg['match']['duration_window']

        for episode in schedule:
            try:
                episode_air = date_parser.parse(episode['air_utc'])
                episode_runtime = episode.get('runtime_min', 30)

                # Check time window
                time_diff = abs((start_dt - episode_air).total_seconds())
                if time_diff > start_window:
                    continue

                # Check duration similarity
                duration_diff = abs(duration_min - episode_runtime)
                if duration_diff > duration_window / 60:
                    continue

                matches.append({
                    **episode,
                    'time_diff_seconds': time_diff,
                    'duration_diff_minutes': duration_diff
                })

            except Exception as e:
                logger.warning(f"Error processing episode {episode.get('id', 'unknown')}: {e}")
                continue

        # Sort by time difference (closest match first)
        matches.sort(key=lambda x: x['time_diff_seconds'])
        return matches

    def get_episode_by_id(self, episode_id: str) -> Optional[Dict]:
        """Get specific episode from cache."""
        schedule = self.get_schedule()
        for episode in schedule:
            if episode.get('id') == episode_id:
                return episode
        return None


def main():
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
    else:
        config_path = "config.yaml"

    cache = TVMazeCache(config_path)

    # Check for force flag
    force_update = '--force' in sys.argv

    cache.update_cache(force=force_update)

    # Print summary
    schedule = cache.get_schedule()
    print(f"Cache contains {len(schedule)} episodes")
    networks = set(ep.get('network', 'Unknown') for ep in schedule)
    print(f"Networks: {', '.join(sorted(networks))}")


if __name__ == "__main__":
    main()