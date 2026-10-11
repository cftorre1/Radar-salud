# Autonomy architecture checkpoints — 2026-10-11

Scope: infrastructure only on main. Product candidates remain isolated from production.
Required policies, queue and learning ledger were read at staging
`cadb6c2d1f3c286a0dbeea3d236f6f10d47df2bb`; they are absent from main.

## 1. Conflict-safe durable state

Decision: replace snapshot rebases with optimistic Git compare-and-swap. Every retry
reads the new remote head and runs the reducer again, including lease checks.
Evidence paths are immutable and commits stage explicit paths only.

Directed validation: `python -m unittest discover -s tests -p test_autonomy_state_store.py -v`.
Nine tests passed, including a real concurrent push to a local bare Git repository,
preservation of both independent writes, fencing revalidation and exhausted retries.
This proves local Git behavior; it does not prove hosted Actions credentials.

Next hypothesis: atomic claims and expiry checks prevent an old worker from recording
results after a new worker takes its lease; live authentication must be verified.

Acceptance Stage A remains unproven. No four-hour useful-progress window is claimed.

## 2. Structured recovery and independent candidate durability

Decision: exact JSON edits use file hashes and unique old-content preconditions,
with atomic validation, no generated unified diff. Protected policy, QA and test
contracts remain outside model write scope. LIVE failures get a scoped probe;
external access failures produce evidence rather than fictional parser repairs.

Directed validation: `work/venv/bin/python -m unittest discover -s tests -p test_autonomy_recovery.py -v`.
28 tests passed. A real temporary staging repository reproduces an assertion,
applies the exact source repair, reruns targeted and full checks, and stages only
the validated file. Additional checks preserve an isolated verified repair when
an unrelated baseline full-suite failure remains, without granting acceptance.

Existing staging gate was independently reproduced on `cadb6c2d…`:
`test_normative_v2_recurates_all_visible_acts_and_routes_opaque_titles_to_review`
still fails `11 >= 12`. The test was not changed. This observation does not prove
missing content and is not a basis to weaken the gate or invent a twelfth row.

Model calls are disabled by the current `config/autopilot.json` policy. Future
model use additionally requires a durable approved shared budget reservation;
ephemeral local usage counters cannot authorize concurrent paid calls.

Next hypothesis: workers can retain directed, non-regressing candidate repairs
while global QA is blocked; a separate candidate reviewer must consume the pinned
candidate instead of silently returning to the old staging tree.
