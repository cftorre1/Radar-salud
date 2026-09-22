from __future__ import annotations
import json,os,sys
from pathlib import Path
from urllib.request import Request,urlopen

def main():
    key=os.getenv("BUTTONDOWN_API_KEY")
    if not key:
        print("BUTTONDOWN_API_KEY not configured; digest not sent.")
        return 0
    data=json.loads(Path("web/data/radar_today.json").read_text(encoding="utf-8"))
    sigs=data.get("signals",[])
    # Weekly email is a scan, not a copy of the website.
    recent=sorted(sigs,key=lambda s:s.get("event_date") or "",reverse=True)[:8]
    if not recent:
        print("No relevant signals; no email.")
        return 0
    lines=["# Alicanto Salud · Resumen semanal","",f"{len(recent)} cambios para revisar esta semana.",""]
    for i,s in enumerate(recent[:5],1):
        lines.append(f"**{i}. {s.get('title','')}**")
        q=s.get("what_happened","")
        if q:lines.append(q[:320])
        if s.get("source_url"):lines.append(f"[Ver detalle / fuente]({s['source_url']})")
        lines.append("")
    lines.append("—")
    lines.append("Alicanto Salud · Lo importante, para que no se te pase.")
    body="\n".join(lines)
    payload={"subject":"Alicanto Salud · Lo que cambió esta semana","body":body}
    req=Request("https://api.buttondown.com/v1/emails",
      data=json.dumps(payload).encode(),method="POST",
      headers={"Authorization":f"Token {key}","Content-Type":"application/json"})
    with urlopen(req,timeout=30) as r:
        resp=json.loads(r.read().decode())
    email_id=resp.get("id")
    if not email_id:raise RuntimeError(resp)
    # Publish immediately to confirmed subscribers.
    req=Request(f"https://api.buttondown.com/v1/emails/{email_id}/publish",
      data=b"{}",method="POST",
      headers={"Authorization":f"Token {key}","Content-Type":"application/json"})
    with urlopen(req,timeout=30) as r:r.read()
    print("Weekly Alicanto digest sent.")
    return 0
if __name__=="__main__":sys.exit(main())
