"""Qualify real captures in an isolated stock; do not activate any production source."""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from review_market_source_coverage import digest_market, review


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--capture-dir',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    root=args.output/'stock'
    if root.resolve().is_relative_to(Path('data').resolve()):
        raise ValueError('Qualification output must be isolated from repository stock')
    if not root.exists():
        for directory in ('entities','market'):
            shutil.copytree(Path('data')/directory,root/'data'/directory)
    command=[sys.executable,'-m','radar_salud.market_sources','--capture-dir',str(args.capture_dir),'--output-root',str(root)]
    subprocess.run(command,check=True)
    initial=digest_market(root)
    subprocess.run(command,check=True)
    replay=digest_market(root)
    result=review(args.capture_dir,root)
    result['replay_idempotent']=initial==replay
    result['replay_differences']=[key for key in set(initial)|set(replay) if initial.get(key)!=replay.get(key)]
    if not result['replay_idempotent']:result['status']='FAIL'
    result['baseline_qa']='Separate mandatory global workflow; qualification does not override its gates'
    result['recurrence_validated']=False
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'independent_review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))
    if result['status']!='PASS':raise SystemExit(1)


if __name__=='__main__':main()
