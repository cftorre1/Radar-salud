from pathlib import Path

from radar_salud.global_intelligence import export


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    export(root / "data/global/themes.json", root / "web/data/global_themes.json")
