"""Targeted state-machine tests; none of these simulations prove live autonomy."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest

from scripts.autonomy_engine import (
    EDITORIAL_TASK, EDITORIAL_REPAIR_TASK, SOURCE_TASKS, LeaseError, ReportError, claim,
    candidate_validated, effective_material_events, evaluate_acceptance, finish, heartbeat, plan, reconcile,
)
from scripts import autonomy_engine as engine


BASE = datetime(2026, 10, 10, tzinfo=timezone.utc)
SHA = "a" * 40
MEDIA = next(task for task, family in SOURCE_TASKS.items() if family == "media")
PUBLIC = next(task for task, family in SOURCE_TASKS.items() if family == "public_data")


def queue(*families):
    selected = families or tuple(SOURCE_TASKS.values())
    return {"input_sha": SHA, "tasks": [
        {"id": task, "status": "approved", "priority": "critical",
         "objective": "Repair " + family, "depends_on": [], "evidence_revision": "v1"}
        for task, family in SOURCE_TASKS.items() if family in selected]}


def gates():
    return [{"name": "targeted", "status": "PASS", "command": "python -m unittest",
             "returncode": 0, "log_path": "evidence/test.log", "log_sha256": "f" * 64}]


def blocked(reason="failed", fingerprint="stable", evidence=None):
    return {"status": "BLOCKED", "blockers": [{"fingerprint": fingerprint,
        "reason": reason, "evidence": evidence or [{"path": "evidence/failure.json", "sha256": "f" * 64}]}]}


def mutation(**overrides):
    report = {"status": "REPAIRED", "candidate_commit": "b" * 40,
        "changed_paths": ["config/source.json"], "validated": True, "gates": gates(),
        "before_hash": "1" * 64, "after_hash": "2" * 64,
        "evidence": [{"path": "evidence/test.log", "sha256": "f" * 64}]}
    report.update(overrides)
    return report


def passed(task_id=MEDIA):
    proof = {
        "verified": True, "task_id": task_id, "candidate_sha": SHA, "verdict": "PASS",
        "path": "evidence/acceptance.json", "sha256": "d" * 64,
        "checks": ["publication_trace", "editorial_acceptance"],
        "evidence": [{"path": "evidence/source.json", "sha256": "e" * 64}]}
    if task_id in SOURCE_TASKS:
        runtime = {"kind": "runtime_after_merge", "path": "evidence/runtime-after-merge.json",
                   "sha256": "9" * 64}
        proof.update(staging_merge_sha=SHA, origin_staging_sha=SHA,
                     runtime_after_merge=[runtime], checks={name: True for name in (
                         "external_reconciliation_30d", "external_reconciliation_90d",
                         "publication_trace", "source_health", "qa_pass",
                         "independent_review_pass", "runtime_after_merge_pass")})
        proof["evidence"].append(deepcopy(runtime))
    return {"status": "PASS", "validated": True, "gates": gates(), "acceptance_proof": [proof]}


def failure(run_id="123"):
    return {"run_id": run_id, "conclusion": "failure", "head_sha": SHA,
            "run_url": "https://github.com/cftorre1/Radar-salud/actions/runs/" + run_id}


def source_failure():
    return {"kind": "source_runtime", "verified": True,
            "source_url": "https://source.example/news", "source_slug": "diario_financiero",
            "failure_signature": "parser-failure", "trace_path": "trace.json",
            "trace_sha256": "7" * 64, "observed_at": BASE.isoformat()}


def partial():
    baseline = {**gates()[0], "status": "FAIL", "returncode": 1, "log_sha256": "3" * 64}
    candidate = {**gates()[0], "status": "FAIL", "returncode": 1, "log_sha256": "4" * 64}
    return mutation(validated=False, partial_candidate=True, targeted_validated=True,
        no_new_failures=True, candidate_scope="isolated", directed_gates=gates(),
        live_validated=True, live_gate=gates()[0],
        gates=[gates()[0], candidate], non_regression={
            "baseline_failures": ["5" * 64], "candidate_failures": ["5" * 64],
            "baseline_gate": baseline, "candidate_gate": candidate})


def qa_observation(run_id, sha, *, product="same-product", variant="1"):
    """Compact reproduction of the hosted four-component transport-only loop."""
    tid = "staging_qa_failed_run_" + run_id
    proof = {**failure(run_id), "head_sha": sha, "failure_signature": "same-normative-contract"}
    q = {"input_sha": sha, "tasks": [{"id": tid, "status": "approved", "family": "staging_qa",
        "failure": proof, "input_fingerprint": product + ":same-executor", "product_input_fingerprint": product}]}
    raw = {"command": ["python", "-m", "pytest"], "returncode": 1,
           "output": "FAILED tests/test_web_snapshot.py::normative - assert 11 >= 12\n1 failed in " + variant + "s\n",
           "captured_stdout_sha256": variant * 64, "captured_stdout_bytes": 200 + int(variant)}
    evidence = [
        ("targeted gate failed", [{"name": "targeted", "status": "FAIL", "returncode": 1,
            "pytest": {"cases": [{"name": "normative", "status": "FAIL", "reason": "assert 11 >= 12"}]},
            "failure_hash": variant * 64},
            {"status": "BLOCKED", "failure_sha256": variant * 64, "evidence": [raw],
             "context": [{"path": "web/data/radar_today.json", "sha256": "f" * 64}]}]),
        ("acceptance missing", [{"family": "staging_qa", "task_id": tid, "diagnostics_are_acceptance": False}]),
        ("reviewer rejected", [{"command": ["python", "review_candidate.py", "--sha", sha],
            "returncode": 1, "status": "FAIL", "failure_hash": variant * 64,
            "reviewer_proof": {"candidate_sha": sha, "checks": {"statistics": False},
                "findings": [{"code": "missing_pdf", "path": "https://source.example/bulletin", "detail": "Four PDFs required"}]}}]),
        ("browser rejected", [{"command": ["npm", "run", "test:browser"], "returncode": 1,
            "status": "FAIL", "failure_hash": variant * 64,
            "browser_proof": {"projects": ["desktop", "mobile"],
                "stats": {"expected": 32, "unexpected": 14, "duration": int(variant) * 100,
                          "startTime": "2026-10-10T00:0" + variant + ":00Z"}}}]),
    ]
    report = {"status": "BLOCKED", "blockers": [{"kind": "technical", "reason": reason,
                "fingerprint": engine._hash([reason, sha, run_id, variant]), "evidence": items}
                for reason, items in evidence]}
    return q, report


def legacy_qa_duplicate_state():
    """Simulate persisted pre-fix events, without invoking the fixed credit path."""
    state = {"tasks": {}, "material_events": [], "lease_events": [], "pending_transitions": [],
             "acceptance": {"mode": "simulation", "started_at": BASE.isoformat()}}
    for index, (run_id, sha) in enumerate((("123", SHA), ("124", "b" * 40))):
        q, report = qa_observation(run_id, sha, variant=str(index + 1))
        current = reconcile({}, q, BASE + timedelta(minutes=index))
        tid = q["tasks"][0]["id"]
        task = current["tasks"][tid]
        details = {"fingerprint": engine._hash([x["fingerprint"] for x in report["blockers"]]),
            "reason": "; ".join(x["reason"] for x in report["blockers"]),
            "blockers": report["blockers"], "evidence": [y for x in report["blockers"] for y in x["evidence"]],
            "real_failure": deepcopy(task["failure"]), "failure_action": "blocked"}
        at = (BASE + timedelta(minutes=index)).isoformat().replace("+00:00", "Z")
        event = {"id": "legacy-" + run_id, "kind": "blocker", "family": "staging_qa", "task_id": tid,
                 "at": at, "details": details}
        task.update(status="BLOCKED", blocker=deepcopy(details), material_progress_at=at,
                    material_watch_started_at=at, recovery_episode=event["id"])
        state["tasks"][tid] = task
        state["material_events"].append(event)
        state["lease_events"].append({"task_id": tid, "kind": "pickup", "autonomous": True, "at": at})
        state["pending_transitions"].append({"task_id": tid, "family": "staging_qa", "event_id": event["id"], "at": at})
    return state


def source_observation(variant="1", *, product="a" * 64):
    """Parsed source facts retain all failures while capture bytes rotate."""
    q = queue("media")
    q["tasks"][0].update(input_fingerprint="scoped-executor", product_input_fingerprint=product,
                         evidence_revision="revision-" + variant)
    row = {"slug": "diario_financiero", "technical_status": "error", "discovered": 0, "dated": 0,
        "inventory_hash": "9" * 64, "samples": [], "error": "HTTPError: HTTP 403 Forbidden",
        "requests": [{"url": "https://source.example/news", "status": "FAIL", "error": "HTTP 403 Forbidden",
                      "response_sha256": variant * 64, "response_bytes": int(variant) * 100},
                     {"url": "https://source.example/archive", "status": "PASS",
                      "response_sha256": variant * 64, "response_bytes": int(variant) * 200}]}
    gate = {"command": ["python", "scout", "--diagnose-source", "diario_financiero"], "returncode": 1,
            "status": "FAIL", "failure_hash": variant * 64, "log_sha256": variant * 64,
            "log_path": "capture-" + variant + ".log", "source_urls": [x["url"] for x in row["requests"]]}
    recovery = {"automated_recovery": {"status": "BLOCKED", "reason": "Approved parser repair plan absent"}}
    report = {"status": "BLOCKED", "real_failure": {**source_failure(), "observed_at": variant,
              "failure_signature": "producer-" + variant}, "failure_action": "blocked", "blockers": [
        {"kind": "technical", "reason": "Scoped live discovery failed: diario_financiero",
         "fingerprint": variant * 64, "evidence": [gate, row, recovery]},
        {"kind": "acceptance", "reason": "Explicit acceptance missing", "fingerprint": "a" * 64,
         "evidence": [{"task_id": MEDIA, "family": "media", "diagnostics_are_acceptance": False}]}]}
    if variant != "1":
        row["requests"].reverse()
        gate["source_urls"].reverse()
        report["blockers"].reverse()
    return q, report


def legacy_source_duplicate_state(*, bindings=True):
    """Simulated historical authority; production imports verify actual Git."""
    state = {"tasks": {}, "material_events": [], "lease_events": [], "pending_transitions": []}
    for index in range(2):
        q, report = source_observation(str(index + 1))
        current = reconcile({}, q, BASE + timedelta(minutes=index))
        task = current["tasks"][MEDIA]
        blockers = engine._blockers(report)
        details = {"fingerprint": engine._hash([b["fingerprint"] for b in blockers]),
            "reason": "; ".join(b["reason"] for b in blockers), "blockers": deepcopy(blockers),
            "evidence": [x for b in blockers for x in b["evidence"]],
            "real_failure": deepcopy(report["real_failure"]), "failure_action": "blocked"}
        at = engine._iso(BASE + timedelta(minutes=index))
        event = {"id": "legacy-source-" + str(index), "task_id": MEDIA, "family": "media",
                 "kind": "blocker", "at": at, "details": details}
        state["material_events"].append(event)
        state["pending_transitions"].append({"task_id": MEDIA, "family": "media", "event_id": event["id"], "at": at})
        task.update(status="BLOCKED", blocker=deepcopy(details), material_progress_at=at,
                    material_watch_started_at=at, recovery_episode=event["id"])
        state["tasks"][MEDIA] = task
        if bindings:
            state.setdefault("material_event_product_bindings", {})[event["id"]] = {
                "schema_version": 1, "verified": True, "task_id": MEDIA, "family": "media",
                "event_sha256": engine._hash(event), "input_sha": SHA, "product_input_fingerprint": "a" * 64,
                "proof": {"state_commit": str(index + 1) * 40, "control_sha256": str(index + 1) * 64,
                    "worker_result": {"path": "data/autopilot/evidence/worker-" + str(index) + ".json", "sha256": "e" * 64}}}
    transition = {"id": "real-transition", "task_id": MEDIA, "family": "media", "kind": "transition",
        "at": engine._iso(BASE + timedelta(seconds=30)), "details": {"independent": True}}
    state["material_events"].insert(1, transition)
    return state, q


class SourceMaterialIdentityTests(unittest.TestCase):
    def test_capture_clock_body_bytes_order_and_producer_signature_are_not_new_problem(self):
        q, report = source_observation()
        state, lease = claim({}, q, "media", "worker", BASE)
        state = finish(state, MEDIA, lease["token"], report, BASE)
        old = deepcopy(state["material_events"])
        q, report = source_observation("2")
        state, lease = claim(state, q, "media", "worker", BASE + timedelta(minutes=1))
        state = finish(state, MEDIA, lease["token"], report, BASE + timedelta(minutes=1))
        self.assertEqual(state["material_events"], old)
        self.assertEqual(old[0]["details"]["product_input_fingerprint"], "a" * 64)
        self.assertEqual(state["tasks"][MEDIA]["status"], "BLOCKED")

    def test_real_urls_errors_inventory_dates_content_and_product_remain_material(self):
        changes = (
            lambda q, row: row["requests"][0].update(url="https://source.example/new"),
            lambda q, row: row["requests"][0].update(status="FAIL", error="HTTP 404 Not Found"),
            lambda q, row: row.update(error="UnicodeEncodeError: URI contains non-ASCII"),
            lambda q, row: row.update(inventory_hash="b" * 64),
            lambda q, row: row.update(samples=[{"title": "New bulletin", "date": "2026-10-11", "content_hash": "c" * 64}]),
            lambda q, row: row.update(samples=[{"assertion": "effective_at", "observed_at": "2026-10-11T00:00:00Z"}]),
            lambda q, row: q["tasks"][0].update(product_input_fingerprint="d" * 64),
        )
        for change in changes:
            with self.subTest(change=change):
                q, report = source_observation()
                state, lease = claim({}, q, "media", "worker", BASE)
                state = finish(state, MEDIA, lease["token"], report, BASE)
                q, report = source_observation("2")
                row = next(b["evidence"][1] for b in report["blockers"] if b["kind"] == "technical")
                change(q, row)
                state, lease = claim(state, q, "media", "worker", BASE + timedelta(minutes=1))
                state = finish(state, MEDIA, lease["token"], report, BASE + timedelta(minutes=1))
                self.assertEqual(len([e for e in state["material_events"] if e["kind"] == "blocker"]), 2)

    def test_source_assertion_dates_and_content_hashes_are_not_observation_metadata(self):
        old = {"samples": [{"publication_date": "2026-10-10", "observed_at": "2026-10-10T00:00:00Z", "sha256": "a" * 64}]}
        for change in ({"publication_date": "2026-10-11"}, {"observed_at": "2026-10-11T00:00:00Z"}, {"sha256": "b" * 64}):
            new = deepcopy(old)
            new["samples"][0].update(change)
            self.assertNotEqual(engine._source_problem(old), engine._source_problem(new))

    def test_opaque_or_malformed_source_rows_cannot_erase_capture_evidence(self):
        for damage in (lambda row: row.update(slug="unknown"), lambda row: row["requests"].append({}),
                       lambda row: row.pop("technical_status")):
            q, report = source_observation()
            technical = report["blockers"][0]
            damage(technical["evidence"][1])
            details = {"blockers": [technical], "evidence": technical["evidence"]}
            self.assertIsNone(engine._source_blocker_identity(details, "a" * 64, "media"))
            self.assertIn("failure_hash", engine._source_problem(technical["evidence"][0]))

    def test_legacy_sources_require_trusted_historical_product_bindings(self):
        state, q = legacy_source_duplicate_state(bindings=False)
        corrected = reconcile(state, q, BASE + timedelta(minutes=2))
        self.assertEqual(len(effective_material_events(corrected)), 3)
        self.assertEqual(corrected["material_event_corrections"], [])

    def test_bound_legacy_duplicate_retires_credit_preserves_raw_and_rolls_back_watch(self):
        state, q = legacy_source_duplicate_state()
        original = deepcopy(state["material_events"])
        corrected = reconcile(state, q, BASE + timedelta(minutes=2))
        self.assertEqual(corrected["material_events"], original)
        self.assertEqual([x["id"] for x in effective_material_events(corrected)], ["legacy-source-0", "real-transition"])
        self.assertEqual(corrected["material_event_corrections"][0]["kind"], "duplicate_source_blocker")
        task = corrected["tasks"][MEDIA]
        self.assertEqual(task["material_progress_at"], original[1]["at"])
        self.assertEqual(task["material_watch_started_at"], original[1]["at"])
        self.assertEqual(task["recovery_episode"], "real-transition")
        self.assertEqual([x["event_id"] for x in corrected["pending_transitions"]], ["legacy-source-0"])
        again = reconcile(corrected, q, BASE + timedelta(minutes=3))
        self.assertEqual(corrected["material_event_corrections"], again["material_event_corrections"])

    def test_historical_binding_tamper_and_product_change_fail_closed(self):
        changes = (
            lambda b: b.update(event_sha256="f" * 64), lambda b: b.update(task_id="other"),
            lambda b: b.update(family="public_data"), lambda b: b.update(verified=False),
            lambda b: b.update(product_input_fingerprint="b" * 64),
            lambda b: b["proof"].update(state_commit="bad"),
            lambda b: b["proof"]["worker_result"].update(path="data/autopilot/evidence/../worker.json"),
            lambda b: b["proof"]["worker_result"].update(sha256="bad"),
        )
        for change in changes:
            with self.subTest(change=change):
                state, q = legacy_source_duplicate_state()
                change(state["material_event_product_bindings"]["legacy-source-1"])
                corrected = reconcile(state, q, BASE + timedelta(minutes=2))
                self.assertEqual(len(effective_material_events(corrected)), 3)

    def test_frozen_correction_survives_future_product_movement_but_not_raw_tampering(self):
        state, q = legacy_source_duplicate_state()
        corrected = reconcile(state, q, BASE + timedelta(minutes=2))
        moved = deepcopy(corrected)
        moved["tasks"][MEDIA]["product_input_fingerprint"] = "b" * 64
        moved.pop("material_event_product_bindings")
        self.assertEqual(len(effective_material_events(moved)), 2)
        component = next(b for b in moved["material_events"][0]["details"]["blockers"] if b["kind"] == "technical")
        component["evidence"][1]["inventory_hash"] = "c" * 64
        self.assertEqual(len(effective_material_events(moved)), 3)

    def test_frozen_historical_proof_cannot_be_substituted_after_correction(self):
        state, q = legacy_source_duplicate_state()
        corrected = reconcile(state, q, BASE + timedelta(minutes=2))
        for change in (lambda b: b["proof"].update(control_sha256="f" * 64),
                       lambda b: b["proof"].update(state_commit="f" * 40),
                       lambda b: b["proof"]["worker_result"].update(sha256="f" * 64),
                       lambda b: b.update(family="public_data")):
            altered = deepcopy(corrected)
            change(altered["material_event_corrections"][0]["bindings"][0])
            self.assertEqual(len(effective_material_events(altered)), 3)

    def test_probe_guard_only_is_not_a_real_source_failure_despite_legacy_verified_flag(self):
        q, report = source_observation()
        row = report["blockers"][0]["evidence"][1]
        row.update(error="RuntimeError: bounded_probe_budget:24 requests per source", technical_status="error")
        row["requests"] = [{"url": "https://source.example/news", "status": "UNVERIFIED", "error": "bounded_probe_budget:24 requests per source"}]
        self.assertFalse(engine.source_failure_evidenced(report["real_failure"], report["blockers"]))
        state, lease = claim({}, q, "media", "worker", BASE)
        state = finish(state, MEDIA, lease["token"], report, BASE)
        self.assertNotIn("last_failure", state["tasks"][MEDIA])
        self.assertEqual(state["failure_history"], {})
        legacy = {"kind": "closure", "family": "media", "details": {**passed(), "input_sha": SHA,
            "real_failure": report["real_failure"], "failure_action": "repaired", "failure_evidence": report["blockers"]}}
        self.assertFalse(engine._repaired_failure_event(legacy))

    def test_correcting_budget_classification_and_skipping_false_recovery_is_not_new_credit(self):
        q, report = source_observation()
        old = report["blockers"][0]
        row = old["evidence"][1]
        row.update(error="RuntimeError: bounded_probe_budget:24 requests per source",
                   requests=[{"url": "https://source.example/news", "status": "PASS", "response_sha256": "a" * 64},
                             {"url": "https://source.example/omitted", "status": "UNVERIFIED", "error": "bounded_probe_budget:24 requests per source"}])
        newer = deepcopy(old)
        newer.update(kind="instrumentation", reason="Scoped coverage INCOMPLETE: internal request budget reached: diario_financiero")
        newer["evidence"][1].update(technical_status="incomplete", probe_complete=False,
            failure_origin="instrumentation_limit", probe_budget={"max_requests": 24, "unexecuted_requests": 1})
        newer["evidence"][2] = {"automated_recovery": {"attempted": False, "reason": "Instrumentation limit is not a demonstrated source failure"}}
        old_identity = engine._source_blocker_identity({"blockers": [old], "evidence": old["evidence"]}, "a" * 64, "media")
        new_identity = engine._source_blocker_identity({"blockers": [newer], "evidence": newer["evidence"]}, "a" * 64, "media")
        self.assertEqual(old_identity, new_identity)
        # An actually executed previously omitted URL changes the retained
        # coverage evidence and may establish a newly evidenced problem.
        newer["evidence"][1]["requests"][1].update(status="FAIL", error="HTTP 403 Forbidden")
        self.assertNotEqual(old_identity, engine._source_blocker_identity(
            {"blockers": [newer], "evidence": newer["evidence"]}, "a" * 64, "media"))

    def test_mixed_guard_and_real_http_or_parser_failure_is_still_verified(self):
        for error in ("HTTP 403 Forbidden", "UnicodeEncodeError: URI contains non-ASCII",
                      "ValueError: parser assertion mentions bounded_probe_budget:24"):
            q, report = source_observation()
            row = report["blockers"][0]["evidence"][1]
            row["requests"].append({"url": "https://source.example/omitted", "status": "UNVERIFIED", "error": "bounded_probe_budget:24"})
            row["error"] = error
            self.assertTrue(engine.source_failure_evidenced(report["real_failure"], report["blockers"]))
            self.assertFalse(engine._source_probe_incomplete(row))

    def test_guard_only_legacy_last_failure_cannot_become_repaired_on_postmerge_closure(self):
        q, report = source_observation()
        row = report["blockers"][0]["evidence"][1]
        row.update(error="bounded_probe_budget:24", requests=[])
        state, lease = claim({}, q, "media", "worker", BASE)
        state["tasks"][MEDIA].update(last_failure=report["real_failure"], blocker={"evidence": [row]})
        closed = finish(state, MEDIA, lease["token"], passed(), BASE)
        self.assertNotIn("failure_action", closed["material_events"][0]["details"])


class AutonomyEngineTests(unittest.TestCase):
    def test_hosted_run_task_sha_and_raw_log_churn_cannot_credit_same_problem(self):
        q, report = qa_observation("123", SHA)
        state, lease = claim({}, q, "staging_qa", "worker", BASE)
        state = finish(state, lease["task_id"], lease["token"], report, BASE)
        old = deepcopy(state["material_events"][0])
        q, report = qa_observation("124", "b" * 40, variant="2")
        state, lease = claim(state, q, "staging_qa", "worker", BASE + timedelta(minutes=1))
        state = finish(state, lease["task_id"], lease["token"], report, BASE + timedelta(minutes=1))
        self.assertEqual([event for event in state["material_events"] if event["kind"] == "blocker"], [old])
        self.assertEqual(old["details"]["product_input_fingerprint"], "same-product")
        self.assertEqual(state["tasks"][lease["task_id"]]["status"], "BLOCKED")
        self.assertEqual(sum(x["attempts"] for x in state["failure_history"].values()), 2)

    def test_new_assertion_url_product_content_and_detailed_browser_failures_are_material(self):
        changes = (
            lambda q, r: r["blockers"][0]["evidence"][0]["pytest"]["cases"][0].update(reason="assert 10 >= 12"),
            lambda q, r: r["blockers"][2]["evidence"][0]["reviewer_proof"]["findings"][0].update(path="https://source.example/other"),
            lambda q, r: r["blockers"][0]["evidence"][1]["context"][0].update(sha256="e" * 64),
            lambda q, r: q["tasks"][0].update(product_input_fingerprint="changed-product"),
            lambda q, r: r["blockers"][3]["evidence"][0]["browser_proof"].update(cases=[{"test": "new assertion", "error": "wrong text"}]),
            lambda q, r: q["tasks"][0]["failure"].update(failure_signature="new-contract-failure"),
            lambda q, r: r["blockers"][0]["evidence"][1]["context"][0].update(startTime="2026-10-11T00:00:00Z"),
        )
        for change in changes:
            with self.subTest(change=change):
                q, report = qa_observation("123", SHA)
                state, lease = claim({}, q, "staging_qa", "worker", BASE)
                state = finish(state, lease["task_id"], lease["token"], report, BASE)
                q, report = qa_observation("124", "b" * 40, variant="2")
                change(q, report)
                state, lease = claim(state, q, "staging_qa", "worker", BASE + timedelta(minutes=1))
                state = finish(state, lease["task_id"], lease["token"], report, BASE + timedelta(minutes=1))
                self.assertEqual(sum(event["kind"] == "blocker" for event in state["material_events"]), 2)

    def test_asserted_and_publication_iso_dates_remain_meaningful_blocker_evidence(self):
        q, report = qa_observation("123", SHA)
        case = report["blockers"][0]["evidence"][0]["pytest"]["cases"][0]
        case.update(reason="assert actual == '2026-10-10T00:00:00Z'", publication_date="2026-10-10T00:00:00Z")
        state, lease = claim({}, q, "staging_qa", "worker", BASE)
        state = finish(state, lease["task_id"], lease["token"], report, BASE)
        q, report = qa_observation("124", "b" * 40, variant="2")
        report["blockers"][0]["evidence"][0]["pytest"]["cases"][0].update(
            reason="assert actual == '2026-10-11T00:00:00Z'", publication_date="2026-10-11T00:00:00Z")
        state, lease = claim(state, q, "staging_qa", "worker", BASE + timedelta(minutes=1))
        state = finish(state, lease["task_id"], lease["token"], report, BASE + timedelta(minutes=1))
        self.assertEqual(sum(event["kind"] == "blocker" for event in state["material_events"]), 2)

    def test_legacy_transport_duplicate_correction_preserves_raw_and_repairs_watch_and_transition(self):
        state = legacy_qa_duplicate_state()
        original = deepcopy(state)
        at = BASE + timedelta(minutes=2)
        corrected = reconcile(state, {"tasks": []}, at)
        self.assertEqual(state, original)
        self.assertEqual(corrected["material_events"], original["material_events"])
        self.assertEqual([x["id"] for x in effective_material_events(corrected)], ["legacy-123"])
        self.assertEqual(len(corrected["material_event_corrections"]), 1)
        self.assertEqual(corrected["material_event_corrections"][0]["event_id"], "legacy-124")
        self.assertEqual([x["event_id"] for x in corrected["pending_transitions"]], ["legacy-123"])
        task = corrected["tasks"]["staging_qa_failed_run_124"]
        self.assertNotIn("material_progress_at", task)
        self.assertEqual(task["material_watch_started_at"], original["lease_events"][1]["at"])
        self.assertEqual(reconcile(corrected, {"tasks": []}, at + timedelta(minutes=1)), corrected)
        result = evaluate_acceptance(corrected, at, wall_now=at)
        self.assertEqual(result["metrics"]["material_event_count"], 1)

    def test_legacy_correction_requires_exact_terminal_binding_and_meaningful_equal_evidence(self):
        for mutate in (
                lambda state: state["tasks"]["staging_qa_failed_run_124"].update(product_input_fingerprint="different"),
                lambda state: state["tasks"]["staging_qa_failed_run_124"].update(status="READY"),
                lambda state: state["tasks"]["staging_qa_failed_run_124"]["failure"].update(head_sha="c" * 40)):
            state = legacy_qa_duplicate_state()
            mutate(state)
            corrected = reconcile(state, {"tasks": []}, BASE + timedelta(minutes=2))
            self.assertEqual(len(effective_material_events(corrected)), 2)
            self.assertEqual(corrected["material_event_corrections"], [])

    def test_frozen_correction_survives_task_movement_but_tampered_raw_event_does_not(self):
        state = reconcile(legacy_qa_duplicate_state(), {"tasks": []}, BASE + timedelta(minutes=2))
        state["tasks"]["staging_qa_failed_run_123"].update(product_input_fingerprint="future-product", failure=None)
        self.assertEqual(len(effective_material_events(state)), 1)
        state["material_events"][1]["details"]["blockers"][0]["evidence"][0]["pytest"]["cases"][0]["reason"] = "new assertion"
        self.assertEqual(len(effective_material_events(state)), 2)

    def test_historical_correction_preserves_real_transition_and_its_material_baseline(self):
        state = legacy_qa_duplicate_state()
        tid = "staging_qa_failed_run_124"
        at = (BASE + timedelta(seconds=30)).isoformat().replace("+00:00", "Z")
        transition = {"id": "real-transition", "kind": "transition", "family": "staging_qa",
            "task_id": tid, "at": at, "details": {"independent": True, "from_task_id": PUBLIC}}
        state["material_events"].insert(1, transition)
        corrected = reconcile(state, {"tasks": []}, BASE + timedelta(minutes=2))
        self.assertEqual([event["id"] for event in effective_material_events(corrected)], ["legacy-123", "real-transition"])
        self.assertEqual(corrected["tasks"][tid]["material_progress_at"], at)
        self.assertEqual(corrected["tasks"][tid]["material_watch_started_at"], at)
        self.assertEqual(corrected["tasks"][tid]["recovery_episode"], "real-transition")

    def test_invalid_correction_cannot_remove_material_evidence(self):
        valid = reconcile(legacy_qa_duplicate_state(), {"tasks": []}, BASE + timedelta(minutes=2))
        for mutation in (
                {"bindings": "invalid"}, {"bindings": [None, None]}, {"bindings": []},
                {"event_sha256": "wrong"}, {"retained_event_sha256": "wrong"},
                {"canonical_signature": "wrong"}, {"product_input_fingerprint": "wrong"},
                {"retained_event_id": "legacy-124"}, {"kind": "unverified_external_assertion"}):
            with self.subTest(mutation=mutation):
                state = deepcopy(valid)
                state["material_event_corrections"][0].update(mutation)
                self.assertEqual(len(effective_material_events(state)), 2)

    def test_reducers_do_not_mutate_inputs(self):
        q = queue()
        original = deepcopy(q)
        initial = {}
        state, lease = claim(initial, q, "media", "worker-1", BASE)
        self.assertEqual(q, original)
        self.assertEqual(initial, {})
        preserved = deepcopy(state)
        heartbeat(state, MEDIA, lease["token"], BASE + timedelta(seconds=60))
        self.assertEqual(state, preserved)

    def test_parallel_family_claims_and_same_family_exclusion(self):
        q = queue()
        state, first = claim({}, q, "media", "one", BASE)
        state, duplicate = claim(state, q, "media", "one", BASE)
        self.assertIsNone(duplicate)
        state, other = claim(state, q, "public_data", "two", BASE)
        self.assertIsNotNone(first)
        self.assertIsNotNone(other)
        self.assertEqual(len(state["material_events"]), 0)
        self.assertEqual(len(state["lease_events"]), 2)

    def test_pickup_and_heartbeat_are_not_material_progress(self):
        q = queue("media")
        state, lease = claim({}, q, "media", "worker", BASE)
        state = heartbeat(state, MEDIA, lease["token"], BASE + timedelta(minutes=1))
        self.assertEqual(state["material_events"], [])
        self.assertNotIn("material_progress_at", state["tasks"][MEDIA])

    def test_expiration_rejects_late_heartbeat_and_finish(self):
        state, lease = claim({}, queue("media"), "media", "worker", BASE)
        expired = BASE + timedelta(minutes=10)
        with self.assertRaises(LeaseError):
            heartbeat(state, MEDIA, lease["token"], expired)
        with self.assertRaises(LeaseError):
            finish(state, MEDIA, lease["token"], mutation(), expired)

    def test_reclaim_fences_late_old_worker_even_with_same_owner(self):
        q = queue("media")
        state, old = claim({}, q, "media", "worker", BASE)
        later = BASE + timedelta(minutes=11)
        state, new = claim(state, q, "media", "worker", later)
        self.assertNotEqual(old["token"], new["token"])
        self.assertGreater(new["fence"], old["fence"])
        with self.assertRaises(LeaseError):
            finish(state, MEDIA, old["token"], blocked(), later)
        with self.assertRaises(LeaseError):
            heartbeat(state, MEDIA, old["token"], later)
        self.assertEqual(len(state["material_events"]), 0)

    def test_heartbeats_cannot_hide_thirty_minute_material_stall(self):
        q = queue("media")
        state, lease = claim({}, q, "media", "worker", BASE)
        for minute in range(1, 30):
            state = heartbeat(state, MEDIA, lease["token"], BASE + timedelta(minutes=minute))
        at_stall = BASE + timedelta(minutes=30)
        with self.assertRaises(LeaseError):
            heartbeat(state, MEDIA, lease["token"], at_stall)
        state = reconcile(state, q, at_stall)
        self.assertEqual(state["tasks"][MEDIA]["status"], "STALLED")
        self.assertEqual(state["tasks"][MEDIA]["reason"], "no_material_progress_30m")
        self.assertEqual(state["material_events"], [])

    def test_verified_twenty_minute_work_does_not_emit_stall_or_recovery_blocker(self):
        q = queue("media")
        state, lease = claim({}, q, "media", "worker", BASE)
        for minute in range(1, 21):
            state = heartbeat(state, MEDIA, lease["token"], BASE + timedelta(minutes=minute))
        state = finish(state, MEDIA, lease["token"], mutation(), BASE + timedelta(minutes=20))
        state, lease = claim(state, q, "media", "worker", BASE + timedelta(minutes=21))
        for minute in range(22, 41):
            state = heartbeat(state, MEDIA, lease["token"], BASE + timedelta(minutes=minute))
        state = finish(state, MEDIA, lease["token"], mutation(candidate_commit="c" * 40,
            before_hash="2" * 64, after_hash="3" * 64), BASE + timedelta(minutes=40))
        self.assertEqual([event["kind"] for event in state["material_events"]], ["mutation", "mutation"])
        self.assertFalse(any(event["kind"] == "stalled" for event in state["lease_events"]))
        self.assertEqual(state["tasks"][MEDIA]["recovery_reclaims"], 0)

    def test_missing_heartbeat_stalls_before_ten_minute_lease(self):
        q = queue("media")
        state, _ = claim({}, q, "media", "worker", BASE)
        state, candidates = plan(state, q, BASE + timedelta(minutes=3))
        self.assertEqual(state["tasks"][MEDIA]["status"], "STALLED")
        self.assertIn("media", candidates)

    def test_ready_without_pickup_stalls_after_thirty_minutes_without_material_credit(self):
        q = queue("media", "public_data")
        state, candidates = plan({}, q, BASE)
        self.assertEqual(state["tasks"][MEDIA]["status"], "READY")
        self.assertIn("media", candidates)
        started = state["tasks"][MEDIA]["pickup_ready_since"]
        state, _ = plan(state, q, BASE + timedelta(minutes=29, seconds=59))
        self.assertEqual(state["tasks"][MEDIA]["status"], "READY")
        self.assertEqual(state["tasks"][MEDIA]["pickup_ready_since"], started)
        state, candidates = plan(state, q, BASE + timedelta(minutes=30))
        self.assertEqual(state["tasks"][MEDIA]["status"], "STALLED")
        self.assertEqual(state["tasks"][MEDIA]["reason"], "no_pickup_30m")
        self.assertEqual(state["material_events"], [])
        self.assertFalse(any(event["kind"] == "pickup" for event in state["lease_events"]))
        self.assertIn("media", candidates)
        self.assertIn("public_data", candidates)

    def test_unmet_dependency_does_not_start_no_pickup_watch_until_actionable(self):
        q = queue("media", "public_data")
        media = next(task for task in q["tasks"] if task["id"] == MEDIA)
        public = next(task for task in q["tasks"] if task["id"] == PUBLIC)
        media["depends_on"] = [PUBLIC]
        state, candidates = plan({}, q, BASE)
        self.assertNotIn("media", candidates)
        self.assertFalse(state["tasks"][MEDIA].get("pickup_ready_since"))
        released = BASE + timedelta(minutes=40)
        state, candidates = plan(state, q, released)
        self.assertEqual(state["tasks"][MEDIA]["status"], "READY")
        self.assertNotIn("media", candidates)
        self.assertFalse(state["tasks"][MEDIA].get("pickup_ready_since"))
        public["status"] = "validated"
        state, candidates = plan(state, q, released)
        self.assertIn("media", candidates)
        ready_since = state["tasks"][MEDIA]["pickup_ready_since"]
        self.assertEqual(datetime.fromisoformat(ready_since.replace("Z", "+00:00")), released)
        state, _ = plan(state, q, released + timedelta(minutes=29, seconds=59))
        self.assertEqual(state["tasks"][MEDIA]["status"], "READY")
        state, candidates = plan(state, q, released + timedelta(minutes=30))
        self.assertEqual(state["tasks"][MEDIA]["status"], "STALLED")
        self.assertEqual(state["tasks"][MEDIA]["reason"], "no_pickup_30m")
        self.assertIn("media", candidates)
        self.assertEqual(state["material_events"], [])

    def test_reclaims_preserve_absolute_material_watch_and_exhaust_without_blocking_other_family(self):
        q = queue("media", "public_data")
        next(task for task in q["tasks"] if task["id"] == MEDIA)["input_fingerprint"] = "unchanged-media-scope"
        state, first = claim({}, q, "media", "worker-0", BASE)
        baseline = state["tasks"][MEDIA]["material_watch_started_at"]
        previous = first
        for attempt, minute in enumerate((11, 22, 33), start=1):
            at = BASE + timedelta(minutes=minute)
            state, lease = claim(state, q, "media", "worker-" + str(attempt), at)
            self.assertIsNotNone(lease)
            self.assertNotEqual(lease["token"], previous["token"])
            self.assertGreater(lease["fence"], previous["fence"])
            self.assertEqual(state["tasks"][MEDIA]["material_watch_started_at"], baseline)
            self.assertEqual(state["tasks"][MEDIA]["recovery_reclaims"], attempt)
            self.assertEqual(state["material_events"], [])
            previous = lease
        # Heartbeats extend ownership but cannot extend the recovery grace.
        for minute in range(34, 43):
            state = heartbeat(state, MEDIA, previous["token"], BASE + timedelta(minutes=minute))
            self.assertEqual(state["tasks"][MEDIA]["material_watch_started_at"], baseline)
        exhausted = BASE + timedelta(minutes=43)
        with self.assertRaises(LeaseError):
            heartbeat(state, MEDIA, previous["token"], exhausted)
        state = reconcile(state, q, exhausted)
        self.assertEqual(state["tasks"][MEDIA]["status"], "STALLED")
        self.assertEqual(state["material_events"], [])
        episode = state["tasks"][MEDIA]["recovery_episode"]
        input_fingerprint = state["tasks"][MEDIA]["input_fingerprint"]
        state, candidates = plan(state, q, exhausted)
        self.assertEqual(state["tasks"][MEDIA]["status"], "BLOCKED")
        self.assertNotIn("media", candidates)
        self.assertIn("public_data", candidates)
        blocker = state["tasks"][MEDIA]["blocker"]
        self.assertEqual(blocker["kind"], "stall_recovery_budget")
        self.assertIn("recovery_budget_exhausted", blocker["fingerprint"])
        self.assertEqual(blocker["reason"], "Three lease recovery pickups without material progress are exhausted.")
        self.assertFalse(blocker["human_required"])
        self.assertEqual(len(blocker["evidence"]), 1)
        evidence = blocker["evidence"][0]
        self.assertEqual(evidence["task_id"], MEDIA)
        self.assertEqual(evidence["recovery_episode"], episode)
        self.assertEqual(evidence["recovery_reclaims"], 3)
        self.assertEqual(evidence["input_fingerprint"], input_fingerprint)
        self.assertEqual(evidence["material_watch_started_at"], baseline)
        self.assertEqual(len(evidence["stalled_leases"]), 4)
        self.assertTrue(all(event["fenced_token"] for event in evidence["stalled_leases"]))
        self.assertEqual([event["kind"] for event in state["material_events"]], ["blocker"])
        again, denied = claim(state, q, "media", "worker-4", exhausted + timedelta(minutes=1))
        self.assertIsNone(denied)
        self.assertEqual(again["material_events"], state["material_events"])
        q["input_sha"] = "c" * 40
        again, denied = claim(again, q, "media", "worker-after-unrelated-staging", exhausted + timedelta(minutes=2))
        self.assertIsNone(denied)
        self.assertEqual(again["material_events"], state["material_events"])

    def test_missing_heartbeat_reclaims_preserve_absolute_watch_across_generations(self):
        q = queue("media")
        state, _ = claim({}, q, "media", "worker-0", BASE)
        baseline = state["tasks"][MEDIA]["material_watch_started_at"]
        for attempt, minute in enumerate((3, 6, 9), start=1):
            state, lease = claim(state, q, "media", "worker-" + str(attempt),
                                 BASE + timedelta(minutes=minute))
            self.assertIsNotNone(lease)
            self.assertEqual(state["tasks"][MEDIA]["recovery_reclaims"], attempt)
            self.assertEqual(state["tasks"][MEDIA]["material_watch_started_at"], baseline)
            self.assertEqual(state["material_events"], [])
        state = reconcile(state, q, BASE + timedelta(minutes=12))
        self.assertEqual(state["tasks"][MEDIA]["status"], "STALLED")
        self.assertEqual(state["material_events"], [])
        state, denied = claim(state, q, "media", "worker-4", BASE + timedelta(minutes=12))
        self.assertIsNone(denied)
        self.assertEqual(state["tasks"][MEDIA]["status"], "BLOCKED")
        self.assertEqual([event["kind"] for event in state["material_events"]], ["blocker"])

    def test_verified_mutation_resets_absolute_watch_and_recovery_episode(self):
        q = queue("media")
        state, _ = claim({}, q, "media", "worker-0", BASE)
        for attempt, minute in enumerate((11, 22), start=1):
            state, lease = claim(state, q, "media", "worker-" + str(attempt),
                                 BASE + timedelta(minutes=minute))
        previous_episode = state["tasks"][MEDIA]["recovery_episode"]
        repaired_at = BASE + timedelta(minutes=23)
        state = finish(state, MEDIA, lease["token"], mutation(), repaired_at)
        task = state["tasks"][MEDIA]
        self.assertEqual(task["status"], "READY")
        self.assertEqual(task["recovery_reclaims"], 0)
        self.assertNotEqual(task["recovery_episode"], previous_episode)
        self.assertEqual(datetime.fromisoformat(task["material_watch_started_at"].replace("Z", "+00:00")),
                         repaired_at)
        self.assertEqual([event["kind"] for event in state["material_events"]], ["mutation"])
        state, lease = claim(state, q, "media", "worker-after-repair", repaired_at)
        state, new = claim(state, q, "media", "worker-after-expiry", BASE + timedelta(minutes=34))
        self.assertIsNotNone(new)
        self.assertEqual(state["tasks"][MEDIA]["recovery_reclaims"], 1)
        self.assertEqual(datetime.fromisoformat(state["tasks"][MEDIA]["material_watch_started_at"].replace("Z", "+00:00")),
                         repaired_at)
        self.assertEqual([event["kind"] for event in state["material_events"]], ["mutation"])

    def test_rotating_audit_fingerprints_cannot_reset_absolute_material_watch(self):
        q = queue("media")
        state = {}
        baseline = None
        for minute in range(0, 30, 5):
            at = BASE + timedelta(minutes=minute)
            state, lease = claim(state, q, "media", "worker-" + str(minute), at)
            self.assertIsNotNone(lease)
            if baseline is None:
                baseline = state["tasks"][MEDIA]["material_watch_started_at"]
            state = finish(state, MEDIA, lease["token"], {
                "status": "SUCCESS", "audit_fingerprint": "different-observation-" + str(minute)}, at)
            self.assertEqual(state["tasks"][MEDIA]["status"], "READY")
            self.assertEqual(state["tasks"][MEDIA]["material_watch_started_at"], baseline)
            self.assertEqual(state["tasks"][MEDIA]["recovery_reclaims"], 0)
            self.assertEqual(state["material_events"], [])
        at_stall = BASE + timedelta(minutes=30)
        state, candidates = plan(state, q, at_stall)
        self.assertEqual(state["tasks"][MEDIA]["status"], "STALLED")
        self.assertEqual(state["tasks"][MEDIA]["reason"], "no_material_progress_30m")
        self.assertIn("media", candidates)
        self.assertEqual(state["material_events"], [])
        state, recovery = claim(state, q, "media", "recovery-worker", at_stall)
        self.assertIsNotNone(recovery)
        self.assertEqual(state["tasks"][MEDIA]["recovery_reclaims"], 1)
        self.assertEqual(state["tasks"][MEDIA]["material_watch_started_at"], baseline)

    def test_queue_approval_revocation_fences_worker(self):
        q = queue("media")
        state, lease = claim({}, q, "media", "worker", BASE)
        q["tasks"][0]["status"] = "paused"
        state = reconcile(state, q, BASE + timedelta(seconds=1))
        self.assertEqual(state["tasks"][MEDIA]["status"], "REVOKED")
        with self.assertRaises(LeaseError):
            finish(state, MEDIA, lease["token"], mutation(), BASE + timedelta(seconds=2))

    def test_unrelated_staging_sha_does_not_revoke_running_parallel_lease(self):
        q = queue("media")
        state, lease = claim({}, q, "media", "worker", BASE)
        q["input_sha"] = "c" * 40
        state = reconcile(state, q, BASE + timedelta(seconds=1))
        self.assertEqual(state["tasks"][MEDIA]["input_sha"], SHA)
        self.assertEqual(state["tasks"][MEDIA]["lease"]["token"], lease["token"])
        state = finish(state, MEDIA, lease["token"], mutation(), BASE + timedelta(seconds=2))
        state = reconcile(state, q, BASE + timedelta(seconds=3))
        self.assertEqual(state["tasks"][MEDIA]["input_sha"], "c" * 40)

    def test_relevant_evidence_change_fences_running_worker(self):
        q = queue("media")
        state, lease = claim({}, q, "media", "worker", BASE)
        q["tasks"][0]["evidence_revision"] = "v2"
        state = reconcile(state, q, BASE + timedelta(seconds=1))
        self.assertEqual(state["tasks"][MEDIA]["status"], "READY")
        with self.assertRaises(LeaseError):
            heartbeat(state, MEDIA, lease["token"], BASE + timedelta(seconds=2))

    def test_unsupported_approved_task_is_blocked_not_completed(self):
        q = {"tasks": [{"id": "unknown_product_task", "status": "approved"}]}
        state, candidates = plan({}, q, BASE)
        self.assertEqual(candidates, {})
        self.assertEqual(state["tasks"]["unknown_product_task"]["status"], "BLOCKED")
        self.assertIn("unsupported_executor", state["tasks"]["unknown_product_task"]["blocker"]["fingerprint"])
        second = reconcile(state, q, BASE + timedelta(minutes=5))
        self.assertEqual(len(second["material_events"]), 1)

    def test_staging_qa_requires_real_failed_run_metadata(self):
        q = queue("media")
        q["tasks"].append({"id": "staging_qa_failed_run_123", "family": "staging_qa",
                           "status": "approved", "failure": failure()})
        state, candidates = plan({}, q, BASE)
        self.assertIn("media", candidates)
        self.assertIn("staging_qa", candidates)
        q["tasks"][-1]["failure"]["conclusion"] = "success"
        state, candidates = plan({}, q, BASE)
        self.assertNotIn("staging_qa", candidates)
        self.assertEqual(state["tasks"]["staging_qa_failed_run_123"]["status"], "BLOCKED")

    def test_editorial_dependency_is_not_bypassed_by_blocked_parent(self):
        parent = "source_audit_issue5_iteration1_recovery_2026_10_09"
        q = queue("media")
        q["tasks"] += [{"id": parent, "status": "in_progress"},
            {"id": EDITORIAL_TASK, "status": "in_progress", "depends_on": [parent]}]
        state, candidates = plan({}, q, BASE)
        self.assertNotIn("editorial", candidates)
        self.assertIn("media", candidates)
        q["tasks"][-2]["status"] = "validated"
        _, candidates = plan(state, q, BASE)
        self.assertIn("editorial", candidates)

    def test_independent_editorial_subtask_does_not_close_parent(self):
        q = queue("media")
        q["tasks"] += [{"id": EDITORIAL_TASK, "status": "in_progress", "depends_on": [MEDIA]},
                       {"id": EDITORIAL_REPAIR_TASK, "status": "approved", "depends_on": [],
                        "provenance": {"parent_task_id": EDITORIAL_TASK}}]
        state, lease = claim({}, q, "editorial", "worker", BASE)
        self.assertEqual(lease["task_id"], EDITORIAL_REPAIR_TASK)
        state = finish(state, EDITORIAL_REPAIR_TASK, lease["token"], passed(EDITORIAL_REPAIR_TASK), BASE)
        self.assertEqual(state["tasks"][EDITORIAL_REPAIR_TASK]["status"], "CLOSED")
        self.assertEqual(state["tasks"][EDITORIAL_TASK]["status"], "READY")

    def test_queue_blocked_by_revokes_lease_and_removal_releases_task(self):
        q = queue("media")
        state, lease = claim({}, q, "media", "worker", BASE)
        q["tasks"][0]["blocked_by"] = ["legal_review"]
        state, candidates = plan(state, q, BASE + timedelta(seconds=1))
        self.assertNotIn("media", candidates)
        with self.assertRaises(LeaseError):
            heartbeat(state, MEDIA, lease["token"], BASE + timedelta(seconds=2))
        q["tasks"][0]["blocked_by"] = []
        _, candidates = plan(state, q, BASE + timedelta(seconds=3))
        self.assertIn("media", candidates)

    def test_blocker_leaves_independent_families_available(self):
        q = queue()
        state, lease = claim({}, q, "media", "worker", BASE)
        state = finish(state, MEDIA, lease["token"], blocked(), BASE + timedelta(seconds=1))
        state, candidates = plan(state, q, BASE + timedelta(seconds=2))
        self.assertNotIn("media", candidates)
        self.assertEqual(set(candidates), {"public_data", "fiscalization", "mutualities"})

    def test_three_identical_audits_block_without_crediting_success(self):
        q = queue("media")
        state = {}
        for attempt in range(3):
            at = BASE + timedelta(minutes=attempt)
            state, lease = claim(state, q, "media", "worker", at)
            state = finish(state, MEDIA, lease["token"], {"status": "SUCCESS",
                "audit_fingerprint": "same-findings", "generated_at": str(at)}, at)
        self.assertEqual(state["tasks"][MEDIA]["status"], "BLOCKED")
        self.assertEqual([e["kind"] for e in state["material_events"]], ["blocker"])
        state, lease = claim(state, q, "media", "worker", BASE + timedelta(minutes=4))
        self.assertIsNone(lease)
        q["tasks"][0]["evidence_revision"] = "changed-proof"
        state, lease = claim(state, q, "media", "worker", BASE + timedelta(minutes=5))
        self.assertIsNotNone(lease)

    def test_observation_timestamp_changes_do_not_reopen_auditor_loop(self):
        q = queue("media")
        q["tasks"][0].pop("evidence_revision")
        q["tasks"][0]["independent_review"] = {"artifact": "audit.json", "reviewed_at": "old"}
        state = {}
        for attempt in range(3):
            state, lease = claim(state, q, "media", "worker", BASE + timedelta(minutes=attempt))
            state = finish(state, MEDIA, lease["token"], {"status": "SUCCESS"},
                           BASE + timedelta(minutes=attempt))
        q["tasks"][0]["independent_review"]["reviewed_at"] = "new"
        state, lease = claim(state, q, "media", "worker", BASE + timedelta(minutes=4))
        self.assertIsNone(lease)

    def test_same_blocker_not_new_material_after_unrelated_input_change(self):
        q = queue("media")
        state, lease = claim({}, q, "media", "worker", BASE)
        state = finish(state, MEDIA, lease["token"], blocked(), BASE)
        q["input_sha"] = "c" * 40
        state, lease = claim(state, q, "media", "worker", BASE + timedelta(minutes=1))
        state = finish(state, MEDIA, lease["token"], blocked(), BASE + timedelta(minutes=1))
        self.assertEqual(len(state["material_events"]), 1)
        q["input_sha"] = "d" * 40
        state, lease = claim(state, q, "media", "worker", BASE + timedelta(minutes=2))
        state = finish(state, MEDIA, lease["token"], blocked(evidence=[{"http_status": 503}]),
                       BASE + timedelta(minutes=2))
        self.assertEqual(len(state["material_events"]), 2)

    def test_scoped_blocked_task_ignores_repeated_global_heads_but_tracks_latest_observation(self):
        q = queue("media")
        q["tasks"][0]["input_fingerprint"] = "unchanged-media-inputs"
        state, lease = claim({}, q, "media", "worker", BASE)
        state = finish(state, MEDIA, lease["token"], blocked(), BASE)
        original = deepcopy(state)
        for minute, revision in enumerate(("b" * 40, "c" * 40, "d" * 40), start=1):
            q["input_sha"] = revision
            state, denied = claim(state, q, "media", "unnecessary-audit-" + str(minute),
                                  BASE + timedelta(minutes=minute))
            self.assertIsNone(denied)
            task = state["tasks"][MEDIA]
            self.assertEqual(task["status"], "BLOCKED")
            self.assertEqual(task["input_sha"], revision)
            self.assertEqual(task["evidence_revision"], original["tasks"][MEDIA]["evidence_revision"])
            self.assertEqual(task["audit_counts"], original["tasks"][MEDIA]["audit_counts"])
            self.assertEqual(task.get("last_audit_fingerprint"),
                             original["tasks"][MEDIA].get("last_audit_fingerprint"))
            self.assertEqual(task["attempts"], 1)
            self.assertEqual(state["material_events"], original["material_events"])
            self.assertEqual(state["lease_events"], original["lease_events"])
        q["tasks"][0]["input_fingerprint"] = "changed-media-inputs"
        state, candidates = plan(state, q, BASE + timedelta(minutes=4))
        self.assertEqual(state["tasks"][MEDIA]["status"], "READY")
        self.assertIn("media", candidates)
        self.assertEqual(state["material_events"], original["material_events"])
        state, resumed = claim(state, q, "media", "necessary-repair", BASE + timedelta(minutes=4))
        self.assertIsNotNone(resumed)

    def test_scoped_blocked_task_reopens_when_evidence_changes_without_input_change(self):
        q = queue("media")
        q["tasks"][0]["input_fingerprint"] = "unchanged-media-inputs"
        state, lease = claim({}, q, "media", "worker", BASE)
        state = finish(state, MEDIA, lease["token"], blocked(), BASE)
        original_events = deepcopy(state["material_events"])
        q["tasks"][0]["evidence_revision"] = "new-source-evidence"
        state, candidates = plan(state, q, BASE + timedelta(minutes=1))
        self.assertEqual(state["tasks"][MEDIA]["status"], "READY")
        self.assertEqual(state["tasks"][MEDIA]["input_sha"], SHA)
        self.assertIn("media", candidates)
        self.assertEqual(state["material_events"], original_events)

    def test_new_acceptance_artifact_reopens_scoped_blocker_but_identical_definition_does_not(self):
        q = queue("media")
        task = q["tasks"][0]
        task["input_fingerprint"] = "unchanged-media-inputs"
        state, lease = claim({}, q, "media", "worker", BASE)
        state = finish(state, MEDIA, lease["token"], blocked(
            reason="Missing revision-bound source acceptance artifact", fingerprint="missing-acceptance",
            evidence=[{"task_id": MEDIA, "acceptance_artifact": None}]), BASE)
        initial_revision = state["tasks"][MEDIA]["evidence_revision"]
        task["acceptance_artifact"] = {"path": "data/autopilot/source-acceptance.json", "sha256": "1" * 64}
        state, candidates = plan(state, q, BASE + timedelta(minutes=1))
        self.assertEqual(state["tasks"][MEDIA]["status"], "READY")
        self.assertNotEqual(state["tasks"][MEDIA]["evidence_revision"], initial_revision)
        self.assertIn("media", candidates)
        state, lease = claim(state, q, "media", "acceptance-reconciliation", BASE + timedelta(minutes=1))
        self.assertIsNotNone(lease)
        state = finish(state, MEDIA, lease["token"], blocked(
            reason="Source runtime evidence is still incomplete", fingerprint="acceptance-runtime-incomplete",
            evidence=[{"acceptance_artifact": deepcopy(task["acceptance_artifact"])}]),
            BASE + timedelta(minutes=1))
        original = deepcopy(state)
        task["acceptance_artifact"] = deepcopy(task["acceptance_artifact"])
        state, denied = claim(state, q, "media", "repeated-acceptance-audit", BASE + timedelta(minutes=2))
        self.assertIsNone(denied)
        self.assertEqual(state["tasks"][MEDIA]["status"], "BLOCKED")
        self.assertEqual(state["tasks"][MEDIA]["evidence_revision"], original["tasks"][MEDIA]["evidence_revision"])
        self.assertEqual(state["tasks"][MEDIA]["audit_counts"], original["tasks"][MEDIA]["audit_counts"])
        self.assertEqual(state["material_events"], original["material_events"])
        self.assertEqual(state["lease_events"], original["lease_events"])
        task["acceptance_artifact"]["sha256"] = "2" * 64
        state, lease = claim(state, q, "media", "changed-acceptance-reconciliation", BASE + timedelta(minutes=3))
        self.assertIsNotNone(lease)
        self.assertNotEqual(state["tasks"][MEDIA]["evidence_revision"], original["tasks"][MEDIA]["evidence_revision"])
        self.assertEqual(state["material_events"], original["material_events"])

    def test_new_approved_repair_patch_reopens_scoped_blocker_but_identical_patch_does_not(self):
        q = queue("media")
        task = q["tasks"][0]
        task.update(input_fingerprint="unchanged-media-inputs", approved_at=BASE.isoformat())
        state, lease = claim({}, q, "media", "worker", BASE)
        state = finish(state, MEDIA, lease["token"], blocked(
            reason="No approved repair plan is available", fingerprint="missing-repair-plan",
            evidence=[{"task_id": MEDIA, "repair_patch": None}]), BASE)
        initial_revision = state["tasks"][MEDIA]["evidence_revision"]
        task["repair_patch"] = {"schema_version": 1, "replacements": [{
            "path": "src/radar_salud/press_pipeline.py", "sha256": "3" * 64,
            "old": "selector = 'legacy'", "new": "selector = 'modern'"}]}
        state, candidates = plan(state, q, BASE + timedelta(minutes=1))
        self.assertEqual(state["tasks"][MEDIA]["status"], "READY")
        self.assertNotEqual(state["tasks"][MEDIA]["evidence_revision"], initial_revision)
        self.assertIn("media", candidates)
        state, lease = claim(state, q, "media", "approved-repair", BASE + timedelta(minutes=1))
        self.assertIsNotNone(lease)
        state = finish(state, MEDIA, lease["token"], blocked(
            reason="Directed repair still needs scoped runtime evidence", fingerprint="repair-runtime-incomplete",
            evidence=[{"repair_patch": deepcopy(task["repair_patch"])}]), BASE + timedelta(minutes=1))
        original = deepcopy(state)
        task["repair_patch"] = deepcopy(task["repair_patch"])
        state, denied = claim(state, q, "media", "identical-repair-replay", BASE + timedelta(minutes=2))
        self.assertIsNone(denied)
        self.assertEqual(state["tasks"][MEDIA]["status"], "BLOCKED")
        self.assertEqual(state["tasks"][MEDIA]["evidence_revision"], original["tasks"][MEDIA]["evidence_revision"])
        self.assertEqual(state["tasks"][MEDIA]["audit_counts"], original["tasks"][MEDIA]["audit_counts"])
        self.assertEqual(state["material_events"], original["material_events"])
        self.assertEqual(state["lease_events"], original["lease_events"])

    def test_meaningful_dispatch_fields_reopen_with_fixed_token_and_scope_but_identical_values_do_not(self):
        variants = (
            ("executor_family", "media", "public_data"),
            ("sources", ["diario_financiero"], ["diario_financiero", "pulso_latercera"]),
            ("source_urls", ["https://source.example/listing"], ["https://source.example/new-listing"]),
            ("approved_at", BASE.isoformat(), (BASE + timedelta(minutes=1)).isoformat()),
        )
        for field, before, after in variants:
            with self.subTest(field=field):
                q = queue("media")
                task = q["tasks"][0]
                task.update(input_fingerprint="unchanged-media-inputs")
                task[field] = deepcopy(before)
                state, lease = claim({}, q, "media", "worker", BASE)
                state = finish(state, MEDIA, lease["token"], blocked(), BASE)
                original_revision = state["tasks"][MEDIA]["evidence_revision"]
                task[field] = deepcopy(after)
                state, candidates = plan(state, q, BASE + timedelta(minutes=1))
                self.assertEqual(state["tasks"][MEDIA]["status"], "READY")
                self.assertNotEqual(state["tasks"][MEDIA]["evidence_revision"], original_revision)
                self.assertIn("media", candidates)
                state, lease = claim(state, q, "media", "changed-definition", BASE + timedelta(minutes=1))
                self.assertIsNotNone(lease)
                state = finish(state, MEDIA, lease["token"], blocked(), BASE + timedelta(minutes=1))
                original = deepcopy(state)
                task[field] = deepcopy(after)
                state, denied = claim(state, q, "media", "identical-definition", BASE + timedelta(minutes=2))
                self.assertIsNone(denied)
                self.assertEqual(state["tasks"][MEDIA]["status"], "BLOCKED")
                self.assertEqual(state["tasks"][MEDIA]["evidence_revision"],
                                 original["tasks"][MEDIA]["evidence_revision"])
                self.assertEqual(state["material_events"], original["material_events"])
                self.assertEqual(state["lease_events"], original["lease_events"])

    def test_scoped_repeatable_closure_ignores_global_heads_and_reopens_only_on_scope_change(self):
        q = queue("media")
        q["tasks"][0].update(input_fingerprint="unchanged-media-inputs", reopen_on_input_change=True)
        state, lease = claim({}, q, "media", "worker", BASE)
        state = finish(state, MEDIA, lease["token"], passed(), BASE)
        original = deepcopy(state)
        for minute, revision in enumerate(("b" * 40, "c" * 40, "d" * 40), start=1):
            q["input_sha"] = revision
            state, denied = claim(state, q, "media", "unnecessary-repeat-" + str(minute),
                                  BASE + timedelta(minutes=minute))
            self.assertIsNone(denied)
            self.assertEqual(state["tasks"][MEDIA]["status"], "CLOSED")
            self.assertEqual(state["tasks"][MEDIA]["input_sha"], revision)
            self.assertEqual(state["tasks"][MEDIA]["audit_counts"], original["tasks"][MEDIA]["audit_counts"])
            self.assertEqual(state["tasks"][MEDIA]["attempts"], 1)
            self.assertEqual(state["material_events"], original["material_events"])
            self.assertEqual(state["lease_events"], original["lease_events"])
        q["tasks"][0]["input_fingerprint"] = "changed-media-inputs"
        state, candidates = plan(state, q, BASE + timedelta(minutes=4))
        self.assertEqual(state["tasks"][MEDIA]["status"], "READY")
        self.assertIn("media", candidates)
        self.assertEqual(state["material_events"], original["material_events"])

    def test_legacy_unscoped_blocker_treats_global_sha_change_as_relevant(self):
        q = queue("media")
        self.assertNotIn("input_fingerprint", q["tasks"][0])
        state, lease = claim({}, q, "media", "worker", BASE)
        state = finish(state, MEDIA, lease["token"], blocked(), BASE)
        original_events = deepcopy(state["material_events"])
        q["input_sha"] = "b" * 40
        state, resumed = claim(state, q, "media", "legacy-repair", BASE + timedelta(minutes=1))
        self.assertIsNotNone(resumed)
        self.assertEqual(state["tasks"][MEDIA]["input_sha"], "b" * 40)
        self.assertEqual(state["material_events"], original_events)

    def test_scoped_revoked_task_restores_approval_without_requiring_input_change(self):
        q = queue("media")
        q["tasks"][0]["input_fingerprint"] = "unchanged-media-inputs"
        state, old = claim({}, q, "media", "worker", BASE)
        q["tasks"][0]["status"] = "paused"
        state = reconcile(state, q, BASE + timedelta(seconds=1))
        self.assertEqual(state["tasks"][MEDIA]["status"], "REVOKED")
        q["tasks"][0]["status"] = "approved"
        state, restored = claim(state, q, "media", "restored-worker", BASE + timedelta(seconds=2))
        self.assertIsNotNone(restored)
        self.assertNotEqual(restored["token"], old["token"])
        self.assertGreater(restored["fence"], old["fence"])
        self.assertEqual(state["tasks"][MEDIA]["input_sha"], SHA)
        self.assertEqual(state["material_events"], [])

    def test_alias_and_reordering_identical_blockers_cannot_manufacture_progress(self):
        q = queue("media")
        one = blocked(fingerprint="one")["blockers"][0]
        two = blocked(fingerprint="two", evidence=[{"status": 503}])["blockers"][0]
        state, lease = claim({}, q, "media", "worker", BASE)
        state = finish(state, MEDIA, lease["token"], {"status": "BLOCKED", "blocker": one,
                       "blockers": [one, two]}, BASE)
        q["input_sha"] = "c" * 40
        state, lease = claim(state, q, "media", "worker", BASE + timedelta(minutes=1))
        state = finish(state, MEDIA, lease["token"], {"status": "BLOCKED", "blocker": two,
                       "blockers": [two, one]}, BASE + timedelta(minutes=1))
        self.assertEqual(len(state["material_events"]), 1)

    def test_mutation_requires_durable_commit_hashes_and_executed_gates(self):
        state, lease = claim({}, queue("media"), "media", "worker", BASE)
        for invalid in (mutation(candidate_commit=None), mutation(after_hash="1" * 64),
                        mutation(gates=["PASS"]), mutation(validated=False)):
            with self.assertRaises(ReportError):
                finish(state, MEDIA, lease["token"], invalid, BASE)
        state = finish(state, MEDIA, lease["token"], mutation(), BASE)
        self.assertEqual(state["tasks"][MEDIA]["status"], "READY")
        self.assertEqual(state["material_events"][0]["kind"], "mutation")
        self.assertEqual(state["material_events"][0]["details"]["parent_input_sha"], SHA)
        self.assertEqual(state["material_events"][0]["details"]["input_fingerprint"],
                         state["tasks"][MEDIA]["input_fingerprint"])

    def test_isolated_candidate_with_baseline_failure_can_make_durable_progress(self):
        q = queue("media")
        state, lease = claim({}, q, "media", "worker", BASE)
        report = partial()
        state = finish(state, MEDIA, lease["token"], report, BASE)
        self.assertEqual(state["tasks"][MEDIA]["status"], "READY")
        self.assertEqual(state["material_events"][0]["details"]["candidate_scope"], "isolated")
        self.assertNotIn("closure", [event["kind"] for event in state["material_events"]])

    def test_candidate_base_keeps_product_identity_when_executor_scope_is_combined(self):
        q = queue("media")
        q["tasks"][0].update(input_fingerprint="product-and-executor-v1",
            product_input_fingerprint="unchanged-product", executor_fingerprint="executor-v1")
        state, lease = claim({}, q, "media", "worker", BASE)
        state = finish(state, MEDIA, lease["token"], partial(), BASE)
        details = state["material_events"][0]["details"]
        self.assertEqual(details["product_input_fingerprint"], "unchanged-product")
        self.assertEqual(details["executor_fingerprint"], "executor-v1")
        self.assertEqual(details["input_fingerprint"], "product-and-executor-v1")
        self.assertNotIn("closure", [event["kind"] for event in state["material_events"]])

    def test_executor_change_reopens_blocker_and_preserves_product_scope(self):
        q = queue("media")
        q["tasks"][0].update(input_fingerprint="product-and-executor-v1",
            product_input_fingerprint="unchanged-product", executor_fingerprint="executor-v1")
        state, lease = claim({}, q, "media", "worker", BASE)
        state = finish(state, MEDIA, lease["token"], blocked(), BASE)
        signatures = state["tasks"][MEDIA]["blocker_signatures"][:]
        q["tasks"][0].update(input_fingerprint="product-and-executor-v2", executor_fingerprint="executor-v2")
        state = reconcile(state, q, BASE + timedelta(seconds=1))
        self.assertEqual(state["tasks"][MEDIA]["status"], "READY")
        self.assertEqual(state["tasks"][MEDIA]["product_input_fingerprint"], "unchanged-product")
        self.assertEqual(state["tasks"][MEDIA]["blocker_signatures"], signatures)

    def test_partial_candidate_requires_hashed_non_regression_and_live_directed_pass(self):
        report = partial()
        report["family"] = "media"
        self.assertTrue(candidate_validated(report))
        for field, invalid in (("non_regression", "tests unchanged"), ("directed_gates", ["PASS"]),
                               ("live_gate", None), ("candidate_scope", "staging")):
            changed = {**report, field: invalid}
            self.assertFalse(candidate_validated(changed))
        changed = deepcopy(report)
        changed["non_regression"]["candidate_failures"] = ["6" * 64]
        self.assertFalse(candidate_validated(changed))
        changed = deepcopy(report)
        changed["non_regression"]["baseline_gate"].pop("log_sha256")
        self.assertFalse(candidate_validated(changed))
        changed = deepcopy(report)
        changed["non_regression"]["candidate_failures"] = []
        changed["non_regression"]["candidate_gate"]["returncode"] = 0
        self.assertTrue(candidate_validated(changed))

    def test_generic_explicit_approved_executor_family_can_pick_next_task(self):
        q = {"input_sha": SHA, "tasks": [{"id": "source_repair_media_new_scope", "status": "approved",
                                             "executor_family": "media", "depends_on": []}]}
        _, lease = claim({}, q, "media", "worker", BASE)
        self.assertEqual(lease["task_id"], "source_repair_media_new_scope")

    def test_failure_budget_is_shared_across_new_github_run_ids(self):
        q = queue("media")
        state = {}
        for attempt in range(3):
            run_id = str(123 + attempt)
            proof = {**failure(run_id), "failure_signature": "same-test-contract"}
            q["tasks"].append({"id": "staging_qa_failed_run_" + run_id, "family": "staging_qa",
                "status": "approved", "failure": proof, "input_fingerprint": "same-relevant-code"})
            at = BASE + timedelta(minutes=attempt)
            state, lease = claim(state, q, "staging_qa", "worker", at)
            state = finish(state, lease["task_id"], lease["token"], blocked(), at)
        run_id = "126"
        q["tasks"].append({"id": "staging_qa_failed_run_" + run_id, "family": "staging_qa",
            "status": "approved", "failure": {**failure(run_id), "failure_signature": "same-test-contract"},
            "input_fingerprint": "same-relevant-code"})
        state, candidates = plan(state, q, BASE + timedelta(minutes=4))
        self.assertNotIn("staging_qa", candidates)
        self.assertIn("media", candidates)
        # The same real failure is not repeatedly credited as new progress.
        failures = [event for event in state["material_events"] if event["kind"] == "blocker"
                    and event["details"].get("fingerprint") == state["tasks"]["staging_qa_failed_run_123"]["blocker"]["fingerprint"]]
        self.assertEqual(len(failures), 1)
        q["tasks"][-1]["input_fingerprint"] = "repaired-relevant-code"
        _, candidates = plan(state, q, BASE + timedelta(minutes=5))
        self.assertIn("staging_qa", candidates)

    def test_known_source_failure_budget_does_not_reset_on_unrelated_staging_sha(self):
        q = queue("media")
        q["tasks"][0]["input_fingerprint"] = "same-media-parser"
        real = {"kind": "source_runtime", "verified": True, "source_url": "https://source.example/news",
                "failure_signature": "same-request-failure", "trace_path": "trace.json",
                "trace_sha256": "7" * 64, "observed_at": BASE.isoformat()}
        state = {}
        for attempt in range(3):
            q["input_sha"] = str(attempt) * 40
            q["tasks"][0]["evidence_revision"] = "new-directed-repair-evidence-" + str(attempt)
            at = BASE + timedelta(minutes=attempt)
            state, lease = claim(state, q, "media", "worker", at)
            self.assertIsNotNone(lease)
            report = {**blocked(), "real_failure": real, "failure_action": "blocked"}
            state = finish(state, MEDIA, lease["token"], report, at)
        original_events = deepcopy(state["material_events"])
        original_blocker = deepcopy(state["tasks"][MEDIA]["blocker"])
        original_history = deepcopy(state["failure_history"])
        q["input_sha"] = "9" * 40
        state, candidates = plan(state, q, BASE + timedelta(minutes=4))
        self.assertNotIn("media", candidates)
        self.assertEqual(state["tasks"][MEDIA]["status"], "BLOCKED")
        self.assertEqual(state["tasks"][MEDIA]["blocker"], original_blocker)
        self.assertEqual(state["material_events"], original_events)
        self.assertEqual(state["failure_history"], original_history)
        q["tasks"][0]["evidence_revision"] = "genuinely-new-repair-evidence"
        state, candidates = plan(state, q, BASE + timedelta(minutes=5))
        self.assertNotIn("media", candidates)
        self.assertIn("failure_budget_exhausted", state["tasks"][MEDIA]["blocker"]["fingerprint"])
        self.assertEqual(state["failure_history"], original_history)
        self.assertTrue(all(history["attempts"] == 3 for history in state["failure_history"].values()))

    def test_same_candidate_or_unchanged_semantic_result_is_not_new_mutation(self):
        q = queue("media")
        state, lease = claim({}, q, "media", "worker", BASE)
        state = finish(state, MEDIA, lease["token"], mutation(), BASE)
        state, lease = claim(state, q, "media", "worker", BASE + timedelta(minutes=1))
        state = finish(state, MEDIA, lease["token"], mutation(candidate_commit="c" * 40),
                       BASE + timedelta(minutes=1))
        self.assertEqual(len(state["material_events"]), 1)

    def test_pass_requires_hash_bound_explicit_acceptance_artifact(self):
        state, lease = claim({}, queue("media"), "media", "worker", BASE)
        for proof in ([], ["tests green"], [{"verified": True, "path": "fake"}]):
            invalid = passed()
            invalid["acceptance_proof"] = proof
            with self.assertRaises(ReportError):
                finish(state, MEDIA, lease["token"], invalid, BASE)
        report = passed()
        report["acceptance_proof"][0]["candidate_sha"] = "wrong-input"
        with self.assertRaises(ReportError):
            finish(state, MEDIA, lease["token"], report, BASE)
        state = finish(state, MEDIA, lease["token"], passed(), BASE)
        self.assertEqual(state["tasks"][MEDIA]["status"], "CLOSED")

    def test_source_closure_rejects_legacy_generic_proof_without_staging_runtime_binding(self):
        state, lease = claim({}, queue("media"), "media", "worker", BASE)
        legacy = passed()
        proof = legacy["acceptance_proof"][0]
        for field in ("staging_merge_sha", "origin_staging_sha", "runtime_after_merge"):
            proof.pop(field)
        proof["checks"] = ["publication_trace", "editorial_acceptance"]
        with self.assertRaises(ReportError):
            finish(state, MEDIA, lease["token"], legacy, BASE)
        self.assertEqual(state["tasks"][MEDIA]["status"], "RUNNING")
        self.assertEqual(state["material_events"], [])

    def test_source_closure_requires_full_staging_sha_and_identical_hashed_runtime_reference(self):
        state, lease = claim({}, queue("media"), "media", "worker", BASE)
        invalid_proofs = []
        for field, value in (("staging_merge_sha", "b" * 40), ("staging_merge_sha", "abc123"),
                             ("origin_staging_sha", "abc123"), ("runtime_after_merge", []),
                             ("runtime_after_merge", [{"kind": "runtime_after_merge", "path": "run.json"}]),
                             ("runtime_after_merge", [{"kind": "candidate_live", "path": "run.json", "sha256": "9" * 64}])):
            report = passed()
            report["acceptance_proof"][0][field] = value
            invalid_proofs.append(report)
        for field in ("staging_merge_sha", "origin_staging_sha", "runtime_after_merge"):
            report = passed()
            report["acceptance_proof"][0].pop(field)
            invalid_proofs.append(report)
        report = passed()
        report["acceptance_proof"][0]["checks"]["runtime_after_merge_pass"] = False
        invalid_proofs.append(report)
        for change in ({"path": "different-runtime.json"}, {"sha256": "8" * 64},
                       {"kind": "candidate_live"}):
            report = passed()
            report["acceptance_proof"][0]["evidence"][-1].update(change)
            invalid_proofs.append(report)
        for report in invalid_proofs:
            with self.subTest(proof=report["acceptance_proof"][0]):
                with self.assertRaises(ReportError):
                    finish(state, MEDIA, lease["token"], report, BASE)
        self.assertEqual(state["material_events"], [])

    def test_source_closure_carries_actual_last_failure_as_verified_repair(self):
        state, lease = claim({}, queue("media"), "media", "worker", BASE)
        actual = source_failure()
        state["tasks"][MEDIA]["last_failure"] = deepcopy(actual)
        state = finish(state, MEDIA, lease["token"], passed(), BASE)
        self.assertEqual(state["tasks"][MEDIA]["status"], "CLOSED")
        self.assertEqual([event["kind"] for event in state["material_events"]], ["closure"])
        details = state["material_events"][0]["details"]
        self.assertEqual(details["real_failure"], actual)
        self.assertEqual(details["failure_action"], "repaired")
        self.assertEqual(details["acceptance_proof"][0]["staging_merge_sha"], SHA)
        result = evaluate_acceptance(state, BASE, wall_now=BASE)
        self.assertNotIn("real_failure_verified_repair_not_observed", result["reasons"])

    def test_transition_credited_once_after_terminal_to_different_independent_task(self):
        q = queue()
        state, lease = claim({}, q, "media", "worker", BASE)
        state = finish(state, MEDIA, lease["token"], blocked(), BASE)
        state, _ = claim(state, q, "public_data", "worker2", BASE + timedelta(seconds=1))
        state, _ = claim(state, q, "fiscalization", "worker3", BASE + timedelta(seconds=2))
        transitions = [e for e in state["material_events"] if e["kind"] == "transition"]
        self.assertEqual(len(transitions), 1)
        self.assertEqual(transitions[0]["details"]["from_task_id"], MEDIA)
        self.assertEqual(transitions[0]["task_id"], PUBLIC)

    def test_real_failed_run_blocker_carries_recovery_proof(self):
        q = {"input_sha": SHA, "tasks": [{"id": "staging_qa_failed_run_123",
             "status": "approved", "family": "staging_qa", "failure": failure()}]}
        state, lease = claim({}, q, "staging_qa", "worker", BASE)
        state = finish(state, lease["task_id"], lease["token"], blocked(), BASE)
        details = state["material_events"][0]["details"]
        self.assertEqual(details["real_failure"]["run_id"], "123")
        self.assertEqual(details["failure_action"], "blocked")

    def test_partial_staging_candidate_is_material_without_claiming_failed_gate_repaired(self):
        q = {"input_sha": SHA, "tasks": [{"id": "staging_qa_failed_run_123",
             "status": "approved", "family": "staging_qa", "failure": failure()}]}
        state, lease = claim({}, q, "staging_qa", "worker", BASE)
        state = finish(state, lease["task_id"], lease["token"], partial(), BASE)
        event = state["material_events"][0]
        self.assertEqual(event["kind"], "mutation")
        self.assertNotEqual(event["details"].get("failure_action"), "repaired")
        result = evaluate_acceptance(state, BASE, wall_now=BASE)
        self.assertIn("real_failure_verified_repair_not_observed", result["reasons"])

    def test_source_isolated_candidate_keeps_target_bound_progress_without_claiming_staging_repair(self):
        q = queue("media")
        state, lease = claim({}, q, "media", "worker", BASE)
        real = source_failure()
        report = partial()
        report.update(real_failure=real, failure_action="repaired", live_scope=["diario_financiero"])
        for override in ({"live_scope": ["unrelated_source"]}, {"live_gate": None}, {"targeted_validated": False}):
            invalid = {**report, **override}
            if override != {"live_scope": ["unrelated_source"]}:
                with self.assertRaises(ReportError):
                    finish(state, MEDIA, lease["token"], invalid, BASE)
            else:
                unbound = finish(state, MEDIA, lease["token"], invalid, BASE)
                self.assertNotEqual(unbound["material_events"][0]["details"].get("failure_action"), "repaired")
        candidate = finish(state, MEDIA, lease["token"], report, BASE)
        self.assertEqual(candidate["tasks"][MEDIA]["status"], "READY")
        self.assertEqual([event["kind"] for event in candidate["material_events"]], ["mutation"])
        self.assertEqual(candidate["material_events"][0]["details"]["failure_action"], "candidate_failure_resolved")
        self.assertEqual(candidate["material_events"][0]["details"]["real_failure"], real)
        result = evaluate_acceptance(candidate, BASE, wall_now=BASE)
        self.assertIn("real_failure_verified_repair_not_observed", result["reasons"])

    def test_blocked_requires_evidence_and_not_just_reason(self):
        state, lease = claim({}, queue("media"), "media", "worker", BASE)
        for invalid in ({"status": "BLOCKED"}, {"status": "BLOCKED", "blockers": ["error"]},
                        {"status": "BLOCKED", "blockers": [{"fingerprint": "x", "reason": "y"}]}):
            with self.assertRaises(ReportError):
                finish(state, MEDIA, lease["token"], invalid, BASE)


class AcceptanceTests(unittest.TestCase):
    def observed_state(self, mode="live"):
        state = {"acceptance": {"mode": mode, "started_at": BASE.isoformat(),
                                "owner_restarts": [], "owner_prompts": [],
                                "owner_observation": {
                                    "verified": True, "started_at": BASE.isoformat(),
                                    "observed_until": (BASE + timedelta(hours=4)).isoformat(),
                                    "channels": ["github_actions", "owner_prompt_events"],
                                    "evidence": {"path": "data/autopilot/evidence/owner-window.json",
                                                 "sha256": "e" * 64}}},
                 "material_events": [], "lease_events": [{"kind": "pickup", "autonomous": True,
                                                           "at": BASE.isoformat()}]}
        for minute in range(0, 241, 20):
            event = {"kind": "mutation", "at": (BASE + timedelta(minutes=minute)).isoformat(),
                     "details": {}}
            state["material_events"].append(event)
        state["material_events"][1]["details"] = {"real_failure": failure(), "failure_action": "repaired",
                                                "validated": True, "gates": gates()}
        state["material_events"][2]["kind"] = "transition"
        state["material_events"][2]["details"] = {"independent": True}
        return state

    def later_productive_state(self):
        """Offline fixture: actual clock evidence is supplied explicitly."""
        state = self.observed_state()
        original = deepcopy(state["material_events"][:3])
        latest = deepcopy(state["material_events"])
        for event in latest:
            event["at"] = engine._iso(engine._time(event["at"]) + timedelta(hours=6))
        state["material_events"] = original + latest
        state["lease_events"].extend([
            {"kind": "stalled", "at": engine._iso(BASE + timedelta(hours=2))},
            {"kind": "pickup", "autonomous": True, "at": engine._iso(BASE + timedelta(hours=6))}])
        state["acceptance"]["owner_observation"].update(
            started_at=engine._iso(BASE + timedelta(hours=6)),
            observed_until=engine._iso(BASE + timedelta(hours=10)))
        return state

    def test_later_continuous_actual_four_hours_can_qualify_without_resetting_first_pickup(self):
        state = self.later_productive_state()
        before = deepcopy(state)
        end = BASE + timedelta(hours=10)
        result = evaluate_acceptance(state, end, wall_now=end)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["metrics"]["observed_seconds"], 4 * 3600)
        self.assertEqual(result["metrics"]["total_elapsed_seconds"], 10 * 3600)
        self.assertEqual(result["metrics"]["original_started_at"], engine._iso(BASE))
        self.assertEqual(result["metrics"]["window_started_at"], engine._iso(BASE + timedelta(hours=6)))
        self.assertEqual(result["metrics"]["material_event_count"], 13)
        self.assertEqual(result["metrics"]["autonomous_pickups"], 1)
        self.assertEqual(state, before)
        self.assertTrue(any(event["kind"] == "stalled" for event in state["lease_events"]))

    def test_later_window_requires_all_existing_proofs_in_the_actual_window(self):
        end = BASE + timedelta(hours=10)
        cases = (
            ("autonomous_pickup_not_observed", lambda s: s.update(lease_events=s["lease_events"][:2])),
            ("durable_verified_mutation_not_observed", lambda s: s.update(material_events=[e for e in s["material_events"]
                if e["kind"] != "mutation" or engine._time(e["at"]) < BASE + timedelta(hours=6)])),
            ("real_failure_verified_repair_not_observed", lambda s: s["material_events"][4]["details"].pop("failure_action")),
            ("automatic_independent_transition_not_observed", lambda s: s["material_events"][5]["details"].update(independent=False)),
            ("owner_intervention_observation_not_verified", lambda s: s["acceptance"]["owner_observation"].update(
                started_at=engine._iso(BASE + timedelta(hours=6, seconds=1)))),
            ("material_progress_gap_exceeded_30m", lambda s: s.update(material_events=s["material_events"][:6] + s["material_events"][8:])),
        )
        for reason, change in cases:
            with self.subTest(reason=reason):
                state = self.later_productive_state()
                change(state)
                result = evaluate_acceptance(state, end, wall_now=end)
                self.assertEqual(result["status"], "NOT_PROVEN")
                self.assertIn(reason, result["reasons"])

    def test_timestamped_owner_interventions_outside_window_remain_history_without_poisoning_it(self):
        state = self.later_productive_state()
        state["acceptance"]["owner_restarts"] = [{"at": engine._iso(BASE + timedelta(hours=2)), "reason": "initial stall"}]
        state["acceptance"]["owner_prompts"] = [{"timestamp": engine._iso(BASE + timedelta(hours=3)), "prompt": "status"}]
        before = deepcopy(state)
        end = BASE + timedelta(hours=10)
        result = evaluate_acceptance(state, end, wall_now=end)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["metrics"]["owner_restarts"], 0)
        self.assertEqual(result["metrics"]["owner_prompts"], 0)
        self.assertEqual(state, before)
        state["acceptance"]["owner_prompts"].append({"observed_at": engine._iso(BASE + timedelta(hours=9)), "prompt": "status"})
        self.assertIn("owner_restart_or_followup_in_window", evaluate_acceptance(state, end, wall_now=end)["reasons"])

    def test_untimed_malformed_and_future_owner_events_cannot_be_filtered_away(self):
        end = BASE + timedelta(hours=10)
        for record in ("status?", {}, {"at": None}, {"at": "invalid"}, {"at": False},
                       {"at": "2026-10-10T02:00:00"}, {"at": engine._iso(end + timedelta(seconds=1))}):
            with self.subTest(record=record):
                state = self.later_productive_state()
                state["acceptance"]["owner_prompts"] = [record]
                result = evaluate_acceptance(state, end, wall_now=end)
                self.assertEqual(result["status"], "NOT_PROVEN")
                self.assertIn("owner_restart_or_followup_in_window", result["reasons"])

    def test_old_proofs_and_document_clock_cannot_substitute_for_real_later_window(self):
        state = self.observed_state()
        end = BASE + timedelta(hours=10)
        state["acceptance"]["owner_observation"].update(observed_until=engine._iso(end))
        result = evaluate_acceptance(state, end, wall_now=end)
        for reason in ("autonomous_pickup_not_observed", "durable_verified_mutation_not_observed",
                       "real_failure_verified_repair_not_observed", "automatic_independent_transition_not_observed",
                       "material_progress_gap_exceeded_30m"):
            self.assertIn(reason, result["reasons"])
        state["acceptance"]["started_at"] = engine._iso(end - timedelta(hours=4))
        self.assertEqual(evaluate_acceptance(state, end, wall_now=end)["status"], "NOT_PROVEN")
        self.assertIn("observation_time_is_in_the_future", evaluate_acceptance(state, end, wall_now=BASE)["reasons"])

    def test_four_real_hours_with_full_evidence_pass_evaluator(self):
        end = BASE + timedelta(hours=4)
        result = evaluate_acceptance(self.observed_state(), end, wall_now=end)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["metrics"]["max_material_gap_seconds"], 1200)
        self.assertTrue(result["metrics"]["owner_observation_verified"])

    def test_empty_owner_lists_without_observation_do_not_prove_absence(self):
        state = self.observed_state()
        del state["acceptance"]["owner_observation"]
        end = BASE + timedelta(hours=4)
        result = evaluate_acceptance(state, end, wall_now=end)
        self.assertEqual(result["status"], "NOT_PROVEN")
        self.assertEqual(result["reasons"], ["owner_intervention_observation_not_verified"])
        self.assertFalse(result["metrics"]["owner_observation_verified"])

    def test_actions_only_or_unverified_owner_observation_does_not_pass(self):
        end = BASE + timedelta(hours=4)
        for patch in ({"channels": ["github_actions"]},
                      {"channels": ["owner_prompt_events"]},
                      {"channels": "github_actions owner_prompt_events"},
                      {"verified": False}, {"verified": 1}):
            with self.subTest(patch=patch):
                state = self.observed_state()
                state["acceptance"]["owner_observation"].update(patch)
                result = evaluate_acceptance(state, end, wall_now=end)
                self.assertEqual(result["status"], "NOT_PROVEN")
                self.assertIn("owner_intervention_observation_not_verified", result["reasons"])

    def test_owner_observation_must_cover_the_entire_real_window(self):
        end = BASE + timedelta(hours=4)
        for patch in ({"started_at": (BASE + timedelta(seconds=1)).isoformat()},
                      {"observed_until": (end - timedelta(seconds=1)).isoformat()},
                      {"observed_until": (end + timedelta(seconds=1)).isoformat()},
                      {"started_at": (end + timedelta(seconds=1)).isoformat()}):
            with self.subTest(patch=patch):
                state = self.observed_state()
                state["acceptance"]["owner_observation"].update(patch)
                result = evaluate_acceptance(state, end, wall_now=end)
                self.assertEqual(result["status"], "NOT_PROVEN")
                self.assertIn("owner_intervention_observation_not_verified", result["reasons"])

    def test_owner_observation_must_have_immutable_evidence_binding(self):
        end = BASE + timedelta(hours=4)
        for evidence in (None, {},
                         {"path": "data/autopilot/evidence/owner.json", "sha256": "short"},
                         {"path": "data/autopilot/owner_latest.json", "sha256": "e" * 64},
                         {"path": "/data/autopilot/evidence/owner.json", "sha256": "e" * 64},
                         {"path": "data/autopilot/evidence/../owner.json", "sha256": "e" * 64},
                         {"path": "data/autopilot/evidence/", "sha256": "e" * 64},
                         {"path": "data/autopilot/evidence/owner\\window.json", "sha256": "e" * 64}):
            with self.subTest(evidence=evidence):
                state = self.observed_state()
                state["acceptance"]["owner_observation"]["evidence"] = evidence
                result = evaluate_acceptance(state, end, wall_now=end)
                self.assertEqual(result["status"], "NOT_PROVEN")
                self.assertIn("owner_intervention_observation_not_verified", result["reasons"])

    def test_malformed_owner_observation_times_fail_closed(self):
        end = BASE + timedelta(hours=4)
        for patch in ({"started_at": "invalid"}, {"observed_until": None},
                      {"observed_until": "2026-10-10T04:00:00"}):
            with self.subTest(patch=patch):
                state = self.observed_state()
                state["acceptance"]["owner_observation"].update(patch)
                result = evaluate_acceptance(state, end, wall_now=end)
                self.assertEqual(result["status"], "NOT_PROVEN")
                self.assertIn("owner_intervention_observation_not_verified", result["reasons"])

    def test_four_hour_block_only_window_remains_material_but_does_not_pass_stage_a(self):
        end = BASE + timedelta(hours=4)
        state = self.observed_state()
        state["material_events"][1]["kind"] = "blocker"
        state["material_events"][1]["details"] = {"real_failure": failure(), "failure_action": "blocked"}
        result = evaluate_acceptance(state, end, wall_now=end)
        self.assertEqual(result["status"], "NOT_PROVEN")
        self.assertEqual(result["reasons"], ["real_failure_verified_repair_not_observed"])
        self.assertEqual(result["metrics"]["material_event_count"], len(state["material_events"]))

    def test_legacy_partial_staging_repaired_label_does_not_prove_actual_repair(self):
        end = BASE + timedelta(hours=4)
        state = self.observed_state()
        state["material_events"][1]["details"].update(validated=False, gates=partial()["gates"], partial_candidate=True)
        result = evaluate_acceptance(state, end, wall_now=end)
        self.assertIn("real_failure_verified_repair_not_observed", result["reasons"])

    def test_legacy_source_premerge_repaired_events_cannot_pass_stage_a(self):
        end = BASE + timedelta(hours=4)
        for kind in ("mutation", "closure"):
            with self.subTest(kind=kind):
                state = self.observed_state()
                report = partial()
                legacy_proof = passed()["acceptance_proof"][0]
                for field in ("staging_merge_sha", "origin_staging_sha", "runtime_after_merge"):
                    legacy_proof.pop(field)
                state["material_events"][1].update(kind=kind, family="media", task_id=MEDIA,
                    details={**report, "real_failure": source_failure(), "failure_action": "repaired",
                             "live_scope": ["diario_financiero"], "input_sha": SHA,
                             "acceptance_proof": [legacy_proof]})
                result = evaluate_acceptance(state, end, wall_now=end)
                self.assertEqual(result["status"], "NOT_PROVEN")
                self.assertEqual(result["reasons"], ["real_failure_verified_repair_not_observed"])

    def test_actual_isolated_source_candidate_is_material_but_does_not_pass_stage_a(self):
        at = BASE + timedelta(minutes=20)
        control, lease = claim({}, queue("media"), "media", "worker", at)
        report = partial()
        report.update(real_failure=source_failure(), failure_action="repaired", live_scope=["diario_financiero"])
        control = finish(control, MEDIA, lease["token"], report, at)
        event = control["material_events"][0]
        self.assertEqual(event["kind"], "mutation")
        self.assertEqual(event["details"]["failure_action"], "candidate_failure_resolved")
        state = self.observed_state()
        state["material_events"][1] = event
        end = BASE + timedelta(hours=4)
        result = evaluate_acceptance(state, end, wall_now=end)
        self.assertEqual(result["status"], "NOT_PROVEN")
        self.assertEqual(result["reasons"], ["real_failure_verified_repair_not_observed"])
        self.assertEqual(result["metrics"]["material_event_count"], len(state["material_events"]))

    def test_actual_postmerge_source_closure_can_satisfy_stage_a_repair_requirement(self):
        at = BASE + timedelta(minutes=20)
        control, lease = claim({}, queue("media"), "media", "worker", at)
        control["tasks"][MEDIA]["last_failure"] = source_failure()
        control = finish(control, MEDIA, lease["token"], passed(), at)
        event = control["material_events"][0]
        self.assertEqual(event["kind"], "closure")
        self.assertEqual(event["details"]["failure_action"], "repaired")
        self.assertEqual(event["details"]["real_failure"], source_failure())
        state = self.observed_state()
        state["material_events"][1] = event
        end = BASE + timedelta(hours=4)
        result = evaluate_acceptance(state, end, wall_now=end)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["reasons"], [])

    def test_simulation_never_satisfies_live_acceptance(self):
        end = BASE + timedelta(hours=4)
        result = evaluate_acceptance(self.observed_state("simulation"), end, wall_now=end)
        self.assertIn("simulation_is_not_live_acceptance", result["reasons"])

    def test_future_clock_cannot_fake_four_elapsed_hours(self):
        result = evaluate_acceptance(self.observed_state(), BASE + timedelta(hours=4), wall_now=BASE)
        self.assertIn("four_real_wall_hours_not_observed", result["reasons"])
        self.assertIn("observation_time_is_in_the_future", result["reasons"])

    def test_owner_followup_or_material_gap_invalidates_acceptance(self):
        end = BASE + timedelta(hours=4)
        state = self.observed_state()
        state["acceptance"]["owner_prompts"] = ["novedades?"]
        state["material_events"] = state["material_events"][:3]
        result = evaluate_acceptance(state, end, wall_now=end)
        self.assertIn("owner_restart_or_followup_in_window", result["reasons"])
        self.assertIn("material_progress_gap_exceeded_30m", result["reasons"])

    def test_heartbeat_success_only_does_not_prove_acceptance(self):
        end = BASE + timedelta(hours=4)
        state = self.observed_state()
        state["material_events"] = []
        result = evaluate_acceptance(state, end, wall_now=end)
        self.assertIn("durable_verified_mutation_not_observed", result["reasons"])
        self.assertIn("real_failure_verified_repair_not_observed", result["reasons"])
        self.assertIn("automatic_independent_transition_not_observed", result["reasons"])


if __name__ == "__main__":
    unittest.main()
