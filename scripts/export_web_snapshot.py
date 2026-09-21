"""Export a public web snapshot from a list of Signal-like dicts.

V0 accepts an input JSON file with either {"signals": [...]} or a raw list.
Later the daily runner will feed this script after all scouts execute.
"""
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--input', required=True)
    ap.add_argument('--output', default='web/data/radar_today.json')
    ap.add_argument('--profile', default='Ejecutivo Isapre')
    ap.add_argument('--date', default=None)
    args=ap.parse_args()
    raw=json.loads(Path(args.input).read_text(encoding='utf-8'))
    signals=raw.get('signals', raw) if isinstance(raw, dict) else raw
    payload={
      'date': args.date or datetime.now().date().isoformat(),
      'profile': args.profile,
      'generated_at': datetime.now(timezone.utc).isoformat(),
      'signals': signals,
    }
    out=Path(args.output); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    print(out)
if __name__=='__main__': main()
