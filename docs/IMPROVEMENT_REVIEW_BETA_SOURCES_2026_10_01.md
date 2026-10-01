# Improvement Review — Beta sources package — 2026-10-01

## Objective
Close source coverage for the first human beta validation without lowering evidence standards or activating noisy feeds merely to increase source count.

## Source Quality Gate decisions
- **FONASA/GRD:** direct FONASA newsroom remains an external HTTP blocker in runtime health. The beta is compensated by the already-integrated FONASA Datos Abiertos surface plus current official MINSAL GRD/productivity evidence and DIPRES 2026 GRD financing evidence.
- **Prestadores Data:** the Intendencia de Prestadores bulletin surface is current through N°2-2026 and exposes RNPI, Acreditación, Mediación and Reclamos. Discovery is integrated. Public promotion stays fail-closed because the listing does not expose an exact publication day; the product must not invent one.
- **Provider networks:** Dávila, Andes Salud and Clínicas Achs Salud pass active integration. RedSalud, INDISA, Bupa and Clínicas de Chile remain existing channels. Clínica Las Condes and Interclínicas are deliberately secondary: their beta-relevant strategic signals are better covered through primary regulatory filings and high-trust business media than through a stable, high-density corporate newsroom.
- **Mutualities:** Achs Seguro Laboral, Mutual de Seguridad and IST pass active integration, with a materiality filter that rejects awards, generic events and promotional noise.
- **Media:** Diario Financiero remains active; Pulso/La Tercera passes active integration. El Mercurio/Economía y Negocios was evaluated but is kept secondary because a stable deterministic current listing was not established and activating an overlapping broad feed would increase duplication. It remains corroboration, not a beta coverage hole.

## Media Early Signal Gate
A media item can enter only for a material business event and stays `media_reported` until company or official evidence confirms it. Confirmation upgrades the existing event rather than creating a second card. Opinion, branded content, generic politics, patient education, events/awards and unattributed rumors are excluded.

## Epidemiology
Maintain separate evidence roles: ISP = laboratory/virus surveillance; MINSAL = care pressure. The same epidemiological week must not be counted twice.

## Improvement-review verdict
**PASS on architecture and policy.** Remaining acceptance evidence must come from the integrated staging run: source health, desktop/mobile QA, Reviewer, preview smoke, dashboard reconciliation and queue/PMO closure.
