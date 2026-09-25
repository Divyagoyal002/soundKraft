"""Longitudinal trend detection over a user's session history.

A single low score means little (a bad night's sleep, a noisy room), so flags are
raised only for *sustained* change relative to the person's own baseline:

* baseline  = mean of the first `baseline_n` sessions (SD floored so a very steady
              baseline does not make tiny dips look large)
* recent    = mean of the last `recent_n` sessions after the baseline
* slope     = least-squares slope of the index across all sessions

Status levels (screening language, not diagnosis):
    insufficient_data - fewer than baseline_n + recent_n sessions
    stable            - no sustained drop
    watch             - drop >= 1 baseline SD, or a negative slope with p < 0.10
    follow_up         - drop >= 2 baseline SD AND a negative slope with p < 0.05
"""

from __future__ import annotations

from statistics import mean, stdev

from scipy import stats

STATUS_TEXT = {
    "insufficient_data": "Not enough sessions yet to see a trend.",
    "stable": "Performance is steady compared with this person's own starting point.",
    "watch": "Performance has dipped below this person's usual range. Keep playing regularly and watch the trend.",
    "follow_up": ("A sustained drop from this person's usual performance. "
                  "This is not a diagnosis, but it is worth discussing with a health professional."),
}


def analyse(values: list[float], baseline_n: int = 3, recent_n: int = 3, sd_floor: float = 4.0) -> dict:
    values = [float(v) for v in values if v is not None]
    n = len(values)
    out: dict = {"n_sessions": n, "status": "insufficient_data"}
    if n < baseline_n:
        out["message"] = STATUS_TEXT["insufficient_data"]
        return out

    base = values[:baseline_n]
    b_mean = mean(base)
    b_sd = max(stdev(base) if len(base) > 1 else 0.0, sd_floor)
    out.update(baseline_mean=round(b_mean, 1), baseline_sd=round(b_sd, 2))

    if n >= 3:
        fit = stats.linregress(range(n), values)
        out.update(slope_per_session=round(fit.slope, 3), slope_p=round(float(fit.pvalue), 4))

    if n < baseline_n + recent_n:
        out["message"] = STATUS_TEXT["insufficient_data"]
        return out

    recent = values[-recent_n:]
    r_mean = mean(recent)
    drop_sd = (b_mean - r_mean) / b_sd
    out.update(recent_mean=round(r_mean, 1), change=round(r_mean - b_mean, 1), drop_in_sd=round(drop_sd, 2))

    declining = out["slope_per_session"] < 0
    p = out["slope_p"]
    if drop_sd >= 2 and declining and p < 0.05:
        status = "follow_up"
    elif drop_sd >= 1 or (declining and p < 0.10):
        status = "watch"
    else:
        status = "stable"
    out["status"] = status
    out["message"] = STATUS_TEXT[status]
    return out
