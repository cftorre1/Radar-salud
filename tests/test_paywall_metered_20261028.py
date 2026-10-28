"""Dirección 28-oct-2026: La Tercera metered sections are paid (policy 1.3.0).

Qué Pasa, Nacional and every section that allows a few free articles a month keep
only title, public lead, date, link and a receipt; analysis uses only those.
"""
import gzip
import json
import re
from pathlib import Path

import pytest

from radar_salud.models import RawItem
from radar_salud.source_rights import access_classification, is_paywalled, load_policy, restrict_raw_to_public

ROOT = Path(__file__).resolve().parents[1]
LEAD = "La autoridad sanitaria informó una nueva medida para reducir los tiempos de espera en la red pública."
BODY = ("Texto completo de una sección medida que el lector sólo ve dentro de su cupo mensual de artículos. ") * 6


def test_config_records_the_metered_decision_and_covers_the_whole_host():
    config = json.loads((ROOT / "config/paywalled_press.json").read_text(encoding="utf-8"))
    rule, = [r for r in config["sources"] if r["id"] == "la_tercera_premium"]
    assert rule["scope"] == "host" and rule["metered_sections_paywalled"] is True
    assert "pending_decision" not in rule and config["metered_decision"]["decided_at"] == "2026-10-28"
    assert load_policy()["version"] == config["version"] == "1.3.0"


@pytest.mark.parametrize("section", ["nacional", "que-pasa", "politica", "servicios", "tendencias", "paula",
                                     "tecnologia", "sustentabilidad", "el-deportivo", "mundo", "videos", "culto",
                                     "branded", "publirreportajes", "pulso", "lt-board"])
def test_every_la_tercera_section_is_paid(section):
    url = f"https://www.latercera.com/{section}/noticia/x/"
    assert is_paywalled(url)
    assert access_classification(url, {})["paywalled"] is True


def test_every_la_tercera_fixture_section_is_paid():
    sections = set()
    for path in (ROOT / "tests/fixtures").rglob("*.html.gz"):
        if "pulso" not in str(path):
            continue
        html = gzip.decompress(path.read_bytes()).decode("utf-8", "replace")
        m = re.search(r'<link rel="canonical" href="(https://www\.latercera\.com/[^"]+)"', html)
        if m:
            sections.add(m.group(1).split("/")[3])
            assert is_paywalled(m.group(1)), m.group(1)
    assert {"nacional", "pulso", "politica"} <= sections


def test_metered_capture_keeps_only_the_lead_for_analysis():
    raw = RawItem("pulso_latercera", "Minsal anuncia medida", "https://www.latercera.com/nacional/noticia/x/",
                  "Pulso / La Tercera", "press_high_trust", raw_text=BODY,
                  metadata={"page_text": BODY, "description": LEAD, "section": "Nacional"})
    restrict_raw_to_public(raw)
    md = raw.metadata
    assert raw.raw_text == md["page_text"] == md["public_teaser"] == LEAD and md["paywalled"] is True
    assert BODY.strip()[:60] not in json.dumps(md, ensure_ascii=False)
    assert any(r["field"] == "page_text" for r in md["rights_redactions"])
