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
# Publication is off in config (re-check 28-oct-2026); apply() tests that need the block opt in explicitly.
REG_PUBLISH = pc.Registry({**pc.load_registry(Path(".")), "corroboration": {"publish_enabled": True}})
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
    out = pc.apply([card, CMF_BIONET], Path("."), corpus=corpus, registry=REG_PUBLISH)
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
    script = "\n".join([pick("esc"), pick("arr"), pick("fmtDate"), pick("corroboration"), pick("corrUrlOk"),
                        pick("corroborationWhat"), pick("corroborationRelated")]) + """
const card={paywalled:true,corroboration:{status:'corroborated',original_label:'Fuente original: Pulso (contenido para suscriptores)',
 what:[{text:'INDISA aceptó oferta de ACHS.',attribution:'la CMF (hecho esencial)',source_url:'https://www.cmfchile.cl/a'},
       {text:'<script>x</script>',attribution:'nadie',source_url:'javascript:alert(1)'}],
 related_sources:[{title:'INSTITUTO DE DIAGNOSTICO S.A.: hecho esencial',source_name:'CMF',url:'https://www.cmfchile.cl/a',event_date:'2026-09-02'}]}};
const both=c=>corroborationWhat(c)+corroborationRelated(c);
console.log(JSON.stringify({what:corroborationWhat(card),rel:corroborationRelated(card),open:both({...card,paywalled:false}),
 none:both({paywalled:true,corroboration:{status:'none',what:[],related_sources:[]}})}));
"""
    out = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)
    # Option B (staging #90): the attributed sentences join the ficha's own "Qué pasó" section and the related
    # sources join its "Fuentes" section; "Fuente original" and the subscriber note come from originalLink/
    # paywallNote (see tests/web.test.cjs), not from a separate block.
    html = out["what"] + out["rel"]
    assert "<h3" not in out["what"] and "Fuentes relacionadas" not in out["what"]
    assert "Según la CMF (hecho esencial): INDISA aceptó oferta de ACHS." in out["what"]
    assert 'href="https://www.cmfchile.cl/a"' in html
    assert "Fuentes relacionadas" in out["rel"]
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


# --- issuer-only anchors (independent review, 28-oct-2026) ---------------------------
# Real records and real headlines. Each false match below shared only the issuer
# tag (src:minsal) and topic words ("listas de espera", "padres", "permiso").

SUSESO_PLAN_ENLACE = signal(
    "https://www.suseso.gob.cl/605/w3-article-790601.html",
    "Minsal y cajas de compensación firman convenio para reducir tiempos de espera de las listas No GES para "
    "beneficiarios de Fonasa",
    "El Minsal y las cajas de compensación Los Héroes, 18 de Septiembre y La Araucana firmaron un convenio para "
    "incorporar sus redes de prestadores al Plan Enlace. La iniciativa identificará a afiliados de las cajas "
    "pertenecientes a los grupos B, C y D de Fonasa que esperan atenciones No GES y les permitirá acceder a "
    "prestaciones en convenio sin costo adicional. SUSESO impulsó la articulación del acuerdo, que se plantea como "
    "una estrategia permanente para enfrentar una lista cercana a 3 millones de personas.",
    "2026-09-23", "Superintendencia de Seguridad Social (SUSESO)")
MINSAL_LEY_MILA = signal(
    "https://www.minsal.cl/a-cinco-anos-de-su-promulgacion-minsal-muestra-avances-de-ley-mila-en-hospitales-e-"
    "implementa-sello-en-recintos/",
    "A cinco años de su promulgación: Minsal muestra avances de Ley Mila en hospitales e implementa sello en recintos",
    "El Ministerio de Salud informó, a cinco años de la promulgación de la Ley Mila (Ley N.º 21.372), los resultados "
    "de una evaluación aplicada a 182 establecimientos de los 29 servicios de salud. Según el reporte, 162 permiten "
    "el acompañamiento de padres, madres o tutores de menores hospitalizados y el 100% de los establecimientos que "
    "atienden partos facilita la compañía de una persona elegida por la mujer. Además, implementará un sello de "
    "certificación para los recintos que cumplan los requisitos de la ley.",
    "2026-10-16", "Ministerio de Salud")
MINSAL_PERMISO_SUICIDIO = signal(
    "https://www.minsal.cl/minsal-ingresa-proyecto-de-ley-que-otorga-a-padres-un-permiso-para-cuidar-a-sus-hijos-"
    "tras-hospitalizacion-por-intento-de-suicidio/",
    "Minsal ingresa proyecto de ley que otorga a padres un permiso para cuidar a sus hijos tras hospitalización por "
    "intento de suicidio",
    "El Ministerio de Salud ingresó al Congreso un proyecto que complementa la Ley Sanna y permitiría a madres, "
    "padres y cuidadores legales afiliados al seguro obtener una licencia laboral para acompañar a hijos de entre 5 "
    "y 17 años después de una hospitalización por intento de suicidio. El permiso sería de 15 días iniciales, "
    "prorrogables por otros 15 días según evaluación médica, hasta 30 días por evento y por cada hijo o hija.",
    "2026-10-15", "Ministerio de Salud")
LT = "https://www.latercera.com/nacional/noticia/"
CARD_6_COLMED = item(
    "Colmed Santiago y expertos ponen paños fríos al optimismo del Minsal por avances en listas de espera",
    "2026-09-22",
    "La presidenta del gremio capitalino, Francisca Crispi, así como exautoridades de salud pública advierten que la "
    "alerta sanitaria del ministerio para reducir las listas oncológicas tuvo un efecto parcial en el balance general "
    "y que el problema sigue siendo estructural.",
    LT + "colmed-santiago-y-expertos-ponen-panos-frios-al-optimismo-del-minsal-por-avances-en-listas-de-espera/")
CARD_7_CHOMALI = item(
    "Chomali por listas de espera: “Yo no esperaba que disminuyeran, lo que yo espero es que disminuyan los tiempos”",
    "2026-09-23",
    "La ministra de Salud respondió a los cuestionamientos por el estado de las listas de espera y defendió que la "
    "estrategia del gobierno está enfocada en reducir los tiempos de espera y avanzar en cambios estructurales.",
    LT + "chomali-por-listas-de-espera-yo-no-esperaba-que-disminuyeran-lo-que-yo-espero-es-que-disminuyan-los-tiempos/")
CARD_9_PERMISO = item(
    MINSAL_PERMISO_SUICIDIO["title"], "2026-10-15",
    "La iniciativa complementa la Ley Sanna y beneficia a madres, padres y cuidadores afiliados al seguro, con hijos "
    "entre 5 y 17 años. El permiso se extenderá hasta 30 días por cada evento y por cada hijo o hija, contados desde "
    "el inicio de la primera licencia.",
    LT + "minsal-ingresa-proyecto-de-ley-que-otorga-a-padres-un-permiso-para-cuidar-a-sus-hijos-tras-"
         "hospitalizacion-por-intento-de-suicidio/")


@pytest.mark.parametrize("card", [CARD_6_COLMED, CARD_7_CHOMALI], ids=["card6_colmed", "card7_chomali"])
def test_waiting_list_commentary_does_not_match_plan_enlace_convenio(card):
    ix = index([SUSESO_PLAN_ENLACE, MINSAL_LEY_MILA])
    block = pc.corroborate(card, ix)
    assert block["status"] == "none" and block["related_sources"] == []
    # The pair is still scored: what rejects it is the issuer-only gate, not the date window.
    doc = next(d for d in ix.docs if d.url == SUSESO_PLAN_ENLACE["source_url"])
    feats = pc.features(f"{card['title']} {card['teaser']}", REG, catalog=ix.catalog)
    feats.terms = pc.terms(card["title"])
    mt = pc.score_pair(feats, card["date"], doc, doc.feat, ix)
    assert mt is not None and [e for e in mt.shared_entities if not e.startswith("src:")] == []
    assert not pc._eligible(mt, REG)


def test_parental_leave_bill_keeps_its_own_record_and_drops_ley_mila_as_extra():
    block = pc.corroborate(CARD_9_PERMISO, index([MINSAL_PERMISO_SUICIDIO, MINSAL_LEY_MILA, SUSESO_PLAN_ENLACE]))
    assert block["status"] == "corroborated"
    assert [r["url"] for r in block["related_sources"]] == [MINSAL_PERMISO_SUICIDIO["source_url"]]


def test_issuer_only_anchor_needs_event_specific_evidence():
    base = dict(doc=None, score=0.9, shared_entities=["src:minsal"], shared_acts=[], day_gap=0, conflicts=[],
                term_recall=0.5)
    generic = pc.Match(shared_terms=["esper", "lista", "tiemp", "permi"], **base)
    assert pc.specific_terms(generic, REG) == [] and not pc._eligible(generic, REG)
    assert not pc._eligible(pc.Match(shared_terms=["padre", "permi"], **base), REG)
    assert not pc._eligible(pc.Match(shared_terms=["eleam", "cuent"], **base), REG)  # 2 < 3 (re-check)
    assert pc._eligible(pc.Match(shared_terms=["eleam", "cuent", "autor"], **base), REG)
    assert pc._eligible(pc.Match(shared_terms=["lista"], shared_amounts=["%12.3"], **base), REG)
    assert pc._eligible(pc.Match(shared_terms=["lista"], shared_places=["Talca"], **base), REG)
    named = {**base, "shared_entities": ["src:minsal", "cl:org:indisa", "cl:org:achs"]}
    assert pc._eligible(pc.Match(shared_terms=["lista"], **named), REG)
    acts = {**base, "shared_acts": ["ley:21372"]}
    assert pc._eligible(pc.Match(shared_terms=[], **acts), REG)


def test_title_recall_floor_is_at_least_the_code_default():
    assert float(REG.matching["min_title_term_recall"]) >= 0.3
    low = pc.Match(doc=None, score=0.9, shared_entities=["src:minsal", "cl:org:indisa", "cl:org:achs"],
                   shared_acts=[], shared_terms=["bione"], day_gap=0, conflicts=[], term_recall=0.25)
    assert not pc._eligible(low, REG)


def test_seremi_headline_matches_the_official_long_form():
    assert "serem" in pc.terms("Secretario Regional Ministerial de Salud de La Araucanía")
    assert "debid" not in pc.terms("debido a declaraciones")


# --- re-check 28-oct-2026: publication off, and four more false pairs -------------------

def test_publication_is_off_and_no_card_gets_corroboration_fields():
    assert REG.raw["corroboration"]["publish_enabled"] is False and not pc.publish_enabled(REG)
    card = redact_signal({"title": BIONET["title"], "source_name": "Pulso / La Tercera",
                          "source_url": BIONET["url"], "event_date": "2026-09-02",
                          "public_teaser": BIONET["teaser"]})
    stale = {**card, "corroboration": {"status": "corroborated", "what": [], "related_sources": []}}
    corpus = pc.build_corpus(Path("."), REG, signal_sets=[[CMF_BIONET]], queue={})
    # The matcher itself still finds the pair (that is what the audit reports) ...
    assert pc.corroborate(BIONET, index([CMF_BIONET]))["status"] == "corroborated"
    # ... but the export attaches nothing and strips any stale block; "Qué pasó" is untouched.
    out = pc.apply([card, stale, CMF_BIONET], Path("."), corpus=corpus)
    assert all("corroboration" not in c for c in out)
    assert out[0] == card and out[1] == card and out[0]["what_happened"] == card["what_happened"]
    snapshot = json.loads(Path("web/data/radar_today.json").read_text(encoding="utf-8"))
    assert not any("corroboration" in c for c in snapshot["signals"])


MINSAL_SARAMPION = signal(
    "https://www.minsal.cl/minsal-busco-y-vacuno-a-mas-de-44-mil-ninos-contra-el-sarampion/",
    "Minsal buscó y vacunó a más de 44 mil niños y niñas contra el sarampión y llama a vacunar a quienes tienen su "
    "esquema pendiente",
    "El Ministerio de Salud informó que la búsqueda activa permitió vacunar a más de 44 mil niños y niñas contra el "
    "sarampión; persisten niños con esquema pendiente.", "2026-10-28", "Ministerio de Salud")


def test_influenza_piece_is_not_corroborated_by_measles_campaign():
    flu = item("Minsal dice que 44 mil niños aún no se vacunan contra la influenza", "2026-10-28")
    assert pc.corroborate(flu, index([MINSAL_SARAMPION]))["status"] == "none"
    assert "condition" in pc.conflicts(pc.features(flu["title"], REG), pc.features(MINSAL_SARAMPION["title"], REG))


def test_suseso_mental_health_study_is_not_corroborated_by_circular_3929():
    study = item("Salud mental en educación: Suseso publica estudio sobre procedimientos estandarizados para "
                 "calificar enfermedades profesionales", "2026-10-05")
    circular = signal("https://www.suseso.gob.cl/612/w3-article-791706.html", "Circular 3929",
                      "La SUSESO publicó la Circular 3929, vigente desde su publicación, que modifica el Compendio de "
                      "Normas del Seguro Social de la Ley N°16.744. La circular incorpora asistencia técnica para "
                      "prevenir acoso laboral, acoso sexual y violencia en el trabajo en centros educativos; aborda "
                      "aspectos de la calificación del origen de patologías de salud mental.", "2026-10-08",
                      "Superintendencia de Seguridad Social (SUSESO)")
    ix = index([circular])
    assert pc.corroborate(study, ix)["status"] == "none"
    feats = pc.features(study["title"], REG, catalog=ix.catalog)
    mt = pc.score_pair(feats, study["date"], ix.docs[0], ix.docs[0].feat, ix)
    assert [e for e in mt.shared_entities if not e.startswith("src:")] == []
    assert len(pc.specific_terms(mt, REG)) < 3 and not pc._eligible(mt, REG)
    assert int(REG.matching["min_issuer_only_terms"]) >= 3


def _ges(month):
    return signal("https://www.superdesalud.gob.cl/biblioteca-digital/estadistica-trimestral-de-casos-ges-auge-de-"
                  f"fonasa-y-sistema-isapre-a-{month}-2025/",
                  f"Estadística Trimestral de Casos GES (AUGE) de Fonasa y Sistema Isapre – a {month} 2025",
                  f"La Superintendencia actualizó a {month} 2025 los casos y tasas de uso GES de Fonasa e Isapres por "
                  "problema de salud.", "2025-10-03", "Superintendencia de Salud")


def test_ges_reports_of_different_quarters_do_not_corroborate_each_other():
    june, march = _ges("junio"), _ges("marzo")
    piece = item(june["title"], "2025-10-03", june["what_happened"])
    block = pc.corroborate(piece, index([march]))
    assert block["status"] == "none"
    assert "period:month" in pc.conflicts(pc.features(june["title"], REG), pc.features(march["title"], REG))
    assert pc.corroborate(piece, index([march, june]))["related_sources"][0]["url"] == june["source_url"]
    assert "period:quarter" in pc.conflicts(pc.features("Informe del primer trimestre 2025", REG),
                                            pc.features("Informe del tercer trimestre 2025", REG))


DO = "https://www.diariooficial.interior.gob.cl/publicaciones/2026/09/02/44540/01/"
DO_CP_20192 = signal(
    DO + "2863854.pdf",
    "Resolución exenta número CP 20.192, de 2026.- Declara zona de riesgo sanitario la comuna de Renaico Ver PDF "
    "(CVE-2862808) Instituto de Salud Pública Extracto de resolución exenta número 4.011, de 2026.- Aprueba "
    "lineamientos y exigencias para productos farmacéuticos peligrosos",
    "Resolución exenta número CP 20.192, de 2026.- Declara zona de riesgo sanitario la comuna de Renaico. Instituto "
    "de Salud Pública Extracto de resolución exenta número 4.011, de 2026.- Aprueba lineamientos y exigencias para "
    "productos farmacéuticos peligrosos.", "2026-09-02", "Diario Oficial")
DO_ISP_4011 = signal(
    DO + "2863853.pdf",
    "Instituto de Salud Pública Extracto de resolución exenta número 4.011, de 2026.- Aprueba lineamientos y "
    "exigencias para productos farmacéuticos peligrosos",
    "Instituto de Salud Pública Extracto de resolución exenta número 4.011, de 2026.- Aprueba lineamientos y "
    "exigencias para productos farmacéuticos peligrosos.", "2026-09-02", "Diario Oficial")


def test_numero_act_ids_are_parsed_and_isp_4011_does_not_match_cp_20192():
    assert pc.act_list(DO_CP_20192["title"])[:2] == ["resolucion:20192", "resolucion:4011"]
    assert pc.act_ids("Ley número 21.809") == {"ley:21809"}
    isp = item("ISP aprueba lineamientos para productos farmacéuticos peligrosos (resolución exenta número 4.011)",
               "2026-09-02")
    assert "act_id" in pc.conflicts(pc.features(isp["title"], REG), pc.features(DO_CP_20192["title"], REG))
    block = pc.corroborate(isp, index([DO_CP_20192]))
    assert block["status"] == "none"
    block = pc.corroborate(isp, index([DO_CP_20192, DO_ISP_4011]))
    assert [r["url"] for r in block["related_sources"]] == [DO_ISP_4011["source_url"]]
