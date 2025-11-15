#!/usr/bin/env python3
"""
Tablo Authentication Handler for 4th Generation Devices
Handles discovery, pairing, and authentication for modern Tablo firmware
"""

import json
import logging
import requests
import time
from typing import Dict, Optional, Set
import urllib.parse

logger = logging.getLogger(__name__)


class TabloAuth:
    """Authentication handler for 4th generation Tablo devices"""

    def __init__(self, ip: str, port: int = 80):
        self.ip = ip
        self.port = port
        self.base_url = f"http://{ip}:{port}"
        self.session = requests.Session()
        self.auth_token = None
        self.device_id = None

        # Set headers that mimic the Tablo web app
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
            'Referer': self.base_url
        })

    def discover_device(self) -> bool:
        """Discover and identify the Tablo device"""
        try:
            # Check basic connectivity
            response = self.session.get(self.base_url, timeout=10)
            if response.status_code == 200:
                if "Tablo Server" in response.text:
                    logger.info(f"Tablo device discovered at {self.base_url}")
                    return True
            return False
        except Exception as e:
            logger.error(f"Failed to discover Tablo device: {e}")
            return False

    def attempt_legacy_access(self) -> bool:
        """Try to access older Tablo API endpoints"""
        legacy_endpoints = [
            '/pvr/',
            '/pvr/recordings',
            '/recordings',
            '/api/recordings',
            '/server/info',
            '/info'
        ]

        for endpoint in legacy_endpoints:
            try:
                url = self.base_url + endpoint
                response = self.session.get(url, timeout=10)

                if response.status_code == 200:
                    logger.info(f"✓ Legacy endpoint accessible: {endpoint}")
                    return True
                elif response.status_code == 403:
                    logger.info(f"✗ Legacy endpoint requires auth: {endpoint}")
                else:
                    logger.info(f"✗ Legacy endpoint returned {response.status_code}: {endpoint}")

            except Exception as e:
                logger.debug(f"Failed to access {endpoint}: {e}")

        return False

    def discover_recordings_via_broadcast(self) -> Set[str]:
        """Try to discover recordings through broadcast/discovery methods"""
        recording_ids = set()

        # Try various discovery methods
        discovery_methods = [
            # Direct HLS playlist approach
            lambda: self._discover_hls_playlists(),
            # Directory listing approach
            lambda: self._discover_directory_listings(),
            # Broadcast API approach
            lambda: self._discover_broadcast_api(),
        ]

        for method in discovery_methods:
            try:
                ids = method()
                if ids:
                    recording_ids.update(ids)
                    logger.info(f"Found {len(ids)} recordings via discovery method")
                    break
            except Exception as e:
                logger.debug(f"Discovery method failed: {e}")

        return recording_ids

    def _discover_hls_playlists(self) -> Set[str]:
        """Discover recordings by trying common recording ID patterns"""
        recording_ids = set()

        # Try common ID ranges (Tablo typically uses sequential IDs)
        for recording_id in range(100000, 100200):  # Try a reasonable range
            playlist_url = f"{self.base_url}/pvr/{recording_id}/pl/playlist.m3u8"

            try:
                response = self.session.get(playlist_url, timeout=5)
                if response.status_code == 200 and '#EXTM3U' in response.text:
                    recording_ids.add(str(recording_id))
                    logger.debug(f"Found recording: {recording_id}")
            except:
                continue

            # Don't overwhelm the device
            if recording_id % 10 == 0:
                time.sleep(0.1)

        return recording_ids

    def _discover_directory_listings(self) -> Set[str]:
        """Discover recordings via directory listings"""
        recording_ids = set()

        try:
            # Try to access PVR directory
            response = self.session.get(f"{self.base_url}/pvr/", timeout=10)
            if response.status_code == 200:
                # Look for recording ID patterns in the response
                import re
                pattern = r'href=["\']/?(\d{6,})["\']'
                matches = re.findall(pattern, response.text)
                recording_ids.update(matches)

        except Exception as e:
            logger.debug(f"Directory listing failed: {e}")

        return recording_ids

    def _discover_broadcast_api(self) -> Set[str]:
        """Try broadcast/discovery APIs"""
        recording_ids = set()

        try:
            # Some Tablo devices expose recordings via broadcast endpoints
            broadcast_endpoints = ['/broadcast', '/broadcasts', '/api/broadcast']
            for endpoint in broadcast_endpoints:
                response = self.session.get(self.base_url + endpoint, timeout=10)
                if response.status_code == 200:
                    try:
                        data = response.json()
                        if 'recordings' in data or 'broadcasts' in data:
                            items = data.get('recordings', data.get('broadcasts', []))
                            for item in items:
                                if 'id' in item:
                                    recording_ids.add(str(item['id']))
                    except:
                        continue
        except Exception as e:
            logger.debug(f"Broadcast API failed: {e}")

        return recording_ids

    def get_recording_segments(self, recording_id: str) -> Optional[list]:
        """Get segment list for a recording"""
        try:
            # Try different segment URL patterns
            segment_urls = [
                f"{self.base_url}/pvr/{recording_id}/segs/",
                f"{self.base_url}/pvr/{recording_id}/segments/",
                f"{self.base_url}/segs/{recording_id}/",
            ]

            for url in segment_urls:
                try:
                    response = self.session.get(url, timeout=10)
                    if response.status_code == 200:
                        # Parse HTML or JSON response for segment files
                        if 'application/json' in response.headers.get('content-type', ''):
                            data = response.json()
                            return data.get('segments', [])
                        else:
                            # Parse HTML for .ts files
                            import re
                            ts_files = re.findall(r'href=["\']([^"\']*\.ts)["\']', response.text)
                            if ts_files:
                                return ts_files
                except:
                    continue

        except Exception as e:
            logger.error(f"Failed to get segments for {recording_id}: {e}")

        return None

    def get_hls_playlist(self, recording_id: str) -> Optional[str]:
        """Get HLS playlist URL for a recording"""
        try:
            playlist_urls = [
                f"{self.base_url}/pvr/{recording_id}/pl/playlist.m3u8",
                f"{self.base_url}/pvr/{recording_id}/playlist.m3u8",
                f"{self.base_url}/hls/{recording_id}/playlist.m3u8",
            ]

            for url in playlist_urls:
                try:
                    response = self.session.get(url, timeout=10)
                    if response.status_code == 200 and '#EXTM3U' in response.text:
                        return url
                except:
                    continue

        except Exception as e:
            logger.error(f"Failed to get HLS playlist for {recording_id}: {e}")

        return None


def test_tablo_4gen(ip: str, port: int = 80) -> bool:
    """Test connection to a 4th generation Tablo device"""
    auth = TabloAuth(ip, port)

    logger.info(f"Testing 4th Gen Tablo at {ip}:{port}")

    # Discover device
    if not auth.discover_device():
        logger.error("Could not discover Tablo device")
        return False

    # Test legacy access
    if auth.attempt_legacy_access():
        logger.info("Legacy access successful")
        return True

    # Try discovery methods
    recording_ids = auth.discover_recordings_via_broadcast()
    if recording_ids:
        logger.info(f"Discovered {len(recording_ids)} recordings")
        return True

    logger.error("Could not access Tablo recordings")
    return False


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    ip = sys.argv[1] if len(sys.argv) > 1 else "192.168.7.123"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 80

    success = test_tablo_4gen(ip, port)
    print(f"\nTest {'SUCCESS' if success else 'FAILED'}")