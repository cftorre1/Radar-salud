"""Daily-cycle evidence standard for mutualidades (Dirección 27-oct-2026).

Queue items whose discovery artifact lived in an uncommitted runtime folder
are verified against a capture taken in the processing run itself, using the
real saved official responses recorded by Actions as fixtures.
"""
from datetime import date
import json
import shutil

import pytest

from radar_salud.occupational_capture import CaptureLoader
from radar_salud.occupational_evidence import verify_capture, verify_visible_header_date, artifact_available
from radar_salud.occupational_sources import SourceDiscoveryError
from radar_salud.processing import DeferredProcessing
from tests.test_occupational_response_binding import LIVE, live_raw

HOSTS = ("www.achs.cl", "achs.cl", "www.mutual.cl", "mutual.cl")
RUNNER = "/home/runner/work/Radar-salud/Radar-salud/data/audits/source_e_recovery/runtime/20261025T203244419407/capture/"


class ReplayCapture:
    """Stands in for CaptureLoader: same record/evidence contract, real bytes."""
    evidence = CaptureLoader.evidence

    def __init__(self, root, source, record, *, blocked=False):
        folder = root / "data/audits/source_e_recovery/runtime/test-processing/capture"
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copy(source, folder / source.name)
        (folder / (source.name.rsplit("-", 1)[0] + ".json")).write_text(json.dumps(record))
        self.records = {record["url"]: dict(record, artifact_dir=str(folder))}
        self.blocked, self.calls = blocked, []

    def __call__(self, url):
        self.calls.append(url)
        if self.blocked:
            raise SourceDiscoveryError("robots_disallowed", url)
        return "captured"


@pytest.fixture
def queued(tmp_path, monkeypatch):
    monkeypatch.setattr("radar_salud.occupational_sources.chile_today", lambda: date(2026, 10, 11))
    monkeypatch.setattr("radar_salud.occupational_evidence.project_root", lambda: tmp_path)

    def build(index=0, **kwargs):
        raw, source, record = live_raw(*LIVE[index])
        # As in data/state/pending_queue.json: the artifact path belongs to an
        # earlier Actions runner and is absent from this checkout.
        raw.metadata["capture_evidence"]["artifact"] = RUNNER + source.name
        return raw, ReplayCapture(tmp_path, source, record, **kwargs)
    return build


def test_missing_runtime_artifact_without_same_run_loader_still_defers(queued):
    raw, _ = queued()
    assert not artifact_available(raw.metadata["capture_evidence"])
    with pytest.raises(DeferredProcessing, match="artifact unavailable"):
        verify_capture(raw, HOSTS)


@pytest.mark.parametrize("index", range(len(LIVE)))
def test_same_run_capture_replaces_manual_artifact_and_stores_evidence(queued, index):
    raw, loader = queued(index)
    stale = dict(raw.metadata["capture_evidence"])
    assert verify_capture(raw, HOSTS, loader=lambda: loader) is None
    evidence = raw.metadata["capture_evidence"]
    record = loader.records[raw.url]
    assert loader.calls == [raw.url]
    assert evidence["capture_mode"] == "same_run_verified" and evidence["tls_verified"] is True
    assert evidence["sha256"] == record["hops"][-1]["sha256"] and evidence["bytes"] == record["hops"][-1]["bytes"]
    assert evidence["final_url"] == record["final_url"] and evidence["fetched_at"] == record["captured_at"]
    assert evidence["http_status"] == 200 and artifact_available(evidence)
    history = raw.metadata["capture_evidence_history"]
    assert history[0]["artifact"] == stale["artifact"] and history[0]["superseded_reason"] == "artifact_unavailable_in_this_run"


def test_same_run_capture_failure_keeps_item_deferred_with_reason(queued):
    raw, loader = queued(blocked=True)
    with pytest.raises(DeferredProcessing, match="same-run capture failed: robots_disallowed"):
        verify_capture(raw, HOSTS, loader=lambda: loader)


def test_same_run_capture_still_requires_identical_title_and_date(queued):
    raw, loader = queued()
    raw.title = "Otro titular"
    with pytest.raises(DeferredProcessing, match="content differs"):
        verify_capture(raw, HOSTS, loader=lambda: loader)
    raw, loader = queued()
    raw.event_date = "2026-01-01"
    with pytest.raises(DeferredProcessing):
        verify_capture(raw, HOSTS, loader=lambda: loader)


def test_fresh_bytes_become_the_analysed_body_only_after_recapture(queued):
    raw, loader = queued()
    body = raw.metadata["page_text"]
    raw.metadata["page_text"] = "texto anterior del listado"
    verify_capture(raw, HOSTS, loader=lambda: loader)
    assert raw.metadata["page_text"] == body and raw.metadata["same_run_capture_body_changed"] is True


def test_ist_visible_header_date_tolerance_is_bounded_and_needs_visible_stamp():
    cms = {"kind": "article:published_time", "date": "2026-08-12", "value": "2026-08-12T11:38:53"}
    proof = {"kind": "publisher:visible_header_date", "value": "10/08/2026", "date": "2026-08-10", "cms_date": "2026-08-12"}
    assert verify_visible_header_date(proof, cms, "10/08/2026 Realizamos una jornada") == "2026-08-10"
    with pytest.raises(DeferredProcessing):
        verify_visible_header_date(proof, cms, "Sin fecha visible")
    with pytest.raises(DeferredProcessing):
        verify_visible_header_date(dict(proof, value="05/08/2026", date="2026-08-05"), cms, "05/08/2026 texto")
    with pytest.raises(DeferredProcessing):
        verify_visible_header_date(proof, dict(cms, date="2026-08-13"), "10/08/2026 texto")
