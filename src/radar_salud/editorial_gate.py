from __future__ import annotations
import re
from typing import Any, Dict, Tuple

from .editorial_rules_v2 import evaluate_editorial_v2

_BINARY=("%pdf-"," endobj"," endstream","/resources ","/contents "," obj <"," stream ")
_HTML=("<a ","<script","<style",'target="_blank"',"schema.org")
_GENERIC=("formaliza un cambio normativo o legal del sector salud","aporta información oficial reciente","describe un cambio material para una parte relevante del sistema de salud")
_UNRELATED=("no hay antecedentes que permitan vincularla con el sector salud", "no se relaciona con el sector salud", "sin vínculo con el sector salud")
_MINSAL_NOISE=("renuncia","nombramiento","nombra,","nombra a","nombra mediante","designa","designación","designacion","asume como","alta dirección pública","alta direccion publica","nuevo subsecretario","nueva subsecretaria","seremi","director del servicio de salud","directora del servicio de salud","visita nuevo","visita el","visita la","continúa recorrido","continua recorrido","conmemora","participa en","trayectoria","historia del ministerio")

def _text(r:Dict[str,Any])->str:return " ".join(str(r.get(k,"") or "") for k in ("title","what_happened","why_it_matters"))
def has_garbage(r:Dict[str,Any])->bool:
    t=_text(r).lower();return any(x in t for x in _BINARY+_HTML) or t.count("�")>=3

def is_minsal_noise(r:Dict[str,Any])->bool:
    if r.get("source_name")!="Ministerio de Salud":return False
    t=_text(r).lower()
    if any(x in t for x in _MINSAL_NOISE):return True
    if any(x in t for x in ("alerta alimentaria","retiro de producto","lote de","marca ")) and int(r.get("editorial_relevance") or 0)<80:return True
    return False

# Regulator institutional agenda (Dirección 27-oct-2026): attending sessions or
# working tables is not market intelligence. Material outcomes ("presenta
# avances", "fiscaliza", "sanciona", "instruye") are not matched.
_AGENDA=re.compile(r"\b(participa|particip[óo]) (en|de)\b|\bse reúne\b|\bse reuni[óo]\b|\bconmemora\b|\bsaluda a\b|\bcelebra (su|el|la)\b",re.I)
_REGULATORS=("Superintendencia de Seguridad Social (SUSESO)","Superintendencia de Salud","Ministerio de Salud")

def is_institutional_agenda(r:Dict[str,Any])->bool:
    return r.get("source_name") in _REGULATORS and bool(_AGENDA.search(str(r.get("title") or "")))

# Health must be the main subject of a general-press piece (Dirección 27-oct-2026):
# the automated summary must not rescue a story about something else through an
# incidental health angle. The title carries the subject; terms live in config.
def _nexus_config()->Dict[str,Any]:
    import json
    from pathlib import Path
    p=Path(__file__).resolve().parents[2]/"config"/"editorial_health_nexus.json"
    try:return json.loads(p.read_text(encoding="utf-8"))
    except (OSError,ValueError):return {}

_NEXUS=None
_GROUP_URLS=None
# Feed-relevance withdrawals: a card leaves the feed; its provenance stays valid.
RELEVANCE_WITHDRAWAL_REASONS=frozenset({"health_not_main_subject"})
# Snapshots exported before this instant predate the relevance rule (Dirección 27-oct-2026).
RELEVANCE_RULE_SINCE="2026-10-27T16:00:00"

def _nexus_regex():
    global _NEXUS
    if _NEXUS is None:
        cfg=_nexus_config();terms=cfg.get("title_terms") or [];whole=cfg.get("whole_word_terms") or []
        alts=[re.escape(t) for t in sorted(terms,key=len,reverse=True)]+[re.escape(t)+r"(?![\w])" for t in whole]
        _NEXUS=(set(cfg.get("applies_to_source_types") or []),
                re.compile(r"(?<![\w])(?:"+"|".join(alts)+r")",re.I) if alts else None)
    return _NEXUS

def _story_member_urls()->set:
    global _GROUP_URLS
    if _GROUP_URLS is None:
        from datetime import date
        from pathlib import Path
        from .story_groups import CONFIG
        import json
        try:groups=json.loads((Path(__file__).resolve().parents[2]/CONFIG).read_text(encoding="utf-8")).get("groups",[])
        except (OSError,ValueError):groups=[]
        today=date.today().isoformat()
        _GROUP_URLS={u for g in groups if isinstance(g,dict) and str(g.get("review_by") or "9999")>=today
                     for u in g.get("member_urls") or []}
    return _GROUP_URLS

def title_has_health_nexus(title:str)->bool:
    _,rx=_nexus_regex()
    return rx is None or bool(rx.search(str(title or "")))

def health_not_main_subject(r:Dict[str,Any])->bool:
    types,rx=_nexus_regex()
    if rx is None or r.get("source_type") not in types:return False
    if r.get("source_url") in _story_member_urls():
        return False  # covered by a reviewed, current synthesis that links it
    return not (title_has_health_nexus(r.get("display_title") or "") or title_has_health_nexus(r.get("title") or ""))

_DO_TITLE=re.compile(r"^(?:Extracto de\s+)?(?:Ley|Decreto|Resoluci[oó]n|Circular|Reglamento)\b",re.I)
def malformed_official_listing_title(r:Dict[str,Any])->bool:
    """Diario Oficial titles built by the old reader can carry markup or the previous act
    ("Ver PDF (CVE-…)", '"> ', 'reach -->'). Such cards are held until rebuilt (audit 27-oct-2026)."""
    if r.get("source_name")!="Diario Oficial":return False
    t=str(r.get("title") or "")
    truncated_id=re.search(r"n[uú]mero\s+(?:[A-Z]{1,3}[ -]?)?\d{1,2}$",t.strip(),re.I) is not None
    return (not _DO_TITLE.match(t) or "Ver PDF" in t or "<" in t or "-->" in t or 'dotted"' in t or truncated_id)

def invalid_validity(r:Dict[str,Any])->bool:
    v=str(r.get("validity_text") or "").lower();return any(x in v for x in ('nj:','"529"','"535"','propertyvalue','javascript','schema.org'))

def quality_score(r:Dict[str,Any])->int:
    q=100
    if not r.get("event_date"):q-=18
    if not r.get("source_url"):q-=15
    if len(str(r.get("title") or "").strip())<12:q-=20
    if str(r.get("editorial_schema_version"))!="3":
        if len(str(r.get("what_happened") or "").strip())<35:q-=20
        if len(str(r.get("why_it_matters") or "").strip())<35:q-=15
    why=" ".join(str(r.get("why_it_matters") or "").lower().split())
    if any(x in why for x in _GENERIC):q-=18
    if has_garbage(r):q-=80
    if is_minsal_noise(r):q-=80
    return max(0,q)

def publication_ready(r:Dict[str,Any])->Tuple[bool,str,int]:
    if str(r.get("editorial_schema_version"))=="3":
        from .editorial_v3 import validate_depth
        from .normative_dates import legal_dates
        legal=legal_dates(r)
        if legal["hold_reason"] or str(r.get("event_type") or "").startswith("SANCTION") and legal["event_date"]!=r.get("event_date"):
            return False,"HOLD_DATE",0
        depth=validate_depth(r)
        if not depth["ok"]:return False,"editorial_v3_"+depth["reason_codes"][0],0
    review = r.get("editorial_review") or {}
    if isinstance(review, dict) and review.get("schema_version") == "pulso_editorial_review_v1" and review.get("decision") in {"reject", "group"}:
        return False, "pulso_independent_editorial_" + review["decision"], quality_score(r)
    if invalid_validity(r):
        if str(r.get("editorial_schema_version"))=="3":
            return False,"editorial_v3_invalid_validity",0
        r["validity_text"]=None
    if "Normativa" in (r.get("signal_types") or []) and (r.get("event_type")=="REGULATION" or r.get("normative_document_label") or r.get("legal_identity")):
        title=str(r.get("display_title") or r.get("title") or "")
        identity=str(r.get("legal_identity") or r.get("normative_document_label") or "")
        if r.get("normative_title_review_required") or not identity or identity.casefold() not in title.casefold() or not str(r.get("normative_context") or r.get("detail_body") or "").strip():
            return False,"normative_title_needs_review",0
    q=quality_score(r)
    if has_garbage(r):return False,"binary_or_markup",q
    if is_minsal_noise(r):return False,"editorial_noise",q
    if is_institutional_agenda(r):return False,"institutional_agenda",q
    if health_not_main_subject(r):return False,"health_not_main_subject",q

    if malformed_official_listing_title(r):return False,"malformed_official_listing_title",q
    why=str(r.get("why_it_matters") or "").lower()
    what=str(r.get("what_happened") or "").lower()
    if any(x in why for x in _UNRELATED):return False,"unrelated_to_health",q
    if any(x in why for x in _GENERIC):return False,"generic_impact",q
    if "[…]" in what or what.rstrip().endswith("[…]"):return False,"truncated_summary",q
    if not r.get("source_url"):return False,"missing_source",q
    if not r.get("event_date") and r.get("source_name") in ("Ministerio de Salud","Diario Financiero","SUSESO","Diario Oficial"):return False,"missing_date",q
    if "editorial_v2" in r:
        v2=evaluate_editorial_v2(r)
        if v2.decision!="accept":return False,f"editorial_v2_{v2.decision}",min(q,v2.materiality_score)
    if q<62:return False,"quality_below_threshold",q
    return True,"ok",q
