from typing import Dict, Any
from .models import RawItem, Signal
from .scoring import ScoreInputs, calculate_radar_score

CATEGORY_KEYWORDS = {
    "Prestadores": ["clínica","hospital","centro médico","prestador"],
    "Aseguramiento": ["isapre","fonasa","seguro"],
    "Regulación & Legal": ["circular","resolución","corte","recurso","demanda","ley","oficio"],
    "Oportunidades & Licitaciones": ["licitación","mercado público","concurso"],
    "Salud Laboral & Seguridad Social": ["suseso","compin","mutual","accidente laboral","licencia médica"],
    "Innovación & Startups": ["startup","venture","healthtech","biotech","ronda","capital"],
    "Radar Mundo": ["medicare","fda","united states","global","internacional"],
}
def infer_category(text: str, default: str = "Mercado") -> str:
    t=text.lower()
    for category,keywords in CATEGORY_KEYWORDS.items():
        if any(k in t for k in keywords):return category
    return default

def build_signal(raw: RawItem, source_cfg: Dict[str, Any]) -> Signal:
    combined=f"{raw.title} {raw.raw_text}"
    default_category=source_cfg.get("default_category","Mercado")
    category=default_category if source_cfg.get("force_category") else infer_category(combined,default_category)
    dimensions=raw.metadata.get("scores",{})
    scores=ScoreInputs(
        economic_impact=dimensions.get("economic",50), regulatory_impact=dimensions.get("regulatory",30),
        scope=dimensions.get("scope",50), novelty=dimensions.get("novelty",70),
        actionability=dimensions.get("actionability",50), source_quality=source_cfg.get("base_confidence",80))
    radar_score=calculate_radar_score(scores)
    confidence=min(100,source_cfg.get("base_confidence",80)+raw.metadata.get("confidence_adjustment",0))
    return Signal(
        title=raw.title,source_name=raw.source_name,source_type=raw.source_type,source_url=raw.url,
        category=category,subcategory=raw.metadata.get("subcategory","General"),
        system_domain=source_cfg.get("system_domain","HEALTH"),
        what_happened=raw.metadata.get("what_happened",raw.raw_text[:350]),event_date=raw.event_date,
        topics=raw.metadata.get("topics",[]),entities=raw.metadata.get("entities",[]),
        geography=raw.metadata.get("geography",[]),key_facts=raw.metadata.get("key_facts",[]),
        key_numbers=raw.metadata.get("key_numbers",[]),why_it_matters=raw.metadata.get("why_it_matters",""),
        who_cares=raw.metadata.get("who_cares",[]),possible_implications=raw.metadata.get("possible_implications",[]),
        watch_tags=raw.metadata.get("watch_tags",[]),event_type=raw.metadata.get("event_type","OTHER"),
        strategic_theme=raw.metadata.get("strategic_theme",[]),institution_types=raw.metadata.get("institution_types",[]),
        country=raw.metadata.get("country","CL"),connection_keys=raw.metadata.get("connection_keys",[]),
        trend_keys=raw.metadata.get("trend_keys",raw.metadata.get("strategic_theme",[])),
        prospective_evidence=raw.metadata.get("prospective_evidence",False),
        economic_impact_score=scores.economic_impact,regulatory_impact_score=scores.regulatory_impact,
        scope_score=scores.scope,novelty_score=scores.novelty,actionability_score=scores.actionability,
        source_quality_score=scores.source_quality,radar_score=radar_score,confidence_score=confidence,
        source_documents=raw.metadata.get("attachments",raw.metadata.get("source_documents",[])),
        key_points=raw.metadata.get("key_points",[]),risk_notes=raw.metadata.get("risk_notes",[]),
        data_insights=raw.metadata.get("data_insights",[]),
        validity_text=raw.metadata.get("validity_text"),
    )
