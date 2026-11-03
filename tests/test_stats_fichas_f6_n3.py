"""F6 · Boletín IP N°3-2026 (Dirección 1-nov-2026).

The SIS listing published N°3-2026 (enero–septiembre 2026) as four loose PDFs, one history record each (no release
page: the 'Septiembre 2026' page still links the N°2 PDFs and stays rejected). Rules tested here:
- the four loose PDFs form ONE release (2026-09), captured within the same SisFetcher limits, dated by first detection;
- the F6 ficha moves to N°3 only when its figures are verified; checker v3 places 'con observaciones' and 'en
  tramitación' ONLY by the approved templates, which must match exactly once on the cited pages (variable cut-off
  date). Otherwise F6 keeps N°2 and N°3 is a HOLD of its own (``release_holds`` → hold/f6_prestadores-2026-09.json);
- when N°3 passes it is compared with N°2 (stocks compared, never summed) and the loose card is absorbed;
- while N°3 is on HOLD the loose cards collapse into one card titled from the documents.

No network. Figures marked SYNTHETIC are test values, not the real N°3 figures: these tests run in a root holding
only the readings up to N°2 (``readings_until='2026-06'``, the state before 2-nov). The committed N°3 reading
(2-nov-2026) is tested at the end of this file against the committed text receipts of the hashed N°3 PDFs.
"""
import copy
import json
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import stats_ficha_fixtures as fx  # noqa: E402
from radar_salud import sis_bulletins as sb  # noqa: E402
from radar_salud import stats_capture as cap  # noqa: E402
from radar_salud import stats_ficha_f6 as f6, stats_fichas as sf  # noqa: E402

TODAY = date(2026, 11, 1)
STORE = "data/stats_fichas/captures/boletin_ip.json"
HIST = json.loads((fx.REPO / "data/history/superintendencia_signals.json").read_text(encoding="utf-8"))["signals"]
LOOSE = [s for s in HIST if s.get("source_name") == sb.LOOSE_SOURCE and "/boletin-n3-2026-" in str(s.get("source_url"))]
N3 = {cap.doc_release(s["source_url"])["topic"]: s["source_url"] for s in LOOSE}
# SYNTHETIC N°3 reading (test values only). Reclamos: (2010 − 1530) / 1530 = 31,4% → the SIS would report 31.
N3_READING = {"acreditacion": {"accredited_providers": 980, "with_observations": 103, "pending_applications": 590,
                               "private_pending": 371, "public_pending": 219},
              "mediacion": {"registered_mediators": 176, "cumulative_requests_2019_to_september2026": 12500},
              "reclamos": {"monthly_average_2026": 2010, "monthly_average_2025": 1530, "reported_growth_percent_rounded": 31},
              "rnpi": {"registered_titles": 1010000, "records_without_birth_date": 4000}}


@pytest.fixture(autouse=True)
def isolated_ledgers(tmp_path, monkeypatch):
    monkeypatch.setenv("RADAR_ROOT", str(tmp_path / "ledger-root"))


M3 = N3_READING["acreditacion"]
TITLE_P8 = ("Numero de solicitudes de acreditacion que estan en tramitacion, al 30 de septiembre de 2026, desagregadas por "
            "region del prestador y tipo")
SENTENCE_P2 = f"{M3['with_observations']} prestadores institucionales obtuvieron el resultado de acreditado con observaciones"
TOTAL_P8 = f"Total general {M3['private_pending']} {M3['public_pending']} {M3['pending_applications']}"


def n3_books(acr_extra=(SENTENCE_P2, TITLE_P8, TOTAL_P8)) -> dict[str, bytes]:
    """SYNTHETIC N°3 PDFs, fixed before any reading exists (the real bytes never depend on our reading): every figure
    next to its context word, plus, for acreditación, the SIS wording the approved templates anchor on."""
    out = {}
    for topic, metrics in N3_READING.items():
        lines = [f"Boletin fixture N3 {topic}", *(fx.figure_line(k, v) for k, v in metrics.items())]
        out[N3[topic]] = fx.pdf_with_text(lines + (list(acr_extra) if topic == "acreditacion" else []))
    return out


def make(tmp_path, books=None):
    """Fixture root with the committed registry, so the approved acreditación templates apply as in production."""
    r = fx.make_root(tmp_path / "root", readings_until="2026-06")
    (r / cap.REGISTRY).parent.mkdir(parents=True, exist_ok=True)
    (r / cap.REGISTRY).write_text((fx.REPO / cap.REGISTRY).read_text(encoding="utf-8"), encoding="utf-8")
    assert set(cap.figure_templates(r, "acreditacion")) == {"with_observations", "pending_applications"}
    books = n3_books() if books is None else books
    fx.capture_all(r, fx.fetcher(r, books))
    n2 = next(d for x in store(r)["releases"] if x["period"] == "2026-06" for d in x["documents"] if d["topic"] == "acreditacion")
    assert n2["parse"]["status"] == "verified" and n2["parse"]["figure_rules"]["with_observations"]["rule"] == "template"
    BOOKS[str(r)] = books
    return r


BOOKS: dict[str, dict] = {}


@pytest.fixture
def root(tmp_path):
    return make(tmp_path)


def store(r):
    return json.loads((r / STORE).read_text(encoding="utf-8"))


def add_n3_reading(r, reading=N3_READING):
    path = r / cap.VERIFIED
    cfg = json.loads(path.read_text(encoding="utf-8"))
    for topic, metrics in reading.items():
        cfg["primary_review"]["documents"].append({"url": N3[topic], "pages_1based": [1], "verified_metrics": metrics,
                                                   "note": "SYNTHETIC test reading"})
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------------------------
# Release from the loose listing PDFs


def test_history_has_the_four_loose_n3_pdfs_and_they_form_one_release():
    assert sorted(N3) == sorted(cap.TOPICS) and len(LOOSE) == 4
    rels, rejected = cap.boletin_releases(fx.REPO)
    n3 = next(r for r in rels if r["period"] == "2026-09")
    assert n3["number"] == "N°3-2026" and n3["basis"] == "listing_documents"
    assert n3["published_at"] is None and n3["first_detected_at"].startswith("2026-10-29")  # no publication date exposed
    assert {d["topic"]: d["url"] for d in n3["documents"]} == N3
    assert all(cap.sis_url_ok(u) for u in N3.values())  # same allowlist as every SIS capture
    # The 'Septiembre 2026' page linking the N°2 PDFs stays rejected and is never relabelled as N°3.
    page = next(r for r in rejected if str(r["title"]).endswith("Septiembre 2026"))
    assert page["reasons"] == ["documents_belong_to_other_release"] and page["document_periods"] == ["2026-06"]
    assert next(r for r in rels if r["period"] == "2026-06")["release_url"].endswith("ip-junio-2026/")


def test_loose_pdfs_form_a_release_only_with_one_pdf_per_topic():
    three = [s for s in LOOSE if "rnpi" not in s["source_url"]]
    ok, rejected = cap.loose_boletin_releases(three)
    assert ok == {} and rejected[0]["reasons"] == ["listing_documents_not_one_per_topic"]
    dup = LOOSE + [{**LOOSE[0], "source_url": LOOSE[0]["source_url"].replace(".pdf", "-2.pdf")}]
    assert cap.loose_boletin_releases(dup)[0] == {}
    other = [{**s, "source_name": "Diario Financiero"} for s in LOOSE]  # only the Prestadores listing records count
    assert cap.loose_boletin_releases(other) == ({}, [])


def test_capture_takes_the_n3_pdfs_within_the_same_limits(root):
    rel = next(r for r in store(root)["releases"] if r["period"] == "2026-09")
    assert rel["number"] == "N°3-2026" and rel["basis"] == "listing_documents" and rel["published_at"] is None
    for d in rel["documents"]:
        assert d["status"] == "captured" and d["format"] == "pdf" and sf.HEX64.fullmatch(d["sha256"])
        assert d["parse"]["status"] == "no_verified_metrics"  # no independent reading of N°3 yet
    acr = next(d for d in rel["documents"] if d["topic"] == "acreditacion")
    assert acr["parse"]["checker_version"] == 3 and acr["parse"]["reading_sha256"] is None
    # Pre-check of the approved templates (variable cut-off date): recorded for the reviewer, never a verified figure.
    pre = acr["parse"]["template_precheck"]
    assert pre["with_observations"] == {"status": "ok", "pages_hint": [2], "pages": [1], "page": 1, "on_hint": False,
                                        "figures": [103]}
    assert pre["pending_applications"] == {"status": "ok", "pages_hint": [8], "pages": [1], "page": 1, "on_hint": False,
                                           "figures": [371, 219, 590]}
    assert "verified_present" not in acr["parse"] and "figure_rules" not in acr["parse"]
    # Each document is fetched once: a further run downloads nothing (no reading changed, no new checker).
    again = fx.fetcher(root, BOOKS[str(root)])
    cap.capture(root, fetch=again)
    assert again.calls == []


# ---------------------------------------------------------------------------------------------
# N°3 on HOLD: N°2 stays live


def test_n3_without_verified_figures_keeps_n2_live_and_holds_n3(root):
    out = f6.run(root, today=TODAY, registry=sf.load_registry(), llm=False)
    assert out["status"] == "pass" and out["period"] == "2026-06", out.get("errors")
    fi = out["ficha"]
    assert fi["headline"] == "Prestadores acreditados suman 971 a junio; 101 con observaciones"
    assert fi["watch"][0] == {"headline": "Nuevo boletín (datos a septiembre 2026): cifras en verificación.",
                              "explanation": "La ficha sigue con el boletín de junio 2026 hasta que las cifras del nuevo "
                                             "boletín se verifiquen en los PDF capturados."}
    assert not any("Septiembre 2026: la página publicada" in w["headline"] for w in fi["watch"])
    hold = out["release_holds"]
    assert [h["period"] for h in hold] == ["2026-09"]
    assert "2026-09:not_verified:acreditacion" in hold[0]["errors"]
    assert not any(":template_precheck:" in e for e in hold[0]["errors"])  # the templates already match N°3
    assert sf.publish(out, root)["published"] is True
    written = sf.publish_release_holds(out, root)
    rec = json.loads(Path(written[0]).read_text(encoding="utf-8"))
    assert Path(written[0]).name == "f6_prestadores-2026-09.json" and rec["status"] == "hold" and rec["live_period"] == "2026-06"
    assert sf.load_live(root, "f6_prestadores")["period"] == "2026-06"
    assert sf.release_hold_reasons(root, "F6")["2026-09"] == hold[0]["errors"]


def test_reading_added_later_rechecks_the_captured_n3_once(root):
    add_n3_reading(root)
    fetch = fx.fetcher(root, BOOKS[str(root)])
    cap.capture(root, fetch=fetch)
    assert sorted(fetch.calls) == sorted(N3.values())  # re-read once, same fetch path and limits
    rel = next(r for r in store(root)["releases"] if r["period"] == "2026-09")
    for d in rel["documents"]:
        assert d["status"] == "captured" and d["parse"]["status"] == "verified", (d["topic"], d["parse"])
        assert d["previous_parse"]["status"] == "no_verified_metrics" and d["rechecked_at"]
    cap.capture(root, fetch=fetch)
    assert len(fetch.calls) == 4  # no second re-check


@pytest.mark.parametrize("case", ["no_template_text", "two_tables", "parts_differ"])
def test_n3_holds_when_the_templates_do_not_match_exactly_once(tmp_path, case):
    # Every figure is next to its context word, so checkers v1/v2 would pass; v3 requires the templates.
    extra = {"no_template_text": (), "two_tables": (SENTENCE_P2, TITLE_P8, TOTAL_P8, TITLE_P8, TOTAL_P8),
             "parts_differ": (SENTENCE_P2, TITLE_P8, f"Total general 370 220 {M3['pending_applications']}")}[case]
    root = make(tmp_path, n3_books(extra))
    add_n3_reading(root)
    fx.capture_all(root, fx.fetcher(root, BOOKS[str(root)]))
    acr = next(d for r in store(root)["releases"] if r["period"] == "2026-09" for d in r["documents"]
               if d["topic"] == "acreditacion")
    status = acr["parse"].get("template_status") or {}
    expected = {"no_template_text": {"with_observations": "no_match", "pending_applications": "no_match"},
                "two_tables": {"pending_applications": "multiple_matches:2"},
                "parts_differ": {"pending_applications": "part_mismatch:private_pending"}}[case]
    assert acr["parse"]["status"] == "verified_figure_missing" and status == expected
    out = f6.run(root, today=TODAY, registry=sf.load_registry(), llm=False)
    assert out["status"] == "pass" and out["period"] == "2026-06"  # F6 keeps N°2
    assert any(e.startswith("2026-09:verified_figure_not_in_document:acreditacion:") for e in out["release_holds"][0]["errors"])


# ---------------------------------------------------------------------------------------------
# N°3 verified: the ficha moves to N°3 and compares with N°2


def test_n3_verified_updates_the_ficha_and_compares_stocks_with_n2(root):
    add_n3_reading(root)
    fx.capture_all(root, fx.fetcher(root, BOOKS[str(root)]))
    p = f6.build_package(root, sf.load_registry())
    assert p["reconciliation"]["ok"], p["reconciliation"]
    assert p["period"] == "2026-09" and p["number"] == "N°3-2026"
    assert p["date_basis"] == "first_detected" and p["published_at"] == "2026-10-29"
    c = p["kpis"]["comparisons"]
    assert p["kpis"]["prev"] == "2026-06"
    # Only acreditación stocks (definition confirmed in both texts); RNPI is hidden and mediación shows its level only.
    assert c == {"acr.acreditados": 980 - 971, "acr.con_observaciones": 103 - 101, "acr.tramite": 590 - 584,
                 "acr.tramite.privadas": 371 - 367, "acr.tramite.publicas": 219 - 217}
    # Stocks compared, never summed; the claims average (a flow) and the accumulated requests are not compared.
    assert not any(k.startswith(("rec.", "med.solicitudes")) for k in c)
    assert not any("+" in str(v.get("formula") or "") and v.get("unit") != "%" for v in p["values"].values()
                   if v.get("kind") == "derived" and str(v.get("id", "")).endswith(".qoq"))
    acr = next(d for r in store(root)["releases"] if r["period"] == "2026-09" for d in r["documents"] if d["topic"] == "acreditacion")
    assert acr["parse"]["figure_rules"]["with_observations"]["rule"] == "template"
    assert acr["parse"]["figure_rules"]["pending_applications"]["sum_check"] == "371 + 219 = 590"
    assert "al 30 de septiembre de 2026" in acr["parse"]["figure_rules"]["pending_applications"]["match"]
    out = f6.run(root, today=TODAY, registry=sf.load_registry(), llm=False)
    assert out["status"] == "pass" and out["period"] == "2026-09" and "release_holds" not in out, out.get("errors")
    fi = out["ficha"]
    assert fi["headline"] == "Prestadores acreditados llegan a 980 a septiembre, 9 más que en junio; 103 con observaciones"
    assert fi["kicker_meta"].startswith("datos a septiembre 2026 · detectado por Alicanto el 29 oct")
    assert "publicado" not in fi["kicker_meta"] and fi["date_basis"] == "first_detected"
    assert "+9 vs. junio 2026" in fi["kpis"][0]["lines"]
    assert "detectado por Alicanto el" in fi["machine_note"]
    card = sf.ficha_card(fi | {"status": "PASS"}, sf.load_registry()["families"]["F6"])
    assert card["publication_date"] is None and card["date_basis"] == "first_detected"


# ---------------------------------------------------------------------------------------------
# One card for the loose N°3 PDFs while N°3 is on HOLD


def live_n2():
    return json.loads((fx.REPO / "data/stats_fichas/live/f6_prestadores.json").read_text(encoding="utf-8"))


def page_card():
    s = next(x for x in HIST if str(x.get("title")).endswith("IP – Septiembre 2026"))
    return sb.apply_bulletin_period({**s, "signal_types": ["Datos"]})


def test_loose_n3_pdfs_collapse_into_one_card_titled_from_the_documents():
    others = [{"title": "Otra noticia", "source_name": "Ministerio de Salud", "source_url": "https://www.minsal.cl/x"}]
    cards = [dict(s) for s in LOOSE] + others
    out = sb.collapse_loose_bulletins(cards, history=HIST, fichas=[live_n2()], holds={"2026-09": ["2026-09:not_verified:acreditacion"]})
    assert len(out) == 2 and out[1] == others[0]
    c = out[0]
    assert c["title"] == c["display_title"] == "Boletín Estadístico Informativo IP N°3 · enero–septiembre 2026"
    assert c["loose_bulletin"]["series_name_basis"] == "history_release_page"
    assert [d["label"] for d in c["source_documents"]] == ["acreditación", "mediación", "reclamos", "RNPI"]
    assert [d["url"] for d in c["source_documents"]] == [N3[t] for t in cap.TOPICS]
    # Each PDF keeps the listing's own link text (never rewritten).
    assert {d["title"] for d in c["source_documents"]} == {" ".join(s["title"].split()) + " (PDF)" for s in LOOSE}
    assert c["source_url"] == N3["acreditacion"] and c["date_basis"] == "first_detected" and c["publication_date"] is None
    assert c["event_date"] == "2026-10-29" and c["data_period"] == "enero–septiembre 2026"
    assert c["stat_family"] == "boletin_ip" and c["stat_period"] == "2026-09"
    assert c["what_happened"] == ("La Intendencia de Prestadores de la Superintendencia de Salud tiene disponible el Boletín "
                                  "N°3-2026 (enero–septiembre 2026) en 4 PDF: acreditación, mediación, reclamos y RNPI.")
    st = c["bulletin_status"]
    assert st["status"] == "verifying" and "verificando las cifras" in st["text"] and st["hold_reasons"]
    assert st["live_ficha"] == {"id": "stats-ficha:F6:2026-06", "period": "2026-06",
                                "label": "Ver la ficha vigente: Boletín IP N°2-2026 · datos a junio 2026"}
    assert c["editorial_committee"]["verdict"] == "PASS"
    # No figure of N°3 anywhere in the card: only numbers from the file names and the live ficha's label.
    import re
    text = json.dumps({k: c[k] for k in ("title", "what_happened", "bulletin_status")}, ensure_ascii=False)
    assert set(re.findall(r"\d+", text)) <= {"3", "2026", "4", "2", "06", "09", "6", "9"}


def test_live_n2_keeps_the_n3_card_and_absorbs_the_september_page_card():
    reg = sf.load_registry()
    cards = sb.collapse_loose_bulletins([dict(s) for s in LOOSE] + [page_card()], history=HIST, fichas=[live_n2()])
    out = sf.apply_to_snapshot(cards, [live_n2()], reg)
    titles = [c.get("display_title") or c.get("title") for c in out]
    assert "Boletín Estadístico Informativo IP N°3 · enero–septiembre 2026" in titles
    # The 'Septiembre 2026' page links the N°2 PDFs (stat_period 2026-06 from its documents): the N°2 ficha covers it.
    assert "Boletín Estadístico Informativo IP N°2 · enero–junio 2026" not in titles
    assert sum(1 for c in out if c.get("stats_ficha")) == 1


def test_when_n3_is_live_the_collapsed_card_is_absorbed():
    reg = sf.load_registry()
    n3_live = copy.deepcopy(live_n2()) | {"period": "2026-09", "id": "stats-ficha:F6:2026-09"}
    cards = sb.collapse_loose_bulletins([dict(s) for s in LOOSE], history=HIST, fichas=[n3_live])
    assert cards[0]["bulletin_status"] is None  # nothing to verify any more
    out = sf.apply_to_snapshot(cards, [n3_live], reg)
    assert [c.get("piece_id") for c in out] == ["stats-ficha:F6:2026-09"]


def test_title_without_a_series_page_in_history_falls_back_to_the_file_names():
    c = sb.collapse_loose_bulletins([dict(s) for s in LOOSE], history=[], fichas=[])[0]
    assert c["title"] == "Boletín N°3-2026 · enero–septiembre 2026" and c["loose_bulletin"]["series_name_basis"] == "none"
    assert "live_ficha" not in c["bulletin_status"]


def test_two_bulletin_numbers_for_one_period_give_no_release_and_keep_the_rejection():
    # Review 2-nov: N°3 complete plus a stray (or complete) N°4 for 2026-09 must not resolve silently.
    from radar_salud.stats_capture import loose_boletin_releases, LOOSE_SOURCE, TOPICS
    def sig(n, topic):
        return {"source_name": LOOSE_SOURCE, "title": f"Boletín N°{n}-2026 {topic}",
                "source_url": f"https://www.superdesalud.gob.cl/app/uploads/2026/10/boletin-n{n}-2026-{topic}-enero-septiembre-2026.pdf"}
    n3 = [sig(3, t) for t in TOPICS]
    for extra in ([sig(4, TOPICS[0])], [sig(4, t) for t in TOPICS]):
        ok, rejected = loose_boletin_releases(n3 + extra)
        assert "2026-09" not in ok
        assert any("multiple_bulletin_numbers_for_period" in r["reasons"] for r in rejected)


def test_a_non_pdf_listing_file_never_forms_a_release():
    from radar_salud.stats_capture import loose_boletin_releases, LOOSE_SOURCE, TOPICS
    sigs = [{"source_name": LOOSE_SOURCE, "title": t, "source_url":
             f"https://www.superdesalud.gob.cl/app/uploads/2026/10/boletin-n3-2026-{t}-enero-septiembre-2026.{'xlsx' if i == 0 else 'pdf'}"}
            for i, t in enumerate(TOPICS)]
    ok, _ = loose_boletin_releases(sigs)
    assert "2026-09" not in ok


# ---------------------------------------------------------------------------------------------
# The committed N°3 reading (2-nov-2026), checked against the committed text receipts of the hashed PDFs


REAL_N3 = {"acreditacion": {"accredited_providers": 1009, "with_observations": 124, "pending_applications": 574,
                            "private_pending": 357, "public_pending": 217},
           "mediacion": {"registered_mediators": 179, "cumulative_requests_2019_to_september2026": 12697},
           "reclamos": {"monthly_average_2026": 1880, "monthly_average_2025": 1530, "reported_growth_percent_rounded": 23},
           "rnpi": {"records_without_birth_date": 5688}}


def committed_root(tmp_path):
    """Copy of the committed registry, readings, history and text receipts, with the Boletín capture store as committed
    on 2-nov-2026 (staging 91b0f422: N°3 captured, nothing re-checked yet). The daily run keeps re-checking and
    committing the live store, so these tests pin the state they describe instead of following it (3-nov-2026: the
    first re-check run turned N°3 'ok' and broke every PR's CI)."""
    import shutil
    r = tmp_path / "committed"
    for rel in ("config/stats_fichas_v1.json", "config/statistical_analysis_verified_v1.json",
                "data/history/superintendencia_signals.json"):
        (r / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(fx.REPO / rel, r / rel)
    (r / STORE).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(Path(__file__).parent / "fixtures/stats_fichas/boletin_ip_store_2026-11-02.json", r / STORE)
    shutil.copytree(fx.REPO / "data/stats_fichas/text", r / "data/stats_fichas/text")
    return r


def recheck_from_receipts(r, monkeypatch, n2=True):
    """What the daily run's one re-check does, with the production checker fed the text of the receipt of each hashed
    PDF (same pypdf extraction) instead of downloading it again; records the parse in the copied store.

    ``n2``: SIMULATED stand-in for the daily re-check of the three N°2 PDFs verified before reading hashes existed
    (mediación, reclamos, RNPI; no committed text receipt): their recorded 'verified' parse is bound to the unchanged
    N°2 reading. Production never does this; it re-downloads and re-checks them (see the committed-state test)."""
    s = store(r)
    verified = cap.verified_metrics(r)
    if n2:
        for d in next(x for x in s["releases"] if x["period"] == "2026-06")["documents"]:
            info = verified[d["url"]]
            if d["parse"].get("reading_sha256") is None:
                assert d["parse"]["status"] == "verified" and all(d["parse"]["verified_present"].values())
                assert set(d["parse"]["verified_present"]) == set(info["metrics"])
                d["parse"]["reading_sha256"] = cap.reading_sha256(info["metrics"], info["pages_1based"])
    for d in next(x for x in s["releases"] if x["period"] == "2026-09")["documents"]:
        rc = json.loads((r / cap.text_receipt_path(d["sha256"])).read_text(encoding="utf-8"))
        assert rc["sha256"] == d["sha256"] and rc["url"] == d["url"] and not rc["truncated"]
        monkeypatch.setattr(cap, "pdf_pages", lambda _b, pages=[p["text_raw"] for p in rc["pages"]]: pages)
        info = verified[d["url"]]
        d["previous_parse"], d["parse"] = d["parse"], cap.parse_boletin_pdf(
            b"", info["metrics"], info["pages_1based"], d["topic"], cap.figure_templates(r, d["topic"]))
    (r / STORE).write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
    return s


def test_committed_n3_reading_uses_the_capture_urls_and_n2_metric_keys():
    verified = cap.verified_metrics(fx.REPO)
    rel = next(r for r in store(fx.REPO)["releases"] if r["period"] == "2026-09")
    for d in rel["documents"]:
        assert verified[d["url"]]["metrics"] == REAL_N3[d["topic"]], d["topic"]  # URL exactly as captured
        for key in verified[d["url"]]["metrics"]:
            assert f6._metric_id(d["topic"], key, "2026-09"), key  # same keys as N°2, month names in English
    # The RNPI total is not read (p.1/p.4 say 1018018, p.2 '1012330 titulos inscritos'): not verified, not shown.
    assert "registered_titles" not in verified[N3["rnpi"]]["metrics"]


def test_committed_state_holds_n3_until_the_daily_run_rechecks_the_hashed_pdfs(tmp_path):
    r = committed_root(tmp_path)
    p = f6.build_package(r, sf.load_registry())
    assert p["releases_state"]["2026-09"] == [f"reading_awaits_document_recheck:{t}" for t in sorted(cap.TOPICS)]
    # N°2's mediación, reclamos and RNPI parses predate reading hashes: bound to no reading, so they are re-checked too.
    assert p["releases_state"]["2026-06"] == [f"reading_awaits_document_recheck:{t}" for t in ("mediacion", "reclamos", "rnpi")]
    assert not p["reconciliation"]["ok"]
    # The build HOLDs; the live N°2 file is left as it is (HOLD never publishes or unpublishes).
    (r / "data/stats_fichas/live").mkdir(parents=True, exist_ok=True)
    live = r / "data/stats_fichas/live/f6_prestadores.json"
    live.write_text((fx.REPO / "data/stats_fichas/live/f6_prestadores.json").read_text(encoding="utf-8"), encoding="utf-8")
    before = live.read_bytes()
    out = f6.run(r, today=date(2026, 11, 2), registry=sf.load_registry(), llm=False)
    assert out["status"] == "hold" and not sf.publish(out, r)["published"]
    assert live.read_bytes() == before and sf.load_live(r, "f6_prestadores")["period"] == "2026-06"
    # The next capture run re-reads each N°3 PDF once (same fetcher and limits); here the download fails (offline),
    # the previous record is kept and nothing is verified.
    calls = []

    def offline(url):
        calls.append(url)
        raise OSError("offline")
    cap.capture(r, fetch=offline)
    assert set(N3.values()) <= set(calls)
    n2 = {d["topic"]: d["url"] for x in store(r)["releases"] if x["period"] == "2026-06" for d in x["documents"]}
    assert n2["acreditacion"] not in calls  # its parse is bound to the unchanged reading (checker v3)
    rel = next(x for x in store(r)["releases"] if x["period"] == "2026-09")
    assert all(d["parse"]["status"] == "no_verified_metrics" and d["recheck"]["status"] == "fetch_failed"
               for d in rel["documents"])


def test_n3_from_the_receipts_publishes_the_approved_ficha(tmp_path, monkeypatch):
    r = committed_root(tmp_path)
    s = recheck_from_receipts(r, monkeypatch)
    acr = next(d for x in s["releases"] if x["period"] == "2026-09" for d in x["documents"] if d["topic"] == "acreditacion")
    assert acr["parse"]["status"] == "verified"
    rules = acr["parse"]["figure_rules"]
    assert rules["with_observations"]["rule"] == "template" and rules["with_observations"]["page"] == 2
    assert rules["pending_applications"]["sum_check"] == "357 + 217 = 574" and rules["pending_applications"]["page"] == 8
    p = f6.build_package(r, sf.load_registry())
    c = p["kpis"]["comparisons"]  # quarter on quarter: verified stocks of the same definition, never summed
    assert c["acr.acreditados"] == 1009 - 971 and c["acr.con_observaciones"] == 124 - 101 and c["acr.tramite"] == 574 - 584
    assert not any(k.startswith(("med.", "rnpi.")) for k in c)  # no N°2 mediación text to confirm the definition
    assert not any(k.startswith("rnpi.") for k in p["values"])  # hidden topic: out of the package and number pool
    out = f6.run(r, today=date(2026, 11, 2), registry=sf.load_registry(), llm=False)
    assert out["status"] == "pass" and out["period"] == "2026-09" and "release_holds" not in out, out.get("errors")
    fi = out["ficha"]
    assert fi["verification"]["verdict"] == "PASS"
    # Headline (Dirección 2-nov), generated from verified values.
    assert fi["headline"] == "Prestadores acreditados llegan a 1.009 a septiembre, 38 más que en junio; 124 con observaciones"
    assert fi["headline_type"] == "qoq_up"
    assert [t["label"] for t in fi["tabs"]] == ["Acreditación", "Con observaciones", "Reclamos", "Mediación"]
    assert {t["id"]: t["index_line"] for t in fi["tabs"]} == {
        "acreditacion": "1.009 prestadores acreditados · +38 vs. junio",
        "observaciones": "124 con observaciones (12,3%) · 101 en junio",
        "reclamos": "1.880 reclamos al mes · +22,9% vs. 2025",
        "mediacion": "179 mediadores inscritos"}
    # 'Mostrar con nota': the applications chart carries the reading's footnote; the SIS figures are not changed.
    tram = next(ch for t in fi["tabs"] for ch in t["charts"] if ch["id"] == "f6-tramite")
    assert tram["source"].endswith("En el boletín, las solicitudes por etapa del proceso suman una menos que el total "
                                   "informado (574) y que el de públicas (217).")
    assert [row["value"] for row in tram["rows"]] == [357, 217]
    assert tram["subtitle"].endswith("septiembre 2026: 574, 10 menos que en junio 2026")
    assert sum("suman una menos" in x for x in sf.displayed_texts(fi)) == 1
    # 574 and 217 appear only in that chart (subtitle, bars, table, source with its note): not in the dek, the feed
    # card text or any topic text.
    rest = {**fi, "tabs": [{**t, "charts": [c for c in t["charts"] if c["id"] != "f6-tramite"]} for t in fi["tabs"]]}
    assert not any("574" in x or "217" in x for x in sf.displayed_texts(rest))
    card = sf.ficha_card(fi | {"status": "PASS"}, sf.load_registry()["families"]["F6"])
    assert "574" not in card["card_what"] and "574" not in card["what_happened"]
    # No RNPI anywhere on the page (the document still gates the release).
    shown = " ".join(sf.displayed_texts(fi))
    assert "RNPI" not in shown and "5.688" not in shown and not any("rnpi" in x["url"] for x in fi["sources"])
    # The rejected 'Septiembre 2026' page is no longer news once N°3 is the ficha's release.
    assert not any("página publicada" in w["headline"] for w in fi["watch"])
    assert fi["watch"][0]["headline"].startswith("Boletín IP a diciembre 2026")


def test_a_source_note_with_an_unknown_figure_holds(tmp_path, monkeypatch):
    r = committed_root(tmp_path)
    path = r / cap.VERIFIED
    cfg = json.loads(path.read_text(encoding="utf-8"))
    doc = next(d for d in cfg["primary_review"]["documents"] if d["url"] == N3["acreditacion"])
    doc["source_notes"] = {"pending_applications": "Las etapas suman {stage_total}."}
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    recheck_from_receipts(r, monkeypatch)
    p = f6.build_package(r, sf.load_registry())
    assert not p["reconciliation"]["ok"]
    assert "source_note_invalid:acreditacion:pending_applications" in p["reconciliation"]["failures"]


def _edit_reading(r, url, key, val):
    path = r / cap.VERIFIED
    cfg = json.loads(path.read_text(encoding="utf-8"))
    next(d for d in cfg["primary_review"]["documents"] if d["url"] == url)["verified_metrics"][key] = val
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")


@pytest.mark.parametrize("topic,key,val", [("mediacion", "registered_mediators", 180),
                                           ("acreditacion", "accredited_providers", 1010),
                                           ("reclamos", "monthly_average_2026", 1881)])
def test_a_reading_edited_after_the_check_holds_until_rechecked(tmp_path, monkeypatch, topic, key, val):
    # Review of PR #126 (stale probe): a verified parse is bound to the reading it checked, for every checker version.
    r = committed_root(tmp_path)
    recheck_from_receipts(r, monkeypatch)
    first = f6.run(r, today=date(2026, 11, 2), registry=sf.load_registry(), llm=False)
    assert first["status"] == "pass" and sf.publish(first, r)["published"]
    live = (r / "data/stats_fichas/live/f6_prestadores.json").read_bytes()
    _edit_reading(r, N3[topic], key, val)
    p = f6.build_package(r, sf.load_registry())
    assert p["releases_state"]["2026-09"] == [f"reading_awaits_document_recheck:{topic}"]
    assert p["period"] == "2026-06"  # the edited figure is never shown: N°3 is not usable until re-checked
    out = f6.run(r, today=date(2026, 11, 2), registry=sf.load_registry(), llm=False)
    assert out["status"] == "hold" and "HOLD_OLDER_PERIOD" in out["errors"] and "ficha" not in out
    assert not sf.publish(out, r)["published"]
    assert (r / "data/stats_fichas/live/f6_prestadores.json").read_bytes() == live  # live N°3 (checked figures) stays
    calls = []

    def offline(url):
        calls.append(url)
        raise OSError("offline")
    cap.capture(r, fetch=offline)  # the capture run re-checks that document (offline here: still HOLD)
    assert N3[topic] in calls
    assert f6.run(r, today=date(2026, 11, 2), registry=sf.load_registry(), llm=False)["status"] == "hold"


def test_n3_holds_while_n2_awaits_its_recheck(tmp_path, monkeypatch):
    # N°3 verified but N°2 (the comparison base) still awaiting its re-check: HOLD, never a ficha without the comparison.
    r = committed_root(tmp_path)
    recheck_from_receipts(r, monkeypatch, n2=False)
    p = f6.build_package(r, sf.load_registry())
    assert p["releases_state"]["2026-09"] == ["ok"]
    assert "2026-06:previous_release_reading_awaits_document_recheck:mediacion" in p["reconciliation"]["failures"]
    assert f6.run(r, today=date(2026, 11, 2), registry=sf.load_registry(), llm=False)["status"] == "hold"
