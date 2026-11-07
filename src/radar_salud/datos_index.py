"""Index for the "Datos" page (Dirección, 3-nov-2026): the latest published ficha of each statistics family.

``web/data/datos.json`` lists every family of ``config/stats_fichas_v1.json`` once:

- an active family with a live ficha in the snapshot (``stats_ficha`` card, PASS) shows that ficha's verified headline
  and 1–2 of its KPIs copied verbatim (``datos_kpis`` by id, else the first two). Nothing is computed here: values,
  labels and the headline are the strings already shown in the ficha;
- ``updating`` is true when a HOLD record exists for a period newer than the live one (``hold/<slug>-<period>.json``),
  i.e. a newer release is being verified ("Actualizándose");
- an active family without a live ficha, and every planned family, is listed without figures (``state`` "pending" /
  "planned").

The piece id is the inbox's (``stats-ficha:<family>:<period>``), so the read state is shared with the Chile feed.
"""
from __future__ import annotations

from pathlib import Path

from . import stats_fichas as sf

SCHEMA = "datos_index_v1"
SOURCE_SHORT = {"Superintendencia de Salud": "SIS"}


def period_short(period: str | None, kind: str | None = None) -> str | None:
    """'2026-08' → 'ago 2026' (Spanish month, three letters); a quarterly family (``period_kind: quarter``, F12/F13,
    whose period is the quarter's last month) → 'abr–jun 2026'."""
    try:
        y, m = sf.period_parts(str(period or ""))
    except ValueError:
        return None
    if kind == "quarter" and m % 3 == 0:
        return f"{sf.MONTHS_ES[m - 3][:3]}–{sf.MONTHS_ES[m - 1][:3]} {y}"
    return f"{sf.MONTHS_ES[m - 1][:3]} {y}"


def _kpis(ficha: dict, wanted: list[str] | None) -> list[dict]:
    kpis = [k for k in ficha.get("kpis") or [] if isinstance(k, dict) and k.get("value") and k.get("label")]
    if wanted:
        by_id = {k.get("id"): k for k in kpis}
        chosen = [by_id[i] for i in wanted if i in by_id]
    else:
        chosen = kpis
    return [{"id": k.get("id"), "label": k["label"], "value": k["value"]} for k in chosen[:2]]


def _day(value) -> str | None:
    s = str(value or "")[:10]
    return s if len(s) == 10 else None


def newer_hold(holds: dict[str, list[str]], period: str) -> str | None:
    """Newest held period strictly after the live one, if any."""
    try:
        live = sf.period_parts(period)
    except ValueError:
        return None
    newer = []
    for p in holds:
        try:
            if sf.period_parts(p) > live:
                newer.append(p)
        except ValueError:
            continue
    return max(newer, key=sf.period_parts) if newer else None


def build(cards: list[dict], *, registry: dict | None = None, root: Path | None = None,
          generated_at: str | None = None) -> dict:
    registry = registry or sf.load_registry()
    cfg_datos = registry.get("datos") or {}
    groups = [{"key": g["key"], "label": g["label"]} for g in cfg_datos.get("groups") or []]
    known = {g["key"] for g in groups}
    live = {}
    for c in cards:
        f = c.get("stats_ficha")
        if isinstance(f, dict) and f.get("status") == "PASS" and f.get("family"):
            live[f["family"]] = c
    families = []
    for order, (fam, cfg) in enumerate(registry["families"].items()):
        group = cfg.get("group")
        if group not in known:
            raise ValueError(f"datos_group_unknown:{fam}:{group}")
        row = {"family": fam, "label": cfg["label"], "group": group, "order": order,
               "cadence": cfg.get("cadence")}
        card = live.get(fam) if cfg.get("status") == "active" else None
        if card is None:
            row["state"] = "planned" if cfg.get("status") != "active" else "pending"
            families.append(row)
            continue
        ficha = card["stats_ficha"]
        source_name = card.get("source_name") or cfg.get("source_name") or ""
        holds = sf.release_hold_reasons(root, fam, registry) if root is not None else {}
        held = newer_hold(holds, ficha["period"])
        row.update({
            "state": "live",
            "piece_id": card["piece_id"],
            "headline": ficha["headline"],
            "kpis": _kpis(ficha, cfg.get("datos_kpis")),
            "period": ficha["period"],
            "period_label": period_short(ficha["period"], cfg.get("period_kind")),
            "source": cfg.get("source_short") or SOURCE_SHORT.get(source_name) or source_name,
            "source_name": source_name,
            "published_at": _day(ficha.get("published_at")),
            # Same day the inbox sorts by: first verification by Alicanto, else validation, else SIS publication.
            "updated_on": _day(card.get("feed_date")) or _day(card.get("validation_date")) or _day(card.get("event_date")),
            "status": "updating" if held else "current",
            **({"updating_period": held, "updating_period_label": period_short(held, cfg.get("period_kind"))} if held else {}),
            "share_url": card.get("share_url"),
        })
        families.append(row)
    return {"schema_version": SCHEMA, "generated_at": generated_at, "groups": groups, "families": families}
