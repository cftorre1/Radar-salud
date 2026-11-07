"""Censo de los trimestres de Prestaciones Bonificadas y Licencias Médicas en datos abiertos SIS (Dirección, 6-nov-2026).

Por trimestre: URL, si está enlazado en la página SIS, bytes, SHA-256, Last-Modified, filas, histograma de campos,
encabezado (si existe), codificación y una huella de esquema. La huella es el SHA-256 de (n° de campos modal,
encabezado, clase de cada columna: numérica / alfanumérica / mixta / vacía) sobre las primeras 200.000 filas. Para el
layout conocido (30 campos en Prestaciones, 44 en Licencias) se listan además los vocabularios de columnas categóricas
no sensibles (valores con >= 10 filas). Para un layout desconocido no se escribe ningún valor, sólo clases y largos,
porque no se sabe qué columna es un identificador cifrado.

Usa la lógica de red del agregador (robots.txt, User-Agent, tope 1 GiB) y borra cada ZIP tras contarlo.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aggregate_sis_open_data as base  # noqa: E402

SCRIPT_VERSION = "sis_historico_censo_v1"
DATASETS = {"Prestaciones Bonificadas": base.PREST_N, "Licencias Medicas": base.LIC_N}
PROFILE_ROWS = 200_000
# Columnas categóricas no sensibles cuyo vocabulario se registra (sólo con el layout conocido).
VOCAB_COLS = {
    "Prestaciones Bonificadas": {base.P_PERIODO: "periodo", base.P_TIPO_REG: "tipo_registro", base.P_SEXO: "sexo",
                                 base.P_TIPO_BEN: "tipo_beneficiario", base.P_REGION: "region_prestador",
                                 base.P_PREFERENTE: "prestador_preferente", base.P_PERTENENCIA: "pertenencia_codigo",
                                 base.P_COBERTURA: "cobertura_financiamiento", base.P_FECHA_BONIF: "fecha_bonificacion",
                                 base.P_TIPO_PRESTADOR: "tipo_prestador", base.P_TIPO_ATENCION: "tipo_atencion",
                                 base.P_TIPO_PLAN: "tipo_plan", base.P_MOD_IQ: "modalidad_iq",
                                 base.P_LEY_URG: "ley_urgencia", base.P_ISAPRE: "codigo_aseguradora"},
    "Licencias Medicas": {base.L_ISAPRE: "codigo_isapre", base.L_TIPO_LIC: "tipo_licencia", base.L_SEXO: "sexo",
                          base.L_TIPO_PROF: "tipo_profesional", base.L_RESOL: "tipo_resolucion",
                          base.L_REGION: "region", base.L_PERIODO: "periodo"},
}


def col_class(numeric: int, empty: int, n: int) -> str:
    filled = n - empty
    if n == 0 or filled == 0:
        return "vacia"
    share = numeric / filled
    return "num" if share >= 0.99 else "alfa" if share <= 0.01 else "mixta"


class Census:
    def __init__(self, dataset: str):
        self.dataset = dataset
        self.n_expected = DATASETS[dataset]
        self.lines = self.blank = 0
        self.fields: Counter = Counter()
        self.enc: Counter = Counter()
        self.header: list[str] | None = None
        self.prof_n = 0
        self.numeric: Counter = Counter()
        self.empty: Counter = Counter()
        self.lengths: dict[int, Counter] = {}
        self.vocab: dict[int, Counter] = {}

    def feed(self, stream) -> None:
        first = True
        for raw in stream:
            self.lines += 1
            line = raw.rstrip(b"\r\n")
            if not line.strip():
                self.blank += 1
                continue
            try:
                s = line.decode("utf-8")
                self.enc["utf-8"] += 1
            except UnicodeDecodeError:
                s = line.decode("latin-1")
                self.enc["latin-1"] += 1
            f = s.split("|")
            if len(f) > 1 and f[-1].strip() == "":
                f.pop()  # delimitador final
            self.fields[len(f)] += 1
            if first:
                first = False
                if not f[0].strip().isdigit():
                    # Un encabezado son nombres de columnas, no datos: se guarda recortado.
                    self.header = [x.strip()[:60] for x in f]
                    continue
            if self.prof_n < PROFILE_ROWS:
                self._profile(f)

    def _profile(self, f: list[str]) -> None:
        self.prof_n += 1
        known = len(f) == self.n_expected
        vocab_cols = VOCAB_COLS[self.dataset] if known else {}
        for i, v in enumerate(f):
            v = v.strip()
            if not v:
                self.empty[i] += 1
                continue
            if v.replace(".", "", 1).replace(",", "", 1).replace("-", "", 1).isdigit():
                self.numeric[i] += 1
            self.lengths.setdefault(i, Counter())[min(len(v), 40)] += 1
            if i in vocab_cols:
                c = self.vocab.setdefault(i, Counter())
                if v in c or len(c) < 300:
                    c[v] += 1

    def result(self) -> dict:
        mode = self.fields.most_common(1)[0][0] if self.fields else 0
        classes = [col_class(self.numeric[i], self.empty[i], self.prof_n) for i in range(mode)]
        fp_src = json.dumps({"n_campos": mode, "encabezado": self.header, "clases": classes}, sort_keys=True)
        rows = self.lines - self.blank - (1 if self.header else 0)
        known = mode == self.n_expected
        names = VOCAB_COLS[self.dataset]
        out = {"lineas": self.lines, "filas": rows, "lineas_vacias": self.blank,
               "histograma_campos": {str(k): v for k, v in sorted(self.fields.items())},
               "n_campos_modal": mode, "n_campos_esperado_layout_2026": self.n_expected,
               "layout_2026_compatible_por_n_campos": known,
               "encabezado": self.header, "codificacion_lineas": dict(self.enc),
               "filas_perfiladas": self.prof_n, "clases_columnas": classes,
               "huella_esquema": hashlib.sha256(fp_src.encode()).hexdigest()[:16],
               "largo_modal_por_columna": [self.lengths[i].most_common(1)[0][0] if self.lengths.get(i) else None
                                           for i in range(mode)]}
        if known:
            out["vocabularios"] = {names[i]: [[v, c] for v, c in self.vocab.get(i, Counter()).most_common(25)
                                              if c >= base.PROFILE_MIN_COUNT] for i in sorted(names)}
        return out


def census_zip(path: Path, dataset: str) -> dict:
    c = Census(dataset)
    with zipfile.ZipFile(path) as zf:
        members = [{"name": i.filename, "size": i.file_size} for i in zf.infolist()]
        for info in zf.infolist():
            if info.is_dir() or not info.filename.lower().endswith((".txt", ".csv")):
                continue
            with zf.open(info) as s:
                c.feed(s)
    return {"zip_members": members, **c.result()}


def linked_quarters(links: list[str], dataset: str) -> dict[str, str]:
    want = dataset.replace(" ", "_").lower()
    out = {}
    for u in links:
        m = base.FILE_RX.search(unquote(u))
        if m and m.group(1).lower() == want:
            out[f"{m.group(2)}t{m.group(3)}"] = u
    return out


def run(years: list[int], out_path: Path, links: list[str] | None = None, local: dict | None = None) -> dict:
    if links is None and local is None:
        links = base.page_links()
    links = links or []
    entries = []
    for dataset in DATASETS:
        linked = linked_quarters(links, dataset)
        for y in years:
            for t in range(1, 5):
                q = f"{y}t{t}"
                if local is not None:
                    path = local.get((dataset, q))
                    if path is None:
                        continue
                    e = {"dataset": dataset, "periodo": q, "url": f"local:{path.name}", "enlazado_en_pagina": None}
                    e.update(census_zip(path, dataset))
                    entries.append(e)
                    continue
                url = linked.get(q) or base.discover(dataset, q, links)
                e = {"dataset": dataset, "periodo": q, "url": url, "enlazado_en_pagina": q in linked}
                h = base.head(url)
                if "error" in h:
                    e["estado"] = f"no_disponible:{h['error']}"
                    if q in linked:  # enlazado pero falló el HEAD: se registra igual
                        entries.append(e)
                    elif not h["error"].startswith("http_404"):
                        entries.append(e)
                    continue
                tmp = Path(tempfile.mkdtemp(prefix="sis_censo_"))
                zp = tmp / f"{q}.zip"
                t0 = time.time()
                try:
                    rec = base.download(url, zp, base.MAX_BYTES[dataset])
                    e.update({k: rec.get(k) for k in ("status", "robots", "bytes", "sha256", "content_length",
                                                       "last_modified", "download_seconds", "error")
                              if rec.get(k) is not None})
                    if "error" not in rec:
                        e.update(census_zip(zp, dataset))
                        e["estado"] = "ok"
                    else:
                        e["estado"] = f"error:{rec['error']}"
                except (zipfile.BadZipFile, OSError, ValueError) as ex:
                    e["estado"] = f"error:{type(ex).__name__}"
                finally:
                    if zp.exists():
                        zp.unlink()
                    tmp.rmdir()
                e["segundos"] = round(time.time() - t0, 1)
                print(json.dumps({k: e.get(k) for k in ("dataset", "periodo", "estado", "bytes", "filas",
                                                        "n_campos_modal", "huella_esquema", "segundos")},
                                 ensure_ascii=False), flush=True)
                entries.append(e)
    out = {"script_version": SCRIPT_VERSION, "generated_at": datetime.now(timezone.utc).isoformat(),
           "github_run_id": os.environ.get("GITHUB_RUN_ID"), "github_sha": os.environ.get("GITHUB_SHA"),
           "user_agent": base.UA, "anios": years, "entradas": entries}
    base.write_json(out_path, out)
    return out


def merge(parts: list[Path], out_path: Path) -> dict:
    entries, runs = [], set()
    for p in parts:
        d = json.loads(p.read_text(encoding="utf-8"))
        entries += d["entradas"]
        runs.add(d.get("github_run_id"))
    entries.sort(key=lambda e: (e["dataset"], base.quarter_key(e["periodo"])))
    resumen = {}
    for ds in DATASETS:
        es = [e for e in entries if e["dataset"] == ds]
        ok = [e for e in es if e.get("estado") == "ok"]
        resumen[ds] = {"trimestres_ok": len(ok), "trimestres_con_error": len(es) - len(ok),
                       "primero": ok[0]["periodo"] if ok else None, "ultimo": ok[-1]["periodo"] if ok else None,
                       "bytes_total": sum(e.get("bytes") or 0 for e in ok),
                       "filas_total": sum(e.get("filas") or 0 for e in ok),
                       "huellas": dict(Counter(e.get("huella_esquema") for e in ok)),
                       "n_campos": dict(Counter(str(e.get("n_campos_modal")) for e in ok))}
    out = {"script_version": SCRIPT_VERSION, "generated_at": datetime.now(timezone.utc).isoformat(),
           "github_run_ids": sorted(r for r in runs if r), "user_agent": base.UA,
           "definicion": __doc__.split("\n\n", 1)[1].strip(), "resumen": resumen, "entradas": entries}
    base.write_json(out_path, out)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r_ = sub.add_parser("run")
    r_.add_argument("--years", required=True, help="p. ej. 2016,2017")
    r_.add_argument("--out", required=True)
    m = sub.add_parser("merge")
    m.add_argument("--out", required=True)
    m.add_argument("parts", nargs="+")
    a = ap.parse_args()
    if a.cmd == "run":
        run([int(y) for y in a.years.split(",")], Path(a.out))
    else:
        merge([Path(p) for p in a.parts], Path(a.out))


if __name__ == "__main__":
    main()
