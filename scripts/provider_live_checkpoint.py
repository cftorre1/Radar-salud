"""Read-only remote probe and bounded candidate evaluation for the provider PR.

All mutations stay inside the checkout and its uploaded checkpoint artifact.
This script never promotes outputs or writes to staging/main.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from radar_salud.pending_queue import atomic_json
from radar_salud.source_scouts import CorporateNewsroomScout, ClinicasChileScout
from radar_salud.beta_sources import CuratedBetaSourceScout
from reconcile_providers import run


def main():
    root=Path('.')
    probes={}
    for slug in ('redsalud','bupa_chile','indisa','red_davila','andes_salud','clinicas_chile','pfizer_chile','clinicas_achs_salud'):
        scout=ClinicasChileScout() if slug=='clinicas_chile' else CuratedBetaSourceScout(slug) if slug in CuratedBetaSourceScout.SOURCES else CorporateNewsroomScout(slug)
        try:
            raws=scout.discover()
            errors=getattr(scout,'discovery_errors',[])
            dates=[r.event_date for r in raws if r.event_date]
            probes[slug]={'discovered':len(raws),'dated':len(dates),'latest_original_at':max(dates) if dates else None,
                          'technical_status':'partial' if errors else 'ok','errors':errors,'evaluation_performed':False}
        except Exception as exc:
            probes[slug]={'discovered':0,'technical_status':'error','error_type':type(exc).__name__,'error':str(exc),'evaluation_performed':False}
    run(root,apply=True,live=bool(os.getenv('OPENAI_API_KEY')),limit=12)
    path=root/'data/audits/provider_live_checkpoint_2026_10_11.json'
    checkpoint=json.loads(path.read_text()) if path.exists() else {'attempted':0,'results':[],'assessment_blocker':'OPENAI_API_KEY_unavailable'}
    checkpoint.update(at=datetime.now(timezone.utc).isoformat(),commit=os.getenv('GITHUB_SHA'),original_discovery=probes,
                      runtime='GitHub Actions isolated PR checkout',promotion='none')
    checkpoint['accepted']=False  # Complete 90-day inventory and review remain required.
    atomic_json(path,checkpoint)
    print(json.dumps({'attempted':checkpoint['attempted'],'discovery':{k:v['technical_status'] for k,v in probes.items()},'promotion':'none'}))


if __name__=='__main__':main()
