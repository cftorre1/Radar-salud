"""Resumen interanual del histórico SIS a partir de los agregados ya publicados (sin descargas, sin datos por fila).

Lee ``data/sis_open_data_history/<q>/`` y escribe ``data/sis_open_data_history/resumen_interanual.json`` con:
- GES por problema y por familia (nacional): t vs t-4 en casos, facturado y bonificado por caso;
- especialidades v0 (nacional x tipo de atención): t vs t-4 en episodios, facturado y mediana por episodio;
- índice encadenado de precios por grupo MLE x tipo de atención (base = primer trimestre disponible = 100), a partir
  de los Laspeyres trimestrales mismo prestador / mismo código; un eslabón faltante corta la cadena (no se imputa);
- estado de cada trimestre (ok / omitido y la razón) y el veredicto del probe de folios.
Sólo se comparan celdas publicadas en ambos trimestres.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aggregate_sis_open_data as base  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "data" / "sis_open_data_history"


def load(root: Path, q: str, prefix: str):
    ps = sorted((root / q).glob(f"{prefix}*.json"))
    return json.loads(ps[-1].read_text(encoding="utf-8")) if ps else None


def var(a, b):
    return round((a / b - 1) * 100, 1) if a is not None and b else None


def build(root: Path = ROOT) -> dict:
    qs = sorted((p.name for p in root.iterdir() if p.is_dir() and base.QUARTER.match(p.name)), key=base.quarter_key)
    estados, ges, fam, spec = {}, {}, {}, {}
    for q in qs:
        rec = load(root, q, "receipts_")
        estados[q] = {"estado": rec.get("estado") if rec else None,
                      "razon": rec.get("razon_omision") if rec else None,
                      "filas": ((rec or {}).get("archivo", {}).get("parse") or {}).get("rows_ok")}
        pr = load(root, q, "folios_probe_")
        if pr:
            estados[q]["pam_valido"] = pr["veredicto"]["agrupacion_por_pam_valida"]
        g = load(root, q, "ges_gpp_")
        if g:
            ges[q] = {r["problema"]: r for r in g["por_problema_nacional"]["filas"]}
            fam[q] = {r["familia"]: r for r in g["por_familia_nacional"]["filas"]}
        s = load(root, q, "especialidades_v0_")
        if s:
            spec[q] = {(r["especialidad"], r["tipo_atencion"]): r for r in s["filas"] if r["estado"] == "publicable"}

    def yoy(store: dict, keyname) -> list:
        out = []
        for q in qs:
            k = base.quarter_key(q) - 4
            p = f"{k // 4}t{k % 4 + 1}"
            if q not in store or p not in store:
                continue
            for key, cur in store[q].items():
                prev = store[p].get(key)
                if prev is None:
                    continue
                row = {"periodo": q, "periodo_comparado": p, **keyname(key, cur)}
                if "casos" in cur:
                    cpc, ppc = (cur["bonificado"] / cur["casos"] if cur["casos"] else None,
                                prev["bonificado"] / prev["casos"] if prev["casos"] else None)
                    row.update(casos=cur["casos"], casos_anterior=prev["casos"], var_casos_pct=var(cur["casos"], prev["casos"]),
                               facturado=cur["facturado"], var_facturado_pct=var(cur["facturado"], prev["facturado"]),
                               bonificado_por_caso=round(cpc) if cpc else None,
                               var_bonificado_por_caso_pct=var(cpc, ppc))
                else:
                    row.update(episodios=cur["episodios"], episodios_anterior=prev["episodios"],
                               var_episodios_pct=var(cur["episodios"], prev["episodios"]),
                               facturado=cur["facturado"], var_facturado_pct=var(cur["facturado"], prev["facturado"]),
                               mediana=cur["costo_episodio_mediana"],
                               var_mediana_pct=var(cur["costo_episodio_mediana"], prev["costo_episodio_mediana"]))
                out.append(row)
        return out

    chains: dict = {}
    for q in qs:
        ix = load(root, q, "indice_precios_")
        if not ix:
            continue
        for a in ix["agregados"]:
            if a["estado"] != "publicable":
                continue
            key = f"{a['grupo_mle']}|{a['tipo_atencion']}"
            for metric in ("laspeyres_facturado_recortado_pct", "laspeyres_bonificado_recortado_pct"):
                v = a.get(metric)
                c = chains.setdefault(key, {}).setdefault(metric, {"base": ix["periodo_anterior"], "serie": {ix["periodo_anterior"]: 100.0}})
                last = max(c["serie"], key=base.quarter_key)
                if v is None or last != ix["periodo_anterior"]:
                    continue  # eslabón faltante: la cadena se corta
                c["serie"][q] = round(c["serie"][last] * (1 + v / 100), 3)
    return {"definicion": __doc__.strip(), "trimestres": estados,
            "ges_problema_interanual": yoy(ges, lambda k, r: {"problema": k, "nombre": r["nombre"], "familia": r["familia"]}),
            "ges_familia_interanual": yoy(fam, lambda k, r: {"familia": k}),
            "especialidades_interanual": yoy(spec, lambda k, r: {"especialidad": k[0], "tipo_atencion": k[1]}),
            "indice_encadenado": chains}


def main() -> None:
    base.write_json(ROOT / "resumen_interanual.json", build())


if __name__ == "__main__":
    main()
