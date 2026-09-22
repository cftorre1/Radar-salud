from __future__ import annotations
import io, re
from urllib.request import Request, urlopen
from typing import Any

def _download(url: str, timeout: int = 30) -> bytes:
    req=Request(url,headers={"User-Agent":"RadarSaludBot/0.3 (+public-source-monitor)"})
    with urlopen(req,timeout=timeout) as r:return r.read()

def extract_pdf_text(url: str, max_pages: int=24) -> str:
    try:
        from pypdf import PdfReader
        reader=PdfReader(io.BytesIO(_download(url)))
        pages=[]
        for p in reader.pages[:max_pages]:
            t=p.extract_text() or ""
            if t:pages.append(t)
        text="\n".join(pages)
    except Exception:
        return ""
    # Remove common OCR/layout garbage without altering substantive language.
    text=text.replace("\x00"," ")
    lines=[]
    for line in text.splitlines():
        s=" ".join(line.split())
        if not s:continue
        low=s.lower()
        if any(x in low for x in ("trabajando para usted","superintendencia de salud")) and len(s)<90:
            continue
        if re.fullmatch(r"\d+\s*/\s*\d+",s):continue
        lines.append(s)
    return "\n".join(lines)

def extract_validity(text: str):
    clean=" ".join((text or "").split())
    patterns=[
      r"((?:las disposiciones|la presente|esta circular|esta resolución|la resolución)[^.]{0,120}(?:entrar[aá]n?|comenzar[aá]n?|regir[aá]n?)[^.]{0,220}\.)",
      r"((?:entra|entrará|rige|regirá)\s+en?\s*vigencia[^.]{0,220}\.)",
      r"((?:a contar de|desde)\s+(?:el\s+)?\d{1,2}\s+de\s+[A-Za-zÁÉÍÓÚáéíóúñÑ]+\s+de\s+20\d{2}[^.]{0,180}\.)",
      r"((?:a contar de|desde)\s+la\s+fecha\s+de\s+(?:su\s+)?(?:publicación|notificación)[^.]{0,180}\.)",
    ]
    for pat in patterns:
        m=re.search(pat,clean,re.I)
        if m:return m.group(1).strip()
    return None

def extract_references(text: str):
    patterns=[
      r"(Circular\s+(?:IF/)?N?[°º]?\s*\d+)",
      r"(Resoluci[oó]n(?:\s+Exenta)?\s+(?:IF/)?N?[°º]?\s*[\d\.]+)",
      r"(Oficio(?:\s+Circular)?\s+(?:IF/)?N?[°º]?\s*[\d\.]+)",
      r"(Ley\s+N?[°º]?\s*[\d\.]+)",
      r"(Decreto(?:\s+Supremo|\s+Exento)?\s+N?[°º]?\s*[\d\.]+)",
    ]
    out=[]
    for pat in patterns:
        for m in re.findall(pat,text or "",re.I):
            v=" ".join(m.split())
            if v.lower() not in [x.lower() for x in out]:out.append(v)
    return out[:8]

def fallback_normative_analysis(text: str, title: str, summary: str):
    clean=" ".join((text or "").split())
    validity=extract_validity(clean)
    # Candidate sentences: substantive verbs, excluding validity and boilerplate.
    sents=[s.strip() for s in re.split(r"(?<=[\.\!\?])\s+",clean) if 35<=len(s.strip())<=520]
    keywords=("modifica","complementa","instruye","prohíbe","establece","autoriza","rechaza","acoge","suspende","deberá","deberán","exige","incorpora","elimina","reemplaza")
    cands=[]
    for s in sents:
        low=s.lower()
        if validity and validity[:40].lower() in low:continue
        if "vigencia" in low:continue
        if any(x in low for x in ("visto:","trabajando para usted","intendencia de fondos")):continue
        if any(k in low for k in keywords):
            cands.append(s)
    pts=[]
    for s in cands:
        if s not in pts:pts.append(s[:360])
        if len(pts)>=3:break
    if not pts and summary:pts=[summary[:360]]
    review=[]
    low=clean.lower()
    if "plazo" in low:review.append("Identificar el plazo operativo específico exigido por la norma y el hito desde el cual comienza a contarse.")
    if any(x in low for x in ("archivo maestro","remitir","reportar","enviar información","informar a la superintendencia")):
        review.append("Verificar cambios en reportabilidad, formato de archivos, periodicidad y responsables de envío.")
    if any(x in low for x in ("cobertura","bonificación","bonificacion","beneficiario","prestación","prestacion")):
        review.append("Verificar cambios concretos en cobertura, bonificación, acceso o comunicación a beneficiarios.")
    if any(x in low for x in ("rechaza","acoge","reposición","reposicion","recurso")):
        review.append("Precisar el efecto de la resolución sobre el acto impugnado y si mantiene, modifica o suspende su aplicación.")
    return {
      "what_happened":summary or title,
      "why_it_matters":"El documento introduce o resuelve una instrucción regulatoria que puede requerir ajustes en procesos, información, cobertura o cumplimiento de los actores alcanzados.",
      "validity_text":validity,
      "key_points":pts[:3],
      "review_points":review[:3],
      "references":extract_references(clean),
    }

def spreadsheet_insights(url: str) -> list[str]:
    try:
        from openpyxl import load_workbook
        wb=load_workbook(io.BytesIO(_download(url)),read_only=True,data_only=True)
    except Exception:return []
    # Conservative V0: only report clear adjacent-period percentage changes.
    out=[]
    period_re=re.compile(r"(20\d{2}|ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)",re.I)
    for ws in wb.worksheets[:4]:
        rows=[list(r[:30]) for r in ws.iter_rows(min_row=1,max_row=250,values_only=True)]
        rows=[r for r in rows if any(v not in (None,"") for v in r)]
        for hi,h in enumerate(rows[:25]):
            cols=[j for j,v in enumerate(h) if v is not None and period_re.search(str(v))]
            if len(cols)<2:continue
            j1,j2=cols[-2],cols[-1]
            p1,p2=str(h[j1]),str(h[j2])
            best=None
            for r in rows[hi+1:]:
                if len(r)<=max(j1,j2):continue
                a,b=r[j1],r[j2]
                label=str(r[0]).strip() if r and r[0] not in (None,"") else ""
                if label and isinstance(a,(int,float)) and isinstance(b,(int,float)) and a not in (0,None):
                    pct=(b-a)/abs(a)*100
                    if abs(pct)<=500 and (best is None or abs(pct)>abs(best[0])):
                        best=(pct,label)
            if best:
                out.append(f"{ws.title}: {best[1]} mostró una variación de {best[0]:+.1f}% entre {p1} y {p2}.")
            break
        if len(out)>=3:break
    return out[:3]
