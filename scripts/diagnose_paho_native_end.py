"""Independent diagnostics of existing PAHO end probes; no endpoint requests."""
import argparse
import hashlib
import importlib.util
import json
from datetime import date
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--captures', type=Path, required=True)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--auditor', type=Path, default=Path('scripts/audit_global_captures.py'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('independent_raw_auditor', args.auditor)
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    inventory_bytes = args.inventory.read_bytes()
    inventory = json.loads(inventory_bytes)
    as_of = date.fromisoformat(inventory['as_of'])
    readers, rows, receipts = {}, {}, {}
    source_hashes = {str(args.inventory): hashlib.sha256(inventory_bytes).hexdigest()}
    results = []
    for route in inventory['routes']:
        if route['route']['source'] != 'paho' or not route.get('date_partitions'):
            continue
        for page in route['pages']:
            url = page['url']
            key = hashlib.sha256(url.encode()).hexdigest()[:24]
            record_path = args.captures / (key + '.json')
            record_bytes = record_path.read_bytes()
            record = json.loads(record_bytes)
            if record['requested_url'] != url or record['body_file'] != key + '.body':
                raise ValueError('capture identity binding failed')
            body_path = args.captures / record['body_file']
            body = body_path.read_bytes()
            if hashlib.sha256(body).hexdigest() != record['body_sha256'] or len(body) != record['body_bytes']:
                raise ValueError('raw capture hash or length failed')
            source_hashes[str(record_path)] = hashlib.sha256(record_bytes).hexdigest()
            source_hashes[str(body_path)] = hashlib.sha256(body).hexdigest()
            readers[url] = audit.NativeHTML(body)
            rows[url] = audit.independent_index(body, route['route'], url, as_of)
            receipts[url] = {'body_sha256': record['body_sha256'], 'origin_json_sha256': source_hashes[str(record_path)]}
        for part in route['date_partitions']:
            if part['stop_reason'] != 'date_partition_empty_unverified':
                continue
            expected = {'date[min]': part['query_from'], 'date[max]': part['query_to']}
            ordered = sorted([page['url'] for page in route['pages']
                              if {k: v for k, v in parse_qsl(urlsplit(page['url']).query) if k in expected} == expected],
                             key=lambda url: int(dict(parse_qsl(urlsplit(url).query)).get('page', 0)))
            proof = audit.native_clamped_empty_end_checks(ordered, readers, rows)
            current = readers[ordered[-1]]
            results.append({'section': route['route']['section'], 'from': part['from'], 'to': part['to'],
                            'terminal_url': ordered[-1], 'prior_url': ordered[-2] if len(ordered) > 1 else None,
                            'checks': proof, 'failed_checks': [k for k, v in proof.items() if not v],
                            'all_independent_checks_passed': all(proof.values()),
                            'news_views': current.news_views, 'global_pager_nodes': current.pager_elements,
                            'current_pager_trees': current.pager_navs,
                            'previous_pager_trees': readers[ordered[-2]].pager_navs if len(ordered) > 1 else [],
                            'global_pagination_rels': [a for a in current.links if set(a.get('rel', '').split()) & {'first', 'prev', 'previous', 'next', 'last'}],
                            'h1': current.h1, 'terminal_capture': receipts[ordered[-1]],
                            'prior_capture': receipts.get(ordered[-2]) if len(ordered) > 1 else None})
    unchanged = all(hashlib.sha256(Path(path).read_bytes()).hexdigest() == value for path, value in source_hashes.items())
    if not unchanged:
        raise ValueError('source input changed during diagnostics')
    report = {'result': 'PASS_DIAGNOSTIC_READ_ONLY', 'run_id': inventory['run_id'],
              'inventory_sha256': hashlib.sha256(inventory_bytes).hexdigest(),
              'auditor_script_sha256': hashlib.sha256(args.auditor.read_bytes()).hexdigest(),
              'network_requests': 0, 'canonical_state_writes': 0, 'does_not_promote_coverage': True,
              'inputs_unchanged': unchanged, 'unverified_partitions': len(results),
              'all_independent_checks_passed': sum(row['all_independent_checks_passed'] for row in results),
              'partitions': results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'partitions'}))


if __name__ == '__main__':
    main()
