"""DF's existing Media Early Signal Gate, applied before history publication."""
import json
from pathlib import Path
from .beta_sources import media_gate_accepts


def policy():
    return json.loads((Path(__file__).resolve().parents[2] / "config/media_early_signal_gate.json").read_text())


def exclusion(raw):
    url = raw.url.lower()
    section = str(raw.metadata.get("article_section", "")).lower()
    title = raw.title.lower()
    if "/opinion/" in url or "opinión" in section or "opinion" in section or title.startswith(("columna:", "columna de")):
        return "media_opinion_or_column"
    if any(x in url for x in ("/brand", "/contenido-patrocinado/", "/patrocinado/")):
        return "media_branded_content"
    return None


def material(title, body):
    text = (title + " " + body).lower()
    # Capacity also includes removal of capacity, not just openings/investment.
    closure = any(x in text for x in ("cierra", "cerrar", "cierre", "suspende", "suspensión", "traslado de pacientes"))
    clinical = any(x in text for x in ("clínica", "clinica", "hospital"))
    return media_gate_accepts(title, body) or (closure and clinical)
