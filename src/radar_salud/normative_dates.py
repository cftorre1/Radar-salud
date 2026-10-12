"""Separate legal time dimensions; sanctions never inherit a crawling/listing date."""
from datetime import date
import re
def _legal_dates(record):
    primary=record.get('primary_document_review') or {}
    issued=record.get('issued_on') or record.get('emission_date')
    try:
        parsed=date.fromisoformat(str(issued));valid_date=parsed.isoformat()==issued and parsed<=date.today()
    except (ValueError,TypeError):valid_date=False
    verified=(valid_date and record.get('event_date_basis')=='verified_primary_emission' and bool(re.fullmatch(r'[a-f0-9]{64}',str(primary.get('primary_document_sha256') or '')))
              and primary.get('emission_date')==issued)
    sanction=record.get('event_type','').startswith('SANCTION') or record.get('fiscalization_kind')=='sanction'
    return {'issued_on':issued,'published_on':record.get('published_on') or record.get('publication_date'),
            'inspection_date':record.get('inspection_date'),'inspection_period':record.get('inspection_period'),
            'fact_period':record.get('fact_period'),'effective_from':record.get('effective_from'),
            'effective_until':record.get('effective_until'),'detected_at':record.get('detected_at'),
            'event_date':issued if sanction and verified else None if sanction else record.get('event_date'),
            'event_date_basis':'verified_primary_emission' if sanction and verified else 'unverified_emission' if sanction else record.get('event_date_basis'),
            'hold_reason':'HOLD_DATE' if sanction and not verified else None}

def legal_dates(record):
    try:return _legal_dates(record)
    except (TypeError,ValueError,AttributeError,KeyError):
        return {'issued_on':None,'published_on':None,'inspection_date':None,'inspection_period':None,'fact_period':None,
                'effective_from':None,'effective_until':None,'detected_at':None,'event_date':None,
                'event_date_basis':'unverified_emission','hold_reason':'HOLD_DATE'}
