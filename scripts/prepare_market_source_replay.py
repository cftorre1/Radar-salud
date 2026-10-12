"""Restore already captured public evidence for offline PR validation."""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile


ARCHIVES = {
    'native_final_indexes.zip': 'f9d37ae521b19e2bb966e60f693284a5d11d23b5d9df42fea3361c6d45241285',
    'native_validated.zip': 'a6315789402ff0d7d1e15e99106f829935e5c5a59eb4cc51de0826bb99c783bc',
    'equity_identity_fixtures.zip': '59068da34358e0179fa00ef7658104a7e1cd905be1cad458074d0a96baaa9dda',
}


def prepare(output):
    evidence = Path(__file__).resolve().parents[1] / 'data/audits/source_expansion'
    output = output.resolve()
    if output.is_relative_to(evidence.parents[1]):
        raise ValueError('Replay must remain outside canonical repository data')
    output.mkdir(parents=True, exist_ok=True)
    for name, expected in ARCHIVES.items():
        if hashlib.sha256((evidence / name).read_bytes()).hexdigest() != expected:
            raise ValueError('Retained archive hash mismatch: ' + name)
    with ZipFile(evidence / 'native_final_indexes.zip') as archive:
        for member in archive.namelist():
            target = (output / member).resolve()
            if not target.is_relative_to(output):
                raise ValueError('Invalid retained archive path')
        archive.extractall(output)
    payload = json.loads((output / 'receipts.json').read_text())
    missing = [r for r in payload['receipts'] if not (output / r['body_file']).is_file()]
    by_hash = {}
    for receipt in missing:
        target = (output / receipt['body_file']).resolve()
        if not target.is_relative_to(output):
            raise ValueError('Invalid retained receipt path')
        by_hash.setdefault(receipt['sha256'], []).append(target)
    for name in ('native_validated.zip', 'equity_identity_fixtures.zip'):
        with ZipFile(evidence / name) as archive:
            for member in archive.namelist():
                if not member.endswith(('.body', '.pdf')):
                    continue
                content = archive.read(member)
                for target in by_hash.pop(hashlib.sha256(content).hexdigest(), []):
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(content)
    absent = [r for r in missing if not (output / r['body_file']).is_file()]
    optional_kinds = {'Análisis Razonado', 'Declaración de responsabilidad',
                      'Hechos Relevantes', 'Estados financieros (PDF)', 'Presentación Corporativa'}
    for receipt in absent:
        if receipt['package'] != 'cmf' or not (receipt['kind'] in optional_kinds or
                receipt['kind'].startswith('https://ilcinversiones.cl/app/uploads/')):
            raise ValueError('Required parser input unavailable: ' + receipt['kind'])
    report = dict(mode='retained_evidence_replay', original_as_of=payload.get('as_of'),
                  remote_source_requests=0, paid_model_calls=0, archives=ARCHIVES,
                  restored_bodies=len(missing)-len(absent),
                  unavailable_unused_bodies=[dict(kind=r['kind'], sha256=r['sha256']) for r in absent],
                  scope='Original retained parser inputs; no fresh capture, recurrence or exhaustive coverage claim')
    (output.parent / 'replay_preparation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'unavailable_unused_bodies'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    prepare(parser.parse_args().output)
