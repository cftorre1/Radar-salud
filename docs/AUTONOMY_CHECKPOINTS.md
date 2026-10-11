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

## 8. Shared demonstrated-failure input

Decision: controller and worker use the same read-only GitHub failure capture.
It validates the staging preview identity, ignores cancelled supersessions and
normalizes failed test names before hashing. An identical run now has identical
evidence revision in both executors; observation wrappers do not create retries.

Directed validation: 9 failure-input tests passed. The independent reviewer also
replayed a captured real failure log and confirmed that controller and worker
inputs leave a running lease intact. Runtime integration currently has 13 tests
passed, including real local Git pickup, durable mutation and next-family pickup.
Those are local fixtures, not hosted Stage A evidence.

Next hypothesis: pinned repair candidates that are later safely integrated into
staging can continue into genuine post-merge runtime acceptance without a false
closure on the isolated branch or loss of the durable candidate.

## 9. Source closure after staging integration and actual runtime

Decision: the `source_recovery_reconciliation_gate_2026_10_11` added to staging
in `24d4c1a8d6a70d73324207b33985378aeff36142` applies to all source families.
An isolated commit or PR remains candidate evidence. Source closure requires the
existing reviewed acceptance manifest, `staging_merge_sha` matching the actual
input SHA, and that SHA incorporated into the recorded current `origin/staging`.
Missing staging references fail closed. The runner does not fetch, merge or
promote any product change while checking acceptance.

The manifest additionally requires `runtime_after_merge_pass` and a hashed
evidence reference with `kind=runtime_after_merge`. Its JSON declares the same
`staging_sha`, `execution_after_merge=true`, and a trace covering every source in
the family. Each entry records the matching source/SHA, an operational outcome
(`published`, `rejected` or `genuine_absence`), source URL, substantive runtime
evidence, execution command and an exact hashed source log. The log must bind
the source, URL, outcome and SHA. Exit-zero metadata alone cannot close a source.
The prior 30/90-day reconciliation, publication trace, health, QA and independent
review checks remain required.

Directed validation: `python -m unittest discover -s tests -p test_autonomy_lane_runner.py -v`.
18 tests passed. Real local Git ancestry tests reject an unincorporated candidate
despite a complete manifest and accept the matching incorporated SHA only with
complete post-merge runtime evidence. Negative cases cover unavailable staging,
wrong merge/runtime SHA, missing after-merge execution, incomplete family traces,
metadata-only traces and mismatched logs. Controlled test source artifacts do
not constitute hosted LIVE evidence or source-repair acceptance.
Source recovery also binds its actual hashed LIVE gate and directed tests to the
specific failed source, so a repaired claim cannot rely on unrelated PASS logs.

Next hypothesis: hosted source executors can record this post-merge provenance
and independently reviewed operational outcome for each source; until then
candidate commits remain useful work and source tasks remain open.

## 10. Verified failure repair required for Stage A

Decision: an evidenced blocker remains material progress and can trigger an
independent transition, but Stage A requires a real failure actually repaired
by a verified durable mutation. A partial staging candidate that retains the
failed gate earns mutation credit without a repaired label. Source repairs bind
the failed source slug to hashed executed LIVE and directed PASS gates. Legacy
optimistic repaired labels on failed partial candidates do not pass acceptance.
Stopping with real blockers while the remaining lanes continue is valid operation
and remains NOT_PROVEN for Stage A.

Directed validation: `python -m unittest tests.test_autonomy_engine -q`.
47 engine tests passed. Four-hour evaluator fixtures distinguish repaired PASS
from an otherwise complete blocker-only window, preserve blocker material credit,
and reject partial staging or unrelated-source repaired claims. Injected clocks
and controlled artifacts remain test evidence, not live four-hour acceptance.

Next hypothesis: hosted executors can produce a genuine target-bound repaired
failure event, followed by four real hours of useful autonomous progress.

## 11. Executable controller and incorporated candidate continuation

Decision: the controller and each independent worker perform lease, heartbeat,
candidate publication and finish through the same replayed Git transactions.
A failed/expired worker keeps its immutable diagnostics without altering a new
owner's task. Approved candidates stay isolated; the executor never promotes a
product ref. A later authorized staging integration is recognized by actual Git
ancestry, rechecked before execution, and resumes on the current staging SHA.
Unincorporated candidates preserve their pinned branch and review context.

Local initialization is simulation. Hosted activation starts a new live window
without carrying earlier fixture events; local reads cannot downgrade a live
window. Four-hour acceptance still requires genuine hosted evidence.

Directed validation: state store, candidate context and runtime integration ran
51 tests PASS: 9 + 27 + 15. Real local Git authorities verify durable isolated
mutation, explicit verified PASS/blocker followed by independent pickup,
conflict-safe writes, stale-token fencing, unpicked STALLED observations,
protected production refs and exact incorporated-candidate continuation.

Next hypothesis: the main workflow triggers can exercise this already committed
runtime on GitHub, with independent families continuing despite staging QA.

## 12. Source governance enforced at the reducer boundary

Decision: legacy source PASS reports cannot bypass staging/runtime requirements.
The reducer requires the verified task/SHA-bound staging merge and hashed
post-merge runtime proof that the runner has checked against actual Git ancestry.
A pre-merge parser fix remains a useful isolated mutation with
`candidate_failure_resolved`; source repair is credited only after verified
post-merge closure. Preserved real failure evidence links that eventual closure
to the original failure. Partial candidates cannot bypass this rule.

Directed validation: 53 engine tests passed. They reject generic legacy source
closures and optimistic pre-merge repair events while accepting verified
post-merge source closure and unchanged full-PASS staging recovery. Four-hour
fixtures test the evaluator contract only; live acceptance remains unproven.

Next hypothesis: owner-intervention observation and actual JSON content hashes
can make the four-hour evaluator resistant to empty counters and timestamp churn.

## 13. Semantic file mutation rather than regenerated JSON clocks

Decision: raw bytes remain diagnostic evidence. Material file fingerprints parse
JSON and discard only explicit observation fields, preserving publication dates,
effective dates, deadlines, source content and substantive hashes. Formatting or
clock-only changes cannot enter candidate publication or earn mutation credit.
Non-JSON source changes retain their byte identity; invalid JSON is explicit.

Directed validation: 23 runner tests passed. Real temporary Git repositories
show changed raw hashes but unchanged material identity for generated-at and
format churn, while changed titles, publication dates and source code remain
material. The independent review reproduced the original timestamp defect and
confirmed its correction.

Next hypothesis: hosted material events can retain meaningful code/content
changes without treating recurring export/audit observations as useful progress.

## 14. Observed owner continuity rather than empty counters

Decision: Stage A requires a verified immutable owner observation covering the
entire actual window in both GitHub Actions and owner prompt events. Empty
restart/prompt arrays cannot attest zero intervention. Missing, partial, future,
unsafe or unhashed observation evidence explicitly keeps acceptance NOT_PROVEN.
No event collector or zero-prompt attestation is fabricated. A trusted Work/chat
event source remains an acceptance instrumentation blocker, not a repair-lane
blocker.

Directed validation: 58 engine tests passed, including five new observation
tests and negative subcases. Clock-injected positive fixtures include explicit
test observations; they remain local test evidence. Live owner absence and
four actual hours remain unproven.

Next hypothesis: automatic GitHub pickup and real repair evidence can be
observed after infrastructure publication while a trusted prompt-event observer
provides the independent continuity proof required for Stage A.

## 15. Main autonomy workflow activation

Decision: only the planning job is serialized. Six family workers and independent
candidate review jobs use separate concurrency groups, with fail-fast disabled.
Main push, ten-minute schedule and completion/explicit wakeups use the committed
runtime. Audit and recovery wrappers dispatch work rather than writing mutable
audit timestamps. Controller and worker share the exact failure input contract.
Completion wakes the controller immediately; no whole-run concurrency gate
serializes independent repairs. Production deployment remains manual and untouched.

Directed validation: actionlint 1.7.7 passed all five changed/new workflows and
git diff --check passed. These are syntax/static integration checks. Hosted
dispatch, secrets/platform access and actual four-hour continuity remain unproven
until the infrastructure payload is published and observed.

Next hypothesis: an authorized fast-forward main infrastructure push starts
parallel hosted pickup and evidence transactions without deploying product bytes.
