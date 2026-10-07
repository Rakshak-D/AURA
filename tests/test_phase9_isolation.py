from pathlib import Path

import pytest

from backend.app import database
from backend.app.config import PROJECT_DIR, config
from backend.app.models.sql_models import User

pytestmark = pytest.mark.unit


def test_api_client_writes_only_to_the_isolated_database(api_client):
    response = api_client.post(
        "/api/auth/register",
        json={"identifier": "isolated@example.com", "password": "correct horse battery"},
    )
    assert response.status_code == 201

    active_database = Path(database.engine.url.database).resolve()
    repository_database = (PROJECT_DIR / "data" / "aura.db").resolve()
    assert active_database != repository_database
    assert active_database.parent.exists()
    assert config.db_path == active_database
    with database.SessionLocal() as db:
        assert db.query(User).count() == 1


def test_each_test_gets_a_fresh_database():
    with database.SessionLocal() as db:
        assert db.query(User).count() == 0
