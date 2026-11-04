"""Daily, bounded refresh of the DIPRES lane that feeds F7 "Financiamiento público" (Director, 4-nov-2026).

The lane ``data/market/dipres_health_budget.json`` was built once, by hand, from a capture of 11-oct-2026
(``scripts/probe_source_expansion.py`` + ``market_sources.collect_dipres``); no workflow ran it again. This module runs
inside the daily statistics step (``scripts/run_stats_fichas.py``, which ``daily-radar.yml`` already calls on staging)
and adds the new monthly execution reports of Partida 16 to the same lane, through the same ``collect_dipres``.

Discovery (no model, no backfill):

- DIPRES lists the execution reports of each institution and year on an appendix page
  ``https://www.dipres.gob.cl/597/aux-multipropertyvalues-<entity>-<year id>.html``. The entities are the four pages
  the lane was built from (Partida 16 Ministerio de Salud 14626, Fonasa 14632, 14678, Redes Asistenciales 14679). The
  year id is read from the year links of the partida page (``w3-multipropertyvalues-14626-<id>.html``, label "2026");
  it is fetched only when the year is not yet known.
- Only "Documento PDF : Informe Ejecución {Partida|Capítulo|Programa} {Mes|… Trimestre} [Pesos]" links are read. The
  label gives the expected cut (year of the page + month; "Primer Trimestre" = March …). A PDF is downloaded once per
  canonical URL (the listing's ``?ts=`` is dropped); a URL already in the lane ledger is never downloaded again.
- Every PDF is hashed and parsed with ``dipres_sources.parse_execution``. It enters the lane only when the parsed
  fiscal year, cut and level equal what its label and page say; otherwise it is rejected (``period_mismatch``,
  ``level_mismatch``), recorded, and never relabelled. A PDF with bytes already in the ledger under another URL is a
  duplicate and is not added.
- Publication dates are never inferred (the listing's ``ts`` is not a publication date): ``collect_dipres`` keeps
  ``published_at = None`` and the ficha is dated by detection.

Guards: one completed check per Chile day; at most ``MAX_NEW`` PDFs per run; failed downloads retried up to
``MAX_ATTEMPTS`` times, then once a week; a time budget for the whole step; HTTPS on dipres.gob.cl only (redirects
included), robots.txt honoured (shared ``load_robots_policy``: 401/403/429/5xx/network fail closed), 25 MB per
response, 30 s per request. Any failure leaves the lane exactly as it was (it is rewritten only when at least one new
document validated). While F7's first publication waits for Dirección's review (``first_pass_requires_review`` and no
live F7 ficha), the refresh does not run, so the evidence under review does not change before it is published; after
that, new evidence follows the normal policy.

State and history: ``data/market/dipres_refresh_state.json`` (year ids, every listed document with its SHA-256,
status and first detection, and the last runs). Binaries are never stored.
"""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin, urlsplit

from .datos_gob_sources import RobotsUnavailable, load_robots_policy
from .official_tables import fold
from .pending_queue import atomic_json
from .stats_capture import MAX_BYTES, MAX_ROBOTS_BYTES, REQUEST_TIMEOUT_S, USER_AGENT, read_capped

SCHEMA = "dipres_refresh_v1"
LANE = Path("data/market/dipres_health_budget.json")
STATE = Path("data/market/dipres_refresh_state.json")
HOSTS = frozenset({"www.dipres.gob.cl", "dipres.gob.cl"})
BASE = "https://www.dipres.gob.cl/597/"
PARTIDA_PAGE = "14626"  # Ministerio de Salud (Partida 16): its page carries the links to every year
ENTITY_PAGES = ("14626", "14632", "14678", "14679")  # the execution indexes the lane was built from (11-oct-2026)
KNOWN_YEAR_IDS = {"2025": "36882", "2026": "37782"}  # read from the retained 11-oct-2026 capture of the partida page
MAX_NEW = 12
MAX_ATTEMPTS = 3
RETRY_AFTER_DAYS = 7
TIME_BUDGET_S = 150
HISTORY_RUNS = 60
MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
          "noviembre", "diciembre")
QUARTERS = {"primer trimestre": 3, "segundo trimestre": 6, "tercer trimestre": 9, "cuarto trimestre": 12}
LABEL = re.compile(r"documento pdf\s*:\s*informe ejecucion (partida|capitulo|programa)\s+("
                   + "|".join(MONTHS + tuple(QUARTERS)) + r")\b")
PDF_HREF = re.compile(r"/597/articles-\d+_doc_pdf\.pdf$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load(path: Path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def url_ok(url: str) -> bool:
    try:
        u = urlsplit(str(url))
        return (u.scheme == "https" and (u.hostname or "") in HOSTS and u.port in (None, 443)
                and not u.username and not u.password)
    except (TypeError, ValueError):
        return False


def canonical(url: str) -> str:
    from .dipres_sources import canonical_url
    return canonical_url(url)


def _redirect_handler():
    from urllib.request import HTTPRedirectHandler

    class DipresOnlyRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if not url_ok(newurl):
                raise PermissionError(f"redirect_off_allowlist: {urlsplit(str(newurl)).hostname}")
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    return DipresOnlyRedirect()


class DipresFetcher:
    """GET on dipres.gob.cl only, robots.txt per host, byte cap, per-request timeout bounded by the step deadline.
    ``opener`` is injectable so tests never touch the network."""

    def __init__(self, *, opener=None, deadline: float | None = None, clock: Callable[[], float] = time.monotonic,
                 timeout: float = REQUEST_TIMEOUT_S, max_bytes: int = MAX_BYTES):
        from urllib.request import build_opener
        self.opener = opener or build_opener(_redirect_handler())
        self.deadline, self.clock, self.timeout, self.max_bytes = deadline, clock, timeout, max_bytes
        self.robots: dict[str, object] = {}

    def _timeout(self) -> float:
        if self.deadline is None:
            return self.timeout
        left = self.deadline - self.clock()
        if left <= 0:
            raise TimeoutError("refresh_time_budget_exhausted")
        return max(1.0, min(self.timeout, left))

    def _get(self, url: str, max_bytes: int) -> bytes:
        from urllib.request import Request
        if not url_ok(url):
            raise PermissionError(f"host_not_allowlisted: {urlsplit(str(url)).hostname}")
        with self.opener.open(Request(url, headers={"User-Agent": USER_AGENT}), timeout=self._timeout()) as response:
            final = response.geturl() if hasattr(response, "geturl") else url
            if not url_ok(final):
                raise PermissionError(f"redirect_off_allowlist: {urlsplit(str(final)).hostname}")
            return read_capped(response, max_bytes, self.deadline, self.clock)

    def __call__(self, url: str) -> bytes:
        if not url_ok(url):
            raise PermissionError(f"host_not_allowlisted: {urlsplit(str(url)).hostname}")
        host = urlsplit(url).hostname
        if host not in self.robots:
            try:
                self.robots[host] = load_robots_policy(lambda u: self._get(u, MAX_ROBOTS_BYTES), f"https://{host}/robots.txt")[0]
            except RobotsUnavailable as exc:
                self.robots[host] = exc
        policy = self.robots[host]
        if isinstance(policy, Exception):
            raise policy
        if not policy.can_fetch(USER_AGENT, url):
            raise PermissionError(f"robots_disallowed: {urlsplit(url).path}")
        return self._get(url, self.max_bytes)


def _links(html: str, base: str) -> list[tuple[str, str]]:
    from html.parser import HTMLParser

    class P(HTMLParser):
        def __init__(self):
            super().__init__()
            self.out, self.href, self.text = [], None, []

        def handle_starttag(self, tag, attrs):
            if tag == "a":
                self.href, self.text = dict(attrs).get("href"), []

        def handle_data(self, data):
            if self.href is not None:
                self.text.append(data)

        def handle_endtag(self, tag):
            if tag == "a" and self.href is not None:
                self.out.append((urljoin(base, self.href), " ".join("".join(self.text).split())))
                self.href = None
    p = P()
    p.feed(html)
    return p.out


def year_links(html: str, base: str) -> dict[str, str]:
    """Year → id from the partida page's year links ('…/w3-multipropertyvalues-14626-37782.html' labelled '2026')."""
    out = {}
    for url, label in _links(html, base):
        m = re.search(r"/597/w3-multipropertyvalues-" + PARTIDA_PAGE + r"-(\d+)\.html$", urlsplit(url).path)
        if m and re.fullmatch(r"20\d{2}", label.strip()) and url_ok(url):
            out.setdefault(label.strip(), m[1])
    return out


def listed_reports(html: str, base: str, year: str) -> list[dict]:
    """Execution-report PDFs of one appendix page, with the cut and level their label declares."""
    out, seen = [], set()
    for url, label in _links(html, base):
        if not url_ok(url) or not PDF_HREF.search(urlsplit(url).path):
            continue
        m = LABEL.search(fold(label))
        if not m:
            continue
        month = QUARTERS.get(m[2]) or MONTHS.index(m[2]) + 1
        canon = canonical(url)
        if canon in seen:
            continue
        seen.add(canon)
        ts = re.search(r"(?:^|&)ts=(\d+)", urlsplit(url).query)
        out.append({"url": url, "canonical_url": canon, "label": label[:100], "level": m[1],
                    "expected_period": f"{year}-{month:02d}", "listing_ts": ts[1] if ts else None})
    return out


def target_years(today: date) -> list[str]:
    """The current fiscal year; until March also the previous one (its December / fourth-quarter report)."""
    years = [str(today.year)]
    if today.month <= 3:
        years.insert(0, str(today.year - 1))
    return years


def validate(text: str, item: dict, *, sha256: str) -> tuple[list[dict] | None, str | None]:
    """Parse one PDF and accept it only if it is the cut and level its listing declares (never relabelled)."""
    from .dipres_sources import parse_execution
    try:
        records = parse_execution(text, source_url=item["canonical_url"], sha256=sha256)
    except ValueError as exc:
        return None, f"parse_failed:{exc}"[:160]
    if not records or any(r.get("metric") == "public_investment_subtitle_31" for r in records):
        return None, "not_an_execution_report"
    periods = {(str(r.get("fiscal_year")), str(r.get("period"))) for r in records}
    exp = item["expected_period"]
    if periods != {(exp[:4], exp)}:
        got = ",".join(sorted(p for _, p in periods))
        return None, f"period_mismatch:listed {exp}, document {got}"
    level = {"partida": "partida", "capitulo": "chapter", "programa": "program"}[item["level"]]
    if {r.get("reporting_level") for r in records} != {level} or {r.get("partida") for r in records} != {"16"}:
        return None, "level_mismatch"
    return records, None


def first_review_pending(root: Path, registry: dict | None) -> bool:
    """F7's first ficha still waits for Dirección (gate in stats_ficha_f7): keep its evidence still until it is live."""
    from . import stats_fichas as sf
    cfg = ((registry or sf.load_registry()).get("families") or {}).get("F7") or {}
    if not cfg.get("first_pass_requires_review"):
        return False
    live = sf.load_live(Path(root), cfg.get("slug") or "f7_financiamiento") or {}
    return not (str(live.get("builder_version") or "").startswith("f7_") and live.get("status") == "PASS")


def _due(doc: dict | None, now: datetime) -> bool:
    if not doc:
        return True
    if doc.get("status") != "fetch_failed":
        return False
    if int(doc.get("attempts") or 0) < MAX_ATTEMPTS:
        return True
    try:
        last = datetime.fromisoformat(str(doc.get("last_attempt_at")))
    except ValueError:
        return True
    return now - last >= timedelta(days=RETRY_AFTER_DAYS)


def refresh(root: Path, *, today: date, registry: dict | None = None, fetch: Callable[[str], bytes] | None = None,
            time_budget_s: float = TIME_BUDGET_S, clock: Callable[[], float] = time.monotonic,
            now: Callable[[], datetime] = _now, extract: Callable[[bytes], str] | None = None,
            force: bool = False) -> dict:
    """One bounded check of the DIPRES execution listings; new validated reports go into the lane via collect_dipres."""
    root = Path(root)
    state = _load(root / STATE, {}) or {}
    state.setdefault("schema_version", SCHEMA)
    docs: dict[str, dict] = state.setdefault("documents", {})
    years: dict[str, str] = state.setdefault("year_ids", dict(KNOWN_YEAR_IDS))
    day = today.isoformat()
    summary: dict = {"day": day, "time_budget_s": time_budget_s}
    if not force and state.get("last_completed_on") == day:
        return {**summary, "status": "skipped_already_checked_today"}
    if first_review_pending(root, registry):
        return {**summary, "status": "skipped_f7_awaiting_first_review"}
    lane = _load(root / LANE, None)
    if not isinstance(lane, dict) or not isinstance(lane.get("records"), list):
        return {**summary, "status": "skipped_lane_missing"}
    deadline = clock() + time_budget_s
    fetch = fetch or DipresFetcher(deadline=deadline, clock=clock)
    if extract is None:
        from . import dipres_sources
        extract = lambda data: dipres_sources.pdf_text(data)  # noqa: E731 (late lookup: patchable in tests)
    started = now()
    ledger_urls = {d.get("source_url") for d in lane.get("document_ledger") or [] if d.get("disposition") == "data_snapshot"}
    ledger_shas = {d.get("source_sha256") for d in lane.get("document_ledger") or []}
    errors: list[str] = []
    counts = {"listed": 0, "new": 0, "duplicates": 0, "rejected": 0, "fetch_failed": 0, "already_known": 0}
    complete = True

    def has_time() -> bool:
        nonlocal complete
        if clock() >= deadline:
            complete = False
            summary["time_budget_exhausted"] = True
            return False
        return True

    def get(url: str) -> bytes | None:
        try:
            return fetch(url)
        except Exception as exc:  # network, robots, cap, timeout: recorded, never fatal
            errors.append(f"{urlsplit(url).path}:{type(exc).__name__}:{exc}"[:200])
            return None

    # 1. Year ids (only when a target year is unknown).
    for y in target_years(today):
        if y in years or not has_time():
            continue
        known = max(years, default=None)
        page = BASE + f"w3-multipropertyvalues-{PARTIDA_PAGE}-{years[known]}.html" if known else None
        body = get(page) if page else None
        if body is None:
            complete = False
            continue
        years.update({k: v for k, v in year_links(body.decode("utf-8", errors="replace"), page).items() if k not in years})
    # 2. Listings.
    listed: list[dict] = []
    for y in target_years(today):
        if y not in years:
            summary.setdefault("years_not_listed", []).append(y)
            continue
        for ent in ENTITY_PAGES:
            if not has_time():
                break
            page = BASE + f"aux-multipropertyvalues-{ent}-{years[y]}.html"
            body = get(page)
            if body is None:
                complete = False
                continue
            listed += listed_reports(body.decode("utf-8", errors="replace"), page, y)
    counts["listed"] = len(listed)
    # 3. Download each new report once; validate cut and level; hash everything.
    accepted: list[tuple[dict, bytes, str]] = []
    stamp = started.isoformat()
    budget = MAX_NEW
    for item in sorted(listed, key=lambda i: (i["expected_period"], i["canonical_url"]), reverse=True):
        canon = item["canonical_url"]
        old = docs.get(canon)
        if canon in ledger_urls:
            counts["already_known"] += 1
            if not old:
                docs[canon] = {"label": item["label"], "expected_period": item["expected_period"], "status": "in_lane",
                               "listing_ts": item["listing_ts"], "first_listed_at": stamp}
            elif item["listing_ts"] and old.get("listing_ts") and item["listing_ts"] != old["listing_ts"]:
                old["listing_ts_changed_at"] = stamp  # visible for review; the document is not re-downloaded
            continue
        if not _due(old, started):
            continue
        if budget <= 0 or not has_time():
            complete = complete and budget > 0
            continue
        budget -= 1
        entry = {**(old or {}), "label": item["label"], "level": item["level"], "expected_period": item["expected_period"],
                 "listing_ts": item["listing_ts"], "last_attempt_at": stamp}
        entry.setdefault("first_listed_at", stamp)
        data = get(item["url"])
        if data is None:
            entry.update(status="fetch_failed", attempts=int(entry.get("attempts") or 0) + 1, error=errors[-1] if errors else None)
            docs[canon] = entry
            counts["fetch_failed"] += 1
            continue
        sha = hashlib.sha256(data).hexdigest()
        entry.update(sha256=sha, bytes=len(data), fetched_at=stamp, attempts=0, error=None)
        if sha in ledger_shas:
            entry.update(status="duplicate_content")
            counts["duplicates"] += 1
        else:
            try:
                text = extract(data)
                records, reason = validate(text, item, sha256=sha)
            except Exception as exc:
                records, reason = None, f"parse_failed:{type(exc).__name__}"
            if reason:
                entry.update(status="rejected", reason=reason)
                counts["rejected"] += 1
            else:
                entry.update(status="accepted", parsed_period=item["expected_period"], observations=len(records))
                accepted.append((item, data, sha))
                ledger_shas.add(sha)
        docs[canon] = entry
    # 4. Feed the lane through the same collector (only when something new validated).
    if accepted:
        try:
            summary["collect"] = _collect(root, accepted, stamp)
            for item, _, _ in accepted:
                docs[item["canonical_url"]].update(status="in_lane", first_detected_at=stamp)
            counts["new"] = len(accepted)
        except Exception as exc:
            errors.append(f"collect:{type(exc).__name__}:{exc}"[:200])
            for item, _, _ in accepted:
                docs[item["canonical_url"]].update(status="collect_failed")
            complete = False
    status = "error" if errors and not counts["listed"] else ("partial" if not complete or errors else "ok")
    run = {"started_at": stamp, "day": day, "status": status, **counts, "errors": errors[:10],
           "time_budget_exhausted": bool(summary.get("time_budget_exhausted"))}
    state["runs"] = ([run] + list(state.get("runs") or []))[:HISTORY_RUNS]
    state["last_run_at"] = stamp
    if status == "ok":
        state["last_completed_on"] = day
        state["last_ok_at"] = stamp
    atomic_json(root / STATE, state)
    return {**summary, **run}


def _collect(root: Path, accepted: list[tuple[dict, bytes, str]], stamp: str) -> dict:
    """Write the accepted PDFs to a throwaway capture directory and run the lane's own collector on it."""
    from .market_sources import Captures, collect_dipres
    from .source_health import record_data_adapter
    with tempfile.TemporaryDirectory(prefix="dipres-refresh-") as tmp:
        tmp_path = Path(tmp)
        receipts = []
        for i, (item, data, sha) in enumerate(accepted):
            name = f"doc{i}.pdf"
            (tmp_path / name).write_bytes(data)
            receipts.append({"package": "dipres", "kind": item["label"], "url": item["canonical_url"], "sha256": sha,
                             "body_file": name, "transport_ok": True, "completed_at": stamp})
        (tmp_path / "receipts.json").write_text(json.dumps({"as_of": stamp[:10], "receipts": receipts}), encoding="utf-8")
        evidence = collect_dipres(Captures(tmp_path), root)
    evidence.update(runtime_activation="stats_fichas_daily_refresh", poll_mode="daily_refresh", recurrence_validated=False)
    record_data_adapter(root, "dipres_health_budget", evidence)
    return {"data_documents": evidence.get("data_documents"), "observations": evidence.get("observations")}


def freshness(root: Path, today: date, max_age_days: int = 3) -> dict:
    """What the ficha may say about freshness: 'daily' only if an automatic check completed in the last days."""
    state = _load(Path(root) / STATE, {}) or {}
    last = str(state.get("last_ok_at") or "")[:10]
    try:
        age = (today - date.fromisoformat(last)).days
    except ValueError:
        return {"mode": "manual", "last_ok_on": None}
    return {"mode": "daily" if 0 <= age <= max_age_days else "stale", "last_ok_on": last}
