"""Generate a SYNTHETIC demo cohort so the dashboard and calibration pipeline can be exercised
before any real participant data exists.

Every simulated player is flagged `is_synthetic` and shown with a "synthetic" tag. Numbers
produced from this data say nothing about real people - they only test the software.

Each simulated person has a latent ability theta (~N(0,1)); a reference MoCA-like score and all
game behaviour are generated from it, and some people are given a gradual decline over time.
Sessions go through exactly the same service layer as the real web app.

Usage:
    python -m scripts.simulate --players 24 --sessions 12
    python -m scripts.simulate --clear      # delete all synthetic players
"""

from __future__ import annotations

import argparse
import math
import random
from datetime import datetime, timedelta, timezone

from soundkraft import config, db, service
from soundkraft.games import MAX_LEVEL
from soundkraft.settings import DEFAULTS

BASE_RT = {"nback": 1100, "stroop": 950, "corsi": 900, "trails": 1150}
CHANCE = {"nback": 0.5, "stroop": 0.3, "corsi": 0.0, "trails": 0.2}


def _p_correct(theta: float, game: str, level: int, extra_difficulty: float = 0.0) -> float:
    d = (level - 1) / max(1, MAX_LEVEL[game] - 1) * 4 - 1.5 + extra_difficulty
    p = 1 / (1 + math.exp(-1.6 * (theta - d)))
    floor = CHANCE[game]
    return floor + (0.97 - floor) * p


def _rt(rng: random.Random, theta: float, game: str, level: int, extra: float = 0.0) -> float:
    ms = BASE_RT[game] * math.exp(-0.28 * theta) * (1 + 0.04 * level) + extra
    return ms * math.exp(rng.gauss(0, 0.22))


def simulate_round(rng: random.Random, theta: float, cfg: dict) -> list[dict]:
    game, level = cfg["game"], cfg["level"]
    window = cfg["response_window_ms"]
    motor = math.exp(-0.2 * theta)
    out = []
    for stim in cfg["trials"]:
        t = {
            "tap_duration_ms": round(110 * motor * math.exp(rng.gauss(0, 0.2)), 1),
            "off_target_touches": int(rng.random() < 0.04 * motor),
            "input_mode": "swipe",
            "touch_x": round(rng.uniform(0.3, 0.7), 3),
            "touch_y": round(rng.uniform(0.4, 0.8), 3),
        }
        if not stim.get("scored", True):
            out.append({**t, "response": None, "rt_ms": None})
            continue

        extra_d = 0.6 if game == "stroop" and not stim.get("congruent", True) else 0.0
        extra_rt = (350 - 90 * theta) if game == "stroop" and not stim.get("congruent", True) else 0.0
        if game == "corsi":
            extra_rt = 650 * len(stim["sequence"]) * math.exp(-0.15 * theta)
        correct = rng.random() < _p_correct(theta, game, level, extra_d)
        rt = _rt(rng, theta, game, level, extra_rt)
        if not correct:
            rt *= 1.2
        if rt > window and game != "corsi":
            out.append({**t, "response": None, "rt_ms": None, "timed_out": True})
            continue
        t["rt_ms"] = round(rt, 1)
        t["first_touch_ms"] = round(rt * (0.85 if game != "corsi" else 1.1 / len(stim["sequence"])), 1)

        answer = stim["answer"]
        if game == "nback":
            t["response"] = answer if correct else ("different" if answer == "same" else "same")
            t["swipe_ms"] = round(420 * motor * math.exp(rng.gauss(0, 0.25)), 1)
            t["swipe_px"] = round(rng.uniform(120, 260), 1)
        elif game == "stroop":
            others = [c["name"] for c in cfg["palette"] if c["name"] != answer]
            t["response"] = answer if correct else rng.choice(others)
        elif game == "corsi":
            seq = list(answer)
            if not correct:
                i = rng.randrange(len(seq) - 1)
                seq[i], seq[i + 1] = seq[i + 1], seq[i]
            t["response"] = seq
        elif game == "trails":
            t["response"] = answer if correct else "?"
            t["wrong_taps"] = 0 if correct else 1
        out.append(t)
    return out


def simulate_person(conn, rng: random.Random, idx: int, n_sessions: int, start: datetime) -> dict:
    theta0 = rng.gauss(0, 1)
    declining = rng.random() < 0.3
    decline_per_session = rng.uniform(0.06, 0.14) if declining else 0.0
    moca = max(10, min(30, round(24.5 + 3.2 * theta0 + rng.gauss(0, 1.3))))
    settings = dict(DEFAULTS, pace=1.0 if theta0 > -1 else 1.25)
    uid = db.create_user(conn, f"Demo {idx:02d}", rng.randint(1940, 1962), rng.randint(6, 18), settings,
                         is_synthetic=True, created_at=start.isoformat(timespec="seconds"))
    when = start
    for s in range(n_sessions):
        theta = theta0 - decline_per_session * s + 0.15 * min(s, 3) / 3  # small practice effect
        theta += rng.gauss(0, 0.15)  # day-to-day variability
        ts = when.isoformat(timespec="seconds")
        sess = service.start_session(conn, uid, {"simulated": True}, started_at=ts)
        for game in config.BATTERY:
            for _ in range(config.ROUNDS_PER_GAME[game]):
                cfg = service.next_round(conn, sess["session_id"], game, started_at=ts, seed=rng.randrange(2**31))
                service.submit_round(conn, cfg["round_id"], simulate_round(rng, theta, cfg), ended_at=ts)
        service.finish_session(conn, sess["session_id"], ended_at=ts)
        if s == 0:
            db.add_reference_score(conn, uid, "MoCA", moca, 30, when.date().isoformat(), "synthetic")
        when += timedelta(days=rng.choice([1, 2, 2, 3, 4]))
    return {"user_id": uid, "theta": round(theta0, 2), "moca": moca, "declining": declining}


def clear(conn) -> int:
    ids = [u["id"] for u in db.list_users(conn) if u["is_synthetic"]]
    for uid in ids:
        db.delete_user(conn, uid)
    return len(ids)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--players", type=int, default=24)
    ap.add_argument("--sessions", type=int, default=12)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--db", default=None, help="database path (default: data/soundkraft.db)")
    ap.add_argument("--clear", action="store_true", help="delete all synthetic players and exit")
    args = ap.parse_args(argv)

    conn = db.connect(args.db)
    if args.clear:
        print(f"Deleted {clear(conn)} synthetic players.")
        return
    rng = random.Random(args.seed)
    start = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=int(args.sessions * 2.7))
    existing = sum(1 for u in db.list_users(conn) if u["is_synthetic"])
    for i in range(args.players):
        p = simulate_person(conn, rng, existing + i + 1, args.sessions, start)
        print(f"  Demo {existing + i + 1:02d}: MoCA {p['moca']:>2}  {'declining' if p['declining'] else 'stable'}")
    print(f"Created {args.players} synthetic players x {args.sessions} sessions.")


if __name__ == "__main__":
    main()
