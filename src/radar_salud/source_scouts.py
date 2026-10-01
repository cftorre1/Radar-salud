from __future__ import annotations
import re
from html.parser import HTMLParser
from urllib.parse import urljoin,urlparse
from datetime import date
from .models import RawItem
from .scouts import fetch_html

class _A(HTMLParser):
    def __init__(self):super().__init__();self.links=[];self._href=None;self._text=[]
    def handle_starttag(self,tag,attrs):
        if tag.lower()=="a":self._href=dict(attrs).get("href");self._text=[]
    def handle_data(self,data):
        if self._href is not None:self._text.append(data)
    def handle_endtag(self,tag):
        if tag.lower()=="a" and self._href is not None:
            self.links.append((self._href," ".join("".join(self._text).split())));self._href=None;self._text=[]

class SusesoNormativeScout:
    SOURCE_SLUG="suseso";SOURCE_NAME="Superintendencia de Seguridad Social (SUSESO)";SOURCE_TYPE="official"
    LATEST_NORMATIVE="https://www.suseso.gob.cl/612/w3-article-790656.html"
    PAGES=[
        "https://www.suseso.gob.cl/601/w3-channel.html",
        "https://www.suseso.gob.cl/612/w3-propertyvalue-10371.html",
        "https://www.suseso.gob.cl/612/w3-propertyvalue-63007.html",
        "https://www.suseso.gob.cl/612/w3-propertyvalue-10335.html",
        "https://www.suseso.gob.cl/612/w3-propertyvalue-31037.html"
    ]
    def discover(self):
        out=[];seen=set()
        for page in self.PAGES:
            try:html=fetch_html(page)
            except Exception as e:print("SUSESO fetch:",e);continue
            p=_A();p.feed(html)
            for href,text in p.links:
                if not href or not text:continue
                url=urljoin(page,href)
                if not re.search(r"/612/w3-article-\d+\.html",url,re.I) or url in seen or not re.search(r"(circular|dictamen)",text,re.I):continue
                seen.add(url);out.append(RawItem(self.SOURCE_SLUG,text,url,self.SOURCE_NAME,self.SOURCE_TYPE,raw_text="",metadata={"discovered_from":page}))
        # The site also exposes a direct "última normativa" detail URL. Seed it
        # explicitly so a redesign of listing pages cannot hide the newest act.
        try:
            from .public_source_pipeline import _Meta, _date
            meta=_Meta();meta.feed(fetch_html(self.LATEST_NORMATIVE))
            body=" ".join(meta.text)
            m=re.search(r"\b(Circular|Dictamen)\s+(?:N?[°º]?\s*)?(\d{3,6})\b",body,re.I)
            title=(f"{m.group(1).title()} {m.group(2)}" if m else (meta.ogtitle or "Última normativa SUSESO"))
            event_date=_date(meta.published) or _date(body[:5000])
            if self.LATEST_NORMATIVE not in seen:
                out.append(RawItem(self.SOURCE_SLUG,title,self.LATEST_NORMATIVE,self.SOURCE_NAME,self.SOURCE_TYPE,
                                   event_date=event_date,raw_text=(meta.description or body[:1800]),
                                   metadata={"discovered_from":"latest_normative","page_text":body[:18000]}))
        except Exception as e:
            print("SUSESO latest normative:",e)
        print(f"SUSESO discovered={len(out)}");return out


class SusesoNewsScout:
    """Official SUSESO newsroom. Detail pages provide the authoritative date."""
    SOURCE_SLUG="suseso_news";SOURCE_NAME="Superintendencia de Seguridad Social (SUSESO)";SOURCE_TYPE="official"
    PAGE="https://www.suseso.gob.cl/601/w3-channel.html"
    def discover(self):
        from .public_source_pipeline import _Meta, _date
        html=fetch_html(self.PAGE);p=_A();p.feed(html);out=[];seen=set()
        for href,title in p.links:
            if not href or len(title)<18:continue
            url=urljoin(self.PAGE,href);parsed=urlparse(url)
            if parsed.netloc not in ("www.suseso.gob.cl","suseso.gob.cl"):continue
            if not re.fullmatch(r"/605/w3-article-\d+\.html",parsed.path) or url in seen:continue
            seen.add(url)
            try:
                meta=_Meta();meta.feed(fetch_html(url))
                event_date=_date(meta.published) or _date(" ".join(meta.text)[:5000])
                body=" ".join(meta.text)
            except Exception:
                continue
            if not event_date:continue
            out.append(RawItem(self.SOURCE_SLUG,title,url,self.SOURCE_NAME,self.SOURCE_TYPE,
                               event_date=event_date,raw_text=(meta.description or body[:1800]),
                               metadata={"discovered_from":self.PAGE,"page_text":body[:18000]}))
        if not out:raise RuntimeError("SUSESO newsroom has no dated article rows")
        out.sort(key=lambda x:x.event_date or "",reverse=True)
        return out[:30]


class SusesoFiscalizacionScout:
    """Official SUSESO fiscalized-actor surfaces, separated from normative acts."""
    SOURCE_SLUG="suseso_fiscalizacion";SOURCE_NAME="Superintendencia de Seguridad Social (SUSESO)";SOURCE_TYPE="official"
    PAGES=[
        ("Isapres","https://www.suseso.gob.cl/612/w3-propertyvalue-30981.html"),
        ("COMPIN","https://www.suseso.gob.cl/612/w3-propertyvalue-30982.html"),
    ]
    def discover(self):
        from .public_source_pipeline import _Meta, _date
        out=[];seen=set()
        for actor,page in self.PAGES:
            html=fetch_html(page);p=_A();p.feed(html)
            for href,title in p.links:
                if not href or len(title)<12:continue
                url=urljoin(page,href);parsed=urlparse(url)
                if parsed.netloc not in ("www.suseso.gob.cl","suseso.gob.cl"):continue
                if not re.fullmatch(r"/612/w3-article-\d+\.html",parsed.path) or url in seen:continue
                seen.add(url)
                try:
                    meta=_Meta();meta.feed(fetch_html(url))
                    body=" ".join(meta.text)
                    event_date=_date(meta.published) or _date(body[:5000])
                except Exception:
                    continue
                if not event_date:continue
                out.append(RawItem(self.SOURCE_SLUG,title,url,self.SOURCE_NAME,self.SOURCE_TYPE,
                                   event_date=event_date,raw_text=(meta.description or body[:1800]),
                                   metadata={"discovered_from":page,"fiscalized_actor":actor,"page_text":body[:18000]}))
        if not out:raise RuntimeError("SUSESO fiscalizacion surfaces have no dated detail items")
        out.sort(key=lambda x:x.event_date or "",reverse=True)
        return out[:40]


class DfHealthScout:
    SOURCE_SLUG="diario_financiero";SOURCE_NAME="Diario Financiero";SOURCE_TYPE="press_high_trust"
    PAGES=["https://www.df.cl/empresas/dfsalud","https://www.df.cl/noticias/site/tag/port/all/tagport_161_1.html"]
    def discover(self):
        out=[];seen=set()
        for page in self.PAGES:
            try:html=fetch_html(page)
            except Exception as e:print("DF fetch:",e);continue
            p=_A();p.feed(html)
            for href,text in p.links:
                if not href or len(text)<18:continue
                url=urljoin(page,href);u=urlparse(url);path=u.path.rstrip("/")
                if u.netloc not in ("www.df.cl","df.cl"):continue
                if any(x in path for x in ("/autor/","/suscripcion","/login","/tag/","/tax/")):continue
                if path in ("/empresas/dfsalud","/empresas/salud","/noticias/site/tag/port/all/tagport_161_1.html") or path.count("/")<3 or url in seen:continue
                seen.add(url);out.append(RawItem(self.SOURCE_SLUG,text,url,self.SOURCE_NAME,self.SOURCE_TYPE,raw_text="",metadata={"discovered_from":page}))
        print(f"DF discovered={len(out)}");return out


class FonasaDataHubScout:
    """Official FONASA Datos Abiertos hubs. Discovery is broad; publication remains fail-closed."""
    SOURCE_SLUG="fonasa_datos_abiertos";SOURCE_NAME="Fondo Nacional de Salud (FONASA)";SOURCE_TYPE="official"
    PAGES=[
        ("Noticias","https://datosabiertos.fonasa.cl/noticias/"),
        ("Biblioteca / Cuenta Pública","https://datosabiertos.fonasa.cl/biblioteca-cuenta-publica/"),
        ("Boletines estadísticos","https://datosabiertos.fonasa.cl/boletines-estadisticos/"),
        ("Análisis","https://datosabiertos.fonasa.cl/analysis/"),
    ]
    HOSTS=("datosabiertos.fonasa.cl","www.datosabiertos.fonasa.cl")
    def discover(self):
        from .public_source_pipeline import _Meta, _date
        out=[];seen=set()
        for channel,page in self.PAGES:
            html=fetch_html(page);p=_A();p.feed(html)
            for href,title in p.links:
                if not href or len(title)<12:continue
                url=urljoin(page,href);parsed=urlparse(url)
                if parsed.netloc not in self.HOSTS or url in seen:continue
                if parsed.path.rstrip("/") in ("","/noticias","/biblioteca-cuenta-publica","/boletines-estadisticos","/analysis"):continue
                if any(x in parsed.path.lower() for x in ("/wp-admin","/wp-login","/author/","/tag/","/category/")):continue
                seen.add(url);event_date=None;body=""
                if parsed.path.lower().endswith((".pdf",".xlsx",".xls",".csv")):
                    event_date=_date(title)
                else:
                    try:
                        meta=_Meta();meta.feed(fetch_html(url));body=" ".join(meta.text)
                        event_date=_date(meta.published) or _date(body[:5000]) or _date(title)
                    except Exception:
                        pass
                out.append(RawItem(self.SOURCE_SLUG,title,url,self.SOURCE_NAME,self.SOURCE_TYPE,
                                   event_date=event_date,raw_text=body[:1800],
                                   metadata={"discovered_from":page,"fonasa_channel":channel,"page_text":body[:18000]}))
        if not out:raise RuntimeError("FONASA Datos Abiertos unavailable or no discoverable items")
        return out[:80]


class FonasaNewsScout:
    """Direct official newsroom; discovery never fabricates publication dates."""
    SOURCE_SLUG="fonasa";SOURCE_NAME="FONASA";SOURCE_TYPE="official"
    PAGE="https://www.fonasa.gob.cl/noticias/"
    def discover_from_html(self,html):
        parser=_A();parser.feed(html)
        out=[];seen=set()
        for href,title in parser.links:
            if not href or len(title)<18:continue
            url=urljoin(self.PAGE,href);parsed=urlparse(url)
            if parsed.netloc not in ("www.fonasa.gob.cl","fonasa.gob.cl") or not re.fullmatch(r"/noticias/[^/]+/?",parsed.path):continue
            if parsed.path.rstrip("/")=="/noticias" or url in seen:continue
            seen.add(url)
            out.append(RawItem(self.SOURCE_SLUG,title,url,self.SOURCE_NAME,self.SOURCE_TYPE,
                               metadata={"discovered_from":self.PAGE}))
        return out
    def discover(self):
        from .public_source_pipeline import _Meta, _date
        items=self.discover_from_html(fetch_html(self.PAGE))
        # A date on the detail page is required to distinguish LIVE from BACKFILL.
        for item in items[:15]:
            try:
                meta=_Meta();meta.feed(fetch_html(item.url))
                item.event_date=_date(meta.published)
            except Exception as exc:
                # A failed detail request is technical failure, not an undated publication.
                raise RuntimeError(f"FONASA detail unavailable: {type(exc).__name__}") from exc
        return items[:15]


class _TableRows(HTMLParser):
    def __init__(self):
        super().__init__(); self.rows=[]; self.row=None; self.cell=None; self.anchor=None
    def handle_starttag(self,tag,attrs):
        if tag.lower()=="tr":self.row={"text":[],"links":[],"cells":[]}
        if self.row is not None and tag.lower() in ("td","th"):self.cell=[]
        if self.row is not None and tag.lower()=="a":self.anchor=[dict(attrs).get("href"),[]]
    def handle_data(self,data):
        if self.row is not None:
            self.row["text"].append(data)
            if self.cell is not None:self.cell.append(data)
            if self.anchor is not None:self.anchor[1].append(data)
    def handle_endtag(self,tag):
        if tag.lower()=="a" and self.anchor is not None:
            self.row["links"].append((self.anchor[0]," ".join(" ".join(self.anchor[1]).split())))
            self.anchor=None
        if tag.lower() in ("td","th") and self.cell is not None:
            self.row["cells"].append(" ".join(" ".join(self.cell).split()));self.cell=None
        if tag.lower()=="tr" and self.row is not None:
            self.rows.append(self.row);self.row=None



class IspSurveillanceScout:
    """Official ISP laboratory surveillance and respiratory-virus publications."""
    SOURCE_SLUG="isp_surveillance";SOURCE_NAME="Instituto de Salud Pública de Chile (ISP)";SOURCE_TYPE="official"
    PAGES=[
        ("Boletines de vigilancia de laboratorios","https://www.ispch.gob.cl/boletin/"),
        ("Vigilancia de virus respiratorios","https://www.ispch.gob.cl/virusrespiratorios/"),
    ]
    HOSTS=("www.ispch.gob.cl","ispch.gob.cl")
    def discover(self):
        from .public_source_pipeline import _Meta, _date
        out=[];seen=set()
        for channel,page in self.PAGES:
            html=fetch_html(page);p=_A();p.feed(html)
            for href,title in p.links:
                if not href or len(title)<8:continue
                url=urljoin(page,href);parsed=urlparse(url)
                if parsed.netloc not in self.HOSTS or url in seen:continue
                low=f"{title} {parsed.path}".lower()
                if not any(k in low for k in ("bolet","vigil","virus","respir","influenza","laboratorio","informe","reporte",".pdf")):continue
                seen.add(url);event_date=_date(title);body=""
                if not parsed.path.lower().endswith(".pdf"):
                    try:
                        meta=_Meta();meta.feed(fetch_html(url));body=" ".join(meta.text)
                        event_date=event_date or _date(meta.published) or _date(body[:5000])
                    except Exception:
                        pass
                out.append(RawItem(self.SOURCE_SLUG,title,url,self.SOURCE_NAME,self.SOURCE_TYPE,
                                   event_date=event_date,raw_text=body[:1800],
                                   metadata={"discovered_from":page,"isp_channel":channel,"page_text":body[:18000]}))
        if not out:raise RuntimeError("ISP surveillance hubs unavailable or empty")
        return out[:80]


class IspAnamedAlertScout:
    """Official ANAMED alerts with a verified date in the listing row."""
    SOURCE_SLUG="isp_anamed";SOURCE_NAME="ISP / ANAMED";SOURCE_TYPE="official"
    PAGE="https://www.ispch.gob.cl/categorias-alertas/anamed/"
    def discover_from_html(self,html):
        # Capture hrefs only within rows; a date on an unrelated page element
        # must never be attributed to an alert.
        from .public_source_pipeline import _date
        parser=_TableRows();parser.feed(html);items=[];seen=set()
        for row in parser.rows:
            body=" ".join(" ".join(row["text"]).split())
            # Only a standalone date cell is a publication date. A date in the
            # alert description or another document is never a publication date.
            dates=[c for c in row["cells"] if re.fullmatch(r"\d{1,2}[/-]\d{1,2}[/-]20\d{2}",c)]
            day=_date(dates[0]) if len(dates)==1 else None
            try:
                if day:day=date.fromisoformat(day).isoformat()
                if day and day>date.today().isoformat():day=None
            except ValueError:day=None
            if not day or not re.search(r"retiro del mercado|nota informativa|falsificad|seguridad",body,re.I):continue
            titles=[cell for cell in row["cells"] if len(cell)>25 and not cell.lower().startswith("publicación isp")]
            if not titles:continue
            title=max(titles,key=len)
            for href,label in row["links"]:
                if not href or label.lower()!="publicación isp":continue
                url=urljoin(self.PAGE,href);parsed=urlparse(url)
                if parsed.netloc not in ("www.ispch.gob.cl","ispch.gob.cl") or not parsed.path.lower().endswith(".pdf") or url in seen:continue
                seen.add(url)
                items.append(RawItem(self.SOURCE_SLUG,title[:300],url,self.SOURCE_NAME,self.SOURCE_TYPE,
                                     event_date=day,metadata={"discovered_from":self.PAGE,"listing_text":body}))
                break
        if not items:raise RuntimeError("ANAMED alert listing has no verified publication rows")
        return items[:20]
    def discover(self):return self.discover_from_html(fetch_html(self.PAGE))



class ClinicasChileScout:
    """Sector-association coverage across news, reports, studies and documents."""
    SOURCE_SLUG="clinicas_chile";SOURCE_NAME="Clínicas de Chile A.G.";SOURCE_TYPE="sector_association"
    PAGES=[
        ("Noticias","https://www.clinicasdechile.cl/noticias/"),
        ("Memorias","https://www.clinicasdechile.cl/knowledgebase_category/memorias/"),
        ("Estudios y análisis","https://www.clinicasdechile.cl/knowledgebase_category/estudios-y-analisis/page/3/?mostrar=6"),
        ("Documentos","https://www.clinicasdechile.cl/knowledgebase_category/documentos/"),
    ]
    HOSTS=("www.clinicasdechile.cl","clinicasdechile.cl")
    def discover(self):
        from .public_source_pipeline import _Meta, _date
        out=[];seen=set()
        for channel,page in self.PAGES:
            html=fetch_html(page);p=_A();p.feed(html)
            for href,title in p.links:
                if not href or len(title)<12:continue
                url=urljoin(page,href);parsed=urlparse(url)
                if parsed.netloc not in self.HOSTS or url in seen:continue
                rootpaths=("/noticias","/knowledgebase_category/memorias","/knowledgebase_category/estudios-y-analisis","/knowledgebase_category/documentos")
                if parsed.path.rstrip("/") in rootpaths:continue
                if any(x in parsed.path.lower() for x in ("/author/","/tag/","/category/","/wp-admin","/page/")) and "knowledgebase" not in parsed.path.lower():continue
                seen.add(url);event_date=_date(title);body=""
                if not parsed.path.lower().endswith((".pdf",".xlsx",".xls",".csv")):
                    try:
                        meta=_Meta();meta.feed(fetch_html(url));body=" ".join(meta.text)
                        event_date=event_date or _date(meta.published) or _date(body[:5000])
                    except Exception:
                        pass
                out.append(RawItem(self.SOURCE_SLUG,title,url,self.SOURCE_NAME,self.SOURCE_TYPE,
                                   event_date=event_date,raw_text=body[:1800],
                                   metadata={"discovered_from":page,"clinicas_channel":channel,"page_text":body[:18000]}))
        if not out:raise RuntimeError("Clínicas de Chile hubs unavailable or empty")
        return out[:100]


class CorporateNewsroomScout:
    """Monitor verified corporate newsrooms; details require editorial review."""
    SOURCES={
        "redsalud":("RedSalud","https://www.redsalud.cl/noticias",("www.redsalud.cl","redsalud.cl"),r"/noticias/[^/]+/?"),
        "bupa_chile":("Bupa Chile","https://www.bupa.cl/somos-bupa/sala-de-prensa",("www.bupa.cl","bupa.cl"),
                      r"/(?:somos-bupa/)?sala-de-prensa/[^/]+/?"),
        "pfizer_chile":("Pfizer Chile","https://www.pfizer.cl/news",("www.pfizer.cl","pfizer.cl"),r"/news/[^/]+/?"),
        "indisa":("Clínica INDISA","https://www.indisa.cl/categoria-blog/novedades-indisa",("www.indisa.cl","indisa.cl"),r"/blog/[^/]+/?"),
    }
    SOURCE_TYPE="corporate"
    def __init__(self,slug):
        if slug not in self.SOURCES:raise ValueError("Unreviewed newsroom")
        self.SOURCE_SLUG=slug
        self.SOURCE_NAME,self.PAGE,self.hosts,self.pattern=self.SOURCES[slug]
    def discover_from_html(self,html):
        parser=(_IndisaCards() if self.SOURCE_SLUG=="indisa" else
                _BupaCards() if self.SOURCE_SLUG=="bupa_chile" else
                _PfizerCards() if self.SOURCE_SLUG=="pfizer_chile" else _RedSaludCards())
        parser.feed(html);out=[];seen=set()
        for href,title in parser.links:
            if not href or len(title)<28:continue
            url=urljoin(self.PAGE,href);parsed=urlparse(url)
            if parsed.scheme!="https" or parsed.netloc not in self.hosts or not re.fullmatch(self.pattern,parsed.path):continue
            if url in seen:continue
            published=None
            if self.SOURCE_SLUG in ("redsalud","pfizer_chile"):
                from .public_source_pipeline import _date
                published=_date(parser.dates.get((href,title)) or parser.dates.get(href))
                if not published:continue
            seen.add(url)
            out.append(RawItem(self.SOURCE_SLUG,title,url,self.SOURCE_NAME,self.SOURCE_TYPE,
                               event_date=published,metadata={"discovered_from":self.PAGE,"listing_date":published,
                                   **({"source_quality_gate":"pending_90_day_audit"} if self.SOURCE_SLUG=="indisa" else {})}))
        if not out:raise RuntimeError(f"{self.SOURCE_NAME} newsroom structure unrecognized")
        return out[:15]
    def discover(self):
        items=self.discover_from_html(fetch_html(self.PAGE))
        if self.SOURCE_SLUG=="indisa":
            from .public_source_pipeline import _IndisaArticle
            verified=[]
            for item in items:
                try:
                    parser=_IndisaArticle();parser.feed(fetch_html(item.url));parser.finish()
                except Exception:
                    continue
                if not parser.title or (item.title.casefold() not in parser.title.casefold()
                                        and parser.title.casefold() not in item.title.casefold()):
                    continue
                item.event_date=parser.event_date()
                if not item.event_date:
                    continue
                item.metadata.update(listing_date=item.event_date)
                verified.append(item)
            if not verified:
                raise RuntimeError("INDISA has no dated listing/detail pairs")
            items=verified
        return items


class _IndisaCards(HTMLParser):
    """Bind INDISA official blog links to their own headline, excluding menus."""
    def __init__(self):
        super().__init__();self.links=[];self.href=None;self.anchor_depth=0;self.heading_depth=0;self.parts=[];self.heading=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs);lower=tag.lower()
        if lower=="a" and not self.href:
            href=attrs.get("href") or ""
            if re.fullmatch(r"/blog/[^/]+/?",urlparse(href).path):
                self.href=href;self.anchor_depth=1;self.parts=[];self.heading=[]
        elif self.href:
            if lower=="a":self.anchor_depth+=1
            if lower in ("h2","h3","h4"):self.heading_depth+=1
    def handle_data(self,data):
        if self.href:
            value=" ".join(data.split())
            if value:self.parts.append(value)
            if self.heading_depth and value:self.heading.append(value)
    def handle_endtag(self,tag):
        lower=tag.lower()
        if self.href and lower in ("h2","h3","h4") and self.heading_depth:self.heading_depth-=1
        elif self.href and lower=="a":
            self.anchor_depth-=1
            if self.anchor_depth<=0:
                title=" ".join(self.heading).strip() or " ".join(self.parts).strip()
                if title and self.href not in {x[0] for x in self.links}:self.links.append((self.href,title))
                self.href=None;self.parts=[];self.heading=[];self.heading_depth=0


class _BupaCards(HTMLParser):
    """Bind a card title to its own URL; anchors themselves say 'Ver más'."""
    def __init__(self):
        super().__init__();self.links=[];self.card=None;self.title_parts=None
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs);classes=(attrs.get("class") or "").split()
        if tag.lower()=="article" and "card" in classes:
            self.card={"href":None,"title":None}
        elif self.card is not None and tag.lower()=="h3" and "card__title" in classes:
            self.title_parts=[]
        elif self.card is not None and tag.lower()=="a" and not self.card["href"]:
            self.card["href"]=attrs.get("href")
    def handle_data(self,data):
        if self.title_parts is not None:self.title_parts.append(data)
    def handle_endtag(self,tag):
        if tag.lower()=="h3" and self.title_parts is not None:
            if self.card is not None:self.card["title"]=" ".join(" ".join(self.title_parts).split())
            self.title_parts=None
        elif tag.lower()=="article" and self.card is not None:
            if self.card["href"] and self.card["title"]:
                self.links.append((self.card["href"],self.card["title"]))
            self.card=None


class _RedSaludCards(HTMLParser):
    """Bind the empty story anchor to sibling headline and date in one card."""
    def __init__(self):
        super().__init__();self.links=[];self.dates={};self.card=None;self._field=None;self._parts=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag.lower()=="article":self.card={"href":None,"title":None,"date":None}
        elif self.card is not None and tag.lower()=="a" and not self.card["href"]:
            self.card["href"]=attrs.get("href")
        elif self.card is not None and tag.lower() in ("h3","p"):
            self._field="title" if tag.lower()=="h3" else "date";self._parts=[]
    def handle_data(self,data):
        if self._field:self._parts.append(data)
    def handle_endtag(self,tag):
        if self.card is not None and ((tag.lower()=="h3" and self._field=="title") or (tag.lower()=="p" and self._field=="date")):
            self.card[self._field]=" ".join(" ".join(self._parts).split());self._field=None
        elif tag.lower()=="article" and self.card is not None:
            if self.card["href"] and self.card["title"] and self.card["date"]:
                self.links.append((self.card["href"],self.card["title"]));self.dates[(self.card["href"],self.card["title"])]=self.card["date"]
            self.card=None;self._field=None


class _PfizerCards(HTMLParser):
    """Bind each Pfizer web-component card's date, headline and detail URL."""
    def __init__(self):
        super().__init__();self.links=[];self.dates={};self.card=None;self._field=None;self._parts=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs);lower=tag.lower()
        if lower=="corporate-article-listing":self.card={"href":None,"title":None,"date":None}
        elif self.card is not None and lower=="helix-core-content" and attrs.get("slot")=="header":
            self._field="date";self._parts=[]
        elif self.card is not None and lower=="helix-core-heading" and attrs.get("variant")=="h4":
            self._field="title";self._parts=[]
        elif self.card is not None and self._field=="title" and lower=="a" and not self.card["href"]:
            self.card["href"]=attrs.get("href")
    def handle_data(self,data):
        if self._field:self._parts.append(data)
    def handle_endtag(self,tag):
        lower=tag.lower()
        if lower=="helix-core-content" and self._field=="date":
            self.card["date"]=" ".join(" ".join(self._parts).split());self._field=None
        elif lower=="helix-core-heading" and self._field=="title":
            self.card["title"]=" ".join(" ".join(self._parts).split());self._field=None
        elif lower=="corporate-article-listing" and self.card is not None:
            if all(self.card.values()):
                self.links.append((self.card["href"],self.card["title"]));self.dates[(self.card["href"],self.card["title"])]=self.card["date"]
            self.card=None;self._field=None


class DeisResourceScout:
    """Official DEIS data releases; a healthy hub may legitimately yield no signal."""
    SOURCE_SLUG="deis";SOURCE_NAME="DEIS";SOURCE_TYPE="official"
    PAGE="https://deis.minsal.cl/"
    _MATERIAL=re.compile(
        r"estad[ií]stic|datos abiertos|publicaci[oó]n|infograf[ií]a|tablero|mortalidad|"
        r"natalidad|egresos hospitalarios|inmunizaci[oó]n|vacunaci[oó]n",re.I)
    _RELEASE=re.compile(r"publicaci[oó]n|publicad[oa]|actualizaci[oó]n|actualizad[oa]|lanzamiento|nuevo conjunto",re.I)
    _HUBS={"/estadisticas","/datos-abiertos","/publicaciones-e-infografias","/tableros-deis"}
    def discover_from_html(self,html):
        plain=" ".join(re.sub(r"<[^>]+>"," ",html).split())
        if (not re.search(r"Departamento de Estad[ií]sticas",plain,re.I)
                or not any(marker in plain for marker in ("Datos Abiertos","Tableros DEIS","Indicadores Sanitarios"))):
            raise RuntimeError("DEIS official hub structure unrecognized")
        parser=_A();parser.feed(html);out=[];seen=set()
        for href,title in parser.links:
            if (not href or len(title)<18 or not self._MATERIAL.search(title)
                    or not self._RELEASE.search(title)):continue
            url=urljoin(self.PAGE,href);parsed=urlparse(url);path=parsed.path.rstrip("/")
            if parsed.scheme!="https" or parsed.netloc!="deis.minsal.cl" or path in self._HUBS or not path:continue
            if url in seen:continue
            seen.add(url);out.append(RawItem(self.SOURCE_SLUG,title[:300],url,self.SOURCE_NAME,self.SOURCE_TYPE,
                metadata={"discovered_from":self.PAGE,"resource_kind":"candidate_data_release"}))
        return out[:20]
    def discover(self):
        from .public_source_pipeline import _date
        candidates=self.discover_from_html(fetch_html(self.PAGE));out=[]
        for raw in candidates[:10]:
            detail=_PublishedMeta();detail.feed(fetch_html(raw.url))
            published=_date(detail.published)
            try:
                if not published or date.fromisoformat(published)>date.today():continue
            except ValueError:continue
            raw.event_date=published
            raw.metadata.update(resource_kind="dated_data_release",publication_date_source="article:published_time")
            out.append(raw)
        return out


class _PublishedMeta(HTMLParser):
    """Only the article publication property, never a dataset coverage date."""
    def __init__(self):super().__init__();self.published=""
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag.lower()=="meta" and attrs.get("property","").lower()=="article:published_time":
            self.published=attrs.get("content","")
