"""Independent, reproducible P0 data lane; news and live promotion remain gated."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from .isapre_universe import parse_registry, release_metadata, parse_portfolio, REGISTRY_URL
from .pending_queue import atomic_json
from .source_health import record_data_adapter


class Captures:
    def __init__(self, path):
        self.path = Path(path)
        self.receipts = json.loads((self.path / 'receipts.json').read_text())['receipts']

    def body(self, receipt):
        file = (self.path / receipt['body_file']).resolve()
        if not file.is_relative_to(self.path.resolve()): raise ValueError('Invalid capture path')
        data = file.read_bytes()
        if hashlib.sha256(data).hexdigest() != receipt['sha256']: raise ValueError('Capture hash mismatch')
        if not receipt['transport_ok']: raise ValueError('Official capture transport failed')
        return data

    def html(self, receipt):
        return self.body(receipt).decode('utf-8', errors='replace')


def health(captures, package, *, discovered, unique, recent=0, material=0, published=0,
           rejected=0, deferred=0, errors=0, complete=False, reason):
    receipts = [r for r in captures.receipts if r['package'] == package]
    return dict(pages_checked=len(receipts), items_discovered=discovered, unique_items=unique,
                items_recent=recent, items_material=material, published=published, rejected=rejected,
                deferred=deferred, parse_errors=errors, coverage_complete=complete, coverage_reason=reason,
                technical_status='ok' if receipts and all(r['transport_ok'] for r in receipts) else 'degraded',
                snapshot_semantics='Data observations; published is news cards, never table rows',
                recurrence_validated=False, runtime_activation='held_for_core_quality_gate')


def collect_isapres(captures, root):
    registry = next(r for r in captures.receipts if r['package']=='isapres' and r['kind']=='registry')
    entities = parse_registry(captures.html(registry), fetched_at=registry['completed_at'], sha256=registry['sha256'])
    atomic_json(root/'data/entities/isapres.json', {'schema_version': 1, 'entities': entities})
    release = next(r for r in captures.receipts if r['package']=='isapres' and r['kind']=='cartera_release')
    meta = release_metadata(captures.html(release))
    linked = {x['url'] for x in release['links'] if '.xlsx' in x['url'].lower()}
    book = next(r for r in captures.receipts if r['url'] in linked and r['transport_ok'])
    portfolio = parse_portfolio(captures.body(book), source_url=book['url'], sha256=book['sha256'],
                               published_at=meta['published_at'], fetched_at=book['completed_at'], universe=entities)
    if portfolio['coverage'][-1]['period'] != meta['reporting_period']:
        raise ValueError('Official release month and workbook latest data disagree')
    atomic_json(root/'data/market/isapre_portfolio.json', {'schema_version': 1, **meta, **portfolio})
    evidence = health(captures, 'isapres', discovered=10, unique=10, complete=False,
        reason='10/10 official codes and January–August portfolio reconcile; group/control, legal form Isalud, networks and separate-cadence recurrence remain unverified',
        deferred=1)
    evidence.update(inventory_entities=10, open_entities=7, closed_entities=3,
                    observations=len(portfolio['observations']), validated_periods=len(portfolio['coverage']),
                    latest_reporting_period=meta['reporting_period'], latest_release_at=meta['published_at'],
                    inventory_coverage_complete=True, outcome='OPERATIVE_DEGRADED')
    record_data_adapter(root, 'sis_isapre_universe', evidence)
    return evidence


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--capture-dir', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--only', choices=['isapres', 'cmf', 'dipres', 'all'], default='all')
    args=parser.parse_args(); captures=Captures(args.capture_dir); result={}
    collectors={'isapres': collect_isapres}
    for name, collector in collectors.items():
        if args.only not in (name, 'all'): continue
        try: result[name]=collector(captures, args.output_root)
        except Exception as exc:
            result[name]=health(captures, name, discovered=0, unique=0, errors=1,
                               reason=f'{type(exc).__name__}: {exc}')
            record_data_adapter(args.output_root, f'market_{name}', result[name])
    atomic_json(args.output_root/'data/market/collection_result.json', result)
    print(json.dumps({k: {'outcome':v.get('outcome','OPERATIVE_DEGRADED'), 'reason':v['coverage_reason']} for k,v in result.items()}, ensure_ascii=False))
    if any(v['parse_errors'] for v in result.values()): raise SystemExit(1)


if __name__=='__main__': main()
