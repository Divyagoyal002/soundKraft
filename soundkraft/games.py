"""Mini-game definitions: level tables and stimulus generation.

All stimuli are generated here (server side) from a seeded RNG so every round is
reproducible and the browser only has to render and time it.

Games and the cognitive domain each one targets:
    nback  - "Kitchen Memory": N-back working memory
    stroop - "Colour Clash":   Stroop selective attention / inhibition
    corsi  - "Garden Path":    Corsi block spatial working memory
    trails - "Trail Walk":     Trail Making A/B executive function (set shifting)
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

GAMES: dict[str, dict] = {
    "nback": {
        "title": "Kitchen Memory",
        "domain": "memory",
        "instructions": (
            "Dishes will appear one at a time. Is this dish the same as the one "
            "{n_text}? Swipe right or press Same if it matches. Swipe left or press Different if not."
        ),
    },
    "stroop": {
        "title": "Colour Clash",
        "domain": "attention",
        "instructions": (
            "A colour word will appear. Ignore what the word says. "
            "Press the button for the colour of the ink."
        ),
    },
    "corsi": {
        "title": "Garden Path",
        "domain": "spatial",
        "instructions": (
            "Watch the flowers light up one by one. "
            "Then tap the same flowers in the same order."
        ),
    },
    "trails": {
        "title": "Trail Walk",
        "domain": "executive",
        "instructions": "{trail_text}",
    },
}

DOMAINS = {g: meta["domain"] for g, meta in GAMES.items()}

FOODS = ["🍎", "🥕", "🍞", "🧀", "🍌", "🥦", "🍇", "🥚", "🍅", "🍐"]
FOOD_NAMES = ["apple", "carrot", "bread", "cheese", "banana", "broccoli", "grapes", "egg", "tomato", "pear"]

COLOURS = [
    {"name": "RED", "hex": "#d7263d"},
    {"name": "BLUE", "hex": "#1b64d1"},
    {"name": "GREEN", "hex": "#1e8a3c"},
    {"name": "YELLOW", "hex": "#e0a800"},
]

NBACK_LEVELS = [  # (n, pool size, response window ms)
    (1, 4, 4000), (1, 6, 3400), (1, 8, 3000),
    (2, 4, 4000), (2, 6, 3400), (2, 8, 3000),
    (3, 6, 4000), (3, 8, 3400),
]
STROOP_LEVELS = [  # (colours, incongruent proportion, response window ms)
    (3, 0.25, 4500), (3, 0.35, 4000), (4, 0.40, 3600), (4, 0.50, 3200),
    (4, 0.55, 2800), (4, 0.60, 2500), (4, 0.70, 2200), (4, 0.75, 1900),
]
CORSI_LEVELS = [2, 3, 4, 5, 6, 7, 8, 9]  # sequence length (span)
TRAILS_LEVELS = [  # (targets, alternate numbers & letters?)
    (6, False), (8, False), (8, True), (10, True), (12, True), (14, True), (16, True),
]

MAX_LEVEL = {
    "nback": len(NBACK_LEVELS),
    "stroop": len(STROOP_LEVELS),
    "corsi": len(CORSI_LEVELS),
    "trails": len(TRAILS_LEVELS),
}


@dataclass
class Round:
    game: str
    level: int
    config: dict

    def as_dict(self) -> dict:
        return {"game": self.game, "level": self.level, **self.config}


def clamp_level(game: str, level: int) -> int:
    return max(1, min(MAX_LEVEL[game], int(level)))


def make_round(game: str, level: int, settings: dict, seed: int | None = None) -> Round:
    if game not in GAMES:
        raise ValueError(f"unknown game: {game}")
    level = clamp_level(game, level)
    rng = random.Random(seed)
    pace = float(settings.get("pace", 1.0))
    builder = {"nback": _nback, "stroop": _stroop, "corsi": _corsi, "trails": _trails}[game]
    cfg = builder(level, pace, rng)
    cfg["title"] = GAMES[game]["title"]
    cfg["domain"] = GAMES[game]["domain"]
    cfg["seed"] = seed
    return Round(game, level, cfg)


def _nback(level: int, pace: float, rng: random.Random) -> dict:
    n, pool_size, window = NBACK_LEVELS[level - 1]
    pool = list(range(pool_size))
    scored = 12
    total = n + scored
    n_matches = round(scored / 3)
    match_positions = set(rng.sample(range(n, total), n_matches))
    seq: list[int] = []
    for i in range(total):
        if i in match_positions:
            seq.append(seq[i - n])
        else:
            choices = [p for p in pool if i < n or p != seq[i - n]]
            seq.append(rng.choice(choices))
    trials = []
    for i, item in enumerate(seq):
        is_match = i >= n and seq[i] == seq[i - n]
        trials.append({
            "item": FOODS[item],
            "name": FOOD_NAMES[item],
            "match": is_match,
            "answer": "same" if is_match else "different",
            "scored": i >= n,
        })
    n_text = {1: "just before it", 2: "two before it", 3: "three before it"}[n]
    return {
        "n": n,
        "response_window_ms": int(window * pace),
        "isi_ms": int(600 * pace),
        "trials": trials,
        "instructions": GAMES["nback"]["instructions"].format(n_text=n_text),
    }


def _stroop(level: int, pace: float, rng: random.Random) -> dict:
    n_colours, p_incongruent, window = STROOP_LEVELS[level - 1]
    palette = COLOURS[:n_colours]
    n_trials = 12
    n_incongruent = round(n_trials * p_incongruent)
    kinds = ["incongruent"] * n_incongruent + ["congruent"] * (n_trials - n_incongruent)
    rng.shuffle(kinds)
    trials = []
    for kind in kinds:
        ink = rng.choice(palette)
        word = ink if kind == "congruent" else rng.choice([c for c in palette if c is not ink])
        trials.append({
            "word": word["name"],
            "ink": ink["hex"],
            "answer": ink["name"],
            "congruent": kind == "congruent",
            "scored": True,
        })
    return {
        "palette": palette,
        "response_window_ms": int(window * pace),
        "isi_ms": int(500 * pace),
        "trials": trials,
        "instructions": GAMES["stroop"]["instructions"],
    }


def _corsi(level: int, pace: float, rng: random.Random) -> dict:
    span = CORSI_LEVELS[level - 1]
    grid = 3 if span <= 5 else 4
    trials = []
    for _ in range(3):
        seq = rng.sample(range(grid * grid), span)
        trials.append({"sequence": seq, "answer": seq, "scored": True})
    return {
        "span": span,
        "grid": grid,
        "flash_ms": int(700 * pace),
        "gap_ms": int(350 * pace),
        "response_window_ms": int((8000 + 2500 * span) * pace),
        "trials": trials,
        "instructions": GAMES["corsi"]["instructions"],
    }


def trail_labels(n: int, alternate: bool) -> list[str]:
    if not alternate:
        return [str(i + 1) for i in range(n)]
    letters = "ABCDEFGHIJKLMNOP"
    return [str(i // 2 + 1) if i % 2 == 0 else letters[i // 2] for i in range(n)]


def _trails(level: int, pace: float, rng: random.Random) -> dict:
    n, alternate = TRAILS_LEVELS[level - 1]
    labels = trail_labels(n, alternate)
    points = _spread_points(n, rng, min_dist=0.2 if n <= 8 else 0.16)
    targets = [{"label": lab, "x": x, "y": y} for lab, (x, y) in zip(labels, points)]
    if alternate:
        text = ("Tap the circles in order, switching between numbers and letters: "
                "1, then A, then 2, then B, and so on.")
    else:
        text = "Tap the numbered circles in order: 1, 2, 3, and so on, as quickly and carefully as you can."
    return {
        "alternate": alternate,
        "targets": targets,
        "response_window_ms": int((30000 + 6000 * n) * pace),
        "trials": [{"target": lab, "answer": lab, "alternate": alternate, "scored": True} for lab in labels],
        "instructions": text,
    }


def _spread_points(n: int, rng: random.Random, min_dist: float) -> list[tuple[float, float]]:
    """Random points in the unit square (with margin) no closer than `min_dist`."""
    for _ in range(200):
        pts: list[tuple[float, float]] = []
        for _ in range(n * 60):
            p = (round(rng.uniform(0.1, 0.9), 3), round(rng.uniform(0.1, 0.9), 3))
            if all(math.dist(p, q) >= min_dist for q in pts):
                pts.append(p)
                if len(pts) == n:
                    return pts
        min_dist *= 0.95
    raise RuntimeError("could not place trail targets")
