"""Probe of the SIS normative inventory (Dirección 9-nov-2026, point B).

Finds the authoritative listing of every normative document type the Superintendencia de Salud
publishes under /normativa/ (circulares, oficios, oficios circulares, resoluciones exentas,
dictámenes...). Read-only, robots.txt honoured, same User-Agent as the daily scouts, standard
library only. Writes a receipt: endpoints tried, counts per type, latest 10 items per type.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

BASE = "https://www.superdesalud.gob.cl"
UA = "RadarSaludBot/0.1 (+public-source-monitor)"
PAUSE = 1.5
MAX_PAGES = 5

TYPES = [
    ("Oficio Circular", r"^oficio\s+circular\b"),
    ("Ordinario Circular", r"^ordinario\s+circular\b"),
    ("Circular", r"^circular\b"),
    ("Resolución Exenta", r"^resoluci[oó]n\s+exenta\b"),
    ("Resolución", r"^resoluci[oó]n\b"),
    ("Oficio", r"^(?:oficio|ord(?:inario)?\.?)\b"),
    ("Dictamen", r"^dictamen\b"),
    ("Instrucción", r"^instrucci[oó]n\b"),
    ("Decreto", r"^decreto\b"),
    ("Norma Técnica", r"^norma\s+t[eé]cnica\b"),
]


def doc_type(title: str) -> str:
    t = " ".join(str(title or "").split())
    for name, pattern in TYPES:
        if re.search(pattern, t, re.I):
            return name
    return "Otro"


def emission(title: str):
    m = re.search(r"emisi[oó]n\s*:?\s*(\d{1,2})[/-](\d{1,2})[/-](20\d{2})", title or "", re.I)
    return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else None


class Probe:
    def __init__(self):
        self.robots = RobotFileParser()
        self.log = []
        self.robots_text = None

    def load_robots(self):
        status, body = self._raw(BASE + "/robots.txt")
        self.robots_text = body[:4000] if body else None
        self.robots.parse((body or "").splitlines())

    def _raw(self, url):
        try:
            with urlopen(Request(url, headers={"User-Agent": UA, "Accept": "*/*"}), timeout=40) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except HTTPError as e:
            return e.code, None
        except (URLError, TimeoutError, OSError) as e:
            return f"{type(e).__name__}", None

    def get(self, url):
        allowed = self.robots.can_fetch(UA, url)
        entry = {"url": url, "robots_allowed": allowed}
        if not allowed:
            entry["status"] = "skipped_robots"
            self.log.append(entry)
            return None
        time.sleep(PAUSE)
        status, body = self._raw(url)
        entry.update(status=status, bytes=len(body or ""))
        self.log.append(entry)
        return body if status == 200 else None


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self._href, self._text = [], None, []
        self.rows, self._row, self._cell = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href, self._text = dict(attrs).get("href"), []
        elif tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join("".join(self._text).split())))
            self._href = None
        elif tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


def normative_links(html, page_url):
    p = Links()
    p.feed(html or "")
    out = []
    for href, text in p.links:
        url = urljoin(page_url, href or "")
        if "/normativa/" in urlsplit(url).path and urlsplit(url).path.rstrip("/") != "/normativa" and text:
            if not re.search(r"descargar|^pdf$|p[aá]gina|siguiente|anterior", text, re.I):
                out.append({"title": text, "url": url})
    return out, p.rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    args = ap.parse_args(argv)
    pr = Probe()
    pr.load_robots()
    receipt = {"probe": "sis_normativa_inventory", "user_agent": UA, "base": BASE,
               "started_at": datetime.now(timezone.utc).isoformat(), "robots_txt": pr.robots_text, "sources": {}}

    # 1. WordPress REST API: post types and taxonomies (only if robots allows /wp-json/).
    types = pr.get(BASE + "/wp-json/wp/v2/types")
    rest = {}
    if types:
        try:
            data = json.loads(types)
            rest = {k: {"rest_base": v.get("rest_base"), "name": v.get("name"), "taxonomies": v.get("taxonomies")}
                    for k, v in data.items()}
        except ValueError:
            pass
    receipt["sources"]["wp_types"] = rest
    taxes = pr.get(BASE + "/wp-json/wp/v2/taxonomies")
    tax_info = {}
    if taxes:
        try:
            tax_info = {k: {"rest_base": v.get("rest_base"), "name": v.get("name"), "types": v.get("types")}
                        for k, v in json.loads(taxes).items()}
        except ValueError:
            pass
    receipt["sources"]["wp_taxonomies"] = tax_info
    items = []
    norm_type = next((v for k, v in rest.items() if "normativ" in k.lower() or "normativ" in str(v.get("rest_base")).lower()), None)
    if norm_type and norm_type.get("rest_base"):
        rb = norm_type["rest_base"]
        receipt["sources"]["wp_normativa_rest_base"] = rb
        for tax in norm_type.get("taxonomies") or []:
            tb = (tax_info.get(tax) or {}).get("rest_base") or tax
            body = pr.get(f"{BASE}/wp-json/wp/v2/{tb}?per_page=100&_fields=id,name,slug,count,link")
            if body:
                try:
                    receipt["sources"].setdefault("wp_terms", {})[tax] = json.loads(body)
                except ValueError:
                    pass
        for page in range(1, MAX_PAGES + 1):
            body = pr.get(f"{BASE}/wp-json/wp/v2/{rb}?per_page=100&page={page}&orderby=date&order=desc"
                          "&_fields=id,date,modified,link,title")
            if not body:
                break
            try:
                rows = json.loads(body)
            except ValueError:
                break
            if not rows:
                break
            for r in rows:
                title = re.sub(r"<[^>]+>", "", str((r.get("title") or {}).get("rendered") or ""))
                items.append({"title": " ".join(title.split()), "url": r.get("link"), "wp_date": r.get("date"),
                              "wp_modified": r.get("modified"), "via": "wp_rest"})

    # 2. HTML archive /normativa/ with pagination.
    html_items = []
    for page in range(1, MAX_PAGES + 1):
        url = BASE + "/normativa/" + (f"page/{page}/" if page > 1 else "")
        body = pr.get(url)
        if not body:
            break
        links, _ = normative_links(body, url)
        if not links:
            break
        html_items += [dict(x, via="html_archive", archive_page=page) for x in links]
    receipt["sources"]["html_archive_count"] = len(html_items)

    # 3. WordPress sitemaps that list /normativa/ documents.
    sitemaps = {}
    for sm in ("/wp-sitemap.xml", "/sitemap_index.xml", "/sitemap.xml"):
        body = pr.get(BASE + sm)
        if body:
            sitemaps[sm] = [u for u in re.findall(r"<loc>([^<]+)</loc>", body) if "normativ" in u.lower()][:50]
    receipt["sources"]["sitemaps"] = sitemaps

    # 4. The 'instrucciones dictadas' taxonomy pages already scraped daily (baseline for dedupe).
    current = {}
    for name, path in (("aseguradoras", "/tax-instrucciones-dictadas-por-la-superintendencia/para-aseguradoras-4097/"),
                       ("otros", "/tax-instrucciones-dictadas-por-la-superintendencia/para-otros-destinatarios-7926/")):
        body = pr.get(BASE + path)
        if body:
            links, rows = normative_links(body, BASE + path)
            current[name] = {"links": len(links), "rows": len(rows), "header": rows[0] if rows else None}
    receipt["sources"]["instrucciones_dictadas_baseline"] = current

    # 5. Taxonomy archive pages per document type, when the REST terms expose links.
    for tax, terms in (receipt["sources"].get("wp_terms") or {}).items():
        for term in terms if isinstance(terms, list) else []:
            link = term.get("link")
            if link and term.get("count"):
                body = pr.get(link)
                if body:
                    links, rows = normative_links(body, link)
                    term["archive_links_first_page"] = len(links)
                    term["archive_header"] = rows[0] if rows else None

    seen, merged = set(), []
    for x in items + html_items:
        if x["url"] in seen:
            continue
        seen.add(x["url"])
        x["doc_type"] = doc_type(x["title"])
        x["emission_in_title"] = emission(x["title"])
        merged.append(x)
    by_type = defaultdict(list)
    for x in merged:
        by_type[x["doc_type"]].append(x)
    receipt["counts_per_type"] = dict(Counter(x["doc_type"] for x in merged))
    receipt["latest_10_per_type"] = {k: v[:10] for k, v in by_type.items()}
    receipt["requests"] = pr.log
    receipt["finished_at"] = datetime.now(timezone.utc).isoformat()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"counts_per_type": receipt["counts_per_type"],
                      "requests": [(r["url"], r.get("status")) for r in pr.log]}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
