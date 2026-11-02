"""Weekly Insight anchored on a statistics-family release (Dirección, 2-nov-2026).

Part of the Monday format-A pipeline (``weekly_insight_a``); it does not publish on its own.

Decision (``config/weekly_insight_stats_anchor_v1.json``):

* **Selection.** A statistics-family ficha (F1 Cartera, F2 FEFI, F4 GES, F6 Boletín IP) that publishes
  a NEW period in the 7 days before the Monday and passes verification is the primary candidate.
  Ties go by materiality: a crossed threshold or a featured ficha ranks above a plain new period;
  then the most recent publication; then the family order of the config.
* **Ficha vs. Insight.** The ficha is the news with its own data. The Insight crosses the anchor
  release with other material from the last 90 days (other fichas, normativa, sanciones, Congreso,
  FNE, Global themes, press) and offers a thesis and what to watch. It must not repeat the ficha.
* **Contract** (``contract_check``), all deterministic:
  1. at least 2 distinct cross-reference sources, from the brief, linked and attributed;
  2. at most 2 anchor figures, each among the brief's allowed figures (traced to ficha refs);
  3. every displayed figure traced to a named source (``figure_sources``) or to a recomputed estimate;
  4. no paragraph that only restates ficha figures and vocabulary;
  5. a "Tesis" section (``essay.reading``) and a "Qué mirar" section (≥ 2 items);
  6. no sentence with stem Jaccard ≥ threshold against a ficha sentence, headline or dek.
  If the plan cannot meet item 1 before drafting, or the draft fails the contract, the pipeline
  falls back to the normal topic selection instead of publishing a weak Insight.

Nothing here calls a model or the network. ``build_brief`` produces the structured brief for a
human or session drafter (anchor, cross-references with links, allowed figures, contract).
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from . import lectura_verifier as lv
from . import stats_fichas as sf
from .weekly_freshness import MONDAY_EVIDENCE_DAYS, displayed_texts, iso_day, number_traces, numbers_in, chart_values

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = Path("config/weekly_insight_stats_anchor_v1.json")
RULE_ID = "stats_anchor_v1"


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


def stats_anchor_candidates(root: Path, anchor: date, cfg: dict, registry: dict | None = None,
                            previous_anchor_id: str | None = None) -> list[dict]:
    """All configured families with the reason each is (or is not) eligible, eligible ones ranked first."""
    registry = registry if registry is not None else _registry(root)
    window = int(cfg.get("window_days") or MONDAY_EVIDENCE_DAYS)
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
        reasons = []
        if ficha.get("family") != fam:
            reasons.append("family_mismatch")
        if ficha.get("status") != "PASS" or (ficha.get("verification") or {}).get("verdict") != "PASS":
            reasons.append("not_verified_pass")
        if (ficha.get("reconciliation") or {}).get("ok") is False:
            reasons.append("reconciliation_fail")
        if "new_period" not in (ficha.get("triggers") or []):
            reasons.append("not_a_new_period")
        if not published or not (anchor - timedelta(days=window) <= published < anchor):
            reasons.append(f"published_outside_week:{ficha.get('published_at')}")
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
            f"{fam} publicó un período nuevo ({ficha.get('period')}) el {ficha.get('published_at')}, dentro de los "
            f"{window} días previos al lunes {anchor.isoformat()}, con verificación y conciliación PASS; "
            f"materialidad {level}: {why}."))
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
    considered = [{k: c.get(k) for k in ("family", "ficha_id", "period", "published_at", "eligible", "reason",
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
                         "published_at": b["published_at"], "materiality": selected["anchor"].get("materiality"),
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
  cifra mostrada (titular, bajada, ensayo, qué mirar, gráficos, notas). Una cifra sin fuente falla.
- essay.reading.heading = "Tesis": qué está pasando y por qué importa, asociando ancla y cruces.
- watch (≥2 ítems) con watch_heading "Qué mirar": señales concretas a seguir.
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
        out["anchor"] = {k: a.get(k) for k in ("ficha_id", "family", "period", "published_at", "url",
                                                "materiality_level", "materiality")}
    if selected.get("cross_refs"):
        out["cross_refs"] = [{k: x.get(k) for k in ("kind", "url", "label", "source_name", "event_date", "why_relevant")}
                             for x in selected["cross_refs"]]
    auth = (selected.get("config") or {}).get("authorization") or {}
    if auth:
        out["authorization"] = f"{auth.get('by')} {auth.get('date')}"
    return out


def build_brief(selected: dict, evidence: dict, anchor: date) -> dict:
    """Structured brief for a human or session drafter (no model call)."""
    return {"schema_version": "weekly_insight_stats_brief_v1", "rule": RULE_ID, "anchor_date": anchor.isoformat(),
            "authorization": (selected.get("config") or {}).get("authorization"),
            "anchor": {**evidence["stats_anchor"], "headline": evidence["candidate"]["title"],
                       "dek": evidence["candidate"]["what"], "sources": [s for s in evidence["sources"] if s["role"] == "ancla"]},
            "selection": {"reason": selected["reason"], "considered": selected.get("considered"), "tried": selected.get("tried")},
            "cross_references": evidence["cross_refs"],
            "allowed_anchor_figures": evidence["allowed_figures"],
            "ficha_text_do_not_repeat": evidence["ficha_text"],
            "contract": {**evidence["contract"], "text": CONTRACT_TEXT.format(
                min_cross=evidence["contract"]["min_cross_sources"], max_anchor=evidence["contract"]["max_anchor_figures"],
                jaccard=evidence["contract"]["sentence_jaccard_max"]),
                "check": "weekly_insight_stats_anchor.contract_check(weekly, evidence)"}}


# ---------------------------------------------------------------------------------------------
# 4. Contract check (deterministic)


def _paragraph_fields(weekly: dict) -> list[tuple[str, str]]:
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

    # 5. Tesis and Qué mirar.
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
