"""CI-only: the F6 checker v2 (anchored, human-reviewed templates) on the real Boletín IP N°2-2026 acreditación PDF.

Downloads the document through the production ``SisFetcher`` (allowlist, robots.txt, byte cap, deadline) and skips
when the network or the SIS is unavailable (e.g. sandboxes without egress). When it runs (GitHub Actions / daily run)
it emits the normalized text of pp. 2, 7 and 8 as GitHub check-run annotations (``::notice title=F6 p<N> (k/n)::``,
~3,000-character chunks, at most 9 annotations with the final ``::notice title=F6 templates::`` summary of whether
each template, as written, would match exactly once). They are written to the real stdout (pytest's capture
suspended with ``capsys.disabled()``), so they appear on the PR's checks (qa.yml job 'tests'). A human copies the exact p.8 table
caption into ``config/stats_fichas_v1.json`` (families.F6.figure_templates.acreditacion.pending_applications.caption)
and reviews both templates.

While the templates are placeholder / unreviewed, the expected result is HOLD (intentional). Once reviewed, the test
requires 101 and 584 to be verified by their templates on pp. 2 and 8 (367 + 217 = 584).
"""
import os
import sys
import time
from pathlib import Path

import pytest

from radar_salud import stats_capture as cap

ACR = "https://www.superdesalud.gob.cl/app/uploads/2026/08/boletin-n2-2026-acreditacion-enero-junio-2026-2.pdf"
SHA = "8b7f7c7a385e4c0997033137adfe604d08ea148a3f01282553d07722b4569a2b"


CHUNK_CHARS = 3000
MAX_ANNOTATIONS = 9  # GitHub shows at most 10 notice annotations per step
PAGES = (2, 7, 8)
TRIM_ORDER = (7, 2, 8)  # when over budget, drop chunks of p.7 first, then p.2; p.8 (the caption) is kept longest


def escape_data(text: str) -> str:
    """GitHub workflow-command message escaping: '%' → %25, '\\r' → %0D, '\\n' → %0A."""
    return str(text).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def annotation_lines(normalized: dict[int, str], summary: str) -> list[str]:
    """``::notice`` lines: each page's normalized text in ~CHUNK_CHARS chunks, then the templates summary; at most
    MAX_ANNOTATIONS in total (pages trimmed in TRIM_ORDER, the last kept chunk of a trimmed page says so)."""
    chunks = {p: [normalized[p][i:i + CHUNK_CHARS] for i in range(0, len(normalized[p]), CHUNK_CHARS)] or [""]
              for p in normalized}
    trimmed = set()
    while sum(len(c) for c in chunks.values()) > MAX_ANNOTATIONS - 1:
        p = next((p for p in TRIM_ORDER if len(chunks.get(p, [])) > 1), None) or next(p for p in TRIM_ORDER if chunks.get(p))
        chunks[p].pop()
        trimmed.add(p)
    out = []
    for p in sorted(chunks):
        n = len(chunks[p])
        for k, chunk in enumerate(chunks[p], 1):
            tail = " [truncated: annotation budget]" if p in trimmed and k == n else ""
            out.append(f"::notice title=F6 p{p} ({k}/{n})::{escape_data(chunk + tail)}")
    out.append(f"::notice title=F6 templates::{escape_data(summary)}")
    return out


def emit(lines: list[str], capsys) -> None:
    """Write to the runner's stdout, one command per line, and flush. pytest's default capture is at the file-descriptor
    level, which also swallows ``sys.__stdout__``; ``capsys.disabled()`` suspends it."""
    with capsys.disabled():
        sys.stdout.write("\n" + "\n".join(lines) + "\n")
        sys.stdout.flush()


def test_annotation_lines_are_escaped_chunked_and_capped():
    lines = annotation_lines({2: "a%b\nc\r", 7: "x" * 7000, 8: "y" * 3001}, "with_observations: ok")
    assert lines[0] == "::notice title=F6 p2 (1/1)::a%25b%0Ac%0D"
    assert [ln.split("::")[1] for ln in lines] == ["notice title=F6 p2 (1/1)", "notice title=F6 p7 (1/3)",
                                                   "notice title=F6 p7 (2/3)", "notice title=F6 p7 (3/3)",
                                                   "notice title=F6 p8 (1/2)", "notice title=F6 p8 (2/2)",
                                                   "notice title=F6 templates"]
    big = annotation_lines({2: "a" * 9000, 7: "b" * 9000, 8: "c" * 9000}, "s")
    assert len(big) == MAX_ANNOTATIONS and big[-1] == "::notice title=F6 templates::s"
    assert [sum(f"title=F6 p{p} " in ln for ln in big) for p in (2, 7, 8)] == [3, 2, 3]  # p.7 trimmed first
    assert all("\n" not in ln and len(ln) < CHUNK_CHARS + 200 for ln in big)
    assert big[4].startswith("::notice title=F6 p7 (2/2)::") and big[4].endswith("[truncated: annotation budget]")
    huge = annotation_lines({2: "a" * 30000, 7: "b" * 30000, 8: "c" * 30000}, "s")
    assert len(huge) == MAX_ANNOTATIONS and [sum(f"title=F6 p{p} " in ln for ln in huge) for p in (2, 7, 8)] == [1, 1, 6]


@pytest.fixture
def real_pdf(capsys) -> bytes:
    try:
        return cap.SisFetcher(deadline=time.monotonic() + 60, timeout=20)(ACR)
    except Exception as exc:  # no egress, proxy refusal, robots/SIS down: nothing to test here
        reason = f"real PDF not reachable: {type(exc).__name__}: {exc}"[:200]
        if os.environ.get("GITHUB_ACTIONS") == "true":  # make the skip visible on the PR's checks too
            emit([f"::notice title=F6 real PDF skipped::{escape_data(reason)}"], capsys)
        pytest.skip(reason)


def test_real_acreditacion_pdf_checker_v2(real_pdf, capsys):
    import hashlib
    sha = hashlib.sha256(real_pdf).hexdigest()
    if sha != SHA:
        emit([f"::notice title=F6 real PDF changed::sha256 {sha} != recorded {SHA}"], capsys)
        pytest.skip(f"SIS document changed ({sha[:12]}…): the capture HOLDs it as hash_mismatch")
    root = Path(__file__).resolve().parents[1]
    info = cap.verified_metrics(root)[ACR]
    pages = cap.pdf_pages(real_pdf)
    templates = cap.figure_templates(root, "acreditacion")
    stamped = {k: {**v, "reviewed_by": "grounding-check", "reviewed_at": "-"} for k, v in templates.items()}
    summary = []
    for k, tpl in stamped.items():
        ev, why = cap.template_evidence(pages, info["pages_1based"], info["metrics"][k], tpl, info["metrics"])
        summary.append(f"{k}: {why}" + (f" p.{ev['page']} match='{ev['match'][:200]}'" if ev else "")
                       + f" (review: {templates[k].get('reviewed_by')!r})")
    emit(annotation_lines({p: cap.normalize_page(pages[p - 1]) for p in PAGES},
                          f"sha256 {sha[:12]}… · " + " | ".join(summary)), capsys)
    old = cap.parse_boletin_pdf(real_pdf, info["metrics"], info["pages_1based"])  # checker v1: today's HOLD
    assert old["verified_present"]["with_observations"] is False and old["verified_present"]["pending_applications"] is False
    res = cap.parse_boletin_pdf(real_pdf, info["metrics"], info["pages_1based"], "acreditacion", templates)
    reviewed = {k: cap.template_pattern(v)[1] == "ok" for k, v in templates.items()}
    for k in ("with_observations", "pending_applications"):
        if not reviewed.get(k):  # intentional HOLD until a human fills and reviews the template
            assert res["verified_present"][k] is False
            assert res["template_status"][k] in {"placeholder", "unreviewed", "not_configured"}, res["template_status"]
        else:
            ev = res["figure_rules"][k]
            assert ev and ev["rule"] == "template", res.get("template_status")
            assert ev["page"] == {"with_observations": 2, "pending_applications": 8}[k], ev
    if all(reviewed.get(k) for k in ("with_observations", "pending_applications")):
        assert res["status"] == "verified" and res["figure_rules"]["pending_applications"]["sum_check"] == "367 + 217 = 584"
