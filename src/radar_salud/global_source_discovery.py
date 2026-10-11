"""Official WHO/PAHO discovery. Produces evidence candidates, never Global cards."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from html import unescape
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit, urljoin

from .global_discovery_common import CaptureClient, Document, canonical_url, publication_day
from .pending_queue import atomic_json
from .global_native_control import native_control


def in_window(day, as_of: date, days: int):
    return bool(day and (as_of - timedelta(days=days-1)).isoformat() <= day <= as_of.isoformat())

def classify(title, section):
    text = ''.join(c for c in unicodedata.normalize('NFKD', title.casefold()) if not unicodedata.combining(c))
    noise = r"\b(welcomes? .{0,30}members|appointed|appointment|elected president|anniversary|webinar|training|celebrates|congratulates|nombramiento|elegid[oa] presidente|aniversario|capacitacion|seminario web|celebracion|felicita)\b"
    if re.search(noise, text):
        return {"materiality": "routine", "priority": 0, "category": "institutional_routine", "reason": "ceremony_training_or_appointment"}
    rules = [
        ("emergency", 95, r"alert|outbreak|brote|epidemiological update|actualizacion epidemiologica|public health emergency|emergencia de salud publica|measles|sarampion|avian influenza|influenza aviar|ebola"),
        ("policy_guidelines", 90, r"guideline|directri|recomend|recommendation|regulat|regulac|normativ|policy|politica|mental health care|salud mental|community-based|framework|marco|roadmap|hoja de ruta|plan .{0,30}salud"),
        ("financing_systems", 88, r"financ|funding|budget|presupuesto|investment|inversion|health system|sistema.{0,10}salud|workforce|fuerza laboral|health coverage|cobertura.{0,10}salud|social protection|proteccion social"),
        ("epidemiology", 85, r"influenza|respirator|epidemiolog|surveillance|vigilancia|intelligence|deaths|muertes|cases|casos|burden|carga|elimina|mortali|immuniz|inmuniz|vaccin|vacun"),
        ("technical_document", 75, r"report|informe|strategy|estrategia|evaluat|evaluac|technical|tecnic|research|investigacion|monitoring|monitoreo|data|datos|survey|encuesta"),
    ]
    if section == "disease_outbreak_news":
        return {"materiality": "candidate", "priority": 95, "category": "emergency", "reason": "official_disease_outbreak_notification"}
    for category, priority, pattern in rules:
        if re.search(pattern, text):
            return {"materiality": "candidate", "priority": priority, "category": category, "reason": "material_topic_requires_editorial_fact_and_consequence_review"}
    return {"materiality": "undetermined", "priority": 0, "category": "context", "reason": "metadata_insufficient_to_establish_business_materiality"}

def entities(title, source, section):
    found = [{"name": source.upper(), "kind": "publisher", "basis": "official_origin", "independence_group": "WHO_UN_SYSTEM"}]
    for name, pattern in [("Chile", r"\bChile(?:an)?\b"), ("Americas", r"\bAmericas\b|Américas"),
                          ("Democratic Republic of the Congo", r"Democratic Republic of the Congo"),
                          ("Russian Federation", r"Russian Federation")]:
        if re.search(pattern, title, re.I):
            found.append({"name": name, "kind": "geography", "basis": "publisher_title"})
    if section.startswith("chile_news") and not any(x["name"] == "Chile" for x in found):
        found.append({"name": "Chile", "kind": "taxonomy_scope", "basis": "official_country_filter_c65", "direct_local_effect_verified": False})
    return found

def reporting_period(title):
    match = re.search(r"(?:Semana Epidemiológica|Epidemiological Week)\s*(\d{1,2})", title, re.I)
    return {"label": match.group(0), "week": int(match[1]), "year": None, "basis": "publisher_title"} if match else None

def parse_who_index(payload, section, as_of):
    if not isinstance(payload, dict) or not isinstance(payload.get("value"), list):
        raise ValueError("WHO API schema changed")
    prefix = {"news": "/news/item", "publications": "/publications/i/item", "disease_outbreak_news": "/emergencies/disease-outbreak-news/item"}[section]
    rows = []
    for item in payload["value"]:
        title = unescape(str((item.get("OverrideTitle") if item.get("UseOverrideTitle") else item.get("Title")) or ""))
        suffix = str(item.get("ItemDefaultUrl") or "")
        if not title or not suffix.startswith("/"):
            raise ValueError("WHO missing official identity")
        url = canonical_url("https://www.who.int" + (suffix if suffix.startswith(prefix + "/") else prefix + suffix))
        raw_dates = [str(item[k]) for k in ("FormatedDate", "FormattedDate", "PublicationDateAndTime") if item.get(k)]
        dates = {publication_day(day, as_of) for day in raw_dates}; dates.discard(None)
        valid = len(dates) == 1 and all(publication_day(day, as_of) for day in raw_dates)
        row = {"url": url, "title": title, "source": "who", "section": section,
               "index_published_at": next(iter(dates)) if valid else None,
               "raw_publication_dates": raw_dates, "publication_date_basis": "official_API_publication_field",
               "publication_date_error": None if valid else "missing_future_or_conflicting_index_date",
               "event_date": (item.get("EmergencyEvent") or {}).get("EmergencyEventStartDate"),
               "event_id": (item.get("EmergencyEvent") or {}).get("EventId"),
               "effective_date": None, "reporting_period": reporting_period(title),
               "document_links": [item["DownloadUrl"]] if item.get("DownloadUrl") else []}
        rows.append(row)
    return rows

def parse_paho_index(html, section, as_of, base):
    document = Document(html).root
    rows = []
    for field in document.nodes():
        if not field.has_class("views-field-title"):
            continue
        anchors = [a for a in field.nodes("a") if a.text() and a.attrs.get("href")]
        if len(anchors) != 1:
            raise ValueError("PAHO title card structure changed")
        anchor = anchors[0]
        parent = field.parent
        dates = list(parent.nodes("time")) if parent else []
        if len(dates) != 1:
            raise ValueError("PAHO card has ambiguous publication date")
        raw_date = dates[0].attrs.get("datetime", dates[0].text())
        day = publication_day(raw_date, as_of)
        rows.append({"url": canonical_url(anchor.attrs["href"], base), "title": anchor.text(),
                     "source": "paho", "section": section, "index_published_at": day,
                     "raw_publication_dates": [raw_date], "publication_date_basis": "official_list_displayed_created_time",
                     "publication_date_error": None if day else "missing_or_future_index_date",
                     "event_date": None, "event_id": None, "effective_date": None,
                     "reporting_period": reporting_period(anchor.text()), "document_links": []})
    next_links = [a.attrs["href"] for a in document.nodes("a") if "next" in a.attrs.get("rel", "").split() and a.attrs.get("href")]
    if len(set(next_links)) > 1:
        raise ValueError("PAHO ambiguous pagination")
    return rows, canonical_url(next_links[0], base) if next_links else None

def detail_metadata(html, as_of, url):
    document = Document(html).root
    h1 = [node.text() for node in document.nodes("h1") if node.text()]
    if len(h1) != 1:
        raise ValueError("detail missing unique H1 / challenge suspected")
    raw_dates = []
    for node in document.nodes("meta"):
        key = (node.attrs.get("property") or node.attrs.get("name") or "").lower()
        if key in {"article:published_time", "datepublished", "citation_publication_date", "dc.date.issued"}:
            raw_dates.append(node.attrs.get("content", ""))
    for node in document.nodes():
        if node.has_class("date") or node.has_class("field--name-created"):
            match = re.match(r"\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})\b", node.text())
            if match:
                raw_dates.append(match[1])
    canonical = [node.attrs["href"] for node in document.nodes("link") if node.attrs.get("rel") == "canonical" and node.attrs.get("href")]
    alternates = [node.attrs["href"] for node in document.nodes("link") if node.attrs.get("rel") == "alternate" and node.attrs.get("hreflang") and node.attrs.get("href")]
    alternates += [node.attrs["href"] for node in document.nodes("a") if node.has_class("language-link") and node.attrs.get("hreflang") and node.attrs.get("href")]
    docs = []
    for node in document.nodes("a"):
        href = node.attrs.get("href", "")
        if ".pdf" in href.lower() or "/bitstreams/" in href or "/bitstream/" in href:
            absolute = __import__('urllib.parse', fromlist=['urljoin']).urljoin(url, href)
            if urlsplit(absolute).scheme == "https" and urlsplit(absolute).hostname in {"www.who.int", "cdn.who.int", "iris.who.int", "www.paho.org", "iris.paho.org"}:
                docs.append(absolute)
    return {"title": h1[0], "publication_dates": sorted({day for value in raw_dates if (day := publication_day(value, as_of))}),
            "raw_publication_dates": raw_dates, "invalid_or_future_publication_fields": [v for v in raw_dates if not publication_day(v, as_of)],
            "canonical_url": canonical_url(canonical[0], url) if canonical else url,
            "alternate_language_urls": sorted({canonical_url(value, url) for value in alternates if urlsplit(__import__('urllib.parse',fromlist=['urljoin']).urljoin(url,value)).hostname in {"www.who.int", "www.paho.org"}}),
            "document_links": sorted(set(docs))}

def verified_news_view(document, route, bounds, *, empty, allow_pager=False):
    """A complete native empty view, never a bare HTTP200 or initial-page proof."""
    required={'news-grid','view','view-news','view-id-news','view-display-id-news_page'}
    views=[n for n in document.nodes() if required<=set(n.attrs.get('class','').split())]
    headings=[n.text() for n in document.nodes('h1')]
    if len(views)!=1 or not views[0].closed or headings!=['Noticias' if '/es/' in route['url'] else 'News']:
        return False
    view=views[0];forms=list(view.nodes('form'))
    if len(forms)!=1 or not forms[0].closed:
        return False
    form=forms[0]
    if form.attrs.get('method','').lower()!='get' or form.attrs.get('data-drupal-selector')!='views-exposed-form-news-news-page' or form.attrs.get('id')!='views-exposed-form-news-news-page':
        return False
    try:
        action=urlsplit(canonical_url(form.attrs.get('action',''),route['url']))
        if action[:3]!=urlsplit(route['url'])[:3] or action.query:return False
    except ValueError:
        return False
    inputs=[n for n in form.nodes('input') if n.attrs.get('name') in {'date[min]','date[max]'}]
    if len(inputs)!=2 or {n.attrs.get('name'):n.attrs.get('value') for n in inputs}!={'date[min]':bounds['query_from'],'date[max]':bounds['query_to']}:
        return False
    forbidden=({'pager','pager-nav','pagination'} if not allow_pager else set())|({'views-row','view-content','views-field-title','views-field-created','field--name-created'} if empty else set())
    if any(forbidden&set(n.attrs.get('class','').split()) or not allow_pager and any(c.startswith(('pager__','js-pager__')) for c in n.attrs.get('class','').split()) for n in view.nodes()):
        return False
    if not empty:
        for cls in ('views-field-title','views-field-created'):
            inside={id(n) for n in view.nodes() if n.has_class(cls)}
            if not inside or inside!={id(n) for n in document.nodes() if n.has_class(cls)}:return False
    if empty and allow_pager:
        navs=[n for n in view.nodes('nav') if n.has_class('pager-nav')]
        if len(navs)!=1:return False
        headers=list(navs[0].nodes('h2'))
        if len(headers)!=1 or not headers[0].closed or headers[0].parent is not navs[0] or headers[0].attrs.get('id')!='pagination-heading' or headers[0].text()!=('Paginación' if '/es/' in route['url'] else 'Pagination'):return False
        if any(n.tag in {'time','article'} or n.tag=='meta' and (n.attrs.get('property') or n.attrs.get('name') or '').lower() in {'article:published_time','datepublished','citation_publication_date','dc.date.issued'} for n in document.nodes()):return False
        excluded={id(form),id(navs[0])}
        def outside(node):
            if id(node) in excluded:return ''
            return ' '.join(outside(c) if hasattr(c,'tag') else c for c in node.children)
        if outside(view).strip():return False
        inside={id(n) for n in navs[0].nodes()}|{id(navs[0])}
        if any(id(n) not in inside for n in document.nodes() if any(c in {'pager','pager-nav','pagination'} or c.startswith(('pager__','js-pager__')) for c in n.attrs.get('class','').split())):return False
        if any(id(a) not in inside for a in document.nodes('a') if {'next','last','prev','previous','first'}&set(a.attrs.get('rel','').split())):return False
    return (not empty or allow_pager or view.text()==form.text()) and (allow_pager or not any(any(c in {'pager','pager-nav','pagination'} or c.startswith(('pager__','js-pager__')) for c in n.attrs.get('class','').split()) for n in document.nodes())) and (allow_pager or not any({'next','last','prev','previous','first'}&set(n.attrs.get('rel','').split()) for n in document.nodes('a')))

def verified_empty_news_view(document, route, bounds):
    return verified_news_view(document,route,bounds,empty=True)

def native_numbered_pager(document, route, bounds, page_url, *, empty=False):
    """Verify the observed bilingual Drupal pager, never infer an end from no-next."""
    if not verified_news_view(document,route,bounds,empty=empty,allow_pager=True):return None
    identity=lambda u:(urlsplit(u)[:3],sorted((k,v) for k,v in parse_qsl(urlsplit(u).query,keep_blank_values=True) if k!='page'))
    values=[v for k,v in parse_qsl(urlsplit(page_url).query,keep_blank_values=True) if k=='page']
    if len(values)>1 or values and not re.fullmatch(r'0|[1-9][0-9]*',values[0]):return None
    current=int(values[0]) if values else 0
    view=next(n for n in document.nodes() if n.has_class('view-id-news'))
    navs=[n for n in view.nodes('nav') if n.has_class('pager-nav')]
    if len(navs)!=1 or not navs[0].has_class('text-center') or not navs[0].closed or navs[0].attrs.get('role')!='navigation' or navs[0].attrs.get('aria-labelledby')!='pagination-heading':return None
    nav=navs[0];lists=[n for n in nav.nodes('ul') if {'pagination','js-pager__items'}<=set(n.attrs.get('class','').split())]
    if len(lists)!=1 or not lists[0].closed or lists[0].parent is not nav or any(not n.closed for n in nav.nodes()):return None
    if any(hasattr(n,'tag') and n.tag!='li' for n in lists[0].children):return None
    lis=list(lists[0].nodes('li'));numbers=[];active=[];targets=[];forward=False;controls=[]
    if not lis or any(not li.closed or li.parent is not lists[0] or not li.has_class('pager__item') for li in lis):return None
    allowed={'pager__item--first','pager__item--previous','pager__item--next','pager__item--last'}
    for li in lis:
        modifiers={c for c in li.attrs.get('class','').split() if c.startswith('pager__item--')}
        if not modifiers<=allowed or len(modifiers)>1:return None
        links=list(li.nodes('a'))
        if len(links)!=1 or not links[0].closed or links[0].parent is not li:return None
        anchor=links[0];raw_target=urlsplit(urljoin(page_url,anchor.attrs.get('href','')))
        canonical_url(urlunsplit(raw_target))
        if raw_target.fragment:return None
        target=urlunsplit(raw_target)
        vals=[v for k,v in parse_qsl(urlsplit(target).query,keep_blank_values=True) if k=='page']
        if identity(target)!=identity(page_url) or len(vals)!=1 or not re.fullmatch(r'0|[1-9][0-9]*',vals[0]):return None
        number=int(vals[0]);targets.append(number)
        forward=forward or bool(modifiers&{'pager__item--next','pager__item--last'} or {'next','last'}&set(anchor.attrs.get('rel','').split()))
        if modifiers:
            modifier=next(iter(modifiers));controls.append(modifier)
            if set(li.attrs.get('class','').split())!={'pager__item',modifier} or anchor.attrs.get('aria-current'):return None
            if modifier in {'pager__item--first','pager__item--previous'}:
                expected=0 if modifier=='pager__item--first' else current-1
                if current<=0 or number!=expected or set(anchor.attrs.get('rel','').split())!={'prev'}:return None
            elif modifier=='pager__item--next' and (number!=current+1 or set(anchor.attrs.get('rel','').split())!={'next'}):return None
            elif modifier=='pager__item--last' and number<=current:return None
            continue
        if anchor.attrs.get('rel'):return None
        match=re.fullmatch(r'(Page|Current page|Página|Página actual) ([1-9][0-9]*)',li.text())
        if not match or int(match[2])-1!=number:return None
        numbers.append(number)
        is_active=li.has_class('is-active') and li.has_class('active')
        if is_active:
            label='Página actual' if '/es/' in route['url'] else 'Current page'
            if match[1]!=label or anchor.attrs.get('aria-current')!='page' or anchor.attrs.get('title')!=label:return None
            active.append(number)
        elif set(li.attrs.get('class','').split())!={'pager__item'} or match[1]!=('Página' if '/es/' in route['url'] else 'Page') or anchor.attrs.get('title')!=f'Go to page {number+1}' or anchor.attrs.get('aria-current'):return None
    expected_backward=1 if current>0 else 0
    if any(controls.count(c)!=expected_backward for c in ('pager__item--first','pager__item--previous')) or len(controls)!=len(set(controls)):return None
    if expected_backward and controls[:2]!=['pager__item--first','pager__item--previous']:return None
    if len(list(nav.nodes('a')))!=len(lis) or not numbers or numbers!=list(range(max(numbers)+1)) or active!=[current]:return None
    maximum=max(numbers+targets)
    return {'current':current,'maximum':maximum,'terminal':not forward and current==maximum and 0<current<8}

def verified_clamped_empty_end(document, previous_document, route, bounds, page_url, previous_url):
    """The observed empty overflow keeps the exact previous terminal pager."""
    identity=lambda u:(urlsplit(u)[:3],sorted((k,v) for k,v in parse_qsl(urlsplit(u).query,keep_blank_values=True) if k!='page'))
    def page(u):
        values=[v for k,v in parse_qsl(urlsplit(u).query,keep_blank_values=True) if k=='page']
        return int(values[0]) if len(values)==1 and re.fullmatch(r'0|[1-9][0-9]*',values[0]) else None
    prior=page(previous_url);actual=page(page_url)
    if prior is None or actual!=prior+1 or identity(page_url)!=identity(previous_url):return None
    before=native_numbered_pager(previous_document,route,bounds,previous_url)
    after=native_numbered_pager(document,route,bounds,previous_url,empty=True)
    if not before or not before['terminal'] or after!=before:return None
    def signature(doc):
        nav=next(n for n in doc.nodes('nav') if n.has_class('pager-nav'))
        return [(n.tag,sorted(n.attrs.items()),n.text()) for n in [nav,*nav.nodes()]]
    if signature(document)!=signature(previous_document):return None
    return {'requested_page':actual,'clamped_current':prior,'maximum':before['maximum'],'terminal':True,'previous_page_url':previous_url}

def collect_route(client, route, as_of, max_pages):
    if route.get("date_slice_days"):
        return collect_date_slices(client,route,as_of,max_pages)
    rows, pages, seen = [], [], set()
    advertised_last=None;previous_without_next=False;previous_single_page_verified=False;previous_structure_verified=False;previous_numbered_end=False;previous_document=None
    cutoff = (as_of - timedelta(days=89)).isoformat()
    complete, stop = False, "page_limit"
    url = route["url"]
    if route["format"] == "who_api":
        body, _ = client.fetch(url)
        match = re.search(r'hubsfiltering\([^,]+,\s*"[^"]+",\s*"([^"]+)"', body.decode(errors="replace"))
        if not match:
            raise ValueError("observed public API missing from official landing")
        url = canonical_url(match[1], "https://www.who.int")
    for page in range(max_pages):
        page_url = url
        if route["format"] == "who_api":
            parts = urlsplit(url); query = [(k,v) for k,v in parse_qsl(parts.query) if k not in {"$top", "$skip"}]
            page_url = urlunsplit((*parts[:3], urlencode(query + [("$skip", str(page*50)), ("$top", "50")]), ""))
        try:
            raw, capture = client.fetch(page_url)
        except Exception as exc:
            stop = "page_fetch_failure: " + type(exc).__name__ + ": " + str(exc)[:200]
            break
        control = native_control(raw, route, as_of, page_url)
        try:
            if route["format"] == "who_api":
                found = parse_who_index(json.loads(raw), route["section"], as_of); next_url = True
            else:
                found, next_url = parse_paho_index(raw.decode(errors="replace"), route["section"], as_of, page_url)
        except Exception as exc:
            pages.append({"url":page_url,"capture":capture,"native_control":control,"native_records":len(control),"items":[]})
            stop = "page_parse_failure: " + type(exc).__name__ + ": " + str(exc)[:200]
            break
        ids = tuple(item["url"] for item in found)
        for item in found:
            item["index_evidence"] = [{"listing_url": page_url, "body_sha256": capture["body_sha256"], "fetched_at": capture["fetched_at"], "http_status":capture["http_status"], "tls_verified":capture["tls_verified"]}]
        pages.append({"url": page_url, "capture": capture, "native_records": len(control), "native_control":control,"items": found})
        if {x["url"] for x in control} != {x["url"] for x in found}:
            rows.extend(found); stop="independent_native_control_mismatch"; break
        if route.get("date_partition"):
            document=Document(raw.decode(errors="replace")).root
            bounds=route["date_partition"]
            echoed={n.attrs.get("name"):n.attrs.get("value") for n in document.nodes("input") if n.attrs.get("name") in {"date[min]","date[max]"}}
            if echoed != {"date[min]":bounds["query_from"],"date[max]":bounds["query_to"]} or any(not row["index_published_at"] or not bounds["query_from"]<=row["index_published_at"]<=bounds["query_to"] for row in found):
                rows.extend(found);stop="page_parse_failure: date_filter_not_corroborated";break
            if found and not verified_news_view(document,route,bounds,empty=False,allow_pager=True):
                rows.extend(found);stop='page_parse_failure: dated_news_view_unverified';break
            numbered=native_numbered_pager(document,route,bounds,page_url) if found else None
            if found and numbered is None and any(any(c=='pager-nav' or c=='pager' or c.startswith(('pager__','js-pager__')) for c in n.attrs.get('class','').split()) for n in document.nodes()):
                rows.extend(found);stop='page_parse_failure: native_numbered_pager_unverified';break
            if numbered:
                pages[-1]['numbered_native_pager']=numbered
                if numbered['maximum']>=8:
                    rows.extend(found);stop='date_partition_saturated_native_cap';break
            last_links=[a.attrs["href"] for a in document.nodes("a") if "last" in a.attrs.get("rel","").split()]
            last_pages=[]
            for value in last_links:
                last_url=canonical_url(value,page_url);last_query=dict(parse_qsl(urlsplit(last_url).query))
                identity=lambda value:(urlsplit(value)[:3],sorted((k,v) for k,v in parse_qsl(urlsplit(value).query,keep_blank_values=True) if k!='page'))
                if identity(last_url)!=identity(page_url) or len([k for k,_ in parse_qsl(urlsplit(last_url).query) if k=='page'])!=1:
                    rows.extend(found);stop='page_parse_failure: dated_pager_identity_conflict';break
                last_pages.append(int(last_query.get('page',0)))
            if stop.startswith('page_parse_failure'):break
            if last_pages and max(last_pages)>=8:
                rows.extend(found);stop="date_partition_saturated_native_cap";break
            if last_pages:advertised_last=max(last_pages)
            if not found:
                clamped=verified_clamped_empty_end(document,previous_document,route,bounds,page_url,pages[-2]['url']) if page>1 and previous_numbered_end and previous_without_next and previous_structure_verified and pages[-2]['items'] and capture.get('final_url')==page_url else None
                if clamped:
                    pages[-1]['clamped_empty_native_pager']=clamped
                    complete=True;stop='date_partition_native_empty_after_clamped_numbered_end';break
                # No official initial-empty message protocol was verified live.
                # A generic view-empty can be an error or an unrelated search view.
                if page>0 and advertised_last==page-1 and previous_without_next and previous_structure_verified and pages[-2]['items'] and verified_empty_news_view(document,route,bounds):
                    complete=True;stop='date_partition_native_empty_after_advertised_end';break
                if page==1 and advertised_last is None and previous_single_page_verified and verified_empty_news_view(document,route,bounds):
                    complete=True;stop='date_partition_single_page_native_end_probe';break
                if page>1 and previous_numbered_end and previous_without_next and previous_structure_verified and pages[-2]['items'] and verified_empty_news_view(document,route,bounds):
                    complete=True;stop='date_partition_native_empty_after_numbered_end';break
                stop='date_partition_empty_unverified';break
            previous_document=document
            previous_numbered_end=bool(numbered and numbered['terminal'])
            previous_without_next=not next_url
            previous_structure_verified=bool(found) and verified_news_view(document,route,bounds,empty=False,allow_pager=True)
            previous_single_page_verified=page==0 and advertised_last is None and bool(found) and verified_news_view(document,route,bounds,empty=False)
        if not found:
            complete, stop = page > 0, "empty_native_page" if page > 0 else "empty_initial_page_unverified"; break
        if ids in seen:
            stop = "date_partition_repeated_page_unverified" if route.get("date_partition") else "repeated_pagination_page"
            break
        seen.add(ids); rows.extend(found)
        dates = [item["index_published_at"] for item in found if item["index_published_at"]]
        if len(dates) == len(found) and dates == sorted(dates, reverse=True) and min(dates) < cutoff:
            complete, stop = True, "verified_older_boundary"; break
        if not next_url:
            if route["format"] == "paho_html":
                # Live PAHO advertises page8 as last, but page9 has distinct
                # records and page10 repeats page9. Probe the observed page
                # parameter within max_pages; a repeat cannot prove 90 days.
                parts = urlsplit(page_url)
                query = parse_qsl(parts.query,keep_blank_values=True)
                current = int(next((v for k,v in query if k=="page"), "0"))
                next_url = urlunsplit((*parts[:3],urlencode([(k,v) for k,v in query if k!="page"]+[("page",str(current+1))]),""))
                pages[-1]["pagination_basis"] = "bounded_probe_of_observed_public_page_parameter_after_advertised_last"
            else:
                complete, stop = True, "native_archive_exhausted"; break
        if route["format"] != "who_api":
            url = next_url
    return {"route": route, "pages": pages, "items": rows, "archive_complete": complete,
            "stop_reason": stop, "date_pending": sum(not x["index_published_at"] for x in rows)}

def collect_date_slices(client,route,as_of,max_pages):
    """Use the publisher's exposed date form; never derive a publication from the query."""
    raw,landing=client.fetch(route["url"])
    document=Document(raw.decode(errors="replace")).root
    forms=[f for f in document.nodes("form") if f.attrs.get("method","").lower()=="get" and {"date[min]","date[max]"}<={n.attrs.get("name") for n in f.nodes("input")}]
    if len(forms)!=1 or canonical_url(forms[0].attrs.get("action",""),route["url"]).split('?')[0]!=route["url"].split('?')[0]:
        raise ValueError("official_date_filter_form_missing_or_changed")
    start=as_of-timedelta(days=89);queue=[]
    while start<=as_of:
        end=min(as_of,start+timedelta(days=route["date_slice_days"]-1));queue.append((start,end));start=end+timedelta(days=1)
    slices=[];pages=[];rows={};failures=[]
    while queue and len(pages)<max_pages:
        start,end=queue.pop(0)
        # One-day overlap handles the publisher's midnight/date-max convention.
        query_from=(start-timedelta(days=1)).isoformat();query_to=(end+timedelta(days=1)).isoformat()
        parts=urlsplit(route["url"]);query=parse_qsl(parts.query)
        url=urlunsplit((*parts[:3],urlencode(query+[("date[min]",query_from),("date[max]",query_to)]),""))
        child={k:v for k,v in route.items() if k!="date_slice_days"}
        child.update(url=url,date_partition={"from":start.isoformat(),"to":end.isoformat(),"query_from":query_from,"query_to":query_to})
        result=collect_route(client,child,as_of,max_pages-len(pages));pages.extend(result["pages"])
        for row in result["items"]:
            if row["url"] not in rows: rows[row["url"]]=dict(row,index_evidence=list(row["index_evidence"]),raw_publication_dates=list(row["raw_publication_dates"]))
            else:
                previous=rows[row["url"]];previous["index_evidence"].extend(row["index_evidence"])
                previous["raw_publication_dates"]=sorted(set(previous["raw_publication_dates"]+row["raw_publication_dates"]))
                if previous["index_published_at"]!=row["index_published_at"]:
                    previous.update(index_published_at=None,publication_date_error="conflicting_official_listing_dates")
        if result["stop_reason"].startswith(("page_fetch_failure","page_parse_failure","independent_native_control_mismatch")):
            failures.append({"url":url,"error":result["stop_reason"]})
        if result["stop_reason"]=="date_partition_saturated_native_cap" and start<end:
            midpoint=start+(end-start)//2;queue[:0]=[(start,midpoint),(midpoint+timedelta(days=1),end)];continue
        slices.append({**child["date_partition"],"url":url,"archive_complete":result["archive_complete"],"stop_reason":result["stop_reason"],"pages":len(result["pages"])})
    complete=not queue and bool(slices) and all(s["archive_complete"] for s in slices)
    return {"route":route,"pages":pages,"items":list(rows.values()),"archive_complete":complete,
        "stop_reason":"verified_date_partition_coverage" if complete else "date_partition_coverage_incomplete",
        "date_pending":sum(not x["index_published_at"] for x in rows.values()),"date_partitions":slices,
        "date_filter_form_evidence":landing,"unvisited_partitions":len(queue),"partition_technical_failures":failures}

def verify_item(client, row, as_of):
    item = dict(row); item["published_at"] = row["index_published_at"]
    item["source_aliases"] = [row["url"]]; item["sections"] = row.get("discovered_sections", [row["section"]])
    item["publication_ready"] = False; item["content_use"] = "metadata_and_link_only"
    item["classification"] = classify(row["title"], row["section"])
    item["entities"] = entities(row["title"], row["source"], "chile_news" if any(s.startswith("chile_news") for s in item["sections"]) else row["section"])
    item["reason"] = row["publication_date_error"]
    item["status"] = "pending" if item["reason"] else "discovered"
    try:
        raw, capture = client.fetch(row["url"])
        metadata = detail_metadata(raw.decode(errors="replace"), as_of, row["url"])
        item["detail_evidence"] = {"capture": capture, "metadata": metadata}
        if canonical_url(capture.get("final_url", row["url"])).rstrip("/") != row["url"].rstrip("/"):
            raise ValueError("detail_final_identity_mismatch")
        normalize = lambda title: re.sub(r"\W+", "", title.casefold())
        if normalize(metadata["title"]) != normalize(row["title"]):
            # DON620 live index adds the definite article to an official country.
            # Restrict this compatibility to the identical geographic suffix.
            country_title = lambda title: re.sub(r" - (?:the )?Russian Federation$", " - Russian Federation", title)
            if row["section"] != "disease_outbreak_news" or country_title(metadata["title"]) != country_title(row["title"]):
                raise ValueError("index_detail_title_mismatch")
            item["title_match_basis"] = "official_DON_Russian_Federation_definite_article_variation"
        if metadata["canonical_url"].rstrip("/") != row["url"].rstrip("/"):
            raise ValueError("detail_canonical_identity_mismatch")
        item["document_links"] = sorted(set(row["document_links"] + metadata["document_links"]))
        observed = metadata["publication_dates"]
        if metadata["invalid_or_future_publication_fields"]:
            item.update(published_at=None, status="pending", reason="invalid_or_future_detail_publication_field")
        elif len(observed) > 1 or (observed and observed[0] != row["index_published_at"]):
            item.update(published_at=None, status="pending", reason="index_detail_publication_conflict")
        elif item["published_at"]:
            material = item["classification"]["materiality"]
            item.update(status="pending" if material != "routine" else "rejected",
                        reason="awaiting_editorial_corroboration_and_rights_review" if material == "candidate" else item["classification"]["reason"])
        item["detail_verified"] = True
    except Exception as exc:
        item.update(status="pending", reason="detail_evidence_unavailable", detail_verified=False,
                    technical_error=type(exc).__name__ + ": " + str(exc)[:250])
    return item

def discover(config, client, as_of):
    routes, failures, indexed = [], [], {}
    for route in config["routes"]:
        try:
            result = collect_route(client, route, as_of, config["max_pages_per_route"])
            routes.append(result)
            failures.extend({"route":route,**failure} for failure in result.get("partition_technical_failures",[]))
            if result["stop_reason"].startswith(("page_fetch_failure", "page_parse_failure", "independent_native_control_mismatch")):
                failures.append({"route": route, "error": result["stop_reason"]})
            for row in result["items"]:
                if row["index_published_at"] is None or in_window(row["index_published_at"], as_of, 90):
                    if row["url"] not in indexed:
                        indexed[row["url"]] = dict(row, discovered_sections=[row["section"]])
                    else:
                        previous = indexed[row["url"]]
                        previous["discovered_sections"] = sorted(set(previous["discovered_sections"]+[row["section"]]))
                        previous["index_evidence"].extend(row["index_evidence"])
                        if previous["index_published_at"] != row["index_published_at"]:
                            previous.update(index_published_at=None, publication_date_error="conflicting_official_listing_dates")
        except Exception as exc:
            failures.append({"route": route, "error": type(exc).__name__ + ": " + str(exc)[:250]})
    with ThreadPoolExecutor(max_workers=3) as pool:
        verified = list(pool.map(lambda row: verify_item(client, row, as_of), indexed.values()))
    return routes, verified, failures

def translation_materiality(group):
    """Use verified official translations while retaining noise/date disagreements."""
    evidence=[{'url':m['url'],'title':m['title'],'section':m['section'],
               'classification':m['classification'],'detail_verified':m['detail_verified'],
               'published_at':m['published_at']} for m in group]
    eligible=[m for m in group if m['detail_verified'] and m['published_at']]
    hold={'materiality':'undetermined','priority':0,'category':'context'}
    if not eligible or len({m['published_at'] for m in group})!=1:
        return dict(hold,reason='translation_date_or_detail_hold'),evidence,[]
    kinds={m['classification']['materiality'] for m in eligible}
    if {'candidate','routine'}<=kinds:
        return dict(hold,reason='translation_materiality_conflict'),evidence,[]
    if 'candidate' in kinds:
        best=max(m['classification']['priority'] for m in eligible if m['classification']['materiality']=='candidate')
        chosen=[m for m in eligible if m['classification']['materiality']=='candidate' and m['classification']['priority']==best]
        return dict(chosen[0]['classification']),evidence,[m['url'] for m in chosen]
    if kinds=={'routine'}:return dict(eligible[0]['classification']),evidence,[m['url'] for m in eligible]
    return dict(hold,reason='metadata_insufficient_to_establish_business_materiality'),evidence,[]

def deduplicate_translations(items):
    """Merge only publisher-declared language aliases; retain conflicting dates."""
    urls={row["url"]:row for row in items};parents={url:url for url in urls}
    def root(url):
        while parents[url] != url: url=parents[url]
        return url
    for row in items:
        aliases=(row.get("detail_evidence") or {}).get("metadata",{}).get("alternate_language_urls",[])
        for alias in aliases:
            if alias in urls and urls[alias]["source"]==row["source"]:
                # Both pages must explicitly declare the relation, not fuzzy title matches.
                reciprocal=(urls[alias].get("detail_evidence") or {}).get("metadata",{}).get("alternate_language_urls",[])
                if row["url"] in reciprocal: parents[root(alias)]=root(row["url"])
    groups={}
    for row in items: groups.setdefault(root(row["url"]),[]).append(row)
    result=[]
    for group in groups.values():
        group.sort(key=lambda row:(not row["detail_verified"],"/en/" not in row["url"],row["url"]))
        row=dict(group[0]);row["source_aliases"]=sorted(member["url"] for member in group)
        row["sections"]=sorted({section for member in group for section in member["sections"]})
        row["entities"] = list({json.dumps(entity,sort_keys=True):entity for member in group for entity in member["entities"]}.values())
        if len(group)>1:
            row["translation_members"]=[{"url":member["url"],"title":member["title"],"section":member["section"],"classification":member["classification"],"published_at":member["published_at"],"index_published_at":member["index_published_at"],"index_evidence":member["index_evidence"],"detail_verified":member["detail_verified"],"technical_error":member.get("technical_error"),"detail_evidence":member.get("detail_evidence")} for member in group]
            classification,receipts,selected=translation_materiality(group)
            row['classification']=classification;row['classification_evidence']=receipts
            row['classification_basis']={'method':'verified_official_translation_metadata','selected_urls':selected,'editorial_score':False}
            if row['detail_verified'] and row['published_at'] and not row.get('technical_error'):
                material=classification['materiality']
                row.update(status='rejected' if material=='routine' else 'pending',reason='awaiting_editorial_corroboration_and_rights_review' if material=='candidate' else classification['reason'])
        if len({member["published_at"] for member in group})>1:
            row.update(published_at=None,status="pending",reason="translation_publication_date_conflict")
        result.append(row)
    return result
