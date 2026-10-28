"""Superintendencia de Salud newsroom (noticias y comunicados), Dirección 28-oct-2026.

Listing: ``https://www.superdesalud.gob.cl/noticias/<año>/`` (one page per year, no
pagination). Each entry is one link wrapping the date (dd/mm/aaaa, sometimes absent),
the title and "Leer noticia"; article URLs follow ``/noticias/AAAA/MM/slug/``.

Rules:
* robots.txt is honoured before any request to the listing or an article
  (``robots_disallowed`` stops the surface; an unreadable robots file fails closed,
  a 404 robots file means no restriction, as RFC 9309 states).
* Terms: public institutional news. We keep title, URL, date and a bounded text
  excerpt for analysis; cards link to the official page. Nothing is republished in full.
* The listing has been seen pairing a title with another entry's URL (15-06-2026), so
  the article page decides title and date; disagreements are recorded, never guessed.
  An entry with no verifiable date is not published (no first-detection dating here).
* Same act as a normativa card: the export folds the news card into the act's card
  (``fold_news_into_acts``), so the feed never shows the same act twice.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Callable, Iterable
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser
from zoneinfo import ZoneInfo

from .models import RawItem
from .scouts import _AnchorParser, fetch_html

SLUG = "superintendencia_noticias"
SOURCE_NAME = "Superintendencia de Salud"
HOST = "www.superdesalud.gob.cl"
ROBOTS = f"https://{HOST}/robots.txt"
USER_AGENT = "RadarSaludBot"
LISTING = "https://www.superdesalud.gob.cl/noticias/{year}/"
ARTICLE_PATH = re.compile(r"^/noticias/(20\d{2})/(0[1-9]|1[0-2])/[a-z0-9][a-z0-9-]*/?$")
_LISTED_DATE = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(20\d{2})\b")
_LEER = re.compile(r"\s*Leer noticia\s*$", re.I)
TERMS_POLICY = "public_institutional_news_title_link_and_bounded_excerpt"
DETAIL_WINDOW_DAYS = 30  # article pages fetched only for entries that can still be processed
CHILE = ZoneInfo("America/Santiago")

_ACT = re.compile(r"\b(Oficio\s+Circular|Circular|Resoluci[oó]n\s+Exenta)\s+(?:(IF|IP|SS)\s*[/\-]?\s*)?N?\s*[°º]?\s*(\d[\d\.]*)", re.I)


def robots_allows(url: str, fetch: Callable[[str], str] = fetch_html) -> bool:
    try:
        body = fetch(ROBOTS)
    except HTTPError as exc:
        if exc.code in (404, 410):
            return True
        raise PermissionError(f"robots_policy_unavailable: HTTP {exc.code}") from exc
    except Exception as exc:  # network failure: fail closed
        raise PermissionError(f"robots_policy_unavailable: {type(exc).__name__}") from exc
    parser = RobotFileParser()
    parser.parse(str(body).splitlines())
    return parser.can_fetch(USER_AGENT, url)


def _iso(day: str, month: str, year: str) -> str | None:
    try:
        return date(int(year), int(month), int(day)).isoformat()
    except ValueError:
        return None


def parse_listing(html: str, page_url: str) -> list[dict]:
    """Entries in page order: url, listing title, listing date (or None)."""
    parser = _AnchorParser()
    parser.feed(html)
    out, seen = [], set()
    for href, text in parser.links:
        url = urljoin(page_url, href or "")
        parts = urlsplit(url)
        if parts.netloc != HOST or not ARTICLE_PATH.match(parts.path) or url in seen:
            continue
        seen.add(url)
        m = _LISTED_DATE.match(text)
        listed = _iso(*m.groups()) if m else None
        title = _LEER.sub("", text[m.end():] if m else text).strip()
        if len(title) < 8:
            continue
        out.append({"url": url, "listing_title": title, "listing_date": listed,
                    "url_month": "-".join(ARTICLE_PATH.match(parts.path).groups())})
    return out


def parse_article(html: str) -> dict:
    from .public_source_pipeline import _Meta, _date
    meta = _Meta()
    meta.feed(html)
    text = " ".join(meta.text)
    published = _date(meta.published) if meta.published else None
    visible = None
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b", text[:4000])
    if m:
        visible = _iso(*m.groups())
    if not visible:
        visible = _date(text[:4000])
    return {"title": meta.ogtitle or None, "published": published, "visible_date": visible,
            "description": meta.description, "text": text}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()
                  .translate(str.maketrans("áéíóúüñ", "aeiouun"))).strip()


def mentioned_acts(text: str) -> list[str]:
    """Normative identities named in the news text (``circular-if-534``)."""
    from .normative_relations import normalize_id, target_key
    keys = []
    for m in _ACT.finditer(text or ""):
        key = target_key(normalize_id(m.group(1), m.group(2), m.group(3)))
        if key and key not in keys:
            keys.append(key)
    return keys


class SuperintendenciaNoticiasScout:
    SOURCE_SLUG = SLUG
    SOURCE_NAME = SOURCE_NAME
    SOURCE_TYPE = "official"

    def __init__(self, fetch: Callable[[str], str] = fetch_html, today: date | None = None, robots=None):
        self.fetch = fetch
        self.today = today
        self.robots = robots or (lambda url: robots_allows(url, self.fetch))
        self.surface_results = []
        self.discovery_errors = []

    def listing_urls(self) -> list[str]:
        today = self.today or datetime.now(CHILE).date()
        years = [today.year] + ([today.year - 1] if today.month == 1 else [])
        return [LISTING.format(year=y) for y in years]

    def discover(self) -> list[RawItem]:
        today = self.today or datetime.now(CHILE).date()
        entries = []
        for page in self.listing_urls():
            if not self.robots(page):
                raise PermissionError("robots_disallowed: " + page)
            found = parse_listing(self.fetch(page), page)
            self.surface_results.append({"url": page, "status": "parsed", "documents": len(found)})
            entries.extend(found)
        if not entries:
            raise RuntimeError("SIS newsroom listing has no article entries")
        out = []
        for entry in entries:
            listed = entry["listing_date"]
            # Bound requests: only entries that can still enter the daily window (or undated ones
            # whose URL month is recent) get their article page.
            previous_month = (today.replace(day=1) - timedelta(days=1)).isoformat()[:7]
            recent_month = entry["url_month"] in (today.isoformat()[:7], previous_month)
            if listed and (today - date.fromisoformat(listed)).days > DETAIL_WINDOW_DAYS:
                continue
            if not listed and not recent_month:
                continue
            meta = {"listing_url": urljoin(entry["url"], f"/noticias/{entry['url_month'][:4]}/"),
                    "listing_title": entry["listing_title"], "listing_date": listed,
                    "terms_policy": TERMS_POLICY}
            title, event_date = entry["listing_title"], listed
            try:
                if not self.robots(entry["url"]):
                    raise PermissionError("robots_disallowed")
                article = parse_article(self.fetch(entry["url"]))
            except Exception as exc:
                self.discovery_errors.append(f"{entry['url']}: {type(exc).__name__}")
                meta["fetch_error"] = type(exc).__name__
                article = None
            if article:
                page_date = article["published"] or article["visible_date"]
                if article["title"]:
                    if _norm(article["title"]) != _norm(title):
                        meta["listing_title_mismatch"] = True  # listing paired another entry's title
                    title = article["title"]
                if page_date and listed and page_date != listed:
                    meta["listing_date_conflict"] = {"listing": listed, "article": page_date}
                event_date = page_date or (listed if not meta.get("listing_title_mismatch") else None)
                meta.update(page_text=article["text"][:18000], publication_date_source=(
                    "article:published_time" if article["published"] else "article_visible_date" if article["visible_date"]
                    else "listing_date" if event_date else None))
                summary = article["description"] or article["text"][:1800]
            else:
                summary = ""
            meta["mentioned_acts"] = mentioned_acts(" ".join([title, meta.get("page_text", "")[:6000]]))
            out.append(RawItem(SLUG, title, entry["url"], SOURCE_NAME, self.SOURCE_TYPE,
                               event_date=event_date, raw_text=summary, metadata=meta))
        out.sort(key=lambda r: r.event_date or "", reverse=True)
        return out


_MATERIAL = ("isapre", "fonasa", "ges", "auge", "caec", "circular", "resolución", "resolucion", "licencia",
             "prestador", "acreditación", "acreditacion", "multa", "sanci", "cobertura", "ley ", "precio",
             "tabla de factores", "restitución", "restitucion", "deuda", "utilidades", "pérdidas", "perdidas",
             "plan de salud", "cotizantes", "beneficiarios", "garantías", "garantias", "superintendente")
_NOISE = ("seminario", "ceremonia", "visita", "punto de vacunación", "punto de vacunacion", "celebra",
          "conmemora", "participa", "asume como", "es nombrado", "subrogante")


def process_superintendencia_noticias(raw, cfg):
    """Usual editorial gate for official news: materiality, AI relevance >= 65 within budget."""
    from .llm_analysis import analyze_official_news
    from .pipeline import build_signal
    from .processing import DeferredProcessing, RejectedProcessing
    if raw.source_slug != SLUG or urlsplit(raw.url).netloc != HOST:
        raise RejectedProcessing("not_an_official_sis_news_url")
    if not raw.event_date:
        raise DeferredProcessing("sis_news_without_verified_publication_date")
    if raw.metadata.get("listing_title_mismatch") and raw.metadata.get("publication_date_source") == "listing_date":
        raise DeferredProcessing("sis_news_listing_identity_mismatch_without_article_date")
    body = raw.metadata.get("page_text") or raw.raw_text or ""
    low = f"{raw.title} {body[:4000]}".lower()
    if any(x in raw.title.lower() for x in _NOISE) and not any(x in raw.title.lower() for x in ("isapre", "ges", "multa")):
        raise RejectedProcessing("institutional_agenda_not_market_signal")
    if not any(x in low for x in _MATERIAL):
        raise RejectedProcessing("not_material_for_health_market")
    ai = analyze_official_news(title=raw.title, text=body[:9000], source_name=SOURCE_NAME)
    score = int(ai.get("relevance_score")) if ai else 66
    if score < 65:
        raise RejectedProcessing("editorial_relevance_below_threshold")
    scopes = []
    if re.search(r"\bisapres?\b", low):
        scopes.append("Isapres")
    if "fonasa" in low:
        scopes.append("Fonasa")
    if re.search(r"prestador|cl[ií]nica|hospital|cesfam|acreditaci", low):
        scopes.append("Prestadores")
    scopes = scopes or ["Sistema de salud"]
    what = ((ai or {}).get("what_happened") or raw.raw_text or raw.title).strip()
    why = ((ai or {}).get("why_it_matters") or
           "Comunicado oficial de la Superintendencia de Salud con efectos para aseguradoras, prestadores o beneficiarios.").strip()
    raw.metadata.update({"what_happened": what, "why_it_matters": why, "signal_types": ["Noticias"], "scopes": scopes,
                         "watch_tags": ["superintendencia de salud", "comunicado"] + [s.lower() for s in scopes],
                         "scores": {"economic": 50, "regulatory": 70, "scope": score, "novelty": score, "actionability": 66}})
    row = build_signal(raw, cfg).to_dict()
    row.update(signal_types=["Noticias"], scopes=scopes, editorial_relevance=score,
               mentioned_acts=raw.metadata.get("mentioned_acts") or [],
               publication_date_source=raw.metadata.get("publication_date_source"))
    if raw.metadata.get("listing_date_conflict"):
        row["listing_date_conflict"] = raw.metadata["listing_date_conflict"]
    return row


def fold_news_into_acts(cards: Iterable[dict]) -> list[dict]:
    """A SIS news card about an act that has its own normativa card is the same story:
    keep the act's card, attach the news as an official alternative source."""
    from .normative_relations import target_key
    cards = [dict(c) for c in cards]
    acts = {}
    for c in cards:
        if c.get("source_name") == SOURCE_NAME and ("Normativa" in (c.get("signal_types") or []) or c.get("event_type") == "REGULATION"):
            key = target_key(str(c.get("normative_document_label") or c.get("title") or ""))
            if key:
                acts[key] = c
    out = []
    for c in cards:
        if str(c.get("source_url") or "").startswith(f"https://{HOST}/noticias/"):
            lead = next((acts[k] for k in c.get("mentioned_acts") or [] if k in acts), None)
            if lead is not None:
                alts = list(lead.get("source_alternatives") or [])
                if c.get("source_url") not in {a.get("url") for a in alts}:
                    alts.append({"title": c.get("title"), "source_name": SOURCE_NAME, "url": c.get("source_url"),
                                 "event_date": c.get("event_date"), "relationship": "Comunicado oficial sobre el mismo acto"})
                lead["source_alternatives"] = alts
                continue
        out.append(c)
    return out
