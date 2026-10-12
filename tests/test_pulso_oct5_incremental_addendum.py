"""Oct5 retry release requires immutable original evidence, never approval."""
import gzip
import hashlib
import json
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

import pytest

from radar_salud import pulso_incremental_review as review
from radar_salud.models import RawItem
from radar_salud.pending_queue import fingerprint
from radar_salud.pulso_source import _verified_detail

ROOT = Path(__file__).resolve().parents[1]
ADDENDUM = json.loads(review.ADDENDUM_PATH.read_text())
CONTROL = json.loads((ROOT / ADDENDUM['article']['primary_body_ref']).read_text())['all_controls'][5]
OLD = json.loads(review.REVIEW_PATH.read_text())


def held_original():
    article = ADDENDUM['article']
    encoded = (ROOT / article['gzip_file']).read_bytes()
    assert hashlib.sha256(encoded).hexdigest() == article['gzip_sha256']
    html = gzip.decompress(encoded).decode('utf-8')
    assert hashlib.sha256(html.encode()).hexdigest() == article['html_sha256']
    detail = _verified_detail({'url':article['source_url'],'listing':'independent-original-fixture'}, lambda _: html, None)
    meta = deepcopy(detail['metadata'])
    assert meta['page_text'] == CONTROL['primary_body_full']
    meta.update(captured_at=article['source_capture_at'], html_sha256=article['html_sha256'],
                article_body_sha256=article['body_sha256'], article_body_complete=True,
                primary_identity_verified=True, publication_date_verified=True,
                editorial_hold=ADDENDUM['prior_review']['reason'],
                editorial_assessment={'decision':'pending','reason':ADDENDUM['prior_review']['reason']},
                editorial_review_context={'compared_signal':OLD['reviews'][0]['compared_signal']},
                incremental_review={'review_ref':review.REVIEW_REF,'review_sha256':review.REVIEW_SHA256,
                    'decision':'keep_hold','reason':ADDENDUM['prior_review']['reason'],
                    'publication_approved':False,'verified_publication_date':article['publication_date'],
                    'verified_body_sha256':article['body_sha256'],'verified_html_sha256':article['html_sha256']})
    return RawItem('pulso_latercera', detail['title'], article['source_url'], 'Pulso / La Tercera',
                   'press_high_trust', article['publication_date'], raw_text=meta['page_text'][:1800], metadata=meta)


def test_pure_verifier_and_release_preserve_prior_review_identity_and_bookkeeping():
    raw=held_original(); before=deepcopy(asdict(raw)); key=fingerprint(raw)
    proof=review.verified_incremental_release(raw)
    assert proof and proof['publication_approved'] is False
    assert asdict(raw)==before
    assert review.apply_incremental_review(raw)
    assert fingerprint(raw)==key
    assert raw.metadata['incremental_review']==before['metadata']['incremental_review']
    assert raw.metadata['editorial_assessment']==before['metadata']['editorial_assessment']
    assert 'editorial_hold' not in raw.metadata
    assert raw.metadata['incremental_review_addendum']==proof
    assert review.verified_incremental_release(raw)==proof
    context=raw.metadata['editorial_review_context']
    assert context['media_materiality_threshold']==72
    assert context['publication_approved'] is False
    assert context['evidence_maturity']=='media_reported'
    assert 'proposed_2027_budget_not_enacted' in context['event_status']
    assert any('30 or 40%' in text for text in context['interpretation_constraints'])
    assert not {'relevance_score','scores','publication_ready_score'} & raw.metadata.keys()
    saved=deepcopy(asdict(raw))
    assert review.apply_incremental_review(raw) is False
    assert asdict(raw)==saved


@pytest.mark.parametrize('field,value',[
    ('article_verified',False),('primary_identity_verified',False),('publication_date_verified',False),
    ('article_body_complete',False),('publication_date',None),('html_sha256','0'*64),
    ('article_body_sha256','0'*64),('page_text','listing summary'),('captured_at','2026-10-10T20:00:00Z'),
    ('canonical_url','https://www.latercera.com/nacional/noticia/other/'),
    ('publication_timestamp','2026-10-05T14:00:49.546Z'),
    ('possible_publication_days',['2026-10-04','2026-10-05']),
    ('publisher_exception_reason','publisher_conflicting_publication_dates'),
    ('editorial_hold','another_hold'),('queue_status','published'),
    ('editorial_assessment',{'decision':'rejected'}),('incremental_review',{}),
])
def test_mismatched_stale_partial_arbitrary_or_terminal_evidence_never_releases(field,value):
    raw=held_original();raw.metadata[field]=value;before=deepcopy(asdict(raw))
    assert review.verified_incremental_release(raw) is None
    assert review.apply_incremental_review(raw) is False
    assert asdict(raw)==before


def test_wrong_raw_day_url_and_unpinned_audit_fail_closed(monkeypatch,tmp_path):
    for field,value in [('event_date','2026-10-04'),('url','https://www.latercera.com/nacional/noticia/other/'),
                        ('source_slug','other')]:
        raw=held_original();setattr(raw,field,value)
        assert review.verified_incremental_release(raw) is None
    modified=deepcopy(ADDENDUM);modified['decision']='publication_approved'
    path=tmp_path/'changed.json';path.write_text(json.dumps(modified));monkeypatch.setattr(review,'ADDENDUM_PATH',path)
    assert review.verified_incremental_release(held_original()) is None
