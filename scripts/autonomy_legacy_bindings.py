"""Verify historical source-event product inputs before importing metadata.

The CLI accepts event IDs, never preverified assertions. Preparation reads the
actual state history, its immutable worker result and the product Git commit.
The optional CAS import changes only the binding registry and proof evidence;
it neither corrects events nor claims material progress.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import tempfile

import autonomy_engine as engine
from autonomy_runtime import FAMILY_INPUTS, scoped_fingerprint
from autonomy_state_store import GitStateStore, Mutation


CONTROL = "data/autopilot/control_v2.json"
EVIDENCE = "data/autopilot/evidence/"
REGISTRY = "material_event_product_bindings"
COMMON_INPUTS = ["src/radar_salud/scouts.py", "src/radar_salud/models.py",
                 "config/sources.json", "config/beta_source_configs.json"]


class BindingVerificationError(ValueError):
    """Historical authority does not establish the requested binding."""


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def digest(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def require(condition, reason):
    if not condition:
        raise BindingVerificationError(reason)


@dataclass(frozen=True)
class VerifiedBindings:
    bindings: dict
    proof: dict

    @property
    def proof_path(self):
        return EVIDENCE + "legacy-product-bindings-" + engine._hash(self.bindings) + ".json"


def _report_matches(event, worker):
    report = worker.get("report", {})
    if (worker.get("kind") != "worker_result" or not isinstance(report, dict)
            or report.get("task_id") != event["task_id"]
            or report.get("family") != event["family"]):
        return False
    actual = list(report.get("blockers", [])) if isinstance(report.get("blockers"), list) else []
    if report.get("blocker"):
        actual.append(report["blocker"])
    expected = event.get("details", {}).get("blockers", [])
    return bool(expected) and {engine._hash(item) for item in actual} == {
        engine._hash(item) for item in expected}


def _verify_finish(reader, git_dir, head, event, worker_path, worker_bytes, products):
    worker = json.loads(worker_bytes)
    report = worker["report"]
    history = reader._git(git_dir, "log", "--format=%H", head, "--", worker_path).stdout.decode().splitlines()
    require(len(history) == 1, "Worker-result evidence is not immutable in Git history")
    finish = history[0]
    require(engine.SHA_RE.fullmatch(finish), "Missing historical finish commit")
    control_bytes = reader._git(git_dir, "show", finish + ":" + CONTROL).stdout
    historical = json.loads(control_bytes)
    matches = [item for item in historical.get("material_events", []) if item.get("id") == event["id"]]
    require(matches == [event], "Historical finish event does not match the current raw event")
    parent = reader._git(git_dir, "rev-parse", finish + "^", check=False)
    require(parent.returncode == 0, "Historical finish must have a parent authority")
    before_bytes = reader._git(git_dir, "show", parent.stdout.decode().strip() + ":" + CONTROL,
                              check=False)
    require(before_bytes.returncode == 0, "Historical finish parent lacks control authority")
    before = json.loads(before_bytes.stdout)
    require(not any(item.get("id") == event["id"] for item in before.get("material_events", [])),
            "Worker result was not committed with the event's actual finish")
    require(reader._git(git_dir, "show", finish + ":" + worker_path).stdout == worker_bytes,
            "Historical worker-result bytes changed")
    task = historical.get("tasks", {}).get(event["task_id"], {})
    require(task.get("id") == event["task_id"] and task.get("family") == event["family"],
            "Historical task/family does not match the event")
    input_sha = report.get("input_sha", "")
    require(engine.SHA_RE.fullmatch(input_sha) and input_sha == task.get("input_sha"),
            "Worker input SHA does not match the historical task authority")
    product = task.get("product_input_fingerprint") or task.get("input_fingerprint", "")
    require(engine.HASH_RE.fullmatch(product), "Historical task lacks a product fingerprint")
    require(_report_matches(event, worker), "Worker blockers do not exactly bind the raw event")
    scope = FAMILY_INPUTS[event["family"]] + COMMON_INPUTS
    key = (input_sha, event["family"])
    if key not in products:
        reader._git(git_dir, "fetch", "--quiet", "--no-tags", "origin", input_sha)
        fetched = reader._git(git_dir, "rev-parse", "FETCH_HEAD^{commit}").stdout.decode().strip()
        require(fetched == input_sha, "Fetched product commit does not match worker input")
        products[key] = scoped_fingerprint(Path(git_dir), input_sha, scope)
    require(products[key] == product, "Committed product scope does not match historical task fingerprint")
    binding = {"schema_version": 1, "verified": True,
        "task_id": event["task_id"], "family": event["family"],
        "event_sha256": engine._hash(event), "input_sha": input_sha,
        "product_input_fingerprint": product,
        "proof": {"state_commit": finish, "control_sha256": digest(control_bytes),
                  "worker_result": {"path": worker_path, "sha256": digest(worker_bytes)}}}
    check = {"event_id": event["id"], "actual_finish_commit": finish,
        "current_raw_event_matches_historical": True, "event_absent_from_finish_parent": True,
        "immutable_worker_result_matches_report_blockers": True,
        "report_task_family_and_input_match_historical_task": True,
        "product_commit": input_sha, "product_scope": scope,
        "computed_product_input_fingerprint": products[key], "product_scope_matches_historical_task": True}
    return binding, check


def prepare_bindings(reader, event_ids):
    """Build bindings solely from fetched Git authority, with no caller proof."""
    requested = sorted(set(event_ids))
    require(bool(requested) and all(engine.HASH_RE.fullmatch(item) for item in requested),
            "Explicit 64-character raw event IDs are required")
    with tempfile.TemporaryDirectory(prefix="autonomy-legacy-verify-") as git_dir:
        reader._initialize(git_dir)
        head = reader._fetch(git_dir)
        snapshot = reader._snapshot(git_dir, head)
        state = snapshot.read_json(CONTROL)
        require(isinstance(state, dict), "Control authority is missing")
        events = {item["id"]: item for item in state.get("material_events", [])}
        workers = []
        for path in snapshot.paths():
            if not path.startswith(EVIDENCE) or not path.endswith(".json"):
                continue
            try:
                worker = json.loads(snapshot.read(path))
            except (ValueError, UnicodeError):
                continue
            if isinstance(worker, dict) and worker.get("kind") == "worker_result":
                workers.append((path, worker))
        bindings, checks, products = {}, [], {}
        for event_id in requested:
            require(event_id in events, "Requested raw event is absent")
            event = events[event_id]
            require(event.get("kind") == "blocker"
                    and engine.SOURCE_TASKS.get(event.get("task_id")) == event.get("family"),
                    "Only registered source-lane blocker events can be imported")
            candidates = [(path, worker) for path, worker in workers if _report_matches(event, worker)]
            verified = []
            for path, _worker in candidates:
                try:
                    verified.append(_verify_finish(reader, git_dir, head, event, path,
                                                   snapshot.read(path), products))
                except BindingVerificationError:
                    continue
            require(len(verified) == 1, "Exactly one immutable historical finish must verify the event")
            bindings[event_id], check = verified[0]
            checks.append(check)
    proof = {"schema": "autonomy_historical_product_bindings.v1", "bindings": bindings,
        "checks": checks, "verification": "actual Git finish, immutable worker result and committed scoped product",
        "counts_as_material_progress": False, "raw_events_modified": False,
        "task_states_modified": False, "acceptance": "NOT_PROVEN", "production_promoted": False}
    return VerifiedBindings(bindings, proof)


def binding_mutation(snapshot, prepared):
    """Replay against fresh authority; preserve all state except the registry."""
    state = snapshot.read_json(CONTROL)
    require(isinstance(state, dict), "Fresh control authority is missing")
    events = {item["id"]: item for item in state.get("material_events", [])}
    registry = state.get(REGISTRY, {})
    require(isinstance(registry, dict), "Binding registry schema must remain a mapping")
    updated = deepcopy(state)
    changed = False
    for event_id, binding in prepared.bindings.items():
        require(event_id in events and engine._hash(events[event_id]) == binding["event_sha256"],
                "Fresh raw event changed or disappeared after verification")
        require(events[event_id].get("task_id") == binding["task_id"]
                and events[event_id].get("family") == binding["family"], "Fresh event task/family mismatch")
        worker = binding["proof"]["worker_result"]
        content = snapshot.read(worker["path"])
        require(content is not None and digest(content) == worker["sha256"],
                "Fresh immutable worker evidence changed or disappeared")
        if event_id in registry:
            require(registry[event_id] == binding, "Never overwrite an existing historical binding")
        else:
            updated.setdefault(REGISTRY, {})[event_id] = deepcopy(binding)
            changed = True
    proof_content = encode(prepared.proof)
    prior_proof = snapshot.read(prepared.proof_path)
    require(prior_proof is None or prior_proof == proof_content.encode(),
            "Never overwrite immutable binding proof evidence")
    writes = {}
    if changed:
        require({k: v for k, v in updated.items() if k != REGISTRY}
                == {k: v for k, v in state.items() if k != REGISTRY}, "Only binding registry metadata may change")
        writes[CONTROL] = encode(updated)
    if prior_proof is None:
        writes[prepared.proof_path] = proof_content
    require(set(writes) <= {CONTROL, prepared.proof_path}, "Import writes must remain explicitly scoped")
    return Mutation(writes, {"binding_count": len(prepared.bindings), "proof_path": prepared.proof_path,
        "proof_sha256": digest(proof_content), "paths": sorted(writes),
        "counts_as_material_progress": False, "raw_events_modified": False, "acceptance": "NOT_PROVEN"})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path("."))
    parser.add_argument("--event", action="append", required=True, help="Historical raw source-blocker event ID")
    parser.add_argument("--apply", action="store_true", help="Import verified metadata using fresh CAS")
    args = parser.parse_args(argv)
    reader = GitStateStore(repository=args.repository, allowed_prefixes=(CONTROL, EVIDENCE))
    prepared = prepare_bindings(reader, args.event)
    if not args.apply:
        print(encode({"prepared": True, "proof_path": prepared.proof_path,
                      "proof_sha256": digest(encode(prepared.proof)), **prepared.proof}))
        return 0
    # Include proven worker paths for reads; their existing immutable bytes are
    # protected, and the reducer permits writes only to control + batch proof.
    workers = tuple(binding["proof"]["worker_result"]["path"] for binding in prepared.bindings.values())
    store = GitStateStore(repository=args.repository,
                          allowed_prefixes=(CONTROL, prepared.proof_path, *workers))
    result = store.transact(lambda snapshot: binding_mutation(snapshot, prepared),
        message="autonomy: bind historical source inputs; metadata is not material progress")
    print(encode({"state_commit": result.commit, "cas_attempts": result.attempts,
                  "changed": result.changed, **result.value}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
