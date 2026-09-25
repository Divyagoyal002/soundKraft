"""Behavioural feature extraction: raw trial logs -> one feature vector per session.

Feature choice follows the literature in the requirement document: level reached,
accuracy, response time, response-time variability, tap time and swipe time
(the N-back/MMSE study found swipe time the single strongest correlate), plus
game-specific markers such as Stroop interference and Corsi span.
"""

from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np

from .games import CORSI_LEVELS, GAMES


def _med(values) -> float | None:
    vals = [v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    return round(float(np.median(vals)), 2) if vals else None


def _cv(values) -> float | None:
    vals = np.array([v for v in values if v is not None], dtype=float)
    if len(vals) < 3 or vals.mean() == 0:
        return None
    return round(float(vals.std(ddof=1) / vals.mean()), 4)


def _dprime(hits: int, n_signal: int, fas: int, n_noise: int) -> float | None:
    if n_signal == 0 or n_noise == 0:
        return None
    # Log-linear correction keeps rates away from 0 and 1.
    h = (hits + 0.5) / (n_signal + 1)
    f = (fas + 0.5) / (n_noise + 1)
    z = NormalDist().inv_cdf
    return round(z(h) - z(f), 4)


def extract(trials: list[dict]) -> dict:
    """`trials` are flat rows (see db.session_trials) carrying game, level and stimulus."""
    feats: dict = {}
    for game in GAMES:
        rows = [t for t in trials if t["game"] == game]
        if not rows:
            continue
        scored = [t for t in rows if t["stimulus"].get("scored", True)]
        correct = [t for t in scored if t["correct"]]
        rts = [t["rt_ms"] for t in correct if t["rt_ms"] is not None and not t["timed_out"]]
        levels = [t["level"] for t in rows]
        n = len(scored) or 1
        feats[f"{game}_accuracy"] = round(len(correct) / n, 4)
        feats[f"{game}_median_rt"] = _med(rts)
        feats[f"{game}_rt_cv"] = _cv(rts)
        feats[f"{game}_max_level"] = max(levels)
        feats[f"{game}_mean_level"] = round(float(np.mean(levels)), 3)
        feats[f"{game}_timeout_rate"] = round(sum(1 for t in scored if t["timed_out"]) / n, 4)
        feats[f"{game}_first_touch_ms"] = _med(t["first_touch_ms"] for t in scored)
        feats.update(_game_specific(game, scored))

    all_rows = [t for t in trials if t["stimulus"].get("scored", True)]
    if all_rows:
        taps = [t["tap_duration_ms"] for t in all_rows]
        swipes = [t["swipe_ms"] for t in all_rows if t["swipe_ms"]]
        off = sum(t["off_target_touches"] or 0 for t in all_rows)
        feats["tap_duration_ms"] = _med(taps)
        feats["swipe_ms"] = _med(swipes)
        feats["off_target_rate"] = round(off / (off + len(all_rows)), 4)
        feats["overall_accuracy"] = round(sum(1 for t in all_rows if t["correct"]) / len(all_rows), 4)
        feats["n_trials"] = len(all_rows)
    return feats


def _game_specific(game: str, scored: list[dict]) -> dict:
    out: dict = {}
    if game == "nback":
        signal = [t for t in scored if t["stimulus"].get("match")]
        noise = [t for t in scored if not t["stimulus"].get("match")]
        hits = sum(1 for t in signal if t["response"] == "same")
        fas = sum(1 for t in noise if t["response"] == "same")
        out["nback_hit_rate"] = round(hits / len(signal), 4) if signal else None
        out["nback_false_alarm_rate"] = round(fas / len(noise), 4) if noise else None
        out["nback_dprime"] = _dprime(hits, len(signal), fas, len(noise))
    elif game == "stroop":
        def rt(cong: bool):
            return _med(t["rt_ms"] for t in scored
                        if t["correct"] and not t["timed_out"] and t["stimulus"].get("congruent") == cong)
        inc, con = rt(False), rt(True)
        out["stroop_interference_ms"] = round(inc - con, 2) if inc is not None and con is not None else None
        incong = [t for t in scored if not t["stimulus"].get("congruent")]
        out["stroop_incongruent_accuracy"] = (
            round(sum(1 for t in incong if t["correct"]) / len(incong), 4) if incong else None
        )
    elif game == "corsi":
        spans = [CORSI_LEVELS[t["level"] - 1] for t in scored if t["correct"]]
        out["corsi_span"] = max(spans) if spans else CORSI_LEVELS[0] - 1
    elif game == "trails":
        steps = [t["rt_ms"] for t in scored if t["rt_ms"] is not None and not t["timed_out"]]
        out["trails_ms_per_step"] = _med(steps)
        alt = [t["rt_ms"] for t in scored
               if t["stimulus"].get("alternate") and t["rt_ms"] is not None and not t["timed_out"]]
        out["trails_b_ms_per_step"] = _med(alt)
        out["trails_errors"] = sum(t.get("wrong_taps") or 0 for t in scored)
    return out
