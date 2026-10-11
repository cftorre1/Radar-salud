"""Apply a durable independent primary-body review to actual paid publications."""
import argparse
import hashlib
import json
from pathlib import Path

from radar_salud.pending_queue import atomic_json
from radar_salud.pulso_editorial_review import apply_review


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
    history_path = root / "data/history/superintendencia_signals.json"
    queue_path = root / "data/state/pending_queue.json"
    history = json.loads(history_path.read_bytes())
    queue = json.loads(queue_path.read_bytes())
    wrapped = isinstance(history, dict)
    rows = history["signals"] if wrapped else history
    corrected, updated_queue, report = apply_review(rows, queue, json.loads(payload),
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
