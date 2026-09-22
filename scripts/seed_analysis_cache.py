from pathlib import Path
from radar_salud.analysis_cache import seed_from_history
root=Path(__file__).resolve().parents[1]
n=seed_from_history(root)
print(f"Seeded {n} normative analyses from existing history.")
