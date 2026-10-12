"""Retain an already captured original from the second zero-call observation."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
from scripts.qa_pulso_recovery import PrimaryDates

SHA = '54dab6ced65f528cca8bcb1c7168d6f92d8525fa33debc703f74bea414e45e77'
GZIP_SHA = '2aa72ec80ad2385d7a1ab917a599b38ef31004146f07933c377987f651586078'
BODY_SHA = 'd5314e898c41422ecea913473d3cac6f7514a20705d10a684a7c91bc38862cd3'
URL = 'https://www.latercera.com/culto/noticia/renocido-actor-gabriel-prieto-fallece-a-los-65-anos/'

def verify(data):
    assert hashlib.sha256(data).hexdigest() == GZIP_SHA, 'original gzip differs'
    raw = gzip.decompress(data)
    assert hashlib.sha256(raw).hexdigest() == SHA, 'original HTML differs'
    parser = PrimaryDates();parser.feed(raw.decode())
    assert parser.canonical == URL and parser.days_for(URL) == {'2026-10-11'}
    title, body = parser.primary_text(URL)
    assert len(body) == 3449 and hashlib.sha256(body.encode()).hexdigest() == BODY_SHA
    return dict(original_run_id=38194404484,original_producer='58d0f929d0d98de798f9460600ffe71ad07604bd',url=URL,
        original_HTML_sha256=SHA,original_gzip_sha256=GZIP_SHA,body_sha256=BODY_SHA,body_characters=3449,
        original_publication_date='2026-10-11',title=title,body=body,HTTP_calls=0,AI_calls=0,
        reason='Publisher HTML transport changed; exact paid body and original byline did not.')

def main():
    p=argparse.ArgumentParser();p.add_argument('--artifact-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    matches=list(args.artifact_root.rglob(SHA+'.gz'))
    assert len(matches)==1, 'one exact original gzip required'
    data=matches[0].read_bytes();result=verify(data)
    args.output.mkdir(parents=True,exist_ok=True)
    target=args.output/(SHA+'.html.gz')
    assert not target.exists() or target.read_bytes()==data
    target.write_bytes(data);result['retained_gzip_file']=str(target)
    (args.output/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='body'},ensure_ascii=False))

if __name__=='__main__':main()
