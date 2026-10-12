"""Second full-body read groups the repeated Kast item, preserving its survivor."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

from radar_salud.pulso_editorial_review import (
    apply_review, canonical_sha, validate_independent_binding,
)

ROOT = Path(__file__).parents[1]
READER = "data/audits/pulso_mixed25_first8_actual_semantic_review_v2_2026_10_11.json"
REVIEW = "data/audits/pulso_mixed25_first8_actual_editorial_review_v2_2026_10_11.json"
spec = importlib.util.spec_from_file_location("mixed_v2_group_qa", ROOT / "scripts/qa_pulso_recovery.py")
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)


@pytest.fixture
def grouped(tmp_path):
    reader_raw, audit_raw = (ROOT / READER).read_bytes(), (ROOT / REVIEW).read_bytes()
    reader, audit = json.loads(reader_raw), json.loads(audit_raw)
    rsha, asha = qa.digest(reader_raw), qa.digest(audit_raw)
    assert rsha == "4e7ac45e904fb776da639a8f4d27f2fecaefe4a7ca409b2b9b729c24b3af2849"
    assert asha == "10542bdbdd5d923fd5b08579952bcf4e4a58d05645d4d2a1f8cf63bf717e8bca"
    validate_independent_binding(audit, reader, independent_sha256=rsha)
    superseded = reader["supersedes_before_application"]
    for path_key, sha_key in (("prior_reader_path", "prior_reader_sha256"),
                              ("prior_review_path", "prior_review_sha256")):
        assert qa.digest((ROOT / superseded[path_key]).read_bytes()) == superseded[sha_key]
    peer = reader["second_peer"]
    assert qa.digest((ROOT / peer["path"]).read_bytes()) == peer["sha256"]
    originals = {}
    for key, ref in reader["inputs"].items():
        raw = subprocess.check_output(["git", "show", ref["commit"] + ":" + ref["path"]], cwd=ROOT)
        assert qa.digest(raw) == ref["file_sha256"]
        if key in {"history", "queue"}:
            originals[key] = json.loads(raw)
    record = next(row for row in reader["all_signals"] if row["decision"] == "group")
    target_url = record["duplicate_of"]
    target_queue = next(row for row in originals["queue"].values()
                        if row["raw"]["url"] == target_url)
    prior_path = target_queue["raw"]["metadata"]["editorial_review"]["review_file"]
    prior_audit = json.loads((ROOT / prior_path).read_bytes())
    prior_reader_path = prior_audit["independent_review"]["path"]
    urls = {row["url"] for row in audit["records"] + prior_audit["records"]}
    queue = {key: row for key, row in originals["queue"].items()
             if row.get("source") == "pulso_latercera" and row["raw"]["url"] in urls}
    history = [row for row in originals["history"]["signals"] if row.get("source_url") in urls]
    assert len(queue) == len(history) == 7  # four new records, all three prior records
    before = deepcopy(dict(queue=queue, history=history))
    after_h, after_q, report = apply_review(history, queue, audit, audit_sha256=asha, audit_path=REVIEW)
    assert before == dict(queue=queue, history=history)
    assert report["applied_count"] == 4
    assert report["decisions"] == {"accept": 3, "reject": 0, "group": 1, "correct": 0}
    (tmp_path / ".git").symlink_to(subprocess.check_output(
        ["git", "rev-parse", "--absolute-git-dir"], cwd=ROOT, text=True).strip(), target_is_directory=True)
    registry = dict(schema_version="pulso_paid_editorial_review_registry_v1", source_id="pulso_latercera", reviews=[])
    for apath, ipath in ((REVIEW, READER), (prior_path, prior_reader_path)):
        for path in (apath, ipath):
            dest = tmp_path / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((ROOT / path).read_bytes())
        registry["reviews"].append(dict(review_file=apath,
            review_sha256=qa.digest((ROOT / apath).read_bytes()), independent_review_file=ipath,
            independent_review_sha256=qa.digest((ROOT / ipath).read_bytes())))
    (tmp_path / qa.EDITORIAL_REGISTRY_PATH).write_text(json.dumps(registry))
    return dict(reader=reader, audit=audit, audit_sha=asha, original=before,
                history=after_h, queue=after_q, root=tmp_path, target_url=target_url)


def test_v2_group_has_full_consumer_completeness_and_keeps_prior_budget_publication_exact(grouped):
    reader, history, queue = grouped["reader"], grouped["history"], grouped["queue"]
    record = next(row for row in reader["all_signals"] if row["decision"] == "group")
    target_url = grouped["target_url"]
    target = next(row for row in history if row["source_url"] == target_url)
    target_item = next(row for row in queue.values() if row["raw"]["url"] == target_url)
    assert canonical_sha(target) == record["duplicate_target_signal_sha256"]
    assert canonical_sha(target_item) == record["duplicate_target_queue_sha256"]
    duplicate = next(row for row in history if row["source_url"] == record["url"])
    duplicate_item = queue[record["queue_fingerprint"]]
    assert duplicate["editorial_decision"] == "group" and duplicate["feed_visibility"] is False
    assert duplicate_item["status"] == "rejected"
    assert duplicate_item["attempts"] == grouped["original"]["queue"][record["queue_fingerprint"]]["attempts"]
    for field in ("page_text", "analysis_model_output", "publication_date", "html_sha256"):
        assert duplicate_item["raw"]["metadata"][field] == grouped["original"]["queue"][record["queue_fingerprint"]]["raw"]["metadata"][field]
    snapshot = dict(signals=[deepcopy(row) for row in history if row.get("feed_visibility") is not False])
    proofs, findings = qa.verify_additional_editorial_reviews(queue, history, snapshot, grouped["root"])
    assert len(proofs) == 7 and not findings
    assert target in snapshot["signals"] and duplicate not in snapshot["signals"]
    assert next(row for row in reader["all_assigned_rows"] if row["sorted_assess25_index"] == 8)["current_independent_decision"] == "group"
    replay_h, replay_q, report = apply_review(history, queue, grouped["audit"],
        audit_sha256=grouped["audit_sha"], audit_path=REVIEW)
    assert replay_h == history and replay_q == queue and report["applied_count"] == 0


@pytest.mark.parametrize("attack", ["missing_history", "missing_queue", "withdrawn", "unpublished"])
def test_group_cannot_remove_candidate_without_an_existing_published_survivor(grouped, attack):
    history, queue = deepcopy(grouped["original"]["history"]), deepcopy(grouped["original"]["queue"])
    target_url = grouped["target_url"]
    target_key = next(key for key, row in queue.items() if row["raw"]["url"] == target_url)
    if attack == "missing_history":
        history = [row for row in history if row["source_url"] != target_url]
    elif attack == "missing_queue":
        del queue[target_key]
    elif attack == "withdrawn":
        next(row for row in history if row["source_url"] == target_url)["feed_visibility"] = False
    else:
        queue[target_key]["status"] = "retry"
    with pytest.raises(ValueError, match="group_surviving_signal"):
        apply_review(history, queue, grouped["audit"], audit_sha256=grouped["audit_sha"], audit_path=REVIEW)
