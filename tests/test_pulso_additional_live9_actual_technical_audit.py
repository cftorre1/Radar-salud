"""Immutable LIVE9 outcomes, real paid requests and exact original HTTP witnesses."""
from collections import Counter
from datetime import datetime
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

from radar_salud.llm_analysis import news_analysis_input
from radar_salud.pulso_source import extract_article

ROOT=Path(__file__).resolve().parents[1]
AUDIT=ROOT/'data/audits/pulso_additional_live9_actual_technical_evidence_2026_10_11.json'

def digest(value):
    if not isinstance(value,bytes):
        value=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    return hashlib.sha256(value).hexdigest()

def frozen(ref,path):
    return subprocess.check_output(['git','show',ref+':'+path],cwd=ROOT)

def stamp(value):
    return datetime.fromisoformat(value.replace('Z','+00:00'))

def test_live9_four_paid_requests_nine_rejections_preserve113_terminal_and_native_stocks():
    audit=json.loads(AUDIT.read_bytes())
    producer,launch=audit['producer_state_commit'],audit['launch_sha']
    assert producer=='d48a495a5fcefb9adaca26ca30b1f12ddad7e59f'
    before=json.loads(frozen(launch,'data/state/pending_queue.json'))
    queue=json.loads(frozen(producer,'data/state/pending_queue.json'))
    execution=json.loads(frozen(producer,'data/audits/pulso_runtime_2026_10_11.json'))['last_core_execution']
    assert execution['engine_called'] is True and execution['engine_completed'] is True
    assert execution['code_sha']==launch and execution['runtime_fingerprint']['sha256']==audit['actual_runtime_fingerprint_sha256']
    assert execution['processing_attempts_increased']==9
    assert execution['budget_before']['month']['fast']['attempted']==516
    assert execution['budget_after']['month']['fast']=={'attempted':520,'successful':520,'failed':0}
    assert execution['budget_after']['month']['deep']==execution['budget_before']['month']['deep']=={'attempted':14,'successful':14,'failed':0}
    old_events=[json.loads(line) for line in frozen(launch,'data/ai_usage/responses.jsonl').splitlines() if line]
    events=[json.loads(line) for line in frozen(producer,'data/ai_usage/responses.jsonl').splitlines() if line]
    paid=[event for event in events if stamp(execution['started_at'])<=stamp(event['at'])<=stamp(execution['finished_at'])]
    assert events[:len(old_events)]==old_events and events[len(old_events):]==paid==audit['actual_new_model_events']
    assert len(paid)==len({event['response_id'] for event in paid})==4
    assert all(event['kind']=='fast' and event['success'] is True for event in paid)
    guard_path='src/radar_salud/pulso_editorial_proof.py'
    guard_bytes=frozen(launch,guard_path)
    assert digest(guard_bytes)==audit['actual_guard_sha256']==execution['runtime_fingerprint']['files'][guard_path]
    guard={'__name__':'radar_salud._immutable_actual_live9_guard','__file__':str(ROOT/guard_path)}
    exec(compile(guard_bytes,guard['__file__'],'exec'),guard)
    assert len(audit['rows'])==9 and Counter(row['status'] for row in audit['rows'])=={'rejected':9}
    assert Counter(row['reason'] for row in audit['rows'])=={'media_materiality_prefilter':5,'editorial_relevance_below_threshold':4}
    scores=[]
    for row in audit['rows']:
        key=row['queue_fingerprint'];entry=queue[key];old=before[key];raw=entry['raw'];meta=raw['metadata']
        assert entry['status']=='rejected' and entry['attempts']==old['attempts']+1==1
        assert row['reason']==entry['reason'] and row['full_actual_primary_body']==meta['page_text']
        assert raw['source_type']=='press_high_trust' and meta['market_role']=='media'
        model=meta.get('analysis_model_output')
        assert model==row['full_actual_model_output']
        if model:
            request=news_analysis_input(title=raw['title'],text=meta['page_text'],source_name=raw['source_name'],full_text=True)
            assert guard['model_binding_matches'](model,source_name=raw['source_name'],input_text_sha256=digest(meta['page_text'].encode()),request_input_sha256=digest(request.encode()))
            validation=guard['validate_pulso_editorial_proof'](model,meta['page_text'])
            validation.update(primary_article_body_sha256=meta['analysis_base_article_body_sha256'],request_input_sha256=meta['analysis_request_input_sha256'],model_response=model['_pulso_analysis_meta'])
            assert validation==meta['pulso_editorial_proof_validation']==row['full_actual_validation']
            assert validation['decision']=='rejected' and validation['reason']=='editorial_relevance_below_threshold'
            assert meta['editorial_assessment']['threshold']==72 and model['relevance_score']<72
            assert model['_pulso_analysis_meta']['response_id'] in {event['response_id'] for event in paid}
            scores.append(model['relevance_score'])
        else:
            assert entry['reason']=='media_materiality_prefilter'
            assert meta['editorial_assessment']=={'decision':'rejected','reason':'media_materiality_prefilter'}
    assert sorted(scores)==[5,35,58,68]
    assert len(audit['terminal113_entry_sha256'])==113
    for key,expected in audit['terminal113_entry_sha256'].items():
        assert before[key]==queue[key] and digest(queue[key])==expected
    native=[{k:v for k,v in rows.items() if v.get('source')!='pulso_latercera'} for rows in [before,queue]]
    assert native[0]==native[1] and len(native[1])==5293
    histories=[json.loads(frozen(ref,'data/history/superintendencia_signals.json'))['signals'] for ref in [launch,producer]]
    assert histories[0]==histories[1]
    assert len([r for r in histories[1] if r.get('source_name')!='Pulso / La Tercera'])==897
    feeds=[json.loads(frozen(ref,'web/data/radar_today.json'))['signals'] for ref in [launch,producer]]
    assert feeds[0]==feeds[1]
    assert sum(r.get('source_name')=='Pulso / La Tercera' for r in feeds[1])==70
    for path,expected in audit['producer_input_files'].items():
        assert digest(frozen(producer,path))==expected
    qa=json.loads(frozen(producer,'data/audits/pulso_directed_processing_qa_2026_10_11.json'))
    assert qa['verdict']=='FAIL' and len(qa['findings'])==audit['qa_original_findings_count']==1477
    assert execution['processing_selection']['outside_selection_pending_url_count']==audit['explicit_unselected_pending_count']==1508
    assert audit['no_global_pending_zero_claim'] is True

def test_all9_originals_and_actual_prieto_update_replay_exact_body_date_canonical_without_refetch():
    audit=json.loads(AUDIT.read_bytes());fixture_ref=audit['retained_original_evidence_commit']
    path='tests/fixtures/pulso_live9_primary_real/manifest.json'
    manifest_bytes=frozen(fixture_ref,path);manifest=json.loads(manifest_bytes)
    assert manifest['verdict']=='PASS_ALL9_AND_UPDATED_PAID_PRIMARY_EXACT_ORIGINALS'
    assert manifest['retained_originals']==9 and manifest['retained_refreshed_originals']==1
    assert manifest['missing']==manifest['refreshed_missing']==[]
    assert len(manifest['requests'])==10
    assert manifest['no_publisher_request'] is True and manifest['no_model_call'] is True and manifest['queue_history_cache_ledger_writes']==0
    assert len({r['artifact_run_id'] for r in manifest['requests']})==5
    retained={}
    for row in audit['rows']:
        for proof_key,body_key,html_key in [('original_primary','full_original_primary_body','original_html_sha256'),('current_paid_primary','full_actual_primary_body','current_html_sha256')]:
            proof=row[proof_key]
            assert proof['status']=='EXACT_ORIGINAL_REPLAY_VERIFIED'
            compressed=frozen(fixture_ref,proof['gzip_file']);payload=gzip.decompress(compressed)
            record=next(r for r in manifest['requests'] if r['url']==row['url'] and r['sha256']==proof['raw_sha256'])
            assert digest(compressed)==proof['gzip_sha256']==record['gzip_sha256']
            assert digest(payload)==proof['raw_sha256']==record['sha256'] and len(payload)==record['bytes']
            html=payload.decode(record.get('charset') or 'utf-8',errors='replace')
            assert digest(html.encode())==record['returned_text_utf8_sha256']==row[html_key]
            title,body,primary=extract_article(html,row['url'])
            assert title==row['title'] and body==row[body_key]
            assert primary['canonical_url']==row['url'] and primary['publication_date']==row['publication_date']=='2026-10-11'
            assert primary['publication_date_verified'] is True and primary['primary_identity_verified'] is True
            assert record['captured_at'] and record['original_capture_manifest_sha256']
            zip_sha=record.get('artifact_zip_sha256')
            if record['target_stage']=='current_paid_processing_primary':
                zip_sha=manifest['current_artifact_zip_sha256']
            assert isinstance(zip_sha,str) and len(zip_sha)==64
            retained[record['sha256']]=compressed
    assert len(retained)==10
    changed=[row for row in audit['rows'] if row['original_body_changed']]
    assert len(changed)==1 and 'renocido-actor' in changed[0]['url']
    assert changed[0]['original_body_characters']==2645 and changed[0]['current_body_characters']==3449
    assert changed[0]['current_primary_body_sha256']=='d5314e898c41422ecea913473d3cac6f7514a20705d10a684a7c91bc38862cd3'
    assert audit['actual_primary_body_sum']==29047 and audit['original_primary_body_sum']==28243
    old_path='tests/fixtures/pulso_live9_primary_real/manifest-0ed143d49970531393b56228506670bc54556f242c9a13a22e1de10dc30d6036.json'
    old_bytes=frozen(fixture_ref,old_path);old=json.loads(old_bytes)
    assert digest(old_bytes)=='0ed143d49970531393b56228506670bc54556f242c9a13a22e1de10dc30d6036'
    assert old['verdict']=='FAIL_ORIGINALS_INCOMPLETE' and old['retained_originals']==4 and len(old['missing'])==5
    assert audit['technical_status']=='TECHNICAL_LINEAGE_VERIFIED_ACCEPTANCE_PENDING'
    assert audit['acceptance']=='NOT_ACCEPTED_ORIGINAL_PROCESSING_QA_FAIL_PRESERVED'
