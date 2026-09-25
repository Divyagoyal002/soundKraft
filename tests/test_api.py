"""Full HTTP flow: join, play a session through the API, and view the dashboard."""
from soundkraft import config, db


def make_player(client, name="Asha", share="yes"):
    r = client.post("/join", data={"display_name": name, "birth_year": "1950", "consent": "yes", "share": share},
                    follow_redirects=False)
    assert r.status_code == 303
    return int(r.headers["location"].rsplit("/", 1)[1])


def perfect_answers(cfg):
    out = []
    for t in cfg["trials"]:
        out.append({"response": t["answer"] if t.get("scored", True) else None, "rt_ms": 900,
                    "first_touch_ms": 700, "tap_duration_ms": 100, "off_target_touches": 0})
    return out


def play_session(client, uid, answer=perfect_answers):
    s = client.post("/api/sessions", json={"user_id": uid}).json()
    for game in s["battery"]:
        for _ in range(s["rounds_per_game"][game]):
            cfg = client.post(f"/api/sessions/{s['session_id']}/rounds", json={"game": game}).json()
            res = client.post(f"/api/rounds/{cfg['round_id']}/results", json={"trials": answer(cfg)}).json()
            assert res["summary"]["n"] > 0
    return s["session_id"], client.post(f"/api/sessions/{s['session_id']}/finish").json()


def test_consent_required(client):
    r = client.post("/join", data={"display_name": "Bo"})
    assert r.status_code == 200 and "consent" in r.text


def test_pages_render(client):
    uid = make_player(client)
    for url in ["/", "/about", "/join", f"/setup/{uid}", f"/settings/{uid}", f"/play/{uid}"]:
        r = client.get(url)
        assert r.status_code == 200, url
        assert config.DISCLAIMER in r.text


def test_session_flow_levels_up_and_scores(client):
    uid = make_player(client)
    sid, done = play_session(client, uid)
    assert done["points"] > 0 and done["sessions_completed"] == 1
    rounds = db.session_rounds(client.conn, sid, "stroop")
    assert [r["level"] for r in rounds] == [1, 2, 3]  # perfect play climbs one level per round
    session = db.get_session(client.conn, sid)
    assert session["composite"] is not None and session["features"]["stroop_accuracy"] == 1.0
    # next session resumes at the last level played
    s2 = client.post("/api/sessions", json={"user_id": uid}).json()
    cfg = client.post(f"/api/sessions/{s2['session_id']}/rounds", json={"game": "stroop"}).json()
    assert cfg["level"] == 3


def test_correctness_is_decided_by_server(client):
    uid = make_player(client)
    s = client.post("/api/sessions", json={"user_id": uid}).json()
    cfg = client.post(f"/api/sessions/{s['session_id']}/rounds", json={"game": "stroop"}).json()
    lies = [{"response": "NOT A COLOUR", "correct": True, "rt_ms": 500} for _ in cfg["trials"]]
    res = client.post(f"/api/rounds/{cfg['round_id']}/results", json={"trials": lies}).json()
    assert res["summary"]["accuracy"] == 0.0


def test_timeouts_trigger_sensory_adaptation(client):
    uid = make_player(client)
    s = client.post("/api/sessions", json={"user_id": uid}).json()
    cfg = client.post(f"/api/sessions/{s['session_id']}/rounds", json={"game": "stroop"}).json()
    res = client.post(f"/api/rounds/{cfg['round_id']}/results",
                      json={"trials": [{"timed_out": True} for _ in cfg["trials"]]}).json()
    assert any(a["setting"] == "pace" for a in res["adaptations"])
    assert db.get_user(client.conn, uid)["settings"]["pace"] == 1.25
    cfg2 = client.post(f"/api/sessions/{s['session_id']}/rounds", json={"game": "stroop"}).json()
    assert cfg2["response_window_ms"] > cfg["response_window_ms"]


def test_dashboard_requires_pin_and_respects_sharing(client):
    shared = make_player(client, "Shared")
    private = make_player(client, "Private", share="no")
    play_session(client, shared)
    assert client.get("/dashboard", follow_redirects=False).status_code == 303
    assert client.post("/dashboard/login", data={"pin": "wrong"}).status_code == 200
    client.post("/dashboard/login", data={"pin": config.DASHBOARD_PIN})
    page = client.get("/dashboard").text
    assert "Shared" in page and "Private" not in page
    assert client.get(f"/dashboard/user/{shared}").status_code == 200
    assert client.get(f"/dashboard/user/{private}").status_code == 403
    csv_text = client.get(f"/dashboard/user/{shared}/trials.csv").text
    assert csv_text.splitlines()[0].startswith("session_id")
    r = client.post(f"/dashboard/user/{shared}/reference",
                    data={"instrument": "MoCA", "score": "27", "assessed_at": "2026-09-01"}, follow_redirects=False)
    assert r.status_code == 303 and db.reference_scores(client.conn, shared)[0]["score"] == 27


def test_withdrawal_deletes_everything(client):
    uid = make_player(client, "Leaving")
    sid, _ = play_session(client, uid)
    client.post("/dashboard/login", data={"pin": config.DASHBOARD_PIN})
    client.post(f"/dashboard/user/{uid}/delete", data={"confirm": "Leaving"})
    assert db.get_user(client.conn, uid) is None
    assert db.session_trials(client.conn, sid) == []
