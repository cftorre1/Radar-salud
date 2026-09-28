# Auditoría de brechas de riesgo de producto — 2026-09-28

**Estado:** diagnóstico validado; recomendaciones solamente.  
**Alcance:** beta cerrada read-only y controles de correo/sugerencias que pueden percibirse activos.  
**Revisión:** lentes independientes de accesibilidad, seguridad/privacidad, confiabilidad/observabilidad y crecimiento/conversión, cotejados contra el repo y Actions staging. No se implementaron cambios.

## Resumen de prioridad

- **P0 — ninguno observado** dentro de una beta read-only con contenido público y sin captura personal activada.
- **P1 — controles de lanzamiento:** URL de staging sin autenticación; funnels newsletter/PREMIUM intencionalmente cerrados y sin evidencia de entrega; CTA de sugerencias sin backend persistente desplegado; falta aislar el alcance exacto antes de una promoción.
- **P2 — calidad operativa:** auditoría WCAG formal pendiente; sin telemetría de conversión por decisión de privacidad; feedback cuantitativo de beta limitado a operación manual; backend de sugerencias no validado en producción.

## 1. Accesibilidad e inclusión

### Evidencia
HTML usa labels asociados en formularios, botones de cierre accesibles, diálogos nativos, role=status/aria-live para mensajes, foco visible y controles principales de 44 px. Tests browser prueban desktop/móvil, algunas condiciones de overflow y acceso al detalle estadístico. Las tablas usan scroll interno en pantallas estrechas.

### Riesgos y recomendación
- **P2:** no hay evidencia de revisión WCAG 2.2 AA, lector de pantalla, ampliación al 200%, reducción de movimiento ni navegación íntegra por teclado. Ejecutar revisión manual y medición de contraste antes de una beta amplia; corregir solo incumplimientos reproducibles.
- **P2:** medir contraste de los colores secundarios y tipografía pequeña sobre pantallas reales.
- **P2:** comprobar que el scroll horizontal interno de tablas sea evidente y legible con teclado y tecnologías de asistencia.
- Preservar los patrones de navegación aprobados.

## 2. Seguridad y privacidad por diseño

### Evidencia
- web/data/analytics.json mantiene analytics apagado, privacy_approved=false y clave vacía; el mapa limita datos y no transmite URL, email ni texto libre.
- web/data/subscription.json mantiene captura/envío apagados, form_action nulo, grupos vacíos, privacidad sin aprobar y remitente sin verificar.
- El borrador legal se declara no vigente y prohíbe activar formularios/analytics desde él.
- Las sugerencias no piden identidad; el servicio proyectado incluye honeypot y controles de abuso. Su esquema evita almacenar IP, user-agent y referrer.
- El preview no tiene autenticación; la beta prevista es read-only y Pato prohíbe contenido sensible.

### Riesgos y recomendación
- **P1:** reenviar el enlace de staging da acceso público por URL. La distribución por invitación es una regla operativa, no autenticación.
- **P1:** correo, consentimiento y autenticación DNS no están activados ni verificados; no existe evidencia SPF/DKIM/DMARC.
- **P1:** el endpoint de sugerencias no corre en GitHub Pages; el submit falla explícitamente y no persiste ni notifica.
- **P2:** antes de activar cada funnel, exigir consentimiento independiente, finalidad/retención aprobadas, grupo correcto, baja y prueba real autorizada. El funnel PREMIUM debe incorporar consentimiento explícito antes de activarse.

Mantener la Beta read-only sin datos sensibles y no describir el enlace como protegido. Antes de activar formularios, obtener aprobación legal/privacidad, proveedor y DNS, y verificar consentimiento, baja, destino y manejo de errores.

## 3. Confiabilidad y observabilidad

### Evidencia
El pipeline de staging valida artefacto, rollback, QA, Reviewer y smoke con SHA. Actions 36430841007 terminó con 244 Python, 39 Node, 46 Playwright, Reviewer sin hallazgos y preview/smoke PASS. El ledger conserva recuperación acotada; Admin representa métricas ausentes como no disponibles. El test de sugerencias intercepta respuestas de API: prueba el contrato de interfaz, no la disponibilidad del servicio.

### Riesgos y recomendación
- **P1:** no existe persistencia real ni notificación de sugerencias en el hosting actual.
- **P2:** no hay monitoreo de entrega email, DNS o estado de esas integraciones; “listo” requiere evidencia del proveedor.
- **P2:** main y staging divergen 688 commits ahead y 5 behind con cambios en varias áreas. Un merge amplio no excluiría trabajo fuera del alcance.

Si Dirección aprueba captura persistente de sugerencias, elegir hosting, almacenamiento durable, límites y alertas antes de activarla. Para release, preparar allowlist de cambios o rama limpia y ejecutar los gates/rollback sobre el candidato exacto.

## 4. Crecimiento y conversión

### Evidencia
Home ofrece CTA de newsletter y PREMIUM; los formularios quedan deshabilitados cuando proveedor/privacidad no están aprobados. Newsletter enlaza a una página separada con consentimiento deshabilitado. Analytics permanece inactivo, por lo que no hay CTR ni conversión confirmada. La beta se plantea para 10–30 invitados, sin cohortes ni medición automatizada.

### Riesgos y recomendación
- **P1:** el CTA de newsletter ofrece recibir señales por correo aunque el diálogo indica que la suscripción abrirá más adelante.
- **P1:** el formulario PREMIUM presenta campos y botón deshabilitados y no registra una inscripción real.
- **P2:** sin analytics, el uso debe evaluarse con feedback voluntario; no inferir conversión.
- **P2:** sugerir fuente no completa la acción colaborativa durante la beta.

Mantener los estados inactivos inequívocos. Dirección debe escoger si espera a la configuración aprobada o habilita un mecanismo de interés separado y consentido. Para beta read-only, usar feedback voluntario por un canal elegido por Dirección, sin atribuir resultados inexistentes.

## Decisiones que requieren Dirección

1. Mantener el preview no autenticado solo para beta operativa read-only, o aprobar una solución de acceso antes de ampliar distribución.
2. Autorizar hosting durable y destinatario SMTP para sugerencias, o mantener la función cerrada.
3. Configurar MailerLite, grupos y remitente; aprobar consentimiento/finalidad; aportar evidencia exacta de SPF/DKIM/DMARC antes de activar captura.
4. Elegir canal de feedback beta e indicadores compatibles con analytics inactivo.
5. Aprobar allowlist de cambios para promoción dado el tamaño/divergencia de ramas.

## Gate recomendado

La beta read-only puede continuar por invitación operativa mientras no contenga datos sensibles. La promoción pública con flujos de correo debe seguir bloqueada hasta que entrega, consentimiento, DNS, sugerencias/registro requeridos, Reviewer/Improvement Review y un candidato limpio de alcance tengan evidencia completa.
