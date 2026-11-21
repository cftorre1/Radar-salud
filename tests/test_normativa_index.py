"""Normativa phase 1 (Dirección, 10–11-nov-2026): standing registry, literal effective dates, manual review."""
import json
import re
from datetime import date
from pathlib import Path

from radar_salud import normativa_index as ni

ROOT = Path(__file__).resolve().parents[1]


def sig(label, typ, src="Superintendencia de Salud", validity=None, ev="2026-11-02", url=None, title=None):
    return {"normative_document_label": label, "normative_document_type": typ, "source_name": src, "event_type": "REGULATION",
            "signal_types": ["Normativa"], "validity_text": validity, "event_date": ev, "source_url": url or f"https://x/{label}",
            "display_title": title or f"{label} · Asunto de {label}"}


def test_parse_validity_is_literal_only():
    p = ni.parse_validity
    assert p("Las disposiciones comenzarán a regir a partir del 1° de enero de 2027 .") == {"kind": "date", "eff": "2027-01-01", "prec": "day", "target": None}
    assert p("Las disposiciones comienzan a regir a contar del mes de marzo de 2027. Dentro de ese plazo…")["prec"] == "month"
    assert p("desde su publicación. Contiene disposiciones transitorias")["kind"] == "on_publication"
    # Review of #180: notification and the Diario Oficial are their own triggers, also OCR-spaced.
    assert p("Las disposiciones de la presente Circular entrarán en vigencia a contar de su notificación.")["kind"] == "on_notification"
    assert p("a contar de la fecha de su not ificació n")["kind"] == "on_notification"
    assert p("desde la fecha de notificación de la Circular")["kind"] == "on_notification"
    assert p("Las disposiciones de la presente Circular entrarán en vigencia a contar de la fecha de su publ icació n en el Diario Oficial")["kind"] == "on_publication_do"
    assert p("a contar de su fecha de publicación")["kind"] == "on_publication"
    assert p("a contar de esta fecha")["kind"] == "on_emission"
    # Never an entry into force: operational starts, deadlines, expiries, impossible dates, relative terms.
    for t in ("Inicio operativo informado: 30 de septiembre de 2026", "Las Isapres deberán remitir el archivo hasta el 15 de enero de 2027.",
              "La autorización tiene vigencia hasta el 30 de junio de 2029.", "Entra en vigencia el 31 de febrero de 2027.",
              "6 meses corridos contados desde su publicación. Contiene disposiciones transitorias.", None, ""):
        assert p(t)["kind"] == "none", t
    # «desde su notificación» wins over a later expiry date; exceptions and several dates are partial.
    r = p("Las instrucciones rigen desde su notificación y se mantiene hasta el 31 de diciembre de 2026.")
    assert r["kind"] == "on_notification" and r["partial"]
    assert p("A partir del 1° de octubre de 2026, salvo aquellas que constan en el numeral 10.2, cuya")["partial"]
    assert p("Capítulo I de esta Circular, desde 30 de enero de 2026 y el Capítulo II desde el 30 de abril de 2026,")["partial"]
    # A date after a cue, not the emission date that precedes it.
    assert p("La Circular IF N°505, de 13 de agosto de 2025, entrará en vigencia el 1 de enero de 2026.")["eff"] == "2026-01-01"
    assert p("4 de enero de 2027")["eff"] == "2027-01-04"
    r = p("La Circular IF/N° 532 difirió su entrada en vigencia hasta el 1 de enero de 2027.")
    assert r["target"] == "Circular IF/N°532" and r["eff"] == "2027-01-01"


def test_every_historical_date_has_an_entry_into_force_cue():
    """Every date the parser takes from the real captured texts follows a cue or is the whole text (review of #180)."""
    sig = json.loads((ROOT / "data/history/superintendencia_signals.json").read_text(encoding="utf-8"))["signals"]
    for t in {s["validity_text"] for s in sig if s.get("validity_text")}:
        r = ni.parse_validity(t)
        if r["kind"] == "date":
            assert not re.search(r"(?i)^\s*Inicio operativo|deber[aá]n remitir", t), t

def test_registry_never_drops_by_age_and_keeps_literal_text():
    reg = ni.update_registry({"items": {}}, [sig("Circular IF/N°534", "Circular", validity="Las disposiciones entran en vigencia el 1 de diciembre de 2026.")], date(2026, 11, 11))
    key = next(iter(reg["items"]))
    later = ni.update_registry(reg, [], date(2027, 6, 1))  # out of the 90-day feed: still there
    assert key in later["items"]
    again = ni.update_registry(later, [sig("Circular IF/N°534", "Circular", validity=None)], date(2027, 6, 2))
    assert again["items"][key]["validity"].startswith("Las disposiciones entran") and again["items"][key]["first_seen"] == "2026-11-11"


def test_build_groups_inputs_topics_review_and_ficha():
    s = [sig("Circular IF/N°541", "Circular", validity="desde su publicación", title="Circular IF/N°541 · Aclara el deducible CAEC"),
         sig("Circular N°3930", "Circular", src="SUSESO", validity="desde 1° de marzo de 2027", title="Circular N°3930 · Licencias médicas en papel"),
         sig("Circular N°3935", "Circular", src="SUSESO", title="Circular N°3935 · Pago de remuneraciones"),
         {**sig("Dictamen O-02-S-03153-2026", None, src="SUSESO", validity="Inicio operativo informado: 30 de septiembre de 2026"), "normative_document_type": None},
         sig("Ley 21.822", "Ley", src="Diario Oficial")]
    reg = ni.update_registry({"items": {}}, s, date(2026, 11, 11))
    assert len(reg["items"]) == 4  # the law is not a SIS/SUSESO norm
    review = {"decisions": {"suseso-circular-n3935": {"kind": "susp", "by": "Resolución Exenta N°1", "quote": "Se suspende la aplicación de la circular.", "on": "2026-11-12", "decided_by": "Dirección"},
                            "bad": {"kind": "susp", "by": "x", "quote": "corta", "on": "2026-11-12"}}}
    ix = ni.build(reg, review, {ni.signal_id(s[0])})
    by = {x["label"]: x for x in ix["items"]}
    assert by["Circular IF/N°541"]["tema"] == "Isapres: planes, GES y CAEC" and by["Circular IF/N°541"]["kind"] == "on_publication"
    assert by["Circular N°3930"]["tema"] == "Licencias médicas y SIL" and by["Circular N°3930"]["eff"] == "2027-03-01"
    assert by["Dictamen O-02-S-03153-2026"]["type"] == "Dictamen" and by["Dictamen O-02-S-03153-2026"]["kind"] == "none"  # «Inicio operativo» is not a vigencia
    assert by["Circular N°3935"]["review"]["kind"] == "susp" and by["Circular N°3935"]["kind"] == "none"
    assert by["Circular IF/N°541"]["in_feed"] and not by["Circular N°3930"]["in_feed"]
    assert all(x["ficha"].startswith(f"index.html?abrir=1&desde=normativa&n={x['id']}#sig-") for x in ix["items"])
    assert ix["review_pending"] == 0  # Dirección 21-nov-2026: a text with no date is in force from its date


def test_signal_id_matches_al_dia():
    import base64
    s = {"source_url": "https://www.superdesalud.gob.cl/x/", "event_date": "2026-09-14", "event_type": "REGULATION"}
    assert base64.b64decode(ni.signal_id(s)).decode() == "https://www.superdesalud.gob.cl/x/|2026-09-14|REGULATION"
    assert ni.signal_id({"piece_id": "p"}) == "p"


def test_published_index_is_built_from_the_registry_and_review():
    pub = json.loads((ROOT / "web/data/normativa.json").read_text(encoding="utf-8"))
    reg = json.loads((ROOT / ni.REGISTRY).read_text(encoding="utf-8"))
    review = json.loads((ROOT / ni.REVIEW).read_text(encoding="utf-8"))
    # Withheld records (e.g. norms outside health, Dirección 12-nov-2026) stay in the registry but leave the index.
    shown = [r for r in reg["items"].values() if not r.get("withheld")]
    assert pub["schema"] == ni.SCHEMA and pub["count"] == len(pub["items"]) >= 25
    assert pub["count"] <= len(shown) <= len(reg["items"])
    rebuilt = ni.build(reg, review, {x["signal_id"] for x in pub["items"] if x.get("in_feed")}, pub.get("generated_at"))
    assert rebuilt["items"] == pub["items"]
    for x in pub["items"]:
        assert x["kind"] in ("date", "on_publication", "on_notification", "on_publication_do", "on_emission", "none") and x["emisor"] in ("SIS", "SUSESO")
        if x["kind"] == "date":
            assert x["validity"], x["label"]  # every date comes from captured literal text


def test_export_writes_normativa_next_to_the_snapshot_and_workflows_keep_the_registry():
    src = (ROOT / "scripts/export_web_snapshot.py").read_text(encoding="utf-8")
    assert "normativa_index.export(" in src
    for wf in ("daily-radar.yml", "queue-hourly.yml"):
        assert "git add data/normativa" in (ROOT / ".github/workflows" / wf).read_text(encoding="utf-8")


def test_withheld_and_withdrawn_norms_leave_the_public_index_and_offline_builds_never_write(tmp_path):
    s = sig("Circular IF/N°534", "Circular", validity="Las disposiciones entran en vigencia el 1 de diciembre de 2026.")
    reg = ni.update_registry({"items": {}}, [s], date(2026, 11, 11))
    key = next(iter(reg["items"]))
    held = ni.update_registry(reg, [{**s, "editorial_committee": {"verdict": "HOLD"}}], date(2026, 11, 12))
    assert held["items"][key]["withheld"] and ni.build(held, {}, set())["items"] == []
    back = ni.update_registry(held, [s], date(2026, 11, 13))
    assert not back["items"][key].get("withheld") and len(ni.build(back, {}, set())["items"]) == 1
    gone = {"decisions": {key: {"kind": "retirada", "on": "2026-11-14", "decided_by": "Dirección"}}}
    assert ni.build(back, gone, set())["items"] == []
    # No churn: the same capture leaves the record untouched.
    assert ni.update_registry(back, [s], date(2027, 1, 5)) == back
    # Offline / --as-of builds read the registry but never write it.
    (tmp_path / "data/normativa").mkdir(parents=True)
    (tmp_path / "web").mkdir()
    ni.export([s], tmp_path, tmp_path / "web", date(2026, 10, 12), persist=False)
    assert not (tmp_path / ni.REGISTRY).exists() and (tmp_path / "web/normativa.json").exists()


def test_review_round_2_terms_deadlines_and_hidden_norms():
    p = ni.parse_validity
    # Deadlines, sending duties and relative terms are never an entry into force (also in words, without «contados»).
    for t in ("Deberán remitirse hasta el mes de junio de 2026", "El plazo vence el mes de marzo de 2026",
              "a contar de la remuneración correspondiente al mes de junio de 2026",
              "Las instrucciones comenzarán a regir en el plazo de 30 días desde su notificación",
              "dentro de cinco días hábiles contados desde la notificación",
              "pagar dentro de cinco días hábiles desde la notificación", "seis meses contados desde su publicación"):
        assert p(t)["kind"] == "none", t
    # The cued date is the rule when publication is only the exception; «del año» and «1ro» are dates.
    r = p("La presente circular rige desde el 31 de marzo del año 2025, con excepción de los numerales que rigen a partir de la fecha de su publicación")
    assert r["kind"] == "date" and r["eff"] == "2025-03-31" and r["partial"]
    assert p("entrará en vigencia el 1ro de enero de 2026")["eff"] == "2026-01-01"
    # A norm hidden later (dropped by curation before export) is withheld from its newest history record.
    s = sig("Circular IF/N°535", "Circular", validity="Las disposiciones entran en vigencia el 1 de diciembre de 2026.")
    reg = ni.update_registry({"items": {}}, [s], date(2026, 11, 11))
    key = next(iter(reg["items"]))
    hidden = ni.update_registry(reg, [], date(2026, 11, 12), history=[s, {**s, "feed_visibility": False}])
    assert hidden["items"][key]["withheld"]
    assert not ni.update_registry(reg, [], date(2026, 11, 12), history=[s])["items"][key].get("withheld")


def test_decision_7_archive_only_enters_when_direccion_lists_it(tmp_path):
    """Dirección 11-nov-2026: an older norm (out of Al día's window) joins the registry only from review.json
    «archive_include», and never the feed."""
    import json as _json
    old = sig("Circular IF/N°532", "Circular", validity="La circular entra en vigencia el 1 de enero de 2027.")
    old["event_date"] = "2026-07-31"
    (tmp_path / "data/normativa").mkdir(parents=True)
    out = tmp_path / "web"; out.mkdir()
    ni.export([], tmp_path, out, date(2026, 11, 11), persist=False, archive=[old])
    assert not _json.loads((out / "normativa.json").read_text())["items"]
    rid = ni.record_from_signal(old)["id"]
    (tmp_path / "data/normativa/review.json").write_text(_json.dumps({"decisions": {}, "archive_include": [rid]}))
    items = _json.loads((out / "normativa.json").read_text()) and ni.export([], tmp_path, out, date(2026, 11, 11), persist=False, archive=[old])["items"]
    assert [x["label"] for x in items] == ["Circular IF/N°532"] and not items[0].get("in_feed")


def test_decision_7_verifier_accepts_the_same_qualifier_in_the_quote():
    from radar_salud import normative_autorecord as na
    ev = ("MODIFICA EL TÍTULO II DEL LIBRO IV DEL COMPENDIO DE NORMAS DEL SEGURO DE LA LEY N°16.744 E IMPARTE INSTRUCCIONES "
          "A LOS ORGANISMOS ADMINISTRADORES DEL SEGURO. Vigencia: 6 meses corridos contados desde su publicación. "
          "Contiene disposiciones transitorias. Plazo: 30 días hábiles contados desde su notificación al organismo.")
    rec = {"plain_language_title": "Circular N°3933 · Compendio del seguro laboral: modifica el Título II",
           "subject_terms": ["COMPENDIO"], "action_terms": ["MODIFICA"],
           "normative_context": "Imparte instrucciones a los organismos administradores. Vigencia: 6 meses corridos contados desde su publicación.",
           "evidence_quotes": ["MODIFICA EL TÍTULO II DEL LIBRO IV DEL COMPENDIO DE NORMAS DEL SEGURO DE LA LEY N°16.744",
                               "Vigencia: 6 meses corridos contados desde su publicación. Contiene disposiciones transitorias."]}
    assert not [p for p in na.verify(rec, "Circular N°3933", ev) if "quantity" in p]
    bare = {**rec, "normative_context": "Imparte instrucciones a los organismos administradores. Plazo de 30 días.",
            "evidence_quotes": rec["evidence_quotes"][:1] + ["Plazo: 30 días hábiles contados desde su notificación al organismo."]}
    assert "date_or_quantity_not_literal_in_quote:30 días" in na.verify(bare, "Circular N°3933", ev)


def test_decision_7_review_a_bare_figure_still_needs_its_own_quote():
    from radar_salud import normative_autorecord as na
    ev = ("MODIFICA EL TÍTULO II DEL LIBRO IV DEL COMPENDIO DE NORMAS DEL SEGURO DE LA LEY N°16.744 E IMPARTE INSTRUCCIONES "
          "A LOS ORGANISMOS ADMINISTRADORES DEL SEGURO. Plazo: 30 días hábiles contados desde su notificación al organismo.")
    rec = {"plain_language_title": "Circular N°3933 · Compendio del seguro laboral: modifica el Título II",
           "subject_terms": ["COMPENDIO"], "action_terms": ["MODIFICA"],
           "normative_context": "Plazo de 30 días hábiles; luego otros 30 días para informar.",
           "evidence_quotes": ["MODIFICA EL TÍTULO II DEL LIBRO IV DEL COMPENDIO DE NORMAS DEL SEGURO DE LA LEY N°16.744",
                               "Plazo: 30 días hábiles contados desde su notificación al organismo."]}
    assert "date_or_quantity_not_literal_in_quote:30 días" in na.verify(rec, "Circular N°3933", ev)


def test_withheld_registry_records_leave_the_published_index():
    reg = {"items": {"a": {"id": "a", "label": "Circular N°1", "emisor": "SUSESO", "type": "Circular", "date": "2026-11-01",
                           "subject": "Licencias médicas", "url": "https://www.suseso.gob.cl/a", "validity": None, "related": []},
                     "b": {"id": "b", "label": "Circular N°3937", "emisor": "SUSESO", "type": "Circular", "date": "2026-11-01",
                           "subject": "Crédito social de las C.C.A.F.", "url": "https://www.suseso.gob.cl/b", "validity": None,
                           "related": [], "withheld": True}}}
    built = ni.build(reg, {"decisions": {}}, set(), "2026-11-12T00:00:00+00:00")
    assert [x["id"] for x in built["items"]] == ["a"] and built["count"] == 1


def test_term_from_publication_is_computed_only_in_calendar_units():
    # Dirección 20-nov-2026: «Sin fecha» only when the text truly gives none.
    f = ni.term_from_publication
    assert f("6 meses corridos contados desde su publicación. Contiene disposiciones transitorias.", "2026-10-28")["eff"] == "2027-04-28"
    assert f("90 días corridos desde su publicación", "2026-01-31")["eff"] == "2026-05-01"
    assert f("un año contado desde su publicación", "2024-02-29")["eff"] == "2025-02-28"
    # Dirección 21-nov-2026: business days are computed (no Saturdays, Sundays or holidays: 8-dic-2026);
    # «30 días» alone are calendar days, unless the text invokes Ley 19.880 (art. 25: business days).
    assert f("30 días hábiles desde su publicación", "2026-10-28")["eff"] == "2026-12-10"
    assert f("30 días desde su publicación", "2026-10-28")["eff"] == "2026-11-27"
    assert f("30 días desde su publicación, conforme a la Ley N° 19.880", "2026-10-28")["eff"] == "2026-12-10"
    assert f("30 días hábiles desde su publicación", "2029-10-28") is None  # holidays of 2029 not listed: never guessed
    # Counted from the Diario Oficial: from the captured edition; pending while it is not captured.
    assert f("seis meses contados desde su publicación en el Diario Oficial", "2026-10-28") == {"kind": "on_publication_do", "eff": None, "prec": None}
    assert f("seis meses contados desde su publicación en el Diario Oficial", "2026-10-28", "2026-11-11")["eff"] == "2027-05-11"


def test_diario_oficial_date_comes_from_the_captured_edition_not_from_detection():
    rec = {"label": "Circular IF/N°539", "type": "Circular", "date": "2026-10-30"}
    rows = [{"source_name": "Diario Oficial", "event_date": "2026-11-11",
             "title": "Circular número IF/539, de 2026.- Aclara el inicio del cómputo del plazo"},
            {"source_name": "Diario Oficial", "event_date": "2026-11-12", "title": "Circular número IF/5390, de 2026.- Otra"},
            {"source_name": "Superintendencia de Salud", "event_date": "2026-10-30", "title": "Circular IF/N°539"}]
    assert ni.diario_oficial_date(rec, rows) == "2026-11-11"
    assert ni.diario_oficial_date({**rec, "label": "Circular IF/N°540"}, rows) is None


def test_deadlines_are_never_an_entry_into_force_and_diario_oficial_terms_wait_for_the_edition():
    f = ni.term_from_publication
    assert f("Las isapres tendrán un plazo de seis meses contados desde su publicación para adecuar sus sistemas", "2026-10-28") is None
    assert f("Deberán informar dentro de 30 días corridos desde su publicación", "2026-10-28") is None
    assert f("Regirá seis meses contados desde la publicación de la presente circular en el Diario Oficial", "2026-10-28")["kind"] == "on_publication_do"
    rec = {"label": "Circular IF/N°539", "type": "Circular", "date": "2026-10-30"}
    other_year = [{"source_name": "Diario Oficial", "event_date": "2026-11-11", "title": "Circular número IF/539, de 2025.- Otra"}]
    assert ni.diario_oficial_date(rec, other_year) is None


def test_validity_from_the_issuer_page_evidence_when_the_capture_missed_it(tmp_path):
    # Circular 3935 (Dirección 20-nov-2026): the SUSESO page says «Observación: Vigencia desde su publicación».
    (tmp_path / "a.json").write_text(json.dumps({"page_url": "https://www.suseso.gob.cl/612/w3-article-793852.html",
        "text": "TODAS LAS COMPIN Observación: Vigencia desde su publicación Acción: Instruye Fuentes: Ley N° 16.395"}), encoding="utf-8")
    url = "https://www.suseso.gob.cl/612/w3-article-793852.html"
    assert ni.evidence_validity(url, tmp_path) == "Vigencia desde su publicación"
    assert ni.parse_validity(ni.evidence_validity(url, tmp_path))["kind"] == "on_publication"
    assert ni.evidence_validity("https://otra.cl/x", tmp_path) is None and ni.evidence_validity(url, None) is None
    (tmp_path / "b.json").write_text(json.dumps({"page_url": "https://www.suseso.gob.cl/x.html",
        "text": "Observación: Vigencia desde 2 de mayo de 2027 Vigencia: No Alterado Acción: Imparte"}), encoding="utf-8")
    assert ni.evidence_validity("https://www.suseso.gob.cl/x.html", tmp_path) == "Vigencia desde 2 de mayo de 2027"  # review of #222


def test_chilean_business_days():
    from radar_salud import cl_calendar as cc
    from datetime import date
    assert cc.add_business_days(date(2027, 1, 1), 10) == date(2027, 1, 15)  # 1-ene holiday, weekends skipped
    assert cc.add_business_days(date(2026, 12, 4), 2) == date(2026, 12, 9)  # 8-dic-2026 Inmaculada Concepción
    assert cc.add_business_days(date(2027, 12, 20), 30) is None  # 2028 not listed
    assert cc.add_term(date(2026, 1, 31), 1, "mes") == date(2026, 2, 28)
    assert cc.add_term(date(2026, 1, 1), 24, "horas") is None


def test_compliance_deadlines_from_the_official_text():
    # Dirección 21-nov-2026: duties with a term, apart from the entry into force, each with its countdown.
    f = ni.compliance_terms
    t538 = ("Asimismo, deberán informar a las personas beneficiarias la cobertura y los topes aplicables a dichas prestaciones, "
            "mediante los canales registrados, dentro de los diez días hábiles siguientes a la vigencia de las presentes instrucciones.")
    [p] = f(t538)
    assert (p["accion"], p["n"], p["habiles"], p["anchor"]) == ("Informar a las personas beneficiarias la cobertura y los topes aplicables a dichas prestaciones", 10, True, "vigencia")
    [d] = ni.due_dates([p], "2027-01-01", "2026-10-26", None)
    assert d == {"accion": p["accion"], "plazo": "10 días hábiles", "desde": "desde la entrada en vigencia", "due": "2027-01-15", "caso": False, "pendiente": False}
    [c] = f("La Isapre deberá pronunciarse respecto de la solicitud dentro del plazo de cinco días hábiles contado desde su presentación y derivar.")
    assert c["anchor"] == "caso" and c["desde"] == "desde su presentación"
    assert ni.due_dates([c], "2027-01-01", "2026-10-26", None)[0]["due"] is None
    [o] = f("c) Comunicar directamente a los Operadores el número de contacto, dato requerido, dentro de 5 días hábiles contados desde la fecha del presente oficio.")
    assert o["anchor"] == "acto" and ni.due_dates([o], None, "2026-09-29", None)[0]["due"] == "2026-10-06"
    [x] = f("Las isapres deberán implementar el mecanismo de registro a más tardar el 1 de noviembre de 2026.")
    assert x == {"accion": "Implementar el mecanismo de registro", "due": "2026-11-01", "anchor": "fecha", "quote": x["quote"]}
    # A deadline anchored to an entry into force not yet known waits; recitals and objectives are not duties.
    assert ni.due_dates([p], None, "2026-10-26", None)[0]["pendiente"] is True
    assert f("OBJETIVO Aclarar el momento a partir del cual se computa el plazo de veinticuatro horas para informar.") == []
    assert f("solicita que se le conceda una extensión del plazo de seis meses, que deberá resolverse dentro de 10 días.") == []
    assert ni.unsplit("la cobertu ra y de la solicitud", {"cobertura", "dela"}) == "la cobertura y de la solicitud"


def test_no_date_means_in_force_from_its_date_and_only_undatable_terms_stay_in_review():
    reg = {"items": {k: {"id": k, "label": f"Resolución Exenta IF/N°{n}", "type": "Resolución Exenta", "emisor": "SIS",
                         "date": "2026-10-01", "subject": "Isapres", "url": f"https://x/{k}", "validity": v, "related": [], "signal_id": k}
                     for k, n, v in (("a", 1, None), ("b", 2, "Seis meses contados desde su notificación."))}}
    built = {x["id"]: x for x in ni.build(reg, {"decisions": {}}, set())["items"]}
    assert ni.effective_base(built["a"]) == "2026-10-01" and not built["a"].get("unclear")
    assert built["b"]["unclear"] is True and ni.effective_base(built["b"]) is None
