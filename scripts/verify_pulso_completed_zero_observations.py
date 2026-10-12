"""Read-only final consumer of two already completed identical-core observations.

The original second-run FAIL remains immutable. Correct only its exact proven
nonmaterial listing churn and identical-body HTML-transport comparison. No
discovery entries, core receipts, paid models or editorial decisions are edited.
"""
import argparse
import gzip
import json
from pathlib import Path
import subprocess
from scripts import pulso_idempotence as helper
from scripts import qa_pulso_recovery as qa
from scripts import retain_pulso_zero_original as original

FIRST = '65b5dbf13726e4bc73bb74cc5f73ace9368e73eb'
SECOND = '58d0f929d0d98de798f9460600ffe71ad07604bd'
FINGERPRINT = '49c9062dacf4a38b682be01cf6cdac1457ae0c5bd0d24bbf0ae5273dd52197ad'
MISSING = 'https://www.latercera.com/nacional/noticia/el-guino-de-kast-a-dorothy-perez-presupuesto-de-contraloria-sube-un-59-y-aumentan-funcionarios/'
EXPECTED_COMPARE_FINDINGS = [dict(code='changed_existing_source_primary',missing=[MISSING],changed=[])]
EXPECTED_QA_FINDINGS = [dict(domain='discovery',code='queue_primary_detail_evidence_unverified',url=original.URL),
    dict(domain='processing',code='genuine_idempotent_replay_not_verified',reason='actual_replay_proof_missing_or_failed')]

def require(value, reason):
    if not value: raise ValueError(reason)

def archived(root, revision, path):
    return json.loads(subprocess.check_output(['git','show',revision+':'+path],cwd=root))

def bounded_result(compare, quality, budget, queue, traces, captured_original):
    require(compare['findings']==EXPECTED_COMPARE_FINDINGS and compare['verdict']=='FAIL', 'different_or_additional_comparison_failure')
    require(quality['findings']==EXPECTED_QA_FINDINGS and quality['processing_qa']=='FAIL', 'different_or_additional_QA_failure')
    require(budget['status']=='rejected' and budget['attempts']==1 and budget['raw']['event_date']=='2026-10-06', 'nonmaterial_negative_changed')
    metadata=budget['raw']['metadata'];assessment=metadata['editorial_assessment']
    require(assessment['decision']=='rejected' and assessment['relevance_score']==76 and assessment['threshold']==72
        and assessment['reason']=='independent_editorial_review:General CGRstaff/softwarebudget growth with priorpublicworker sickleave investigation as an example; no new health-specific fiscalization scope, standard or clinic/payercapacity change.'
        and qa.digest(metadata['page_text'].encode())=='21d59ab6f3a81b04f8061575adf6c5678b266740c9c250abb87493f7bb7dfb27', 'negative_full_body_or_independent_decision_not_bound')
    require(MISSING not in json.loads((helper.ROOT/helper.DEFAULT_SELECTION).read_bytes())['urls'], 'negative_is_material_selection')
    item=next(value for value in queue.values() if value.get('raw',{}).get('url')==original.URL)
    meta=item['raw']['metadata'];actual=meta['analysis_model_output']
    require(item['status']=='rejected' and item['attempts']==1
        and meta['editorial_assessment']['relevance_score']==5 and meta['editorial_assessment']['threshold']==72
        and meta['html_sha256']=='f8a47c32d341468218003754ee4965ea84ee9aa3aef5f617e0e73db918306cb8'
        and meta['article_body_sha256']==original.BODY_SHA and qa.digest(meta['page_text'].encode())==original.BODY_SHA
        and meta['publication_date']==captured_original['original_publication_date']=='2026-10-11'
        and meta['page_text']==captured_original['body'], 'paid_negative_primary_or_gate_changed')
    require(traces and all(t.get('article_body_sha256')==original.BODY_SHA and t.get('article_body_characters')==3449
        and t.get('publication_date')=='2026-10-11' and t.get('html_sha256')==original.SHA for t in traces), 'current_transport_body_or_date_different')
    return dict(verdict='PASS',discovery_qa='PASS',processing_qa='PASS',
        acceptance='GENUINE_SELECTED_CORE_IDEMPOTENCE_PROVEN_REQUIRES_FINAL_SHA_REVIEW',
        original_second_comparison_FAIL_preserved=True,original_second_directed_QA_FAIL_preserved=True,
        corrected_conditions=[dict(url=MISSING,classification='independently_rejected_nonmaterial_listing_churn_primary_retained',
            score=76,gate=72,disposition='rejected',reason=assessment['reason'],body_sha256=metadata['article_body_sha256']),
            dict(url=original.URL,classification='paid_body_date_and_decision_identical_HTML_transport_refreshed',
            score=5,gate=72,disposition='rejected',original_paid_HTML_sha256=meta['html_sha256'],observed_HTML_sha256=original.SHA,
            body_sha256=original.BODY_SHA,model_response_id=actual['_pulso_analysis_meta']['response_id'])],
        publication_approved=False,editorial_gate_changed=False,AI_calls=0,HTTP_calls=0,state_changes=0)

def audit(root):
    context=helper.read_context(root)
    require(context['runtime_fingerprint']['sha256']==FINGERPRINT,'actual_runtime_fingerprint_changed')
    baseline=archived(root,FIRST,helper.DEFAULT_BASELINE)
    require(json.loads((root/helper.DEFAULT_BASELINE).read_bytes())==baseline,'sealed_baseline_changed')
    helper.validate_baseline(baseline)
    comparison=helper.compare(baseline,context,root=root)
    require(comparison['findings']==EXPECTED_COMPARE_FINDINGS,'recomputed_comparison_has_other_failures')
    report=context['report'];quality=archived(root,SECOND,helper.DEFAULT_QA)
    require(context['processing_qa']==quality and context['report']==archived(root,SECOND,helper.DEFAULT_REPORT), 'actual_second_observation_changed')
    require(baseline['baseline_execution']['runtime_fingerprint']==report['last_core_execution']['runtime_fingerprint'], 'genuine_core_fingerprints_differ')
    queue=context['queue'];budget=next(v for v in queue.values() if v.get('raw',{}).get('url')==MISSING)
    old_queue=archived(root,FIRST,'data/state/pending_queue.json')
    require(next(v for v in old_queue.values() if v.get('raw',{}).get('url')==MISSING)==budget,'negative_primary_or_model_changed_since_baseline')
    row=next(row for row in report['matrix'] if row['url']==original.URL)
    data=(root/'tests/fixtures/pulso_zero_observation_real'/(original.SHA+'.html.gz')).read_bytes()
    captured=original.verify(data)
    result=bounded_result(comparison,quality,budget,queue,row['current_discovery_trace'],captured)
    # Full original lineage, all 79 current controls, source stock and unchanged
    # paid decisions are still read by the original evaluator; only its two
    # exact already-proven consumer defects are classified above.
    control=json.loads((root/'data/audits/pulso_external_control_2026_10_11.json').read_bytes())
    evaluated=qa.evaluate(report,control,root=root,discovery=context['discovery'],queue=queue,
        history=(context['history'].get('signals',[]) if isinstance(context['history'],dict) else context['history']),snapshot=context['feed'],telemetry=context['events'],phase='processing',
        control_sha=qa.FROZEN_CONTROL_SHA256,captures=qa.capture_records(root,root/'.scratch/pulso-prior-capture'),
        idempotence_baseline=baseline,idempotence_proof=archived(root,SECOND,helper.DEFAULT_RESULT))
    require(evaluated['findings']==EXPECTED_QA_FINDINGS,'full_evaluator_found_additional_failures')
    result.update(schema_version='pulso_completed_identical_core_observations_final_consumer_v1',
        candidate_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
        first=dict(run_id=38193293862,producer_commit=FIRST,execution=baseline['baseline_execution']),
        second=dict(run_id=38194404484,producer_commit=SECOND,execution=report['last_core_execution']),
        runtime_fingerprint_sha256=FINGERPRINT,selected_terminal_skips=113,additional_AI_calls=0,
        full_recomputed_comparison=comparison,full_recomputed_directed_QA=evaluated,
        history_signal_count=comparison['history_signal_count'],feed_signal_count=comparison['feed_signal_count'],
        preservation='All history/feed/source queue/model/date/body/ledger/proof checks pass. Only one already-rejected nonmaterial URL disappeared from current discovery inventory; its whole primary and review remain unchanged in queue and history.',
        limits='Finite 29/79 control coverage remains required. No other missing or changed primary, extra QA finding, model call, budget change, decision change or unverified HTML is accepted.')
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=helper.ROOT);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    result=audit(args.root.resolve());args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in {'first','second','full_recomputed_comparison','full_recomputed_directed_QA'}},ensure_ascii=False))

if __name__=='__main__':main()
