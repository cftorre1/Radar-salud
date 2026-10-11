"""Execute independent staging diagnostics, safe repairs and fail-closed acceptance.

This script never pushes. The controller owns leases, commits and continuation.
Successful diagnostics are observations, not publication or task closure evidence.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
FAMILIES = {
    "media": ("diario_financiero", "pulso_latercera"),
    "public_data": ("fonasa", "fonasa_datos_abiertos", "isp_anamed", "isp_surveillance", "deis"),
    "fiscalization": ("superintendencia_fiscalizacion", "suseso_fiscalizacion"),
    "mutualities": ("clinicas_achs_salud", "achs_seguro_laboral", "mutual_seguridad", "ist"),
    "editorial": (),
    "staging_qa": (),
}
TESTS = {
    "media": ("test_press_pipeline.py", "test_live_evidence_replay.py", "test_beta_source_package.py"),
    "public_data": ("test_fonasa_source.py", "test_isp_anamed_source.py", "test_deis_source.py"),
    "fiscalization": ("test_superintendencia_pipeline.py", "test_suseso_pipeline.py", "test_source_health_facets.py"),
    "mutualities": ("test_beta_source_package.py", "test_corporate_newsrooms.py"),
    "editorial": ("test_weekly_freshness.py", "test_editorial_audit_90d.py", "test_editorial_rules_v2.py", "test_quality_editorial.py"),
    "staging_qa": (),
}
VOLATILE_KEYS = {
    "generated_at", "updated_at", "checked_at", "reviewed_at", "started_at", "finished_at",
    "heartbeat_at", "last_heartbeat_at", "duration", "duration_seconds", "elapsed_seconds",
    "run_id", "log_path", "log_sha256", "response_sha256", "response_bytes",
}
PRODUCT_OBSERVATION_KEYS = {
    "generated_at", "updated_at", "checked_at", "reviewed_at", "started_at", "finished_at",
    "heartbeat_at", "last_heartbeat_at", "duration", "duration_seconds", "elapsed_seconds", "run_id",
}
SOURCE_ACCEPTANCE = {
    "external_reconciliation_30d", "external_reconciliation_90d", "publication_trace",
    "source_health", "qa_pass", "independent_review_pass", "runtime_after_merge_pass",
}
EDITORIAL_ACCEPTANCE = {"freshness", "top3_audited", "editorial_business_review_pass", "qa_pass", "independent_review_pass"}
MAX_SOURCE_REQUESTS = 24


def structured_source_problem(value):
    """Request capture hashes are redundant only alongside scoped source facts."""
    return (isinstance(value, dict) and value.get("slug") in {slug for slugs in FAMILIES.values() for slug in slugs}
        and isinstance(value.get("requests"), list) and "technical_status" in value
        and isinstance(value.get("discovered"), int) and isinstance(value.get("dated"), int)
        and (isinstance(value.get("inventory_hash"), str) or isinstance(value.get("samples"), list))
        and all(isinstance(request, dict) and request.get("url") and request.get("status") for request in value["requests"]))


def source_problem_rows(value):
    if structured_source_problem(value):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from source_problem_rows(item)
    elif isinstance(value, list):
        for item in value:
            yield from source_problem_rows(item)


def known_probe_budget_error(value):
    return bool(re.fullmatch(r"(?:RuntimeError:\s*)?bounded_probe_budget:\s*\d+(?: requests per source)?", str(value or "")))


def source_probe_incomplete(row):
    """Canonicalize our guard, without erasing an independent source failure."""
    return (structured_source_problem(row)
        and any(request.get("status") == "UNVERIFIED" and known_probe_budget_error(request.get("error"))
            for request in row["requests"])
        and not any(request.get("status") == "FAIL" for request in row["requests"])
        and not (row.get("error") and not known_probe_budget_error(row["error"])))


def classify_source_probe(row):
    """Our HTTP cap limits evidence; it cannot establish a publisher failure."""
    result = dict(row)
    requests = row.get("requests") or []
    omitted = [request for request in requests if request.get("status") == "UNVERIFIED"
        and known_probe_budget_error(request.get("error"))]
    actual_failures = [request for request in requests if request.get("status") == "FAIL"]
    if omitted:
        result.update(probe_complete=False, probe_budget={"max_requests": MAX_SOURCE_REQUESTS,
            "executed_requests": len(requests) - len(omitted), "unexecuted_requests": len(omitted)})
        parser_error = bool(row.get("error") and not known_probe_budget_error(row["error"]))
        if not actual_failures and not parser_error:
            result.update(technical_status="incomplete", failure_origin="instrumentation_limit")
        else:
            result.update(technical_status="error", failure_origin="source_or_product_fetch")
    return result


def digest(value):
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def semantic(value):
    if isinstance(value, dict):
        return {key: semantic(item) for key, item in sorted(value.items()) if key not in VOLATILE_KEYS}
    if isinstance(value, list):
        return [semantic(item) for item in value]
    if isinstance(value, str):
        if value.startswith("--junitxml="):
            return "--junitxml=<artifact>"
        value = re.sub(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\b", "<timestamp>", value)
        return re.sub(r"\bin \d+(?:\.\d+)?s\b", "in <duration>", value)
    return value


def semantic_hash(value):
    return digest(json.dumps(semantic(value), sort_keys=True, ensure_ascii=False, separators=(",", ":")))


def problem_semantic(value, *, task=None, input_sha=None):
    """Identify a demonstrated problem without changing its raw evidence.

    Product and acceptance identities use their existing stricter contracts.
    Only aliases explicitly bound to the failed QA episode lose run identity.
    An opaque log hash alone still distinguishes an otherwise unknown failure.
    """
    task = task or {}
    failure = task.get("failure") or {}
    run_id = str(failure.get("run_id", ""))
    bound = bool(run_id.isdigit() and task.get("id") == "staging_qa_failed_run_" + run_id
        and failure.get("failure_signature") and task.get("product_input_fingerprint"))
    aliases = {sha for sha in (input_sha, failure.get("head_sha")) if isinstance(sha, str) and re.fullmatch(r"[a-fA-F0-9]{40}", sha)} if bound else set()
    clocks = VOLATILE_KEYS - {"response_sha256", "response_bytes"}
    captures = {"captured_stdout_sha256", "captured_stdout_bytes", "source_evidence_sha256", "failure_sha256", "failure_hash", "fingerprint"}

    source_rows = list(source_problem_rows(value))
    known_source = {row["slug"] for row in source_rows}
    incomplete_slugs = {slug for slug in known_source
        if all(source_probe_incomplete(row) for row in source_rows if row["slug"] == slug)}
    source_urls = {slug: {request["url"] for row in source_rows if row["slug"] == slug for request in row["requests"]}
        for slug in known_source}

    def meaningful(item):
        if isinstance(item, list):
            return any(meaningful(child) for child in item)
        if not isinstance(item, dict):
            return False
        if item.get("output") or item.get("error") or item.get("failure_details"):
            return True
        pytest = item.get("pytest") or {}
        if isinstance(pytest, dict) and pytest.get("cases"):
            return True
        review = item.get("reviewer_proof") or {}
        if isinstance(review, dict) and (review.get("checks") or review.get("findings")):
            return True
        browser = item.get("browser_proof") or {}
        if isinstance(browser, dict) and (browser.get("cases") or (bound and browser.get("stats") and browser.get("projects"))):
            return True
        return any(meaningful(child) for child in item.values())

    def visit(item, path=(), source_scope=False, covered_slugs=()):
        if isinstance(item, dict):
            source_row = structured_source_problem(item)
            source_scope = source_scope or source_row
            incomplete_component = False
            if item.get("kind") and item.get("reason") and isinstance(item.get("evidence"), list):
                component_rows = list(source_problem_rows(item["evidence"]))
                covered_slugs = {row["slug"] for row in component_rows}
                incomplete_component = bool(component_rows) and all(source_probe_incomplete(row) for row in component_rows)
            command = item.get("command")
            covered_probe = False
            if isinstance(command, list) and "--diagnose-source" in command:
                index = command.index("--diagnose-source") + 1
                covered_probe = index < len(command) and command[index] in covered_slugs
            aggregate = item.get("blockers")
            duplicate_evidence = False
            if isinstance(aggregate, list) and isinstance(item.get("evidence"), list):
                flattened = [row for child in aggregate if isinstance(child, dict) for row in child.get("evidence", [])]
                duplicate_evidence = (sorted(json.dumps(row, sort_keys=True) for row in flattened)
                    == sorted(json.dumps(row, sort_keys=True) for row in item["evidence"]))
            actual = meaningful(item)
            result = {}
            for key, child in sorted(item.items()):
                if (key in clocks or (key == "startTime" and path[-2:] == ("browser_proof", "stats"))
                    or (key == "observed_at" and (source_row or path[-1:] == ("real_failure",)))
                    or (key in {"trace_path", "trace_sha256", "failure_signature"} and item.get("source_slug") in known_source and path[-1:] == ("real_failure",))
                    or (key in {"response_sha256", "response_bytes"} and source_scope and path[-1:] == ("requests",))
                    or (source_row and key in {"probe_complete", "probe_budget", "failure_origin"})
                    or (key == "real_failure" and isinstance(child, dict) and child.get("kind") == "source_runtime"
                        and child.get("source_slug") in incomplete_slugs
                        and child.get("source_url") in source_urls[child["source_slug"]])
                    or (key == "output" and structured_source_problem(item.get("source_evidence")))
                    or (key == "evidence" and duplicate_evidence)
                    or (key in captures and (actual or covered_probe)) or (key == "fingerprint" and item.get("reason") and "evidence" in item)):
                    continue
                if key == "technical_status" and source_row and source_probe_incomplete(item):
                    child = "incomplete"
                elif incomplete_component and key == "kind":
                    child = "instrumentation"
                elif incomplete_component and key == "reason":
                    child = "Scoped source coverage incomplete: " + ",".join(sorted(covered_slugs))
                elif incomplete_component and key == "evidence":
                    # Old parser-repair attempts were misdirected at our own
                    # guard. Their removal does not establish a new problem.
                    child = [row for row in child if not (isinstance(row, dict) and "automated_recovery" in row)]
                elif key == "reason" and isinstance(item.get("blockers"), list):
                    child = "; ".join(sorted({visit(row, path + ("blockers",)).get("reason", "")
                        for row in item["blockers"] if isinstance(row, dict)}))
                elif bound and key == "task_id" and child == task.get("id"):
                    child = "staging_qa_failed_run_<episode>"
                elif bound and key in {"candidate_sha", "head_sha"} and isinstance(child, str) and child in aliases:
                    child = "<bound_candidate>"
                elif bound and key in {"source_run_id", "run_url", "source_run_url"} and isinstance(child, (int, str)) and child in {failure.get("run_id"), str(failure.get("run_id")), failure.get("run_url")}:
                    child = "<bound_run>"
                elif key == "command" and isinstance(child, list):
                    command = []
                    reviewer = "scripts/review_candidate.py" in child
                    for index, argument in enumerate(child):
                        previous = child[index - 1] if index else None
                        if bound and previous == "--sha" and argument in aliases:
                            argument = "<bound_candidate>"
                        elif reviewer and previous == "--output":
                            argument = "<review_artifact>"
                        elif isinstance(argument, str) and argument.startswith("--junitxml="):
                            argument = "--junitxml=<artifact>"
                        command.append(argument)
                    child = command
                normalized = visit(child, path + (key,), source_scope, covered_slugs)
                if (key in {"blockers", "evidence", "source_urls"} or (key == "requests" and source_row)) and isinstance(normalized, list):
                    normalized = sorted(normalized, key=lambda row: json.dumps(row, sort_keys=True))
                result[key] = normalized
            return result
        if isinstance(item, list):
            return [visit(child, path, source_scope, covered_slugs) for child in item]
        if isinstance(item, str) and path and path[-1] in {"output", "stdout", "stderr"}:
            # Content and assertions retain dates/durations; test log timing moves.
            return re.sub(r"\bin \d+(?:\.\d+)?s\b", "in <duration>", item)
        return item
    problem = visit(value)
    return {"failure_signature": failure["failure_signature"], "product_input_fingerprint": task["product_input_fingerprint"],
        "problem": problem} if bound else problem


def problem_hash(value, *, task=None, input_sha=None):
    return digest(json.dumps(problem_semantic(value, task=task, input_sha=input_sha), sort_keys=True,
        ensure_ascii=False, separators=(",", ":")))


def source_problem_hash(row):
    return problem_hash(row)


def browser_failure_cases(browser):
    """Retain executed Playwright failure identities, beyond aggregate counts."""
    cases = []
    def visit(suites):
        for suite in suites or []:
            for spec in suite.get("specs", []):
                for test in spec.get("tests", []):
                    failures = [result for result in test.get("results", []) if result.get("status") not in {"passed", "skipped"}]
                    if failures:
                        cases.append({"file": spec.get("file"), "title": spec.get("title"), "project": test.get("projectName"),
                            "expected_status": test.get("expectedStatus"), "status": test.get("status"),
                            "results": [{"status": result.get("status"), "errors": result.get("errors") or ([result["error"]] if result.get("error") else [])} for result in failures]})
            visit(suite.get("suites", []))
    visit(browser.get("suites", []))
    return sorted(cases, key=lambda case: json.dumps(case, sort_keys=True))


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            json.dump(value, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def read_json(path, fallback=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def run_command(command, workspace, timeout=180, env=None):
    environment = dict(os.environ)
    environment.update({"RADAR_ROOT": str(workspace), "PYTHONPATH": str(workspace / "src") + os.pathsep + str(workspace)})
    if env:
        environment.update(env)
    try:
        process = subprocess.run(command, cwd=workspace, env=environment, capture_output=True, text=True, timeout=timeout)
        return {"command": command, "returncode": process.returncode, "stdout": process.stdout, "stderr": process.stderr}
    except subprocess.TimeoutExpired as error:
        def decode(value):
            return value.decode(errors="replace") if isinstance(value, bytes) else (value or "")
        return {"command": command, "returncode": 124, "stdout": decode(error.stdout), "stderr": decode(error.stderr) + "\nBounded command timeout"}
    except OSError as error:
        return {"command": command, "returncode": 127, "stdout": "", "stderr": f"{type(error).__name__}: {error}"}


def pytest_counts(xml_path):
    try:
        cases = list(ET.parse(xml_path).getroot().iter("testcase"))
    except (OSError, ET.ParseError):
        return {"collected": 0, "passed": 0, "skipped": 0, "failed": 0, "cases": [], "proof": False}
    outcomes = []
    for case in cases:
        failed = case.find("failure")
        error = case.find("error")
        skipped = case.find("skipped")
        status = "FAIL" if failed is not None or error is not None else ("SKIP" if skipped is not None else "PASS")
        detail = failed if failed is not None else (error if error is not None else skipped)
        outcomes.append({"name": case.get("classname", "") + "::" + case.get("name", ""), "status": status,
                         "reason": (detail.get("message", "") if detail is not None else "")})
    return {"collected": len(cases), "passed": sum(x["status"] == "PASS" for x in outcomes),
            "skipped": sum(x["status"] == "SKIP" for x in outcomes), "failed": sum(x["status"] == "FAIL" for x in outcomes),
            "cases": outcomes, "proof": bool(cases) and all(x["status"] == "PASS" for x in outcomes)}


def tracked_hashes(workspace):
    result = run_command(["git", "ls-files", "-z"], workspace)
    hashes = {}
    for relative in result["stdout"].split("\0"):
        if not relative or relative.startswith((".github/", "artifacts/", "work/", "docs/", "tests/")):
            continue
        path = workspace / relative
        hashes[relative] = digest(path.read_bytes()) if path.is_file() else None
    return hashes


def product_semantic(value):
    """Ignore observation clocks, retaining publication dates, strings and hashes."""
    if isinstance(value, dict):
        return {key: product_semantic(item) for key, item in sorted(value.items()) if key not in PRODUCT_OBSERVATION_KEYS}
    if isinstance(value, list):
        return [product_semantic(item) for item in value]
    return value


def material_file_hashes(workspace, raw_hashes):
    """JSON contents define material changes; other files retain their exact bytes."""
    fingerprints = dict(raw_hashes)
    unknown = []
    for relative, raw_hash in raw_hashes.items():
        path = workspace / relative
        if path.suffix.lower() != ".json" or raw_hash is None:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            # Invalid/unreadable JSON cannot be confidently ignored as churn.
            # Preserve the raw identity and leave its required gates in control.
            unknown.append(relative)
            continue
        fingerprints[relative] = digest(json.dumps(product_semantic(payload), sort_keys=True, ensure_ascii=False, separators=(",", ":")))
    return fingerprints, sorted(unknown)


def blocker(reason, evidence, *, kind="technical", urls=()):
    identity = {"kind": kind, "reason": reason, "evidence": evidence, "source_urls": sorted(set(urls))}
    return {**identity, "fingerprint": semantic_hash(identity), "human_required": kind == "policy"}


def save_command_evidence(result, directory, name, counts=None):
    log = result["stdout"] + result["stderr"]
    path = directory / (name + ".log")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(log, encoding="utf-8")
    # Raw log retained for reproduction; durations and log paths do not define progress.
    evidence = {"command": result["command"], "returncode": result["returncode"],
                "status": "PASS" if result["returncode"] == 0 else "FAIL", "log_path": str(path), "log_sha256": digest(log)}
    if counts is not None:
        evidence["pytest"] = counts
        if not counts["proof"] and result["returncode"] == 0:
            evidence["status"] = "SKIP" if counts["skipped"] else "UNVERIFIED"
    evidence["failure_hash"] = semantic_hash({"command": result["command"], "returncode": result["returncode"],
                                              "cases": (counts or {}).get("cases"),
                                              "reason": re.sub(r"in \d+(?:\.\d+)?s", "in <duration>", log[-12000:])}) if evidence["status"] == "FAIL" else None
    return evidence


def recovery_module():
    path = SCRIPT_ROOT / "scripts/autonomy_recovery.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("autonomy_recovery_lane", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def preserve_partial_proof(report, recovery, logs, label):
    """Retain directed repair proof while keeping global integration failures open."""
    if not (recovery.get("partial_candidate") and recovery.get("targeted_validated") and recovery.get("no_new_failures")):
        return
    def convert(raw, name):
        result = {"command": raw.get("command", []), "returncode": raw.get("returncode", 127),
                  "stdout": raw.get("output", raw.get("stdout", "")), "stderr": raw.get("stderr", "")}
        return save_command_evidence(result, logs, label + "-" + name)
    comparison = recovery.get("non_regression", {})
    report.update(partial_candidate=True, candidate_scope="isolated", no_new_failures=True,
                  targeted_validated=True, directed_gates=[convert(raw, "directed-" + str(index))
                    for index, raw in enumerate(recovery.get("directed_gates", []))],
                  non_regression={**comparison,
                    "baseline_gate": convert(comparison.get("baseline_gate", {}), "baseline-full"),
                    "candidate_gate": convert(comparison.get("candidate_gate", {}), "candidate-full")})
    if recovery.get("live_validated") and recovery.get("live_gate"):
        report.update(live_validated=True, live_gate=convert(recovery["live_gate"], "live-after-repair"),
                      live_scope=[recovery["source_slug"]])


def source_worker(slug):
    """Call the current product scout, recording hidden HTTP exceptions as evidence."""
    from radar_salud import source_scouts, scouts, beta_sources, beta_sources_fast, superintendencia_fiscalizacion
    constructors = {
        "diario_financiero": source_scouts.DfHealthScout,
        "pulso_latercera": lambda: beta_sources_fast.FastCuratedBetaSourceScout("pulso_latercera"),
        "fonasa": source_scouts.FonasaNewsScout,
        "fonasa_datos_abiertos": source_scouts.FonasaDataHubScout,
        "isp_anamed": source_scouts.IspAnamedAlertScout,
        "isp_surveillance": source_scouts.IspSurveillanceScout,
        "deis": source_scouts.DeisResourceScout,
        "superintendencia_fiscalizacion": superintendencia_fiscalizacion.SuperintendenciaFiscalizacionScout,
        "suseso_fiscalizacion": source_scouts.SusesoFiscalizacionScout,
    }
    if slug in FAMILIES["mutualities"]:
        constructors[slug] = lambda: beta_sources_fast.FastCuratedBetaSourceScout(slug)
    requests = []
    original = scouts.fetch_html
    def fetch(url, *args, **kwargs):
        entry = {"url": str(url)}
        requests.append(entry)
        if len(requests) > MAX_SOURCE_REQUESTS:
            entry.update(status="UNVERIFIED", error=f"bounded_probe_budget: {MAX_SOURCE_REQUESTS} requests per source")
            raise RuntimeError(entry["error"])
        try:
            response = original(url, *args, **kwargs)
            entry.update(status="PASS", response_sha256=digest(response), response_bytes=len(response.encode()))
            return response
        except Exception as error:
            entry.update(status="FAIL", error=f"{type(error).__name__}: {error}")
            raise
    for module in (source_scouts, scouts, beta_sources, beta_sources_fast, superintendencia_fiscalizacion):
        module.fetch_html = fetch
    error = None
    try:
        items = constructors[slug]().discover()
    except Exception as exception:
        items = []
        error = f"{type(exception).__name__}: {exception}"
    rows = sorted(({"source_url": item.url, "title": item.title, "event_date": item.event_date,
                    "content_hash": digest(str(getattr(item, "raw_text", "") or ""))} for item in items),
                  key=lambda item: (item["event_date"] or "", item["source_url"]), reverse=True)
    failures = [request for request in requests if request.get("status") != "PASS"]
    result = {"slug": slug, "technical_status": "error" if error or failures else "ok", "error": error,
              "discovered": len(rows), "dated": sum(bool(row["event_date"]) for row in rows),
              "newest_event_date": max((row["event_date"] for row in rows if row["event_date"]), default=None),
              "samples": rows[:12], "inventory_hash": semantic_hash(rows), "requests": requests,
              "publication_verified": False, "scope": "discovery_only"}
    result = classify_source_probe(result)
    print("AUTONOMY_SOURCE_JSON=" + json.dumps(result, ensure_ascii=False))
    return 1 if result["technical_status"] != "ok" else 0


def source_urls(workspace, task, family):
    urls = set()
    def visit(value):
        if isinstance(value, str):
            urls.update(re.findall(r"https?://[^\s\"'<>]+", value))
        elif isinstance(value, dict):
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
    visit(task.get("source_urls", []))
    visit(task.get("sources", []))
    for filename in ("sources.json", "beta_source_configs.json"):
        catalog = read_json(workspace / "config" / filename, [])
        if isinstance(catalog, list):
            for row in catalog:
                if row.get("slug") in FAMILIES[family]:
                    visit(row)
    return sorted(urls)


def verify_acceptance(workspace, task, family, input_sha):
    """Only a task- and revision-bound explicit acceptance manifest can close work."""
    manifest = task.get("acceptance_artifact")
    if not isinstance(manifest, dict) or not manifest.get("path") or not manifest.get("sha256"):
        return [], "Missing revision-bound acceptance_artifact with path and sha256"
    path = (workspace / manifest["path"]).resolve()
    if not path.is_relative_to(workspace.resolve()) or not path.is_file():
        return [], "Acceptance artifact is missing or outside the candidate workspace"
    if digest(path.read_bytes()) != manifest["sha256"]:
        return [], "Acceptance artifact hash does not match its explicit task reference"
    payload = read_json(path, {})
    if not isinstance(payload, dict):
        return [], "Acceptance artifact must contain a manifest object"
    if payload.get("task_id") != task.get("id") or payload.get("candidate_sha") != input_sha or payload.get("verdict") != "PASS":
        return [], "Acceptance artifact does not bind PASS to this task and candidate revision"
    required = SOURCE_ACCEPTANCE if FAMILIES[family] else (EDITORIAL_ACCEPTANCE if family == "editorial" else {"qa_pass", "browser_desktop_pass", "browser_mobile_pass", "independent_review_pass"})
    checks = payload.get("checks", {})
    if not isinstance(checks, dict):
        return [], "Acceptance artifact checks must contain explicit named PASS decisions"
    if any(checks.get(name) is not True for name in required):
        return [], "Acceptance artifact lacks explicit PASS checks: " + ", ".join(sorted(name for name in required if checks.get(name) is not True))
    references = payload.get("evidence", [])
    if not isinstance(references, list) or not references:
        return [], "Acceptance artifact has no verifiable evidence references"
    verified = []
    for reference in references:
        if not isinstance(reference, dict) or not reference.get("path") or not reference.get("sha256"):
            return [], "Every acceptance evidence item needs an artifact path and sha256"
        target = (workspace / reference["path"]).resolve()
        if not target.is_relative_to(workspace.resolve()) or not target.is_file() or digest(target.read_bytes()) != reference["sha256"]:
            return [], "Acceptance evidence missing or changed: " + str(reference.get("path"))
        verified.append(reference)
    if FAMILIES[family]:
        if not set(FAMILIES[family]) <= set(payload.get("sources", [])):
            return [], "Acceptance manifest does not cover every source in this independent family"
        source_proof, reason = verify_source_staging_acceptance(workspace, payload, verified, family, input_sha)
        if reason:
            return [], reason
    else:
        source_proof = {}
    return [{"path": manifest["path"], "sha256": manifest["sha256"], "checks": checks, "evidence": verified,
             "verified": True, "task_id": task["id"], "candidate_sha": input_sha, "verdict": "PASS", **source_proof}], None


def verify_source_staging_acceptance(workspace, payload, references, family, input_sha):
    """An isolated candidate is never source implementation or source closure."""
    if not re.fullmatch(r"[0-9a-f]{40}", str(input_sha)) or payload.get("staging_merge_sha") != input_sha:
        return {}, "Source acceptance must bind staging_merge_sha to the actual input SHA"
    reference = run_command(["git", "rev-parse", "--verify", "refs/remotes/origin/staging^{commit}"], workspace, timeout=10)
    staging_sha = reference["stdout"].strip()
    if reference["returncode"] != 0 or not re.fullmatch(r"[0-9a-f]{40}", staging_sha):
        return {}, "Source acceptance requires the recorded current origin/staging reference; it is unavailable"
    ancestry = run_command(["git", "merge-base", "--is-ancestor", input_sha, staging_sha], workspace, timeout=10)
    if ancestry["returncode"] != 0:
        return {}, "Source candidate input SHA is not incorporated into recorded origin/staging"
    runtime_refs = [item for item in references if item.get("kind") == "runtime_after_merge"]
    if not runtime_refs:
        return {}, "Source acceptance needs hashed runtime_after_merge evidence after staging integration"
    covered = set()
    outcomes = {"published", "rejected", "genuine_absence"}
    for item in runtime_refs:
        runtime = read_json(workspace / item["path"], {})
        if not isinstance(runtime, dict) or runtime.get("staging_sha") != input_sha or runtime.get("execution_after_merge") is not True:
            return {}, "Source runtime artifact must prove execution_after_merge bound to staging SHA"
        trace = runtime.get("trace")
        if not isinstance(trace, list) or not trace:
            return {}, "Source runtime artifact has no actual source execution trace"
        for entry in trace:
            if not isinstance(entry, dict):
                return {}, "Source runtime trace must contain evidence objects"
            slug = entry.get("source")
            url = str(entry.get("source_url") or "")
            parsed_url = urlparse(url)
            detail = entry.get("runtime_evidence")
            if (slug not in FAMILIES[family] or entry.get("staging_sha") != input_sha or
                    entry.get("outcome") not in outcomes or parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc or
                    not isinstance(detail, (dict, list)) or not semantic(detail)):
                return {}, "Source runtime trace lacks a matching source/SHA and substantive operational outcome"
            command = entry.get("command")
            if not isinstance(command, list) or not command or not all(isinstance(arg, str) and arg for arg in command) or entry.get("returncode") != 0:
                return {}, "Source runtime trace lacks successful actual execution evidence"
            log_path = entry.get("log_path")
            log_hash = entry.get("log_sha256")
            if not isinstance(log_path, str) or not re.fullmatch(r"[0-9a-f]{64}", str(log_hash)):
                return {}, "Source runtime trace lacks its exact execution log and hash"
            log = (workspace / log_path).resolve()
            if not log.is_relative_to(workspace.resolve()) or not log.is_file() or digest(log.read_bytes()) != log_hash:
                return {}, "Source runtime execution log is missing or changed"
            content = log.read_text(errors="replace")
            if not all(value in content for value in (input_sha, slug, url, entry["outcome"])):
                return {}, "Source runtime log does not bind actual source execution and outcome to the staging SHA"
            covered.add(slug)
    if covered != set(FAMILIES[family]):
        return {}, "Post-merge runtime evidence does not cover every source in this independent family"
    return {"staging_merge_sha": input_sha, "origin_staging_sha": staging_sha, "runtime_after_merge": runtime_refs}, None


def sync_reviewed_editorial(workspace):
    """Restore/expire only the existing human-reviewed weekly item, never draft copy."""
    sys.path.insert(0, str(workspace / "src"))
    from radar_salud.weekly_freshness import reviewed_weekly
    approved = read_json(workspace / "data/weekly_insight/editorial_approved.json", {})
    current = reviewed_weekly(approved)
    changed = []
    for relative in ("data/weekly_insight/latest.json", "web/data/free_value.json"):
        path = workspace / relative
        payload = read_json(path)
        if not isinstance(payload, dict):
            continue
        if semantic_hash(payload.get("weekly_insight")) == semantic_hash(current):
            continue
        payload["weekly_insight"] = current
        if relative.startswith("web/"):
            payload.setdefault("selection_policy", {})["weekly_insight_status"] = "published_deep_intelligence" if current else "editorial_review_required"
        else:
            payload["status"] = "pass" if current else "editorial_review_required"
            if current:
                payload["audit"] = approved["audit"]
        atomic_json(path, payload)
        changed.append(relative)
    return {"operation": "sync_existing_reviewed_weekly", "changed_paths": changed,
            "reviewed_item_available": bool(current), "acceptance": False,
            "reason": "Existing reviewed freshness gate; task closure requires independent editorial acceptance"}


def execute_lane(family, workspace, task, report_path, *, allow_llm=False, timeout=180, command_runner=run_command, input_sha=None):
    workspace = Path(workspace).resolve()
    report_path = Path(report_path).resolve()
    logs = report_path.parent / (report_path.stem + "-logs")
    logs.mkdir(parents=True, exist_ok=True)
    branch_result = command_runner(["git", "symbolic-ref", "--quiet", "--short", "HEAD"], workspace, timeout=10)
    branch = branch_result["stdout"].strip()
    sha_result = command_runner(["git", "rev-parse", "HEAD"], workspace, timeout=10)
    actual_sha = sha_result["stdout"].strip()
    input_sha = input_sha or actual_sha
    report = {"version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "task_id": task.get("id"),
              "family": family, "input_sha": input_sha, "status": "BLOCKED", "evidence": [], "blockers": [],
              "gates": [], "acceptance_proof": [], "changed_paths": [], "validated": False,
              "workflow_success_is_progress": False, "source_results": []}
    if branch in {"main", "master", "production", "production-stable"} or sha_result["returncode"] or input_sha != actual_sha:
        report["blockers"].append(blocker("Runner requires an isolated staging candidate at the declared input SHA", [branch_result, sha_result], kind="policy"))
        report["semantic_hash"] = semantic_hash(report["blockers"])
        atomic_json(report_path, report)
        return report
    before = tracked_hashes(workspace)
    before_material, before_unknown = material_file_hashes(workspace, before)
    report["before_hash"] = digest(json.dumps(before_material, sort_keys=True))
    report["raw_before_hash"] = digest(json.dumps(before, sort_keys=True))
    supplied_failure = ""
    if task.get("failure_log_path"):
        failure_path = (workspace / task["failure_log_path"]).resolve()
        if failure_path.is_relative_to(workspace) and failure_path.is_file() and failure_path.stat().st_size <= 512000:
            supplied_failure = failure_path.read_text(errors="replace")
            report["evidence"].append({"failed_workflow_log": str(failure_path), "sha256": digest(failure_path.read_bytes()),
                                       "source_run_id": task.get("source_run_id") or task.get("failure", {}).get("run_id"),
                                       "source_run_url": task.get("source_run_url") or task.get("failure", {}).get("run_url")})
        else:
            report["blockers"].append(blocker("Failed workflow log is missing, unsafe or exceeds bounded input size", [{"failure_log_path": task["failure_log_path"]}]))
    tests = ["tests/" + name for name in TESTS[family] if (workspace / "tests" / name).is_file()]
    if family == "staging_qa":
        tests = ["tests"]
    if not tests:
        report["blockers"].append(blocker("No targeted deterministic gate is installed for this family", [{"expected_tests": list(TESTS[family])}]))
    else:
        xml = logs / "targeted-pytest.xml"
        command = [sys.executable, "-m", "pytest", "-q", "-rs", "--junitxml=" + str(xml)]
        if family == "staging_qa":
            command.extend(["-m", "not integration"])
        result = command_runner([*command, *tests], workspace, timeout=timeout)
        gate = save_command_evidence(result, logs, "targeted-pytest", pytest_counts(xml))
        gate["name"] = "targeted_deterministic_tests"
        report["gates"].append(gate)
        report["evidence"].append(gate)
        if gate["status"] == "FAIL" or (family == "staging_qa" and supplied_failure):
            module = recovery_module()
            if module is not None:
                try:
                    recovery = module.recover(workspace, task, supplied_failure or (result["stdout"] + result["stderr"]),
                                              patch=task.get("repair_patch"), allow_model=allow_llm and bool(os.environ.get("OPENAI_API_KEY")), stage=False)
                except Exception as error:
                    recovery = {"status": "BLOCKED", "reason": f"{type(error).__name__}: {error}"}
                report["recovery"] = recovery
                report["evidence"].append({"recovery_attempt": recovery})
                if recovery.get("validated") or recovery.get("partial_candidate"):
                    result = command_runner(gate["command"], workspace, timeout=timeout)
                    gate = save_command_evidence(result, logs, "targeted-pytest-after-recovery", pytest_counts(xml))
                    gate["name"] = "targeted_deterministic_tests"
                    report["gates"][0] = gate
                    report["evidence"].append(gate)
                    if gate["status"] == "PASS":
                        preserve_partial_proof(report, recovery, logs, "test-recovery")
            if gate["status"] != "PASS":
                report["blockers"].append(blocker("Targeted deterministic gate failed; no validated repair candidate", [gate, report.get("recovery", {"attempted": False, "reason": "Recovery module unavailable"})]))
        elif gate["status"] != "PASS":
            report["blockers"].append(blocker("Targeted test run lacks executed PASS evidence; pytest skips do not prove a live path", [gate]))

    if FAMILIES[family]:
        def diagnose(slug, phase=""):
            command = [sys.executable, str(Path(__file__).resolve()), "--diagnose-source", slug]
            result = command_runner(command, workspace, timeout=timeout)
            evidence = save_command_evidence(result, logs, "source-" + slug + phase)
            lines = [line.partition("=")[2] for line in result["stdout"].splitlines() if line.startswith("AUTONOMY_SOURCE_JSON=")]
            row = read_json_string(lines[-1]) if lines else None
            if not row:
                row = {"slug": slug, "technical_status": "error", "error": "No completed scoped discovery evidence", "requests": [], "publication_verified": False}
            row = classify_source_probe(row)
            urls = [entry["url"] for entry in row.get("requests", [])] or source_urls(workspace, task, family)
            evidence["source_urls"] = urls
            return row, evidence
        with ThreadPoolExecutor(max_workers=min(3, len(FAMILIES[family]))) as pool:
            diagnoses = list(pool.map(diagnose, FAMILIES[family]))
        for row, evidence in diagnoses:
            report["source_results"].append(row)
            report["evidence"].append(evidence)
            if row["technical_status"] != "ok" or not row.get("dated"):
                recovery = None
                if row["technical_status"] not in {"ok", "incomplete"}:
                    failed_urls = [entry["url"] for entry in row.get("requests", []) if entry.get("status") == "FAIL"]
                    source_url = (failed_urls or evidence["source_urls"] or [None])[0]
                    report["real_failure"] = {"kind": "source_runtime", "source_url": source_url,
                                              "source_slug": row["slug"],
                                              "failure_signature": source_problem_hash(row),
                                              "trace_path": evidence["log_path"], "trace_sha256": evidence["log_sha256"],
                                              "observed_at": datetime.now(timezone.utc).isoformat(), "verified": bool(source_url and (row.get("error") or failed_urls))}
                    module = recovery_module()
                    if module is not None:
                        try:
                            recovery = module.recover(workspace, task, Path(evidence["log_path"]).read_text(),
                                                      source_slug=row["slug"], patch=task.get("repair_patch"),
                                                      allow_model=allow_llm and bool(os.environ.get("OPENAI_API_KEY")), stage=False)
                        except Exception as error:
                            recovery = {"status": "BLOCKED", "validated": False, "blocker": f"{type(error).__name__}: {error}"}
                        report.setdefault("source_recovery", []).append({"slug": row["slug"], "attempt": recovery})
                        report["evidence"].append({"source_recovery_attempt": recovery, "source": row["slug"]})
                    if recovery and (recovery.get("validated") or recovery.get("partial_candidate")):
                        updated, updated_evidence = diagnose(row["slug"], "-after-recovery")
                        report["evidence"].append(updated_evidence)
                        if updated["technical_status"] == "ok" and updated.get("dated"):
                            report["source_results"][-1] = updated
                            report["failure_action"] = "repaired"
                            report.update(live_gate=updated_evidence, live_scope=[row["slug"]], live_validated=True,
                                          directed_gates=[gate for gate in report["gates"] if gate["status"] == "PASS"])
                            preserve_partial_proof(report, recovery, logs, "source-recovery-" + row["slug"])
                            continue
                    report["failure_action"] = "blocked"
                incomplete = row["technical_status"] == "incomplete"
                reason = ("Scoped coverage INCOMPLETE: internal request budget reached: " + row["slug"] if incomplete else
                    "Scoped live discovery failed: " + row["slug"] if row["technical_status"] != "ok" else "No dated discovery proves current coverage: " + row["slug"])
                skipped = "Instrumentation limit is not a demonstrated source failure" if incomplete else "No test failure or source recovery module installed"
                report["blockers"].append(blocker(reason, [evidence, row, {"automated_recovery": recovery or {"attempted": False, "reason": skipped}}],
                    kind="instrumentation" if incomplete else "technical", urls=evidence["source_urls"]))

    if family == "editorial" and report["gates"] and all(gate["status"] == "PASS" for gate in report["gates"]):
        try:
            report["evidence"].append(sync_reviewed_editorial(workspace))
        except (ImportError, OSError, KeyError, ValueError, TypeError) as error:
            report["blockers"].append(blocker("Existing reviewed weekly sync could not be proven", [{"error": f"{type(error).__name__}: {error}"}]))

    after = tracked_hashes(workspace)
    after_material, after_unknown = material_file_hashes(workspace, after)
    raw_changed = sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))
    changed = [path for path in raw_changed if before_material.get(path) != after_material.get(path)]
    if changed:
        xml = logs / "full-pytest.xml"
        result = command_runner([sys.executable, "-m", "pytest", "-q", "-rs", "-m", "not integration", "--junitxml=" + str(xml)], workspace, timeout=max(timeout, 300))
        gate = save_command_evidence(result, logs, "full-pytest", pytest_counts(xml))
        gate["name"] = "full_deterministic_tests_before_candidate"
        report["gates"].append(gate)
        report["evidence"].append(gate)
        if gate["status"] != "PASS":
            report["blockers"].append(blocker("Full acceptance gate rejects the candidate; preserve demonstrated failures without lowering gates", [gate]))
        if (workspace / "tests/web.test.cjs").is_file():
            result = command_runner(["npm", "test"], workspace, timeout=timeout)
            gate = save_command_evidence(result, logs, "web-tests")
            gate["name"] = "web_deterministic_tests"
            report["gates"].append(gate)
            report["evidence"].append(gate)
            if gate["status"] != "PASS":
                report["blockers"].append(blocker("Web regression gate rejects repair candidate", [gate]))
    # Product candidates and the staging QA lane retain independent reviewer and
    # browser contracts. Missing tools are explicit technical blockers, not PASS.
    if changed or family == "staging_qa":
        commands = [
            ("independent_reviewer", [sys.executable, "scripts/review_candidate.py", "--web", "web", "--sha", input_sha,
                                       "--output", str(logs / "reviewer.json")]),
            ("browser_desktop_and_mobile", ["npm", "run", "test:browser"]),
        ]
        for name, command in commands:
            proof_path = logs / "reviewer.json" if name == "independent_reviewer" else workspace / "artifacts/browser.json"
            if proof_path.is_file() and not proof_path.is_symlink():
                proof_path.unlink()
            result = command_runner(command, workspace, timeout=max(timeout, 300))
            gate = save_command_evidence(result, logs, name)
            gate["name"] = name
            if name == "independent_reviewer":
                review = read_json(logs / "reviewer.json", {})
                gate["reviewer_proof"] = review
                if result["returncode"] == 0 and (review.get("candidate_sha") != input_sha or
                        not review.get("checks") or not all(value is True for value in review["checks"].values()) or
                        any(item.get("severity") == "critical" for item in review.get("findings", []))):
                    gate["status"] = "UNVERIFIED"
            else:
                browser = read_json(workspace / "artifacts/browser.json", {})
                stats = browser.get("stats", {})
                projects = {item.get("name") for item in browser.get("config", {}).get("projects", [])}
                gate["browser_proof"] = {"stats": stats, "projects": sorted(projects), "cases": browser_failure_cases(browser)}
                if result["returncode"] == 0 and (not stats.get("expected") or stats.get("unexpected", 0) or
                        stats.get("skipped", 0) or not {"desktop", "mobile"} <= projects):
                    gate["status"] = "UNVERIFIED"
            report["gates"].append(gate)
            report["evidence"].append(gate)
            if gate["status"] != "PASS":
                report["blockers"].append(blocker("Independent candidate gate rejected or could not execute: " + name, [gate]))
    report["changed_paths"] = changed
    report["after_hash"] = digest(json.dumps(after_material, sort_keys=True))
    report["raw_after_hash"] = digest(json.dumps(after, sort_keys=True))
    report["raw_changed_paths"] = raw_changed
    report["ignored_observation_paths"] = sorted(set(raw_changed) - set(changed))
    report["semantic_noop"] = bool(raw_changed) and not changed
    report["semantic_unknown_paths"] = sorted(set(before_unknown) | set(after_unknown))
    report["targeted_validated"] = bool(report["gates"]) and report["gates"][0]["status"] == "PASS"
    report["family_live_validated"] = bool(report["source_results"]) and all(row["technical_status"] == "ok" and row.get("dated") for row in report["source_results"])
    if not report.get("live_scope"):
        report["live_validated"] = report["family_live_validated"]
    report["validated"] = bool(report["gates"]) and all(gate["status"] == "PASS" for gate in report["gates"]) and (not FAMILIES[family] or report["family_live_validated"])
    proof, missing = verify_acceptance(workspace, task, family, input_sha)
    if proof and report["validated"] and not report["blockers"] and not changed:
        report["status"] = "PASS"
        report["acceptance_proof"] = proof
    else:
        if missing:
            report["blockers"].append(blocker("Explicit task acceptance is still open: " + missing,
                                              [{"family": family, "task_id": task.get("id"), "diagnostics_are_acceptance": False}], kind="acceptance"))
        if changed and (report["validated"] or report.get("partial_candidate")):
            report["status"] = "REPAIRED"
    report["blocker"] = report["blockers"][0] if report["blockers"] else None
    for item in report["blockers"]:
        identity = {key: child for key, child in item.items() if key not in {"fingerprint", "human_required"}}
        item["fingerprint"] = problem_hash(identity, task=task, input_sha=input_sha)
    report["audit_fingerprint"] = problem_hash({"blockers": report["blockers"], "source_results": report["source_results"],
        "gates": [{"name": gate["name"], "status": gate["status"], "pytest": gate.get("pytest")} for gate in report["gates"]]}, task=task, input_sha=input_sha)
    report["semantic_hash"] = semantic_hash({"status": report["status"], "audit_fingerprint": report["audit_fingerprint"],
                                              "changed_paths": changed, "after_hash": report["after_hash"], "acceptance_proof": report["acceptance_proof"]})
    definition_keys = ("id", "objective", "instructions", "constraints", "evidence_required", "approved_at", "sources", "source_urls",
                       "repair_patch", "acceptance_artifact", "independent_review")
    # A new lease, owner/run or pickup commit cannot license another identical audit.
    report["evidence_revision"] = semantic_hash({"task": {key: task[key] for key in definition_keys if key in task}, "acceptance": proof})
    report["material_progress"] = {"mutation_candidate": bool(changed and (report["validated"] or report.get("partial_candidate"))), "blocker_candidate": bool(report["blockers"]),
                                   "verified_closure": report["status"] == "PASS", "requires_durable_comparison": True,
                                   "workflow_success": False}
    atomic_json(report_path, report)
    return report


def read_json_string(value):
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", choices=FAMILIES)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--task-json", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--input-sha")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--allow-llm", action="store_true")
    parser.add_argument("--no-llm", action="store_true", help="Default: use deterministic diagnosis and approved existing editorial evidence")
    parser.add_argument("--diagnose-source", choices=sorted({slug for slugs in FAMILIES.values() for slug in slugs}), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.diagnose_source:
        return source_worker(args.diagnose_source)
    if not all((args.family, args.workspace, args.task_json, args.report)):
        parser.error("--family, --workspace, --task-json and --report are required")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    task = read_json(args.task_json)
    if not isinstance(task, dict) or not task.get("id"):
        parser.error("--task-json must contain a task object with id")
    report = execute_lane(args.family, args.workspace, task, args.report, allow_llm=args.allow_llm and not args.no_llm,
                          timeout=args.timeout, input_sha=args.input_sha)
    print(json.dumps({"task_id": report["task_id"], "family": report["family"], "status": report["status"],
                      "validated": report["validated"], "changed_paths": report["changed_paths"], "semantic_hash": report["semantic_hash"]}))
    # A faithfully recorded blocker is a successful worker completion, never a task PASS.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
