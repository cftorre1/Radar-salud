"""Three headline candidates and a blind reviewer for the weekly insight (Dirección 13-nov-2026).

After the drafted insight passes deterministic verification, one call writes three title + dek pairs, one per style:

  A «hecho + tensión»: the fact with its figure in the title, the tension in the dek;
  B «consecuencia de negocio»: who gains, who loses or what changes in the market, figure in the dek;
  C «corto con contraste»: ≤ 8 words with two poles, figures in the dek.

Each candidate replaces the draft's headline/dek and must pass the same deterministic verification as the insight
(numbers traced to the evidence, rule 8: the dek does not repeat the headline). A second model, blind to the styles and
in shuffled order, scores every passing candidate 1–5 on precisión, claridad, novedad and largo. The highest total wins;
a tie goes to A, then B. All candidates and scores are kept for audit. Any failure (budget, parse, no passing
candidate) keeps the draft's own headline: the insight is never blocked by this step.
"""
from __future__ import annotations

import json
import random
from typing import Any, Callable

STYLES = {"A": "hecho + tensión: el título dice el hecho con su cifra (≤ 12 palabras); la bajada (≤ 25 palabras) "
               "explica la tensión o por qué importa, sin repetir palabras del título",
          "B": "consecuencia de negocio: el título dice quién gana, quién pierde o qué cambia en el mercado, sin "
               "especular más allá de la evidencia; la bajada trae el dato",
          "C": "corto con contraste: título de máximo 8 palabras con dos polos que se entienda solo; las cifras van en "
               "la bajada"}
CRITERIA = ("precision", "claridad", "novedad", "largo")
FEATURE, REVIEW_FEATURE = "weekly_headline_candidates", "weekly_headline_review"


def candidates_prompt(weekly: dict, evidence: dict) -> str:
    body = weekly.get("body") or weekly.get("essay") or ""
    return ("Eres editor jefe de un servicio de inteligencia de salud en Chile. Escribe TRES pares título + bajada para "
            "este insight, uno por estilo. Usa SOLO cifras que estén en el texto o la evidencia; no inventes.\n" +
            "".join(f"- {k}: {v}\n" for k, v in STYLES.items()) +
            "Responde SOLO JSON {\"A\":{\"headline\":\"…\",\"dek\":\"…\"},\"B\":{…},\"C\":{…}}.\n"
            f"TÍTULO ACTUAL: {weekly.get('headline')}\nBAJADA ACTUAL: {weekly.get('dek')}\n"
            "TEXTO:\n" + json.dumps(body, ensure_ascii=False)[:9000] +
            "\nEVIDENCIA (cifras):\n" + json.dumps(evidence.get("numbers") or [], ensure_ascii=False)[:2000])


def review_prompt(options: list[tuple[str, dict]], weekly: dict) -> str:
    listing = "\n".join(f"{i + 1}. Título: {c['headline']}\n   Bajada: {c['dek']}" for i, (_, c) in enumerate(options))
    return ("Revisor independiente. Puntúa cada opción de título + bajada de 1 a 5 en: precision (fiel al texto, sin "
            "exagerar), claridad (se entiende sin leer el texto), novedad (dice algo no obvio), largo (cabe en una fila "
            "del teléfono). Responde SOLO JSON {\"scores\":[{\"option\":1,\"precision\":n,\"claridad\":n,\"novedad\":n,"
            "\"largo\":n}, …]}.\nOPCIONES:\n" + listing +
            "\nTEXTO DEL INSIGHT:\n" + json.dumps(weekly.get("body") or weekly.get("essay") or "", ensure_ascii=False)[:6000])


def choose(weekly: dict, evidence: dict, verify: Callable[[dict], dict], call_draft: Callable[[str, str], Any],
           call_review: Callable[[str, str], Any], rng: random.Random | None = None) -> dict:
    """Returns the audit record; on success ``weekly`` gets the winning headline/dek (in place)."""
    audit: dict[str, Any] = {"status": "kept_draft", "draft": {"headline": weekly.get("headline"), "dek": weekly.get("dek")}}
    try:
        raw = call_draft(candidates_prompt(weekly, evidence), FEATURE).output
    except Exception as exc:  # noqa: BLE001 - never blocks the insight
        audit["error"] = f"{type(exc).__name__}:{exc}"[:200]
        return audit
    cands = {}
    for k in STYLES:
        c = raw.get(k) if isinstance(raw, dict) else None
        if isinstance(c, dict) and str(c.get("headline") or "").strip() and str(c.get("dek") or "").strip():
            trial = {**weekly, "headline": str(c["headline"]).strip(), "dek": str(c["dek"]).strip()}
            trial["title"] = trial["insight_title"] = trial["headline"]
            try:
                v = verify(trial)
            except Exception as exc:  # noqa: BLE001 - a verifier crash rejects the candidate, never the insight
                v = {"verdict": "FAIL", "errors": [f"verifier_error:{type(exc).__name__}"]}
            cands[k] = {"headline": trial["headline"], "dek": trial["dek"], "verdict": v["verdict"],
                        "errors": v.get("errors") or []}
    audit["candidates"] = cands
    passing = [(k, c) for k, c in cands.items() if c["verdict"] == "PASS"]
    if not passing:
        return audit
    order = passing[:]
    (rng or random.Random()).shuffle(order)
    audit["review_order"] = [k for k, _ in order]  # option n of the review = review_order[n-1]
    try:
        out = call_review(review_prompt(order, weekly), REVIEW_FEATURE).output
        scores = {}
        for row in (out or {}).get("scores") or []:
            i = int(row.get("option")) - 1
            if 0 <= i < len(order):
                vals = [max(1, min(5, int(row.get(c) or 0))) for c in CRITERIA]
                scores[order[i][0]] = {**dict(zip(CRITERIA, vals)), "total": sum(vals)}
    except Exception as exc:  # noqa: BLE001
        audit["error"] = f"{type(exc).__name__}:{exc}"[:200]
        return audit
    if not scores:
        return audit
    audit["scores"] = scores
    winner = sorted(scores, key=lambda k: (-scores[k]["total"], "ABC".index(k)))[0]
    # Every field that carries the title (home card, share pages, archive) gets the chosen one (review of #207).
    weekly["headline"], weekly["dek"] = cands[winner]["headline"], cands[winner]["dek"]
    weekly["title"] = weekly["insight_title"] = cands[winner]["headline"]
    audit.update(status="chosen", winner=winner)
    return audit
