"""Adaptive difficulty engine (rules-based staircase) and per-round summaries.

The engine keeps each player near the edge of their ability: hard enough to be
informative, easy enough to stay enjoyable. Levels move one step per round.
"""

from __future__ import annotations

from statistics import median

from .games import clamp_level


def summarise_round(trials: list[dict]) -> dict:
    """Accuracy, median correct RT and timeout rate over the scored trials of one round."""
    scored = [t for t in trials if t.get("stimulus", {}).get("scored", True)]
    if not scored:
        return {"n": 0, "accuracy": None, "median_rt_ms": None, "timeout_rate": None}
    correct = [t for t in scored if t.get("correct")]
    rts = [t["rt_ms"] for t in correct if t.get("rt_ms") is not None and not t.get("timed_out")]
    return {
        "n": len(scored),
        "accuracy": round(len(correct) / len(scored), 4),
        "median_rt_ms": round(median(rts), 1) if rts else None,
        "timeout_rate": round(sum(1 for t in scored if t.get("timed_out")) / len(scored), 4),
    }


def next_level(game: str, level: int, summary: dict) -> tuple[int, str]:
    """Return (new level, reason) given the summary of the round just played at `level`."""
    acc = summary.get("accuracy")
    timeouts = summary.get("timeout_rate") or 0.0
    if acc is None:
        return level, "no scored trials"

    if game == "corsi":
        # Classic Corsi rule: 2 of 3 sequences right -> longer span; none right -> shorter.
        right = round(acc * summary["n"])
        if right >= 2:
            return clamp_level(game, level + 1), "2+ sequences correct"
        if right == 0:
            return clamp_level(game, level - 1), "no sequences correct"
        return level, "1 sequence correct"

    up, down = (0.9, 0.7) if game == "trails" else (0.85, 0.6)
    if acc >= up and timeouts <= 0.1:
        return clamp_level(game, level + 1), f"accuracy {acc:.0%} >= {up:.0%}"
    if acc < down or timeouts > 0.3:
        return clamp_level(game, level - 1), f"accuracy {acc:.0%} or timeouts {timeouts:.0%} too high"
    return level, "in target range"


def starting_level(previous_level: int | None) -> int:
    """First level of a game in a new session: resume where the player last played."""
    return previous_level if previous_level else 1
