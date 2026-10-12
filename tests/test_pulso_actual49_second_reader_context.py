"""Second-reader route decisions refer to unchanged, genuinely paid originals."""
import hashlib
import json
from pathlib import Path
import subprocess

from radar_salud.pulso_editorial_review import canonical_sha

ROOT = Path(__file__).parents[1]
PATH = ROOT / "data/audits/pulso_actual49_second_reader_reuse_context_2026_10_11.json"


def test_all49_second_reader_references_match_immutable_originals_without_approving_repeat_fallout():
    reader = json.loads(PATH.read_bytes())
    assert hashlib.sha256(PATH.read_bytes()).hexdigest() == "bc37cc01288c6a118c329fd9033b9da9d556a0ed56c1a7df500820cd8438a9c7"
    original_queue = json.loads(subprocess.check_output([
        "git", "show", reader["producer_commit"] + ":data/state/pending_queue.json"], cwd=ROOT))
    original_history = json.loads(subprocess.check_output([
        "git", "show", reader["producer_commit"] + ":data/history/superintendencia_signals.json"], cwd=ROOT))["signals"]
    by_identity = {(entry["raw"]["url"], entry["raw"]["event_date"]): entry
                   for entry in original_queue.values() if entry.get("source") == "pulso_latercera"}
    assert len(reader["rows"]) == 49 and reader["summary"]["bounded_reuse_semantically_eligible"] == 18
    assert reader["publication_approved"] is False and reader["summary"]["AI_calls"] == 0
    for row in reader["rows"]:
        metadata = by_identity[(row["url"], row["publication_date"])]["raw"]["metadata"]
        assert row["original_body_sha256"] == hashlib.sha256(metadata["page_text"].encode()).hexdigest()
        assert row["original_model_output_sha256"] == canonical_sha(metadata["analysis_model_output"])
        assert row["original_model_response"] == metadata["analysis_model_output"]["_pulso_analysis_meta"]
        assert row["actual_score"] == metadata["analysis_model_output"]["relevance_score"]
        assert row["publication_approved"] is False
        if row.get("approved_route") == "reuse_code_fn":
            assert row["independently_read_complete_body_and_model"] is True and row["actual_score"] >= 72
    duplicate = next(row for row in reader["rows"] if row["cohort_index"] == 16)
    assert duplicate["approved_route"] == "assess_contract_or_semantic_defect"
    assert duplicate["semantically_eligible_for_bounded_reuse"] is False
    context = duplicate["existing_publication_context"]
    target = next(signal for signal in original_history if signal.get("source_url") == context["url"]
                  and signal.get("event_date") == context["publication_date"])
    assert context["cohort_index"] == 36 and context["publication_date"] == "2026-09-01"
    assert context["original_full_signal"] == target and context["original_signal_sha256"] == canonical_sha(target)
    assert "17 personas" in target["what_happened"] and "$26 mil millones" in target["what_happened"]
