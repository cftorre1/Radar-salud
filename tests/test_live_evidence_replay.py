"""Controlled replay of the production discovery/queue/history/feed/report path.

These fixtures prove the mechanics; they are never presented as observed LIVE data.
"""
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from radar_salud import engine_cli, paths
from radar_salud.models import RawItem
from radar_salud.history import load_history
from radar_salud.pending_queue import PendingQueue


def _module(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_deterministic_live_replay_through_feed_and_coverage(tmp_path,monkeypatch):
    now=datetime.now(timezone.utc)
    state=tmp_path/"data/state";state.mkdir(parents=True)
    (state/"discovery_watermarks.json").write_text(json.dumps({"minsal":(now-timedelta(days=1)).isoformat()}))
    items=[RawItem("minsal",title,f"https://example.org/{suffix}","Ministerio de Salud","official",event)
        for title,suffix,event in (("Acto reciente de prueba","live",now.date().isoformat()),
                                   ("Acto histórico de prueba","backfill",(now-timedelta(days=12)).date().isoformat()),
                                   ("Acto sin fecha de prueba","undated",None))]
    class Scout:
        def __init__(self,*args,**kwargs):pass
        def discover(self,*args,**kwargs):return []
    class Minsal(Scout):
        def discover(self):return items
    for name in ("SuperintendenciaStatsScout","SuperintendenciaNormativaScout","SuperintendenciaFiscalizacionScout",
                 "SusesoNormativeScout","DfHealthScout","FonasaNewsScout","IspAnamedAlertScout","DiarioOficialHealthScout"):
        monkeypatch.setattr(engine_cli,name,Scout)
    monkeypatch.setattr(engine_cli,"MinsalNewsScout",Minsal)
    monkeypatch.setattr(engine_cli,"load_sources",lambda path:[])
    monkeypatch.setattr(engine_cli,"source_index",lambda sources:{name:object() for name in (
        "superintendencia_salud","superintendencia_normativa","superintendencia_fiscalizacion",
        "minsal","fonasa","isp_anamed","suseso","diario_financiero","diario_oficial")})
    monkeypatch.setattr(paths,"project_root",lambda:tmp_path)
    monkeypatch.setattr(engine_cli,"seed_from_history",lambda root:None)
    monkeypatch.setattr(engine_cli,"has_capacity",lambda kind:True)
    monkeypatch.setattr(engine_cli,"health_record",lambda *args,**kwargs:None)
    def process(raw,cfg):
        if not raw.event_date:return None
        return {"title":raw.title,"source_name":raw.source_name,"source_url":raw.url,"source_type":raw.source_type,
                "event_date":raw.event_date,"what_happened":f"El Ministerio de Salud informó {raw.title.lower()} con fecha comprobable.",
                "why_it_matters":"Permite verificar el efecto de una publicación fechada sin atribuirle efectos que la fuente no establece.",
                "key_points":["La publicación corresponde a un acto identificado y verificable."],
                "signal_types":["Noticias"],"scopes":["Sistema de salud"],"radar_score":78,"confidence_score":95}
    monkeypatch.setattr(engine_cli,"process_minsal",process)
    monkeypatch.setattr(sys,"argv",["engine_cli","--limit","3"])
    engine_cli.main()
    queue=PendingQueue(state/"pending_queue.json")
    assert {v["raw"]["title"]:(v["lane"],v["status"]) for v in queue.items.values()}=={
        "Acto reciente de prueba":("LIVE","published"),
        "Acto histórico de prueba":("BACKFILL","published"),
        "Acto sin fecha de prueba":("BACKFILL","rejected")}
    history=load_history(tmp_path/"data/history/superintendencia_signals.json")
    assert len(history)==2
    curator=_module("replay_snapshot",Path(__file__).resolve().parents[1]/"scripts/export_web_snapshot.py")
    signals=curator.curate(history,resolve_external=False)
    assert {s["ingestion_mode"] for s in signals}=={"LIVE","BACKFILL"}
    web=tmp_path/"web/data";web.mkdir(parents=True)
    (web/"radar_today.json").write_text(json.dumps({"generated_at":now.isoformat(),"signals":signals}))
    report=_module("replay_report",Path(__file__).resolve().parents[1]/"scripts/product_report.py").build(tmp_path,web)
    assert report["coverage_live"]=={"detected":1,"evaluated":1,"selected":1}
    assert report["queue"]["live_pending"]==report["queue"]["backfill_pending"]==0
    assert report["queue"]["rejected"]==1
    engine_cli.main()  # Same discovery on the next pass is idempotent.
    assert all(v["new"]==0 for v in json.loads((state/"discovery_run.json").read_text())["sources"].values())
    assert len(PendingQueue(state/"pending_queue.json").items)==3
