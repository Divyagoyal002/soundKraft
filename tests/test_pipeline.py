"""Features, scoring and calibration on a small synthetic cohort."""
import joblib
import pytest

from soundkraft import calibration, db, features, scoring, service


def test_session_features_and_composite(conn, cohort):
    s = db.user_sessions(conn, cohort[0]["user_id"])[-1]
    f = s["features"]
    for key in ["nback_accuracy", "nback_dprime", "stroop_interference_ms", "corsi_span",
                "trails_ms_per_step", "swipe_ms", "tap_duration_ms"]:
        assert key in f
    assert set(f["domains"]) == set(scoring.DOMAIN_LABELS)
    assert 0 <= s["composite"] <= 100
    # re-extracting from stored trials gives the same numbers
    fresh = features.extract(db.session_trials(conn, s["id"]))
    assert fresh["nback_accuracy"] == f["nback_accuracy"]


def test_composite_tracks_ability(conn, cohort):
    by_theta = sorted(cohort, key=lambda p: p["theta"])
    first = service.user_report(conn, by_theta[0]["user_id"])["trend"]["baseline_mean"]
    last = service.user_report(conn, by_theta[-1]["user_id"])["trend"]["baseline_mean"]
    assert last > first


def test_calibration_end_to_end(conn, cohort, tmp_path):
    df = calibration.build_dataset(conn)
    assert len(df) == len(cohort)
    corr = calibration.correlations(df)
    assert {"feature", "spearman_rho", "spearman_p"} <= set(corr.columns)
    bundle = calibration.train(df, k=4)
    assert len(bundle["features"]) <= 4 and "composite" not in bundle["features"]
    assert bundle["metrics"]["loocv_mae"] < 5
    path = tmp_path / "m.joblib"
    joblib.dump(bundle, path)
    est = scoring.model_estimate(db.user_sessions(conn, cohort[0]["user_id"])[0]["features"], path)
    assert 0 <= est["estimate"] <= 30


def test_calibration_refuses_tiny_samples(conn, cohort):
    df = calibration.build_dataset(conn).head(5)
    with pytest.raises(ValueError):
        calibration.train(df)
