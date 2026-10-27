"""CMF health ecosystem and SIS isapre universe inside the daily engine.

Dirección 27-oct-2026 (decision c): lift ``held_for_core_quality_gate``. The
existing market lane (verified-TLS capture -> ``market_sources`` collectors ->
reviewed primary bindings) now runs in the daily discovery phase with a hard
time budget. ``sis_isapre_universe`` stays a data adapter (no cards). Verified
CMF events (hechos esenciales whose primary PDF bytes match the reviewed
record in ``config/cmf_verified_events_2026_10_11.json``) enter the normal
pending queue and editorial gate as source ``cmf_health_ecosystem``.

Nothing is published from stale evidence: when this run's capture or
collection fails, the scout emits no items and reports the failure.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .models import RawItem
from .processing import DeferredProcessing

SLUG = "cmf_health_ecosystem"
SOURCE_NAME = "Comisión para el Mercado Financiero (CMF)"
ACTIVATION = "daily_engine"
DEFAULT_BUDGET_SECONDS = 900
ISSUER_LABELS = {"cl:rut:93930000-7": "Clínica Las Condes", "cl:rut:94139000-5": "ILC",
                 "cl:rut:76020458-7": "RedSalud", "cl:rut:92051000-0": "INDISA",
                 "cl:rut:96528990-9": "Banmédica", "cl:rut:76005001-6": "Bupa Chile"}


def lane_enabled(env=None):
    from .live_lanes import enabled
    return enabled("RADAR_MARKET_DAILY", env)


def _official_cmf(url):
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == "https" and parsed.hostname in ("www.cmfchile.cl", "cmfchile.cl")
                and parsed.port in (None, 443) and not parsed.username and not parsed.password)
    except (TypeError, ValueError):
        return False


def capture(root, output, budget_seconds, runner=subprocess.run):
    """Verified public capture of the CMF and isapre packages, bounded in time."""
    command = [sys.executable, str(Path(root) / "scripts/probe_source_expansion.py"),
               "--output", str(output), "--packages", "cmf", "isapres"]
    runner(command, check=True, timeout=budget_seconds, cwd=str(root))
    return output


def verified_items(root):
    """Queue items for verified, material CMF events (supporting updates excluded)."""
    root = Path(root)
    events = json.loads((root / "data/market/cmf_events.json").read_text()).get("events", [])
    documents = {d["record_id"]: d for d in json.loads((root / "data/market/cmf_disclosures.json").read_text()).get("documents", [])}
    items = []
    for event in events:
        if event.get("supporting_update") or not event.get("event_date") or not event.get("what_happened"):
            continue
        disclosures = [documents.get(record) for record in event.get("primary_disclosures", [])]
        lead = next((d for d in disclosures if d and d.get("official_document_number") == event.get("official_document_number")), None)
        # Existing verification, re-run in this poll: the primary PDF bytes were
        # fetched now and their sha256 matched the reviewed record.
        if (lead is None or lead.get("primary_verified") is not True or not lead.get("verified_event")
                or lead.get("primary_fetched_this_poll") is not True
                or not _official_cmf(lead.get("discovered_from")) or not _official_cmf(lead.get("source_url"))):
            continue
        number = event["official_document_number"]
        issuer = ISSUER_LABELS.get(event.get("issuer_entity_id"), lead.get("issuer_name") or "Emisor")
        # CMF document links carry a transient token; the issuer's hechos
        # esenciales tab plus the document number is the stable identity.
        stable_url = f"{lead['discovered_from']}#hecho-esencial-{number}"
        items.append(RawItem(
            SLUG, f"{issuer}: {event['what_happened']}"[:350], stable_url, SOURCE_NAME, "official",
            event_date=event["event_date"], raw_text=event["what_happened"],
            metadata={"verified_event": event, "official_document_number": number,
                      "issuer_entity_id": event.get("issuer_entity_id"), "issuer_label": issuer,
                      "primary_document_url": lead["source_url"], "primary_sha256": lead.get("primary_sha256"),
                      "primary_fetched_this_poll": lead.get("primary_fetched_this_poll"),
                      "primary_disclosures": event.get("primary_disclosures", []),
                      "publication_date_source": "cmf_hecho_esencial_fecha",
                      "publication_date_evidence": {"kind": "cmf_hecho_esencial_fecha", "date": lead.get("published_at"),
                                                    "url": lead["discovered_from"], "document": number},
                      "entity_scope": "issuer", "entities": [issuer],
                      "verification": "primary_pdf_sha256_matches_reviewed_record"}))
    return items


class CmfDailyScout:
    slug = SLUG

    def __init__(self, root=None, enabled=None, budget_seconds=None, runner=subprocess.run, collectors=None):
        from .paths import project_root
        self.root = Path(root or project_root())
        self.enabled = enabled
        self.budget_seconds = budget_seconds
        self.runner = runner
        self.collectors = collectors
        self.surface_results = []
        self.discovery_errors = []

    def _record_lane_failure(self, record, reason, slugs=("sis_isapre_universe",)):
        """A daily source that failed is still polled: record the error, never a stale success."""
        for slug in slugs:
            try:
                record(self.root, slug, _lane_failure_evidence(reason))
            except Exception:
                pass

    def discover(self):
        enabled = lane_enabled() if self.enabled is None else self.enabled
        if not enabled:
            self.surface_results = [{"lane": "market_daily", "status": "not_run_outside_engine_runtime"}]
            return []
        from .market_sources import Captures, collect_cmf, collect_isapres
        from .source_health import record_data_adapter
        budget = self.budget_seconds or int(os.getenv("RADAR_MARKET_SECONDS", DEFAULT_BUDGET_SECONDS) or DEFAULT_BUDGET_SECONDS)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output = self.root / "data/market/runtime" / stamp
        started = datetime.now(timezone.utc)
        summary = {"lane": "market_daily", "runtime_activation": ACTIVATION, "budget_seconds": budget,
                   "started_at": started.isoformat(), "capture_dir": str(output.relative_to(self.root))}
        try:
            capture(self.root, output, budget, runner=self.runner)
            captures = Captures(output)
        except subprocess.TimeoutExpired as exc:
            summary.update(status="capture_time_budget_exceeded")
            self.surface_results = [summary]
            self._record_lane_failure(record_data_adapter, f"capture exceeded {budget}s budget")
            raise RuntimeError(f"CMF/SIS capture exceeded {budget}s budget") from exc
        except Exception as exc:
            summary.update(status="capture_failed", error=f"{type(exc).__name__}: {exc}"[:300])
            self.surface_results = [summary]
            self._record_lane_failure(record_data_adapter, f"capture failed: {type(exc).__name__}")
            raise
        collectors = self.collectors or {"sis_isapre_universe": collect_isapres, SLUG: collect_cmf}
        outcomes = {}
        failed = set()
        for slug, collector in collectors.items():
            try:
                evidence = collector(captures, self.root)
                evidence.update(runtime_activation=ACTIVATION, recurrence_validated=False,
                                poll_mode="daily_engine")
                record_data_adapter(self.root, slug, evidence)
                outcomes[slug] = {"status": "ok", "technical_status": evidence.get("technical_status"),
                                  "coverage_reason": evidence.get("coverage_reason")}
            except Exception as exc:
                outcomes[slug] = {"status": "error", "error": f"{type(exc).__name__}: {exc}"[:300]}
                self.discovery_errors.append(f"{slug}: {type(exc).__name__}")
                failed.add(slug)
        if "sis_isapre_universe" in failed:
            self._record_lane_failure(record_data_adapter, outcomes["sis_isapre_universe"]["error"], slugs=("sis_isapre_universe",))
        summary.update(status="collected", collectors=outcomes,
                       elapsed_seconds=round((datetime.now(timezone.utc) - started).total_seconds(), 1))
        self.surface_results = [summary]
        if outcomes.get(SLUG, {}).get("status") != "ok":
            raise RuntimeError("CMF collection failed in this run; no item is emitted from stale evidence")
        return verified_items(self.root)


def _lane_failure_evidence(reason):
    return {"pages_checked": 0, "items_discovered": None, "unique_items": None, "items_recent": None,
            "items_material": None, "published": 0, "rejected": 0, "deferred": 0, "parse_errors": 1,
            "coverage_complete": False, "coverage_reason": f"Daily market lane failed: {reason}",
            "technical_status": "error", "runtime_activation": ACTIVATION, "recurrence_validated": False,
            "poll_mode": "daily_engine", "outcome": "OPERATIVE_DEGRADED"}


def process_cmf_event(raw, cfg):
    """Deterministic card from a reviewed, byte-verified hecho esencial (no AI)."""
    from .editorial_gate import publication_ready
    from .pipeline import build_signal
    from .processing import RejectedProcessing
    event = raw.metadata.get("verified_event") or {}
    if (raw.source_slug != SLUG or raw.metadata.get("verification") != "primary_pdf_sha256_matches_reviewed_record"
            or event.get("event_date") != raw.event_date or not _official_cmf(raw.metadata.get("primary_document_url"))):
        raise DeferredProcessing("CMF verified event binding unavailable")
    effect = " ".join(str(event.get("effect") or "").split())
    number = raw.metadata["official_document_number"]
    why = (f"{effect} " if effect else "") + (
        f"Hecho esencial oficial informado a la CMF (documento N° {number}); fuente primaria del emisor, "
        "no reporte de prensa.")
    raw.metadata.update({"what_happened": event["what_happened"], "why_it_matters": why,
                         "signal_types": ["Noticias"], "scopes": ["Prestadores"],
                         "watch_tags": ["cmf", "hecho esencial", raw.metadata.get("issuer_label", "").lower()],
                         "event_type": "CORPORATE_FINANCE",
                         "scores": {"economic": 80, "regulatory": 40, "scope": 70, "novelty": 75, "actionability": 70}})
    row = build_signal(raw, cfg).to_dict()
    row.update(signal_types=["Noticias"], scopes=["Prestadores"], primary_source_url=raw.metadata["primary_document_url"],
               official_document_number=number, issuer_entity_id=raw.metadata.get("issuer_entity_id"),
               publication_date=raw.event_date, publication_date_source="cmf_hecho_esencial_fecha",
               primary_sha256=raw.metadata.get("primary_sha256"), event_stage=event.get("stage"),
               amount=event.get("amount"), deterministic_processing=True, editorial_relevance=78,
               verification="primary_pdf_sha256_matches_reviewed_record")
    accepted, reason, quality = publication_ready(row)
    if not accepted:
        raise RejectedProcessing(f"editorial_gate_{reason}")
    row["publication_ready_score"] = quality
    return row
