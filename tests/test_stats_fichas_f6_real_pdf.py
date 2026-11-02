"""CI-only: the approved F6 acreditación templates on the real Boletín IP PDFs (N°2-2026 and N°3-2026).

Downloads the documents through the production ``SisFetcher`` (allowlist, robots.txt, byte cap, deadline) and skips
when the network or the SIS is unavailable (e.g. sandboxes without egress). When it runs (GitHub Actions) it emits, as
GitHub check-run annotations written to the real stdout (pytest's capture suspended with ``capsys.disabled()``), at most
9 ``::notice`` lines in total (qa.yml job 'tests'):
- the normalized text of the N°3 acreditación pages equivalent to p.8 and p.2 of N°2 (the pages where each template
  matches, else its ``pages_hint``), ~3,000-character chunks (``F6 N°3 p<N> (k/n)``);
- ``F6 N°3 templates``: sha256 vs. the scout's recorded hash, per template the pre-check over the whole document
  (status, page vs. ``pages_hint``, captured figures), the parse, and the F6 state of the N°3 release;
- ``F6 N°2 templates``: the N°2 match summary only (its page text was reviewed on 30-oct and is not repeated).

N°2 (approved 30-oct) must still verify: bytes hash to the recorded SHA-256; the v1 window misses 101 and 584; each
template matches exactly once on the cited pages; the parse (checker v3: template only) is 'verified'; and the F6 package
from the committed store with this parse passes reconciliation. N°3 asserts rules, not figures: without an independent
reading it is never verified and F6 keeps the last verified release.
"""
import os
import sys
import time
from pathlib import Path

import pytest

from radar_salud import stats_capture as cap

ACR = "https://www.superdesalud.gob.cl/app/uploads/2026/08/boletin-n2-2026-acreditacion-enero-junio-2026-2.pdf"
SHA = "8b7f7c7a385e4c0997033137adfe604d08ea148a3f01282553d07722b4569a2b"
N3_PERIOD = "2026-09"

CHUNK_CHARS = 3000
MAX_ANNOTATIONS = 9  # GitHub shows at most 10 notice annotations per step


def escape_data(text: str) -> str:
    """GitHub workflow-command message escaping: '%' → %25, '\\r' → %0D, '\\n' → %0A."""
    return str(text).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def annotation_lines(pages: list[tuple[str, str]], summaries: list[tuple[str, str]]) -> list[str]:
    """``::notice`` lines: each (title, text) page in ~CHUNK_CHARS chunks, then the summaries; at most MAX_ANNOTATIONS in
    total. ``pages`` is in priority order: every page first gets one chunk, then the extra chunks go to the pages in that
    order; a page with no room is dropped, and the last kept chunk of a cut page says so."""
    budget = MAX_ANNOTATIONS - len(summaries)
    chunks = [[t[i:i + CHUNK_CHARS] for i in range(0, len(t), CHUNK_CHARS)] or [""] for _, t in pages]
    take = [0] * len(pages)
    for i in range(len(pages)):
        if budget > 0:
            take[i], budget = 1, budget - 1
    for i in range(len(pages)):
        extra = min(budget, len(chunks[i]) - take[i]) if take[i] else 0
        take[i], budget = take[i] + extra, budget - extra
    out = []
    for (title, _), cs, n in zip(pages, chunks, take):
        for k, chunk in enumerate(cs[:n], 1):
            tail = " [truncated: annotation budget]" if n < len(cs) and k == n else ""
            out.append(f"::notice title={title} ({k}/{n})::{escape_data(chunk + tail)}")
    out += [f"::notice title={title}::{escape_data(text)}" for title, text in summaries]
    return out


def emit(lines: list[str], capsys) -> None:
    """Write to the runner's stdout, one command per line, and flush. pytest's default capture is at the file-descriptor
    level, which also swallows ``sys.__stdout__``; ``capsys.disabled()`` suspends it."""
    with capsys.disabled():
        sys.stdout.write("\n" + "\n".join(lines) + "\n")
        sys.stdout.flush()


def test_annotation_lines_are_escaped_chunked_prioritised_and_capped():
    s = [("F6 N°3 templates", "a"), ("F6 N°2 templates", "b")]
    lines = annotation_lines([("F6 N°3 p8", "a%b\nc\r"), ("F6 N°3 p2", "x" * 7000)], s)
    assert lines[0] == "::notice title=F6 N°3 p8 (1/1)::a%25b%0Ac%0D"
    assert [ln.split("::")[1] for ln in lines] == ["notice title=F6 N°3 p8 (1/1)", "notice title=F6 N°3 p2 (1/3)",
                                                   "notice title=F6 N°3 p2 (2/3)", "notice title=F6 N°3 p2 (3/3)",
                                                   "notice title=F6 N°3 templates", "notice title=F6 N°2 templates"]
    big = annotation_lines([("A", "a" * 30000), ("B", "b" * 30000)], s)
    assert len(big) == MAX_ANNOTATIONS and big[-2:] == ["::notice title=F6 N°3 templates::a", "::notice title=F6 N°2 templates::b"]
    assert [sum(f"title={p} " in ln for ln in big) for p in ("A", "B")] == [6, 1]  # B keeps one chunk, A the rest
    assert big[5].endswith("[truncated: annotation budget]") and big[6].endswith("[truncated: annotation budget]")
    assert all("\n" not in ln and len(ln) < CHUNK_CHARS + 200 for ln in big)
    many = annotation_lines([(f"P{i}", "x") for i in range(10)], s)
    assert len(many) == MAX_ANNOTATIONS and "title=P7 " not in " ".join(many)  # pages past the budget are dropped


def fetch(url: str) -> bytes:
    return cap.SisFetcher(deadline=time.monotonic() + 60, timeout=20)(url)


@pytest.fixture
def real_pdf(capsys) -> bytes:
    try:
        return fetch(ACR)
    except Exception as exc:  # no egress, proxy refusal, robots/SIS down: nothing to test here
        reason = f"real PDF not reachable: {type(exc).__name__}: {exc}"[:200]
        if os.environ.get("GITHUB_ACTIONS") == "true":  # make the skip visible on the PR's checks too
            emit([f"::notice title=F6 real PDF skipped::{escape_data(reason)}"], capsys)
        pytest.skip(reason)


def n3_release(root: Path) -> dict | None:
    return next((r for r in cap.boletin_releases(root)[0] if r["period"] == N3_PERIOD), None)


def n3_summary(root: Path, templates: dict) -> tuple[list[tuple[str, str]], str, dict | None]:
    """(pages to annotate, summary, the N°3 acreditación record for the F6 check). Never fails on N°3's content."""
    import hashlib
    import json
    rel = n3_release(root)
    if not rel:
        return [], "no N°3 release in the history", None
    url = next(d["url"] for d in rel["documents"] if d["topic"] == "acreditacion")
    try:
        data = fetch(url)
    except Exception as exc:
        return [], f"N°3 acreditación not reachable: {type(exc).__name__}: {exc}"[:300], None
    sha = hashlib.sha256(data).hexdigest()
    hist = json.loads((root / cap.HISTORY).read_text(encoding="utf-8"))["signals"]
    recorded = next((s.get("document_sha256") for s in hist if s.get("source_url") == url), None)
    pages = cap.pdf_pages(data)
    pre = cap.template_precheck(pages, templates)
    parts, show = [f"{url.rsplit('/', 1)[-1]} sha256 {sha[:12]}… ({'= scout' if sha == recorded else f'scout {str(recorded)[:12]}…'})"
                   f" · {len(pages)} pp."], []
    for key in sorted(templates):
        r = pre[key]
        parts.append(f"{key}: {r['status']}" + (f" p.{r['page']} (hint p.{r['pages_hint']}) figures {r['figures']}" if r.get("page")
                                               else f" on p.{r.get('pages', [])} (hint p.{r['pages_hint']})"))
    # The p.8 equivalent (the 'en tramitación' table) first, then the p.2 equivalent; hinted pages when nothing matched.
    show = []
    for key in ("pending_applications", "with_observations"):
        r = pre.get(key) or {}
        show += [p for p in (r.get("pages") or r.get("pages_hint") or []) if 1 <= p <= len(pages) and p not in show]
    verified = cap.verified_metrics(root).get(url) or {}
    res = cap.parse_boletin_pdf(data, verified.get("metrics"), verified.get("pages_1based"), "acreditacion", templates)
    parts.append(f"parse (checker v{res['checker_version']}): {res['status']}"
                 + (f" {res.get('template_status')}" if res.get("template_status") else ""))
    page_items = [(f"F6 N°3 p{p}", cap.normalize_page(pages[p - 1])) for p in show]
    doc = {"url": url, "topic": "acreditacion", "sha256": sha, "bytes": len(data), "format": "pdf", "status": "captured",
           "parse": res}
    return page_items, " | ".join(parts), doc


def test_real_acreditacion_pdfs_templates(real_pdf, capsys, tmp_path, monkeypatch):
    import hashlib
    import json
    import shutil
    from radar_salud import stats_ficha_f6 as f6, stats_fichas as sf
    sha = hashlib.sha256(real_pdf).hexdigest()
    if sha != SHA:
        emit([f"::notice title=F6 real PDF changed::sha256 {sha} != recorded {SHA}"], capsys)
        pytest.skip(f"SIS document changed ({sha[:12]}…): the capture HOLDs it as hash_mismatch")
    root = Path(__file__).resolve().parents[1]
    info = cap.verified_metrics(root)[ACR]
    pages = cap.pdf_pages(real_pdf)
    templates = cap.figure_templates(root, "acreditacion")
    found, summary = {}, []
    for k, tpl in templates.items():
        ev, why = cap.template_evidence(pages, info["pages_1based"], info["metrics"][k], tpl, info["metrics"])
        found[k] = (ev, why)
        summary.append(f"{k}: {why}" + (f" p.{ev['page']} match='{ev['match'][:200]}'" if ev else "")
                       + f" (review: {tpl.get('reviewed_by')!r} {tpl.get('reviewed_at')!r})")
    res = cap.parse_boletin_pdf(real_pdf, info["metrics"], info["pages_1based"], "acreditacion", templates)
    summary.append(f"parse (checker v{res['checker_version']}): {res['status']}")

    n3_pages, n3_text, n3_doc = n3_summary(root, templates)
    # F6 with the committed store, the N°2 parse above and the N°3 release (its acreditación as just parsed).
    monkeypatch.setenv("RADAR_ROOT", str(tmp_path / "ledger-root"))
    for rel in (cap.VERIFIED, f6.CAPTURE, cap.HISTORY):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(root / rel, tmp_path / rel)
    store = json.loads((tmp_path / f6.CAPTURE).read_text(encoding="utf-8"))
    acr = next(d for r in store["releases"] for d in r["documents"] if d["url"] == ACR)
    assert acr["sha256"] == sha
    acr.update(status="captured", parse=res)
    n3 = n3_release(root)
    if n3 and not any(r["period"] == N3_PERIOD for r in store["releases"]):
        store["releases"].append({**n3, "documents": [n3_doc if n3_doc and d["topic"] == "acreditacion" else {**d, "status": "not_fetched"}
                                                      for d in n3["documents"]]})
    (tmp_path / f6.CAPTURE).write_text(json.dumps(store, ensure_ascii=False), encoding="utf-8")
    pkg = f6.build_package(tmp_path, sf.load_registry())
    n3_state = pkg["releases_state"].get(N3_PERIOD)
    emit(annotation_lines(n3_pages, [("F6 N°3 templates", f"{n3_text} | F6: ficha {pkg['period']}, N°3 {n3_state}"),
                                     ("F6 N°2 templates", f"sha256 {sha[:12]}… · " + " | ".join(summary))]), capsys)

    old = cap.parse_boletin_pdf(real_pdf, info["metrics"], info["pages_1based"])  # checker v1: the production HOLD
    assert old["verified_present"]["with_observations"] is False and old["verified_present"]["pending_applications"] is False
    # Both templates are reviewed and match exactly once on the cited pages of the real N°2 PDF.
    for k, page in (("with_observations", 2), ("pending_applications", 8)):
        assert cap.template_pattern(templates[k])[1] == "ok", templates[k]
        ev, why = found[k]
        assert why == "ok" and ev["page"] == page, (k, why)
    assert found["with_observations"][0]["match"] == \
        "101 prestadores institucionales obtuvieron el resultado de acreditado con observaciones"
    assert found["pending_applications"][0]["sum_check"] == "367 + 217 = 584"
    assert found["pending_applications"][0]["parts_equal"] == {"private_pending": 367, "public_pending": 217}
    assert res["status"] == "verified" and all(res["verified_present"].values()), res.get("template_status")
    assert res["figure_rules"]["with_observations"]["rule"] == "template"
    assert res["figure_rules"]["pending_applications"]["rule"] == "template"
    assert pkg["reconciliation"]["ok"] is True and pkg["reconciliation"]["failures"] == [], pkg["reconciliation"]
    assert pkg["releases_state"]["2026-06"] == ["ok"], pkg["releases_state"]
    # N°3: never verified without its independent reading; F6 keeps the last verified release meanwhile.
    if n3 and n3_doc and n3_doc["url"] not in cap.verified_metrics(root):
        assert pkg["period"] == "2026-06" and any(w.startswith("not_verified:") for w in n3_state), n3_state
        assert n3_doc["parse"]["status"] == "no_verified_metrics" and set(n3_doc["parse"]["template_precheck"]) == set(templates)
