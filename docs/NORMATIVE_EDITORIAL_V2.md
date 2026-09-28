# Normative Editorial V2

## Purpose
Make every regulatory signal understandable in seconds while preserving a highly visible legal identity.

## Visual hierarchy
1. **Legal identity badge / eyebrow** — prominent, immediately recognizable, e.g. `RESOLUCIÓN EXENTA IF/N°11156` or `CIRCULAR IF/N°533`.
2. **Plain-language title** — explains the substantive change and business meaning.
3. **Compact metadata** — date and source remain secondary.

Legal identity must never be styled as quietly as date/source.

## Editorial title contract
A plain-language title should normally answer at least two of:
- What changed?
- Who is affected?
- What must they do differently?
- When/status if material?

Do not use legal procedural status as the main idea unless it changes the substantive operational state.

Bad:
> Resolución Exenta IF/N°9994 sobre Circular IF/N°532: mantiene su ejecución pese a las impugnaciones

Better:
> Suscripción y desafiliación electrónica: la nueva regulación sigue adelante pese a la impugnación

Legal badge/subtitle:
> RESOLUCIÓN EXENTA IF/N°9994 · CIRCULAR IF/N°532

## Required structured output
- legal_identity
- legal_action
- affected_rule
- business_subject
- affected_actor
- required_change
- effective_date_or_status
- plain_language_title
- legal_subtitle

## Committee
Normative signals require:
- editorial_intelligence
- health_business
- regulatory_legal
- evidence_research
- **regulatory_business_editor**

The regulatory_business_editor owns the translation from legally accurate content to executive comprehension.

## Five-second gate
Before publication, ask:
> Reading only the title, can an industry professional explain what changed?

If no, FAIL.

## Deterministic guards
Reject or route to review if:
- title ends in a preposition/conjunction or clearly incomplete clause;
- title is mechanically built from `normative_subject`;
- title says only that a rule is modified/suspended/maintained without naming its substantive subject;
- title contains duplicate legal identifiers;
- visible title is mechanically truncated;
- legal identity is missing or visually downgraded to ordinary metadata.

## Mandatory regression corpus
- IF/N°11156 — TEA / no annual cap / RND
- IF/N°10670 — EMP / partial report in October / rule remains in force
- IF/N°10615 — Nueva Masvida / MAS2026 / contribution, loss ratio and mandate
- IF/N°533 — monthly SIL inventory / new fields and validations
- IF/N°9994 — electronic subscription/disaffiliation / rule continues despite challenge
- IF/N°8760 — CAEC emergency referral rules temporarily suspended
- IF/N°532 — electronic subscription/disaffiliation evidence requirements

## Example target titles
- **TEA: se mantiene la cobertura sin tope anual y no se podrá exigir RND**
- **Metas EMP: el informe parcial pasa a octubre y la regla sigue vigente pese a los recursos**
- **Nueva Masvida deberá ajustar el Plan MAS2026: aporte, siniestralidad y mandato**
- **Isapres deberán ampliar el archivo mensual de devolución de SIL con nuevos campos y validaciones**
- **Suscripción y desafiliación electrónica: la nueva regulación sigue adelante pese a la impugnación**
- **CAEC: se suspenden temporalmente las nuevas reglas de derivación en urgencias**

## Learning closure
This task is not complete after correcting today's titles. Completion requires:
1. current visible normative signals recurated;
2. regression tests;
3. committee rule updated;
4. future normative signals generated under this contract;
5. historical recuration plan/evidence;
6. desktop/mobile QA and Improvement Review.
