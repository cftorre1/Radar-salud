"""Export a concise, publication-ready web snapshot from Signal-like dicts.

The public homepage is intentionally NOT a raw dump of every item collected.
It groups repetitive statistical releases, hides stale/low-value items and
keeps deeper history available to the data layer rather than the front page.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timezone, date
from pathlib import Path


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).date()
    except ValueError:
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None


def _latest_event_date(signals):
    dates = [_parse_date(s.get('event_date')) for s in signals]
    dates = [d for d in dates if d]
    return max(dates) if dates else datetime.now().date()


def _is_technical_garbage(s):
    text = ' '.join(str(s.get(k, '') or '') for k in ('title','what_happened','why_it_matters')).lower()
    return any(x in text for x in ('@context','@graph','schema.org','"@type"','"ispartof"'))


def _is_monthly_isapre_stats(s):
    title = (s.get('title') or '').lower()
    return (
        s.get('source_name') == 'Superintendencia de Salud'
        and ('mensual' in title or 'cartera' in title or 'movilidad' in title or 'suscripciones' in title)
        and 'isapre' in title
    )


def _normalize_period(value):
    if not value:
        return None
    value=' '.join(str(value).strip(' .').lower().split())
    value=re.sub(r'\s+de\s+(20\d{2})$', r' \1', value)
    return value


def _updated_period(s):
    for fact in s.get('key_facts', []) or []:
        m = re.search(r'actualizada? a\s+(.+?)[\.]?$', fact, re.I)
        if m:
            return _normalize_period(m.group(1))
    title = s.get('title','')
    m = re.search(r'[-–]\s*(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)(?:\s+de)?\s+20\d{2}', title, re.I)
    return _normalize_period(m.group(0).lstrip('-– ').strip()) if m else None


def _group_monthly_package(items):
    if len(items) < 2:
        return items
    # Use the freshest subgroup when several months were discovered during the first backfill run.
    periods = defaultdict(list)
    for s in items:
        periods[_updated_period(s) or 'actual'].append(s)
    best_period, best = max(periods.items(), key=lambda kv: (len(kv[1]), max((_parse_date(x.get('event_date')) or date.min) for x in kv[1])))
    if len(best) < 2:
        return [max(items, key=lambda x: _parse_date(x.get('event_date')) or date.min)]

    kinds=[]
    for s in best:
        t=(s.get('title') or '').lower()
        if 'movilidad' in t: kinds.append('movilidad de cotizantes')
        elif 'suscripciones' in t or 'desahucios' in t: kinds.append('suscripciones y desahucios')
        elif 'regional' in t: kinds.append('cartera regional')
        elif 'cartera' in t: kinds.append('cartera total')
    kinds=list(dict.fromkeys(kinds))
    src_urls=[s.get('source_url') for s in best if s.get('source_url')]
    base=max(best, key=lambda x: x.get('radar_score',0))
    grouped=dict(base)
    grouped.update({
        'title': f'Actualización mensual del sistema Isapre — {best_period}',
        'what_happened': 'La Superintendencia actualizó en un mismo ciclo ' + ', '.join(kinds) + '.',
        'why_it_matters': 'Leído en conjunto, este paquete permite detectar cambios de tamaño de cartera, entradas y salidas, movilidad entre competidores y diferencias regionales sin revisar varias publicaciones por separado.',
        'source_url': src_urls[0] if src_urls else base.get('source_url'),
        'additional_sources': src_urls[1:],
        'radar_score': max(s.get('radar_score',0) for s in best),
        'confidence_score': min(s.get('confidence_score',100) for s in best),
        'grouped_count': len(best),
        'grouped_titles': [s.get('title') for s in best],
    })
    return [grouped]


def curate(signals, max_local=6, max_world=2):
    clean=[s for s in signals if not _is_technical_garbage(s) and s.get('validation_status') != 'human_review_required']
    latest=_latest_event_date(clean)
    # The homepage is a current briefing, not a historical archive. On the first
    # backfill run this suppresses months-old statistical releases.
    current=[s for s in clean if not _parse_date(s.get('event_date')) or (latest - _parse_date(s.get('event_date'))).days <= 21]
    if not current:
        current=clean

    monthly=[s for s in current if _is_monthly_isapre_stats(s)]
    rest=[s for s in current if s not in monthly]
    curated=_group_monthly_package(monthly)+rest
    curated.sort(key=lambda s:(s.get('personal_score', s.get('radar_score',0)), s.get('confidence_score',0)), reverse=True)
    local=[s for s in curated if s.get('category')!='Radar Mundo'][:max_local]
    world=[s for s in curated if s.get('category')=='Radar Mundo'][:max_world]
    return local+world


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--input', required=True)
    ap.add_argument('--output', default='web/data/radar_today.json')
    ap.add_argument('--profile', default='Ejecutivo Isapre')
    ap.add_argument('--date', default=None)
    args=ap.parse_args()
    raw=json.loads(Path(args.input).read_text(encoding='utf-8'))
    signals=raw.get('signals', raw) if isinstance(raw, dict) else raw
    signals=curate(signals)
    payload={
      'date': args.date or datetime.now().date().isoformat(),
      'profile': args.profile,
      'generated_at': datetime.now(timezone.utc).isoformat(),
      'signals': signals,
    }
    out=Path(args.output); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    print(out)
if __name__=='__main__': main()
