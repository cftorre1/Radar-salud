"""One scoped inventory contract shared by live runtime and offline replay."""
from __future__ import annotations
from datetime import timedelta
from .occupational_inventory import _calendar, discover_inventory, enrich_inventory_from_ist_api
from .occupational_sources import valid_date


def _merge(report, extra):
    if report.get("as_of") != extra.get("as_of"):
        raise ValueError("Cannot merge source inventories from different as_of days")
    today = _calendar(report["as_of"])
    urls, unique_rows, duplicate_rows = set(), [], {}
    for row in report["rows"] + extra["rows"]:
        duplicate_rows.setdefault(row["url"], []).append(row)
        if row["url"] not in urls:
            urls.add(row["url"])
            unique_rows.append(row)
    conflicts = []
    for kept in unique_rows:
        observations = []
        for row in duplicate_rows[kept["url"]]:
            observed = list(row.get("publication_date_observations", []))
            if row.get("publication_date") is not None:
                observed.append({"publication_date": row["publication_date"],
                                 "publication_evidence": row.get("publication_evidence"),
                                 "date_evidence": row.get("date_evidence"),
                                 "listing_url": row.get("listing_url"),
                                 "detail_sha256": row.get("detail_sha256")})
            for value in observed:
                if value not in observations:
                    observations.append(value)
        verified = {day for value in observations
                    if (day := valid_date(value.get("publication_date"), today=today))}
        if len(verified) > 1:
            kept.update(publication_date=None, event_date=None, publication_evidence=None,
                        date_evidence=None, materiality_accepted=None, status="pending",
                        reason="merged_publication_date_conflict", publication_date_observations=observations)
            conflicts.append({"code": "merged_publication_date_conflict", "url": kept["url"],
                              "verified_dates": sorted(verified), "observations": observations})
    raw_urls, unique_raw = set(), []
    for item in report["raw_items"] + extra["raw_items"]:
        if item.url not in raw_urls:
            raw_urls.add(item.url)
            unique_raw.append(item)
    report["rows"], report["raw_items"] = unique_rows, unique_raw
    report["pages"].extend(extra["pages"])
    report["errors"].extend(extra["errors"])
    for conflict in conflicts:
        if not any(error.get("code") == conflict["code"] and error.get("url") == conflict["url"]
                   for error in report["errors"]):
            report["errors"].append(conflict)
    if conflicts:
        report["stop_reason"] = "merged_publication_date_conflict"
    report.setdefault("surface_reports", {})[extra["surface_slug"]] = {k:v for k,v in extra.items() if k not in {"raw_items", "rows"}}
    report["coverage_complete"] = report["coverage_complete"] and extra["coverage_complete"]
    from .beta_sources import CuratedBetaSourceScout
    cfg = CuratedBetaSourceScout.SOURCES[report["source_slug"]]
    accepted_roles = cfg.get("accepted_roles", (cfg["role"],))
    from .achs_clinics import is_static_service_surface
    non_publication_urls = {row["url"] for row in unique_rows if is_static_service_surface(row)}
    verified_days = {row["url"]: valid_date(row.get("publication_date"), today=today) for row in unique_rows}
    blocked_urls = {row["url"] for row in unique_rows
                    if not verified_days[row["url"]] or row.get("status") == "pending"}
    report["raw_items"] = [item for item in report["raw_items"] if item.url not in blocked_urls]
    unknown = sum(day is None and url not in non_publication_urls for url, day in verified_days.items())
    report["coverage_complete"] = bool(report["coverage_complete"] and not unknown and
                                       not any(row.get("status") == "pending" for row in unique_rows))
    report["metrics"] = {}
    for days in (30, 90):
        start = (today - timedelta(days=days)).isoformat()
        end = today.isoformat()
        for row in unique_rows:
            day = verified_days[row["url"]]
            row[f"within_{days}_days"] = bool(day and start <= day <= end)
        rows = [row for row in unique_rows if row[f"within_{days}_days"]]
        report["metrics"][str(days)] = {
            "start": start, "end": end, "dated_articles": len(rows),
            "expected_role": sum(row.get("market_role") in accepted_roles for row in rows),
            "candidates": sum(row.get("status") == "candidate" for row in rows),
            "rejected": sum(row.get("status") == "rejected" for row in rows),
            "excluded_role": sum(row.get("status") == "excluded_role" for row in rows),
            "pending": sum(row.get("status") == "pending" for row in rows),
            "unknown_date_items": unknown, "complete": report["coverage_complete"],
        }
    report["unknown_publication_dates"] = unknown
    report["excluded_non_publication_surfaces"] = len(non_publication_urls)
    report["technical_status"] = "ok" if report["coverage_complete"] else "partial" if unique_rows else "blocked"
    return report


def _decorate(report, scout, loader):
    """Final document/taxonomy view; the primary capture and merge stay intact."""
    from collections import Counter
    from .occupational_documents import attach_documents, verified_document_text, additional_document_facts, documentary_materiality
    from .occupational_sources import classify_content_kind
    from .processing import DeferredProcessing
    rows = {row["url"]: row for row in report["rows"]}
    report["document_diagnostics"] = []
    for raw in report["raw_items"]:
        row = rows.get(raw.url)
        if raw.url in getattr(loader, "records", {}) and not raw.metadata.get("capture_evidence"):
            raw.metadata["capture_evidence"] = loader.evidence(raw.url)
        attach_documents(raw, loader)
        primary = raw.metadata.get("page_text", "")
        try:
            verified = verified_document_text(raw, scout.cfg["hosts"])
            facts = additional_document_facts(primary, verified)
            accepted, reason = documentary_materiality(raw, primary + ("\n" + facts if facts else ""), verified)
            if (raw.metadata.get("supporting_documents_required") and not accepted
                    and any(document.get("truncated") for document in raw.metadata.get("supporting_documents", []))):
                raise DeferredProcessing("required_document_materiality_unresolved_bounded_extraction")
            raw.metadata.update(materiality_accepted=accepted, materiality_reason=reason)
            if row:
                row.update(materiality_accepted=accepted, materiality_reason=reason,
                           status="candidate" if accepted else "rejected", reason=reason)
        except DeferredProcessing as exc:
            reason = str(exc)
            raw.metadata.update(materiality_accepted=None, materiality_reason=reason)
            if row:
                row.update(materiality_accepted=None, materiality_reason=reason, status="pending", reason=reason)
            report["coverage_complete"] = False
            report["document_diagnostics"].append({"code": reason, "url": raw.url})
        for error in raw.metadata.get("supporting_document_diagnostics", []):
            report["document_diagnostics"].append(dict(error, url=error.get("document_url", raw.url)))
        label = classify_content_kind(raw.metadata.get("materiality_reason"), raw.title, primary)
        raw.metadata["content_kind"] = label
        if row:
            row.update(content_kind=label, supporting_document_status=raw.metadata.get("supporting_document_status"),
                       supporting_documents=raw.metadata.get("supporting_documents", []))
    for row in report["rows"]:
        row.setdefault("content_kind", classify_content_kind(row.get("materiality_reason") or row.get("reason"), row.get("title", "")))
    for error in report["document_diagnostics"]:
        if error not in report["errors"]:
            report["errors"].append(error)
    for days, metrics in report.get("metrics", {}).items():
        recent = [row for row in report["rows"] if row.get(f"within_{days}_days")]
        for state, key in (("candidate", "candidates"), ("rejected", "rejected"), ("pending", "pending")):
            metrics[key] = sum(row.get("status") == state for row in recent)
        metrics["content_kinds"] = dict(Counter(row["content_kind"] for row in recent))
        metrics["complete"] = report["coverage_complete"]
    if not report["coverage_complete"] or report["errors"]:
        report["technical_status"] = "partial" if report["rows"] else "blocked"
    return report


def inventory(scout, loader, as_of=None):
    if scout.slug == "mutual_seguridad":
        from .mutual_sources import MutualNewsScout
        return _decorate(MutualNewsScout(fetcher=loader, as_of=as_of).discover_inventory(), scout, loader)
    # The native API provides exhaustive IST date-window pagination; three
    # linked HTML pages suffice to compare it without crawling old archives.
    report = discover_inventory(scout, loader, as_of=as_of, max_pages=3 if scout.slug == "ist" else 20)
    report["newsroom_coverage_complete"] = report["coverage_complete"]
    if scout.slug == "ist":
        return _decorate(enrich_inventory_from_ist_api(report, scout, loader,
            api_headers=lambda url: loader.records[url]["hops"][-1]["headers"]), scout, loader)
    if scout.slug == "clinicas_achs_salud":
        from .achs_blog import discover_blog_inventory
        from .achs_clinics import discover_clinics_inventory
        report = _merge(report, discover_blog_inventory(scout, loader, as_of=as_of))
        report = _merge(report, discover_clinics_inventory(scout, loader, as_of=as_of))
        report["required_clinic_publishers_checked"] = 9
    return _decorate(report, scout, loader)
