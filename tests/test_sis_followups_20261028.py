"""Dirección 28-oct-2026 04:28: late SIS resolutions, SIS newsroom, 90-day availability."""
import json
from datetime import date
from pathlib import Path
from urllib.error import HTTPError

import pytest

import scripts.export_web_snapshot as exporter
from radar_salud import regulatory
from radar_salud.accreditation_pulse import accreditation_pulse, accreditation_pulses
from radar_salud.models import RawItem
from radar_salud.normative_relations import apply_backlinks, extract_relations, related_documents
from radar_salud.processing import DeferredProcessing, RejectedProcessing
from radar_salud import sis_news
from radar_salud.sis_news import (SuperintendenciaNoticiasScout, fold_news_into_acts, mentioned_acts,
                                  parse_listing, process_superintendencia_noticias, robots_allows)

FIX = Path(__file__).parent / "fixtures" / "sis"


@pytest.fixture(autouse=True)
def _isolated_failure_ledger(tmp_path, monkeypatch):
    # Never write the article-failure ledger into the repository's data/state.
    monkeypatch.setattr(SuperintendenciaNoticiasScout, "_failures_path", lambda self: self.state_path or tmp_path / "news_failures.json")
SIS = "Superintendencia de Salud"
SUSPENSION_534 = ("Ha lugar a la suspensión de los efectos de la Circular IF/Nº534, de fecha 14 de septiembre de 2026, "
                  "hasta que se resuelvan los recursos de reposición de que conoce esta Intendencia.")


def _late_resolution(**extra):
    card = {"title": "Resolución Exenta IF/N°12001", "source_name": SIS, "event_date": "2026-10-27",
            "source_url": "https://www.superdesalud.gob.cl/normativa/resolucion-exenta-if-n12001/",
            "official_subject": SUSPENSION_534}
    card["normative_relations"] = extract_relations(SUSPENSION_534, card["title"], SIS)
    card.update(extra)
    return card


C534 = {"title": "Circular IF/N°534", "source_name": SIS, "event_date": "2026-09-14",
        "source_url": "https://www.superdesalud.gob.cl/normativa/circular-if-n534/"}


# --- 1. Late resolutions ----------------------------------------------------------------------

def test_original_older_than_90_days_links_to_history_record():
    old = dict(C534, event_date="2026-05-14")  # 167 days before the late act: outside any feed window
    docs = related_documents(_late_resolution(), [old], index={}, in_feed=[])
    assert docs == [dict(docs[0], basis="history_record", url=old["source_url"], verified=True)]
    assert docs[0]["history_ficha"] == {"title": "Circular IF/N°534", "event_date": "2026-05-14",
                                        "source_url": old["source_url"], "in_feed": False}
    assert "suspende transitoriamente" in docs[0]["relationship"]


def test_original_missing_from_history_uses_official_listing_url(monkeypatch):
    html = (FIX / "circulares_aseguradoras_20261028.html").read_text(encoding="utf-8")
    monkeypatch.setattr(regulatory, "fetch_html", lambda url: html)
    scout = regulatory.SuperintendenciaNormativaScout()
    monkeypatch.setattr(scout, "PAGES", [("Para ISAPREs y FONASA", "https://www.superdesalud.gob.cl/x/", "Isapres / Fonasa")])
    scout.discover()
    index = scout.listing_index
    assert index["circular-if-534"]["url"] == "https://www.superdesalud.gob.cl/normativa/circular-if-n534/"
    assert index["circular-if-528"]["url"].endswith("/circular-if-n528-2/")  # real URL, never a constructed one
    docs = related_documents(_late_resolution(), [], index=index)
    assert docs[0]["basis"] == "official_listing_index" and docs[0]["url"] == index["circular-if-534"]["url"]
    assert docs[0]["event_date"] == "2026-09-14"


def test_original_unknown_shows_identity_without_link():
    docs = related_documents(_late_resolution(), [], index={})
    assert docs == [{"title": "Circular IF/N°534", "summary": None, "relationship": docs[0]["relationship"],
                     "url": None, "event_date": None, "verified": False, "basis": "id_only",
                     "target_id": "Circular IF/N°534"}]


def test_never_links_an_ip_or_foreign_record_for_an_if_target():
    ip = dict(C534, title="Circular IP/N°534", source_url="https://www.superdesalud.gob.cl/normativa/circular-ip-n534/")
    suseso = dict(C534, source_name="SUSESO", source_url="https://www.suseso.cl/x")
    assert related_documents(_late_resolution(), [ip, suseso], index={})[0]["basis"] == "id_only"
    assert related_documents(dict(_late_resolution(), source_name="Diario Financiero"), [C534], index={}) == []


def test_export_attaches_documents_to_minimal_and_reviewed_cards(tmp_path):
    index_path = tmp_path / "index.json"
    index_path.write_text(json.dumps({"acts": {}}), encoding="utf-8")
    minimal = _late_resolution(normative_minimal=True, related_context=None)
    reviewed = dict(_late_resolution(), source_url="https://www.superdesalud.gob.cl/normativa/resolucion-exenta-if-n12002/",
                    title="Resolución Exenta IF/N°12002",
                    related_context=[{"title": "Ley N°19.880", "url": None, "verified": False}])
    old = dict(C534, event_date="2026-05-14")
    out = {r["title"]: r for r in exporter._late_related_documents([minimal, reviewed], [old, minimal, reviewed], index_path)}
    m = out["Resolución Exenta IF/N°12001"]
    assert m["official_related_documents"][0]["url"] == old["source_url"]
    assert m["related_context"] is None  # minimal cards keep no automated relations
    r = out["Resolución Exenta IF/N°12002"]
    assert [x["title"] for x in r["related_context"]] == ["Circular IF/N°534", "Ley N°19.880"]


def test_original_card_shows_backlink_when_present_even_if_act_is_older_than_window():
    late = _late_resolution()
    original_in_feed = dict(C534)
    out = exporter._normative_status([original_in_feed], [dict(C534), late])
    assert out[0]["normative_status"] == "Suspendida transitoriamente"
    assert out[0]["normative_status_events"][0]["by_url"] == late["source_url"]


# --- 2. SIS newsroom --------------------------------------------------------------------------

LISTING = (FIX / "noticias_2026_listing_20261028.html").read_text(encoding="utf-8")
ARTICLE = (FIX / "noticias_article_synthetic.html").read_text(encoding="utf-8")


def _article(title, published, body="Las isapres deberán informar la cobertura GES.", visible=""):
    return (ARTICLE.replace("TITLE_PLACEHOLDER", title).replace("DATE_PLACEHOLDER", published)
            .replace("DESCRIPTION_PLACEHOLDER", body[:120]).replace("BODY_PLACEHOLDER", body).replace("VISIBLE_DATE", visible))


def test_listing_structure():
    entries = parse_listing(LISTING, "https://www.superdesalud.gob.cl/noticias/2026/")
    assert len(entries) == 5  # year selector links are not articles
    assert entries[0]["listing_date"] == "2026-10-14" and entries[0]["listing_title"].startswith("Más de 62 millones")
    assert entries[2]["listing_date"] is None and entries[2]["url_month"] == "2026-09"
    assert all("Leer noticia" not in e["listing_title"] for e in entries)


def _fetcher(pages):
    def fetch(url):
        if url == sis_news.ROBOTS:
            return pages.get("robots", "User-agent: *\nAllow: /\n")
        return pages[url]
    return fetch


def test_discover_window_article_decides_title_and_date():
    ges = "https://www.superdesalud.gob.cl/noticias/2026/10/mas-de-62-millones-de-casos-ges-desde-2005-salud-presenta-cifras-actualizadas-y-llama-a-ejercer-las-garantias/"
    comunicado = "https://www.superdesalud.gob.cl/noticias/2026/09/comunicado-de-prensa-3/"
    seminario = "https://www.superdesalud.gob.cl/noticias/2026/09/superintendencia-de-salud-realizo-seminario-de-entidades-acreditadoras-con-participacion-del-instituto-de-salud-publica/"
    pages = {"https://www.superdesalud.gob.cl/noticias/2026/": LISTING,
             ges: _article("Más de 62 millones de casos GES desde 2005: Salud presenta cifras actualizadas y llama a ejercer las garantías", "2026-10-14T10:00:00-03:00"),
             comunicado: _article("Comunicado de prensa sobre la Circular IF/N°534", "2026-09-30T12:00:00-03:00",
                                  body="La Superintendencia suspende los efectos de la Circular IF/N°534 para las isapres."),
             seminario: _article("Superintendencia de Salud realizó Seminario de Entidades Acreditadoras", "", visible="")}
    scout = SuperintendenciaNoticiasScout(fetch=_fetcher(pages), today=date(2026, 10, 28))
    items = {i.url: i for i in scout.discover()}
    assert set(items) == {ges, comunicado, seminario}  # 20-08 and 15-06 entries are outside the window: not fetched
    assert scout.discovery_errors == []
    assert items[ges].event_date == "2026-10-14"
    assert items[ges].metadata["publication_date_source"] == "article:published_time"
    c = items[comunicado]
    assert c.title == "Comunicado de prensa sobre la Circular IF/N°534" and c.metadata["listing_title_mismatch"]
    assert c.metadata["mentioned_acts"] == ["circular-if-534"]  # named in the title
    assert items[seminario].event_date is None  # undated listing and article: never dated by guess


def test_robots_policy():
    assert robots_allows("https://www.superdesalud.gob.cl/noticias/2026/", lambda url: "User-agent: *\nDisallow: /noticias/\n") is False
    def missing(url):
        raise HTTPError(url, 404, "nf", None, None)
    assert robots_allows("https://www.superdesalud.gob.cl/noticias/2026/", missing) is True
    def down(url):
        raise OSError("timeout")
    with pytest.raises(PermissionError):
        robots_allows("https://www.superdesalud.gob.cl/noticias/2026/", down)
    scout = SuperintendenciaNoticiasScout(fetch=_fetcher({"robots": "User-agent: *\nDisallow: /\n"}), today=date(2026, 10, 28))
    with pytest.raises(PermissionError):
        scout.discover()


def _news(title, body, **meta):
    return RawItem("superintendencia_noticias", title, "https://www.superdesalud.gob.cl/noticias/2026/10/x/", SIS, "official",
                   event_date="2026-10-14", raw_text=body[:200],
                   metadata={"lead": body[:400], "publication_date_source": "article:published_time", **meta})


def test_editorial_gate(monkeypatch):
    import radar_salud.llm_analysis as llm
    monkeypatch.setattr(llm, "analyze_official_news", lambda **k: None)  # no paid call in tests
    monkeypatch.setattr(sis_news, "_transient_article_text", lambda url: "Las isapres y Fonasa registran casos GES acumulados.")
    cfg = {"slug": "superintendencia_noticias", "name": SIS, "source_type": "official", "base_confidence": 100,
           "default_category": "Regulación & Legal"}
    with pytest.raises(DeferredProcessing):  # no AI score and no deterministic signal: pending
        process_superintendencia_noticias(_news("Más de 62 millones de casos GES desde 2005",
                                                "Las isapres y Fonasa registran casos GES acumulados."), cfg)
    with pytest.raises(DeferredProcessing):  # agenda item: AI score only
        process_superintendencia_noticias(_news("Superintendencia de Salud realizó Seminario de Entidades Acreditadoras",
                                                "Seminario con el ISP."), cfg)
    monkeypatch.setattr(llm, "analyze_official_news", lambda **k: {"relevance_score": 78})
    row = process_superintendencia_noticias(_news("Más de 62 millones de casos GES desde 2005",
                                                  "Las isapres y Fonasa registran casos GES acumulados."), cfg)
    assert row["signal_types"] == ["Noticias"] and set(row["scopes"]) == {"Isapres", "Fonasa"}
    monkeypatch.setattr(llm, "analyze_official_news", lambda **k: None)
    with pytest.raises(DeferredProcessing):
        process_superintendencia_noticias(RawItem("superintendencia_noticias", "Isapres", "https://www.superdesalud.gob.cl/noticias/2026/10/y/",
                                                  SIS, "official", event_date=None), cfg)
    monkeypatch.setattr(llm, "analyze_official_news", lambda **k: {"relevance_score": 40})
    with pytest.raises(RejectedProcessing):
        process_superintendencia_noticias(_news("Isapres: nuevo informe", "Las isapres informan."), cfg)


def test_news_about_an_act_folds_into_the_normativa_card():
    act = dict(C534, signal_types=["Normativa"], event_type="REGULATION", normative_document_label="Circular IF/N°534")
    news = {"title": "Comunicado sobre la Circular IF/N°534", "source_name": SIS, "event_date": "2026-09-30",
            "source_url": "https://www.superdesalud.gob.cl/noticias/2026/09/comunicado-de-prensa-3/",
            "signal_types": ["Noticias"], "mentioned_acts": mentioned_acts("Circular IF/N°534")}
    other = dict(news, source_url="https://www.superdesalud.gob.cl/noticias/2026/10/ges/", mentioned_acts=[], title="GES")
    out = fold_news_into_acts([act, news, other])
    assert [c["title"] for c in out] == ["Circular IF/N°534", "GES"]
    assert out[0]["source_alternatives"][0]["url"] == news["source_url"]
    assert mentioned_acts("Circular IP/N°534") == ["circular-ip-534"]


def test_source_registered_in_catalog_policy_and_engine():
    sources = json.loads(Path("config/sources.json").read_text(encoding="utf-8"))
    rows = sources if isinstance(sources, list) else sources["sources"]
    assert any(r["slug"] == "superintendencia_noticias" and r["cadence"] == "daily" for r in rows)
    policy = json.loads(Path("config/source_freshness_policy.json").read_text(encoding="utf-8"))
    assert "superintendencia_noticias" in policy["activated_daily_2026_10_28"]
    assert "superintendencia_noticias" not in policy["non_daily_sources"]
    from radar_salud.public_source_catalog import CATALOG, SHORT_NAMES
    assert CATALOG["superintendencia_noticias"][1] == "https://www.superdesalud.gob.cl/noticias/"
    assert SHORT_NAMES["superintendencia_noticias"] == SIS
    engine = Path("src/radar_salud/engine_cli.py").read_text(encoding="utf-8")
    assert '("superintendencia_noticias","superintendencia_noticias",SuperintendenciaNoticiasScout().discover' in engine


# --- 3. 90-day availability -------------------------------------------------------------------

def _act(n, subject, day):
    return {"title": f"Resolución Exenta IP/N°{n}", "source_name": SIS, "event_date": day,
            "source_url": f"https://www.superdesalud.gob.cl/normativa/resolucion-exenta-ip-n{n}/", "official_subject": subject}


def test_accreditation_acts_stay_available_90_days():
    acts = [_act(1, "Inscríbase en el Registro Público de Prestadores Institucionales de Salud Acreditados, al Prestador Institucional Clínica Uno, de la Ciudad de Talca, Región del Maule", "2026-10-20"),
            _act(2, "Manténgase con la inscripción N°2 en el Registro, al Prestador Institucional Clínica Dos, de la Comuna de Recoleta, Región Metropolitana", "2026-09-10"),
            _act(3, "Modifíquese la inscripción del Prestador Institucional Hospital de Río Negro, inscrito en el Registro Nacional", "2026-10-15"),
            _act(4, "Manténgase … al Prestador Institucional Antigua, de la Ciudad de Arica", "2026-07-20")]
    pulses = accreditation_pulses(acts, date(2026, 10, 28))
    assert [p["title"] for p in pulses] == ["Acreditación de prestadores · últimos 30 días: 2 actos",
                                            "Acreditación de prestadores · días 31 a 90: 1 acto"]
    assert "Hospital de Río Negro" in pulses[0]["what_happened"]  # registry changes were invisible before
    assert "Clínica Dos" in pulses[1]["what_happened"] and "Entre 31 y 90 días atrás" in pulses[1]["what_happened"]
    assert all("Antigua" not in p["what_happened"] for p in pulses)  # 100 days: history only
    assert accreditation_pulse(acts, date(2026, 10, 28))["window_days"] == [0, 30]


def test_export_retains_90_days_and_keeps_a_31_to_90_accreditation_card():
    source = Path("scripts/export_web_snapshot.py").read_text(encoding="utf-8")
    assert "0<=(latest-day).days<=90" in source  # feed retention
    assert "accreditation_pulses(signals,latest)" in source
    from radar_salud.accreditation_pulse import RETENTION_DAYS
    assert RETENTION_DAYS == 90


# --- Review of 955a1461 ---------------------------------------------------------------------------

GES_URL = "https://www.superdesalud.gob.cl/noticias/2026/10/mas-de-62-millones-de-casos-ges-desde-2005-salud-presenta-cifras-actualizadas-y-llama-a-ejercer-las-garantias/"


@pytest.mark.parametrize("failure", ["timeout", "robots", "http"])
def test_article_failure_drops_item_and_marks_discovery_partial(failure):
    pages = {"https://www.superdesalud.gob.cl/noticias/2026/": LISTING}

    def fetch(url):
        if url == sis_news.ROBOTS:
            return "User-agent: *\nDisallow: /noticias/2026/10/\n" if failure == "robots" else "User-agent: *\nAllow: /\n"
        if url in pages:
            return pages[url]
        if failure == "http":
            raise HTTPError(url, 503, "unavailable", None, None)
        raise TimeoutError("read timeout")
    scout = SuperintendenciaNoticiasScout(fetch=fetch, today=date(2026, 10, 28))
    items = scout.discover()
    assert GES_URL not in {i.url for i in items}  # never published from the listing alone
    assert any(GES_URL in e for e in scout.discovery_errors)  # engine keeps the watermark: retried next run


def _gate_cfg():
    return {"slug": "superintendencia_noticias", "name": SIS, "source_type": "official", "base_confidence": 100,
            "default_category": "Regulación & Legal"}


def test_gestion_is_not_ges_and_agenda_news_is_not_published(monkeypatch):
    import radar_salud.llm_analysis as llm
    monkeypatch.setattr(llm, "analyze_official_news", lambda **k: None)
    monkeypatch.setattr(sis_news, "_transient_article_text", lambda url: "Se abordó la gestión hospitalaria y la gestión clínica.")
    with pytest.raises(RejectedProcessing):
        process_superintendencia_noticias(_news("Superintendente participa en seminario sobre gestión hospitalaria",
                                                "Gestión hospitalaria."), _gate_cfg())
    assert not sis_news._MATERIAL.search("Seminario sobre gestión y sugestión")


def test_unscored_news_stays_pending_without_deterministic_signal(monkeypatch):
    import radar_salud.llm_analysis as llm
    monkeypatch.setattr(llm, "analyze_official_news", lambda **k: None)
    monkeypatch.setattr(sis_news, "_transient_article_text", lambda url: "Informe sobre beneficiarios del sistema de salud.")
    with pytest.raises(DeferredProcessing):
        process_superintendencia_noticias(_news("Nuevo informe sobre beneficiarios", "Informe."), _gate_cfg())
    with pytest.raises(DeferredProcessing):  # topic without an action verb
        process_superintendencia_noticias(_news("Isapres deberán restituir cobros por Tabla de Factores", "Isapres."), _gate_cfg())
    row = process_superintendencia_noticias(_news("Superintendencia ordena a isapres restituir cobros por Tabla de Factores",
                                                  "Isapres."), _gate_cfg())
    assert row["relevance_basis"] == "deterministic_topic_and_action_in_clause"
    monkeypatch.setattr(llm, "analyze_official_news", lambda **k: {"relevance_score": 81, "what_happened": "x" * 50})
    row = process_superintendencia_noticias(_news("Nuevo informe sobre beneficiarios", "Informe."), _gate_cfg())
    assert row["relevance_basis"] == "ai_relevance" and row["editorial_relevance"] == 81


def test_article_unavailable_at_processing_stays_pending(monkeypatch):
    def down(url):
        raise TimeoutError
    monkeypatch.setattr(sis_news, "_transient_article_text", down)
    with pytest.raises(DeferredProcessing):
        process_superintendencia_noticias(_news("Isapres: nuevas instrucciones", "Isapres."), _gate_cfg())


def test_passing_mention_does_not_fold_and_hidden_act_lets_news_stand():
    body = ("La Superintendencia de Salud presentó el balance GES 2005-2026 con más de 62 millones de casos atendidos. "
            * 3 + "Entre otras materias, recordó la Circular IF/N°534 sobre bono electrónico.")
    pages = {"https://www.superdesalud.gob.cl/noticias/2026/": LISTING,
             GES_URL: _article("Más de 62 millones de casos GES desde 2005", "2026-10-14T10:00:00-03:00", body=body)}
    scout = SuperintendenciaNoticiasScout(fetch=_fetcher(pages), today=date(2026, 10, 28))
    item = next(i for i in scout.discover() if i.url == GES_URL)
    assert item.metadata["mentioned_acts"] == []  # IF/534 only in passing, outside title and lead
    act = dict(C534, signal_types=["Normativa"], event_type="REGULATION", normative_document_label="Circular IF/N°534")
    news = {"title": "Comunicado sobre la Circular IF/N°534", "source_name": SIS, "event_date": "2026-09-30",
            "source_url": "https://www.superdesalud.gob.cl/noticias/2026/09/comunicado-de-prensa-3/",
            "signal_types": ["Noticias"], "mentioned_acts": ["circular-if-534"]}
    assert len(fold_news_into_acts([dict(act, feed_visibility=False), news])) == 2  # hidden act: news stands
    assert len(fold_news_into_acts([news])) == 1
    source = Path("scripts/export_web_snapshot.py").read_text(encoding="utf-8")
    assert source.index("fold_news_into_acts(recent)") > source.index("apply_story_groups(recent")


def test_stored_state_stays_within_rights_cap(tmp_path):
    long_body = "Las isapres deberán informar. " * 2000  # ~60k chars of article text
    pages = {"https://www.superdesalud.gob.cl/noticias/2026/": LISTING,
             GES_URL: _article("Más de 62 millones de casos GES desde 2005", "2026-10-14T10:00:00-03:00", body=long_body)}
    scout = SuperintendenciaNoticiasScout(fetch=_fetcher(pages), today=date(2026, 10, 28))
    items = scout.discover()
    from radar_salud.pending_queue import PendingQueue
    q = PendingQueue(tmp_path / "q.json")
    q.discover("superintendencia_noticias", items)
    stored = json.loads((tmp_path / "q.json").read_text(encoding="utf-8"))
    for entry in stored.values():
        raw = entry["raw"]
        assert len(raw["raw_text"]) <= sis_news.EXCERPT_MAX
        assert "page_text" not in raw["metadata"]
        assert len(raw["metadata"].get("lead") or "") <= sis_news.LEAD_MAX
        assert len(json.dumps(raw, ensure_ascii=False)) < 2500


def test_listing_index_only_from_https_sis_hosts_and_survives_corruption(tmp_path):
    from radar_salud.regulatory import merge_sis_index, official_sis_url, record_listing_identity
    assert official_sis_url("https://www.superdesalud.gob.cl/normativa/circular-if-n534/")
    assert not official_sis_url("http://www.superdesalud.gob.cl/normativa/circular-if-n534/")
    assert not official_sis_url("https://superdesalud.gob.cl.evil.example/normativa/")
    assert not official_sis_url("https://evil.example/?u=superdesalud.gob.cl")
    index = {}
    record_listing_identity(index, "Circular IF/N°534", "https://evil.example/superdesalud.gob.cl/x", "2026-09-14", "", "")
    assert index == {}
    path = tmp_path / "sis_normative_index.json"
    path.write_text("{not json", encoding="utf-8")
    acts = merge_sis_index(path, {"circular-if-534": {"id": "Circular IF/N°534", "url": C534["source_url"]}})
    assert acts["circular-if-534"]["url"] == C534["source_url"]
    assert json.loads(path.read_text(encoding="utf-8"))["acts"] == acts


def test_ui_links_require_https_and_backlink_has_aria_label():
    js = Path("web/app.js").read_text(encoding="utf-8")
    assert "x.url&&x.verified&&/^https:\\/\\//.test(x.url)" in js
    assert 'aria-label="${esc(\'Ver \'+(x.by||' in js


# --- Re-review of 753368f5 ------------------------------------------------------------------------

@pytest.mark.parametrize("title", [
    "Superintendente se reúne con gerentes de isapres en seminario",
    "Superintendencia realiza seminario sobre GES en regiones",
    "Superintendente expone ante gremio de isapres",
    "Fonasa y Superintendencia firman convenio de colaboración",
    "Ceremonia de aniversario de la Superintendencia: multas récord",
    "Isapres y Fonasa en la jornada anual del sector",
])
def test_agenda_titles_never_use_the_deterministic_fallback(title, monkeypatch):
    import radar_salud.llm_analysis as llm
    monkeypatch.setattr(llm, "analyze_official_news", lambda **k: None)
    monkeypatch.setattr(sis_news, "_transient_article_text", lambda url: "Las isapres y Fonasa; cobertura GES y multas.")
    assert sis_news.deterministic_signal(title, "", ["circular-if-534"]) is None  # agenda wins even over a named act
    with pytest.raises(DeferredProcessing):
        process_superintendencia_noticias(_news(title, "Isapres y Fonasa."), _gate_cfg())
    # With a real AI score the item is judged on that score alone.
    monkeypatch.setattr(llm, "analyze_official_news", lambda **k: {"relevance_score": 50})
    with pytest.raises(RejectedProcessing):
        process_superintendencia_noticias(_news(title, "Isapres y Fonasa."), _gate_cfg())


@pytest.mark.parametrize("title,lead,basis", [
    ("Superintendencia de Salud sanciona a Isapre X con multa de 500 UF", "", "deterministic_topic_and_action_in_clause"),
    ("Superintendencia publica circular que modifica la cobertura CAEC", "", "deterministic_topic_and_action_in_clause"),
    ("Nuevas instrucciones a las aseguradoras", "La Circular IF/N°540 regula la cobertura.", "deterministic_names_specific_act"),
])
def test_deterministic_fallback_positives(title, lead, basis, monkeypatch):
    import radar_salud.llm_analysis as llm
    monkeypatch.setattr(llm, "analyze_official_news", lambda **k: None)
    monkeypatch.setattr(sis_news, "_transient_article_text", lambda url: "Isapres y cobertura.")
    acts = mentioned_acts(f"{title} {lead}")
    raw = _news(title, lead or "Isapres.", mentioned_acts=acts)
    raw.metadata["lead"] = lead
    row = process_superintendencia_noticias(raw, _gate_cfg())
    assert row["relevance_basis"] == basis


def test_topic_and_action_must_share_a_clause():
    assert sis_news.deterministic_signal("Isapres: balance anual. La Superintendencia sanciona prácticas") is None
    assert sis_news.deterministic_signal("Informe de cotizantes") is None


def test_article_failing_three_runs_is_skipped_and_source_not_partial(tmp_path):
    ledger = tmp_path / "ledger.json"
    pages = {"https://www.superdesalud.gob.cl/noticias/2026/": LISTING}

    def fetch(url):
        if url == sis_news.ROBOTS:
            return "User-agent: *\nAllow: /\n"
        if url in pages:
            return pages[url]
        raise TimeoutError("read timeout")
    for run in (1, 2):
        scout = SuperintendenciaNoticiasScout(fetch=fetch, today=date(2026, 10, 28), state_path=ledger)
        scout.discover()
        assert any(GES_URL in e for e in scout.discovery_errors)  # partial: watermark held, retried
    scout = SuperintendenciaNoticiasScout(fetch=fetch, today=date(2026, 10, 28), state_path=ledger)
    scout.discover()
    assert scout.discovery_errors == []  # third failure: skipped, source no longer partial
    assert {"url": GES_URL, "status": "article_skipped", "reason": "TimeoutError", "failures": 3} in scout.discovery_audit
    assert json.loads(ledger.read_text())[GES_URL]["skipped"] is True
    later = SuperintendenciaNoticiasScout(fetch=fetch, today=date(2026, 10, 28), state_path=ledger)
    later.discover()
    assert later.discovery_errors == [] and later.discovery_audit[0]["status"] == "article_skipped"


def test_a_success_resets_the_failure_count(tmp_path):
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps({GES_URL: {"failures": 2, "skipped": False}}), encoding="utf-8")
    pages = {"https://www.superdesalud.gob.cl/noticias/2026/": LISTING,
             GES_URL: _article("Más de 62 millones de casos GES desde 2005", "2026-10-14T10:00:00-03:00")}
    SuperintendenciaNoticiasScout(fetch=_fetcher(pages), today=date(2026, 10, 28), state_path=ledger).discover()
    assert GES_URL not in json.loads(ledger.read_text())


def test_unscored_news_revived_once_when_ai_budget_returns(tmp_path):
    from datetime import datetime, timezone
    from radar_salud.pending_queue import PendingQueue
    now = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)
    q = PendingQueue(tmp_path / "q.json")
    def item(day, **extra):
        raw = {"source_slug": "superintendencia_noticias", "title": "t", "url": f"https://www.superdesalud.gob.cl/noticias/{day}",
               "source_name": SIS, "source_type": "official", "event_date": day, "raw_text": "", "metadata": {}}
        return {"source": "superintendencia_noticias", "status": "deferred", "lane": "LIVE", "attempts": 4,
                "reason": "retry_exhausted:sis_news_relevance_unscored", "detected_at": now.isoformat(), "raw": raw, **extra}
    q.items = {"recent": item("2026-10-20"), "old": item("2026-09-01"),
               "other": dict(item("2026-10-20"), reason="retry_exhausted:other")}
    assert q.revive_unscored_sis_news(now, ai_available=False) == 0
    assert q.revive_unscored_sis_news(now, ai_available=True, max_attempts=4) == 1
    assert q.items["recent"]["status"] == "retry" and q.items["recent"]["attempts"] == 2  # two more tries
    assert q.items["old"]["status"] == "deferred" and q.items["other"]["status"] == "deferred"
    q.items["recent"].update(status="deferred", reason="retry_exhausted:sis_news_relevance_unscored", attempts=4)
    assert q.revive_unscored_sis_news(now, ai_available=True) == 0  # never a second revival
