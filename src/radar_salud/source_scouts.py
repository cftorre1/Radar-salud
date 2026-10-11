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


from .suseso_fiscalizacion import SusesoFiscalizacionScout


class DfHealthScout:
    SOURCE_SLUG="diario_financiero";SOURCE_NAME="Diario Financiero";SOURCE_TYPE="press_high_trust"
    PAGES=["https://www.df.cl/empresas/dfsalud","https://www.df.cl/noticias/site/tag/port/all/tagport_161_1.html",
           "https://www.df.cl/noticias/site/tag/port/all/tagport_2916_1.html"]
    def discover(self):
        from .df_article import bind_df_article
        from .df_inventory import DfListing
        out=[];seen=set()
        for page in self.PAGES:
            try:html=fetch_html(page)
            except Exception as e:print("DF fetch:",e);continue
            p=_A();p.feed(html)
            listing=DfListing();listing.feed(html)
            links=listing.primary_links if listing.has_primary_layout else p.links
            for href,text in links:
                if not href or len(text)<18:continue
                url=urljoin(page,href);u=urlparse(url);path=u.path.rstrip("/")
                if u.netloc not in ("www.df.cl","df.cl"):continue
                if any(x in path for x in ("/autor/","/suscripcion","/login","/tag/","/tax/")):continue
                if path.endswith(".pdf") or re.search(r"/p/\d+/?$",path):continue
                if path in ("/empresas/dfsalud","/empresas/salud","/noticias/site/tag/port/all/tagport_161_1.html") or path.count("/")<3 or url in seen:continue
                seen.add(url)
                raw=RawItem(self.SOURCE_SLUG,text,url,self.SOURCE_NAME,self.SOURCE_TYPE,
                            metadata={"discovered_from":page,"listing_extraction":"primary_cards" if listing.has_primary_layout else "unstructured_links"})
                try:
                    bind_df_article(raw,fetch_html(url))
                except Exception as exc:
                    raw.metadata["fetch_error"]=type(exc).__name__
                out.append(raw)
        if not out:raise RuntimeError("DF listing unavailable or no article candidates")
        print(f"DF discovered={len(out)}");return out


# Public data source exports use the same strict scouts as the daily runtime.
from .fonasa_sources import FonasaDataHubScout, FonasaNewsScout
from .isp_sources import IspSurveillanceScout, IspAnamedAlertScout


class ClinicasChileScout:
    """Sector-association coverage across news, reports, studies and documents."""
    SOURCE_SLUG="clinicas_chile";SOURCE_NAME="Clínicas de Chile A.G.";SOURCE_TYPE="sector_association"
    PAGES=[
        ("Noticias","https://www.clinicasdechile.cl/noticias/"),
        ("Memorias","https://www.clinicasdechile.cl/knowledgebase_category/memorias/"),
        ("Estudios y análisis","https://www.clinicasdechile.cl/knowledgebase_category/estudios-y-analisis/"),
        ("Documentos","https://www.clinicasdechile.cl/knowledgebase_category/documentos/"),
    ]
    HOSTS=("www.clinicasdechile.cl","clinicasdechile.cl")
    def discover_from_html(self,html,channel,page):
        parser=_ClinicasLinks();parser.feed(html);out=[];seen=set()
        for href,title in parser.links:
            if not href or len(title)<12:continue
            url=urljoin(page,href);parsed=urlparse(url)
            if parsed.scheme!="https" or parsed.netloc not in self.HOSTS or url in seen:continue
            document=bool(re.fullmatch(r"/wp-content/uploads/.+\.(?:pdf|xlsx?|csv)",parsed.path,re.I))
            if channel=="Noticias":
                if (len(title)<25 or document or not re.fullmatch(r"/(?:noticias/)?[^/]+/?",parsed.path)
                        or parsed.path.rstrip("/") in ("/noticias","/quienes-somos","/asociados","/seminarios","/biblioteca","/contacto","/equipo-de-trabajo","/consejo-medico","/temas-de-coyuntura")):
                    continue
            elif not (document and title.casefold().startswith("descargar")):
                continue
            seen.add(url)
            event_date=parser.dates.get(href) if channel=="Noticias" else None
            out.append(RawItem(self.SOURCE_SLUG,title,url,self.SOURCE_NAME,self.SOURCE_TYPE,
                event_date=event_date,metadata={"discovered_from":page,"clinicas_channel":channel,
                "publication_date_source":"dated_news_listing" if event_date else "unverified"}))
        return out
    def discover(self):
        from .public_source_pipeline import _VisibleArticle, _date
        out=[];seen=set();self.discovery_errors=[]
        for channel,page in self.PAGES:
            # The library lists 3/3/4 pages. Scan each channel from page 1;
            # library order is not a verified chronology.
            count={"Memorias":3,"Estudios y análisis":3,"Documentos":4}.get(channel,1)
            pages=[page]+[f"{page}page/{n}/?mostrar=6" for n in range(2,count+1)]
            candidates=[]
            for listing in pages:
                try:candidates.extend(self.discover_from_html(fetch_html(listing),channel,listing))
                except Exception as exc:self.discovery_errors.append(f"{channel}: {listing}: {type(exc).__name__}")
            for raw in candidates:
                if raw.url in seen:continue
                seen.add(raw.url)
                if channel=="Noticias":
                    # A detail fetch failure remains retryable, never a date
                    # borrowed from navigation, legal citations or PDF body text.
                    try:detail=fetch_html(raw.url)
                    except Exception as exc:
                        self.discovery_errors.append(f"{channel}: {raw.url}: {type(exc).__name__}")
                        out.append(raw);continue
                    article=_VisibleArticle();article.feed(detail)
                    stamp=_PublishedMeta();stamp.feed(detail)
                    # _Meta includes several historical date names; only the
                    # explicit article property can replace the listing stamp.
                    verified=_date(stamp.published)
                    if verified and raw.event_date and verified != raw.event_date:
                        self.discovery_errors.append(f"{channel}: {raw.url}: publication_date_mismatch")
                        raw.event_date=None;raw.metadata["publication_date_source"]="conflicting_stamps"
                    elif verified:
                        raw.event_date=verified;raw.metadata["publication_date_source"]="article:published_time"
                    raw.metadata["page_text"]=" ".join(article.text)[:18000]
                    raw.raw_text=raw.metadata["page_text"][:1800]
                out.append(raw)
        if not out:raise RuntimeError("Clínicas de Chile hubs unavailable or empty: "+"; ".join(self.discovery_errors))
        return out[:100]


class _ClinicasLinks(_A):
    """Associate the site's publication stamp with the following news headline."""
    def __init__(self):super().__init__();self.dates={};self._stamp=None;self._heading=False
    def handle_starttag(self,tag,attrs):
        lower=tag.lower()
        if lower in ("article","nav","footer"):self._stamp=None
        if lower in ("h2","h3"):self._heading=True
        super().handle_starttag(tag,attrs)
    def handle_data(self,data):
        from .public_source_pipeline import _date
        if re.fullmatch(r"\s*\d{1,2}:\d{2}\s*[ap]m\s+el\s+\d{1,2}\s+de\s+\w+\s+del\s+20\d{2}\s*",data,re.I):
            self._stamp=_date(data)
        super().handle_data(data)
    def handle_endtag(self,tag):
        href=self._href
        super().handle_endtag(tag)
        if tag.lower()=="a" and href and self._heading and self._stamp:
            self.dates[href]=self._stamp;self._stamp=None
        if tag.lower() in ("h2","h3","article"):
            self._stamp=None;self._heading=False


class CorporateNewsroomScout:
    """Monitor verified corporate newsrooms; details require editorial review."""
    SOURCES={
        "redsalud":("RedSalud","https://www.redsalud.cl/noticias",("www.redsalud.cl","redsalud.cl"),r"/noticias/[^/]+/?"),
        "bupa_chile":("Bupa Chile","https://www.bupa.cl/somos-bupa/sala-de-prensa",("www.bupa.cl","bupa.cl"),
                      r"/(?:(?:somos-bupa/)?sala-de-prensa/)?[a-z0-9][a-z0-9-]+/?"),
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
        return out[:100]
    def discover(self):
        self.discovery_errors=[]
        items=self.discover_from_html(fetch_html(self.PAGE))
        if self.SOURCE_SLUG=="redsalud":
            # First-page-only polling hides capacity/convenio articles in the
            # rolling backfill window. Follow same-newsroom pagination, bounded.
            seen={item.url for item in items}
            for number in range(1,5):
                page=f"{self.PAGE}?page={number}"
                try:page_items=self.discover_from_html(fetch_html(page))
                except Exception as exc:
                    self.discovery_errors.append(f"{page}: {type(exc).__name__}");continue
                for item in page_items:
                    if item.url not in seen:
                        seen.add(item.url);item.metadata["discovered_from"]=page;items.append(item)
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
        return items[:100]


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
