"""Weekly Insight anchored on a statistics-family release (Dirección, 2-nov-2026).

Part of the Monday format-A pipeline (``weekly_insight_a``); it does not publish on its own.

Decision (``config/weekly_insight_stats_anchor_v1.json``):

* **Selection.** A statistics-family ficha (F1 Cartera, F2 FEFI, F4 GES, F6 Boletín IP) with a NEW period
  that passes verification is the primary candidate when Alicanto **first verified** that period in the
  7 days before the Monday and the SIS publication is at most ``sis_max_age_days`` (30) old on the Monday
  (Dirección 2-nov, decision 1). The first-verification time comes from the live ficha
  (``first_verified_at``, stamped by ``stats_fichas.publish``) or, for fichas published before the stamp
  existed, from the git history of the live file (the ``generated_at`` of the first committed PASS version
  of the same ``release_key``). Both dates go into the selection reason.
  Ties go by materiality: a crossed threshold or a featured ficha ranks above a plain new period;
  then the most recent SIS publication; then the family order of the config.
* **Ficha vs. Insight.** The ficha is the news with its own data. The Insight crosses the anchor
  release with other material from the last 90 days (other fichas, normativa, sanciones, Congreso,
  FNE, Global themes, press) and offers a thesis and what to watch. It must not repeat the ficha.
* **Contract** (``contract_check``), all deterministic:
  1. at least 2 distinct cross-reference sources, from the brief, linked and attributed;
  2. at most 2 anchor figures, each among the brief's allowed figures (traced to ficha refs);
  3. every displayed figure traced to a named source (``figure_sources``) or to a recomputed estimate;
  4. no paragraph that only restates ficha figures and vocabulary;
  5. v1: a "Tesis" section (``essay.reading``) and a "Qué mirar" section (≥ 2 items); v2 essay (Dirección
     10-nov-2026): a closing of ≥ 40 words that states the thesis and what to watch, in prose;
  6. no sentence with stem Jaccard ≥ threshold against a ficha sentence, headline or dek.
  If the plan cannot meet item 1 before drafting, or the draft fails the contract, the pipeline
  falls back to the normal topic selection instead of publishing a weak Insight (decision 2, kept:
  a second draft on the normal topic inside the same ``MAX_RUN_USD`` cap).
* **Editorial gate** (decision 3). Insights written by editorial sessions must use the brief and record a
  passing contract check (``write_contract_record``); ``contract_gate`` fails CI when an Insight anchored
  on a stats ficha has no valid record. Insights on a normal topic are not affected.

Nothing here calls a model or the network. ``build_brief`` produces the structured brief for a
human or session drafter (anchor, cross-references with links, allowed figures, contract).
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import unicodedata
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from . import lectura_verifier as lv
from . import stats_fichas as sf
from .weekly_freshness import MONDAY_EVIDENCE_DAYS, displayed_texts, iso_day, number_traces, numbers_in, chart_values
from . import weekly_insight_essay as essay_v2

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = Path("config/weekly_insight_stats_anchor_v1.json")
RULE_ID = "stats_anchor_v1"
SANTIAGO = ZoneInfo("America/Santiago")
SIS_MAX_AGE_DAYS = 30


# ---------------------------------------------------------------------------------------------
# Config and small helpers


def load_config(root: Path = ROOT) -> dict:
    try:
        return json.loads((Path(root) / CONFIG_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"enabled": False, "missing": True}


def _registry(root: Path) -> dict:
    try:
        return sf.load_registry(Path(root) / "config/stats_fichas_v1.json")
    except (OSError, ValueError):
        return {"families": {}}


def fold(text: Any) -> str:
    s = unicodedata.normalize("NFKD", str(text or "")).casefold()
    return "".join(c for c in s if not unicodedata.combining(c))


def _day(value: Any) -> date | None:
    return iso_day(str(value)[:10]) if value else None


def _https(url: Any) -> bool:
    return isinstance(url, str) and url.startswith("https://") and len(url) > 12


def keyword_hits(text: str, keywords: list[str]) -> list[str]:
    folded = fold(text)
    return sorted({k for k in keywords if re.search(r"(?<![a-z0-9])" + re.escape(fold(k)) + r"(?![a-z0-9])", folded)})


def _numbers(text: str) -> set[float]:
    return {abs(v) for _, v, _ in numbers_in(text)}


def ficha_texts(ficha: dict) -> list[str]:
    return sf.displayed_texts(ficha)


def ficha_number_pool(ficha: dict) -> list[float]:
    """Every value the ficha's evidence package or its displayed text holds."""
    ev = ficha.get("evidence") or {}
    pool = set(sf.number_pool(ev))
    for key in ("lectura_pool", "derived_ratios"):
        for e in ev.get(key) or []:
            v = e.get("value") if isinstance(e, dict) else None
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                pool.add(abs(float(v)))
    for text in ficha_texts(ficha):
        pool |= _numbers(text)
    return sorted(pool)


def _traces(value: float, decimals: int, pool) -> bool:
    return number_traces(value, decimals, list(pool))


# ---------------------------------------------------------------------------------------------
# 1. Selection rule


def _ficha_brief(ficha: dict) -> dict:
    src = next((s for s in ficha.get("sources") or [] if _https(s.get("url"))), {})
    return {"ficha_id": ficha.get("id"), "family": ficha.get("family"), "family_label": ficha.get("family_label"),
            "period": ficha.get("period"), "published_at": ficha.get("published_at"), "headline": ficha.get("headline"),
            "dek": ficha.get("dek"), "url": src.get("url"), "source_label": src.get("label"),
            "featured": bool(ficha.get("featured")), "triggers": list(ficha.get("triggers") or [])}


def materiality(ficha: dict) -> tuple[int, str]:
    if "threshold_crossed" in (ficha.get("triggers") or []) or ficha.get("featured"):
        why = "umbral cruzado" if "threshold_crossed" in (ficha.get("triggers") or []) else "ficha destacada"
        return 2, why
    return 1, "período nuevo sin umbral cruzado"


def local_day(value: Any) -> date | None:
    """Chile calendar day of an ISO date or timestamp (UTC when the timestamp has no offset)."""
    if not value:
        return None
    text = str(value)
    if len(text) <= 10:
        return iso_day(text[:10])
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return iso_day(text[:10])
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(SANTIAGO).date()


def _git(root: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def _is_pass(ficha: dict) -> bool:
    return ficha.get("status") == "PASS" and (ficha.get("verification") or {}).get("verdict") == "PASS"


@lru_cache(maxsize=64)
def _git_first_pass(root: str, rel: str, release_key: str) -> tuple | None:
    top = _git(Path(root), "rev-parse", "--show-toplevel")
    if not top or Path(top.strip()).resolve() != Path(root).resolve():
        return None  # not this repository's history (e.g. a temporary test root)
    shallow = (_git(Path(root), "rev-parse", "--is-shallow-repository") or "").strip() == "true"
    log = _git(Path(root), "log", "--reverse", "--format=%H %cI", "--", rel) or ""
    for line in log.splitlines():
        sha, _, committed = line.partition(" ")
        body = _git(Path(root), "show", f"{sha}:{rel}")
        try:
            old = json.loads(body) if body else None
        except ValueError:
            continue
        if isinstance(old, dict) and old.get("release_key") == release_key and _is_pass(old):
            return (old.get("first_verified_at") or old.get("generated_at") or committed, sha[:12], committed, shallow)
    return None


def first_verified(ficha: dict, root: Path) -> dict:
    """When Alicanto first verified (PASS) this release, and on what record that rests.

    1. ``first_verified_at`` in the live ficha (stamped by ``stats_fichas.publish`` on the first PASS);
    2. the git history of the live file: ``generated_at`` of the first committed PASS version of the same
       ``release_key`` (a shallow clone only sees part of the history and says so in the basis);
    3. the live ficha's ``generated_at``, an upper bound (a later rebuild of the same release moves it);
    4. the SIS ``published_at`` when nothing else exists (lower bound)."""
    if ficha.get("first_verified_at"):
        return {"at": str(ficha["first_verified_at"]), "basis": "ficha.first_verified_at"}
    slug = ficha.get("slug")
    if slug and ficha.get("release_key"):
        hit = _git_first_pass(str(Path(root).resolve()), f"data/stats_fichas/live/{slug}.json", str(ficha["release_key"]))
        if hit:
            at, sha, committed, shallow = hit
            return {"at": str(at), "basis": f"git_history:{sha}" + (":shallow" if shallow else ""), "committed_at": committed}
    if ficha.get("generated_at"):
        return {"at": str(ficha["generated_at"]), "basis": "ficha.generated_at (cota superior: sin registro de primera verificación)"}
    return {"at": str(ficha.get("published_at") or ""), "basis": "published_at (sin registro de verificación)"}


def stats_anchor_candidates(root: Path, anchor: date, cfg: dict, registry: dict | None = None,
                            previous_anchor_id: str | None = None) -> list[dict]:
    """All configured families with the reason each is (or is not) eligible, eligible ones ranked first.

    "New in the week" (Dirección 2-nov, decision 1): the day Alicanto first verified the period falls in
    [Monday − window, Monday) and the SIS publication is at most ``sis_max_age_days`` old on the Monday."""
    registry = registry if registry is not None else _registry(root)
    window = int(cfg.get("window_days") or MONDAY_EVIDENCE_DAYS)
    max_age = int(cfg.get("sis_max_age_days") or SIS_MAX_AGE_DAYS)
    order = list(cfg.get("families") or [])
    out = []
    for fam in order:
        fcfg = (registry.get("families") or {}).get(fam)
        rec: dict = {"family": fam, "eligible": False}
        if not fcfg:
            out.append({**rec, "reason": "family_not_in_registry"})
            continue
        ficha = sf.load_live(Path(root), fcfg["slug"])
        if not ficha:
            out.append({**rec, "reason": "no_live_ficha"})
            continue
        rec.update(_ficha_brief(ficha))
        published = _day(ficha.get("published_at"))
        fv = first_verified({**ficha, "slug": ficha.get("slug") or fcfg["slug"]}, root)
        verified = local_day(fv["at"])
        age = (anchor - published).days if published else None
        rec.update(sis_published_at=ficha.get("published_at"), first_verified_at=fv["at"],
                   first_verified_day=verified.isoformat() if verified else None, first_verified_basis=fv["basis"],
                   sis_age_days=age)
        reasons = []
        if ficha.get("family") != fam:
            reasons.append("family_mismatch")
        if not _is_pass(ficha):
            reasons.append("not_verified_pass")
        if (ficha.get("reconciliation") or {}).get("ok") is False:
            reasons.append("reconciliation_fail")
        if "new_period" not in (ficha.get("triggers") or []):
            reasons.append("not_a_new_period")
        if not verified or not (anchor - timedelta(days=window) <= verified < anchor):
            reasons.append(f"first_verified_outside_week:{rec['first_verified_day']}")
        if age is None or age < 0 or age > max_age:
            reasons.append(f"sis_publication_older_than_{max_age}d:{ficha.get('published_at')}({age}d)")
        if not rec.get("url"):
            reasons.append("no_https_source")
        if previous_anchor_id and ficha.get("id") == previous_anchor_id:
            reasons.append("anchored_last_week")
        level, why = materiality(ficha)
        rec.update(materiality_level=level, materiality=why, ficha=ficha)
        if reasons:
            out.append({**rec, "reason": ",".join(reasons)})
            continue
        rec.update(eligible=True, reason=(
            f"{fam} tiene un período nuevo ({ficha.get('period')}): la SIS lo publicó el {ficha.get('published_at')} "
            f"({age} días antes del lunes, tope {max_age}) y Alicanto lo verificó por primera vez el "
            f"{rec['first_verified_day']} (registro: {fv['basis']}), dentro de los {window} días previos al lunes "
            f"{anchor.isoformat()}, con verificación y conciliación PASS; materialidad {level}: {why}."))
        out.append(rec)
    rank = {f: i for i, f in enumerate(order)}
    eligible = [r for r in out if r["eligible"]]
    eligible.sort(key=lambda r: (-r["materiality_level"], -(_day(r["published_at"]) or date.min).toordinal(),
                                 rank.get(r["family"], 99)))
    return eligible + [r for r in out if not r["eligible"]]


# ---------------------------------------------------------------------------------------------
# 2. Cross-reference candidates (last 90 days, our data only)


def _signal_text(s: dict) -> str:
    return " ".join(str(s.get(k) or "") for k in ("title", "display_title", "what_happened", "card_what",
                                                   "why_it_matters", "card_why"))


def classify(s: dict) -> str:
    name, title = fold(s.get("source_name")), fold(s.get("title"))
    types = {fold(t) for t in s.get("signal_types") or []}
    etype = str(s.get("event_type") or "").upper()
    if "fiscalia nacional economica" in name or re.search(r"\bfne\b", name + " " + title):
        return "fne"
    if "congreso" in name or "senado" in name or "camara de diputad" in name or "proyecto de ley" in title:
        return "congreso"
    if etype.startswith("SANCTION") or "fiscalizacion" in types:
        return "sancion"
    if "normativa" in types or etype in {"REGULATION", "LAW_OR_POLICY_CHANGE"} or "legal" in types:
        return "normativa"
    if "licencia" in title or "suseso" in name:
        return "licencias"
    if str(s.get("source_type") or "").startswith("press"):
        return "prensa"
    return "noticia"


def _signal_brief(s: dict) -> dict:
    return {"title": s.get("display_title") or s.get("title"), "source_name": s.get("source_name"),
            "source_type": s.get("source_type"), "url": s.get("source_url"), "event_date": s.get("event_date"),
            "what": s.get("card_what") or s.get("what_happened"), "why": s.get("card_why") or s.get("why_it_matters"),
            **{k: s[k] for k in ("key_numbers",) if s.get(k)}}


def _excluded_signal(s: dict) -> bool:
    decision = fold(s.get("editorial_decision") or s.get("editorial_source_decision") or "accept")
    return (s.get("feed_visibility") is False or bool(s.get("editorial_hold")) or bool(s.get("hold"))
            or decision == "reject" or str(s.get("piece_id") or "").startswith("stats-ficha:"))


def _same_family_series(s: dict, fcfg: dict | None) -> bool:
    """A loose card or pulse of the anchor's own series is the same news, not a cross-reference."""
    sup = (fcfg or {}).get("supersedes") or {}
    prefixes = tuple(sup.get("event_titles_prefix") or ())
    if prefixes and str(s.get("title") or "").startswith(prefixes):
        return True
    return sf._stat_family(s) in set(sup.get("stat_families") or ())


def _theme_date(t: dict) -> date | None:
    days = [d for s in t.get("sources") or [] if (d := _day(s.get("published_at")))]
    return max(days) if days else None


def cross_reference_candidates(ficha: dict, *, root: Path, anchor: date, signals: list[dict], cfg: dict,
                               registry: dict | None = None, themes: list[dict] | None = None) -> list[dict]:
    """Relevant sources of the last ``cross_lookback_days`` (other fichas, signals, Global themes).

    Relevance is deterministic: the family keywords of the anchor (config) and the Isapre codes of
    the ficha's evidence. Every candidate records why it is relevant and the numbers its own text
    holds (its trace pool)."""
    registry = registry if registry is not None else _registry(root)
    fam = ficha.get("family")
    start = anchor - timedelta(days=int(cfg.get("cross_lookback_days") or 90))
    in_window = lambda d: bool(d) and start <= d <= anchor
    own = {s.get("url") for s in ficha.get("sources") or []}
    keywords = list((cfg.get("family_keywords") or {}).get(fam) or [])
    codes = {f"cl:isapre:{c}" for c in (ficha.get("evidence") or {}).get("entity_codes") or []}
    min_rel = int(cfg.get("min_relevance") or 2)
    own_cfg = (registry.get("families") or {}).get(fam)
    out: dict[str, dict] = {}

    def add(item: dict) -> None:
        url = item["url"]
        if url in own or not _https(url):
            return
        if url not in out or item["score"] > out[url]["score"]:
            out[url] = item

    for other in cfg.get("related_families", {}).get(fam) or []:
        ocfg = (registry.get("families") or {}).get(other)
        live = sf.load_live(Path(root), ocfg["slug"]) if ocfg else None
        if not live or live.get("status") != "PASS" or live.get("family") != other:
            continue
        if not in_window(_day(live.get("published_at"))):
            continue
        b = _ficha_brief(live)
        add({"kind": "ficha", "url": b["url"], "label": f"Ficha {other} · {b['family_label']} ({b['period']})",
             "source_name": cfg.get("source_name") or "Superintendencia de Salud", "event_date": b["published_at"],
             "score": 10, "why_relevant": [f"familia relacionada con {fam} (config related_families)"],
             "brief": {"headline": b["headline"], "dek": b["dek"]}, "numbers": ficha_number_pool(live),
             "ficha_id": b["ficha_id"]})

    for s in signals:
        d = _day(s.get("event_date"))
        if not in_window(d) or _excluded_signal(s) or not s.get("title") or _same_family_series(s, own_cfg):
            continue
        text = _signal_text(s)
        hits = keyword_hits(text, keywords)
        ents = sorted(codes & {str(r.get("canonical_id")) for r in s.get("entity_refs") or [] if isinstance(r, dict)})
        score = len(hits) + 2 * len(ents)
        if score < min_rel:
            continue
        brief = _signal_brief(s)
        add({"kind": classify(s), "url": s.get("source_url"), "label": brief["title"], "source_name": s.get("source_name"),
             "event_date": str(s.get("event_date"))[:10], "score": score,
             "why_relevant": [f"términos: {', '.join(hits)}"] + ([f"entidades: {', '.join(ents)}"] if ents else []),
             "brief": brief, "numbers": sorted({abs(v) for _, v, _ in numbers_in(json.dumps(brief, ensure_ascii=False))})})

    for t in themes if themes is not None else _themes(root):
        d = _theme_date(t)
        if not in_window(d):
            continue
        text = " ".join(str(t.get(k) or "") for k in ("title", "global_finding", "why_it_matters"))
        hits = keyword_hits(text, keywords)
        if len(hits) < min_rel:
            continue
        src = next((s for s in t.get("sources") or [] if _https(s.get("url"))), None)
        if not src:
            continue
        brief = {"title": t.get("title"), "finding": t.get("global_finding"), "why": t.get("why_it_matters"),
                 "publisher": src.get("publisher")}
        add({"kind": "global", "url": src["url"], "label": t.get("title"), "source_name": f"Global · {src.get('publisher')}",
             "event_date": d.isoformat(), "score": len(hits), "why_relevant": [f"términos: {', '.join(hits)}"],
             "brief": brief, "numbers": sorted(_numbers(text + " " + str(src.get("evidence") or "")))})

    items = sorted(out.values(), key=lambda x: (-x["score"], -(_day(x["event_date"]) or date.min).toordinal(), x["url"]))
    # Diversity first: the best of each kind, then the rest by score.
    first, seen = [], set()
    for x in items:
        if x["kind"] not in seen:
            first.append(x)
            seen.add(x["kind"])
    rest = [x for x in items if x not in first]
    return (first + rest)[: int(cfg.get("max_cross_candidates") or 6)]


def _themes(root: Path) -> list[dict]:
    try:
        return json.loads((Path(root) / "data/global/themes.json").read_text(encoding="utf-8")).get("themes") or []
    except (OSError, ValueError, AttributeError):
        return []


# ---------------------------------------------------------------------------------------------
# 3. Plan (selection + feasibility) and evidence/brief


def plan(signals: list[dict], anchor: date, *, root: Path = ROOT, previous: dict | None = None,
         cfg: dict | None = None, themes: list[dict] | None = None) -> dict:
    """Decide whether this Monday is anchored on a stats release. No model, no network."""
    cfg = cfg if cfg is not None else load_config(root)
    if not cfg.get("enabled"):
        return {"rule": RULE_ID, "status": "disabled", "reason": "config_disabled_or_missing"}
    registry = _registry(root)
    prev_id = (((previous or {}).get("weekly_insight") or {}).get("stats_anchor") or {}).get("ficha_id")
    cands = stats_anchor_candidates(root, anchor, cfg, registry, prev_id)
    considered = [{k: c.get(k) for k in ("family", "ficha_id", "period", "published_at", "first_verified_at",
                                         "first_verified_basis", "sis_age_days", "eligible", "reason",
                                         "materiality_level")} for c in cands]
    tried = []
    for c in [c for c in cands if c["eligible"]]:
        cross = cross_reference_candidates(c["ficha"], root=root, anchor=anchor, signals=signals, cfg=cfg,
                                           registry=registry, themes=themes)
        if len({x["url"] for x in cross}) >= int(cfg.get("min_cross_sources") or 2):
            return {"rule": RULE_ID, "status": "selected", "anchor": c, "cross_refs": cross, "reason": c["reason"],
                    "considered": considered, "tried": tried, "config": cfg}
        tried.append({"ficha_id": c["ficha_id"], "reason": f"insufficient_cross_refs:{len(cross)}"})
    reason = "insufficient_cross_refs" if tried else "no_stats_new_period_in_week"
    return {"rule": RULE_ID, "status": "fallback", "reason": reason, "considered": considered, "tried": tried}


def allowed_figures(ficha: dict) -> list[dict]:
    """KPI values and lines of the anchor ficha, each with its evidence refs (the writer may use ≤ 2)."""
    pool = ficha_number_pool(ficha)
    out = []
    for k in ficha.get("kpis") or []:
        for text in [k.get("value")] + list(k.get("lines") or []):
            nums = numbers_in(str(text or ""))
            if nums and all(_traces(v, d, pool) for _, v, d in nums):
                out.append({"kpi": k.get("id"), "label": k.get("label"), "text": str(text), "refs": list(k.get("refs") or []),
                            "numbers": [abs(v) for _, v, _ in nums]})
    return out


def redundancy_corpus(anchor_ficha: dict, root: Path, registry: dict | None = None) -> list[str]:
    """Anchor ficha sentences + headline/dek of every live ficha (an Insight copies none of them)."""
    out = [s for t in ficha_texts(anchor_ficha) for s in lv.sentences(t)]
    registry = registry if registry is not None else _registry(root)
    for fcfg in (registry.get("families") or {}).values():
        live = sf.load_live(Path(root), fcfg["slug"]) if fcfg.get("slug") else None
        if live:
            out += [s for t in (live.get("headline"), live.get("dek")) for s in lv.sentences(t or "")]
    return [s for s in out if len(s.split()) >= 5]


def build_evidence(selected: dict, root: Path = ROOT) -> dict:
    """Evidence package in the shape of ``weekly_insight_a.build_evidence`` plus the contract inputs."""
    cfg = selected.get("config") or load_config(root)
    ficha = selected["anchor"]["ficha"]
    b = _ficha_brief(ficha)
    figures = allowed_figures(ficha)
    anchor_sources = [{"label": s.get("label"), "url": s["url"], "source_name": cfg.get("source_name"),
                       "source_type": "official_statistics", "event_date": s.get("published_at"), "role": "ancla"}
                      for s in ficha.get("sources") or [] if _https(s.get("url"))]
    cross = selected["cross_refs"]
    cross_sources = [{"label": x["label"], "url": x["url"], "source_name": x["source_name"], "source_type": x["kind"],
                      "event_date": x["event_date"], "role": "cruce"} for x in cross]
    anchor_pool = sorted({n for f in figures for n in f["numbers"]})
    pools = {s["url"]: anchor_pool for s in anchor_sources}
    pools.update({x["url"]: x["numbers"] for x in cross})
    numbers = sorted(set(anchor_pool) | {n for x in cross for n in x["numbers"]})
    sources = anchor_sources + cross_sources
    return {
        "mode": "stats_anchor",
        "candidate": {"title": b["headline"], "source_name": cfg.get("source_name"), "source_type": "official_statistics",
                      "url": b["url"], "event_date": b["published_at"], "what": b["dek"],
                      "why": f"Ficha {b['family']} · {b['family_label']}, período {b['period']}"},
        "related": [{"title": x["label"], "source_name": x["source_name"], "source_type": x["kind"], "url": x["url"],
                     "event_date": x["event_date"], **x["brief"]} for x in cross],
        "series": [], "numbers": numbers, "sources": sources, "allowed_urls": sorted({s["url"] for s in sources}),
        "score": None,
        "stats_anchor": {"ficha_id": b["ficha_id"], "family": b["family"], "period": b["period"],
                         "published_at": b["published_at"], "first_verified_at": selected["anchor"].get("first_verified_at"),
                         "first_verified_basis": selected["anchor"].get("first_verified_basis"),
                         "materiality": selected["anchor"].get("materiality"),
                         "selection_reason": selected["reason"]},
        "anchor_urls": [s["url"] for s in anchor_sources],
        "allowed_figures": figures,
        "cross_refs": [{k: x[k] for k in ("kind", "url", "label", "source_name", "event_date", "why_relevant", "brief")}
                       for x in cross],
        "source_pools": pools,
        "ficha_text": [t for t in (ficha.get("headline"), ficha.get("dek"),
                                   *((ficha.get("facts") or {}).get("paragraphs") or [])) if t],
        "redundancy_corpus": redundancy_corpus(ficha, root),
        "contract": {k: cfg.get(k) for k in ("min_cross_sources", "max_anchor_figures", "sentence_jaccard_max",
                                             "restatement_coverage")},
    }


CONTRACT_TEXT = """CONTRATO FICHA ≠ INSIGHT (Dirección 2-nov-2026; se verifica de forma determinista):
- La ficha ya publicó la noticia y el análisis de sus propios datos (FICHA_NO_REPETIR). El Insight NO la repite:
  cruza el dato ancla con al menos {min_cross} fuentes de CRUCES distintas, las asocia y propone una tesis.
- Cita esas fuentes en sources (url de CRUCES, label y role que diga qué aporta).
- Usa como máximo {max_anchor} cifras de la ficha, elegidas de CIFRAS_ANCLA_PERMITIDAS.
- figure_sources: [{{"figure":"cifra tal como aparece","source_url":"url de la fuente que la contiene"}}] para CADA
  cifra mostrada (titular, bajada, cuerpo, cierre, recuadro de cifras, gráficos, método, fuentes). Una cifra sin fuente falla.
- Tesis: el ensayo dice qué está pasando y por qué importa, asociando ancla y cruces; el cierre (closing, ≥40 palabras)
  remata esa tesis e integra en prosa las señales concretas que hay que mirar.
- Ningún párrafo puede solo reescribir cifras de la ficha; ninguna frase puede parecerse a una frase, titular o bajada de
  la ficha (similitud de raíces ≥ {jaccard})."""


def draft_prompt(evidence: dict, anchor: date) -> str:
    from .weekly_insight_a import FORMAT_A, RULES
    c = evidence["contract"]
    payload = {"ANCLA": {**evidence["candidate"], **evidence["stats_anchor"]},
               "CIFRAS_ANCLA_PERMITIDAS": evidence["allowed_figures"], "FICHA_NO_REPETIR": evidence["ficha_text"],
               "CRUCES": evidence["related"], "sources": evidence["sources"]}
    return ("Eres el editor senior de Alicanto Salud (inteligencia de mercado de salud en Chile, lectores ejecutivos de "
            "Isapres, Fonasa, prestadores, mutualidades y laboratorios). Escribe el Insight semanal del lunes "
            f"{anchor.isoformat()}, anclado en la publicación estadística de la semana. Prioriza claridad ejecutiva e "
            "información incremental, no extensión.\n" + FORMAT_A + "\n" + RULES + "\n" +
            CONTRACT_TEXT.format(min_cross=c["min_cross_sources"], max_anchor=c["max_anchor_figures"],
                                 jaccard=c["sentence_jaccard_max"]) +
            "\nEVIDENCIA:\n" + json.dumps(payload, ensure_ascii=False))


REVIEW_SUFFIX = ("\nCONTRATO FICHA ≠ INSIGHT (Dirección 2-nov-2026): este Insight está anclado en una ficha estadística "
                 "(EVIDENCIA.candidate). Falla también (FAIL) si solo repite la ficha en vez de cruzarla con las otras fuentes, "
                 "si la tesis no asocia el ancla con los cruces o si un cruce citado no es pertinente.")


def summary(selected: dict) -> dict:
    """The selection record kept with the result (no ficha body)."""
    out = {k: selected.get(k) for k in ("rule", "status", "reason", "considered", "tried")}
    a = selected.get("anchor")
    if a:
        out["anchor"] = {k: a.get(k) for k in ("ficha_id", "family", "period", "published_at", "first_verified_at",
                                                "first_verified_basis", "sis_age_days", "url",
                                                "materiality_level", "materiality")}
    if selected.get("cross_refs"):
        out["cross_refs"] = [{k: x.get(k) for k in ("kind", "url", "label", "source_name", "event_date", "why_relevant")}
                             for x in selected["cross_refs"]]
    auth = (selected.get("config") or {}).get("authorization") or {}
    if auth:
        out["authorization"] = f"{auth.get('by')} {auth.get('date')}"
    return out


CONTRACT_INPUT_KEYS = ("anchor_urls", "cross_refs", "source_pools", "allowed_figures", "redundancy_corpus", "contract")


def contract_inputs(evidence: dict) -> dict:
    """Exactly what ``contract_check`` reads; frozen in the brief so a later check needs no re-planning."""
    return {k: evidence.get(k) for k in CONTRACT_INPUT_KEYS}


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def brief_id_for(evidence: dict, anchor: date | str) -> str:
    """Deterministic id: Monday + anchor ficha + hash of the frozen contract inputs (tamper-evident)."""
    day = anchor.isoformat() if isinstance(anchor, date) else str(anchor)
    ficha_id = (evidence.get("stats_anchor") or {}).get("ficha_id")
    digest = hashlib.sha256(_canonical({"anchor_date": day, "ficha_id": ficha_id,
                                        "contract_inputs": contract_inputs(evidence)})).hexdigest()[:16]
    return f"stats-brief:{day}:{ficha_id}:{digest}"


def build_brief(selected: dict, evidence: dict, anchor: date) -> dict:
    """Structured brief for a human or session drafter (no model call)."""
    auth = (selected.get("config") or {}).get("authorization") or selected.get("authorization")
    return {"schema_version": "weekly_insight_stats_brief_v1", "rule": RULE_ID, "anchor_date": anchor.isoformat(),
            "brief_id": brief_id_for(evidence, anchor),
            "authorization": auth,
            "anchor": {**evidence["stats_anchor"], "headline": evidence["candidate"]["title"],
                       "dek": evidence["candidate"]["what"], "sources": [s for s in evidence["sources"] if s["role"] == "ancla"]},
            "selection": {"reason": selected.get("reason"), "considered": selected.get("considered"), "tried": selected.get("tried")},
            "cross_references": evidence["cross_refs"],
            "allowed_anchor_figures": evidence["allowed_figures"],
            "ficha_text_do_not_repeat": evidence["ficha_text"],
            "contract": {**evidence["contract"], "text": CONTRACT_TEXT.format(
                min_cross=evidence["contract"]["min_cross_sources"], max_anchor=evidence["contract"]["max_anchor_figures"],
                jaccard=evidence["contract"]["sentence_jaccard_max"]),
                "check": "python scripts/check_weekly_insight_contract.py --brief <este archivo> --write"},
            "insight_must_declare": {"weekly_insight.stats_anchor": {"ficha_id": evidence["stats_anchor"]["ficha_id"],
                                                                     "brief_id": brief_id_for(evidence, anchor)}},
            "contract_inputs": contract_inputs(evidence)}


# ---------------------------------------------------------------------------------------------
# 4. Contract check (deterministic)


def _paragraph_fields(weekly: dict) -> list[tuple[str, str]]:
    if essay_v2.is_v2(weekly):
        out = [(f"body[{i}]", essay_v2.plain(b.get("text"))) for i, b in enumerate(weekly.get("body") or [])
               if isinstance(b, dict) and b.get("type") == "paragraph"]
        return out + [("closing", essay_v2.plain(essay_v2.closing_text(weekly)))]
    essay = weekly.get("essay") or {}
    out = []
    for key in ("facts", "reading"):
        for i, p in enumerate(((essay.get(key) or {}).get("paragraphs") or []) if isinstance(essay.get(key), dict) else []):
            out.append((f"essay.{key}[{i}]", str(p)))
    return out


def _sentence_fields(weekly: dict) -> list[tuple[str, str]]:
    out = [("headline", weekly.get("headline")), ("dek", weekly.get("dek")), ("insight_teaser", weekly.get("insight_teaser"))]
    out += _paragraph_fields(weekly)
    for i, w in enumerate(weekly.get("watch") or []):
        if isinstance(w, dict):
            out += [(f"watch[{i}]", w.get("headline")), (f"watch[{i}]", w.get("explanation"))]
    return [(k, re.sub(r"\[\^n\d+\]", "", str(v))) for k, v in out if v]


def contract_check(weekly: dict, evidence: dict) -> dict:
    c = evidence.get("contract") or {}
    errors: list[str] = []
    anchor_urls = set(evidence.get("anchor_urls") or [])
    cross_urls = {x["url"] for x in evidence.get("cross_refs") or []}
    pools = {u: [float(n) for n in ns] for u, ns in (evidence.get("source_pools") or {}).items()}

    # 1. Cross-references: distinct, from the brief, linked and attributed.
    cited = {s.get("url") for s in weekly.get("sources") or [] if isinstance(s, dict) and s.get("url") in cross_urls
             and str(s.get("label") or "").strip() and str(s.get("role") or s.get("short_role") or "").strip()}
    if len(cited) < int(c.get("min_cross_sources") or 2):
        errors.append(f"cross_sources_below_min:{len(cited)}")

    # 3. Figure → source map.
    entries = []
    for i, f in enumerate(weekly.get("figure_sources") or []):
        if not isinstance(f, dict):
            errors.append(f"figure_source_invalid:{i}")
            continue
        url, nums = f.get("source_url"), numbers_in(str(f.get("figure") or ""))
        if url not in pools or not nums:
            errors.append(f"figure_source_unknown:{f.get('figure')}")
            continue
        for tok, v, d in nums:
            if not _traces(v, d, pools[url]):
                errors.append(f"figure_not_in_its_source:{tok}")
                continue
            entries.append({"value": abs(v), "decimals": d, "anchor": url in anchor_urls})
    estimates = [abs(float(e["value"])) for e in weekly.get("estimates") or []
                 if isinstance(e, dict) and isinstance(e.get("value"), (int, float))]

    def origin(value: float, decimals: int) -> str | None:
        hits = [e for e in entries if _traces(value, decimals, [e["value"]])]
        if any(not e["anchor"] for e in hits):
            return "cross"
        if hits:
            return "anchor"
        if _traces(value, decimals, estimates):
            return "estimate"
        return None

    shown = [(w, tok, v, d) for w, t in displayed_texts(weekly, strict=True) for tok, v, d in numbers_in(t)]
    for chart in weekly.get("charts") or []:
        if isinstance(chart, dict):
            for label, v in chart_values(chart):
                shown.append((f"chart.{chart.get('id')}", f"{label}={v}", float(v), 1 if v != int(v) else 0))
    anchor_used = set()
    for where, tok, v, d in shown:
        o = origin(abs(v), d)
        if o is None:
            errors.append(f"figure_untraced:{where}:{tok}")
        elif o == "anchor":
            anchor_used.add(round(abs(v), 6))

    # 2. Anchor figures: at most N, each an allowed figure (KPI value/line with refs).
    allowed = [n for f in evidence.get("allowed_figures") or [] for n in f.get("numbers") or []]
    if len(anchor_used) > int(c.get("max_anchor_figures") or 2):
        errors.append(f"anchor_figures_over_max:{len(anchor_used)}")
    for v in sorted(anchor_used):
        if not any(abs(v - a) < 1e-6 or _traces(v, 2, [a]) for a in allowed):
            errors.append(f"anchor_figure_not_allowed:{v:g}")

    # 4. A paragraph that only restates ficha figures and vocabulary.
    corpus = evidence.get("redundancy_corpus") or []
    ficha_stems = set().union(*[lv.content_stems(s) for s in corpus]) if corpus else set()
    for where, p in _paragraph_fields(weekly):
        nums = numbers_in(p)
        if not nums or any(origin(abs(v), d) != "anchor" for _, v, d in nums):
            continue
        stems = lv.content_stems(re.sub(r"\[\^n\d+\]", "", p))
        coverage = len(stems & ficha_stems) / len(stems) if stems else 1.0
        if coverage >= float(c.get("restatement_coverage") or 0.7):
            errors.append(f"paragraph_restates_ficha:{where}:{coverage:.2f}")

    # 5. Tesis and Qué mirar (v2: both live in the closing, as prose).
    if essay_v2.is_v2(weekly):
        if essay_v2.words(essay_v2.closing_text(weekly)) < 40:
            errors.append("closing_missing")
    else:
        reading = (weekly.get("essay") or {}).get("reading") or {}
        if not (isinstance(reading, dict) and fold(reading.get("heading")).startswith("tesis") and reading.get("paragraphs")):
            errors.append("tesis_missing")
        if len(weekly.get("watch") or []) < 2 or not fold(weekly.get("watch_heading")).startswith("que mirar"):
            errors.append("que_mirar_missing")

    # 6. Non-redundancy against the ficha's sentences, headlines and deks.
    limit = float(c.get("sentence_jaccard_max") or 0.5)
    corpus_stems = [lv.content_stems(s) for s in corpus]
    for where, text in _sentence_fields(weekly):
        for s in lv.sentences(text):
            if len(s.split()) < 5:
                continue
            st = lv.content_stems(s)
            best = max((lv.jaccard(st, cs) for cs in corpus_stems), default=0.0)
            if best >= limit:
                errors.append(f"sentence_redundant_with_ficha:{where}:{best:.2f}")
    return {"verdict": "PASS" if not errors else "FAIL", "errors": errors, "cross_sources_cited": sorted(cited),
            "anchor_figures_used": len(anchor_used)}


# ---------------------------------------------------------------------------------------------
# 5. Contract-check record and CI gate (Dirección 2-nov, decision 3)

CHECKS_DIR = Path("data/weekly_insight/contract_checks")
BRIEFS_DIR = Path("data/weekly_insight/candidates")
RECORD_SCHEMA = "weekly_insight_contract_check_v1"


def insight_sha256(weekly: dict) -> str:
    return hashlib.sha256(_canonical(weekly)).hexdigest()


def _safe(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z_.-]+", "-", str(text)).strip("-")


def record_path(root: Path, insight_id: str) -> Path:
    return Path(root) / CHECKS_DIR / f"{_safe(insight_id)}.json"


def check_against_brief(weekly: dict, brief: dict) -> dict:
    """``contract_check`` with the brief's frozen inputs, plus the brief's own integrity."""
    inputs = brief.get("contract_inputs") or {}
    expected = brief_id_for({**inputs, "stats_anchor": {"ficha_id": (brief.get("anchor") or {}).get("ficha_id")}},
                            str(brief.get("anchor_date")))
    if brief.get("brief_id") != expected:
        return {"verdict": "FAIL", "errors": [f"brief_id_mismatch:{brief.get('brief_id')}!={expected}"]}
    result = contract_check(weekly, inputs)
    declared = (weekly.get("stats_anchor") or {}).get("brief_id")
    if declared and declared != brief.get("brief_id"):
        result = {**result, "verdict": "FAIL", "errors": list(result["errors"]) + [f"insight_declares_other_brief:{declared}"]}
    return result


def write_contract_record(root: Path, weekly: dict, brief: dict, brief_path: Path | str, *,
                          source_sha: str | None = None, checked_by: str = "editorial_session") -> dict:
    """Run the check and write ``contract_checks/<insight id>.json`` (PASS or FAIL; only PASS clears the gate)."""
    root = Path(root)
    check = check_against_brief(weekly, brief)
    bp = Path(brief_path)
    rel = str(bp.resolve().relative_to(root.resolve())) if bp.is_absolute() else str(bp)
    record = {"schema_version": RECORD_SCHEMA, "rule": RULE_ID, "insight_id": weekly.get("id"),
              "anchor_date": weekly.get("freshness_anchor_date") or brief.get("anchor_date"),
              "ficha_id": (brief.get("anchor") or {}).get("ficha_id"), "brief_id": brief.get("brief_id"),
              "brief_path": rel, "insight_sha256": insight_sha256(weekly),
              "check": {k: check.get(k) for k in ("verdict", "errors", "cross_sources_cited", "anchor_figures_used")},
              "checked_by": checked_by, "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "source_sha": source_sha or (_git(root, "rev-parse", "HEAD") or "").strip() or None}
    path = record_path(root, str(weekly.get("id")))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {**record, "path": str(path)}


def stats_source_urls(root: Path) -> set[str]:
    """Source URLs of every stats ficha in the repo (live, archive, hold candidates)."""
    base = Path(root) / "data/stats_fichas"
    urls: set[str] = set()
    for path in [*base.glob("live/*.json"), *base.glob("archive/*/*.json")]:
        try:
            ficha = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        urls |= {s.get("url") for s in ficha.get("sources") or [] if isinstance(s, dict) and _https(s.get("url"))}
    return urls


def anchored_on_stats(payload: dict, stats_urls: set[str]) -> str | None:
    """Why an Insight counts as anchored on a stats ficha, or None for a normal-topic Insight.

    Declared (``weekly_insight.stats_anchor``), selected by the rule (``topic_selection``), or its primary
    source is a stats ficha's source file. A stats file cited only as a secondary source does not anchor."""
    w = payload.get("weekly_insight") if isinstance(payload.get("weekly_insight"), dict) else None
    if not w:
        return None
    if w.get("stats_anchor"):
        return "declared_stats_anchor"
    ts = payload.get("topic_selection") or {}
    if ts.get("rule") == RULE_ID and ts.get("status") == "selected":
        return "topic_selection_stats_anchor"
    if w.get("source_url") in stats_urls:
        return "primary_source_is_stats_ficha"
    return None


def insight_payloads(root: Path) -> list[tuple[str, dict]]:
    base = Path(root) / "data/weekly_insight"
    out = []
    for path in [base / "editorial_approved.json", *sorted((base / "archive").glob("*.json"))]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(payload, dict):
            out.append((str(path.relative_to(root)), payload))
    return out


def contract_gate(root: Path = ROOT) -> list[str]:
    """CI gate: every Insight anchored on a stats ficha has a PASS contract record for its exact content.

    Checks, all deterministic: record exists; ``check.verdict`` PASS; ``insight_sha256`` matches the
    committed Insight; the brief file exists and its ``brief_id`` matches the record and its content; the
    contract re-run on the brief's frozen inputs still PASSes. Normal-topic Insights are skipped."""
    root = Path(root)
    urls = stats_source_urls(root)
    errors = []
    for where, payload in insight_payloads(root):
        why = anchored_on_stats(payload, urls)
        if not why:
            continue
        weekly = payload["weekly_insight"]
        iid = str(weekly.get("id"))
        tag = f"{where}:{iid}"
        rpath = record_path(root, iid)
        try:
            record = json.loads(rpath.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            errors.append(f"{tag}:missing_contract_record({why}):{rpath.relative_to(root)}")
            continue
        if (record.get("check") or {}).get("verdict") != "PASS":
            errors.append(f"{tag}:contract_record_not_pass:{(record.get('check') or {}).get('errors')}")
            continue
        if record.get("insight_sha256") != insight_sha256(weekly):
            errors.append(f"{tag}:insight_changed_after_check")
            continue
        try:
            brief = json.loads((root / str(record.get("brief_path"))).read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            errors.append(f"{tag}:brief_missing:{record.get('brief_path')}")
            continue
        if brief.get("brief_id") != record.get("brief_id"):
            errors.append(f"{tag}:brief_id_mismatch")
            continue
        recheck = check_against_brief(weekly, brief)
        if recheck["verdict"] != "PASS":
            errors.append(f"{tag}:contract_recheck_fail:{recheck['errors']}")
    return errors
