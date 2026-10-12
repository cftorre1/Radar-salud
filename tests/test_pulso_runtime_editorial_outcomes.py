"""Real reviewed history is retained without labeling withdrawals as feed loss."""
import importlib.util
import json
from pathlib import Path

from radar_salud.pulso_editorial_review import apply_review, canonical_sha

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("audit_pulso_runtime", ROOT / "scripts/audit_pulso_runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


def inputs():
    original = json.loads((ROOT / "tests/fixtures/pulso_editorial_real/first_paid_outputs.json").read_bytes())
    audit = json.loads((ROOT / "data/audits/pulso_first_paid_editorial_corrections_2026_10_11.json").read_bytes())
    history = [r["signal"] for r in original["records"]]
    queue = {str(i): r["queue_item"] for i, r in enumerate(original["records"])}
    urls = {r["source_url"] for r in history}
    audit["records"] = [r for r in audit["records"] if r["url"] in urls]
    reviewed, new_queue, _ = apply_review(history, queue, audit, audit_sha256=canonical_sha(audit),
                                        audit_path="data/audits/pulso_first_paid_editorial_corrections_2026_10_11.json")
    discovery = {"runtime": "daily_core", "selected_sources": ["pulso_latercera"],
                 "sources": {"pulso_latercera": {"discovered": len(urls), "error_type": None}},
                 "source_details": {"pulso_latercera": [dict(status="discovered", url=row["source_url"],
                    publication_date=row["publication_date"], publication_date_verified=True) for row in reviewed]}}
    feed = [row for row in reviewed if row["feed_visibility"]]
    return discovery, new_queue, reviewed, feed, {}


def test_rejected_and_grouped_real_history_keep_specific_terminal_reason_and_original_gate():
    report = runtime.join_report(*inputs())
    rejected = next(r for r in report["matrix"] if "china-joyvio" in r["url"])
    assert rejected["history_present"] and not rejected["feed_present"]
    assert rejected["history_publication_withdrawn"]
    assert not rejected["traceability_unresolved"] and not rejected["consistency_findings"]
    assert rejected["editorial_outcome"] == "rejected_after_independent_editorial_review"
    assert rejected["exact_reason"].startswith("independent_editorial_review:")
    assert rejected["passed_gate"] is False and rejected["original_model_gate_passed"]
    assert rejected["media_gate_threshold"] == 72 and rejected["editorial_relevance_score"] == 78
    grouped = next(r for r in report["matrix"] if "may-chomali-el-impensado" in r["url"])
    assert grouped["editorial_outcome"] == "grouped_with_published_signal"
    assert grouped["duplicate_of"]["url"] in {r["url"] for r in report["matrix"] if r["feed_present"]}
    assert report["unresolved_recent_feed_exclusions"] == []
    assert report["counts"]["history_urls"] == 5 and report["counts"]["published_in_feed"] == 3


def test_without_matching_review_history_rejection_is_still_a_consistency_failure():
    discovery, queue, history, feed, control = inputs()
    target = next(v for v in queue.values() if "china-joyvio" in v["raw"]["url"])
    target["raw"]["metadata"].pop("editorial_review")
    report = runtime.join_report(discovery, queue, history, feed, control)
    rejected = next(r for r in report["matrix"] if "china-joyvio" in r["url"])
    assert rejected["traceability_unresolved"]
    assert "history_present_with_terminal_queue_rejection" in rejected["consistency_findings"]


def test_withdrawal_accidentally_present_in_serialized_feed_cannot_pass():
    discovery, queue, history, feed, control = inputs()
    feed.append(next(row for row in history if "china-joyvio" in row["source_url"]))
    report = runtime.join_report(discovery, queue, history, feed, control)
    rejected = next(r for r in report["matrix"] if "china-joyvio" in r["url"])
    assert rejected["passed_gate"] is False
    assert "withdrawn_publication_still_in_feed" in rejected["consistency_findings"]
