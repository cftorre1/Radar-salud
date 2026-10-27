"""Verifiable source text for recent normative acts (Dirección, 27-oct-2026).

The daily runner can reach the regulators; the editorial session cannot. This
stores the extracted text of each recent SIS/SUSESO act's official document so
editorial records (V2.1 "qué cambia") are verified against the real text,
not against automated summaries. Deterministic: no AI, bounded per run, and it
never fails the capture.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from typing import Any, Callable, Iterable

EVIDENCE_DIR = Path("data/analysis_cache/normative_evidence")
SOURCES = {"Superintendencia de Salud", "Superintendencia de Seguridad Social (SUSESO)"}
MAX_CHARS = 60_000


def _key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]


def _document_url(signal: dict[str, Any]) -> tuple[str | None, str]:
    from .regulatory_pipeline import pdf_identity_mismatch
    docs = signal.get("source_documents") if isinstance(signal.get("source_documents"), list) else []
    for doc in docs:
        url = doc.get("url") if isinstance(doc, dict) else None
        if url and ".pdf" in url.lower() and not pdf_identity_mismatch(signal.get("title"), url):
            return url, "pdf"
    if signal.get("source_url") and signal.get("source_name") == "Superintendencia de Seguridad Social (SUSESO)":
        return signal["source_url"], "html"  # SUSESO publishes circulars as HTML articles
    return None, ""


def _html_text(html: str) -> str:
    html = re.sub(r"<(script|style|nav|header|footer)\b.*?</\1>", " ", html, flags=re.S | re.I)
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


def capture_missing(root: Path, signals: Iterable[dict[str, Any]], *, today: date | None = None, days: int = 45,
                    max_docs: int = 20, pdf_text: Callable[[str], str] | None = None,
                    html_fetch: Callable[[str], str] | None = None) -> list[str]:
    if pdf_text is None:
        from .document_intelligence import extract_pdf_text as pdf_text
    if html_fetch is None:
        from .scouts import fetch_html as html_fetch
    today = today or date.today()
    out_dir = Path(root) / EVIDENCE_DIR
    written: list[str] = []
    for s in signals:
        if len(written) >= max_docs:
            break
        if s.get("source_name") not in SOURCES or "Normativa" not in (s.get("signal_types") or []):
            continue
        try:
            day = date.fromisoformat(str(s.get("event_date"))[:10])
        except ValueError:
            continue
        if not timedelta(0) <= today - day <= timedelta(days=days):
            continue
        url, kind = _document_url(s)
        if not url or (out_dir / f"{_key(url)}.json").exists():
            continue
        try:
            text = pdf_text(url) if kind == "pdf" else _html_text(html_fetch(url))
        except Exception:
            continue  # evidence is best-effort; the capture never fails here
        text = (text or "").strip()[:MAX_CHARS]
        if len(text) < 200:
            continue
        out_dir.mkdir(parents=True, exist_ok=True)
        record = {"act": s.get("title"), "source_name": s.get("source_name"), "page_url": s.get("source_url"),
                  "document_url": url, "kind": kind, "event_date": s.get("event_date"),
                  "fetched_at": datetime.now(timezone.utc).isoformat(),
                  "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "text": text}
        (out_dir / f"{_key(url)}.json").write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
        written.append(url)
    return written
