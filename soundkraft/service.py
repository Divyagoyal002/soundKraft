"""Session workflow shared by the web API and the simulator.

start_session -> (next_round -> submit_round)* per game -> finish_session
"""

from __future__ import annotations

import random

from . import adaptive, config, db, features, scoring, sensory, trends
from .games import DOMAINS, MAX_LEVEL, make_round
from .settings import normalise

POINTS_PER_CORRECT = 10
POINTS_PER_LEVEL_UP = 25


class NotFound(Exception):
    pass


def start_session(conn, user_id: int, device: dict | None = None, started_at: str | None = None) -> dict:
    user = db.get_user(conn, user_id)
    if not user:
        raise NotFound("user")
    settings = normalise(user["settings"])
    sid = db.create_session(conn, user_id, settings, device, started_at)
    return {"session_id": sid, "battery": config.BATTERY, "rounds_per_game": config.ROUNDS_PER_GAME,
            "settings": settings}


def _level_for(conn, session: dict, game: str) -> tuple[int, int]:
    """(level, round_index) for the next round of `game` in this session."""
    played = [r for r in db.session_rounds(conn, session["id"], game) if r["ended_at"]]
    if played:
        last = played[-1]
        summary = adaptive.summarise_round(db.round_trials(conn, last["id"]))
        level, _ = adaptive.next_level(game, last["level"], summary)
        return level, len(played)
    return adaptive.starting_level(db.last_completed_level(conn, session["user_id"], game)), 0


def next_round(conn, session_id: int, game: str, started_at: str | None = None,
               seed: int | None = None) -> dict:
    session = db.get_session(conn, session_id)
    if not session:
        raise NotFound("session")
    if session["ended_at"]:
        raise ValueError("session already finished")
    if game not in DOMAINS:
        raise ValueError(f"unknown game {game}")
    user = db.get_user(conn, session["user_id"])
    settings = normalise(user["settings"])  # picks up adaptations made earlier in the session
    level, idx = _level_for(conn, session, game)
    seed = seed if seed is not None else random.randrange(2**31)
    rnd = make_round(game, level, settings, seed)
    rid = db.create_round(conn, session_id, game, idx, rnd.level, rnd.config, started_at)
    return {"round_id": rid, "round_index": idx, "rounds_total": config.ROUNDS_PER_GAME[game],
            "max_level": MAX_LEVEL[game], "settings": settings, **rnd.as_dict()}


TRIAL_NUMERIC = ["rt_ms", "first_touch_ms", "tap_duration_ms", "swipe_ms", "swipe_px", "touch_x", "touch_y"]


def _clean_trial(i: int, raw: dict, stimulus: dict) -> dict:
    t = {"trial_index": i, "stimulus": stimulus}
    for k in TRIAL_NUMERIC:
        v = raw.get(k)
        t[k] = float(v) if isinstance(v, (int, float)) else None
    resp = raw.get("response")
    if isinstance(resp, list):
        t["response"] = ",".join(str(x) for x in resp)[:64]
    else:
        t["response"] = None if resp is None else str(resp)[:64]
    t["timed_out"] = int(bool(raw.get("timed_out")))
    t["off_target_touches"] = int(raw.get("off_target_touches") or 0)
    t["wrong_taps"] = int(raw.get("wrong_taps") or 0)
    t["input_mode"] = raw.get("input_mode")
    t["error_type"] = raw.get("error_type")
    # Correctness is decided here, never trusted from the client.
    t["correct"] = int(not t["timed_out"] and _is_correct(stimulus, raw.get("response")))
    if not t["correct"] and not t["error_type"]:
        t["error_type"] = "timeout" if t["timed_out"] else "wrong"
    return t


def _is_correct(stimulus: dict, response) -> bool:
    answer = stimulus.get("answer")
    if isinstance(answer, list):
        return isinstance(response, (list, str)) and _as_seq(response) == answer
    return response is not None and str(response) == str(answer)


def _as_seq(response) -> list[int]:
    try:
        if isinstance(response, str):
            return [int(x) for x in response.split(",") if x.strip()]
        return [int(x) for x in response]
    except (TypeError, ValueError):
        return []


def submit_round(conn, round_id: int, raw_trials: list[dict], ended_at: str | None = None) -> dict:
    rnd = db.get_round(conn, round_id)
    if not rnd:
        raise NotFound("round")
    session = db.get_session(conn, rnd["session_id"])
    if session["ended_at"]:
        raise ValueError("session already finished")
    stimuli = rnd["config"]["trials"]
    trials = [_clean_trial(i, raw, stimuli[i]) for i, raw in enumerate(raw_trials[: len(stimuli)])]
    summary = adaptive.summarise_round(trials)
    db.save_trials(conn, round_id, trials, summary["accuracy"], summary["median_rt_ms"], ended_at)

    new_level, reason = adaptive.next_level(rnd["game"], rnd["level"], summary)

    user = db.get_user(conn, session["user_id"])
    changes = sensory.recommend(user["settings"], trials)
    if changes:
        db.update_user_settings(conn, user["id"], sensory.apply(user["settings"], changes))
        for c in changes:
            db.log_adaptation(conn, user["id"], round_id, c["setting"], c["old"], c["new"], c["reason"])

    points = POINTS_PER_CORRECT * sum(t["correct"] for t in trials if t["stimulus"].get("scored", True))
    if new_level > rnd["level"]:
        points += POINTS_PER_LEVEL_UP
    stars = 3 if (summary["accuracy"] or 0) >= 0.85 else 2 if (summary["accuracy"] or 0) >= 0.6 else 1
    return {
        "summary": summary,
        "level": rnd["level"],
        "next_level": new_level,
        "level_reason": reason,
        "points": points,
        "stars": stars,
        "adaptations": [{"setting": c["setting"], "message": c["message"]} for c in changes],
    }


def finish_session(conn, session_id: int, ended_at: str | None = None) -> dict:
    session = db.get_session(conn, session_id)
    if not session:
        raise NotFound("session")
    rows = db.session_trials(conn, session_id)
    feats = features.extract(rows)
    comp = scoring.composite(feats)
    feats["domains"] = scoring.domain_scores(feats)
    est = scoring.model_estimate(feats)
    if est:
        feats["model_estimate"] = est
    scored = [r for r in rows if r["stimulus"].get("scored", True)]
    points = POINTS_PER_CORRECT * sum(r["correct"] for r in scored)
    db.finish_session(conn, session_id, feats, comp, points, ended_at)
    games_played = sorted({r["game"] for r in rows})
    return {"session_id": session_id, "points": points, "games_played": games_played,
            "total_points": total_points(conn, session["user_id"]),
            "sessions_completed": len(db.user_sessions(conn, session["user_id"]))}


def total_points(conn, user_id: int) -> int:
    return sum(s["points"] for s in db.user_sessions(conn, user_id))


def user_report(conn, user_id: int) -> dict:
    """Everything the caregiver dashboard shows for one person."""
    sessions = [s for s in db.user_sessions(conn, user_id) if s["composite"] is not None]
    series = [{"session_id": s["id"], "date": s["started_at"][:10], "composite": s["composite"],
               "domains": (s["features"] or {}).get("domains", {})} for s in sessions]
    overall = trends.analyse([p["composite"] for p in series])
    domain_trends = {}
    for d in scoring.DOMAIN_LABELS:
        vals = [p["domains"].get(d) for p in series if p["domains"].get(d) is not None]
        domain_trends[d] = trends.analyse(vals)
    latest = sessions[-1] if sessions else None
    return {
        "series": series,
        "trend": overall,
        "domain_trends": domain_trends,
        "latest": latest,
        "references": db.reference_scores(conn, user_id),
        "adaptations": db.user_adaptations(conn, user_id),
    }
