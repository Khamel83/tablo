#!/usr/bin/env python3
"""
Tablo Connectivity Test Script
Tests various methods to connect to Tablo device
"""

import requests
import sys

def test_tablo_connection(ip, port=18080):
    """Test various approaches to connect to Tablo"""

    base_url = f"http://{ip}:{port}"

    # Test different user agents
    user_agents = [
        'Mozilla/5.0 (iPad; CPU OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Tablo/2.0',
        'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'TabloAutoRenamer/1.0'
    ]

    # Test different endpoints
    endpoints = [
        '/',
        '/pvr/',
        '/server/info',
        '/info',
        '/discover',
        '/api/',
        '/api/info',
        '/recordings',
        '/broadcasts',
        '/pvr/pl/',
        '/guide'
    ]

    print(f"Testing Tablo at {base_url}")
    print("=" * 50)

    for ua in user_agents:
        print(f"\nTesting with User-Agent: {ua[:60]}...")

        session = requests.Session()
        session.headers.update({'User-Agent': ua})

        for endpoint in endpoints:
            url = base_url + endpoint
            try:
                response = session.get(url, timeout=10)
                status = response.status_code

                if status == 200:
                    content_type = response.headers.get('content-type', 'unknown')
                    content_len = len(response.content)
                    print(f"  ✓ {endpoint} -> {status} ({content_type}, {content_len} bytes)")

                    # If we get a successful response, show some content
                    if content_len < 500:
                        content_preview = response.text[:100].replace('\n', ' ')
                        print(f"    Content: {content_preview}...")

                elif status == 403:
                    print(f"  ✗ {endpoint} -> {status} (Forbidden)")
                elif status == 404:
                    print(f"  ✗ {endpoint} -> {status} (Not Found)")
                else:
                    print(f"  ✗ {endpoint} -> {status}")

            except requests.exceptions.ConnectRefusedError:
                print(f"  ✗ {endpoint} -> Connection refused")
            except requests.exceptions.Timeout:
                print(f"  ✗ {endpoint} -> Timeout")
            except Exception as e:
                print(f"  ✗ {endpoint} -> {type(e).__name__}: {e}")

def test_tablo_discovery():
    """Test Tablo discovery on common ports"""
    ip = "192.168.7.123"

    common_ports = [80, 443, 18080, 8885, 8080, 8443]

    print(f"Testing Tablo discovery for {ip}")
    print("=" * 50)

    for port in common_ports:
        url = f"http://{ip}:{port}/"
        try:
            response = requests.get(url, timeout=5)
            server = response.headers.get('server', 'unknown')
            print(f"✓ Port {port} -> {response.status_code} (Server: {server})")
        except requests.exceptions.ConnectRefusedError:
            print(f"✗ Port {port} -> Connection refused")
        except requests.exceptions.Timeout:
            print(f"✗ Port {port} -> Timeout")
        except Exception as e:
            print(f"✗ Port {port} -> {type(e).__name__}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        ip = sys.argv[1]
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 18080
    else:
        ip = "192.168.7.123"
        port = 18080

    print("Tablo Connectivity Test")
    print("=" * 50)

    # First test port discovery
    test_tablo_discovery()

    # Then test detailed connection
    test_tablo_connection(ip, port)

    print("\n" + "=" * 50)
    print("Test complete!")
    print("\nIf all endpoints return 403 Forbidden, your Tablo may require:")
    print("1. Authentication via the Tablo app first")
    print("2. A specific pairing process")
    print("3. Authentication tokens/cookies")
    print("\nTry running this from the same network as your Tablo app device.")