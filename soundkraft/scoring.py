"""Composite Cognitive Performance Index (0-100, higher = better performance).

Before a calibration study exists, the index is a transparent, rule-based
combination of level reached, accuracy and speed in each domain. After the
validation study, `calibration.py` trains a model whose exploratory
reference-scale estimate is reported alongside (never instead of) this index.

This index is a tracking indicator, not a diagnostic score.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from . import config
from .games import CORSI_LEVELS, DOMAINS, MAX_LEVEL


def _unit(value, best, worst) -> float | None:
    """Map `value` linearly so best -> 1 and worst -> 0, clamped."""
    if value is None:
        return None
    x = (value - worst) / (best - worst)
    return max(0.0, min(1.0, x))


def _weighted(parts: list[tuple[float | None, float]]) -> float | None:
    parts = [(v, w) for v, w in parts if v is not None]
    if not parts:
        return None
    total = sum(w for _, w in parts)
    return round(100 * sum(v * w for v, w in parts) / total, 1)


def domain_scores(f: dict) -> dict[str, float]:
    scores: dict[str, float | None] = {}
    if "nback_accuracy" in f:
        scores["memory"] = _weighted([
            (_unit(f["nback_mean_level"], MAX_LEVEL["nback"], 1), 0.45),
            (_unit(f["nback_accuracy"], 1.0, 0.5), 0.35),
            (_unit(f.get("nback_median_rt"), 700, 3000), 0.20),
        ])
    if "stroop_accuracy" in f:
        scores["attention"] = _weighted([
            (_unit(f["stroop_mean_level"], MAX_LEVEL["stroop"], 1), 0.35),
            (_unit(f["stroop_accuracy"], 1.0, 0.5), 0.35),
            (_unit(f.get("stroop_median_rt"), 600, 2800), 0.30),
        ])
    if "corsi_accuracy" in f:
        scores["spatial"] = _weighted([
            (_unit(f.get("corsi_span"), CORSI_LEVELS[-1], CORSI_LEVELS[0] - 1), 0.6),
            (_unit(f["corsi_accuracy"], 1.0, 0.0), 0.2),
            (_unit(f.get("corsi_first_touch_ms"), 600, 4000), 0.2),
        ])
    if "trails_accuracy" in f:
        scores["executive"] = _weighted([
            (_unit(f["trails_mean_level"], MAX_LEVEL["trails"], 1), 0.4),
            (_unit(f["trails_accuracy"], 1.0, 0.5), 0.3),
            (_unit(f.get("trails_ms_per_step"), 700, 5000), 0.3),
        ])
    return {k: v for k, v in scores.items() if v is not None}


def composite(f: dict) -> float | None:
    d = domain_scores(f)
    return round(sum(d.values()) / len(d), 1) if d else None


DOMAIN_LABELS = {
    "memory": "Memory",
    "attention": "Attention",
    "spatial": "Spatial",
    "executive": "Planning & switching",
}
assert set(DOMAIN_LABELS) == set(DOMAINS.values())


# ---------------------------------------------------------------- calibrated model (optional)

@lru_cache(maxsize=1)
def _load_model(path: str, mtime: float):
    import joblib
    return joblib.load(path)


def load_model(path: Path | None = None):
    path = Path(path or config.MODEL_PATH)
    if not path.exists():
        return None
    return _load_model(str(path), path.stat().st_mtime)


def model_estimate(f: dict, path: Path | None = None) -> dict | None:
    """Exploratory reference-scale estimate from the calibrated model, if one is trained."""
    bundle = load_model(path)
    if bundle is None:
        return None
    import pandas as pd

    X = pd.DataFrame([{k: f.get(k) for k in bundle["features"]}], dtype=float)
    est = float(bundle["regressor"].predict(X)[0])
    est = max(0.0, min(bundle["max_score"], est))
    out = {"instrument": bundle["instrument"], "estimate": round(est, 1), "max_score": bundle["max_score"],
           "n_train": bundle["n"]}
    if bundle.get("classifier") is not None:
        out["below_cutoff_probability"] = round(float(bundle["classifier"].predict_proba(X)[0, 1]), 3)
        out["cutoff"] = bundle["cutoff"]
    return out
