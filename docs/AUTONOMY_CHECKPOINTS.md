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

## 16. Relevant retries and committed semantic inputs

Decision: unrelated staging SHAs update observed authority without reopening
scoped blocked or repeatable closed tasks. New acceptance artifacts, repair
plans, declared executor/source inputs and approval authority remain meaningful
even under a fixed evidence token. Legacy unscoped SHA changes remain relevant.
The global three-attempt failure guard cannot be reset by a new run or clock.

QA fingerprints cover committed snapshots, UI, validation build scripts and
explicit product contracts. JSON uses content semantics, preserving actual
publication dates while excluding observation churn. Working-tree bytes never
replace committed authority. Source parser families retain independent scopes.

Directed validation: engine and candidate context ran 93 tests PASS (66 + 27);
runtime ran 17 PASS. Real Git regressions cover unchanged global heads, genuine
scope changes, artifact/patch additions under a fixed token, snapshot/config/UI
changes, ignored export clocks and unchanged independent parser fingerprints.

Next hypothesis: the final hosted payload retries only on actual new repair or
acceptance inputs, and continues other families when the same fault is blocked.

## 17. Final independent verification and publication checkpoint

Final code reviewed: `250c650f2ba00d2066506e61f03b3e730ca69b6c`.
The independent suite passed 193 tests in 34.850 seconds. Actionlint passed all
five autonomy workflows. Twenty independent checks confirm relevant retries,
fenced leases, durable candidate continuation, material content identity and
strict source/owner acceptance. Product bytes and original gates are unchanged.
The committed JSON verification records code-file hashes and exact proof limits.

Actual staging remains blocked by eleven normative rows against the unchanged
twelve-row test at `73aff5c…`. No content was invented and no gate relaxed.
Local source access is restricted by the managed cloud allowlist; paid model
repair is disabled by policy. Hosted access and recovery have not been observed.
Four real hours and complete owner-event observation remain NOT_PROVEN.

Next hypothesis: publishing this concrete, reviewed infrastructure payload to
the explicitly authorized main ref starts useful hosted pickup while independent
work continues. If platform approval/authentication blocks publication, retain
all commits, a patch, a Git bundle and the exact continuation instructions; never
substitute local fixture success for hosted acceptance.

## 18. Automatic publication approval blocker and preserved continuation

The normal main push of the reviewed `620e156` checkpoint was rejected before
execution by automatic approval review. Its stated reason: authorization for
main autonomy workflows does not clearly cover the complete sixteen-commit
infrastructure code/docs/tests payload and its external publication/automation.
No connector, alternate branch or indirect publication bypass was attempted.
Main remains unchanged by this front. The branch contains only infrastructure,
tests and documentation; the existing deployment workflow remains manual.

Explicit approval of this concrete public main infrastructure payload is the
remaining publication requirement. The patch and Git bundle preserve every
checkpoint; the final verification identifies the tested code and exact limits.
After approval, verify the remote main head, use a normal fast-forward push,
then observe actual `control_v2.json`, worker evidence and independent transitions.
Do not count Actions conclusions as progress or invent owner-event coverage.

Directed validation of this metadata-only checkpoint: JSON parse and
git diff --check. The code remains the independently reviewed `250c650` version
with 193 tests and five workflows validated. No hosted acceptance is claimed.

Next hypothesis: approval of the full reviewed payload removes the publication
blocker; hosted pickup can then be measured while the existing independent
source/provider Work fronts continue in their isolated branches.
## 19. Publish approved infrastructure and isolate unused credentials

The owner explicitly authorized public main publication of the complete seventeen
infrastructure commits and workflow activation. The normal fast-forward push of
`b6794bf` succeeded at 2026-10-11T05:28:53Z. Controller run `38114913138` started
from that push and actual canonical state recorded six distinct family claims
between 05:29:46Z and 05:30:03Z. Existing production deployment remains manual.

The requested pre-push validation repeated all 193 autonomy tests successfully
with the documented venv (17.550 seconds), actionlint 1.7.7 accepted the five
workflows, and twelve continuity artifact hashes plus the incremental bundle
restoration passed. The default interpreter lacks pytest; its separate initial
failure log is retained and is not represented as a passing environment.

Hosted repair workers no longer inject the unused existing model credential.
Current policy disables paid model repair. Removing that credential also keeps
global deterministic validation from enabling unrelated eight-source integration
tests based only on the presence of an API key. No credential was added or
revoked, no gate was changed and source-family LIVE probes remain separate.

Directed validation: actionlint for repair-lanes.yml; inspection that the job
environment has no OPENAI_API_KEY and that original product tests are unchanged.
Next hypothesis: bounded source evidence must survive log truncation, and a
corrected executor must automatically retry an infrastructure-blocked task when
its relevant executor implementation changes. Hosted four-hour acceptance remains
NOT_PROVEN; the owner prompt-event observer is still unavailable.
## 20. Observe independently and exercise real heartbeat failure safely

The observer runs as a separate job after planning. Its failure cannot suppress
six-family dispatch. It pins Git queue/ledger blobs, infrastructure and staging
SHAs, reads fresh canonical state inside CAS, publishes queue/PMO projections and
deduplicated learning records, and leaves approvals, material events and product
refs intact. Work/chat owner followups remain unknown, so neither green Actions
nor empty counters can validate four-hour acceptance.

The heartbeat canary uses the existing engine/store in a separate namespace and
a fixed single episode. A real later observation must detect the omitted
heartbeat, reclaim a new generation and reject the old token. It labels every
record as infrastructure fault injection and excludes those records from useful
work and source LIVE evidence. Terminal calls validate immutable proof and do
not write again.

Directed validation: fifteen canary tests, including actual bare-Git conflict
replay, preserved product/live control, bounded episode and environment guards;
observer tests cover fresh CAS replay, projections, token hashing and truthful
owner/acceptance limitations. Actionlint validates the independent job wiring.
Next hypothesis: the first real hosted canary reaches STALLED after at least
three actual minutes and publishes a fenced recovery proof while ordinary repair
families continue independently.

## 21. Correct observed transport and retry scope defects

The twelve post-publication infrastructure checkpoints are isolated and reviewed
against b6794bf. They fix browser-gate reproduction, child credential isolation,
structured source parsing before bounded logs, explicit no-pickup reports, and
the real first-pickup acceptance clock. The executor revision now permits a
bounded retry after committed runner/recovery changes while product identity
remains independent for candidate context and historical failure budgets remain
intact. Docs, observations, canary updates and dirty working files cannot reopen
those source tasks.

Directed tests include exact offline transport replay of the real SUSESO failure;
it preserves RuntimeError bounded_probe_budget and never claims LIVE PASS. The
complete corrected code at 4b07e433 passed 244 autonomy tests in 39.160 seconds;
actionlint 1.7.7 passed all five workflows. Product and original gates are
unchanged. Each individual test log, commit, decision and next hypothesis is
preserved under work/prepush-20261011 and work/live-review.

Next hypothesis: publishing this exact corrected executor dispatches another
actual task automatically, preserves its complete failure evidence, records a
real independent transition and keeps the scoped staging blocker isolated. The
canary must wait for actual elapsed time. Four useful hours and owner event
coverage remain NOT_PROVEN.

## 22. Verify real hosted transport recovery and isolated STALLED

The corrective publication `dd2d206` started controller `38115967398` at
05:48:09Z. Six families acquired new fenced leases after the relevant executor
revision, renewed heartbeats and produced six independent task transitions.
The original first-pickup clock was retained. Completion and scheduled audit
controllers did not receive material credit for their green conclusions.

Real fiscalization job `114400854282` now extracts SUSESO structured evidence
from the same 55,588-byte capture that the previous worker truncated before
parsing. Both captures hash to
`17511ebd09faf49db9ae7ef295c73173d0cbacf4a2372423c3ae2327ca63e18e`.
Sixteen directed source tests PASS. The original baseline still has 265 PASS,
one FAIL and one SKIP; the historical executor reported BLOCKED because it lacked
a supported bounded repair strategy. This implementation limitation is addressed
in checkpoint 27. This proves infrastructure transport recovery, not source closure.

The separate hosted canary reached STALLED after 183.402066 actual seconds,
reclaimed a new generation and rejected the old worker. All six checks PASS;
later observations verified the immutable proof and wrote no duplicate result.
Canary control is isolated from live source tasks. Fault injection is expressly
excluded from useful progress, source LIVE and four-hour acceptance.

Directed evidence: `work/continuity/recovery-before-after.json` and
`work/continuity/canary-proof.json`, with canonical hashes and run/job IDs.
Next hypothesis: a real new staging failure is escalated through the family
lease without corrupt-patch or state-write loops and leaves independent lanes free.

## 23. Preserve canonical governance and compare old/new recovery

CAS publication `c4819844` updates only the two authorized autonomy task records,
PMO autonomy metadata, one learning incident and an immutable acceptance snapshot.
The current Work 3 staging metadata was preserved. Seven targeted PMO tests PASS.
No product byte, gate, existing task constraint, readiness or validated block
was changed. The historical snapshot remains pending live acceptance.

That metadata commit triggered a real preview run `38116961282`: the unchanged
gate again failed `assert 11 >= 12` at 06:06:45Z. New recovery `38116996270`
dispatched only staging_qa. Worker `38117002323` claimed at 06:07:52.299198Z,
renewed its lease and ended BLOCKED with actual QA, Reviewer, browser and missing
acceptance evidence. The competing controller worker returned NO_EXECUTABLE_TASK
without claiming. Later controllers skipped repair on unchanged inputs.

The previous recovery run `38113859321` failed at corrupt patch line 11 and then
lost a Git ref race. Earlier runs failed at corrupt lines 9 and 10. The new
existing recovery workflow replaces that diff-writing mechanism with a bounded
family dispatch; the old patch writer is no longer a parallel execution path.
Wrapper SUCCESS means dispatch only. No product repair or production promotion
is asserted. Raw immutable history and original failure evidence remain visible.

Next hypothesis: metadata-only run identities cannot make the identical failed
QA problem earn another blocker credit; genuine new assertion evidence can.

## 24. Repair demonstrated duplicate material credit

Comparison of the two real QA episodes found one invalid extra blocker event:
`f6682fbf21e28a62f0333785de12f199ec8b884a0136d612d3ef30f1e21eb12f`.
Run/task IDs, candidate metadata SHA and raw capture hashes changed while the
demonstrated failure, product identity and structured problems remained equal.
Historical browser aggregates cannot establish individual assertion equality;
an opaque raw-hash change alone cannot justify new material novelty.

Five isolated commits repair the defect: `bc0dff4`, `8262cad`, `fd5408c`,
`e214243` and `9244340`. Canonical problem identity preserves actual assertions,
URLs, source content, publication dates and product changes. Only bound transport
aliases and diagnostic clocks are removed. Browser failures now retain concrete
case/error details. The append-only correction binds both immutable raw events
by hashes and demonstrated product/problem; malformed corrections fail closed.
Raw history is preserved. Observer and acceptance consume verified effective
events, and the affected material watch returns to its real last transition.

Directed validation: 76 engine tests, 16 observer tests and 29 runner tests PASS;
complete suite 259 PASS in 25.682 seconds. Actionlint 1.7.7 PASS on all five
workflows. Independent scope/security review confirms only infrastructure and
tests changed, with product, original gates and deployment intact. The 35-commit
code bundle restored the exact complete tree from the original main base.
Publication `9244340` started hosted controller `38118016823` at 06:25:34Z.

Next hypothesis: hosted planning applies the hash-bound correction automatically,
keeps the original acceptance clock and continues only relevant independent work.
The final pinned result and exact external continuation are recorded in the
verification JSON and `work/continuity/hosted-evidence.json`; neither documentation
nor a successful workflow counts as material progress or four-hour acceptance.

## 25. Repair demonstrated source-credit and guard classification defects

The third hosted episode produced four additional source blocker credits without
new demonstrated problems. Diagnostic clocks, capture hashes, request ordering
and producer-version changes were the cause. Four genuine source pairs and the
fourteen newly recorded QA/browser cases were compared separately. The QA evidence
is retained; it is new evidence of existing failures, not a repaired regression.

Isolated commits `3d692dd`, `2492254`, `ec05e1f`, `01cc158` and `ce40f5a`
canonicalize evidenced source problems and classify the exact bounded-probe guard
as incomplete instrumentation coverage. Independent HTTP/Unicode/parser errors
remain real failures. Arbitrary text mentioning the guard is not suppressed.
Unknown source structures fail closed. Source inventories, actual URLs/statuses,
dates, assertions and semantic content remain significant. Raw history and gates
are unchanged; pure internal coverage exhaustion is not counted as source repair.

Directed validation: 94 engine tests, 36 runner tests plus 51 subtests, and
18 observer tests PASS. Independent four-pair historical replay and seven
tampering checks PASS. Evidence is pinned in the final verification and hosted
snapshot; local replay is expressly offline and earns no live progress.

Next hypothesis: the first hosted plan automatically retires only the four false
source credits, retains the existing QA correction and real new QA evidence,
and source guard normalization alone earns no new material credit.

## 26. Bind historical evidence through actual Git provenance

Isolated commit `5785223` adds a conflict-safe legacy binding importer. It verifies
each immutable worker result, unique original raw event, finish commit and parent,
task/family/input SHA and actual product fingerprint derived from committed blobs.
It never infers an old product from today's task or accepts a supplied verified
attestation. Ten real-Git tests PASS, including idempotence and invalid provenance.

Actual CAS `46fbcc6675f215ffb7f45522065b82afa2a8d26e` imported eight bindings and
one immutable proof. All other control bytes, tasks, leases, history and ledger
were preserved. Binding metadata is not material progress. Final independent
replay keeps 58 raw events, projects 53 effective events after five corrections,
preserves eleven transitions, the original pickup clock and new fourteen-case
QA evidence. The hosted correction proof is recorded separately; offline counts
do not certify GitHub application.

Next hypothesis: concurrent hosted writers retain this registry and all raw
events while planning appends verified corrections, without force pushes.

## 27. Repair the missing deterministic executor capability

Policy and task inspection found that bounded reversible source repair is already
approved. Earlier checkpoint wording about a missing approved plan described the
executor's limitation and must not be read as a new Toba permission requirement.
The lack of acceptance_artifact still prevents closure; it does not prevent
starting already approved repair. No paid model is enabled.

Isolated commits `436cc20`, `b01a8c0`, `998f1c5` and `f2ec534` add a read-only
planner for the actual ACHS non-ASCII URI failure and integrate it ahead of the
optional model. It checks exact candidate SHA, task approval, source AST and
preimage, then generates bounded JSON. Unknown problems are reported as
executor_capability_missing before scope rejection; recognized unauthorized
repairs fail closed. Existing recovery applies only inside an isolated candidate
and keeps all directed, source LIVE, full QA, Reviewer and rollback requirements.

Directed validation: sixteen planner tests, 41 recovery tests and 26 runtime
tests PASS. The stdlib HTTP URI failure is reproduced before encoding, and
Unicode authority, ASCII controls, pre-existing percent escapes and unrelated
bytes remain protected. A generated plan is not mutation/repair evidence.

Next hypothesis: hosted mutual-source execution attempts this recognized repair
without owner restart; an unmet LIVE or QA gate rolls back and records the actual
failure while unrelated families continue. No product promotion is authorized.

## 28. Preserve history while evaluating a current real acceptance window

Isolated commit `0b8b87d` selects the latest actual four-hour window while keeping
the original first pickup and full history. Earlier work, stalls and prompts
remain visible and cannot supply missing gates inside a later window. Mutation,
verified source repair, independent transition, maximum material gap and complete
Actions/owner coverage are still required in that same window. Five new directed
window tests are included in the 94 passing engine tests; future, malformed and
simulated observations fail closed.

All eleven corrections were dependency-ordered before publication only; the
final tree is unchanged and public history was not rewritten. Complete frozen
code `ce40f5afaad0efb1efec3a010db86d9eb1e9d676` passed 316 tests in 37.305 seconds
and actionlint 1.7.7 on five workflows. Independent final scope review passed
all 46 commits/32 infrastructure paths, with zero credential findings and no
product, original-gate or production-deployment changes. The 46-commit bundle
restored the exact complete tree from the original main base.

Normal fast-forward publication started hosted controller `38120110728` at
07:03:52Z. Acceptance remains NOT_PROVEN; actual outcome, UTC, immutable hashes,
raw/effective counts and limits are in work/continuity/hosted-evidence.json.
Next hypothesis: the new real episode verifies correction, classified evidence,
automatic relevant pickup and bounded repair behavior without false progress;
the external owner-event channel still requires trustworthy complete coverage.

The first new hosted plan `c58db62d` at 07:04:08.198661Z verified the exact
58-to-53 projection, unchanged raw history/eight bindings and six organic
no-material-progress STALLED detections without credit. Actual mutual finish
`1522674e` at 07:06:00.551910Z attempted both recognized ACHS repairs. Requests
passed in the candidate; zero dated/verified detail items still failed LIVE, so
both attempts rolled back with no changed paths or material mutation. Other
families continued independently. These are real hosted proofs with the exact
limits recorded; they do not validate Stage A or four useful hours.

## 29. Remove capability-label credit without losing independent evidence

The fourth real hosted episode ended with raw62/effective57, 25 pickups and
twelve actual transitions. Two additional blocker credits were invalid: public
data and QA had only acquired a typed UNSUPPORTED diagnostic while their
demonstrated source, normative and fourteen browser-case failures were unchanged.
The actual ACHS repair attempt and failed LIVE/rollback evidence were distinct and
are retained. Metadata is not a new product/source failure.

Isolated commits `4731574` and `c4417f1` normalize only the exact unsupported
no-plan/no-execution capability envelope and verify redundant source-output bytes
against the recorded serializer, hashes, count and suffix. Independent review
initially found that arbitrary assertion text could disappear beside parsed
source JSON; the second commit fixes that demonstrated negative case. Unknown
fields, plans, rejection, paid attempts, source facts, baseline assertions and
extra diagnostic text remain meaningful. The canonical engine controls novelty
even when a legacy producer hash is opaque. Raw events are never rewritten.

Directed validation: 106 engine tests PASS; independent 46 actual-envelope and
eleven extra source-output negatives PASS, five hash/count/assertion tampering
cases rejected and 25 independent directed tests PASS. Pinned actual2e7658 replay
preserves raw62, projects55 with seven corrections, retires only the two extra
credits, preserves the prior five corrections/eight bindings and is idempotent.
No offline replay earns material or LIVE acceptance credit.

Next hypothesis: the next real hosted plan appends those two corrections without
new claims or repeated diagnoses because execution inputs remain unchanged.

## 30. Distinguish identical Git convergence from a durable new write

The first complete follow-up suite exposed two missing-pytest failures from an
incorrect root interpreter and a genuine store telemetry defect. The recovery
tests passed under the repository venv. A deterministic real-Git reproduction
then confirmed that a second identical commit can push successfully as up-to-date
while the store falsely returns changed=true.

Isolated commit `cc0b715` reads the exact target-ref porcelain result: `=` is a
no-op; ordinary fast-forward/new-ref updates are writes; unknown, missing or
duplicate success statuses fail closed. It preserves normal fast-forward CAS.
The canary race uses distinct actual-run identities to force different candidates
and retains its exact attempts[1,2] assertion. A separate fixed-date identical
candidate test proves same SHA, attempts[1,1], only one changed write and one
immutable episode. Eleven store and fifteen canary tests PASS. No gate is weakened.

Frozen code `c4417f1959227444f2f841a0e0c534f25d245e99` passed 330 tests in 28.391
seconds using `.venv/bin/python`, actionlint 1.7.7 on five workflows and fifteen
independent critical contracts. Full diff review covers 49 commits/32 autonomy
paths with zero credential findings and unchanged product, original gates and
production deployment. The 49-commit bundle restored the exact complete tree
from the original main base; earlier bundles remain preserved.

Normal fast-forward publication started controller `38121721113` at 07:32:35Z.
Next hypothesis: verified hosted correction preserves all raw evidence and
transitions while the corrected store reports writes honestly. Acceptance stays
NOT_PROVEN; the pinned result and exact continuation are in the final evidence.

The actual fifth first plan `a703892e` at 07:32:52.798673Z applied exactly the two
additional corrections: raw62 unchanged, effective55, seven corrections, eight
historical bindings, 25 pickups and twelve transitions. The subsequent observer
commit `a7495354` changed only four observation metadata paths and retained the
same control blob. Repair and candidate jobs were SKIPPED with unchanged inputs;
no new claims, mutation or audit-loop credit occurred. Independent verification
checked all eight immutable evidence references and their Git blob/SHA256 hashes.
The actual observed window ended at 07:33:14.686220Z: 7,408.454723 seconds with a
2,216.775938-second maximum material gap. Neither meets four useful hours or the
unchanged thirty-minute gap gate. Owner coverage remains unverified.

## 31. Retain independent errors beside incomplete recovery diagnostics

Independent final review reproduced a remaining false-negative: an additional
assertion beside the historical fiscalization recovery source JSON disappeared
when the outer source coverage was incomplete. The previous filter omitted every
automated_recovery component under that condition. This was an infrastructure
identity defect, not a newly observed hosted publisher failure.

Isolated commit `fc03cfb` replaces that broad omission with a strict recognizer
for the exact unexecuted guard diagnostic. Serializer/capture hashes bind the
source output. The known legacy baseline and context use documented provenance
digests; only pytest duration is ignored. Unknown fields, extra outputs/assertions,
changed baseline/context, additional gates, planned/paid/candidate/rejected work
remain evidence. The unchanged DF discovery count is recognized exactly.

Directed validation: 112 engine tests PASS, including six new recovery-identity
methods and 24 actual negative cases. Reproduction is RED on `c4417f1` and GREEN
on `fc03cfb`. Actual fifth-state replay keeps raw62/effective55/seven corrections,
eight bindings, 25 pickups and twelve transitions; all are idempotent. No offline
assertion earns live progress.

Frozen code `fc03cfb5e9106ba985d47b7c4a9db537042449ac` passed 336 tests in 28.477
seconds and actionlint 1.7.7 on five workflows. Its 50-commit bundle restored the
exact full tree from the original main base. Earlier validation and bundles remain
preserved. The next hypothesis is that hosted observation retains canonical
history without reopening unchanged tasks, while a genuinely new independent
recovery error remains distinguishable. Actual publication and outcome are pinned
in the final hosted evidence; acceptance stays NOT_PROVEN.

Normal fast-forward publication was confirmed at 07:52:53.771697Z and started
controller `38122862769` (created 07:52:49Z). Actual first plan `aa50989e`, parent
`a7495354`, reduced at 07:53:07.227053Z: unchanged raw62/effective55/seven
corrections, 25 pickups and twelve transitions, with empty repair/candidate
matrices. Repair and candidate jobs were SKIPPED. The latest staged inputs were
read from `eee5dbb0`; unrelated changes did not restart the identical diagnoses.
Independent final review also passed 64 actual-record negative cases, retaining
new hash-bound assertions and changed baseline/context. No new claims or
useful-progress credit is inferred from this controller SUCCESS.

## 32. Require independent primary source evidence for diagnostic equivalence

A further independent negative changed the nested DF discovery count from 64 to
65 and refreshed every real JSON, source, capture and failure hash, while the
principal observed source row stayed at 64. The recovery had incorrectly matched
its own nested row, so the changed evidence disappeared. This was reproduced
against immutable `fc03cfb` code, not reported as an actual new hosted source fact.

Isolated commit `15416d1` restricts corroboration to direct primary source rows in
the component evidence. Recovery/context/wrapper data cannot corroborate itself.
Unknown, absent or malformed independent rows fail closed. Two new test methods
cover twelve structured fact changes and untrusted wrappers; 114 engine tests PASS.
Independent review preserved all 29 boundary cases with fresh hashes, including
dates, content, URLs, inventories, requests and two self-matching recoveries.
All four proven legacy adapters and raw62/effective55/seven corrections remain
unchanged and idempotent; eight independent directed tests also PASS.

Frozen code `15416d1dee5b71f5afd4468a4e295fd3efc5ff49` passed 338 tests in 45.777
seconds, actionlint on five workflows, 23 independent critical contracts and a
full 51-commit/32-path scope review with zero credential findings. Product,
original gates and deployment are unchanged. The 51-commit bundle restored the
exact full tree. Publication was confirmed at 08:04:01.906332Z and activated
controller `38123500601`, created 08:03:57Z.

Next hypothesis: the hosted controller retains existing history and avoids
unchanged claims; new independently evidenced recovery facts remain meaningful.
Final actual result, canonical state, metadata reconciliation and exact blockers
are pinned in the final continuity evidence. Stage A remains NOT_PROVEN.

## 33. Reconcile governance and verify the resulting real failure

Governance commit `e87e844aa9c5615381291ae925a6c6d2200f6012`, parent
`eee5dbb0668b30605a22d86b7355b75b6a340ef6`, published four metadata paths by
fresh staging CAS: queue, PMO baseline, learning ledger and a new immutable
acceptance artifact. Independent review preserved all 82 unrelated queue tasks,
Work3, approvals, product bytes, original gates, requirements and the original
acceptance artifact. The ledger appended entry 21. Status remains NOT_PROVEN;
documentation and governance writes earn no runtime material credit.

Directed checks passed 15 governance adversarial guards, four publisher
regressions and seven tests against the actual staging PMO module. An initial
local PMO collection error executed zero tests; it was recorded and corrected
before the seven actual tests passed. No false initial PASS is retained.

The resulting real staging preview `38123952091` failed at 08:12:22Z with
`assert 11 >= 12`: one failed, 265 passed, one skipped. QA, Reviewer and preview
were not bypassed. Recovery `38123989947` dispatched the QA family; worker
`38123995343` completed semantically BLOCKED at 08:14:42.041899Z and released
its lease. Controller `38123990147` completed at 08:15:54Z. Shared identical
failure budget increased from one to two of three; it did not reset across run IDs.

Actual canonical state `5c0429e2` at 08:19:13.644521Z retained all earlier raw
events and leases. One new pickup and transition produced raw63/effective56,
with seven corrections, but no new blocker, mutation or closure. Independent
reproduction showed that the transition was an alias retry of already attempted
logical QA work. That credit is not certified useful progress. The next
hypothesis is that a logical-work guard and evidence-bound append-only correction
retain the actual bounded retry without inventing an independent transition.

The prior immutable QA report records a different `evidence_revision` from the
execution task. Read-only reproduction recovered both exact hashes: the engine
revision binds the synthetic approved queue, failure, dependencies and input;
the runner revision binds task objective and acceptance. These historical fields
have different semantic bases. The report revision does not authorize lease
fencing or finish. Correction proof preserves both values and instead verifies
the actual claim/finish state, worker bytes and committed product/executor scopes.

## 34. Bind logical QA retries to frozen work and retain honest publication holds

Isolated checkpoint `37c9529` reproduced the actual alias transition
`007b6742` and stopped equivalent run IDs from consuming the pending terminal
event as another useful transition. Future attempts freeze logical work in
failure-history contexts. Historical correction uses an explicit immutable
before/claim/worker proof; today's mutable task fields cannot authorize it.
Unknown older transitions remain unchanged. Declared instruction assertions,
dates and durations remain exact.

The prepared binding was read from actual Git snapshots and passed 20 directed
importer/CAS tests. Its prospective reducer replay preserved all 63 raw events,
prior seven corrections, eight product bindings, lease and failure history and
the original acceptance window, while projecting 55 effective events, eight
corrections and twelve transitions. This replay is local verification, not LIVE
progress or publication evidence.

Frozen `37c9529` passed 351 complete autonomy tests in 30.787 seconds and
actionlint on five workflows. Its 52-commit bundle restored the exact tree from
the original base. Independent review nevertheless found a concrete bypass:
invalid or clock-only repair descriptors could reset an exhausted QA budget
and earn a transition without executable work. Publication was held. Later
adversarial review also identified reordered equivalent replacements and
removal of a formerly valid action as retry-budget aliases, plus malformed
Unicode capable of crashing reconciliation. Those local reproductions are not
new hosted source failures.

The next hypothesis is that only a structurally valid, genuinely changed
bounded action opens a new bounded QA episode, while malformed, removed or
equivalent action descriptors preserve proven attempt authority. The follow-up
checkpoint must pass directed negative cases, full frozen-code validation and
independent scope review before either checkpoint is published. The historical
351-test PASS does not certify the independently discovered budget defect.

## 35. Recognize executable repair actions and retain exhausted attempt authority

Isolated commit `1d87d8c4c9bf0e659d868e250578d8e313eef8ec` changes only the
engine and its directed tests. QA action identity recognizes the executor's
bounded exact replacement schema and relative artifact path/hash references.
Malformed and clock-only descriptors cannot open a fresh budget or transition.
Equivalent replacement row order and relative artifact aliases canonicalize to
the same work. Removing or corrupting a previously attempted action, including
an unchanged subset of patch/artifact, retains its proven frozen attempt budget.
Genuinely changed valid actions receive the existing bounded three attempts;
the fourth remains blocked. Legacy empty QA and all source-family keys remain
unchanged. The engine's hash safely retains malformed Unicode as escaped JSON
without changing any valid UTF-8 hash.

Directed engine validation passed 135 tests, including 21 logical-alias methods.
Independent review passed 129 boundary/provenance checks, 21 methods and a
separate 21-test/112-subtest executor parity review. Prior action removal was
RED before this change and is GREEN at both one and three prior attempts.
Declared domain assertions, dates, durations and genuinely new actions remain
distinguishable. Structural recognition does not prove file existence, preimage,
candidate syntax, real artifact content, LIVE results or any acceptance gate.
Absolute artifact descriptors have no prospective new-budget authority in the
pure engine; the runner still verifies actual workspace-bound evidence.

The actual immutable alias-binding replay remains raw63/effective55/eight
corrections/twelve transitions, with earlier history and window exact. Next
hypothesis: the hosted first plan applies only that proven correction, preserves
all raw/state provenance and does not reopen identical source or QA work.

## 36. Make malformed JSON evidence writable through the real Git CAS

Isolated commit `720af52a7e652adcd34afabb43dd609d154f5ca2` changes only runtime
JSON serialization and its tests. A malformed declared string could survive
engine validation but crash UTF-8 materialization before the durable state CAS.
The runtime now escapes only unencodable Unicode; valid UTF-8 JSON bytes remain
exact, and a literal escape stays distinct from the malformed value.

Both new tests are RED with the exact encoder extracted from immutable
`37c9529`: two UnicodeEncodeError exceptions. All 28 runtime integration tests
PASS after the fix, including a real local GitStateStore transaction, parsed
evidence round-trip, idempotent replay, zero material credit and unchanged
product refs. This is directed local proof, not fabricated hosted recovery.
The runtime is outside EXECUTOR_INPUTS, so this serialization repair does not
refresh source budgets.

Frozen code `720af52` passed 361 complete autonomy tests in 30.734 seconds,
actionlint 1.7.7 on five workflows and independent 54-commit/32-path scope review
with zero credential findings. Product, original gates and deployment remain
unchanged. The 54-commit bundle restored the exact full tree from the original
main base. Earlier 351-test candidate validation and its publication hold remain
historical evidence. The next hypothesis is that trusted metadata-only binding,
hosted correction and another genuine staging failure preserve these invariants.

## 37. Publish the evidence-bound correction and verify its actual hosted effect

The metadata-only binding CAS `0c29dcfb` adds one trusted transition binding and
one immutable proof to autopilot-state. It preserves all 63 raw events, leases,
failure history, earlier corrections and the acceptance window. After that CAS
succeeded, local receipt hashing raised a TypeError. Read-only verification of
the actual commit, parent, two paths and exact proof recovered the receipt;
there was no second mutation. Original 20-test importer results stay historical.
At current code, two old fixtures still rejected but expected different error
messages. The separate final-contract suite uses actual declared assertions and
retains those malformed-descriptor negatives: all 22 tests PASS.

Normal fast-forward publication of code `720af52` activated controller
`38127573265` at 09:13:02Z. Its actual first plan `6ba8a53b` at
09:13:22.246797Z retained raw63 and pickups26, while correcting effective56 to
55, corrections7 to8 and transitions13 to12. The alias retry remains in raw
history and receives no independently useful transition credit. The original
first pickup remains 05:29:46.231497Z. Observer `0e1cd350` preserved the exact
control blob and appended metadata only. Repair/candidate were SKIPPED without
new executable inputs. All 15 immutable SHA256/Git-blob references were verified.

The eighth hosted proof records a 7,641-second maximum material gap. Merely
passing four wall-clock hours cannot satisfy the unchanged thirty-minute gap
limit. The complete 09:15:32Z schedule-only Actions snapshot has no new scheduled
controller since the initial publication; push/completion dispatch works, and
the cause of missing scheduled delivery remains UNDETERMINED. Current tool
inventory exposes no complete trusted owner-event channel. Owner count stays
NULL and acceptance stays NOT_PROVEN.

The final-v2 private metadata preflight rejected two schema incompatibilities
before any remote mutation: actual validation field names and the newer cadence
counter name. Strict explicit aliases now bind the same frozen code/log hashes;
conflicting, missing and boolean counters reject. Nineteen reconciliation tests,
eight publisher-verifier tests and seven tests against the actual PMO module
PASS. Independent review approved the actual four-path payload and guards.
The next hypothesis is that fresh staging CAS preserves concurrent metadata and
that its genuine QA failure uses the shared budget without another alias credit.

## 38. Reconcile governance through fresh CAS and verify the third bounded retry

The final-v2 staging CAS `4ff51cfe3f5b61217699eb68612a9861239b72a8` used fresh
parent `eb7e0463`, not the older final-v1 parent. One CAS attempt changed exactly
queue, PMO, learning ledger and the new immutable final-v2 acceptance artifact
(SHA256 `7f945f324059b4de2c5ad1add378b6da1ad711cdfe8ecba5090e50eb78d9fd0b`).
Independent actual-commit verification preserved all product bytes, original
gates, PMO references, Work3, 82 other tasks, owned-task approvals/dependencies
and original/final-v1 evidence. The ledger retains its 21-row exact prefix and
appends one reconciliation entry. Metadata receives zero runtime material credit.

Actual staging preview `38128983053` completed FAILURE at 09:37:16Z, retaining
`assert 11 >= 12`: one failed, 265 passed and one skipped in 4.88 seconds.
Recovery `38129022561` completed at 09:37:25Z and dispatched worker
`38129027112`, which completed at 09:39:39Z. Its immutable result is BLOCKED,
validated=false, with no changed paths or candidate. The same logical QA bucket
`22b36587` moved from two attempts to three of three. No additional run identity
reset the budget or earned another transition. Controller `38129022812`
completed at 09:40:31Z; canonical state `695a7d67` retains raw63/effective55,
eight corrections and twelve transitions. Pickup27 is operational activity,
not useful progress. Active leases are zero, and no new raw/effective material
event, blocker, product mutation or closure occurred.
The final read-only snapshot `641a8963` at 09:46:17.848619Z includes later
metadata with the same projection. Its immutable worker report SHA256 is
`b98642321f97448c351a8ca5062e6b45945e7e4ac7d1ba3b41959771e09828a7`,
introduced at `4ba2c1ff` on 09:39:30Z. Whole pending transitions, old family
material clocks, raw/correction history and all bindings remain exact.

The old recovery repeatedly failed on corrupt unified diffs and state ref
races. The new recovery has no competing legacy writer: dispatch and fenced
shared-budget handling complete, with the real product failure visible.
The earlier same-stdout transport repair remains a verified infrastructure
recovery, while source repair/LIVE acceptance remain unproved. Repeated wrapper
SUCCESS is not a repair. Independent native fronts progressed despite blocked
QA; their successes do not become this runtime's useful progress.

Acceptance remains NOT_PROVEN after more than four elapsed hours. Missing
scheduled delivery and complete owner-event observation are exact external
blockers; source capability/coverage and the genuine editorial gate remain
visible in their approved fronts. The next hypothesis is that genuinely changed
approved source inputs open only their own family and produce verified mutation
and transition, while the exhausted identical QA episode stays bounded.
Continuation requires trusted owner export plus a verified producer and actual
scheduler delivery, not owner restarts or fabricated zero-event attestations.
