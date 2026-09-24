"""One scheduled attempt; fixed, allowlisted repairs only, never arbitrary code.

The outer workflow persists the reservation before calling this script and keeps
the ledger on autopilot-state. A failure cannot reset the daily count.
"""
import argparse
import json
import os
import subprocess
from pathlib import Path
from radar_salud.autopilot import reserve, approve, save_ledger, should_attempt

def run(command):
    return subprocess.run(command, check=False).returncode == 0

def main():
    p=argparse.ArgumentParser();p.add_argument("action",choices=["reserve","execute"]);p.add_argument("--ledger",required=True);p.add_argument("--sha",required=True)
    args=p.parse_args();path=Path(args.ledger)
    ledger=json.loads(path.read_text()) if path.exists() else {"iterations":[]}
    if args.action=="reserve":
        if not should_attempt(ledger,args.sha):
            if os.environ.get("GITHUB_OUTPUT"):
                with open(os.environ["GITHUB_OUTPUT"],"a") as out:out.write("reserved=false\n")
            print("Already reviewed this candidate; waiting for a new SHA")
            return
        entry=reserve(ledger,args.sha,"deterministic-builder")
        save_ledger(path,ledger)
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"],"a") as out:out.write("reserved=true\n")
        print(entry["id"]);return
    entry=ledger["iterations"][-1]
    if entry["state"]!="reserved" or entry["candidate_sha"]!=args.sha:
        raise RuntimeError("Missing matching reservation")
    try:
        entry["state"]="building"
        # Only derived operational reports are repaired automatically. Content,
        # prompts, thresholds, pricing, credentials and code are not changed.
        build=run(["python","scripts/product_report.py"])
        tests=run(["python","-m","pytest","-q"]) and run(["npm","test"])
        browser=build and tests and run(["npm","run","test:browser"])
        reviewed=run(["python","scripts/review_candidate.py","--sha",args.sha])
        report_path=Path("artifacts/review.json")
        reports=[json.loads(report_path.read_text())] if report_path.exists() else []
        checks={"tests":tests,"desktop":bool(browser),"mobile":bool(browser),"reviewer":reviewed,
            "editorial":bool(reports and reports[0]["checks"]["editorial"]),
            "data":bool(reports and reports[0]["checks"]["data"])}
        passed=approve(entry,reports,checks)
        entry["changes"]=["Rebuilt derived product report and Excel diagnostic CSV"]
        entry["promotion"]="blocked_until_remote_preview" if passed else "blocked"
        if not passed:entry["next_action"]="next scheduled attempt may rebuild reports; code/editorial findings require review"
    except Exception as exc:
        entry.update(state="failed",error=type(exc).__name__)
        raise
    finally:
        save_ledger(path,ledger)
        target=Path("data/autopilot/ledger.json");save_ledger(target,ledger)
        run(["python","scripts/product_report.py"])
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"],"a") as out:out.write("qa_passed="+str(entry["state"]=="qa_passed").lower()+"\n")

if __name__=="__main__":main()
