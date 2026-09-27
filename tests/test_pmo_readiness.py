import json
from pathlib import Path

from radar_salud.pmo import full_qa,project


def test_every_declared_validated_requirement_has_matching_successful_qa():
    baseline=json.loads(Path('config/pmo_baseline.json').read_text())
    for block in baseline['blocks']:
        for requirement in block.get('requirements',[]):
            if requirement['status']!='Validado':
                continue
            proof=baseline['evidence_catalog'].get(requirement.get('evidence'),{})
            assert full_qa(proof), (block['id'],requirement['label'],'missing full QA')
            assert requirement['label'] in proof.get('validated_requirements',[]), (block['id'],requirement['label'],'missing explicit match')


def test_validated_requires_full_evidence_for_exact_candidate(tmp_path):
    baseline = json.loads(Path("config/pmo_baseline.json").read_text())
    block = baseline["blocks"][0]
    block["status"] = "Validado"
    block["evidence"] = ["staging_qa"]
    block["missing"] = []
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(baseline))
    old = project(path, "a" * 40)
    assert old["blocks"][0]["status"] == "Implementado"
    assert not old["readiness"]["ready"]
    current = project(path, baseline["reference_staging_sha"])
    assert current["blocks"][0]["status"] == "Implementado"
    baseline["evidence_catalog"]["staging_qa"]["validated_blocks"] = ["pmo"]
    path.write_text(json.dumps(baseline))
    current = project(path, baseline["reference_staging_sha"])
    assert current["blocks"][0]["status"] == "Validado"
    baseline["evidence_catalog"]["staging_qa"]["checks"].remove("reviewer")
    path.write_text(json.dumps(baseline))
    assert project(path, baseline["reference_staging_sha"])["blocks"][0]["status"] == "Implementado"


def test_source_baseline_has_no_unproven_validation():
    report = project(Path("config/pmo_baseline.json"), "b" * 40)
    assert report["readiness"]["validated"] == 0
    assert report["open_failures"]
    assert report["human_blockers"]
    assert any("Excel" in x for x in report["missing_for_beta"])
    assert 0 < report["readiness"]["validated_requirements"] < report["readiness"]["total_requirements"]
    assert report["readiness"]["requirement_percent"] == round(100*report["readiness"]["validated_requirements"]/report["readiness"]["total_requirements"])
    assert report["external_observations"][0]["id"]=="first_genuine_live"
    assert all("publicación genuina LIVE" not in x for x in report["missing_for_beta"])

def test_subrequirement_without_successful_full_evidence_never_counts(tmp_path):
    baseline=json.loads(Path("config/pmo_baseline.json").read_text())
    first=baseline["blocks"][0]["requirements"][0]
    first.update(status="Validado",evidence="live_discovery")
    path=tmp_path/"baseline.json";path.write_text(json.dumps(baseline))
    result=project(path,baseline["reference_staging_sha"])
    assert result["blocks"][0]["requirements"][0]["status"]=="Implementado"
    assert result["readiness"]["validated_requirements"]==project(Path("config/pmo_baseline.json"),baseline["reference_staging_sha"])["readiness"]["validated_requirements"]-1


def test_requirement_rejects_missing_sha_foreign_url_and_unlinked_proof(tmp_path):
    baseline=json.loads(Path('config/pmo_baseline.json').read_text())
    path=tmp_path/'baseline.json'
    for mutation in ('sha', 'url', 'validated_requirements'):
        changed=json.loads(json.dumps(baseline))
        evidence=changed['evidence_catalog']['staging_qa']
        if mutation=='sha': evidence.pop('sha')
        elif mutation=='url': evidence['url']='https://example.org/not-evidence'
        else: evidence['validated_requirements']=[]
        path.write_text(json.dumps(changed))
        result=project(path,changed['reference_staging_sha'])
        assert result['blocks'][0]['requirements'][0]['status']=='Implementado'
        assert result['readiness']['validated_requirements'] < project(Path('config/pmo_baseline.json'), changed['reference_staging_sha'])['readiness']['validated_requirements']


def test_closed_beta_readiness_is_independent_from_commercial_readiness(tmp_path):
    baseline=json.loads(Path("config/pmo_baseline.json").read_text())
    baseline["closed_beta"]={
        "status":"ready",
        "scope":"invite-only read-only beta",
        "audience":"invited users",
        "evidence":"closed_beta_test",
        "non_blocking":["email","analytics"],
        "remaining_human_gates":["Direction release approval"],
    }
    baseline["evidence_catalog"]["closed_beta_test"]={
        "kind":"github_actions",
        "result":"success",
        "checks":["tests","desktop","mobile","reviewer","preview"],
        "sha":"c"*40,
        "url":"https://github.com/cftorre1/Radar-salud/actions/runs/123456789",
        "validated_blocks":[],
        "validated_requirements":[],
    }
    path=tmp_path/"baseline.json";path.write_text(json.dumps(baseline))
    report=project(path,"d"*40)
    assert report["closed_beta"]["ready"] is True
    assert report["closed_beta"]["label"]=="Lista para Beta cerrada"
    assert report["readiness"]["ready"] is False
    assert report["closed_beta"]["non_blocking"]==["email","analytics"]


def test_closed_beta_never_claims_ready_without_full_qa(tmp_path):
    baseline=json.loads(Path("config/pmo_baseline.json").read_text())
    baseline["closed_beta"]={"status":"ready","scope":"beta","evidence":"bad","non_blocking":[],"remaining_human_gates":[]}
    baseline["evidence_catalog"]["bad"]={"kind":"github_actions","result":"success","checks":["tests"],"sha":"c"*40,"url":"https://github.com/cftorre1/Radar-salud/actions/runs/123456789"}
    path=tmp_path/"baseline.json";path.write_text(json.dumps(baseline))
    assert project(path,"d"*40)["closed_beta"]["ready"] is False
