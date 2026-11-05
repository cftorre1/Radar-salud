"""Descriptions of Fonasa-arancel codes as written in the SIS 'Arancel Isapre' open-data file (one Isapre's text per
code, the most frequent across Isapres). Reuses the probe's robots-aware fetcher."""
import collections
import io
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe_sis_open_data as probe  # noqa: E402

URL = "https://datos.superdesalud.gob.cl/archivos/Arancel%20Isapre/2026/Arancel_Isapre_2026.zip"
wanted = set(json.loads(Path("scripts/arancel_codes_wanted.json").read_text()))
ok, why = probe.allowed(URL)
if not ok:
    raise SystemExit(why)
status, blob, _ = probe.get(URL)
zf = zipfile.ZipFile(io.BytesIO(blob))
names = collections.defaultdict(collections.Counter)
for info in zf.infolist():
    with zf.open(info) as f:
        for raw in io.TextIOWrapper(f, encoding="latin-1"):
            p = raw.rstrip("\n").split("|")
            if len(p) > 7 and p[5] in wanted:
                names[p[5]][p[7].strip()] += 1
out = {c: names[c].most_common(1)[0][0] for c in sorted(names)}
Path("data/audits/arancel_descripciones.json").write_text(json.dumps(
    {"source": URL, "status": status, "found": len(out), "wanted": len(wanted), "descriptions": out},
    ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(len(out), "of", len(wanted))
