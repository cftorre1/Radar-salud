"""Article-scoped ACHS extraction and a deterministic materiality gate.

Do not infer publication dates from navigation, event dates or related news.
An editorial rejection is evidence of discovery, not a technical failure.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

from .models import RawItem
from .public_source_pipeline import _date

SOURCES = {"clinicas_achs_salud", "achs_seguro_laboral", "ist"}


class SourceDiscoveryError(RuntimeError):
    def __init__(self, code, url, detail=""):
        self.code, self.url, self.detail = code, url, detail
        super().__init__(f"{code}: {url}" + (f" ({detail})" if detail else ""))


def chile_today():
    return datetime.now(ZoneInfo("America/Santiago")).date()


def fold(text):
    return "".join(c for c in unicodedata.normalize("NFD", text.casefold())
                   if unicodedata.category(c) != "Mn")


def valid_date(value):
    parsed = _date(value or "")
    try:
        return parsed if date.fromisoformat(parsed) <= chile_today() else None
    except (ValueError, TypeError):
        return None


class Article(HTMLParser):
    """Visible H1 and following content, ending before related news/footer.

This intentionally uses semantic elements, not unverified CSS classes. Missing
or conflicting publication evidence is fail-closed.
"""
    STOP = ("ultimas publicaciones", "noticias relacionadas", "informacion corporativa",
            "tambien te puede interesar", "deja una respuesta", "dejar un comentario", "que es ist")
    IGNORE = {"script", "style", "nav", "footer", "aside", "noscript"}

    def __init__(self):
        super().__init__()
        self.title = ""
        self.meta_date = ""
        self.visible_date = ""
        self.date_evidence = ""
        self.parts = []
        self._ignore = []
        self._heading = None
        self._heading_parts = []
        self._active = False
        self._stopped = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in self.IGNORE:
            self._ignore.append(tag)
            if tag == "footer":
                self._stopped = True
            return
        if self._ignore:
            return
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").casefold()
            if key in ("article:published_time", "datepublished", "publishdate"):
                self.meta_date = a.get("content") or ""
        if re.fullmatch("h[1-6]", tag):
            self._heading, self._heading_parts = tag, []
        if tag == "time" and self._active and "published" in (a.get("class") or ""):
            self.visible_date = a.get("datetime") or self.visible_date
            self.date_evidence = "time.published@datetime"

    def handle_endtag(self, tag):
        if self._ignore:
            if tag == self._ignore[-1]:
                self._ignore.pop()
            return
        if tag == self._heading:
            heading = " ".join(" ".join(self._heading_parts).split())
            self._heading = None
            if tag == "h1" and not self.title:
                self.title, self._active = heading, True
            elif fold(heading) in self.STOP:
                self._stopped = True
            elif self._active and not self._stopped and heading != self.title:
                self.parts.append(heading)

    def handle_data(self, data):
        if self._ignore or self._stopped:
            return
        text = " ".join(data.split())
        if not text:
            return
        if self._heading:
            self._heading_parts.append(text)
            return
        if not self._active:
            return
        # Only a standalone header date, never a date embedded in body prose.
        if not self.visible_date and len(" ".join(self.parts)) < 350:
            if re.fullmatch(r"\d{1,2}[/-]\d{1,2}[/-]20\d{2}", text):
                self.visible_date, self.date_evidence = text, "visible_date_after_h1"
        self.parts.append(text)

    def result(self):
        visible, meta = valid_date(self.visible_date), valid_date(self.meta_date)
        if self.visible_date and not visible:
            return self.title, None, " ".join(self.parts), "invalid_visible_date"
        if self.meta_date and not meta:
            return self.title, None, " ".join(self.parts), "invalid_published_meta"
        if visible and meta and visible != meta:
            return self.title, None, " ".join(self.parts), "conflicting_publication_dates"
        return (self.title, visible or meta, " ".join(self.parts),
                self.date_evidence if visible else "article:published_time" if meta else "missing_publication_date")


def market_role(title, body):
    text = fold(f"{title} {body}")
    if "achs salud" in fold(title) and "centros" in fold(title) and "clinicas achs salud" not in text:
        return "provider_achs_centers"
    # Provider attribution requires the clinic network as an actor in the story.
    # A link/footer or a physician from Hospital del Trabajador is insufficient.
    if "clinicas achs salud" in text or re.search(
            r"clinica (?:atacama|portada|maitenes|lircay|los andes|del sur|puerto montt) achs salud", text):
        if "accidentes de trayecto" not in fold(title):
            return "provider_achs"
    return "mutuality"


def materiality(role, title, body):
    """Reason codes are retained in raw metadata and the reconciliation ledger."""
    text, headline = fold(f"{title} {body}"), fold(title)
    # Require a concrete change even when the page contains prevention keywords.
    if re.search(r"feria de bienestar|testimonio|historia de superacion|campana|semana de la|"
                 r"reconoc|premio|conmemor|seminario|congreso|webinar|caminata|pausas activas", headline):
        return False, "campaign_event_testimonial_or_recognition"
    if re.search(r"\b(?:inaugur|ampli|apertur|traslad|inversion|adqui|habilit|nuevo centro|nueva clinica)", text):
        return True, "capacity_or_investment_change"
    if re.search(r"(?:activa|incorpora|se suman|se suma).{0,180}(?:fonasa|safed|mcc)|"
                 r"(?:fonasa|safed|mcc).{0,180}(?:activa|incorpora|prestaciones|atencion)", text):
        return True, "public_private_coverage_change"
    if role == "mutuality":
        if re.search(r"(?:nuevo adherente|incorpora|incorporando).{0,160}\d[\d.,]*.{0,35}trabajador", text):
            return True, "quantified_coverage_change"
        if re.search(r"(?:accident|siniestr|enfermedad).{0,220}(?:aument|disminu|alza|baja|reduccion).{0,100}\d|"
                     r"(?:aument|disminu|alza|baja|reduccion).{0,100}\d.{0,140}(?:accident|siniestr)", text):
            return True, "quantified_occupational_data"
        if re.search(r"(?:nueva guia|nuevo protocolo|nueva plataforma|nuevo modulo|estrena modulo)", text):
            if re.search(r"(?:tratamiento|reintegro|evaluacion|reporteria|accidentes graves|patologias)", text):
                return True, "new_operational_tool_or_protocol"
    return False, "no_verifiable_material_change"


def discover_items(scout, html, detail_loader):
    from .beta_sources import _Links
    from urllib.parse import urljoin, urlparse, urlunparse

    class NewsHeadings(_Links):
        """IST news links occur in article headings, not the main navigation."""
        def __init__(self):
            super().__init__()
            self.heading = False
            self.ignored = []
        def handle_starttag(self, tag, attrs):
            if tag in ("nav", "header", "footer", "aside"):
                self.ignored.append(tag)
            if tag in ("h2", "h3") and not self.ignored:
                self.heading = True
            if self.heading and not self.ignored:
                super().handle_starttag(tag, attrs)
        def handle_endtag(self, tag):
            super().handle_endtag(tag)
            if tag in ("h2", "h3"):
                self.heading = False
            if self.ignored and tag == self.ignored[-1]:
                self.ignored.pop()
    links = NewsHeadings() if scout.slug == "ist" else _Links()
    links.feed(html)
    rows, seen = [], set()
    scout.decisions = []
    attempted = 0
    for href, _ in links.links:
        parsed = urlparse(urljoin(scout.cfg["page"], href or ""))
        if parsed.scheme != "https" or parsed.netloc not in scout.cfg["hosts"]:
            continue
        if not re.fullmatch(scout.cfg["path"], parsed.path):
            continue
        if scout.slug == "ist" and parsed.path.rstrip("/") in ("/noticias", "/contacto", "/historia", "/quienes-somos"):
            continue
        url = urlunparse(parsed._replace(query="", fragment=""))
        if url in seen:
            continue
        seen.add(url)
        if attempted >= 60:
            break
        attempted += 1
        try:
            article = Article()
            article.feed(detail_loader(url))
        except Exception as exc:
            raise SourceDiscoveryError("detail_fetch_failed", url, type(exc).__name__) from exc
        title, published, body, evidence = article.result()
        decision = {"url": url, "title": title, "event_date": published, "date_evidence": evidence}
        scout.decisions.append(decision)
        if not published or len(title) < 18 or len(body) < 160:
            decision.update(status="pending", reason=evidence if not published else "article_content_unrecognized")
            continue
        if (chile_today() - date.fromisoformat(published)).days > 90:
            decision.update(status="rejected", reason="outside_90_day_horizon")
            continue
        role = market_role(title, body) if scout.slug != "ist" else "mutuality"
        expected = scout.cfg["role"]
        if role != expected:
            decision.update(status="rejected", reason="different_market_role", actual_role=role)
            continue
        accepted, reason = materiality(role, title, body)
        decision.update(status="candidate" if accepted else "rejected", reason=reason)
        rows.append(RawItem(scout.slug, title[:350], url, scout.cfg["name"], scout.cfg["type"],
                            event_date=published, raw_text=body[:1800], metadata={
                                "discovered_from": scout.cfg["page"], "page_text": body[:18000],
                                "market_role": role, "article_extraction": "occupational_v1",
                                "date_evidence": evidence, "publication_date": published,
                                "source_quality_gate": "passed", "materiality_accepted": accepted,
                                "materiality_reason": reason}))
    if not attempted:
        raise SourceDiscoveryError("listing_structure_unrecognized", scout.cfg["page"])
    if not rows and any(d["status"] == "pending" for d in scout.decisions):
        raise SourceDiscoveryError("detail_publication_evidence_missing", scout.cfg["page"])
    # Zero items for the requested role is a valid editorial outcome.
    return sorted(rows, key=lambda r: r.event_date, reverse=True)
