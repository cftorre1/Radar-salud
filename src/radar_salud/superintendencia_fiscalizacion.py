from __future__ import annotations
import re
from urllib.parse import urljoin, urlsplit, urlunsplit
from datetime import date
from .models import RawItem
from .scouts import fetch_html
from .regulatory import _TableParser, _date

PAGES=[
 ("Informes de fiscalización","https://www.superdesalud.gob.cl/tax-otros-actos-de-la-superintendencia/informes-de-fiscalizacion-5126/","Sistema de salud","report"),
 ("Sanciones a Isapres","https://www.superdesalud.gob.cl/tax-fiscalizacion/resultados-de-la-fiscalizacion-3031/sanciones-aplicadas-5185/sanciones-a-isapres-6248/","Isapres","sanction"),
 ("Sanciones a Prestadores","https://www.superdesalud.gob.cl/tax-fiscalizacion/resultados-de-la-fiscalizacion-3031/sanciones-aplicadas-5185/sanciones-a-prestadores-6249/","Prestadores","sanction"),
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
    for row in parser.rows:
        cells = [cell.get("text", "") for cell in row]
        if len(cells) < 3:
            continue
        publication_date = _valid_date(cells[0])
        if not publication_date:
            continue
        title_cell = row[2] if kind == "sanction" and len(row) >= 5 else row[1]
        summary = cells[3] if kind == "sanction" and len(row) >= 5 else cells[2]
        title = title_cell.get("text", "")
        pdf = detail = None
        for href, label in title_cell.get("links", []):
            absolute = urljoin(page_url, href)
            if urlsplit(absolute).scheme not in ("http", "https"):
                continue
            if ".pdf" in absolute.lower():
                pdf = absolute
            elif re.search(r"informe|instrucci[oó]n|resoluci[oó]n|resultados", label, re.I):
                detail = absolute
                title = label
        if not (detail or pdf) or not re.search(r"informe|instrucci[oó]n|resoluci[oó]n|resultados", title, re.I):
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
        entity = (cells[1].strip() if kind == "sanction" and len(cells) >= 5 else "") or _entity(summary)
        item_scope = scope
        if kind == "report":
            low = (title + " " + summary).casefold()
            if "prestador" in low or "intendencia de prestadores" in low:
                item_scope = "Prestadores"
            elif "isapre" in low:
                item_scope = "Isapres"
        amount, unit = _amount(summary)
        low = summary.casefold()
        effect = ("revocation" if "dejando sin efecto" in low or "dejar sin efecto" in low else
                  "amendment" if "rebajando" in low or "reemplazando" in low else
                  "warning" if "amonesta" in low else "sanction")
        out.append(RawItem("superintendencia_fiscalizacion", title, url,
            "Superintendencia de Salud", "official", event_date=emission_date or publication_date,
            raw_text=summary, metadata={
                "listing_url": page_url, "listing_name": page_name, "scope": item_scope,
                "fiscalization_kind": kind, "fiscalization_topic": cells[-1] if kind == "sanction" else None,
                "regulated_entity": entity, "actor_evidence": "entity_column" if kind == "sanction" and cells[1].strip() else "summary",
                "sanction_amount": amount, "sanction_unit": unit, "sanction_effect": effect,
                "publication_date": publication_date, "emission_date": emission_date,
                "event_date_basis": "emission" if emission_date else "publication", "date_conflicts": conflicts,
                "attachments": [{"url": pdf, "label": "PDF"}] if pdf else [],
            }))
    return out


class SuperintendenciaFiscalizacionScout:
    SOURCE_SLUG = "superintendencia_fiscalizacion"
    SOURCE_NAME = "Superintendencia de Salud"
    SOURCE_TYPE = "official"

    def discover(self):
        out = {}
        self.surface_results = []
        for page_name, page_url, scope, kind in PAGES:
            try:
                items = parse_listing(fetch_html(page_url), page_name, page_url, scope, kind)
                if not items:
                    raise ValueError("Fiscalization table has no identifiable dated documents")
                self.surface_results.append({"url": page_url, "status": "parsed", "documents": len(items)})
                for raw in items:
                    out.setdefault(raw.url, raw)
            except Exception as exc:
                self.surface_results.append({"url": page_url, "status": "error", "error": type(exc).__name__})
        if not out:
            raise RuntimeError("No SIS fiscalization surface parsed successfully")
        return sorted(out.values(), key=lambda raw: raw.event_date or "", reverse=True)

def process_fiscalizacion(raw,cfg):
    from .pipeline import build_signal
    from .processing import RejectedProcessing, DeferredProcessing
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
          "signal_types":["Fiscalización"],"scopes":[scope],"event_type":{"amendment":"SANCTION_AMENDMENT","revocation":"SANCTION_REVOCATION"}.get(effect,"SANCTION"),
          "watch_tags":["fiscalización","sanción",scope.lower()]+([topic.lower()] if topic else []),
          "scores":{"economic":65 if amount else 50,"regulatory":88,"scope":72,"novelty":70,"actionability":84}})
    else:
        raw.metadata.update({"what_happened":raw.raw_text or raw.title,
          "why_it_matters":"Muestra qué materias, procesos o actores está revisando la Superintendencia y qué hallazgos está observando, una señal útil para anticipar focos de cumplimiento.",
          "signal_types":["Fiscalización"],"scopes":[scope],"event_type":"FISCALIZATION_REPORT",
          "watch_tags":["fiscalización","informe",scope.lower()],
          "scores":{"economic":55,"regulatory":90,"scope":78,"novelty":75,"actionability":88}})
    s=build_signal(raw,cfg);row=s.to_dict()
    row["signal_types"]=["Fiscalización"];row["scopes"]=[scope]
    row["regulated_entity"]=entity;row["sanction_amount"]=amount;row["sanction_unit"]=unit
    row.update(publication_date=raw.metadata.get("publication_date"), emission_date=raw.metadata.get("emission_date"),
        event_date_basis=raw.metadata.get("event_date_basis"), date_conflicts=raw.metadata.get("date_conflicts", []),
        sanction_effect=raw.metadata.get("sanction_effect"),actor_evidence=raw.metadata.get("actor_evidence"))
    row["fiscalization_topic"]=topic;row["source_documents"]=raw.metadata.get("attachments",[])
    return row
