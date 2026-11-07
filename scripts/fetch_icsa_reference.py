"""Descarga los documentos oficiales del ICSA (Superintendencia de Salud) a data/reference/icsa/ con recibos.

Usa la lógica de red del agregador SIS (robots.txt con el User-Agent del bot, falla cerrada; tope por archivo). Los
PDF se convierten a texto con ``pdftotext -layout`` (poppler) si está disponible. Las URLs vienen de las páginas
"Indicador de Costos de la Salud (ICSA) 2023/2024/2025" de la biblioteca digital SIS (revisadas el 6-nov-2026) y de la
Resolución Exenta SIS N°196 (DO 20-feb-2024); no se infiere ninguna.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aggregate_sis_open_data as base  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "data" / "reference" / "icsa"
LIMIT = 50 * 1024 * 1024
U = "https://www.superdesalud.gob.cl/app/uploads/"
FILES = [
    ("2025", "1-resultados_icsa_2025.pdf", U + "2026/03/1-resultados_icsa_2025.pdf"),
    ("2025", "2-documento_metodologico_icsa_2025.pdf", U + "2026/03/2-documento_metodologico_icsa_2025.pdf"),
    ("2025", "3-memoria_de_calculo_icsa_2025.pdf", U + "2026/03/3-memoria_de_calculo_icsa_2025.pdf"),
    ("2025", "4-mle_canasta_ponderadores_homologaciones_icsa_2025.xlsx",
     U + "2026/03/4-mle_canasta_ponderadores_homologaciones_icsa_2025.xlsx"),
    ("2025", "5-insumos_ipc__cartera_icsa_2025.xlsx", U + "2026/03/5-insumos_ipc__cartera_icsa_2025.xlsx"),
    ("2025", "6-bbdd_enero2024_diciembre2025_icpre.csv", U + "2026/03/6-bbdd_enero2024_diciembre2025_icpre.csv"),
    ("2025", "7-diccionario_variables_icpre.pdf", U + "2026/03/7-diccionario_variables_icpre.pdf"),
    ("2025", "8-bbdd_enero2024_diciembre2025_igsi.csv", U + "2026/03/8-bbdd_enero2024_diciembre2025_igsi.csv"),
    ("2025", "9-diccionario_variables_igsi.pdf", U + "2026/03/9-diccionario_variables_igsi.pdf"),
    ("2024", "1-resultados_icsa_2024.pdf", U + "2025/03/1-resultados_icsa_2024.pdf"),
    ("2024", "2-documento_metodologico_icsa_2024.pdf", U + "2025/03/2-documento_metodologico_icsa_2024.pdf"),
    ("2024", "3-memoria_de_calculo_icsa_2024.pdf", U + "2025/03/3-memoria_de_calculo_icsa_2024.pdf"),
    ("2024", "4-mle_canasta_ponderadores_homologaciones_icsa_2024.xlsx",
     U + "2025/03/4-mle_canasta_ponderadores_homologaciones_icsa_2024.xlsx"),
    ("2024", "5-bbdd_enero2023_diciembre2024_icpre.csv", U + "2025/03/5-bbdd_enero2023_diciembre2024_icpre.csv"),
    ("2024", "6-diccionario_variables_icpre.pdf", U + "2025/03/6-diccionario_variables_icpre.pdf"),
    ("2024", "7-bbdd_enero2023_diciembre2024_igsi.csv", U + "2025/03/7-bbdd_enero2023_diciembre2024_igsi.csv"),
    ("2023", "resultados_icsa_2023.pdf", U + "2024/02/articles-26520_recurso_1.pdf"),
    ("2023", "recurso_2_icsa_2023.pdf", U + "2024/02/articles-26520_recurso_2.pdf"),
    ("2023", "recurso_3_icsa_2023.xlsx", U + "2024/02/articles-26520_recurso_3.xlsx"),
    ("2023", "recurso_4_icsa_2023.pdf", U + "2024/02/articles-26520_recurso_4.pdf"),
    ("normativa", "res_ex_196_2024_icsa_2023_DO.pdf",
     "https://www.diariooficial.interior.gob.cl/publicaciones/2024/02/20/43781/01/2454660.pdf"),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    receipts = []
    have_pdftotext = shutil.which("pdftotext") is not None
    for year, name, url in FILES:
        dest = OUT / year / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        rec = {"anio_icsa": year, "archivo": f"{year}/{name}", **base.download(url, dest, LIMIT)}
        if "error" in rec:
            if dest.exists():
                dest.unlink()
        elif name.endswith(".pdf") and have_pdftotext:
            txt = dest.with_suffix(".txt")
            p = subprocess.run(["pdftotext", "-layout", str(dest), str(txt)], capture_output=True, text=True)
            rec["texto"] = f"{year}/{txt.name}" if p.returncode == 0 else f"error_pdftotext:{p.returncode}"
        receipts.append(rec)
        print(json.dumps({k: rec.get(k) for k in ("archivo", "status", "bytes", "robots", "error")}), flush=True)
    base.write_json(OUT / "receipts.json", {
        "fuente": "Superintendencia de Salud, Indicador de Costos de la Salud (ICSA), biblioteca digital; Diario Oficial",
        "retrieved_at": datetime.now(timezone.utc).isoformat(), "user_agent": base.UA,
        "requested_by": "Dirección, 6-nov-2026 (metodología ICSA, Ley 21.350)", "archivos": receipts})
    if any("error" in r for r in receipts):
        print("algunos archivos no se descargaron; ver receipts.json")


if __name__ == "__main__":
    main()
