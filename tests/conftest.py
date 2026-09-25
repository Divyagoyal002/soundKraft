import random
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from soundkraft import db
from soundkraft.app import create_app


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "test.db")
    yield c
    c.close()


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path / "app.db")
    with TestClient(app) as c:
        c.conn = app.state.conn
        yield c


@pytest.fixture
def cohort(conn):
    """A small synthetic cohort (8 sessions each) built through the real service layer."""
    from scripts.simulate import simulate_person

    rng = random.Random(3)
    start = datetime.now(timezone.utc) - timedelta(days=30)
    people = [simulate_person(conn, rng, i + 1, 8, start) for i in range(12)]
    return people
