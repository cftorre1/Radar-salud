"""GES por problema (SIS, Prestaciones Bonificadas): publication-safe aggregates and the leak check behind F14.

The historical backfill (``scripts/sis_historico_ges.py``, GES part of ``sis_historico_v3``) writes ``ges_gpp_<q>.json``
with cells of at least 10 distinct GES cases and complementary suppression inside each table. An independent check
(10-nov-2026) found that those files are not safe to publish as they are:

- many published cells have only 1 or 2 providers (a single provider's GES billing, or two that can subtract each
  other), and
- cross-table subtraction recovers hidden cells: family − its published problems, family × Isapre − its published
  problem × Isapre cells, and the intervention letters of a problem.

``sanitize`` keeps only the four tables F14 shows and makes them safe from the published side alone (the row-level
data is never available here):

1. a row is shown only with ≥ ``MIN_CASES`` distinct cases and ≥ ``MIN_PROVIDERS`` distinct pseudonymous providers;
2. for every published parent, the part that is not shown (parent − Σ shown children) is either nothing, or never
   attributable to a single candidate child and, where cases add up (problems within a family, Isapres within a family), ≥ 10 cases;
3. where the source did not apply complementary suppression inside the group (problems within a family, families
   within the GES total), a hidden remainder always gets at least one more hidden child, so it can never be a single
   cell;
4. a hidden problem hides all its regional rows.

``check`` is the attacker's view, run by the builder on every read (any finding → HOLD) and by the tests on the
committed files. Encrypted identifiers never exist in these files: cases were counted in memory as opaque keys.
"""
from __future__ import annotations

from collections import defaultdict

MIN_CASES = 10
MIN_PROVIDERS = 3
PUBLIC_VERSION = "ges_publicable_v1"
TABLES = ("por_familia_nacional", "por_problema_nacional", "por_familia_isapre", "por_problema_region")
MONEY = ("facturado", "bonificado", "frecuencia")


def family_of(ref: dict) -> dict[int, str]:
    return {int(p): f for f, ps in (ref.get("familias") or {}).items() for p in ps}


def _tol(kids: list[dict]) -> int:
    """Each row is rounded to the peso: a remainder up to the number of rounded terms is rounding, not a cell."""
    return len(kids) + 1


def groups(doc: dict, ref: dict) -> list[dict]:
    """Every published linear relation between the four tables: parent row, shown children, the universe of possible
    children (seen in shown rows), whether cases add up across children, and whether the source applied complementary suppression."""
    fam = family_of(ref)
    T = {t: (doc.get(t) or {}).get("filas") or [] for t in TABLES}
    # Candidates are the Isapres / regions that appear in some shown row of the same table: an Isapre or region never
    # shown is not a credible place for a remainder, so it never counts as cover (stricter than the declared universe).
    isapres = {r["isapre"] for r in T["por_familia_isapre"]}
    regions = {r["region"] for r in T["por_problema_region"]}
    families = set((ref.get("familias") or {})) | {r["familia"] for r in T["por_familia_nacional"]}
    out = []
    tot = doc.get("totales") or {}
    out.append({"tag": "total<-familia", "parent": {"facturado": tot.get("facturado"), "bonificado": tot.get("bonificado"),
                                                    "frecuencia": tot.get("frecuencia"), "casos": None},
                "kids": T["por_familia_nacional"], "key": "familia", "universe": families, "additive": False,
                "complemented": False})
    pn = {r["problema"]: r for r in T["por_problema_nacional"]}
    for fr in T["por_familia_nacional"]:
        f = fr["familia"]
        kids = [r for p, r in pn.items() if fam.get(p, "otros") == f]
        universe = {p for p in fam if fam[p] == f} | {r["problema"] for r in kids}
        out.append({"tag": f"familia<-problema:{f}", "parent": fr, "kids": kids, "key": "problema", "universe": universe,
                    "additive": True, "complemented": False})
        kids = [r for r in T["por_familia_isapre"] if r["familia"] == f]
        out.append({"tag": f"familia<-isapre:{f}", "parent": fr, "kids": kids, "key": "isapre", "universe": isapres,
                    "additive": True, "complemented": True})
    by = defaultdict(list)
    for r in T["por_problema_region"]:
        by[r["problema"]].append(r)
    for p, pr in pn.items():
        out.append({"tag": f"problema<-region:{p}", "parent": pr, "kids": by.get(p, []), "key": "region",
                    "universe": regions, "additive": False, "complemented": True})
    return out


def group_findings(g: dict) -> list[str]:
    par, kids = g["parent"], g["kids"]
    if par.get("facturado") is None:
        return []
    out = []
    shown = {k[g["key"]] for k in kids}
    cand = set(g["universe"]) - shown
    rest = {m: (par.get(m) or 0) - sum(k.get(m) or 0 for k in kids) for m in MONEY}
    if any(v < -_tol(kids) for v in rest.values()):
        out.append(f"children_exceed_parent:{g['tag']}")
    hidden = rest["facturado"] > _tol(kids)
    if hidden and len(cand) == 1:  # no candidate at all: nothing new can be attributed to any child
        out.append(f"single_candidate:{g['tag']}")
    if hidden and g["additive"] and par.get("casos") is not None:
        rc = par["casos"] - sum(k["casos"] for k in kids)
        if 0 < rc < MIN_CASES:
            out.append(f"hidden_cases_under_{MIN_CASES}:{g['tag']}")
    return out


def check(doc: dict, ref: dict) -> list[str]:
    """Attacker's view of a publication-safe file: every shown row meets the minimums, a hidden problem has no
    regional rows, and no hidden cell or small hidden group can be recovered by subtraction."""
    out = []
    if doc.get("version_publicable") != PUBLIC_VERSION:
        out.append(f"public_version:{doc.get('version_publicable')}")
    for t in TABLES:
        for r in (doc.get(t) or {}).get("filas") or []:
            tag = f"{t}:{r.get('problema', r.get('familia'))}:{r.get('isapre', '')}{r.get('region', '')}"
            if not isinstance(r.get("casos"), int) or r["casos"] < MIN_CASES:
                out.append(f"cell_under_{MIN_CASES}_cases:{tag}")
            if not isinstance(r.get("n_prestadores"), int) or r["n_prestadores"] < MIN_PROVIDERS:
                out.append(f"cell_under_{MIN_PROVIDERS}_providers:{tag}")
    for t in set(doc) - set(TABLES):
        if isinstance(doc[t], dict) and "filas" in doc[t]:
            out.append(f"table_not_allowed:{t}")
    shown_p = {r["problema"] for r in (doc.get("por_problema_nacional") or {}).get("filas") or []}
    for r in (doc.get("por_problema_region") or {}).get("filas") or []:
        if r["problema"] not in shown_p:
            out.append(f"region_row_of_hidden_problem:{r['problema']}:{r['region']}")
    for g in groups(doc, ref):
        out += group_findings(g)
    return out


def sanitize(src: dict, ref: dict) -> tuple[dict, dict]:
    """(publication-safe doc, suppression report) from a source ``ges_gpp_<q>.json``. Raises ValueError when a family
    or the GES total itself would have to be hidden (the ficha then has nothing safe to stand on)."""
    rep = {"filas_fuente": {}, "suprimidas_por_casos": 0, "suprimidas_por_prestadores": 0, "suprimidas_complementarias": 0,
           "suprimidas_por_problema_oculto": 0, "tablas_omitidas": []}
    isapres, regions = set(), set()
    for t, v in src.items():
        if isinstance(v, dict) and "filas" in v:
            rep["filas_fuente"][t] = len(v["filas"])
            isapres |= {r["isapre"] for r in v["filas"] if "isapre" in r}
            regions |= {r["region"] for r in v["filas"] if "region" in r}
            if t not in TABLES:
                rep["tablas_omitidas"].append(t)
    order = lambda x: (not str(x).isdigit(), int(x) if str(x).isdigit() else 0, str(x))  # noqa: E731
    doc: dict = {"universos": {"isapres": sorted(isapres, key=order), "regiones": sorted(regions, key=order)}}
    for t in TABLES:
        keep = []
        for r in src[t]["filas"]:
            if r["casos"] < MIN_CASES:
                rep["suprimidas_por_casos"] += 1
            elif r["n_prestadores"] < MIN_PROVIDERS:
                rep["suprimidas_por_prestadores"] += 1
            else:
                keep.append(dict(r))
        doc[t] = {"filas": keep}
    doc["totales"] = dict(src["totales"])
    doc["version_publicable"] = PUBLIC_VERSION
    shown_fams = {r["familia"] for r in doc["por_familia_nacional"]["filas"]}
    if shown_fams != {r["familia"] for r in src["por_familia_nacional"]["filas"]}:
        raise ValueError("family_row_would_be_hidden")
    own: dict[str, int] = defaultdict(int)
    for _ in range(500):
        changed = False
        shown_p = {r["problema"] for r in doc["por_problema_nacional"]["filas"]}
        before = len(doc["por_problema_region"]["filas"])
        doc["por_problema_region"]["filas"] = [r for r in doc["por_problema_region"]["filas"] if r["problema"] in shown_p]
        rep["suprimidas_por_problema_oculto"] += before - len(doc["por_problema_region"]["filas"])
        for g in groups(doc, ref):
            par, kids = g["parent"], g["kids"]
            hidden = (par.get("facturado") or 0) - sum(k["facturado"] for k in kids) > _tol(kids)
            need = bool(group_findings(g)) or (hidden and not g["complemented"] and own[g["tag"]] == 0)
            if not need or not kids:
                continue
            if g["tag"] == "total<-familia":
                raise ValueError("family_row_would_be_hidden")
            victim = min(kids, key=lambda k: (k["casos"], k["facturado"], str(k[g["key"]])))
            table = {"problema": "por_problema_nacional", "isapre": "por_familia_isapre", "region": "por_problema_region"}[g["key"]]
            doc[table]["filas"] = [r for r in doc[table]["filas"] if r is not victim]
            own[g["tag"]] += 1
            rep["suprimidas_complementarias"] += 1
            changed = True
            break  # groups change after each suppression: recompute them
        if not changed:
            break
    else:
        raise ValueError("suppression_did_not_converge")
    for t in TABLES:
        doc[t]["celdas_ocultas"] = rep["filas_fuente"].get(t, 0) - len(doc[t]["filas"])
    left = check(doc, ref)
    if left:
        raise ValueError("leak_after_sanitize:" + ";".join(left[:5]))
    return doc, rep
