# Global official metadata discovery

This directory contains WHO/PAHO metadata discovery and its source health, ledger,
HTTP cooldown state and up to ten editorial candidates. It is separate from the
approved `data/global/themes.json` collection and its unchanged exporter.
Discovery is not a published card or a Chile LIVE signal. Default window of 30 days,
inventory of 90 days, at most 10 topics by materiality; no quota and no paid AI.

The current qualification contract and Reuters license hold are in
`config/global_discovery.json`. Coverage and checked_at are measured per publisher.
Counts require a verified detail identity/publication. Indexed counts, language
aliases, pending dates, technical errors and native-control recall stay distinct.
Recall covers declared surfaces, never the publisher's unknown historical universe.

## Run the isolated qualification

Use branch `codex/global-intelligence-recurrent-20261011`. The official sites are
unreachable from this Codex executor's proxy; this does not prove a publisher block.
Use GitHub Actions `global-source-discovery.yml` on this branch, or update the
tracked `.github/run-global-discovery-now` marker and push this branch. The workflow
cannot write another branch and has no deployment or paid AI authority.

Check `http_cooldowns.json` before a fresh run. The collector enforces Retry-After
across jobs, serializes requests at one per second, checks robots on every origin
and redirect, and makes no retries or identity rotations. A 45 minute live budget
produces explicit incomplete health rather than exceeding the 50 minute daily step.
Global runs after core with `always`; the existing weekday 09:30 UTC cadence is
proposed only in this isolated branch, not activated on staging/main/production.

Each run checkpoints `data/audits/global_source_recovery_2026_10_11/runs/<run_id>/`:
inventory JSON/CSV, hash/HTTP/TLS/redirect/UA manifest, replay, independent raw audit,
Python and desktop/mobile QA. Raw bytes are the `global-discovery-<run_id>` Actions
artifact, not product article bodies. CSV includes materiality/priority, dispositions,
aliases/entities, document links and capture hashes; priority is not editorial score.

Two complete **fresh** live runs with distinct IDs, identical coverage contract and
at least 86,400 seconds separation are required to prove cadence. Use per-source
`next_cadence_validation_not_before`. Legacy ledgers without mode/reuse provenance,
campaign resume and zero-network replay cannot satisfy that requirement. A resume
has a one-hour capture age bound and preserves original timestamps.

## Reproduce without publisher requests

Restore the matching Actions artifact's `work/global-runtime-captures` directory.
The inventory and bytes must have the same run ID. Then:

```sh
python -m pytest -q tests/test_global_source_discovery.py tests/test_global_source_probe_policy.py tests/test_global_intelligence.py tests/test_global_capture_audit.py
python scripts/replay_global_sources.py
python scripts/audit_global_captures.py --captures work/global-runtime-captures --inventory data/global_intelligence/discovery.json --output work/independent_capture_audit.json
python scripts/discover_global_sources.py --project-inventory-csv
```

Replay uses a disposable root, zero network/AI/publication and checks ten canonical
hashes including cooldown/ledger, source-health mirrors and both curated datasets.
The independent auditor imports no collector and rederives dates, aliases, native
index control and bounded date-partition end evidence from original bytes.

Reuters remains disabled until written automated-collection consent, service
entitlement and commercial-use scope are documented. Do not fetch Reuters titles,
metadata, articles or sitemaps. An editor may supply a link without fetching Reuters
and an original description supported by independent primary evidence, subject to
rights/editorial review. Keep credentials out of code, evidence and logs.

Qualification outcomes and operational holds are documented in
`docs/GLOBAL_SOURCE_DISCOVERY_2026_10_11.md` and the three `data/audits/w4_*` reports.
Core recovery/balance, cadence and rights/editorial acceptance remain separate.
