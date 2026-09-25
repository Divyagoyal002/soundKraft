from soundkraft import adaptive, sensory


def trials(n_correct, n, **extra):
    return [{"correct": i < n_correct, "rt_ms": 1000.0, "timed_out": False, "stimulus": {"scored": True}, **extra}
            for i in range(n)]


def test_staircase_moves_one_step_and_clamps():
    up = adaptive.summarise_round(trials(12, 12))
    down = adaptive.summarise_round(trials(5, 12))
    mid = adaptive.summarise_round(trials(9, 12))
    assert adaptive.next_level("stroop", 3, up)[0] == 4
    assert adaptive.next_level("stroop", 3, down)[0] == 2
    assert adaptive.next_level("stroop", 3, mid)[0] == 3
    assert adaptive.next_level("stroop", 1, down)[0] == 1
    assert adaptive.next_level("stroop", 8, up)[0] == 8


def test_corsi_two_of_three_rule():
    assert adaptive.next_level("corsi", 3, adaptive.summarise_round(trials(2, 3)))[0] == 4
    assert adaptive.next_level("corsi", 3, adaptive.summarise_round(trials(1, 3)))[0] == 3
    assert adaptive.next_level("corsi", 3, adaptive.summarise_round(trials(0, 3)))[0] == 2


def test_timeouts_lower_level_and_slow_pace():
    ts = [{"correct": False, "rt_ms": None, "timed_out": True, "stimulus": {"scored": True}}] * 5 + trials(7, 7)
    summary = adaptive.summarise_round(ts)
    assert adaptive.next_level("nback", 4, summary)[0] == 3
    changes = sensory.recommend({"pace": 1.0}, ts)
    assert [c["setting"] for c in changes] == ["pace"]
    assert sensory.apply({"pace": 1.0}, changes)["pace"] == 1.25


def test_off_target_and_swipe_trouble():
    ts = trials(8, 8, off_target_touches=1, error_type="swipe_unclear")  # 8 misses in 8 trials
    changes = {c["setting"]: c["new"] for c in sensory.recommend({"input_mode": "swipe"}, ts)}
    assert changes["target_scale"] == 1.2 and changes["input_mode"] == "tap"


def test_no_changes_for_clean_round():
    assert sensory.recommend({}, trials(10, 12)) == []


def test_trail_wrong_circles_do_not_enlarge_buttons():
    ts = trials(4, 8, wrong_taps=1)
    assert sensory.recommend({}, ts) == []
