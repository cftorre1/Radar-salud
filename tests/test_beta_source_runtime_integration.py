import json
import os
from pathlib import Path

import pytest

from radar_salud.beta_source_engine import main

ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.integration
def test_beta_source_runtime_discovery_and_health():
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("live beta source integration runs in the collector workflow with analysis credentials")
    main()
    report=json.loads((ROOT/"data/state/beta_source_validation.json").read_text(encoding="utf-8"))
    required={"prestadores_data","red_davila","andes_salud","clinicas_achs_salud","achs_seguro_laboral","mutual_seguridad","ist","pulso_latercera"}
    assert required<=set(report["sources"])
    for slug in required:
        row=report["sources"][slug]
        assert row["technical_status"]=="ok", f"{slug}: {row}"
        assert row["discovered"]>0, f"{slug}: no discoverable dated evidence"
    assert report["sources"]["prestadores_data"]["discovered"]>=4
