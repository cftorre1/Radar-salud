"""Read genuine core observations to prove a selected processing replay is inert.

No engine, model, discovery, queue or editorial mutation is invoked here. A
baseline requires independently passing paid processing; a later real core run
must expose zero attempts and zero new response events, not mocked analysis.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

SOURCE = "pulso_latercera"
SCHEMA = "pulso_idempotence_v1"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SELECTION = "data/audits/pulso_material_recovery_cohort_2026_10_11.json"
DEFAULT_REPORT = "data/audits/pulso_runtime_2026_10_11.json"
DEFAULT_QA = "data/audits/pulso_directed_processing_qa_2026_10_11.json"
DEFAULT_BASELINE = "data/audits/pulso_idempotence_baseline_2026_10_11.json"
DEFAULT_RESULT = "data/audits/pulso_idempotence_2026_10_11.json"
RUNTIME_HELPERS = (
    "scripts/audit_pulso_runtime.py", "scripts/qa_pulso_recovery.py",
    "scripts/retain_pulso_runtime_fixtures.py", "scripts/export_web_snapshot.py",
    "scripts/product_report.py", "scripts/apply_pulso_editorial_review.py",
    "scripts/pulso_idempotence.py", "pyproject.toml",
    ".github/workflows/daily-radar.yml", ".github/workflows/pulso-runtime-recovery.yml",
)
RUNTIME_CONFIGS = (
    "sources.json", "beta_source_configs.json", "source_quality_gate.json",
    "media_early_signal_gate.json", "model_routing_v1.json", "taxonomy_v2.json",
    "editorial_rules_v2.json", "editorial_copy_overrides_v1.json",
    "editorial_intelligence_committee_v1.json", "normative_editorial_v2.json",
)
TERMINAL = {"published", "rejected", "archived"}
IMMUTABLE_COHORT_INPUTS = ("frozen_control", "independent_primary_review", "expanded_negative_review")
TECHNICAL_HOLDS = {"analysis_unavailable", "article_verification_failed", "budget_or_analysis_deferred",
                   "analysis_complete_primary_body_not_proven", "fast_analysis_capacity_exhausted"}


def digest(value):
    if not isinstance(value, bytes):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(value).hexdigest()


def stamp(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result if result.tzinfo else None
    except (AttributeError, TypeError, ValueError):
        return None


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def runtime_fingerprint(root):
    # Include newly added runtime modules automatically. Governance queues and
    # marker/git SHAs are not implementation fingerprints.
    files = sorted({str(path.relative_to(root)) for path in (root / "src/radar_salud").glob("*.py")}
                   | set(RUNTIME_HELPERS) | {"config/" + name for name in RUNTIME_CONFIGS})
    required = {"src/radar_salud/engine_cli.py", "src/radar_salud/pulso_source.py", "src/radar_salud/ai_budget.py"}
    require(required <= set(files), "runtime_implementation_missing")
    hashes = {path: digest((root / path).read_bytes()) for path in files}
    return {"files": hashes, "sha256": digest(hashes), "git_or_marker_sha_used": False}


def core_checkout_files(root, code_ref, paths):
    """Bind implementation bytes to the real run's recorded checkout revision.

    The revision locates original blobs; only file hashes establish equality.
    Different marker/data commits can therefore use identical implementation.
    """
    if not isinstance(code_ref, str) or not re.fullmatch(r"[0-9a-f]{40}", code_ref):
        return {"error": "recorded_core_checkout_revision_missing"}
    hashes = {}
    for path in paths:
        result = subprocess.run(["git", "show", code_ref + ":" + path], cwd=root, capture_output=True)
        if result.returncode:
            return {"error": "recorded_core_implementation_blob_unavailable", "path": path}
        hashes[path] = digest(result.stdout)
    return {"files": hashes, "sha256": digest(hashes), "git_or_marker_sha_used": False}


def compact(value):
    """Hash large primary text while retaining its length, never dropping proof."""
    if isinstance(value, dict):
        return {key: ({"utf8_sha256": digest(item.encode()), "characters": len(item)}
                      if key in {"page_text", "raw_text"} and isinstance(item, str) else compact(item))
                for key, item in value.items() if key not in {"last_checked_at", "cache_hit"}}
    if isinstance(value, list):
        return [compact(item) for item in value]
    return value


def signal_index(signals):
    if isinstance(signals, dict):
        signals = signals["signals"]
    require(isinstance(signals, list), "invalid_signal_snapshot")
    indexed = {}
    for signal in signals:
        identity = json.dumps([signal.get("source_url"), signal.get("event_date")], ensure_ascii=False)
        require(identity not in indexed, "duplicate_effective_signal_identity")
        indexed[identity] = digest(signal)
    return indexed


def budget_delta(execution):
    delta = {}
    for tier in ("fast", "deep"):
        delta[tier] = {}
        for metric in ("attempted", "successful", "failed"):
            changes = []
            for scope in ("run", "month"):
                before = execution["budget_before"][scope][tier][metric]
                after = execution["budget_after"][scope][tier][metric]
                require(type(before) is int and type(after) is int and 0 <= before <= after,
                        "invalid_or_decreased_analysis_counter")
                changes.append(after - before)
            require(changes[0] == changes[1], "run_month_analysis_delta_disagree")
            delta[tier][metric] = changes[0]
        require(delta[tier]["attempted"] == delta[tier]["successful"] + delta[tier]["failed"],
                "analysis_attempt_without_result")
    return delta


def source_queue(queue):
    rows = {}
    for fingerprint, item in queue.items():
        if item.get("source") != SOURCE:
            continue
        url = item.get("raw", {}).get("url")
        metadata = item.get("raw", {}).get("metadata", {})
        require(isinstance(url, str) and url not in rows, "duplicate_or_invalid_source_queue_identity")
        rows[url] = dict(fingerprint=fingerprint, status=item.get("status"), attempts=item.get("attempts", 0),
                         semantic_sha256=digest(compact(item)), retry_at=item.get("retry_at"),
                         publication_date=item.get("raw", {}).get("event_date"),
                         lane=item.get("lane"), reason=item.get("reason"),
                         assessment=metadata.get("editorial_assessment"), editorial_hold=metadata.get("editorial_hold"),
                         body_sha256=metadata.get("article_body_sha256"), body_characters=metadata.get("article_body_characters"),
                         source_quality_gate=metadata.get("source_quality_gate"),
                         editorial_review_sha256=digest(metadata["editorial_review"]) if metadata.get("editorial_review") else None)
    return rows


def selected_partition(rows, urls, now):
    terminal, held = [], []
    for url in urls:
        require(url in rows, "selected_queue_identity_missing:" + url)
        row = rows[url]
        require(type(row["attempts"]) is int and row["attempts"] >= 0, "invalid_queue_attempts")
        if row["status"] in TERMINAL:
            terminal.append(url)
            continue
        assessment = row.get("assessment") or {}
        reason = assessment.get("reason") or row.get("editorial_hold") or row.get("reason")
        require(row["status"] in {"pending", "retry"} and isinstance(reason, str) and reason
                and reason not in TECHNICAL_HOLDS and not reason.startswith("pulso_editorial_proof_"),
                "selected_non_editorial_or_unresolved_hold:" + url)
        retry = stamp(row.get("retry_at"))
        future = row.get("lane") == "BACKFILL" and (row.get("publication_date") or "")[:10] > now.date().isoformat()
        require((retry is not None and retry > now) or future, "selected_editorial_hold_is_due:" + url)
        held.append(url)
    return {"terminal_urls": sorted(terminal), "held_not_due_urls": sorted(held)}


def read_context(root, *, selection=DEFAULT_SELECTION, report=DEFAULT_REPORT, qa=DEFAULT_QA):
    paths = dict(selection=selection, report=report, processing_qa=qa,
                 discovery="data/state/discovery_run.json", queue="data/state/pending_queue.json",
                 history="data/history/superintendencia_signals.json", feed="web/data/radar_today.json")
    values, hashes = {}, {}
    for key, relative in paths.items():
        raw = (root / relative).read_bytes()
        hashes[relative] = digest(raw)
        values[key] = json.loads(raw)
    telemetry = root / "data/ai_usage/responses.jsonl"
    raw = telemetry.read_bytes()
    hashes[str(telemetry.relative_to(root))] = digest(raw)
    events = [json.loads(line) for line in raw.decode().splitlines() if line.strip()]
    ledgers = {}
    for path in sorted((root / "data/ai_usage").glob("????-??.json")):
        raw = path.read_bytes()
        ledgers[path.name] = json.loads(raw)
        hashes[str(path.relative_to(root))] = digest(raw)
    references = set()
    inputs = values["selection"].get("inputs", {})
    for key in IMMUTABLE_COHORT_INPUTS:
        value = inputs.get(key)
        require(isinstance(value, dict) and isinstance(value.get("path"), str), "immutable_cohort_reference_missing:" + key)
        path = (root / value["path"]).resolve()
        require(path.is_relative_to(root.resolve()) and digest(path.read_bytes()) == value.get("sha256"),
                "immutable_cohort_reference_changed:" + key)
        references.add(value["path"])
    history = values["history"].get("signals", []) if isinstance(values["history"], dict) else values["history"]
    reviewed = [row.get("editorial_review", {}) for row in history]
    reviewed.extend(item.get("raw", {}).get("metadata", {}).get("editorial_review", {}) for item in values["queue"].values())
    references.update(review["review_file"] for review in reviewed if isinstance(review, dict) and isinstance(review.get("review_file"), str))
    proof_files = {}
    for relative in sorted(references):
        path = (root / relative).resolve()
        require(path.is_relative_to(root.resolve()), "unsafe_referenced_proof_file")
        proof_files[relative] = digest(path.read_bytes())
        hashes[relative] = proof_files[relative]
    fingerprint = runtime_fingerprint(root)
    core_execution = values["report"].get("last_core_execution") or values["report"].get("execution", {})
    values.update(events=events, ledgers=ledgers, observed_files=hashes, runtime_fingerprint=fingerprint,
                  referenced_proof_files=proof_files,
                  cohort_declared_reference_provenance=inputs,
                  recorded_core_runtime_fingerprint=core_checkout_files(root, core_execution.get("code_sha"), fingerprint["files"]))
    return values


def core_proof(context):
    report, discovery, cohort = context["report"], context["discovery"], context["selection"]
    execution = report.get("last_core_execution") or report.get("execution", {})
    start, end = stamp(execution.get("started_at")), stamp(execution.get("finished_at"))
    require(execution.get("mode") == "real_core_processing" and execution.get("engine_called") is True
            and execution.get("engine_completed") is True and start and end and start <= end,
            "genuine_completed_core_processing_required")
    require(execution.get("ai_guardrails_modified") is False, "analysis_guardrails_changed")
    require(isinstance(execution.get("code_sha"), str) and re.fullmatch(r"[0-9a-f]{40}", execution["code_sha"])
            and execution.get("runtime_fingerprint") == context["runtime_fingerprint"]
            and context.get("recorded_core_runtime_fingerprint") == execution["runtime_fingerprint"],
            "actual_core_runtime_fingerprint_unverified")
    require(report.get("discovery_persisted_by_current_execution") is True
            and stamp(discovery.get("at")) and start <= stamp(discovery["at"]) <= end,
            "current_original_discovery_missing")
    source = discovery.get("sources", {}).get(SOURCE, {})
    require(report.get("source") == SOURCE and report.get("runtime") == "daily_core" and report.get("core_source_present") is True
            and discovery.get("runtime") == "daily_core" and discovery.get("selected_sources") == [SOURCE],
            "genuine_source_scoped_daily_core_required")
    require(source.get("technical_status") == "ok" and not source.get("error_type"), "source_discovery_not_complete")
    urls = cohort.get("urls", [])
    require(cohort.get("source") == SOURCE and len(urls) == len(set(urls)) == 113
            and {row["url"] for row in cohort.get("items", [])} == set(urls), "full_immutable_113_cohort_required")
    recorded = discovery.get("processing_selection")
    require(isinstance(recorded, dict) and recorded == execution.get("processing_selection"), "selection_not_bound_to_actual_core")
    sha = context["observed_files"][DEFAULT_SELECTION]
    require(recorded.get("sha256") == recorded.get("file_sha256") == sha
            and recorded.get("reason") == "explicit_queue_selection"
            and recorded.get("selected_urls") == urls
            and recorded.get("selected_url_count") == recorded.get("matched_existing_url_count") == 113
            and not recorded.get("validation_error"), "actual_113_selection_mismatch")
    current = source_queue(context["queue"])
    for item in cohort["items"]:
        url = item["url"]
        require(url in current and current[url]["fingerprint"] == item.get("queue_fingerprint"),
                "immutable_selected_queue_fingerprint_changed:" + url)
        raw = context["queue"][current[url]["fingerprint"]]["raw"]
        metadata = raw.get("metadata", {})
        body = metadata.get("page_text")
        require(isinstance(body, str) and digest(body.encode()) == metadata.get("article_body_sha256") == item.get("body_sha256")
                and len(body) == item.get("body_characters") and raw.get("event_date") == item.get("publication_date"),
                "immutable_selected_primary_body_or_date_changed:" + url)
    delta = budget_delta(execution)
    require(context["ledgers"].get(end.strftime("%Y-%m") + ".json") == execution["budget_after"]["month"],
            "actual_persisted_month_ledger_mismatch")
    run_events = [event for event in context["events"] if stamp(event.get("at")) and start <= stamp(event["at"]) <= end]
    for tier in ("fast", "deep"):
        events = [event for event in run_events if event.get("kind") == tier]
        require(len(events) == delta[tier]["attempted"]
                and sum(event.get("success") is True for event in events) == delta[tier]["successful"],
                "actual_response_events_ledger_mismatch")
        require(all(event.get("response_id") for event in events if event.get("success") is True),
                "actual_successful_response_id_missing")
    ids = [event["response_id"] for event in run_events if event.get("success") is True]
    require(len(ids) == len(set(ids)), "duplicate_actual_response_id")
    return execution, urls, delta, run_events


def semantic_snapshot(context):
    rows = source_queue(context["queue"])
    source_primary = {}
    for row in context["report"].get("matrix", []):
        if not row.get("current_core_detected"):
            continue
        facts = dict(publication_date=row.get("publication_date"), publication_date_verified=row.get("publication_date_verified"),
                     current_core_verified_health=row.get("current_core_verified_health"),
                     metadata_only_candidate=row.get("metadata_only_candidate"),
                     publisher_exception_reason=row.get("publisher_exception_reason"))
        traces = row.get("current_discovery_trace", [])
        facts["body_sha256s"] = sorted({trace["article_body_sha256"] for trace in traces if trace.get("article_body_sha256")})
        source_primary[row["url"]] = facts
    require(source_primary, "current_source_primary_inventory_missing")
    return dict(source_queue=rows, source_primary=source_primary,
                history=signal_index(context["history"]), feed=signal_index(context["feed"]),
                referenced_proof_files=context.get("referenced_proof_files", {}),
                ledgers=context["ledgers"], response_event_sha256s=[digest(event) for event in context["events"]],
                actual_response_ids=[event.get("response_id") for event in context["events"] if event.get("success") is True])


def capture_baseline(context, *, now=None):
    now = now or datetime.now(timezone.utc)
    qa = context["processing_qa"]
    require(qa.get("phase") == "real_core_processing" and qa.get("requested_phase") == "processing"
            and qa.get("verdict") == "PASS_AUTOMATED_PROCESSING_REQUIRES_INDEPENDENT_REVIEW"
            and qa.get("discovery_qa") == "PASS" and qa.get("processing_qa") == "PASS"
            and qa.get("acceptance") == "PENDING_INDEPENDENT_EDITORIAL_AND_FINAL_SHA_REVIEW"
            and not qa.get("findings"), "paid_processing_qa_pass_required")
    execution, urls, delta, events = core_proof(context)
    require(context.get("recorded_core_runtime_fingerprint") == context["runtime_fingerprint"],
            "current_implementation_differs_from_genuine_paid_core")
    require(delta["fast"]["attempted"] > 0 and delta["fast"]["successful"] > 0,
            "positive_genuine_paid_processing_required")
    require(qa.get("checks", {}).get("actual_ai_budget_delta") == delta
            and qa.get("checks", {}).get("actual_fast_response_events") == delta["fast"]["attempted"],
            "passing_qa_not_bound_to_actual_paid_observations")
    selection_check = qa.get("checks", {}).get("processing_selection", {})
    require(selection_check.get("sha256") == context["observed_files"][DEFAULT_SELECTION]
            and selection_check.get("selected_urls") == 113,
            "passing_qa_not_bound_to_full_processing_cohort")
    snapshot = semantic_snapshot(context)
    partition = selected_partition(snapshot["source_queue"], urls, now)
    bundle = dict(schema_version=SCHEMA, mode="genuine_processing_baseline", at=now.isoformat(), read_only=True,
                  baseline_execution=execution, paid_budget_delta=delta,
                  paid_successful_response_ids=[event["response_id"] for event in events if event.get("success") is True],
                  selection=dict(path=DEFAULT_SELECTION, sha256=context["observed_files"][DEFAULT_SELECTION], urls=urls,
                                 count=113, current_partition=partition),
                  observed_files=context["observed_files"], runtime_fingerprint=context["runtime_fingerprint"],
                  cohort_declared_reference_provenance=context.get("cohort_declared_reference_provenance", {}),
                  moving_reference_policy="Cohort-declared runtime/queue hashes cite historical observations; current mutable paths are not immutable review files.",
                  processing_qa=dict(verdict=qa["verdict"], discovery_qa="PASS", processing_qa="PASS",
                                     requested_phase=qa["requested_phase"],
                                     acceptance=qa["acceptance"], phase=qa["phase"],
                                     sha256=context["observed_files"][DEFAULT_QA], checks=qa.get("checks", {})),
                  semantic=snapshot,
                  acceptance_note="Paid processing QA passes; independent editorial/final staging acceptance remains separate.")
    bundle["payload_sha256"] = digest(bundle)
    return bundle


def validate_baseline(bundle):
    require(bundle.get("schema_version") == SCHEMA and bundle.get("mode") == "genuine_processing_baseline"
            and bundle.get("read_only") is True, "invalid_idempotence_baseline")
    require(bundle.get("payload_sha256") == digest({key: value for key, value in bundle.items() if key != "payload_sha256"}),
            "baseline_payload_sha256_mismatch")
    require(bundle.get("processing_qa", {}).get("verdict") == "PASS_AUTOMATED_PROCESSING_REQUIRES_INDEPENDENT_REVIEW"
            and bundle["processing_qa"].get("discovery_qa") == bundle["processing_qa"].get("processing_qa") == "PASS"
            and bundle.get("paid_budget_delta", {}).get("fast", {}).get("successful", 0) > 0
            and bundle.get("paid_successful_response_ids"), "baseline_genuine_paid_proof_missing")
    require(bundle.get("selection", {}).get("count") == 113
            and len(set(bundle["selection"]["urls"])) == 113, "baseline_full_113_selection_missing")
    require(budget_delta(bundle["baseline_execution"]) == bundle["paid_budget_delta"]
            and len(bundle["paid_successful_response_ids"]) == sum(tier["successful"] for tier in bundle["paid_budget_delta"].values())
            and len(set(bundle["paid_successful_response_ids"])) == len(bundle["paid_successful_response_ids"])
            and set(bundle["paid_successful_response_ids"]) <= set(bundle["semantic"]["actual_response_ids"]),
            "baseline_paid_response_ids_or_ledger_invalid")
    require(bundle["baseline_execution"].get("runtime_fingerprint") == bundle["runtime_fingerprint"]
            and re.fullmatch(r"[0-9a-f]{40}", str(bundle["baseline_execution"].get("code_sha", ""))),
            "baseline_original_core_implementation_proof_missing")


def preflight(bundle, context, *, now=None):
    """Fail before engine/model activity if the genuine baseline cannot replay."""
    validate_baseline(bundle)
    now = now or datetime.now(timezone.utc)
    require(bundle["runtime_fingerprint"] == context["runtime_fingerprint"], "runtime_implementation_or_policy_changed")
    require(bundle["selection"]["sha256"] == context["observed_files"][DEFAULT_SELECTION]
            and bundle["selection"]["urls"] == context["selection"]["urls"], "immutable_113_selection_changed")
    snapshot = semantic_snapshot(context)
    require(snapshot == bundle["semantic"], "runtime_state_changed_since_passing_baseline")
    partition = selected_partition(snapshot["source_queue"], bundle["selection"]["urls"], now)
    require(partition == bundle["selection"]["current_partition"], "selected_terminal_or_not_due_partition_changed")
    return dict(schema_version=SCHEMA, mode="before_genuine_core", verdict="PASS", read_only=True,
                baseline_sha256=bundle["payload_sha256"], selected=113, partition=partition,
                ai_calls=0, fingerprint_uses_git_sha=False)


def compare(bundle, context, *, now=None):
    validate_baseline(bundle)
    now = now or datetime.now(timezone.utc)
    findings = []
    def check(condition, code, **evidence):
        if not condition:
            findings.append(dict(code=code, **evidence))
    check(bundle["runtime_fingerprint"] == context["runtime_fingerprint"], "runtime_implementation_or_policy_changed")
    check(context.get("recorded_core_runtime_fingerprint") == context["runtime_fingerprint"],
          "actual_second_core_implementation_not_bound")
    try:
        execution, urls, delta, events = core_proof(context)
        check(stamp(execution["started_at"]) > stamp(bundle["baseline_execution"]["finished_at"]), "second_actual_core_not_fresh")
        check(context["observed_files"][DEFAULT_SELECTION] == bundle["selection"]["sha256"]
              and urls == bundle["selection"]["urls"], "immutable_113_selection_changed")
        check(all(value == 0 for tier in delta.values() for value in tier.values()), "new_analysis_budget_consumed", delta=delta)
        check(not events, "new_actual_model_response_events", count=len(events))
        check(execution.get("processing_attempts_increased") == 0
              and context["discovery"].get("processing_attempts") == 0, "second_core_processing_attempts_nonzero")
        recorded = execution["processing_selection"]
        partition = selected_partition(source_queue(context["queue"]), urls, now)
        check(not recorded.get("ready_selected_urls") and not recorded.get("skipped_in_progress_urls")
              and sorted(recorded.get("skipped_terminal_urls", [])) == partition["terminal_urls"]
              and sorted(recorded.get("skipped_not_due_urls", [])) == partition["held_not_due_urls"],
              "actual_terminal_skip_or_held_not_due_not_proven")
    except (KeyError, TypeError, ValueError) as error:
        findings.append(dict(code="genuine_second_core_proof_invalid", reason=str(error)))
        delta, partition = {}, {}
    after, before = semantic_snapshot(context), bundle["semantic"]
    for key in ("history", "feed", "referenced_proof_files", "ledgers", "response_event_sha256s", "actual_response_ids"):
        check(after[key] == before[key], "changed_" + key)
    added = {}
    for key in ("source_queue", "source_primary"):
        missing = sorted(set(before[key]) - set(after[key]))
        changed = sorted(url for url in set(before[key]) & set(after[key]) if before[key][url] != after[key][url])
        new = sorted(set(after[key]) - set(before[key]))
        check(not missing and not changed, "changed_existing_" + key, missing=missing, changed=changed)
        check(not set(new) & set(bundle["selection"]["urls"]), "new_selected_identity_appeared")
        if key == "source_queue":
            check(all(after[key][url]["attempts"] == 0 and after[key][url]["status"] in {"pending", "archived"} for url in new),
                  "new_unselected_discovery_was_processed")
        added[key] = new
    return dict(schema_version=SCHEMA, mode="after_genuine_core", verdict="FAIL" if findings else "PASS",
                acceptance="IDEMPOTENCE_NOT_PROVEN" if findings else "GENUINE_SELECTED_CORE_IDEMPOTENCE_PROVEN",
                read_only=True, baseline_sha256=bundle["payload_sha256"], observed_files=context["observed_files"],
                runtime_fingerprint=context["runtime_fingerprint"], actual_budget_delta=delta,
                selected_partition=partition, new_unselected_discovery=added,
                history_signal_count=len(after["history"]), feed_signal_count=len(after["feed"]),
                findings=findings, method="Actual selected core execution, paid baseline and immutable semantic identities; no mocked model or injected discovery.")


def write_result(root, path, result):
    target = path if path.is_absolute() else root / path
    relative = target.resolve().relative_to(root.resolve()) if target.resolve().is_relative_to(root.resolve()) else None
    require(relative is None or not str(relative).startswith(("data/state/", "data/history/", "data/ai_usage/", "web/data/")),
            "refusing_to_overwrite_runtime_state")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("capture", "preflight", "compare"))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--baseline", type=Path, default=Path(DEFAULT_BASELINE))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        context = read_context(args.root)
        baseline_path = args.baseline if args.baseline.is_absolute() else args.root / args.baseline
        if args.mode == "capture":
            output = args.output or args.baseline
            destination = output if output.is_absolute() else args.root / output
            if destination.exists():
                result = json.loads(destination.read_bytes())
                preflight(result, context)
                require(result["baseline_execution"] == (context["report"].get("last_core_execution") or context["report"].get("execution")),
                        "refusing_to_replace_genuine_processing_baseline")
            else:
                result = capture_baseline(context)
        else:
            baseline = json.loads(baseline_path.read_bytes())
            result = preflight(baseline, context) if args.mode == "preflight" else compare(baseline, context)
            output = args.output or (Path(DEFAULT_RESULT) if args.mode == "compare" else None)
        if output is not None:
            write_result(args.root, output, result)
        print(json.dumps({key: result.get(key) for key in ("schema_version", "mode", "verdict", "acceptance", "baseline_sha256", "findings")}))
        return 0 if result.get("verdict", "PASS") == "PASS" else 1
    except (OSError, KeyError, TypeError, ValueError) as error:
        print(json.dumps(dict(verdict="FAIL", mode=args.mode, reason=str(error), read_only=True, ai_calls=0)))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
