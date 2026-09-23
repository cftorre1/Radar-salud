"""One repository/data root, also usable in isolated tests."""
import os
from pathlib import Path

def project_root():
    return Path(os.environ.get("RADAR_ROOT", Path(__file__).resolve().parents[2]))
