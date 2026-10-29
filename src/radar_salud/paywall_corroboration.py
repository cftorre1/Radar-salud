"""Corroborate thin paywalled press with authorized open sources (Dirección, 28-oct-2026 15:16).

"Para las noticias de DF y Pulso, donde no podamos acceder, a partir del título
busquemos otras fuentes autorizadas donde sí podamos usar su contenido."

Rules (absolute):

* Only sources with ``status == "enabled"`` in config/corroboration_sources.json
  contribute text. Today every enabled source is ``corpus_only``: we reuse what
  Alicanto already captured; nothing is fetched here.
* Inputs from the paywalled piece are only its public title, public lead and date.
  The locked body is never read (we no longer have it).
* Matching is deterministic: shared entity or act ID, key-term recall, date
  proximity, and hard conflict checks (act IDs, amounts, places, opposite
  verbs). A cheap model check may only rule on *borderline* pairs, through
  ``ai_budget`` with a per-run cap, and only when a judge is injected.
* "Qué pasó" is a list of sentences copied from one field of the corroborating
  record, each with its source, field and the field's sha256, so every sentence
  is traceable. Nothing is generated. No match: the card stays title + lead.

Kept apart from source_rights internals: only its public helpers are used.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlsplit

from . import entity_watch
from .paths import project_root
from .source_rights import (clean_teaser, contains_fingerprinted, is_paywalled, load_fingerprints,
                            paywall_policy, sha256_text, teaser_from_raw)

CONFIG = Path("config/corroboration_sources.json")
CHECKED_AT = "2026-10-28"
_RUN = {"llm_calls": 0}


# --- registry ---------------------------------------------------------------

def load_registry(root: Path | str | None = None) -> dict[str, Any]:
    base = Path(root) if root else project_root()
    return json.loads((base / CONFIG).read_text(encoding="utf-8"))


def _host(url: str | None) -> str:
    try:
        return (urlsplit(str(url or "").strip()).hostname or "").lower()
    except ValueError:
        return ""


class Registry:
    def __init__(self, raw: dict[str, Any]):
        self.raw = raw
        self.matching = raw.get("matching") or {}
        self.sources = list(raw.get("sources") or [])
        self.enabled = [s for s in self.sources if s.get("status") == "enabled"]
        self.by_host: dict[str, dict] = {}
        self.by_slug: dict[str, dict] = {}
        for s in self.sources:  # any status: a rejected host must never resolve to an enabled source
            for h in s.get("hosts") or []:
                self.by_host.setdefault(h.lower(), s)
            for slug in s.get("source_slugs") or []:
                self.by_slug.setdefault(slug, s)
        self.issuers = [(s["id"], [re.compile(p) for p in s.get("issuer_patterns") or []]) for s in self.enabled]
        self.derived = [re.compile(p, re.I) for p in self.matching.get("derived_from_paywalled_patterns") or []]

    def source_for(self, url: str | None, slug: str | None = None) -> dict | None:
        """The registry entry for a record, or None. Host wins over slug."""
        entry = self.by_host.get(_host(url))
        if entry is None and slug:
            entry = self.by_slug.get(slug)
        return entry

    def enabled_source(self, url: str | None, slug: str | None = None) -> dict | None:
        entry = self.source_for(url, slug)
        return entry if entry and entry.get("status") == "enabled" else None


# --- features ---------------------------------------------------------------

def fold(text: Any) -> str:
    text = "".join(c for c in unicodedata.normalize("NFKD", str(text or "")) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip()


_STOP = set("""
a al algo ante antes aun bajo cada como con contra cual cuando de del desde donde dos e el ella ellas ellos en
entre era es esa ese eso esta este esto estos estas fue fueron ha han hasta hay la las le les lo los mas me mi
muy no nos o otra otro para pero por porque que quien se sea segun ser si sin sobre su sus tambien tan tras
tu un una uno unos unas y ya ano anos mes meses dia dias hoy ayer manana nuevo nueva nuevos nuevas primer
primera tras busca buscan sera seran podria puede pueden chile chilena chileno pais millones mil us usd uf clp
debido
""".split())
_STEM = 5
# Official long forms that press headlines abbreviate: one token for both spellings.
_ABBREVIATIONS = [(re.compile(r"\bsecretari[oa]s? regional(?:es)? ministerial(?:es)?\b"), "seremi")]


def terms(text: str) -> set[str]:
    out = set()
    folded = fold(text).casefold()
    for rx, short in _ABBREVIATIONS:
        folded = rx.sub(short, folded)
    for tok in re.findall(r"[a-z0-9ñ]+", folded):
        if len(tok) < 4 or tok in _STOP or tok.isdigit():
            continue
        out.add(tok[:_STEM])
    return out


_ACT = re.compile(r"\b(resoluci[oó]n exenta|res\.? ?ex\.?|resoluci[oó]n|circular|oficio|ord\.?|decreto|dictamen|"
                  r"ley|bolet[ií]n)\s*(?:[a-z]{1,4}\s*/\s*)?(?:n[°ºo.]?\s*)?(\d[\d.\-]*\d|\d)", re.I)
_ACT_KIND = {"ord": "oficio", "boletin": "boletin"}


def act_ids(text: str) -> set[str]:
    out = set()
    for kind, num in _ACT.findall(fold(text)):
        k = re.sub(r"[^a-z ]", "", kind.casefold()).strip()
        k = "resolucion" if k.startswith("res") else _ACT_KIND.get(k, k.split(" ")[0])
        # Boletín 18.255-31: the root number identifies the bill; the suffix is the committee code
        n = re.sub(r"[^\d]", "", num.split("-")[0] if k == "boletin" else num)
        # "ley 2026" or a 1-2 digit "ley 5" is not an act id; laws in force are 5 digits (21.xxx)
        if k == "ley" and len(n) != 5:
            continue
        out.add(f"{k}:{n}")
    return out


_SCALE = {"mil millones": 1e9, "millones": 1e6, "millon": 1e6, "mm": 1e6, "mil": 1e3}
_AMOUNT = re.compile(r"(us\$|usd|\$|uf|clp)?\s?(\d{1,3}(?:[.\s]\d{3})+|\d+(?:,\d+)?)\s*(mil millones|millones|millon|mm|mil)?\s*(%|por ciento)?",
                     re.I)


def amounts(text: str) -> set[tuple[str, float]]:
    """(unit, value) pairs for money and percentages. Bare numbers are ignored."""
    out = set()
    for cur, num, scale, pct in _AMOUNT.findall(fold(text).casefold()):
        if not cur and not pct:
            continue
        value = float(num.replace(".", "").replace(" ", "").replace(",", "."))
        unit = "%" if pct else {"usd": "us$", "clp": "$"}.get(cur, cur)
        value *= _SCALE.get(scale, 1.0)
        out.add((unit, round(value, 4)))
    return out


_OPPOSITES = [("abre", "cierr"), ("inaugur", "cierr"), ("aprueb", "rechaz"), ("aprob", "rechaz"),
              ("sube", "baja"), ("alza", "caida"), ("aument", "dismin"), ("compra", "vende"), ("adquier", "vende"),
              ("multa", "absuel"), ("gana", "pierde"), ("ganancia", "perdida")]


def _verbs(text: str) -> set[str]:
    words = re.findall(r"[a-z]+", fold(text).casefold())
    found = set()
    for a, b in _OPPOSITES:
        for w in words:
            if w.startswith(a):
                found.add(a)
            if w.startswith(b):
                found.add(b)
    return found


@dataclass
class Features:
    entities: set[str] = field(default_factory=set)
    acts: set[str] = field(default_factory=set)
    amounts: set[tuple[str, float]] = field(default_factory=set)
    places: set[str] = field(default_factory=set)
    terms: set[str] = field(default_factory=set)
    verbs: set[str] = field(default_factory=set)


def _mask_entities(text: str, catalog) -> str:
    folded = fold(text)
    for e in catalog:
        for rx, _ctx in e.patterns:
            folded = rx.sub(" ", folded)
    return folded


def places(text: str, registry: Registry, catalog=None) -> set[str]:
    masked = _mask_entities(text, catalog or entity_watch.load_catalog()).casefold()
    return {p for p in registry.matching.get("places") or []
            if re.search(r"\b" + re.escape(fold(p).casefold()) + r"\b", masked)}


def features(text: str, registry: Registry, own_source: dict | None = None, catalog=None) -> Features:
    catalog = catalog or entity_watch.load_catalog()
    ents = set(entity_watch.match_text(text, catalog))
    folded = fold(text)
    for sid, patterns in registry.issuers:
        if any(p.search(folded) for p in patterns):
            ents.add("src:" + sid)
    if own_source is not None and own_source.get("issuer_patterns"):
        ents.add("src:" + own_source["id"])
    return Features(entities=ents, acts=act_ids(text), amounts=amounts(text), places=places(text, registry, catalog),
                    terms=terms(text), verbs=_verbs(text))


# --- corpus -----------------------------------------------------------------

@dataclass
class Doc:
    url: str
    title: str
    text: str
    field: str
    source: dict
    source_name: str
    event_date: date | None
    origin: str
    feat: Features | None = None
    excluded: str | None = None
    parties: list[str] = field(default_factory=list)

    @property
    def attribution(self) -> str:
        label = self.source.get("attribution") or self.source_name
        return label.replace("{source_name}", self.source_name)


def _day(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def _doc_from_signal(row: dict, registry: Registry, origin: str) -> Doc | None:
    url = row.get("source_url")
    if row.get("paywalled") or is_paywalled(url, row) or row.get("df_duplicate_of"):
        return None
    source = registry.enabled_source(url, row.get("source_slug"))
    text = clean_teaser(row.get("what_happened"))
    if not source or not text or str(text).startswith("Contenido para suscriptores"):
        return None
    return Doc(url=url, title=clean_teaser(row.get("title")), text=text, field="what_happened", source=source,
               source_name=row.get("source_name") or source["name"], event_date=_day(row.get("event_date")),
               origin=origin, parties=[p.get("name") for p in row.get("fne_parties") or [] if p.get("name")])


def _doc_from_queue(item: dict, registry: Registry, statuses: set[str]) -> Doc | None:
    raw = item.get("raw") or {}
    if item.get("status") not in statuses:
        return None
    url = raw.get("url")
    md = raw.get("metadata") or {}
    if is_paywalled(url, md):
        return None
    source = registry.enabled_source(url, raw.get("source_slug"))
    text = clean_teaser(md.get("what_happened"))
    if not source or not text:
        return None
    return Doc(url=url, title=clean_teaser(md.get("article_title") or raw.get("title")), text=text,
               field="raw.metadata.what_happened", source=source,
               source_name=raw.get("source_name") or source["name"], event_date=_day(raw.get("event_date")),
               origin="data/state/pending_queue.json",
               parties=[p.get("name") for p in md.get("parties") or [] if p.get("name")])


def _docs_from_cmf(root: Path, registry: Registry) -> list[Doc]:
    source = next((s for s in registry.enabled if s["id"] == "cmf"), None)
    if not source:
        return []
    try:
        events = json.loads((root / "data/market/cmf_events.json").read_text(encoding="utf-8")).get("events") or []
        docs = json.loads((root / "data/market/cmf_disclosures.json").read_text(encoding="utf-8")).get("documents") or []
    except (OSError, ValueError):
        return []
    by_id = {d.get("record_id"): d for d in docs}
    out = []
    for ev in events:
        disc = next((by_id[r] for r in ev.get("primary_disclosures") or [] if r in by_id), None)
        url = (disc or {}).get("source_url")
        text = clean_teaser(ev.get("what_happened"))
        if not url or not text or _host(url) not in (source.get("hosts") or []):
            continue
        out.append(Doc(url=url, title=f"{clean_teaser(disc.get('issuer_name'))}: hecho esencial", text=text,
                       field="what_happened", source=source, source_name=source["name"],
                       event_date=_day(ev.get("event_date")), origin="data/market/cmf_events.json"))
    return out


def build_corpus(root: Path | str | None = None, registry: Registry | None = None,
                 signal_sets: Iterable[Iterable[dict]] = (), queue: dict | None = None) -> list[Doc]:
    """Authorized documents already captured. Explicit inputs win; otherwise read the repo files."""
    base = Path(root) if root else project_root()
    registry = registry or Registry(load_registry(base))
    statuses = set(registry.raw.get("corpus_statuses") or ["published", "archived"])
    if not signal_sets:
        sets = []
        for rel in ("data/history/superintendencia_signals.json", "web/data/radar_today.json"):
            try:
                sets.append((rel, json.loads((base / rel).read_text(encoding="utf-8")).get("signals") or []))
            except (OSError, ValueError):
                pass
    else:
        sets = [(f"input[{i}]", rows) for i, rows in enumerate(signal_sets)]
    if queue is None:
        try:
            queue = json.loads((base / "data/state/pending_queue.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            queue = {}
    docs: dict[str, Doc] = {}
    for origin, rows in sets:
        for row in rows:
            d = _doc_from_signal(row, registry, origin)
            if d and d.url not in docs:
                docs[d.url] = d
    for item in (queue or {}).values():
        d = _doc_from_queue(item, registry, statuses)
        if d and d.url not in docs:
            docs[d.url] = d
    for d in _docs_from_cmf(base, registry):
        docs.setdefault(d.url, d)
    return list(docs.values())


# --- matching ---------------------------------------------------------------

@dataclass
class Match:
    doc: Doc
    score: float
    shared_entities: list[str]
    shared_acts: list[str]
    shared_terms: list[str]
    day_gap: int
    conflicts: list[str]
    term_recall: float
    shared_amounts: list[str] = field(default_factory=list)
    shared_places: list[str] = field(default_factory=list)


class CorpusIndex:
    """Features computed once per authorized document, plus corpus term frequencies.

    A term shared by many documents ("salud", "licencias", "isapres") says nothing
    about *which* event; only distinctive terms (document frequency below
    ``distinctive_max_df``) count towards key-term overlap. Words that are part of
    an entity's name are covered by the entity match and are not counted twice.
    """

    def __init__(self, docs: list[Doc], registry: Registry, *, fingerprints: set | None = None, catalog=None):
        self.registry = registry
        self.catalog = catalog or entity_watch.load_catalog()
        fingerprints = load_fingerprints() if fingerprints is None else fingerprints
        self.docs = []
        self.party_rx: dict[str, re.Pattern] = {}
        for doc in docs:
            if any(rx.search(fold(doc.text)) for rx in registry.derived):
                doc.excluded = "derived_from_paywalled_press"  # not independent of the paywalled piece
            elif contains_fingerprinted(doc.text, fingerprints):
                doc.excluded = "contains_paywalled_body"
            doc.feat = features(f"{doc.title} {doc.text}", registry, own_source=doc.source, catalog=self.catalog)
            for name in doc.parties:  # FNE merging parties (Dirección 28-oct-2026 17:08)
                key = party_key(name)
                if key:
                    self.party_rx.setdefault(key, party_regex(key))
                    doc.feat.entities.add(key)
            self.docs.append(doc)
        counts: dict[str, int] = {}
        for doc in self.docs:
            for t in doc.feat.terms:
                counts[t] = counts.get(t, 0) + 1
        n = max(len(self.docs), 1)
        limit = float(registry.matching.get("distinctive_max_df", 0.02))
        floor = int(registry.matching.get("distinctive_min_count", 5))  # tiny corpora: nothing is "common"
        self.common = {t for t, c in counts.items() if c > max(limit * n, floor)}
        names = []
        for e in self.catalog:
            names += [e.name, *e.aliases]
        for src in registry.sources:
            names += [src.get("name") or "", src.get("attribution") or ""]
        self.name_terms = set().union(*(terms(x) for x in names)) if names else set()

    def parties_in(self, text: str) -> set[str]:
        folded = fold(text).casefold()
        return {k for k, rx in self.party_rx.items() if rx.search(folded)}

    def distinctive(self, ts: set[str]) -> set[str]:
        return {t for t in ts if t not in self.common and t not in self.name_terms}


_PARTY_GENERIC = {"grupo", "empresas", "holding", "fondo", "fondos", "sociedad", "inversiones", "chile", "clinica",
                  "laboratorio", "laboratorios", "farmacia", "farmacias", "isapre", "hospital"}


def party_key(name: str) -> str | None:
    """Entity key for a merging party named by the FNE ("party:rotter & krauss"), or None if too generic."""
    words = re.findall(r"[a-z0-9ñ&]+", fold(name).casefold())
    if not words or all(w in _PARTY_GENERIC or w in _STOP for w in words) or len("".join(words)) < 4:
        return None
    return "party:" + " ".join(words)


def party_regex(key: str) -> re.Pattern:
    words = key.split(":", 1)[1].split(" ")
    return re.compile(r"(?<![a-z0-9ñ])" + r"[\s.,\-]*".join(re.escape(w) for w in words) + r"(?![a-z0-9ñ])")


def _same_amount(a: float, b: float) -> bool:
    """Headlines round ("$80 mil millones" for CLP 80.119.759.016): 2% relative tolerance."""
    return a == b or (max(abs(a), abs(b)) > 0 and abs(a - b) / max(abs(a), abs(b)) <= 0.02)


def conflicts(p: Features, d: Features) -> list[str]:
    """Facts in the paywalled title/lead that the candidate states differently."""
    out = []
    # Only IDs of the same kind can disagree: a press "Ley 21.674" and a bill's
    # "boletín 18255" name different things, not different versions of one act.
    kinds = {a.split(":")[0] for a in p.acts} & {a.split(":")[0] for a in d.acts}
    if any(not ({a for a in p.acts if a.startswith(k + ":")} & {a for a in d.acts if a.startswith(k + ":")})
           for k in kinds):
        out.append("act_id")
    for unit, value in sorted(p.amounts):
        same_unit = {v for u, v in d.amounts if u == unit}
        if same_unit and not any(_same_amount(value, v) for v in same_unit):
            out.append(f"amount:{unit}{value:g}")
    if p.places and d.places and not (p.places & d.places):
        out.append("place")
    for a, b in _OPPOSITES:
        if (a in p.verbs and b in d.verbs and a not in d.verbs) or (b in p.verbs and a in d.verbs and b not in d.verbs):
            out.append(f"polarity:{a}/{b}")
    return out


def score_pair(p: Features, pdate: date | None, doc: Doc, d: Features, index: CorpusIndex) -> Match | None:
    m = index.registry.matching
    window = int(m.get("window_days", 7))
    if pdate is None or doc.event_date is None:
        return None
    gap = abs((doc.event_date - pdate).days)
    if gap > window:
        return None
    shared_e = sorted(p.entities & d.entities)
    shared_a = sorted(p.acts & d.acts)
    title_terms = index.distinctive(p.terms)
    shared_t = sorted(title_terms & d.terms)
    ent = 1.0 if shared_a else (len(shared_e) / len(p.entities) if p.entities else 0.0)
    shared_m = sorted(f"{u}{a:g}" for u, a in p.amounts if any(u == du and _same_amount(a, b) for du, b in d.amounts))
    # The headline's key facts are its distinctive terms plus, when the piece states one,
    # its figure: a stated amount counts once in the denominator, and once in the
    # numerator only if the candidate states the same amount.
    has_m = 1 if p.amounts else 0
    denom = len(title_terms) + has_m
    recall = (len(shared_t) + min(len(shared_m), 1)) / denom if denom else 0.0
    w = m.get("weights") or {"entity": 0.45, "terms": 0.35, "date": 0.2}
    score = w["entity"] * ent + w["terms"] * recall + w["date"] * (1 - gap / (window + 1))
    return Match(doc=doc, score=round(score, 4), shared_entities=shared_e, shared_acts=shared_a,
                 shared_terms=shared_t, day_gap=gap, conflicts=conflicts(p, d), term_recall=round(recall, 3),
                 shared_amounts=shared_m, shared_places=sorted(p.places & d.places))


# Words that name a health-policy *topic*, not an event: "listas de espera",
# "permiso", "licencias", "plan", "programa"... An issuer's own press room uses
# them every week, so sharing them with a headline proves nothing (review of
# 28-oct-2026: Colmed/Chomali on waiting lists matched a Minsal-cajas convenio;
# a parental-leave bill matched "Ley Mila a cinco años"). Stored as 5-letter
# stems, like ``terms``; config ``matching.generic_terms`` adds to this list.
GENERIC_TERMS = frozenset(t[:_STEM] for t in """
lista listas espera esperas tiempo tiempos permiso permisos licencia licencias salud sanitario sanitaria ministerio
ministro ministra plan planes programa programas proyecto proyectos gobierno sistema servicio servicios medida
medidas paciente pacientes hospital hospitales atencion medico medicos medica publico publica publicos politica
politicas reforma anuncio anuncia anuncian avance avances balance cifras datos informe nacional regional
""".split())


def _generic(registry: Registry) -> set[str]:
    return set(GENERIC_TERMS).union(*(terms(t) for t in registry.matching.get("generic_terms") or []))


def specific_terms(match: Match, registry: Registry) -> list[str]:
    """Shared distinctive terms that name the event, not the policy topic."""
    generic = _generic(registry)
    return [t for t in match.shared_terms if t not in generic]


def _eligible(match: Match, registry: Registry) -> bool:
    """Hard gates before any score, applied to *every* candidate (primary and extra related sources).

    * No conflicting fact, and title-term recall at least ``min_title_term_recall``.
    * A shared act ID is enough.
    * An issuer tag ("src:minsal": the title names the Ministerio) is the weakest
      anchor. When it is the only shared entity, the pair also needs a shared named
      entity outside the issuer (company, person, merging party), a shared place, a
      shared amount or figure, or at least ``min_distinctive_terms`` shared terms that
      are not on the generic stoplist (``GENERIC_TERMS``).
    * Two named catalog entities (e.g. Indisa and Achs) need one distinctive term;
      a single named entity needs ``min_distinctive_terms`` (an amount counts as one).
    """
    m = registry.matching
    if match.conflicts or match.term_recall < float(m.get("min_title_term_recall", 0.3)):
        return False
    if match.shared_acts:
        return True
    if not match.shared_entities:
        return False
    need_terms = int(m.get("min_distinctive_terms", 2))
    named = [e for e in match.shared_entities if not e.startswith("src:")]
    if not named:
        # Issuer-only anchor: event-specific evidence is mandatory.
        if match.shared_places or match.shared_amounts:
            return True
        return len(specific_terms(match, registry)) >= need_terms
    need = 1 if len(named) >= 2 else need_terms
    return len(match.shared_terms) + min(len(match.shared_amounts), 1) >= need


# --- borderline model check -------------------------------------------------

Judge = Callable[[dict, dict], dict]


def _llm_allowed(registry: Registry) -> bool:
    cfg = registry.matching.get("llm_check") or {}
    if not cfg.get("enabled"):
        return False
    cap = int(os.getenv(cfg.get("per_run_env", "RADAR_CORROBORATION_LLM_PER_RUN"), cfg.get("per_run_default", 5)))
    if _RUN["llm_calls"] >= cap:
        return False
    from . import ai_budget
    if not ai_budget.allow_call(cfg.get("budget_kind", "fast")):
        return False
    _RUN["llm_calls"] += 1
    return True


def _llm_check(item: dict, match: Match, registry: Registry, judge: Judge | None) -> bool | None:
    """True/False from the injected judge, None when no call was made."""
    if judge is None or not _llm_allowed(registry):
        return None
    from . import ai_budget
    kind = (registry.matching.get("llm_check") or {}).get("budget_kind", "fast")
    try:
        verdict = judge({"title": item["title"], "lead": item["teaser"], "date": str(item["date"])},
                        {"title": match.doc.title, "text": match.doc.text, "date": str(match.doc.event_date),
                         "source": match.doc.source_name})
    except Exception:  # a failed check never accepts
        ai_budget.record_result(kind, False)
        return None
    ai_budget.record_result(kind, True)
    return bool(isinstance(verdict, dict) and verdict.get("same_event") is True and verdict.get("overlap"))


# --- "Qué pasó" ---------------------------------------------------------------

_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿¡\"«“(0-9])")
_ABBREV = re.compile(r"(?:\b(?:Dra?|Sra?|Srta|Sres|Av|Nº|N°|Art|Arts|Inc|Ltda|Cía|Hno|Ing|Prof|Mons|Gral|St|S\.A|S\.p\.A)|\b[A-ZÁÉÍÓÚ])\.$")


def sentences(text: str) -> list[str]:
    """Split on sentence ends, never after an abbreviation ("Dra.", "N°.", "S.A.") or an initial."""
    out: list[str] = []
    for part in _SENT.split(clean_teaser(text)):
        part = part.strip()
        if not part:
            continue
        if out and _ABBREV.search(out[-1]):
            out[-1] = f"{out[-1]} {part}"
        else:
            out.append(part)
    return out


def what_from(doc: Doc, limit: int) -> list[dict]:
    """Whole sentences from the corroborating field, up to ``limit`` characters. Never cut a sentence."""
    out, used = [], 0
    digest = sha256_text(doc.text)
    for s in sentences(doc.text):
        if used + len(s) > limit:
            break
        out.append({"text": s, "attribution": doc.attribution, "source_name": doc.source_name,
                    "source_url": doc.url, "field": doc.field, "origin": doc.origin, "field_sha256": digest,
                    "kind": "excerpt" if doc.source.get("excerpt_allowed") and doc.field != "what_happened"
                    else "alicanto_summary_of_authorized_source"})
        used += len(s) + 1
    return out


def render_what(what: list[dict]) -> str:
    """Plain-text 'Qué pasó' with attribution on every sentence group (UI renders the same)."""
    groups: list[tuple[str, list[str]]] = []
    for w in what:
        if groups and groups[-1][0] == w["attribution"]:
            groups[-1][1].append(w["text"])
        else:
            groups.append((w["attribution"], [w["text"]]))
    return " ".join(f"Según {a}: {' '.join(ts)}" for a, ts in groups)


# --- main entry points ------------------------------------------------------

def paywalled_item(row: dict, *, raw: dict | None = None) -> dict | None:
    """Public view of a paywalled record: title, lead, date, url. Body never read."""
    if raw is not None:
        url, md = raw.get("url"), raw.get("metadata") or {}
        rule = paywall_policy(url, md, raw.get("source_slug"))
        if not rule:
            return None
        return {"title": clean_teaser(md.get("article_title") or raw.get("title")), "teaser": teaser_from_raw(raw),
                "date": _day(raw.get("event_date")), "url": url, "paywall_name": rule["name"]}
    rule = paywall_policy(row.get("source_url"), row)
    if not rule:
        return None
    return {"title": clean_teaser(row.get("title")), "teaser": clean_teaser(row.get("public_teaser")),
            "date": _day(row.get("event_date")), "url": row.get("source_url"), "paywall_name": rule["name"]}


def is_thin(item: dict, registry: Registry) -> bool:
    return len(item.get("teaser") or "") < int(registry.matching.get("thin_teaser_characters", 200))


def corroborate(item: dict, index: CorpusIndex, *, judge: Judge | None = None) -> dict:
    """Corroboration block for one paywalled item (title + public lead + date)."""
    registry = index.registry
    m = registry.matching
    pf = features(f"{item['title']} {item.get('teaser') or ''}", registry, catalog=index.catalog)
    pf.terms = terms(item["title"])  # recall is measured on the headline: the lead may be a quote
    pf.entities |= index.parties_in(f"{item['title']} {item.get('teaser') or ''}")
    original = f"Fuente original: {item.get('paywall_name') or 'prensa con muro de pago'} (contenido para suscriptores)"
    base = {"status": "none", "checked_at": CHECKED_AT, "original_label": original, "what": [], "related_sources": []}
    matches = []
    window = int(m.get("window_days", 7))
    for doc in index.docs:
        if doc.excluded or doc.url == item.get("url") or item.get("date") is None or doc.event_date is None:
            continue
        if abs((doc.event_date - item["date"]).days) > window:
            continue
        mt = score_pair(pf, item.get("date"), doc, doc.feat, index)
        if mt and _eligible(mt, registry):
            matches.append(mt)
    matches.sort(key=lambda x: (-x.score, x.day_gap, x.doc.url))
    accepted = [x for x in matches if x.score >= float(m.get("accept_score", 0.62))]
    method = "deterministic"
    if not accepted:
        border = [x for x in matches if x.score >= float(m.get("borderline_score", 0.45))]
        if border:
            verdict = _llm_check(item, border[0], registry, judge)
            if verdict:
                accepted, method = [border[0]], "llm_check"
            else:
                base.update(status="borderline_review", candidates=[_related(x) for x in border[:3]])
                return base
    if not accepted:
        return base
    accepted = accepted[: int(m.get("max_related_sources", 3))]
    what = []
    for x in accepted:
        what = what_from(x.doc, int(m.get("max_what_characters", 300)))
        if what:
            break
    base.update(status="corroborated" if what else "related_only", method=method, what=what,
                related_sources=[_related(x) for x in accepted])
    return base


def _related(x: Match) -> dict:
    return {"title": x.doc.title, "source_name": x.doc.source_name, "url": x.doc.url,
            "event_date": x.doc.event_date.isoformat() if x.doc.event_date else None,
            "score": x.score, "day_gap": x.day_gap,
            "matched_on": {"entities": x.shared_entities, "acts": x.shared_acts, "terms": x.shared_terms,
                           "amounts": x.shared_amounts, "places": x.shared_places}}


def apply(cards: list[dict], root: Path | str | None = None, *, corpus: list[Doc] | None = None,
          registry: Registry | None = None, judge: Judge | None = None, history: Iterable[dict] = ()) -> list[dict]:
    """Attach ``corroboration`` to thin paywalled cards. Other cards are returned unchanged.

    Must run *after* source_rights.redact_signal: it only adds a separate field and
    never touches title, public_teaser or what_happened.
    """
    base = Path(root) if root else project_root()
    registry = registry or Registry(load_registry(base))
    targets = [(i, paywalled_item(c)) for i, c in enumerate(cards)]
    targets = [(i, it) for i, it in targets if it and is_thin(it, registry)]
    if not targets:
        return cards
    if corpus is None:
        corpus = build_corpus(base, registry, signal_sets=[cards, list(history)] if history else [cards])
    index = CorpusIndex(corpus, registry, fingerprints=load_fingerprints(base))
    out = list(cards)
    for i, it in targets:
        block = corroborate(it, index, judge=judge)
        if block["status"] in ("corroborated", "related_only"):
            out[i] = {**cards[i], "corroboration": block}
    return out
