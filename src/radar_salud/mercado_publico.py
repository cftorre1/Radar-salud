from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import RawItem, Signal
from .pipeline import build_signal
from .validation import ValidationResult


HEALTH_TERMS = (
    "salud", "hospital", "clínica", "clinica", "médic", "medic", "radioterapia",
    "oncolog", "telemedicina", "domiciliari", "laboratorio", "imagenolog", "farmac",
    "medicamento", "quirúrg", "quirurg", "ambulancia", "rehabilit", "kinesiolog",
    "dental", "diálisis", "dialisis", "isapre", "fonasa", "servicio de salud",
)

SPECIALTIES = {
    "oncología": ("oncolog", "radioterapia", "quimioterapia"),
    "atención domiciliaria": ("domiciliari", "homecare", "hospitalización domiciliaria"),
    "telemedicina": ("telemedicina", "telemonitoreo", "remoto"),
    "imagenología": ("imagenolog", "scanner", "resonancia", "tomografía", "tomografia"),
    "medicamentos": ("medicamento", "farmac", "fármaco", "farmaco"),
    "laboratorio": ("laboratorio", "exámenes", "examenes"),
}


class MercadoPublicoClient:
    BASE_URL = "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json"

    def __init__(self, ticket: str, timeout: int = 20):
        if not ticket:
            raise ValueError("Mercado Público requires an API ticket")
        self.ticket = ticket
        self.timeout = timeout

    def _get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        query = urlencode({**params, "ticket": self.ticket})
        req = Request(f"{self.BASE_URL}?{query}", headers={"User-Agent": "RadarSaludBot/0.1"})
        with urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def list_by_date(self, day: Optional[date] = None) -> Dict[str, Any]:
        day = day or date.today()
        # API uses ddmmyyyy.
        return self._get({"fecha": day.strftime("%d%m%Y")})

    def detail(self, code: str) -> Dict[str, Any]:
        return self._get({"codigo": code})


def _text(obj: Dict[str, Any]) -> str:
    return " ".join(str(obj.get(k, "")) for k in (
        "Nombre", "Descripcion", "CodigoExterno", "Estado", "NombreOrganismo", "UnidadNombre"
    )).lower()


def is_health_tender(item: Dict[str, Any]) -> bool:
    text = _text(item)
    return any(term in text for term in HEALTH_TERMS)


def _specialty(text: str) -> str:
    low = text.lower()
    for label, terms in SPECIALTIES.items():
        if any(t in low for t in terms):
            return label
    return "General"


def raw_items_from_response(payload: Dict[str, Any]) -> List[RawItem]:
    items: List[RawItem] = []
    for obj in payload.get("Listado", []) or []:
        if not is_health_tender(obj):
            continue
        code = str(obj.get("CodigoExterno") or obj.get("Codigo") or "").strip()
        title = str(obj.get("Nombre") or "Licitación Mercado Público").strip()
        buyer = str(obj.get("NombreOrganismo") or obj.get("UnidadNombre") or "").strip()
        close = obj.get("FechaCierre") or obj.get("Fechas", {}).get("FechaCierre")
        description = str(obj.get("Descripcion") or "").strip()
        source_url = f"https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idLicitacion={code}" if code else "https://www.mercadopublico.cl/"
        combined = f"{title} {description} {buyer}"
        items.append(RawItem(
            source_slug="mercado_publico",
            title=title,
            url=source_url,
            source_name="Mercado Público",
            source_type="official_api",
            raw_text=description,
            metadata={
                "code": code,
                "buyer": buyer,
                "status": obj.get("Estado") or obj.get("CodigoEstado"),
                "close_date": close,
                "subcategory": _specialty(combined),
                "watch_tags": ["licitaciones", _specialty(combined)] + ([buyer] if buyer else []),
                "entities": [buyer] if buyer else [],
                "who_cares": ["desarrollo de negocios", "prestadores", "proveedores de salud"],
                "why_it_matters": "Puede representar una oportunidad comercial o una señal de demanda pública por prestaciones, tecnología o insumos de salud.",
                "what_happened": f"{buyer + ': ' if buyer else ''}{title}" + (f". Cierre: {close}" if close else ""),
                "scores": {"economic": 65, "regulatory": 20, "scope": 55, "novelty": 80, "actionability": 90},
                "structured_api": True,
            },
        ))
    return items


def validate_marketplace_item(raw: RawItem, base_confidence: int = 100) -> ValidationResult:
    required = [raw.metadata.get("code"), raw.title, raw.metadata.get("buyer")]
    evidence = sum(bool(x) for x in required)
    confidence = min(100, base_confidence - (3 - evidence) * 8)
    status = "automatic" if confidence >= 90 else "cross_checked" if confidence >= 75 else "human_review_required"
    return ValidationResult(confidence_score=confidence, status=status, reasons=["official structured API"])


def process_marketplace_item(raw: RawItem, source_cfg: Dict[str, Any]) -> Signal:
    validation = validate_marketplace_item(raw, source_cfg.get("base_confidence", 100))
    raw.metadata["confidence_adjustment"] = validation.confidence_score - source_cfg.get("base_confidence", 100)
    # Transaction/event type dominates semantic keywords such as "hospital".
    cfg = dict(source_cfg)
    cfg["force_category"] = True
    signal = build_signal(raw, cfg)
    signal.confidence_score = validation.confidence_score
    signal.validation_status = validation.status
    return signal
