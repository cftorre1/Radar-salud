"""Public metadata discovery primitives. No inferred dates or article summaries."""
from __future__ import annotations

import hashlib
import json
import re
import ssl
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from threading import RLock
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, HTTPSHandler
from urllib.robotparser import RobotFileParser

USER_AGENT = "AlicantoHealthRadar/1.0 (+https://github.com/cftorre1/Radar-salud; metadata monitoring, no model training)"
HOSTS = {"www.who.int", "who.int", "www.paho.org", "paho.org", "iris.paho.org"}
MONTHS = {name.lower(): number for number, names in enumerate([
    ("January", "Jan", "enero"), ("February", "Feb", "febrero"), ("March", "Mar", "marzo"),
    ("April", "Apr", "abril"), ("May", "mayo"), ("June", "Jun", "junio"),
    ("July", "Jul", "julio"), ("August", "Aug", "agosto"), ("September", "Sep", "Sept", "septiembre"),
    ("October", "Oct", "octubre"), ("November", "Nov", "noviembre"), ("December", "Dec", "diciembre")], 1) for name in names}

def canonical_url(url: str, base: str = "") -> str:
    parsed = urlsplit(urljoin(base, url))
    if parsed.scheme != "https" or parsed.hostname not in HOSTS or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("unapproved public URL")
    query = [(key, val) for key, val in parse_qsl(parsed.query, keep_blank_values=True)
             if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}]
    return urlunsplit(("https", parsed.netloc.lower(), parsed.path or "/", urlencode(query), ""))

def publication_day(value: str, as_of: date) -> str | None:
    text = str(value or "").strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            result = date.fromisoformat(text)
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?", text):
            result = datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        else:
            match = re.fullmatch(r"(\d{1,2})\s+(?:de\s+)?([A-Za-z]+)\.?\s+(?:de\s+)?(\d{4})", text)
            if not match or match[2].lower() not in MONTHS:
                return None
            result = date(int(match[3]), MONTHS[match[2].lower()], int(match[1]))
        return result.isoformat() if result <= as_of else None
    except ValueError:
        return None

@dataclass
class Node:
    tag: str
    attrs: dict = field(default_factory=dict)
    parent: "Node | None" = None
    children: list = field(default_factory=list)
    closed: bool = False
    def nodes(self, tag=None):
        for child in self.children:
            if isinstance(child, Node):
                if tag is None or child.tag == tag:
                    yield child
                yield from child.nodes(tag)
    def text(self):
        return " ".join(" ".join(child.text() if isinstance(child, Node) else child for child in self.children).split())
    def has_class(self, name):
        return name in self.attrs.get("class", "").split()

class Document(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.root = self.current = Node("root")
        self.feed(text)
    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict(attrs), self.current)
        self.current.children.append(node)
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.current = node
    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)
    def handle_endtag(self, tag):
        node = self.current
        while node.parent:
            if node.tag == tag:
                node.closed = True
                self.current = node.parent
                break
            node = node.parent
    def handle_data(self, value):
        self.current.children.append(value)

class PublicRedirect(HTTPRedirectHandler):
    def __init__(self, client):
        self.client = client
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = canonical_url(newurl, req.full_url)
        self.client.check_cooldown(target)
        self.client.check_live_budget()
        is_robots = getattr(req, "_global_is_robots", False)
        if is_robots:
            if urlsplit(target).path != "/robots.txt":
                raise ValueError("robots_redirect_to_content_denied")
        else:
            self.client.check_robots(target)
        self.client.check_live_budget()
        chain = getattr(req, "_global_redirect_chain", [])
        chain.append({"from_url": req.full_url, "http_status": code, "location": target,
                      "tls_verified": True, "destination_robots_checked": not is_robots})
        redirected = super().redirect_request(req, fp, code, msg, headers, target)
        if redirected:
            redirected._global_is_robots = is_robots
            redirected._global_redirect_chain = chain
        return redirected

class CaptureClient:
    def __init__(self, directory: Path, replay: Path | None = None, delay: float = 1., cooldown_file: Path | None = None, resume: bool = False, live_budget_seconds: float = 1800.):
        self.directory, self.replay, self.delay = directory, replay, delay
        directory.mkdir(parents=True, exist_ok=True)
        self.records, self.robots, self.network_requests = {}, {}, 0
        self._live_lock = RLock()
        if live_budget_seconds <= 0:
            raise ValueError('live capture budget must be positive')
        self.live_deadline = time.monotonic() + live_budget_seconds
        self.cooldown_file = cooldown_file
        self.cooldowns = json.loads(cooldown_file.read_text()) if cooldown_file and cooldown_file.exists() and not replay else {}
        self.resume = resume
        self.reused_urls = set()
        if resume and not replay:
            for path in directory.glob('*.json'):
                record=json.loads(path.read_text());url=canonical_url(record['requested_url'])
                key=hashlib.sha256(url.encode()).hexdigest()[:24]
                if path.name!=key+'.json' or record['body_file']!=key+'.body': raise ValueError('resume capture filename mismatch')
                raw=(directory/record['body_file']).read_bytes()
                age=datetime.now(timezone.utc)-datetime.fromisoformat(record['fetched_at'])
                if age<timedelta(0) or age>timedelta(hours=1): raise ValueError('resume campaign capture outside one-hour bound')
                if record['tls_verified'] is not True or record['user_agent']!=USER_AGENT or hashlib.sha256(raw).hexdigest()!=record['body_sha256'] or len(raw)!=record['body_bytes']:
                    raise ValueError('resume capture integrity mismatch')
                canonical_url(record['final_url'])
                self.records[url]=record
        self.opener = build_opener(PublicRedirect(self), HTTPSHandler(context=ssl.create_default_context()))
    def check_robots(self, url):
        origin = urlunsplit((*urlsplit(url)[:2], "", "", ""))
        if origin not in self.robots:
            raw, policy = self.fetch(origin + "/robots.txt", robots=True)
            if policy["http_status"] != 200:
                raise ValueError("robots_policy_unavailable")
            parsed = RobotFileParser(); parsed.parse(raw.decode(errors="replace").splitlines())
            self.robots[origin] = parsed
        if not self.robots[origin].can_fetch(USER_AGENT, url):
            raise ValueError("robots_disallowed: " + url)
    def fetch(self, url: str, *, robots=False):
        # Serialize requests, including redirects/robots, so a 429 stops queued workers.
        # Replays reproduce historical bytes, including requests made by older collectors.
        with self._live_lock:
            url = canonical_url(url)
            if url not in self.records:
                self.check_cooldown(url)
                self.check_live_budget()
            return self._fetch(url, robots=robots)

    def check_live_budget(self):
        if not self.replay and time.monotonic() >= self.live_deadline:
            raise ValueError('capture_campaign_budget_exhausted_without_request')

    def check_cooldown(self, url):
        origin = urlunsplit((*urlsplit(url)[:2], "", "", ""))
        cooldown = self.cooldowns.get(origin)
        if not self.replay and cooldown and datetime.now(timezone.utc) < datetime.fromisoformat(cooldown["retry_until"]):
            raise ValueError("rate_limit_deferred_without_request_until_" + cooldown["retry_until"])

    def _fetch(self, url: str, *, robots=False):
        url = canonical_url(url)
        if url in self.records:
            record = self.records[url]
            if self.resume and not robots:
                age=datetime.now(timezone.utc)-datetime.fromisoformat(record['fetched_at'])
                raw=(self.directory/record['body_file']).read_bytes()
                if age<timedelta(0) or age>timedelta(hours=1): raise ValueError('resume campaign capture outside one-hour bound')
                if hashlib.sha256(raw).hexdigest()!=record['body_sha256'] or len(raw)!=record['body_bytes']:
                    raise ValueError('resume capture integrity mismatch')
                for target in [url]+[hop['location'] for hop in record.get('redirect_chain',[])]+[record['final_url']]:
                    self.check_robots(canonical_url(target))
                self.reused_urls.add(url)
            if record["http_status"] != 200:
                raise ValueError("http_" + str(record["http_status"]))
            return (self.directory / record["body_file"]).read_bytes(), record
        key = hashlib.sha256(url.encode()).hexdigest()[:24]
        if self.replay:
            record = json.loads((self.replay / (key + ".json")).read_text())
            data = (self.replay / record["body_file"]).read_bytes()
            if record["requested_url"] != url or hashlib.sha256(data).hexdigest() != record["body_sha256"]:
                raise ValueError("capture identity/hash mismatch")
            if record.get("tls_verified") is not True:
                raise ValueError("capture TLS not verified")
            canonical_url(record["final_url"])
            if not robots:
                for target in [url] + [hop["location"] for hop in record.get("redirect_chain", [])] + [record["final_url"]]:
                    self.check_robots(canonical_url(target))
        else:
            if not robots:
                self.check_robots(url)
            time.sleep(self.delay)
            self.check_live_budget()
            self.network_requests += 1
            from urllib.parse import quote
            # Non-ASCII characters in a URL (e.g. an en dash in a WHO slug) are percent-encoded for
            # transport; the URL identity used for robots, evidence and dedup is unchanged.
            request = Request(quote(url, safe=":/?&=%+#;,@!$()*[]~"), headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/json,application/xml"})
            request._global_is_robots = robots
            request._global_redirect_chain = []
            try:
                response = self.opener.open(request, timeout=25)
            except HTTPError as exc:
                response = exc
            with response:
                data = response.read(5000001)
                if len(data) > 5000000:
                    raise ValueError("response_body_limit")
                canonical_url(response.url)
                # A transport-only percent-encoding of the requested URL is not a redirect: keep the identity.
                final_url = url if response.url == request.full_url else response.url
                record = {"requested_url": url, "final_url": final_url, "http_status": response.code,
                          "fetched_at": datetime.now(timezone.utc).isoformat(), "tls_verified": True,
                          "headers": {key.lower(): value for key, value in response.headers.items()
                                      if key.lower() in {"content-type", "last-modified", "date", "server", "retry-after"}},
                          "body_file": key + ".body", "body_sha256": hashlib.sha256(data).hexdigest(),
                          "body_bytes": len(data), "user_agent": USER_AGENT,
                          "redirect_chain": request._global_redirect_chain}
        (self.directory / record["body_file"]).write_bytes(data)
        (self.directory / (key + ".json")).write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
        self.records[url] = record
        if record["http_status"] == 429 and not self.replay:
            observed = datetime.fromisoformat(record["fetched_at"])
            retry = record["headers"].get("retry-after", "")
            try:
                until = observed + timedelta(seconds=int(retry)) if retry.isdigit() else parsedate_to_datetime(retry)
                if until.tzinfo is None: until = until.replace(tzinfo=timezone.utc)
                if until <= observed: until = observed + timedelta(hours=1)
            except (ValueError, TypeError, OverflowError):
                until = observed + timedelta(hours=1)
            origin = urlunsplit((*urlsplit(record["final_url"])[:2], "", "", ""))
            self.cooldowns[origin] = {"http_status":429, "observed_at":record["fetched_at"],
                "retry_after":retry, "retry_until":until.isoformat(), "requested_url":url,
                "body_sha256":record["body_sha256"], "behavior":"no_new_requests_until_retry_until"}
            if self.cooldown_file:
                self.cooldown_file.parent.mkdir(parents=True,exist_ok=True)
                self.cooldown_file.write_text(json.dumps(self.cooldowns,indent=2)+"\n")
        if record["http_status"] != 200:
            raise ValueError("http_" + str(record["http_status"]))
        return data, record
