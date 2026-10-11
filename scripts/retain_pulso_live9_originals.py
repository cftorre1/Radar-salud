"""Recover existing LIVE9 publisher bytes from a verified Actions artifact.

No publisher request, model call, discovery, or queue/history/cache mutation.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

from radar_salud.pulso_source import extract_article

REPO = Path(__file__).resolve().parents[1]
ARTIFACT_SHA256 = '481a48062b1a689a370df5040a211889ba59d664f0f0b9a2fad5728e86d0c26e'
LIVE_ARTIFACT_SHA256 = '9346939527e5ece2c6ff82c8e0659489e9ae26c6af1034527b29b9d6570d3c02'
PRIETO_URL = 'https://www.latercera.com/culto/noticia/renocido-actor-gabriel-prieto-fallece-a-los-65-anos/'
PRIETO_CURRENT_HTML_SHA256 = 'f8a47c32d341468218003754ee4965ea84ee9aa3aef5f617e0e73db918306cb8'
PRIETO_CURRENT_BODY_SHA256 = 'd5314e898c41422ecea913473d3cac6f7514a20705d10a684a7c91bc38862cd3'
SUPPLEMENTAL_ARTIFACTS = (
    {'artifact_run_id':38159032940,'artifact_id':11710432466,'artifact_zip_sha256':'57eec3e2b193d4dd6b7894faf112f459710258ce074e27ab7fd3e5ecf11db52b'},
    {'artifact_run_id':38172352115,'artifact_id':11714388920,'artifact_zip_sha256':'23ba2e30ff5dbe3dacde409badf63c278c2b51308843c3d21b678894e423b001'},
    {'artifact_run_id':38181190464,'artifact_id':11718153077,'artifact_zip_sha256':'7fa4b6850451f9aa7093446072fdb14a62bb5b63e351248300ba52cceb3d210d'},
)
COHORT = 'data/audits/pulso_additional_live9_recovery_cohort_2026_10_11.json'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify_zip(path, expected=ARTIFACT_SHA256):
    if digest(Path(path).read_bytes()) != expected:
        raise ValueError('original_actions_artifact_zip_digest_mismatch')
    with zipfile.ZipFile(path) as archive:
        for entry in archive.infolist():
            parts = Path(entry.filename).parts
            if Path(entry.filename).is_absolute() or '..' in parts:
                raise ValueError('unsafe_original_actions_artifact_path')
        if archive.testzip() is not None:
            raise ValueError('original_actions_artifact_crc_mismatch')


def targets_from_git(ref, repo=REPO):
    def blob(path):
        return subprocess.check_output(['git', 'show', ref + ':' + path], cwd=repo)
    cohort_bytes, queue_bytes = blob(COHORT), blob('data/state/pending_queue.json')
    urls = json.loads(cohort_bytes)['urls']
    queue = json.loads(queue_bytes)
    if len(urls) != 9 or len(set(urls)) != 9:
        raise ValueError('exact_existing_live9_target_set_required')
    targets = []
    for url in urls:
        matches = [(key, entry) for key, entry in queue.items()
                   if entry.get('source') == 'pulso_latercera' and entry.get('raw', {}).get('url') == url]
        if len(matches) != 1:
            raise ValueError('existing_live_primary_queue_identity_not_unique')
        key, entry = matches[0]
        raw, meta = entry['raw'], entry['raw']['metadata']
        if (any(meta.get(field) is not True for field in ['article_verified', 'primary_identity_verified', 'publication_date_verified'])
                or meta.get('canonical_url') != url or digest(meta['page_text'].encode()) != meta['article_body_sha256']):
            raise ValueError('existing_live_primary_body_date_identity_unverified')
        targets.append(dict(url=url, queue_fingerprint=key, title=raw['title'], publication_date=raw['event_date'],
                            html_sha256=meta['html_sha256'], body_sha256=meta['article_body_sha256'],
                            body_characters=len(meta['page_text'])))
    return targets, dict(target_commit=ref, cohort_path=COHORT, cohort_sha256=digest(cohort_bytes),
                         queue_path='data/state/pending_queue.json', queue_sha256=digest(queue_bytes))


def refreshed_targets(baseline, current):
    """Preserve the one observed LIVE9 update; reject unrecorded substitutions."""
    prior = {r['url']: r for r in baseline}
    if len(prior) != 9 or {r['url'] for r in current} != set(prior):
        raise ValueError('live9_original_target_identity_set_changed')
    changed = [r for r in current if r != prior[r['url']]]
    if (len(changed) != 1 or changed[0]['url'] != PRIETO_URL
            or changed[0]['html_sha256'] != PRIETO_CURRENT_HTML_SHA256
            or changed[0]['body_sha256'] != PRIETO_CURRENT_BODY_SHA256
            or changed[0]['body_characters'] != 3449
            or changed[0]['queue_fingerprint'] != prior[PRIETO_URL]['queue_fingerprint']
            or changed[0]['publication_date'] != prior[PRIETO_URL]['publication_date']):
        raise ValueError('live9_publisher_update_not_exact_observed_prieto_revision')
    return changed


def recover_originals(artifact_root, targets, destination, repo=REPO):
    artifact_root, destination, repo = map(lambda p: Path(p).resolve(), [artifact_root, destination, repo])
    if not destination.is_relative_to(repo / 'tests/fixtures'):
        raise ValueError('original_fixture_destination_outside_repository_fixtures')
    destination.mkdir(parents=True, exist_ok=True)
    originals = []
    for manifest in sorted(artifact_root.rglob('manifest.json')):
        payload = manifest.read_bytes()
        try:
            requests = json.loads(payload).get('requests', [])
        except (ValueError, AttributeError):
            continue
        for request in requests:
            if isinstance(request, dict) and request.get('gzip_file'):
                originals.append((manifest, digest(payload), request))
    files_by_name = {}
    for path in artifact_root.rglob('*.gz'):
        files_by_name.setdefault(path.name, []).append(path)
    retained, missing = [], []
    for target in targets:
        errors, selected = [], None
        for manifest, manifest_sha, request in originals:
            if request.get('url') != target['url'] or request.get('status') != 200:
                continue
            try:
                original_path = Path(request['gzip_file'])
                if '..' in original_path.parts:
                    raise ValueError('unsafe_original_capture_gzip_path')
                if target['html_sha256'] not in [request.get('sha256'), request.get('returned_text_utf8_sha256')]:
                    continue
                candidates = files_by_name.get(original_path.name, [])
                matched = None
                for candidate in candidates:
                    compressed = candidate.read_bytes()
                    if digest(compressed) != request.get('gzip_sha256'):
                        continue
                    raw = gzip.decompress(compressed)
                    if digest(raw) != request.get('sha256') or len(raw) != request.get('bytes'):
                        raise ValueError('original_capture_raw_hash_or_size_mismatch')
                    matched = candidate, compressed, raw
                    break
                if matched is None:
                    raise ValueError('exact_original_capture_gzip_bytes_missing')
                candidate, compressed, raw = matched
                html = raw.decode(request.get('charset') or 'utf-8', errors='replace')
                if digest(html.encode()) != target['html_sha256']:
                    raise ValueError('original_capture_decoded_html_sha_mismatch')
                title, body, primary = extract_article(html, target['url'])
                if (title != target['title'] or primary.get('canonical_url') != target['url']
                        or primary.get('publication_date') != target['publication_date']
                        or digest(body.encode()) != target['body_sha256'] or len(body) != target['body_characters']
                        or any(primary.get(field) is not True for field in ['article_verified', 'primary_identity_verified', 'publication_date_verified'])):
                    raise ValueError('original_capture_primary_body_date_canonical_or_title_mismatch')
                if not request.get('captured_at'):
                    raise ValueError('original_capture_timestamp_missing')
                name = request['sha256'] + '.html.gz'
                output = destination / name
                if output.exists() and output.read_bytes() != compressed:
                    name = request['sha256'] + '-' + request['gzip_sha256'][:12] + '.html.gz'
                    output = destination / name
                if output.exists() and output.read_bytes() != compressed:
                    raise ValueError('immutable_original_fixture_conflict')
                if not output.exists():
                    shutil.copyfile(candidate, output)
                selected = dict(deepcopy(request), gzip_file=str(output.relative_to(repo)),
                    captured_at=request['captured_at'], charset=request.get('charset') or 'utf-8',
                    returned_text_utf8_sha256=digest(html.encode()), gzip_sha256=digest(compressed),
                    original_capture_gzip_file=request['gzip_file'], original_capture_manifest_sha256=manifest_sha,
                    original_capture_manifest_path=str(manifest.relative_to(artifact_root)),
                    capture_provenance='preserved_original_http_response',
                    primary_identity_verified=True, publication_date_verified=True,
                    publication_date=primary['publication_date'], publication_date_source=primary.get('publication_date_source'),
                    primary_body_sha256=digest(body.encode()), primary_body_characters=len(body),
                    expected_html_sha256=target['html_sha256'], primary_replay_status='EXACT_ORIGINAL_REPLAY_VERIFIED',
                    queue_fingerprint=target['queue_fingerprint'])
                break
            except (OSError, ValueError, KeyError, TypeError) as error:
                errors.append(str(error))
        if selected is None:
            missing.append(dict(target, status='EXACT_ORIGINAL_MISSING_OR_INVALID', errors=sorted(set(errors))))
        else:
            retained.append(selected)
    return retained, missing


def recover_across_observed_artifacts(sources, targets, destination, repo=REPO):
    retained, remaining, history_errors = [], list(targets), {}
    for root, artifact_proof in sources:
        if not remaining:
            break
        found, missing = recover_originals(root, remaining, destination, repo)
        for request in found:
            request.update(artifact_proof)
        retained.extend(found)
        for row in missing:
            history_errors.setdefault(row['url'], set()).update(row['errors'])
        urls = {row['url'] for row in missing}
        remaining = [row for row in remaining if row['url'] in urls]
    missing = [dict(row, status='EXACT_ORIGINAL_MISSING_OR_INVALID',
                    errors=sorted(history_errors.get(row['url'], set()))) for row in remaining]
    order = {row['url']: index for index, row in enumerate(targets)}
    retained.sort(key=lambda row: order[row['url']])
    return retained, missing


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--artifact-zip', required=True)
    parser.add_argument('--artifact-root', required=True)
    parser.add_argument('--target-commit', required=True)
    parser.add_argument('--current-commit', required=True)
    parser.add_argument('--live-artifact-zip', required=True)
    parser.add_argument('--live-artifact-root', required=True)
    parser.add_argument('--supplemental-artifact-root', action='append', required=True)
    parser.add_argument('--supplemental-artifact-zip', action='append', required=True)
    parser.add_argument('--destination', default='tests/fixtures/pulso_live9_primary_real')
    args = parser.parse_args()
    verify_zip(args.artifact_zip)
    verify_zip(args.live_artifact_zip, LIVE_ARTIFACT_SHA256)
    if len(args.supplemental_artifact_zip) != 3 or len(args.supplemental_artifact_root) != 3:
        raise ValueError('exact_three_supplemental_original_artifacts_required')
    for path, proof in zip(args.supplemental_artifact_zip, SUPPLEMENTAL_ARTIFACTS):
        verify_zip(path, proof['artifact_zip_sha256'])
    targets, target_proof = targets_from_git(args.target_commit)
    current, current_proof = targets_from_git(args.current_commit)
    changed = refreshed_targets(targets, current)
    sources = [(args.artifact_root, dict(artifact_run_id=38149773071, artifact_id=11707255596,artifact_zip_sha256=ARTIFACT_SHA256))]
    sources.extend(zip(args.supplemental_artifact_root, SUPPLEMENTAL_ARTIFACTS))
    retained, missing = recover_across_observed_artifacts(sources, targets, REPO / args.destination)
    refreshed, refreshed_missing = recover_originals(args.live_artifact_root, changed, REPO / args.destination)
    for request in retained:
        request['target_stage'] = 'original_discovery_primary'
    for request in refreshed:
        request['target_stage'] = 'current_paid_processing_primary'
        request['artifact_run_id'] = 38183583899
        request['artifact_id'] = 11718992843
    complete = len(retained)==9 and not missing and len(refreshed)==1 and not refreshed_missing
    proof = dict(schema_version='pulso_live9_original_primary_recovery_v1',
        artifact_run_id=38149773071, artifact_id=11707255596, artifact_zip_sha256=ARTIFACT_SHA256,
        target_proof=target_proof, current_target_proof=current_proof,
        verified_supplemental_original_artifacts=list(SUPPLEMENTAL_ARTIFACTS),
        current_artifact_run_id=38183583899, current_artifact_id=11718992843,
        current_artifact_zip_sha256=LIVE_ARTIFACT_SHA256, retained_at=datetime.now(timezone.utc).isoformat(),
        targets=len(targets), retained_originals=len(retained), refreshed_primary_targets=len(changed),
        retained_refreshed_originals=len(refreshed), requests=retained+refreshed, missing=missing,
        refreshed_missing=refreshed_missing,
        verdict='PASS_ALL9_AND_UPDATED_PAID_PRIMARY_EXACT_ORIGINALS' if complete else 'FAIL_ORIGINALS_INCOMPLETE',
        no_publisher_request=True, no_model_call=True, no_discovery_call=True,
        queue_history_cache_ledger_writes=0, publication_approved=False)
    output = REPO / args.destination / 'manifest.json'
    if output.exists():
        prior = output.read_bytes()
        history = output.parent / ('manifest-' + digest(prior) + '.json')
        if not history.exists():
            history.write_bytes(prior)
    output.write_text(json.dumps(proof, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'verdict':proof['verdict'], 'retained':len(retained), 'missing':len(missing),
                      'retained_refreshed':len(refreshed),'refreshed_missing':len(refreshed_missing),
                      'manifest_sha256':digest(output.read_bytes())}))
    raise SystemExit(0 if complete else 1)


if __name__ == '__main__':
    main()
