"""Fiscalía Nacional Económica (FNE): health-sector merger control and competition cases.

Dirección 28-oct-2026 17:08: "Avanza con FNE y Congreso". Many DF/Pulso health
stories are mergers, acquisitions and competition cases; the FNE's own news
listing is the official, open record of each step (investigation opened,
Phase 2, approved, approved with conditions, prohibited) and of conduct cases
(requerimientos ante el TDLC, acuerdos, estudios de mercado).

Surface (verified with WebFetch on 28-oct-2026):
``https://www.fne.gob.cl/comunicaciones/noticias-2/`` and
``.../noticias-2/page/{n}/`` — six items per page, each a thumbnail link, a
date shown as ``DD/ MM / YYYY``, an ``h3`` title link to
``https://www.fne.gob.cl/<slug>/`` and a truncated excerpt. The merger
"Buscador" page has no server-rendered listing, and no RSS/REST endpoint was
found, so the news listing is the source.

Rights: the site footer reads "Todos los derechos reservados, Fiscalía
Nacional Económica". We therefore keep only the official title, date, link and
the case stage/parties derived deterministically from the title. Excerpts and
bodies are never stored. robots.txt is honoured (``official_open.RobotsGate``).
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from .models import RawItem
from .official_open import RobotsGate, chile_today, fetch, fold, health_basis, official, scopes_for
from .processing import DeferredProcessing, RejectedProcessing

SLUG = "fne_competencia"
SOURCE_NAME = "Fiscalía Nacional Económica (FNE)"
HOSTS = ("www.fne.gob.cl", "fne.gob.cl")
LISTING = "https://www.fne.gob.cl/comunicaciones/noticias-2/"
EVIDENCE_KIND = "fne_news_listing_date"
TERMS_POLICY = "title_date_link_only"
DEFAULT_PAGES = 4
DEFAULT_WINDOW_DAYS = 10
_DATE = re.compile(r"\b(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(20\d{2})\b")
# First-level paths that are site sections, never a news post.
_SECTIONS = {"comunicaciones", "fusiones", "antimonopolios", "nosotros", "biblioteca", "fiscalizacion",
             "servicios", "en", "wp-content", "tag", "category", "page", "transparencia", "contacto",
             "biblioteca-digital", "mapa-del-sitio", "politica-de-privacidad", "advocacy", "estudios-de-mercado"}


def live_lane_enabled(env=None):
    from .live_lanes import enabled
    return enabled("RADAR_FNE", env)


def listing_url(page):
    return LISTING if page <= 1 else f"{LISTING}page/{page}/"


def post_url(url):
    """A single-segment FNE post URL (``https://www.fne.gob.cl/<slug>/``)."""
    if not official(url, HOSTS):
        return False
    parts = [p for p in urlsplit(url).path.split("/") if p]
    return len(parts) == 1 and parts[0] not in _SECTIONS and "." not in parts[0] and not urlsplit(url).query


class _ListingParser(HTMLParser):
    """Title links in document order, each with the listing date shown before it."""

    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.rows = []
        self._href = None
        self._text = []
        self._date = None

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)
            return
        m = _DATE.search(data)
        if m:
            d, mo, y = (int(x) for x in m.groups())
            try:
                self._date = date(y, mo, d).isoformat()
            except ValueError:
                pass

    def handle_endtag(self, tag):
        if tag != "a" or self._href is None:
            return
        text = " ".join("".join(self._text).split())
        href, self._href, self._text = self._href, None, []
        url = urljoin(self.base, href or "")
        if self._date and len(text) >= 20 and post_url(url):
            self.rows.append({"title": text, "url": url, "date": self._date})
            self._date = None  # one date per row


def parse_listing(html, base_url=LISTING):
    rows, seen = [], set()
    parser = _ListingParser(base_url)
    parser.feed(html)
    for row in parser.rows:
        if row["url"] not in seen:
            seen.add(row["url"])
            rows.append(row)
    return rows


# --- deterministic case reading of the official title ---------------------------

_NOISE = re.compile(
    r"\b(particip[oa]|participan|charla|feria|taller|seminario|conversatorio|webinar|se reuni[oe]|reunion con|"
    r"conmemora|cuenta publica|nombra|asume|visita|convenio de colaboracion|dicto|capacitacion|premi[oa]|"
    r"concurso|pasantia|saluda|encuentro|jornada|curso|clase magistral|expuso|expone|presento libro)\b")
_MERGER = r"(adquisicion|compra|fusion|toma de control|operacion de concentracion|asociacion|joint venture|control)"


def classify(title):
    """(family, stage) from the official title, or ("noise", reason)."""
    t = fold(title).casefold()
    if _NOISE.search(t):
        return "noise", "institutional_agenda"
    merger = re.search(_MERGER, t)
    if merger and re.search(r"\bprohib", t):
        return "merger", "prohibida"
    if merger and re.search(r"\bfase (2|ii)\b", t):
        return "merger", "en_analisis_fase_2"
    if merger and re.search(r"\b(aprueb|aprob|autoriz|luz verde)", t):
        cond = re.search(r"\b(condicion|medidas|mitigacion|remedio)", t)
        return "merger", "aprobada_con_condiciones" if cond else "aprobada"
    if merger and re.search(r"\b(inicia|abre) (la )?investigacion|\binvestigacion (por|sobre)|\bnotific", t):
        return "merger", "en_analisis_fase_1"
    if merger and re.search(r"\b(desist|abandon|retir)", t):
        return "merger", "desistida"
    if re.search(r"\b(requerimiento|requiere|pide al tdlc|demanda|acusa)\b", t):
        return "conduct", "requerimiento"
    if re.search(r"\bacuerdo extrajudicial\b", t):
        return "conduct", "acuerdo_extrajudicial"
    if re.search(r"\b(tdlc|corte suprema)\b", t) and re.search(r"\b(acoge|condena|sanciona|multa|rechaza|confirma)", t):
        return "conduct", "resolucion_judicial"
    if re.search(r"\bestudio de mercado\b", t):
        return "market_study", "estudio_mercado"
    if re.search(r"\b(archiva|cierra investigacion)", t):
        return "conduct", "archivo"
    if re.search(r"\b(recomienda|propone|sugiere|informe)\b", t):
        return "advocacy", "recomendacion"
    if merger:
        return "merger", "comunicado"
    return "other", "comunicado"


_LEGAL = re.compile(r",?\s*\b(S\.?\s?A\.?|SpA|S\.?p\.?A\.?|Ltda\.?|Limitada|Inc\.?|LLC|Ltd\.?|N\.?V\.?|S\.?L\.?)\s*$", re.I)


def _party(text):
    text = re.sub(r"\(.*?\)", " ", text)
    text = re.sub(r"^(la|el|las|los|su|sus|matriz de|parte de|control (en|de)|activos de|acciones de)\s+", "", text.strip(), flags=re.I)
    text = _LEGAL.sub("", text.strip(" ,.;:"))
    return " ".join(text.split()).strip(" ,.;:")


def parties(title):
    """Merging parties named in the title: [{"role", "name"}]. Empty when not stated."""
    t = " ".join(str(title or "").split())
    m = re.search(r"(?:adquisici[oó]n|compra|toma) de (?:control (?:en|de) )?(?P<target>.+?) por parte de (?P<acq>.+?)$", t, re.I)
    if m:
        out = [{"role": "target", "name": _party(m["target"])}]
        out += [{"role": "acquirer", "name": _party(x)} for x in re.split(r"\s+y\s+|,\s*", m["acq"]) if _party(x)]
        return [p for p in out if len(p["name"]) >= 3]
    m = re.search(r"fusi[oó]n (?:entre|de) (?P<a>.+?) y (?P<b>.+?)$", t, re.I)
    if m:
        return [{"role": "party", "name": _party(m["a"])}, {"role": "party", "name": _party(m["b"])}]
    return []


STAGE_LABEL = {
    "en_analisis_fase_1": "inició la investigación (Fase 1) de una operación de concentración",
    "en_analisis_fase_2": "extendió a Fase 2 la investigación de una operación de concentración",
    "aprobada": "aprobó una operación de concentración",
    "aprobada_con_condiciones": "aprobó con condiciones una operación de concentración",
    "prohibida": "prohibió una operación de concentración",
    "desistida": "informó el desistimiento de una operación de concentración",
    "requerimiento": "presentó o anunció una acción por conducta anticompetitiva",
    "acuerdo_extrajudicial": "informó un acuerdo extrajudicial",
    "resolucion_judicial": "informó una resolución judicial en un caso de libre competencia",
    "estudio_mercado": "informó un estudio de mercado",
    "archivo": "informó el archivo de una investigación",
    "recomendacion": "emitió una recomendación o propuesta",
    "comunicado": "publicó un comunicado",
}


def items_from_rows(rows, *, listing, today, window_days, catalog=None, report=None):
    start = today - timedelta(days=window_days)
    out = []
    for row in rows:
        day = date.fromisoformat(row["date"])
        decision = {"url": row["url"], "date": row["date"]}
        if not start <= day <= today:
            decision["reason"] = "outside_window"
        else:
            family, stage = classify(row["title"])
            basis = health_basis(row["title"], catalog)
            if family == "noise":
                decision["reason"] = "institutional_agenda"
            elif not basis:
                decision["reason"] = "not_health_sector"
            else:
                decision["reason"] = "accepted"
                found = parties(row["title"]) if family == "merger" else []
                out.append(RawItem(
                    SLUG, row["title"][:350], row["url"], SOURCE_NAME, "official", event_date=row["date"], raw_text="",
                    metadata={"case_family": family, "case_stage": stage, "parties": found,
                              "health_basis": basis, "listing_url": listing,
                              "publication_date_source": EVIDENCE_KIND,
                              "publication_date_evidence": {"kind": EVIDENCE_KIND, "url": listing, "date": row["date"]},
                              "terms_policy": TERMS_POLICY}))
        if report is not None:
            report.append(decision)
    return out


class FneScout:
    """Health-sector FNE news (mergers and competition) inside the daily window."""
    slug = SLUG

    def __init__(self, fetch_fn=None, today=None, window_days=None, pages=None, enabled=None, robots=None):
        self.fetch = fetch_fn or (lambda url: fetch(url, HOSTS))
        self.today = today
        self.window_days = window_days
        self.pages = pages or DEFAULT_PAGES
        self.enabled = enabled
        self.robots = robots
        self.diagnostics = {}
        self.discovery_errors = []
        self.discovery_audit = []

    def _allowed(self, url):
        if self.robots is None:
            self.robots = RobotsGate(self.fetch).allowed
        return self.robots(url)

    def discover(self):
        enabled = live_lane_enabled() if self.enabled is None else self.enabled
        if not enabled:
            self.diagnostics = {"status": "not_run_outside_engine_runtime", "partial_failure": False}
            return []
        today = self.today or chile_today()
        window = self.window_days or DEFAULT_WINDOW_DAYS
        items, pages, errors = [], [], []
        for page in range(1, self.pages + 1):
            url = listing_url(page)
            try:
                if not self._allowed(url):
                    raise PermissionError(f"robots_disallowed: {urlsplit(url).path}")
                body, capture = self.fetch(url)
                rows = parse_listing(body.decode((capture or {}).get("charset") or "utf-8", errors="replace"), url)
            except Exception as exc:
                errors.append({"url": url, "reason": f"{type(exc).__name__}: {exc}"[:300]})
                break
            if not rows:
                errors.append({"url": url, "reason": "listing_structure_changed: no dated post links"})
                break
            items += items_from_rows(rows, listing=url, today=today, window_days=window, report=self.discovery_audit)
            pages.append({"url": url, "rows": len(rows), "oldest": min(r["date"] for r in rows),
                          "sha256": (capture or {}).get("sha256")})
            if min(r["date"] for r in rows) < (today - timedelta(days=window)).isoformat():
                break  # the window is covered
        covered = bool(pages) and pages[-1]["oldest"] < (today - timedelta(days=window)).isoformat()
        self.diagnostics = {"pages": pages, "errors": errors, "window_days": window, "window_complete": covered,
                            "partial_failure": bool(errors), "terms_policy": TERMS_POLICY}
        if errors and not pages:
            raise RuntimeError("FNE discovery failed: " + "; ".join(e["reason"] for e in errors))
        self.discovery_errors = [f"{e['url']}: {e['reason']}" for e in errors]
        if not covered and not errors:
            self.discovery_errors.append(f"window_not_fully_covered_by_{self.pages}_pages")
        return items


WHY = {
    "merger": ("Las operaciones de concentración en salud cambian la estructura de mercado de prestadores, "
               "aseguradores o proveedores; la etapa informada por la FNE indica si la operación puede "
               "materializarse y bajo qué condiciones."),
    "conduct": ("Es una actuación oficial de la autoridad de libre competencia en un mercado del sector salud; "
                "puede derivar en sanciones o en cambios de conducta de los actores involucrados."),
    "market_study": "Un estudio de mercado de la FNE puede anticipar recomendaciones regulatorias para el sector.",
    "advocacy": ("Es una recomendación oficial de la autoridad de libre competencia; no obliga por sí sola, "
                 "pero suele orientar cambios regulatorios o decisiones del TDLC."),
    "other": "Es un comunicado oficial de la autoridad de libre competencia referido al sector salud.",
}


def process_fne(raw, cfg):
    """Deterministic card (no AI). Only the official title, date, link and title-derived stage."""
    from .editorial_gate import publication_ready
    from .pipeline import build_signal
    md = raw.metadata or {}
    ev = md.get("publication_date_evidence") or {}
    if (raw.source_slug != SLUG or not post_url(raw.url) or ev.get("kind") != EVIDENCE_KIND
            or ev.get("date") != raw.event_date or not official(ev.get("url"), HOSTS)):
        raise DeferredProcessing("FNE listing evidence unverified")
    family, stage = classify(raw.title)
    if family == "noise":
        raise RejectedProcessing("fne_institutional_agenda")
    if not health_basis(raw.title):
        raise RejectedProcessing("fne_not_health_sector")
    names = [p["name"] for p in md.get("parties") or []]
    what = f"La FNE {STAGE_LABEL.get(stage, STAGE_LABEL['comunicado'])}: «{raw.title}» ({raw.event_date})."
    if names:
        what += " Partes: " + "; ".join(names) + "."
    scopes = scopes_for(raw.title)
    raw.metadata.update({"what_happened": what, "why_it_matters": WHY.get(family, WHY["other"]),
                         "signal_types": ["Mercado" if family == "merger" else "Legal"], "scopes": scopes,
                         "watch_tags": ["fne", "libre competencia"] + (["fusiones"] if family == "merger" else []),
                         "event_type": "M_AND_A" if family == "merger" else "REGULATORY_ENFORCEMENT",
                         "entities": names,
                         "scores": {"economic": 75 if family == "merger" else 60, "regulatory": 60, "scope": 60,
                                    "novelty": 70, "actionability": 65}})
    row = build_signal(raw, cfg).to_dict()
    row.update(signal_types=raw.metadata["signal_types"], scopes=scopes, publication_date=raw.event_date,
               publication_date_source=EVIDENCE_KIND, publication_date_evidence=ev, fne_case_family=family,
               fne_case_stage=stage, fne_parties=md.get("parties") or [], health_basis=md.get("health_basis"),
               deterministic_processing=True, editorial_relevance=72, terms_policy=TERMS_POLICY)
    accepted, reason, quality = publication_ready(row)
    if not accepted:
        raise RejectedProcessing(f"editorial_gate_{reason}")
    row["publication_ready_score"] = quality
    return row
