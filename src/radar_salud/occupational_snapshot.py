"""Publish the four reconciled occupational lanes without rebuilding other feeds."""
from __future__ import annotations

import copy
from datetime import timedelta
import json

from .beta_sources import CuratedBetaSourceScout
from .editorial_committee import build_committee_artifact
from .editorial_gate import publication_ready
from .history import load_history
from .models import RawItem
from .occupational_evidence import verify_capture
from .occupational_sources import SOURCES, valid_date
from .pending_queue import atomic_json


def prepare_signal(signal):
    """Apply the existing public gate to an already assessed signal."""
    row = copy.deepcopy(signal)
    ok, reason, quality = publication_ready(row)
    if not ok:
        return None, reason
    committee = build_committee_artifact(row)
    if committee["verdict"] != "PASS" or row.get("feed_visibility") is False:
        return None, "committee_" + committee["verdict"].lower()
    row.update(publication_ready_score=quality, publication_gate_reason=reason,
               editorial_committee=committee, feed_visibility=True)
    return row, "ok"


def export_snapshot(root, reports, *, as_of):
    """Only replace exact URLs owned by the supplied source inventories."""
    from .occupational_inventory import _calendar
    today = _calendar(as_of)
    selected = set(reports) & set(SOURCES)
    queue = json.loads((root / "data/state/pending_queue.json").read_text())
    if isinstance(queue, dict) and "items" in queue:
        queue = queue["items"]
    by_url = {item.get("raw", {}).get("url"): item for item in queue.values()
              if item.get("source") in selected}
    current = {row["url"]: (slug, row) for slug, report in reports.items()
               if slug in selected for row in report["rows"] if row.get("status") != "excluded_role"}
    history = load_history(root / "data/history/superintendencia_signals.json")
    accepted, rejected = {}, {}
    for signal in history:
        url = signal.get("source_url")
        if url not in current or url not in by_url:
            continue
        slug, inventory_row = current[url]
        item = by_url[url]
        try:
            raw = RawItem(**item["raw"])
            source_cfg = CuratedBetaSourceScout.SOURCES[slug]
            accepted_roles = source_cfg.get("accepted_roles", (source_cfg["role"],))
            day = valid_date(signal.get("publication_date"), today=today)
            if (item.get("status") != "published" or raw.source_slug != slug
                    or day != raw.event_date or signal.get("event_date") != day
                    or not day or day < (today - timedelta(days=90)).isoformat()
                    or inventory_row.get("publication_date") != day
                    or inventory_row.get("alicanto_status") != "published"
                    or signal.get("title") != raw.title
                    or signal.get("market_role") != raw.metadata.get("market_role")
                    or signal.get("market_role") != inventory_row.get("market_role")
                    or signal.get("market_role") not in accepted_roles
                    or raw.metadata.get("provider_subtype") != inventory_row.get("provider_subtype")
                    or int(signal.get("editorial_relevance", 0)) < 75
                    or signal.get("editorial_relevance") != item.get("editorial_assessment", {}).get("score")
                    or signal.get("what_happened") != raw.metadata.get("what_happened")
                    or signal.get("why_it_matters") != raw.metadata.get("why_it_matters")):
                raise ValueError("publication_queue_inventory_mismatch")
            hosts = source_cfg["hosts"]
            verify_capture(raw, hosts)
            from .occupational_documents import verified_document_text
            verified_document_text(raw, hosts)
            public, reason = prepare_signal(signal)
            if public is None:
                raise ValueError(reason)
            accepted[url] = public
        except Exception as exc:
            rejected[url] = str(exc)
    path = root / "web/data/radar_today.json"
    payload = json.loads(path.read_text())
    before = copy.deepcopy(payload)
    # Preserve every unrelated object and all global snapshot timestamps. A
    # source update is not a fresh collection of the other 26 sources.
    existing_urls = {row.get("source_url") for row in payload["signals"]}
    payload["signals"] = [accepted.get(row.get("source_url"), row) for row in payload["signals"]]
    payload["signals"].extend(row for url, row in accepted.items() if url not in existing_urls)
    if payload != before:
        atomic_json(path, payload)
    for slug, report in reports.items():
        if slug not in selected:
            continue
        for row in report["rows"]:
            url = row["url"]
            if url in accepted:
                row["feed_state"] = "published"
            elif url in rejected:
                row.update(feed_state="deferred", feed_reason=rejected[url])
        report["feed_reconciliation"] = {
            "published": sum(r.get("feed_state") == "published" for r in report["rows"]),
            "deferred": {r["url"]: r["feed_reason"] for r in report["rows"] if r.get("feed_state") == "deferred"},
            "unrelated_signals_preserved": len(before["signals"]) - sum(r.get("source_url") in accepted for r in before["signals"]),
        }
    return {"published": len(accepted), "deferred": rejected, "snapshot_changed": payload != before}
