from pathlib import Path
from src.radar_salud.history import merge_history, save_history, load_history


def test_merge_history_replaces_same_source_url():
    old=[{'source_url':'https://x/a','title':'old','radar_score':50}]
    new=[{'source_url':'https://x/a','title':'new','radar_score':70},{'source_url':'https://x/b','title':'b'}]
    out=merge_history(old,new)
    assert len(out)==2
    by={x['source_url']:x for x in out}
    assert by['https://x/a']['title']=='new'


def test_history_roundtrip(tmp_path: Path):
    p=tmp_path/'history.json'
    save_history(p,[{'source_url':'https://x/a','title':'a'}])
    assert load_history(p)[0]['title']=='a'
