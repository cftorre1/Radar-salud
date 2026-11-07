"""Réplica del IVUBI del ICSA y reconciliación con los agregados trimestrales Alicanto (sin GES, como el ICSA).

Entradas (todas públicas o agregadas):
- base oficial ICPRE de la SIS (tipo_atencion x código x mes, bonificado y frecuencia nominales), canasta con
  ponderadores IVUBI y el IPC de los insumos ICSA, en data/reference/icsa/<año>/;
- ``data/sis_open_data_history/<q>/icsa_canasta_<q>.json`` del backfill histórico.

Salidas en ``data/sis_open_data_history/icsa_reconciliacion_<año>.json``:
1. ``oficial_mensual``: IVUBI replicado con la base oficial y el algoritmo del documento metodológico (encadenado
   mensual, deflactado por IPC, ponderadores IVUBI del año base, rebase al promedio del año base = 100, promedio de
   las 12 variaciones a 12 meses);
2. ``oficial_trimestral``: el mismo con la base oficial sumada a trimestres (aísla el efecto de granularidad);
3. ``alicanto_trimestral``: el mismo con nuestros agregados trimestrales;
4. ``totales``: bonificado y frecuencia por tipo de atención y trimestre, oficial vs Alicanto, sobre los códigos de la
   canasta presentes en ambos.
Se compara contra el valor publicado; brecha > 1 pp -> HOLD. Las homologaciones de códigos no se aplican [pendiente].
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aggregate_sis_open_data as base  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "data" / "reference" / "icsa"
HIST = ROOT / "data" / "sis_open_data_history"
PUBLISHED = {2025: {"general": 0.8, "Ambulatoria": 0.9, "Hospitalaria": 0.7},
             2024: {"general": 3.0, "Ambulatoria": 2.4, "Hospitalaria": 3.5},
             2023: {"general": 3.0, "Ambulatoria": 4.0, "Hospitalaria": 2.2}}
CONFIG = {2025: ("2025/6-bbdd_enero2024_diciembre2025_icpre.csv",
                 "2025/4-mle_canasta_ponderadores_homologaciones_icsa_2025.xlsx",
                 "2025/5-insumos_ipc__cartera_icsa_2025.xlsx")}
TIPOS = {1: "Ambulatoria", 2: "Hospitalaria"}


def _sheets(path: Path) -> dict:
    import openpyxl  # sólo para leer los XLSX oficiales
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    return {ws.title.lower(): list(ws.iter_rows(values_only=True)) for ws in wb.worksheets}


def load_official(year: int):
    csv_p, can_p, ipc_p = (REF / x for x in CONFIG[year])
    sh = _sheets(can_p)
    canasta = {}
    for t, key in ((1, "canasta amb"), (2, "canasta hosp")):
        rows = next(v for k, v in sh.items() if k.startswith(key))
        canasta[TIPOS[t]] = {str(int(r[0])).zfill(7): float(r[1]) for r in rows[2:]
                             if r and isinstance(r[0], (int, float)) and r[1] is not None}
    lv = next(v for k, v in sh.items() if k.startswith("ponderadores"))
    lvl = dict(zip(lv[0], lv[1]))
    level = {"Ambulatoria": float(lvl["Ponderador IVUBI ambulatorio"]),
             "Hospitalaria": float(lvl["Ponderador IVUBI hospitalario"])}
    data: dict = defaultdict(dict)
    with open(csv_p, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh, delimiter=";"):
            code = str(int(r["codigo_prestacion"])).zfill(7)
            data[(TIPOS[int(r["tipo_atencion"])], code)][int(r["periodo"])] = (
                float(r["suma_bonificado"].replace(",", ".")), float(r["suma_frecuencia"].replace(",", ".")))
    months = sorted({p for v in data.values() for p in v})
    ipc_rows = _sheets(ipc_p)["ipc"][1:]
    ipc = dict(zip(months, [float(r[1]) for r in ipc_rows if r[1] is not None]))
    return canasta, level, data, months, ipc


def ivubi(series: dict, periods: list, deflator: dict, canasta: dict, level: dict, per_year: int) -> dict:
    """series: (tipo, code) -> {period: (bonificado, frecuencia)}; algoritmo del documento metodológico."""
    out, idx = {}, {}
    for tipo, weights in canasta.items():
        tot = {p: 0.0 for p in periods}
        wsum = 0.0
        for code, w in weights.items():
            s = series.get((tipo, code), {})
            if not all(p in s and s[p][1] > 0 and s[p][0] > 0 for p in periods):
                continue
            p0 = s[periods[0]][0] / s[periods[0]][1]
            for p in periods:
                tot[p] += w * (100 * (s[p][0] / s[p][1]) / p0) / deflator[p] * 100
            wsum += w
        if not wsum:
            continue
        b = sum(tot[p] for p in periods[:per_year]) / per_year
        idx[tipo] = {p: tot[p] / b * 100 for p in periods}
        out[f"peso_canasta_cubierto_{tipo}"] = round(wsum / sum(weights.values()), 4)
    if len(idx) == 2:
        gen = {p: sum(level[t] * idx[t][p] for t in idx) / sum(level[t] for t in idx) for p in periods}
        idx["general"] = gen

    def avg(ix):
        n = len(periods) - per_year
        return round((sum(ix[periods[i]] / ix[periods[i - per_year]] for i in range(per_year, len(periods))) / n - 1) * 100, 2)
    out.update({f"ivubi_{k}_pct": avg(v) for k, v in idx.items()})
    return out


def quarter_of(month: int) -> str:
    y, m = divmod(month, 100)
    return f"{y}t{(m - 1) // 3 + 1}"


def run(year: int) -> dict:
    canasta, level, data, months, ipc = load_official(year)
    res = {"anio_icsa": year, "publicado": PUBLISHED.get(year), "definicion": __doc__.strip()}
    res["oficial_mensual"] = ivubi(data, months, ipc, canasta, level, 12)
    qs = sorted({quarter_of(m) for m in months}, key=base.quarter_key)
    qdata: dict = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
    for k, s in data.items():
        for m, (b, f) in s.items():
            a = qdata[k][quarter_of(m)]
            a[0] += b; a[1] += f
    qipc = {q: sum(ipc[m] for m in months if quarter_of(m) == q) / 3 for q in qs}
    res["oficial_trimestral"] = ivubi({k: {q: tuple(v) for q, v in s.items()} for k, s in qdata.items()},
                                      qs, qipc, canasta, level, 4)
    ours: dict = defaultdict(dict)
    missing = []
    for q in qs:
        p = HIST / q / f"icsa_canasta_{q}.json"
        if not p.exists():
            missing.append(q)
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        for row in d["rows"]:
            r = dict(zip(d["columns"], row))
            if r["estado"] == "publicable" and r["frecuencia"]:
                ours[(r["tipo_atencion"], r["codigo_prestacion"])][q] = (float(r["bonificado"]), float(r["frecuencia"]))
    if missing:
        res["alicanto_trimestral"] = {"estado": "pendiente", "trimestres_faltantes": missing}
    else:
        res["alicanto_trimestral"] = ivubi(ours, qs, qipc, canasta, level, 4)
        tot = []
        for q in qs:
            for tipo, weights in canasta.items():
                o = [qdata[(tipo, c)][q] for c in weights if q in qdata.get((tipo, c), {}) and (tipo, c) in ours
                     and q in ours[(tipo, c)]]
                a = [ours[(tipo, c)][q] for c in weights if (tipo, c) in ours and q in ours[(tipo, c)]
                     and q in qdata.get((tipo, c), {})]
                ob, of = sum(x[0] for x in o), sum(x[1] for x in o)
                ab, af = sum(x[0] for x in a), sum(x[1] for x in a)
                tot.append({"periodo": q, "tipo_atencion": tipo, "codigos": len(a), "bonificado_oficial": round(ob),
                            "bonificado_alicanto": round(ab), "dif_bonificado_pct": base.pct(ab - ob, ob),
                            "frecuencia_oficial": round(of), "frecuencia_alicanto": round(af),
                            "dif_frecuencia_pct": base.pct(af - of, of)})
        res["totales"] = tot
        pub = PUBLISHED.get(year) or {}
        gaps = {k: round(res["alicanto_trimestral"].get(f"ivubi_{k}_pct", float("nan")) - v, 2) for k, v in pub.items()}
        res["brecha_vs_publicado_pp"] = gaps
        res["veredicto"] = "PASS" if gaps and all(abs(g) <= 1 for g in gaps.values()) else "HOLD"
    base.write_json(HIST / f"icsa_reconciliacion_{year}.json", res)
    return res


if __name__ == "__main__":
    for y in (int(a) for a in sys.argv[1:] or ["2025"]):
        print(json.dumps(run(y), ensure_ascii=False)[:2000])
