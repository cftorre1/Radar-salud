"""Persistent surface stop-loss and daily freshness; transport is not coverage."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
import hashlib
import json
from urllib.parse import urlsplit

from .pending_queue import atomic_json

SOURCES = frozenset(('minsal','fonasa','fonasa_datos_abiertos','isp_anamed','isp_surveillance'))
_scope = ContextVar('daily_first_scope', default=None)


class SurfaceHeld(RuntimeError):
    pass


@contextmanager
def monitor_scope(root, slug, *, now=None, monitor=None):
    monitor = monitor if monitor is not None else {'root':root, 'slug':slug, 'now':now, 'requests':[], 'held':[]}
    token = _scope.set(monitor if slug in SOURCES else None)
    try:
        yield monitor
    finally:
        _scope.reset(token)


def _stamp(value):
    try:
        stamp = datetime.fromisoformat(value.replace('Z','+00:00'))
        return stamp if stamp.tzinfo else None
    except (ValueError, TypeError, AttributeError):
        return None


def controlled_download(url, slug, fetch):
    monitor = _scope.get()
    if not monitor or monitor['slug'] != slug:
        return fetch()
    root, now = monitor['root'], monitor['now'] or datetime.now(timezone.utc)
    path = root/'data/state/daily_first_surfaces.json'
    state = json.loads(path.read_text()) if path.exists() else {}
    # www/bare aliases of one domain share stop-loss; .gob.cl stays independent of .cl.
    parsed = urlsplit(url)
    surface = (parsed.hostname or '').removeprefix('www.')+parsed.path+'?'+parsed.query
    key = hashlib.sha256(f'{slug}|{surface}'.encode()).hexdigest()
    old = state.get(key,{})
    retry = _stamp(old.get('retry_after'))
    if retry and now < retry:
        monitor['held'].append(dict(url=url, retry_after=old['retry_after'], reason=old.get('hold_reason','two_equivalent_failures_stop_loss')))
        raise SurfaceHeld('daily_first_surface_held_until_'+old['retry_after'])
    row = dict(source=slug,url=url,last_attempt_at=now.isoformat())
    try:
        result = fetch()
    except Exception as exc:
        from .public_source_evidence import failure_details
        signature = failure_details(exc)['failure_signature']
        count = old.get('equivalent_failures',0)+1 if old.get('failure_signature') == signature else 1
        row.update(outcome='failed', failure_signature=signature, equivalent_failures=count,
                   last_successful_capture_at=old.get('last_successful_capture_at'))
        if count >= 2:
            row['retry_after'] = (now+timedelta(hours=24)).isoformat()
        state[key] = row; atomic_json(path,state)
        monitor['requests'].append(row)
        raise
    row.update(outcome='captured', equivalent_failures=0, failure_signature=None,
               retry_after=None, last_successful_capture_at=now.isoformat())
    state[key] = row; atomic_json(path,state)
    monitor['requests'].append(row)
    return result


def freshness(row, *, now=None):
    now = now or datetime.now(timezone.utc)
    checked = _stamp(row.get('last_attempt_at') or row.get('checked_at'))
    complete = _stamp(row.get('last_verified_discovery_at'))
    age = (now-checked).total_seconds()/3600 if checked else None
    return dict(poll_age_hours=round(age,2) if age is not None else None,
                daily_check_state='unknown' if age is None else 'invalid_future' if age < -0.0834 else 'stale_48h' if age >= 48 else 'overdue_24h' if age >= 24 else 'checked_within_24h',
                last_verified_discovery_at=complete.isoformat() if complete else None,
                recovery_cadence_validated=False)


def annotate_health(root, slug, *, previous, monitor, items, inventory=None, error=None, source_queue=None, now=None):
    """Decorate only the selected source after core discovery/editorial processing."""
    now = now or datetime.now(timezone.utc)
    path = root/'data/source_health.json'
    if not path.exists():
        return  # Health writer may be substituted in an isolated engine test.
    data = json.loads(path.read_text()); row = data['sources'][slug]
    inventory = inventory or {}
    requests = monitor.get('requests',[]); held = monitor.get('held',[])
    verified = [r for r in items if r.get('event_date')]
    dates = [r['event_date'] for r in verified]
    successful = [r for r in requests if r['outcome'] == 'captured']
    last_attempt = max((r['last_attempt_at'] for r in requests), default=previous.get('last_attempt_at',previous.get('checked_at')))
    complete = bool(verified and not error and not inventory.get('parse_errors'))
    observed_hashes={r['url']:r.get('metadata',{}).get('primary_body_sha256') for r in items}
    assessments=[r['raw']['metadata']['editorial_assessment'] for r in source_queue or []
                 if r.get('raw',{}).get('metadata',{}).get('editorial_assessment')
                 and r['raw']['metadata']['editorial_assessment'].get('primary_body_sha256')
                 and r['raw']['metadata']['editorial_assessment']['primary_body_sha256']==observed_hashes.get(r['raw']['url'])]
    zero_reason=(None if row.get('published') else 'editorial_rejections_this_run' if row.get('processed_rejections')
                 else 'blocked_surface_not_evidence_of_absence' if not items
                 else 'verified_candidates_pending_editorial' if row.get('pending')
                 else 'terminal_decisions_replayed_no_new_publications')
    row.update(last_attempt_at=last_attempt,
               assessed_at=now.isoformat(), last_successful_capture_at=max((r['last_successful_capture_at'] for r in successful),default=previous.get('last_successful_capture_at')),
               last_verified_discovery_at=now.isoformat() if complete else previous.get('last_verified_discovery_at'),
               latest_verified_publication_at=max(dates,default=previous.get('latest_verified_publication_at')),
               latest_detected_at=max(dates,default=previous.get('latest_detected_at')),
               pages_checked=len(requests), held_surfaces=len(held),
               items_discovered=inventory.get('items_discovered',len(items)), unique_items=len(items),
               items_recent=inventory.get('items_recent',sum(0 <= (now.date()-datetime.fromisoformat(r['event_date']).date()).days < 3 for r in verified)),
               items_material=sum(a.get('decision')=='accept' for a in assessments) if assessments else None,
               items_evaluated=len(assessments), materiality_status='primary_bound_editorial_assessment' if assessments else 'requires_existing_editorial_assessment',
               parse_errors=inventory.get('parse_errors',0), coverage_complete=False,
               coverage_reason=inventory.get('coverage_reason','official_surface_blocked_inventory_unknown' if error else 'bounded_discovery_not_exhaustive_reconciliation'),
               recovery_outcome='EXTERNAL_BLOCKER_PROVEN' if not items and (error or held) and previous.get('recovery_outcome')=='EXTERNAL_BLOCKER_PROVEN' else 'OPERATIVE_DEGRADED',
               zero_publication_reason=zero_reason,
               next_retry_at=min((r['retry_after'] for r in requests+held if r.get('retry_after')),default=None))
    if not requests:
        row['checked_at'] = previous.get('checked_at')
        row['engine_checked_at'] = previous.get('engine_checked_at')
        row['technical_status'] = 'held' if held else 'not_observed'
    row['status'] = 'error' if not items and (error or held) else 'warning'
    row['coverage_status'] = 'partial' if items else 'blocked' if error or held else 'gap'
    if not items:
        row['items_recent'] = None
        row['unique_items'] = None
    row.update(freshness(row,now=now))
    atomic_json(path,data)
