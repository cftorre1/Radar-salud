"""Dirección 28-oct-2026 15:16: thin DF/Pulso pieces borrow "Qué pasó" only from authorized open sources.

Offline: the real registry (config/corroboration_sources.json) and entity catalog,
synthetic corpus records. No network, no model.
"""
import json
import re
import shutil
import socket
import subprocess
from datetime import date
from pathlib import Path

import pytest

from radar_salud import paywall_corroboration as pc
from radar_salud.source_rights import redact_signal, sha256_text

REG = pc.Registry(pc.load_registry(Path(".")))
DF = "https://www.df.cl/empresas/salud/"
PULSO = "https://www.latercera.com/pulso/noticia/"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("network access in a corroboration test")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    pc._RUN["llm_calls"] = 0


def signal(url, title, what, day, source_name, **kw):
    return {"source_url": url, "title": title, "what_happened": what, "event_date": day,
            "source_name": source_name, **kw}


def item(title, day, teaser="", url=DF + "x"):
    return {"title": title, "teaser": teaser, "date": date.fromisoformat(day), "url": url,
            "paywall_name": "Diario Financiero"}


def index(rows, registry=REG):
    docs = pc.build_corpus(Path("."), registry, signal_sets=[rows], queue={})
    docs = [d for d in docs if d.origin != "data/market/cmf_events.json"]  # only the synthetic rows
    return pc.CorpusIndex(docs, registry, fingerprints=set())


CMF_BIONET = signal("https://www.cmfchile.cl/sitio/aplic/serdoc/ver_sgd.php?s567=abc",
                    "INSTITUTO DE DIAGNOSTICO S.A.: hecho esencial",
                    "INDISA aceptó oferta no vinculante de ACHS por su 50% de Bionet a UF457.668; compraventa y "
                    "contrato de laboratorio sujetos a condiciones.", "2026-09-02",
                    "Comisión para el Mercado Financiero (CMF)")
BIONET = item("Indisa acuerda venta de su participación en laboratorios Bionet a la Achs", "2026-09-02",
              "La clínica recibirá UF 457.668 por el 50% de la sociedad.", PULSO + "bionet")


# --- matching precision ------------------------------------------------------

def test_true_same_event_is_corroborated_with_traceable_fields():
    block = pc.corroborate(BIONET, index([CMF_BIONET]))
    assert block["status"] == "corroborated" and block["method"] == "deterministic"
    rel = block["related_sources"][0]
    assert rel["url"] == CMF_BIONET["source_url"]
    assert set(rel["matched_on"]["entities"]) >= {"cl:org:indisa", "cl:org:achs"}
    assert "uf457668" in rel["matched_on"]["amounts"]


@pytest.mark.parametrize("paywalled,open_row,why", [
    # same company, same verb, other city
    (item("RedSalud inaugura clínica de alta complejidad en Talca con US$ 45 millones", "2026-09-08"),
     signal("https://www.redsalud.cl/noticias/puerto-montt", "RedSalud inaugura clínica en Puerto Montt",
            "RedSalud inauguró una clínica de alta complejidad en Puerto Montt.", "2026-09-08", "RedSalud"),
     "place"),
    # same company and operation, different amount
    (item("Clínica Las Condes finaliza aumento de capital y recauda $80 mil millones", "2026-08-05"),
     signal("https://www.cmfchile.cl/sitio/aplic/serdoc/ver_sgd.php?s567=clc", "CLINICA LAS CONDES S.A.: hecho esencial",
            "CLC terminó el aumento de capital y reportó CLP 50.000.000.000 recaudados.", "2026-08-05",
            "Comisión para el Mercado Financiero (CMF)"),
     "amount"),
    # opposite action on the same asset
    (item("Bupa abre nueva clínica oncológica en Antofagasta", "2026-09-21"),
     signal("https://www.bupa.cl/somos-bupa/cierre", "Bupa cierra clínica oncológica en Antofagasta",
            "Bupa Chile cierra su clínica oncológica de Antofagasta.", "2026-09-21", "Bupa Chile"),
     "polarity"),
    # same regulator, nothing event-specific in common
    (item("Super de Salud ordena a las isapres garantizar acceso inmediato a tratamientos por cáncer", "2026-05-13"),
     signal("https://www.superdesalud.gob.cl/fiscalizacion/resolucion-exenta-if-n5292/", "Resolución Exenta IF/N°5292",
            "La Superintendencia de Salud multó al prestador por no garantizar el cumplimiento de la Ley de Urgencia.",
            "2026-05-13", "Superintendencia de Salud"),
     "issuer_only"),
    # different act number
    (item("Suseso publica Circular 3925 sobre licencias médicas de dentistas", "2026-10-26"),
     signal("https://www.suseso.gob.cl/612/w3-article-1.html", "Circular 3923",
            "La SUSESO publicó la Circular 3923 sobre licencias médicas de dentistas.", "2026-10-26",
            "Superintendencia de Seguridad Social (SUSESO)"),
     "act_id"),
    # right event words, outside the ±7 day window
    (BIONET, {**CMF_BIONET, "event_date": "2026-09-12"}, "window"),
])
def test_similar_titles_about_different_events_do_not_match(paywalled, open_row, why):
    block = pc.corroborate(paywalled, index([open_row]))
    assert block["status"] == "none", why
    assert block["what"] == [] and block["related_sources"] == []


def test_conflict_detectors_name_the_differing_fact():
    p = pc.features("Clínica Las Condes recauda $80 mil millones en Talca", REG)
    d = pc.features("CLC reportó CLP 50.000.000.000 recaudados en Temuco", REG)
    found = pc.conflicts(p, d)
    assert "place" in found and any(c.startswith("amount:$") for c in found)
    # headline rounding is not a conflict
    assert pc.conflicts(pc.features("recauda $80 mil millones", REG),
                        pc.features("reportó CLP 80.119.759.016 recaudados", REG)) == []
    assert pc.act_ids("Resolución Exenta IF/N°5292 y Circular 3923; Ley 21.674") == {
        "resolucion:5292", "circular:3923", "ley:21674"}


# --- authorized sources only -------------------------------------------------

@pytest.mark.parametrize("url,source_name,what", [
    ("https://www.df.cl/empresas/salud/otra", "Diario Financiero", None),                      # paywalled
    ("https://www.latercera.com/nacional/noticia/bionet/", "La Tercera", None),               # rejected host
    ("https://www.biobiochile.cl/noticias/bionet.shtml", "BioBioChile", None),              # needs_permission
    ("https://www.cmfchile.cl/sitio/aplic/serdoc/ver_sgd.php?s567=x", "CMF",                 # derived from DF
     "Según el Diario Financiero, INDISA aceptó oferta de ACHS por Bionet a UF457.668."),
])
def test_unauthorized_or_derived_records_never_corroborate(url, source_name, what):
    row = {**CMF_BIONET, "source_url": url, "source_name": source_name}
    if what:
        row["what_happened"] = what
    assert pc.corroborate(BIONET, index([row]))["status"] == "none"


def test_registry_enables_only_corpus_sources_without_live_search_or_excerpts():
    statuses = {s["id"]: s["status"] for s in REG.sources}
    assert set(statuses.values()) <= set(REG.raw["statuses"])
    for s in REG.sources:
        assert {"status", "reason", "evidence_urls", "verified_at", "next_step", "reevaluate_after"} <= set(s), s["id"]
        if s["status"] == "enabled":
            assert s["mode"] == "corpus_only" and s["live_search"] is False and s["excerpt_allowed"] is False
    assert statuses["paywalled_press"] == statuses["la_tercera_open_sections"] == "rejected"
    assert statuses["general_web_search"] == "rejected"
    assert not any(s["kind"] == "open_press" and s["status"] == "enabled" for s in REG.sources)
    assert REG.enabled_source("https://www.df.cl/x") is None
    assert REG.enabled_source("https://www.latercera.com/nacional/x", "minsal") is None  # host wins over slug


# --- no invention --------------------------------------------------------------

def test_every_sentence_of_que_paso_traces_to_a_source_field():
    long_doc = signal("https://www.suseso.gob.cl/605/w3-article-792643.html",
                      "Emisión de licencias médicas disminuyó un 12,3% entre enero y septiembre de 2026",
                      "La SUSESO informó que entre enero y septiembre de 2026 se emitieron 5.155.495 licencias médicas "
                      "electrónicas, un 12,3% menos que en igual período de 2025. La caída alcanzó tanto a Fonasa "
                      "(-13,4%) como a Isapres (-12,2%), mientras que las licencias por trastornos mentales "
                      "disminuyeron 24,3%. La Dra. Pérez explicó la metodología de la serie mensual publicada.",
                      "2026-10-23", "Superintendencia de Seguridad Social (SUSESO)")
    paywalled = item("¿Efecto de más fiscalización? Licencias médicas por salud mental se desploman y lideran caída "
                     "de reposos", "2026-10-28", "Según la Suseso, las licencias por salud mental caen 24,3% y la emisión total 12,3%.")
    idx = index([long_doc])
    block = pc.corroborate(paywalled, idx)
    assert block["status"] == "corroborated"
    doc = next(d for d in idx.docs if d.url == long_doc["source_url"])
    total = 0
    for w in block["what"]:
        assert w["text"] in doc.text                     # verbatim from the field, never generated
        assert w["field"] == "what_happened" and w["source_url"] == doc.url
        assert w["field_sha256"] == sha256_text(doc.text)
        assert w["attribution"] == "la Superintendencia de Seguridad Social (SUSESO)"
        total += len(w["text"])
    assert total <= 300                                  # whole sentences only, within the cap
    assert not any(w["text"].endswith("Dra.") for w in block["what"])
    rendered = pc.render_what(block["what"])
    body = rendered.removeprefix("Según la Superintendencia de Seguridad Social (SUSESO): ")
    assert body != rendered and body == " ".join(w["text"] for w in block["what"])
    assert "Diario Financiero (contenido para suscriptores)" in block["original_label"]


def test_no_shared_actor_means_no_corroboration():
    """Same topic and figures but the paywalled title/lead names no actor of the open record."""
    doc = signal("https://www.suseso.gob.cl/605/w3-article-1.html", "Emisión de licencias médicas disminuyó",
                 "La SUSESO informó que las licencias por trastornos mentales disminuyeron 24,3%.", "2026-10-23",
                 "Superintendencia de Seguridad Social (SUSESO)")
    paywalled = item("Licencias médicas por salud mental se desploman y lideran caída de reposos", "2026-10-28",
                     "Las licencias por salud mental caen 24,3%.")
    assert pc.corroborate(paywalled, index([doc]))["status"] == "none"


def test_sentence_splitter_keeps_abbreviations():
    assert pc.sentences("Imponer al prestador Hospital Clínico Dra. Eloísa Díaz una multa. Segunda frase.") == [
        "Imponer al prestador Hospital Clínico Dra. Eloísa Díaz una multa.", "Segunda frase."]


def test_apply_leaves_uncorroborated_cards_as_title_and_lead(tmp_path):
    card = redact_signal({"title": "Healthatom abre oficina en España", "source_name": "Diario Financiero",
                          "source_url": DF + "healthatom", "event_date": "2026-10-14", "public_teaser": "",
                          "what_happened": "cuerpo bloqueado"})
    out = pc.apply([card], Path("."), corpus=[], registry=REG)
    assert out == [card] and "corroboration" not in out[0]


def test_apply_attaches_block_without_touching_public_fields():
    card = redact_signal({"title": BIONET["title"], "source_name": "Pulso / La Tercera",
                          "source_url": BIONET["url"], "event_date": "2026-09-02",
                          "public_teaser": BIONET["teaser"]})
    corpus = pc.build_corpus(Path("."), REG, signal_sets=[[CMF_BIONET]], queue={})
    out = pc.apply([card, CMF_BIONET], Path("."), corpus=corpus, registry=REG)
    assert out[1] is CMF_BIONET and "corroboration" not in out[1]   # open cards untouched
    got = out[0]
    assert {k: v for k, v in got.items() if k != "corroboration"} == card
    assert got["corroboration"]["status"] == "corroborated"
    assert got["what_happened"] == BIONET["teaser"] and got["paywalled"] is True


# --- attribution rendering (UI) -----------------------------------------------

@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_ui_renders_attribution_original_source_and_related_sources():
    js = Path("web/app.js").read_text(encoding="utf-8")
    pick = lambda name: re.search(r"^(?:const|function) " + name + r"\b.*$", js, re.M).group(0)
    script = "\n".join([pick("esc"), pick("arr"), pick("fmtDate"), pick("corroborationBlock")]) + """
const card={paywalled:true,corroboration:{status:'corroborated',original_label:'Fuente original: Pulso (contenido para suscriptores)',
 what:[{text:'INDISA aceptó oferta de ACHS.',attribution:'la CMF (hecho esencial)',source_url:'https://www.cmfchile.cl/a'},
       {text:'<script>x</script>',attribution:'nadie',source_url:'javascript:alert(1)'}],
 related_sources:[{title:'INSTITUTO DE DIAGNOSTICO S.A.: hecho esencial',source_name:'CMF',url:'https://www.cmfchile.cl/a',event_date:'2026-09-02'}]}};
console.log(JSON.stringify({ok:corroborationBlock(card),open:corroborationBlock({...card,paywalled:false}),
 none:corroborationBlock({paywalled:true,corroboration:{status:'none',what:[],related_sources:[]}})}));
"""
    out = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)
    html = out["ok"]
    assert "<h3>Qué pasó</h3>" in html
    assert "Según la CMF (hecho esencial): INDISA aceptó oferta de ACHS." in html
    assert 'href="https://www.cmfchile.cl/a"' in html
    assert "Fuente original: Pulso (contenido para suscriptores)" in html and "Fuentes relacionadas" in html
    assert "javascript:" not in html and "<script>" not in html and "nadie" not in html
    assert out["open"] == "" and out["none"] == ""


# --- budget cap ------------------------------------------------------------------

def _borderline_setup(monkeypatch, allow=True):
    raw = json.loads(json.dumps(REG.raw))
    raw["matching"]["llm_check"]["enabled"] = True
    raw["matching"]["accept_score"] = 0.99          # force every eligible pair into the borderline band
    raw["matching"]["borderline_score"] = 0.1
    reg = pc.Registry(raw)
    calls = {"allow": 0, "record": []}
    from radar_salud import ai_budget

    def allow_call(kind):
        calls["allow"] += 1
        return allow
    monkeypatch.setattr(ai_budget, "allow_call", allow_call)
    monkeypatch.setattr(ai_budget, "record_result", lambda kind, ok: calls["record"].append((kind, ok)))
    return reg, calls


def test_borderline_model_check_respects_per_run_cap(monkeypatch):
    reg, calls = _borderline_setup(monkeypatch)
    monkeypatch.setenv("RADAR_CORROBORATION_LLM_PER_RUN", "1")
    judged = []

    def judge(paywalled, candidate):
        judged.append(candidate["title"])
        return {"same_event": True, "overlap": ["Indisa vende 50% de Bionet a Achs"]}
    idx = index([CMF_BIONET], reg)
    first = pc.corroborate(BIONET, idx, judge=judge)
    second = pc.corroborate(BIONET, idx, judge=judge)
    assert first["status"] == "corroborated" and first["method"] == "llm_check"
    assert second["status"] == "borderline_review" and second["what"] == []
    assert len(judged) == 1 and calls["allow"] == 1 and calls["record"] == [("fast", True)]


def test_borderline_without_budget_or_judge_is_never_accepted(monkeypatch):
    reg, calls = _borderline_setup(monkeypatch, allow=False)
    judge = lambda a, b: pytest.fail("judge called without budget")
    assert pc.corroborate(BIONET, index([CMF_BIONET], reg), judge=judge)["status"] == "borderline_review"
    reg2, calls2 = _borderline_setup(monkeypatch)
    assert pc.corroborate(BIONET, index([CMF_BIONET], reg2), judge=None)["status"] == "borderline_review"
    assert calls2["allow"] == 0                       # no judge: no budget consumed
    # default registry: model check disabled entirely
    assert REG.matching["llm_check"]["enabled"] is False


def test_judge_saying_no_or_failing_never_accepts(monkeypatch):
    reg, calls = _borderline_setup(monkeypatch)
    idx = index([CMF_BIONET], reg)
    assert pc.corroborate(BIONET, idx, judge=lambda a, b: {"same_event": False})["status"] == "borderline_review"

    def boom(a, b):
        raise RuntimeError("timeout")
    assert pc.corroborate(BIONET, idx, judge=boom)["status"] == "borderline_review"
    assert calls["record"][-1] == ("fast", False)
