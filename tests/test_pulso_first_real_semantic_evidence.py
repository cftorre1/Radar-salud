"""Every first-run publication finding binds a complete original and output."""
import hashlib
import json
from pathlib import Path
import re
import unicodedata

ROOT = Path(__file__).resolve().parents[1]


def normalized(value):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()


def test_all32_full_originals_verbatim_findings_and_immutable_output_snapshot_are_bound():
    review = json.loads((ROOT / "data/audits/pulso_first_real_all32_semantic_review_2026_10_11.json").read_text())
    ref = review["inputs"]["firstreal_feed"]
    snapshot_path = ROOT / ref["path"]
    assert hashlib.sha256(snapshot_path.read_bytes()).hexdigest() == ref["sha256"]
    signals = json.loads(snapshot_path.read_text())["signals"]
    rows = review["all_signals"]
    assert len(rows) == len(signals) == 32
    assert {row["url"] for row in rows} == {signal["source_url"] for signal in signals}
    assert review["acceptance_pass"] is False and review["changes_applied"] is False
    assert review["required_media_gate_threshold"] == 72
    assert review["frozen_control_denominators_changed"] is False
    by_url = {signal["source_url"]: signal for signal in signals}
    for row in rows:
        signal = by_url[row["url"]]
        body = row["original_full_primary_body"]
        assert row["full_original_body_read"] is True and row["full_signal_read"] is True
        assert len(body) == row["original_primary_body_characters"]
        assert hashlib.sha256(body.encode()).hexdigest() == row["original_body_sha256"]
        assert row["publication_date"] == signal["publication_date"]
        signal_hash = hashlib.sha256(json.dumps(signal, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        assert signal_hash == row["original_output_binding"]["signal_sha256"]
        assert row["original_output_binding"]["snapshot_sha256"] == ref["sha256"]
        assert row["original_model_output_sha256"] is None  # No invented raw provider response.
        assert signal["editorial_relevance"] >= 72 and signal["evidence_maturity"] == "media_reported"
        assert row["decision"] in {"accept", "reject", "group", "correct"}
        assert row["exact_reason"] and row["supporting_verbatim_quotes"]
        for quote in row["supporting_verbatim_quotes"]:
            if quote["origin"] == "original":
                assert normalized(quote["text"]) in normalized(body)
            elif quote["origin"] == "signal":
                assert normalized(quote["text"]) in normalized(signal[quote["field"]])
            else:
                raise AssertionError("Every quoted finding must identify its original or published field")
        assert row["changes_applied"] is False


def test_future_care_expansion_correction_and_later_clinical_increment_are_preserved():
    rows = json.loads((ROOT / "data/audits/pulso_first_real_all32_semantic_review_2026_10_11.json").read_text())["all_signals"]
    care = next(row for row in rows if row["review_index"] == 14)
    assert care["decision"] == "correct"
    assert "habrá un aumento de 2.624 millones" in care["original_full_primary_body"]
    assert "Esto permitirá incorporar 24 nuevas comunas" in care["original_full_primary_body"]
    assert care["proposed_what_happened"] and care["proposed_why_it_matters"]
    clinical_increment = next(row for row in rows if row["review_index"] == 7)
    assert clinical_increment["decision"] == "accept" and clinical_increment["duplicate_of"] is None
    for index in (23, 24, 32):
        assert next(row for row in rows if row["review_index"] == index)["decision"] == "reject"
