from __future__ import annotations
import json,os,sys
from datetime import date,timedelta
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request,urlopen

def select_weekly_signals(signals, today):
    """Only timely, traceable and relevant material can trigger a send."""
    eligible=[]
    for s in signals:
        try:
            published=date.fromisoformat(s['event_date'])
            url=urlparse(s['source_url'])
            score=int(s['radar_score']); confidence=int(s['confidence_score'])
        except (KeyError,TypeError,ValueError,OverflowError):
            continue
        if not (today-timedelta(days=7)<published<=today and url.scheme=='https' and url.netloc):
            continue
        if score<50 or confidence<75 or s.get('validation_status') not in ('automatic','cross_checked','validated'):
            continue
        if not s.get('title') or not (s.get('card_what') or s.get('what_happened')):
            continue
        eligible.append(s)
    return sorted(eligible,key=lambda s:(s['event_date'],int(s['radar_score'])),reverse=True)[:5]

def build_free_digest(signals,today):
    selected=select_weekly_signals(signals,today)
    if not selected:return None
    lines=['# Alicanto Salud · Resumen semanal','',f'{len(selected)} cambios relevantes publicados en los últimos 7 días.','']
    for i,s in enumerate(selected,1):
        lines.extend([f"**{i}. {s['title']}**",s.get('card_what') or s['what_happened'],f"[Fuente original]({s['source_url']})",''])
    lines.extend(['—','Alicanto Salud · Lo importante, para que no se te pase.'])
    return {'subject':'Alicanto Salud · Lo que cambió esta semana','body':'\n'.join(lines)}

def main():
    data=json.loads(Path("web/data/radar_today.json").read_text(encoding="utf-8"))
    payload=build_free_digest(data.get('signals',[]),date.today())
    if payload is None:
        print('No relevant signals published in the past week; no email.')
        return 0
    key=os.getenv("BUTTONDOWN_API_KEY")
    if not key:
        print("BUTTONDOWN_API_KEY not configured; digest not sent.")
        return 0
    req=Request("https://api.buttondown.com/v1/emails",
      data=json.dumps(payload).encode(),method="POST",
      headers={"Authorization":f"Token {key}","Content-Type":"application/json"})
    with urlopen(req,timeout=30) as r:
        resp=json.loads(r.read().decode())
    email_id=resp.get("id")
    if not email_id:raise RuntimeError('Email provider did not return an id; nothing published.')
    # Publish immediately to confirmed subscribers.
    req=Request(f"https://api.buttondown.com/v1/emails/{email_id}/publish",
      data=b"{}",method="POST",
      headers={"Authorization":f"Token {key}","Content-Type":"application/json"})
    with urlopen(req,timeout=30) as r:r.read()
    print("Weekly Alicanto digest sent.")
    return 0
if __name__=="__main__":sys.exit(main())
