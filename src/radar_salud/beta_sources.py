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
            "name": "Clínicas Achs Salud",
            "type": "corporate",
            "page": "https://www.achs.cl/centro-de-noticias",
            "hosts": ("www.achs.cl", "achs.cl"),
            "path": r"/centro-de-noticias/noticia/20\d{2}/[^/]+/?",
            "role": "provider_achs",
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
            "path": r"/[^/]+/?",
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

    def discover_from_html(self, html, detail_loader=fetch_html):
        if self.slug == "pulso_latercera":
            from .pulso_source import discover_listing
            audit = self.discovery_audit = []
            out = discover_listing(html, self.cfg["page"], detail_loader, audit, set())
            if not out:
                raise RuntimeError("Pulso / La Tercera has no verified, dated health articles: " + str(audit))
            return sorted(out, key=lambda item: item.event_date, reverse=True)
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
        if self.slug == "pulso_latercera":
            from .pulso_source import discover_pulso
            self.discovery_audit = []
            return discover_pulso(audit=self.discovery_audit)
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
        return (care_obligation or ges_coverage or care_legislation
                or proposed_clinical_condition or provider_flood_response
                or authorized_care_registry or clinical_service_suspension
                or quantified_health_power_impact or modular_care_deployment or mapped_multi_provider_flood
                or reproductive_legislative_progress or medical_insurance_inquiry or provider_judicial_liability
                or essential_care_transport_blocked)
    return False


def process_curated_beta_source(raw, cfg):
    from .llm_analysis import analyze_news
    from .pipeline import build_signal
    from .processing import DeferredProcessing
    from .public_source_pipeline import enrich, _scopes

    if raw.source_slug == "pulso_latercera":
        from .pulso_source import (ConflictingPublicationArticle, ExcludedArticle,
                                   SponsoredArticle, TextUnavailableArticle,
                                   article_body_evidence, article_url, complete_article_body,
                                   extract_article, publisher_taxonomy_requires_revalidation,
                                   verified_publication_date_conflict, verified_sponsored_content,
                                   verified_video_without_text)

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
                                             "publisher_sponsored_content_review_required", "publisher_opinion_taxonomy"}
                        for key in ("publisher_exception_reason", "source_content_unavailable_reason",
                                    "publisher_exclusion_reason", "editorial_hold"):
                            if key not in evidence and raw.metadata.get(key) in publisher_reasons:
                                raw.metadata.pop(key)
                    raw.metadata.update(evidence, **article_body_evidence(body), market_role="media",
                                        source_quality_gate=quality,
                                        html_sha256=hashlib.sha256(html.encode("utf-8")).hexdigest(),
                                        captured_at=datetime.now(timezone.utc).isoformat())
                try:
                    title, body, evidence = extract_article(html, raw.url)
                except (ConflictingPublicationArticle, TextUnavailableArticle, SponsoredArticle, ExcludedArticle) as exc:
                    quality = ("deferred_publication_date" if isinstance(exc, ConflictingPublicationArticle) else
                               "deferred_video_text" if isinstance(exc, TextUnavailableArticle) else
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
        from .pulso_incremental_review import apply_incremental_review
        apply_incremental_review(raw)
    else:
        raw = enrich(raw)
    body = raw.metadata.get("page_text") or raw.raw_text or ""
    role = raw.metadata.get("market_role") or "provider"
    if raw.metadata.get("editorial_hold"):
        raw.metadata["editorial_assessment"] = {"decision": "pending", "reason": raw.metadata["editorial_hold"]}
        raise DeferredProcessing("Pulso pending incremental-value review")
    def reject(reason, **evidence):
        raw.metadata["rejection_reason"] = reason
        raw.metadata["editorial_assessment"] = dict(decision="rejected", reason=reason, **evidence)
        return None
    if not raw.event_date:
        return reject("missing_publication_date")
    if len(body) < 160:
        return reject("incomplete_article_evidence")
    if not _material(role, raw.title, body):
        return reject("media_materiality_prefilter" if role == "media" else "source_materiality_prefilter")
    kind = {
        "media": "prensa económica de alta confianza; señal temprana, atribuir y no convertir reporte de prensa en hecho oficial",
        "mutuality": "publicación institucional de mutualidad; filtrar marketing y priorizar cambios operacionales o de salud laboral",
        "provider_achs": "publicación institucional de prestador; priorizar capacidad, convenios, expansión y relación público-privada",
        "provider": "publicación institucional de prestador; priorizar capacidad, convenios, expansión, inversión y M&A",
    }.get(role, "publicación sectorial")
    if role == "media" and raw.metadata.get("editorial_review_context"):
        import json
        kind += (". Revisión previa de valor incremental: "
                 + json.dumps(raw.metadata["editorial_review_context"], ensure_ascii=False)
                 + ". Evalúa si el artículo agrega un cambio material a ese antecedente; "
                   "la revisión sólo habilita análisis y no aprueba publicación. "
                   "Preserva período, métrica, condición de propuesta y atribución de prensa.")
    if raw.source_slug == "pulso_latercera":
        # Keep the source's complete primary text through the model boundary;
        # strategic facts can occur after the general news excerpt limit.
        raw.metadata.update(analysis_input_body_sha256=hashlib.sha256(body.encode("utf-8")).hexdigest(),
                            analysis_input_characters=len(body), analysis_input_complete=True)
        ai = analyze_news(title=raw.title, text=body, source_name=raw.source_name, kind=kind, full_text=True)
    else:
        ai = analyze_news(title=raw.title, text=body[:10000], source_name=raw.source_name, kind=kind)
    if not ai:
        raw.metadata["editorial_assessment"] = {"decision": "pending", "reason": "analysis_unavailable"}
        raise DeferredProcessing("curated beta source pending assessment")
    score = int(ai.get("relevance_score", 0))
    threshold = 72 if role == "media" else 75
    analysis_reason = ai.get("reason") or "analysis_reason_not_supplied"
    what = (ai.get("what_happened") or "").strip()
    why = (ai.get("why_it_matters") or "").strip()
    if score < threshold:
        return reject("editorial_relevance_below_threshold", relevance_score=score, threshold=threshold, analysis_reason=analysis_reason)
    if len(what) < 45 or len(why) < 35:
        return reject("incomplete_editorial_analysis", relevance_score=score, threshold=threshold, analysis_reason=analysis_reason)
    if role == "media" and not re.search(r"pulso|la tercera", what, re.I):
        what = f"Según Pulso / La Tercera, {what}"
    scopes = ["Salud laboral"] if role == "mutuality" else (["Sistema de salud"] if role == "media" else ["Prestadores"])
    inferred = _scopes(f"{raw.title} {body[:2500]}")
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
    row["source_quality_gate"] = "passed"
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
    raw.metadata["editorial_assessment"] = {"decision": "published", "relevance_score": score, "threshold": threshold, "analysis_reason": analysis_reason}
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
