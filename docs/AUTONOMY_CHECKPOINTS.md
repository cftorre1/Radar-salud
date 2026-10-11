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

## 3. Fenced leases, useful progress and bounded loops

Decision: six concurrent executor families have atomic 10-minute task leases,
60-second renewals, 3-minute missing-heartbeat detection and a 30-minute material
stall limit. Heartbeats and pickup do not count as material progress. Approval
revocation and relevant input changes fence old tokens. Unrelated staging commits
do not cancel a live worker.

Directed validation: `python -m unittest discover -s tests -p test_autonomy_engine.py -v`.
36 tests passed, covering independent claims, lost tokens, expiry, STALLED while
heartbeats continue, repeated/reordered blockers, globally repeated failures,
explicit acceptance proof, scoped non-regression and real-clock Stage A checks.
The four-hour evaluator test injects a clock; it is not live Stage A evidence.

Only a durable verified mutation, a new evidenced blocker, a verified closure, or
an actual independent task transition earns progress. Identical audits are capped
at three; unchanged blocked tasks remain open without synthetic progress.

Next hypothesis: hosted Actions can use the same lease/CAS contract and continue
another family immediately after a PASS or blocker, with independent candidate
review and explicit unresolved-task evidence.

## 4. Family workers and honest LIVE evidence

Decision: media, public data, fiscalization, mutualities, editorial and staging QA
have separate workers. Source probes run concurrently and call scoped recovery
even when fixtures pass. Pytest skips never constitute LIVE proof. Blockers retain
commands, URLs and log hashes; semantic identities exclude observation clocks.

Directed validation: `python -m unittest discover -s tests -p test_autonomy_lane_runner.py -v`.
13 tests passed. A real local staging media run executed 13 directed tests; DF and
Pulso returned proxy HTTP 403. Recovery reproduced both failures and recorded
external technical blockers without model calls. This is local network evidence,
not hosted source repair or coverage acceptance. Those source hosts are not in
the managed cloud network allowlist; no network bypass was attempted.

Next hypothesis: hosted workers can exercise their scoped public-source paths,
save a useful isolated candidate despite unrelated staging failures, and route it
to an independent reviewer rather than restart from the old tree.

## 5. Durable candidate review and exact context continuation

Decision: a separate executor validates the recorded isolated SHA and saves an
immutable review. Completed reviews bind future work to that candidate while
retaining the latest staging queue's approval, dependencies and constraints.
A moved ref, dirty checkout or changed relevant base produces an exact blocker;
there is no implicit merge, reset or promotion. Reviews never close source or
editorial acceptance merely because technical checks pass.

Directed validation: `python -m unittest discover -s tests -p test_autonomy_candidate_review.py -v`
and `python -m unittest discover -s tests -p test_autonomy_candidate_context.py -v`.
10 independent-review and 21 candidate-context tests passed with real bare Git
repositories and real validation subprocesses. They cover preserved candidate
code, scoped-base drift, unsafe/moved refs, review races and no model credentials.

Next hypothesis: the controller can dispatch review independently, select the
reviewed candidate on its next lease, and retain blockers without losing repairs
or inflating useful progress. Hosted credentials and pickup remain unproved.

## 6. Unpicked work and bounded stall recovery

Decision: actionable READY tasks become STALLED after thirty minutes without
pickup. The material-progress baseline survives expired/missing-heartbeat lease
generations and changing audit fingerprints. Three stalled lease recoveries are
the maximum; after the absolute material deadline, a recovery receives ten
minutes that heartbeat renewals cannot extend. Exhaustion records the actual
fenced lease evidence in a terminal blocker, while independent families remain
available. An unrelated staging SHA cannot reopen the exhausted episode.
Review wrapper timestamps/hashes do not change candidate-context eligibility;
the semantic review fingerprint does.

Directed validation: `python -m unittest tests.test_autonomy_engine tests.test_autonomy_candidate_context -q`.
65 tests passed: 43 engine tests and 22 candidate-context tests. They cover
thirty-minute unpicked work, dependency release, expiry/heartbeat recovery,
rotating audit outputs, bounded recovery grace, exact lost-lease blocker evidence,
ordinary twenty-minute useful work, and review wrapper churn. This is directed
state-machine and local Git evidence, not four hours of hosted acceptance.

Next hypothesis: hosted controller observations expose unpicked/stalled work and
automatically recover it with the same bounded leases, leaving other families
active when a lane exhausts its recovery budget.

## 7. Stable review identities and paid-call guard

Decision: a completed review of the same isolated SHA is reused without rerunning
gates or writing state/evidence. Review semantics exclude wrapper clocks and log
hashes. Optional model imports retain the existing package budget guard and
cannot authorize a paid call without the approved durable reservation.

Directed validation: candidate reviewer 12 tests, recovery 30 tests, engine and
candidate context 65 tests passed. These checks execute local Git transactions
and validation subprocesses. They do not establish hosted pickup or Stage A.

Next hypothesis: a shared staging-failure capture contract will keep controller
and worker evidence revisions identical and avoid fencing a healthy repair.
