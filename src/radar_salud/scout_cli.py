from pathlib import Path

from .scouts import SeenStore, SuperintendenciaStatsScout, save_raw_items


def main():
    root = Path(__file__).resolve().parents[2]
    state = root / "data" / "state" / "superintendencia_seen.json"
    out = root / "data" / "inbox" / "superintendencia_new.json"

    scout = SuperintendenciaStatsScout()
    store = SeenStore(state)
    items = scout.discover_new(store)
    save_raw_items(items, out)

    print("RADAR SCOUT #1 — Superintendencia de Salud")
    print(f"New items: {len(items)}")
    print(f"Saved to: {out}")
    for item in items[:10]:
        print(f"- {item.title}\n  {item.url}")


if __name__ == "__main__":
    main()
