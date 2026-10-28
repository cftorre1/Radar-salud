from __future__ import annotations

import hashlib
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


def coverage_gap_diagnostics(inventory):
    """Explain an incomplete inventory that recorded no per-URL error.

    Mutual's IBM portal paginator can repeat a category page before its cards
    reach the 90-day start (Dirección 27-oct-2026: a clean stop, not an
    inventory error). Coverage is still incomplete, so name each stalled
    branch instead of reporting a bare listing URL.
    """
    rows = [{"code": "pagination_stalled_before_90_day_cutoff", "url": note.get("url"),
             "branch": note.get("branch"),
             "oldest_verified_listing_date": note.get("oldest_verified_listing_date"),
             "detail": "publisher paginator repeated the page before reaching the 90-day start"}
            for note in inventory.get("pagination_notes") or []
            if note.get("code") == "repeated_pagination_page_stop" and not note.get("reached_90_day_cutoff")]
    if not rows:
        rows = [{"code": "inventory_capture_incomplete", "url": None,
                 "detail": "coverage incomplete: " + str(inventory.get("stop_reason"))}]
    return rows


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
            "path": r"/(?:pulso|nacional)/noticia/[^/]+(?:/[A-Za-z0-9]{26})?/?",
            "role": "media",
        },
    }

    def __init__(self, slug):
        if slug not in self.SOURCES:
            raise ValueError("source has not passed beta Source Quality Gate")
        self.slug = slug
        self.cfg = self.SOURCES[slug]
        self.discovery_audit = []

    def discover_from_html(self, html, detail_loader=None):
        detail_loader = detail_loader or fetch_html
        if self.slug == "pulso_latercera":
            from .pulso_source import discover_listing
            audit = self.discovery_audit = []
            out = discover_listing(html, self.cfg["page"], detail_loader, audit, set())
            if not out:
                raise RuntimeError("Pulso / La Tercera has no verified, dated health articles: " + str(audit))
            return sorted(out, key=lambda item: item.event_date, reverse=True)
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
        if self.slug == "pulso_latercera":
            from .pulso_source import discover_pulso
            self.discovery_audit = []
            return discover_pulso(audit=self.discovery_audit)
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
                if not errors:
                    errors = self.inventory["coverage_gaps"] = coverage_gap_diagnostics(self.inventory)
                codes = {error.get("code") or error.get("reason") for error in errors}
                # One shared cause names the failure; mixed causes stay generic
                # and every per-URL/branch diagnostic is kept either way.
                code = (codes.pop() if len(codes) == 1 and None not in codes
                        else "inventory_capture_incomplete")
                exc = SourceDiscoveryError(code, (errors[0].get("url") if errors else None) or self.cfg["page"])
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
    "presupuesto", "deuda", "fuerza de ventas", "estructura organizacional", "suspensión de operaciones",
    "suspende operaciones", "cierre", "traslado de pacientes", "residencias para adultos mayores",
    "reforma", "norma", "acreditación", "acreditacion", "auditor", "fiscaliza",
    "certificación", "certificacion", "recorte", "trasplante", "ficha clínica", "ficha clinica",
    "vacunación", "vacunacion", "alerta", "oncol", "aseguramiento", "cenabast",
)
_NOISE = (
    "seminario", "feria de bienestar", "premio", "reconoc", "conmemor", "campeonato", "charla",
    "semana de la", "día de la", "dia de la", "testimonio", "historia de superación",
)


def _material(role, title, body):
    text = f"{title} {body}".lower()
    if role == "media":
        from .pulso_source import health_anchor
        if not health_anchor(text):
            return False
    consequential = ("inversión", "fonasa", "isapre", "adquiere", "capital", "lista de espera",
                     "cierre", "suspende", "suspensión", "traslado", "recorte", "presupuesto",
                     "reforma", "norma", "auditor", "fiscaliza", "capacidad", "trasplante", "financiamiento")
    noise_text = title.lower() if role == "media" else text
    exceptions = consequential if role == "media" else ("inversión", "fonasa", "isapre", "adquiere", "capital", "lista de espera")
    if any(x in noise_text for x in _NOISE) and not any(x in text for x in exceptions):
        return False
    terms = _MEDIA_TERMS if role == "media" else _MUTUAL_TERMS if role == "mutuality" else _PROVIDER_TERMS
    if role == "provider_achs" and "clínicas achs salud" not in text and "clinicas achs salud" not in text:
        return False
    if any(x in text for x in terms):
        return True
    if role == "media":
        # Primary reports of care-network obligations and GES coverage changes
        # must reach editorial analysis even without a finance/provider keyword.
        # These matches only permit analysis; relevance/publication gates follow.
        care_obligation = "uso obligatorio" in text and bool(re.search(
            r"servicios? de urgencia|unidades? de di[aá]lisis|oncohematolog|"
            r"red p[uú]blica(?: y privada)?|red privada", text))
        ges_coverage = bool(re.search(r"\bges\b|garant[ií]as? expl[ií]citas? de salud", text)) and bool(
            re.search(r"\bcobertura\b|incorpor", text))
        care_legislation = bool(re.search(r"c[oó]digo sanitario", text)) and bool(
            re.search(r"proyecto|modific|tramit", text)) and bool(re.search(
                r"\bprestaci[oó]n\b|atenci[oó]n|interrupci[oó]n(?: voluntaria)? del embarazo", text))
        proposed_clinical_condition = bool(re.search(r"escucha su coraz[oó]n", text)) and bool(
            re.search(r"proyecto|propuesta|iniciativa", text)) and bool(re.search(
                r"aborto|abortar|interrupci[oó]n (?:legal |voluntaria )?del embarazo|ley de tres causales", text)) and bool(
            re.search(r"mujeres?[^.!?]{0,100}\bdeban escuchar\b[^.!?]{0,100}\blatidos?\b|"
                      r"m[eé]dico[^.!?]{0,120}\bnegarse a (?:realizar|practicar)\b[^.!?]{0,50}(?:procedimiento|interrupci[oó]n)|"
                      r"\bcondicion(?:ando|a|ar)[^.!?]{0,70}(?:realizaci[oó]n|prestaci[oó]n)[^.!?]{0,70}"
                      r"(?:procedimiento|interrupci[oó]n)[^.!?]{0,70}(?:aceptaci[oó]n|escuchar)", text))
        provider_flood_response = bool(re.search(
            r"\b(?:cl[ií]nica|hospital)\b[^.!?]{0,100}\binundad[oa]s?\b", text)) and bool(
            re.search(r"ministerio de salud|\bminsal\b|autoridad sanitaria", text)) and bool(
            re.search(r"monitore|protecci[oó]n de los pacientes|resguard", text))
        authorized_care_registry = all(re.search(pattern, text) for pattern in (
            r"\beleam\b|establecimientos? de larga estad[ií]a",
            r"\bminsal\b|ministerio de salud|autoridad sanitaria",
            r"autorizaci[oó]n sanitaria", r"\bn[oó]mina\b|\blistado\b|\bregistro\b|\blista\b|\bcatastro\b",
            r"disponible p[uú]blicamente|listado publicado esta jornada|lista ser[aá] actualizada semanalmente|"
            r"public(?:a|ó|ado|ada|ar)\b[^.!?]{0,90}(?:n[oó]mina|listado|registro|catastro)"))
        clinical_service_suspension = bool(re.search(r"\bcl[ií]nica\b|\bhospital\b|red de salud", text)) and bool(
            re.search(r"\bsuspend(?:e|er[aá]|id[oa]|ieron|emos)\b[^.!?]{0,100}\batenci[oó]n\b[^.!?]{0,100}"
                      r"(?:urgencias?|consultas? m[eé]dicas|procedimientos? ambulatorios?)", text))
        quantified_health_power_impact = ("electrodependientes" in text and bool(re.search(
            r"\bcentros de salud\b[^!?]{0,120}\bafectados\b[^!?]{0,60}\b\d+", text)) and bool(re.search(
            r"cortes? de (?:suministro(?: el[eé]ctrico)?|electricidad)|sin suministro el[eé]ctrico", text)))
        modular_care_deployment = ("hospital modular" in text and bool(re.search(
            r"\btraslad[oa]|\bimplementaci[oó]n\b", text)) and bool(re.search(r"reforzar|apoyar", text))
            and "atención de salud" in text)
        mapped_multi_provider_flood = (bool(re.search(r"cl[ií]nicas inundadas", text))
            and "recintos asistenciales afectados" in text and "carabineros" in text
            and bool(re.search(r"dron|monitoreo", text)))
        reproductive_legislative_progress = (bool(re.search(r"comisi[oó]n de salud", text))
            and bool(re.search(r"inici[oó] la discusi[oó]n del proyecto de ley", text))
            and "gestación subrogada" in text)
        medical_insurance_inquiry = ("dipreca" in text and bool(re.search(
            r"cirug[ií]as (?:est[eé]ticas|reconstructivas)", text)) and bool(re.search(
            r"investigaci[oó]n en curso|\bsumario\b", text)) and bool(re.search(r"cubiertas|cobertura", text)))
        provider_judicial_liability = ("hospital" in text and "servicio de salud" in text
            and "corte de apelaciones" in text and bool(re.search(r"conden[oó][^!?]{0,160}\bpagar\b", text))
            and "indemnización" in text and "falta de servicio" in text)
        essential_care_transport_blocked = ("necesitaban dializarse" in text
            and bool(re.search(r"aislad[oa]s?|bloquead[oa]s?", text))
            and "no permitía que los helicópteros pudiesen volar para evacuarlos" in text)
        compulsory_respiratory_health_measure = ("uso obligatorio de mascarilla" in text
            and "autoridad sanitaria" in text and "resolución exenta" in text
            and bool(re.search(r"prev(?:enir|enci[oó]n)[^.!?]{0,80}enfermedades respiratorias", text)))
        damaged_hospital_emergency_funds = (bool(re.search(r"ley n[°º]?\s*16\.282", text))
            and "diario oficial" in text and "fondos de emergencia" in text
            and "hospitales con daños en la infraestructura" in text)
        minors_mental_health_legislative_urgency = ("salud mental" in text
            and bool(re.search(r"ni[ñn]os|menores", text)) and "sumo urgencia al proyecto de ley" in text
            and "primer trámite constitucional" in text)
        national_health_cost_access_measurement = ("encuesta" in text
            and "casos a nivel nacional representativos" in text and "gastos de salud y cuidados" in text
            and "barrera de acceso es el costo" in text and "psicólogo o psiquiatra" in text)
        territorial_toxic_exposure_health_order = ("suspensión de clases" in text
            and "seremi de salud" in text and "toxicidad del humo" in text
            and bool(re.search(r"todos los (?:colegios|establecimientos) de la comuna", text)))
        institutional_food_health_investigation = ("junaeb" in text and "fiscal" in text
            and "delitos contra la salud pública" in text and "distribución de comida contaminada" in text
            and "incautación" in text)
        return (care_obligation or ges_coverage or care_legislation
                or proposed_clinical_condition or provider_flood_response
                or authorized_care_registry or clinical_service_suspension
                or quantified_health_power_impact or modular_care_deployment or mapped_multi_provider_flood
                or reproductive_legislative_progress or medical_insurance_inquiry or provider_judicial_liability
                or essential_care_transport_blocked or compulsory_respiratory_health_measure
                or damaged_hospital_emergency_funds or minors_mental_health_legislative_urgency
                or national_health_cost_access_measurement or territorial_toxic_exposure_health_order
                or institutional_food_health_investigation)
    return False


def _attribute_pulso_what(what):
    """Attribute a dated generic note at its start, preserving the Model copy."""
    if not what:
        return what
    publisher = r"pulso|la tercera"
    generic_note_intro = re.match(r"^seg[uú]n\s+la\s+nota\b", what, re.I)
    named_intro = re.search(publisher, what.split(",", 1)[0], re.I)
    if re.search(publisher, what, re.I) and (not generic_note_intro or named_intro):
        return what
    return f"Según Pulso / La Tercera, {what}"


def process_curated_beta_source(raw, cfg):
    from .llm_analysis import analyze_news, news_analysis_input
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
                 "publisher:achs_div_fecha", "publisher:publication_container", "publisher:mutual_div_fecha", "publisher:mutual_detail_fecha",
                 "publisher:visible_header_date"}
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
        from .occupational_evidence import verify_capture, same_run_loader
        # Daily-cycle evidence standard (Dirección 27-oct-2026): a capture
        # verified in this run replaces the manual recovery artifact.
        verify_capture(raw, hosts, loader=same_run_loader)
    role = raw.metadata.get("market_role") or "provider"
    from .provider_assessment import assessed, prefilter_rejected
    if raw.source_slug == "pulso_latercera":
        from .pulso_source import (ConflictingPublicationArticle, ExcludedArticle,
                                   SponsoredArticle, TextUnavailableArticle,
                                   article_body_evidence, article_url, complete_article_body,
                                   extract_article, liveblog_analysis_text, liveblog_requires_revalidation,
                                   publisher_taxonomy_requires_revalidation, verified_liveblog_temporal_evidence,
                                   verified_publication_date_conflict, verified_sponsored_content,
                                   verified_sponsored_without_text, verified_video_without_text)

        def defer_verified_publisher_limitation():
            if article_url(raw.url) != raw.metadata.get("canonical_url"):
                return
            reason = None
            if verified_publication_date_conflict(raw.metadata) and raw.event_date is None:
                # Preserve both primary days; no retry or model can choose one.
                reason = "publisher_conflicting_publication_dates"
            elif raw.event_date and raw.event_date == raw.metadata.get("publication_date"):
                if verified_video_without_text(raw.metadata):
                    reason = "publisher_video_text_unavailable"
                elif verified_sponsored_content(raw.metadata):
                    reason = "publisher_sponsored_content_review_required"
                elif verified_sponsored_without_text(raw.metadata):
                    reason = "publisher_sponsored_text_unavailable"
            if reason:
                raw.metadata["editorial_assessment"] = {"decision": "pending", "reason": reason}
                raise DeferredProcessing(reason)

        defer_verified_publisher_limitation()
        sponsor_flag = (raw.metadata.get("publisher_content_classification") == "sponsored"
                        or raw.metadata.get("publisher_exception_reason") == "publisher_sponsored_content_review_required")
        taxonomy = raw.metadata.get("publisher_taxonomy", {})
        opinion_flag = isinstance(taxonomy, dict) and taxonomy.get("classification") == "opinion"
        # The earlier video parser hashed its wrapper as if it were a complete
        # article. A matching legacy hash cannot establish a transcript.
        legacy_video = (urlparse(raw.url).path.startswith("/videos/")
                        and raw.metadata.get("video_identity_verified") is not True)
        if (sponsor_flag or opinion_flag or legacy_video or publisher_taxonomy_requires_revalidation(raw.metadata)
                or liveblog_requires_revalidation(raw.metadata)
                or not (raw.metadata.get("article_verified") and complete_article_body(raw.metadata) and raw.event_date)):
            try:
                from datetime import datetime, timezone
                html = fetch_html(raw.url)
                def save_primary(title, body, evidence, quality):
                    raw.title, raw.event_date, raw.raw_text = title, evidence["publication_date"], body[:1800]
                    taxonomy = evidence.get("publisher_taxonomy", {})
                    if isinstance(taxonomy, dict) and taxonomy.get("classification") in {"factual", "opinion", "sponsored"}:
                        # A fresh primary classification replaces old publisher
                        # exceptions, while reviewed duplicate holds remain.
                        publisher_reasons = {"publisher_conflicting_publication_dates", "publisher_video_text_unavailable",
                                             "publisher_sponsored_content_review_required", "publisher_opinion_taxonomy",
                                             "publisher_liveblog_entry_dates_unverified", "publisher_sponsored_text_unavailable"}
                        for key in ("publisher_exception_reason", "source_content_unavailable_reason",
                                    "publisher_exclusion_reason", "editorial_hold"):
                            if key not in evidence and raw.metadata.get(key) in publisher_reasons:
                                raw.metadata.pop(key)
                    if raw.metadata.get("publisher_document_type") == "liveblog" and evidence.get("publisher_document_type") != "liveblog":
                        for key in ("publisher_document_type", "liveblog_temporal_evidence", "liveblog_temporal_evidence_verified"):
                            raw.metadata.pop(key, None)
                    raw.metadata.update(evidence, **article_body_evidence(body), market_role="media",
                                        source_quality_gate=quality,
                                        html_sha256=hashlib.sha256(html.encode("utf-8")).hexdigest(),
                                        captured_at=datetime.now(timezone.utc).isoformat())
                try:
                    title, body, evidence = extract_article(html, raw.url)
                except (ConflictingPublicationArticle, TextUnavailableArticle, SponsoredArticle, ExcludedArticle) as exc:
                    quality = ("deferred_publication_date" if isinstance(exc, ConflictingPublicationArticle) else
                               ("deferred_sponsored_text" if str(exc) == "publisher_sponsored_text_unavailable"
                                else "deferred_video_text") if isinstance(exc, TextUnavailableArticle) else
                               "deferred_sponsored_content_review" if isinstance(exc, SponsoredArticle) else
                               "excluded_publisher_opinion")
                    save_primary(exc.title, exc.body, exc.metadata, quality)
                    if isinstance(exc, ExcludedArticle):
                        if not (str(exc) in {"publisher_opinion_taxonomy", "excluded_opinion_content"}
                                and article_url(raw.url) == raw.metadata.get("canonical_url")
                                and raw.metadata.get("primary_identity_verified") is True
                                and raw.metadata.get("publication_date_verified") is True
                                and raw.event_date):
                            raise ValueError("unproven_publisher_opinion_exclusion") from exc
                        raw.metadata["article_body_complete"] = complete_article_body(raw.metadata)
                        raw.metadata["rejection_reason"] = str(exc)
                        raw.metadata["editorial_assessment"] = {"decision": "rejected", "reason": str(exc)}
                        return None
                    defer_verified_publisher_limitation()
                    raise ValueError("unproven_publisher_limitation") from exc
                save_primary(title, body, evidence, "passed")
            except DeferredProcessing:
                raise
            except Exception as exc:
                raw.metadata["article_body_complete"] = False
                raw.metadata["editorial_assessment"] = {"decision": "pending", "reason": "article_verification_failed", "error_type": type(exc).__name__}
                raise DeferredProcessing("Pulso article verification failed") from exc
        raw.metadata["article_body_complete"] = True
        if raw.metadata.get("publisher_document_type") == "liveblog" and not verified_liveblog_temporal_evidence(raw.metadata):
            raw.metadata["editorial_assessment"] = {"decision": "pending", "reason": "publisher_liveblog_entry_dates_unverified"}
            raise DeferredProcessing("publisher_liveblog_entry_dates_unverified")
        # Complete publisher evidence must belong to this queue item. Binding
        # the model request to a body does not bind the eventual signal URL/day.
        # Never repair either identity silently from another item's metadata.
        if (article_url(raw.url) != raw.metadata.get("canonical_url")
                or raw.event_date != raw.metadata.get("publication_date")):
            reason = "pulso_primary_item_identity_or_date_mismatch"
            raw.metadata["primary_item_binding"] = {
                "verified": False, "reason": reason, "raw_url": raw.url,
                "normalized_raw_url": article_url(raw.url),
                "primary_canonical_url": raw.metadata.get("canonical_url"),
                "raw_event_date": raw.event_date,
                "primary_publication_date": raw.metadata.get("publication_date"),
                "model_calls_permitted": False,
            }
            raw.metadata["editorial_assessment"] = {"decision": "pending", "reason": reason}
            raise DeferredProcessing(reason)
        flags = {name: raw.metadata.get(name) for name in (
            "primary_identity_verified", "publication_date_verified")}
        if any(value is not True for value in flags.values()):
            reason = "pulso_primary_verification_flags_missing_or_false"
            raw.metadata["primary_item_binding"] = {
                "verified": False, "reason": reason,
                "raw_url": raw.url, "primary_canonical_url": raw.metadata.get("canonical_url"),
                "raw_event_date": raw.event_date,
                "primary_publication_date": raw.metadata.get("publication_date"),
                "primary_verification_flags": flags, "model_calls_permitted": False,
            }
            raw.metadata["editorial_assessment"] = {"decision": "pending", "reason": reason}
            raise DeferredProcessing(reason)
        previous_binding = raw.metadata.get("primary_item_binding")
        if isinstance(previous_binding, dict) and previous_binding.get("verified") is False:
            from copy import deepcopy
            prior = raw.metadata.setdefault("primary_item_binding_prior_deferrals", [])
            if previous_binding not in prior:
                prior.append(deepcopy(previous_binding))
        raw.metadata["primary_item_binding"] = {
            "verified": True, "reason": "pulso_primary_item_identity_and_date_verified",
            "raw_url": raw.url, "primary_canonical_url": raw.metadata["canonical_url"],
            "raw_event_date": raw.event_date,
            "primary_publication_date": raw.metadata["publication_date"],
            "primary_verification_flags": flags,
            "model_calls_permitted": True, "other_editorial_and_budget_gates_still_apply": True,
            "publication_approved": False,
        }
        from .pulso_incremental_review import apply_incremental_review
        apply_incremental_review(raw)
    elif not scoped:
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
    if raw.metadata.get("editorial_hold"):
        raw.metadata["editorial_assessment"] = {"decision": "pending", "reason": raw.metadata["editorial_hold"]}
        raise DeferredProcessing("Pulso pending incremental-value review")
    def reject(reason, **evidence):
        raw.metadata["rejection_reason"] = reason
        raw.metadata["editorial_assessment"] = dict(decision="rejected", reason=reason, **evidence)
        return None
    if scoped:
        accepted, material_reason = documentary_materiality(raw, body, verified_document)
        if (raw.metadata.get("supporting_documents_required") and not accepted
                and any(document.get("truncated") for document in raw.metadata.get("supporting_documents", []))):
            raise DeferredProcessing("required_document_materiality_unresolved_bounded_extraction")
        raw.metadata.update(materiality_accepted=accepted, materiality_reason=material_reason,
                            content_kind=classify_content_kind(material_reason, raw.title, primary_body))
    if raw.source_slug == "pulso_latercera":
        if scoped and (not raw.event_date or len(body) < 160 or not accepted):
            raw.metadata["publication_rejection_reason"] = material_reason
            return None
        if not raw.event_date:
            return reject("missing_publication_date")
        if len(body) < 160:
            return reject("incomplete_article_evidence")
        if not scoped and not _material(role, raw.title, body):
            return reject("media_materiality_prefilter" if role == "media" else "source_materiality_prefilter")
    else:
        if not scoped:
            accepted = _material(role, raw.title, body)
        if not raw.event_date or len(body) < 160 or not accepted:
            if scoped:
                raw.metadata["publication_rejection_reason"] = material_reason
            else:
                prefilter_rejected(raw,"publication_date_missing" if not raw.event_date else "insufficient_readable_body" if len(body)<160 else "no_material_change_under_provider_prefilter")
            return None
    supporting=[]
    for evidence in ([] if raw.source_slug == 'pulso_latercera' else
                     (raw.metadata.get('supporting_official_sources') or [])[:1]):
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
    if role == "media" and raw.metadata.get("editorial_review_context"):
        import json
        kind += (". Revisión previa de valor incremental: "
                 + json.dumps(raw.metadata["editorial_review_context"], ensure_ascii=False)
                 + ". Evalúa si el artículo agrega un cambio material a ese antecedente; "
                   "la revisión sólo habilita análisis y no aprueba publicación. "
                   "Preserva período, métrica, condición de propuesta y atribución de prensa.")
    if raw.source_slug == "pulso_latercera":
        kind += (f". Publicación original: {raw.event_date}; fecha de revisión Chile: {chile_today().isoformat()}. "
                 "Puede ingresar por BACKFILL: describe lo observado o anunciado a la fecha de publicación, "
                 "y conserva el período de datos. Una emergencia entonces en curso, un reglamento entonces "
                 "pendiente o una medida temporal no acredita que ese estado siga vigente en la fecha de revisión. "
                 "Usa atribución temporal explícita y no conviertas el reporte histórico en estado actual.")
        # Keep the source's complete primary text through the model boundary;
        # strategic facts can occur after the general news excerpt limit.
        text = body
        input_format = "full_primary_article_body"
        if raw.metadata.get("publisher_document_type") == "liveblog":
            text = liveblog_analysis_text(raw.metadata)
            input_format = "full_primary_body_with_verified_liveblog_entry_timeline_v1"
            kind += ". Cobertura en vivo: usa las fechas verificadas de cada entrada, separadas de la fecha del documento; conserva condiciones y no sumes balances repetidos."
        request_input = news_analysis_input(title=raw.title, text=text, source_name=raw.source_name, full_text=True)
        raw.metadata.update(analysis_base_article_body_sha256=hashlib.sha256(body.encode("utf-8")).hexdigest(),
                            analysis_base_article_body_characters=len(body), analysis_input_format=input_format,
                            analysis_input_body_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                            analysis_input_characters=len(text), analysis_input_complete=True,
                            analysis_request_input_sha256=hashlib.sha256(request_input.encode("utf-8")).hexdigest(),
                            analysis_request_input_characters=len(request_input))
        if raw.metadata.get("publisher_document_type") == "liveblog":
            raw.metadata["analysis_liveblog_entries_sha256"] = raw.metadata["liveblog_temporal_evidence"]["entries_sha256"]
        paid_revalidation = None
        current_paid_revalidation = None
        followup_paid_revalidation = None
        final_paid_revalidation = None
        from . import pulso_final_paid_revalidation as final_paid
        from . import pulso_followup_paid_revalidation as followup_paid
        from . import pulso_current_paid_revalidation as current_paid
        if final_paid.has_claim(raw.metadata) or final_paid.known_original_candidate(raw):
            try:
                final_paid_revalidation, _ = final_paid.verified_processing_mode(raw)
                ai = final_paid.unchanged_output(raw)
            except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
                raw.metadata["editorial_assessment"] = {"decision":"pending", "threshold":72,
                    "reason":"pulso_paid_revalidation_evidence_unverified", "evidence_error":str(exc)}
                raise DeferredProcessing("pulso_paid_revalidation_evidence_unverified") from exc
        elif followup_paid.has_claim(raw.metadata) or followup_paid.known_original_candidate(raw):
            try:
                followup_paid_revalidation, _ = followup_paid.verified_processing_mode(raw)
                context = followup_paid.reassessment_context(raw)
                if context is not None:
                    kind += (". Revisión del contrato y de la novedad sobre este mismo cuerpo completo; "
                             "las citas sugeridas son literales y no aprueban publicación: " + context["context_text"])
                ai = (analyze_news(title=raw.title, text=text, source_name=raw.source_name, kind=kind,
                                   full_text=True, pulso_editorial_proof=True)
                      if followup_paid_revalidation["new_model_request"] else followup_paid.unchanged_output(raw))
            except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
                raw.metadata["editorial_assessment"] = {"decision":"pending", "threshold":72,
                    "reason":"pulso_paid_revalidation_evidence_unverified", "evidence_error":str(exc)}
                raise DeferredProcessing("pulso_paid_revalidation_evidence_unverified") from exc
        elif current_paid.has_claim(raw.metadata):
            from .pulso_paid_revalidation import verified_paid_processing_mode
            try:
                current_paid_revalidation, _ = current_paid.verified_processing_mode(raw)
                # The earlier 981 admission remains a distinct, mandatory
                # history. A current repair never relabels its new29731 answer.
                paid_revalidation, _ = verified_paid_processing_mode(raw)
                context = current_paid.reassessment_context(raw)
                if context is not None:
                    kind += (". Revisión del contrato editorial sobre este mismo artículo completo: "
                             + context["context_text"])
                ai = (analyze_news(title=raw.title, text=text, source_name=raw.source_name, kind=kind,
                                   full_text=True, pulso_editorial_proof=True)
                      if current_paid_revalidation["new_model_request"] else current_paid.unchanged_output(raw))
            except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
                raw.metadata["editorial_assessment"] = {"decision":"pending", "threshold":72,
                    "reason":"pulso_paid_revalidation_evidence_unverified", "evidence_error":str(exc)}
                raise DeferredProcessing("pulso_paid_revalidation_evidence_unverified") from exc
        elif raw.metadata.get("paid_guard_revalidation_admission") is not None:
            from .pulso_paid_revalidation import (verified_paid_processing_mode, unchanged_paid_output,
                                                  verified_reassessment_context)
            try:
                paid_revalidation, _ = verified_paid_processing_mode(raw)
                context = verified_reassessment_context(raw)
                if context is not None:
                    kind += (". Contexto incremental de una publicación previa, verificado contra su cuerpo completo: "
                             + context["context_text"])
                ai = (analyze_news(title=raw.title, text=text, source_name=raw.source_name, kind=kind,
                                   full_text=True, pulso_editorial_proof=True)
                      if paid_revalidation["new_model_request"] else unchanged_paid_output(raw))
            except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
                raw.metadata["editorial_assessment"] = {"decision":"pending", "threshold":72,
                    "reason":"pulso_paid_revalidation_evidence_unverified", "evidence_error":str(exc)}
                raise DeferredProcessing("pulso_paid_revalidation_evidence_unverified") from exc
        else:
            ai = analyze_news(title=raw.title, text=text, source_name=raw.source_name, kind=kind, full_text=True,
                              pulso_editorial_proof=True)
    else:
        ai_text = (primary_body[:3500] + "\n\nHechos adicionales del documento oficial verificado:\n" + document_facts
                   if document_facts else body[:10000])
        ai = analyze_news(title=raw.title, text=ai_text, source_name=raw.source_name, kind=kind)
    if not ai:
        raw.metadata["editorial_assessment"] = {"decision": "pending", "reason": "analysis_unavailable"}
        raise DeferredProcessing("curated beta source pending assessment")
    if raw.source_slug == "pulso_latercera":
        from .pulso_editorial_proof import model_binding_matches, validate_pulso_editorial_proof
        validation=validate_pulso_editorial_proof(ai,text)
        validation.update(primary_article_body_sha256=raw.metadata["analysis_base_article_body_sha256"],
                          request_input_sha256=raw.metadata["analysis_request_input_sha256"],
                          model_response=ai.get("_pulso_analysis_meta") if isinstance(ai,dict) else None)
        if not model_binding_matches(ai,source_name=raw.source_name,
                                     input_text_sha256=raw.metadata["analysis_input_body_sha256"],
                                     request_input_sha256=raw.metadata["analysis_request_input_sha256"]):
            validation.update(decision="deferred",reason="pulso_editorial_model_binding_mismatch")
        if final_paid_revalidation is not None:
            try:
                raw.metadata[final_paid.RECEIPT] = final_paid.revalidation_receipt(raw, ai, validation)
            except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
                raw.metadata["editorial_assessment"] = {"decision":"pending", "threshold":72,
                    "reason":"pulso_paid_revalidation_evidence_unverified", "evidence_error":str(exc)}
                raise DeferredProcessing("pulso_paid_revalidation_evidence_unverified") from exc
        elif followup_paid_revalidation is not None:
            try:
                if followup_paid_revalidation["new_model_request"]:
                    from . import pulso_paid_revalidation as original_paid
                    followup_receipt = followup_paid.new_fast_attempt_receipt(raw, ai, validation)
                    current_receipt = current_paid.new_fast_attempt_receipt(raw, ai, validation)
                    legacy_receipt = original_paid.new_fast_attempt_receipt(raw, ai, validation)
                    raw.metadata.setdefault(followup_paid.NEW_FAST_RECEIPTS, []).append(followup_receipt)
                    raw.metadata.setdefault(current_paid.NEW_FAST_RECEIPTS, []).append(current_receipt)
                    raw.metadata.setdefault(original_paid.NEW_FAST_RECEIPTS, []).append(legacy_receipt)
                else:
                    raw.metadata[followup_paid.RECEIPT] = followup_paid.revalidation_receipt(raw, ai, validation)
            except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
                raw.metadata["analysis_model_output"] = ai
                raw.metadata["pulso_editorial_proof_validation"] = validation
                raw.metadata["editorial_assessment"] = {"decision":"pending", "threshold":72,
                    "reason":"pulso_paid_revalidation_evidence_unverified", "evidence_error":str(exc)}
                raise DeferredProcessing("pulso_paid_revalidation_evidence_unverified") from exc
        elif current_paid_revalidation is not None:
            from . import pulso_current_paid_revalidation as current_paid
            try:
                if current_paid_revalidation["new_model_request"]:
                    from .pulso_paid_revalidation import NEW_FAST_RECEIPTS, new_fast_attempt_receipt
                    current_receipt = current_paid.new_fast_attempt_receipt(raw, ai, validation)
                    legacy_receipt = new_fast_attempt_receipt(raw, ai, validation)
                    raw.metadata.setdefault(current_paid.NEW_FAST_RECEIPTS, []).append(current_receipt)
                    raw.metadata.setdefault(NEW_FAST_RECEIPTS, []).append(legacy_receipt)
                else:
                    raw.metadata[current_paid.RECEIPT] = current_paid.revalidation_receipt(raw, ai, validation)
            except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
                raw.metadata["analysis_model_output"] = ai
                raw.metadata["pulso_editorial_proof_validation"] = validation
                raw.metadata["editorial_assessment"] = {"decision":"pending", "threshold":72,
                    "reason":"pulso_paid_revalidation_evidence_unverified", "evidence_error":str(exc)}
                raise DeferredProcessing("pulso_paid_revalidation_evidence_unverified") from exc
        elif paid_revalidation is not None and not paid_revalidation["new_model_request"]:
            from .pulso_paid_revalidation import revalidation_receipt
            try:
                raw.metadata["paid_guard_revalidation_receipt"] = revalidation_receipt(raw, ai, validation)
            except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
                raw.metadata["editorial_assessment"] = {"decision":"pending", "threshold":72,
                    "reason":"pulso_paid_revalidation_evidence_unverified", "evidence_error":str(exc)}
                raise DeferredProcessing("pulso_paid_revalidation_evidence_unverified") from exc
        elif paid_revalidation is not None:
            from .pulso_paid_revalidation import NEW_FAST_RECEIPTS, new_fast_attempt_receipt
            try:
                receipt = new_fast_attempt_receipt(raw, ai, validation)
                raw.metadata.setdefault(NEW_FAST_RECEIPTS, []).append(receipt)
            except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
                # Preserve even an unbound paid response for diagnosis. It is
                # not eligible for automatic revalidation or publication.
                raw.metadata["analysis_model_output"] = ai
                raw.metadata["pulso_editorial_proof_validation"] = validation
                raw.metadata["editorial_assessment"] = {"decision":"pending", "threshold":72,
                    "reason":"pulso_paid_revalidation_evidence_unverified", "evidence_error":str(exc)}
                raise DeferredProcessing("pulso_paid_revalidation_evidence_unverified") from exc
        raw.metadata["pulso_editorial_proof_validation"]=validation
        raw.metadata["analysis_model_output"]=ai
        if validation["decision"] == "deferred":
            raw.metadata["editorial_assessment"]={"decision":"pending","reason":validation["reason"],
                                                  "threshold":72,"proof_version":validation["version"]}
            raise DeferredProcessing(validation["reason"])
        if validation["decision"] == "rejected":
            return reject(validation["reason"],relevance_score=ai["relevance_score"],threshold=72,
                          proof_version=validation["version"],analysis_reason=ai.get("reason"))
        raw.metadata["prospective_evidence"]=validation["prospective_evidence"]
    score = int(ai.get("relevance_score", 0))
    if scoped:
        raw.metadata["editorial_assessment"] = {"score": score, "reason": ai.get("reason"), "threshold": 75}
    threshold = 72 if role == "media" else 75
    analysis_reason = ai.get("reason") or "analysis_reason_not_supplied"
    what = (ai.get("what_happened") or "").strip()
    why = (ai.get("why_it_matters") or "").strip()
    if raw.source_slug == "pulso_latercera":
        if scoped and (score < threshold or len(what) < 45 or len(why) < 35):
            raw.metadata["publication_rejection_reason"] = "editorial_score_or_summary_below_threshold"
            return None
        if score < threshold:
            return reject("editorial_relevance_below_threshold", relevance_score=score, threshold=threshold, analysis_reason=analysis_reason)
        if len(what) < 45 or len(why) < 35:
            return reject("incomplete_editorial_analysis", relevance_score=score, threshold=threshold, analysis_reason=analysis_reason)
        if role == "media":
            what = _attribute_pulso_what(what)
    elif scoped:
        if score < threshold or len(what) < 45 or len(why) < 35:
            raw.metadata["publication_rejection_reason"] = "editorial_score_or_summary_below_threshold"
            return None
    elif not assessed(raw, ai, threshold):
        return None
    scopes = ["Salud laboral"] if role == "mutuality" else (["Sistema de salud"] if role == "media" else ["Prestadores"])
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
    if role == "media" and len(scopes) > 1:
        scopes.remove("Sistema de salud")
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
    if raw.source_slug != 'pulso_latercera':
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
        row["publication_date"] = raw.metadata.get("publication_date") or raw.event_date
        row["publication_timestamp"] = raw.metadata.get("publication_timestamp")
        row["publication_date_source"] = raw.metadata.get("publication_date_source")
        from .editorial_gate import publication_ready
        accepted, reason, quality = publication_ready(row)
        if not accepted:
            return reject(reason, relevance_score=score, threshold=threshold, quality_score=quality, analysis_reason=analysis_reason)
    if raw.source_slug == "pulso_latercera":
        raw.metadata["editorial_assessment"] = {"decision": "published", "relevance_score": score, "threshold": threshold, "analysis_reason": analysis_reason}
        row["editorial_assessment"] = raw.metadata["editorial_assessment"]
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


_PRESTADORES_HOSTS = ("www.superdesalud.gob.cl", "superdesalud.gob.cl")
_PRESTADORES_MAX_BYTES = 15 * 1024 * 1024


def _prestadores_official(url):
    try:
        parsed = urlparse(url)
        return (parsed.scheme == "https" and parsed.hostname in _PRESTADORES_HOSTS and parsed.port in (None, 443)
                and not parsed.username and not parsed.password)
    except (TypeError, ValueError):
        return False


def prestadores_listing_pdf_urls(html):
    """Every official PDF linked by the bulletin listing (baseline = whole listing)."""
    parser = _Links()
    parser.feed(html)
    urls = set()
    for href, _ in parser.links:
        url = urljoin(PrestadoresDataScout.PAGE, href or "")
        if _prestadores_official(url) and urlparse(url).path.lower().endswith(".pdf"):
            urls.add(url)
    return sorted(urls)


def download_prestadores_pdf(url, *, timeout=30, max_bytes=_PRESTADORES_MAX_BYTES):
    """Verified-TLS PDF download bounded in bytes; redirects stay on the official host."""
    from urllib.request import HTTPRedirectHandler, Request, build_opener

    class _SameHost(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if not _prestadores_official(newurl):
                raise ValueError("Prestadores redirect left the official HTTPS host")
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    if not _prestadores_official(url):
        raise ValueError("Prestadores bulletin URL must be official HTTPS")
    request = Request(url, headers={"User-Agent": "RadarSaludBot/0.3 (+public-source-monitor)"})
    with build_opener(_SameHost()).open(request, timeout=timeout) as response:
        if not _prestadores_official(response.geturl()):
            raise ValueError("Prestadores response left the official HTTPS host")
        declared = response.headers.get("Content-Length")
        if declared and declared.isdigit() and int(declared) > max_bytes:
            raise ValueError("Prestadores bulletin exceeds the byte limit")
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("Prestadores bulletin exceeds the byte limit")
    if not data.startswith(b"%PDF-"):
        raise ValueError("Prestadores bulletin is not a PDF")
    return data


def prestadores_pdf_text(data, max_pages=3):
    """Unfiltered text of the first pages (the shared extractor drops short
    'Superintendencia de Salud' header lines, which can carry the issuer)."""
    import io
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages[:max_pages])


class PrestadoresDailyScout:
    """Daily-engine view of the bulletins with a first-detection baseline.

    The listing exposes no publication date (Dirección 27-oct-2026, decision
    d). The first daily run records every PDF linked by the listing (the whole
    listing, not only the 2026 subset) as a baseline and queues nothing, so a
    backlog is never presented as "detected today"; later runs queue only
    bulletins absent from it.
    """
    SOURCE_SLUG = PrestadoresDataScout.SOURCE_SLUG

    def __init__(self, root=None, scout=None, enabled=None, fetch=None):
        from pathlib import Path
        from .paths import project_root
        self.root = Path(root or project_root())
        self.scout = scout or PrestadoresDataScout()
        self.enabled = enabled
        self.fetch = fetch or fetch_html
        self.surface_results = []

    def discover(self):
        import json
        from datetime import datetime, timezone
        from .live_lanes import enabled as lane_enabled
        from .pending_queue import atomic_json
        enabled = lane_enabled("RADAR_PRESTADORES_DAILY") if self.enabled is None else self.enabled
        if not enabled:
            self.surface_results = [{"status": "not_run_outside_engine_runtime"}]
            return []
        html = self.fetch(self.scout.PAGE)
        listed = prestadores_listing_pdf_urls(html)
        items = self.scout.discover_from_html(html)
        path = self.root / "data/state/prestadores_data_baseline.json"
        if not path.exists():
            atomic_json(path, {"established_at": datetime.now(timezone.utc).isoformat(),
                               "reason": "first_detection_baseline_dated_items_unavailable",
                               "urls": sorted(set(listed) | {raw.url for raw in items})})
            self.surface_results = [{"status": "baseline_established", "baseline_items": len(listed)}]
            return []
        baseline = set(json.loads(path.read_text()).get("urls", []))
        fresh = [raw for raw in items if raw.url not in baseline]
        self.surface_results = [{"status": "ok", "listed_pdfs": len(listed), "candidates": len(items),
                                 "new_since_baseline": len(fresh)}]
        return fresh


def process_prestadores_bulletin(raw, cfg):
    """Deterministic 'Datos' card dated by first detection (never as publication)."""
    from .date_basis import apply_first_detected, label_first_detected
    from .pipeline import build_signal
    from .processing import DeferredProcessing
    try:
        data = download_prestadores_pdf(raw.url)
        text = prestadores_pdf_text(data)
    except Exception as exc:
        # Off-host redirect, non-PDF or oversize response: transient/unverified
        # evidence, deferred for retry, never a durable rejection.
        raise DeferredProcessing(f"Prestadores bulletin unavailable: {exc}"[:200]) from exc
    if len(" ".join(text.split())) < 250 or "intendencia de prestadores" not in " ".join(text.split()).casefold():
        raise DeferredProcessing("Prestadores bulletin unreadable")
    raw.metadata.update(validated_document=True, document_sha256=hashlib.sha256(data).hexdigest(),
                        document_bytes=len(data))
    apply_first_detected(raw)
    family = raw.metadata.get("data_family") or "prestadores"
    period = raw.metadata.get("data_period") or "2026"
    raw.metadata.update({
        "what_happened": (f"La Intendencia de Prestadores de la Superintendencia de Salud tiene disponible el "
                          f"{raw.title} (tema: {family}; período de datos: {period})."),
        "why_it_matters": (f"Boletín estadístico oficial sobre {family} de prestadores: insumo para seguir "
                           "acreditación, reclamos y registro. La fuente no informa fecha de publicación; "
                           "se muestra la fecha en que Alicanto lo detectó."),
        "signal_types": ["Datos"], "scopes": ["Prestadores"],
        "watch_tags": ["prestadores", "superintendencia de salud", family],
        "scores": {"economic": 45, "regulatory": 60, "scope": 60, "novelty": 60, "actionability": 55},
    })
    row = build_signal(raw, cfg).to_dict()
    row.update(signal_types=["Datos"], scopes=["Prestadores"], data_period=period, deterministic_processing=True,
               document_sha256=raw.metadata["document_sha256"])
    return label_first_detected(row, raw)


def media_gate_accepts(title, body=""):
    return _material("media", title, body)
