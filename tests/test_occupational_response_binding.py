"""Origin-response binding regressions using actual saved official captures."""
from copy import deepcopy
from datetime import date
import hashlib
import json
from pathlib import Path
import pytest

from radar_salud.models import RawItem
from radar_salud.occupational_evidence import _captured, verify_capture
from radar_salud.occupational_sources import Article
from radar_salud.processing import DeferredProcessing

ROOT = Path(__file__).resolve().parents[1]
LIVE = [
    ("achs_seguro_laboral", "38120730741/2f8702b2b7fdab6e7e6c"),
    ("achs_seguro_laboral", "38116209530/inventory/capture/f7ea1315f5a411c15bcb"),
    ("achs_seguro_laboral", "38116209530/inventory/capture/a2b95068261acc188842"),
    ("mutual_seguridad", "38116209530/inventory/capture/416dcb2831bc0e60f941"),
]


def live_raw(slug, stem):
    prefix = ROOT / "data/audits/source_e_recovery/actions" / stem
    record = json.loads(prefix.with_suffix(".json").read_text())
    hop = record["hops"][-1]
    path = prefix.parent / hop["body_file"]
    capture = dict(url=record["url"], final_url=record["final_url"], captured_at=record["captured_at"],
                   artifact=str(path), sha256=hop["sha256"], http_status=200, tls_verified=True)
    html = path.read_text()
    if slug == "mutual_seguridad":
        from radar_salud.mutual_sources import parse_detail
        detail = parse_detail(html, record["url"])
        title, day, body, proof = detail["title"], detail["event_date"], detail["body"], detail["evidence"]
    else:
        article = Article(record["url"])
        article.feed(html)
        title, day, body, _ = article.result(today=date(2026, 10, 11))
        proof = article.publication_evidence()
    raw = RawItem(source_slug=slug, title=title, url=record["url"], source_name=slug,
                  source_type="institution_verified", event_date=day, raw_text=body[:1800],
                  metadata={"capture_evidence": capture, "publication_evidence": proof, "page_text": body[:18000]})
    return raw, path, record


@pytest.mark.parametrize("slug,stem", LIVE)
def test_four_current_editorially_published_origin_responses_remain_valid(slug, stem, monkeypatch):
    monkeypatch.setattr("radar_salud.occupational_sources.chile_today", lambda: date(2026, 10, 11))
    raw, _, _ = live_raw(slug, stem)
    assert verify_capture(raw, ("www.achs.cl", "achs.cl", "www.mutual.cl", "mutual.cl")) is None


@pytest.fixture
def copied_real_capture(tmp_path, monkeypatch):
    monkeypatch.setattr("radar_salud.occupational_sources.chile_today", lambda: date(2026, 10, 11))
    monkeypatch.setattr("radar_salud.occupational_evidence.project_root", lambda: tmp_path)
    raw, source, record = live_raw(*LIVE[0])
    folder = tmp_path / "data/audits/source_e_recovery/proof"
    folder.mkdir(parents=True)
    body = folder / source.name
    body.write_bytes(source.read_bytes())
    record_path = folder / (source.name.rsplit("-", 1)[0] + ".json")
    record_path.write_text(json.dumps(record))
    raw.metadata["capture_evidence"]["artifact"] = str(body)
    return raw, body, record_path, record


def test_copied_real_bytes_with_their_actual_record_remain_verifiable(copied_real_capture):
    raw, _, _, _ = copied_real_capture
    assert verify_capture(raw, ("www.achs.cl",)) is None


@pytest.mark.parametrize("mutation", ["arbitrary_name", "missing_record", "request_url", "first_url", "user_agent",
    "final_url", "last_url", "declared_time", "record_time", "stop_reason", "waf", "record_status",
    "hop_status", "curl_exit", "tls", "body_file", "body_sha", "byte_count", "hop_number", "malformed_record"])
def test_real_bytes_cannot_borrow_an_unverified_response_record(copied_real_capture, mutation):
    raw, body, record_path, record = copied_real_capture
    last = record["hops"][-1]
    if mutation == "arbitrary_name":
        unsupported = body.with_name("unsupported-proof.body")
        unsupported.write_bytes(body.read_bytes())
        raw.metadata["capture_evidence"]["artifact"] = str(unsupported)
    elif mutation == "missing_record":
        record_path.unlink()
    elif mutation == "request_url": record["url"] += "/another-article"
    elif mutation == "first_url": last["url"] = "https://www.achs.cl/another-article"
    elif mutation == "user_agent": record["user_agent"] = "browser"
    elif mutation == "final_url": record["final_url"] += "/another-article"
    elif mutation == "last_url": last["url"] = "https://attacker.example/article"
    elif mutation == "declared_time": raw.metadata["capture_evidence"]["captured_at"] = "2000-01-01T00:00:00Z"
    elif mutation == "record_time": record.pop("captured_at")
    elif mutation == "stop_reason": record["stop_reason"] = "network_error"
    elif mutation == "waf": record["waf"] = "challenge"
    elif mutation == "record_status": record["http_status"] = 403
    elif mutation == "hop_status": last["http_status"] = 403
    elif mutation == "curl_exit": last["curl_exit"] = 60
    elif mutation == "tls": last["tls"]["verified"] = False
    elif mutation == "body_file": last["body_file"] = "unrelated.body"
    elif mutation == "body_sha": last["sha256"] = "0" * 64
    elif mutation == "byte_count": last["bytes"] += 1
    elif mutation == "hop_number":
        renamed = body.with_name(body.name.replace("-0.body", "-1.body"))
        body.rename(renamed)
        last["body_file"] = renamed.name
        raw.metadata["capture_evidence"]["artifact"] = str(renamed)
    else:
        record_path.write_text("not-json")
    if mutation not in {"missing_record", "malformed_record"}:
        record_path.write_text(json.dumps(record))
    with pytest.raises(DeferredProcessing):
        verify_capture(raw, ("www.achs.cl",))


@pytest.mark.parametrize("mutation", ["external_hop", "insecure_hop", "bad_redirect_status", "redirect_tls", "redirect_curl"])
def test_native_mutual_redirect_chain_is_revalidated_as_a_whole(tmp_path, monkeypatch, mutation):
    raw, source, record = live_raw(*LIVE[-1])
    monkeypatch.setattr("radar_salud.occupational_evidence.project_root", lambda: tmp_path)
    folder = tmp_path / "data/audits/source_e_recovery/proof"
    folder.mkdir(parents=True)
    body = folder / source.name
    body.write_bytes(source.read_bytes())
    raw.metadata["capture_evidence"]["artifact"] = str(body)
    first = record["hops"][0]
    if mutation == "external_hop": first["url"] = "https://attacker.example/redirect"
    elif mutation == "insecure_hop": first["url"] = first["url"].replace("https:", "http:")
    elif mutation == "bad_redirect_status": first["http_status"] = 200
    elif mutation == "redirect_tls": first["tls"]["verified"] = False
    else: first["curl_exit"] = 35
    body.with_name(body.name.rsplit("-", 1)[0] + ".json").write_text(json.dumps(record))
    with pytest.raises(DeferredProcessing, match="saved response unverified"):
        _captured(raw.metadata["capture_evidence"], raw.url, ("www.mutual.cl", "mutual.cl"))
