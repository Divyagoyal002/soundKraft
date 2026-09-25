"""Runtime configuration, read from environment variables."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DB_PATH = Path(os.environ.get("SOUNDKRAFT_DB", ROOT / "data" / "soundkraft.db"))
MODEL_PATH = Path(os.environ.get("SOUNDKRAFT_MODEL", ROOT / "models" / "calibration.joblib"))

# PIN protecting the caregiver/clinician dashboard. Change it before any real use.
DASHBOARD_PIN = os.environ.get("SOUNDKRAFT_DASHBOARD_PIN", "2468")
SECRET_KEY = os.environ.get("SOUNDKRAFT_SECRET_KEY", "dev-only-change-me")

# Battery order: memory, attention, spatial, executive function.
BATTERY = ["nback", "stroop", "corsi", "trails"]
ROUNDS_PER_GAME = {"nback": 3, "stroop": 3, "corsi": 3, "trails": 2}

DISCLAIMER = (
    "SoundKraft is a research prototype for screening and tracking only. "
    "It does not diagnose any condition. Any concern about memory or thinking "
    "should be discussed with a qualified health professional."
)
