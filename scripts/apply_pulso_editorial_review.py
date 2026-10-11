"""Apply a durable independent primary-body review to actual paid publications."""
import argparse
import hashlib
import json
from pathlib import Path

from radar_salud.pending_queue import atomic_json
from radar_salud.pulso_editorial_review import apply_review, validate_independent_binding


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--apply", action="store_true", help="Persist verified corrections; default validates only")
    args = parser.parse_args()
    root = args.root.resolve()
    review_path = args.review.resolve()
    if not review_path.is_relative_to(root / "data/audits"):
        parser.error("The review must be a durable repository audit")
    payload = review_path.read_bytes()
    audit = json.loads(payload)
    independent_path = root / (audit.get("independent_review") or {}).get("path", "")
    independent_path = independent_path.resolve()
    if not independent_path.is_relative_to(root / "data/audits") or not independent_path.is_file():
        parser.error("The independent reader evidence must be a durable repository audit")
    independent_bytes = independent_path.read_bytes()
    validate_independent_binding(audit, json.loads(independent_bytes),
                                 independent_sha256=hashlib.sha256(independent_bytes).hexdigest())
    history_path = root / "data/history/superintendencia_signals.json"
    queue_path = root / "data/state/pending_queue.json"
    history = json.loads(history_path.read_bytes())
    queue = json.loads(queue_path.read_bytes())
    wrapped = isinstance(history, dict)
    rows = history["signals"] if wrapped else history
    corrected, updated_queue, report = apply_review(rows, queue, audit,
                                                   audit_sha256=hashlib.sha256(payload).hexdigest(),
                                                   audit_path=str(review_path.relative_to(root)))
    if args.apply and report["applied_count"]:
        if wrapped:
            history["signals"] = corrected
        atomic_json(history_path, history if wrapped else corrected)
        atomic_json(queue_path, updated_queue)
    print(json.dumps(dict(report, persisted=args.apply), ensure_ascii=False))


if __name__ == "__main__":
    main()
