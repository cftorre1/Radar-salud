from __future__ import annotations
import re
from urllib.parse import urljoin, urlsplit, urlunsplit
from datetime import date
from dataclasses import asdict
from .models import RawItem
from .scouts import fetch_html
from .regulatory import _TableParser, _date

PAGES=[
 ("Informes de fiscalización","https://www.superdesalud.gob.cl/tax-otros-actos-de-la-superintendencia/informes-de-fiscalizacion-5126/","Sistema de salud","report"),
 ("Sanciones a Isapres","https://www.superdesalud.gob.cl/tax-fiscalizacion/resultados-de-la-fiscalizacion-3031/sanciones-aplicadas-5185/sanciones-a-isapres-6248/","Isapres","sanction"),
 ("Sanciones a Prestadores","https://www.superdesalud.gob.cl/tax-fiscalizacion/resultados-de-la-fiscalizacion-3031/sanciones-aplicadas-5185/sanciones-a-prestadores-6249/","Prestadores","sanction"),
 ("Resultados: informes de fiscalización","https://www.superdesalud.gob.cl/tax-fiscalizacion/resultados-de-la-fiscalizacion-3031/informes-de-fiscalizacion-3218/","Sistema de salud","report"),
 ("Sanciones a entidades acreditadoras","https://www.superdesalud.gob.cl/tax-fiscalizacion/resultados-de-la-fiscalizacion-3031/sanciones-aplicadas-5185/sanciones-a-entidades-acreditadoras-7059/","Entidades acreditadoras","sanction"),
 ("Sanciones a agentes de ventas","https://www.superdesalud.gob.cl/tax-fiscalizacion/resultados-de-la-fiscalizacion-3031/sanciones-aplicadas-5185/sanciones-agentes-de-ventas-7441/","Agentes de ventas","sanction"),
 ("Índice general de sanciones","https://www.superdesalud.gob.cl/tax-otros-actos-de-la-superintendencia/sanciones-aplicadas-5113/","Sistema de salud","sanction"),
]

AMOUNT_RE = re.compile(
    r"(?:multa\s+(?:de|por)|multa\s+impuesta\s+a)\s*(\d[\d.,]*)\s*"
    r"(UF|UTM|Unidades de Fomento|Unidades Tributarias Mensuales)", re.I)
ENTITY_PATTERNS = [
    re.compile(r"(?:a la Isapre|a Isapre)\s+(.+?)(?=\s+una\b|\s+por\b|,|$)", re.I),
    re.compile(r"(?:al prestador|por el prestador|a la prestadora)\s+[“\"']?(.+?)(?=[”\"']|,|\s+una\b|\s+en contra\b|\s+por\b|$)", re.I),
    re.compile(r"(?:a|al)\s+((?:Nueva )?Cl[ií]nica\s+.+?|Hospital\s+.+?|Centro\s+M[eé]dico.+?)(?=,|\s+por\b|$)", re.I),
]


def canonical_url(url):
    parts = urlsplit(url)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip('/'), '', ''))


def _entity(text):
    for pattern in ENTITY_PATTERNS:
        match = pattern.search(text or "")
        if match:
            return " ".join(match.group(1).strip(" \"'“”").split())[:160]
    return None


def _amount(text):
    match = AMOUNT_RE.search(text or "")
    if not match:
        return None, None
    value = float(match.group(1).replace(".", "").replace(",", "."))
    unit = match.group(2).upper()
    return value, "UTM" if "TRIBUT" in unit or unit == "UTM" else "UF"


def _valid_date(text):
    value = _date(text or "")
    try:
        return date.fromisoformat(value).isoformat()
    except (ValueError, TypeError):
        return None


def _emission_date(text):
    match = re.search(r"(?:Fecha\s+(?:de\s+)?emisi[oó]n|Emisi[oó]n)\s*:\s*([^|]{1,70})", text or "", re.I)
    return _valid_date(match.group(1)) if match else None


def parse_listing(html, page_name, page_url, scope, kind):
    """Read source columns independently; preserve contradictory source dates."""
    parser = _TableParser()
    parser.feed(html)
    out = []
    seen = set()
    columns = {}
    for row in parser.rows:
        cells = [cell.get("text", "") for cell in row]
        if len(cells) < 3:
            continue
        if 'fecha de publicación' in cells[0].casefold():
            columns = {name.casefold(): index for index, name in enumerate(cells)}
            continue
        publication_date = _valid_date(cells[0])
        if not publication_date:
            continue
        title_index = columns.get('título', 2 if kind == "sanction" and len(row) >= 5 else 1)
        summary_index = columns.get('resumen y modificaciones', 3 if kind == "sanction" and len(row) >= 5 else 2)
        title_cell = row[title_index]
        summary = cells[summary_index]
        title = title_cell.get("text", "")
        pdf = detail = None
        for href, label in title_cell.get("links", []):
            absolute = urljoin(page_url, href)
            if urlsplit(absolute).scheme not in ("http", "https"):
                continue
            if ".pdf" in absolute.lower():
                pdf = absolute
            elif re.search(r"informe|instrucci[oó]n|resoluci[oó]n|resultados?", label, re.I):
                detail = absolute
                title = label
        if not (detail or pdf) or not re.search(r"informe|instrucci[oó]n|resoluci[oó]n|resultados?", title, re.I):
            continue
        url = canonical_url(detail or pdf)
        if url in seen:
            continue
        seen.add(url)
        title_date = _emission_date(title)
        summary_date = _emission_date(summary)
        emission_date = title_date or summary_date
        conflicts = []
        if title_date and summary_date and title_date != summary_date:
            conflicts.append("emission_dates_disagree")
        if emission_date and publication_date < emission_date:
            conflicts.append("publication_precedes_emission")
        entity_index = next((index for name, index in columns.items()
            if any(word in name for word in ('prestador', 'isapre', 'agente', 'acreditadora'))), None)
        entity_column = cells[entity_index].strip() if entity_index is not None else (
            cells[1].strip() if kind == "sanction" and len(cells) >= 5 else '')
        entity = entity_column or _entity(summary)
        item_scope = scope
        if kind == "report":
            low = (title + " " + summary).casefold()
            if "prestador" in low or "intendencia de prestadores" in low:
                item_scope = "Prestadores"
            elif "isapre" in low:
                item_scope = "Isapres"
        amount, unit = _amount(summary)
        low = summary.casefold()
        effect = ("revocation" if any(term in low for term in ('dejando sin efecto', 'dejar sin efecto', 'deja sin efecto')) else
                  "amendment" if "rebajando" in low or "reemplazando" in low else
                  "registration_cancellation" if 'cancél' in low or 'cancel' in low else
                  "warning" if any(term in low for term in ('amonesta', 'amonsta', 'censúr', 'censure')) else "sanction")
        asset_aliases=[canonical_url(urljoin(page_url,href)) for href,_ in title_cell.get('links',[])
            if re.search(r'\.(?:jpg|jpeg|png)(?:\?|$)',href,re.I)]
        out.append(RawItem("superintendencia_fiscalizacion", title, url,
            "Superintendencia de Salud", "official", event_date=emission_date or publication_date,
            raw_text=summary, metadata={
                "listing_url": page_url, "listing_name": page_name, "scope": item_scope,
                "fiscalization_kind": kind, "fiscalization_topic": cells[columns['materia']] if 'materia' in columns else (cells[-1] if kind == "sanction" and len(cells)>=5 else None),
                "regulated_entity": entity, "actor_evidence": "entity_column" if entity_column else "summary",
                "sanction_amount": amount, "sanction_unit": unit, "sanction_effect": effect,
                "publication_date": publication_date, "emission_date": emission_date,
                "event_date_basis": "emission" if emission_date else "publication", "date_conflicts": conflicts,
                "attachments": [{"url": pdf, "label": "PDF"}] if pdf else [],
                **({'listing_asset_aliases':asset_aliases} if asset_aliases else {}),
            }))
    return out


class SuperintendenciaFiscalizacionScout:
    SOURCE_SLUG = "superintendencia_fiscalizacion"
    SOURCE_NAME = "Superintendencia de Salud"
    SOURCE_TYPE = "official"

    def discover(self):
        import json
        from .paths import project_root
        reviews_path=project_root()/'config/fiscalization_editorial_reviews.json'
        all_reviews=json.loads(reviews_path.read_text()) if reviews_path.exists() else {}
        primary_reviews=all_reviews.get('primary_document_reviews',{})
        out = {}
        self.surface_results = []
        for page_name, page_url, scope, kind in PAGES:
            try:
                items = parse_listing(fetch_html(page_url), page_name, page_url, scope, kind)
                if not items:
                    raise ValueError("Fiscalization table has no identifiable dated documents")
                self.surface_results.append({"url": page_url, "status": "parsed", "documents": len(items)})
                for raw in items:
                    if raw.url in primary_reviews:
                        raw=reviewed_primary_act(raw,primary_reviews)
                    if raw.url in out:
                        previous = out[raw.url]
                        previous.metadata['listing_urls'] = sorted(set(previous.metadata.get('listing_urls', [previous.metadata['listing_url']]) + [page_url]))
                        if previous.metadata['publication_date'] != raw.metadata['publication_date']:
                            previous.metadata.setdefault('date_conflicts', []).append('listing_publication_dates_disagree')
                    else:
                        out[raw.url] = raw
            except Exception as exc:
                self.surface_results.append({"url": page_url, "status": "error", "error": type(exc).__name__})
        if not out:
            raise RuntimeError("No SIS fiscalization surface parsed successfully")
        for review in all_reviews.get('historical_identity_reviews',{}).values():
            urls=review['urls']
            if (review.get('decision')=='one_verified_primary_act_two_listing_aliases'
                and all(url in out for url in urls)
                and all(review['primary_document_url'] in {a['url'] for a in out[url].metadata.get('attachments',[])} for url in urls)):
                primary=out[urls[0]]
                primary.metadata.update(primary_identity_review=review,
                    primary_alias_observations=[asdict(out[url]) for url in urls[1:]])
                for url in urls[1:]:del out[url]
        return sorted(out.values(), key=lambda raw: raw.event_date or "", reverse=True)

def reviewed_primary_act(raw, primary_reviews=None):
    """Resolve only an exact, documented primary-source review; keep observations."""
    import json
    from dataclasses import replace
    from .paths import project_root
    if primary_reviews is None:
        path = project_root() / 'config/fiscalization_editorial_reviews.json'
        reviews = json.loads(path.read_text()) if path.exists() else {}
        primary_reviews=reviews.get('primary_document_reviews', {})
    review = primary_reviews.get(canonical_url(raw.url))
    if not review or review.get('decision') != 'publish_fiscalization':
        return raw
    documents = {canonical_url(a['url']) for a in raw.metadata.get('attachments', [])}
    if (raw.metadata.get('primary_document_review') == review
        and canonical_url(review['primary_document_url']) in documents
        and raw.metadata.get('emission_date') == review['emission_date']
        and raw.metadata.get('publication_date') == (None if review.get('publication_unreliable', True) else review.get('observed_listing_publication_date'))):
        # Scout, processor and stock reconciliation share this function. Applying
        # the same review twice must retain the actual listing observation.
        return raw
    if (canonical_url(review['primary_document_url']) not in documents or
        not re.fullmatch(r'[a-f0-9]{64}', review.get('primary_document_sha256', '')) or
        raw.metadata.get('emission_date') != review['emission_date'] or
        raw.metadata.get('publication_date') != review.get('observed_listing_publication_date')):
        return raw
    metadata = {**raw.metadata, 'primary_document_review': review,
        'observed_listing_publication_date': raw.metadata.get('publication_date'),
        'observed_listing_regulated_entity':raw.metadata.get('regulated_entity'),
        'observed_listing_summary':raw.raw_text,
        'observed_date_conflicts': raw.metadata.get('date_conflicts', []),
        'publication_date': None if review.get('publication_unreliable', True) else raw.metadata.get('publication_date'), 'emission_date': review['emission_date'],
        'event_date_basis': 'verified_primary_emission' if review.get('emission_date') else 'publication', 'date_conflicts': [],
        'date_reconciliation': 'primary_emission_verified; listing_publication_unreliable' if review.get('publication_unreliable',True) else 'primary_actor_effect_verified',
        'regulated_entity': review['regulated_entity'], 'actor_evidence': 'verified_primary_document',
        'sanction_amount': review['sanction_amount'], 'sanction_unit': review['sanction_unit'],
        'fact_date': review.get('fact_date'), 'validity_text': review.get('validity_text')}
    for field in ('fiscalization_topic','related_entities','replaced_fine_amount','replaced_fine_unit','fact_period','key_points','why_it_matters','scopes'):
        if field in review:metadata[field]=review[field]
    metadata['sanction_effect']=review.get('effect',metadata.get('sanction_effect'))
    return replace(raw, event_date=review.get('emission_date') or raw.event_date, raw_text=review.get('what_happened') or raw.raw_text, metadata=metadata)


def process_fiscalizacion(raw,cfg):
    from .pipeline import build_signal
    from .processing import RejectedProcessing, DeferredProcessing
    raw = reviewed_primary_act(raw)
    if raw.metadata.get("date_conflicts"):
        raise RejectedProcessing("source_date_conflict_requires_review")
    if not raw.event_date:
        raise DeferredProcessing("missing_verified_fiscalization_date")
    kind=raw.metadata.get("fiscalization_kind")
    scope=raw.metadata.get("scope") or "Sistema de salud"
    entity=raw.metadata.get("regulated_entity")
    topic=raw.metadata.get("fiscalization_topic")
    amount=raw.metadata.get("sanction_amount");unit=raw.metadata.get("sanction_unit")
    if kind=="sanction":
        if not entity:
            raise DeferredProcessing("missing_verified_regulated_entity")
        bits=[]
        if entity:bits.append(entity)
        if amount and unit:bits.append(f"{amount:g} {unit}")
        if topic:bits.append(topic)
        effect = raw.metadata.get("sanction_effect", "sanction")
        subject = topic or "la materia descrita en la resolución"
        why = (f"{entity}: la resolución {'modifica una sanción anterior' if effect in ('amendment', 'revocation') else 'documenta una medida de cumplimiento'} "
               f"en {subject}. Permite revisar el incumplimiento y el efecto exacto del acto en la fuente oficial.")
        raw.metadata.update({"what_happened":raw.raw_text or raw.title,"why_it_matters":why,
          "signal_types":["Fiscalización"],"scopes":[scope],"event_type":{"amendment":"SANCTION_AMENDMENT","revocation":"SANCTION_REVOCATION","fine_replaced_by_registration_cancellation":"SANCTION_SUBSTITUTION","registration_cancellation":"REGISTRATION_CANCELLATION","warning":"SANCTION_WARNING"}.get(effect,"SANCTION"),
          "watch_tags":["fiscalización","sanción",scope.lower()]+([topic.lower()] if topic else []),
          "scores":{"economic":65 if amount else 50,"regulatory":88,"scope":72,"novelty":70,"actionability":84}})
    else:
        raw.metadata.update({"what_happened":raw.raw_text or raw.title,
          "why_it_matters":raw.metadata.get('why_it_matters') or "Muestra qué materias, procesos o actores está revisando la Superintendencia y qué hallazgos está observando, una señal útil para anticipar focos de cumplimiento.",
          "signal_types":["Fiscalización"],"scopes":[scope],"event_type":"FISCALIZATION_REPORT",
          "watch_tags":["fiscalización","informe",scope.lower()],
          "scores":{"economic":55,"regulatory":90,"scope":78,"novelty":75,"actionability":88}})
    s=build_signal(raw,cfg);row=s.to_dict()
    row["signal_types"]=["Fiscalización"];row["scopes"]=raw.metadata.get('primary_document_review',{}).get('scopes') or [scope]
    row["regulated_entity"]=entity;row["sanction_amount"]=amount;row["sanction_unit"]=unit
    row.update(publication_date=raw.metadata.get("publication_date"), emission_date=raw.metadata.get("emission_date"),
        event_date_basis=raw.metadata.get("event_date_basis"), date_conflicts=raw.metadata.get("date_conflicts", []),
        sanction_effect=raw.metadata.get("sanction_effect"),actor_evidence=raw.metadata.get("actor_evidence"))
    for field in ('observed_listing_publication_date', 'observed_listing_regulated_entity','observed_listing_summary','observed_date_conflicts', 'date_reconciliation', 'primary_document_review', 'fact_date', 'fact_period','validity_text','related_entities','replaced_fine_amount','replaced_fine_unit'):
        if field in raw.metadata:
            row[field] = raw.metadata[field]
    row["fiscalization_topic"]=topic;row["source_documents"]=raw.metadata.get("attachments",[])
    return row


# A visible card title must say what the act does, never only its legal identity.
BARE_ACT_TITLE_RE = re.compile(r"^(Circular|Resolución|Oficio|Decreto).*N°\s*\d+$", re.I)
_ACT_LABEL_RE = re.compile(
    r"\b(Resolución(?:\s+Exenta)?|Circular|Oficio(?:\s+Ord(?:inario)?)?|Decreto)\s+(?:(IF|IP)\s*[/\-]?\s*)?N?[°º]?\s*([\d\.]+)", re.I)
# Captured listing summaries state the infringement after "por": keep that clause verbatim.
_GROUND_RE = re.compile(
    r"\bpor\s+((?:haber\s+)?(?:infring|incumpl|vulner|transgred|no\s+haber)[^.]*?)(?=\.\s|\.$|\s*Fecha de emisi[oó]n|$)", re.I)
_DATE_FRAGMENT_RE = re.compile(r",?\s*de\s+\d{1,2}\s+de\s+[a-záéíóú]+\s+de\s+\d{4}", re.I)


def is_bare_act_title(title):
    return bool(BARE_ACT_TITLE_RE.match(" ".join(str(title or "").split())))


def sanction_card_title(r):
    """Deterministic descriptive title for an individual sanction card.

    Uses only captured fields: the act identity, sanctioned entity, amount and
    either the reviewed topic or the infringement clause of the regulator's own
    summary. Returns None when that data is missing; the caller must then hold
    the card instead of publishing the bare act identity.
    """
    title = " ".join(str(r.get("title") or "").split())
    m = _ACT_LABEL_RE.search(title)
    entity = " ".join(str(r.get("regulated_entity") or "").split())
    if not m or not entity:
        return None
    kind = " ".join(m.group(1).split())
    prefix = (m.group(2) or "").upper()
    label = f"{kind} {prefix + '/' if prefix else ''}N°{m.group(3)}"
    event_type = str(r.get("event_type") or "")
    amount, unit = r.get("sanction_amount"), str(r.get("sanction_unit") or "").strip()
    if event_type == "SANCTION" and isinstance(amount, (int, float)) and not isinstance(amount, bool) and amount > 0 and unit:
        action = f"Multa de {amount:g} {unit} a {entity}"
    elif event_type == "SANCTION":
        action = f"Sanción a {entity}"
    elif event_type == "SANCTION_WARNING":
        action = f"Amonestación a {entity}"
    else:
        return None  # amendments, revocations and substitutions need their own reviewed wording
    topic = " ".join(str(r.get("fiscalization_topic") or "").split()).strip(" .")
    if topic:
        out = f"{label} · {action}: {topic}"
    else:
        g = _GROUND_RE.search(" ".join(str(r.get("what_happened") or "").split()))
        if not g:
            return None
        ground = _DATE_FRAGMENT_RE.sub("", g.group(1))
        ground = re.sub(r"\s+,", ",", re.sub(r",\s*,", ",", ground)).strip(" ,;:")
        if not ground:
            return None
        out = f"{label} · {action} por {ground}"
    return None if is_bare_act_title(out) else out
