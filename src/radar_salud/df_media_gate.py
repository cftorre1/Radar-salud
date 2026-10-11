"""DF's existing Media Early Signal Gate, applied before history publication."""
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from .beta_sources import media_gate_accepts


def policy():
    return json.loads((Path(__file__).resolve().parents[2] / "config/media_early_signal_gate.json").read_text())


def exclusion(raw):
    url = raw.url.lower()
    path = urlsplit(url).path
    if path.endswith('.pdf') or '/noticias/site/docs/' in path or re.search(r'/p/\d+/?$', path):
        return "df_not_article"
    section = str(raw.metadata.get("article_section", "")).lower()
    title = raw.title.lower()
    if "/opinion/" in url or "opinión" in section or "opinion" in section or title.startswith(("columna:", "columna de")):
        return "media_opinion_or_column"
    if any(x in url for x in ("/brand", "/contenido-patrocinado/", "/patrocinado/")):
        return "media_branded_content"
    return None


def material(title, body):
    from .public_source_pipeline import _health_relevance
    # A macroeconomic event and an unrelated mention of health somewhere else
    # do not establish a material health event. Require the same sentence.
    statements = [title, *re.split(r'(?<=[.!?])\s+', body)]
    for statement in statements:
        if not _health_relevance(statement, ""):
            continue
        if _material_statement(statement):
            return True
    return False


def _material_statement(text):
    text = text.lower()
    # Capacity also includes removal of capacity, not just openings/investment.
    closure = any(x in text for x in ("cierra", "cerrar", "cierre", "suspende", "suspensión", "traslado de pacientes"))
    clinical = any(x in text for x in ("clínica", "clinica", "hospital"))
    return media_gate_accepts(text, "") or (closure and clinical) or any(x in text for x in
        ("circular", "deberá", "recorte", "registró una caída", "liquidación", "insolvencia"))
