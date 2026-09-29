# Improvement Review — visible respiratory epidemiology pulse

## Review result

PASS for the bounded staging change. The card is a dated weekly signal, distinguishes ISP laboratory surveillance from MINSAL care pressure, preserves source attribution, and is scoped to public health, providers, Fonasa and Isapres. It publishes only after a material week-over-week movement; a high occupancy value by itself does not create a repeated pulse. Builder freshness is limited to 14 days.

## Review dimensions

- **Strategic fit:** adds a cross-system operating signal without reducing Isapre coverage or imposing segment quotas.
- **Clarity and editorial quality:** the report retains week, positivity/virus context and available care-pressure measures, with lab surveillance and hospital system data attributed separately. No causal claim is inferred between them.
- **Data integrity:** stale input emits no signal. The existing official MINSAL report anchors the visible card and the ISP surveillance page is attributed as the laboratory dimension. Both remain historical/BACKFILL; an independent raw-workbook reconciliation is not claimed.
- **UX and regression risk:** feed rendering and responsive desktop/mobile checks passed in staging QA. The workflow now runs the epidemiology builder before export/recuration.
- **Maintainability:** threshold and freshness behavior are deterministic and covered by Python tests.

## Non-blocking follow-up

Reconcile the ISP raw weekly workbook against the corresponding MINSAL report before describing the pulse as independently cross-validated. This gap is carried forward in the coverage task backlog and does not block the current staging card.
