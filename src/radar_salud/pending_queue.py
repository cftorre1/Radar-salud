"""Durable global queue. Discovery never consumes the AI budget.

Single writer enforced by workflow concurrency. Atomic replace protects local
checkpoints; a processing item is retryable after interruption.
"""
import hashlib
import json
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

def now_utc():
    return datetime.now(timezone.utc)

FISCALIZATION_SOURCES = {"superintendencia_fiscalizacion", "suseso_fiscalizacion"}


def legacy_fingerprint(raw):
    return hashlib.sha256(f"{raw.source_slug}|{raw.url}|{raw.title}".encode()).hexdigest()


def fingerprint(raw):
    if raw.source_slug in FISCALIZATION_SOURCES:
        from .superintendencia_fiscalizacion import canonical_url
        identity = raw.metadata.get('source_record_id')
        suffix = f'|record:{identity}' if identity else ''
        return hashlib.sha256(f"{raw.source_slug}|{canonical_url(raw.url)}{suffix}".encode()).hexdigest()
    release = (raw.metadata or {}).get('release_key')
    if raw.source_slug == 'superintendencia_salud' and release:
        # Rolling SIS statistics keep one URL; each re-dated listing is a new release.
        return hashlib.sha256(f"{raw.source_slug}|{raw.url}|{raw.title}|release:{release}".encode()).hexdigest()
    return legacy_fingerprint(raw)

def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)

def lane(raw, now, last_discovered_at=None):
    # Newly integrated sources remain historical until their required
    # 90-day value audit is explicitly completed and reviewed.
    if raw.metadata.get("source_quality_gate") not in (None, "passed"):
        return "BACKFILL"
    if not last_discovered_at:
        return "BACKFILL"
    try:
        published = datetime.fromisoformat(raw.event_date[:10]).date()
        stamp = datetime.fromisoformat(last_discovered_at.replace("Z", "+00:00"))
        current_day=now.date()
        if raw.source_slug=="diario_financiero":
            from zoneinfo import ZoneInfo
            # DF publishes Chile calendar days. A UTC midnight watermark must
            # not turn a still-current Chile article into historical backfill.
            if stamp.tzinfo:stamp=stamp.astimezone(ZoneInfo("America/Santiago"))
            if now.tzinfo:current_day=now.astimezone(ZoneInfo("America/Santiago")).date()
        watermark = stamp.date()
        return "LIVE" if watermark <= published <= current_day and (current_day - published).days <= 7 else "BACKFILL"
    except (TypeError, ValueError):
        return "BACKFILL"

def beyond_backfill_horizon(raw, now, days=90):
    if current_sanction_stock(raw, now):
        return False
    try:
        published = datetime.fromisoformat(raw.event_date[:10]).date()
        return (now.date() - published).days > days
    except (TypeError, ValueError):
        bound=raw.metadata.get('execution_period_year_upper_bound')
        if raw.metadata.get('document_class')=='historical_enforcement_report' and bound:
            try:return (now.date()-datetime.fromisoformat(bound).date()).days>days
            except (TypeError,ValueError):pass
        return False

def current_sanction_stock(raw, now):
    from .suseso_fiscalizacion import current_professional_suspension
    return (raw.source_slug == 'suseso_fiscalizacion'
        and raw.event_date == raw.metadata.get('emission_date')
        and current_professional_suspension(raw.url, raw.metadata, now.date()))


def _reviewed_pulso_admission(raw, previous):
    """Bind a new analysis release to the exact existing reviewed hold.

    Fresh primary fields always win. Only the earlier editorial context is
    copied for the immutable addendum verifier; terminal records never enter
    this path. The returned item grants analysis, never publication.
    """
    if previous.get("status") not in {"pending", "retry"}:
        return None
    old = previous.get("raw", {}).get("metadata", {})
    if not old.get("editorial_hold") and not isinstance(old.get("incremental_review_addendum"), dict):
        return None
    assessment = old.get("editorial_assessment")
    if old.get("editorial_hold") and (not isinstance(assessment, dict)
            or assessment.get("decision") != "pending"
            or assessment.get("reason") != old["editorial_hold"]):
        return None
    from .pulso_incremental_review import apply_incremental_review, verified_incremental_release
    from .pulso_source import complete_article_body
    candidate = deepcopy(raw)
    # Normal discovery retains the complete body/hash without this processor
    # annotation. Derive it from that proof before admission, never override
    # an explicit incomplete primary document.
    candidate.metadata.setdefault("article_body_complete", complete_article_body(candidate.metadata))
    for field in ("incremental_review", "incremental_review_addendum",
                  "editorial_review_context", "event_equivalence_review"):
        if field in old and field not in candidate.metadata:
            candidate.metadata[field] = deepcopy(old[field])
    # The old queue decision must itself match the new bound release. Never
    # replace a fresh, different hold or a different review supplied upstream.
    if (candidate.metadata.get("incremental_review") != old.get("incremental_review")
            or candidate.metadata.get("editorial_hold") not in (None, old.get("editorial_hold"))):
        return None
    if "incremental_review_addendum" not in candidate.metadata:
        candidate.metadata["editorial_hold"] = old["editorial_hold"]
        apply_incremental_review(candidate)
    evidence = verified_incremental_release(candidate)
    if evidence is None or (old.get("editorial_hold") and evidence["previous_hold"] != old["editorial_hold"]):
        return None
    return candidate, evidence, bool(old.get("editorial_hold"))



def _code_repair_pulso_admission(raw, previous):
    """Release a pinned failed assessment once for a new model call only."""
    if (previous.get("status") not in {"pending", "retry"}
            or type(previous.get("attempts")) is not int or previous["attempts"] < 1):
        return None
    old = previous.get("raw", {}).get("metadata", {})
    reason = previous.get("reason")
    assessment = old.get("editorial_assessment")
    validation = old.get("pulso_editorial_proof_validation")
    model = old.get("analysis_model_output")
    old_binding = old.get("primary_item_binding")
    new_binding = raw.metadata.get("primary_item_binding")
    if ("editorial_code_repair_admission" in old
            or not isinstance(assessment, dict) or assessment.get("decision") != "pending"
            or assessment.get("reason") != reason or assessment.get("threshold") != 72
            or not isinstance(validation, dict) or validation.get("decision") != "deferred"
            or validation.get("reason") != reason
            or assessment.get("proof_version") != validation.get("version")
            or not isinstance(model, dict)
            or validation.get("model_response") != model.get("_pulso_analysis_meta")
            or validation.get("analysis_text_sha256") != old.get("analysis_input_body_sha256")
            or validation.get("request_input_sha256") != old.get("analysis_request_input_sha256")
            or validation.get("primary_article_body_sha256") != old.get("article_body_sha256")
            or not isinstance(old_binding, dict) or old_binding.get("verified") is not True
            or old_binding.get("raw_url") != raw.url or old_binding.get("primary_canonical_url") != raw.url
            or old_binding.get("raw_event_date") != raw.event_date
            or old_binding.get("primary_publication_date") != raw.event_date
            or old_binding.get("primary_verification_flags") != {
                "primary_identity_verified": True, "publication_date_verified": True}
            or ("primary_item_binding" in raw.metadata and (
                not isinstance(new_binding, dict) or new_binding.get("verified") is not True
                or new_binding.get("raw_url") != raw.url or new_binding.get("primary_canonical_url") != raw.url
                or new_binding.get("raw_event_date") != raw.event_date
                or new_binding.get("primary_publication_date") != raw.event_date))
            or raw.metadata.get("analysis_input_complete") is False):
        return None
    from .pulso_editorial_proof import verified_code_repair_admission
    from .pulso_source import complete_article_body
    candidate = deepcopy(raw)
    candidate.metadata.setdefault("article_body_complete", complete_article_body(candidate.metadata))
    evidence = verified_code_repair_admission(candidate, previous["raw"], reason)
    if evidence is None:
        return None
    return candidate, evidence

def _same_pulso_model_request(previous_raw, fresh):
    """Retain past processing evidence only for its unchanged primary request."""
    old = previous_raw.get("metadata", {})
    model = old.get("analysis_model_output")
    binding = model.get("_pulso_analysis_meta") if isinstance(model, dict) else None
    if fresh.metadata.get("paywalled") is True:
        return _same_paywalled_pulso_request(previous_raw, fresh, binding)
    if (not isinstance(binding, dict) or not binding.get("response_id")
            or old.get("analysis_input_complete") is not True
            or old.get("article_body_complete") is not True
            or previous_raw.get("url") != fresh.url
            or previous_raw.get("title") != fresh.title
            or previous_raw.get("source_name") != fresh.source_name
            or previous_raw.get("event_date") != fresh.event_date
            or old.get("html_sha256") != fresh.metadata.get("html_sha256")
            or old.get("article_body_sha256") != fresh.metadata.get("article_body_sha256")
            or old.get("page_text") != fresh.metadata.get("page_text")):
        return False
    from .llm_analysis import news_analysis_input
    from .pulso_source import liveblog_analysis_text
    text = (liveblog_analysis_text(fresh.metadata)
            if fresh.metadata.get("publisher_document_type") == "liveblog" else fresh.metadata["page_text"])
    request = news_analysis_input(title=fresh.title, text=text, source_name=fresh.source_name, full_text=True)
    return (hashlib.sha256(text.encode()).hexdigest() == old.get("analysis_input_body_sha256")
            == binding.get("analysis_text_sha256")
            and hashlib.sha256(request.encode()).hexdigest() == old.get("analysis_request_input_sha256")
            == binding.get("request_input_sha256")
            and binding.get("source_name") == fresh.source_name)


def _same_paywalled_pulso_request(previous_raw, fresh, binding):
    """Premium section: compare body receipts (sha256), never stored text.

    The old paid answer is retained when the fresh capture proves the same body
    (same sha256 receipt) and that answer was bound either to that full body
    (pre-policy) or to this exact teaser request. Re-analysis is then decided
    once by ``pulso_paywall``; an unchanged article is never paid again here.
    """
    from .source_rights import redacted_body_verified
    old = previous_raw.get("metadata", {})
    new = fresh.metadata
    if (not isinstance(binding, dict) or not binding.get("response_id")
            or previous_raw.get("url") != fresh.url or previous_raw.get("title") != fresh.title
            or previous_raw.get("source_name") != fresh.source_name
            or previous_raw.get("event_date") != fresh.event_date
            or not redacted_body_verified(new)
            or old.get("article_body_sha256") != new.get("article_body_sha256")
            or old.get("article_body_characters") != new.get("article_body_characters")):
        return False
    if (old.get("analysis_base_article_body_sha256") == new.get("article_body_sha256")
            and binding.get("analysis_text_sha256") == old.get("analysis_input_body_sha256")):
        return True  # pre-policy full-body answer, bound to the receipt's body hash
    from .llm_analysis import news_analysis_input
    teaser = new.get("public_teaser") or ""
    request = news_analysis_input(title=fresh.title, text=teaser, source_name=fresh.source_name, full_text=True)
    return (binding.get("analysis_text_sha256") == hashlib.sha256(teaser.encode()).hexdigest()
            and binding.get("request_input_sha256") == hashlib.sha256(request.encode()).hexdigest())


def _final_paid_revalidation_pulso_admission(raw, previous):
    """Revalidate the two exact c2db answers without another model request."""
    if (previous.get("status") not in {"pending", "retry"}
            or type(previous.get("attempts")) is not int or previous["attempts"] != 5):
        return None
    from .pulso_final_paid_revalidation import verified_admission
    from .pulso_source import complete_article_body
    candidate = deepcopy(raw)
    candidate.metadata.setdefault("article_body_complete", complete_article_body(candidate.metadata))
    evidence = verified_admission(candidate, previous)
    return (candidate, evidence) if evidence is not None else None


def _followup_paid_revalidation_pulso_admission(raw, previous):
    """Release exactly the five reviewed de514 answers, once and unchanged."""
    if (previous.get("status") not in {"pending", "retry"}
            or type(previous.get("attempts")) is not int or previous["attempts"] != 4):
        return None
    from .pulso_followup_paid_revalidation import verified_admission
    from .pulso_source import complete_article_body
    candidate = deepcopy(raw)
    candidate.metadata.setdefault("article_body_complete", complete_article_body(candidate.metadata))
    evidence = verified_admission(candidate, previous)
    return (candidate, evidence) if evidence is not None else None


def _current_paid_revalidation_pulso_admission(raw, previous):
    """Release only the independently reviewed genuine 29731 deferrals."""
    if (previous.get("status") not in {"pending", "retry"}
            or type(previous.get("attempts")) is not int or previous["attempts"] != 3):
        return None
    from .pulso_current_paid_revalidation import verified_admission
    from .pulso_source import complete_article_body
    candidate = deepcopy(raw)
    candidate.metadata.setdefault("article_body_complete", complete_article_body(candidate.metadata))
    evidence = verified_admission(candidate, previous)
    return (candidate, evidence) if evidence is not None else None


def _paid_revalidation_pulso_admission(raw, previous):
    """Clear one pinned paid guard failure without changing its model answer."""
    from .pulso_paid_revalidation import verified_paid_revalidation_admission
    from .pulso_source import complete_article_body
    candidate = deepcopy(raw)
    candidate.metadata.setdefault("article_body_complete", complete_article_body(candidate.metadata))
    evidence = verified_paid_revalidation_admission(candidate, previous)
    return (candidate, evidence) if evidence is not None else None

_FINGERPRINTS = None


def _fingerprints():
    global _FINGERPRINTS
    if _FINGERPRINTS is None:
        from .source_rights import load_fingerprints
        _FINGERPRINTS = load_fingerprints()
    return _FINGERPRINTS


def persisted_items(items):
    """What ``PendingQueue.save`` writes: paywalled captures keep only lead + receipts (Dirección 28-oct-2026)."""
    from .source_rights import paywall_policy, scrub_queue_item
    fingerprints = _fingerprints()
    persisted = {}
    for key, item in items.items():
        raw = item.get("raw") or {} if isinstance(item, dict) else {}
        if isinstance(item, dict) and paywall_policy(raw.get("url", ""), raw.get("metadata")):
            item = deepcopy(item)
            scrub_queue_item(item, fingerprints)
        persisted[key] = item
    return persisted


class PendingQueue:
    def __init__(self, path):
        self.path = Path(path)
        self.items = json.loads(self.path.read_text()) if self.path.exists() else {}
        if not isinstance(self.items, dict):
            raise ValueError("Invalid pending queue; refusing to discard state")

    def save(self):
        # Rights policy (Dirección 28-oct-2026): whatever path wrote a paywalled
        # capture (rediscovery merges, recovery observations, revisions, superseded
        # records), the persisted queue keeps only public lead + receipts.
        # The persisted copy is redacted; the in-memory items are left as the caller holds them.
        atomic_json(self.path, persisted_items(self.items))

    def discover(self, source, items, seen=(), now=None, last_discovered_at=None, published_urls=()):
        now = now or now_utc()
        added = 0
        # Pulso article titles can change between listing, byline and metadata.
        # A single canonical news URL must retain its original durable identity.
        pulso_urls = {}
        if source == "pulso_latercera":
            from .pulso_source import (article_url, complete_article_body,
                                       verified_publication_date_conflict, verified_sponsored_content,
                                       verified_video_without_text, verified_liveblog_temporal_evidence,
                                       verified_sponsored_without_text)
            pulso_urls = {article_url(item["raw"]["url"]): key for key,item in self.items.items()
                          if item["source"] == source and article_url(item["raw"]["url"])}
        # URL identity is scoped to fiscalization. Legacy hashes remain evidence,
        # and a verified rediscovery can repair stock without consuming AI twice.
        from .superintendencia_fiscalizacion import canonical_url
        from collections import Counter
        items=list(items)
        asset_uses=Counter(alias for raw in items for alias in raw.metadata.get('listing_asset_aliases',[]))
        fiscal_index = {}
        for old_key, item in self.items.items():
            if item.get("source") in FISCALIZATION_SOURCES:
                fiscal_index.setdefault((item["source"], canonical_url(item["raw"]["url"]), item['raw'].get('metadata', {}).get('source_record_id')), []).append(old_key)
        for raw in items:
            key = fingerprint(raw)
            if source == "pulso_latercera":
                url = article_url(raw.url)
                previous = self.items.get(pulso_urls.get(url)) if url else None
                if previous is not None:
                    metadata = raw.metadata
                    primary_bound = bool(url and metadata.get("canonical_url") == url)
                    publisher_exception = primary_bound and (
                        (verified_publication_date_conflict(metadata) and raw.event_date is None)
                        or ((verified_video_without_text(metadata) or verified_sponsored_content(metadata)
                             or verified_sponsored_without_text(metadata))
                            and raw.event_date == metadata.get("publication_date")))
                    factual_verified = (metadata.get("article_verified") is True and primary_bound
                                        and metadata.get("primary_identity_verified") is True
                                        and metadata.get("publication_date_verified") is True
                                        and raw.event_date == metadata.get("publication_date")
                                        and complete_article_body(metadata)
                                        and metadata.get("article_body_complete") is not False
                                        and (metadata.get("publisher_document_type") != "liveblog"
                                             or verified_liveblog_temporal_evidence(metadata)))
                    if previous["status"] in ("pending", "retry", "processing") and (factual_verified or publisher_exception):
                        old = previous["raw"]
                        old_meta = old.get("metadata", {})
                        old_assessment = old_meta.get("editorial_assessment")
                        if (isinstance(old_assessment, dict) and old_assessment.get("decision")
                                in {"published", "rejected", "accepted", "approved"}):
                            # Contradictory queue bookkeeping cannot authorize
                            # discarding an already terminal editorial decision.
                            continue
                        body_completeness_derived = "article_body_complete" not in metadata
                        if factual_verified and body_completeness_derived and old_meta.get("article_body_complete") is True:
                            # The processor annotates completeness after analysis;
                            # normal Source discovery retains the full body/hash.
                            # Its omitted annotation is not a changed primary and
                            # must not erase a retained genuine model response.
                            raw = deepcopy(raw)
                            metadata = raw.metadata
                            metadata["article_body_complete"] = complete_article_body(metadata)
                        # Premium sections never enter the pinned full-body paid admissions:
                        # their single teaser decision is made in processing (pulso_paywall).
                        premium = metadata.get("paywalled") is True
                        reviewed_release = _reviewed_pulso_admission(raw, previous) if factual_verified else None
                        admission = reviewed_release if reviewed_release and reviewed_release[2] else None
                        if reviewed_release is not None:
                            raw, admission_evidence, _ = reviewed_release
                            metadata = raw.metadata
                        code_repair = _code_repair_pulso_admission(raw, previous) if factual_verified and not premium else None
                        if code_repair is not None:
                            raw, code_repair_evidence = code_repair
                            metadata = raw.metadata
                        paid_revalidation = _paid_revalidation_pulso_admission(raw, previous) if factual_verified and not premium else None
                        if paid_revalidation is not None:
                            raw, paid_revalidation_evidence = paid_revalidation
                            metadata = raw.metadata
                        current_paid = _current_paid_revalidation_pulso_admission(raw, previous) if factual_verified and not premium else None
                        if current_paid is not None:
                            raw, current_paid_evidence = current_paid
                            metadata = raw.metadata
                        followup_paid = _followup_paid_revalidation_pulso_admission(raw, previous) if factual_verified and not premium else None
                        if followup_paid is not None:
                            raw, followup_paid_evidence = followup_paid
                            metadata = raw.metadata
                        final_paid = _final_paid_revalidation_pulso_admission(raw, previous) if factual_verified and not premium else None
                        if final_paid is not None:
                            raw, final_paid_evidence = final_paid
                            metadata = raw.metadata
                        publisher_holds = {"publisher_conflicting_publication_dates", "publisher_video_text_unavailable",
                                           "publisher_sponsored_content_review_required", "publisher_opinion_taxonomy",
                                           "publisher_liveblog_entry_dates_unverified", "publisher_sponsored_text_unavailable"}
                        resolved_publisher_hold = (factual_verified and not metadata.get("editorial_hold")
                                                   and old_meta.get("editorial_hold") in publisher_holds)
                        proof_fields = ("article_verified", "primary_identity_verified", "publication_date_verified",
                                        "canonical_url", "source_quality_gate", "article_body_complete",
                                        "article_body_sha256", "article_body_characters", "publisher_taxonomy",
                                        "publisher_content_classification", "publisher_exception_reason",
                                        "source_content_unavailable_reason", "video_identity_verified", "video_evidence",
                                        "publication_date_source", "publication_timestamp", "publication_evidence",
                                        "publisher_date_convention", "visible_publication_date", "possible_publication_days",
                                        "html_sha256", "publisher_lastmod", "publisher_document_type",
                                        "liveblog_temporal_evidence", "liveblog_temporal_evidence_verified",
                                        "sponsored_text_evidence")
                        changed = (old.get("event_date") != raw.event_date
                                   or old.get("title") != raw.title or old_meta.get("page_text") != metadata.get("page_text")
                                   or resolved_publisher_hold
                                   or admission is not None or code_repair is not None or paid_revalidation is not None or current_paid is not None or followup_paid is not None or final_paid is not None
                                   or any(old_meta.get(field) != metadata.get(field) for field in proof_fields))
                        if changed:
                            same_processing_input = factual_verified and _same_pulso_model_request(old, raw)
                            revisions = old_meta.get("evidence_revisions", []) + [dict(
                                at=now.isoformat(), previous_publication_date=old.get("event_date"),
                                verified_publication_date=raw.event_date, previous_title=old.get("title"),
                                verified_title=raw.title, previous_capture_method=old_meta.get("capture_method"),
                                reason=("verified_final_paid_guard_revalidation_admission" if final_paid is not None
                                        else "verified_followup_paid_guard_revalidation_admission" if followup_paid is not None
                                        else "verified_current_paid_guard_revalidation_admission" if current_paid is not None
                                        else "verified_paid_guard_revalidation_admission" if paid_revalidation is not None
                                        else "verified_editorial_code_repair_analysis_admission" if code_repair is not None
                                        else "approved_incremental_review_discovery_admission" if admission is not None
                                        else "verified_publisher_exception_rediscovery" if publisher_exception
                                        else "verified_article_rediscovery"),
                                previous_publisher_exception_reason=old_meta.get("publisher_exception_reason"),
                                verified_publisher_exception_reason=metadata.get("publisher_exception_reason"),
                                lane_preserved=previous["lane"])]
                            if old_meta.get("analysis_model_output") or old_meta.get("pulso_editorial_proof_validation"):
                                # Preserve the complete old input, response and
                                # decision before replacing changed evidence.
                                # Revision chains stay separate to avoid copying
                                # the same historical chain into itself.
                                revisions[-1]["previous_processing_raw"] = dict(
                                    deepcopy(old), metadata={field:deepcopy(value) for field,value in old_meta.items()
                                                             if field != "evidence_revisions"})
                            previous["raw"] = asdict(raw)
                            if same_processing_input:
                                for field,value in old_meta.items():
                                    if field.startswith("analysis_") or field in (
                                            "pulso_editorial_proof_validation", "primary_item_binding",
                                            "editorial_assessment", "prospective_evidence", "editorial_code_repair_admission",
                                            "paid_guard_revalidation_admission", "paid_guard_revalidation_receipt",
                                            "paid_guard_new_fast_attempt_receipts", "current_paid_guard_revalidation_admission",
                                            "current_paid_guard_revalidation_receipt", "current_paid_new_fast_attempt_receipts",
                                            "followup_paid_guard_revalidation_admission", "followup_paid_guard_revalidation_receipt",
                                            "followup_paid_new_fast_attempt_receipts", "final_paid_guard_revalidation_admission",
                                            "final_paid_guard_revalidation_receipt"):
                                        previous["raw"]["metadata"][field] = deepcopy(value)
                                revisions[-1]["retained_processing_input_unchanged"] = True
                            if admission is not None:
                                revisions[-1].update(
                                    incremental_review_addendum=deepcopy(admission_evidence),
                                    previous_retry_at=previous.get("retry_at"),
                                    previous_editorial_hold=old_meta["editorial_hold"],
                                    body_completeness_derived_from_verified_hash=body_completeness_derived,
                                    status_preserved=previous["status"], attempts_preserved=previous["attempts"],
                                    detected_at_preserved=previous["detected_at"],
                                    fingerprint_preserved=pulso_urls[url])
                                previous["retry_at"] = None
                            if code_repair is not None:
                                revisions[-1].update(
                                    code_repair_admission=deepcopy(code_repair_evidence),
                                    previous_retry_at=previous.get("retry_at"),
                                    body_completeness_derived_from_verified_hash=body_completeness_derived,
                                    status_preserved=previous["status"], attempts_preserved=previous["attempts"],
                                    detected_at_preserved=previous["detected_at"],
                                    fingerprint_preserved=pulso_urls[url])
                                previous["raw"]["metadata"]["editorial_code_repair_admission"] = deepcopy(code_repair_evidence)
                                previous["retry_at"] = None
                            if paid_revalidation is not None:
                                revisions[-1].update(
                                    paid_guard_revalidation_admission=deepcopy(paid_revalidation_evidence),
                                    previous_retry_at=previous.get("retry_at"),
                                    body_completeness_derived_from_verified_hash=body_completeness_derived,
                                    status_preserved=previous["status"], attempts_preserved=previous["attempts"],
                                    detected_at_preserved=previous["detected_at"], fingerprint_preserved=pulso_urls[url])
                                previous["raw"]["metadata"]["paid_guard_revalidation_admission"] = deepcopy(paid_revalidation_evidence)
                                previous["retry_at"] = None
                            if current_paid is not None:
                                revisions[-1].update(
                                    current_paid_guard_revalidation_admission=deepcopy(current_paid_evidence),
                                    previous_retry_at=previous.get("retry_at"),
                                    body_completeness_derived_from_verified_hash=body_completeness_derived,
                                    status_preserved=previous["status"], attempts_preserved=previous["attempts"],
                                    detected_at_preserved=previous["detected_at"], fingerprint_preserved=pulso_urls[url])
                                previous["raw"]["metadata"]["current_paid_guard_revalidation_admission"] = deepcopy(current_paid_evidence)
                                previous["retry_at"] = None
                            if followup_paid is not None:
                                revisions[-1].update(
                                    followup_paid_guard_revalidation_admission=deepcopy(followup_paid_evidence),
                                    previous_retry_at=previous.get("retry_at"),
                                    body_completeness_derived_from_verified_hash=body_completeness_derived,
                                    status_preserved=previous["status"], attempts_preserved=previous["attempts"],
                                    detected_at_preserved=previous["detected_at"], fingerprint_preserved=pulso_urls[url])
                                previous["raw"]["metadata"]["followup_paid_guard_revalidation_admission"] = deepcopy(followup_paid_evidence)
                                previous["retry_at"] = None
                            if final_paid is not None:
                                revisions[-1].update(
                                    final_paid_guard_revalidation_admission=deepcopy(final_paid_evidence),
                                    previous_retry_at=previous.get("retry_at"),
                                    body_completeness_derived_from_verified_hash=body_completeness_derived,
                                    status_preserved=previous["status"], attempts_preserved=previous["attempts"],
                                    detected_at_preserved=previous["detected_at"], fingerprint_preserved=pulso_urls[url])
                                previous["raw"]["metadata"]["final_paid_guard_revalidation_admission"] = deepcopy(final_paid_evidence)
                                previous["retry_at"] = None
                            for field in ("editorial_hold", "event_equivalence_review"):
                                # A newly proven factual primary article can resolve a
                                # publisher limitation. Incremental/duplicate reviews
                                # are independent editorial decisions and remain.
                                if (field == "editorial_hold" and (admission is not None or (factual_verified
                                        and old_meta.get(field) in publisher_holds))):
                                    continue
                                if field in old_meta and field not in previous["raw"]["metadata"]:
                                    previous["raw"]["metadata"][field] = old_meta[field]
                            previous["raw"]["metadata"]["evidence_revisions"] = revisions
                            previous["raw"]["metadata"]["queue_identity_fingerprint"] = pulso_urls[url]
                    continue
            if source == "diario_financiero":
                from .df_recovery import reconcile_existing
                if reconcile_existing(self, raw, now, last_discovered_at, published_urls):
                    continue
            identity = raw.metadata.get('source_record_id')
            aliases = fiscal_index.get((source, canonical_url(raw.url), identity), []) if source in FISCALIZATION_SOURCES else []
            if source in FISCALIZATION_SOURCES:
                aliases=list(dict.fromkeys(aliases+[key for asset in raw.metadata.get('listing_asset_aliases',[]) if asset_uses[asset]==1
                    for key in fiscal_index.get((source,canonical_url(asset),identity),[])]))
            if aliases:
                records = [(old_key, self.items.pop(old_key)) for old_key in aliases]
                rank = {"published": 5, "rejected": 4, "processing": 3, "retry": 2, "pending": 1, "archived": 0}
                old_key, item = max(records, key=lambda pair: rank.get(pair[1].get("status"), 0))
                item['detected_at']=min(record['detected_at'] for _,record in records)
                legacy_keys = set(item.get("legacy_keys", [])) | {alias for alias, _ in records if alias != key}
                if legacy_keys:
                    item["legacy_keys"] = sorted(legacy_keys)
                duplicates = [record for alias, record in records if alias != old_key]
                if duplicates:
                    item.setdefault("superseded_records", []).extend(duplicates)
                self.items[key] = item
                fiscal_index[(source, canonical_url(raw.url), identity)] = [key]
                verified_date = raw.event_date and raw.metadata.get("event_date_basis")
                if verified_date and asdict(raw) != item["raw"]:
                    item.setdefault("rediscovery_repairs", []).append({
                        "at": now.isoformat(), "previous_raw": item["raw"],
                        "previous_lane": item.get("lane"), "previous_status": item["status"],
                        "previous_reason": item.get("reason"), "reason": "verified_fiscalization_rediscovery"})
                    item["raw"] = asdict(raw)
                    if (item['status']=='rejected' and item.get('reason')=='source_date_conflict_requires_review'
                        and raw.metadata.get('primary_document_review',{}).get('decision')=='publish_fiscalization'
                        and not raw.metadata.get('date_conflicts')):
                        item.update(status='pending',lane='BACKFILL',reason=None,retry_at=None)
                    if item["status"] not in ("published", "rejected"):
                        item["lane"] = lane(raw, now, last_discovered_at)
                        archived = item["lane"] == "BACKFILL" and beyond_backfill_horizon(raw, now)
                        item.update(status="archived" if archived else "pending",
                            reason="outside_90_day_backfill" if archived else None, retry_at=None)
                if item['status'] == 'archived' and str(item.get('reason') or '').startswith('outside_daily_window_'):
                    # Lagged SIS listing: the act became public inside the window (daily_window).
                    from .daily_window import lagged_publication_date, requested_window_days
                    public = lagged_publication_date(item['raw'])
                    if public and (now.date() - public).days <= requested_window_days():
                        item.setdefault('rediscovery_repairs', []).append({
                            'at': now.isoformat(), 'previous_status': 'archived', 'previous_reason': item['reason'],
                            'reason': 'listing_publication_inside_daily_window', 'listing_publication_date': public.isoformat()})
                        item.update(status='pending', reason=None, retry_at=None)
                if (item['status'] == 'archived' and item.get('reason') == 'outside_90_day_backfill'
                    and current_sanction_stock(raw, now)):
                    item.setdefault('rediscovery_repairs', []).append({
                        'at': now.isoformat(), 'previous_status': 'archived',
                        'previous_reason': item['reason'],
                        'reason': 'historical_office_with_current_suspension_stock_context'})
                    item.update(status='pending', lane='BACKFILL', reason=None, retry_at=None)
                continue
            if key not in self.items and raw.source_slug in ('redsalud','bupa_chile','indisa','red_davila','andes_salud','clinicas_chile','pfizer_chile','clinicas_achs_salud'):
                key=next((k for k,v in self.items.items() if v['source']==source and v['raw']['url'].rstrip('/')==raw.url.rstrip('/')),key)
            if key in self.items:
                item=self.items[key]
                # A failed detail fetch may have enqueued an undated news card.
                # Rediscovery can add its now-verified stamp without changing
                # queue identity, detection time, lane or source-quality gate.
                if (raw.source_slug=="clinicas_chile" and item.get("status") in ("pending","retry")
                        and not item["raw"].get("event_date") and raw.event_date
                        and raw.metadata.get("publication_date_source") in ("article:published_time","dated_news_listing")):
                    old_gate=item["raw"].get("metadata",{}).get("source_quality_gate")
                    item["raw"]["event_date"]=raw.event_date
                    item["raw"]["metadata"].update(raw.metadata)
                    if old_gate:item["raw"]["metadata"]["source_quality_gate"]=old_gate
                    item["retry_at"]=None
                continue
            if key in seen or (source in FISCALIZATION_SOURCES and legacy_fingerprint(raw) in seen):
                continue
            item_lane = lane(raw, now, last_discovered_at)
            archived = item_lane == "BACKFILL" and beyond_backfill_horizon(raw, now)
            already_published=False
            if source=="diario_financiero":
                from .df_article import article_url
                already_published=article_url(raw.url) in {article_url(url) for url in published_urls}
            self.items[key] = dict(raw=asdict(raw), source=source, lane=item_lane,
                status="superseded" if already_published else "archived" if archived else "pending", detected_at=now.isoformat(),
                attempts=0, reason="already_published_in_history" if already_published else "outside_90_day_backfill" if archived else None,
                classification_watermark=last_discovered_at)
            # Rights policy (Dirección 28-oct-2026): a new paywalled capture enters the queue
            # already in its stored form (lead + receipts), so memory and disk agree.
            from .source_rights import purge_raw_metadata
            purge_raw_metadata(self.items[key]["raw"])
            if source in FISCALIZATION_SOURCES:
                fiscal_index[(source, canonical_url(raw.url), identity)] = [key]
            added += 1
            if source == "pulso_latercera" and url:
                pulso_urls[url] = key
        self.save()
        return added

    def enforce_backfill_horizon(self, now=None, sources=None):
        now = now or now_utc()
        changed = 0
        for item in self.items.values():
            if sources is not None and item.get("source") not in sources:continue
            if item.get("lane") == "BACKFILL" and item.get("status") in ("pending", "retry", "processing"):
                raw = item.get("raw", {})
                from .models import RawItem
                if raw.get('source_slug') == 'suseso_fiscalizacion' and current_sanction_stock(RawItem(**raw), now):
                    continue
                try:
                    published = datetime.fromisoformat(str(raw.get("event_date"))[:10]).date()
                except (TypeError, ValueError):
                    continue
                if (now.date() - published).days > 90:
                    item.update(status="archived", reason="outside_90_day_backfill")
                    changed += 1
        if changed:self.save()
        return changed

    def defer_exhausted(self, max_attempts=4):
        """Items that keep failing for structural reasons (no verifiable date, video-only article,
        missing capture artifact, ungrounded model output) stop counting as pending after
        ``max_attempts``: they move to ``deferred`` with the last reason kept (Dirección 27-oct-2026:
        pending must mean "still on its way to the feed")."""
        changed = 0
        for item in self.items.values():
            if item.get("status") == "retry" and int(item.get("attempts") or 0) >= max_attempts:
                item.update(status="deferred", reason=f"retry_exhausted:{item.get('reason')}", retry_at=None)
                changed += 1
        if changed:self.save()
        return changed

    def archive_sources(self, slugs, reason):
        """Pending items of sources retired by a recorded decision are kept, archived."""
        changed = 0
        for item in self.items.values():
            if item.get("source") in slugs and item.get("status") in ("pending", "retry"):
                item.update(status="archived", reason=reason)
                changed += 1
        if changed:self.save()
        return changed

    def archive_outside_daily_window(self, days, now=None, sources=None):
        """Items older than the daily processing window can never be processed by the
        daily run; keep them (archived, with a reason) instead of counting them as pending."""
        now = now or now_utc()
        changed = 0
        for item in self.items.values():
            if sources is not None and item.get("source") not in sources:continue
            if item.get("status") not in ("pending", "retry"):continue
            raw = item.get("raw", {})
            if raw.get('source_slug') == 'suseso_fiscalizacion':
                from .models import RawItem
                if current_sanction_stock(RawItem(**raw), now):continue
            from .daily_window import item_date
            published = item_date(item)
            if published is None:
                continue
            if (now.date() - published).days > days:
                item.update(status="archived", reason=f"outside_daily_window_{days}d")
                changed += 1
        if changed:self.save()
        return changed

    def ready(self, now=None):
        now = now or now_utc()
        items = [(key, item) for key, item in self.items.items()
                 if item["status"] in ("pending", "retry", "processing")
                 and not (item.get("lane") == "BACKFILL" and item.get("raw", {}).get("event_date")
                          and str(item["raw"]["event_date"])[:10] > now.date().isoformat())
                 and (not item.get("retry_at") or item["retry_at"] <= now.isoformat())]
        return sorted(items, key=lambda pair: (
            pair[1]["lane"] != "LIVE", pair[1]["attempts"], pair[1]["detected_at"]))

    def start(self, key):
        self.items[key].update(status="processing", attempts=self.items[key]["attempts"] + 1)
        self.save()

    def finish(self, key, status, reason=None, now=None):
        item = self.items[key]
        item.update(status=status, reason=reason, updated_at=(now or now_utc()).isoformat())
        item["retry_at"] = ((now or now_utc()) + timedelta(hours=min(24, 2 ** min(item["attempts"], 5)))).isoformat() if status == "retry" else None
        self.save()

    def counts(self, source=None):
        items = [x for x in self.items.values() if source is None or x["source"] == source]
        return {"live_pending": sum(x["lane"] == "LIVE" and x["status"] in ("pending", "retry", "processing") for x in items),
                "backfill_pending": sum(x["lane"] == "BACKFILL" and x["status"] in ("pending", "retry", "processing") for x in items),
                "rejected": sum(x["status"] == "rejected" for x in items),
                "published": sum(x["status"] == "published" for x in items)}
