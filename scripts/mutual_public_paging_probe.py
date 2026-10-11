"""Observe Mutual's public client and native archive links in an anonymous browser.

Diagnostic only: no queue writes, forms, credentials, paid APIs or challenges.
Network bodies and rendered DOM are labeled separately. Cookies and request
headers are never persisted. The browser accepts normal anonymous session state.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import posixpath
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, unquote, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

try:
    from scripts.occupational_access_probe import SAFE_HEADERS, USER_AGENTS, capture, waf_kind
except ModuleNotFoundError:
    from occupational_access_probe import SAFE_HEADERS, USER_AGENTS, capture, waf_kind

PAGE = "https://www.mutual.cl/portal/publico/empresa/home/nuestra-mutual/noticias/"
WORKER_PAGE = "https://www.mutual.cl/portal/publico/trabajador/home/nuestra-mutual/noticias"
OBSERVED_ENTRY_URLS = {PAGE, WORKER_PAGE}
ROBOTS = "https://www.mutual.cl/robots.txt"


def public_url(url):
    try:
        p = urlsplit(url)
        path = posixpath.normpath("/" + unquote(unquote(p.path)).lstrip("/")).casefold()
        return (p.scheme == "https" and p.hostname == "www.mutual.cl"
                and p.port in (None, 443) and not p.username and not p.password
                and path != "/portal/privado" and not path.startswith("/portal/privado/"))
    except ValueError:
        return False


def safe_response_headers(headers):
    return {name.lower(): value for name, value in headers.items() if name.lower() in SAFE_HEADERS}


def now():
    return datetime.now(timezone.utc).isoformat()


async def guard_browser_route(route, policy, output, report, *, inspection_only=False, deadline=None):
    """Inspect executable responses before an anonymous browser receives them."""
    request = route.request
    if (request.method not in {"GET", "HEAD"} or not public_url(request.url)
            or (policy and not policy.can_fetch(USER_AGENTS["identified"], request.url))):
        if inspection_only:
            report["errors"].append({"url": request.url, "reason": "inspection_outside_allowed_public_scope"})
        await route.abort()
        return
    if request.resource_type in {"image", "font", "media"}:
        await route.abort()
        return
    # Ignore unrelated tracking and root WAF fingerprint resources; a portal
    # script still requires response inspection before it can execute.
    if request.resource_type == "script" and not urlsplit(request.url).path.startswith("/portal/"):
        await route.abort()
        return
    if request.resource_type not in {"document", "xhr", "fetch", "script"}:
        await route.continue_()
        return
    current = request.url
    redirect_chain = []
    for hop in range(6):
        # Chromium does not guarantee another route callback for an automatic
        # redirect after fulfill(302). Inspect bounded observed Location hops
        # ourselves, then abort the original browser redirect without rendering
        # those bodies. No URL is manufactured; cookies and authorization
        # headers are never copied or recorded.
        remaining = deadline - time.monotonic() if deadline is not None else 30
        if remaining <= 0:
            report["errors"].append({"url": current, "reason": "diagnostic_time_limit"})
            break
        response = await route.fetch(max_redirects=0, timeout=max(1, min(10000, int(remaining * 1000))),
                                     **({"url": current} if hop else {}))
        body = await response.body()
        challenge = waf_kind(body)
        identity = hashlib.sha256((current + "\n" + str(len(report["responses"]))).encode()).hexdigest()[:20]
        body_file = identity + ".body"
        (Path(output) / body_file).write_bytes(body)
        headers = safe_response_headers(response.headers)
        record = {"url": current, "response_url": response.url,
            "resource_type": request.resource_type if not hop else "redirect_raw_inspection",
            "method": request.method, "captured_at": now(),
            "http_status": response.status, "headers": headers,
            "tls_verified": True, "tls_mechanism": "default_playwright_certificate_validation",
            "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body), "body_file": body_file,
            "waf": challenge}
        if hop or inspection_only:
            record["browser_rendered"] = False
        if hop:
            record["redirect_from"] = redirect_chain[-1]["url"]
        report["responses"].append(record)
        redirect_chain.append(record)
        if challenge:
            report["errors"].append({"url": current, "reason": challenge})
            break
        if response.status not in {301, 302, 303, 307, 308}:
            if not hop:
                await route.fulfill(response=response, body=body)
                return
            break
        location = headers.get("location")
        destination = urljoin(current, location) if location else None
        if (not destination or not public_url(destination)
                or (policy and not policy.can_fetch(USER_AGENTS["identified"], destination))):
            report["errors"].append({"url": current, "reason": "browser_redirect_outside_allowed_scope",
                                     "redirect_destination": destination})
            break
        if hop == 5:
            report["errors"].append({"url": current, "reason": "browser_redirect_limit"})
            break
        current = destination
    if redirect_chain and (len(redirect_chain) > 1 or redirect_chain[0]["http_status"] in {301, 302, 303, 307, 308}):
        report.setdefault("redirect_captures", []).append({
            "request_url": request.url, "final_url": redirect_chain[-1]["url"],
            "http_status": redirect_chain[-1]["http_status"],
            "mode": "raw_inspection_only_browser_redirect_not_executed",
            "hops": [x["url"] for x in redirect_chain], "browser_rendered": False})
        if not inspection_only:
            report["errors"].append({"url": request.url, "reason": "browser_redirect_not_followed"})
    await route.abort()


class _NewsIdentities(HTMLParser):
    """Diagnostic link IDs only; never infer publication from URL or related text."""
    def __init__(self, html):
        super().__init__()
        self.identities = set()
        self.components = set()
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get("class", "").split()
        if tag == "div" and "cards-noticias" in classes and re.fullmatch(r"component-\d+", attrs.get("id", "")):
            self.components.add(attrs["id"])
        if tag != "a" or "href-button" not in classes:
            return
        values = parse_qs(urlsplit(attrs.get("href", "")).query).get("urile", [])
        marker = "/sa_noticias/sa_noticias_detalle/"
        if (len(values) == 1 and values[0].lower().startswith("wcm:path:")
                and marker in values[0].lower() and values[0].lower().split(marker, 1)[1].strip("/")):
            self.identities.add(values[0])


async def inspect_observed_archives(context, anchors, baseline_ids, policy, output, report, deadline):
    """Read at most21 literal current DOM hrefs, without executing their HTML."""
    unique = {}
    for anchor in anchors:
        url = anchor.get("absolute_href")
        if url and url not in unique:
            unique[url] = anchor
    inventory = {"observed_links": len(anchors), "unique_observed_urls": len(unique),
                 "baseline_wcm_ids": len(baseline_ids), "records": [], "new_wcm_ids": [],
                 "coverage_complete": False, "mode": "bounded_observed_raw_GET_without_rendering"}
    report["observed_worker_archive"] = inventory
    union = set()
    for url, anchor in list(unique.items())[:21]:
        if time.monotonic() >= deadline:
            report["errors"].append({"reason": "diagnostic_time_limit"})
            break
        before = len(report["responses"])
        class InspectionRoute:
            request = SimpleNamespace(url=url, method="GET", resource_type="document")
            async def fetch(self, **kwargs):
                target = kwargs.pop("url", url)
                return await context.request.get(target, **kwargs)
            async def fulfill(self, **kwargs):
                pass  # Inspection has no page or renderer.
            async def abort(self):
                pass
        try:
            await asyncio.wait_for(guard_browser_route(InspectionRoute(), policy, output, report,
                                    inspection_only=True, deadline=deadline), timeout=max(.01, deadline-time.monotonic()))
        except Exception as exc:
            report["errors"].append({"url": url, "reason": "observed_archive_inspection_failed",
                                     "exception_type": type(exc).__name__})
        hops = report["responses"][before:]
        record = {"anchor": anchor, "requested_url": url, "hops": [x["url"] for x in hops],
                  "publisher_ids": [], "publication_date_evidence": None}
        if hops:
            final = hops[-1]
            record.update(final_url=final["url"], http_status=final["http_status"],
                          sha256=final["sha256"], body_file=final["body_file"],
                          tls_verified=final["tls_verified"], waf=final["waf"])
            if final["http_status"] == 200 and not final["waf"]:
                parsed = _NewsIdentities((Path(output)/final["body_file"]).read_bytes().decode("utf8", "replace"))
                record["publisher_ids"] = sorted(parsed.identities)
                record["native_category_components"] = len(parsed.components)
                union.update(parsed.identities)
        inventory["records"].append(record)
        if hops and hops[-1]["waf"]:
            break
    inventory["new_wcm_ids"] = sorted(union - set(baseline_ids))
    inventory["inspected_urls"] = len(inventory["records"])
    inventory["all_observed_urls_attempted"] = len(inventory["records"]) == len(unique) <= 21
    inventory["verified_final_responses"] = sum(x.get("http_status") == 200 and not x.get("waf")
                                                for x in inventory["records"])
    if len(unique) > 21:
        report["errors"].append({"reason": "observed_archive_url_limit"})


async def observe(output, as_of, page_url=PAGE):
    # Both literal entry URLs were captured as real public HTML. The worker
    # result intentionally lacks a final slash: retain its actual base URI and
    # let the browser resolve the publisher's anchor without rewriting it.
    if page_url not in OBSERVED_ENTRY_URLS:
        raise ValueError("unobserved_public_news_entry_url")
    deadline = time.monotonic() + 120
    from playwright.async_api import async_playwright

    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    report = {"source_slug": "mutual_seguridad", "started_at": now(), "as_of_chile": as_of,
              "entry_url": page_url,
              "mode": "anonymous_public_browser_diagnostic", "queue_mutated": False,
              "paid_api_called": False, "coverage_complete": False, "responses": [], "steps": [], "errors": []}
    # Inspect real publisher HTML before executing any of it. A challenge is a
    # diagnostic stop, never a reason to execute its scripts or manufacture state.
    policy = None
    for url in (ROBOTS, page_url):
        record = capture(url, output / "preflight", timeout=10)
        report.setdefault("preflight", []).append(record)
        last = record.get("hops", [{}])[-1]
        if (record.get("stop_reason") != "response_captured" or record.get("waf")
                or not last.get("tls", {}).get("verified") or not public_url(record.get("final_url", ""))):
            report["errors"].append({"url": url, "reason": "preflight_unverified_or_challenge"})
            return report
        if url == ROBOTS:
            if last.get("http_status") == 404:
                continue
            if last.get("http_status") != 200:
                report["errors"].append({"url": url, "reason": "robots_policy_unavailable"})
                return report
            policy = RobotFileParser()
            policy.parse((output / "preflight" / last["body_file"]).read_bytes().decode("utf8", "replace").splitlines())
            if not policy.can_fetch(USER_AGENTS["identified"], page_url):
                report["errors"].append({"url": page_url, "reason": "robots_disallowed"})
                return report
        elif last.get("http_status") != 200:
            report["errors"].append({"url": page_url, "reason": "newsroom_http_status", "http_status": last.get("http_status")})
            return report

    async with async_playwright() as p:
        if time.monotonic() >= deadline:
            report["errors"].append({"reason": "diagnostic_time_limit"})
            return report
        browser = await p.chromium.launch(headless=True, timeout=max(1, min(30000, int((deadline-time.monotonic())*1000))))
        context = await browser.new_context(user_agent=USER_AGENTS["identified"], ignore_https_errors=False)
        async def guard(route):
            await guard_browser_route(route, policy, output, report, deadline=deadline)
        await context.route("**/*", guard)
        page = await context.new_page()
        page.set_default_timeout(15000)

        async def snapshot(label):
            await page.wait_for_timeout(400)
            html = (await page.content()).encode()
            file = label + ".dom.html"
            (output / file).write_bytes(html)
            cards = await page.locator("#component-filtered-dynamic .card-noticia").evaluate_all(
                "els => els.map(el => ({title:el.querySelector('.title-card')?.textContent.trim(),"
                "date:el.querySelector('.fecha')?.textContent.trim(),href:el.querySelector('a.href-button')?.getAttribute('href')}))")
            state = {"step": label, "url": page.url, "document_base_uri": await page.evaluate("document.baseURI"),
                     "dom_artifact": file, "dom_sha256": hashlib.sha256(html).hexdigest(),
                     "evidence_type": "browser_rendered_dom_not_raw_publisher_response", "visible_cards": cards,
                     "native_category_components": await page.locator('div.cards-noticias[id^="component-"]').count()}
            report["steps"].append(state)
            return state

        worker_anchors, baseline_ids, native_request = [], set(), None
        try:
            await page.goto(page_url, wait_until="domcontentloaded", timeout=max(1, min(45000, int((deadline-time.monotonic())*1000))))
            await snapshot("initial")
            if page_url == WORKER_PAGE:
                worker_anchors = await page.locator('div.cards-noticias[id^="component-"] a[id$="_nextPage"]').evaluate_all(
                    "els => els.map(el => ({href:el.getAttribute('href'),absolute_href:el.href,"
                    "branch:el.closest('div.cards-noticias').id}))")
                report["observed_worker_anchors"] = worker_anchors
                initial = next((x for x in report["responses"] if x["url"] == page_url
                                and x["http_status"] == 200 and x["waf"] is None), None)
                if initial:
                    baseline_ids = _NewsIdentities((output/initial["body_file"]).read_bytes().decode("utf8", "replace")).identities
            second = page.locator('.paginacion-noticias .page-btn[data-page="2"]')
            if await second.count() == 1 and await second.is_visible():
                before = len(report["responses"])
                await second.click()
                state = await snapshot("visible_client_page_2")
                state["new_document_or_xhr_responses"] = len(report["responses"]) - before
            else:
                report["errors"].append({"reason": "visible_client_page_2_unavailable"})
            # The archive link is present in raw public HTML but hidden by the
            # client union paginator. Record this fact; do not portray it as a
            # visible UI control. Click the actual observed element, no URL edits.
            anchor = page.locator('#component-2 a[id$="_nextPage"]')
            if await anchor.count() == 1:
                metadata = await anchor.evaluate("el => ({href:el.getAttribute('href'),absolute_href:el.href,onclick:el.getAttribute('onclick')})")
                metadata.update(step="observed_native_next_anchor", visible=await anchor.is_visible())
                native_request = metadata["absolute_href"]
                report["steps"].append(metadata)
                async with page.expect_navigation(wait_until="domcontentloaded", timeout=45000):
                    await anchor.evaluate("el => el.click()")
                await snapshot("native_next_result")
            else:
                report["errors"].append({"reason": "observed_native_next_anchor_unavailable"})
        except Exception as exc:
            native_capture = next((x for x in report.get("redirect_captures", [])
                                   if x["request_url"] == native_request), None)
            if native_capture:
                report["steps"].append({"step": "native_next_result",
                    "evidence_type": "raw_redirect_inspection_without_browser_rendering",
                    "capture": native_capture})
            else:
                report["errors"].append({"reason": "browser_observation_failed", "exception_type": type(exc).__name__, "detail": str(exc)[:1800]})
        if worker_anchors and not any(x.get("waf") for x in report["responses"]):
            await inspect_observed_archives(context, worker_anchors, baseline_ids, policy, output, report, deadline)
        await context.close()
        await browser.close()
    report["finished_at"] = now()
    report["stop_reason"] = "public_behavior_observed" if not report["errors"] else "public_behavior_partial"
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--as-of", default="2026-10-11")
    parser.add_argument("--listing-url", "--page-url", dest="listing_url",
                        choices=sorted(OBSERVED_ENTRY_URLS), default=PAGE)
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    try:
        report = asyncio.run(observe(output, args.as_of, args.listing_url))
    except Exception as exc:
        report = {"source_slug": "mutual_seguridad", "coverage_complete": False,
                  "errors": [{"reason": "browser_setup_failed", "exception_type": type(exc).__name__, "detail": str(exc)[:1800]}]}
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"report": str(output / "report.json"), "errors": report.get("errors", []),
                      "coverage_complete": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
