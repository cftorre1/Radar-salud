"""Daily freshness observer. No network, activation, source poll or publication."""
import argparse
import json
from pathlib import Path

from radar_salud.daily_first import SOURCES, freshness


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    health=json.loads((args.root/'data/source_health.json').read_text())['sources']
    result={slug:{**freshness(health.get(slug,{})),
                  'coverage_status':health.get(slug,{}).get('coverage_status','unknown'),
                  'editorial_outcome':health.get(slug,{}).get('editorial_outcome','unknown')}
            for slug in sorted(SOURCES)}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2))
    print(json.dumps(result))


if __name__=='__main__':main()
