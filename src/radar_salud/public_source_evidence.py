"""Publication provenance for the five public-data source lanes.

A dataset period, filename, upload directory or HTTP modification date is not
publication evidence. Every accepted date is bound to an official surface.
"""
from __future__ import annotations

from datetime import date, datetime
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo


HOSTS = {
    "fonasa": {"www.fonasa.gob.cl", "fonasa.gob.cl", "www.fonasa.cl", "fonasa.cl"},
    "fonasa_datos_abiertos": {"datosabiertos.fonasa.cl", "www.datosabiertos.fonasa.cl"},
    "isp_anamed": {"www.ispch.gob.cl", "ispch.gob.cl", "www.ispch.cl", "ispch.cl"},
    "isp_surveillance": {"www.ispch.gob.cl", "ispch.gob.cl", "www.ispch.cl", "ispch.cl"},
    "deis": {"deis.minsal.cl", "repositoriodeis.minsal.cl", "datos.gob.cl"},
}
DATE_SOURCES = {
    "article:published_time", "datePublished", "jsonld.datePublished",
    "official_listing_date_cell", "listing:fecha_publicacion", "detail:published_time",
    "official_document_listing:published", "official_document_listing:updated",
}
DETAIL_KINDS = {"article:published_time", "datePublished", "jsonld.datePublished", "detail:published_time"}


def publication_field_date(value: str, kind: str) -> str | None:
    value = str(value).strip()
    iso = re.fullmatch(r"20\d{2}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?)?", value)
    numeric = re.fullmatch(r"\d{1,2}[/-]\d{1,2}[/-]20\d{2}", value)
    spanish = re.fullmatch(r"\d{1,2}\s+(?:de\s+)?[a-záéíóú]+,?\s+(?:de\s+)?20\d{2}", value, re.I)
    notice = re.fullmatch(r"(?:publicad[oa]|actualizad[oa]|actualizaci[oó]n)\s*(?:el\s+|:\s*)?\d{1,2}[/-]\d{1,2}[/-]20\d{2}", value, re.I)
    if kind in {"article:published_time", "datePublished", "jsonld.datePublished"} and not iso:return None
    if kind == "detail:published_time" and not (iso or numeric or spanish):return None
    if kind in {"official_listing_date_cell", "listing:fecha_publicacion"} and not (numeric or spanish):return None
    if kind.startswith("official_document_listing:") and not (notice or numeric or spanish):return None
    if notice and kind == "official_document_listing:published" and not value.lower().startswith("publicad"):
        return None
    if notice and kind == "official_document_listing:updated" and value.lower().startswith("publicad"):
        return None
    try:
        if iso:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
        if notice or numeric:
            match=re.search(r"(\d{1,2})[/-](\d{1,2})[/-](20\d{2})",value)
            day,month,year=map(int,match.groups())
        else:
            match=re.fullmatch(r"(\d{1,2})\s+(?:de\s+)?([a-záéíóú]+),?\s+(?:de\s+)?(20\d{2})",value,re.I)
            months={"enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,
                    "julio":7,"agosto":8,"septiembre":9,"setiembre":9,"octubre":10,"noviembre":11,"diciembre":12}
            day,month,year=int(match[1]),months[match[2].lower()],int(match[3])
        return date(year,month,day).isoformat()
    except (TypeError,ValueError,KeyError,AttributeError):return None


def chile_today() -> date:
    return datetime.now(ZoneInfo("America/Santiago")).date()


def official_url(url: str, slug: str) -> bool:
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == "https" and parsed.hostname in HOSTS.get(slug, set())
                and parsed.port in (None, 443) and not parsed.username and not parsed.password)
    except (ValueError, TypeError):
        return False


def verified_publication(raw, *, today: date | None = None) -> bool:
    """Validate date provenance before fetching, enriching or evaluating content."""
    if not official_url(raw.url, raw.source_slug) or raw.source_type != "official":
        return False
    evidence = raw.metadata.get("publication_date_evidence")
    if not isinstance(evidence, dict):
        return False
    kind = evidence.get("kind")
    if kind not in DATE_SOURCES or raw.metadata.get("publication_date_source") != kind:
        return False
    if evidence.get("date") != raw.event_date or not str(evidence.get("value") or "").strip():
        return False
    if not official_url(evidence.get("url"), raw.source_slug):
        return False
    if kind in DETAIL_KINDS and evidence["url"] != raw.url:
        link_evidence=raw.metadata.get("publication_document_link_evidence") or {}
        if not (raw.source_slug == "isp_surveillance"
                and raw.metadata.get("publication_detail_url") == evidence["url"]
                and raw.metadata.get("document_detail_url") == evidence["url"]
                and raw.metadata.get("publication_document_url") == raw.url
                and isinstance(link_evidence,dict)
                and link_evidence.get("detail_url") == evidence["url"]
                and link_evidence.get("document_url") == raw.url
                and str(raw.url).lower().endswith(".pdf")):
            return False
    if kind not in DETAIL_KINDS and evidence["url"] != raw.metadata.get("discovered_from"):
        return False
    try:
        day = date.fromisoformat(raw.event_date)
        declared = publication_field_date(evidence["value"], kind)
        return (declared == raw.event_date and day.isoformat() == raw.event_date
                and day <= (today or chile_today()))
    except (TypeError, ValueError):
        return False


def failure_details(exc: Exception) -> dict:
    """Keep the exact transport cause without credentials or query parameters."""
    chain = []
    current = exc
    seen = set()
    while current is not None and id(current) not in seen and len(chain) < 5:
        seen.add(id(current))
        row = {"type": type(current).__name__}
        if isinstance(current, HTTPError):
            row["http_status"] = current.code
            parsed = urlsplit(current.url)
            row["url"] = urlunsplit((parsed.scheme, parsed.hostname or "", parsed.path, "", ""))
            row["reason"] = str(current.reason)[:300]
        elif isinstance(current, URLError):
            row["reason"] = str(current.reason)[:300]
        elif isinstance(current, (TimeoutError, ConnectionError)):
            row["reason"] = str(current)[:300]
        elif isinstance(current, ValueError):
            row["reason"] = str(current)[:300]
        chain.append(row)
        current = current.__cause__ or current.__context__
    result={"exception_chain": chain, "failure_signature": " > ".join(
        entry["type"] + (":" + str(entry["http_status"]) if "http_status" in entry else "")
        + (":" + entry["reason"] if entry.get("reason") else "") for entry in chain)}
    surfaces=getattr(exc,"diagnostics",None)
    if isinstance(surfaces,list):
        failures=[{"url":row.get("url"),"type":row.get("exception"),"reason":row.get("message")}
                  for row in surfaces if row.get("exception")]
        if failures:
            result["endpoint_failures"]=failures
            result["failure_signature"]+=" > "+"; ".join(
                str(row["type"])+":"+str(row["reason"]) for row in failures)
    if "Tunnel connection failed: 403" in result["failure_signature"]:
        result["transport_stage"]="proxy_connect_rejected"
        result["origin_tls_observed"]=False
    return result


def discovery_diagnostics(scout, items=None) -> dict:
    diagnostics = getattr(scout, "diagnostics", None)
    if isinstance(diagnostics, dict):
        result = dict(diagnostics)
    elif isinstance(diagnostics, list):
        result = {"surfaces": diagnostics, "partial_failure": any(
            row.get("status") == "blocked" or row.get("exception") for row in diagnostics)}
    else:
        result = {}
    if items is not None:
        dates = [item.event_date for item in items if verified_publication(item)]
        result["verified_publications"] = len(dates)
        result["latest_verified_publication_date"] = max(dates) if dates else None
    return result
