"""Captures for the F4 (GES) and F6 (Boletín IP) statistics fichas.

The SIS releases are listed in ``data/history/superintendencia_signals.json`` (title, release page and document
URLs). This module downloads each document once, stores its SHA-256 and the parsed, reconciled values in
``data/stats_fichas/captures/<kind>.json`` and never stores the binary. A document already captured is not downloaded
again (no backfill: only the releases already in the history are read, at most ``max_new`` per run), except once when
the Boletín checker version or the figure templates of its topic change: then it is re-checked and must
hash to the recorded SHA-256.

- GES (xlsx): ``data_insights.parse_ges_workbook`` — the corrected parser: the sheet of the reporting year is
  pinned and the rows must add up to the declared total, else HOLD.
- Boletín IP (PDF): the text is never interpreted by a model. The figures come from the independent reading in
  ``config/statistical_analysis_verified_v1.json`` and the capture only records whether each verified figure is
  present in the captured document's text (``verified_present``) and under which rule (``figure_rules``: the
  context window or, for acreditación, a human-reviewed anchored template). Releases whose documents belong to another
  release (e.g. a 'Septiembre 2026' page listing the 'enero-junio-2026' PDFs) are rejected, never relabelled.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

from . import data_insights
from .datos_gob_sources import RobotsUnavailable, load_robots_policy

SCHEMA = "stats_capture_v1"
STORE = Path("data/stats_fichas/captures")
HISTORY = Path("data/history/superintendencia_signals.json")
VERIFIED = Path("config/statistical_analysis_verified_v1.json")
MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
          "noviembre", "diciembre")
TOPICS = ("acreditacion", "mediacion", "reclamos", "rnpi")
MAX_ATTEMPTS = 3
RETRY_AFTER_DAYS = 7
# Network guard for the capture step (SIS only, robots.txt honoured, bounded bytes and time).
SIS_HOSTS = frozenset({"www.superdesalud.gob.cl", "superdesalud.gob.cl"})
MAX_BYTES = 25 * 1024 * 1024
MAX_ROBOTS_BYTES = 512 * 1024
REQUEST_TIMEOUT_S = 30
TIME_BUDGET_S = 8 * 60
USER_AGENT = data_insights.USER_AGENT


def _fold(text: str) -> str:
    return str(text or "").casefold().translate(str.maketrans("áéíóúüñ", "aeiouun"))


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def title_period(title: str) -> str | None:
    """'… – a junio 2026' / '… – Junio 2026' → '2026-06'."""
    m = re.search(r"(" + "|".join(MONTHS) + r")\s+(20\d{2})\s*$", _fold(title).strip())
    return f"{m[2]}-{MONTHS.index(m[1]) + 1:02d}" if m else None


def file_format(data: bytes) -> str:
    if data[:4] == b"PK\x03\x04":
        return "xlsx"
    if data[:5] == b"%PDF-":
        return "pdf"
    if data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return "xls"
    return "unknown"


def _signals(root: Path) -> list[dict]:
    data = _load(Path(root) / HISTORY, {})
    return list(data.get("signals") or []) if isinstance(data, dict) else []


def _docs(sig: dict) -> list[str]:
    return [d.get("url") for d in sig.get("source_documents") or [] if str(d.get("url") or "").startswith("https://")]


def ges_releases(root: Path) -> list[dict]:
    out = {}
    for sig in _signals(root):
        title = str(sig.get("title") or "")
        if "casos ges" not in _fold(title) or sig.get("source_name") != "Superintendencia de Salud":
            continue
        period = title_period(title)
        docs = [u for u in _docs(sig) if u.lower().endswith((".xlsx", ".xls"))]
        if not period or len(docs) != 1:
            continue
        out[period] = {"period": period, "title": title, "release_url": sig.get("source_url"),
                       "published_at": str(sig.get("event_date") or "")[:10] or None, "documents": [{"url": docs[0]}]}
    return [out[k] for k in sorted(out)]


BOLETIN_DOC = re.compile(r"boletin-n(?P<n>\d)-(?P<y>20\d{2})-(?P<topic>[a-z]+)-enero-(?P<m>[a-z]+)-(?P<y2>20\d{2})")


def doc_release(url: str) -> dict | None:
    """'…/boletin-n2-2026-acreditacion-enero-junio-2026-2.pdf' → number 2, topic, period 2026-06."""
    m = BOLETIN_DOC.search(url.rsplit("/", 1)[-1].lower())
    if not m or m["m"] not in MONTHS or m["topic"] not in TOPICS or m["y"] != m["y2"]:
        return None
    return {"number": f"N°{m['n']}-{m['y']}", "topic": m["topic"], "period": f"{m['y']}-{MONTHS.index(m['m']) + 1:02d}"}


def boletin_releases(root: Path) -> tuple[list[dict], list[dict]]:
    """Releases with exactly one document per topic whose file names carry the release's own period."""
    ok, rejected = {}, []
    for sig in _signals(root):
        title = str(sig.get("title") or "")
        if "boletin estadistico informativo ip" not in _fold(title):
            continue
        period = title_period(title)
        docs = [(u, doc_release(u)) for u in _docs(sig)]
        topics = sorted(d["topic"] for _, d in docs if d)
        reasons = []
        if not period:
            reasons.append("period_not_in_title")
        if any(d is None for _, d in docs) or topics != sorted(TOPICS):
            reasons.append("documents_not_one_per_topic")
        if period and any(d and d["period"] != period for _, d in docs):
            reasons.append("documents_belong_to_other_release")
        if len({d["number"] for _, d in docs if d}) > 1:
            reasons.append("mixed_bulletin_numbers")
        if reasons:
            rejected.append({"title": title, "release_url": sig.get("source_url"), "reasons": reasons,
                             "document_periods": sorted({d["period"] for _, d in docs if d})})
            continue
        number = next(d["number"] for _, d in docs if d)
        ok[period] = {"period": period, "number": number, "title": title, "release_url": sig.get("source_url"),
                      "published_at": str(sig.get("event_date") or "")[:10] or None,
                      "documents": [{"url": u, "topic": d["topic"]} for u, d in sorted(docs, key=lambda x: x[1]["topic"])]}
    return [ok[k] for k in sorted(ok)], rejected


def verified_metrics(root: Path) -> dict[str, dict]:
    """Independently verified Boletín figures by document URL (config/statistical_analysis_verified_v1.json)."""
    cfg = _load(Path(root) / VERIFIED, {})
    out = {}
    for doc in (cfg.get("primary_review") or {}).get("documents") or []:
        if doc.get("url") and isinstance(doc.get("verified_metrics"), dict):
            out[doc["url"]] = {"metrics": doc["verified_metrics"], "pages_1based": doc.get("pages_1based"),
                               "reviewed_at": cfg.get("reviewed_at"), "unit_caution": doc.get("unit_caution")}
    return out


def number_forms(n: int | float) -> list[str]:
    """Ways a verified integer can be printed in a SIS PDF: 1.004.982 · 1004982 · 1 004 982."""
    v = int(n)
    dotted = f"{v:,}".replace(",", ".")
    return list(dict.fromkeys([dotted, str(v), dotted.replace(".", " ")]))


# Words that must appear near a verified figure (same page, within CONTEXT_CHARS) for it to count as present.
# Folded (no accents). Small numbers such as 30, 101 or 175 never match on their own (page numbers, dates, codes).
GENERIC_CONTEXT = ("acreditad", "tramite", "tramitacion", "mediador", "mediacion", "reclamo", "titulo")
METRIC_CONTEXT = {
    "accredited_providers": ("acreditad",),
    "with_observations": ("observacion",),
    "pending_applications": ("tramite", "tramitacion"),
    "private_pending": ("privad",),
    "public_pending": ("public",),
    "registered_mediators": ("mediador",),
    "cumulative_requests_2019_to_june2026": ("solicitud", "mediacion"),
    "monthly_average_2026": ("reclamo",),
    "monthly_average_2025": ("reclamo",),
    "reported_growth_percent_rounded": ("reclamo", "aument", "variacion", "increment"),
    "registered_titles": ("titulo",),
    "records_without_birth_date": ("nacimiento",),
}
CONTEXT_CHARS = 80


def present_in(text: str, n: int | float, context: tuple[str, ...] = GENERIC_CONTEXT, window: int = CONTEXT_CHARS) -> bool:
    """The number, printed in one of its SIS forms, with one of the context words within ``window`` characters."""
    folded = _fold(text)
    for form in number_forms(n):
        for m in re.finditer(r"(?<![\d.,])" + re.escape(form) + r"(?![\d]|[.,]\d)", folded):
            near = folded[max(0, m.start() - window): m.end() + window]
            if any(word in near for word in context):
                return True
    return False


# Checker version of the Boletín IP parse, per topic (recorded as ``checker_version`` in every parse result). A captured
# document whose recorded version is older than the code's, or whose recorded ``templates_sha256`` differs from the
# current figure templates of its topic, is re-checked on the next run (``capture``): the bytes are obtained again
# within the same limits, must hash to the recorded SHA-256 (else HOLD: status 'hash_mismatch') and are re-parsed.
# Version 1 = context window only. Version 2 (acreditación, Dirección 2026-10-29) adds per-figure anchored templates
# declared in ``config/stats_fichas_v1.json`` (families.F6.figure_templates) and reviewed by a human; the context
# window is unchanged. No generic sentence or table heuristic is used.
CHECKER_VERSIONS = {"acreditacion": 2}
DEFAULT_CHECKER_VERSION = 1
REGISTRY = Path("config/stats_fichas_v1.json")
PLACEHOLDER = re.compile(r"<<[^>]*>>")
UNREVIEWED = frozenset({"", "pendiente", "pending", "todo"})


def checker_version(topic: str | None) -> int:
    return CHECKER_VERSIONS.get(str(topic or ""), DEFAULT_CHECKER_VERSION)


def figure_templates(root: Path, topic: str | None) -> dict:
    """The topic's figure templates (``families.F6.figure_templates.<topic>``) of the root's registry; {} if none."""
    reg = _load(Path(root) / REGISTRY, {})
    fam = ((reg.get("families") or {}).get("F6") or {}) if isinstance(reg, dict) else {}
    out = (fam.get("figure_templates") or {}).get(str(topic or "")) or {}
    return {k: v for k, v in out.items() if isinstance(v, dict)}


def templates_sha256(templates: dict | None) -> str | None:
    if not templates:
        return None
    return hashlib.sha256(json.dumps(templates, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def normalize_page(text: str) -> str:
    """Template text: case and accents folded, thousands dots removed ('1.004.982' → '1004982'), all whitespace
    (newlines included) collapsed to single spaces."""
    t = _fold(text)
    t = re.sub(r"(?<=\d)\.(?=\d{3}(?!\d))", "", t)
    return re.sub(r"\s+", " ", t).strip()


def template_pattern(tpl: dict) -> tuple[re.Pattern | None, str]:
    """Compile a template, or say why it is not usable ('placeholder', 'unreviewed', 'invalid')."""
    caption = tpl.get("caption")
    raw = str(tpl.get("pattern") or "")
    if not raw or PLACEHOLDER.search(raw) or (caption is not None and (not str(caption).strip()
                                                                       or PLACEHOLDER.search(str(caption)))):
        return None, "placeholder"
    if str(tpl.get("reviewed_by") or "").strip().casefold() in UNREVIEWED or not str(tpl.get("reviewed_at") or "").strip():
        return None, "unreviewed"
    if "{caption}" in raw:
        if caption is None:
            return None, "placeholder"
        raw = raw.replace("{caption}", re.escape(normalize_page(str(caption))))
    try:
        pat = re.compile(raw)
    except re.error:
        return None, "invalid"
    if pat.groups != int(tpl.get("groups") or 1) or not 1 <= int(tpl.get("figure_group") or 1) <= pat.groups:
        return None, "invalid"
    return pat, "ok"


def template_evidence(pages: list[str], cited: list[int], n: int | float, tpl: dict | None,
                      metrics: dict | None = None) -> tuple[dict | None, str]:
    """Apply one reviewed template to the cited pages: it must match exactly once across them, the captured figure
    must equal the independent reading's ``n``, and the optional ``sum_of`` / ``parts_equal`` checks must hold."""
    if not tpl:
        return None, "not_configured"
    pat, why = template_pattern(tpl)
    if not pat:
        return None, why
    hits = [(p, m) for p in cited for m in pat.finditer(normalize_page(pages[p - 1]))]
    if len(hits) != 1:
        return None, "no_match" if not hits else f"multiple_matches:{len(hits)}"
    page, m = hits[0]
    groups = [int(g) for g in m.groups()]
    if groups[int(tpl.get("figure_group") or 1) - 1] != int(n):
        return None, "figure_mismatch"
    ev = {"rule": "template", "page": page, "match": m[0][:300], "reviewed_by": tpl.get("reviewed_by"),
          "reviewed_at": tpl.get("reviewed_at")}
    if tpl.get("sum_of"):
        parts = [groups[i - 1] for i in tpl["sum_of"]]
        if sum(parts) != int(n):
            return None, "sum_mismatch"
        ev["sum_check"] = " + ".join(map(str, parts)) + f" = {int(n)}"
    for g, key in (tpl.get("parts_equal") or {}).items():
        want = (metrics or {}).get(key)
        if not isinstance(want, (int, float)) or groups[int(g) - 1] != int(want):
            return None, f"part_mismatch:{key}"
    if tpl.get("parts_equal"):
        ev["parts_equal"] = {key: groups[int(g) - 1] for g, key in tpl["parts_equal"].items()}
    return ev, "ok"


def figure_evidence(pages: list[str], cited: list[int], n: int | float, context: tuple[str, ...],
                    version: int = DEFAULT_CHECKER_VERSION, key: str | None = None, templates: dict | None = None,
                    metrics: dict | None = None) -> dict | None:
    """Which rule places the figure on a cited page: 'context_window' (all versions), then, from v2, the reviewed
    anchored 'template' of the metric (``templates[key]``). Nothing else."""
    for p in cited:
        if present_in(pages[p - 1], n, context):
            return {"rule": "context_window", "page": p}
    if version < 2 or not key:
        return None
    return template_evidence(pages, cited, n, (templates or {}).get(key), metrics)[0]


def pdf_pages(data: bytes) -> list[str]:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    return [(page.extract_text() or "") for page in reader.pages]


def pdf_text(data: bytes) -> tuple[str, int]:
    pages = pdf_pages(data)
    return "\n".join(pages), len(pages)


def parse_boletin_pdf(data: bytes, metrics: dict | None, pages_1based: list[int] | None = None,
                      topic: str | None = None, templates: dict | None = None) -> dict:
    """Hash-bound check of verified figures; no figure is read from the PDF by guesswork.

    A figure counts as present only on the pages cited by the independent reading (``pages_1based``): next to a
    context word of its metric, or (checker v2) through its reviewed anchored template. Without cited pages nothing is
    verified (fail closed). ``figure_rules`` records the rule per figure, ``template_status`` why a template did not
    apply ('not_configured', 'placeholder', 'unreviewed', 'no_match', 'multiple_matches:N', …)."""
    version = checker_version(topic)
    templates = templates if version >= 2 else None
    base = {"checker_version": version, "templates_sha256": templates_sha256(templates)}
    try:
        pages = pdf_pages(data)
    except Exception as exc:  # unreadable PDF: captured hash, no verification
        return {"status": "pdf_unreadable", "error": f"{type(exc).__name__}"[:80], **base}
    text = "\n".join(pages)
    out = {"status": "no_verified_metrics", "pages": len(pages),
           "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), **base}
    if metrics:
        cited = [p for p in (pages_1based or []) if isinstance(p, int) and 1 <= p <= len(pages)]
        evidence, status = {}, {}
        for k, v in metrics.items():
            if not isinstance(v, (int, float)):
                continue
            evidence[k] = figure_evidence(pages, cited, v, METRIC_CONTEXT.get(k, GENERIC_CONTEXT), version, k,
                                          templates, metrics)
            if evidence[k] is None and version >= 2:
                status[k] = template_evidence(pages, cited, v, (templates or {}).get(k), metrics)[1]
        present = {k: e is not None for k, e in evidence.items()}
        out.update(status="verified" if present and all(present.values()) else "verified_figure_missing",
                   verified_present=present, pages_checked=cited, figure_rules=evidence)
        if status:
            out["template_status"] = status
    return out


def sis_url_ok(url: str) -> bool:
    """HTTPS on an allowlisted SIS host, default port, no credentials."""
    try:
        u = urlsplit(str(url))
        return (u.scheme == "https" and (u.hostname or "") in SIS_HOSTS and u.port in (None, 443)
                and not u.username and not u.password)
    except (TypeError, ValueError):
        return False


def sis_redirect_handler():
    from urllib.request import HTTPRedirectHandler

    class SisOnlyRedirect(HTTPRedirectHandler):
        """Follow a redirect only to another allowlisted SIS HTTPS URL."""

        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if not sis_url_ok(newurl):
                raise PermissionError(f"redirect_off_allowlist: {urlsplit(str(newurl)).hostname}")
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    return SisOnlyRedirect()


def read_capped(response, max_bytes: int, deadline: float | None = None,
                clock: Callable[[], float] = time.monotonic) -> bytes:
    """Read in chunks; abort as soon as the body passes ``max_bytes`` (declared length checked first) or, when a
    deadline is given, as soon as it passes (a server trickling bytes cannot outlast the capture budget)."""
    declared = (getattr(response, "headers", None) or {}).get("Content-Length")
    if declared and str(declared).isdigit() and int(declared) > max_bytes:
        raise ValueError(f"response_too_large: declared {declared} > {max_bytes}")
    chunks, size = [], 0
    while True:
        chunk = response.read(64 * 1024)
        if not chunk:
            break
        if deadline is not None and clock() >= deadline:
            raise TimeoutError("capture_time_budget_exhausted")
        size += len(chunk)
        if size > max_bytes:
            raise ValueError(f"response_too_large: > {max_bytes} bytes")
        chunks.append(chunk)
    return b"".join(chunks)


class SisFetcher:
    """GET for SIS documents: allowlisted hosts (redirects included), robots.txt per host (shared policy of
    ``datos_gob_sources.load_robots_policy``: 401/403/429/5xx/network fail closed, 404 allowed), a byte cap and a
    per-request timeout bounded by the capture deadline. ``opener`` is injectable so tests never touch the network."""

    def __init__(self, *, opener=None, deadline: float | None = None, clock: Callable[[], float] = time.monotonic,
                 timeout: float = REQUEST_TIMEOUT_S, max_bytes: int = MAX_BYTES):
        from urllib.request import build_opener
        self.opener = opener or build_opener(sis_redirect_handler())
        self.deadline, self.clock, self.timeout, self.max_bytes = deadline, clock, timeout, max_bytes
        self.robots: dict[str, object] = {}

    def _timeout(self) -> float:
        if self.deadline is None:
            return self.timeout
        left = self.deadline - self.clock()
        if left <= 0:
            raise TimeoutError("capture_time_budget_exhausted")
        return max(1.0, min(self.timeout, left))

    def _get(self, url: str, max_bytes: int) -> bytes:
        from urllib.request import Request
        if not sis_url_ok(url):
            raise PermissionError(f"host_not_allowlisted: {urlsplit(str(url)).hostname}")
        req = Request(url, headers={"User-Agent": USER_AGENT})
        with self.opener.open(req, timeout=self._timeout()) as response:
            final = response.geturl() if hasattr(response, "geturl") else url
            if not sis_url_ok(final):
                raise PermissionError(f"redirect_off_allowlist: {urlsplit(str(final)).hostname}")
            return read_capped(response, max_bytes, self.deadline, self.clock)

    def _policy(self, host: str):
        if host not in self.robots:
            try:
                self.robots[host] = load_robots_policy(lambda u: self._get(u, MAX_ROBOTS_BYTES), f"https://{host}/robots.txt")[0]
            except RobotsUnavailable as exc:
                self.robots[host] = exc
        policy = self.robots[host]
        if isinstance(policy, Exception):
            raise policy
        return policy

    def __call__(self, url: str) -> bytes:
        if not sis_url_ok(url):
            raise PermissionError(f"host_not_allowlisted: {urlsplit(str(url)).hostname}")
        if not self._policy(urlsplit(url).hostname).can_fetch(USER_AGENT, url):
            raise PermissionError(f"robots_disallowed: {urlsplit(url).path}")
        return self._get(url, self.max_bytes)


def default_fetch(url: str) -> bytes:
    return SisFetcher()(url)


def _capture_doc(doc: dict, *, fetch: Callable[[str], bytes], parse: Callable[[bytes], dict], expected: str) -> dict:
    try:
        data = fetch(doc["url"])
    except Exception as exc:
        return {**doc, "status": "fetch_failed", "error": f"{type(exc).__name__}:{exc}"[:160],
                "attempts": int(doc.get("attempts") or 0) + 1, "fetched_at": _now()}
    fmt = file_format(data)
    rec = {"url": doc["url"], **({"topic": doc["topic"]} if doc.get("topic") else {}),
           "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "format": fmt, "fetched_at": _now()}
    if fmt != expected:
        return {**rec, "status": "unexpected_format", "parse": None}
    try:
        parsed = parse(data)
    except Exception as exc:  # one bad file never aborts the capture; recorded and retried after RETRY_AFTER_DAYS
        return {**rec, "status": "parse_failed", "parse": None, "error": f"{type(exc).__name__}:{exc}"[:160],
                "attempts": int(doc.get("attempts") or 0) + 1}
    return {**rec, "status": "captured", "parse": parsed}


def _recheck_doc(prev: dict, *, fetch: Callable[[str], bytes], parse: Callable[[bytes], dict],
                 stored: Callable[[dict], bytes | None] | None = None) -> dict:
    """Re-check a document already captured with an older checker version. The bytes come from ``stored`` when it
    has them (this module never stores binaries, so by default they are downloaded again through ``fetch``, i.e. the
    same allowlist / robots / size / time limits). They must hash to the recorded SHA-256: on mismatch the document
    goes to HOLD ('hash_mismatch', recorded hash and parse kept, never re-captured automatically). A failed download or
    parse leaves the previous record in place and notes the attempt in ``recheck``."""
    attempts = int((prev.get("recheck") or {}).get("attempts") or 0) + 1
    try:
        data = (stored(prev) if stored else None) or fetch(prev["url"])
    except Exception as exc:
        return {**prev, "recheck": {"status": "fetch_failed", "error": f"{type(exc).__name__}:{exc}"[:160],
                                    "attempts": attempts, "at": _now()}}
    sha = hashlib.sha256(data).hexdigest()
    if sha != prev.get("sha256"):
        return {**prev, "status": "hash_mismatch", "recheck": {"status": "hash_mismatch", "recorded_sha256": prev.get("sha256"),
                                                              "fetched_sha256": sha, "bytes": len(data), "at": _now()}}
    try:
        parsed = parse(data)
    except Exception as exc:
        return {**prev, "recheck": {"status": "parse_failed", "error": f"{type(exc).__name__}:{exc}"[:160],
                                    "attempts": attempts, "at": _now()}}
    rest = {k: v for k, v in prev.items() if k not in ("recheck", "previous_parse")}
    return {**rest, "status": "captured", "parse": parsed, "previous_parse": prev.get("parse"), "rechecked_at": _now(),
            "rechecked_from_checker_version": int((prev.get("parse") or {}).get("checker_version") or DEFAULT_CHECKER_VERSION)}


def capture(root: Path, *, fetch: Callable[[str], bytes] | None = None, max_new: int = 6,
            time_budget_s: float = TIME_BUDGET_S, clock: Callable[[], float] = time.monotonic,
            stored: Callable[[dict], bytes | None] | None = None) -> dict:
    """Download each listed document once (at most ``max_new`` per kind and run, newest release first); store hashes
    and parsed values, never binaries. A failed download is retried up to MAX_ATTEMPTS times, then once a week; a file
    that downloads but fails to parse is retried after RETRY_AFTER_DAYS. The whole step stops starting downloads once
    ``time_budget_s`` has elapsed (documents left for the next run stay 'not_fetched').

    A Boletín document already captured whose parse carries an older ``checker_version`` than the code's, or other
    ``templates_sha256`` than its topic's current figure templates (and that has verified figures to check), is
    re-checked once (``_recheck_doc``); it uses the same download budget and limits."""
    root = Path(root)
    deadline = clock() + time_budget_s
    fetch = fetch or SisFetcher(deadline=deadline, clock=clock)
    budget = {"left": max_new}
    summary: dict = {"time_budget_s": time_budget_s, "time_budget_exhausted": False}

    def has_time() -> bool:
        if clock() >= deadline:
            summary["time_budget_exhausted"] = True
            return False
        return True

    def days_since(old: dict) -> float:
        try:
            last = datetime.fromisoformat(str(old.get("fetched_at")))
        except ValueError:
            return float("inf")
        return (datetime.now(timezone.utc) - last).total_seconds() / 86400

    def needs(old: dict | None) -> bool:
        if not old or old.get("status") == "not_fetched":
            return True
        if old.get("status") == "parse_failed":
            return days_since(old) >= RETRY_AFTER_DAYS
        if old.get("status") != "fetch_failed":
            return False
        if int(old.get("attempts") or 0) < MAX_ATTEMPTS:
            return True
        return days_since(old) >= RETRY_AFTER_DAYS

    def needs_recheck(old: dict | None, topic: str | None, has_metrics: bool, templates: dict) -> bool:
        if not old or old.get("status") != "captured" or old.get("format") != "pdf" or not has_metrics:
            return False
        parsed = old.get("parse") or {}
        version = checker_version(topic)
        recorded = int(parsed.get("checker_version") or DEFAULT_CHECKER_VERSION)
        current_tpl = templates_sha256(templates) if version >= 2 else None
        if recorded >= version and parsed.get("templates_sha256") == current_tpl:
            return False
        last = old.get("recheck") or {}
        if last.get("status") == "fetch_failed" and int(last.get("attempts") or 0) >= MAX_ATTEMPTS:
            return days_since({"fetched_at": last.get("at")}) >= RETRY_AFTER_DAYS
        if last.get("status") == "parse_failed":
            return days_since({"fetched_at": last.get("at")}) >= RETRY_AFTER_DAYS
        return True

    # GES
    path = root / STORE / "ges_quarterly.json"
    store = _load(path, {}) or {}
    known = {r["period"]: r for r in store.get("releases") or []}
    for rel in reversed(ges_releases(root)):
        old = known.get(rel["period"])
        old_doc = (old or {}).get("document")
        if old_doc and old_doc.get("url") != rel["documents"][0]["url"]:
            old_doc = None  # a new file for the same period: capture it (the revision is detected downstream)
        if needs(old_doc) and budget["left"] > 0 and has_time():
            budget["left"] -= 1
            title = rel["title"]
            doc = _capture_doc({**(old_doc or {}), "url": rel["documents"][0]["url"]}, fetch=fetch, expected="xlsx",
                               parse=lambda b, t=title: data_insights.parse_ges_workbook(b, t))
            known[rel["period"]] = {k: rel[k] for k in ("period", "title", "release_url", "published_at")} | {"document": doc}
        elif old:
            known[rel["period"]] = {**old, **{k: rel[k] for k in ("title", "release_url", "published_at")}}
    store = {"schema_version": SCHEMA, "kind": "ges", "updated_at": _now(), "releases": [known[k] for k in sorted(known)]}
    _write(path, store)
    used = max_new - budget["left"]
    budget["left"] = max_new
    summary["ges"] = {"releases": len(store["releases"]), "downloads": used,
                      "captured": sum(1 for r in store["releases"] if (r.get("document") or {}).get("status") == "captured")}

    # Boletín IP
    path = root / STORE / "boletin_ip.json"
    store = _load(path, {}) or {}
    known = {r["period"]: r for r in store.get("releases") or []}
    releases, rejected = boletin_releases(root)
    verified = verified_metrics(root)
    for rel in reversed(releases):
        old = known.get(rel["period"]) or {}
        old_docs = {d["url"]: d for d in old.get("documents") or []}
        docs = []
        for d in rel["documents"]:
            prev = old_docs.get(d["url"])
            info = verified.get(d["url"]) or {}
            tpl = figure_templates(root, d.get("topic"))
            parse = (lambda b, m=info.get("metrics"), pg=info.get("pages_1based"), t=d.get("topic"), tp=tpl:
                     parse_boletin_pdf(b, m, pg, t, tp))
            if needs(prev) and budget["left"] > 0 and has_time():
                budget["left"] -= 1
                docs.append(_capture_doc({**(prev or {}), **d}, fetch=fetch, expected="pdf", parse=parse))
            elif needs_recheck(prev, d.get("topic"), bool(info.get("metrics")), tpl) and budget["left"] > 0 and has_time():
                budget["left"] -= 1
                docs.append(_recheck_doc({**prev, **d}, fetch=fetch, parse=parse, stored=stored))
            else:
                docs.append(prev or {**d, "status": "not_fetched"})
        known[rel["period"]] = {k: rel[k] for k in ("period", "number", "title", "release_url", "published_at")} | {"documents": docs}
    store = {"schema_version": SCHEMA, "kind": "boletin_ip", "updated_at": _now(),
             "releases": [known[k] for k in sorted(known)], "rejected_releases": rejected}
    _write(path, store)
    summary["boletin_ip"] = {"releases": len(store["releases"]), "rejected": len(rejected), "downloads": max_new - budget["left"]}
    return summary


def _write(path: Path, payload: dict) -> None:
    """Rewrite only when something other than ``updated_at`` changed (no daily churn in the committed store)."""
    old = _load(path, None)
    if isinstance(old, dict) and {k: v for k, v in old.items() if k != "updated_at"} == \
            {k: v for k, v in payload.items() if k != "updated_at"}:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
