from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from .analysis import AnalysisResult
from .models import RawItem, Signal
from .pipeline import build_signal
from .validation import validate_official_item

MONTHS = {
    'enero':'01','febrero':'02','marzo':'03','abril':'04','mayo':'05','junio':'06',
    'julio':'07','agosto':'08','septiembre':'09','octubre':'10','noviembre':'11','diciembre':'12'
}
NUMBER_RE = re.compile(r"(?<!\w)(?:\$\s*)?\d[\d\.,]*(?:\s*(?:%|MM|mil|millones?|camas?|boxes?|prestaciones?|personas?|proyectos?))?", re.I)

class _MinsalParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.text=[]; self.title=[]; self.links=[]; self._h1=False; self._href=None; self._a=[]
    def handle_starttag(self, tag, attrs):
        tag=tag.lower()
        if tag=='h1': self._h1=True
        if tag=='a': self._href=dict(attrs).get('href'); self._a=[]
    def handle_data(self, data):
        s=' '.join(data.split())
        if not s: return
        self.text.append(s)
        if self._h1: self.title.append(s)
        if self._href is not None: self._a.append(s)
    def handle_endtag(self, tag):
        tag=tag.lower()
        if tag=='h1': self._h1=False
        if tag=='a' and self._href is not None:
            self.links.append((self._href, ' '.join(self._a))); self._href=None; self._a=[]

def _date(text: str) -> Optional[str]:
    m=re.search(r"(\d{1,2})\s+de\s+([A-Za-zÁÉÍÓÚáéíóúñÑ]+)\s+de\s+(\d{4})", text, re.I)
    if not m: m=re.search(r"([A-Za-zÁÉÍÓÚáéíóúñÑ]+)\s+(\d{1,2}),\s+(\d{4})", text, re.I)
    if not m: return None
    if m.group(1).isdigit(): d,mon,y=m.group(1),m.group(2).lower(),m.group(3)
    else: mon,d,y=m.group(1).lower(),m.group(2),m.group(3)
    if mon not in MONTHS: return None
    return f"{y}-{MONTHS[mon]}-{int(d):02d}"

def extract_minsal_detail(raw: RawItem, html: str) -> RawItem:
    p=_MinsalParser(); p.feed(html)
    title=' '.join(p.title).strip() or raw.title
    evidence=' '.join(p.text)
    attachments=[]
    for href,label in p.links:
        low=f"{href} {label}".lower()
        if any(x in low for x in ('.pdf','.xlsx','.xls','.csv','descargar')):
            attachments.append({'url':urljoin(raw.url,href),'label':' '.join(label.split())})
    numbers=[]
    for x in NUMBER_RE.findall(evidence[:5000]):
        x=' '.join(x.split())
        if x and x not in numbers: numbers.append(x)
    meta=dict(raw.metadata)
    meta.update({'description':evidence[:3000],'evidence_text':evidence[:12000],'attachments':attachments,'extracted_numbers':numbers[:25]})
    return RawItem(raw.source_slug,title,raw.url,raw.source_name,raw.source_type,_date(evidence) or raw.event_date,evidence[:3000],meta)

def analyze_minsal(raw: RawItem) -> AnalysisResult:
    text=f"{raw.title} {raw.raw_text}".lower()
    tags=['minsal']; who=['estrategia','estudios']; econ,reg,scope,novel,action=45,35,65,70,55
    sub='Sistema público'; category_override=None; domain_override=None
    why='Aporta una señal oficial sobre cambios, inversiones o políticas del sistema de salud.'

    if any(k in text for k in ('compin','licencia médica','licencias médicas','emisor','emisores')):
        tags += ['compin','licencias médicas']; who += ['compin','isapres','rrhh','mutualidades']
        reg,scope,action=85,80,80; sub='COMPIN / Licencias médicas'; domain_override='SOCIAL_SECURITY'
        category_override='Regulación & Legal' if any(k in text for k in ('decreto','reglamento','fiscalización','fiscalizacion','sanción','sancion')) else 'Salud Laboral & Seguridad Social'
        why='Puede modificar fiscalización, criterios o procesos de licencias médicas y afectar a aseguradores, empleadores y seguridad social.'
    elif any(k in text for k in ('hospital','centro de diagnóstico','centro de diagnostico','cesfam','infraestructura','construcción','construccion')):
        tags += ['infraestructura','prestadores','red pública']; who += ['prestadores','proveedores','desarrollo de negocios']
        econ,scope,action=70,80,75; sub='Infraestructura'; category_override='Prestadores'; domain_override='HEALTH_PROVIDERS'
        why='Puede cambiar capacidad asistencial, oferta regional y oportunidades para prestadores y proveedores.'
    elif any(k in text for k in ('transformación digital','transformacion digital','interoperabilidad','receta digital','salud digital','telemedicina')):
        tags += ['salud digital','transformación digital']; who += ['healthtech','tecnología','prestadores','aseguradores']
        econ,scope,novel,action=65,85,85,75; sub='Transformación digital'; category_override='Mercado'; domain_override='PUBLIC_HEALTH'
        why='Señala prioridades tecnológicas del sistema público que pueden abrir cambios operativos y oportunidades para proveedores digitales.'
    elif any(k in text for k in ('ges','garantías explícitas','garantias explicitas')):
        tags += ['ges']; who += ['isapres','fonasa','prestadores']; reg=max(reg,75); scope=85; sub='GES'; category_override='Regulación & Legal'
        why='Puede alterar cobertura, garantías u obligaciones relevantes para aseguradores, prestadores y beneficiarios.'

    desc=raw.metadata.get('description') or raw.raw_text
    return AnalysisResult(
        what_happened=desc[:650] if desc else raw.title,
        key_facts=[desc[:500]] if desc else [],
        key_numbers=[{'raw':x} for x in raw.metadata.get('extracted_numbers',[])[:12]],
        why_it_matters=why,
        who_cares=list(dict.fromkeys(who)),
        watch_tags=list(dict.fromkeys(tags)),
        scores={'economic':econ,'regulatory':reg,'scope':scope,'novelty':novel,'actionability':action},
        subcategory=sub,
    ), category_override, domain_override

def process_minsal_detail(raw: RawItem, html: str, source_cfg: Dict[str, Any]) -> Signal:
    enriched=extract_minsal_detail(raw,html)
    validation=validate_official_item(enriched, source_cfg.get('base_confidence',100))
    analysis,category_override,domain_override=analyze_minsal(enriched)
    enriched.metadata.update({
        'what_happened':analysis.what_happened,'key_facts':analysis.key_facts,'key_numbers':analysis.key_numbers,
        'why_it_matters':analysis.why_it_matters,'who_cares':analysis.who_cares,'watch_tags':analysis.watch_tags,
        'scores':analysis.scores,'subcategory':analysis.subcategory,
        'confidence_adjustment':validation.confidence_score-source_cfg.get('base_confidence',100),
    })
    signal=build_signal(enriched,source_cfg)
    if category_override: signal.category=category_override
    if domain_override: signal.system_domain=domain_override
    signal.confidence_score=validation.confidence_score; signal.validation_status=validation.status
    return signal
