import json
from pathlib import Path
from typing import Dict, Any, List


def load_sources(path: str | Path) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def source_index(sources: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {s["slug"]: s for s in sources}
