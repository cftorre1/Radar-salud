"""Poder Judicial source candidates (Dirección 29-oct-2026): evaluated, none enabled."""
import json
from pathlib import Path


def test_judicial_sources_registry_is_conservative():
    data = json.loads(Path("config/judicial_sources.json").read_text(encoding="utf-8"))
    required = {"id", "name", "status", "reason", "evidence_urls", "verified_at", "next_step", "reevaluate_after"}
    ids = [s["id"] for s in data["sources"]]
    assert len(ids) == len(set(ids))
    for s in data["sources"]:
        assert required <= set(s), s["id"]
        assert s["status"] in data["statuses"] and s["status"] != "enabled"
        assert s["live_search"] is False and s["scout_enabled"] is False
        assert all(u.startswith("https://") for u in s["evidence_urls"])
    assert {s["id"]: s["status"] for s in data["sources"]}["pjud_oficina_judicial_virtual"] == "rejected"
