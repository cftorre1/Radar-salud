from __future__ import annotations
import json,os,sys
from datetime import date
from pathlib import Path
from urllib.request import Request,urlopen

from radar_salud.newsletter import render_free_weekly,weekly_material

def _approved(config):
    return (config.get("provider")=="buttondown"
            and config.get("send_enabled") is True
            and config.get("privacy_approved") is True
            and config.get("double_opt_in") is True)

def main(config_path=Path("web/data/subscription.json"),data_path=Path("web/data/radar_today.json")):
    config=json.loads(config_path.read_text(encoding="utf-8"))
    if not _approved(config):
        print("Email delivery is not approved; digest not built or sent.")
        return 0
    data=json.loads(data_path.read_text(encoding="utf-8"))
    today=os.getenv("ALICANTO_DIGEST_DATE",date.today().isoformat())
    material=weekly_material(data.get("signals",[]),today)
    rendered=render_free_weekly(material,today)
    if not rendered:
        print("No relevant signals; no email.")
        return 0
    key=os.getenv("BUTTONDOWN_API_KEY")
    if not key:
        print("BUTTONDOWN_API_KEY not configured; relevant digest built but not sent.")
        return 0
    subject,body=rendered
    payload={"subject":subject,"body":body}
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
