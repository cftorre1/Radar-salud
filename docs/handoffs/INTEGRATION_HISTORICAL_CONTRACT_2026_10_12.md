# Historical Pulso receipt versus integrated runtime

The PR26 reconciliation at 4bd5b3f65029771ec8d1ee071048ef333b1bde16 adds four Python modules. CI 38202982071 reported 3764 passing tests and 38 setup errors in one historical Pulso fixture. PR16 at 85091cac53b93e678097b96c110f8a3fd4f3edf8 reproduced the same failure with 3796 passing tests.

`required_runtime_fingerprint_paths(root)` intentionally requires all source modules. A receipt from the original producer cannot prove an execution of subsequent Global or P0 code. Relaxing that check would wrongly reuse paid-runtime authority.

The fixture now exports the accepted Pulso staging tree 515b8809ecc391600c4093ce0435955d7d3685c5 to a temporary directory and overlays only the current explicitly allowed validator/consumer paths. The existing anti-tampering tests run against that historical scope. An additional negative test inserts an unrecorded module and requires the strict production verifier to reject it. No production validator, receipt, budget, queue, historical model or publisher capture is changed.

This fixture proves historical lineage only. It does not qualify a new integration runtime or daily recurrence. Those need separate exact-SHA execution, source freshness, preservation, browser and Reviewer gates. Global collection remains disabled and Reuters remains paused. No readiness percentage is asserted.

The integrated Python test job ceiling is 25 minutes rather than 15: the P0 candidate already used 781 seconds before the historical fixture completed, and the full immutable replay must not be skipped to meet an obsolete ceiling. This is a timeout ceiling, not a request for repeated suites.

Local validation: all 39 historical and negative contract tests PASS (413.96 seconds, including first-time retrieval of original Git blobs); 11 PMO/orchestration tests PASS. The exported fixture is then narrowed to the actual Pulso evidence families to avoid copying unrelated capture archives; its setup and new negative gate receive a separate focused check before publication.
