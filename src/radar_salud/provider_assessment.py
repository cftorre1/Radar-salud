"""Durable editorial diagnostics under unchanged provider publication gates."""
from datetime import datetime, timezone


def assessed(raw, ai, threshold):
    score=int(ai.get('relevance_score',0))
    what=(ai.get('what_happened') or '').strip()
    why=(ai.get('why_it_matters') or '').strip()
    failures=[]
    if score<threshold:failures.append('relevance_below_source_gate')
    if len(what)<45:failures.append('insufficient_verifiable_what')
    if len(why)<35:failures.append('insufficient_specific_why')
    raw.metadata['editorial_assessment']={
        'assessed_at':datetime.now(timezone.utc).isoformat(),
        'relevance_score':score,'minimum_relevance':threshold,
        'editorial_reason':ai.get('reason') or 'model_reason_not_returned',
        'what_characters':len(what),'why_characters':len(why),
        'gate_failures':failures,'outcome':'rejected' if failures else 'passed',
        'publication_date':raw.event_date,
        'publication_date_source':raw.metadata.get('publication_date_source'),
    }
    return not failures


def prefilter_rejected(raw, reason):
    raw.metadata['editorial_assessment']={
        'assessed_at':datetime.now(timezone.utc).isoformat(),'outcome':'rejected',
        'editorial_reason':reason,'gate_failures':[reason],'paid_analysis':False,
    }


def rejection_reason(raw):
    assessment=raw.metadata.get('editorial_assessment') or {}
    failures=assessment.get('gate_failures') or []
    return ';'.join(failures) or 'processor_rejected_without_editorial_diagnostics'
