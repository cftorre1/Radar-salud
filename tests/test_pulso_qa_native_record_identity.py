"""Native offices may share a listing URL; Pulso articles remain unique."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("native_identity_independent_qa", ROOT / "scripts/qa_pulso_recovery.py")
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)
FIXTURE = ROOT / "tests/fixtures/pulso_qa_native_official_record_identity.json"


@pytest.fixture
def native():
    encoded = FIXTURE.read_bytes()
    assert qa.digest(encoded) == "a7fa64b05212588d031ed300f2366dfabc177106e14dea17f0aae803c3e720f4"
    return json.loads(encoded)["signals"]


def test_actual_three_suseso_oct2_offices_remain_distinct_and_unchanged(native):
    before = deepcopy(native)
    hashes = qa.idempotence_signal_hashes(native)
    assert len(hashes) == 3
    assert {json.loads(key)[2] for key in hashes} == {
        "O-02-S-03209-2026", "O-02-S-03210-2026", "O-02-S-03211-2026"}
    assert set(hashes.values()) == {qa.object_digest(signal) for signal in native}
    assert native == before


def test_same_office_duplicate_is_still_rejected_even_when_copy_differs(native):
    duplicate = deepcopy(native[0])
    duplicate["what_happened"] = "Changing text cannot create another official office."
    duplicate["source_record_id"] = " " + duplicate["source_record_id"] + " "
    with pytest.raises(ValueError, match="duplicate_effective_signal_identity"):
        qa.idempotence_signal_hashes(native + [duplicate])


@pytest.mark.parametrize("record", [None, "", "   ", 123])
def test_missing_or_invalid_native_record_identifier_grants_no_duplicate_exemption(native, record):
    first, second = deepcopy(native[:2])
    first["source_record_id"] = second["source_record_id"] = record
    with pytest.raises(ValueError, match="duplicate_effective_signal_identity"):
        qa.idempotence_signal_hashes([first, second])


@pytest.mark.parametrize("source_type", ["press_high_trust", "official"])
@pytest.mark.parametrize("host", ["www.latercera.com", "latercera.com"])
def test_pulso_duplicate_cannot_invent_record_ids_or_official_label(source_type, host):
    signal = dict(source_type=source_type, source_url=f"https://{host}/pulso/noticia/same-article/",
                  event_date="2026-10-02", source_record_id="fake-one")
    duplicate = dict(signal, source_record_id="fake-two")
    with pytest.raises(ValueError, match="duplicate_effective_signal_identity"):
        qa.idempotence_signal_hashes([signal, duplicate])


def test_non_official_record_ids_do_not_distinguish_duplicates(native):
    first, second = deepcopy(native[:2])
    first["source_type"] = second["source_type"] = "corporate"
    with pytest.raises(ValueError, match="duplicate_effective_signal_identity"):
        qa.idempotence_signal_hashes([first, second])
