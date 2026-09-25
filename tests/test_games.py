import pytest

from soundkraft import games
from soundkraft.settings import DEFAULTS, normalise


@pytest.mark.parametrize("game", list(games.GAMES))
@pytest.mark.parametrize("level", [1, 3, 99])
def test_rounds_are_reproducible_and_well_formed(game, level):
    a = games.make_round(game, level, DEFAULTS, seed=42)
    b = games.make_round(game, level, DEFAULTS, seed=42)
    assert a.as_dict() == b.as_dict()
    assert 1 <= a.level <= games.MAX_LEVEL[game]
    assert a.config["trials"] and all("answer" in t for t in a.config["trials"])


def test_nback_answers_match_sequence():
    for level in range(1, games.MAX_LEVEL["nback"] + 1):
        cfg = games.make_round("nback", level, DEFAULTS, seed=level).config
        n, trials = cfg["n"], cfg["trials"]
        assert sum(not t["scored"] for t in trials) == n
        for i, t in enumerate(trials):
            if i >= n:
                assert t["match"] == (t["item"] == trials[i - n]["item"])
        assert sum(t["match"] for t in trials) == 4


def test_stroop_congruency():
    cfg = games.make_round("stroop", 5, DEFAULTS, seed=1).config
    hexes = {c["name"]: c["hex"] for c in cfg["palette"]}
    for t in cfg["trials"]:
        assert hexes[t["answer"]] == t["ink"]
        assert (t["word"] == t["answer"]) == t["congruent"]


def test_corsi_sequences_distinct_and_in_grid():
    cfg = games.make_round("corsi", 8, DEFAULTS, seed=5).config
    for t in cfg["trials"]:
        assert len(set(t["sequence"])) == cfg["span"] == 9
        assert all(0 <= i < cfg["grid"] ** 2 for i in t["sequence"])


def test_trails_labels_and_spacing():
    assert games.trail_labels(6, True) == ["1", "A", "2", "B", "3", "C"]
    cfg = games.make_round("trails", games.MAX_LEVEL["trails"], DEFAULTS, seed=9).config
    pts = [(t["x"], t["y"]) for t in cfg["targets"]]
    assert all(0.05 <= x <= 0.95 and 0.05 <= y <= 0.95 for x, y in pts)


def test_pace_stretches_time_windows():
    slow = normalise({"pace": 2.0})
    assert games.make_round("stroop", 1, slow, 1).config["response_window_ms"] == \
        2 * games.make_round("stroop", 1, DEFAULTS, 1).config["response_window_ms"]


def test_settings_are_clamped():
    s = normalise({"pace": 9, "target_scale": 0.1, "text_scale": 1.3, "contrast": "x", "audio_cues": "false"})
    assert s["pace"] == 2.0 and s["target_scale"] == 1.0 and s["text_scale"] == 1.25
    assert s["contrast"] == "standard" and s["audio_cues"] is False


def test_old_database_is_migrated(tmp_path):
    import sqlite3

    from soundkraft import db

    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE trials (id INTEGER PRIMARY KEY, round_id INTEGER, trial_index INTEGER)")
    old.close()
    cols = {r["name"] for r in db.connect(path).execute("PRAGMA table_info(trials)")}
    assert "wrong_taps" in cols
