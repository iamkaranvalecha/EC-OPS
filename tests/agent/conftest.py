from __future__ import annotations

import uuid

import pytest

from src.auth.dependencies import get_current_user
from src.auth.models import User
from src.main import app


@pytest.fixture(autouse=True)
def bypass_auth():
    """Bypass JWT auth for all agent unit tests.

    Agent tests focus on routing and streaming logic with mocked executors —
    they don't exercise the auth layer and don't have a DB session to look up
    users with.  Overriding get_current_user here keeps the tests focused.
    """

    async def _fake_user() -> User:
        return User(id=uuid.uuid4(), username="testuser", hashed_password="", is_active=True)

    app.dependency_overrides[get_current_user] = _fake_user
    yield
    app.dependency_overrides.pop(get_current_user, None)
