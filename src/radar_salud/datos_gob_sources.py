"""datos.gob.cl (CKAN) data releases for FONASA and DEIS-MINSAL.

Dirección 27-oct-2026 (decision a): fonasa.cl answers HTTP 403 to Actions, so
the national open-data catalog is the substitute for FONASA data. The scout is
deterministic (no AI): it lists each publisher's datasets with their CKAN
``metadata_modified`` and keeps only datasets that are new or updated inside
the daily window. That timestamp is labelled a *data release* date
(``date_basis='data_release'``), never a news publication date.

CKAN terms: only catalog metadata and links are stored; resource files are
never downloaded or republished. robots.txt is honoured before any API call.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from urllib.parse import urlencode, urlsplit
from urllib.robotparser import RobotFileParser

from .date_basis import CHILE, DATA_RELEASE, chile_day
from .models import RawItem
from .processing import DeferredProcessing

SLUG = "datos_gob_cl"
HOST = "datos.gob.cl"
API = "https://datos.gob.cl/api/3/action/package_search"
ROBOTS = "https://datos.gob.cl/robots.txt"
USER_AGENT = "RadarSaludBot/0.3 (+public-source-monitor)"
ROWS = 100
EVIDENCE_KIND = "ckan:metadata_modified"


def _is_deis(row):
    notes = row.get("notes") or ""
    return (any(str(t.get("name", "")).casefold() == "deis" for t in row.get("tags") or [])
            or row.get("author_email") == "deis@minsal.cl"
            or "Departamento de Estadísticas e Información de Salud" in notes)


PUBLISHERS = {
    "fondo_nacional_de_salud": {"label": "FONASA", "source_name": "FONASA (datos.gob.cl)",
                                "scopes": ["Fonasa"], "accept": lambda row: True},
    "ministerio_de_salud": {"label": "DEIS-MINSAL", "source_name": "DEIS-MINSAL (datos.gob.cl)",
                            "scopes": ["Sistema de salud"], "accept": _is_deis},
}


def live_lane_enabled(env=None):
    from .live_lanes import enabled
    return enabled("RADAR_DATOS_GOB", env)


def query_url(organization, rows=ROWS):
    return API + "?" + urlencode({"fq": f"organization:{organization}", "sort": "metadata_modified desc",
                                  "rows": str(rows)})


def _official(url):
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == "https" and parsed.hostname == HOST and parsed.port in (None, 443)
                and not parsed.username and not parsed.password)
    except (TypeError, ValueError):
        return False


def _fetch(url, *, timeout=30, max_bytes=12 * 1024 * 1024):
    """Verified-TLS GET restricted to datos.gob.cl (redirects included)."""
    from datetime import timezone
    from urllib.request import HTTPRedirectHandler, Request, build_opener

    class _SameHost(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if not _official(newurl):
                raise ValueError("datos.gob.cl redirect left the official HTTPS host")
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    if not _official(url):
        raise ValueError("datos.gob.cl URL must be official HTTPS")
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json,text/plain;q=0.9"})
    # Default HTTPS handler: system CA trust and hostname verification stay on.
    with build_opener(_SameHost()).open(request, timeout=timeout) as response:
        final = response.geturl()
        if not _official(final):
            raise ValueError("datos.gob.cl response left the official HTTPS host")
        body = response.read(max_bytes + 1)
    if len(body) > max_bytes:
        raise ValueError("datos.gob.cl response exceeds the byte limit")
    return body, {"url": url, "final_url": final, "sha256": hashlib.sha256(body).hexdigest(),
                  "bytes": len(body), "tls_verified": True,
                  "captured_at": datetime.now(timezone.utc).isoformat()}


class RobotsUnavailable(PermissionError):
    """robots.txt could not be read (429, 5xx, network): the policy is unknown, so crawling fails closed."""

    def __init__(self, cause):
        self.cause = str(cause)
        super().__init__(f"robots_unavailable: {cause}"[:200])


def load_robots_policy(fetch_bytes, robots_url):
    """Read a robots.txt following RFC 9309 status rules; returns ``(RobotFileParser, status)``.

    A 4xx other than 401/403/429 (e.g. 404) means "no robots file": crawling is allowed (the same rule as
    ``RobotFileParser.read``). 401/403 disallow all. A 429, a 5xx or a network error leaves the policy unknown and
    raises ``RobotsUnavailable`` (fail closed). Shared by the datos.gob.cl lane and the SIS stats capture.
    """
    from urllib.error import HTTPError
    parser = RobotFileParser()
    try:
        body = fetch_bytes(robots_url)
        parser.parse(body.decode("utf-8", errors="replace").splitlines())
        status = "parsed"
    except HTTPError as exc:
        if exc.code in (401, 403):
            parser.disallow_all, status = True, f"http_{exc.code}_disallow_all"
        elif 400 <= exc.code < 500 and exc.code != 429:
            parser.allow_all, status = True, f"http_{exc.code}_no_robots_file"
        else:
            raise RobotsUnavailable(f"HTTP {exc.code}") from exc
    except Exception as exc:
        raise RobotsUnavailable(f"{type(exc).__name__}: {exc}") from exc
    return parser, status


def parse_package_search(payload, organization, *, api_url, today, window_days, capture=None):
    """CKAN package_search -> (RawItems inside the window, per-surface report)."""
    publisher = PUBLISHERS[organization]
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise ValueError("CKAN package_search did not return success")
    result = payload.get("result") or {}
    rows = result.get("results")
    if not isinstance(rows, list) or not isinstance(result.get("count"), int):
        raise ValueError("CKAN package_search result is malformed")
    start = today - timedelta(days=window_days)
    items, excluded, modified_days = [], [], []
    for row in rows:
        if not isinstance(row, dict) or (row.get("organization") or {}).get("name") != organization:
            excluded.append({"id": (row or {}).get("id"), "reason": "publisher_not_verified"})
            continue
        if row.get("private") or row.get("state") not in (None, "active"):
            excluded.append({"id": row.get("id"), "reason": "not_public_active"})
            continue
        try:
            modified = chile_day(row["metadata_modified"])
            created = chile_day(row.get("metadata_created") or row["metadata_modified"])
        except (KeyError, TypeError, ValueError):
            excluded.append({"id": row.get("id"), "reason": "metadata_modified_invalid"})
            continue
        modified_days.append(modified)
        if not publisher["accept"](row):
            excluded.append({"id": row.get("id"), "reason": "publisher_scope_not_verified"})
            continue
        if not start <= modified <= today:
            continue
        dataset_url = f"https://{HOST}/dataset/{row.get('name') or row['id']}"
        resources = []
        for resource in row.get("resources") or []:
            link = str(resource.get("url") or "")
            try:
                updated = chile_day(resource.get("last_modified") or resource.get("created"))
            except (TypeError, ValueError):
                updated = None
            resources.append({"id": resource.get("id"), "name": (resource.get("name") or "").strip()[:160],
                              "format": (resource.get("format") or "").strip()[:20], "url": link,
                              "last_modified": resource.get("last_modified"), "created": resource.get("created"),
                              "updated_in_window": bool(updated and start <= updated <= today)})
        is_new = start <= created <= today
        title = " ".join(str(row.get("title") or row.get("name") or "").split())
        # "Datos actualizados" only when the dataset is new or a resource changed
        # inside the window; a metadata-only edit is a catalog update.
        scope = "data" if is_new or any(r["updated_in_window"] for r in resources) else "catalog"
        action = ("publicó un nuevo conjunto de datos" if is_new else
                  "actualizó el conjunto de datos" if scope == "data" else "actualizó la ficha de catálogo de")
        # Identity = dataset + release month (also the history key): weekly
        # refreshes inside one month replace each other; a new month is a new card.
        release_url = f"{dataset_url}#liberacion-{modified:%Y-%m}"
        evidence = {"kind": EVIDENCE_KIND, "url": api_url, "dataset_url": dataset_url,
                    "value": row["metadata_modified"], "date": modified.isoformat(),
                    "basis": "data_release_not_news_publication"}
        if capture:
            evidence.update(api_sha256=capture.get("sha256"), captured_at=capture.get("captured_at"))
        items.append(RawItem(
            # Queue identity is slug|url|title: the title carries no action, so a
            # catalog->data change in the same month never creates a second card.
            SLUG, f"{publisher['label']} en datos.gob.cl: «{title}»"[:350], release_url,
            publisher["source_name"], "official", event_date=modified.isoformat(),
            raw_text=" ".join(str(row.get("notes") or "").split())[:1800],
            metadata={"organization": organization, "publisher_label": publisher["label"],
                      "dataset_id": row.get("id"), "dataset_name": row.get("name"), "dataset_title": title,
                      "metadata_modified": row["metadata_modified"], "metadata_created": row.get("metadata_created"),
                      "release_kind": "new_dataset" if is_new else "dataset_update", "release_action": action,
                      "license_id": row.get("license_id"), "license_title": row.get("license_title"),
                      "resources": resources, "scopes": publisher["scopes"],
                      "date_basis": DATA_RELEASE, "data_release_date": modified.isoformat(),
                      "data_release_scope": scope, "dataset_url": dataset_url, "release_month": f"{modified:%Y-%m}",
                      "publication_date_source": EVIDENCE_KIND, "publication_date_evidence": evidence,
                      "date_label": ("Fecha de liberación del dato en datos.gob.cl (metadata_modified), no fecha de noticia"
                                     if scope == "data" else
                                     "Fecha de actualización de la ficha del catálogo (metadata_modified); sin recurso nuevo"),
                      "terms_policy": "catalog_metadata_and_links_only"}))
    oldest = min(modified_days) if modified_days else None
    # Sorted by metadata_modified desc: the window is fully covered when the
    # catalog is exhausted or the last returned dataset is older than it.
    complete = len(rows) >= result["count"] or bool(oldest and oldest < start)
    report = {"organization": organization, "url": api_url, "catalog_count": result["count"],
              "returned": len(rows), "in_window": len(items), "excluded": excluded,
              "window_start": start.isoformat(), "window_complete": complete,
              "latest_metadata_modified": max(modified_days).isoformat() if modified_days else None}
    if capture:
        report["capture"] = {k: capture.get(k) for k in ("sha256", "bytes", "captured_at", "final_url")}
    return items, report


class DatosGobScout:
    """FONASA and DEIS datasets new/updated inside the daily window."""
    slug = SLUG

    def __init__(self, fetch=None, today=None, window_days=None, enabled=None, robots=None):
        self.fetch = fetch or _fetch
        self.today = today
        self.window_days = window_days
        self.enabled = enabled
        self.robots = robots
        self.robots_status = "injected" if robots is not None else None
        self._robots = None
        self._robots_failure = None
        self.diagnostics = {}

    def _robots_policy(self):
        """Fetch robots.txt once per run (``load_robots_policy``, RFC 9309 status rules).

        The outcome is cached for the run, failures included: robots.txt is requested once, not once per publisher.
        """
        if getattr(self, "_robots_failure", None) is not None:
            raise PermissionError(self._robots_failure)
        if getattr(self, "_robots", None) is not None:
            return self._robots
        try:
            parser, status = load_robots_policy(lambda url: self.fetch(url)[0], ROBOTS)
        except RobotsUnavailable as exc:
            self._robots_unavailable(exc.cause)
        self._robots, self.robots_status = parser, status
        return parser

    def _robots_unavailable(self, cause):
        self.robots_status = "robots_unavailable"
        self._robots_failure = f"robots_unavailable: {cause}"[:200]
        raise PermissionError(self._robots_failure)

    def _allowed(self, url):
        if self.robots is not None:
            return self.robots(url)
        return self._robots_policy().can_fetch(USER_AGENT, url)

    def discover(self):
        enabled = live_lane_enabled() if self.enabled is None else self.enabled
        if not enabled:
            self.diagnostics = {"status": "not_run_outside_engine_runtime", "partial_failure": False}
            return []
        from .daily_window import requested_window_days
        today = self.today or datetime.now(CHILE).date()
        window = self.window_days or requested_window_days()
        items, surfaces, errors = [], [], []
        for organization in PUBLISHERS:
            url = query_url(organization)
            try:
                if not _official(url) or not self._allowed(url):
                    raise PermissionError(f"robots_disallowed: {urlsplit(url).path} for {USER_AGENT}")
                body, capture = self.fetch(url)
                found, report = parse_package_search(json.loads(body), organization, api_url=url, today=today,
                                                     window_days=window, capture=capture)
                items.extend(found)
                surfaces.append(report)
                if not report["window_complete"]:
                    errors.append({"organization": organization, "reason": "window_not_fully_covered_by_rows"})
            except Exception as exc:
                errors.append({"organization": organization, "url": url, "reason": f"{type(exc).__name__}: {exc}"[:300]})
        self.diagnostics = {"surfaces": surfaces, "errors": errors, "partial_failure": bool(errors),
                            "robots_status": self.robots_status,
                            "window_days": window, "date_basis": DATA_RELEASE,
                            "terms_policy": "catalog_metadata_and_links_only"}
        if errors and not surfaces:
            raise RuntimeError("datos.gob.cl discovery failed: " + "; ".join(e["reason"] for e in errors))
        self.discovery_errors = [f"{e['organization']}: {e['reason']}" for e in errors]
        return sorted(items, key=lambda raw: raw.event_date or "", reverse=True)


def process_datos_gob(raw, cfg):
    """Deterministic 'Datos' card for a verified data release (no AI)."""
    from .pipeline import build_signal
    evidence = raw.metadata.get("publication_date_evidence") or {}
    if (raw.source_slug != SLUG or not _official(raw.url) or evidence.get("kind") != EVIDENCE_KIND
            or not _official(evidence.get("url")) or evidence.get("date") != raw.event_date
            or raw.metadata.get("date_basis") != DATA_RELEASE):
        raise DeferredProcessing("datos.gob.cl release evidence unverified")
    try:
        if chile_day(evidence["value"]).isoformat() != raw.event_date:
            raise ValueError
    except (KeyError, TypeError, ValueError) as exc:
        raise DeferredProcessing("datos.gob.cl release evidence unverified") from exc
    label, title = raw.metadata["publisher_label"], raw.metadata["dataset_title"]
    updated = [r for r in raw.metadata.get("resources", []) if r.get("updated_in_window")]
    names = "; ".join(f"{r['name']} ({r['format']})" if r.get("format") else r["name"]
                      for r in updated[:4] if r.get("name"))
    new = raw.metadata.get("release_kind") == "new_dataset"
    catalog_only = raw.metadata.get("data_release_scope") == "catalog"
    verb = ("publicó en datos.gob.cl el nuevo conjunto de datos" if new else
            "actualizó en datos.gob.cl la ficha de catálogo (sin recurso nuevo) del conjunto de datos" if catalog_only else
            "actualizó en datos.gob.cl el conjunto de datos")
    what = f"{label} {verb} «{title}» ({raw.event_date})." + (f" Recursos actualizados: {names}." if names else "")
    notes = " ".join(str(raw.raw_text or "").split())
    why = ((notes[:260].rstrip(" ,;") + ". ") if len(notes) >= 40 else "")
    why += ("Es una liberación oficial de datos, no una noticia: permite actualizar series de seguimiento "
            "y comparaciones con la fuente primaria; la fecha corresponde a la actualización del catálogo.")
    raw.metadata.update({"what_happened": what, "why_it_matters": why, "signal_types": ["Datos"],
                         "scopes": raw.metadata.get("scopes") or ["Sistema de salud"],
                         "watch_tags": ["datos.gob.cl", label.lower(), "datos abiertos"],
                         "scores": {"economic": 55, "regulatory": 35, "scope": 65, "novelty": 70 if new else 60,
                                    "actionability": 60}})
    row = build_signal(raw, cfg).to_dict()
    row.update(signal_types=["Datos"], scopes=raw.metadata["scopes"], source_channel="datos.gob.cl",
               date_basis=DATA_RELEASE, data_release_date=raw.event_date, publication_date=None,
               data_release_scope=raw.metadata.get("data_release_scope", "data"),
               publication_date_source=EVIDENCE_KIND, publication_date_evidence=evidence,
               date_label=raw.metadata["date_label"], dataset_id=raw.metadata.get("dataset_id"),
               license_id=raw.metadata.get("license_id"),
               source_documents=[{"title": r["name"], "url": r["url"], "format": r.get("format")}
                                 for r in raw.metadata.get("resources", []) if r.get("url")][:6],
               deterministic_processing=True,
               record_hash=hashlib.sha256(json.dumps([raw.url, evidence.get("value")]).encode()).hexdigest()[:24])
    return row
