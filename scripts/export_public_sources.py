from pathlib import Path
import json
from radar_salud.public_source_catalog import build_catalog

def export_public_sources(source_path=Path('data/source_health.json'),output=Path('web/data/public_sources.json')):
    data=json.loads(source_path.read_text(encoding='utf-8'))
    payload=build_catalog(data.get('sources') or {})
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return payload

if __name__=='__main__':export_public_sources()
