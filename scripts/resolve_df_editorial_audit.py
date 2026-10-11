"""Read recorded decisions; retain evidence and align DF review outcomes offline."""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from radar_salud.df_article import article_url
from radar_salud.df_media_gate import assessment_exclusion, exclusion
from radar_salud.df_recovery import _remember
from radar_salud.history import load_history, save_history
from radar_salud.models import RawItem
from radar_salud.pending_queue import PendingQueue, atomic_json
from radar_salud.scouts import SeenStore


def main():
    root=Path(__file__).resolve().parents[1]
    branch=subprocess.check_output(['git','branch','--show-current'],cwd=root,text=True).strip()
    if not branch.startswith('codex/df-'):raise ValueError('Only isolated DF branch')
    now=datetime.now(timezone.utc)
    queue=PendingQueue(root/'data/state/pending_queue.json')
    history=load_history(root/'data/history/superintendencia_signals.json')
    decisions=[];terminal=[]
    for key,item in queue.items.items():
        if item.get('source')!='diario_financiero' or item['status']=='superseded':continue
        raw=RawItem(**item['raw']);metadata=raw.metadata
        assessment=metadata.get('editorial_assessment') or {}
        reason=assessment_exclusion(assessment) if item['status']=='published' else None
        if item['status'] in ('pending','retry') and exclusion(raw)=='df_not_article':reason='df_not_article'
        if reason:
            _remember(item,now,'recorded_primary_evidence_editorial_review')
            item.update(status='rejected',reason=reason,retry_at=None,updated_at=now.isoformat())
            metadata['rejection_reason']=reason
            terminal.append(key)
            decisions.append({'url':raw.url,'reason':reason,'score':assessment.get('score'),
                              'basis':'Recorded original/assessment; no new fetch or model call'})
        for row in history:
            if article_url(row.get('source_url',''))!=article_url(raw.url):continue
            if reason:
                before={k:v for k,v in row.items() if k!='df_media_gate_observations'}
                row.setdefault('df_media_gate_observations',[]).append({'at':now.isoformat(),'before':before})
                row.update(editorial_decision='reject',feed_visibility=False,df_media_gate_reason=reason)
            if row.get('df_body_reaudit_observations') and item['status'] in ('retry','rejected'):
                row.update(df_body_reaudit_status=item['status']+'_after_primary_body_reassessment',
                           df_body_reaudit_reason=item.get('reason'),df_body_reaudit_latest_assessment=assessment or None,
                           editorial_decision='reject',feed_visibility=False)
    queue.save();save_history(root/'data/history/superintendencia_signals.json',history)
    SeenStore(root/'data/state/diario_financiero_seen.json').add_many(terminal)
    health_path=root/'data/source_health.json';health=json.loads(health_path.read_text());df=health['sources']['diario_financiero']
    counts=queue.counts('diario_financiero')
    deferred=sum(i.get('source')=='diario_financiero' and i['status']=='deferred' for i in queue.items.values())
    df.update(rejected=counts['rejected'],live_pending=counts['live_pending'],backfill_pending=counts['backfill_pending'],
              pending=counts['live_pending']+counts['backfill_pending'],editorial_reviewed_at=now.isoformat(),
              deferred=deferred,deferred_multimedia=sum(i.get('source')=='diario_financiero' and i['status']=='deferred'
                  and i.get('df_resolution',{}).get('state')=='DEFERRED_MULTIMEDIA' for i in queue.items.values()),
              unverifiable_date_dispositions=sum(i.get('source')=='diario_financiero' and i['status']=='deferred'
                  and i.get('df_resolution',{}).get('state')=='RESOLVED_NO_VERIFIABLE_DATE' for i in queue.items.values()),
              accepted_queue_publications=counts['published'],review_withdrawn=len(decisions),
              last_signal_at=max([r['event_date'] for r in history if r.get('source_name')=='Diario Financiero'
                                  and r.get('event_date') and r.get('editorial_decision')!='reject'],default=None))
    atomic_json(health_path,health)
    report={'at':now.isoformat(),'branch':branch,'code_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
            'model_calls':0,'original_fetches':0,'decisions':decisions,'queue_counts':counts,
            'note':'Primary-body rejections/retries replace obsolete pending review labels. Numeric score cannot override explicit nonmaterial verdict; thresholds unchanged.'}
    audit_path=root/'data/audits/df_editorial_review_2026_10_11.json'
    previous=json.loads(audit_path.read_text()) if audit_path.exists() else {}
    retained={(d['url'],d['reason']):d for d in previous.get('decisions',[])}
    retained.update({(d['url'],d['reason']):d for d in decisions})
    report.update(decisions=list(retained.values()),decisions_this_run=decisions,
                  first_review_at=previous.get('first_review_at') or previous.get('at') or now.isoformat())
    atomic_json(audit_path,report)
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
