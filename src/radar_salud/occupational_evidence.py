"""Verify publisher evidence against the actual saved public response bytes."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit, parse_qs, unquote
from .occupational_sources import Article, fold, valid_date
from .paths import project_root
from .processing import DeferredProcessing


def _public(url, hosts):
    try:
        p = urlsplit(url)
        return (p.scheme == "https" and p.hostname in hosts and not p.username and not p.password
                and p.port in (None, 443) and "/privado/" not in p.path and not p.fragment)
    except (TypeError, ValueError):
        return False


def _captured(evidence, url, hosts):
    if (not isinstance(evidence, dict) or evidence.get("url") != url
            or not _public(url, hosts) or not _public(evidence.get("final_url"), hosts)
            or evidence.get("http_status") != 200
            or evidence.get("tls_verified") is not True):
        raise DeferredProcessing("occupational public capture authority unverified")
    if evidence.get("final_url") != url:
        # The IBM query selector redirects to the same named public article.
        requested, final = urlsplit(url), urlsplit(evidence["final_url"])
        query = parse_qs(requested.query)
        content = query.get("urile", [])
        slug = unquote(content[0]).rstrip("/").rsplit("/", 1)[-1] if len(content) == 1 else None
        path = "/portal/publico/empresa/home/nuestra-mutual/noticias/noticias_detalle/"
        final_slug = final.path[len(path):].split("/", 1)[0] if final.path.startswith(path) else None
        if (requested.hostname not in {"www.mutual.cl", "mutual.cl"}
                or query.get("page") != ["publico.empresa.home.nuestraMutual.noticias.noticiasDetalle"]
                or not slug or slug != final_slug or final.query):
            raise DeferredProcessing("occupational capture redirect article identity mismatch")
    root = project_root().resolve()
    path = Path(evidence.get("artifact", ""))
    path = path.resolve() if path.is_absolute() else (root / path).resolve()
    match = re.fullmatch(r"([0-9a-f]{20})-(\d+)\.body", path.name)
    if not match or not path.is_relative_to(root / "data/audits/source_e_recovery") or not path.is_file():
        raise DeferredProcessing("occupational capture artifact unavailable")
    # Metadata alone cannot establish that a successful public response was
    # captured. Bind the exact bytes to the original URL/UA response record.
    try:
        record_path = path.with_name(match[1] + ".json")
        if not record_path.resolve().is_relative_to(root / "data/audits/source_e_recovery"):
            raise ValueError("response record outside audit root")
        record = json.loads(record_path.read_text())
        hops = record["hops"]
        if not isinstance(hops, list) or not hops or not all(isinstance(hop, dict) for hop in hops):
            raise ValueError("invalid response chain")
        last = hops[-1]
        identity = hashlib.sha256((url + "\n" + record["user_agent"]).encode()).hexdigest()[:20]
        if (identity != match[1] or int(match[2]) != len(hops) - 1
                or record["url"] != url or hops[0]["url"] != url
                or record["final_url"] != evidence["final_url"] or last["url"] != record["final_url"]
                or record.get("captured_at") != evidence.get("captured_at") or not record.get("captured_at")
                or record.get("stop_reason") != "response_captured" or record.get("waf")
                or record.get("http_status") != 200 or last["http_status"] != 200
                or last["body_file"] != path.name or last["sha256"] != evidence["sha256"]
                or any(not _public(hop["url"], hosts) or hop.get("curl_exit") != 0
                       or hop.get("waf") or hop.get("tls", {}).get("verified") is not True for hop in hops)
                or any(hop["http_status"] not in (301, 302, 303, 307, 308) for hop in hops[:-1])):
            raise ValueError("saved response differs from declared capture")
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
        raise DeferredProcessing("occupational capture saved response unverified") from exc
    data = path.read_bytes()
    if len(data) != last.get("bytes") or hashlib.sha256(data).hexdigest() != evidence.get("sha256"):
        raise DeferredProcessing("occupational capture bytes mismatch")
    return data.decode("utf-8", errors="replace")


def verify_capture(raw, hosts):
    evidence = raw.metadata.get("publication_evidence") or raw.metadata.get("publication_date_evidence") or {}
    html = _captured(raw.metadata.get("capture_evidence"), raw.url, hosts)
    if raw.source_slug == "mutual_seguridad":
        from .mutual_sources import parse_detail, parse_listing, _detail_url
        if not _detail_url(raw.url):
            raise DeferredProcessing("occupational mutual public article selector unverified")
        parsed = parse_detail(html, raw.url)
        if evidence.get("kind") == "publisher:mutual_card_fecha":
            listing_url = evidence.get("url")
            listing = _captured(raw.metadata.get("listing_capture_evidence"), listing_url, hosts)
            if (evidence.get("detail_sha256") != raw.metadata["capture_evidence"]["sha256"]
                    or evidence.get("listing_sha256") != raw.metadata["listing_capture_evidence"]["sha256"]
                    or evidence.get("item_url") != raw.url):
                raise DeferredProcessing("occupational listing detail hash binding mismatch")
            cards = [c for b in parse_listing(listing, listing_url)["branches"].values() for c in b["cards"]]
            match = [c for c in cards if c["url"] == raw.url and fold(c["title"]) == fold(raw.title)]
            if (not match or any(c["listing_date"] != raw.event_date for c in match)
                    or parsed["reason"] != "missing_publication_date"):
                raise DeferredProcessing("occupational listing publisher identity unverified")
            published = raw.event_date
        else:
            published = parsed["event_date"]
            if evidence != parsed.get("evidence"):
                raise DeferredProcessing("occupational publisher field differs from capture")
        title, body = parsed["title"], parsed["body"]
    else:
        from .achs_clinics import ClinicArticle, clinic_for_host
        article_class = ClinicArticle if clinic_for_host(urlsplit(raw.url).hostname) else Article
        article = article_class(url=raw.url)
        article.feed(html)
        title, published, body, _ = article.result()
        actual = article.publication_evidence()
        if actual != evidence:
            raise DeferredProcessing("occupational publisher field differs from capture")
    if (published != raw.event_date or valid_date(published) != published or fold(title) != fold(raw.title)
            or raw.metadata.get("page_text") != body[:18000]):
        raise DeferredProcessing("occupational article content differs from capture")
