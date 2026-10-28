"""Rights policy for paywalled press (Dirección 28-oct-2026).

Only what a reader sees on the publisher's page without an account may be
stored in public outputs or used for analysis: title, public lead/teaser as
published, date and link. Anything beyond that is replaced by a receipt that
proves what was removed (sha256 + length) without republishing it.
"""
from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from .paths import project_root

POLICY_PATH = Path("config/paywalled_press.json")
PAYWALL_LABEL = "Contenido para suscriptores"
_REDACTED_AT = "2026-10-28"
_REASON_KEYS = ("reason", "analysis_reason")


@lru_cache(maxsize=1)
def load_policy(path: str | None = None) -> dict:
    target = Path(path) if path else project_root() / POLICY_PATH
    return json.loads(target.read_text(encoding="utf-8"))


def _host(url: str) -> str:
    try:
        return (urlsplit(str(url or "").strip()).hostname or "").lower()
    except ValueError:
        return ""


def _article_flagged(metadata: dict | None) -> bool:
    md = metadata or {}
    if md.get("isAccessibleForFree") in (False, "false", "False") or md.get("is_accessible_for_free") is False:
        return True
    if md.get("publisher_paywall") is True or str(md.get("content_tier") or "").lower() == "locked":
        return True
    return False


def paywall_policy(url: str, metadata: dict | None = None, source_slug: str | None = None) -> dict | None:
    """Return the matching paywalled-source rule, or None for open content."""
    host = _host(url)
    path = urlsplit(str(url or "").strip()).path if host else ""
    for rule in load_policy()["sources"]:
        if host not in rule["hosts"]:
            continue
        if rule["scope"] == "host":
            return rule
        if any(path.startswith(prefix) for prefix in rule.get("path_prefixes", [])) or _article_flagged(metadata):
            return rule
    return None


def is_paywalled(url: str, metadata: dict | None = None) -> bool:
    return paywall_policy(url, metadata) is not None


def receipt(value, field: str, reason: str = "paywalled_press_public_teaser_only") -> dict:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    return {"field": field, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "characters": len(text), "reason": reason, "redacted_at": _REDACTED_AT}


def clean_teaser(text) -> str:
    return " ".join(str(text or "").split())


def public_teaser(candidate, body: str | None = None, title: str | None = None) -> str:
    """Accept a publisher lead only if it is a lead, not a body excerpt.

    Parsers fall back to ``body[:1800]`` when no description exists; such a
    fallback is paywalled body, never a teaser.
    """
    teaser = clean_teaser(candidate)
    limit = int(load_policy()["teaser_max_characters"])
    if not teaser or len(teaser) > limit:
        return ""
    flat_body = clean_teaser(body)
    if flat_body and len(flat_body) > len(teaser) + 40 and flat_body.startswith(teaser[:120]):
        return ""
    if title and clean_teaser(title).casefold() == teaser.casefold():
        return ""
    return teaser


def teaser_from_raw(raw_like: dict) -> str:
    """Public lead from a stored queue ``raw`` dict (DF og:description, LT description)."""
    md = raw_like.get("metadata") or {}
    body = md.get("page_text") or ""
    title = md.get("article_title") or raw_like.get("title")
    for candidate in (md.get("public_teaser"), md.get("description"), md.get("og_description"), raw_like.get("raw_text")):
        teaser = public_teaser(candidate, body, title)
        if teaser:
            return teaser
    # A DF listing card title carries "<headline> <teaser>"; keep the visible card text.
    listing_title, headline = clean_teaser(raw_like.get("title")), clean_teaser(md.get("article_title"))
    if headline and listing_title.startswith(headline) and len(listing_title) > len(headline) + 20:
        return public_teaser(listing_title[len(headline):], body, headline)
    return ""


def restrict_raw_to_public(raw) -> object:
    """Mutate a RawItem so only public text remains available for analysis/storage."""
    rule = paywall_policy(raw.url, raw.metadata, raw.source_slug)
    if not rule:
        return raw
    md = raw.metadata
    body = md.get("page_text") or ""
    teaser = public_teaser(raw.raw_text, body, md.get("article_title") or raw.title) or teaser_from_raw(
        {"title": raw.title, "raw_text": raw.raw_text, "metadata": md})
    receipts = list(md.get("rights_redactions") or [])
    if body and body != teaser:
        receipts.append(receipt(body, "page_text"))
    md.update(page_text=teaser, public_teaser=teaser, paywalled=True, access_policy=load_policy()["policy"],
              paywall_source=rule["id"], rights_redactions=receipts)
    raw.raw_text = teaser
    return raw


_GENERIC = re.compile(r"^(isapre|cl[ií]nica|hospital|laboratorio|mutual|caja)\s+", re.I)


def _named_in(name, visible: str) -> bool:
    name = clean_teaser(name).casefold()
    return bool(name) and (name in visible or _GENERIC.sub("", name) in visible)


def redact_signal(row: dict, teaser: str | None = None) -> dict:
    """Public card for a paywalled piece: title, public lead, date, link; nothing else derived."""
    rule = paywall_policy(row.get("source_url"), row)
    if not rule or row.get("derived_from") == "editorial_story_group":
        # Alicanto syntheses cite several sources; their copy is reviewed separately.
        return row
    policy = load_policy()
    out = dict(row)
    teaser = clean_teaser(teaser if teaser is not None else out.get("public_teaser"))
    receipts = list(out.get("rights_redactions") or [])
    for key in policy["redacted_signal_fields"]:
        if out.get(key) not in (None, "", [], {}):
            receipts.append(receipt(out[key], key))
        out.pop(key, None)
    committee = out.get("editorial_committee")
    if isinstance(committee, dict):
        # Keep the committee verdict (publication contract); its copy becomes public-only.
        committee = dict(committee)
        for key in policy.get("redacted_committee_fields", []):
            value = committee.get(key)
            if value not in (None, "", [], {}) and value != (teaser if key == "what_happened" else out.get("title")):
                receipts.append(receipt(value, f"editorial_committee.{key}"))
        committee.update(what_happened=teaser, why_it_matters="", public_title=out.get("title"),
                         uncertainties=[], analysis_basis="public_teaser_only")
        out["editorial_committee"] = committee
    previous_what = out.get("what_happened")
    if previous_what and clean_teaser(previous_what) != teaser and not str(previous_what).startswith(PAYWALL_LABEL):
        receipts.append(receipt(previous_what, "what_happened"))
    assessment = out.get("editorial_assessment")
    if isinstance(assessment, dict) and any(assessment.get(k) for k in _REASON_KEYS):
        for k in _REASON_KEYS:
            if assessment.get(k):
                receipts.append(receipt(assessment[k], f"editorial_assessment.{k}"))
        out["editorial_assessment"] = {k: v for k, v in assessment.items() if k not in _REASON_KEYS}
    # Entity refs inferred from the locked body are not public evidence.
    visible = f"{out.get('title') or ''} {teaser}".casefold()
    refs = [r for r in out.get("entity_refs") or [] if isinstance(r, dict) and _named_in(r.get("name"), visible)]
    if out.get("entity_refs") and refs != out.get("entity_refs"):
        out["entity_refs"] = refs
    # De-duplicate receipts deterministically (re-running the migration is a no-op).
    seen, unique = set(), []
    for r in receipts:
        key = (r["field"], r["sha256"])
        if key not in seen:
            seen.add(key)
            unique.append(r)
    out.update(
        what_happened=teaser or f"{PAYWALL_LABEL} de {rule['name']}: sólo el titular es público.",
        why_it_matters="",
        card_why_optional=True,
        public_teaser=teaser,
        paywalled=True,
        paywall_label=f"{PAYWALL_LABEL} · {rule['name']}",
        access_policy=policy["policy"],
        paywall_source=rule["id"],
        analysis_basis="public_teaser_only",
        rights_redactions=unique,
    )
    if out.get("article_content_source"):
        out["article_content_source"] = "public_teaser"
    return out


def excess_fields(row: dict) -> list[str]:
    """Names of fields that a paywalled public row must not carry (for validators/tests)."""
    if not is_paywalled(row.get("source_url"), row) or row.get("derived_from") == "editorial_story_group":
        return []
    policy = load_policy()
    bad = [k for k in policy["redacted_signal_fields"] if row.get(k) not in (None, "", [], {})]
    if row.get("why_it_matters"):
        bad.append("why_it_matters")
    committee = row.get("editorial_committee")
    if isinstance(committee, dict) and (committee.get("why_it_matters")
                                        or clean_teaser(committee.get("what_happened")) != clean_teaser(row.get("public_teaser"))):
        bad.append("editorial_committee")
    teaser = clean_teaser(row.get("public_teaser"))
    what = clean_teaser(row.get("what_happened"))
    if what and teaser and what != teaser:
        bad.append("what_happened")
    if what and not teaser and not what.startswith(PAYWALL_LABEL):
        bad.append("what_happened")
    if row.get("paywalled") is not True:
        bad.append("paywalled")
    if isinstance(row.get("editorial_assessment"), dict) and any(row["editorial_assessment"].get(k) for k in _REASON_KEYS):
        bad.append("editorial_assessment.reason")
    return bad


_LONG = 600


def purge_raw_metadata(raw_like: dict) -> bool:
    """Redact stored paywalled body/derived text from a queue ``raw`` dict in place."""
    url = raw_like.get("url") or ""
    md = raw_like.get("metadata")
    if not isinstance(md, dict) or not paywall_policy(url, md):
        return False
    policy = load_policy()
    teaser = teaser_from_raw(raw_like)
    receipts = list(md.get("rights_redactions") or [])
    changed = False
    for key in policy["redacted_body_fields"]:
        value = md.get(key)
        if value in (None, "", [], {}) or (isinstance(value, str) and clean_teaser(value) == teaser):
            continue
        receipts.append(receipt(value, f"metadata.{key}"))
        md[key] = teaser if key == "page_text" else None
        changed = True
    assessment = md.get("editorial_assessment")
    if isinstance(assessment, dict) and any(assessment.get(k) for k in _REASON_KEYS):
        for k in _REASON_KEYS:
            if assessment.get(k):
                receipts.append(receipt(assessment[k], f"metadata.editorial_assessment.{k}"))
        md["editorial_assessment"] = {k: v for k, v in assessment.items() if k not in _REASON_KEYS}
        changed = True
    raw_text = raw_like.get("raw_text")
    if raw_text and clean_teaser(raw_text) != teaser:
        receipts.append(receipt(raw_text, "raw_text"))
        raw_like["raw_text"] = teaser
        changed = True
    if changed or md.get("paywalled") is not True:
        seen, unique = set(), []
        for r in receipts:
            if (r["field"], r["sha256"]) not in seen:
                seen.add((r["field"], r["sha256"]))
                unique.append(r)
        md.update(public_teaser=teaser, paywalled=True, access_policy=policy["policy"], rights_redactions=unique)
        changed = True
    return changed


def purge_long_text(node, url_hint: str | None = None, path: str = "") -> int:
    """Walk any JSON value and redact long text attached to a paywalled URL. Returns count."""
    count = 0
    if isinstance(node, dict):
        url = next((node[k] for k in ("url", "source_url", "canonical_url", "requested_url", "final_url")
                    if isinstance(node.get(k), str) and node.get(k)), url_hint)
        paywalled = bool(url) and is_paywalled(url, node)
        for key in list(node):
            value = node[key]
            if paywalled and isinstance(value, str) and len(value) > _LONG and not re.match(r"https?://", value):
                node[key] = {"redacted": True, **receipt(value, key)}
                count += 1
            else:
                count += purge_long_text(value, url, f"{path}.{key}")
    elif isinstance(node, list):
        for value in node:
            count += purge_long_text(value, url_hint, path)
    return count
