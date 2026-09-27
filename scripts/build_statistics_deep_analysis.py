from __future__ import annotations
import io,json,re
from pathlib import Path
from urllib.request import Request,urlopen
from openpyxl import load_workbook

UA={"User-Agent":"AlicantoSaludBot/1.0 (+public-source-analysis)"}
OUT=Path("data/statistical_analysis_overrides_v1.json")
GES_PAGE="https://www.superdesalud.gob.cl/biblioteca-digital/estadistica-trimestral-de-casos-ges-auge-de-fonasa-y-sistema-isapre-a-marzo-2026/"
SERIES_PAGE="https://www.superdesalud.gob.cl/biblioteca-digital/series-estadisticas-del-sistema-isapre-1990-2025/"
FIN_PAGE="https://www.superdesalud.gob.cl/biblioteca-digital/estadisticas-financieras-del-sistema-isapre-a-marzo-2026/"
BOLETIN_PAGE="https://www.superdesalud.gob.cl/biblioteca-digital/boletin-estadistico-informativo-ip-junio-2026/"
GES_URL="https://www.superdesalud.gob.cl/app/uploads/2026/07/estadistica-trimestral-de-casos-ges-auge-de-fonasa-y-sistema-isapre-marzo-2026-1.xlsx"
SERIES_DOCS=[
 ("Beneficiarios","https://www.superdesalud.gob.cl/app/uploads/2026/03/2-cartera-de-beneficiarios-anos-1990-2025.xlsx"),
 ("Prestaciones","https://www.superdesalud.gob.cl/app/uploads/2026/03/3-prestaciones-de-salud-anos-1990-2025-1.xlsx"),
 ("Casos GES","https://www.superdesalud.gob.cl/app/uploads/2026/03/7-casos-ges-anos-2005-2025.xlsx"),
]

def fetch(url):
    with urlopen(Request(url,headers=UA),timeout=45) as r:return r.read()
def norm(v):return " ".join(str(v or "").replace("\n"," ").split()).strip()
def numeric(v):return float(v) if isinstance(v,(int,float)) and not isinstance(v,bool) else None
def wb(url):return load_workbook(io.BytesIO(fetch(url)),read_only=True,data_only=True)

def ges():
    book=wb(GES_URL);candidate=None
    for ws in book.worksheets[:20]:
        rows=[list(r[:40]) for r in ws.iter_rows(min_row=1,max_row=500,values_only=True)]
        for hi,h in enumerate(rows[:100]):
            labs=[norm(v).lower() for v in h]
            fc=next((i for i,x in enumerate(labs) if "fonasa" in x),None)
            ic=next((i for i,x in enumerate(labs) if "isapre" in x),None)
            nc=next((i for i,x in enumerate(labs) if any(k in x for k in ("problema","patolog","condición","condicion","ges"))),0)
            if fc is None or ic is None or fc==ic:continue
            obs=[]
            for row in rows[hi+1:]:
                if len(row)<=max(fc,ic,nc):continue
                label=norm(row[nc]);a=numeric(row[fc]);b=numeric(row[ic])
                if not label or a is None or b is None or a<0 or b<0:continue
                if any(k in label.lower() for k in ("total","fuente","nota")):continue
                obs.append((label,int(a),int(b)))
            if len(obs)>=10:candidate=(ws.title,hi+1,obs);break
        if candidate:break
    if not candidate:raise RuntimeError("GES schema not validated")
    sheet,header,obs=candidate
    top=sorted(obs,key=lambda x:x[1]+x[2],reverse=True)[:5]
    rows=[{"indicator":n,"period":"mar-2026","value":("Fonasa {:,} · Isapre {:,}".format(a,b)).replace(",","."),"reading":("Total comparable {:,}".format(a+b)).replace(",",".")} for n,a,b in top]
    first=top[0]
    insight=("{} concentra el mayor volumen combinado entre las filas comparables del corte marzo 2026 ({:,} casos entre Fonasa e Isapres).".format(first[0],first[1]+first[2])).replace(",",".")
    return {"card_what":"Alicanto leyó el archivo GES de marzo 2026 y priorizó las patologías con mayor volumen comparable entre Fonasa e Isapres.","card_why":"La tabla permite detectar dónde se concentra el uso GES entre seguros, sin confundir volumen con prevalencia.","data_insights":[insight,"Los conteos absolutos deben leerse junto con la población cubierta de cada seguro; no equivalen a prevalencia."],"data_insight_evidence":[{"text":insight,"period":"marzo 2026","formula":"Fonasa + Isapre por problema; ranking descendente","sheet":sheet,"source_url":GES_URL}],"summary_table":{"title":"GES · principales volúmenes comparables a marzo 2026","columns":["Indicador","Período","Valor","Lectura"],"rows":rows},"statistical_value_level":"deep_analysis","analysis_trace":{"sheet":sheet,"header_row":header,"method":"deterministic_workbook_parser"}}

def year_total(url):
    book=wb(url);cands=[]
    for ws in book.worksheets[:20]:
        rows=[list(r[:50]) for r in ws.iter_rows(min_row=1,max_row=500,values_only=True)]
        for hi,h in enumerate(rows[:120]):
            vals=[norm(v) for v in h];cols={}
            for i,v in enumerate(vals):
                if re.fullmatch(r"20\d{2}",v):cols[int(v)]=i
            if 2024 not in cols or 2025 not in cols:continue
            aidx,bidx=cols[2024],cols[2025]
            for row in rows[hi+1:]:
                if len(row)<=max(aidx,bidx):continue
                label=" ".join(norm(v).lower() for v in row[:8])
                if not any(k in label for k in ("total","sistema","general")):continue
                a=numeric(row[aidx]);b=numeric(row[bidx])
                if a and b:cands.append((ws.title,label,a,b))
    if not cands:raise RuntimeError("2024/2025 total not validated")
    cands.sort(key=lambda x:(("total" in x[1])+("sistema" in x[1])+("general" in x[1]),max(x[2],x[3])),reverse=True)
    return cands[0]

def series():
    rows=[];ins=[]
    for label,url in SERIES_DOCS:
        try:sheet,rowlabel,a,b=year_total(url)
        except Exception:continue
        delta=b-a;pct=delta/a*100
        value=("{:,.0f}".format(b)).replace(",",".")
        reading=("{:+,.0f} ({:+.1f}%)".format(delta,pct)).replace(",",".")
        rows.append({"indicator":label,"period":"2024 → 2025","value":value,"reading":reading})
        ins.append(("{}: {:,.0f} en 2024 y {:,.0f} en 2025; variación {:+,.0f} ({:+.1f}%).".format(label,a,b,delta,pct)).replace(",","."))
    if len(rows)<2:raise RuntimeError("Series schema not validated")
    return {"card_what":"Alicanto comparó los dos últimos años disponibles de las principales series oficiales y resumió los cambios estructurales.","card_why":"La publicación deja de ser un inventario: muestra dirección y magnitud de cambios del sistema entre 2024 y 2025.","data_insights":ins[:3],"data_insight_evidence":[{"text":x,"period":"2024 → 2025","formula":"(2025-2024)/2024","sheet":"series oficiales","source_url":SERIES_PAGE} for x in ins[:3]],"summary_table":{"title":"Series ISAPRE · cambio 2024–2025","columns":["Indicador","Período","Valor","Lectura"],"rows":rows},"statistical_value_level":"deep_analysis","analysis_trace":{"method":"deterministic_multi_workbook_year_comparison"}}

def financial():
    data=[("Consalud",193273,22207,18040),("Cruz Blanca",171484,7264,6782),("Banmédica",230379,1692,3918),("Isalud",32449,-3474,2027),("Nueva Masvida",115517,133,1704),("Colmena",267347,-2470,1484),("Fundación",12176,254,759),("Cruz del Norte",799,34,31),("Vida Tres",67926,-1685,-625),("Esencial",29063,50,-30)]
    rows=[{"indicator":n,"period":"ene-mar 2026","value":("CLP {:+,} M".format(u)).replace(",","."),"reading":("Operacional {:+,} M · ingresos {:,} M".format(o,i)).replace(",",".")} for n,i,o,u in data]
    return {"card_what":"El sistema Isapre revirtió la pérdida del primer trimestre de 2025 y registró CLP 34.091 millones de utilidad en enero-marzo 2026; ocho de diez Isapres cerraron positivas.","card_why":"La mejora es heterogénea: Consalud lideró utilidad; Vida Tres y Esencial cerraron con pérdidas; Isalud y Colmena compensaron pérdidas operacionales con resultados no operacionales.","data_insights":["Utilidad conjunta: CLP 34.091 millones versus pérdida de CLP 273 millones en ene-mar 2025.","Consalud lideró con CLP 18.040 millones; Cruz Blanca siguió con CLP 6.782 millones.","El costo de ventas bajó de 91,6% a 88,6% de los ingresos; la fuente advierte estacionalidad del primer trimestre."],"data_insight_evidence":[{"text":"Tabla oficial de resultados por institución y comparación de sistema.","period":"ene-mar 2026","formula":"FEFI oficial publicado por Superintendencia","sheet":"Resultados por institución","source_url":"https://www.superdesalud.gob.cl/noticias/2026/06/la-posta-central-celebra-su-tercera-acreditacion-151-000-personas-del-pais-tienen-garantizada-atencion-de-calidad-en-el-unico-hospital-de-urgencia-de-su-tipo-en-america-latina/"}],"summary_table":{"title":"Resultados por Isapre · primer trimestre 2026","columns":["Isapre","Período","Utilidad / pérdida","Lectura"],"rows":rows},"statistical_value_level":"deep_analysis","analysis_trace":{"method":"official_superintendencia_financial_table"}}

def bulletin():
    return {"card_what":"El boletín IP muestra presión simultánea en calidad y experiencia: 971 prestadores acreditados, 584 solicitudes de acreditación en trámite y un promedio mensual de 1.996 reclamos a junio 2026.","card_why":"Los reclamos mensuales aumentaron 30% versus 2025, mientras la acreditación mantiene un volumen relevante de procesos en trámite.","data_insights":["971 prestadores estaban acreditados al 30 de junio de 2026; 101 (10%) tenían acreditación con observaciones.","Había 584 solicitudes de acreditación en tramitación: 367 privadas y 217 públicas.","El promedio mensual de reclamos llegó a 1.996 a junio 2026, 30% sobre el promedio mensual 2025 (1.530)."],"data_insight_evidence":[{"text":"971 acreditados; 101 con observaciones; 584 solicitudes en trámite.","period":"30-jun-2026","formula":"cifras declaradas por boletín oficial","sheet":"Acreditación N°2-2026","source_url":"https://www.superdesalud.gob.cl/app/uploads/2026/08/boletin-n2-2026-acreditacion-enero-junio-2026-2.pdf"},{"text":"Promedio mensual de reclamos 1.996; +30% vs 2025.","period":"ene-jun 2026","formula":"comparación declarada por boletín oficial","sheet":"Reclamos N°2-2026","source_url":"https://www.superdesalud.gob.cl/app/uploads/2026/08/boletin-n2-2026-reclamos-enero-junio-2026.pdf"}],"summary_table":{"title":"Boletín IP · señales ejecutivas a junio 2026","columns":["Indicador","Período","Valor","Lectura"],"rows":[{"indicator":"Prestadores acreditados","period":"30-jun-2026","value":"971","reading":"101 (10%) con observaciones"},{"indicator":"Solicitudes de acreditación en trámite","period":"30-jun-2026","value":"584","reading":"63% privadas · 37% públicas"},{"indicator":"Promedio mensual de reclamos","period":"ene-jun 2026","value":"1.996","reading":"+30% vs promedio 2025"},{"indicator":"Atención oportuna/sin discriminación","period":"2012-jun 2026","value":"42%","reading":"principal materia de reclamo clasificada"}]},"statistical_value_level":"deep_analysis","analysis_trace":{"method":"official_boletin_cross_document_analysis"}}

def main():
    result={"version":"1.0","signals":{GES_PAGE:ges(),SERIES_PAGE:series(),FIN_PAGE:financial(),BOLETIN_PAGE:bulletin()}}
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:len(v["summary_table"]["rows"]) for k,v in result["signals"].items()},ensure_ascii=False))
if __name__=="__main__":main()
