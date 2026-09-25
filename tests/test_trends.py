from soundkraft import trends


def test_insufficient_data():
    assert trends.analyse([50, 52])["status"] == "insufficient_data"
    assert trends.analyse([50, 52, 51, 50])["status"] == "insufficient_data"


def test_stable_series():
    assert trends.analyse([50, 53, 49, 52, 50, 51, 48, 52, 50])["status"] == "stable"


def test_sustained_decline_flags_follow_up():
    r = trends.analyse([60, 62, 61, 58, 55, 52, 49, 46, 44])
    assert r["status"] == "follow_up" and r["change"] < 0


def test_single_bad_day_is_not_follow_up():
    assert trends.analyse([60, 62, 61, 60, 61, 62, 60, 61, 40])["status"] != "follow_up"


def test_improvement_is_stable():
    assert trends.analyse([40, 42, 41, 45, 48, 50, 52])["status"] == "stable"
