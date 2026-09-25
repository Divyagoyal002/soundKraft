"""Sensory adaptation controller.

Infers accessibility needs from interaction patterns during play and nudges the
user's settings (slower pace, larger targets, tap instead of swipe). Every change
is logged so analysts can account for it, because settings affect raw metrics.
"""

from __future__ import annotations

from .settings import PACE_RANGE, TARGET_SCALE_RANGE, normalise


def recommend(settings: dict, trials: list[dict]) -> list[dict]:
    """Return a list of {setting, old, new, reason, message} changes suggested by one round."""
    s = normalise(settings)
    scored = [t for t in trials if t.get("stimulus", {}).get("scored", True)] or trials
    if len(scored) < 3:
        return []
    n = len(scored)
    changes: list[dict] = []

    timeout_rate = sum(1 for t in scored if t.get("timed_out")) / n
    if timeout_rate >= 0.3 and s["pace"] < PACE_RANGE[1]:
        new = min(PACE_RANGE[1], round(s["pace"] + 0.25, 2))
        changes.append({
            "setting": "pace", "old": s["pace"], "new": new,
            "reason": f"timeout rate {timeout_rate:.0%}",
            "message": "We have given you a little more time for each question.",
        })

    touches = sum(t.get("off_target_touches") or 0 for t in scored)
    off_rate = touches / (touches + n)
    if touches >= 3 and off_rate >= 0.2 and s["target_scale"] < TARGET_SCALE_RANGE[1]:
        new = min(TARGET_SCALE_RANGE[1], round(s["target_scale"] + 0.2, 2))
        changes.append({
            "setting": "target_scale", "old": s["target_scale"], "new": new,
            "reason": f"off-target touch rate {off_rate:.0%}",
            "message": "We have made the buttons bigger.",
        })

    swipe_fail = sum(1 for t in scored if t.get("error_type") == "swipe_unclear")
    if s["input_mode"] == "swipe" and swipe_fail / n >= 0.25:
        changes.append({
            "setting": "input_mode", "old": "swipe", "new": "tap",
            "reason": f"unclear swipes {swipe_fail}/{n}",
            "message": "You can now answer by pressing buttons instead of swiping.",
        })
    return changes


def apply(settings: dict, changes: list[dict]) -> dict:
    s = dict(normalise(settings))
    for c in changes:
        s[c["setting"]] = c["new"]
    return normalise(s)
