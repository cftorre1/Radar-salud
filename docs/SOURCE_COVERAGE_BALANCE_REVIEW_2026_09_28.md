# Coverage balance: epidemiology and providers — 2026-09-28

## Decision

Add the dated official INDISA newsroom to the staging discovery catalog. Its 2026-09-11 article about the preferred-care agreement with Isapre Esencial provides a concrete provider–payer relationship, service scope and locations, an approximate current portfolio and a stated growth target. The parser/fixture review is complete, but the 90-day newsroom inventory audit is not exhaustive yet. The source therefore carries `pending_90_day_audit` and is held in BACKFILL until that audit passes; a company statement remains attributed and is not treated as independently verified performance.

Do not activate the other reviewed provider sources yet:

| Source | Review result | Treatment |
| --- | --- | --- |
| Clínicas de Chile A.G. | The accessible recent items reviewed were opinion or sector events; no dated, quantified change meeting the business materiality bar was established. | Not registered as a signal source. Reconsider when it publishes a substantive sector indicator, policy position with operational consequence, or agreement. |
| Clínica Alemana | The material located in the review window did not establish a timely provider-market change suitable for the feed. | Not activated. Preserve as a candidate for a later dated-source review. |
| UC CHRISTUS | The candidate pages/results did not provide a sufficiently verified date and article evidence pair in this review. | Not activated pending source/date verification. |
| Clínica INDISA | Official dated announcement of a preferred-provider agreement with Isapre Esencial, with stated terms and reach. | Added to staging discovery; details and materiality are checked before publication. |

## Controls

- Listing links must match the official INDISA host and `/blog/<slug>` path.
- Discovery binds each listing title to the same article headline and requires an article publication date. A broken or mismatched individual detail is skipped; a listing with no verified dated pair is a source-level technical failure.
- The pending 90-day audit gate forces all new INDISA discoveries to BACKFILL even when a date would otherwise be LIVE. Queue tests cover release only after an explicit `passed` gate.
- Processing revalidates source identity, URL, title, date and a minimum 350-character body; it uses the existing corporate-news assessment and materiality threshold (score 78), with attributed language.
- Isapre Esencial and INDISA scope the signal to Isapres and Prestadores. No quota is assigned to either segment.
- The respiratory epidemiology pulse remains a dated historical item until it enters the existing 14-day LIVE horizon. A high occupancy value alone does not create a weekly pulse; material change thresholds and source freshness are enforced by the epidemiology builder.
- Fonasa coverage is represented through official Fonasa, MINSAL, Superintendencia, DEIS and other official data routes. The feed/dashboard reports source and signal coverage, not a claim of exhaustive public/private interaction capture.
- The admin coverage table keeps LIVE detection/selection metrics unavailable until there is a successful global discovery measurement, separates published feed stock, and shows the age of the most recent dated signal. Segment counts diagnose blind spots; they do not impose editorial quotas.

## Follow-up

Backlog the remaining 90-day INDISA catalog audit and dated 90-day recrawl of the three inactive provider candidates, then explicitly pass the INDISA source gate. Independently reconcile the ISP respiratory workbook with the MINSAL report before claiming a fully cross-source epidemiology view. These are non-blocking for this staging iteration; none is represented as completed here.
