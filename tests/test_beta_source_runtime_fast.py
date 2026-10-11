import json
import os
from pathlib import Path

import pytest

from radar_salud.beta_source_engine_fast import main

ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.integration
def test_beta_source_runtime_discovery_and_health():
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("live beta source integration runs in collector workflow")
    main()
    report=json.loads((ROOT/"data/state/beta_source_validation.json").read_text(encoding="utf-8"))
    required={"prestadores_data","red_davila","andes_salud","clinicas_achs_salud","achs_seguro_laboral","mutual_seguridad","ist","pulso_latercera"}
    assert required<=set(report["sources"])
    for slug in required:
        row=report["sources"][slug]
        if slug in {"clinicas_achs_salud","achs_seguro_laboral","mutual_seguridad","ist"}:
            if row["technical_status"]=="error":
                blocker=row.get("error_detail") or {}
                assert blocker.get("code") in {"external_waf_challenge","executor_proxy_denied"}, f"{slug}: {row}"
                assert blocker.get("url","").startswith("https://"), f"{slug}: blocker without exact URL"
                continue
            assert row["technical_status"]=="ok", f"{slug}: {row}"
            assert row.get("decisions"), f"{slug}: no original article examined"
            assert all(d.get("reason")!="missing_publication_date" for d in row["decisions"]), f"{slug}: unresolved dates"
            continue
        assert row["technical_status"]=="ok", f"{slug}: {row}"
        assert row["discovered"]>0, f"{slug}: no discoverable dated evidence"
    assert report["sources"]["prestadores_data"]["discovered"]>=4
