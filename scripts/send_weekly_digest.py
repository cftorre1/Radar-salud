from __future__ import annotations
import html,json,os,sys
from datetime import date
from pathlib import Path
from urllib.request import Request,urlopen

from radar_salud.newsletter import render_free_weekly,weekly_material

def select_weekly_signals(signals,today):
    """Compatibility surface for deterministic digest selection tests."""
    return weekly_material(signals,today)[:5]

def build_free_digest(signals,today):
    selected=select_weekly_signals(signals,today)
    rendered=render_free_weekly(selected,today.isoformat())
    if not rendered:return None
    subject,body=rendered
    return {"subject":subject,"body":body}

def _approved(config):
    return (config.get("provider")=="mailerlite"
            and config.get("send_enabled") is True
            and config.get("privacy_approved") is True
            and config.get("double_opt_in") is True
            and config.get("api_html_content_supported") is True
            and (config.get("sender") or {}).get("verified") is True)

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
    key=os.getenv("MAILERLITE_API_KEY")
    group_id=(config.get("groups") or {}).get("newsletter_weekly")
    sender=config.get("sender") or {}
    if not key or not group_id or not sender.get("email") or not sender.get("name"):
        print("MailerLite credentials, newsletter group or verified sender not configured; relevant digest built but not sent.")
        return 0
    subject,body=rendered
    content="<p>"+html.escape(body).replace("\n\n","</p><p>").replace("\n","<br>")+"</p>"
    payload={"name":subject,"type":"regular","groups":[str(group_id)],"emails":[{
        "subject":subject,"from_name":sender["name"],"from":sender["email"],
        "reply_to":sender.get("reply_to") or sender["email"],"content":content,
    }]}
    req=Request("https://connect.mailerlite.com/api/campaigns",
      data=json.dumps(payload).encode(),method="POST",
      headers={"Authorization":f"Bearer {key}","Content-Type":"application/json",
               "Accept":"application/json"})
    with urlopen(req,timeout=30) as r:
        resp=json.loads(r.read().decode())
    campaign_id=(resp.get("data") or {}).get("id")
    if not campaign_id:raise RuntimeError(resp)
    req=Request(f"https://connect.mailerlite.com/api/campaigns/{campaign_id}/schedule",
      data=json.dumps({"delivery":"instant"}).encode(),method="POST",
      headers={"Authorization":f"Bearer {key}","Content-Type":"application/json",
               "Accept":"application/json"})
    with urlopen(req,timeout=30) as r:r.read()
    print("Weekly Alicanto digest sent.")
    return 0
if __name__=="__main__":sys.exit(main())
