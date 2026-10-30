"""CI-only: the F6 checker v2 (anchored, human-reviewed templates) on the real Boletín IP N°2-2026 acreditación PDF.

Downloads the document through the production ``SisFetcher`` (allowlist, robots.txt, byte cap, deadline) and skips
when the network or the SIS is unavailable (e.g. sandboxes without egress). When it runs (GitHub Actions / daily run)
it PRINTS the extracted and the normalized text of pp. 2, 7 and 8, so a human can copy the exact p.8 table caption
into ``config/stats_fichas_v1.json`` (families.F6.figure_templates.acreditacion.pending_applications.caption) and
review both templates. It also prints whether each template, as written, would match exactly once ('GROUNDING').

While the templates are placeholder / unreviewed, the expected result is HOLD (intentional). Once reviewed, the test
requires 101 and 584 to be verified by their templates on pp. 2 and 8 (367 + 217 = 584).
"""
import time
from pathlib import Path

import pytest

from radar_salud import stats_capture as cap

ACR = "https://www.superdesalud.gob.cl/app/uploads/2026/08/boletin-n2-2026-acreditacion-enero-junio-2026-2.pdf"
SHA = "8b7f7c7a385e4c0997033137adfe604d08ea148a3f01282553d07722b4569a2b"


@pytest.fixture(scope="module")
def real_pdf() -> bytes:
    try:
        return cap.SisFetcher(deadline=time.monotonic() + 60, timeout=20)(ACR)
    except Exception as exc:  # no egress, proxy refusal, robots/SIS down: nothing to test here
        pytest.skip(f"real PDF not reachable: {type(exc).__name__}: {exc}"[:200])


def test_real_acreditacion_pdf_checker_v2(real_pdf, capsys):
    import hashlib
    sha = hashlib.sha256(real_pdf).hexdigest()
    if sha != SHA:
        pytest.skip(f"SIS document changed ({sha[:12]}…): the capture HOLDs it as hash_mismatch")
    root = Path(__file__).resolve().parents[1]
    info = cap.verified_metrics(root)[ACR]
    pages = cap.pdf_pages(real_pdf)
    templates = cap.figure_templates(root, "acreditacion")
    stamped = {k: {**v, "reviewed_by": "grounding-check", "reviewed_at": "-"} for k, v in templates.items()}
    with capsys.disabled():
        for p in (2, 7, 8):
            print(f"\n===== F6 acreditación p.{p} · extracted text =====\n{pages[p - 1]}")
            print(f"===== F6 acreditación p.{p} · normalized text =====\n{cap.normalize_page(pages[p - 1])}")
        for k, tpl in stamped.items():
            ev, why = cap.template_evidence(pages, info["pages_1based"], info["metrics"][k], tpl, info["metrics"])
            print(f"GROUNDING {k}: {why} {ev or ''}")
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
