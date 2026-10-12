"""Daily checkout must retain Git producers used by paid Pulso proof replay.

The temporary Git graph is explicitly a unit fixture. Its archive contains
unchanged real proof bytes; no publisher/model request or runtime write occurs.
"""
import hashlib
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
PROOF = 'data/audits/pulso_followup5_paid_guard_revalidation_manifest_2026_10_11.json'
PROOF_SHA256 = '1c7389906e3855d2e622e4bc4aab91addcf1e8615e8251f03def15b447f922fa'


def daily_checkout():
    workflow = (ROOT / '.github/workflows/daily-radar.yml').read_text()
    checkouts = re.findall(
        r'^      - uses: actions/checkout@[^\n]+\n        with:\n((?:          [^\n]+\n)+)',
        workflow, re.MULTILINE)
    assert len(checkouts) == 1, 'The daily writer must have one explicit staging checkout'
    return {key.strip(): value.strip() for line in checkouts[0].splitlines()
            for key, separator, value in [line.partition(':')] if separator}


def git(directory, *args, check=True):
    return subprocess.run(['git', *args], cwd=directory, capture_output=True, check=check)


def test_daily_checkout_preserves_staging_and_complete_paid_producer_history():
    options = daily_checkout()
    assert options['ref'] == 'staging'
    assert options.get('fetch-depth') == '0', (
        'Paid producer Git commits are unavailable in a fresh depth-one daily checkout')


def test_real_proof_bytes_in_head_do_not_make_old_producer_available_to_shallow_checkout(tmp_path):
    origin = tmp_path / 'unit-origin'; origin.mkdir()
    git(origin, 'init', '--initial-branch=staging')
    archive = origin / PROOF; archive.parent.mkdir(parents=True)
    payload = (ROOT / PROOF).read_bytes()
    assert hashlib.sha256(payload).hexdigest() == PROOF_SHA256
    archive.write_bytes(payload)
    git(origin, 'add', PROOF)
    commit_options = ('-c', 'user.name=Pulso Git protocol unit',
                      '-c', 'user.email=pulso-unit@example.invalid')
    git(origin, *commit_options, 'commit', '-m', 'unit original immutable paid proof')
    producer = git(origin, 'rev-parse', 'HEAD').stdout.decode().strip()
    (origin / 'README.md').write_text('Later unit checkout; the real proof file remains unchanged.\n')
    git(origin, 'add', 'README.md')
    git(origin, *commit_options, 'commit', '-m', 'unit later checkout')

    # actions/checkout's default depth one has the current file, but cannot
    # perform the historical git-show protocol used by all paid generations.
    git(tmp_path, 'clone', '--depth=1', '--single-branch', '--branch=staging',
        origin.as_uri(), 'unit-shallow')
    shallow = tmp_path / 'unit-shallow'
    assert git(shallow, 'rev-parse', '--is-shallow-repository').stdout.strip() == b'true'
    assert git(shallow, 'show', 'HEAD:' + PROOF).stdout == payload
    missing = git(shallow, 'show', producer + ':' + PROOF, check=False)
    assert missing.returncode != 0 and not missing.stdout

    # Exercise the actual workflow's checkout depth, without mocking a Pulso
    # producer or weakening any model, date, materiality or publication gate.
    options = daily_checkout()
    args = ['clone', '--single-branch', '--branch=' + options['ref']]
    if int(options['fetch-depth']) > 0:
        args.append('--depth=' + options['fetch-depth'])
    git(tmp_path, *args, origin.as_uri(), 'unit-daily')
    daily = tmp_path / 'unit-daily'
    assert git(daily, 'rev-parse', '--is-shallow-repository').stdout.strip() == b'false'
    restored = git(daily, 'show', producer + ':' + PROOF).stdout
    assert restored == payload and hashlib.sha256(restored).hexdigest() == PROOF_SHA256
