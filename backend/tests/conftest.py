from __future__ import annotations

import os

import pytest


TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
if TEST_DATABASE_URL is not None and "supabase" in TEST_DATABASE_URL.lower():
    raise RuntimeError("TEST_DATABASE_URL must not point to Supabase.")

# Prevent app imports from loading the development database when integration
# tests are not configured.
if TEST_DATABASE_URL:
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
else:
    os.environ["DATABASE_URL"] = (
        "postgresql+psycopg://cloudvault:invalid@127.0.0.1:1/cloudvault_test"
    )

os.environ.setdefault("SECRET_KEY", "test-secret-key-with-at-least-32-bytes")
os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:54321")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("SUPABASE_BUCKET", "cloudvault-test")
os.environ.setdefault("TEST_SUPABASE_BUCKET", "cloudvault-test")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app as fastapi_app
import app.models  # noqa: F401


def _require_test_database() -> None:
    if not TEST_DATABASE_URL:
        pytest.skip(
            "Set TEST_DATABASE_URL to a dedicated local PostgreSQL database "
            "before running integration tests."
        )


@pytest.fixture(scope="session")
def test_engine():
    _require_test_database()
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(test_engine):
    test_session = sessionmaker(
        bind=test_engine,
        autoflush=False,
        expire_on_commit=False,
    )

    def override_db():
        db = test_session()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = override_db
    with TestClient(fastapi_app) as test_client:
        yield test_client
    fastapi_app.dependency_overrides.clear()
    with test_engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE shares, files, folders, users "
                "RESTART IDENTITY CASCADE"
            )
        )


@pytest.fixture
def make_user(client):
    def _make_user(
        email: str = "alice@example.com",
        password: str = "password123",
        name: str = "Alice",
    ):
        registered = client.post(
            "/api/auth/register",
            json={"name": name, "email": email, "password": password},
        )
        assert registered.status_code == 201, registered.text

        logged_in = client.post(
            "/api/auth/login",
            data={"username": email, "password": password},
        )
        assert logged_in.status_code == 200, logged_in.text
        token = logged_in.json()["access_token"]
        return {
            "Authorization": f"Bearer {token}",
        }, registered.json()

    return _make_user
