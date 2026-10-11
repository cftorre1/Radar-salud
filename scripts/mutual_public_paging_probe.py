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
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit
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
        path = unquote(unquote(p.path)).casefold()
        return (p.scheme == "https" and p.hostname == "www.mutual.cl"
                and p.port in (None, 443) and not p.username and not p.password
                and path != "/portal/privado" and not path.startswith("/portal/privado/"))
    except ValueError:
        return False


def safe_response_headers(headers):
    return {name.lower(): value for name, value in headers.items() if name.lower() in SAFE_HEADERS}


def now():
    return datetime.now(timezone.utc).isoformat()


async def guard_browser_route(route, policy, output, report):
    """Inspect executable responses before an anonymous browser receives them."""
    request = route.request
    if (request.method not in {"GET", "HEAD"} or not public_url(request.url)
            or (policy and not policy.can_fetch(USER_AGENTS["identified"], request.url))):
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
    response = await route.fetch(max_redirects=0, timeout=30000)
    body = await response.body()
    challenge = waf_kind(body)
    identity = hashlib.sha256((request.url + "\n" + str(len(report["responses"]))).encode()).hexdigest()[:20]
    body_file = identity + ".body"
    (Path(output) / body_file).write_bytes(body)
    report["responses"].append({"url": request.url, "response_url": response.url,
        "resource_type": request.resource_type, "method": request.method, "captured_at": now(),
        "http_status": response.status, "headers": safe_response_headers(response.headers),
        "tls_verified": True, "tls_mechanism": "default_browser_certificate_validation",
        "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body), "body_file": body_file,
        "waf": challenge})
    if challenge:
        report["errors"].append({"url": request.url, "reason": challenge})
        await route.abort()
    else:
        await route.fulfill(response=response, body=body)


async def observe(output, as_of, page_url=PAGE):
    # Both literal entry URLs were captured as real public HTML. The worker
    # result intentionally lacks a final slash: retain its actual base URI and
    # let the browser resolve the publisher's anchor without rewriting it.
    if page_url not in OBSERVED_ENTRY_URLS:
        raise ValueError("unobserved_public_news_entry_url")
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
        record = capture(url, output / "preflight")
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
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=USER_AGENTS["identified"], ignore_https_errors=False)
        async def guard(route):
            await guard_browser_route(route, policy, output, report)
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

        try:
            await page.goto(page_url, wait_until="domcontentloaded", timeout=45000)
            await snapshot("initial")
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
                report["steps"].append(metadata)
                async with page.expect_navigation(wait_until="domcontentloaded", timeout=45000):
                    await anchor.evaluate("el => el.click()")
                await snapshot("native_next_result")
            else:
                report["errors"].append({"reason": "observed_native_next_anchor_unavailable"})
        except Exception as exc:
            report["errors"].append({"reason": "browser_observation_failed", "exception_type": type(exc).__name__, "detail": str(exc)[:1800]})
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
