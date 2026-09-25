"""Export all data to CSV for analysis in Python/R/Excel.

    python -m scripts.export_data            # -> exports/trials.csv, sessions.csv, reference_scores.csv
    python -m scripts.export_data --real-only

Player names are replaced by numeric IDs in the export.
"""

from __future__ import annotations

import argparse
import json

import pandas as pd

from soundkraft import config, db


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=None)
    ap.add_argument("--out", default=str(config.ROOT / "exports"))
    ap.add_argument("--real-only", action="store_true")
    args = ap.parse_args(argv)

    conn = db.connect(args.db)
    users = [u for u in db.list_users(conn) if not (args.real_only and u["is_synthetic"])]
    trials, sessions = [], []
    for u in users:
        for s in db.user_sessions(conn, u["id"]):
            feats = dict(s["features"] or {})
            domains = feats.pop("domains", {})
            feats.pop("model_estimate", None)
            sessions.append({"user_id": u["id"], "session_id": s["id"], "started_at": s["started_at"],
                             "composite": s["composite"], **{f"domain_{k}": v for k, v in domains.items()},
                             **feats})
            for t in db.session_trials(conn, s["id"]):
                t["stimulus"] = json.dumps(t["stimulus"], ensure_ascii=False)
                trials.append({"user_id": u["id"], "session_id": s["id"], **t})
    refs = [r for r in db.reference_scores(conn) if r["user_id"] in {u["id"] for u in users}]
    people = [{"user_id": u["id"], "birth_year": u["birth_year"], "education_years": u["education_years"],
               "is_synthetic": u["is_synthetic"]} for u in users]

    out = config.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(trials).to_csv(out / "trials.csv", index=False)
    pd.DataFrame(sessions).to_csv(out / "sessions.csv", index=False)
    pd.DataFrame(refs).drop(columns=["notes"], errors="ignore").to_csv(out / "reference_scores.csv", index=False)
    pd.DataFrame(people).to_csv(out / "participants.csv", index=False)
    print(f"Exported {len(people)} participants, {len(sessions)} sessions, {len(trials)} trials to {out}/")


if __name__ == "__main__":
    main()
