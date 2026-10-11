"""One scoped inventory contract shared by live runtime and offline replay."""
from __future__ import annotations
from .occupational_inventory import discover_inventory, enrich_inventory_from_ist_api


def _merge(report, extra):
    urls = {r["url"] for r in report["rows"]}
    report["rows"].extend(r for r in extra["rows"] if r["url"] not in urls)
    report["raw_items"].extend(r for r in extra["raw_items"] if r.url not in urls)
    report["pages"].extend(extra["pages"])
    report["errors"].extend(extra["errors"])
    report.setdefault("surface_reports", {})[extra["surface_slug"]] = {k:v for k,v in extra.items() if k not in {"raw_items", "rows"}}
    report["coverage_complete"] = report["coverage_complete"] and extra["coverage_complete"]
    for days, metrics in report["metrics"].items():
        extra_metrics = extra["metrics"].get(days, {})
        for key in ("dated_articles", "expected_role", "candidates", "rejected", "pending", "unknown_date_items"):
            metrics[key] = metrics.get(key, 0) + extra_metrics.get(key, 0)
        metrics["complete"] = report["coverage_complete"]
    return report


def inventory(scout, loader):
    if scout.slug == "mutual_seguridad":
        from .mutual_sources import MutualNewsScout
        return MutualNewsScout(fetcher=loader).discover_inventory()
    report = discover_inventory(scout, loader)
    report["newsroom_coverage_complete"] = report["coverage_complete"]
    if scout.slug == "ist":
        return enrich_inventory_from_ist_api(report, scout, loader,
            api_headers=lambda url: loader.records[url]["hops"][-1]["headers"])
    if scout.slug == "clinicas_achs_salud":
        from .achs_blog import discover_blog_inventory
        report = _merge(report, discover_blog_inventory(scout, loader))
        report["errors"].append({"code": "individual_clinic_surfaces_pending", "url": "https://www.clinicasachssalud.cl/",
                                "detail": "Central portal opens in public web service; Actions TCP timeout. Individual official clinic routes remain under reconciliation."})
        report["coverage_complete"] = False
    return report

