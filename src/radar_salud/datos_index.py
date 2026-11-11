"""Index for the "Datos" page (Dirección, 3-nov-2026): the latest published ficha of each statistics family.

``web/data/datos.json`` lists every family of ``config/stats_fichas_v1.json`` once:

- an active family with a live ficha in the snapshot (``stats_ficha`` card, PASS) carries that ficha's verified headline
  and 1–2 of its KPIs copied verbatim (``datos_kpis`` by id, else the first two). Nothing is computed here: values,
  labels and the headline are the strings already shown in the ficha;
- since Dirección 10-nov-2026 the overview card shows a descriptive title (registry ``index_title``, else the family
  label) and the ficha's topic index: ``topics`` lists the published ficha's ``tabs`` (``id``/``label`` verbatim, in
  order, same filter and id rule as the ficha renderer) so each topic deep-links to ``&tema=<id>``. The card looks and
  behaves as the Chile feed row of the same piece (Dirección 10-nov 22:05): ``feed_row`` copies, verbatim, the card
  fields the shared row date line reads (web/data-card.js ``rowDate``/``feedSource``), and ``share_title`` is the
  title the Chile row shares;
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


def _topics(ficha: dict) -> list[dict]:
    """The ficha's tabs as the renderer lists them (web/stats-ficha.js ``topics``): tabs with a label, in order; the id
    is the tab's own id (the renderer falls back to the position, so this does too)."""
    tabs = [t for t in ficha.get("tabs") or [] if isinstance(t, dict) and t.get("label")]
    return [{"id": str(t.get("id") or i), "label": t["label"]} for i, t in enumerate(tabs)]


# The fields of a feed card that the shared row date line («Detectado 10 nov 2026 · SIS») reads.
FEED_ROW_KEYS = ("date_basis", "first_detected_at", "event_date", "data_release_date", "event_type", "emission_date",
                 "issued_on", "event_date_basis", "published_on", "publication_date", "detected_at", "signal_types",
                 "source_name", "source_link", "source_url", "source_link_status")


def _feed_row(card: dict) -> dict:
    return {k: card[k] for k in FEED_ROW_KEYS if card.get(k) not in (None, "", [])}


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
               "cadence": cfg.get("cadence"), "index_title": cfg.get("index_title") or cfg["label"]}
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
            "topics": _topics(ficha),
            "period": ficha["period"],
            "period_label": period_short(ficha["period"], cfg.get("period_kind")),
            "source": cfg.get("source_short") or SOURCE_SHORT.get(source_name) or source_name,
            "source_name": source_name,
            # Dirección 11-nov-2026: the organism alone does not tell two SIS sources apart; name the dataset too.
            **({"source_dataset": cfg["source_dataset"]} if cfg.get("source_dataset") else {}),
            "published_at": _day(ficha.get("published_at")),
            # Same day the inbox sorts by: first verification by Alicanto, else validation, else SIS publication.
            "updated_on": _day(card.get("feed_date")) or _day(card.get("validation_date")) or _day(card.get("event_date")),
            "status": "updating" if held else "current",
            **({"updating_period": held, "updating_period_label": period_short(held, cfg.get("period_kind"))} if held else {}),
            "share_url": card.get("share_url"),
            # Dirección 11-nov-2026: share the ficha's generic name and period, not one view's finding.
            "share_title": " · ".join(x for x in (cfg.get("index_title") or ficha.get("family_label") or ficha["headline"],
                                                  period_short(ficha.get("period"), cfg.get("period_kind"))) if x),
            "feed_row": _feed_row(card),
        })
        families.append(row)
    return {"schema_version": SCHEMA, "generated_at": generated_at, "groups": groups, "families": families}
