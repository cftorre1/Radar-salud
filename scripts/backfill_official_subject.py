"""One-off, deterministic: copy the regulator's verbatim listing subject (already
captured in the pending queue) into durable history as ``official_subject``.
No network, no AI. Only fills missing values; never rewrites existing fields."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "data/history/superintendencia_signals.json"
QUEUE = ROOT / "data/state/pending_queue.json"
SLUGS = {"superintendencia_normativa"}


def main() -> None:
    queue = json.loads(QUEUE.read_text(encoding="utf-8"))
    items = queue.get("items", queue)
    subjects = {}
    for item in (items.values() if isinstance(items, dict) else items):
        raw = item.get("raw") or {}
        text = str(raw.get("raw_text") or "").strip()
        if raw.get("source_slug") in SLUGS and text and text != str(raw.get("title") or "").strip() and len(text) <= 600:
            subjects[raw.get("url")] = text
    payload = json.loads(HISTORY.read_text(encoding="utf-8"))
    filled = 0
    for signal in payload["signals"]:
        subject = subjects.get(signal.get("source_url"))
        if subject and not signal.get("official_subject"):
            signal["official_subject"] = subject
            filled += 1
    HISTORY.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"official_subject filled={filled}")


if __name__ == "__main__":
    main()
