"""Shared plumbing for open official sources (FNE, Congreso) added 28-oct-2026.

Dirección 28-oct-2026 17:08: "Avanza con FNE y Congreso". These scouts are
deterministic (no AI) and store only what an official listing or web service
publishes as metadata: titles, dates, identifiers, short official procedural
text and links. Bodies of news pages or PDFs are never downloaded.

* Verified-TLS GET restricted to an allowlist of official HTTPS hosts,
  redirects included; bounded response size.
* robots.txt is read once per host and run and honoured (RFC 9309 status
  rules, as in ``datos_gob_sources``). If it cannot be read, discovery fails
  closed and says so. Nothing here retries around a block or a CAPTCHA.
* Network lanes run only inside the real engine (``live_lanes.enabled``),
  never inside the test suite.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timezone
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

USER_AGENT = "RadarSaludBot/0.3 (+public-source-monitor)"


def official(url, hosts):
    try:
        parsed = urlsplit(str(url or ""))
        return (parsed.scheme == "https" and (parsed.hostname or "") in hosts and parsed.port in (None, 443)
                and not parsed.username and not parsed.password)
    except (TypeError, ValueError):
        return False


def fetch(url, hosts, *, timeout=30, max_bytes=6 * 1024 * 1024, accept="text/html,application/xml;q=0.9"):
    """Verified-TLS GET restricted to ``hosts`` (redirects included)."""
    from urllib.request import HTTPRedirectHandler, Request, build_opener

    class _SameHosts(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if not official(newurl, hosts):
                raise ValueError("redirect left the official HTTPS hosts")
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    if not official(url, hosts):
        raise ValueError("URL must be official HTTPS")
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    with build_opener(_SameHosts()).open(request, timeout=timeout) as response:
        final = response.geturl()
        if not official(final, hosts):
            raise ValueError("response left the official HTTPS hosts")
        body = response.read(max_bytes + 1)
        charset = response.headers.get_content_charset() if hasattr(response, "headers") else None
    if len(body) > max_bytes:
        raise ValueError("response exceeds the byte limit")
    return body, {"url": url, "final_url": final, "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body),
                  "charset": charset, "tls_verified": True, "captured_at": datetime.now(timezone.utc).isoformat()}


class RobotsGate:
    """robots.txt per host, read once per run.

    401/403 disallow all; another 4xx (not 429) means "no robots file" (allow);
    429, 5xx or a network error leave the policy unknown and fail closed.
    """

    def __init__(self, fetcher, user_agent=USER_AGENT):
        self.fetcher = fetcher
        self.user_agent = user_agent
        self.parsers = {}
        self.failures = {}
        self.status = {}

    def _policy(self, host):
        from urllib.error import HTTPError
        if host in self.failures:
            raise PermissionError(self.failures[host])
        if host in self.parsers:
            return self.parsers[host]
        parser = RobotFileParser()
        try:
            body, _ = self.fetcher(f"https://{host}/robots.txt")
            parser.parse(body.decode("utf-8", errors="replace").splitlines())
            status = "parsed"
        except HTTPError as exc:
            if exc.code in (401, 403):
                parser.disallow_all, status = True, f"http_{exc.code}_disallow_all"
            elif 400 <= exc.code < 500 and exc.code != 429:
                parser.allow_all, status = True, f"http_{exc.code}_no_robots_file"
            else:
                return self._unavailable(host, f"HTTP {exc.code}")
        except Exception as exc:
            return self._unavailable(host, f"{type(exc).__name__}: {exc}")
        self.parsers[host], self.status[host] = parser, status
        return parser

    def _unavailable(self, host, cause):
        self.status[host] = "robots_unavailable"
        self.failures[host] = f"robots_unavailable: {host}: {cause}"[:200]
        raise PermissionError(self.failures[host])

    def allowed(self, url):
        return self._policy(urlsplit(url).hostname or "").can_fetch(self.user_agent, url)


# --- health scope ---------------------------------------------------------------

def fold(text):
    text = "".join(c for c in unicodedata.normalize("NFKD", str(text or "")) if not unicodedata.combining(c))
    return " ".join(text.split())


# Sector words for official titles that are not general press. "Sanitarias"
# (water utilities) and "fibra óptica" (telecom) are deliberately absent: both
# are frequent FNE markets that are not health.
HEALTH_TERMS = re.compile(
    r"\bsalud\b|\bclinic|\bhospital|\bisapre|\bfonasa\b|\bmedic[oa]s?\b|\bmedicament|\bfarmac|\blaboratori|"
    r"\bopticas\b|\bgrupo optico\b|\bdispositivos? medic|\binsumos? medic|\bdiagnostic|\bdental|\bodontol|"
    r"\bmutual(idad|idades|es)?\b|\blicencias? medic|\bges\b|\bauge\b|\bricarte soto\b|\bcenabast\b|\bisp\b|"
    r"\banamed\b|\benfermer|\bpaciente|\bprestador(es)? de salud|\bseguros? de salud|\bseguro complementario|"
    r"\boncolog|\bdialisis|\bvacun|\bsalud mental|\bcancer\b|\bcompin\b|\bsuseso\b|\baccidentes del trabajo|"
    r"\benfermedades profesionales|\bsuperintendencia de salud\b|\bminsal\b|\bcuidados paliativos|\beutanasia|"
    r"\bsanatorio|\bbanmedica|\bredsalud|\bbupa\b|\bchristus\b|\bindisa\b|\binterclinica|\bsalcobrand|\bcruz verde\b|"
    r"\bahumada\b|\bpreunic\b|\bsaval\b|\bchemopharma|\bsanitas\b|\brecalcine|\bandromaco|\bbiosimil|\bgeneric[oa]s?\b",
    re.I)


def health_basis(text, catalog=None):
    """Why a title is in health scope (empty list: out of scope). Entities first."""
    from . import entity_watch
    from .editorial_gate import title_has_health_nexus
    basis = []
    ents = entity_watch.match_text(str(text or ""), catalog or entity_watch.load_catalog())
    if ents:
        basis.append("entity:" + ",".join(sorted(ents)))
    m = HEALTH_TERMS.search(fold(text).casefold())
    if m:
        basis.append("term:" + m.group(0).strip())
    elif title_has_health_nexus(str(text or "")):
        basis.append("nexus")
    return basis


def scopes_for(text):
    t = fold(text).casefold()
    out = []
    for scope, rx in (("Isapres", r"\bisapre"), ("Fonasa", r"\bfonasa"),
                      ("Farma / medicamentos", r"farmac|medicament|laboratori|cenabast|\bisp\b|generic|biosimil|opticas|salcobrand|cruz verde|ahumada|rotter"),
                      ("Prestadores", r"clinic|hospital|prestador|sanatorio|dialisis|diagnostic"),
                      ("Salud laboral", r"mutual|licencia|accidentes del trabajo|enfermedades profesionales|suseso|compin")):
        if re.search(rx, t):
            out.append(scope)
    return out or ["Sistema de salud"]


def chile_today():
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("America/Santiago")).date()
