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

SOURCES = {"clinicas_achs_salud", "achs_seguro_laboral", "ist", "mutual_seguridad"}


class SourceDiscoveryError(RuntimeError):
    def __init__(self, code, url, detail="", *, diagnostics=None, partial_items=None):
        self.code, self.url, self.detail = code, url, detail
        self.diagnostics = diagnostics or []
        self.partial_items = partial_items or []
        super().__init__(f"{code}: {url}" + (f" ({detail})" if detail else ""))


# Sitefinity (achs.cl's CMS) renders an unfilled upgrade-notice template whose
# H1 is literally "Upgraded to Sitefinity {{currentVersion}}". The 28-oct-2026
# daily run captured it on five achs.cl article URLs (distinct bytes per URL)
# with no usable article header or publication field. It is publisher CMS output, never
# an article title, and never publication evidence.
CMS_PLACEHOLDER_HEADING = re.compile(r"^upgraded to sitefinity\b", re.I)


def is_cms_placeholder_heading(text):
    return bool(CMS_PLACEHOLDER_HEADING.match(" ".join((text or "").split())))


def assert_not_challenge(html, url):
    if re.search(r"_Incapsula_Resource|Request unsuccessful.*Incapsula|Incapsula incident ID", html, re.I | re.S):
        raise SourceDiscoveryError("external_waf_challenge", url, "Incapsula response; not newsroom content")


def fetch_listing(scout, loader):
    scout.diagnostics = []
    scout.discovery_incomplete = False
    scout.coverage_status = "not_started"
    try:
        html = loader(scout.cfg["page"])
        assert_not_challenge(html, scout.cfg["page"])
    except Exception as exc:
        diagnostic = _failure(exc, scout.cfg["page"], "listing_fetch_failed")
        scout.diagnostics = [diagnostic]
        scout.discovery_incomplete = True
        scout.coverage_status = "incomplete"
        raise SourceDiscoveryError(diagnostic["code"], diagnostic["url"], diagnostic["detail"],
                                   diagnostics=scout.diagnostics) from exc
    return html


def _failure(exc, url, default_code):
    code = (exc.code if isinstance(exc, SourceDiscoveryError) else
            "executor_proxy_denied" if "Tunnel connection failed: 403" in str(exc) else default_code)
    detail = exc.detail if isinstance(exc, SourceDiscoveryError) else f"{type(exc).__name__}: {exc}"
    diagnostic = {"code": code, "url": url, "detail": detail, "exception_type": type(exc).__name__}
    # A proxy CONNECT denial is not an HTTP response from the publisher.
    if code != "executor_proxy_denied" and isinstance(getattr(exc, "code", None), int):
        diagnostic["http_status"] = exc.code
    return diagnostic


def chile_today():
    return datetime.now(ZoneInfo("America/Santiago")).date()


def fold(text):
    return "".join(c for c in unicodedata.normalize("NFD", text.casefold())
                   if unicodedata.category(c) != "Mn")


def valid_date(value, *, today=None):
    """Parse a whole publication field; never search body text for a date."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?)?", value):
            if "T" in value:
                instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
                parsed = (instant.astimezone(ZoneInfo("America/Santiago")) if instant.tzinfo else instant).date()
            else:
                parsed = date.fromisoformat(value)
        else:
            numbered = re.fullmatch(r"(\d{1,2})([/-])(\d{1,2})\2(\d{4})", value)
            if numbered:
                parsed = date(int(numbered[4]), int(numbered[3]), int(numbered[1]))
            else:
                named = re.fullmatch(r"(\d{1,2})\s+(?:de\s+)?([a-záéíóúñ]+)\.?\s+(?:de\s+)?(\d{4})", value, re.I)
                months = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
                          "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}
                months.update({"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7,
                               "ago": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dic": 12})
                months.update({"january": 1, "jan": 1, "february": 2, "march": 3, "mar": 3,
                               "april": 4, "apr": 4, "june": 6, "july": 7, "august": 8, "aug": 8,
                               "september": 9, "october": 10, "november": 11, "december": 12, "dec": 12})
                # The captured IST CMS uses both "Oct 7, 2026" and "Ago 31,
                # 2026" in an explicitly marked publisher date container.
                # Accept that entire field, including its comma, not a date
                # embedded in a heading, event description or free text.
                cms = re.fullmatch(r"([a-záéíóúñ]+)\.?\s+(\d{1,2}),\s+(\d{4})", value, re.I)
                if cms and fold(cms[1]) in months:
                    parsed = date(int(cms[3]), months[fold(cms[1])], int(cms[2]))
                elif named and fold(named[2]) in months:
                    parsed = date(int(named[3]), months[fold(named[2])], int(named[1]))
                else:
                    return None
        return parsed.isoformat() if parsed <= (today or chile_today()) else None
    except (ValueError, TypeError):
        return None


class Article(HTMLParser):
    """Article scope plus explicit publisher date fields; conflicts fail closed.

    A bare date after H1 can be an event date. The ACHS ``div.fecha`` selector
    is restricted to its verified publisher host and the article header; other
    sites need semantic publication attributes or a verified native selector.
    """
    STOP = ("ultimas publicaciones", "noticias relacionadas", "informacion corporativa",
            "tambien te puede interesar", "deja una respuesta", "dejar un comentario", "que es ist")
    IGNORE = {"script", "style", "nav", "footer", "aside", "noscript"}
    VOID = {"meta", "img", "br", "hr", "input", "link", "source", "area", "base", "embed", "param", "wbr"}
    PUBLICATION_CLASSES = {"published", "publication-date", "published-date", "date-published"}

    def __init__(self, url=None):
        super().__init__()
        self.url = url
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
        self._body_started = False
        self._elements = []
        self._publication_fields = []
        self.date_candidates = []
        self.cms_placeholder = False

    def _date_candidate(self, kind, value):
        self.date_candidates.append({"kind": kind, "value": value or ""})
        if kind in ("article:published_time", "datePublished", "publishdate") and not self.meta_date:
            self.meta_date = value or ""
        elif not self.visible_date:
            self.visible_date, self.date_evidence = value or "", kind

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        tag = tag.lower()
        if tag in self.IGNORE:
            self._ignore.append(tag)
            if tag == "footer":
                self._stopped = True
            return
        if self._ignore:
            return
        if tag not in self.VOID:
            self._elements.append(tag)
        if tag == "meta":
            key = (a.get("property") or a.get("name") or a.get("itemprop") or "").casefold()
            if key in ("article:published_time", "datepublished", "publishdate"):
                self._date_candidate("datePublished" if key == "datepublished" else key, a.get("content"))
        if re.fullmatch("h[1-6]", tag):
            self._heading, self._heading_parts = tag, []
        if not self._active or self._stopped:
            return
        classes = set((a.get("class") or "").casefold().split())
        itemprop = set((a.get("itemprop") or "").casefold().split())
        semantic = bool(classes & self.PUBLICATION_CLASSES) or "datepublished" in itemprop
        from urllib.parse import urlsplit
        publisher_url = urlsplit(self.url or "")
        native_achs = (tag == "div" and "fecha" in classes and not self._body_started
                       and publisher_url.hostname in ("www.achs.cl", "achs.cl")
                       and re.fullmatch(r"/centro-de-noticias/noticia/\d{4}/[^/]+/?", publisher_url.path) is not None)
        if semantic or native_achs:
            kind = ("datePublished" if "datepublished" in itemprop else
                    "time.published@datetime" if tag == "time" and "published" in classes and "datetime" in a else
                    "publisher:achs_div_fecha" if native_achs else "publisher:publication_container")
            if tag == "time" and a.get("datetime") is not None:
                self._date_candidate(kind, a["datetime"])
            elif a.get("content") is not None:
                self._date_candidate(kind, a["content"])
            elif tag not in self.VOID:
                self._publication_fields.append({"depth": len(self._elements), "parts": [], "kind": kind})

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self._ignore:
            if tag == self._ignore[-1]:
                self._ignore.pop()
            return
        if self._elements and tag in self._elements:
            depth = len(self._elements) - self._elements[::-1].index(tag)
            for field in list(self._publication_fields):
                if field["depth"] >= depth:
                    value = " ".join(" ".join(field["parts"]).split())
                    value = re.sub(r"^(?:publicad[oa]|fecha de publicaci[oó]n)\s*:?\s*(?:el\s+)?", "", value, flags=re.I)
                    self._date_candidate(field["kind"], value)
                    self._publication_fields.remove(field)
            del self._elements[depth - 1:]
        if tag == self._heading:
            heading = " ".join(" ".join(self._heading_parts).split())
            self._heading = None
            if tag == "h1" and not self.title and is_cms_placeholder_heading(heading):
                # Not the article: keep waiting for the real H1 so that its
                # native header date can still be bound (or fail closed).
                self.cms_placeholder = True
            elif tag == "h1" and not self.title:
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
        if self._publication_fields:
            for field in self._publication_fields:
                field["parts"].append(text)
        else:
            self._body_started = True
        self.parts.append(text)

    def result(self, *, today=None):
        dates = [valid_date(candidate["value"], today=today) for candidate in self.date_candidates]
        if any(day is None for day in dates):
            return self.title, None, " ".join(self.parts), "invalid_publication_date"
        if len(set(dates)) > 1:
            return self.title, None, " ".join(self.parts), "conflicting_publication_dates"
        return (self.title, dates[0] if dates else None, " ".join(self.parts),
                self.date_candidates[0]["kind"] if dates else "missing_publication_date")

    def publication_evidence(self, url=None, *, today=None):
        _, published, _, kind = self.result(today=today)
        if not published or not (url or self.url):
            return None
        return {"url": url or self.url, "value": self.date_candidates[0]["value"], "date": published, "kind": kind}


def market_role(title, body):
    headline = fold(title)
    # A center plan remains a distinct provider activity even if a clinic is
    # mentioned as an out-of-hours referral elsewhere in the article.
    if "achs salud" in headline and re.search(r"\bcentros?\b", headline) and "clinicas achs salud" not in headline:
        return "provider_achs_centers"
    actor = (r"(?:clinicas achs salud|clinica (?:atacama|portada|maitenes|lircay|los andes|del sur|"
             r"puerto montt|los coihues|curico|la serena) achs salud)")
    if re.search(actor, headline):
        return "provider_achs"
    # Attribution requires an action by the provider. Quoted advice and a
    # physician's employer are not changes operated by that employer.
    unquoted = re.sub(r'"[^"\n]*"|“[^”]*”|«[^»]*»', " ", body)
    action = (r"(?:activ\w*|incorpor\w*|habilit\w*|inaugur\w*|ampli\w*|abre|abrio|apertura|"
              r"implement\w*|adquier\w*|inviert\w*|inversion|ofrece|ofrecera|entrega|entregara|"
              r"particip\w*|se suma|se une|prestaciones|atencion gratuita)")
    for sentence in re.split(r"[.!?;\n]", fold(unquoted)):
        for mention in re.finditer(actor, sentence):
            before, after = sentence[:mention.start()], sentence[mention.end():]
            if re.search(r"\b(?:doctor\w*|medic\w*|especialista|profesional|traumatolog\w*|psicolog\w*)\b.{0,100}$", before):
                continue
            if re.match(r"\s*(?:que\s+)?(?:explica|comenta|senala|recomienda|aconseja)\b", after):
                continue
            if re.search(action, after[:180]):
                return "provider_achs"
            if re.search(r"(?:filial|red de clinicas|junto con|a traves de).{0,100}$", before) and re.search(action, sentence):
                return "provider_achs"
    return "mutuality"


def materiality(role, title, body):
    """Reason codes are retained in raw metadata and the reconciliation ledger."""
    text, headline = fold(f"{title} {body}"), fold(title)
    # Numeric punctuation is not a sentence boundary: "32.522" and "36,9%"
    # must stay attached to the measurement they quantify.
    clauses = re.split(r"(?<!\d)\.|\.(?!\d)|[!?;\n]|\b(?:pero|sin embargo)\b", text)
    affirmative = []
    for clause in clauses:
        negation_scope = re.sub(r"\bsin\s+(?:costo|copago|cargo)(?:s)?\b", " ", clause)
        if not re.search(r"\b(?:no|nunca|tampoco|sin)\b", negation_scope):
            affirmative.append(clause)
    new_labor_report = bool(any(re.search(r"(?:publico|publica|presento|presenta).{0,50}(?:informe|estudio)", c)
                                  for c in affirmative)
                            and re.search(r"(?:acoso laboral|violencia en el trabajo|salud mental laboral)", text))
    new_adherent = any(re.search(r"(?:nuevo adherente|se incorpora|se adhiere|se adhieren|"
                                r"forma parte de las entidades empleadoras adheridas)", c) for c in affirmative)
    # Check affirmative clauses before the headline noise gate. A campaign can
    # accompany a real opening or a new operational protocol.
    for clause in affirmative:
        capacity = r"(?:centro\w*|clinica\w*|pabellon\w*|boxes|box|camas?|salas?|unidades?|infraestructura|equipamiento|servicios?|prestaciones?)"
        change = (r"(?:inaugur\w*|ampli\w*|apertura|se traslada|traslado temporal|adquier\w*|adquisicion|"
                  r"habilit\w*|moderniz\w*|renovad\w*|remodelad\w*|reabr\w*|reabiert\w*|"
                  r"(?:vuelve|volvio) a abrir)")
        if (re.search(rf"\b{change}\b.{{0,100}}\b{capacity}\b|\b{capacity}\b.{{0,100}}\b{change}\b", clause)
                or re.search(r"\b(?:nuevo centro|nueva clinica)\b|\binversion de.{0,30}\d", clause)):
            return True, "capacity_or_investment_change"
        if (re.search(r"\blicitacion publica\b", clause)
                and re.search(r"(?:adquisicion|ejecucion|construccion).{0,100}(?:obras civiles|modular)", clause)
                and re.search(r"(?:centro de atencion|clinica|hospital|capacidad).{0,250}\d[\d.,]*\s*m(?:²|2)", text)):
            # A published procurement call is a capacity signal. It does not
            # establish an award, a completed building or an unconditional
            # opening; preserve those qualifications in the article body.
            return True, "capacity_procurement_call"
        if re.search(r"(?:activ\w*|incorpor\w*|se suman|se suma).{0,180}(?:fonasa|safed|mcc)|"
                     r"(?:fonasa|safed|mcc).{0,180}(?:activ\w*|incorpor\w*|prestaciones|atencion)", clause):
            return True, "public_private_coverage_change"
        if role == "mutuality":
            if re.search(r"(?:nuevo adherente|incorpor\w*|se adhiere|se adhieren|adhiere).{0,160}\d[\d.,]*.{0,35}trabajador", clause):
                return True, "quantified_coverage_change"
            if (new_adherent and re.search(r"(?:pasa a asesorar|protege|cubre).{0,80}"
                    r"(?:\d+|uno|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\s+de\s+(?:las?\s+)?"
                    r"(?:\d+|uno|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\s+empresas", clause)):
                return True, "quantified_coverage_change"
            if re.search(r"(?:accident|siniestr|enfermedad).{0,220}(?:aument|disminu|alza|baja|reduccion).{0,100}\d|"
                         r"(?:aument|disminu|alza|baja|reduccion).{0,100}\d.{0,140}(?:accident|siniestr)", clause):
                return True, "quantified_occupational_data"
            if (re.search(r"(?:atenciones.{0,80}salud mental|salud mental.{0,80}atenciones)", clause)
                    and re.search(r"(?:triplic\w*|duplic\w*|aument\w*|disminu\w*).{0,100}\d", clause)):
                return True, "quantified_occupational_data"
            if (new_labor_report and re.search(r"(?:recibio|registro|registraron).{0,35}\d[\d.,]*\s+"
                    r"(?:requerimientos|atenciones|casos)", clause)):
                return True, "quantified_occupational_data"
            if (re.search(r"(?:automatiz\w*|inscripcion automatica)", clause)
                    and re.search(r"(?:inscripcion|inscribir)", text)
                    and re.search(r"(?:cursos|capacitaciones).{0,30}e-learning|e-learning.{0,30}(?:cursos|capacitaciones)", text)
                    and re.search(r"sin (?:la )?necesidad de esperar (?:el plazo de )?\d+ horas", text)):
                return True, "quantified_operational_process_change"
            if (re.search(r"se elaboro.{0,30}guia tecnica", clause)
                    and re.search(r"kit de herramientas.{0,160}instituciones publicas.{0,70}implementacion", clause)
                    and re.search(r"salud mental|violencia laboral", clause)):
                return True, "new_operational_tool_or_protocol"
            if (re.search(r"(?:nueva guia|nuevo protocolo|nueva plataforma|nuevo modulo|estrena modulo|"
                          r"implement\w*.{0,50}(?:guia|protocolo|plataforma|modulo)|"
                          r"(?:guia|protocolo|plataforma|modulo).{0,50}(?:publicad|publica|implement))", clause)
                    and re.search(r"(?:tratamiento|reintegro|evaluacion|reporteria|accidentes graves|patologias|"
                                  r"atencion clinica|abordaje.{0,30}salud mental)", clause)):
                return True, "new_operational_tool_or_protocol"
    if re.search(r"feria de bienestar|testimonio|historia de superacion|campana|semana de la|"
                 r"reconoc|premio|conmemor|seminario|congreso|webinar|caminata|pausas activas", headline):
        return False, "campaign_event_testimonial_or_recognition"
    return False, "no_verifiable_material_change"


def classify_content_kind(materiality_reason, title="", body=""):
    """Describe source content without changing date, role or editorial gates.

    A dated study can lack material evidence in its short landing page. Its
    type remains ``study`` while the linked document awaits assessment.
    These four labels are inventory descriptors, not relevance scores.
    """
    headline, text = fold(title), fold(f"{title} {body}")
    if (materiality_reason == "quantified_occupational_data"
            or re.search(r"\b(?:estudio|informe|reporte|analisis|boletin estadistico)\b", headline)):
        return "study"
    if materiality_reason in {"quantified_coverage_change", "capacity_procurement_call"}:
        return "commercial"
    if materiality_reason in {"capacity_or_investment_change", "public_private_coverage_change",
                              "quantified_operational_process_change"}:
        return "news"
    if materiality_reason == "new_operational_tool_or_protocol":
        return "prevention" if re.search(r"\b(?:guia|manual|protocolo)\b", headline) else "news"
    if re.search(r"\b(?:licitacion|tarifas?|descuentos?|promocion comercial|venta|cotiza)\b", headline):
        return "commercial"
    if re.search(r"\b(?:guia|manual|protocolo|recomendaciones|prevencion|preventiva|preventivas|"
                 r"consejos|autocuidado|campana)\b", headline):
        return "prevention"
    if (materiality_reason == "campaign_event_testimonial_or_recognition"
            and re.search(r"\b(?:campana|prevencion|preventiv\w*|bienestar)\b", text)):
        return "prevention"
    return "news"


def discover_items(scout, html, detail_loader, *, as_of=None, max_items=None):
    from .beta_sources import _Links
    from urllib.parse import urljoin, urlparse, urlunparse

    today = as_of or chile_today()
    if max_items is not None and (not isinstance(max_items, int) or max_items < 0):
        raise ValueError("max_items must be a nonnegative integer or None")
    scout.decisions, scout.diagnostics = [], []
    scout.discovery_incomplete = False
    scout.coverage_status = "not_started"
    try:
        assert_not_challenge(html, scout.cfg["page"])
    except SourceDiscoveryError as exc:
        scout.diagnostics.append(_failure(exc, scout.cfg["page"], "listing_fetch_failed"))
        scout.discovery_incomplete, scout.coverage_status = True, "incomplete"
        raise SourceDiscoveryError(exc.code, exc.url, exc.detail, diagnostics=scout.diagnostics) from exc
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
    attempted = 0
    truncated = 0
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
        if max_items is not None and attempted >= max_items:
            truncated += 1
            continue
        attempted += 1
        try:
            detail = detail_loader(url)
            assert_not_challenge(detail, url)
            article = Article(url=url)
            article.feed(detail)
        except Exception as exc:
            diagnostic = _failure(exc, url, "detail_fetch_failed")
            scout.diagnostics.append(diagnostic)
            scout.decisions.append({"url": url, "title": "", "event_date": None,
                                    "status": "pending", "reason": diagnostic["code"], "error": diagnostic})
            continue
        title, published, body, evidence = article.result(today=today)
        role = market_role(title, body) if scout.slug in ("clinicas_achs_salud", "achs_seguro_laboral") else "mutuality"
        decision = {"url": url, "title": title, "event_date": published, "date_evidence": evidence}
        decision["market_role"] = role
        scout.decisions.append(decision)
        if not published or len(title) < 18 or len(body) < 160:
            if article.cms_placeholder and not published:
                # External: the publisher served its CMS upgrade template
                # instead of an article header. Explicit, never a success.
                decision.update(status="pending", reason="publisher_cms_placeholder")
                scout.diagnostics.append({"code": "publisher_cms_placeholder", "url": url,
                                          "detail": "captured page carries the Sitefinity upgrade template "
                                                    "('Upgraded to Sitefinity {{currentVersion}}') and no "
                                                    "article publication field",
                                          "date_evidence": evidence, "external": True})
                continue
            decision.update(status="pending", reason=evidence if not published else "article_content_unrecognized")
            scout.diagnostics.append({"code": "detail_publication_evidence_missing" if not published else "article_content_unrecognized",
                                      "url": url, "detail": decision["reason"], "date_evidence": evidence})
            continue
        if (today - date.fromisoformat(published)).days > 90:
            decision.update(status="rejected", reason="outside_90_day_horizon")
            continue
        accepted_roles = scout.cfg.get("accepted_roles", (scout.cfg["role"],))
        if role not in accepted_roles:
            decision.update(status="rejected", reason="different_market_role", actual_role=role)
            continue
        accepted, reason = materiality(role, title, body)
        decision.update(status="candidate" if accepted else "rejected", reason=reason)
        rows.append(RawItem(scout.slug, title[:350], url, scout.cfg["name"], scout.cfg["type"],
                            event_date=published, raw_text=body[:1800], metadata={
                                "discovered_from": scout.cfg["page"], "page_text": body[:18000],
                                "market_role": role, "article_extraction": "occupational_v1",
                                "date_evidence": evidence, "publication_date": published,
                                "publication_date_source": evidence,
                                "publication_evidence": article.publication_evidence(today=today),
                                "provider_subtype": "centros" if role == "provider_achs_centers" else "clinicas" if role == "provider_achs" else None,
                                "source_quality_gate": "audit_pending_90_day", "materiality_accepted": accepted,
                                "materiality_reason": reason}))
    if truncated:
        scout.diagnostics.append({"code": "detail_limit_reached", "url": scout.cfg["page"],
                                  "detail": f"{truncated} distinct candidate details not fetched; max_items={max_items}"})
    if not attempted and not truncated:
        scout.diagnostics.append({"code": "listing_structure_unrecognized", "url": scout.cfg["page"], "detail": "No recognized detail links"})
    rows = sorted(rows, key=lambda r: r.event_date, reverse=True)
    if scout.diagnostics:
        scout.discovery_incomplete, scout.coverage_status = True, "incomplete"
        primary = scout.diagnostics[0]
        code = primary["code"] if len(scout.diagnostics) == 1 else "partial_detail_capture"
        raise SourceDiscoveryError(code, primary["url"], primary["detail"],
                                   diagnostics=scout.diagnostics, partial_items=rows)
    scout.coverage_status = "observed_page_complete"
    # Zero items for the requested role is a valid editorial outcome.
    return rows
