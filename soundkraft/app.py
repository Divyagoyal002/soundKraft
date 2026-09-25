"""FastAPI application: player pages, game API and the caregiver/clinician dashboard.

Run with:  uvicorn soundkraft.app:app --reload
"""

from __future__ import annotations

import csv
import hmac
import io
import json
from datetime import date
from pathlib import Path

from fastapi import Body, Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from . import __version__, charts, config, db, games, scoring, service, trends
from .settings import DEFAULTS, TEXT_SCALES, normalise

HERE = Path(__file__).resolve().parent


class SessionIn(BaseModel):
    user_id: int
    device: dict = Field(default_factory=dict)


class RoundIn(BaseModel):
    game: str


class ResultsIn(BaseModel):
    trials: list[dict] = Field(max_length=64)


def create_app(db_path: str | Path | None = None) -> FastAPI:
    app = FastAPI(title="SoundKraft", version=__version__)
    app.add_middleware(SessionMiddleware, secret_key=config.SECRET_KEY, same_site="strict",
                       max_age=4 * 3600)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")
    templates.env.globals.update(DISCLAIMER=config.DISCLAIMER, DOMAIN_LABELS=scoring.DOMAIN_LABELS,
                                 STATUS_TEXT=trends.STATUS_TEXT, GAMES=games.GAMES, version=__version__)
    conn = db.connect(db_path)
    app.state.conn = conn

    def get_conn():
        return conn

    def page(request: Request, name: str, **ctx):
        return templates.TemplateResponse(request, name, ctx)

    def require_user(uid: int) -> dict:
        user = db.get_user(conn, uid)
        if not user:
            raise HTTPException(404, "player not found")
        return user

    # ------------------------------------------------------------------ player pages

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        players = [u for u in db.list_users(conn) if not u["is_synthetic"]]
        return page(request, "home.html", players=players)

    @app.get("/about", response_class=HTMLResponse)
    def about(request: Request):
        return page(request, "about.html")

    @app.get("/join", response_class=HTMLResponse)
    def join_form(request: Request):
        return page(request, "join.html", error=None, form={})

    @app.post("/join")
    def join(request: Request, display_name: str = Form(""), birth_year: str = Form(""),
             education_years: str = Form(""), consent: str = Form(""), share: str = Form("")):
        form = {"display_name": display_name, "birth_year": birth_year, "education_years": education_years,
                "share": share}
        name = display_name.strip()[:40]
        error = None
        if not name:
            error = "Please enter a name or nickname."
        elif consent != "yes":
            error = "Please read the information and tick the consent box to continue."
        by = _int_or_none(birth_year, 1900, date.today().year)
        ey = _int_or_none(education_years, 0, 30)
        if birth_year.strip() and by is None:
            error = error or "Birth year does not look right."
        if error:
            return page(request, "join.html", error=error, form=form)
        uid = db.create_user(conn, name, by, ey, dict(DEFAULTS), share_with_caregiver=share == "yes")
        return RedirectResponse(f"/setup/{uid}", status_code=303)

    @app.get("/setup/{uid}", response_class=HTMLResponse)
    def setup(request: Request, uid: int):
        user = require_user(uid)
        return page(request, "setup.html", user=user, settings=normalise(user["settings"]),
                    text_scales=TEXT_SCALES)

    @app.get("/settings/{uid}", response_class=HTMLResponse)
    def settings_page(request: Request, uid: int):
        user = require_user(uid)
        return page(request, "settings.html", user=user, settings=normalise(user["settings"]),
                    text_scales=TEXT_SCALES, saved=request.query_params.get("saved"))

    @app.post("/settings/{uid}")
    async def settings_save(request: Request, uid: int):
        user = require_user(uid)
        form = await request.form()
        raw = {k: form.get(k) for k in DEFAULTS}
        raw["audio_cues"] = form.get("audio_cues") == "on"
        raw["spoken_instructions"] = form.get("spoken_instructions") == "on"
        merged = normalise({**user["settings"], **{k: v for k, v in raw.items() if v is not None}})
        db.update_user_settings(conn, uid, merged)
        return RedirectResponse(f"/settings/{uid}?saved=1", status_code=303)

    @app.get("/play/{uid}", response_class=HTMLResponse)
    def play(request: Request, uid: int):
        user = require_user(uid)
        return page(request, "play.html", user=user, settings=normalise(user["settings"]),
                    total_points=service.total_points(conn, uid),
                    sessions_done=len(db.user_sessions(conn, uid)))

    # ------------------------------------------------------------------ game API

    @app.post("/api/sessions")
    def api_start(body: SessionIn, c=Depends(get_conn)):
        return _call(service.start_session, c, body.user_id, body.device)

    @app.post("/api/sessions/{sid}/rounds")
    def api_round(sid: int, body: RoundIn, c=Depends(get_conn)):
        return _call(service.next_round, c, sid, body.game)

    @app.post("/api/rounds/{rid}/results")
    def api_results(rid: int, body: ResultsIn, c=Depends(get_conn)):
        return _call(service.submit_round, c, rid, body.trials)

    @app.post("/api/sessions/{sid}/finish")
    def api_finish(sid: int, c=Depends(get_conn)):
        return _call(service.finish_session, c, sid)

    @app.put("/api/users/{uid}/settings")
    def api_settings(uid: int, body: dict = Body(...), c=Depends(get_conn)):
        user = require_user(uid)
        merged = normalise({**user["settings"], **body})
        db.update_user_settings(c, uid, merged)
        return merged

    # ------------------------------------------------------------------ caregiver / clinician dashboard

    def authed(request: Request) -> bool:
        return bool(request.session.get("dashboard"))

    def require_auth(request: Request):
        if not authed(request):
            raise HTTPException(303, headers={"Location": "/dashboard/login"})

    def shared_user(uid: int) -> dict:
        user = require_user(uid)
        if not user["share_with_caregiver"]:
            raise HTTPException(403, "this player has not agreed to share results")
        return user

    @app.get("/dashboard/login", response_class=HTMLResponse)
    def login_form(request: Request):
        return page(request, "login.html", error=None)

    @app.post("/dashboard/login")
    def login(request: Request, pin: str = Form("")):
        if hmac.compare_digest(pin.strip().encode(), config.DASHBOARD_PIN.encode()):
            request.session["dashboard"] = True
            return RedirectResponse("/dashboard", status_code=303)
        return page(request, "login.html", error="That PIN is not correct.")

    @app.get("/dashboard/logout")
    def logout(request: Request):
        request.session.clear()
        return RedirectResponse("/", status_code=303)

    @app.get("/dashboard", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
    def dashboard(request: Request):
        rows = []
        for u in db.list_users(conn, shared_only=True):
            rep = service.user_report(conn, u["id"])
            rows.append({"user": u, "trend": rep["trend"], "n": len(rep["series"]),
                         "latest": rep["series"][-1] if rep["series"] else None,
                         "spark": charts.line_chart([(p["date"], p["composite"]) for p in rep["series"]],
                                                    width=160, height=40, compact=True)})
        order = {"follow_up": 0, "watch": 1, "stable": 2, "insufficient_data": 3}
        rows.sort(key=lambda r: (order[r["trend"]["status"]], r["user"]["display_name"].lower()))
        model = scoring.load_model()
        return page(request, "dashboard.html", rows=rows,
                    model=model and {k: model[k] for k in ("instrument", "n", "metrics", "trained_at", "features")})

    @app.get("/dashboard/user/{uid}", response_class=HTMLResponse, dependencies=[Depends(require_auth)])
    def dashboard_user(request: Request, uid: int):
        user = shared_user(uid)
        rep = service.user_report(conn, uid)
        t = rep["trend"]
        band = None
        if "baseline_mean" in t:
            band = (t["baseline_mean"] - t["baseline_sd"], t["baseline_mean"] + t["baseline_sd"])
        main_chart = charts.line_chart([(p["date"], p["composite"]) for p in rep["series"]],
                                       band=band, label="Performance index")
        domain_charts = {
            d: charts.line_chart([(p["date"], p["domains"][d]) for p in rep["series"] if d in p["domains"]],
                                 width=300, height=120, label=scoring.DOMAIN_LABELS[d])
            for d in scoring.DOMAIN_LABELS
        }
        return page(request, "user_report.html", user=user, rep=rep, main_chart=main_chart,
                    domain_charts=domain_charts, today=date.today().isoformat())

    @app.post("/dashboard/user/{uid}/reference", dependencies=[Depends(require_auth)])
    def add_reference(uid: int, instrument: str = Form(...), score: float = Form(...),
                      assessed_at: str = Form(...), notes: str = Form("")):
        shared_user(uid)
        max_score = {"MoCA": 30.0, "MMSE": 30.0}.get(instrument)
        if max_score is None or not 0 <= score <= max_score:
            raise HTTPException(400, "invalid instrument or score")
        try:
            date.fromisoformat(assessed_at)
        except ValueError:
            raise HTTPException(400, "invalid date")
        db.add_reference_score(conn, uid, instrument, score, max_score, assessed_at, notes.strip()[:500] or None)
        return RedirectResponse(f"/dashboard/user/{uid}", status_code=303)

    @app.post("/dashboard/user/{uid}/delete", dependencies=[Depends(require_auth)])
    def delete_player(uid: int, confirm: str = Form("")):
        user = require_user(uid)
        if confirm.strip() != user["display_name"]:
            raise HTTPException(400, "type the player's name exactly to confirm deletion")
        db.delete_user(conn, uid)
        return RedirectResponse("/dashboard", status_code=303)

    @app.get("/dashboard/user/{uid}/trials.csv", dependencies=[Depends(require_auth)])
    def export_trials(uid: int):
        shared_user(uid)
        buf = io.StringIO()
        writer = None
        for s in db.user_sessions(conn, uid, finished_only=False):
            for t in db.session_trials(conn, s["id"]):
                t["stimulus"] = json.dumps(t["stimulus"], ensure_ascii=False)
                t = {"session_id": s["id"], "session_started_at": s["started_at"], **t}
                if writer is None:
                    writer = csv.DictWriter(buf, fieldnames=list(t))
                    writer.writeheader()
                writer.writerow(t)
        return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                                 headers={"Content-Disposition": f'attachment; filename="player{uid}_trials.csv"'})

    @app.get("/dashboard/user/{uid}/sessions.json", dependencies=[Depends(require_auth)])
    def export_sessions(uid: int):
        shared_user(uid)
        return JSONResponse(db.user_sessions(conn, uid),
                            headers={"Content-Disposition": f'attachment; filename="player{uid}_sessions.json"'})

    return app


def _call(fn, *args):
    try:
        return fn(*args)
    except service.NotFound as e:
        raise HTTPException(404, f"{e} not found")
    except ValueError as e:
        raise HTTPException(400, str(e))


def _int_or_none(v: str, lo: int, hi: int) -> int | None:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return n if lo <= n <= hi else None


app = create_app()
