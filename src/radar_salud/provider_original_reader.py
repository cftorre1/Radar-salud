"""Ordinary native browser fallback for public Dávila article HTTP403 only.

No challenge solver, alternate identity, authentication or insecure TLS flags.
The caller still verifies original H1, own publication date and editorial gates.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import re
from urllib.error import HTTPError
from urllib.parse import urlparse

def read_provider_detail(url, fetch):
    try:
        return fetch(url)
    except HTTPError as denied:
        parsed=urlparse(url)
        if (denied.code!=403 or parsed.scheme!='https'
                or parsed.netloc not in ('www.davila.cl','davila.cl')
                or parsed.query or parsed.fragment
                or not re.fullmatch(r'/novedades/[^/]+/?',parsed.path)):
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
        if re.search(r'Just a moment|cf-chl-|captcha|Access denied|403 Forbidden|ERR_CERT_',result.stdout,re.I):
            raise denied
        # Native dump-dom cannot expose the final response URL. Require the
        # document's canonical AND its own Article identity before any caller
        # can use header metadata or consume a paid assessment.
        from .public_source_pipeline import _RedSaludArticle
        article=_RedSaludArticle(url);article.feed(result.stdout);article.finish()
        def identity(value):
            if isinstance(value,dict):value=value.get('@id') or value.get('url')
            p=urlparse(str(value or ''))
            return (p.scheme,p.netloc.removeprefix('www.'),p.path.rstrip('/'),p.query)
        own=identity(url)
        if (identity(article.canonical_url)!=own or not any(
                identity(x.get('url') or x.get('mainEntityOfPage') or x.get('@id'))==own
                and x.get('datePublished') for x in article.schemas)):
            raise denied
        return result.stdout
