"""Source URL hygiene for "abrir fuente original" links (Dirección 28-oct-2026).

``normalize_source_url`` repairs what can be repaired deterministically
(whitespace, %20 tails, scheme/host variants, tracking parameters, fragments,
unencoded spaces/accents). ``source_url_problem`` names what cannot be
repaired; such a row shows no link instead of a broken one.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

TRACKING_PARAMS = re.compile(r"^(utm_[a-z_]+|fbclid|gclid|dclid|msclkid|mc_cid|mc_eid|_ga|_gl|igshid|ref_src)$", re.I)
_WS = re.compile(r"[\s ​﻿]+")

# Host aliases that serve the same site; the canonical host is what MINSAL links to.
HOST_ALIASES = {"minsal.cl": "www.minsal.cl", "df.cl": "www.df.cl", "latercera.com": "www.latercera.com"}

# Paths under www.minsal.cl that are not a specific publication. They are either
# navigation (listings/archives/search/feeds) or retired portal layouts that now
# 404 since the WordPress migration (/portal/url/). Legacy Drupal documents under
# /sites/default/files/ are NOT presumed dead: many still resolve. Such a link is
# withheld only when its row carries a verified failure (see
# ``verified_link_failure``), never on the path alone.
MINSAL_NON_ARTICLE = (
    (re.compile(r"^/?$"), "minsal_home"),
    (re.compile(r"^/(category|tag|author|page|feed|comments)(/|$)"), "minsal_listing"),
    (re.compile(r"^/\d{4}(/\d{2}(/\d{2})?)?/?$"), "minsal_date_archive"),
    (re.compile(r"^/(portal/url|portal/|noticias/|index\.php)"), "minsal_retired_path"),
    (re.compile(r"^/wp-(admin|json|login)"), "minsal_wp_internal"),
)


def _encode_path(path: str) -> str:
    # Decode once then re-encode, so "a b", "a%20b" and accented paths converge.
    # An encoded slash (%2F) is data inside one segment, not a separator: decoding
    # it would change the resource. Decode each segment separately and keep it.
    segments = re.split(r"(%2F)", path, flags=re.I)
    return "".join(seg.upper() if seg.upper() == "%2F" else quote(unquote(seg), safe="/:@!$&'()*+,;=-._~")
                   for seg in segments)


LEGACY_MINSAL_FILES = re.compile(r"^/sites/default/files/")


def verified_link_failure(row: dict | None) -> dict | None:
    """A recorded, verified failure of this row's source link (404/410 over verified TLS), or None.

    Shape (written by a link checker or a reviewed migration):
    ``{"url": ..., "http_status": 404, "checked_at": "...", "tls_verified": true}``.
    """
    check = (row or {}).get("source_link_check")
    if (isinstance(check, dict) and check.get("url") == (row or {}).get("source_url")
            and check.get("http_status") in (404, 410) and check.get("tls_verified") is True
            and isinstance(check.get("checked_at"), str) and check["checked_at"]):
        return check
    return None


def normalize_source_url(url) -> str | None:
    """Return a cleaned absolute https URL, or None when not repairable."""
    if not isinstance(url, str):
        return None
    value = _WS.sub(" ", url).strip()
    value = re.sub(r"(%20|%C2%A0|\+)+$", "", value, flags=re.I).strip()
    if not value:
        return None
    if value.startswith("//"):
        value = "https:" + value
    if re.match(r"^(www\.)?[a-z0-9.-]+\.(cl|com|org|gob\.cl)/", value, re.I):
        value = "https://" + value
    try:
        parts = urlsplit(value)
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        return None
    host = parts.hostname.lower().rstrip(".")
    host = HOST_ALIASES.get(host, host)
    if parts.port not in (None, 80, 443) or parts.username or parts.password:
        return None
    path = parts.path or "/"
    # "https://www.df.cl/https/www.df.cl/empresas/..." (scheme pasted into the path).
    nested = re.match(r"^/https?:?/+([a-z0-9.-]+)(/.*)$", path, re.I)
    if nested and HOST_ALIASES.get(nested.group(1).lower(), nested.group(1).lower()) == host:
        path = nested.group(2)
    path = _encode_path(path)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not TRACKING_PARAMS.match(k)]
    query_s = urlencode(query, doseq=True, quote_via=quote, safe="/:,=")
    return urlunsplit(("https", host, path, query_s, ""))


def source_url_problem(url) -> str | None:
    """Why a stored URL must not be shown as "fuente original"; None if it is fine."""
    if not isinstance(url, str) or not url.strip():
        return "missing"
    raw = url
    if raw != raw.strip() or _WS.search(raw):
        return "whitespace"
    if not re.match(r"^https://", raw):
        return "relative_or_non_https" if not raw.startswith("http://") else "insecure_http"
    try:
        parts = urlsplit(raw)
    except ValueError:
        return "unparseable"
    host = (parts.hostname or "").lower()
    if not host or "." not in host:
        return "bad_host"
    if host in HOST_ALIASES:
        return "non_canonical_host"
    if re.search(r"(%20|%C2%A0)$", raw, re.I):
        return "encoded_whitespace"
    if re.match(r"^/https?[:/]", parts.path) or re.search(r"/https?:?/+[a-z0-9.-]+\.[a-z]{2,}/", parts.path):
        return "nested_url_in_path"
    if any(TRACKING_PARAMS.match(k) for k, _ in parse_qsl(parts.query, keep_blank_values=True)):
        return "tracking_parameters"
    if parts.fragment:
        return "fragment"
    if "{{" in raw or "}}" in raw:
        return "template_placeholder"
    if host == "www.minsal.cl":
        if re.fullmatch(r"p=\d+", parts.query or ""):
            return "minsal_shortlink"
        if parts.query and parts.query.startswith("s="):
            return "minsal_search"
        for pattern, reason in MINSAL_NON_ARTICLE:
            if pattern.search(parts.path):
                return reason
    return None


def safe_source_url(url) -> str | None:
    """Repaired URL when it passes validation; otherwise None (render no link)."""
    fixed = normalize_source_url(url)
    if fixed and source_url_problem(fixed) is None:
        return fixed
    return None


# --- MINSAL specific ---------------------------------------------------------

def minsal_article_url(href, base: str = "https://www.minsal.cl/") -> str | None:
    """Normalise a link found on minsal.cl; None unless it is a publication URL.

    WordPress publications live at ``/<slug>/`` and uploaded documents under
    ``/wp-content/uploads/``. Listings, archives, ``?p=`` shortlinks and the
    retired Drupal/portal layouts are rejected.
    """
    from urllib.parse import urljoin

    if not isinstance(href, str):
        return None
    href = _WS.sub(" ", href).strip()
    if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
        return None
    fixed = normalize_source_url(urljoin(base, href))
    if not fixed or urlsplit(fixed).hostname != "www.minsal.cl":
        return None
    parts = urlsplit(fixed)
    if parts.query:
        return None
    path = parts.path
    if LEGACY_MINSAL_FILES.match(path):
        return None  # a legacy document, not a publication slug (the link itself may still be valid)
    if not path.startswith("/wp-content/uploads/") and not path.endswith("/"):
        path += "/"  # WordPress canonical slug form; avoids a redirect hop.
    fixed = urlunsplit(("https", "www.minsal.cl", path, "", ""))
    return fixed if source_url_problem(fixed) is None else None


# --- Public snapshot ---------------------------------------------------------

LINK_LISTS = ("source_documents", "additional_sources", "related_context", "source_alternatives",
              "supporting_sources", "sources", "related_reference_contexts")


def sanitize_card_links(card: dict) -> dict:
    """Public card whose every link opens; identity (``source_url``) is never rewritten.

    The UI opens ``source_link`` when present; ``source_link_status: invalid``
    means no "fuente original" link is rendered at all.
    """
    out = dict(card)
    url = out.get("source_url")
    problem = source_url_problem(url)
    if problem is None and verified_link_failure(out):
        problem = "verified_link_failure"  # e.g. a legacy /sites/default/files/ document confirmed 404
    out.pop("source_link", None)
    if problem is None:
        out.pop("source_link_status", None)
        out.pop("source_link_problem", None)
    else:
        fixed = None if problem == "verified_link_failure" else safe_source_url(url)
        if fixed:
            out.update(source_link=fixed, source_link_status="repaired", source_link_problem=problem)
        else:
            out.update(source_link_status="invalid", source_link_problem=problem)
    if out.get("primary_source_url") is not None and source_url_problem(out["primary_source_url"]):
        out["primary_source_url"] = safe_source_url(out["primary_source_url"])
    for key in LINK_LISTS:
        items = out.get(key)
        if not isinstance(items, list):
            continue
        kept = []
        for item in items:
            if isinstance(item, str):
                fixed = item if source_url_problem(item) is None else safe_source_url(item)
                if fixed:
                    kept.append(fixed)
            elif isinstance(item, dict) and "url" in item and item.get("url"):
                if source_url_problem(item["url"]) is None:
                    kept.append(item)
                else:
                    fixed = safe_source_url(item["url"])
                    if fixed:
                        kept.append({**item, "url": fixed})
                    elif key == "related_context":
                        kept.append({**item, "url": None, "verified": False})
            else:
                kept.append(item)
        out[key] = kept
    return out


def card_link_problems(card: dict) -> list[str]:
    """Every link the UI would render for this card that is malformed (validator)."""
    problems = []
    if card.get("source_link_status") != "invalid":
        link = card.get("source_link") or card.get("source_url")
        problem = source_url_problem(link)
        if problem:
            problems.append(f"source_url:{problem}:{link!r}")
    for key in LINK_LISTS:
        for item in card.get(key) or []:
            url = item if isinstance(item, str) else item.get("url") if isinstance(item, dict) else None
            if url is None:
                continue
            problem = source_url_problem(url)
            if problem:
                problems.append(f"{key}:{problem}:{url!r}")
    return problems
