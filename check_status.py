#!/usr/bin/env python3
import subprocess
import json
import sys

# Check webapp status
result = subprocess.run(
    ['az', 'webapp', 'show', '--name', 'visiondock-api', '--resource-group', 'vision-doc', 
     '--query', '{state:state,host:defaultHostName,linuxFxVersion:siteConfig.linuxFxVersion}', '-o', 'json'],
    capture_output=True, text=True
)

if result.returncode == 0:
    data = json.loads(result.stdout)
    print(f"WebApp State: {data.get('state', 'unknown')}")
    print(f"Hostname: {data.get('host', 'unknown')}")
    print(f"Linux Version: {data.get('linuxFxVersion', 'unknown')}")
else:
    print(f"Error checking webapp: {result.stderr}")
    sys.exit(1)

# Try to curl the endpoint
import urllib.request
import ssl
import socket

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

try:
    response = urllib.request.urlopen(
        'https://visiondock-api.azurewebsites.net/', 
        timeout=10, 
        context=ctx
    )
    print(f"\nHTTP Status: {response.status}")
    body = response.read().decode('utf-8', errors='ignore')[:200]
    print(f"Response: {body}")
except urllib.error.HTTPError as e:
    print(f"\nHTTP Error: {e.code} - {e.reason}")
except urllib.error.URLError as e:
    print(f"\nURL Error: {e.reason}")
except socket.timeout:
    print("\nConnection timed out after 10 seconds")
except Exception as e:
    print(f"\nError: {type(e).__name__}: {e}")
