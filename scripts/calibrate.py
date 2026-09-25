"""Correlate game features with reference screening scores and train the calibration model.

    python -m scripts.calibrate                     # MoCA, ridge regression
    python -m scripts.calibrate --method random_forest --k 8
    python -m scripts.calibrate --real-only         # ignore synthetic demo players
    python -m scripts.calibrate --report-only       # correlations only, no model saved

Writes models/calibration.joblib (used automatically by the app) and
exports/calibration_correlations.csv.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import joblib
import pandas as pd

from soundkraft import calibration, config, db


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instrument", default="MoCA", choices=["MoCA", "MMSE"])
    ap.add_argument("--method", default="ridge", choices=["ridge", "random_forest"])
    ap.add_argument("--k", type=int, default=6, help="number of features to keep")
    ap.add_argument("--max-days", type=int, default=30, help="max gap between reference test and session")
    ap.add_argument("--real-only", action="store_true", help="exclude synthetic demo players")
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--db", default=None)
    ap.add_argument("--out", default=str(config.MODEL_PATH))
    args = ap.parse_args(argv)

    conn = db.connect(args.db)
    df = calibration.build_dataset(conn, args.instrument, args.max_days)
    if args.real_only and not df.empty:
        synthetic = {u["id"] for u in db.list_users(conn) if u["is_synthetic"]}
        df = df[~df["user_id"].isin(synthetic)]
    print(f"Paired participants: {len(df)}")
    if len(df) < 5:
        print("Not enough paired data yet (need at least 5 for correlations, 8 for a model).")
        return

    corr = calibration.correlations(df)
    exports = config.ROOT / "exports"
    exports.mkdir(exist_ok=True)
    corr.to_csv(exports / "calibration_correlations.csv", index=False)
    with pd.option_context("display.width", 120, "display.float_format", "{:.3f}".format):
        print("\nFeature correlations with", args.instrument, "(sorted by |Spearman rho|):")
        print(corr.head(15).to_string(index=False))

    if args.report_only:
        return
    bundle = calibration.train(df, args.instrument, args.method, args.k)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, args.out)
    m = bundle["metrics"]
    print(f"\nModel ({args.method}) on {m['n']} participants, features: {', '.join(bundle['features'])}")
    print(f"  Leave-one-out MAE {m['loocv_mae']} points, r = {m['loocv_r']}")
    if "loocv_auc" in m:
        print(f"  Below-cutoff ({bundle['cutoff']:g}) classifier: AUC {m['loocv_auc']}, "
              f"sensitivity {m['sensitivity']}, specificity {m['specificity']} ({m['n_below_cutoff']} below cut-off)")
    print(f"Saved to {args.out}")
    print("\nReminder: pilot-sized results are preliminary and exploratory, not clinical validation.")


if __name__ == "__main__":
    main()
