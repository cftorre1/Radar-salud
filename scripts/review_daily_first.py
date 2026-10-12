"""Independent read-only evidence Reviewer; rejects unsupported recovery claims."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re


def review(root):
    findings=[]
    def require(ok, message):
        if not ok:findings.append(message)
    replay=json.loads((root/'replay.json').read_text())
    captures=json.loads((root/'native-captures.json').read_text())
    delta=json.loads((root/'queue-delta.json').read_text())
    new=json.loads((root/'history-new.json').read_text())
    usage=json.loads((root/'usage-delta.json').read_text())
    by_url={r['url']:r for r in captures}
    require(replay['replay']=='PASS','non_idempotent_replay')
    require(replay['window_days']<=30 and replay['priority_hours']==72,'window_outside_mission')
    require(replay['unrelated_queue_and_health_preserved'],'unrelated_state_changed')
    require(usage['after']['deep']==usage['before']['deep'],'unexpected_deep_spend')
    require(len(usage['new_responses'])==replay['ai_calls']<=4,'unexplained_fast_spend')
    for row in captures:
        body=(root/row['body_path']).read_bytes()
        require(hashlib.sha256(body).hexdigest()==row['sha256'],'capture_hash_mismatch')
        require(row.get('url','').startswith('https://www.minsal.cl/'),'nonofficial_native_capture')
    for key,item in delta.items():
        raw=item['raw']; meta=raw['metadata']; captured=by_url.get(raw['url'])
        require(item['source']=='minsal' and captured is not None,'unexpected_queue_delta')
        require(item['lane']=='BACKFILL','stock_rejuvenated_as_live')
        require(item.get('minsal_provenance_repairs') is not None,'missing_previous_undated_evidence')
        if not captured:continue
        html=(root/captured['body_path']).read_text()
        stamps=re.findall(r'<meta\s+property="article:published_time"\s+content="([^"]+)"',html)
        require(meta['publication_date_evidence']['value'] in stamps,'publication_not_in_primary')
        require(meta['publication_date_evidence']['url']==raw['url'],'date_borrowed_from_another_document')
        require(meta['minsal_primary_verified'] and len(meta['page_text'])>=180,'primary_content_missing')
        require(item['status'] in ('published','rejected','pending','retry'),'unexplained_disposition')
        if item['status']=='rejected':require(bool(item['reason']),'rejection_without_reason')
        if item['status']=='published':
            matches=[r for r in new if r['source_url']==raw['url']]
            require(len(matches)==1,'publication_missing_or_duplicated')
            require(matches[0]['event_date']==raw['event_date'] if matches else False,'published_date_changed')
    health=json.loads((root/'health.json').read_text())
    require(health['coverage_complete'] is False,'unsupported_exhaustive_coverage')
    require(health['recovery_outcome']=='OPERATIVE_DEGRADED','unverified_recurring_operation')
    return {'reviewer':'independent_read_only_daily_first_evidence','findings':findings,
            'result':'PASS' if not findings else 'FAIL','queue_records':len(delta),
            'limitations':['No legal/medical certification; no proof of recurring 24h operation or exhaustive30d coverage.']}


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--runtime',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    result=review(args.runtime);args.output.write_text(json.dumps(result,indent=2));print(json.dumps(result))
    raise SystemExit(0 if result['result']=='PASS' else 1)
