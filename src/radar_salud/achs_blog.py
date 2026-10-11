"""Inventory the observed ACHS Salud blog DOM without executing its pager.

The captured page serializes ``cf_item`` records and explicitly distinguishes
PublicationDate, DateCreated and LastModified. A custom FechaArticulo can
contradict PublicationDate; those records remain pending. Listing evidence
supports inventory counts, but a material item still needs its own verified
detail publication before becoming a RawItem.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

from .models import RawItem
from .occupational_sources import Article, assert_not_challenge, chile_today, fold, materiality

BLOG_URL = "https://www.achssalud.cl/blog"
FIELDS = {"navigateUrl", "Title", "Contenido", "Resume", "PublicationDate", "sortPublicationDate",
          "FechaArticulo", "LastModified", "DateCreated"}


def _cms_date(value, *, today):
    """Whole-field Sitefinity Spanish timestamp, as observed in this publisher."""
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"(ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)\. (\d{1,2}), (\d{4}), (\d{2}):(\d{2})", value.strip(), re.I)
    if not match:
        return None
    months = dict(zip(("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"), range(1, 13)))
    try:
        stamp = datetime(int(match[3]), months[match[1].casefold()], int(match[2]), int(match[4]), int(match[5]))
    except ValueError:
        return None
    return stamp if stamp.date() <= today else None


class _BlogRecords(HTMLParser):
    VOID = {"meta", "img", "br", "hr", "input", "link", "source", "area", "base", "embed", "param", "wbr"}
    IGNORE = {"script", "style", "nav", "header", "footer", "aside"}

    def __init__(self):
        super().__init__()
        self.stack, self.ignored, self.fields, self.records = [], [], [], []
        self.current = None
        self.errors = []

    def handle_starttag(self, tag, attrs):
        if tag in self.IGNORE:
            self.ignored.append(tag)
            return
        if self.ignored:
            return
        attrs = dict(attrs)
        if tag not in self.VOID:
            self.stack.append(tag)
        classes = set(attrs.get("class", "").split())
        if "cf_item" in classes:
            if self.current is not None:
                self.errors.append("nested_blog_record")
            else:
                self.current = {"depth": len(self.stack), "fields": {}}
        if self.current is not None and tag not in self.VOID:
            for key in classes & FIELDS:
                self.fields.append({"depth": len(self.stack), "key": key, "parts": []})

    def handle_data(self, text):
        if not self.ignored:
            for field in self.fields:
                field["parts"].append(text)

    def handle_endtag(self, tag):
        if self.ignored:
            if tag == self.ignored[-1]:
                self.ignored.pop()
            return
        if tag not in self.stack:
            return
        depth = len(self.stack) - self.stack[::-1].index(tag)
        for field in list(self.fields):
            if field["depth"] >= depth:
                value = " ".join(" ".join(field["parts"]).split())
                self.current["fields"].setdefault(field["key"], []).append(value)
                self.fields.remove(field)
        if self.current is not None and self.current["depth"] >= depth:
            self.records.append(self.current["fields"])
            self.current = None
        del self.stack[depth - 1:]

    def finish(self):
        if self.current is not None:
            self.errors.append("unclosed_blog_record")


class _BodyText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.ignored = [], []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "footer", "aside"):
            self.ignored.append(tag)

    def handle_endtag(self, tag):
        if self.ignored and self.ignored[-1] == tag:
            self.ignored.pop()

    def handle_data(self, text):
        if not self.ignored:
            self.parts.append(text)


def _one(fields, name):
    values = fields.get(name, [])
    return values[0] if values and len(set(values)) == 1 else None


def _url(href):
    try:
        parsed = urlsplit(urljoin(BLOG_URL, href or ""))
        if (parsed.scheme != "https" or parsed.netloc != "www.achssalud.cl"
                or not re.fullmatch(r"/blog/detalle/[^/]+/?", parsed.path)):
            return None
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    except ValueError:
        return None


def _error(exc, url, default):
    code = getattr(exc, "code", None)
    if not isinstance(code, str):
        code = "executor_proxy_denied" if "Tunnel connection failed: 403" in str(exc) else default
    error = {"code": code, "url": url, "exception_type": type(exc).__name__, "detail": str(exc)}
    if code != "executor_proxy_denied" and isinstance(getattr(exc, "code", None), int):
        error["http_status"] = exc.code
    return error


def _publication(fields, today):
    values = fields.get("PublicationDate", [])
    stamps = [_cms_date(value, today=today) for value in values]
    observations = {key: fields.get(key, []) for key in ("PublicationDate", "sortPublicationDate", "FechaArticulo", "LastModified", "DateCreated")}
    if not values or any(stamp is None for stamp in stamps):
        return None, "missing_or_invalid_publication_date", observations
    if len({stamp.date() for stamp in stamps}) != 1:
        return None, "conflicting_publication_dates", observations
    day = stamps[0].date()
    for value in fields.get("sortPublicationDate", []):
        try:
            if not re.fullmatch(r"\d{14}", value):
                raise ValueError()
            sortable = datetime.strptime(value, "%Y%m%d%H%M%S")
            if sortable.replace(second=0) not in stamps:
                return None, "conflicting_publication_dates", observations
        except ValueError:
            return None, "invalid_sort_publication_date", observations
    for value in fields.get("FechaArticulo", []):
        custom = _cms_date(value, today=today)
        if custom is None:
            return None, "invalid_editorial_article_date", observations
        if custom.date() != day:
            return None, "publication_editorial_date_conflict", observations
    return day, "listing:sitefinity.PublicationDate", observations


def discover_blog_inventory(scout, loader, as_of=None):
    """Read all serialized blog records; never turn general advice into a signal.

    No URL or API is synthesized for pagination. The verified publisher script
    pages an in-memory list in groups of nine, sorted by LastModified. Reported
    CMS dates are retained separately from safe publication dates and never
    advance newsroom completion or live watermarks.
    """
    if scout.slug != "clinicas_achs_salud":
        raise ValueError("ACHS Salud blog belongs to the provider lane")
    today = as_of or chile_today()
    if isinstance(today, datetime):
        today = today.date()
    if isinstance(today, str):
        today = date.fromisoformat(today)
    starts = {days: today - timedelta(days=days) for days in (30, 90)}
    report = {"source_slug": scout.slug, "surface_slug": "achs_salud_blog", "as_of": today.isoformat(),
              "window": {"convention": "rolling_elapsed_days_inclusive", "end": today.isoformat(),
                         "start_30": starts[30].isoformat(), "start_90": starts[90].isoformat()},
              "rows": [], "raw_items": [], "pages": [], "errors": [], "metrics": {},
              "coverage_complete": False, "observed_dataset_exhausted": False,
              "stop_reason": None, "technical_status": "blocked"}
    try:
        html = loader(BLOG_URL)
        assert_not_challenge(html, BLOG_URL)
        parser = _BlogRecords()
        parser.feed(html)
        parser.finish()
    except Exception as exc:
        report["errors"].append(_error(exc, BLOG_URL, "blog_fetch_failed"))
        report["stop_reason"] = report["errors"][0]["code"]
        return _metrics(report, starts, today)
    page = {"url": BLOG_URL, "sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
            "records": len(parser.records), "status": "captured", "pagination": "serialized_client_side_dataset",
            "next_url": None}
    report["pages"].append(page)
    report["errors"].extend({"code": code, "url": BLOG_URL} for code in parser.errors)
    if not parser.records:
        report["errors"].append({"code": "blog_structure_unrecognized", "url": BLOG_URL})
    report["observed_dataset_exhausted"] = bool(parser.records) and not parser.errors
    seen = set()
    for fields in parser.records:
        title, href = _one(fields, "Title"), _one(fields, "navigateUrl")
        url = _url(href)
        day, evidence, observations = _publication(fields, today)
        primary = _cms_date(_one(fields, "PublicationDate"), today=today)
        body_field = _one(fields, "Contenido")
        text = _BodyText()
        text.feed(body_field or "")
        body = " ".join(" ".join(text.parts).split())
        row = {"url": url or href, "title": title or "", "listing_url": BLOG_URL,
               "section": "blog_salud_y_bienestar", "type": "health_advice_article",
               "source_type": scout.cfg["type"], "market_role": "provider_achs_centers", "provider_subtype": "centros",
               "publication_date": day.isoformat() if day else None, "event_date": day.isoformat() if day else None,
               "publisher_reported_date": primary.date().isoformat() if primary else None,
               "date_evidence": evidence, "date_observations": observations, "status": "pending", "reason": evidence,
               "materiality_accepted": None, "materiality_reason": None,
               "publication_evidence": ({"date": day.isoformat(), "value": fields["PublicationDate"][0],
                                         "url": BLOG_URL, "kind": evidence, "record_url": url,
                                         "selector": ".cf_item .PublicationDate"} if day else None)}
        reported_days = [stamp.date() for key in ("PublicationDate", "FechaArticulo")
                         for value in fields.get(key, []) if (stamp := _cms_date(value, today=today))]
        for days in (30, 90):
            row[f"within_{days}_days"] = bool(day and starts[days] <= day <= today)
            row[f"potentially_within_{days}_days"] = any(starts[days] <= reported <= today for reported in reported_days)
        if not url or not title or len(title) < 12 or not body_field or len(body) < 160:
            row.update(status="pending", reason="blog_record_content_unrecognized")
        elif url in seen:
            row.update(status="pending", reason="duplicate_blog_record")
        elif not day:
            pass
        elif day < starts[90]:
            row.update(status="outside_window", reason="outside_90_day_horizon")
        else:
            accepted, reason = materiality("provider_achs_centers", title, body)
            row.update(materiality_accepted=accepted, materiality_reason=reason,
                       status="pending" if accepted else "rejected", reason="detail_publication_verification_required" if accepted else reason)
            if accepted:
                try:
                    detail_html = loader(url)
                    assert_not_challenge(detail_html, url)
                    detail = Article(url=url)
                    detail.feed(detail_html)
                    detail_title, detail_day, detail_body, detail_kind = detail.result(today=today)
                    detail_evidence = detail.publication_evidence(today=today)
                    if (detail_day != day.isoformat() or fold(detail_title) != fold(title) or len(detail_body) < 160 or not detail_evidence):
                        row["reason"] = "detail_listing_publication_or_content_mismatch"
                    else:
                        detail_accepted, detail_reason = materiality("provider_achs_centers", detail_title, detail_body)
                        if detail_accepted:
                            row.update(status="candidate", reason=detail_reason, publication_evidence=detail_evidence,
                                       date_evidence=detail_kind, type="provider_change_article")
                            report["raw_items"].append(RawItem(scout.slug, detail_title[:350], url, scout.cfg["name"], scout.cfg["type"],
                                event_date=detail_day, raw_text=detail_body[:1800], metadata={
                                    "discovered_from": BLOG_URL, "page_text": detail_body[:18000],
                                    "market_role": "provider_achs_centers", "provider_subtype": "centros",
                                    "article_extraction": "occupational_v1", "publication_date": detail_day,
                                    "publication_date_source": detail_kind, "publication_evidence": detail_evidence,
                                    "source_quality_gate": "audit_pending_90_day", "materiality_accepted": True,
                                    "materiality_reason": detail_reason}))
                        else:
                            row.update(status="rejected", reason="material_change_not_confirmed_in_detail", materiality_accepted=False)
                except Exception as exc:
                    row["error"] = _error(exc, url, "blog_detail_fetch_failed")
                    row["reason"] = row["error"]["code"]
        if url:
            seen.add(url)
        if row["status"] == "pending":
            report["errors"].append(row.get("error") or {"code": row["reason"], "url": url or BLOG_URL})
        report["rows"].append(row)
    # Even an exhausted blog DOM cannot establish coverage for all clinic
    # publishers. The parent combines this surface with separately probed sites.
    report["stop_reason"] = "date_or_detail_gaps_in_blog" if report["errors"] else "observed_blog_dataset_exhausted_additional_sites_pending"
    report["technical_status"] = "partial" if report["rows"] else "blocked"
    page["status"] = "partial" if report["errors"] else "captured"
    return _metrics(report, starts, today)


def _metrics(report, starts, today):
    for days in (30, 90):
        rows = [row for row in report["rows"] if row[f"within_{days}_days"]]
        report["metrics"][str(days)] = {"start": starts[days].isoformat(), "end": today.isoformat(),
            "dated_articles": len(rows), "expected_role": len(rows),
            "candidates": sum(row["status"] == "candidate" for row in rows),
            "rejected": sum(row["status"] == "rejected" for row in rows), "excluded_role": 0,
            "pending": sum(row["status"] == "pending" and row[f"potentially_within_{days}_days"] for row in report["rows"]),
            "publisher_reported_articles": sum(bool(row["publisher_reported_date"] and starts[days].isoformat() <= row["publisher_reported_date"] <= today.isoformat()) for row in report["rows"]),
            "unknown_date_items": sum(not row["publication_date"] for row in report["rows"]), "complete": False}
    report["unknown_publication_dates"] = sum(not row["publication_date"] for row in report["rows"])
    return report
