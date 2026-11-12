"""Insights de semanas anteriores en el feed (Dirección 12-nov-2026).

«Los insight una vez pasada la semana, deben quedar en el feed con la fecha de creación» y «Al insight le faltan los
botones de compartir que son clave para difundir la plataforma».

Writes ``web/data/insights.json`` (every archived insight that passed review, newest first; the current week's
insight stays in «Esta semana» and is listed as ``current``) and one share page per insight, ``web/i/<slug>.html``:
its own title, dek and date as link-preview metadata (WhatsApp, LinkedIn), then it opens the insight in Al día.
Only reviewed text is used; nothing is generated here.
"""
from __future__ import annotations

import html
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = "https://alicantosalud.cl/"
IMAGE = "https://cftorre1.github.io/Radar-salud/assets/alicanto-logo-header.png"  # same image as index.html


def _weekly(doc: dict) -> dict | None:
    if not isinstance(doc, dict) or str(doc.get("status") or "pass").lower() != "pass":
        return None
    w = doc.get("weekly_insight") if isinstance(doc.get("weekly_insight"), dict) else None
    return w if w and (w.get("insight_title") or w.get("headline") or w.get("title")) else None


def _date(w: dict) -> str:
    return str(w.get("freshness_anchor_date") or w.get("event_date") or "")[:10]


def _title(w: dict) -> str:
    return str(w.get("insight_title") or w.get("headline") or w.get("title") or "").strip()


def _dek(w: dict) -> str:
    for key in ("dek", "insight_teaser", "summary"):
        v = w.get(key)
        if isinstance(v, list):  # legacy insights kept the summary as a list of sentences
            v = next((x for x in v if isinstance(x, str) and x.strip()), "")
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def slug(w: dict) -> str:
    m = re.match(r"^weekly-insight:(\d{4}-\d{2}-\d{2}):([a-z0-9-]+)$", str(w.get("id") or ""))
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    words = unicodedata.normalize("NFKD", _title(w).lower()).encode("ascii", "ignore").decode()
    words = re.sub(r"[^a-z0-9]+", "-", words).strip("-")
    return f"{_date(w)}-{'-'.join(words.split('-')[:6])}".strip("-")


def share_page(w: dict) -> str:
    s, title, dek = slug(w), _title(w), _dek(w)
    target = f"../index.html?insight={s}"
    e = lambda x: html.escape(x, quote=True)
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)} · Alicanto Salud</title>
<meta name="description" content="{e(dek)}">
<meta property="og:type" content="article"><meta property="og:site_name" content="Alicanto Salud">
<meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(dek)}">
<meta property="og:url" content="{e(SITE + 'i/' + s + '.html')}"><meta property="og:image" content="{IMAGE}">
<meta property="article:published_time" content="{e(_date(w))}">
<meta name="twitter:card" content="summary_large_image">
<link rel="canonical" href="{e(SITE + 'i/' + s + '.html')}">
<meta http-equiv="refresh" content="0; url={e(target)}">
<style>body{{font:16px/1.5 system-ui,sans-serif;color:#1D3345;background:#FAF9F5;margin:0;padding:24px 16px;max-width:640px}}a{{color:#8A5420}}</style>
</head><body><p>Insight de la semana · Alicanto Salud</p><h1>{e(title)}</h1><p>{e(dek)}</p>
<p><a href="{e(target)}">Leer el análisis completo</a></p></body></html>
"""


def _expired(w: dict | None, today: str) -> bool:
    return bool(w and w.get("expires_on") and str(w["expires_on"])[:10] <= today)


def build(root: Path = ROOT, today: str | None = None) -> dict:
    folder = root / "data/weekly_insight"
    today = today or datetime.now(timezone.utc).date().isoformat()
    approved = _weekly(json.loads((folder / "editorial_approved.json").read_text(encoding="utf-8"))) \
        if (folder / "editorial_approved.json").exists() else None
    # Past its week the insight leaves «Esta semana»; if no newer one replaced it yet, it joins the feed here.
    current = None if _expired(approved, today) else approved
    seen, items = set(), []
    paths = sorted((folder / "archive").glob("*.json"), reverse=True)
    if approved and current is None:
        paths = [folder / "editorial_approved.json"] + paths
    for path in paths:
        try:
            w = _weekly(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
        if not w or (current and _title(w) == _title(current)):
            continue
        s = slug(w)
        if s in seen:
            continue
        seen.add(s)
        items.append({"slug": s, "date": _date(w), "title": _title(w), "dek": _dek(w), "share_path": f"i/{s}.html",
                      "weekly": w})
    items.sort(key=lambda x: x["date"], reverse=True)
    out = {"schema": "alicanto_insights_v1", "generated_at": datetime.now(timezone.utc).isoformat(), "items": items}
    if current:
        out["current"] = {"slug": slug(current), "date": _date(current), "title": _title(current),
                          "share_path": f"i/{slug(current)}.html"}
    return out


def write(root: Path = ROOT, web: Path | None = None, today: str | None = None) -> dict:
    web = web or root / "web"
    data = build(root, today)
    pages = list(data["items"]) + ([{"weekly": None, **data["current"]}] if data.get("current") else [])
    (web / "i").mkdir(parents=True, exist_ok=True)
    folder = root / "data/weekly_insight"
    current_w = _weekly(json.loads((folder / "editorial_approved.json").read_text(encoding="utf-8"))) \
        if data.get("current") else None
    for p in pages:
        w = p["weekly"] or current_w
        text = share_page(w)
        target = web / "i" / f"{p['slug']}.html"
        if not target.exists() or target.read_text(encoding="utf-8") != text:
            target.write_text(text, encoding="utf-8")
    payload = {k: v for k, v in data.items() if k != "generated_at"}
    path = web / "data/insights.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if {k: v for k, v in old.items() if k != "generated_at"} != payload:  # no daily churn
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return data


if __name__ == "__main__":
    d = write()
    print(f"insights: {len(d['items'])} archived, current={bool(d.get('current'))}")
