# SoundKraft

**A gamified, sensory-adaptive system for early screening and tracking of cognitive change in older adults.**

SoundKraft offers four short brain games (about 10 minutes a day). While people play, it records how they answer: accuracy, response time, hesitation, and tap and swipe dynamics. Over many sessions it compares each person with their own usual level, and a caregiver or clinician dashboard flags sustained declines.

> ⚠️ **SoundKraft is a research prototype for screening and tracking only. It does not diagnose any condition.**
> Every output is framed as a tracking indicator that should prompt a conversation with a qualified health professional.

---

## Quick start

Requires Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

# optional: synthetic demo players, so the dashboard has something to show
python -m scripts.simulate --players 24 --sessions 12
python -m scripts.calibrate          # trains the demo calibration model

uvicorn soundkraft.app:app --host 0.0.0.0 --port 8000
```

* Player app: <http://localhost:8000>. On a tablet on the same Wi-Fi, use `http://<computer-ip>:8000`.
* Caregiver/clinician dashboard: <http://localhost:8000/dashboard>. The default PIN is `2468`. **Change it** with the `SOUNDKRAFT_DASHBOARD_PIN` environment variable.
* Run the tests with `pytest`.

| Environment variable | Default | Purpose |
|---|---|---|
| `SOUNDKRAFT_DB` | `data/soundkraft.db` | SQLite database file |
| `SOUNDKRAFT_MODEL` | `models/calibration.joblib` | trained calibration model |
| `SOUNDKRAFT_DASHBOARD_PIN` | `2468` | dashboard PIN |
| `SOUNDKRAFT_SECRET_KEY` | dev value | signs the dashboard login cookie; set a long random value |

To remove the demo data, run `python -m scripts.simulate --clear`.

---

## What it does (mapped to the requirement document)

| Req. | How SoundKraft meets it |
|---|---|
| **FR-1** game battery | Four games, one per domain: **Kitchen Memory** (N-back, working memory), **Colour Clash** (Stroop, attention/inhibition), **Garden Path** (Corsi blocks, spatial memory), **Trail Walk** (Trail Making A/B, executive function) |
| **FR-2** behavioural metrics | Per trial: response time, correctness, error type, time to first touch (hesitation), tap duration, swipe time and distance, touch position, and off-target touches (see [docs/METHODS.md](docs/METHODS.md)) |
| **FR-3** adaptive difficulty | A rules-based staircase moves the level up or down after each round ([soundkraft/adaptive.py](soundkraft/adaptive.py)) |
| **FR-4** sensory adaptation | A first-run profile sets text size, contrast, a hearing check and a swipe test. Players can change text size, button size, contrast, pace, swipe or tap input, feedback sounds and spoken instructions. During play, SoundKraft also changes settings **automatically**: frequent timeouts slow the pace, off-target touches enlarge buttons, and unclear swipes switch input to buttons. Every automatic change is logged ([soundkraft/sensory.py](soundkraft/sensory.py)) |
| **FR-5** composite score + calibration | A 0–100 Performance Index built from four domain scores. A calibration pipeline correlates features with MoCA/MMSE and trains a ridge or random-forest model with leave-one-out validation ([soundkraft/calibration.py](soundkraft/calibration.py)) |
| **FR-6** longitudinal storage | Every session, round and trial is stored in SQLite. Trend detection compares each person with their own baseline ([soundkraft/trends.py](soundkraft/trends.py)) |
| **FR-7** dashboard | PIN-protected. Shows status per player, trend charts overall and per skill, a sessions table, entry of reference scores, CSV/JSON export, and withdrawal/deletion |
| **FR-8** non-diagnostic | Players only ever see points and stars. The dashboard uses screening language ("Steady", "Watch", "Discuss with a professional") and a disclaimer appears on every page |

Non-functional: large touch targets, high-contrast mode, light and dark themes, reduced-motion support, sessions of about 8–12 minutes, points, stars and levels for engagement, and results shared only with consent.

---

## How it works

```
 Tablet browser (HTML/JS)                 Python (FastAPI)
 ┌──────────────────────────┐   JSON   ┌───────────────────────────────────────┐
 │ play.js  session runner  │ ───────► │ service.py   session workflow         │
 │ games/*.js render+timing │ ◄─────── │ games.py     stimulus generation      │
 │ core.js  touch recorder, │          │ adaptive.py  difficulty staircase     │
 │          audio, speech   │          │ sensory.py   accessibility inference  │
 └──────────────────────────┘          │ features.py  trial logs → features    │
                                       │ scoring.py   Performance Index        │
 Dashboard (server-rendered) ◄──────── │ trends.py    decline detection        │
                                       │ calibration.py  MoCA/MMSE model       │
                                       │ db.py        SQLite                   │
                                       └───────────────────────────────────────┘
```

* **Python owns all the logic.** It generates every round's stimuli from a seed so rounds are reproducible, decides correctness (it never trusts the browser's claim), picks the next level and adapts settings. The browser only renders the game and measures timing.
* **Session flow:** `POST /api/sessions` → for each game and round: `POST /api/sessions/{id}/rounds`, then `POST /api/rounds/{id}/results` → `POST /api/sessions/{id}/finish`, which computes the features and the Performance Index.

### Performance Index and trend flags

Each domain score (0–100) combines the level reached, accuracy and speed. The Performance Index is the mean of the four domain scores. Before calibration these weights are transparent, hand-set defaults ([soundkraft/scoring.py](soundkraft/scoring.py)).

Trend status compares the **mean of the last 3 sessions** with the **baseline** (the first 3 sessions) and checks the slope across all sessions:

| Status | Rule |
|---|---|
| Building baseline | fewer than 6 sessions |
| Steady | no sustained drop |
| Watch | drop ≥ 1 baseline SD, **or** a negative slope with p < 0.10 |
| Discuss with a professional | drop ≥ 2 baseline SD **and** a negative slope with p < 0.05 |

A single bad day never produces the strongest flag.

---

## Running the validation study

1. **Before recruiting:** get ethics/consent approval (see *Ethics* below). Register for MoCA at mocacognition.com, which is free for academic, non-commercial use.
2. **Each participant:** a guardian or family member helps where appropriate. The participant joins in the app (the consent screen is built in), completes one full SoundKraft session, and a trained administrator gives the MoCA in the **same visit**.
3. **Enter the MoCA score** on the participant's dashboard page (*Reference screening scores*).
4. **Analyse:**
   ```bash
   python -m scripts.calibrate --real-only          # correlations + model, real participants only
   python -m scripts.export_data --real-only        # CSVs in exports/ for your own analysis in pandas/R/Excel
   ```
   `calibrate` prints Pearson and Spearman correlations for every feature (also saved to `exports/calibration_correlations.csv`). It then trains the model and reports leave-one-out error, AUC, sensitivity and specificity. **Feature selection is repeated inside every cross-validation fold**, so the small sample does not inflate the reported accuracy.
5. With 15–30 participants, report results as **preliminary and exploratory**. State the sample size and the limitations.

The simulated demo data (`scripts/simulate.py`) exists **only to test the software**. Its correlations are built in by design and must never be reported as findings.

---

## Ethics, privacy and IRIS compliance

* Informed consent is required before anyone can play, and sharing with the caregiver dashboard is a separate opt-in.
* The dashboard is PIN-protected and lists only players who agreed to share. Withdrawal deletes all of that person's data.
* Data stays on the machine running the server (`data/`), which is git-ignored. Participant data must **never** be committed or uploaded.
* Exports use numeric IDs, not names.
* Never describe SoundKraft's output as a diagnosis, in the app, paper, abstract or video. Do not show school, city or state names in any materials.
* This prototype has no per-user accounts. Run it only on a trusted device or network during the study.

---

## Project layout

```
soundkraft/            Python package (FastAPI app + all logic)
  templates/           Jinja2 pages (player app + dashboard)
  static/js/games/     the four mini-games (rendering + timing only)
scripts/
  simulate.py          synthetic demo cohort (software testing only)
  calibrate.py         correlation analysis + model training
  export_data.py       CSV export for analysis
tests/                 pytest suite (unit + full HTTP flow)
docs/METHODS.md        task parameters, feature dictionary, scoring details
```

## References

See section 11 of the project requirement document. Key sources: the gamified N-back/MMSE study (PMC11799731), Neuro-World (medRxiv 2025), the GOAL trial (NCT03383549), Smart Ageing (UPC), and Choi (2016).
