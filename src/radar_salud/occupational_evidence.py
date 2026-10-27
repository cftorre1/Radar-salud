"""Verify publisher evidence against the actual saved public response bytes."""
from __future__ import annotations
import hashlib
import json
import os
from datetime import datetime, timezone
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


def artifact_available(evidence):
    """True when the declared capture body still exists under the audit root.

    Discovery captures live in a run-scoped runtime directory that the daily
    workflow does not commit; a later run (hourly queue, next daily) cannot
    reread them. Absence is not a verification failure: it triggers a fresh
    same-run capture (Dirección 27-oct-2026), never a weaker check.
    """
    if not isinstance(evidence, dict) or not evidence.get("artifact"):
        return False
    try:
        root = project_root().resolve()
        path = Path(evidence["artifact"])
        path = path.resolve() if path.is_absolute() else (root / path).resolve()
        return path.is_file() and path.is_relative_to(root / "data/audits/source_e_recovery")
    except (OSError, TypeError, ValueError):
        return False


_SAME_RUN_LOADER = None


def same_run_loader():
    """One processing-scoped capture loader per engine run (robots + verified TLS)."""
    global _SAME_RUN_LOADER
    if _SAME_RUN_LOADER is None:
        from .occupational_capture import CaptureLoader
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        _SAME_RUN_LOADER = CaptureLoader(project_root() / "data/audits/source_e_recovery/runtime" / f"{stamp}-processing")
    return _SAME_RUN_LOADER


def _recapture(raw, key, url, loader):
    """Capture ``url`` now and store its verified evidence in item metadata.

    The stored record is what the manual artifact used to prove: exact bytes
    (sha256 + length), verified TLS on every hop, HTTP 200, the final public
    URL and the fetch time. The superseded evidence is kept for audit.
    """
    try:
        loader(url)
        evidence = loader.evidence(url)
        last = loader.records[url]["hops"][-1]
    except DeferredProcessing:
        raise
    except Exception as exc:
        code = getattr(exc, "code", None) or type(exc).__name__
        raise DeferredProcessing(f"occupational same-run capture failed: {code}") from exc
    evidence.update(capture_mode="same_run_verified", fetched_at=evidence["captured_at"],
                    bytes=last.get("bytes"),
                    environment="github_actions" if os.getenv("GITHUB_ACTIONS") == "true" else "local")
    previous = raw.metadata.get(key)
    if isinstance(previous, dict) and previous:
        history = raw.metadata.setdefault("capture_evidence_history", [])
        stale = dict(previous, superseded_reason="artifact_unavailable_in_this_run", key=key)
        if stale not in history:
            history.append(stale)
    raw.metadata[key] = evidence
    return evidence


VISIBLE_DATE_TOLERANCE_DAYS = 3


def verify_capture(raw, hosts, *, loader=None):
    """Verify the item against captured bytes.

    ``loader`` (a callable returning a CaptureLoader) enables the daily-cycle
    standard: when the declared artifact is not present in this run, the page
    is captured again now and every content check runs against those bytes.
    Without ``loader`` (offline replay/snapshots) the strict artifact rule holds.
    """
    evidence = raw.metadata.get("publication_evidence") or raw.metadata.get("publication_date_evidence") or {}
    recaptured = False
    if loader is not None and not artifact_available(raw.metadata.get("capture_evidence")):
        _recapture(raw, "capture_evidence", raw.url, loader())
        recaptured = True
    html = _captured(raw.metadata.get("capture_evidence"), raw.url, hosts)
    if raw.source_slug == "mutual_seguridad":
        from .mutual_sources import parse_detail, parse_listing, _detail_url
        if not _detail_url(raw.url):
            raise DeferredProcessing("occupational mutual public article selector unverified")
        parsed = parse_detail(html, raw.url)
        if evidence.get("kind") == "publisher:mutual_card_fecha":
            listing_url = evidence.get("url")
            if loader is not None and not artifact_available(raw.metadata.get("listing_capture_evidence")):
                _recapture(raw, "listing_capture_evidence", listing_url, loader())
                recaptured = True
            listing = _captured(raw.metadata.get("listing_capture_evidence"), listing_url, hosts)
            if recaptured:
                # Rebind the card date to the bytes captured in this run; the
                # card lookup below still requires the same URL, title and date.
                evidence = dict(evidence, detail_sha256=raw.metadata["capture_evidence"]["sha256"],
                                listing_sha256=raw.metadata["listing_capture_evidence"]["sha256"])
                key = "publication_evidence" if raw.metadata.get("publication_evidence") else "publication_date_evidence"
                raw.metadata[key] = evidence
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
        if evidence.get("kind") == "publisher:visible_header_date":
            # IST: the visible header date replaces a WordPress post date that
            # differs by <= 3 days (Dirección 27-oct-2026). The captured page
            # must still carry the CMS date and show the visible stamp.
            published = verify_visible_header_date(evidence, actual, body)
        elif actual != evidence:
            raise DeferredProcessing("occupational publisher field differs from capture")
    if published != raw.event_date or valid_date(published) != published or fold(title) != fold(raw.title):
        raise DeferredProcessing("occupational article content differs from capture")
    if raw.metadata.get("page_text") != body[:18000]:
        if not recaptured:
            raise DeferredProcessing("occupational article content differs from capture")
        # Same URL, title and publication date verified on fresh bytes: the
        # fresh body is the evidence analysed from now on (edits are recorded).
        raw.metadata["same_run_capture_body_changed"] = True
        raw.metadata["page_text"] = body[:18000]
    if recaptured and raw.metadata.get("supporting_documents"):
        from .occupational_documents import attach_documents
        attach_documents(raw, loader())


def verify_visible_header_date(evidence, cms_evidence, body):
    """Return the visible date when it is within tolerance of the CMS date."""
    visible = valid_date(evidence.get("value"))
    cms = evidence.get("cms_date")
    if (not visible or visible != evidence.get("date") or not isinstance(cms_evidence, dict)
            or cms_evidence.get("date") != cms or not cms):
        raise DeferredProcessing("occupational visible header date unverified")
    try:
        gap = abs((datetime.fromisoformat(visible) - datetime.fromisoformat(cms)).days)
    except ValueError as exc:
        raise DeferredProcessing("occupational visible header date unverified") from exc
    if gap > VISIBLE_DATE_TOLERANCE_DAYS or str(evidence.get("value")) not in body[:1200]:
        raise DeferredProcessing("occupational visible header date unverified")
    return visible
