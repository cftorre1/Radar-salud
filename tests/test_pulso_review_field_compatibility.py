"""Pulso's review schema must coexist with unrelated staged review prose."""
from copy import deepcopy
import json
from pathlib import Path

from radar_salud.editorial_gate import publication_ready

ROOT = Path(__file__).parents[1]


def test_real_staging_fiscalization_review_prose_keeps_its_existing_gate():
    rows = json.loads((ROOT / "data/history/superintendencia_signals.json").read_bytes())["signals"]
    originals = [row for row in rows if isinstance(row.get("editorial_review"), str)]
    assert originals
    for original in originals:
        before = deepcopy(original)
        before.pop("editorial_review")
        assert publication_ready(deepcopy(original)) == publication_ready(before)


def test_real_pulso_reviewed_withdrawals_still_fail_publication_gate():
    rows = json.loads((ROOT / "data/history/superintendencia_signals.json").read_bytes())["signals"]
    withdrawn = [row for row in rows if isinstance(row.get("editorial_review"), dict)
                 and row["editorial_review"].get("schema_version") == "pulso_editorial_review_v1"
                 and row["editorial_review"].get("review_file") == "data/audits/pulso_first_paid_editorial_corrections_2026_10_11.json"
                 and row["editorial_review"].get("decision") in {"reject", "group"}]
    assert len(withdrawn) == 20
    for row in withdrawn:
        allowed, reason, _ = publication_ready(deepcopy(row))
        assert allowed is False
        assert reason == "pulso_independent_editorial_" + row["editorial_review"]["decision"]
