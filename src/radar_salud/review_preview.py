"""Review previews of statistics fichas held only by their first-review gate (Dirección 4-nov-2026: "Pasa a staging
casos GES y lo reviso desde ahí").

A ficha whose deterministic verification PASSED and that is held ONLY by ``HOLD_FIRST_REVIEW`` is exported to
``web/data/preview/<slug>.json`` for the unlisted, ``noindex`` page ``web/preview.html`` on staging, so Dirección
reviews it on the real site. It never enters the feed, Datos, share pages or ``radar_today.json``. Any other hold
(reconciliation, verification, parser) is never previewed, and a hold older than the family's live ficha is skipped.
Approval still goes through ``config/stats_fichas_v1.json`` (``first_review``): the preview publishes nothing.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import stats_fichas as sf

FIRST_REVIEW_HOLD = "HOLD_FIRST_REVIEW:awaiting_first_review"
HOLD_DIR = Path("data/stats_fichas/hold")
LIVE_DIR = Path("data/stats_fichas/live")


SLUG = re.compile(r"^[a-z0-9_]+$")


def _load(p: Path) -> dict:
    """A JSON object, or {} for anything else (a malformed hold never breaks the daily export)."""
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _obj(x) -> dict:
    return x if isinstance(x, dict) else {}


def candidates(root: Path) -> list[dict]:
    live = {}
    for p in sorted((root / LIVE_DIR).glob("*.json")):
        d = _load(p)
        if isinstance(d.get("family"), str):
            live[d["family"]] = str(d.get("period") or "")
    out = []
    for p in sorted((root / HOLD_DIR).glob("*.json")):
        d = _load(p)
        holds = _obj(d.get("decision")).get("holds")
        cand = _obj(d.get("candidate"))
        fam, per, slug = cand.get("family"), str(cand.get("period") or ""), str(cand.get("slug") or "")
        # Only a ficha that passed verification and waits for nothing but the first review (the page renders it).
        if (holds != [FIRST_REVIEW_HOLD] or cand.get("status") != "AWAITING_FIRST_REVIEW"
                or _obj(cand.get("verification")).get("verdict") != "PASS" or not cand.get("headline")
                or not isinstance(fam, str) or not SLUG.match(slug)):
            continue
        if fam in live and live[fam] >= per:  # the live ficha already covers this period
            continue
        out.append({"slug": slug, "family": fam, "period": per, "held_since": d.get("generated_at"),
                    "ficha": sf.public_ficha(cand)})
    # One preview per family: the newest period waiting for review (two holds would share a slug).
    newest: dict[str, dict] = {}
    for it in out:
        if it["family"] not in newest or it["period"] > newest[it["family"]]["period"]:
            newest[it["family"]] = it
    return sorted(newest.values(), key=lambda it: it["slug"])


def write(root: Path, web_data_dir: Path) -> list[str]:
    """Rewrite ``<web_data_dir>/preview/`` from the current holds; stale previews are removed."""
    pdir = Path(web_data_dir) / "preview"
    pdir.mkdir(parents=True, exist_ok=True)
    for old in pdir.glob("*.json"):
        old.unlink()
    items = candidates(Path(root))
    for it in items:
        (pdir / f"{it['slug']}.json").write_text(json.dumps(
            {"preview": {k: it[k] for k in ("slug", "family", "period", "held_since")}, "ficha": it["ficha"]},
            ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (pdir / "index.json").write_text(json.dumps(
        {"previews": [{k: it[k] for k in ("slug", "family", "period", "held_since")} | {"headline": it["ficha"]["headline"]}
                      for it in items]}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return [it["slug"] for it in items]
