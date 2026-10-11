"""Public occupational capture cache: verified TLS, saved bytes and robots policy."""
from __future__ import annotations
import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
try:
    from scripts.occupational_access_probe import capture, USER_AGENTS
except ModuleNotFoundError:
    from occupational_access_probe import capture, USER_AGENTS
from .occupational_sources import SourceDiscoveryError
from .pending_queue import atomic_json

class CaptureLoader:
    """Public capture cache with verified TLS, hashed bytes and robots controls."""
    def __init__(self, output, *, replay=None, cache=None, probe=None):
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.records = {}
        self.robots = {}
        self.replay_only = replay is not None
        if replay or cache:
            index = Path(replay or cache) / "capture_index.json"
            for url, record in json.loads(index.read_text()).items():
                self.records[url] = record
        if probe and not self.replay_only:
            report = json.loads(Path(probe).read_text())
            for record in report["records"]:
                if record.get("user_agent") == "identified":
                    self.records[record["url"]] = dict(record, artifact_dir=str(Path(probe).parent))
        atomic_json(self.output / "capture_index.json", self.records)

    def _request(self, url):
        if url in self.records:
            return self.records[url]
        if self.replay_only:
            raise SourceDiscoveryError("replay_capture_missing", url)
        record = capture(url, self.output / "capture")
        record["artifact_dir"] = str(self.output / "capture")
        self.records[url] = record
        atomic_json(self.output / "capture_index.json", self.records)
        print(json.dumps({"capture": url, "http": record.get("http_status"), "result": record.get("stop_reason")}), flush=True)
        time.sleep(1)
        return record

    def _body(self, record):
        last = record["hops"][-1]
        path = Path(record["artifact_dir"]) / last["body_file"]
        body = path.read_bytes()
        if hashlib.sha256(body).hexdigest() != last["sha256"]:
            raise SourceDiscoveryError("capture_hash_mismatch", record["url"])
        if record.get("stop_reason") != "response_captured" or record.get("waf"):
            raise SourceDiscoveryError(record.get("stop_reason", "transport_error"), record["url"])
        if not last["tls"]["verified"]:
            raise SourceDiscoveryError("origin_tls_unverified", record["url"])
        if last["http_status"] != 200:
            raise SourceDiscoveryError("origin_http_status", record["url"], str(last["http_status"]))
        return body.decode("utf-8", errors="replace")

    def __call__(self, url):
        parsed = urlsplit(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self.robots:
            robots_url = origin + "/robots.txt"
            try:
                text = self._body(self._request(robots_url))
                robot = RobotFileParser()
                robot.parse(text.splitlines())
                self.robots[origin] = robot
            except SourceDiscoveryError as exc:
                # A verified 404 means no robots file. A blocked policy request
                # is not permission to crawl the rest of that host.
                record = self.records.get(robots_url, {})
                if record.get("http_status") == 404 and record.get("hops", [{}])[-1].get("tls", {}).get("verified"):
                    self.robots[origin] = None
                else:
                    raise SourceDiscoveryError("robots_policy_unavailable", robots_url, str(exc)) from exc
        policy = self.robots[origin]
        if policy and not policy.can_fetch(USER_AGENTS["identified"], url):
            raise SourceDiscoveryError("robots_disallowed", url)
        return self._body(self._request(url))

    def evidence(self, url):
        r = self.records[url]
        h = r["hops"][-1]
        return {"url": url, "final_url": r["final_url"], "captured_at": r["captured_at"],
                "sha256": h["sha256"], "http_status": h["http_status"], "tls_verified": h["tls"]["verified"],
                "artifact": str(Path(r["artifact_dir"]) / h["body_file"]), "environment": "github_actions"}

