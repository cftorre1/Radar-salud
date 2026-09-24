#!/usr/bin/env python3
"""Local operations CLI for reviewing anonymous source suggestions."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from radar_salud.source_suggestions import SqliteSuggestionStore


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=os.environ.get("SOURCE_SUGGESTIONS_DB_PATH", "data/source_suggestions.sqlite3"))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    status = sub.add_parser("status")
    status.add_argument("id")
    status.add_argument("value", choices=["received", "reviewing", "accepted", "rejected"])
    args = parser.parse_args()
    store = SqliteSuggestionStore(Path(args.db))
    if args.command == "list":
        print(json.dumps(store.list(), ensure_ascii=False, indent=2))
        return
    if not store.set_status(args.id, args.value):
        raise SystemExit("Suggestion not found")


if __name__ == "__main__":
    main()
