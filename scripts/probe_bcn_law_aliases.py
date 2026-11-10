"""Verify the curated law alias map against BCN LeyChile (Dirección 10-nov-2026).

For each law number: robots.txt, then one request to the verified endpoint
(https://www.leychile.cl/Consulta/obtxml?opt=7&idLey=<n>, verified 4-nov by
bcn_leychile_watch). Only metadata is recorded (type/number, title, publication
date, idNorma, common names); the norm text is never stored.
"""
import argparse, json, sys, time, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

UA = "RadarSaludBot/0.3 (+public-source-monitor)"
BASE = "https://www.leychile.cl/Consulta/obtxml"
LAWS = ["20850", "19966", "21674", "16744", "21643", "20584", "21331"]


def get(url):
    with urlopen(Request(url, headers={"User-Agent": UA}), timeout=40) as r:
        return r.status, r.read()


def local(tag):
    return tag.rsplit("}", 1)[-1]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--output", required=True); a = ap.parse_args()
    rp = RobotFileParser()
    try:
        _, body = get("https://www.leychile.cl/robots.txt"); rp.parse(body.decode("utf-8", "replace").splitlines()); robots = "parsed"
    except Exception as e:
        rp.parse([]); robots = f"unavailable:{type(e).__name__}"
    out = {"probe": "bcn_law_aliases", "user_agent": UA, "robots": robots,
           "at": datetime.now(timezone.utc).isoformat(), "laws": {}}
    for n in LAWS:
        url = f"{BASE}?opt=7&idLey={n}"
        rec = {"url": url, "robots_allowed": rp.can_fetch(UA, url)}
        if rec["robots_allowed"]:
            time.sleep(2)
            try:
                status, body = get(url); rec["http_status"] = status
                root = ET.fromstring(body)
                rec["id_norma"] = root.attrib.get("normaId")
                names, tipos = [], []
                for el in root.iter():
                    t = local(el.tag)
                    if t == "TituloNorma": rec["titulo"] = (el.text or "").strip()
                    elif t in ("NombreUsoComun", "NombresUsoComun"):
                        if (el.text or "").strip(): names.append(el.text.strip())
                    elif t == "TipoNumero":
                        tipos.append(" ".join((c.text or "").strip() for c in el))
                    elif t == "Identificador":
                        rec["fecha_publicacion"] = el.attrib.get("fechaPublicacion")
                rec["nombres_uso_comun"] = names; rec["tipo_numero"] = tipos
            except Exception as e:
                rec["error"] = f"{type(e).__name__}: {str(e)[:120]}"
        out["laws"][n] = rec
        print(n, json.dumps({k: rec.get(k) for k in ("http_status", "titulo", "nombres_uso_comun", "tipo_numero", "error")}, ensure_ascii=False))
    p = Path(a.output); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
