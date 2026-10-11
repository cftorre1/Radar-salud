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
