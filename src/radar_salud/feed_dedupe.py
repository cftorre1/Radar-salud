"""One card per event in the Chile feed (Dirección 3-nov-2026: "algunas noticias … están duplicadas").

Two deterministic collapses, applied to the curated snapshot cards (``scripts/export_web_snapshot.py``):

1. ``collapse_bill_milestones``: the Senate open-data source emits one card per milestone (#hito-<kind>-<date>). The
   cards of one bill (``bill_boletin``) become one: the latest milestone (date, then legislative order) stays as the
   card; the others are listed in ``bill_history`` ("Trámites de este proyecto"). Nothing is rewritten.
2. ``merge_same_event``: the same event reported by different outlets (e.g. a Minsal release and the La Tercera piece
   about it, same day). Two news cards are the same event only when ALL hold: different sources, event dates at most
   ``MAX_DAYS`` apart, ≥ ``MIN_SHARED`` shared title terms, no conflicting WATCH entities (each card names an entity the
   other does not) and EITHER a shared non-year figure ('44 mil', '62 millones') with Jaccard ≥ ``MIN_JACCARD`` OR
   near-identical titles (Jaccard ≥ ``NEAR_IDENTICAL``). Titles that differ in one name ('multa a Colmena' / 'multa a
   Cruz Blanca', 'paracetamol' / 'ibuprofeno') share many generic words but no figure: they stay separate (review of
   PR #135). Normative records,
   bills, statistics fichas, syntheses and other aggregates never merge. The kept card is the official one (else the
   open one, else the earliest); the others go to ``same_event_sources`` ("También informaron"), title and link only.

Both are conservative: when in doubt the cards stay separate. Every merge is recorded in ``dedupe`` on the kept card.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date

MAX_DAYS = 2
MIN_SHARED = 3
MIN_JACCARD = 0.35
NEAR_IDENTICAL = 0.8

# Legislative order of the Congreso milestones (congreso_sources.MILESTONE_LABEL, plus the final ones).
BILL_ORDER = ["ingreso", "informe_comision", "aprobacion_general", "aprobacion_particular",
              "aprobacion_general_particular", "rechazo", "comision_mixta", "despacho", "veto",
              "control_constitucional", "publicacion", "archivo"]

STOP = set("""de la el los las y en a para por con del al un una unos unas que se su sus es o u como mas sobre tras entre
ante sin este esta estos estas ese esa eso nuevo nueva nuevos nuevas chile chilena chileno pais hace tiene son ser fue
segun desde hasta durante cada todo toda todos todas otro otra mil millones salud minsal gobierno""".split())

# Cards that are records or aggregates in their own right: never merged across sources.
NEVER_MERGE_TYPES = {"official_normative", "normative", "editorial_synthesis"}
NEVER_MERGE_EVENTS = {"STORY_SUMMARY", "DATA_PULSE", "ACCREDITATION_PULSE", "SANCTION_PULSE", "WEEKLY_INSIGHT"}
NEVER_MERGE_SOURCES = ("Diario Oficial", "Congreso Nacional")
OFFICIAL = {"official"}


def _day(card: dict) -> date | None:
    for k in ("event_date", "publication_date"):
        try:
            return date.fromisoformat(str(card.get(k) or "")[:10])
        except ValueError:
            continue
    return None


def terms(title: str) -> set[str]:
    """Significant title terms: words of 4+ letters (first 7 letters, accents folded) and numbers of 2+ digits that are
    not years. '44 mil niños' and '44.000 niños' both give '44'."""
    t = unicodedata.normalize("NFKD", str(title or "").casefold()).encode("ascii", "ignore").decode()
    out = set()
    for w in re.findall(r"[a-z]+|\d+", t):
        if w.isdigit():
            if len(w) >= 2 and not re.fullmatch(r"(19|20)\d\d", w):
                out.add(w)
        elif len(w) > 3 and w not in STOP:
            out.add(w[:7])
    return out


def _title(card: dict) -> str:
    return str(card.get("display_title") or card.get("title") or "")


def _ref(card: dict) -> dict:
    """What a merged card leaves behind: the source, its own title and link (paywalled press: its public title only)."""
    return {k: v for k, v in {
        "source_name": card.get("source_name"), "title": _title(card), "url": card.get("source_url"),
        "event_date": card.get("event_date") or card.get("publication_date"),
        "paywalled": True if card.get("paywalled") is True else None}.items() if v is not None}


def _absorb(kept: dict, merged: list[dict]) -> dict:
    """The kept card inherits the WATCH entity refs of the merged ones (a follower of either actor still sees it) and
    their identity keys (``merged_from``), so a shared '#sig-<id>' link of a merged card opens the kept one."""
    refs = list(kept.get("entity_refs") or [])
    seen = {r.get("canonical_id") for r in refs if isinstance(r, dict)}
    for c in merged:
        for r in c.get("entity_refs") or []:
            if isinstance(r, dict) and r.get("canonical_id") not in seen:
                refs.append(r)
                seen.add(r.get("canonical_id"))
    if refs:
        kept["entity_refs"] = refs
    keys = list(kept.get("merged_from") or [])
    for c in merged:
        keys.append({k: c.get(k) for k in ("piece_id", "source_url", "event_date", "event_type") if c.get(k)})
        keys.extend(c.get("merged_from") or [])
    kept["merged_from"] = keys
    return kept


# ---------------------------------------------------------------------------------------------------------------
# 1. Bill milestones


def _bill_rank(card: dict) -> tuple:
    kind = str(card.get("bill_milestone") or "")
    order = BILL_ORDER.index(kind) if kind in BILL_ORDER else -1
    return (_day(card) or date.min, order)


def collapse_bill_milestones(cards: list[dict]) -> list[dict]:
    groups: dict[str, list[int]] = {}
    for i, c in enumerate(cards):
        b = c.get("bill_boletin")
        if b and not c.get("stats_ficha"):
            groups.setdefault(str(b), []).append(i)
    drop: set[int] = set()
    out = list(cards)
    for boletin, idx in groups.items():
        if len(idx) < 2:
            continue
        keep = max(idx, key=lambda i: _bill_rank(cards[i]))
        others = sorted((i for i in idx if i != keep), key=lambda i: _bill_rank(cards[i]), reverse=True)
        k = _absorb(dict(cards[keep]), [cards[i] for i in others])
        k["bill_history"] = [{**_ref(cards[i]), "material": _title(cards[i]).split(":", 1)[0]} for i in others]
        k["dedupe"] = {**(k.get("dedupe") or {}), "bill_milestones": {"boletin": boletin, "merged": len(others)}}
        out[keep] = k
        drop.update(others)
    return [c for i, c in enumerate(out) if i not in drop]


# ---------------------------------------------------------------------------------------------------------------
# 2. Same event across sources


def mergeable(card: dict) -> bool:
    if card.get("stats_ficha") or card.get("bill_boletin") or card.get("derived_from"):
        return False
    if str(card.get("source_type") or "") in NEVER_MERGE_TYPES or str(card.get("event_type") or "") in NEVER_MERGE_EVENTS:
        return False
    if str(card.get("source_name") or "").startswith(NEVER_MERGE_SOURCES):
        return False
    if str(card.get("editorial_schema_version")) == "3":
        return False  # v3 fichas render no 'También informaron' list (review of #135)
    if card.get("normative_minimal") or card.get("loose_bulletin"):
        return False
    return bool(card.get("source_url")) and _day(card) is not None and len(terms(_title(card))) >= MIN_SHARED


def same_event(a: dict, b: dict) -> dict | None:
    """The match evidence when two cards report the same event, else None."""
    if str(a.get("source_name") or "") == str(b.get("source_name") or ""):
        return None
    da, db = _day(a), _day(b)
    if da is None or db is None or abs((da - db).days) > MAX_DAYS:
        return None
    ta, tb = terms(_title(a)), terms(_title(b))
    shared = ta & tb
    jac = len(shared) / len(ta | tb) if ta | tb else 0.0
    if len(shared) < MIN_SHARED:
        return None
    ea, eb = _entities(a), _entities(b)
    if ea - eb and eb - ea:
        return None  # each names an entity the other does not: two events about different actors
    figures = {t for t in shared if t.isdigit()}
    if not ((figures and jac >= MIN_JACCARD) or jac >= NEAR_IDENTICAL):
        return None
    return {"shared_terms": sorted(shared), "shared_figures": sorted(figures), "jaccard": round(jac, 3),
            "days_apart": abs((da - db).days)}


def _entities(card: dict) -> set[str]:
    return {str(r.get("canonical_id")) for r in card.get("entity_refs") or [] if isinstance(r, dict) and r.get("canonical_id")}


def _keep_rank(card: dict) -> tuple:
    official = str(card.get("source_type") or "") in OFFICIAL
    open_ = card.get("paywalled") is not True
    d = _day(card) or date.max
    return (official, open_, -d.toordinal())


def merge_same_event(cards: list[dict]) -> list[dict]:
    idx = [i for i, c in enumerate(cards) if mergeable(c)]
    parent = {i: i for i in idx}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    evidence: dict[tuple[int, int], dict] = {}
    for n, i in enumerate(idx):
        for j in idx[n + 1:]:
            ev = same_event(cards[i], cards[j])
            if ev:
                evidence[(i, j)] = ev
                parent[find(j)] = find(i)
    groups: dict[int, list[int]] = {}
    for i in idx:
        groups.setdefault(find(i), []).append(i)
    out = list(cards)
    drop: set[int] = set()
    for members in groups.values():
        if len(members) < 2:
            continue
        keep = max(members, key=lambda i: _keep_rank(cards[i]))
        # Every merged card must match the kept one directly (no chains A~B~C where A and C share nothing).
        others = [i for i in members if i != keep and (evidence.get((min(i, keep), max(i, keep))))]
        if not others:
            continue
        k = _absorb(dict(cards[keep]), [cards[i] for i in others])
        k["same_event_sources"] = list(k.get("same_event_sources") or []) + [_ref(cards[i]) for i in others]
        k["dedupe"] = {**(k.get("dedupe") or {}), "same_event": [
            {"merged_source": cards[i].get("source_name"), "merged_url": cards[i].get("source_url"),
             **evidence[(min(i, keep), max(i, keep))]} for i in others]}
        out[keep] = k
        drop.update(others)
    return [c for i, c in enumerate(out) if i not in drop]


def apply(cards: list[dict]) -> list[dict]:
    return merge_same_event(collapse_bill_milestones(cards))
