"""DIPRES daily refresh (dipres_refresh, Director 4-nov-2026): discovery, guards and F7 picking up a newer cut.

Everything is SYNTHETIC and offline: listing pages are small HTML strings shaped like the retained 11-oct-2026 DIPRES
appendix pages, "PDFs" are bytes starting with %PDF whose text is supplied by a fake extractor, amounts are test
values. No network: the fetcher is a dict lookup that records every URL asked.
"""
import copy
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from radar_salud import dipres_refresh as dr
from radar_salud import dipres_sources
from radar_salud import stats_ficha_f7 as f7
from radar_salud import stats_fichas as sf

from test_stats_ficha_f7 import lane as f7_lane, reg_open, write as write_lane

TODAY = date(2026, 11, 4)
NOW = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
YEAR_ID = dr.KNOWN_YEAR_IDS["2026"]
AUX = dr.BASE + "aux-multipropertyvalues-{ent}-" + YEAR_ID + ".html"
PDF = dr.BASE + "articles-{n}_doc_pdf.pdf"


def listing(*docs):
    """docs: (article number, label). Each also gets the XML/CSV/XLS siblings DIPRES lists (ignored)."""
    rows = []
    for n, label in docs:
        for ext, kind in (("xml.xml", "XML"), ("xls.xls", "Excel"), ("pdf.pdf", "PDF")):
            rows.append(f'<li><a href="/597/articles-{n}_doc_{ext}?ts=17880{n}">Documento {kind} : {label}</a></li>')
    return ("<html><body><ul>" + "".join(rows) + "</ul></body></html>").encode()


def execution_text(month: str, executed: str, vigente: str, *, code="16", year=2026):
    return (f"INFORME EJECUCION MENSUAL PERIODO {year}\nAcumulado a {month}\n{code} : MINISTERIO DE SALUD\n"
            f"Miles de $\nMontos Devengados\nINGRESOS 100 200 150\nGASTOS 16.800.000 {vigente} {executed}\n")


class Fetch:
    def __init__(self, pages: dict, fail: set = frozenset()):
        self.pages, self.fail, self.calls = pages, set(fail), []

    def __call__(self, url):
        self.calls.append(url)
        if url in self.fail or url.split("?")[0] in self.fail:
            raise TimeoutError("synthetic network failure")
        body = self.pages.get(url) or self.pages.get(url.split("?")[0])
        if body is None:
            raise FileNotFoundError(url)
        return body


def pdf(tag: str) -> bytes:
    return b"%PDF-1.4 synthetic " + tag.encode()


TEXTS: dict[bytes, str] = {}


def make_pdf(tag, text):
    data = pdf(tag)
    TEXTS[data] = text
    return data


@pytest.fixture
def root(tmp_path, monkeypatch):
    write_lane(tmp_path, f7_lane())  # partida Jan–Mar 2026, capítulo 02 Jan–Mar, programa 02.01 (comparative)
    monkeypatch.setattr(dipres_sources, "pdf_text", lambda data: TEXTS[data])  # collect_dipres' own extraction
    return tmp_path


def pages(partida_docs=(), extra=None):
    out = {AUX.format(ent=e): listing() for e in dr.ENTITY_PAGES}
    out[AUX.format(ent="14626")] = listing(*partida_docs)
    out.update(extra or {})
    return out


def run(root, fetch, **kw):
    kw.setdefault("registry", reg_open())
    return dr.refresh(root, today=kw.pop("today", TODAY), fetch=fetch, now=lambda: NOW,
                      extract=lambda d: TEXTS[d], **kw)


def lane_bytes(root):
    return (root / dr.LANE).read_bytes()


# ---------------------------------------------------------------------------------------------------------------------
# Discovery


def test_new_month_enters_the_lane_and_f7_builds_from_the_newer_cut(root):
    aug = make_pdf("aug", execution_text("Agosto", "9.000.000", "17.500.000"))
    fetch = Fetch(pages([(430001, "Informe Ejecución Partida Agosto [Pesos]")], {PDF.format(n=430001): aug}))
    before = f7.build_package(root, reg_open())
    assert before["period"] == "2026-03"
    out = run(root, fetch)
    assert out["status"] == "ok" and out["new"] == 1 and out["rejected"] == 0
    # Only the PDF is downloaded (XML/XLS siblings ignored); the canonical URL drops the listing's ?ts=.
    assert [u for u in fetch.calls if "articles-" in u] == [PDF.format(n=430001) + "?ts=17880430001"]
    lane = json.loads((root / dr.LANE).read_text())
    led = next(d for d in lane["document_ledger"] if d["source_url"] == PDF.format(n=430001))
    assert led["source_sha256"] == hashlib.sha256(aug).hexdigest() and led["fetched_at"] == NOW.isoformat()
    new = [r for r in lane["records"] if r["source_url"] == PDF.format(n=430001)]
    assert {r["period"] for r in new} == {"2026-08"} and all(r["published_at"] is None for r in new)  # no invented date
    # History is kept: the earlier documents and records are still there.
    assert len(lane["document_ledger"]) == len(f7_lane()["document_ledger"]) + 1
    state = json.loads((root / dr.STATE).read_text())
    doc = state["documents"][PDF.format(n=430001)]
    assert doc["status"] == "in_lane" and doc["sha256"] == led["source_sha256"] and doc["expected_period"] == "2026-08"
    assert state["runs"][0]["new"] == 1 and state["last_completed_on"] == TODAY.isoformat()
    # F7 picks up the new cut by itself, and its reconciliation still applies to it.
    p = f7.build_package(root, reg_open())
    assert p["reconciliation"]["ok"], p["reconciliation"]["failures"]
    assert p["period"] == "2026-08" and p["primary_source"]["url"] == PDF.format(n=430001)
    assert p["values"]["partida.2026-08.pct"]["value"] == pytest.approx(9_000_000 / 17_500_000 * 100)
    assert p["published_at"] == "2026-11-04" and p["date_basis"] == "first_detected"
    assert p["evidence_sha256"] != before.get("evidence_sha256")  # new evidence → a new release, under the normal policy


def test_reconciliation_still_holds_a_bad_new_cut(root):
    """A new report whose accumulated execution falls below an earlier cut enters the lane but F7 HOLDs."""
    bad = make_pdf("bad", execution_text("Agosto", "1.000.000", "17.500.000"))
    fetch = Fetch(pages([(430002, "Informe Ejecución Partida Agosto [Pesos]")], {PDF.format(n=430002): bad}))
    assert run(root, fetch)["new"] == 1
    p = f7.build_package(root, reg_open())
    assert not p["reconciliation"]["ok"] and "executed_decreases:partida:2026-03>2026-08" in p["reconciliation"]["failures"]


def test_known_document_is_never_downloaded_again(root):
    known = f7_lane()["document_ledger"][0]["source_url"]  # articles-1000, already in the lane
    n = int(known.split("articles-")[1].split("_")[0])
    fetch = Fetch(pages([(n, "Informe Ejecución Partida Enero [Pesos]")]))
    before = lane_bytes(root)
    out = run(root, fetch)
    assert out["status"] == "ok" and out["already_known"] == 1 and out["new"] == 0
    assert not [u for u in fetch.calls if "articles-" in u] and lane_bytes(root) == before


def test_duplicate_content_under_another_url_is_not_added(root):
    aug = make_pdf("aug-dup", execution_text("Agosto", "9.000.000", "17.500.000"))
    fetch = Fetch(pages([(430010, "Informe Ejecución Partida Agosto [Pesos]")], {PDF.format(n=430010): aug}))
    assert run(root, fetch)["new"] == 1
    before = lane_bytes(root)
    fetch2 = Fetch(pages([(430011, "Informe Ejecución Partida Agosto [Pesos]")], {PDF.format(n=430011): aug}))
    out = run(root, fetch2, force=True)
    assert out["duplicates"] == 1 and out["new"] == 0 and lane_bytes(root) == before
    assert json.loads((root / dr.STATE).read_text())["documents"][PDF.format(n=430011)]["status"] == "duplicate_content"


def test_document_of_another_period_is_rejected_never_relabelled(root):
    """Listed as September, but the PDF is the August report: rejected, recorded, not in the lane, not retried."""
    wrong = make_pdf("wrong", execution_text("Agosto", "9.000.000", "17.500.000"))
    fetch = Fetch(pages([(430020, "Informe Ejecución Partida Septiembre [Pesos]")], {PDF.format(n=430020): wrong}))
    before = lane_bytes(root)
    out = run(root, fetch)
    assert out["rejected"] == 1 and out["new"] == 0 and lane_bytes(root) == before
    doc = json.loads((root / dr.STATE).read_text())["documents"][PDF.format(n=430020)]
    assert doc["status"] == "rejected" and doc["reason"].startswith("period_mismatch:listed 2026-09, document 2026-08")
    assert doc["sha256"] == hashlib.sha256(wrong).hexdigest()
    fetch2 = Fetch(fetch.pages)
    run(root, fetch2, force=True)
    assert not [u for u in fetch2.calls if "articles-" in u]
    # A report of another fiscal year on this year's page is rejected the same way.
    old = make_pdf("old", execution_text("Agosto", "9.000.000", "17.500.000", year=2025))
    fetch3 = Fetch(pages([(430021, "Informe Ejecución Partida Agosto [Pesos]")], {PDF.format(n=430021): old}))
    run(root, fetch3, force=True)
    assert json.loads((root / dr.STATE).read_text())["documents"][PDF.format(n=430021)]["reason"].startswith("period_mismatch")
    # A level other than the one listed (a capítulo PDF listed as the partida) is rejected too.
    cap = make_pdf("cap", execution_text("Agosto", "9.000.000", "17.500.000", code="1602"))
    fetch4 = Fetch(pages([(430022, "Informe Ejecución Partida Agosto [Pesos]")], {PDF.format(n=430022): cap}))
    run(root, fetch4, force=True)
    assert json.loads((root / dr.STATE).read_text())["documents"][PDF.format(n=430022)]["reason"] == "level_mismatch"
    assert lane_bytes(root) == before


def test_quarter_labels_map_to_their_month_end():
    items = dr.listed_reports(listing((1, "Informe Ejecución Capítulo Tercer Trimestre [Pesos]"),
                                      (2, "Identificación y Ejecución de Inversión a Julio [Pesos]"),
                                      (3, "Informe Ejecución Programa Diciembre [Pesos]")).decode(), AUX.format(ent="14632"), "2026")
    assert [(i["level"], i["expected_period"]) for i in items] == [("capitulo", "2026-09"), ("programa", "2026-12")]


def test_fetch_failure_keeps_the_last_good_capture(root):
    fetch = Fetch(pages([(430030, "Informe Ejecución Partida Agosto [Pesos]")]), fail={PDF.format(n=430030)})
    before = lane_bytes(root)
    out = run(root, fetch)
    assert out["status"] == "partial" and out["fetch_failed"] == 1 and lane_bytes(root) == before
    state = json.loads((root / dr.STATE).read_text())
    assert state["documents"][PDF.format(n=430030)]["status"] == "fetch_failed" and "last_completed_on" not in state
    # Every listing page down: error, lane untouched, F7 still builds from the previous cut.
    down = Fetch({}, fail={AUX.format(ent=e) for e in dr.ENTITY_PAGES})
    out = run(root, down)
    assert out["status"] == "error" and lane_bytes(root) == before
    assert f7.build_package(root, reg_open())["period"] == "2026-03"
    # Retries stop after MAX_ATTEMPTS, then wait a week.
    for _ in range(dr.MAX_ATTEMPTS):
        run(root, fetch)
    calls = len(fetch.calls)
    run(root, fetch)
    assert not [u for u in fetch.calls[calls:] if "articles-" in u]


# ---------------------------------------------------------------------------------------------------------------------
# Guards


def test_once_per_day(root):
    fetch = Fetch(pages())
    assert run(root, fetch)["status"] == "ok"
    n = len(fetch.calls)
    assert run(root, fetch)["status"] == "skipped_already_checked_today" and len(fetch.calls) == n
    assert run(root, fetch, today=date(2026, 11, 5))["status"] == "ok" and len(fetch.calls) > n


def test_time_budget_stops_new_requests(root):
    aug = make_pdf("aug-budget", execution_text("Agosto", "9.000.000", "17.500.000"))
    ticks = iter(range(0, 10_000, 100))
    fetch = Fetch(pages([(430040, "Informe Ejecución Partida Agosto [Pesos]")], {PDF.format(n=430040): aug}))
    before = lane_bytes(root)
    out = dr.refresh(root, today=TODAY, registry=reg_open(), fetch=fetch, now=lambda: NOW, extract=lambda d: TEXTS[d],
                     time_budget_s=250, clock=lambda: next(ticks))
    assert out["time_budget_exhausted"] and out["status"] == "partial" and len(fetch.calls) < len(dr.ENTITY_PAGES)
    assert lane_bytes(root) == before


def test_waits_while_f7_first_review_is_pending(root):
    reg = copy.deepcopy(sf.load_registry())
    assert reg["families"]["F7"]["first_pass_requires_review"] is True
    fetch = Fetch(pages())
    assert run(root, fetch, registry=reg)["status"] == "skipped_f7_awaiting_first_review" and not fetch.calls
    # Once an F7 ficha is live in PASS, the refresh runs (new evidence then follows the normal policy).
    live = sf.paths(root, reg["families"]["F7"]["slug"])["live"]
    live.parent.mkdir(parents=True, exist_ok=True)
    live.write_text(json.dumps({"status": "PASS", "builder_version": f7.BUILDER_VERSION}))
    assert run(root, fetch, registry=reg)["status"] == "ok" and fetch.calls


def test_new_year_page_is_discovered_from_the_year_links(root):
    nav = dr.BASE + f"w3-multipropertyvalues-14626-{YEAR_ID}.html"
    links = ('<a href="/597/w3-multipropertyvalues-14626-39999.html">2027</a>'
             f'<a href="/597/w3-multipropertyvalues-14626-{YEAR_ID}.html">2026</a>')
    jan = make_pdf("jan27", execution_text("Enero", "2.000.000", "18.000.000", year=2027))
    p = {nav: links.encode(), PDF.format(n=440001): jan}
    for e in dr.ENTITY_PAGES:
        p[dr.BASE + f"aux-multipropertyvalues-{e}-{YEAR_ID}.html"] = listing()
        p[dr.BASE + f"aux-multipropertyvalues-{e}-39999.html"] = listing()
    p[dr.BASE + "aux-multipropertyvalues-14626-39999.html"] = listing((440001, "Informe Ejecución Partida Enero [Pesos]"))
    out = run(root, Fetch(p), today=date(2027, 2, 20))
    assert out["status"] == "ok" and out["new"] == 1
    assert json.loads((root / dr.STATE).read_text())["year_ids"]["2027"] == "39999"


def test_fetcher_refuses_other_hosts_and_robots_disallow():
    with pytest.raises(PermissionError):
        dr.DipresFetcher(opener=object())("https://example.org/597/articles-1_doc_pdf.pdf")
    with pytest.raises(PermissionError):
        dr.DipresFetcher(opener=object())("http://www.dipres.gob.cl/597/articles-1_doc_pdf.pdf")

    class Resp:
        def __init__(self, body):
            self.body, self.headers = [body, b""], {}

        def read(self, n):
            return self.body.pop(0)

        def geturl(self):
            return "https://www.dipres.gob.cl/robots.txt"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class Opener:
        def open(self, req, timeout):
            return Resp(b"User-agent: *\nDisallow: /597/\n")
    with pytest.raises(PermissionError, match="robots_disallowed"):
        dr.DipresFetcher(opener=Opener())(PDF.format(n=1))


# ---------------------------------------------------------------------------------------------------------------------
# Runner wiring and the F7 freshness copy


def test_runner_calls_the_refresh_and_a_failure_never_blocks_f7(root, monkeypatch, capsys):
    import importlib.util
    spec = importlib.util.spec_from_file_location("rsf_dipres", Path(__file__).resolve().parents[1] / "scripts/run_stats_fichas.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    assert runner.DIPRES_CAPTURED == {"F7"} and "F7" not in runner.CAPTURED | runner.FEFI_CAPTURED
    opened = reg_open()
    monkeypatch.setattr(runner.stats_fichas, "load_registry", lambda: opened)

    def boom(*a, **k):
        raise RuntimeError("dipres down")
    monkeypatch.setattr(runner.dipres_refresh, "refresh", boom)
    assert runner.main(["--root", str(root), "--as-of", TODAY.isoformat(), "--family", "F7", "--no-llm"]) == 0
    s = json.loads(capsys.readouterr().out)
    assert s["capture_dipres"]["status"] == "error" and s["F7"]["status"] == "pass"
    seen = []
    monkeypatch.setattr(runner.dipres_refresh, "refresh", lambda r, **k: seen.append(k) or {"status": "ok"})
    runner.main(["--root", str(root), "--as-of", TODAY.isoformat(), "--family", "F7", "--no-llm"])
    assert seen and 0 < seen[0]["time_budget_s"] <= dr.TIME_BUDGET_S
    runner.main(["--root", str(root), "--as-of", TODAY.isoformat(), "--family", "F7", "--no-capture"])
    assert len(seen) == 1  # --no-capture never checks DIPRES


def test_freshness_copy_says_daily_only_after_a_recent_automatic_check(root):
    fi = f7.run(root, today=TODAY, registry=reg_open(), llm=False)["ficha"]
    assert "captura manual, próxima actualización pendiente" in fi["kicker_meta"] and "manual" in fi["watch"][0]["explanation"]
    assert run(root, Fetch(pages()))["status"] == "ok"
    fi = f7.run(root, today=TODAY, registry=reg_open(), llm=False)["ficha"]
    assert fi["kicker_meta"].startswith("datos al 31 mar 2026 (corte; se revisa a diario; DIPRES publica mensualmente)")
    assert "manual" not in " ".join(sf.displayed_texts(fi)) + fi["kicker_meta"]
    assert "a diario" in fi["watch"][0]["explanation"] and fi["kicker"].endswith("corte 31 mar 2026")
    stale = f7.run(root, today=date(2026, 11, 20), registry=reg_open(), llm=False)
    fi = stale.get("ficha") or stale.get("candidate")
    assert "revisión diaria detenida" in fi["kicker_meta"]


# ---------------------------------------------------------------------------------------------------------------------
# Independent review of PR #142


def test_freshness_uses_the_chile_day_not_the_utc_stamp(root):
    """An OK check at 00:07Z is still 21:07 of the previous Chile day: the ficha must say 'a diario', not 'detenida'."""
    late = datetime(2026, 11, 5, 0, 7, tzinfo=timezone.utc)  # 4-nov 21:07 in Santiago
    out = dr.refresh(root, today=TODAY, registry=reg_open(), fetch=Fetch(pages()), now=lambda: late,
                     extract=lambda d: TEXTS[d])
    state = json.loads((root / dr.STATE).read_text())
    assert out["status"] == "ok" and state["last_ok_on"] == "2026-11-04" and state["last_ok_at"].startswith("2026-11-05")
    assert dr.freshness(root, TODAY) == {"mode": "daily", "last_ok_on": "2026-11-04"}
    fi = f7.run(root, today=TODAY, registry=reg_open(), llm=False)["ficha"]
    assert "se revisa a diario" in fi["kicker_meta"] and "detenida" not in fi["kicker_meta"]
    assert f7.build_package(root, reg_open())["lane"]["refresh_last_ok_on"] == "2026-11-04"


def test_a_validated_report_whose_collect_crashed_is_retried_once_a_day(root, monkeypatch):
    aug = make_pdf("aug-crash", execution_text("Agosto", "9.000.000", "17.500.000"))
    fetch = Fetch(pages([(430050, "Informe Ejecución Partida Agosto [Pesos]")], {PDF.format(n=430050): aug}))
    real = dr._collect

    def crash(*a, **k):
        raise RuntimeError("collector crashed")
    monkeypatch.setattr(dr, "_collect", crash)
    before = lane_bytes(root)
    assert run(root, fetch)["status"] == "partial" and lane_bytes(root) == before
    assert json.loads((root / dr.STATE).read_text())["documents"][PDF.format(n=430050)]["status"] == "collect_failed"
    monkeypatch.setattr(dr, "_collect", real)
    n = len(fetch.calls)
    run(root, fetch, force=True)  # same Chile day: not downloaded again
    assert not [u for u in fetch.calls[n:] if "articles-" in u]
    out = run(root, fetch, today=date(2026, 11, 5))  # next day: retried and it reaches the lane
    assert out["new"] == 1 and f7.build_package(root, reg_open())["period"] == "2026-08"
    # A document left 'accepted' (crash between validation and collect) is due again the same way.
    state = json.loads((root / dr.STATE).read_text())
    assert dr._due({"status": "accepted", "last_attempt_on": "2026-11-05"}, NOW, "2026-11-06")
    assert not dr._due({"status": "accepted", "last_attempt_on": "2026-11-06"}, NOW, "2026-11-06")
    assert state["documents"][PDF.format(n=430050)]["status"] == "in_lane"


def test_a_subpartida_report_is_never_taken_as_the_partida():
    text = execution_text("Agosto", "9.000.000", "17.500.000") + "SUBPARTIDA : 1603 SERVICIOS DE SALUD\n"
    item = {"canonical_url": PDF.format(n=1), "expected_period": "2026-08", "level": "partida"}
    assert dr.validate(text, item, sha256="0" * 64) == (None, "level_mismatch")
    records, reason = dr.validate(execution_text("Agosto", "9.000.000", "17.500.000"), item, sha256="0" * 64)
    assert reason is None and records


def test_no_pdf_is_parsed_after_the_deadline(root):
    a = make_pdf("dl-a", execution_text("Agosto", "9.000.000", "17.500.000"))
    b = make_pdf("dl-b", execution_text("Septiembre", "10.000.000", "17.500.000"))
    fetch = Fetch(pages([(430060, "Informe Ejecución Partida Agosto [Pesos]"), (430061, "Informe Ejecución Partida Septiembre [Pesos]")],
                        {PDF.format(n=430060): a, PDF.format(n=430061): b}))
    parsed = []
    t = {"now": 0.0}

    def clock():
        return t["now"]

    def fetch_slow(url):
        body = fetch(url)
        if "articles-" in url:
            t["now"] += 100  # each PDF download eats 100 s of a 150 s budget
        return body
    before = lane_bytes(root)
    out = dr.refresh(root, today=TODAY, registry=reg_open(), fetch=fetch_slow, now=lambda: NOW, clock=clock,
                     extract=lambda d: parsed.append(d) or TEXTS[d], time_budget_s=150)
    assert out["time_budget_exhausted"] and out["status"] == "partial"
    assert parsed == [b] and len([u for u in fetch.calls if "articles-" in u]) == 2  # second download: not parsed
    docs = json.loads((root / dr.STATE).read_text())["documents"]
    assert PDF.format(n=430060) not in docs  # left due for the next run, not marked failed
    assert lane_bytes(root) != before


def test_a_redirect_off_dipres_is_refused_before_the_other_host_is_requested():
    import io
    import urllib.request
    from email.message import Message
    from urllib.response import addinfourl

    class FakeHTTPS(urllib.request.BaseHandler):
        handler_order = 100  # ahead of the real HTTPSHandler: nothing leaves the process

        def __init__(self):
            self.opened = []

        def https_open(self, req):
            self.opened.append(req.full_url)
            headers = Message()
            if req.full_url.endswith("/robots.txt"):
                resp = addinfourl(io.BytesIO(b"User-agent: *\nAllow: /\n"), headers, req.full_url, 200)
                resp.msg = "OK"
                return resp
            headers["Location"] = "https://evil.example.org/articles-1_doc_pdf.pdf"
            resp = addinfourl(io.BytesIO(b""), headers, req.full_url, 302)
            resp.msg = "Found"
            return resp
    fake = FakeHTTPS()
    opener = urllib.request.build_opener(dr._redirect_handler(), fake)
    with pytest.raises(PermissionError, match="redirect_off_allowlist"):
        dr.DipresFetcher(opener=opener)(PDF.format(n=1))
    assert fake.opened == ["https://www.dipres.gob.cl/robots.txt", PDF.format(n=1)]
    assert not any("example.org" in u for u in fake.opened)
