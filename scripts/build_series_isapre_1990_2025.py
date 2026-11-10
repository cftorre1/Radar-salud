"""Series largas del sistema Isapre 1990-2025 para Datos (determinista, falla cerrada).

Lee sólo el libro oficial "2-cartera-de-beneficiarios-anos-1990-2025.xlsx" de la SIS (descargado con recibo por
``fetch_sis_series_1990_2025.py``) y escribe ``web/data/series_isapre.json``. Toda cifra que muestra la página viene
pre-formateada de aquí; la página no calcula. Antes de escribir, concilia:

- Abiertas + Cerradas = Total Sistema (cotizantes, cargas, beneficiarios; cada año);
- Cotizantes + Cargas = Beneficiarios (cada tipo y año);
- suma por Isapre = subtotales Abiertas / Cerradas y total (cuadros 2.11.1 y 2.11.3);
- suma por región = total (cuadro 2.6.3).

Si una conciliación falla por más de ``TOL`` personas, no se escribe nada (``SystemExit``).
La columna de año se toma por posición desde 1990; el encabezado debe coincidir con el año, salvo la errata "2204"
(= 2004) del cuadro 2.11.1, que se documenta en ``notas``.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "data" / "reference" / "sis_series_1990_2025"
BOOK = "2-cartera-de-beneficiarios-anos-1990-2025.xlsx"
OUT = ROOT / "web" / "data" / "series_isapre.json"
PAGE = "https://www.superdesalud.gob.cl/biblioteca-digital/series-estadisticas-del-sistema-isapre-1990-2025/"
Y0, Y1 = 1990, 2025
YEARS = list(range(Y0, Y1 + 1))
TOL = 1
# Diferencias propias del libro SIS (descarga del 10-nov-2026, sha256 4db87d29…): se aceptan sólo con este valor exacto
# y se informan en notas; cualquier otra diferencia, o un cambio de ésta, hace fallar la construcción.
KNOWN_SOURCE_GAPS = {("2.6.3.total_vs_2.1", 2002): 2251}
HEADER_ERRATA = {2004: {"2204"}}
# Nombre corto que usan las fichas de Alicanto (F1, F2, F12, F13) para las Isapres vigentes, por (código SIS, tipo).
SHORT_ISAPRE = {("67", "abierta"): "Colmena", ("78", "abierta"): "Cruz Blanca", ("80", "abierta"): "Vida Tres",
                ("81", "abierta"): "Nueva Masvida", ("99", "abierta"): "Banmédica", ("107", "abierta"): "Consalud",
                ("108", "abierta"): "Esencial", ("63", "cerrada"): "Isalud", ("76", "cerrada"): "Fundación",
                ("94", "cerrada"): "Cruz del Norte"}
# Nombre corto de región como en F12/F13, por código de región del cuadro 2.6.3.
SHORT_REGION = {"XV": "Arica y Parinacota", "I": "Tarapacá", "II": "Antofagasta", "III": "Atacama", "IV": "Coquimbo",
                "V": "Valparaíso", "R.M.": "Metropolitana", "VI": "O'Higgins", "VII": "Maule", "XVI": "Ñuble",
                "VIII": "Biobío", "IX": "La Araucanía", "XIV": "Los Ríos", "X": "Los Lagos", "XI": "Aysén",
                "XII": "Magallanes"}
MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


class Fail(SystemExit):
    pass


def norm(v) -> str:
    return " ".join(str(v if v is not None else "").split())


def year_of(v) -> int | None:
    m = re.match(r"^(\d{4})", norm(v))
    return int(m.group(1)) if m else None


def num(v) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def rows_of(ws) -> list[list]:
    return [list(r) for r in ws.iter_rows(values_only=True)]


def year_columns(header: list) -> dict[int, int]:
    """Map year -> column, by position from the first header cell equal to 1990; headers are verified."""
    start = next((i for i, v in enumerate(header) if year_of(v) == Y0), None)
    if start is None:
        raise Fail("encabezado_sin_1990")
    cols = {}
    for k, y in enumerate(YEARS):
        c = start + k
        h = norm(header[c]) if c < len(header) else ""
        if year_of(h) != y and h not in HEADER_ERRATA.get(y, set()):
            raise Fail(f"encabezado_inesperado:{y}:{h!r}")
        cols[y] = c
    return cols


def find_table(rows: list[list], cuadro: str) -> int:
    for i, r in enumerate(rows):
        if norm(r[0] if r else "").upper() == f"CUADRO {cuadro}":
            return i
    raise Fail(f"cuadro_no_encontrado:{cuadro}")


def header_after(rows, i) -> tuple[int, dict[int, int]]:
    for j in range(i + 1, min(i + 8, len(rows))):
        if any(year_of(v) == Y0 for v in rows[j]):
            return j, year_columns(rows[j])
    raise Fail(f"sin_encabezado_de_anos:fila{i + 1}")


def series(row, cols) -> list[float | None]:
    return [num(row[cols[y]]) if cols[y] < len(row) else None for y in YEARS]


def tipo_table(rows, cuadro) -> dict[str, list]:
    """Abiertas / Cerradas / Total Sistema rows of a cuadro."""
    i = find_table(rows, cuadro)
    h, cols = header_after(rows, i)
    out = {}
    for r in rows[h + 1:h + 6]:
        label = norm(r[0]).lower()
        key = {"abiertas": "abiertas", "cerradas": "cerradas", "total sistema": "total"}.get(label)
        if key:
            out[key] = series(r, cols)
    if set(out) != {"abiertas", "cerradas", "total"}:
        raise Fail(f"tipos_incompletos:{cuadro}")
    return out


def labelled_block(rows, cuadro, stop_labels) -> tuple[list[dict], dict[str, list]]:
    """Rows after the header until a total row; returns body rows and the named total rows."""
    i = find_table(rows, cuadro)
    h, cols = header_after(rows, i)
    body, totals = [], {}
    for r in rows[h + 1:]:
        first = norm(r[0])
        if not first and not norm(r[1] if len(r) > 1 else ""):
            if totals:
                break
            continue
        low = first.lower()
        if low in stop_labels:
            totals[stop_labels[low]] = series(r, cols)
            if stop_labels[low] == "total":
                break
            continue
        body.append({"code": first, "name": norm(r[1]) if len(r) > 1 else "", "values": series(r, cols)})
    return body, totals


def check(label: str, a: list, b: list, problems: list[str]) -> int:
    worst = 0
    for y, x, z in zip(YEARS, a, b):
        if x is None and z is None:
            continue
        d = abs((x or 0) - (z or 0))
        if not (d > TOL and KNOWN_SOURCE_GAPS.get((label, y)) == round(d)):
            worst = max(worst, d)
        if d > TOL and KNOWN_SOURCE_GAPS.get((label, y)) == round(d):
            continue
        if d > TOL:
            problems.append(f"{label}:{y}:{x}!={z}")
    return round(worst)


def add(*seqs) -> list[float | None]:
    out = []
    for vals in zip(*seqs):
        known = [v for v in vals if v is not None]
        out.append(sum(known) if known else None)
    return out


def fmt_int(v: float) -> str:
    return f"{round(v):,}".replace(",", ".")


def fmt_signed(v: float) -> str:
    return ("+" if v > 0 else "−" if v < 0 else "") + fmt_int(abs(v))


def fmt_pct(v: float, nd: int = 1) -> str:
    s = f"{abs(v):.{nd}f}".replace(".", ",")
    return ("+" if v > 0 else "−" if v < 0 else "") + s + "%"


def ints(seq) -> list[int | None]:
    return [None if v is None else round(v) for v in seq]


def build(book_path: Path, receipts: dict) -> dict:
    wb = openpyxl.load_workbook(book_path, read_only=True, data_only=True)
    problems: list[str] = []
    anual = rows_of(wb["Cartera Anual de Isapre"])
    cot, car, ben = tipo_table(anual, "2.1.1"), tipo_table(anual, "2.1.2"), tipo_table(anual, "2.1.4")
    worst = {}
    for name, t in (("cotizantes", cot), ("cargas", car), ("beneficiarios", ben)):
        worst[f"{name}_abiertas_mas_cerradas"] = check(f"{name}.tipos", add(t["abiertas"], t["cerradas"]), t["total"], problems)
    for k in ("abiertas", "cerradas", "total"):
        worst[f"cotizantes_mas_cargas_{k}"] = check(f"identidad.{k}", add(cot[k], car[k]), ben[k], problems)

    stops = {"subtotal isapres abiertas": "abiertas", "subtotal isapres cerradas": "cerradas", "total sistema": "total"}
    isapres = {}
    for kind, sheet, cuadro in (("beneficiarios", "Beneficiarios por Isapre", "2.11.3"),
                                ("cotizantes", "Cotizantes por Isapre", "2.11.1")):
        body, totals = labelled_block(rows_of(wb[sheet]), cuadro, stops)
        if set(totals) != {"abiertas", "cerradas", "total"}:
            raise Fail(f"subtotales_incompletos:{cuadro}")
        n_open = next(i for i, r in enumerate(rows_of(wb[sheet])) if norm(r[0]).lower() == "subtotal isapres abiertas")
        # Rows before the "Subtotal Isapres Abiertas" line are open Isapres; the rest, closed (sheet order).
        all_rows = rows_of(wb[sheet])
        open_codes_names = set()
        for r in all_rows[:n_open]:
            if re.fullmatch(r"\d+", norm(r[0])):
                open_codes_names.add((norm(r[0]), norm(r[1])))
        for b in body:
            b["tipo"] = "abierta" if (b["code"], b["name"]) in open_codes_names else "cerrada"
        worst[f"{kind}_isapres_abiertas"] = check(f"{cuadro}.abiertas", add(*[b["values"] for b in body if b["tipo"] == "abierta"]), totals["abiertas"], problems)
        worst[f"{kind}_isapres_cerradas"] = check(f"{cuadro}.cerradas", add(*[b["values"] for b in body if b["tipo"] == "cerrada"]), totals["cerradas"], problems)
        ref = ben if kind == "beneficiarios" else cot
        worst[f"{kind}_isapres_total_vs_2_1"] = check(f"{cuadro}.total_vs_2.1", totals["total"], ref["total"], problems)
        isapres[kind] = body

    region_body, region_tot = labelled_block(rows_of(wb["Cartera por Región"]), "2.6.3", {"total": "total"})
    worst["beneficiarios_regiones"] = check("2.6.3.regiones", add(*[r["values"] for r in region_body]), region_tot["total"], problems)
    worst["beneficiarios_regiones_vs_2_1"] = check("2.6.3.total_vs_2.1", region_tot["total"], ben["total"], problems)

    susc_rows = rows_of(wb["Suscripción y Desahucios"])
    i = find_table(susc_rows, "2.10.1")
    hdr = susc_rows[i + 3]
    first = next(c for c, v in enumerate(hdr) if year_of(v) == 1991)
    susc = {}
    for r in susc_rows[i + 4:i + 8]:
        key = {"suscripciones": "suscripciones", "desahucios": "desahucios", "incremento neto": "neto"}.get(norm(r[0]).lower())
        if key:
            susc[key] = [None] + [num(r[first + k]) for k in range(Y1 - 1991 + 1)]
    if set(susc) != {"suscripciones", "desahucios", "neto"}:
        raise Fail("suscripciones_incompletas")
    worst["suscripciones_menos_desahucios"] = check("2.10.1.neto", [None if a is None else a - b for a, b in zip(susc["suscripciones"], susc["desahucios"])], susc["neto"], problems)

    vigentes = {(b["code"], b["tipo"]) for b in isapres["beneficiarios"] if (b["values"][-1] or 0) > 0}
    if vigentes != set(SHORT_ISAPRE):
        problems.append(f"isapres_vigentes_distintas:{sorted(vigentes ^ set(SHORT_ISAPRE))}")
    if problems:
        raise Fail("conciliacion_fallida: " + "; ".join(problems[:12]))

    # Market history: Isapres with beneficiaries in December of each year (2.11.3), by type. Deterministic count.
    n_abiertas = [sum(1 for b in isapres["beneficiarios"] if b["tipo"] == "abierta" and (b["values"][k] or 0) > 0) for k in range(len(YEARS))]
    n_cerradas = [sum(1 for b in isapres["beneficiarios"] if b["tipo"] == "cerrada" and (b["values"][k] or 0) > 0) for k in range(len(YEARS))]

    tot = ben["total"]
    k_peak = max(range(len(YEARS)), key=lambda k: tot[k] or 0)
    k_last = len(YEARS) - 1
    cot_tot = cot["total"]
    kc_peak = max(range(len(YEARS)), key=lambda k: cot_tot[k] or 0)
    last5 = tot[k_last] - tot[k_last - 5]
    highlights = [
        {"id": "beneficiarios", "label": f"Beneficiarios a dic {Y1}", "value": fmt_int(tot[k_last]),
         "lines": [f"{fmt_signed(tot[k_last] - tot[k_last - 1])} vs. dic {Y1 - 1} ({fmt_pct((tot[k_last] / tot[k_last - 1] - 1) * 100)})",
                   f"máximo: {fmt_int(tot[k_peak])} en {YEARS[k_peak]}"]},
        {"id": "cotizantes", "label": f"Cotizantes a dic {Y1}", "value": fmt_int(cot_tot[k_last]),
         "lines": [f"{fmt_signed(cot_tot[k_last] - cot_tot[k_last - 1])} vs. dic {Y1 - 1}",
                   f"máximo: {fmt_int(cot_tot[kc_peak])} en {YEARS[kc_peak]}"]},
        {"id": "desde_maximo", "label": f"Cambio desde el máximo ({YEARS[k_peak]})",
         "value": fmt_pct((tot[k_last] / tot[k_peak] - 1) * 100),
         "lines": [f"{fmt_signed(tot[k_last] - tot[k_peak])} beneficiarios", f"últimos 5 años: {fmt_signed(last5)}"]},
        {"id": "isapres", "label": f"Isapres con cartera en {Y1}", "value": str(n_abiertas[k_last] + n_cerradas[k_last]),
         "lines": [f"{n_abiertas[k_last]} abiertas · {n_cerradas[k_last]} cerradas",
                   f"{Y0}: {n_abiertas[0] + n_cerradas[0]} ({n_abiertas[0]} abiertas)"]},
    ]

    def isapre_rows(kind):
        out = []
        for b in isapres[kind]:
            vals = ints(b["values"])
            years_active = [y for y, v in zip(YEARS, vals) if v]
            if not years_active:
                continue
            out.append({"code": b["code"], "name": b["name"], "short": SHORT_ISAPRE.get((b["code"], b["tipo"])),
                        "tipo": b["tipo"], "desde": years_active[0],
                        "hasta": years_active[-1], "values": vals})
        return out

    rec = {r["archivo"]: r for r in receipts.get("archivos", [])}
    book_rec = rec.get(BOOK, {})
    sha_local = hashlib.sha256(book_path.read_bytes()).hexdigest()
    if book_rec.get("sha256") and book_rec["sha256"] != sha_local:
        raise Fail("sha256_distinto_del_recibo")
    return {
        "schema_version": "series_isapre_v1",
        "title": "Sistema Isapre 1990–2025",
        "years": YEARS,
        "unit": "personas vigentes en diciembre de cada año",
        "highlights": highlights,
        "sistema": {
            "beneficiarios": {k: ints(v) for k, v in ben.items()},
            "cotizantes": {k: ints(v) for k, v in cot.items()},
            "cargas": {k: ints(v) for k, v in car.items()},
        },
        "mercado": {"isapres_abiertas": n_abiertas, "isapres_cerradas": n_cerradas,
                    "isapres_total": [a + c for a, c in zip(n_abiertas, n_cerradas)],
                    "definicion": "Isapres con al menos un beneficiario vigente en diciembre (cuadro 2.11.3)."},
        "contratos": {"desde": 1991, "suscripciones": ints(susc["suscripciones"]), "desahucios": ints(susc["desahucios"]),
                      "neto": ints(susc["neto"])},
        "regiones": [{"code": r["code"], "name": r["name"], "short": SHORT_REGION.get(r["code"], r["name"]),
                      "values": ints(r["values"])} for r in region_body
                     if any(r["values"])],
        "isapres": {"beneficiarios": isapre_rows("beneficiarios")},
        "verificacion": {"status": "PASS", "tolerancia_personas": TOL, "diferencia_maxima": worst,
                         "diferencias_de_la_fuente": [{"control": k[0], "anio": k[1], "personas": v} for k, v in KNOWN_SOURCE_GAPS.items()]},
        "notas": [
            "Cifras a diciembre de cada año (stock), no promedios anuales; información provisional según la SIS.",
            "Desde 2021 la SIS incorpora «Sin clasificar» cuando falta la región; las regiones creadas después de 1990 (Arica y Parinacota, Los Ríos, Ñuble) parten en su primer año informado.",
            "Las Isapres se muestran con el nombre y código que usa la SIS; los cambios de nombre o fusiones no se encadenan.",
            "Suscripciones 1991: sólo septiembre–diciembre (nota de la SIS).",
            "En 2002 el total del cuadro regional (2.6.3) es 2.251 beneficiarios menor que el del cuadro 2.1.4; se publican ambos tal como los informa la SIS.",
            "El encabezado del cuadro 2.11.1 dice «2204» en la columna de 2004; se lee como 2004 por posición.",
        ],
        "source": {
            "name": "Superintendencia de Salud", "short": "SIS",
            "label": "Series estadísticas del sistema Isapre 1990–2025 · II. Cartera de beneficiarios",
            "page": PAGE, "url": book_rec.get("url"), "sha256": sha_local,
            "last_modified": book_rec.get("last_modified"), "retrieved_at": receipts.get("retrieved_at"),
            "cuadros": ["2.1.1", "2.1.2", "2.1.4", "2.6.3", "2.10.1", "2.11.1", "2.11.3"],
        },
    }


def main(argv: list[str]) -> int:
    book = Path(argv[1]) if len(argv) > 1 else REF / BOOK
    receipts = json.loads((REF / "receipts.json").read_text(encoding="utf-8"))
    data = build(book, receipts)
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(OUT.relative_to(ROOT)), **data["verificacion"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
