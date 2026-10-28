"""Rights policy for paywalled press (Dirección 28-oct-2026).

Only what a reader sees on the publisher's page without an account may be
stored in public outputs or used for analysis: title, public lead/teaser as
published, date and link. Anything beyond that is replaced by a receipt that
proves what was removed (sha256 + length) without republishing it.

The public lead must come from an explicitly public element: og:description,
the meta/JSON-LD description, a lead element rendered before the lock marker,
or the publisher's listing card. Body text is never a lead, however short.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from .paths import project_root

POLICY_PATH = Path("config/paywalled_press.json")
FINGERPRINTS_PATH = Path("data/audits/paywalled_body_fingerprints_2026_10_28.json")
PAYWALL_LABEL = "Contenido para suscriptores"
_REDACTED_AT = "2026-10-28"
_REASON_KEYS = ("reason", "analysis_reason")
# Publisher text, as captured. Model outputs are Alicanto work product: they are
# kept internally (never displayed) and only scrubbed of verbatim body sentences.
BODY_KEYS = ("page_text", "body", "article_body", "articleBody", "description_full", "full_text", "text")
# Where a lead may come from. Anything else (raw_text, body[:1800]) is not a lead.
TEASER_SOURCES = {"og:description", "meta:description", "jsonld:description", "public_lead_element",
                  "df_listing_card", "legacy_description_verified"}
TITLE_ONLY = "title_only"


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
    overlap = md.get(OVERLAP_KEY)
    if isinstance(overlap, dict) and overlap.get("paywalled") is True:
        # Its body reproduces a known paywalled body (same piece re-filed under an open path).
        return True
    return False


# --- Per-article access flags (captured as booleans/tokens; never body text) --
OVERLAP_KEY = "paywall_overlap"
ACCESS_RECORD = "publisher_access"
# Lock elements La Tercera renders inside a locked article (observed in tests/fixtures/pulso_*).
# ``lt-paywall-slot`` is page chrome on almost every page: kept as evidence, never a flag.
_LOCK_ELEMENT = re.compile(r'(?:class|id)\s*=\s*"[^"]*?(?<![\w-])(article-body__teaser--locked|article-body__unlock-skeleton|'
                           r'article-body__amp-paywall|articleLock|article-lock|content--locked|paywall-content)(?![\w-])',
                           re.I)


def _flag_bool(value):
    if value is True or (isinstance(value, str) and value.strip().lower() == "true"):
        return True
    if value is False or (isinstance(value, str) and value.strip().lower() == "false"):
        return False
    return None


def publisher_access_flags(node, metas: dict | None, html: str | None) -> dict:
    """Small access flags from a captured page: JSON-LD, meta tags and lock elements.

    ``node`` is the URL-bound article/liveblog JSON-LD node (an embedded VideoObject's
    flag describes the video, not the article). Returns metadata to merge:
    ``publisher_access`` (evidence record), ``access_verified`` (True only when the
    page itself declares access: an explicit isAccessibleForFree, a locked hasPart,
    a content tier or a lock element) and the flags ``_article_flagged`` reads.
    """
    node = node if isinstance(node, dict) else {}
    metas = metas if isinstance(metas, dict) else {}
    free = _flag_bool(node.get("isAccessibleForFree"))
    parts = node.get("hasPart")
    parts = parts if isinstance(parts, list) else [parts] if isinstance(parts, dict) else []
    haspart_locked = any(isinstance(p, dict) and _flag_bool(p.get("isAccessibleForFree")) is False for p in parts)
    tier = next((str(v).strip().lower()[:24] for k, v in metas.items()
                 if isinstance(k, str) and k.lower().endswith("content_tier") and str(v or "").strip()), None)
    part_of = node.get("isPartOf")
    part_of = part_of if isinstance(part_of, list) else [part_of] if isinstance(part_of, dict) else []
    product = any(isinstance(p, dict) and ("Product" in (p.get("@type") if isinstance(p.get("@type"), list)
                                                          else [p.get("@type")]) or p.get("productID"))
                  for p in part_of)
    lock = sorted({m.lower() for m in _LOCK_ELEMENT.findall(html or "")})[:6]
    record = {"jsonld_isAccessibleForFree": free, "jsonld_haspart_locked": haspart_locked,
              "meta_content_tier": tier, "premium_marker": product or tier in ("locked", "premium"),
              "lock_element": bool(lock), "lock_element_classes": lock,
              "paywall_slot_present": "lt-paywall-slot" in (html or ""), "schema": 1}
    out = {ACCESS_RECORD: record,
           "access_verified": free is not None or haspart_locked or bool(lock) or tier is not None}
    if free is not None:
        out["isAccessibleForFree"] = free
    if haspart_locked or lock or (tier == "locked"):
        out["publisher_paywall"] = True
    if tier:
        out["content_tier"] = tier
    return out


def access_classification(url: str, metadata: dict | None = None) -> dict:
    """How a stored item's access was decided: {paywalled, basis, access_verified}.

    ``basis``: host | path_prefix | section | article_flag | sentence_overlap | open_path.
    ``access_verified`` is True only when the capture stored an explicit per-article
    access flag (``publisher_access_flags``); otherwise the path-based answer stands,
    unverified.
    """
    md = metadata if isinstance(metadata, dict) else {}
    host = _host(url)
    try:
        path = urlsplit(str(url or "").strip()).path if host else ""
    except ValueError:
        path = ""
    verified = md.get("access_verified") is True
    for rule in load_policy()["sources"]:
        if host not in rule["hosts"]:
            continue
        if rule["scope"] == "host":
            return {"paywalled": True, "basis": "host", "access_verified": True}
        if any(path.startswith(p) for p in rule.get("path_prefixes", [])):
            return {"paywalled": True, "basis": "path_prefix", "access_verified": verified}
        overlap = md.get(OVERLAP_KEY)
        if isinstance(overlap, dict) and overlap.get("paywalled") is True:
            return {"paywalled": True, "basis": "sentence_overlap", "access_verified": verified}
        if _article_flagged(md):
            return {"paywalled": True, "basis": "article_flag", "access_verified": verified}
        section = md.get("section")
        if isinstance(section, str) and section.strip() in rule.get("sections", []):
            return {"paywalled": True, "basis": "section", "access_verified": verified}
        return {"paywalled": False, "basis": "open_path", "access_verified": verified}
    return {"paywalled": False, "basis": "not_in_policy", "access_verified": False}


def paywall_policy(url: str, metadata: dict | None = None, source_slug: str | None = None) -> dict | None:
    """Return the matching paywalled-source rule, or None for open content."""
    host = _host(url)
    try:
        path = urlsplit(str(url or "").strip()).path if host else ""
    except ValueError:
        path = ""
    for rule in load_policy()["sources"]:
        if host not in rule["hosts"]:
            continue
        if rule["scope"] == "host":
            return rule
        if any(path.startswith(prefix) for prefix in rule.get("path_prefixes", [])) or _article_flagged(metadata):
            return rule
        # A premium-section piece published under another path (e.g. /nacional/ with
        # the publisher's own section label "Pulso") is premium too.
        section = (metadata or {}).get("section") if isinstance(metadata, dict) else None
        if isinstance(section, str) and section.strip() in rule.get("sections", []):
            return rule
    return None


def is_paywalled(url: str, metadata: dict | None = None) -> bool:
    return paywall_policy(url, metadata) is not None


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def receipt(value, field: str, reason: str = "paywalled_press_public_teaser_only") -> dict:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    return {"field": field, "sha256": sha256_text(text),
            "characters": len(text), "reason": reason, "redacted_at": _REDACTED_AT}


def is_receipt(value) -> bool:
    return isinstance(value, dict) and value.get("redacted") is True and "sha256" in value


def clean_teaser(text) -> str:
    return " ".join(str(text or "").split())


def public_teaser(candidate, body: str | None = None, title: str | None = None, source: str | None = None) -> str:
    """Accept a lead only when it comes from an explicitly public element.

    ``source`` names that element (see ``TEASER_SOURCES``). Without a public
    provenance the text is treated as body: parsers used to fall back to
    ``body[:1800]``, so a short locked body would otherwise pass as a lead.
    """
    if source not in TEASER_SOURCES:
        return ""
    teaser = clean_teaser(candidate)
    limit = int(load_policy()["teaser_max_characters"])
    if not teaser or len(teaser) > limit:
        return ""
    if title and clean_teaser(title).casefold() == teaser.casefold():
        return ""
    return teaser


def teaser_with_source(raw_like: dict) -> tuple[str, str]:
    """(public lead, provenance) from a stored queue ``raw`` dict; ("", "title_only") if none."""
    md = raw_like.get("metadata") or {}
    title = md.get("article_title") or raw_like.get("title")
    source = md.get("public_teaser_source")
    if source == TITLE_ONLY:
        return "", TITLE_ONLY
    if source in TEASER_SOURCES:
        teaser = public_teaser(md.get("public_teaser"), None, title, source)
        if teaser:
            return teaser, source
    for key, src in (("og_description", "og:description"), ("meta_description", "meta:description"),
                     ("jsonld_description", "jsonld:description"), ("public_lead", "public_lead_element")):
        teaser = public_teaser(md.get(key), None, title, src)
        if teaser:
            return teaser, src
    if raw_like.get("source_slug") == "pulso_latercera" or "latercera.com" in _host(raw_like.get("url") or ""):
        # La Tercera's stored ``description`` is the URL-bound JSON-LD description.
        teaser = public_teaser(md.get("description"), None, title, "jsonld:description")
        if teaser:
            return teaser, "jsonld:description"
    # A DF listing card title carries "<headline> <teaser>"; that card is public.
    listing_title, headline = clean_teaser(raw_like.get("title")), clean_teaser(md.get("article_title"))
    if headline and listing_title.startswith(headline) and len(listing_title) > len(headline) + 20:
        teaser = public_teaser(listing_title[len(headline):], None, headline, "df_listing_card")
        if teaser:
            return teaser, "df_listing_card"
    return "", TITLE_ONLY


def teaser_from_raw(raw_like: dict) -> str:
    """Public lead from a stored queue ``raw`` dict (DF og:description, LT description)."""
    return teaser_with_source(raw_like)[0]


def _dedupe(receipts: list[dict]) -> list[dict]:
    seen, unique = set(), []
    for r in receipts:
        key = (r["field"], r["sha256"])
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def _redact_liveblog(md: dict, receipts: list[dict]) -> int:
    proof = md.get("liveblog_temporal_evidence")
    removed = 0
    if isinstance(proof, dict):
        for entry in proof.get("entries") or []:
            if isinstance(entry, dict) and isinstance(entry.get("body"), str) and entry["body"]:
                receipts.append(receipt(entry["body"], f"liveblog_temporal_evidence.entries[{entry.get('index')}].body"))
                removed += len(entry["body"])
                entry["body"] = ""
                entry["body_redacted"] = True
    return removed


def _redact_body_fields(md: dict, teaser: str, receipts: list[dict], prefix: str = "") -> int:
    """Replace publisher body fields by the lead (page_text) or remove them; return characters removed."""
    removed = 0
    for key in BODY_KEYS:
        value = md.get(key)
        if value in (None, "", [], {}) or (isinstance(value, str) and clean_teaser(value) == teaser):
            continue
        if key == "page_text" and isinstance(value, str):
            if not md.get("article_body_sha256"):
                md["article_body_sha256"] = sha256_text(value)
                md.setdefault("article_body_characters", len(value))
            elif md["article_body_sha256"] == sha256_text(value):
                # The capture hash proves this exact body: its length is part of the receipt.
                md.setdefault("article_body_characters", len(value))
        receipts.append(receipt(value, prefix + key))
        removed += len(value) if isinstance(value, str) else len(json.dumps(value, ensure_ascii=False))
        if key == "page_text":
            md[key] = teaser
        else:
            md.pop(key, None)
        md["body_redacted"] = True
    return removed


def apply_overlap_policy_raw(raw, fingerprints=None) -> str | None:
    """``apply_overlap_policy`` for a RawItem (page_text and raw_text); marks unflagged items unverified."""
    record = {"url": raw.url, "metadata": raw.metadata, "raw_text": raw.raw_text}
    outcome = apply_overlap_policy(record, fingerprints)
    raw.raw_text = record["raw_text"]
    if isinstance(raw.metadata, dict) and any(_host(raw.url) in r["hosts"] and r["scope"] != "host"
                                              for r in load_policy()["sources"]):
        raw.metadata.setdefault("access_verified", False)
    return outcome


def restrict_raw_to_public(raw) -> object:
    """Mutate a RawItem so only public text remains available for analysis/storage."""
    rule = paywall_policy(raw.url, raw.metadata, raw.source_slug)
    if not rule:
        return raw
    md = raw.metadata
    teaser, source = teaser_with_source({"title": raw.title, "url": raw.url, "source_slug": raw.source_slug,
                                         "metadata": md})
    receipts = list(md.get("rights_redactions") or [])
    _redact_body_fields(md, teaser, receipts)
    _redact_liveblog(md, receipts)
    if raw.raw_text and clean_teaser(raw.raw_text) != teaser:
        receipts.append(receipt(raw.raw_text, "raw_text"))
    md.update(page_text=teaser, public_teaser=teaser, public_teaser_source=source, paywalled=True,
              access_policy=load_policy()["policy"], paywall_source=rule["id"], rights_redactions=_dedupe(receipts))
    raw.raw_text = teaser
    return raw


def redacted_body_verified(md: dict) -> bool:
    """The full body existed and was verified at capture; only its receipt remains (paywalled press)."""
    sha, chars = md.get("article_body_sha256"), md.get("article_body_characters")
    if not (md.get("paywalled") is True and md.get("body_redacted") is True
            and isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{64}", sha)
            and type(chars) is int and chars >= 160):
        return False
    return any(r.get("field") in ("page_text", "metadata.page_text") and r.get("sha256") == sha
               and r.get("characters") == chars for r in md.get("rights_redactions") or [] if isinstance(r, dict))


_GENERIC = re.compile(r"^(isapre|cl[ií]nica|hospital|laboratorio|mutual|caja)\s+", re.I)


def _named_in(name, visible: str) -> bool:
    name = clean_teaser(name).casefold()
    return bool(name) and (name in visible or _GENERIC.sub("", name) in visible)


def redact_signal(row: dict, teaser: str | None = None) -> dict:
    """Public card for a paywalled piece: title, public lead, date, link; nothing else derived.

    No exemption for syntheses: a story-group card whose source is paywalled is
    redacted like any other row; a synthesis must cite an open primary source and
    carry only public text (see config/editorial_story_groups.json rights_basis).
    """
    rule = paywall_policy(row.get("source_url"), row)
    if not rule:
        return row
    policy = load_policy()
    out = dict(row)
    teaser = clean_teaser(teaser if teaser is not None else out.get("public_teaser"))
    receipts = list(out.get("rights_redactions") or [])
    review = out.get("editorial_review")
    for key in policy["redacted_signal_fields"]:
        if out.get(key) not in (None, "", [], {}) and not (
                key == "editorial_review" and isinstance(review, dict) and review_skeleton(review) == review):
            receipts.append(receipt(out[key], key))
        out.pop(key, None)
    if isinstance(review, dict):
        # An independent review's verdict (decision, file, hashes) is a publication
        # contract: a withdrawn piece must stay withdrawn. Only its prose goes.
        out["editorial_review"] = review_skeleton(review)
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
        rights_redactions=_dedupe(receipts),
    )
    if out.get("article_content_source"):
        out["article_content_source"] = "public_teaser"
    return out


def _is_token(value) -> bool:
    return not isinstance(value, str) or (len(value) <= 120 and not re.search(r"\s", value))


def review_skeleton(review):
    """Keep the structural part of a review (ids, paths, hashes, dates, decisions, scores); drop prose."""
    if isinstance(review, dict):
        out = {}
        for key, value in review.items():
            if isinstance(value, (dict, list)):
                kept = review_skeleton(value)
                if kept not in ({}, []):
                    out[key] = kept
            elif _is_token(value):
                out[key] = value
        return out
    if isinstance(review, list):
        return [k for k in (review_skeleton(v) if isinstance(v, (dict, list)) else v for v in review)
                if (isinstance(k, (dict, list)) and k) or (not isinstance(k, (dict, list)) and _is_token(k))]
    return review if _is_token(review) else None


def excess_fields(row: dict) -> list[str]:
    """Names of fields that a paywalled public row must not carry (for validators/tests)."""
    if not is_paywalled(row.get("source_url"), row):
        return []
    policy = load_policy()
    bad = [k for k in policy["redacted_signal_fields"] if row.get(k) not in (None, "", [], {})
           and not (k == "editorial_review" and isinstance(row[k], dict) and review_skeleton(row[k]) == row[k])]
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


def purge_raw_metadata(raw_like: dict) -> bool:
    """Redact stored paywalled body/derived text from a queue ``raw`` dict in place."""
    return _purge_raw(raw_like) is not None


def _purge_raw(raw_like: dict) -> int | None:
    """Like ``purge_raw_metadata``; returns characters removed (0 = only flags set) or None if unchanged."""
    url = raw_like.get("url") or ""
    md = raw_like.get("metadata")
    if not isinstance(md, dict) or not paywall_policy(url, md):
        return None
    policy = load_policy()
    teaser, source = teaser_with_source(raw_like)
    receipts = list(md.get("rights_redactions") or [])
    before = len(receipts)
    removed = _redact_body_fields(md, teaser, receipts, "metadata.")
    removed += _redact_liveblog(md, receipts)
    preserved = set(policy.get("preserved_internal_fields", []))
    for key in policy["redacted_body_fields"]:
        if key in BODY_KEYS or key in preserved:
            continue
        value = md.get(key)
        if value in (None, "", [], {}) or (isinstance(value, str) and clean_teaser(value) == teaser):
            continue
        receipts.append(receipt(value, f"metadata.{key}"))
        removed += len(value) if isinstance(value, str) else len(json.dumps(value, ensure_ascii=False))
        md[key] = None
    assessment = md.get("editorial_assessment")
    if isinstance(assessment, dict) and any(assessment.get(k) for k in _REASON_KEYS):
        for k in _REASON_KEYS:
            if assessment.get(k):
                receipts.append(receipt(assessment[k], f"metadata.editorial_assessment.{k}"))
                removed += len(str(assessment[k]))
        md["editorial_assessment"] = {k: v for k, v in assessment.items() if k not in _REASON_KEYS}
    raw_text = raw_like.get("raw_text")
    if raw_text and clean_teaser(raw_text) != teaser:
        receipts.append(receipt(raw_text, "raw_text"))
        removed += len(raw_text)
        raw_like["raw_text"] = teaser
    flags = dict(public_teaser=teaser, public_teaser_source=source, paywalled=True, access_policy=policy["policy"])
    if len(receipts) == before and all(md.get(k) == v for k, v in flags.items()):
        return None
    md.update(flags, rights_redactions=_dedupe(receipts))
    return removed


def _is_raw_like(node) -> bool:
    return isinstance(node, dict) and isinstance(node.get("url"), str) and isinstance(node.get("metadata"), dict)


def scrub_queue_item(item: dict, fingerprints: set | None = None) -> dict:
    """Redact every capture stored in a queue item, including nested history.

    Walks ``raw`` and every nested raw-like record (``recovery_observations[*].before.raw``,
    ``superseded_records[*].raw``, ``evidence_revisions[*].previous_processing_raw``,
    ``rediscovery_repairs[*].previous_raw``...). With ``fingerprints`` it also replaces any
    remaining string containing a known paywalled body sentence. Returns truthful counts.
    """
    stats = {"records": 0, "characters": 0, "fingerprint_strings": 0, "fingerprint_characters": 0}
    raw = item.get("raw") or {}
    if not paywall_policy(raw.get("url", ""), raw.get("metadata")):
        return stats

    def walk(node):
        if isinstance(node, dict):
            if _is_raw_like(node):
                removed = _purge_raw(node)
                if removed is not None:
                    stats["records"] += 1
                    stats["characters"] += removed
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(item)
    if fingerprints:
        n, chars = scrub_fingerprinted(item, fingerprints, force=True)
        stats["fingerprint_strings"] += n
        stats["fingerprint_characters"] += chars
    return stats


# --- Verbatim-body fingerprints (sentence hashes; no text is stored) ----------

_SPLIT = re.compile(r"(?<=[.!?;:»\"])\s+|\n+")
_MIN_SEGMENT = 60


def _segments(text: str):
    for part in _SPLIT.split(text):
        part = " ".join(part.split()).casefold()
        if len(part) >= _MIN_SEGMENT:
            yield part


def _segment_hash(segment: str) -> str:
    return hashlib.sha256(segment.encode("utf-8")).hexdigest()[:20]


def body_fingerprints(text: str, public=()) -> set[str]:
    """Sentence hashes of a paywalled body, minus sentences that are public (titles/leads).

    ``public`` is one text or an iterable of texts; each is segmented on its own.
    """
    return {_segment_hash(s) for s in _segments(text or "")} - public_fingerprints(public)


def public_fingerprints(public) -> set[str]:
    texts = [public] if isinstance(public, str) else list(public or ())
    out = set()
    for text in texts:
        if isinstance(text, str) and text:
            out |= {_segment_hash(s) for s in _segments(text)}
            flat = " ".join(text.split()).casefold()
            if len(flat) >= _MIN_SEGMENT:
                out.add(_segment_hash(flat))
    return out


def contains_fingerprinted(text: str, fingerprints: set) -> bool:
    return isinstance(text, str) and len(text) >= _MIN_SEGMENT and any(
        _segment_hash(s) in fingerprints for s in _segments(text))


def load_fingerprints(root: Path | None = None) -> set[str]:
    path = (root or project_root()) / FINGERPRINTS_PATH
    try:
        return set(json.loads(path.read_text(encoding="utf-8"))["segment_sha256_prefix20"])
    except (OSError, ValueError, KeyError, TypeError):
        return set()


@lru_cache(maxsize=1)
def _runtime_fingerprints() -> frozenset:
    return frozenset(load_fingerprints())


# --- Open-path pieces that reproduce a paywalled body ----------------------------
# Review 3 (28-oct): an open-section capture (/sustentabilidad/...) shared most of its
# sentences with a body captured under the Pulso section. Sentence overlap with a
# known paywalled body is treated as paywalled: above the ratio the whole piece is
# paywalled (lead + receipt); below it, only the overlapping sentences are redacted.
OVERLAP_PAYWALL_RATIO = 0.5
SENTENCE_REDACTIONS = "rights_sentence_redactions"
BODY_SENTENCE_PROOF = "article_body_sentence_redaction"
OVERLAP_REASON = "sentence_overlap_with_paywalled_body"


def _segment_spans(text: str):
    """(start, end, normalised segment) for each sentence ``_segments`` would yield."""
    start = 0
    for match in list(_SPLIT.finditer(text)) + [None]:
        end = match.start() if match else len(text)
        part = text[start:end]
        norm = " ".join(part.split()).casefold()
        if len(norm) >= _MIN_SEGMENT:
            lead = len(part) - len(part.lstrip())
            yield start + lead, start + len(part.rstrip()), norm
        if match:
            start = match.end()


def body_overlap(text, fingerprints) -> tuple[int, int]:
    """(sentences matching a paywalled-body fingerprint, sentences) in ``text``."""
    segments = list(_segments(text)) if isinstance(text, str) else []
    return sum(1 for s in segments if _segment_hash(s) in fingerprints), len(segments)


def redact_fingerprinted_sentences(text: str, fingerprints, field: str) -> tuple[str, list[dict]]:
    """Replace only the sentences of ``text`` that reproduce a paywalled body by inline receipts."""
    if not isinstance(text, str) or not fingerprints:
        return text, []
    out, receipts, cursor = [], [], 0
    for start, end, norm in _segment_spans(text):
        if _segment_hash(norm) not in fingerprints:
            continue
        sentence = text[start:end]
        r = receipt(sentence, field, OVERLAP_REASON)
        receipts.append(r)
        out.append(text[cursor:start])
        out.append(f"[redactado: muro de pago; sha256={r['sha256']}; caracteres={r['characters']}]")
        cursor = end
    if not receipts:
        return text, []
    out.append(text[cursor:])
    return "".join(out), receipts


def sentence_redacted_body_verified(md: dict) -> bool:
    """The stored page_text is the verified capture body minus receipted overlapping sentences."""
    proof = md.get(BODY_SENTENCE_PROOF)
    body = md.get("page_text")
    return (isinstance(proof, dict) and isinstance(body, str) and len(body.strip()) >= 160
            and proof.get("original_sha256") == md.get("article_body_sha256")
            and re.fullmatch(r"[0-9a-f]{64}", str(proof.get("original_sha256") or "")) is not None
            and proof.get("page_text_sha256") == sha256_text(body)
            and proof.get("page_text_characters") == len(body))


def apply_overlap_policy(record: dict, fingerprints=None) -> str | None:
    """Apply the overlap rule to a raw-like/cache record of an open path, in place.

    Returns ``"paywalled"`` (flagged; the caller redacts it as paywalled),
    ``"sentences"`` (overlapping sentences replaced by receipts) or None.
    Idempotent: redacted sentences no longer match, a flagged record is paywalled.
    """
    md = record.get("metadata") if isinstance(record, dict) else None
    url = record.get("url") if isinstance(record, dict) else None
    if not isinstance(md, dict) or not isinstance(url, str) or paywall_policy(url, md):
        return None
    if not any(_host(url) in rule["hosts"] for rule in load_policy()["sources"]):
        return None
    fps = _runtime_fingerprints() if fingerprints is None else fingerprints
    if not fps:
        return None
    fields = [("page_text", md), ("raw_text", record), ("body", record)]
    best = max((body_overlap(holder.get(key), fps) for key, holder in fields), key=lambda hn: (hn[0] / hn[1]) if hn[1] else 0)
    hits, total = best
    if not hits:
        return None
    ratio = round(hits / total, 3) if total else 0.0
    if ratio >= OVERLAP_PAYWALL_RATIO:
        md[OVERLAP_KEY] = {"paywalled": True, "segments_matched": hits, "segments": total, "ratio": ratio,
                           "basis": OVERLAP_REASON, "fingerprints": str(FINGERPRINTS_PATH),
                           "threshold": OVERLAP_PAYWALL_RATIO}
        return "paywalled"
    receipts = list(md.get(SENTENCE_REDACTIONS) or [])
    original_body = md.get("page_text")
    body_verified = (isinstance(original_body, str) and md.get("article_body_sha256") == sha256_text(original_body))
    changed = False
    for key, holder in fields:
        new, found = redact_fingerprinted_sentences(holder.get(key), fps, key if holder is md else f"record.{key}")
        if found:
            holder[key] = new
            receipts.extend(found)
            changed = True
    if not changed:
        return None
    if body_verified and md.get("page_text") != original_body:
        md[BODY_SENTENCE_PROOF] = {"original_sha256": md["article_body_sha256"],
                                   "original_characters": len(original_body),
                                   "page_text_sha256": sha256_text(md["page_text"]),
                                   "page_text_characters": len(md["page_text"]), "reason": OVERLAP_REASON,
                                   "redacted_at": _REDACTED_AT}
    md[SENTENCE_REDACTIONS] = _dedupe(receipts)
    md[OVERLAP_KEY] = {"paywalled": False, "segments_matched": hits, "segments": total, "ratio": ratio,
                       "basis": OVERLAP_REASON, "sentences_redacted": True, "threshold": OVERLAP_PAYWALL_RATIO}
    return "sentences"


_URL_KEYS = ("url", "source_url", "canonical_url", "requested_url", "final_url", "raw_url")
# Public by definition (title, lead with proven provenance, publisher description):
# never fingerprint-redacted, or the lead would vanish and the next run would no
# longer recognise its sentences as public.
_PUBLIC_TEXT_KEYS = {"title", "article_title", "primary_header_title", "headline", "public_title", "display_title",
                     "description", "og_description", "public_teaser", "label", "legacy_title", "source_title_full"}


def _url_key(url) -> str:
    return str(url or "").strip().rstrip("/")


def scrub_fingerprinted(node, fingerprints: set, url_hint: str | None = None, force: bool = False,
                        reason: str = "paywalled_press_public_teaser_only", *, open_sentences: bool = False,
                        paywalled_urls: set | None = None) -> tuple[int, int]:
    """Replace strings that contain a paywalled body sentence by a receipt. Returns (strings, characters).

    Outside a paywalled URL context (or ``force``) the string is kept; with
    ``open_sentences`` only its overlapping sentences become inline receipts (an
    open piece reproducing a paywalled body, review 3). ``paywalled_urls`` adds
    URLs found paywalled by sentence overlap. A paid model output met on the way is
    redacted by ``redact_model_output`` (structure kept, original digest recorded)
    before the rest of its record.
    """
    count = chars = 0
    extra = paywalled_urls or set()

    def paywalled(url, md=None):
        return is_paywalled(url, md) or (_url_key(url) in extra if extra else False)

    if isinstance(node, dict):
        url = next((node[k] for k in _URL_KEYS if isinstance(node.get(k), str) and node.get(k)), url_hint)
        context = force or url is None or paywalled(url, node if isinstance(node, dict) else None)
        if (context or open_sentences) and isinstance(node.get(MODEL_OUTPUT_KEY), dict):
            # A paid output keeps its structure and its original digest in either context.
            n, c = redact_model_output(node, fingerprints)
            count += n
            chars += c
        lead = node.get("public_teaser") if isinstance(node.get("public_teaser"), str) else None
        for key in list(node):
            value = node[key]
            if isinstance(value, str):
                if key in _PUBLIC_TEXT_KEYS or (lead and value == lead):
                    continue
                if not contains_fingerprinted(value, fingerprints):
                    continue
                if context:
                    node[key] = {"redacted": True, **receipt(value, key, reason)}
                    count += 1
                    chars += len(value)
                elif open_sentences:
                    new, found = redact_fingerprinted_sentences(value, fingerprints, key)
                    if found:
                        node[key] = new
                        count += 1
                        chars += sum(r["characters"] for r in found)
            else:
                child_url = key if isinstance(key, str) and re.match(r"https?://", key) else url
                n, c = scrub_fingerprinted(value, fingerprints, child_url, force, reason,
                                           open_sentences=open_sentences, paywalled_urls=paywalled_urls)
                count += n
                chars += c
    elif isinstance(node, list):
        url = url_hint
        context = force or url is None or paywalled(url)
        for i, value in enumerate(node):
            if isinstance(value, str):
                if not contains_fingerprinted(value, fingerprints):
                    continue
                if context:
                    node[i] = {"redacted": True, **receipt(value, f"[{i}]", reason)}
                    count += 1
                    chars += len(value)
                elif open_sentences:
                    new, found = redact_fingerprinted_sentences(value, fingerprints, f"[{i}]")
                    if found:
                        node[i] = new
                        count += 1
                        chars += sum(r["characters"] for r in found)
            else:
                n, c = scrub_fingerprinted(value, fingerprints, url_hint, force, reason,
                                           open_sentences=open_sentences, paywalled_urls=paywalled_urls)
                count += n
                chars += c
    return count, chars


# --- Paid model outputs (Alicanto work product; rule 6: preserve paid outputs) -----

MODEL_OUTPUT_KEY = "analysis_model_output"
MODEL_OUTPUT_RIGHTS = "analysis_model_output_rights"
QUOTE_REASON = "paywalled_body_quote_in_paid_output"


def model_output_digest(value) -> str:
    """Canonical digest of a model output (same form as the validators' ``model_output_sha256``)."""
    return sha256_text(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _output_receipts(node, path=""):
    if isinstance(node, dict):
        if node.get("redacted") is True and "sha256" in node:
            yield {"path": path, "sha256": node["sha256"], "characters": node.get("characters")}
            return
        for key in sorted(node):
            yield from _output_receipts(node[key], f"{path}.{key}" if path else key)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _output_receipts(value, f"{path}[{i}]")


def redact_model_output(metadata: dict, fingerprints: set) -> tuple[int, int]:
    """Replace verbatim paywalled-body quotes inside a paid output by receipts, keeping its structure.

    The paid answer itself is preserved: only strings that reproduce a locked body
    sentence become ``{"redacted": true, sha256, characters, reason}`` in place. The
    digest of the output *before* any redaction is recorded as
    ``original_model_output_sha256`` (the key every earlier validation was bound
    to), with the redacted digest and the receipt list, so ``verified_model_output_digest``
    can prove the stored output is that paid answer minus the listed quotes.
    """
    model = metadata.get(MODEL_OUTPUT_KEY)
    if not isinstance(model, dict) or not fingerprints:
        return 0, 0
    before = model_output_digest(model)
    had_receipts = next(_output_receipts(model), None) is not None
    count = chars = 0
    for key in list(model):
        if key == "_pulso_analysis_meta":
            continue  # hashes and ids only
        value = model[key]
        if isinstance(value, str):
            if contains_fingerprinted(value, fingerprints):
                model[key] = {"redacted": True, **receipt(value, key, QUOTE_REASON)}
                count += 1
                chars += len(value)
        else:
            n, c = scrub_fingerprinted(value, fingerprints, force=True, reason=QUOTE_REASON)
            count += n
            chars += c
    if not count:
        return 0, 0
    record = metadata.get(MODEL_OUTPUT_RIGHTS)
    if isinstance(record, dict) and record.get("redacted_model_output_sha256") == before:
        original, basis = record.get("original_model_output_sha256"), "previous_record"
    elif not had_receipts:
        original, basis = before, "digest_of_the_stored_output_before_redaction"
    else:
        original, basis = None, "earlier_redaction_without_record"  # never guessed: reuse is refused
    receipts = list(_output_receipts(model))
    metadata[MODEL_OUTPUT_RIGHTS] = {
        "original_model_output_sha256": original,
        "original_basis": basis,
        "redacted_model_output_sha256": model_output_digest(model),
        "redactions": receipts,
        "reason": QUOTE_REASON,
        "redacted_at": _REDACTED_AT,
        "note": "Paid output preserved; verbatim paywalled-body quotes kept only as sha256 + length receipts.",
    }
    return count, chars


def verified_model_output_digest(metadata: dict) -> tuple[str | None, str]:
    """(digest an earlier validation must match, basis) for the stored paid output.

    Unredacted output: its own digest. Redacted output: the recorded original
    digest, only if the stored output is exactly the recorded redacted form
    (same digest, same receipts at the same paths). Otherwise ``None``.
    """
    model = metadata.get(MODEL_OUTPUT_KEY)
    if not isinstance(model, dict):
        return None, "no_paid_output"
    receipts = list(_output_receipts(model))
    record = metadata.get(MODEL_OUTPUT_RIGHTS)
    if not receipts and record is None:
        return model_output_digest(model), "unredacted_output"
    if (not isinstance(record, dict) or record.get("redacted_model_output_sha256") != model_output_digest(model)
            or record.get("redactions") != receipts
            or not re.fullmatch(r"[0-9a-f]{64}", str(record.get("original_model_output_sha256") or ""))):
        return None, "redacted_output_record_mismatch"
    return record["original_model_output_sha256"], "redacted_output_verified"


_LONG = 600


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


# --- Public-text check --------------------------------------------------------

_STOP = {"según", "segun", "df", "diario", "financiero", "pulso", "la", "el", "los", "las", "tercera", "alicanto",
         "chile", "en", "de", "del", "y", "con", "para", "por", "un", "una", "este", "esta", "lt", "pm"}


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.casefold().split())


def _claims(text: str) -> set[str]:
    """Numbers and named actors in ``text`` (the facts a public lead must already contain)."""
    claims = set()
    for number in re.findall(r"(?<![\w])\d[\d.,]*", text):
        digits = re.sub(r"[.,]", "", number)
        if digits:
            claims.add("#" + digits)
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        words = re.findall(r"[A-Za-zÁÉÍÓÚÑÜáéíóúñü][\wÁÉÍÓÚÑÜáéíóúñü'’-]*", sentence)
        for i, word in enumerate(words):
            if (word[0].isupper() and i > 0) or (len(word) >= 2 and word.isupper()):
                if _fold(word) not in _STOP:
                    claims.add(_fold(word))
    return claims


# Function words and Alicanto's own framing vocabulary (hedges, attribution,
# evaluation): they carry no publisher fact, so they need no support in the lead.
_FUNCTION_WORDS = set("""
a al algo algun alguna algunas alguno algunos ante antes aqui asi aun aunque bajo cada casi como con contra cual
cuales cuando de del desde donde dos durante e el ella ellas ello ellos en entre era eran es esa esas ese eso esos
esta estaba estado estan estar estas este esto estos fue fueron ha habia han hasta hay la las le les lo los mas
me mientras muy ni no nos o otra otras otro otros para pero poco por porque pues que quien quienes se sea segun ser
si sido sin sobre son su sus tal tambien tan tanto te todavia toda todas todo todos tras tu un una unas uno unos
y ya ademas luego solo sola solamente mismo misma mismos mismas cuyo cuya cuyos cuyas tiene tienen tener podria
podrian puede pueden poder debe deben deberia haber hace hacen hacer cual dicha dicho dichos dichas
""".split())
_FRAMING_WORDS = set("""
plantea planteo propuesta senal senales medida medidas adoptada adoptado sectorial implica implican implicancia
implicancias efecto efectos impacto riesgo riesgos decision aun todavia segun reporta reporto informa informo indica
indico seria serian posible posibles eventual eventuales relevante relevantes clave importa importante importantes
contexto lectura alicanto nota prensa reporte articulo pieza bajada titular titulo publica publico publicada
publicado fuente fuentes atribucion atribuido dato datos cifra cifras confirma confirmar confirmado confirmada
verificar verificado verificada oficial oficiales pendiente pendientes vigente vigentes ahora hoy fecha
afirma afirmo senala senalo dijo dice sostiene sostuvo agrega agrego explica explico asegura aseguro declara declaro
advierte advirtio
""".split())
_STEM = 5


def _content_stems(folded: str) -> list[str]:
    words = re.findall(r"[a-z][a-z'-]+", folded)
    return [w[:_STEM] for w in words
            if len(w) >= 4 and w not in _FUNCTION_WORDS and w not in _FRAMING_WORDS and w not in _STOP]


_MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
           "noviembre", "diciembre")


def public_date_text(iso) -> str:
    """The publication date is a public field: "29 de septiembre de 2026" for the text check."""
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", str(iso or "")[:10])
    if not m or not 1 <= int(m.group(2)) <= 12:
        return ""
    return f"{int(m.group(3))} de {_MONTHS[int(m.group(2)) - 1]} de {m.group(1)}"


def public_text_supported(text, public: str) -> tuple[bool, list[str]]:
    """True when ``text`` adds no fact beyond the public title + lead.

    Every number and named actor must already appear in ``public``; so must every
    content word (nouns, verbs, adjectives, compared by a 5-letter stem). Function
    words and Alicanto's framing vocabulary (hedges, attribution) are exempt. So
    "sin aumentar presupuesto" fails against a lead that never mentions a budget,
    even though it carries no number or proper noun.
    """
    if not isinstance(text, str):
        return False, ["<non_text>"]
    available = _claims(public) | {"#" + re.sub(r"[.,]", "", n) for n in re.findall(r"\d[\d.,]*", public)}
    folded = _fold(public)
    missing = sorted(c for c in _claims(text) if c not in available and (c.startswith("#") or c not in folded))
    public_stems = set(_content_stems(folded))
    for stem in _content_stems(_fold(text)):
        if stem not in public_stems and "~" + stem not in missing:
            missing.append("~" + stem)
    return not missing, missing


# --- Public payloads (weekly insight, Global, free value) --------------------

EDITORIAL_TEXT_KEYS = ("reason", "summary", "what", "why", "what_happened", "why_it_matters", "key_figures", "key_points",
                       "insight_reading", "insight_teaser", "card_what", "card_why", "decision_use",
                       "what_to_watch", "uncertainties", "actors", "analysis", "body", "description",
                       "executive_thesis", "what_changed", "business_implications", "teaser", "lead")


def _field_sha(value) -> str:
    return sha256_text(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True))


def rights_review_entry(node: dict, fields: list[str], basis: str, reviewer: str) -> dict:
    """Pin a rights review of ``fields`` to their exact current text (any edit voids it).

    The entry starts ``qa_status: pending``: it bypasses nothing until an independent
    QA records ``qa_status: approved`` and ``qa_by`` (see ``review_qa_approved``).
    """
    return {"basis": basis, "reviewer": reviewer, "reviewed_at": _REDACTED_AT, "qa_status": "pending",
            "fields": {f: _field_sha(node[f]) for f in fields if f in node}}


def review_qa_approved(review) -> bool:
    """A rights review counts only after an independent QA: ``qa_status: approved`` and ``qa_by``."""
    return (isinstance(review, dict) and review.get("qa_status") == "approved"
            and isinstance(review.get("qa_by"), str) and bool(review["qa_by"].strip())
            and review["qa_by"].strip() != str(review.get("reviewer") or "").strip())


def _reviewed(node: dict, key: str) -> bool:
    """``key`` may bypass the public-text check only under a QA-approved review pinned to its exact text."""
    review = node.get("rights_review")
    return (review_qa_approved(review) and isinstance(review.get("fields"), dict)
            and review["fields"].get(key) == _field_sha(node.get(key)))


def redact_public_payload(payload, teasers: dict | None = None, stats: dict | None = None):
    """Apply the paywall policy to any public payload.

    * Signal rows (``source_url`` + ``title``) of paywalled press go through ``redact_signal``.
    * Other objects referencing a paywalled URL (weekly picks, insight items, Global/free
      teasers) keep editorial text only if it is supported by the title + public lead, or
      carries a ``rights_review`` pinned to that exact text. Otherwise the text is replaced
      by a receipt and the object is flagged ``rights_review_required``.

    The input is never mutated; unchanged subtrees are returned as the same objects.
    """
    teasers = teasers or {}
    stats = stats if stats is not None else {"signals": 0, "fields": 0}

    def teaser_for(url):
        return teasers.get(str(url or "").strip().rstrip("/"), "")

    def walk(node):
        if isinstance(node, list):
            items = [walk(v) for v in node]
            return node if all(a is b for a, b in zip(items, node)) else items
        if not isinstance(node, dict):
            return node
        children = {k: walk(v) for k, v in node.items()}
        out = node if all(children[k] is node[k] for k in node) else children
        url = out.get("source_url") or out.get("url")
        if not isinstance(url, str) or not url:
            # A committee/evidence block without its own URL inherits the paywalled
            # source it maps (e.g. ``evidence_map: [{url: df.cl/...}]``).
            url = next((e.get("url") for e in out.get("evidence_map") or [] if isinstance(e, dict)
                        and isinstance(e.get("url"), str) and is_paywalled(e["url"])), None)
        if not isinstance(url, str) or not is_paywalled(url, out):
            return out
        if out.get("source_url") and out.get("title") and ("what_happened" in out or "why_it_matters" in out):
            stats["signals"] += 1
            teaser = out.get("public_teaser") if out.get("paywalled") else teaser_for(url)
            redacted = redact_signal(out, teaser or "")
            return out if redacted == out else redacted
        res = dict(out)
        teaser = res.get("public_teaser") or teaser_for(url)
        if teaser and not res.get("public_teaser") and any(res.get(k) for k in EDITORIAL_TEXT_KEYS):
            res["public_teaser"] = teaser  # the lead the check used travels with the object
        public = f"{res.get('title') or res.get('public_title') or ''} {teaser}"
        flagged = False
        for key in EDITORIAL_TEXT_KEYS:
            value = res.get(key)
            if value in (None, "", [], {}) or _reviewed(res, key):
                continue
            texts = value if isinstance(value, list) else [value]
            if all(isinstance(t, str) and public_text_supported(t, public)[0] for t in texts):
                continue
            res["rights_redactions"] = list(res.get("rights_redactions") or []) + [receipt(value, key)]
            res[key] = [] if isinstance(value, list) else ""
            stats["fields"] += 1
            flagged = True
        if flagged:
            res.update(paywalled=True, rights_review_required=True, access_policy=load_policy()["policy"])
        return out if res == out else res

    return walk(payload)


def public_teaser_index(*row_sets) -> dict:
    """URL -> public lead, from rows already carrying ``public_teaser`` (history/snapshot)."""
    index = {}
    for rows in row_sets:
        for row in rows or []:
            if isinstance(row, dict) and row.get("paywalled") and row.get("public_teaser") and row.get("source_url"):
                index.setdefault(str(row["source_url"]).strip().rstrip("/"), row["public_teaser"])
    return index
