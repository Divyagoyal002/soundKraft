# SoundKraft methods reference

Parameters and definitions to cite in the research paper. The source of truth is the code; the file for each section is linked.

## 1. Task battery ([games.py](../soundkraft/games.py))

A daily session runs the four games in a fixed order. Each game has several rounds, and the difficulty level changes between rounds. Every time window is multiplied by the player's **pace** setting (1.0–2.0).

| Game | Paradigm | Rounds | Trials/round | Level parameters |
|---|---|---|---|---|
| Kitchen Memory | N-back (answer "Same" or "Different" on every item) | 3 | n + 12 (the first n items are "remember" items and are not scored) | 8 levels: n = 1→3, item pool 4→8, response window 4.0→3.0 s. About one third of scored items are matches. |
| Colour Clash | Stroop colour naming | 3 | 12 | 8 levels: 3→4 colours, share of incongruent trials 25%→75%, window 4.5→1.9 s |
| Garden Path | Corsi block tapping | 3 | 3 sequences | 8 levels: span 2→9 on a 3×3 grid (4×4 from span 6). Each flash lasts 700 ms. |
| Trail Walk | Trail Making (A: numbers; B: alternating numbers and letters) | 2 | one trial per circle | 7 levels: 6→16 circles, with part B from level 3 onward |

## 2. Adaptive difficulty ([adaptive.py](../soundkraft/adaptive.py))

* The **first round** of each game starts at the level of the player's most recent completed round of that game.
* **N-back and Stroop:** the level goes up when accuracy ≥ 85% and timeouts ≤ 10%. It goes down when accuracy < 60% or timeouts > 30%. Otherwise it stays the same.
* **Trail Walk:** the same rule with thresholds of 90% and 70%.
* **Corsi:** the level goes up when at least 2 of 3 sequences are correct and down when none are (the classic Corsi rule).

Because the level adapts, raw accuracy alone understates ability. The features therefore include `*_max_level` and `*_mean_level`.

## 3. Sensory adaptation ([sensory.py](../soundkraft/sensory.py))

These checks run after every round, using that round's scored trials:

| Trigger | Change |
|---|---|
| timeouts ≥ 30% of trials | pace +0.25 (max 2.0) |
| ≥ 3 off-target touches **and** ≥ 20% of touches off target | button size +0.2 (max 1.6) |
| unclear swipes (moved 25–80 px without committing) in ≥ 25% of trials | switch from swipe to tap input |

Every change is stored in the `adaptations` table and shown on the dashboard, because it can shift raw metrics. Report it as a covariate or limitation.

## 4. Per-trial measurements ([core.js](../soundkraft/static/js/core.js), [db.py](../soundkraft/db.py))

| Field | Definition |
|---|---|
| `rt_ms` | time from stimulus onset to the committed response (for Corsi: from "Your turn" to the last tap; for Trails: from the previous correct circle to this one) |
| `first_touch_ms` | time from stimulus onset to the first touch anywhere. Used as the decision-latency / hesitation measure. |
| `tap_duration_ms` | time the finger stays down on the committing touch |
| `swipe_ms`, `swipe_px` | duration and distance of the committing swipe (Kitchen Memory in swipe mode) |
| `touch_x`, `touch_y` | position of the committing touch, normalised to 0–1 within the play area |
| `off_target_touches` | touches that hit no target (a motor precision measure) |
| `wrong_taps` | Trail Walk: taps on the wrong circle (a cognitive error, kept separate from motor misses) |
| `timed_out`, `correct`, `error_type` | correctness is decided by the server. `error_type` is one of `wrong`, `timeout` or `swipe_unclear`. |

Timing uses `performance.now()` in the browser, which has sub-millisecond resolution. Actual precision is limited by the display refresh rate (about 16 ms at 60 Hz) and by touchscreen latency. Use the same device model for everyone in the study where possible.

## 5. Session features ([features.py](../soundkraft/features.py))

For each game `g`: `g_accuracy`, `g_median_rt` (correct, non-timeout trials), `g_rt_cv` (coefficient of variation, i.e. intra-individual variability), `g_max_level`, `g_mean_level`, `g_timeout_rate`, and `g_first_touch_ms`.

Game-specific features:

* `nback_hit_rate`, `nback_false_alarm_rate`, `nback_dprime` (log-linear corrected)
* `stroop_interference_ms` (median RT on incongruent trials minus congruent), `stroop_incongruent_accuracy`
* `corsi_span` (longest sequence reproduced correctly)
* `trails_ms_per_step`, `trails_b_ms_per_step`, `trails_errors`

Features across all games: `tap_duration_ms`, `swipe_ms`, `off_target_rate`, `overall_accuracy`.

## 6. Performance Index ([scoring.py](../soundkraft/scoring.py))

Each component is mapped linearly to 0–1 between a "best" and a "worst" anchor and clamped. Each domain score is the weighted mean of its components × 100.

| Domain | Components (weight) |
|---|---|
| Memory | N-back mean level (0.45), accuracy 50→100% (0.35), median RT 3000→700 ms (0.20) |
| Attention | Stroop mean level (0.35), accuracy (0.35), median RT 2800→600 ms (0.30) |
| Spatial | Corsi span 1→9 (0.6), accuracy (0.2), first-touch latency 4000→600 ms (0.2) |
| Planning & switching | Trails mean level (0.4), accuracy (0.3), ms per step 5000→700 (0.3) |

The index is the mean of the available domain scores. These weights are **uncalibrated defaults**. The validation study's correlation analysis is how to justify or revise them.

## 7. Trend detection ([trends.py](../soundkraft/trends.py))

* Baseline = mean of sessions 1–3.
* Baseline SD = the SD of those 3 sessions, with a floor of 4 points so that an unusually steady baseline does not make small dips look large.
* Recent = mean of the last 3 sessions.
* Slope = least-squares linear regression of the index against session number (`scipy.stats.linregress`).

The thresholds for each status are in the README. The same rules also run separately for each domain.

Practice effects usually raise scores over the first few sessions, which makes decline detection conservative. Consider one or two practice sessions before the baseline in the study protocol.

## 8. Calibration ([calibration.py](../soundkraft/calibration.py))

1. Each reference score is paired with the same person's finished session that is closest in time (at most 30 days apart).
2. Candidate features must be present for at least 80% of participants and must vary. The composite index is excluded.
3. Leave-one-out cross-validation. Inside each fold:
   * select the top *k* features (default 6) by |Spearman ρ| with p < 0.10
   * fit `SimpleImputer → StandardScaler → RidgeCV` (or a random forest)
   * if at least 3 participants fall on each side of the cut-off, also fit a logistic-regression classifier for "below cut-off" (MoCA < 26, MMSE < 24)
4. Reported metrics: LOOCV MAE and Pearson r for the regression; LOOCV AUC, sensitivity and specificity (at p = 0.5) for the classifier. The final model is refit on all participants.
