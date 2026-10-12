"""Independent index control: raw provider fields/HTML, not collector DOM output."""
import json
import re
from datetime import date, datetime
from html import unescape
from urllib.parse import urljoin

def day(value, as_of):
    try:
        result = date.fromisoformat(value[:10]) if re.match(r"^\d{4}-\d{2}-\d{2}", value) else datetime.strptime(value,"%d %B %Y").date()
        return result.isoformat() if result <= as_of else None
    except (ValueError, TypeError): return None

def native_control(raw, route, as_of, page_url):
    control=[]
    if route["format"] == "who_api":
        payload=json.loads(raw)
        prefix={"news":"/news/item", "publications":"/publications/i/item", "disease_outbreak_news":"/emergencies/disease-outbreak-news/item"}[route["section"]]
        for item in payload.get("value",[]):
            suffix=item.get("ItemDefaultUrl","")
            dates=[day(str(item[key]),as_of) for key in ("FormatedDate","FormattedDate","PublicationDateAndTime") if item.get(key)]
            control.append({"url":"https://www.who.int"+(suffix if suffix.startswith(prefix+"/") else prefix+suffix),"published_at":dates[0] if dates and None not in dates and len(set(dates))==1 else None})
    else:
        text=raw.decode(errors="replace")
        # Date is immediately before the title field in the native Drupal cards.
        for match in re.finditer(r'<div\s+class="[^"]*views-field-title[^"]*"[^>]*>.*?<a\b[^>]*href="([^"]+)"',text,re.S):
            prefix=text[:match.start()]
            times=list(re.finditer(r'<time\b[^>]*datetime="([^"]+)"',prefix))
            control.append({"url":urljoin(page_url,unescape(match[1])),"published_at":day(times[-1][1],as_of) if times else None})
    return control
