"""The second peer is bound to actual copies, primary bytes and exact edits."""
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

from radar_salud.pulso_editorial_review import canonical_sha
from radar_salud.pulso_source import extract_article

ROOT = Path(__file__).parents[1]
PATH = ROOT / "data/audits/pulso_mixed_eight_other_publications_second_peer_2026_10_11.json"


def test_all_eight_second_reads_bind_to_primary_actual_model_signal_and_first_readers():
    audit = json.loads(PATH.read_bytes())
    ref = audit["inputs"]["queue"]
    raw = subprocess.check_output(["git", "show", ref["commit"] + ":" + ref["path"]], cwd=ROOT)
    assert hashlib.sha256(raw).hexdigest() == ref["file_sha256"]
    queue = json.loads(raw)
    ref = audit["inputs"]["history"]
    raw = subprocess.check_output(["git", "show", ref["commit"] + ":" + ref["path"]], cwd=ROOT)
    assert hashlib.sha256(raw).hexdigest() == ref["file_sha256"]
    signals = json.loads(raw)["signals"]
    readers = {}
    for ref in audit["independent_first_readers"]:
        raw = (ROOT / ref["reader_path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == ref["reader_sha256"]
        readers[ref["reader_path"]] = json.loads(raw)
        assert hashlib.sha256((ROOT / ref["template_path"]).read_bytes()).hexdigest() == ref["template_sha256"]
    assert len(audit["rows"]) == 8
    for row in audit["rows"]:
        item = next(item for item in queue.values() if item["raw"]["url"] == row["url"])
        metadata = item["raw"]["metadata"]
        signal = next(signal for signal in signals if signal.get("source_url") == row["url"])
        assert item["status"] == "published"
        assert canonical_sha(signal) == row["original_signal_sha256"]
        assert canonical_sha(metadata["analysis_model_output"]) == row["original_model_output_semantic_sha256"]
        assert metadata["analysis_model_output"]["_pulso_analysis_meta"] == row["original_model_response"]
        raw = gzip.decompress((ROOT / row["raw_fixture_path"]).read_bytes())
        assert hashlib.sha256(raw).hexdigest() == row["original_html_sha256"]
        _, body, original = extract_article(raw.decode("utf-8"), row["url"])
        assert hashlib.sha256(body.encode()).hexdigest() == row["original_body_sha256"]
        assert original["publication_date"] == row["publication_date"] == signal["event_date"]
        assert all(quote in body for quote in row["supporting_verbatim_quotes"])
        first = next(record for record in readers[row["first_reader_path"]]["all_signals"]
                     if record["url"] == row["url"])
        assert canonical_sha(first) == row["first_reader_record_sha256"]
        assert row["score_preserved"] == signal["editorial_relevance"] >= 72
        assert row["publication_preapproval"] is False


def test_peer_supports_only_two_exact_existing_corrections_without_new_numbers():
    audit = json.loads(PATH.read_bytes())
    corrections = [row for row in audit["rows"] if row["proposed"]]
    assert len(corrections) == 2
    listeria = next(row for row in corrections if row["sorted25_index"] == 12)
    assert listeria["proposed"] == dict(what_happened=listeria["original_what_happened"],
        why_it_matters=listeria["original_why_it_matters"], category="Regulación & Legal")
    respiratory = next(row for row in corrections if row["sorted25_index"] == 18)
    assert "de la cual 41,2%" in respiratory["original_what_happened"]
    assert "de la cual 41,2%" not in respiratory["proposed"]["what_happened"]
    assert "ocupación general de 86,4%" in respiratory["proposed"]["what_happened"]
    assert "ocupación por causa respiratoria de 41,2%" in respiratory["proposed"]["what_happened"]
    assert respiratory["proposed"]["why_it_matters"] == respiratory["original_why_it_matters"]
    assert audit["summary"]["additional_findings"] == 0
    assert audit["publication_preapproval"] is False and audit["global_acceptance"] is False
