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
        self.discovery_errors = []
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
                provenance = "legacy_detail_date"
                if self.cfg['role'].startswith('provider'):
                    from .public_source_pipeline import _VisibleArticle
                    article=_VisibleArticle();article.feed(detail)
                    body=' '.join(article.text)
                    stamp = _ProviderPublication(url);stamp.feed(detail)
                    published, provenance = stamp.publication()
                else:
                    published = _date(meta.published) or _date(body[:6500]) or _date(listing_title)
                if not published or date.fromisoformat(published) > date.today():
                    self.discovery_errors.append(f"{url}: publication_date_unverified")
                    continue
                title = meta.ogtitle or listing_title
                title = re.sub(r"\s+", " ", title).strip()
                if len(title) < 18:
                    continue
            except Exception as exc:
                self.discovery_errors.append(f"{url}: {type(exc).__name__}")
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
                    "publication_date_source": provenance,
                },
            ))
        if not out:
            raise RuntimeError(f"{self.cfg['name']} has no dated, verified detail items: "+"; ".join(self.discovery_errors))
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
        if self.slug!='andes_salud':return self.discover_from_html(fetch_html(self.cfg["page"]))
        # The official post API exposes the full published 90-day archive,
        # including Frutillar, which is absent from the nine-card landing page.
        # Each candidate still resolves to its own H1/publication header.
        import json
        from datetime import timedelta
        from html import escape
        cached={}
        def detail(url):
            if url not in cached:cached[url]=fetch_html(url)
            return cached[url]
        all_items={};errors=[]
        try:
            for raw in self.discover_from_html(fetch_html(self.cfg['page']),detail):all_items[raw.url.rstrip('/')]=raw
            errors.extend(self.discovery_errors)
        except Exception as exc:errors.append('landing: '+type(exc).__name__)
        cutoff=date.today()-timedelta(days=90)
        for number in range(1,6):
            api=f'https://www.andessalud.cl/wp-json/wp/v2/posts?after={cutoff}T00:00:00&before={date.today()+timedelta(days=1)}T00:00:00&per_page=100&page={number}'
            try:
                posts=json.loads(fetch_html(api))
                if not isinstance(posts,list):raise ValueError('published posts array missing')
                by_url={post['link'].rstrip('/'):post for post in posts if post.get('status')=='publish' and post.get('link')}
                markup=''.join(f'<a href="{escape(url,quote=True)}">{escape(re.sub("<[^>]+>"," ",post.get("title",{}).get("rendered", "")))}</a>' for url,post in by_url.items())
                if markup:
                    raws=self.discover_from_html(markup,detail);errors.extend(self.discovery_errors)
                    for raw in raws:
                        post=by_url[raw.url.rstrip('/')]
                        if str(post.get('date') or '')[:10]!=raw.event_date:
                            errors.append(raw.url+': cms/header publication mismatch');continue
                        raw.metadata.update(discovered_from_api=api,cms_post_id=post.get('id'),
                                            cms_publication_date=str(post['date'])[:10])
                        all_items[raw.url.rstrip('/')]=raw
                    # These two public campaign pages were inspected in the
                    # original 90-day audit. They add no independent signal.
                    # Match the exact URL, title and release date: changed or
                    # unknown CMS paths still retain partial-discovery errors.
                    reviewed_campaigns={
                        'https://www.andessalud.cl/destacamos/campana-me-chequeare':('Campaña: Me Chequearé','2026-10-05'),
                        'https://www.andessalud.cl/destacamos/campana-clinica-andes-salud-talca':('Campaña: Clínica Andes Salud Talca','2026-09-09'),
                    }
                    excluded={url for url,post in by_url.items() if url in reviewed_campaigns
                        and (post.get('title',{}).get('rendered'),str(post.get('date') or '')[:10])==reviewed_campaigns[url]}
                    skipped=set(by_url)-{raw.url.rstrip('/') for raw in raws}-excluded
                    if skipped:errors.extend(url+': CMS item outside reviewed path or detail verification failed' for url in sorted(skipped))
                if len(posts)<100:break
                if number==5:errors.append('CMS archive page bound reached')
            except Exception as exc:
                errors.append(api+': '+type(exc).__name__);break
        self.discovery_errors=errors
        if not all_items:raise RuntimeError('Andes Salud original discovery failed: '+'; '.join(errors))
        return sorted(all_items.values(),key=lambda raw:raw.event_date or '',reverse=True)


class _ProviderPublication(HTMLParser):
    """Only explicit publication metadata or the isolated article-header stamp.

    Dávila places 'Novedades dd/mm/yyyy' before H1. Andes and Achs place a
    standalone stamp immediately after H1. Body and related-item dates cannot
    supply a missing publication date.
    """
    def __init__(self,url=None):
        super().__init__();self.meta=None;self.header=None;self._before=[];self._h1=False;self._after=False;self._seen_title=False
        self.url=url
        from .public_source_pipeline import _RedSaludArticle
        self._article=_RedSaludArticle(url) if url else None
    def feed(self,data):
        super().feed(data)
        if self._article:self._article.feed(data)
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs);tag=tag.lower()
        if tag=='meta' and (attrs.get('property') or attrs.get('name') or '').lower() in ('article:published_time','datepublished'):
            self.meta=attrs.get('content')
        elif tag=='h1' and not self._seen_title:
            from .public_source_pipeline import _date
            match=re.search(r'(?:Novedades|Operativos Médicos)\s+(\d{1,2}/\d{1,2}/20\d{2})\s*$', ' '.join(self._before)[-180:])
            if match:self.header=_date(match.group(1))
            self._h1=True;self._seen_title=True
        elif self._after and tag in ('p','h2','h3','nav','footer','aside'):
            self._after=False
    def handle_endtag(self, tag):
        if tag.lower()=='h1' and self._h1:self._h1=False;self._after=True
    def handle_data(self, data):
        text=' '.join(data.split())
        if not text:return
        if self._after:
            from .public_source_pipeline import _date
            if re.fullmatch(r'(?:\d{1,2}/\d{1,2}/20\d{2}|[A-Za-zÁÉÍÓÚáéíóúñÑ]+ \d{1,2}, 20\d{2})',text):
                self.header=_date(text)
            self._after=False
        elif not self._h1:self._before.append(text)
    def publication(self):
        from .public_source_pipeline import _date
        meta=_date(self.meta)
        if self._article:
            self._article.finish()
            def identity(item):
                value=item.get('url') or item.get('mainEntityOfPage') or item.get('@id')
                if isinstance(value,dict):value=value.get('@id') or value.get('url')
                return urljoin(self.url,str(value)).split('#')[0].rstrip('/') if value else None
            own=any(identity(item)==self.url.split('#')[0].rstrip('/') for item in self._article.schemas)
            schema=_date(self._article.published) if own else None
            if schema and ((meta and meta!=schema) or (self.header and self.header!=schema)):return None,'conflicting_stamps'
            if schema and not meta and not self.header:return schema,'url_associated_jsonld_datePublished'
        if meta and self.header and meta!=self.header:return None,'conflicting_stamps'
        return (meta,'article:published_time') if meta else (self.header,'verified_article_header' if self.header else 'unverified')


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

    from .occupational_sources import SOURCES, materiality, valid_date, classify_content_kind, chile_today
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
    role = raw.metadata.get("market_role") or "provider"
    from .provider_assessment import assessed, prefilter_rejected
    if not scoped:
        if role.startswith('provider'):
            gate=raw.metadata.get('source_quality_gate')
            if gate and gate!='passed':
                raise DeferredProcessing(f'Provider source quality gate not passed: {gate}')
            if (not raw.event_date or raw.metadata.get('publication_date_source')
                    not in ('article:published_time','verified_article_header','url_associated_jsonld_datePublished')):
                raise DeferredProcessing('Provider publication date unverified')
            from .processing import OutsideBackfillHorizon
            published=date.fromisoformat(raw.event_date)
            if published>date.today():raise DeferredProcessing('Provider future publication date')
            if (date.today()-published).days>90:raise OutsideBackfillHorizon(raw.event_date)
        if role.startswith('provider'):
            from .public_source_pipeline import _VisibleArticle
            try:
                from .provider_original_reader import read_provider_detail
                detail=read_provider_detail(raw.url,fetch_html)
            except Exception as exc:raise DeferredProcessing(f'Provider detail unavailable: {raw.url}: {type(exc).__name__}') from exc
            stamp=_ProviderPublication(raw.url);stamp.feed(detail)
            verified,_=stamp.publication()
            if verified!=raw.event_date:raise DeferredProcessing(f'Provider listing/detail publication date mismatch: {raw.url}')
            article=_VisibleArticle();article.feed(detail)
            if not article.title or (raw.title.casefold() not in article.title.casefold() and article.title.casefold() not in raw.title.casefold()):
                raise DeferredProcessing(f'Provider listing/detail headline mismatch: {raw.url}')
            raw.metadata['page_text']=' '.join(article.text)[:18000]
            raw.raw_text=raw.metadata['page_text'][:1800]
        else:raw = enrich(raw)
        if raw.metadata.get("fetch_error"):
            raise DeferredProcessing(f"Provider detail unavailable: {raw.url}: {raw.metadata['fetch_error']}")
    primary_body = raw.metadata.get("page_text") or raw.raw_text or ""
    body, document_facts = primary_body, ""
    if scoped:
        from .occupational_documents import verified_document_text, additional_document_facts, documentary_materiality
        verified_document = verified_document_text(raw, hosts)
        document_facts = additional_document_facts(primary_body, verified_document)
        if document_facts:
            body += "\n" + document_facts
    role = raw.metadata.get("market_role") or "provider"
    if scoped:
        accepted, material_reason = documentary_materiality(raw, body, verified_document)
        if (raw.metadata.get("supporting_documents_required") and not accepted
                and any(document.get("truncated") for document in raw.metadata.get("supporting_documents", []))):
            raise DeferredProcessing("required_document_materiality_unresolved_bounded_extraction")
        raw.metadata.update(materiality_accepted=accepted, materiality_reason=material_reason,
                            content_kind=classify_content_kind(material_reason, raw.title, primary_body))
    else:
        accepted = _material(role, raw.title, body)
    if not raw.event_date or len(body) < 160 or not accepted:
        if scoped:
            raw.metadata["publication_rejection_reason"] = material_reason
        else:
            prefilter_rejected(raw,"publication_date_missing" if not raw.event_date else "insufficient_readable_body" if len(body)<160 else "no_material_change_under_provider_prefilter")
        return None
    supporting=[]
    for evidence in (raw.metadata.get('supporting_official_sources') or [])[:1]:
        target=urlparse(evidence.get('url') or '')
        source=CuratedBetaSourceScout.SOURCES.get(raw.source_slug,{})
        if (target.scheme!='https' or target.netloc not in source.get('hosts',())
                or not re.fullmatch(source.get('path',r'(?!)'),target.path)
                or evidence.get('relationship')!='programme_announcement_before_execution'):
            raise DeferredProcessing('Supporting provider evidence identity unverified')
        try:
            page=fetch_html(evidence['url']);stamp=_ProviderPublication(evidence['url']);stamp.feed(page)
            article=_VisibleArticle();article.feed(page)
        except Exception as exc:raise DeferredProcessing('Supporting provider original unavailable') from exc
        verified,_=stamp.publication()
        if (verified!=evidence.get('publication_date') or not verified or verified>raw.event_date
                or article.title!=evidence.get('title') or not re.search(r'\bEnlace\b',body)
                or not re.search(r'\bEnlace\b',' '.join(article.text))):
            raise DeferredProcessing('Supporting provider publication/programme mismatch')
        from hashlib import sha256
        supporting_text=' '.join(article.text)
        supporting.append({**evidence,'body_sha256':sha256(supporting_text.encode()).hexdigest()})
        # Same publication gate, richer original evidence: announced commitment
        # and observed execution are explicitly attributed and never summed.
        body=(f'Fuente principal; ejecución publicada {raw.event_date}:\n{body[:3200]}\n'
              f'Fuente oficial relacionada; compromiso anunciado {verified}, {evidence["url"]}:\n{supporting_text[:1800]}')
    if supporting:raw.metadata['supporting_evidence_capture']=supporting
    kind = {
        "media": "prensa económica de alta confianza; señal temprana, atribuir y no convertir reporte de prensa en hecho oficial",
        "mutuality": "publicación institucional de mutualidad; filtrar marketing y priorizar cambios operacionales o de salud laboral",
        "provider_achs": "publicación institucional de prestador; priorizar capacidad, convenios, expansión y relación público-privada",
        "provider_achs_centers": "publicación de centros clínicos Achs Salud; no atribuir sus cambios a las clínicas ni al seguro laboral",
        "provider": "publicación institucional de prestador; priorizar capacidad, convenios, expansión, inversión y M&A",
    }.get(role, "publicación sectorial")
    if scoped:
        kind += (f". Tipo de contenido: {raw.metadata['content_kind']}. Publicación: {raw.event_date}; "
                 f"fecha de revisión Chile: {chile_today().isoformat()}. Puede ingresar por BACKFILL. "
                 "No afirmes que una convocatoria, inscripción o vigencia continúa abierta hoy a partir de una "
                 "publicación histórica: exige fechas explícitas y diferencia publicación, período de datos y plazo operativo.")
        if raw.url == "https://ist.cl/reporte-sostenibilidad-2025/" and document_facts:
            kind += (" El informe corresponde al período 2025. Sus tablas comparan ingresos y egresos ordinarios 2025/2024; "
                     "conserva los encabezados y la categoría ordinarios. No deduzcas déficit ni resultado neto "
                     "mediante su resta. La afirmación sobre ausencia de excedentes debe atribuirse al informe.")
    ai_text = (primary_body[:3500] + "\n\nHechos adicionales del documento oficial verificado:\n" + document_facts
               if document_facts else body[:10000])
    ai = analyze_news(title=raw.title, text=ai_text, source_name=raw.source_name, kind=kind)
    if not ai:
        raise DeferredProcessing("curated beta source pending assessment")
    score = int(ai.get("relevance_score", 0))
    if scoped:
        raw.metadata["editorial_assessment"] = {"score": score, "reason": ai.get("reason"), "threshold": 75}
    threshold = 72 if role == "media" else 75
    what = (ai.get("what_happened") or "").strip()
    why = (ai.get("why_it_matters") or "").strip()
    if (score < threshold or len(what) < 45 or len(why) < 35) if scoped else not assessed(raw,ai,threshold):
        if scoped:
            raw.metadata["publication_rejection_reason"] = "editorial_score_or_summary_below_threshold"
        return None
    scopes = ["Salud laboral"] if role == "mutuality" else (["Isapres", "Prestadores"] if role == "media" else ["Prestadores"])
    scope_text=f"{raw.title} {body[:2500]}"
    named_pharma=(re.search(r'\b(?:pfizer|roche|sanofi|merck|novartis|astrazeneca|bayer|gsk|abbott)\b',scope_text,re.I)
        or re.search(r'\b(?:[Ll]aboratorios?|[Ff]armacias?)\s+(?!(?:[Cc]l[ií]nic[oa]s?|[Cc]entral|[Dd]e|[Dd]el)\b)[A-ZÁÉÍÓÚ][\wÁÉÍÓÚáéíóúñÑ-]+',scope_text))
    if role.startswith('provider') and not named_pharma:
        # A hospital's pharmacy and diagnostic laboratory are clinical capacity.
        # Keep original industry inference for named labs/pharmacy companies.
        scope_text=re.sub(r'\b(?:farmacias?|laboratorios?)\b','servicios clínicos',scope_text,flags=re.I)
    inferred = _scopes(scope_text)
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
    row['editorial_assessment']=raw.metadata['editorial_assessment']
    row["source_quality_gate"] = "passed"
    if scoped:
        row.update(source_slug=raw.source_slug, market_role=role,
                   provider_subtype=raw.metadata.get("provider_subtype"),
                   data_period=raw.metadata.get("data_period"), publication_date=raw.event_date,
                   date_evidence=raw.metadata["date_evidence"],
                   publication_evidence=raw.metadata.get("publication_evidence") or raw.metadata.get("publication_date_evidence"),
                   capture_evidence=raw.metadata.get("capture_evidence"),
                   materiality_reason=raw.metadata["materiality_reason"],
                   content_kind=raw.metadata["content_kind"],
                   supporting_documents=raw.metadata.get("supporting_documents", []),
                   source_quality_gate=raw.metadata["source_quality_gate"])
    if supporting:row['supporting_sources']=supporting
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
