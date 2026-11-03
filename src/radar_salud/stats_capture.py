"""Captures for the F4 (GES) and F6 (Boletín IP) statistics fichas.

The SIS releases are listed in ``data/history/superintendencia_signals.json`` (title, release page and document
URLs). This module downloads each document once, stores its SHA-256 and the parsed, reconciled values in
``data/stats_fichas/captures/<kind>.json`` and never stores the binary. A document already captured is not downloaded
again (no backfill: only the releases already in the history are read, at most ``max_new`` per run), except once when
the Boletín checker version or the figure templates of its topic change: then it is re-checked and must
hash to the recorded SHA-256.

Text receipts (2-nov-2026): each captured or re-checked document also leaves its extracted text in
``data/stats_fichas/text/<sha256[:16]>.json`` (once per sha256, capped), for the reviewer who writes the independent
reading; a captured document of the newest release of each kind without one is downloaded once more for it.

- GES (xlsx): ``data_insights.parse_ges_workbook`` — the corrected parser: the sheet of the reporting year is
  pinned and the rows must add up to the declared total, else HOLD.
- Boletín IP (PDF): the text is never interpreted by a model. The figures come from the independent reading in
  ``config/statistical_analysis_verified_v1.json`` and the capture only records whether each verified figure is
  present in the captured document's text (``verified_present``) and under which rule (``figure_rules``: the
  context window or, for acreditación, a human-reviewed anchored template). Releases whose documents belong to another
  release (e.g. a 'Septiembre 2026' page listing the 'enero-junio-2026' PDFs) are rejected, never relabelled.
  A release can also be listed as loose PDFs (the Intendencia de Prestadores listing, one history record per PDF,
  e.g. N°3-2026 detected on 29-oct-2026): one PDF per topic with the same number and period in the file names forms
  the release; it has no publication date (dated by first detection).
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


LOOSE_SOURCE = "Superintendencia de Salud · Intendencia de Prestadores"


def loose_boletin_releases(signals: list[dict]) -> tuple[dict[str, dict], list[dict]]:
    """Releases formed by the loose PDF records of the Prestadores listing (one record per PDF, no release page).

    Grouped by the number and period in the file names; a group is a release only with exactly one PDF per topic.
    No publication date is exposed by that listing: ``published_at`` stays None and ``first_detected_at`` dates it."""
    groups: dict[tuple, dict] = {}
    for sig in signals:
        url = str(sig.get("source_url") or "")
        if sig.get("source_name") != LOOSE_SOURCE or sig.get("source_documents") or not url.startswith("https://"):
            continue
        d = doc_release(url)
        if not d or not url.lower().split("?")[0].endswith(".pdf"):
            continue
        g = groups.setdefault((d["number"], d["period"]), {"docs": {}, "titles": [], "detected": []})
        g["docs"].setdefault(d["topic"], set()).add(url)
        g["titles"].append(" ".join(str(sig.get("title") or "").split()))
        day = str(sig.get("first_detected_at") or sig.get("detected_at") or sig.get("event_date") or "")
        if day:
            g["detected"].append(day)
    ok, rejected = {}, []
    numbers_by_period: dict[str, set] = {}
    for (number, period) in groups:
        numbers_by_period.setdefault(period, set()).add(number)
    for (number, period), g in sorted(groups.items(), key=lambda kv: kv[0][1]):
        # Two bulletin numbers claiming one period (review 2-nov): never pick one silently; every group is rejected.
        if len(numbers_by_period[period]) > 1:
            rejected.append({"title": f"PDF sueltos {number}", "release_url": None, "reasons": ["multiple_bulletin_numbers_for_period"],
                             "document_periods": [period], "listing_titles": sorted(set(g["titles"]))})
            continue
        if sorted(g["docs"]) != sorted(TOPICS) or any(len(u) != 1 for u in g["docs"].values()):
            rejected.append({"title": f"PDF sueltos {number}", "release_url": None, "reasons": ["listing_documents_not_one_per_topic"],
                             "document_periods": [period], "listing_titles": sorted(set(g["titles"]))})
            continue
        ok[period] = {"period": period, "number": number, "title": f"PDF sueltos {number}", "release_url": None,
                      "published_at": None, "first_detected_at": min(g["detected"]) if g["detected"] else None,
                      "basis": "listing_documents", "listing_titles": sorted(set(g["titles"])),
                      "documents": [{"url": next(iter(g["docs"][t])), "topic": t} for t in sorted(g["docs"])]}
    return ok, rejected


def boletin_releases(root: Path) -> tuple[list[dict], list[dict]]:
    """Releases with exactly one document per topic whose file names carry the release's own period.

    A release page wins over loose listing PDFs of the same period; loose PDFs fill a period no valid page covers
    (e.g. N°3-2026, whose 'Septiembre 2026' page still linked the N°2 PDFs)."""
    ok, rejected = {}, []
    signals = _signals(root)
    for sig in signals:
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
    loose, loose_rejected = loose_boletin_releases(signals)
    for period, rel in loose.items():
        ok.setdefault(period, rel)
    rejected += [r for r in loose_rejected
                 if r["document_periods"][0] not in ok or "multiple_bulletin_numbers_for_period" in r["reasons"]]
    return [ok[k] for k in sorted(ok)], rejected


def verified_metrics(root: Path) -> dict[str, dict]:
    """Independently verified Boletín figures by document URL (config/statistical_analysis_verified_v1.json)."""
    cfg = _load(Path(root) / VERIFIED, {})
    out = {}
    for doc in (cfg.get("primary_review") or {}).get("documents") or []:
        if doc.get("url") and isinstance(doc.get("verified_metrics"), dict):
            out[doc["url"]] = {"metrics": doc["verified_metrics"], "pages_1based": doc.get("pages_1based"),
                               "reviewed_at": cfg.get("reviewed_at"), "unit_caution": doc.get("unit_caution"),
                               # Short footnotes on figures whose source tables do not add up (Dirección 2-nov,
                               # 'mostrar con nota'): metric key → text with {metric} placeholders; never a fix.
                               "source_notes": doc.get("source_notes") if isinstance(doc.get("source_notes"), dict) else {}}
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
    "cumulative_requests_2019_to_june2026": ("solicitud", "mediacion"),  # any '…_to_<month><year>': see metric_context
    "monthly_average_2026": ("reclamo",),
    "monthly_average_2025": ("reclamo",),
    "reported_growth_percent_rounded": ("reclamo", "aument", "variacion", "increment"),
    "registered_titles": ("titulo",),
    "records_without_birth_date": ("nacimiento",),
}
CONTEXT_CHARS = 80


def metric_context(key: str) -> tuple[str, ...]:
    """Context words of a verified metric; keys carrying a period are matched by pattern (N°3: '…_to_september2026')."""
    if key in METRIC_CONTEXT:
        return METRIC_CONTEXT[key]
    if re.fullmatch(r"cumulative_requests_20\d{2}_to_[a-z]+20\d{2}", key):
        return ("solicitud", "mediacion")
    if re.fullmatch(r"monthly_average_20\d{2}", key):
        return ("reclamo",)
    return GENERIC_CONTEXT


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
# Version 3 (acreditación, Dirección 2026-11-01, Boletín N°3): a metric that has a figure template is placed ONLY by
# that template (it must match exactly once on the cited pages; the context window no longer substitutes for it), and
# a document without an independent reading yet records a template pre-check (``template_precheck``: status, page,
# whether it is the hinted page, and matched figures per template, over the whole document) for the reviewer. The
# pre-check never verifies a figure.
CHECKER_VERSIONS = {"acreditacion": 3}
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
    text = m[0] if len(m[0]) <= 300 else f"{m[0][:150]} … {m[0][-120:]}"  # both anchors kept
    ev = {"rule": "template", "page": page, "match": text, "reviewed_by": tpl.get("reviewed_by"),
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
    anchored 'template' of the metric (``templates[key]``). From v3 a metric with a template is placed only by it.
    Nothing else."""
    if version >= 3 and key and (templates or {}).get(key):
        return template_evidence(pages, cited, n, templates[key], metrics)[0]
    for p in cited:
        if present_in(pages[p - 1], n, context):
            return {"rule": "context_window", "page": p}
    if version < 2 or not key:
        return None
    return template_evidence(pages, cited, n, (templates or {}).get(key), metrics)[0]


def template_precheck(pages: list[str], templates: dict | None) -> dict:
    """Without an independent reading: does each approved template match exactly once in the document? Records the
    status, the page (and whether it is the template's ``pages_hint`` page) and the matched figures for the reviewer who
    writes the reading; never a verified figure (the reading's cited pages decide, see ``template_evidence``)."""
    out = {}
    for key, tpl in sorted((templates or {}).items()):
        pat, why = template_pattern(tpl)
        hint = [p for p in tpl.get("pages_hint") or [] if isinstance(p, int)]
        if not pat:
            out[key] = {"status": why, "pages_hint": hint}
            continue
        hits = [(i, m) for i, text in enumerate(pages, 1) for m in pat.finditer(normalize_page(text))]
        rec = {"status": "ok" if len(hits) == 1 else ("no_match" if not hits else f"multiple_matches:{len(hits)}"),
               "pages_hint": hint}
        if hits:
            rec["pages"] = sorted({i for i, _ in hits})
        if len(hits) == 1:
            page, m = hits[0]
            groups = [int(g) for g in m.groups()]
            rec.update(page=page, on_hint=page in hint, figures=groups)
            if tpl.get("sum_of") and sum(groups[i - 1] for i in tpl["sum_of"]) != groups[int(tpl.get("figure_group") or 1) - 1]:
                rec["status"] = "sum_mismatch"
        out[key] = rec
    return out


def reading_sha256(metrics: dict | None, pages_1based: list | None) -> str | None:
    """Hash of the independent reading of one document (figures and cited pages); None without a reading."""
    if not metrics:
        return None
    return hashlib.sha256(json.dumps({"metrics": metrics, "pages": pages_1based or []}, sort_keys=True,
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


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
    # The reading hash is recorded for every checker version (review of PR #126, 2-nov): a parse is bound to the exact
    # reading it checked, and a parse whose reading changed (or carries no hash) is re-checked and HOLDs meanwhile.
    base = {"checker_version": version, "templates_sha256": templates_sha256(templates),
            "reading_sha256": reading_sha256(metrics, pages_1based)}
    try:
        pages = pdf_pages(data)
    except Exception as exc:  # unreadable PDF: captured hash, no verification
        return {"status": "pdf_unreadable", "error": f"{type(exc).__name__}"[:80], **base}
    text = "\n".join(pages)
    out = {"status": "no_verified_metrics", "pages": len(pages),
           "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), **base}
    if not metrics and version >= 3 and templates:
        out["template_precheck"] = template_precheck(pages, templates)
    if metrics:
        cited = [p for p in (pages_1based or []) if isinstance(p, int) and 1 <= p <= len(pages)]
        evidence, status = {}, {}
        for k, v in metrics.items():
            if not isinstance(v, (int, float)):
                continue
            evidence[k] = figure_evidence(pages, cited, v, metric_context(k), version, k, templates, metrics)
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


# Text receipts (Dirección 2-nov-2026, data/stats_fichas/POLICY.md "Text receipts"). The reviewer who writes the
# independent reading of a new release needs the documents' text, and only the daily run can download SIS files. Each
# captured (or re-checked) SIS document leaves data/stats_fichas/text/<sha256[:16]>.json: url, sha256, extracted_at,
# extractor, and per page the raw extracted text and the template-normalized text (``normalize_page``). For xlsx: the
# sheet names and the first TEXT_XLSX_ROWS rows of each sheet. Public SIS statistics only (``sis_url_ok``); written once
# per sha256; capped at TEXT_MAX_UNITS pages (sheets) and TEXT_MAX_BYTES of JSON per document.
TEXT_STORE = Path("data/stats_fichas/text")
TEXT_SCHEMA = "stats_text_receipt_v1"
TEXT_MAX_UNITS = 60
TEXT_MAX_BYTES = 200 * 1024
TEXT_XLSX_ROWS = 40
TEXT_BASIS = ("public_government_statistics: Superintendencia de Salud (superdesalud.gob.cl) statistics bulletin, "
              "data/stats_fichas/POLICY.md")
# Receipt states after which the document is never downloaded again for its text (``needs_text_backfill``).
TEXT_DONE = frozenset({"written", "exists", "extract_failed", "refused", "hash_mismatch", "prefix_collision",
                       "unsupported_format"})
# Backfill reaches only the newest captured release(s) of each kind: the one awaiting an independent reading.
TEXT_BACKFILL_RELEASES = 1


def text_receipt_path(sha256: str) -> Path:
    return TEXT_STORE / f"{str(sha256)[:16]}.json"


def _cell_text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _pdf_units(data: bytes) -> tuple[dict, int, list[str]]:
    import pypdf
    reader = pypdf.PdfReader(io.BytesIO(data))
    total = len(reader.pages)
    raws = [(reader.pages[i].extract_text() or "") for i in range(min(total, TEXT_MAX_UNITS))]
    return {"name": "pypdf", "version": getattr(pypdf, "__version__", None)}, total, raws


def _xlsx_units(data: bytes) -> tuple[dict, int, list[str], list[str]]:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        names = list(wb.sheetnames)
        raws = []
        for name in names[:TEXT_MAX_UNITS]:
            rows = []
            for row in wb[name].iter_rows(min_row=1, max_row=TEXT_XLSX_ROWS, values_only=True):
                cells = [_cell_text(v) for v in row]
                while cells and not cells[-1]:
                    cells.pop()
                rows.append("\t".join(cells))
            while rows and not rows[-1]:
                rows.pop()
            raws.append("\n".join(rows))
    finally:
        wb.close()
    return {"name": "openpyxl", "version": getattr(openpyxl, "__version__", None)}, len(names), raws, names


def _dump(payload: dict) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def build_text_receipt(url: str, data: bytes, fmt: str | None = None, *, now: str | None = None) -> dict:
    """The receipt of one document's bytes (no I/O). Raises on unreadable bytes; the caller records the failure."""
    fmt = fmt or file_format(data)
    if fmt == "pdf":
        extractor, total, raws = _pdf_units(data)
        names, unit = None, "pages"
    elif fmt == "xlsx":
        extractor, total, raws, names = _xlsx_units(data)
        unit = "sheets"
    else:
        raise ValueError(f"unsupported_format:{fmt}")
    receipt = {"schema_version": TEXT_SCHEMA, "url": url, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
               "format": fmt, "extracted_at": now or _now(), "extractor": extractor,
               "normalization": "stats_capture.normalize_page: casefold, accents folded, thousands dots removed, "
                                "whitespace collapsed",
               "basis": TEXT_BASIS,
               "limits": {"max_units": TEXT_MAX_UNITS, "max_bytes": TEXT_MAX_BYTES,
                          **({"rows_per_sheet": TEXT_XLSX_ROWS} if fmt == "xlsx" else {})},
               f"{unit}_total": total, **({"sheet_names": names} if names is not None else {}),
               "truncated": total > TEXT_MAX_UNITS, "truncated_reasons": (["max_units"] if total > TEXT_MAX_UNITS else []),
               f"{unit}_kept": 0, unit: []}
    key = "page" if unit == "pages" else "sheet"
    for i, raw in enumerate(raws, 1):
        entry = {key: i, **({"name": names[i - 1]} if names is not None else {}),
                 "text_normalized": normalize_page(raw), "text_raw": raw}
        receipt[unit].append(entry)
        receipt[f"{unit}_kept"] = len(receipt[unit])
        if len(_dump(receipt)) <= TEXT_MAX_BYTES:
            continue
        # This unit overflows the byte cap: keep the longest prefix of its texts that fits, then stop.
        receipt[unit].pop()
        receipt[f"{unit}_kept"] = len(receipt[unit]) + 1  # the truncated prefix below (dropped again if it is empty)
        receipt["truncated"] = True
        receipt["truncated_reasons"] = sorted(set(receipt["truncated_reasons"]) | {"max_bytes"})
        lo, hi = 0, max(len(raw), len(entry["text_normalized"]))
        while lo < hi:
            mid = (lo + hi + 1) // 2
            receipt[unit].append({**entry, "text_normalized": entry["text_normalized"][:mid], "text_raw": raw[:mid],
                                  "text_truncated": True})
            fits = len(_dump(receipt)) <= TEXT_MAX_BYTES
            receipt[unit].pop()
            lo, hi = (mid, hi) if fits else (lo, mid - 1)
        if lo > 0:
            receipt[unit].append({**entry, "text_normalized": entry["text_normalized"][:lo], "text_raw": raw[:lo],
                                  "text_truncated": True})
        break
    receipt[f"{unit}_kept"] = len(receipt[unit])
    if len(_dump(receipt)) > TEXT_MAX_BYTES:  # only when even the header does not fit (never for SIS documents)
        raise ValueError("receipt_header_over_max_bytes")
    return receipt


def write_text_receipt(root: Path, url: str, data: bytes, fmt: str | None = None, *, now: str | None = None) -> dict:
    """Write the text receipt of ``data`` once per sha256; returns the state recorded on the capture record.

    Refused (nothing written) for any URL outside the SIS allowlist: only public SIS statistics bulletins are kept as
    text; never another host, a paywalled or a non-government source."""
    if not sis_url_ok(url):
        return {"status": "refused", "reason": "host_not_allowlisted"}
    sha = hashlib.sha256(data).hexdigest()
    rel = text_receipt_path(sha)
    path = Path(root) / rel
    old = _load(path, None)
    if isinstance(old, dict):
        if old.get("sha256") == sha:
            return {"status": "exists", "path": rel.as_posix()}
        return {"status": "prefix_collision", "path": rel.as_posix(), "other_sha256": old.get("sha256")}
    fmt = fmt or file_format(data)
    if fmt not in ("pdf", "xlsx"):
        return {"status": "unsupported_format", "format": fmt}
    try:
        receipt = build_text_receipt(url, data, fmt, now=now)
    except Exception as exc:  # unreadable bytes: recorded, never retried for the same sha
        return {"status": "extract_failed", "error": f"{type(exc).__name__}:{exc}"[:160]}
    payload = _dump(receipt)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return {"status": "written", "path": rel.as_posix(), "bytes": len(payload), "truncated": receipt["truncated"]}


def needs_text_backfill(root: Path, doc: dict | None) -> bool:
    """A document captured before text receipts existed (or whose download for it failed) gets its receipt once."""
    if not doc or doc.get("status") != "captured" or doc.get("format") not in ("pdf", "xlsx"):
        return False
    if not doc.get("sha256") or not sis_url_ok(doc.get("url")):
        return False
    if (Path(root) / text_receipt_path(doc["sha256"])).exists():
        return False
    last = doc.get("text_receipt") or {}
    if last.get("status") in TEXT_DONE:
        return False
    if last.get("status") == "fetch_failed" and int(last.get("attempts") or 0) >= MAX_ATTEMPTS:
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(str(last.get("at")))).total_seconds() / 86400
        except ValueError:
            return True
        return age >= RETRY_AFTER_DAYS
    return True


def _backfill_text(root: Path, doc: dict, *, fetch: Callable[[str], bytes],
                   stored: Callable[[dict], bytes | None] | None = None) -> dict:
    """Obtain the bytes of a captured document again (same fetcher and limits), check they hash to the recorded
    SHA-256 and write its text receipt. The capture record itself (status, parse) is left unchanged."""
    attempts = int((doc.get("text_receipt") or {}).get("attempts") or 0) + 1
    try:
        data = (stored(doc) if stored else None) or fetch(doc["url"])
    except Exception as exc:
        return {**doc, "text_receipt": {"status": "fetch_failed", "error": f"{type(exc).__name__}:{exc}"[:160],
                                        "attempts": attempts, "at": _now(), "backfill": True}}
    sha = hashlib.sha256(data).hexdigest()
    if sha != doc.get("sha256"):
        return {**doc, "text_receipt": {"status": "hash_mismatch", "recorded_sha256": doc.get("sha256"),
                                        "fetched_sha256": sha, "at": _now(), "backfill": True}}
    return {**doc, "text_receipt": {**write_text_receipt(root, doc["url"], data, doc.get("format")), "backfill": True}}


def _receipt(text: Callable[[str, bytes, str], dict] | None, url: str, data: bytes, fmt: str) -> dict:
    if not text:
        return {}
    try:
        return {"text_receipt": text(url, data, fmt)}
    except Exception as exc:  # a receipt failure never fails the capture
        return {"text_receipt": {"status": "write_failed", "error": f"{type(exc).__name__}:{exc}"[:160]}}


def _capture_doc(doc: dict, *, fetch: Callable[[str], bytes], parse: Callable[[bytes], dict], expected: str,
                 text: Callable[[str, bytes, str], dict] | None = None) -> dict:
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
    rec.update(_receipt(text, doc["url"], data, fmt))
    try:
        parsed = parse(data)
    except Exception as exc:  # one bad file never aborts the capture; recorded and retried after RETRY_AFTER_DAYS
        return {**rec, "status": "parse_failed", "parse": None, "error": f"{type(exc).__name__}:{exc}"[:160],
                "attempts": int(doc.get("attempts") or 0) + 1}
    return {**rec, "status": "captured", "parse": parsed}


def _recheck_doc(prev: dict, *, fetch: Callable[[str], bytes], parse: Callable[[bytes], dict],
                 stored: Callable[[dict], bytes | None] | None = None,
                 text: Callable[[str, bytes, str], dict] | None = None) -> dict:
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
    rest.update(_receipt(text, prev["url"], data, prev.get("format") or file_format(data)))
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
    re-checked once (``_recheck_doc``); it uses the same download budget and limits.

    Every capture and re-check also writes the document's text receipt (``write_text_receipt``, once per sha256). A
    captured document of the newest ``TEXT_BACKFILL_RELEASES`` release(s) of each kind that has no receipt yet is
    downloaded once more for it (``_backfill_text``), after captures and re-checks, within the same budget and limits."""
    root = Path(root)
    deadline = clock() + time_budget_s
    fetch = fetch or SisFetcher(deadline=deadline, clock=clock)
    budget = {"left": max_new}
    text = lambda url, data, fmt: write_text_receipt(root, url, data, fmt)  # noqa: E731
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

    def needs_recheck(old: dict | None, topic: str | None, info: dict, templates: dict) -> bool:
        if not old or old.get("status") != "captured" or old.get("format") != "pdf" or not info.get("metrics"):
            return False
        parsed = old.get("parse") or {}
        version = checker_version(topic)
        recorded = int(parsed.get("checker_version") or DEFAULT_CHECKER_VERSION)
        current_tpl = templates_sha256(templates) if version >= 2 else None
        # An independent reading added (or changed) after the capture: the document is read again once (e.g. N°3,
        # captured before its reading existed). A parse without a reading hash (checker v1/v2 before 2-nov) cannot show
        # which reading it checked, so it is re-checked too (bytes must hash to the recorded SHA-256).
        reading_changed = parsed.get("reading_sha256") != reading_sha256(info.get("metrics"), info.get("pages_1based"))
        if recorded >= version and parsed.get("templates_sha256") == current_tpl and not reading_changed:
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
                               parse=lambda b, t=title: data_insights.parse_ges_workbook(b, t), text=text)
            known[rel["period"]] = {k: rel[k] for k in ("period", "title", "release_url", "published_at")} | {"document": doc}
        elif old:
            known[rel["period"]] = {**old, **{k: rel[k] for k in ("title", "release_url", "published_at")}}
    text_backfills = 0
    for period in sorted(known, reverse=True)[:TEXT_BACKFILL_RELEASES]:
        doc = known[period].get("document")
        if needs_text_backfill(root, doc) and budget["left"] > 0 and has_time():
            budget["left"] -= 1
            text_backfills += 1
            known[period] = {**known[period], "document": _backfill_text(root, doc, fetch=fetch, stored=stored)}
    store = {"schema_version": SCHEMA, "kind": "ges", "updated_at": _now(), "releases": [known[k] for k in sorted(known)]}
    _write(path, store)
    used = max_new - budget["left"]
    budget["left"] = max_new
    summary["ges"] = {"releases": len(store["releases"]), "downloads": used,
                      "captured": sum(1 for r in store["releases"] if (r.get("document") or {}).get("status") == "captured"),
                      "text_backfills": text_backfills}

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
                docs.append(_capture_doc({**(prev or {}), **d}, fetch=fetch, expected="pdf", parse=parse, text=text))
            elif needs_recheck(prev, d.get("topic"), info, tpl) and budget["left"] > 0 and has_time():
                budget["left"] -= 1
                docs.append(_recheck_doc({**prev, **d}, fetch=fetch, parse=parse, stored=stored, text=text))
            else:
                docs.append(prev or {**d, "status": "not_fetched"})
        known[rel["period"]] = ({k: rel[k] for k in ("period", "number", "title", "release_url", "published_at")}
                                | {k: rel[k] for k in ("first_detected_at", "basis", "listing_titles") if k in rel}
                                | {"documents": docs})
    text_backfills = 0
    for period in sorted(known, reverse=True)[:TEXT_BACKFILL_RELEASES]:
        docs = []
        for doc in known[period].get("documents") or []:
            if needs_text_backfill(root, doc) and budget["left"] > 0 and has_time():
                budget["left"] -= 1
                text_backfills += 1
                doc = _backfill_text(root, doc, fetch=fetch, stored=stored)
            docs.append(doc)
        known[period] = {**known[period], "documents": docs}
    store = {"schema_version": SCHEMA, "kind": "boletin_ip", "updated_at": _now(),
             "releases": [known[k] for k in sorted(known)], "rejected_releases": rejected}
    _write(path, store)
    summary["boletin_ip"] = {"releases": len(store["releases"]), "rejected": len(rejected), "downloads": max_new - budget["left"],
                             "text_backfills": text_backfills}
    return summary


def _write(path: Path, payload: dict) -> None:
    """Rewrite only when something other than ``updated_at`` changed (no daily churn in the committed store)."""
    old = _load(path, None)
    if isinstance(old, dict) and {k: v for k, v in old.items() if k != "updated_at"} == \
            {k: v for k, v in payload.items() if k != "updated_at"}:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
