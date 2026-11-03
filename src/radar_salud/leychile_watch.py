"""BCN LeyChile: WATCH a fixed list of key health norms for new versions.

Dirección 3-nov-2026: first a probe (robots.txt + one real query from CI); if
it passes, a no-AI watch of key norms. Only metadata is stored (type/number,
title, organism, fechaVersion/fechaPublicacion, idNorma, link); the text of a
norm is never stored or reproduced. The licence is unclear (CC BY-NC-SA
announced in 2007; the current bcn.cl privacy page metadata says CC BY-SA 3.0
CL): metadata + link only (config/bcn_leychile_watch.json, ``license_note``).

Service (Biblioteca del Congreso Nacional, document "accesoLeyesChilenas4.pdf",
2009, possibly outdated): ``/Consulta/obtxml?opt=7&idNorma=<id>`` or
``&idLey=<n>`` returns the XML of the norm's latest version (root ``Norma``
with ``normaId``/``fechaVersion``; ``Identificador`` with
``fechaPublicacion``/``fechaPromulgacion``, ``TiposNumeros``, ``Organismos``;
``Metadatos/TituloNorma``; parts carry ``fechaVersion``). Third-party clients
use ``opt=61&cadena=`` for search. None of this could be verified from the
development session (bcn.cl / leychile.cl are outside its proxy allowlist):
the first daily run in GitHub Actions produces the evidence, recorded in
``data/state/bcn_leychile_watch.json`` (``probe``) and ``data/source_health.json``.

Behaviour
* Runs only inside the real engine (``live_lanes.enabled("RADAR_LEYCHILE")``),
  never inside the test suite.
* At most one lane pass per Chile day (the daily workflow runs four times):
  at most one request per norm per day, plus robots.txt; the endpoint probe
  may try one fallback host once until an endpoint is verified.
* robots.txt honoured through ``RobotsGate`` for the first URL and for every
  redirect target, before it is requested. 429 stops the pass.
* Probe = the first request (``probe_norm``). If robots denies it, or it
  fails, or the response does not parse into the expected identity, nothing
  else is requested and the source records an error.
* The first verified version of a norm is a baseline (no change signal). A
  later, newer ``fechaVersion`` creates a candidate "Se modificó <norma>
  (versión vigente desde <fecha>)" with status ``held_for_review``. Nothing
  is published: the CLAUDE.md auto-publish exceptions cover only SIS/SUSESO
  circulars, the weekly insight and statistics fichas. ``discover`` returns
  no queue items, so no row can reach the history or the feed.
* idNorma only from a verified response (never guessed); otherwise the norm
  stays ``unresolved`` with its cause.
"""
from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit

from .official_open import USER_AGENT, RobotsGate, chile_today, fetch as open_fetch, fold, official
from .processing import RejectedProcessing

SLUG = "bcn_leychile_watch"
SOURCE_NAME = "Biblioteca del Congreso Nacional · LeyChile (vigilancia de normas clave)"
HOSTS = ("www.leychile.cl", "leychile.cl", "www.bcn.cl", "bcn.cl", "nuevo.leychile.cl")
# Documented path first (2009 doc, over HTTPS); the second is the current BCN host. Only the
# probe tries the second, once, and only while no endpoint has been verified.
ENDPOINTS = ("https://www.leychile.cl/Consulta/obtxml", "https://www.bcn.cl/leychile/Consulta/obtxml")
NORM_PAGE = "https://www.bcn.cl/leychile/navegar"
CONFIG_PATH = Path("config/bcn_leychile_watch.json")
STATE_PATH = Path("data/state/bcn_leychile_watch.json")
TERMS_POLICY = "metadata_and_link_only_license_unresolved"
TIMEOUT = 20
MAX_NORM_BYTES = 25 * 1024 * 1024
MAX_SEARCH_BYTES = 2 * 1024 * 1024
MAX_RUNS_KEPT = 60
REVIEW_BASIS = ("CLAUDE.md §3: las excepciones de autopublicación cubren sólo circulares SIS/SUSESO, "
                "el insight semanal y las fichas estadísticas; esta fuente queda retenida para revisión.")


def live_lane_enabled(env=None):
    from .live_lanes import enabled
    return enabled("RADAR_LEYCHILE", env)


def load_config(root=None):
    path = (Path(root) / CONFIG_PATH) if root else CONFIG_PATH
    return json.loads(path.read_text(encoding="utf-8"))


def norm_url(endpoint, *, id_norma=None, id_ley=None):
    if id_norma:
        return f"{endpoint}?{urlencode({'opt': 7, 'idNorma': id_norma})}"
    return f"{endpoint}?{urlencode({'opt': 7, 'idLey': id_ley})}"


def search_url(endpoint, cadena):
    return f"{endpoint}?opt=61&cadena={quote(cadena, safe='')}"


def norm_page(id_norma=None, id_ley=None):
    """Public LeyChile page (constructed, not fetched by this module)."""
    if id_norma:
        return f"{NORM_PAGE}?idNorma={quote(str(id_norma), safe='')}"
    return f"{NORM_PAGE}?idLey={quote(str(id_ley), safe='')}" if id_ley else None


def _now():
    return datetime.now(timezone.utc).isoformat()


def _local(tag):
    return str(tag).rsplit("}", 1)[-1]


def _attr(node, *names):
    if node is None:
        return None
    wanted = {n.casefold() for n in names}
    for key, value in node.attrib.items():
        if _local(key).casefold() in wanted and str(value).strip():
            return str(value).strip()
    return None


def _text(node):
    return " ".join("".join(node.itertext()).split()) if node is not None else ""


def _first(root, *names):
    wanted = {n.casefold() for n in names}
    for node in root.iter():
        if _local(node.tag).casefold() in wanted:
            return node
    return None


def iso_day(value):
    """'2024-05-31', '2024-05-31T00:00:00' or '31-05-2024' -> '2024-05-31'; else None."""
    text = str(value or "").strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        y, mo, d = m.groups()
    else:
        m = re.match(r"(\d{2})[-/](\d{2})[-/](\d{4})$", text)
        if not m:
            return None
        d, mo, y = m.groups()
    try:
        return datetime(int(y), int(mo), int(d)).date().isoformat()
    except ValueError:
        return None


def _safe_xml(body, limit):
    if len(body) > limit:
        raise ValueError("response too large")
    head = body[:4096]
    if b"<!DOCTYPE" in head or b"<!ENTITY" in head:
        raise ValueError("DTD/entities not accepted")
    try:
        return ET.fromstring(body)
    except ET.ParseError as exc:
        raise ValueError(f"not XML: {exc}") from exc


def parse_norm(body):
    """Metadata of a norm XML (opt=7). Raises ValueError on a structure change.

    Only identifying metadata leaves this function: the body text is never kept.
    """
    root = _safe_xml(body, MAX_NORM_BYTES)
    if _local(root.tag) != "Norma":
        raise ValueError(f"unexpected root <{_local(root.tag)}>")
    ident = _first(root, "Identificador")
    tipos = [(_text(_first(tn, "Tipo")), _text(_first(tn, "Numero")))
             for tn in root.iter() if _local(tn.tag) == "TipoNumero"]
    organismos = [_text(o) for o in root.iter() if _local(o.tag) == "Organismo" and _text(o)]
    part_versions = sorted({d for n in root.iter() if n is not root
                            for d in [iso_day(_attr(n, "fechaVersion"))] if d})
    root_version = iso_day(_attr(root, "fechaVersion"))
    meta = {
        "id_norma": _attr(root, "normaId", "idNorma"),
        "fecha_version": root_version or (part_versions[-1] if part_versions else None),
        "fecha_version_basis": "root@fechaVersion" if root_version else ("max(part@fechaVersion)" if part_versions else None),
        "max_part_fecha_version": part_versions[-1] if part_versions else None,
        "fecha_publicacion": iso_day(_attr(ident, "fechaPublicacion") or _attr(root, "fechaPublicacion")),
        "fecha_promulgacion": iso_day(_attr(ident, "fechaPromulgacion") or _attr(root, "fechaPromulgacion")),
        "tipos_numeros": [{"tipo": t, "numero": n} for t, n in tipos if t or n],
        "organismos": organismos[:5],
        "titulo": _text(_first(root, "TituloNorma"))[:500] or None,
        "derogado": _attr(root, "derogado"),
        "parts_with_version": len(part_versions),
    }
    if not meta["fecha_version"]:
        raise ValueError("norm without fechaVersion")
    if not meta["tipos_numeros"]:
        raise ValueError("norm without TipoNumero")
    return meta


_SEARCH_ID = ("idnorma", "normaid", "id_norma")
_SEARCH_FIELDS = {"tipo": ("tipo", "tiponorma", "tipo_norma"), "numero": ("numero", "numeronorma", "numero_norma"),
                  "titulo": ("titulo", "titulonorma", "nombre"), "organismo": ("organismo",),
                  "fecha_publicacion": ("fechapublicacion", "fecha_publicacion"),
                  "fecha_promulgacion": ("fechapromulgacion", "fecha_promulgacion")}


def parse_search(body):
    """Candidate records of an opt=61 search. Tolerant: the schema is not documented.

    A record is any element that carries an idNorma (child element or
    attribute); its fields come from its own descendants. Unknown shapes give [].
    """
    root = _safe_xml(body, MAX_SEARCH_BYTES)
    out = []
    for node in root.iter():
        nid = _attr(node, *_SEARCH_ID)
        if not nid:
            child = next((c for c in node if _local(c.tag).casefold() in _SEARCH_ID and _text(c)), None)
            nid = _text(child) if child is not None else None
        if not nid or not re.fullmatch(r"\d{1,10}", nid):
            continue
        row = {"id_norma": nid}
        for field, names in _SEARCH_FIELDS.items():
            found = _first(node, *names)
            value = _text(found) if found is not None and found is not node else _attr(node, *names)
            if value:
                row[field] = value[:300]
        out.append(row)
    unique = {}
    for row in out:
        unique.setdefault(row["id_norma"], row)
    return list(unique.values())[:20]


_TIPO_ALIASES = {"ley": {"ley"}, "decreto con fuerza de ley": {"decreto con fuerza de ley", "dfl", "d.f.l."},
                 "decreto": {"decreto", "decreto supremo", "ds", "d.s."}}


def _digits(value):
    digits = re.sub(r"\D", "", str(value or ""))
    return digits.lstrip("0") or ("0" if digits else "")


def _tipo_ok(expected, found):
    found = fold(found).casefold().strip()
    return found in _TIPO_ALIASES.get(expected, {expected})


def identity_check(spec, meta):
    """Problems ([] = match) between the configured identity and a parsed response."""
    problems = []
    pairs = meta.get("tipos_numeros") or [{"tipo": meta.get("tipo"), "numero": meta.get("numero")}]
    if not any(_tipo_ok(spec["tipo"], p.get("tipo")) and _digits(p.get("numero")) == _digits(spec["numero"])
               for p in pairs):
        problems.append("tipo_numero")
    if spec.get("organismo"):
        orgs = meta.get("organismos") or ([meta["organismo"]] if meta.get("organismo") else [])
        if not any(spec["organismo"] in fold(o).casefold() for o in orgs):
            problems.append("organismo")
    if spec["tipo"] != "ley" and spec.get("anio"):
        # DFL and decree numbers repeat across years and ministries: the year must match too.
        years = {(iso_day(meta.get(k)) or "")[:4] for k in ("fecha_promulgacion", "fecha_publicacion")}
        if str(spec["anio"]) not in years:
            problems.append("anio")
    return problems


def _redact(url):
    p = urlsplit(url or "")
    return f"{p.scheme}://{p.hostname}{p.path}" + (f"?{p.query}" if p.query else "") if p.hostname else None


class LeyChileWatchScout:
    """Daily, no-AI watch of key norms in LeyChile. Returns no queue items (nothing publishes)."""
    slug = SLUG

    def __init__(self, state_path=None, config=None, fetch_fn=None, robots_fetch=None, robots=None,
                 today=None, enabled=None, now=None, config_path=None):
        self.state_path = Path(state_path) if state_path else None
        self.config = config
        self.config_path = Path(config_path) if config_path else None
        self.fetch_fn = fetch_fn
        self.robots_fetch = robots_fetch
        self.robots = robots
        self.today = today
        self.enabled = enabled
        self.now = now or _now
        self.diagnostics = {}
        # Per-norm problems stay here (health "degraded"); the engine reads discovery_errors as a
        # source-level failure, which a single unreachable norm is not.
        self.discovery_errors = []
        self.norm_errors = []
        self.discovery_audit = []
        self.requests = []

    # --- network ---------------------------------------------------------------------

    def _gate(self):
        if self.robots is None:
            fetcher = self.robots_fetch or (lambda url: open_fetch(url, HOSTS, timeout=TIMEOUT, accept="text/plain"))
            self.robots = RobotsGate(fetcher, USER_AGENT)
        return self.robots

    def _allowed(self, url):
        gate = self._gate()
        return getattr(gate, "allowed", gate)(url)

    def _robots_status(self):
        gate = self.robots
        return dict(getattr(gate, "status", {}) or {})

    def _get(self, url, limit):
        """One request: robots first (also for each redirect target); returns (body, capture)."""
        if not official(url, HOSTS):
            raise ValueError("URL must be official HTTPS")
        if not self._allowed(url):
            raise PermissionError(f"robots_disallowed: {urlsplit(url).hostname}{urlsplit(url).path}")
        self.requests.append(url)
        if self.fetch_fn is not None:
            return self.fetch_fn(url)
        return _robots_aware_fetch(url, self._allowed, limit)

    # --- state -----------------------------------------------------------------------

    def _load_state(self):
        if self.state_path and self.state_path.exists():
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            if not isinstance(state, dict):
                raise ValueError("invalid LeyChile watch state")
            return state
        return {}

    def _save_state(self, state):
        if self.state_path is None:
            return
        from .pending_queue import atomic_json
        atomic_json(self.state_path, state)

    # --- run -------------------------------------------------------------------------

    def discover(self):
        enabled = live_lane_enabled() if self.enabled is None else self.enabled
        if not enabled:
            self.diagnostics = {"status": "not_run_outside_engine_runtime", "partial_failure": False}
            return []
        config = self.config or (json.loads(self.config_path.read_text(encoding="utf-8")) if self.config_path
                                 else load_config())
        today = (self.today or chile_today()).isoformat()
        state = self._load_state()
        state.setdefault("schema_version", 1)
        state.update(source=SLUG, license_note=config.get("license_note"), terms_policy=TERMS_POLICY)
        state.setdefault("norms", {})
        state.setdefault("candidates", [])
        if state.get("last_run_day") == today:
            # At most one pass per Chile day: no network on the later daily runs.
            probe = state.get("probe") or {}
            self.diagnostics = self._summary(state, status="skipped_already_checked_today")
            if not probe.get("passed"):
                raise RuntimeError(f"leychile_probe_failed_today (sin reintento hasta mañana): {probe.get('failure')}")
            return []
        state["last_run_day"] = today
        run = {"day": today, "at": self.now(), "requests": 0, "baselines": [], "changes": [], "errors": []}
        try:
            self._run(config, state, run, today)
        finally:
            run["requests"] = len(self.requests)
            run["robots"] = self._robots_status()
            state["runs"] = (state.get("runs") or [])[-(MAX_RUNS_KEPT - 1):] + [run]
            self._save_state(state)
            self.diagnostics = self._summary(state, status=run.get("status") or "error", run=run)
        return []

    def _run(self, config, state, run, today):
        norms = {n["key"]: n for n in config["norms"]}
        probe_key = config.get("probe_norm") or next(iter(norms))
        order = [probe_key] + [k for k in norms if k != probe_key]
        probe_passed = bool((state.get("probe") or {}).get("passed") and (state.get("endpoint") or {}).get("base"))
        for key in order:
            spec, entry = norms[key], state["norms"].setdefault(key, {})
            entry.update(label=spec["label"], tipo=spec["tipo"], numero=spec["numero"])
            is_probe = not probe_passed
            try:
                outcome = self._check(spec, entry, state, today, probe=is_probe)
            except PermissionError as exc:
                # robots denial (or 429 treated as stop): fail closed, request nothing else.
                self._fail(state, run, key, exc, is_probe)
                msg = str(exc)
                run["status"] = ("robots_unavailable" if "robots_unavailable" in msg else
                                 "robots_disallowed" if "robots_disallowed" in msg else "stopped")
                raise
            except Exception as exc:
                self._fail(state, run, key, exc, is_probe)
                if is_probe:
                    run["status"] = "probe_failed"
                    raise
                if isinstance(exc, HTTPError) and exc.code == 429:
                    run["status"] = "rate_limited"
                    raise PermissionError("rate_limited_429: pass stopped") from exc
                continue
            if outcome.get("skipped"):
                if is_probe:
                    run["status"] = "probe_pending"  # inconsistent state: never a second request today
                    break
                continue
            if is_probe:
                if outcome.get("probe_passed"):
                    probe_passed = True
                else:
                    run["status"] = "probe_failed"
                    failure = (state.get("probe") or {}).get("failure")
                    run["errors"].append({"norm": key, "error": failure, "http_status": None})
                    raise RuntimeError(f"leychile_probe_failed: {failure}")
            if outcome.get("baseline"):
                run["baselines"].append(key)
            if outcome.get("change"):
                run["changes"].append(key)
        run.setdefault("status", "ok_partial" if run["errors"] else "ok")

    def _fail(self, state, run, key, exc, is_probe):
        cause = f"{type(exc).__name__}: {exc}"[:300]
        http = getattr(exc, "code", None) if isinstance(exc, HTTPError) else None
        entry = state["norms"].setdefault(key, {})
        entry.update(last_error=cause, last_http_status=http, last_checked_at=self.now())
        run["errors"].append({"norm": key, "error": cause, "http_status": http})
        self.norm_errors.append(f"{key}: {cause}"[:200])
        if is_probe:
            state["probe"] = {"passed": False, "at": self.now(), "norm": key, "failure": cause, "http_status": http,
                              "robots": self._robots_status(), "requests": list(map(_redact, self.requests))}

    def _check(self, spec, entry, state, today, *, probe):
        if entry.get("last_request_day") == today:
            return {"skipped": True}
        id_norma = entry.get("id_norma") or spec.get("id_norma")
        id_ley = (spec.get("lookup") or {}).get("id_ley")
        search = (spec.get("lookup") or {}).get("search")
        endpoint = (state.get("endpoint") or {}).get("base")
        if not id_norma and not id_ley:
            if not search:
                entry.update(status="unresolved", unresolved_reason="no_lookup_configured")
                return {}
            if probe:
                # The probe must be a norm fetch; a search-only norm waits for a verified endpoint.
                raise ValueError("probe norm needs id_ley or a verified id_norma")
            return self._resolve_by_search(spec, entry, endpoint, search, today)
        endpoints = [endpoint] if endpoint else list(ENDPOINTS)
        for base in endpoints:
            url = norm_url(base, id_norma=id_norma, id_ley=None if id_norma else id_ley)
            entry["last_request_day"] = today
            try:
                body, capture = self._get(url, MAX_NORM_BYTES)
            except HTTPError as exc:
                # Only the unverified-endpoint probe may try the next documented host (404/410 only).
                if probe and not endpoint and exc.code in (404, 410) and base != endpoints[-1]:
                    continue
                raise
            meta = parse_norm(body)
            break
        problems = identity_check(spec, meta)
        if id_norma and meta.get("id_norma") and str(meta["id_norma"]) != str(id_norma):
            problems.append("id_norma")
        capture = capture or {}
        evidence = {"url": _redact(url), "final_url": _redact(capture.get("final_url") or url),
                    "http_status": capture.get("http_status", 200), "sha256": capture.get("sha256"),
                    "bytes": capture.get("bytes"), "captured_at": capture.get("captured_at") or self.now()}
        entry.update(last_checked_at=self.now(), last_http_status=evidence["http_status"],
                     last_sha256=evidence["sha256"], last_error=None)
        if probe:
            state["probe"] = {"passed": not problems, "at": self.now(), "norm": spec["key"], "endpoint": base,
                              "robots": self._robots_status(), "evidence": evidence,
                              "parsed_fields": {k: meta.get(k) for k in ("id_norma", "fecha_version", "fecha_version_basis",
                                                                         "fecha_publicacion", "tipos_numeros",
                                                                         "organismos", "titulo")},
                              "identity_problems": problems,
                              "failure": f"identity_mismatch: {','.join(problems)}" if problems else None}
            if not problems:
                state["endpoint"] = {"base": base, "verified_at": self.now(), "verified_by": spec["key"]}
        if problems:
            entry.update(status="identity_mismatch", identity_problems=problems)
            self.norm_errors.append(f"{spec['key']}: identity_mismatch {problems}")
            return {"probe_passed": False}
        resolved_id = meta.get("id_norma") or id_norma
        if resolved_id and not entry.get("id_norma"):
            entry.update(id_norma=resolved_id, resolution_basis=("opt7_idLey_response_normaId" if not id_norma
                                                                  else entry.get("resolution_basis") or "config_id_verified_by_identity"),
                         resolved_at=self.now())
        previous = entry.get("fecha_version")
        current = meta["fecha_version"]
        link = norm_page(resolved_id, None if resolved_id else id_ley)
        entry.update(status="watching", titulo=meta.get("titulo"), organismos=meta.get("organismos"),
                     fecha_publicacion=meta.get("fecha_publicacion"), fecha_promulgacion=meta.get("fecha_promulgacion"),
                     max_part_fecha_version=meta.get("max_part_fecha_version"),
                     fecha_version_basis=meta.get("fecha_version_basis"), derogado=meta.get("derogado"),
                     link=link, link_basis="constructed_leychile_navegar_not_fetched", identity_problems=[],
                     unresolved_reason=None)
        outcome = {"probe_passed": True}
        if previous is None:
            entry.update(fecha_version=current, baseline_established_at=self.now(), baseline_evidence=evidence)
            outcome["baseline"] = True
        elif current > previous:
            entry.update(fecha_version=current, previous_fecha_version=previous, changed_at=self.now())
            self._candidate(spec, entry, state, previous, current, link, evidence)
            outcome["change"] = True
        elif current < previous:
            entry["version_anomaly"] = {"observed": current, "stored": previous, "at": self.now()}
            self.norm_errors.append(f"{spec['key']}: fechaVersion went back {previous} -> {current}")
        return outcome

    def _resolve_by_search(self, spec, entry, endpoint, cadena, today):
        if not endpoint:
            entry.update(status="unresolved", unresolved_reason="awaiting_verified_endpoint")
            return {}
        url = search_url(endpoint, cadena)
        entry["last_request_day"] = today
        body, capture = self._get(url, MAX_SEARCH_BYTES)
        candidates = parse_search(body)
        matches = [c for c in candidates if not identity_check(spec, c)]
        entry.update(last_checked_at=self.now(), last_error=None,
                     search={"url": _redact(url), "at": self.now(), "sha256": (capture or {}).get("sha256"),
                             "candidates": candidates[:10], "matches": [m["id_norma"] for m in matches]})
        if len(matches) == 1:
            entry.update(id_norma=matches[0]["id_norma"], resolution_basis="opt61_search_unique_identity_match",
                         resolved_at=self.now(), status="resolved_pending_first_fetch", unresolved_reason=None)
        else:
            entry.update(status="unresolved", unresolved_reason=("search_no_parsable_candidates" if not candidates else
                                                                 "search_no_identity_match" if not matches else
                                                                 "search_ambiguous_identity_match"))
        return {}

    def _candidate(self, spec, entry, state, previous, current, link, evidence):
        cid = f"{spec['key']}:{current}"
        if any(c.get("id") == cid for c in state["candidates"]):
            return
        when = f"{current[8:10]}-{current[5:7]}-{current[:4]}"
        state["candidates"].append({
            "id": cid, "status": "held_for_review", "published": False, "review_basis": REVIEW_BASIS,
            "title": f"Se modificó {spec['label']} (versión vigente desde {when})",
            "norm_key": spec["key"], "id_norma": entry.get("id_norma"), "tipo": spec["tipo"], "numero": spec["numero"],
            "titulo_oficial": entry.get("titulo"), "organismos": entry.get("organismos"),
            "fecha_publicacion": entry.get("fecha_publicacion"), "previous_fecha_version": previous,
            "fecha_version": current, "link": link, "evidence": evidence, "detected_at": self.now(),
            "ai_used": False, "terms_policy": TERMS_POLICY})

    def _summary(self, state, *, status, run=None):
        norms = state.get("norms") or {}
        probe = state.get("probe") or {}
        return {
            "status": status, "probe_status": ("passed" if probe.get("passed") else
                                               f"failed: {probe.get('failure')}" if probe else "not_run"),
            "probe": probe, "endpoint": (state.get("endpoint") or {}).get("base"),
            "requests_this_run": len(self.requests), "requested_urls": [_redact(u) for u in self.requests],
            "robots": self._robots_status(),
            "norms": {k: {f: v.get(f) for f in ("status", "id_norma", "fecha_version", "last_http_status",
                                               "unresolved_reason", "last_error")} for k, v in norms.items()},
            "watching": sorted(k for k, v in norms.items() if v.get("status") == "watching"),
            "unresolved": sorted(k for k, v in norms.items() if v.get("status") in ("unresolved", "resolved_pending_first_fetch")),
            "baselines_this_run": (run or {}).get("baselines", []), "changes_this_run": (run or {}).get("changes", []),
            "candidates_held_for_review": sum(c.get("status") == "held_for_review" for c in state.get("candidates") or []),
            "published": 0, "publication_policy": "held_for_review_never_auto_published", "ai_used": False,
            "partial_failure": bool((run or {}).get("errors")) or bool(self.norm_errors),
            "norm_errors": self.norm_errors[:10],
            "terms_policy": TERMS_POLICY,
        }


def _robots_aware_fetch(url, allowed, max_bytes):
    """Verified-TLS GET; every redirect target must be official and allowed by robots.txt first."""
    from urllib.request import HTTPRedirectHandler, Request, build_opener

    class _Gate(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if not official(newurl, HOSTS):
                raise ValueError("redirect left the official HTTPS hosts")
            if not allowed(newurl):
                raise PermissionError(f"robots_disallowed: redirect to {urlsplit(newurl).hostname}{urlsplit(newurl).path}")
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/xml,text/xml;q=0.9"})
    with build_opener(_Gate()).open(request, timeout=TIMEOUT) as response:
        final = response.geturl()
        if not official(final, HOSTS):
            raise ValueError("response left the official HTTPS hosts")
        status = getattr(response, "status", None)
        content_type = response.headers.get("Content-Type") if hasattr(response, "headers") else None
        body = response.read(max_bytes + 1)
    if len(body) > max_bytes:
        raise ValueError("response exceeds the byte limit")
    return body, {"url": url, "final_url": final, "http_status": status, "content_type": content_type,
                  "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body), "tls_verified": True,
                  "captured_at": _now()}


def process_leychile_watch(raw, cfg):
    """Defensive: the watch never queues items; anything that arrives is rejected, never published."""
    raise RejectedProcessing("leychile_watch_held_for_review_never_published")
