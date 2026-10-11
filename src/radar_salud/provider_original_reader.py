"""Ordinary native browser fallback for public Dávila article HTTP403 only.

No challenge solver, alternate identity, authentication or insecure TLS flags.
The caller still verifies original H1, own publication date and editorial gates.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.error import HTTPError
from urllib.parse import urlparse

def read_provider_detail(url, fetch):
    try:
        return fetch(url)
    except HTTPError as denied:
        parsed=urlparse(url)
        if (denied.code!=403 or parsed.scheme!='https'
                or parsed.netloc not in ('www.davila.cl','davila.cl')
                or not __import__('re').fullmatch(r'/novedades/[^/]+/?',parsed.path)):
            raise
        chrome=shutil.which('google-chrome') or shutil.which('chromium')
        if not chrome:
            raise
        with tempfile.TemporaryDirectory(prefix='provider-original-') as profile:
            result=subprocess.run([chrome,'--headless','--disable-gpu','--no-sandbox',
                '--user-data-dir='+str(Path(profile).resolve()),'--virtual-time-budget=5000',
                '--dump-dom',url],capture_output=True,text=True,timeout=25)
        if result.returncode or len(result.stdout.encode())>6*1024*1024 or not result.stdout.strip():
            raise denied
        return result.stdout
