"""Global relevance gate (Dirección 28-oct-2026 09:58): trends and global interest.

Global shows what helps the Chilean market prepare: development of new technologies, new health
trends, international studies, policy and system reforms, financing and payment models, AI in
health and workforce trends. Operational one-off news is NOT relevant for Chile: bed use, drug
safety alerts and recalls, provider acquisitions, new center openings, and approvals of single
products (unless the release marks a novel technology or a first-of-kind approval).

Deterministic keyword rules on the publisher's title (and feed categories) only: no summary,
no paid model (paid_ai_calls=0). Exclusions win over any interest signal; a per-source rule
(config ``global_relevance.sources``) can add exclusions and interest signals, never override a
global exclusion. There is no "always include" rule: safety alerts are excluded too.
"""
from __future__ import annotations

import re
import unicodedata

METHOD = "direccion_global_interest_v1"
DECISION = "Dirección 28-oct-2026 09:58: relevancia Global = tendencias e interés global"

# Novel technology / first-of-kind approval: keeps an approval that would otherwise be "single product".
FIRST_TREATMENT = (r"\bfirst\b.{0,50}\b(treatment|therapy|therapies|drug|medicine|test|device|vaccine|approval|gene|cell|"
                   r"diagnostic|class|ai|artificial intelligence|digital)\b|\bprimer[ao]?\b.{0,50}\b(tratamiento|terapia|vacuna|dispositivo)\b")
FIRST_OF_KIND = (FIRST_TREATMENT + r"|first-in-class|first-of-(a|its)-kind|"
                 r"\bnovel\b|\bbreakthrough\b|new class of|gene (therapy|editing)|\bcrispr\b|cell therapy|\bcar-t\b|"
                 r"artificial intelligence|\bai\b|machine learning|\bdigital\b|software|algorithm")
# An approval, pathway or merger as a POLICY subject (rule, guidance, reform, study) is not a one-off.
POLICY_CONTEXT = (r"\b(guidance|guideline|framework|pathway|rule|rules|policy|policies|reform|legislation|law|bill|program|"
                  r"programme|strategy|antitrust|competition (authority|law|regulator)|ftc|merger (review|guidelines|rules|control)|"
                  r"study|report|analysis|trends?|survey)\b|reforma|politica|estudio|informe")

EXCLUSIONS = (
    ("safety_alert_or_recall",
     r"\brecall(s|ed|ing)?\b|safety (alert|communication|notice|warning|update)s?\b|patient safety alert|field safety|"
     r"drug safety|medication safety alert|warning letters?\b|boxed warning|market withdrawal|withdrawn from (the )?market|"
     r"\bcontaminat\w*|defect information|\bmedwatch\b|do not use\b|counterfeit|falsified (medicine|product)s?|"
     r"retiro del mercado|retira(r)? (el |los )?lotes?|alerta (sanitaria|de seguridad|farmacologica)|"
     r"\bclass (1|2|3|4|i|ii|iii) (medicines? |device )?(recall|defect)"),
    ("bed_or_capacity_use",
     r"\bbeds?\b.{0,40}\b(occupancy|use|usage|capacity|availability|shortage|pressures?)\b|bed (occupancy|days|use|usage)|"
     r"(hospital|icu|ward) (occupancy|capacity)|ocupacion de camas|\bcamas\b"),
    ("provider_transaction",
     r"\bacquir(e|es|ed|ing)\b|\bacquisition(s)?\b|\bmerg(e|er|ers|es|ed|ing)\b|\bbuys?\b|to buy\b|\btakeover\b|"
     r"completes? (the )?(purchase|sale)|\bdivest\w*|adquisicion|adquiere|\bfusion\b|compra de"),
    ("facility_opening",
     r"\b(opens?|opened|opening|inaugurat\w*|unveils?|breaks ground|groundbreaking|ribbon)\b.{0,60}"
     r"\b(hospital|clinic|cent(er|re)|campus|facility|wing|unit|ward|site|office|laboratory|lab)s?\b|"
     r"\bnew (hospital|clinic|cent(er|re)|campus|facility|wing|ward)s?\b|inaugura|abre (un |una )?nuev[oa]|nuevo (hospital|centro|cesfam)"),
    ("single_product_approval",
     r"\bapprov(e|es|ed|al|als)\b|\bauthori[sz](e|es|ed|ation)\b|\bclear(s|ed|ance)\b|positive opinion|"
     r"recommends? (approval|granting|marketing)|new (human )?medicines?\b|\bgeneric (version|drug)s?\b|\bbiosimilar\b|"
     r"emergency use|label (change|expansion|update)|new indication|expanded indication|aprueba|autoriza"),
)
# Approvals/transactions are excluded only as one-offs: first-of-kind or policy-level context keeps them.
EXCEPTIONS = {"single_product_approval": (FIRST_OF_KIND, POLICY_CONTEXT), "provider_transaction": (POLICY_CONTEXT,)}

INTEREST = (
    ("new_technology",
     r"technolog|innovat|\bdigital\b|genomic|genetic test|gene (therap|editing)|\bcrispr\b|cell therap|\bcar-t\b|\bmrna\b|"
     r"precision medicine|personali[sz]ed medicine|telehealth|telemedicine|virtual (care|ward)|remote monitoring|wearable|"
     r"robot|3d.print|health data|data (platform|space|sharing|infrastructure)|interoperab|electronic (health|medical) record|"
     r"\behr\b|software|first-in-class|first-of-(a|its)-kind|\bnovel\b|breakthrough|new class of|" + FIRST_TREATMENT +
     r"|tecnologia|innovacion|salud digital|telesalud"),
    ("ai_in_health",
     r"artificial intelligence|\bai\b|machine learning|algorithm|chatbot|large language model|\bllms?\b|generative|"
     r"inteligencia artificial|\bia\b"),
    ("international_study_or_trend",
     r"\btrends?\b|\bstud(y|ies)\b|\bsurvey\b|\breport\b|\banalysis\b|meta-analysis|\bevidence\b|research (finds|shows)|"
     r"\bfinds\b|\bshows\b|data show|\brising\b|\bgrowing\b|increase in|decline in|\bglobal\b|worldwide|international|"
     r"\bcountries\b|cross-country|burden of|forecast|outlook|projection|\bestimates?\b|statistics|life expectancy|"
     r"ageing|aging|obesity|chronic (disease|condition)s?|noncommunicable|non-communicable|mental health|"
     r"antimicrobial resistance|\bamr\b|tendencia|estudio|informe|encuesta|mundial|envejecimiento"),
    ("policy_or_system_reform",
     r"\breform|\bpolic(y|ies)\b|legislat|\blaw\b|\bbill\b|\brules?\b|\bregulation\b|regulatory (framework|reform|pathway|science)|"
     r"framework|strategy|action plan|universal health coverage|\buhc\b|health systems?\b|primary (health )?care|"
     r"guideline|guidance|consultation|white paper|\bdirective\b|\bact\b|pharmaceutical (package|strategy|legislation)|"
     r"reforma|politica|ley\b|estrategia|sistema de salud|atencion primaria|cobertura universal"),
    ("financing_and_payment",
     r"financ|funding|budget|spending|expenditure|\bcosts?\b|\bprices?\b|pricing|payment|\bpay\b|reimburs|value-based|"
     r"bundled|capitation|insur|payer|\bcoverage\b|premium|medicare|medicaid|out-of-pocket|affordab|tariff|"
     r"health technology assessment|\bhta\b|cost-effective|financiamiento|\bcosto|\bpago|seguro|aseguradora|cobertura"),
    ("workforce_trend",
     r"workforce|staffing|health ?care workers?|health workers?|\bnurs(e|es|ing)\b|physicians?|\bdoctors?\b|burnout|"
     r"\bwages?\b|\blabou?r\b|recruitment|retention|residency|task shifting|scope of practice|fuerza laboral|"
     r"recursos humanos|personal de salud|trabajadores de la salud|enfermer"),
)
# Immunization coverage is epidemiology, not insurance coverage.
VACCINE_COVERAGE = (r"(vaccin\w*|immuni[sz]ation|vacunacion|inmunizacion)\s+(rate\s+)?coverage|coverage\s+(of|for|with)\s+(\w+\s+){0,2}"
                    r"(vaccin\w*|immuni[sz]ation|doses?)|cobertura\s+(de\s+)?(vacunacion|inmunizacion|vacunas?)")


def fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", (text or "").casefold()) if not unicodedata.combining(c))


def source_rules(config: dict | None, source: str | None) -> dict:
    return (((config or {}).get("global_relevance") or {}).get("sources") or {}).get(source or "", {}) or {}


def validate_rules(config: dict) -> None:
    for source, rules in (((config or {}).get("global_relevance") or {}).get("sources") or {}).items():
        unknown = set(rules) - {"exclude_title_patterns", "interest_title_patterns", "note"}
        if unknown:
            raise ValueError(f"global_relevance.{source}: unknown keys {sorted(unknown)} (no include-always rule)")
        for pattern in rules.get("exclude_title_patterns", []) + rules.get("interest_title_patterns", []):
            re.compile(pattern)


def global_interest(title: str, categories=(), *, source: str | None = None, rules: dict | None = None) -> dict:
    """Does this headline help the Chilean market prepare? Exclusions first, then an interest signal."""
    rules = rules or {}
    title_text = fold(title)
    text = fold(" ".join([title or "", *(categories or ())]))
    for category, pattern in EXCLUSIONS:
        if re.search(pattern, title_text):
            if any(re.search(p, title_text) for p in EXCEPTIONS.get(category, ())):
                continue
            return {"relevant": False, "category": category, "signals": [], "reason": "not_global_interest:" + category,
                    "method": METHOD, "source": source}
    for pattern in rules.get("exclude_title_patterns", []):
        if re.search(pattern, title_text):
            return {"relevant": False, "category": "source_rule_exclusion", "signals": [], "pattern": pattern,
                    "reason": "not_global_interest:source_rule_exclusion", "method": METHOD, "source": source}
    scrubbed = re.sub(VACCINE_COVERAGE, " ", text)
    signals = [name for name, pattern in INTEREST if re.search(pattern, scrubbed)]
    if any(re.search(p, title_text) for p in rules.get("interest_title_patterns", [])):
        signals.append("source_rule_interest")
    if not signals:
        return {"relevant": False, "category": "no_global_interest_signal", "signals": [],
                "reason": "not_global_interest:no_global_interest_signal", "method": METHOD, "source": source}
    return {"relevant": True, "category": signals[0], "signals": signals, "reason": "global_interest_signal",
            "method": METHOD, "source": source}
