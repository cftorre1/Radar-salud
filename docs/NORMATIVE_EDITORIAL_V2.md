# Normative Editorial V2.1 — document-first clarity

## Principle
For regulatory content, the legal document is not secondary metadata. The user should understand in the headline itself:

1. **What document is this?**
2. **What subject does it regulate or decide?**
3. **What changed / what did the authority decide?**

A user should not need to open “Contexto de la señal” to discover the document identity or the substance.

## Headline patterns

### Circulars / instructions
Preferred pattern:

`Circular IF/N°XXX · [subject]: [concrete obligation/change]`

Examples:
- **Circular IF/N°535 · Reembolsos públicos: isapres no podrán compensarlos con deudas del empleador**
- **Circular IF/N°534 · Bonos electrónicos: isapres deberán permitir compra con cédula si falla la biometría**
- **Circular IF/N°533 · SIL: nuevo archivo mensual incorpora campos y validaciones adicionales**

### Resolutions affecting another act
Preferred semantic order:

`Resolución Exenta IF/N°XXXX · [subject]: [decision by the resolution] regarding [Circular/Oficio Y], por lo que [explicit consequence for the prior rule]`

The headline must distinguish:
1. the substantive subject;
2. what the **resolution** decided;
3. which earlier act it acted on;
4. the resulting effect on that earlier act.

Preferred examples:
- **Resolución Exenta IF/N°10670 · Metas EMP: rechaza recursos contra Circular IF/N°531, por lo que sigue vigente el cambio de junio a octubre del informe parcial EMP**
- **Resolución Exenta IF/N°9994 · Afiliación electrónica: rechaza suspender la Circular IF/N°532, por lo que continúan vigentes sus nuevas exigencias de suscripción y desafiliación**
- **Resolución Exenta IF/N°8760 · CAEC: suspende la Circular IF/N°529, por lo que quedan temporalmente en pausa las nuevas reglas de derivación en urgencias**
- **Resolución Exenta IF/N°10615 · Plan MAS2026: acoge parcialmente el recurso contra Oficio IF/N°27.377, por lo que Nueva Masvida debe ajustar aporte, siniestralidad y mandato**

Avoid ambiguous forms such as:
> Resolución X · rechaza recursos contra Circular Y: el informe pasa a octubre

because the user may not know whether the last clause describes the resolution or the circular.

These are editorial patterns, not rigid templates. The committee may rewrite when another formulation is clearer.

## Length
Do not optimize for the shortest possible title. Two or three mobile lines are acceptable when necessary to preserve document identity, subject and change.

## Context
“Contexto de la señal” is optional depth, not a crutch for an incomplete title. It should add:
- relevant antecedent;
- what the document changes/decides;
- practical scope or timing when material.

Avoid repeating the headline verbatim.

## Committee gate
Permanent reviewers:
- Regulatory Business Editor
- Regulatory/Legal
- Health Business
- Editorial Intelligence
- Evidence Research

Before publication, answer:
- Do I know which document this is?
- Do I understand the subject?
- Do I understand what changed or was decided?

Any “no” => REVISE.

## Tests
Use stable identity (source URL / document number) for locators. Test semantic requirements:
- type + number visible;
- substantive subject present;
- action/change understandable;
- no real truncation;
- context adds incremental value.

Do not encode exact editorial phrasing or fragile regex rules.

## Stock recuration
Apply to all currently visible/vigente normative signals and future ones. The stock review is part of completion, not optional backfill.
