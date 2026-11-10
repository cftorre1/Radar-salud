"""GES part of the historical SIS backfill (``sis_historico_v3``, branch ``claude/sis-historico``): spend, frecuencia
and distinct cases by GES health problem (numeric prefix of ``codigo_gpp``), family, Isapre and region.

Only what ficha F14 needs was brought over from ``scripts/sis_historico_backfill.py`` (Dirección approved that
backfill on 6-nov-2026): the GPP parser, the DS 29 reference, the GES accumulator and its tables, unchanged. The price
index, folio probe and specialty parts stay on that branch.

Output per quarter (``--quarter 2026t3 [--zip local.zip]``; without ``--zip`` the ZIP is discovered and streamed with
the aggregator's network rules: robots.txt, User-Agent, 1 GiB cap, deleted after parsing):

- ``ges_gpp_publicable_<q>.json``: the GES tables after ``radar_salud.ges_privacy.sanitize`` (≥ 10 cases and ≥ 3
  providers per row, complementary suppression across tables, four tables only). The unsanitized tables live only in
  memory; they are never written by this script;
- ``receipts_<q>.json``: URL, bytes, SHA-256, rows, schema check and facturado by tipo de atención.

Encrypted identifiers (RUN, RUT prestador, folios, id GES) are opaque keys that live only in memory; they are never
reversed or written, not even as a hash. Field map (public file, 30 fields; Compendio SIS 07.09.2026, Título V):
public 29 = master 34 (GPP), public 30 = master 35 (id GES); 0-based indices come from ``aggregate_sis_open_data``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aggregate_sis_open_data as base  # noqa: E402  (robots, tope 1 GiB, streaming, RowReader)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from radar_salud import ges_privacy  # noqa: E402

SCRIPT_VERSION = "sis_historico_v3"  # same GES code as the backfill: its outputs and these are comparable
OUT_ROOT = ROOT / "data" / "sis_open_data_history"
GES_REF = ROOT / "data" / "reference" / "ges_problemas_ds29_2025.json"
DATASET = "Prestaciones Bonificadas"

I_ISAPRE, I_PREST, I_REGION = base.P_ISAPRE, base.P_PRESTADOR, base.P_REGION
I_COB, I_ATN = base.P_COBERTURA, base.P_TIPO_ATENCION
I_FREC, I_FACT, I_BONIF, I_GPP, I_GES = base.P_FREC, base.P_FACT, base.P_BONIF, base.P_GPP, base.P_GES
NO_PROVIDER = base.NO_PROVIDER

GES_MIN_CASES = 10
SCHEMA_MAX_UNKNOWN_PCT = 0.5
SCHEMA_MAX_MALFORMED_PCT = 1.0
ATN = {"atencion ambulatoria": "Ambulatoria", "ambulatoria": "Ambulatoria", "ambulatorio": "Ambulatoria",
       "1": "Ambulatoria", "atencion hospitalaria": "Hospitalaria", "hospitalaria": "Hospitalaria",
       "hospitalario": "Hospitalaria", "2": "Hospitalaria"}
COB = {"ges": "ges", "1": "ges", "caec": "caec", "2": "caec", "ges-caec": "ges_caec", "3": "ges_caec",
       "plan complementario": "plan_complementario", "4": "plan_complementario", "no bonificado": "no_bonificado",
       "5": "no_bonificado", "otro": "otro", "6": "otro"}
GPP_RX = re.compile(r"^(\d{1,3})([A-Za-z])(\d{0,4})$")


def load_ges_reference(path: Path = GES_REF) -> dict:
    d = json.loads(path.read_text(encoding="utf-8"))
    fam_of = {int(p): f for f, ps in d["familias"].items() for p in ps}
    return {"names": {int(k): v for k, v in d["problemas"].items()}, "family": fam_of, "fuentes": d["fuentes"], "raw": d}


def parse_gpp(gpp: str) -> tuple[int, str] | None:
    """'21T1' -> (21, 'T'); 'X' o vacío -> None. El prefijo numérico es el n° de problema (Compendio, campo 34)."""
    m = GPP_RX.match(gpp.strip())
    if not m:
        return None
    return int(m.group(1)), m.group(2).upper()


def _norm_cached(cache: dict, vocab: dict, raw: str) -> str | None:
    try:
        return cache[raw]
    except KeyError:
        n = base.norm(raw)
        v = vocab.get(n)
        if v is None:
            for k, val in vocab.items():
                if not k.isdigit() and n.startswith(k):
                    v = val
                    break
        cache[raw] = v
        return v


def complementary(sizes: dict, initial: set, groups: list[list], min_hidden: int) -> set:
    """Supresión complementaria genérica: parte de ``initial`` y, mientras un grupo publicado tenga un remanente
    oculto entre 1 y min_hidden-1, suprime la celda publicada más pequeña del grupo. Repite hasta estabilizar."""
    sup = set(initial)
    changed = True
    while changed:
        changed = False
        for g in groups:
            hidden = sum(sizes[k] for k in g if k in sup)
            n_hidden = sum(1 for k in g if k in sup)
            while (0 < hidden < min_hidden) or n_hidden == 1:
                rest = sorted((sizes[k], str(k)) for k in g if k not in sup)
                if not rest:
                    break
                key = next(k for k in g if str(k) == rest[0][1] and k not in sup)
                sup.add(key)
                hidden += sizes[key]
                n_hidden += 1
                changed = True
    return sup


class GesAgg:
    """One quarter, GES part only (same accumulation as ``QuarterAgg`` in the backfill)."""

    def __init__(self):
        self.rows = 0
        self.err: Counter = Counter()
        self.unknown: dict[str, Counter] = defaultdict(Counter)
        self._c_atn: dict = {}
        self._c_cob: dict = {}
        self.total_fact = 0.0
        self.tot_atn: dict[str, list] = defaultdict(lambda: [0.0, 0.0, 0.0, 0])
        self.ges: dict[tuple, list] = {}      # (problema, isapre, region) -> [fact, bonif, frec, casos, prov]
        self.ges_letter: dict[tuple, list] = {}
        self.ges_tot = [0.0, 0.0, 0.0, 0]
        self.ges_sin_gpp = [0.0, 0]
        self.ges_sin_id = 0
        self.gpp_unparsed: Counter = Counter()

    def _atn(self, raw):
        v = _norm_cached(self._c_atn, ATN, raw)
        if v is None:
            self.unknown["tipo_atencion"][raw.strip()[:40]] += 1
        return v

    def _cob(self, raw):
        v = _norm_cached(self._c_cob, COB, raw)
        if v is None:
            self.unknown["cobertura_financiamiento"][raw.strip()[:40]] += 1
        return v

    def add(self, f: list[str]) -> None:
        self.rows += 1
        num, err = base.num, self.err
        atn = self._atn(f[I_ATN])
        cob = self._cob(f[I_COB])
        region = f[I_REGION].strip() or "(vacío)"
        fact = num(f[I_FACT], err, "valor_facturado")
        freq = num(f[I_FREC], err, "frecuencia")
        bonif = num(f[I_BONIF], err, "valor_bonificado")
        isapre, prov = f[I_ISAPRE].strip(), f[I_PREST].strip()
        t = self.tot_atn[atn or "(desconocido)"]
        t[0] += fact; t[1] += bonif; t[2] += freq; t[3] += 1
        self.total_fact += fact
        gpp = f[I_GPP].strip()
        if gpp and gpp.upper() != "X":
            p = parse_gpp(gpp)
            if p is None:
                self.gpp_unparsed["no_parseable"] += 1
                return
            prob, letter = p
            idg = f[I_GES].strip()
            case = None
            if idg and idg.upper() != "X":
                case = hash((isapre, idg))  # llave opaca en memoria (hash aleatorizado por proceso); nunca se escribe
            else:
                self.ges_sin_id += 1
            for store, k in ((self.ges, (prob, isapre, region)), (self.ges_letter, (prob, letter))):
                c = store.get(k)
                if c is None:
                    c = store[k] = [0.0, 0.0, 0.0, set(), set()]
                c[0] += fact; c[1] += bonif; c[2] += freq
                if case is not None:
                    c[3].add(case)
                if prov not in NO_PROVIDER:
                    c[4].add(prov)
            g = self.ges_tot
            g[0] += fact; g[1] += bonif; g[2] += freq; g[3] += 1
        elif cob == "ges":
            self.ges_sin_gpp[0] += fact; self.ges_sin_gpp[1] += 1

    def schema_check(self, parse: dict) -> dict:
        lines = max(parse.get("lines_read", 0) - parse.get("blank_lines", 0) - (1 if parse.get("header_row_detected") else 0), 0)
        malformed_pct = base.pct(parse.get("rows_malformed", 0), lines) or 0.0
        unknown = {k: base.pct(sum(v.values()), self.rows) or 0.0 for k, v in self.unknown.items()}
        reasons = []
        if not self.rows:
            reasons.append("sin_filas_con_30_campos")
        if malformed_pct > SCHEMA_MAX_MALFORMED_PCT:
            reasons.append(f"filas_con_n_campos_distinto_a_{base.PREST_N}:{malformed_pct}%")
        for k, v in unknown.items():
            if v > SCHEMA_MAX_UNKNOWN_PCT:
                reasons.append(f"valores_no_mapeados_{k}:{v}%")
        return {"ok": not reasons, "razones": reasons, "pct_filas_malformadas": malformed_pct,
                "pct_valores_no_mapeados": unknown, "gpp_no_parseable": dict(self.gpp_unparsed)}

    def ges_tables(self, ref: dict) -> dict:
        """The backfill's GES tables, verbatim (in memory only here; ``ges_privacy.sanitize`` decides what is written)."""
        names, family = ref["names"], ref["family"]

        def label(p):
            return names.get(p, f"problema {p}")

        def cell(v: list) -> dict:
            return {"casos": len(v[3]), "facturado": round(v[0]), "bonificado": round(v[1]), "frecuencia": round(v[2]),
                    "n_prestadores": len(v[4])}

        def merge(items: Iterable[list]) -> list:
            acc = [0.0, 0.0, 0.0, set(), set()]
            for v in items:
                acc[0] += v[0]; acc[1] += v[1]; acc[2] += v[2]; acc[3] |= v[3]; acc[4] |= v[4]
            return acc

        by_pi: dict[tuple, list] = defaultdict(list)
        by_pr: dict[tuple, list] = defaultdict(list)
        by_p: dict[int, list] = defaultdict(list)
        by_fi: dict[tuple, list] = defaultdict(list)
        by_f: dict[str, list] = defaultdict(list)
        for (p, i, reg), v in self.ges.items():
            by_pi[(p, i)].append(v); by_pr[(p, reg)].append(v); by_p[p].append(v)
            fam = family.get(p, "otros")
            by_fi[(fam, i)].append(v); by_f[fam].append(v)
        pi = {k: merge(v) for k, v in by_pi.items()}
        pr = {k: merge(v) for k, v in by_pr.items()}
        pn = {k: merge(v) for k, v in by_p.items()}
        fi = {k: merge(v) for k, v in by_fi.items()}
        fn = {k: merge(v) for k, v in by_f.items()}

        def sup_one_way(cells: dict, parent_of) -> set:
            sizes = {k: len(v[3]) for k, v in cells.items()}
            init = {k for k, s in sizes.items() if s < GES_MIN_CASES}
            groups: dict = defaultdict(list)
            for k in cells:
                groups[parent_of(k)].append(k)
            return complementary(sizes, init, list(groups.values()), GES_MIN_CASES)

        sup_pn = {k for k, v in pn.items() if len(v[3]) < GES_MIN_CASES}
        sup_pi = sup_one_way(pi, lambda k: k[0])
        sup_pr = sup_one_way(pr, lambda k: k[0])
        sup_fn = {k for k, v in fn.items() if len(v[3]) < GES_MIN_CASES}
        sup_fi = sup_one_way(fi, lambda k: k[0])

        def rows(cells: dict, sup: set, keyf) -> tuple[list, dict]:
            out, hidden = [], 0
            for k in sorted(cells, key=lambda x: tuple(str(y).zfill(4) for y in (x if isinstance(x, tuple) else (x,)))):
                if k in sup:
                    hidden += 1
                    continue
                out.append({**keyf(k), **cell(cells[k])})
            return out, {"celdas_suprimidas": hidden}

        def pk(p):
            return {"problema": p, "nombre": label(p), "familia": family.get(p, "otros")}

        nat, nat_s = rows(pn, sup_pn, pk)
        isa, isa_s = rows(pi, sup_pi, lambda k: {**pk(k[0]), "isapre": k[1]})
        reg, reg_s = rows(pr, sup_pr, lambda k: {**pk(k[0]), "region": k[1]})
        fam_n, fam_n_s = rows(fn, sup_fn, lambda k: {"familia": k})
        fam_i, fam_i_s = rows(fi, sup_fi, lambda k: {"familia": k[0], "isapre": k[1]})
        g = self.ges_tot
        return {
            "definicion": "Filas con codigo_gpp (campo 34 del Compendio) distinto de 'X'; problema = prefijo numérico del "
                          "GPP; casos = id GES distintos (campo 35) por Isapre, contados en memoria como llave opaca. "
                          f"Celdas con >= {GES_MIN_CASES} casos; supresión complementaria dentro de cada problema. Los "
                          "casos no son aditivos entre regiones o intervenciones (un caso puede tener filas en varias).",
            "fuente_nombres": ref["fuentes"],
            "totales": {"filas_con_gpp": g[3], "facturado": round(g[0]), "bonificado": round(g[1]),
                        "frecuencia": round(g[2]), "pct_facturado_del_trimestre": base.pct(g[0], self.total_fact),
                        "filas_gpp_sin_id_ges": self.ges_sin_id,
                        "ges_sin_gpp": {"filas": self.ges_sin_gpp[1], "facturado": round(self.ges_sin_gpp[0])}},
            "por_problema_nacional": {"filas": nat, **nat_s},
            "por_problema_isapre": {"filas": isa, **isa_s},
            "por_problema_region": {"filas": reg, **reg_s},
            "por_familia_nacional": {"filas": fam_n, **fam_n_s},
            "por_familia_isapre": {"filas": fam_i, **fam_i_s},
        }


def run_quarter(q: str, out_root: Path = OUT_ROOT, local: Path | None = None, links: list[str] | None = None) -> dict:
    """One quarter: parse (local ZIP or the SIS file), write the publication-safe GES file and the receipt."""
    base.quarter_key(q)
    t0 = time.time()
    ref = load_ges_reference()
    rec: dict = {"script_version": SCRIPT_VERSION, "subconjunto": "ges", "periodo": q, "dataset": DATASET,
                 "generated_at": datetime.now(timezone.utc).isoformat(), "user_agent": base.UA,
                 "max_file_bytes": base.MAX_FILE_BYTES}
    agg = GesAgg()
    tmpdir = Path(tempfile.mkdtemp(prefix="sis_ges_"))
    path = None
    try:
        if local is not None:
            path = local
            frec = {"url": f"local:{local.name}", "bytes": local.stat().st_size,
                    "sha256": hashlib.sha256(local.read_bytes()).hexdigest()}
        else:
            links = links if links is not None else base.page_links()
            url = base.discover(DATASET, q, links)
            frec = {"url": url, "enlazado_en_pagina": url in links}
            path = tmpdir / f"{q}.zip"
            frec.update(base.download(url, path, base.MAX_BYTES[DATASET]))
        if "error" not in frec:
            base.process_zip(path, base.PREST_N, agg.add, frec)
            frec["numeric_parse_errors"] = dict(agg.err)
    finally:
        if local is None and path is not None and path.exists():
            path.unlink()
        try:
            tmpdir.rmdir()
        except OSError:
            pass
    rec["archivo"] = frec
    schema = agg.schema_check(frec.get("parse", {})) if "error" not in frec else {"ok": False, "razones": [frec["error"]]}
    rec["esquema"] = schema
    qdir = out_root / q
    qdir.mkdir(parents=True, exist_ok=True)
    written = []
    if schema.get("ok"):
        tables = agg.ges_tables(ref)
        doc, rep = ges_privacy.sanitize(tables, ref["raw"])
        out = {"periodo": q, "script_version": SCRIPT_VERSION, "version_publicable": ges_privacy.PUBLIC_VERSION,
               "sha256_zip": frec.get("sha256"), "filas_zip": (frec.get("parse") or {}).get("rows_ok"),
               "definicion": tables["definicion"], "supresion": rep, "fuente_nombres": tables["fuente_nombres"], **doc}
        fp = qdir / f"ges_gpp_publicable_{q}.json"
        base.write_json(fp, out)
        written.append(fp.name)
        rec["estado"] = "ok"
    else:
        rec["estado"] = "omitido"
        rec["razon_omision"] = schema.get("razones")
    rec["archivos_escritos"] = written
    rec["totales_por_tipo_atencion"] = {a: {"facturado": round(v[0]), "bonificado": round(v[1]), "frecuencia": round(v[2]),
                                            "filas": v[3]} for a, v in sorted(agg.tot_atn.items())}
    rec["segundos"] = round(time.time() - t0, 1)
    base.write_json(qdir / f"receipts_{q}.json", rec)
    return rec


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--quarter", required=True)
    ap.add_argument("--zip", type=Path, default=None, help="ZIP local (sin descarga)")
    ap.add_argument("--output-root", type=Path, default=OUT_ROOT)
    a = ap.parse_args()
    rec = run_quarter(a.quarter, a.output_root, a.zip)
    print(json.dumps({"periodo": rec["periodo"], "estado": rec["estado"], "archivos": rec["archivos_escritos"]}))


if __name__ == "__main__":
    main()
