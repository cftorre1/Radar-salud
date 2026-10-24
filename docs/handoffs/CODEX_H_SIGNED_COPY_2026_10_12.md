# Codex H · cierre focal de la proyección editorial v3

Contrato: [PR32](https://github.com/cftorre1/Radar-salud/pull/32), SHA `a3e254d9ada6d2750787b416d7a9ee2253c08334`. Base reconciliada: staging `74da1c6d33b9e5746e79e0f481be3057f33d45df`. Rama aislada: `codex/h-contract-followup-20261012`. Código comprobado: `6048a1d5def99e060dd973fd9640c508d1ec853d`; el head final y Actions exactas figuran en la PR.

## Estado real y alcance

Los paquetes A–D ya existen en [PR33](https://github.com/cftorre1/Radar-salud/pull/33), integrada por el Integration Commander. Su cierre y el [run38272609619](https://github.com/cftorre1/Radar-salud/actions/runs/38272609619) vinculan QA, Reviewer y preview SUCCESS al SHA actual de staging. Se consultaron PR32 y su discusión, Work5 handoff/evidencia/Reviewer, dictamen Work6 y recheck W6-01, Issue5, queue/PMO, contratos y código vigente. Esta entrega conserva esa implementación y corrige exclusivamente un P1 encontrado por un nuevo Reviewer independiente.

**P1-SIGNED-TITLE:** un registro v3 válido sin `display_title` puede retener `card_what` o `normative_subject` legacy fuera de `content_version`. Los gates backend y exporter admiten el registro sin cambiar su receipt, pero el resolver frontend sustituía el título revisado. Caso reproducido: «Resolución IF/N°1 rechaza reposición» aparecía como «acoge reposición y levanta la sanción» en tarjeta, Ponte al día y ficha.

## Corrección

Para v3, título público = `display_title || title`; síntesis = `brief_deck` opcional. Esos campos ya pertenecen al hash revisado. No se aplican overrides por URL, materias legacy ni abreviaciones derivadas de `card_what`. La ruta v2 conserva sus reglas históricas. `triageSummary` también se acota como prevención; Ponte al día actualmente no renderiza esa síntesis, por lo que no se atribuye al defecto una exposición visible de resúmenes que no existe.

No se amplía el hash, no se reescriben los cinco receipts editoriales aprobados y no se promueven fixtures. El único cambio productivo está en dos funciones de `web/app.js`.

## Evidencia y aceptación

Artefactos: [evidencia focal](../evidence/codex_h_signed_copy_20261012/).

| Verificación | Resultado local |
|---|---|
| Python: producto v3, calidad editorial y Reviewer estadístico | 59 PASS; el fixture sintético conserva hash, publication gate y export válidos con copy legacy contradictorio |
| Node: render y compatibilidad vigente | 50 PASS; normativa, noticia larga, override por URL, título firmado, síntesis opcional y preservación v2 |
| Browser: product-v3, editorial-v3 y regresión nueva | 28 PASS, 0 skip/flaky/unexpected; desktop1440×900 y mobile390×844; probes estadísticos320/195 heredados ejecutados en la suite focal |
| Superficies del P1 | Tarjeta, Ponte, h2 de ficha, aria-label y compartir mantienen el título revisado; título y Más info abren la misma ficha |
| Integridad | 5.675 paths protegidos con blobs Git idénticos a la base; cinco hashes/receipts originales intactos |

Las capturas `desktop.png` y `mobile.png` son previews del **fixture sintético de regresión**, no del sitio publicado. La suite editorial también usa los cinco candidatos ya revisados y el fixture de cartera; no equivale a publicar esas fichas.

El primer intento local Python importó el editable de otro checkout y falló durante colección; se corrigió el runner poniendo este `src` primero. El servidor de browser necesitó permiso de red del sandbox para localhost. Ninguno de esos errores es un defecto del producto ni se modificó un workflow para ocultarlo. El nuevo test Node falló antes de la corrección y pasó después. No se repitió la suite completa local: la PR conserva los gates CI normales.

**PASS técnico scoped:** [Reviewer independiente](../evidence/codex_h_signed_copy_20261012/reviewer/REVIEW_FINAL_2026_10_12.md), código `6048a1d5`, cero P0/P1 abiertos en este delta. Corroboró el cierre en Chromium desktop/mobile y ausencia de diferencias en 165 señales legacy por cuatro funciones. **PASS editorial previo de los cinco candidatos:** receipts/bytes/hash preservados; no es una nueva certificación de originales ni PASS editorial de la copy legacy publicada. Actions del head final debe terminar antes de valorar integración del código; la situación editorial real sigue separada y esta entrega no declara READY global.

## HOLD y consumo

IF10670 live sigue REVISE editorial según el cierre del Commander; los candidatos corregidos siguen fixtures. Permanecen FEFI/Esencial, BCBSA/método, SE37, Reuters/licencia, preflight CENS/iHEALTH, PR29 y los gates operativos/beta. W6-04 y las políticas generales de tolerancia conservan su alcance P2; esta corrección no pretende cerrar una auditoría sancionatoria o financiera adicional.

Consumo incremental del pipeline: **0 llamadas IA pagadas, 0 recapturas, 0 resets, 0 receipts históricos reescritos**. Sesiones Builder/Reviewer: tokens y costo no expuestos; no se inventa importe. Queue, PMO, presupuestos, fuentes, history, datos publicados, main y producción no reciben cambios.

## Handoff para Integration Commander

1. Confirmar head de la PR y base de staging contra los SHA indicados. Si cambia staging, conciliar el delta antes de reutilizar resultados.
2. Revisar el P1 y su cierre independiente, `integrity.json`, logs, `browser.json` y capturas. Los commits posteriores al código deben contener sólo evidencia/handoff.
3. Exigir QA y Reviewer CI SUCCESS del head final; distinguir ese PASS técnico de la situación editorial de las fichas reales. No integrar mientras exista P0/P1 abierto.
4. Integrar exclusivamente mediante su proceso hacia staging. Conservar todos los HOLD, los cinco receipts y la separación de fixtures/publicación; no habilitar fuentes, gasto, beta ni producción.

El Builder no fusiona esta PR ni modifica refs de main, staging o producción.
