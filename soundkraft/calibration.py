"""Calibration against a validated reference screening tool (MoCA by default).

Pipeline (mirrors the N-back/MMSE and Neuro-World methodology in the PRD):
1. Pair each reference score with the participant's game session closest in time.
2. Correlate every game feature with the reference score (Pearson and Spearman).
3. Keep the most strongly correlated features.
4. Fit a small, regularised model and report leave-one-out cross-validated error,
   because pilot cohorts (15-30 people) are far too small for a held-out test set.

Results from a pilot cohort are preliminary and exploratory, never clinical validation.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, RidgeCV
from sklearn.metrics import mean_absolute_error, roc_auc_score
from sklearn.model_selection import LeaveOneOut
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from . import db

# MoCA: 26/30 is the conventional screening cut-off (scores below suggest follow-up).
DEFAULT_CUTOFFS = {"MoCA": 26.0, "MMSE": 24.0}
EXCLUDE = {"n_trials"}


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)


def build_dataset(conn, instrument: str = "MoCA", max_days: int = 30) -> pd.DataFrame:
    """One row per reference score: that person's closest finished session's features + score."""
    rows = []
    for ref in db.reference_scores(conn):
        if ref["instrument"] != instrument:
            continue
        when = _parse(ref["assessed_at"])
        best, best_gap = None, timedelta(days=max_days)
        for s in db.user_sessions(conn, ref["user_id"]):
            if not s["features"]:
                continue
            gap = abs(_parse(s["started_at"]) - when)
            if gap <= best_gap:
                best, best_gap = s, gap
        if best is None:
            continue
        row = {k: v for k, v in best["features"].items() if k not in EXCLUDE}
        row.update(user_id=ref["user_id"], session_id=best["id"], composite=best["composite"],
                   score=ref["score"], max_score=ref["max_score"])
        rows.append(row)
    return pd.DataFrame(rows)


def feature_columns(df: pd.DataFrame) -> list[str]:
    skip = {"user_id", "session_id", "score", "max_score"}
    return [c for c in df.columns if c not in skip and pd.api.types.is_numeric_dtype(df[c])]


def correlations(df: pd.DataFrame, target: str = "score") -> pd.DataFrame:
    out = []
    for col in feature_columns(df):
        pair = df[[col, target]].dropna()
        if len(pair) < 5 or pair[col].nunique() < 2:
            continue
        pr, pp = stats.pearsonr(pair[col], pair[target])
        sr, sp = stats.spearmanr(pair[col], pair[target])
        out.append({"feature": col, "n": len(pair), "pearson_r": pr, "pearson_p": pp,
                    "spearman_rho": sr, "spearman_p": sp})
    res = pd.DataFrame(out)
    if res.empty:
        return res
    res["abs_rho"] = res["spearman_rho"].abs()
    return res.sort_values("abs_rho", ascending=False).drop(columns="abs_rho").reset_index(drop=True)


def select_features(df: pd.DataFrame, candidates: list[str], k: int = 6, max_p: float = 0.1,
                    target: str = "score") -> list[str]:
    """Top-k candidate features by |Spearman rho| with the target, keeping only p < max_p."""
    corr = correlations(df[candidates + [target]], target)
    if corr.empty:
        return []
    return corr[corr["spearman_p"] < max_p]["feature"].head(k).tolist()


def candidate_features(df: pd.DataFrame, min_coverage: float = 0.8) -> list[str]:
    """Numeric game features present for most participants. The composite is excluded
    because it is derived from the other features."""
    return [c for c in feature_columns(df)
            if c != "composite" and df[c].notna().mean() >= min_coverage and df[c].nunique() > 1]


def _regressor(method: str):
    if method == "random_forest":
        est = RandomForestRegressor(n_estimators=300, min_samples_leaf=2, random_state=0)
    else:
        est = RidgeCV(alphas=np.logspace(-2, 3, 30))
    return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), est)


def _classifier():
    return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                         LogisticRegression(C=1.0, max_iter=1000))


def train(df: pd.DataFrame, instrument: str = "MoCA", method: str = "ridge", k: int = 6,
          max_p: float = 0.1, cutoff: float | None = None) -> dict:
    """Fit the calibration model and estimate its accuracy with leave-one-out CV.

    Feature selection is repeated inside every CV fold, so the reported error is
    not inflated by having chosen features on the held-out person.
    """
    if len(df) < 8:
        raise ValueError(f"need at least 8 paired participants, have {len(df)}")
    df = df.reset_index(drop=True)
    candidates = candidate_features(df)
    y = df["score"].astype(float).to_numpy()
    cutoff = cutoff if cutoff is not None else DEFAULT_CUTOFFS.get(instrument, float(np.median(y)))
    labels = (y < cutoff).astype(int)
    do_clf = min(labels.sum(), len(labels) - labels.sum()) >= 3

    pred = np.zeros(len(df))
    prob = np.zeros(len(df))
    chosen_counts: dict[str, int] = {}
    for train_idx, test_idx in LeaveOneOut().split(df):
        tr, te = df.iloc[train_idx], df.iloc[test_idx]
        feats = select_features(tr, candidates, k, max_p) or candidates[:k]
        for f in feats:
            chosen_counts[f] = chosen_counts.get(f, 0) + 1
        reg = _regressor(method).fit(tr[feats].astype(float), tr["score"].astype(float))
        pred[test_idx] = reg.predict(te[feats].astype(float))
        tr_labels = labels[train_idx]
        if do_clf and 0 < tr_labels.sum() < len(tr_labels):
            clf = _classifier().fit(tr[feats].astype(float), tr_labels)
            prob[test_idx] = clf.predict_proba(te[feats].astype(float))[:, 1]

    metrics = {
        "n": len(df),
        "loocv_mae": round(float(mean_absolute_error(y, pred)), 3),
        "loocv_r": round(float(stats.pearsonr(pred, y)[0]), 3),
    }
    if do_clf:
        guess = (prob >= 0.5).astype(int)
        tp = int(((guess == 1) & (labels == 1)).sum())
        tn = int(((guess == 0) & (labels == 0)).sum())
        metrics.update(
            loocv_auc=round(float(roc_auc_score(labels, prob)), 3),
            sensitivity=round(tp / labels.sum(), 3),
            specificity=round(tn / (len(labels) - labels.sum()), 3),
            n_below_cutoff=int(labels.sum()),
        )

    features = select_features(df, candidates, k, max_p) or candidates[:k]
    X = df[features].astype(float)
    reg = _regressor(method).fit(X, y)
    clf = _classifier().fit(X, labels) if do_clf else None
    return {
        "regressor": reg,
        "classifier": clf,
        "features": features,
        "selection_frequency": {f: round(c / len(df), 2) for f, c in
                                sorted(chosen_counts.items(), key=lambda kv: -kv[1])},
        "instrument": instrument,
        "max_score": float(df["max_score"].max()),
        "cutoff": cutoff,
        "method": method,
        "n": len(df),
        "metrics": metrics,
        "trained_at": datetime.now().isoformat(timespec="seconds"),
    }
