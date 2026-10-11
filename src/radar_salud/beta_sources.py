from __future__ import annotations

import re
from datetime import date
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from .models import RawItem
from .scouts import fetch_html


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self._href = None
        self._parts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self._href = dict(attrs).get("href")
            self._parts = []

    def handle_data(self, data):
        if self._href is not None:
            value = " ".join(data.split())
            if value:
                self._parts.append(value)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            title = " ".join(self._parts).strip()
            self.links.append((self._href, title))
            self._href = None
            self._parts = []


class CuratedBetaSourceScout:
    """Small, explicit beta catalog for provider, mutuality and media signals.

    Inclusion here means Source Quality Gate passed. Discovery remains fail-closed:
    a listing must resolve to a dated detail page on the expected host.
    """

    SOURCES = {
        "red_davila": {
            "name": "Red Dávila",
            "type": "corporate",
            "page": "https://www.davila.cl/novedades",
            "hosts": ("www.davila.cl", "davila.cl"),
            "path": r"/novedades/[^/]+/?",
            "role": "provider",
        },
        "andes_salud": {
            "name": "Andes Salud",
            "type": "corporate",
            "page": "https://www.andessalud.cl/novedades/",
            "hosts": ("www.andessalud.cl", "andessalud.cl"),
            "path": r"/novedades/[^/]+/?",
            "role": "provider",
        },
        "clinicas_achs_salud": {
            "name": "Achs Salud / Clínicas",
            "type": "corporate",
            "page": "https://www.achs.cl/centro-de-noticias",
            "hosts": ("www.achs.cl", "achs.cl", "www.achssalud.cl", "achssalud.cl",
                      "clinicaportada.cl", "www.clinicaportada.cl", "clinicaatacama.cl", "www.clinicaatacama.cl",
                      "clinicaloscoihues.cl", "clinicamaitenes.cl", "www.clinicamaitenes.cl",
                      "clinicalircay.cl", "www.clinicalircay.cl", "clinicalosandes.cl", "www.clinicalosandes.cl",
                      "www.clinicasur.cl", "clinicapuertomontt.cl", "www.clinicapuertomontt.cl",
                      "clinica-curico.cl", "www.clinica-curico.cl"),
            "path": r"/centro-de-noticias/noticia/20\d{2}/[^/]+/?",
            "role": "provider_achs",
            "accepted_roles": ("provider_achs", "provider_achs_centers"),
            "provider_identity_url": "https://www.achssalud.cl/areasdeatencion/clinicas",
        },
        "achs_seguro_laboral": {
            "name": "Achs Seguro Laboral",
            "type": "mutuality",
            "page": "https://www.achs.cl/centro-de-noticias",
            "hosts": ("www.achs.cl", "achs.cl"),
            "path": r"/centro-de-noticias/noticia/20\d{2}/[^/]+/?",
            "role": "mutuality",
        },
        "mutual_seguridad": {
            "name": "Mutual de Seguridad CChC",
            "type": "mutuality",
            "page": "https://www.mutual.cl/portal/publico/empresa/home/nuestra-mutual/noticias/",
            "hosts": ("www.mutual.cl", "mutual.cl"),
            "path": r"/portal/publico/empresa/home/nuestra-mutual/noticias/noticias_detalle/[^/]+/?",
            "role": "mutuality",
        },
        "ist": {
            "name": "Instituto de Seguridad del Trabajo (IST)",
            "type": "mutuality",
            "page": "https://ist.cl/noticias/",
            "hosts": ("www.ist.cl", "ist.cl"),
            "path": r"/[a-z0-9][a-z0-9-]*/?",
            "role": "mutuality",
        },
        "pulso_latercera": {
            "name": "Pulso / La Tercera",
            "type": "press_high_trust",
            "page": "https://www.latercera.com/canal/pulso/",
            "hosts": ("www.latercera.com", "latercera.com"),
            "path": r"/pulso/noticia/[^/]+/?",
            "role": "media",
        },
    }

    def __init__(self, slug):
        if slug not in self.SOURCES:
            raise ValueError("source has not passed beta Source Quality Gate")
        self.slug = slug
        self.cfg = self.SOURCES[slug]

    def discover_from_html(self, html, detail_loader=None):
        detail_loader = detail_loader or fetch_html
        from .occupational_sources import SOURCES, discover_items
        if self.slug in SOURCES:
            return discover_items(self, html, detail_loader)
        from .public_source_pipeline import _Meta, _date

        parser = _Links()
        parser.feed(html)
        out = []
        seen = set()
        for href, listing_title in parser.links:
            if not href:
                continue
            url = urljoin(self.cfg["page"], href)
            parsed = urlparse(url)
            if parsed.scheme != "https" or parsed.netloc not in self.cfg["hosts"]:
                continue
            if not re.fullmatch(self.cfg["path"], parsed.path):
                continue
            if url in seen:
                continue
            seen.add(url)
            try:
                detail = detail_loader(url)
                meta = _Meta()
                meta.feed(detail)
                body = " ".join(meta.text)
                published = _date(meta.published) or _date(body[:6500]) or _date(listing_title)
                if not published or date.fromisoformat(published) > date.today():
                    continue
                title = meta.ogtitle or listing_title
                title = re.sub(r"\s+", " ", title).strip()
                if len(title) < 18:
                    continue
            except Exception:
                continue
            out.append(RawItem(
                self.slug,
                title[:350],
                url,
                self.cfg["name"],
                self.cfg["type"],
                event_date=published,
                raw_text=(meta.description or body[:1800]),
                metadata={
                    "discovered_from": self.cfg["page"],
                    "page_text": body[:18000],
                    "market_role": self.cfg["role"],
                    "source_quality_gate": "passed",
                },
            ))
        if not out:
            raise RuntimeError(f"{self.cfg['name']} has no dated, verified detail items")
        out.sort(key=lambda x: x.event_date or "", reverse=True)
        return out[:30]

    def discover(self):
        from .occupational_sources import SOURCES, SourceDiscoveryError
        if self.slug in SOURCES:
            from .occupational_capture import CaptureLoader
            from .paths import project_root
            from datetime import datetime, timezone
            loader = CaptureLoader(project_root() / "data/audits/source_e_recovery/runtime" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f"))
            def attach(rows):
                for raw in rows:
                    raw.metadata["capture_evidence"] = loader.evidence(raw.url)
                    raw.metadata["listing_capture_evidence"] = loader.evidence(raw.metadata["discovered_from"])
                return rows
        if self.slug in SOURCES:
            from .occupational_recovery import inventory
            self.inventory = inventory(self, loader)
            rows = attach(self.inventory["raw_items"])
            self.decisions = self.inventory["rows"]
            if not self.inventory["coverage_complete"]:
                errors = self.inventory["errors"]
                code = errors[0].get("code", "inventory_capture_incomplete") if len(errors) == 1 and not rows else "inventory_capture_incomplete"
                exc = SourceDiscoveryError(code, errors[0].get("url", self.cfg["page"]) if errors else self.cfg["page"])
                exc.partial_items = rows
                exc.diagnostics = errors
                raise exc
            return rows
        return self.discover_from_html(fetch_html(self.cfg["page"]))


class PrestadoresDataScout:
    """Current Intendencia de Prestadores statistical bulletin inventory."""

    SOURCE_SLUG = "prestadores_data"
    SOURCE_NAME = "Superintendencia de Salud · Intendencia de Prestadores"
    SOURCE_TYPE = "official"
    PAGE = "https://www.superdesalud.gob.cl/tax-observatorio-de-calidad-en-salud/boletines-estadisticos-7994/"

    def discover_from_html(self, html):
        parser = _Links()
        parser.feed(html)
        out = []
        seen = set()
        for href, title in parser.links:
            if not href or "2026" not in title:
                continue
            low = title.lower()
            family = next((x for x in ("acreditación", "mediación", "reclamos", "rnpi", "registro") if x in low), None)
            if not family:
                continue
            url = urljoin(self.PAGE, href)
            parsed = urlparse(url)
            if parsed.netloc not in ("www.superdesalud.gob.cl", "superdesalud.gob.cl"):
                continue
            if not parsed.path.lower().endswith(".pdf") or url in seen:
                continue
            seen.add(url)
            out.append(RawItem(
                self.SOURCE_SLUG,
                re.sub(r"\s+", " ", title).strip(),
                url,
                self.SOURCE_NAME,
                self.SOURCE_TYPE,
                metadata={
                    "discovered_from": self.PAGE,
                    "data_family": family,
                    "data_period": "enero-junio 2026" if ("n°2-2026" in low or "n2-2026" in low or "junio 2026" in low) else "2026",
                    "publication_date_status": "not_exactly_exposed_on_listing",
                    "source_quality_gate": "passed_data",
                },
            ))
        if not out:
            raise RuntimeError("Prestadores statistical bulletin structure unrecognized")
        return out[:12]

    def discover(self):
        return self.discover_from_html(fetch_html(self.PAGE))


_PROVIDER_TERMS = (
    "adquiere", "adquisición", "compra", "control", "inversión", "invierte", "expansión", "expande",
    "inaugura", "nuevo centro", "nueva clínica", "nueva clinica", "camas", "pabellones", "capacidad",
    "convenio", "alianza", "fonasa", "isapre", "lista de espera", "listas de espera", "mcc",
    "modalidad de cobertura complementaria", "operativo", "prestaciones",
)
_MUTUAL_TERMS = (
    "accidentabilidad", "accidentes", "enfermedad profesional", "salud mental", "riesgo psicosocial",
    "riesgos psicosociales", "seguro laboral", "prevención", "prevencion", "adherente", "adherentes",
    "centro de salud", "clínica", "clinica", "inversión", "convenio", "protocolo", "ley karin",
    "seguridad y salud", "vigilancia", "fiscalización",
)
_MEDIA_TERMS = _PROVIDER_TERMS + (
    "utilidad", "pérdida", "perdida", "capital", "bonos", "financiamiento", "fusión", "fusion",
    "participación", "participacion", "licitación", "licitacion", "tarifa", "precio", "planes",
    "cotizantes", "beneficiarios", "licencias médicas", "licencias medicas", "regulación", "regulacion",
)
_NOISE = (
    "seminario", "feria de bienestar", "premio", "reconoc", "conmemor", "campeonato", "charla",
    "semana de la", "día de la", "dia de la", "testimonio", "historia de superación",
)


def _material(role, title, body):
    text = f"{title} {body}".lower()
    if any(x in text for x in _NOISE) and not any(x in text for x in ("inversión", "fonasa", "isapre", "adquiere", "capital", "lista de espera")):
        return False
    terms = _MEDIA_TERMS if role == "media" else _MUTUAL_TERMS if role == "mutuality" else _PROVIDER_TERMS
    if role == "provider_achs" and "clínicas achs salud" not in text and "clinicas achs salud" not in text:
        return False
    return any(x in text for x in terms)


def process_curated_beta_source(raw, cfg):
    from .llm_analysis import analyze_news
    from .pipeline import build_signal
    from .processing import DeferredProcessing
    from .public_source_pipeline import enrich, _scopes

    from .occupational_sources import SOURCES, materiality, valid_date
    scoped = raw.source_slug in SOURCES
    if scoped and raw.metadata.get("article_extraction") != "occupational_v1":
        raise DeferredProcessing("occupational detail requires verified article extraction")
    if scoped and (raw.event_date != raw.metadata.get("publication_date") or
                   not raw.metadata.get("date_evidence")):
        raise DeferredProcessing("occupational publication date evidence mismatch")
    if scoped:
        parsed = urlparse(raw.url)
        hosts = CuratedBetaSourceScout.SOURCES[raw.source_slug]["hosts"]
        evidence = raw.metadata.get("publication_evidence") or raw.metadata.get("publication_date_evidence") or {}
        kinds = {"article:published_time", "datePublished", "publishdate", "time.published@datetime",
                 "publisher:achs_div_fecha", "publisher:publication_container", "publisher:mutual_div_fecha", "publisher:mutual_detail_fecha"}
        if (parsed.scheme != "https" or parsed.hostname not in hosts or parsed.username or parsed.password
                or parsed.port not in (None, 443)):
            raise DeferredProcessing("occupational official article authority unverified")
        bound = isinstance(evidence, dict) and evidence.get("kind") in kinds and evidence.get("url") == raw.url
        if isinstance(evidence, dict) and evidence.get("kind") == "publisher:mutual_card_fecha":
            listing = urlparse(evidence.get("url", ""))
            bound = (raw.source_slug == "mutual_seguridad" and evidence.get("item_url") == raw.url
                     and listing.scheme == "https" and listing.hostname in hosts
                     and not listing.username and not listing.password and listing.port in (None, 443)
                     and listing.path.startswith("/portal/publico/empresa/home/nuestra-mutual/noticias")
                     and all(re.fullmatch(r"[0-9a-f]{64}", str(evidence.get(k, "")))
                             for k in ("listing_sha256", "detail_sha256")))
        if (not bound or evidence.get("date") != raw.event_date
                or valid_date(evidence.get("value")) != raw.event_date or valid_date(raw.event_date) != raw.event_date):
            raise DeferredProcessing("occupational explicit publication evidence unverified")
        from .occupational_evidence import verify_capture
        verify_capture(raw, hosts)
    if not scoped:
        raw = enrich(raw)
    body = raw.metadata.get("page_text") or raw.raw_text or ""
    role = raw.metadata.get("market_role") or "provider"
    accepted = materiality(role, raw.title, body)[0] if scoped else _material(role, raw.title, body)
    if not raw.event_date or len(body) < 160 or not accepted:
        if scoped:
            raw.metadata["publication_rejection_reason"] = materiality(role, raw.title, body)[1]
        return None
    kind = {
        "media": "prensa económica de alta confianza; señal temprana, atribuir y no convertir reporte de prensa en hecho oficial",
        "mutuality": "publicación institucional de mutualidad; filtrar marketing y priorizar cambios operacionales o de salud laboral",
        "provider_achs": "publicación institucional de prestador; priorizar capacidad, convenios, expansión y relación público-privada",
        "provider_achs_centers": "publicación de centros clínicos Achs Salud; no atribuir sus cambios a las clínicas ni al seguro laboral",
        "provider": "publicación institucional de prestador; priorizar capacidad, convenios, expansión, inversión y M&A",
    }.get(role, "publicación sectorial")
    ai = analyze_news(title=raw.title, text=body[:10000], source_name=raw.source_name, kind=kind)
    if not ai:
        raise DeferredProcessing("curated beta source pending assessment")
    score = int(ai.get("relevance_score", 0))
    if scoped:
        raw.metadata["editorial_assessment"] = {"score": score, "reason": ai.get("reason"), "threshold": 75}
    threshold = 72 if role == "media" else 75
    what = (ai.get("what_happened") or "").strip()
    why = (ai.get("why_it_matters") or "").strip()
    if score < threshold or len(what) < 45 or len(why) < 35:
        if scoped:
            raw.metadata["publication_rejection_reason"] = "editorial_score_or_summary_below_threshold"
        return None
    scopes = ["Salud laboral"] if role == "mutuality" else (["Isapres", "Prestadores"] if role == "media" else ["Prestadores"])
    inferred = _scopes(f"{raw.title} {body[:2500]}")
    for scope in inferred:
        if scope != "Sistema de salud" and scope not in scopes:
            scopes.append(scope)
    raw.metadata.update({
        "what_happened": what,
        "why_it_matters": why,
        "signal_types": ["Noticias"],
        "scopes": scopes,
        "watch_tags": [raw.source_slug, role] + [x.lower() for x in scopes],
        "scores": {
            "economic": min(95, max(60, score)),
            "regulatory": 55 if role in ("media", "mutuality") else 30,
            "scope": max(70, score),
            "novelty": score,
            "actionability": 76,
        },
    })
    row = build_signal(raw, cfg).to_dict()
    row["signal_types"] = ["Noticias"]
    row["scopes"] = scopes
    row["editorial_relevance"] = score
    row["source_quality_gate"] = "passed"
    if scoped:
        row.update(market_role=role, publication_date=raw.event_date,
                   date_evidence=raw.metadata["date_evidence"],
                   publication_evidence=raw.metadata.get("publication_evidence") or raw.metadata.get("publication_date_evidence"),
                   capture_evidence=raw.metadata.get("capture_evidence"),
                   materiality_reason=raw.metadata["materiality_reason"],
                   source_quality_gate=raw.metadata["source_quality_gate"])
    if role == "media":
        row["evidence_maturity"] = "media_reported"
        row["confirmation_policy"] = "upgrade_same_signal_when_company_or_official_source_confirms"
    return row


def process_prestadores_data(raw, cfg):
    """Validate bulletin accessibility and structure without inventing a publication date.

    The beta uses this channel as structured-data coverage. Exact publication date is
    required before promotion to the public feed.
    """
    from .document_intelligence import extract_pdf_text
    text = extract_pdf_text(raw.url, max_pages=3)
    if not text or len(text) < 250 or "Intendencia de Prestadores" not in text:
        raise RuntimeError("Prestadores bulletin unreadable")
    raw.metadata["validated_document"] = True
    return None


def media_gate_accepts(title, body=""):
    return _material("media", title, body)
