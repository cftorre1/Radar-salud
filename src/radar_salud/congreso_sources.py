"""Congreso Nacional: health bills and their tramitación milestones (both chambers).

Dirección 28-oct-2026 17:08: "Avanza con FNE y Congreso".

Structured source: the Senado's public legislative web service ("Datos
Abiertos Legislativos", ``https://tramitacion.senado.cl/wspublico/``).

* ``tramitacion.php?fecha=DD/MM/YYYY`` returns every bill with movement since
  that date (the service page ``invoca_tramitacion_fecha.html`` says: "Este
  listado devolverá la información de todos los proyectos que han tenido
  movimiento desde la fecha indicada. Esta fecha no puede exceder de un mes
  hacia atrás.").
* The XML per bill (verified with WebFetch on 28-oct-2026 for
  ``tramitacion.php?boletin=18623``): ``proyectos/proyecto/descripcion``
  (boletin, titulo, fecha_ingreso, iniciativa, camara_origen, urgencia_actual,
  etapa, subetapa, leynro, diariooficial, estado, refundidos,
  link_mensaje_mocion), ``tramitacion/tramite`` (SESION, FECHA,
  DESCRIPCIONTRAMITE, ETAPDESCRIPCION, CAMARATRAMITE), urgencias, informes,
  comparados, oficios, indicaciones, observaciones, materias.
* ``comisiones.php`` lists committees; Comisión de Salud del Senado is id 195.

The Senado service records each trámite with the chamber where it happened
(``CAMARATRAMITE``), so one call covers milestones in the Cámara de Diputadas
y Diputados too. The Cámara's own web services (opendata.camara.cl) are not
used: WebFetch reported its service page as disallowed by robots.txt.

Only official metadata is stored: boletín, title, dates, stage and the short
official trámite description, plus links. Procedural noise (cuenta, urgencias,
citaciones, oficios de trámite) is dropped; only status changes publish.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from urllib.parse import quote, urlsplit

from .models import RawItem
from .official_open import RobotsGate, chile_today, fetch, fold, health_basis, official, scopes_for
from .processing import DeferredProcessing, RejectedProcessing

SLUG = "congreso_tramitacion"
SOURCE_NAME = "Congreso Nacional · Tramitación (Senado, datos abiertos)"
HOSTS = ("tramitacion.senado.cl",)
WS = "https://tramitacion.senado.cl/wspublico/tramitacion.php"
BILL_PAGE = "https://tramitacion.senado.cl/appsenado/templates/tramitacion/index.php?boletin_ini="
SENATE_HEALTH_COMMITTEE_ID = "195"
EVIDENCE_KIND = "senado_ws_tramite_fecha"
TERMS_POLICY = "official_metadata_and_procedural_text_only"
DEFAULT_WINDOW_DAYS = 7
MAX_WINDOW_DAYS = 30  # the service refuses dates more than a month back


def live_lane_enabled(env=None):
    from .live_lanes import enabled
    return enabled("RADAR_CONGRESO", env)


def query_url(since):
    return f"{WS}?fecha={quote(since.strftime('%d/%m/%Y'), safe='')}"


def bill_page(boletin):
    return BILL_PAGE + quote(str(boletin), safe="-")


def _day(text):
    try:
        return datetime.strptime(" ".join(str(text or "").split())[:10], "%d/%m/%Y").date()
    except ValueError:
        return None


def _txt(node, tag):
    child = node.find(tag) if node is not None else None
    return " ".join((child.text or "").split()) if child is not None and child.text else ""


def parse_tramitacion(xml_bytes):
    """Bills from the service XML. Raises ValueError on a structure change."""
    if len(xml_bytes) > 20 * 1024 * 1024:
        raise ValueError("response too large")
    if b"<!DOCTYPE" in xml_bytes[:2048] or b"<!ENTITY" in xml_bytes[:4096]:
        raise ValueError("DTD/entities not accepted")
    root = ET.fromstring(xml_bytes)
    if root.tag != "proyectos":
        raise ValueError(f"unexpected root <{root.tag}>")
    bills = []
    for p in root.findall("proyecto"):
        d = p.find("descripcion")
        if d is None or not _txt(d, "boletin"):
            raise ValueError("proyecto without descripcion/boletin")
        tramites = [{"sesion": _txt(t, "SESION"), "fecha": _txt(t, "FECHA"), "descripcion": _txt(t, "DESCRIPCIONTRAMITE"),
                     "etapa": _txt(t, "ETAPDESCRIPCION"), "camara": _txt(t, "CAMARATRAMITE")}
                    for t in p.findall("tramitacion/tramite")]
        materias = [" ".join("".join(m.itertext()).split()) for m in p.findall("materias/*")]
        bills.append({k: _txt(d, k) for k in ("boletin", "titulo", "fecha_ingreso", "iniciativa", "camara_origen",
                                              "urgencia_actual", "etapa", "subetapa", "leynro", "diariooficial",
                                              "estado", "link_mensaje_mocion")}
                     | {"tramites": tramites, "materias": [m for m in materias if m]})
    return bills


# --- milestones -----------------------------------------------------------------

# Order matters: the first match wins. None = procedural noise.
_RULES = [
    (r"\burgencia\b", None),
    (r"^cuenta\b", None),
    (r"\bcitaci", None),
    (r"\bpublicad[oa] en (el )?diario oficial|\bpromulga|\bpublicacion\b", "publicacion"),
    (r"\btribunal constitucional\b", "control_constitucional"),
    (r"\bcomision mixta\b", "comision_mixta"),
    (r"\b(veto|observaciones del (presidente|ejecutivo))\b", "veto"),
    (r"\bingreso de proyecto\b", "ingreso"),
    (r"\b(primer|segundo|nuevo segundo|nuevo primer)? ?informe de comision\b", "informe_comision"),
    (r"\brechazad[oa]\b", "rechazo"),
    (r"\baprobad[oa] en general y (en )?particular|\bgeneral y particular a la vez", "aprobacion_general_particular"),
    (r"\baprobad[oa] en general\b", "aprobacion_general"),
    (r"\baprobad[oa] en particular\b", "aprobacion_particular"),
    (r"\boficio\b.*\b(camara revisora|camara de origen|de ley a s\.? ?e\.?|al presidente de la republica)", "despacho"),
    (r"\bdespach", "despacho"),
    (r"\b(archiv|retir)ad?[oa]\b|\bse archiva\b", "archivo"),
]
MILESTONE_LABEL = {
    "ingreso": "Ingresó a tramitación",
    "informe_comision": "Informe de comisión",
    "aprobacion_general": "Aprobado en general",
    "aprobacion_particular": "Aprobado en particular",
    "aprobacion_general_particular": "Aprobado en general y particular",
    "rechazo": "Rechazado",
    "comision_mixta": "Comisión mixta",
    "despacho": "Despachado",
    "control_constitucional": "Control del Tribunal Constitucional",
    "veto": "Veto u observaciones del Ejecutivo",
    "publicacion": "Publicado como ley",
    "archivo": "Archivado o retirado",
}


def milestone(description):
    t = fold(description).casefold()
    for rx, kind in _RULES:
        if re.search(rx, t):
            return kind
    return None


def committee(description):
    m = re.search(r"informe de (?:la )?comisi[oó]n (?:de |del )?([^.;]+?)(?:\s*[.;]|\s+pasa\b|$)", description, re.I)
    return " ".join(m.group(1).split()) if m else None


def health_scope(bill, catalog=None):
    """Basis for a bill being a health bill: title, materias or Comisión de Salud."""
    basis = health_basis(bill.get("titulo"), catalog)
    if any(re.search(r"\bsalud\b|medic|farmac|isapre|fonasa|enfermedad|hospital", fold(m).casefold())
           for m in bill.get("materias") or []):
        basis.append("materia")
    if any(re.search(r"comisi[oó]n de salud", t.get("descripcion") or "", re.I) for t in bill.get("tramites") or []):
        basis.append("comision_de_salud")
    return basis


def items_from_bills(bills, *, api_url, since, today, catalog=None, report=None, capture=None):
    out = []
    for bill in bills:
        basis = health_scope(bill, catalog)
        decision = {"boletin": bill["boletin"]}
        if not basis:
            decision["reason"] = "not_health"
            if report is not None:
                report.append(decision)
            continue
        emitted, dropped = set(), 0
        for t in bill["tramites"]:
            day = _day(t["fecha"])
            if day is None or not since <= day <= today:
                continue
            kind = milestone(t["descripcion"])
            if kind is None:
                dropped += 1
                continue
            if (kind, day) in emitted:
                continue  # one card per bill, milestone and day
            emitted.add((kind, day))
            label = MILESTONE_LABEL[kind]
            title = f"{label}: {bill['titulo']} (Boletín {bill['boletin']})"
            evidence = {"kind": EVIDENCE_KIND, "url": api_url, "date": day.isoformat(), "tramite": t,
                        "bill_page": bill_page(bill["boletin"])}
            if capture:
                evidence.update(api_sha256=capture.get("sha256"), captured_at=capture.get("captured_at"))
            out.append(RawItem(
                SLUG, title[:350], f"{bill_page(bill['boletin'])}#hito-{kind}-{day.isoformat()}", SOURCE_NAME,
                "official", event_date=day.isoformat(), raw_text="",
                metadata={"bill": {k: v for k, v in bill.items() if k != "tramites"}, "tramite": t,
                          "milestone": kind, "milestone_label": label, "committee": committee(t["descripcion"]),
                          "health_basis": basis, "publication_date_source": EVIDENCE_KIND,
                          "publication_date_evidence": evidence, "terms_policy": TERMS_POLICY}))
        decision.update(reason="accepted" if emitted else "procedural_only", milestones=len(emitted),
                        procedural_dropped=dropped)
        if report is not None:
            report.append(decision)
    return out


class CongresoScout:
    """Health-bill milestones from the Senado tramitación web service."""
    slug = SLUG

    def __init__(self, fetch_fn=None, today=None, window_days=None, enabled=None, robots=None):
        self.fetch = fetch_fn or (lambda url: fetch(url, HOSTS, accept="application/xml,text/xml;q=0.9"))
        self.today = today
        self.window_days = window_days
        self.enabled = enabled
        self.robots = robots
        self.diagnostics = {}
        self.discovery_errors = []
        self.discovery_audit = []

    def discover(self):
        enabled = live_lane_enabled() if self.enabled is None else self.enabled
        if not enabled:
            self.diagnostics = {"status": "not_run_outside_engine_runtime", "partial_failure": False}
            return []
        today = self.today or chile_today()
        window = min(self.window_days or DEFAULT_WINDOW_DAYS, MAX_WINDOW_DAYS)
        since = today - timedelta(days=window)
        url = query_url(since)
        allowed = self.robots or RobotsGate(self.fetch).allowed
        if not official(url, HOSTS) or not allowed(url):
            raise PermissionError(f"robots_disallowed: {urlsplit(url).path}")
        body, capture = self.fetch(url)
        bills = parse_tramitacion(body)
        items = items_from_bills(bills, api_url=url, since=since, today=today, report=self.discovery_audit,
                                 capture=capture)
        self.diagnostics = {"url": url, "bills_with_movement": len(bills), "health_bills": sum(
            d["reason"] != "not_health" for d in self.discovery_audit), "milestones": len(items),
            "window_days": window, "partial_failure": False, "terms_policy": TERMS_POLICY,
            "sha256": (capture or {}).get("sha256")}
        return items


CHAMBER = {"c.diputados": "la Cámara de Diputadas y Diputados", "camaradediputados": "la Cámara de Diputadas y Diputados",
           "senado": "el Senado", "congresopleno": "el Congreso Pleno"}
VERB = {
    "ingreso": "Ingresó a tramitación",
    "informe_comision": "La comisión de {committee} emitió informe sobre",
    "aprobacion_general": "Se aprobó en general",
    "aprobacion_particular": "Se aprobó en particular",
    "aprobacion_general_particular": "Se aprobó en general y en particular",
    "rechazo": "Se rechazó",
    "comision_mixta": "Pasó a comisión mixta",
    "despacho": "Se despachó",
    "control_constitucional": "Pasó a control del Tribunal Constitucional",
    "veto": "El Ejecutivo formuló observaciones (veto) a",
    "publicacion": "Se publicó como ley{law}",
    "archivo": "Se archivó o retiró",
}


def _when(day):
    return f"{day[8:10]}-{day[5:7]}-{day[:4]}"


def process_congreso(raw, cfg):
    """Deterministic card (no AI): official bill metadata and the trámite that changed its status."""
    from .editorial_gate import publication_ready
    from .pipeline import build_signal
    md = raw.metadata or {}
    ev, bill, t = md.get("publication_date_evidence") or {}, md.get("bill") or {}, md.get("tramite") or {}
    if (raw.source_slug != SLUG or not official(raw.url, HOSTS) or ev.get("kind") != EVIDENCE_KIND
            or not official(ev.get("url"), HOSTS) or ev.get("date") != raw.event_date or not bill.get("boletin")
            or _day(t.get("fecha")) is None or _day(t.get("fecha")).isoformat() != raw.event_date):
        raise DeferredProcessing("Senado tramitación evidence unverified")
    kind = milestone(t.get("descripcion"))
    if kind is None or kind != md.get("milestone"):
        raise RejectedProcessing("congreso_procedural_noise")
    # Basis recorded at discovery (title, materias or a Comisión de Salud trámite of the bill).
    basis = md.get("health_basis") or []
    if not basis or not (health_scope({**bill, "tramites": [t]}) or "comision_de_salud" in basis):
        raise RejectedProcessing("congreso_not_health")
    chamber = CHAMBER.get(fold(t.get("camara")).casefold().replace(" ", ""), t.get("camara") or "el Congreso")
    law = f" N° {bill['leynro']}" if kind == "publicacion" and bill.get("leynro") else ""
    lead = VERB[kind].format(committee=md.get("committee") or "respectiva", law=law)
    official_text = re.sub(r"\s+([.,;])", r"\1", t.get("descripcion") or "")
    what = (f"{lead} el proyecto «{bill.get('titulo')}» (Boletín N° {bill['boletin']}) el {_when(raw.event_date)}, "
            f"en {chamber}. Trámite oficial: «{official_text}».")
    stage = "; ".join(x for x in (bill.get("etapa"), bill.get("subetapa")) if x)
    if stage:
        what += f" Etapa actual: {stage}."
    why = ("Marca un cambio de estado en la tramitación de un proyecto de ley de salud; "
           + ("la ley queda publicada y su vigencia depende del texto oficial."
              if kind == "publicacion" else "aún no es ley vigente y su contenido puede cambiar en los trámites siguientes."))
    if bill.get("urgencia_actual"):
        why += f" Urgencia vigente: {bill['urgencia_actual']}."
    scopes = scopes_for(bill.get("titulo"))
    raw.metadata.update({"what_happened": what, "why_it_matters": why, "signal_types": ["Legal"], "scopes": scopes,
                         "watch_tags": ["congreso", "proyecto de ley", f"boletín {bill['boletin']}"],
                         "event_type": "LAW_OR_POLICY_CHANGE",
                         "scores": {"economic": 50, "regulatory": 80, "scope": 70,
                                    "novelty": 70, "actionability": 60}})
    row = build_signal(raw, cfg).to_dict()
    row.update(signal_types=["Legal"], scopes=scopes, publication_date=raw.event_date,
               publication_date_source=EVIDENCE_KIND, publication_date_evidence=ev,
               bill_boletin=bill["boletin"], bill_title=bill.get("titulo"), bill_milestone=kind,
               bill_chamber=chamber, bill_stage=bill.get("etapa"), bill_committee=md.get("committee"),
               primary_source_url=bill_page(bill["boletin"]), health_basis=md.get("health_basis"),
               deterministic_processing=True, editorial_relevance=70, terms_policy=TERMS_POLICY)
    accepted, reason, quality = publication_ready(row)
    if not accepted:
        raise RejectedProcessing(f"editorial_gate_{reason}")
    row["publication_ready_score"] = quality
    return row
