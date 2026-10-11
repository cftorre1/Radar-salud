"""Recover a trusted Actions checkpoint without repeating already-paid analyses."""
import argparse
import json
import shutil
from pathlib import Path
from radar_salud.history import load_history, merge_history, save_history
from radar_salud.models import RawItem
from radar_salud.pending_queue import atomic_json
from radar_salud.public_source_pipeline import df_signal_from_assessment
from radar_salud.sources import load_sources, source_index


def main():
    ap=argparse.ArgumentParser();ap.add_argument("artifact",type=Path);args=ap.parse_args()
    root=Path(__file__).resolve().parents[1];artifact=args.artifact
    import subprocess
    branch=subprocess.check_output(["git","branch","--show-current"],text=True).strip()
    if not branch.startswith("codex/df-"):ap.error("Recovery only on isolated DF branch")
    run_id="38111768459"
    path=root/"config/orchestrator_queue.json";tasks=json.loads(path.read_text())
    df=next(t for t in tasks["tasks"] if t["id"]=="source_repair_media_lane_2026_10_11")["df_execution"]
    report_path=artifact/"data/audits/df_reconciliation_2026_10_11.json"
    report=json.loads(report_path.read_text())
    if report.get("code_sha")!="d68d444e04b43e6a08de9be31f2f04983d40f41f":
        raise ValueError("Unexpected original checkpoint SHA")
    shutil.copytree(artifact/"work/df-originals",root/"work/df-originals",dirs_exist_ok=True)
    preserved=root/"data/audits/df_original_capture_2026_10_11.json"
    if not preserved.exists():shutil.copyfile(report_path,preserved)
    current=root/"data/audits/df_reconciliation_2026_10_11.json"
    if current.exists() and not json.loads(current.read_text()).get("originals"):
        shutil.copyfile(report_path,current)
    if df.get("runtime_restored")==run_id:return
    cfg=source_index(load_sources(root/"config/sources.json"))["diario_financiero"]
    state=json.loads((artifact/"data/state/pending_queue.json").read_text())
    history=load_history(root/"data/history/superintendencia_signals.json")
    restored=[]
    for item in state.values():
        if item["source"]!="diario_financiero" or item["status"]!="published":continue
        raw=RawItem(**item["raw"]);metadata=raw.metadata;assessment=metadata["editorial_assessment"]
        ai={"relevance_score":assessment["score"],"reason":assessment["reason"],
            "what_happened":metadata["what_happened"],"why_it_matters":metadata["why_it_matters"]}
        row=df_signal_from_assessment(raw,cfg,ai)
        if not row:raise ValueError("Recovered paid publication fails current gate")
        row.update(detected_at=item["detected_at"],ingestion_mode=item["lane"],
                   recovery_trace={"run_id":run_id,"basis":"Actual paid assessment and article evidence from failed checkpoint artifact; no new model call"})
        restored.append(row)
    if len(restored)!=2:raise ValueError("Expected two actual paid DF publications")
    for relative in ("data/state/pending_queue.json","data/state/diario_financiero_seen.json",
                     "data/state/discovery_run.json","data/state/discovery_watermarks.json","data/source_health.json"):
        shutil.copyfile(artifact/relative,root/relative)
    shutil.copytree(artifact/"work/df-originals",root/"work/df-originals",dirs_exist_ok=True)
    shutil.copyfile(report_path,root/"data/audits/df_reconciliation_2026_10_11.json")
    save_history(root/"data/history/superintendencia_signals.json",merge_history(history,restored))
    # The original Actions log records 31→45 attempted/successful fast calls,
    # and unchanged deep 14. Preserve that observed aggregate, not invented costs.
    usage_path=root/"data/ai_usage/2026-10.json";usage=json.loads(usage_path.read_text())
    usage["fast"]["attempted"]=max(45,usage["fast"]["attempted"])
    usage["fast"]["successful"]=max(45,usage["fast"]["successful"])
    atomic_json(usage_path,usage)
    evidence={"run_id":run_id,"source_artifact_id":11691902368,"artifact_zip_sha256":"9ca3cae1a230aeabd7a7cf8eb922d9201acde5c4b3adc13e4e4ebe4f6b9ae022",
              "restored_urls":[row["source_url"] for row in restored],"ai_usage_basis":"Original job log: fast attempted/successful 45, failed 0; no new calls during restoration",
              "limitation":"Original per-response usage JSONL was not included in artifact; aggregate usage is recovered from job log. Original full HTML is retained.",
              "checkpoint_failure":"git add referred to absent data/telemetry; corrected; original data preserved by artifact upload"}
    atomic_json(root/"data/audits/df_runtime_restoration_2026_10_11.json",evidence)
    df.update(runtime_restored=run_id,runtime_artifact="data/audits/df_reconciliation_2026_10_11.json")
    atomic_json(path,tasks)
    print(json.dumps(evidence))


if __name__=="__main__":main()
