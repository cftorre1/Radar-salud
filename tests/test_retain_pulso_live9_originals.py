"""Exact real original replay plus independent hash/path/ZIP mutations."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import shutil
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / 'src/radar_salud').exists():
    ROOT = Path('/workspace/Radar-salud')
SOURCE = ROOT / 'scripts/retain_pulso_live9_originals.py'
if not SOURCE.exists():
    SOURCE = Path('/workspace/work/retain_pulso_live9_originals.py')
spec = importlib.util.spec_from_file_location('live_original_retainer', SOURCE)
retainer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retainer)


@pytest.fixture
def original(tmp_path):
    from radar_salud.pulso_source import extract_article
    import gzip
    manifest_path = ROOT / 'tests/fixtures/pulso_runtime_real/manifest.json'
    manifest = json.loads(manifest_path.read_bytes())
    record = next(r for r in manifest['requests'] if r.get('gzip_file') and
                  'todas-somos-vulnerables' in r.get('url',''))
    gzip_path = Path(record['gzip_file'])
    if not str(gzip_path).startswith('tests/fixtures/'):
        gzip_path = manifest_path.parent / gzip_path.name
    else:
        gzip_path = ROOT / gzip_path
    compressed = gzip_path.read_bytes()
    title, body, primary = extract_article(gzip.decompress(compressed).decode(record.get('charset') or 'utf-8'), record['url'])
    target = dict(url=record['url'],queue_fingerprint='explicit-unit-target-key',title=title,
                  publication_date=primary['publication_date'],html_sha256=record['returned_text_utf8_sha256'],
                  body_sha256=retainer.digest(body.encode()),body_characters=len(body))
    artifact = tmp_path / 'original-artifact'
    artifact.mkdir()
    copy = deepcopy(record)
    copy['gzip_file'] = '/original/runner/' + Path(record['gzip_file']).name
    (artifact/'manifest.json').write_text(json.dumps({'requests':[copy]}))
    (artifact/Path(copy['gzip_file']).name).write_bytes(compressed)
    repo = tmp_path / 'isolated-repository'
    return artifact,target,copy,repo


def test_real_original_bytes_body_byline_and_capture_time_are_preserved(original):
    artifact,target,record,repo = original
    retained,missing = retainer.recover_originals(artifact,[target],repo/'tests/fixtures/pulso_live9_primary_real',repo)
    assert not missing and len(retained)==1
    kept = retained[0]
    assert (repo/kept['gzip_file']).read_bytes() == (artifact/Path(record['gzip_file']).name).read_bytes()
    assert kept['captured_at']==record['captured_at']
    assert kept['publication_date']==target['publication_date']
    assert kept['primary_body_sha256']==target['body_sha256']
    assert kept['original_capture_manifest_sha256']==retainer.digest((artifact/'manifest.json').read_bytes())
    assert kept['primary_replay_status']=='EXACT_ORIGINAL_REPLAY_VERIFIED'


@pytest.mark.parametrize('attack',['gzip','raw_sha','traversal','html','body','day','canonical','timestamp'])
def test_changed_hash_date_path_and_missing_original_never_claim_pass(original,attack):
    artifact,target,record,repo=original
    if attack=='gzip':
        (artifact/Path(record['gzip_file']).name).write_bytes(b'explicit-unit-corrupted-original')
    elif attack=='raw_sha':record['sha256']='0'*64
    elif attack=='traversal':record['gzip_file']='../../'+Path(record['gzip_file']).name
    elif attack=='html':target['html_sha256']='1'*64
    elif attack=='body':target['body_sha256']='2'*64
    elif attack=='day':target['publication_date']='2026-10-10'
    elif attack=='canonical':target['url']+='explicit-unit-changed-path/'
    else:record.pop('captured_at',None)
    (artifact/'manifest.json').write_text(json.dumps({'requests':[record]}))
    kept,missing=retainer.recover_originals(artifact,[target],repo/'tests/fixtures/pulso_live9_primary_real',repo)
    assert not kept and len(missing)==1
    assert missing[0]['status']=='EXACT_ORIGINAL_MISSING_OR_INVALID'


def test_zip_digest_and_archive_path_traversal_fail_closed(tmp_path):
    path=tmp_path/'original.zip'
    with zipfile.ZipFile(path,'w') as archive:archive.writestr('capture/manifest.json','{}')
    retainer.verify_zip(path,retainer.digest(path.read_bytes()))
    with pytest.raises(ValueError,match='digest_mismatch'):retainer.verify_zip(path,'0'*64)
    with zipfile.ZipFile(path,'w') as archive:archive.writestr('../untrusted.json','{}')
    with pytest.raises(ValueError,match='unsafe_original_actions_artifact_path'):
        retainer.verify_zip(path,retainer.digest(path.read_bytes()))


def test_immutable_live9_original_and_actual_paid_prieto_revision_are_separate():
    old, _ = retainer.targets_from_git('1b4817164dbd9cd091197e1c7ebd03de6fa93526', ROOT)
    current, _ = retainer.targets_from_git('d48a495a5fcefb9adaca26ca30b1f12ddad7e59f', ROOT)
    changed = retainer.refreshed_targets(old, current)
    assert len(changed) == 1
    assert changed[0]['url'] == retainer.PRIETO_URL
    assert changed[0]['body_characters'] == 3449
    assert next(r for r in old if r['url'] == retainer.PRIETO_URL)['body_characters'] == 2645
    attacked = deepcopy(current)
    attacked[0]['html_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='not_exact_observed'):
        retainer.refreshed_targets(old, attacked)
