"""Publication test gate for daily-radar.yml (step "Core deterministic tests before collection").

The step runs the whole deterministic suite once (``pytest --junitxml``) and this script decides
whether its failures block publication, using config/publication_test_policy.json:

* every test is publication-critical (blocking) unless its file is listed in ``non_blocking_files``;
* a listed file whose name contains a ``protected_name_fragments`` word is ignored (stays blocking);
* failures in listed files are reported as warnings and in the step summary, but do not block;
* anything unexpected fails CLOSED: pytest exit code other than 0/1 (interrupted, internal error,
  usage error, no tests), a missing/unreadable JUnit report, exit code 1 with no failure recorded,
  a failure that cannot be mapped to a test file, or an unreadable policy.

Standard library only. Exit code 0 = publication may proceed, 1 = blocked.

    python scripts/publication_test_gate.py --junit core-tests.xml --pytest-rc 1 --policy config/publication_test_policy.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

DEFAULT_POLICY = "config/publication_test_policy.json"


def load_policy(path: str | Path) -> tuple[frozenset[str], list[str]]:
    """Return (effective non-blocking files, warnings). Raises on an unreadable policy."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    fragments = [f.lower() for f in data.get("protected_name_fragments", [])]
    allowed, warnings = set(), []
    for entry in data.get("non_blocking_files", []):
        name = Path(entry).name.lower().removeprefix("test_")
        hit = next((f for f in fragments if f in name), None)
        if hit:
            warnings.append(f"{entry}: name contains protected fragment '{hit}'; kept blocking")
        else:
            allowed.add(entry)
    return frozenset(allowed), warnings


def test_file_of(classname: str, name: str) -> str | None:
    """Map a JUnit testcase to its test file. pytest derives ``classname`` from the node id
    (``tests/pulso/test_x.py::TestC::test_y`` -> ``tests.pulso.test_x.TestC``); collection errors
    have an empty classname and the module path in ``name``."""
    dotted = classname or name
    parts = dotted.split(".") if dotted else []
    for i, part in enumerate(parts):
        if part.startswith("test_") or part.endswith("_test"):
            return "/".join(parts[: i + 1]) + ".py"
    return None


def failures_from_junit(path: str | Path) -> list[dict]:
    """Every failed or errored testcase as {file, id, message}."""
    root = ET.parse(path).getroot()
    out = []
    for case in root.iter("testcase"):
        bad = [c for c in case if c.tag in ("failure", "error")]
        if not bad:
            continue
        classname, name = case.get("classname", ""), case.get("name", "")
        out.append({
            "file": test_file_of(classname, name),
            "id": f"{classname}::{name}" if classname else name,
            "kind": bad[0].tag,
            "message": (bad[0].get("message") or "").splitlines()[0][:200] if bad[0].get("message") else "",
        })
    return out


def decide(pytest_rc: int, failures: list[dict] | None, non_blocking: frozenset[str]) -> tuple[bool, str, list, list]:
    """Return (blocked, reason, blocking_failures, non_blocking_failures)."""
    if pytest_rc == 0:
        return False, "all_tests_passed", [], []
    if pytest_rc != 1:
        return True, f"pytest_exit_{pytest_rc}", [], []
    if failures is None:
        return True, "junit_report_unreadable", [], []
    if not failures:
        return True, "pytest_failed_without_recorded_failure", [], []
    blocking = [f for f in failures if f["file"] is None or f["file"] not in non_blocking]
    tolerated = [f for f in failures if f not in blocking]
    if blocking:
        return True, "publication_critical_failure", blocking, tolerated
    return False, "only_non_blocking_failures", [], tolerated


def _annotate(level: str, title: str, f: dict) -> str:
    text = f"{f['id']} - {f['message']}".replace("\n", " ").replace("%", "%25")
    return f"::{level} title={title}::{text}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--junit", required=True)
    ap.add_argument("--pytest-rc", type=int, required=True)
    ap.add_argument("--policy", default=DEFAULT_POLICY)
    args = ap.parse_args(argv)
    try:
        non_blocking, warnings = load_policy(args.policy)
    except Exception as exc:  # unreadable policy: everything blocks
        non_blocking, warnings = frozenset(), [f"policy unreadable ({type(exc).__name__}); every test blocks"]
    try:
        failures = failures_from_junit(args.junit)
    except Exception:
        failures = None
    blocked, reason, blocking, tolerated = decide(args.pytest_rc, failures, non_blocking)
    lines = [f"::warning title=Publication test policy::{w}" for w in warnings]
    lines += [_annotate("error", "Core test (blocks publication)", f) for f in blocking[:20]]
    lines += [_annotate("warning", "Core test (internal tooling, non-blocking)", f) for f in tolerated[:20]]
    if blocked and not blocking:
        lines.append(f"::error title=Core test gate::{reason} (pytest exit {args.pytest_rc}); publication blocked")
    print("\n".join(lines + [f"publication_blocked={'true' if blocked else 'false'}", f"reason={reason}"]))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("### Core tests before collection\n")
            fh.write(f"Decision: {'BLOCKED' if blocked else 'PASS'} ({reason}); pytest exit {args.pytest_rc}.\n\n")
            for label, rows in (("Blocking failures", blocking), ("Non-blocking failures (internal tooling)", tolerated)):
                if rows:
                    fh.write(f"{label}: {len(rows)}\n\n" + "".join(f"- `{r['id']}`\n" for r in rows[:50]) + "\n")
    return 1 if blocked else 0


if __name__ == "__main__":
    sys.exit(main())
