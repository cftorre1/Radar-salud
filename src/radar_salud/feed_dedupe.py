"""One card per event in the Chile feed (Dirección 3-nov-2026: "algunas noticias … están duplicadas").

Two deterministic collapses, applied to the curated snapshot cards (``scripts/export_web_snapshot.py``):

1. ``collapse_bill_milestones``: the Senate open-data source emits one card per milestone (#hito-<kind>-<date>). The
   cards of one bill (``bill_boletin``) become one: the latest milestone (date, then legislative order) stays as the
   card; the others are listed in ``bill_history`` ("Trámites de este proyecto"). Nothing is rewritten.
2. ``merge_same_event``: the same event reported by different outlets (e.g. a Minsal release and the La Tercera piece
   about it, same day). Two news cards are the same event only when ALL hold: different sources, event dates at most
   ``MAX_DAYS`` apart, ≥ ``MIN_SHARED`` shared title terms, the same WATCH entities when both cards name any, and
   EITHER the same figures in both titles, ≥ ``MIN_FIGURES`` of them ('44 mil … 140 mil'), with Jaccard ≥
   ``MIN_JACCARD`` OR the same title word for word (case, accents and punctuation aside). One shared round figure ('500 UF', '20%') or one differing name ('Colmena' / 'Cruz
   Blanca', 'Viña del Mar' / 'Concepción') is not the same event: the two reviews of PR #135 broke every looser rule.
   Normative records,
   bills, statistics fichas, syntheses and other aggregates never merge. The kept card is the official one (else the
   open one, else the earliest); the others go to ``same_event_sources`` ("También informaron"), title and link only.

3. ``group_act_series`` (Dirección 4-nov-2026): the same act issued the same day for several health services — e.g.
   'Res. exenta CP 14.658/2026 · Aprueba actualización de Arsenal Farmacológico …, del Servicio de Salud Araucanía
   Norte' and 'Res. exenta CP 24.861/2026 · Actualiza Arsenal Farmacológico …, del Servicio de Salud Araucanía Sur'.
   They are different acts, so nothing is merged away: one grouped card names every act number and every service,
   and its ficha lists each act with its own link (``group_items``, "Actos incluidos"). Grouped only when: Diario
   Oficial, same day, same kind of act, an operative text that ends in ', del Servicio de Salud <X>', the same text
   before it (once 'aprueba actualización de' reads as 'actualiza'), and a different service in each act.

Both are conservative: when in doubt the cards stay separate. Every merge is recorded in ``dedupe`` on the kept card.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date

MAX_DAYS = 1  # review 4 of #135: a recurring headline two days later is a new report
MIN_SHARED = 3
MIN_JACCARD = 0.35
MIN_FIGURES = 2

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


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKD", str(text or "").casefold()).encode("ascii", "ignore").decode()


NUM = r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?"
IDENT = re.compile(r"\b(ley|n|no|nro|numero|boletin|decreto|ds|dfl|resolucion|exenta|circular|oficio)\W{0,3}$")


def figures(title: str) -> set[str]:
    """Every figure of a title, whole ('$1.200 millones' → '1200', '3,5%' → '3,5', '4 muertes' → '4'), except years
    and identifiers ('Ley 21.063', 'Boletín 18803', 'N° 12'), which are names, not figures (review 3 of #135)."""
    t = _fold(title)
    out = set()
    for m in re.finditer(NUM, t):
        if IDENT.search(t[:m.start()]) or (m.end() < len(t) and t[m.end()] == "-") or t[max(m.start() - 1, 0):m.start()] == "-":
            continue
        v = m.group().replace(".", "")
        if not re.fullmatch(r"(19|20)\d\d", v):
            out.add(v)
    return out


def terms(title: str) -> set[str]:
    """Significant title terms: words of 4+ letters (first 7 letters, accents folded) and the title's figures."""
    out = set(figures(title))
    for w in re.findall(r"[a-z]+", _fold(title)):
        if len(w) > 3 and w not in STOP:
            out.add(w[:7])
    return out


def names(title: str) -> set[str]:
    """Name-like words of a title: capitalized words and acronyms ('Colmena', 'Banmédica', 'VIH', 'Temuco'), folded,
    except opening quote/punctuation artefacts and generic words (STOP)."""
    out = set()
    for w in re.findall(r"[A-ZÁÉÍÓÚÑ][\wáéíóúñü]+", str(title or "")):
        f = _fold(w)
        if len(f) >= 3 and f not in STOP:
            out.add(f)
    return out


def _text(card: dict) -> str:
    return _fold(" ".join(str(card.get(k) or "") for k in ("display_title", "title", "what_happened")))


def name_conflict(a: dict, b: dict) -> list[str]:
    """Names of one card that the other card's title and lead never mention: a different actor, place, drug or illness
    (review 3 of #135: 'Colmena' / 'Banmédica', 'VIH' / 'VRS', 'Viña del Mar' / 'Concepción')."""
    words_a, words_b = set(re.findall(r"[a-z0-9]+", _text(a))), set(re.findall(r"[a-z0-9]+", _text(b)))
    return sorted({n for n in names(_title(a)) if n not in words_b} | {n for n in names(_title(b)) if n not in words_a})


def same_words(a: str, b: str) -> bool:
    """The same title, word for word, ignoring case, accents and punctuation (every digit and acronym counts)."""
    return re.findall(r"[a-z0-9]+", _fold(a)) == re.findall(r"[a-z0-9]+", _fold(b))


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
    if ea and eb and ea != eb:
        return None  # both name WATCH entities and not the same ones: possibly different actors (review 2 of #135)
    if name_conflict(a, b):
        return None
    fa, fb = figures(_title(a)), figures(_title(b))
    figs = fa & fb
    # Figures path: ≥2 shared figures and no figure in one title only ('3 muertes' / '4 muertes' never match).
    # Single-digit figures ('2 muertes') must agree but never count toward the minimum (review 4 of #135).
    by_figures = len({f for f in figs if len(f.split(",")[0]) >= 2}) >= MIN_FIGURES and fa == fb and jac >= MIN_JACCARD
    identical = same_words(_title(a), _title(b))
    if not (by_figures or identical):
        return None
    return {"shared_terms": sorted(shared), "shared_figures": sorted(figs), "jaccard": round(jac, 3),
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


# ---------------------------------------------------------------------------------------------------------------
# 3. One act, several health services (Diario Oficial)

ACT_TITLE = re.compile(r"^(?P<kind>.+?) (?P<num>(?:[A-Z]{1,3} )?\d[\d.]*)/(?P<year>\d{4}) · (?P<op>.+)$")
SERVICE_TAIL = re.compile(r"^(?P<core>.+?),? del Servicio de Salud (?P<svc>[^,.;·]+?)\.?$")
VERB_SYNONYMS = (("aprueba actualizacion de ", "actualiza "),)


def act_parts(card: dict) -> dict | None:
    """(kind, number, year, operative core, service) of a Diario Oficial act title, or None."""
    if card.get("source_name") != "Diario Oficial" or card.get("stats_ficha") or card.get("group_items"):
        return None
    m = ACT_TITLE.match(_title(card).strip())
    if not m:
        return None
    t = SERVICE_TAIL.match(m["op"].strip())
    if not t:
        return None
    core = " ".join(_fold(t["core"]).split())
    for a, b in VERB_SYNONYMS:
        if core.startswith(a):
            core = b + core[len(a):]
    return {"kind": m["kind"], "num": m["num"], "year": m["year"], "op": t["core"].strip(), "core": core,
            "service": t["svc"].strip()}


def _join(xs: list[str]) -> str:
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " y " + xs[-1]


def group_act_series(cards: list[dict]) -> list[dict]:
    buckets: dict[tuple, list[int]] = {}
    for i, c in enumerate(cards):
        p = act_parts(c)
        if p:
            buckets.setdefault((c.get("event_date"), _fold(p["kind"]), p["year"], p["core"]), []).append(i)
    drop: set[int] = set()
    out = list(cards)
    for idx in buckets.values():
        parts = [act_parts(cards[i]) for i in idx]
        services = [p["service"] for p in parts]
        if len(idx) < 2 or len(set(_fold(x) for x in services)) != len(services):
            continue
        order = sorted(range(len(idx)), key=lambda k: parts[k]["num"])
        members = [cards[idx[k]] for k in order]
        ps = [parts[k] for k in order]
        first = dict(members[0])
        kind, year = ps[0]["kind"], ps[0]["year"]
        # Object of the act, without its verb: every act in the group does it; the kinds' own words are kept.
        obj = re.sub(r"^(?:aprueba actualización de|aprueba actualizacion de|actualiza)\s+", "", ps[0]["op"], flags=re.I)
        obj = obj[:1].upper() + obj[1:]
        nums = _join([p["num"] for p in ps])
        # The services go before the object: they are what tells these acts apart, and a long title is clamped in the feed.
        title = f"{kind} {nums}/{year} · Servicios de Salud {_join([p['service'] for p in ps])} · {obj}"
        whats = [f"{_title(m).split(' · ')[0]} (Servicio de Salud {p['service']}): {m.get('what_happened') or m.get('card_what') or ''}".rstrip(': ')
                 for m, p in zip(members, ps)]
        first.update(title=title, display_title=title, short_title=title, source_title_full=title,
                     # One paragraph per act in the ficha ('Qué pasó' renders what_happened, then each key point).
                     what_happened=whats[0], key_points=whats[1:], key_facts=[], card_what=None, card_why=None,
                     # Each act's own reason, kept (the feed's publication contract requires one; the ficha omits it).
                     why_it_matters=" ".join(str(m.get("why_it_matters") or m.get("card_why") or "").strip()
                                             for m in members).strip() or None,
                     group_items=[_ref(m) for m in members],
                     source_documents=[d for m in members for d in (m.get("source_documents") or [])])
        first["dedupe"] = {"rule": "act_series", "acts": [p["num"] for p in ps], "services": [p["service"] for p in ps]}
        out[idx[order[0]]] = _absorb(first, members[1:])
        drop.update(idx[k] for k in order[1:])
    return [c for i, c in enumerate(out) if i not in drop]


def apply(cards: list[dict]) -> list[dict]:
    return group_act_series(merge_same_event(collapse_bill_milestones(cards)))
