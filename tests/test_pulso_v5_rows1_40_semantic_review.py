"""Read the real producer, then test the eight-copy review only in memory."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

from radar_salud.pulso_editorial_review import apply_review, validate_independent_binding

ROOT = Path(__file__).parents[1]
READER = "data/audits/pulso_v5_rows1_40_semantic_review_2026_10_11.json"
REVIEW = "data/audits/pulso_v5_rows1_40_editorial_corrections_2026_10_11.json"
spec = importlib.util.spec_from_file_location("reader8_qa", ROOT / "scripts/qa_pulso_recovery.py")
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)


@pytest.fixture
def reviewed(tmp_path):
    reader_raw, audit_raw = (ROOT / READER).read_bytes(), (ROOT / REVIEW).read_bytes()
    reader, audit = json.loads(reader_raw), json.loads(audit_raw)
    reader_sha, audit_sha = qa.digest(reader_raw), qa.digest(audit_raw)
    assert reader_sha == "9164682449e8982f9693ff70692e3a41dee13127c281bb74c1c1b570052811be"
    assert audit_sha == "c363e514752d850b0eefbd14873dd666f98a9f067146def30763f0fffbd09545"
    validate_independent_binding(audit, reader, independent_sha256=reader_sha)
    producer = reader["producer_commit"]
    originals = {}
    for key, reference in reader["inputs"].items():
        original = subprocess.check_output(["git", "show", producer + ":" + reference["path"]], cwd=ROOT)
        assert hashlib.sha256(original).hexdigest() == reference["file_sha256"]
        if key in {"history", "queue"}:
            originals[key] = json.loads(original)
    urls = {row["url"] for row in reader["all_signals"]}
    history = [row for row in originals["history"]["signals"] if row.get("source_url") in urls]
    queue = {key: item for key, item in originals["queue"].items()
             if item.get("source") == "pulso_latercera" and item["raw"].get("url") in urls}
    before = deepcopy(dict(history=history, queue=queue))
    history_after, queue_after, report = apply_review(history, queue, audit,
        audit_sha256=audit_sha, audit_path=REVIEW)
    assert before == dict(history=history, queue=queue)
    assert report["applied_count"] == 8
    (tmp_path / ".git").symlink_to(subprocess.check_output(
        ["git", "rev-parse", "--absolute-git-dir"], cwd=ROOT, text=True).strip(), target_is_directory=True)
    for path, raw in ((READER, reader_raw), (REVIEW, audit_raw)):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    registry = dict(schema_version="pulso_paid_editorial_review_registry_v1", source_id="pulso_latercera",
        reviews=[dict(review_file=REVIEW, review_sha256=audit_sha,
                      independent_review_file=READER, independent_review_sha256=reader_sha)])
    (tmp_path / qa.EDITORIAL_REGISTRY_PATH).write_text(json.dumps(registry))
    return dict(root=tmp_path, history=history_after, queue=queue_after,
                snapshot=dict(signals=deepcopy(history_after)))


def test_all_eight_actual_paid_copies_have_independently_consumable_original_binding(reviewed):
    proofs, findings = qa.verify_additional_editorial_reviews(**reviewed)
    assert len(proofs) == 8 and findings == []
    reader = json.loads((ROOT / READER).read_bytes())
    assert set(reader["inputs"]) == {"history", "queue", "runtime_report", "telemetry"}
    assert [row["cohort_index"] for row in reader["all_signals"]] == [6, 13, 21, 22, 23, 26, 36, 40]
    corrected = next(row for row in reader["all_signals"] if row["cohort_index"] == 23)
    assert corrected["proposed_what_happened"] == "Según La Tercera, " + corrected["original_published_what_happened"]
    assert corrected["proposed_why_it_matters"] == corrected["original_published_why_it_matters"]
    assert corrected["event_status"] == "proposed"
    assert reader["summary"]["raw_retention_pending"] == 2


@pytest.mark.parametrize("attack", ["body", "model", "date"])
def test_real_paid_copy_review_cannot_rebind_to_altered_primary_or_response(reviewed, attack):
    item = next(iter(reviewed["queue"].values()))
    if attack == "body":
        item["raw"]["metadata"]["page_text"] += " invented"
    elif attack == "model":
        item["raw"]["metadata"]["analysis_model_output"]["what_happened"] += " invented"
    else:
        item["raw"]["event_date"] = "2026-10-11"
    assert qa.verify_additional_editorial_reviews(**reviewed)[1]
