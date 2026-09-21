import json
from pathlib import Path

from .models import RawItem
from .sources import load_sources, source_index
from .pipeline import build_signal
from .distribution import choose_distribution, UserPlan


ROOT = Path(__file__).resolve().parents[2]


def main():
    sources = source_index(load_sources(ROOT / "config" / "sources.json"))
    with open(ROOT / "data" / "sample_raw_items.json", "r", encoding="utf-8") as f:
        items = json.load(f)

    print("RADAR ENGINE V0\n")
    for item in items:
        raw = RawItem(**item)
        cfg = sources[raw.source_slug]
        signal = build_signal(raw, cfg)

        pro_distribution = choose_distribution(
            signal.radar_score,
            signal.confidence_score,
            UserPlan("pro"),
            signal.watch_tags,
            user_watch_tags={"isapres", "licitaciones", "suseso"},
        )
        free_distribution = choose_distribution(
            signal.radar_score,
            signal.confidence_score,
            UserPlan("free"),
            signal.watch_tags,
            user_watch_tags=set(),
        )

        print(f"[{signal.radar_score:>3}] {signal.title}")
        print(f"      category: {signal.category}")
        print(f"      confidence: {signal.confidence_score}")
        print(f"      FREE -> {free_distribution}")
        print(f"      PRO  -> {pro_distribution}\n")


if __name__ == "__main__":
    main()
