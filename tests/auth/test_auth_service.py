from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from jose import JWTError

from src.auth.models import User
from src.auth.service import (
    authenticate_user,
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_hash_and_verify_password():
    hashed = hash_password("mysecret")
    assert hashed != "mysecret"
    assert verify_password("mysecret", hashed)
    assert not verify_password("wrong", hashed)


def test_create_and_decode_token():
    uid = uuid.uuid4()
    token = create_access_token(uid, "alice")
    payload = decode_token(token)
    assert payload["sub"] == str(uid)
    assert payload["username"] == "alice"


def test_decode_token_rejects_tampered():
    uid = uuid.uuid4()
    token = create_access_token(uid, "alice")
    # Corrupt the signature
    tampered = token[:-4] + "XXXX"
    with pytest.raises(JWTError):
        decode_token(tampered)


# ── authenticate_user ─────────────────────────────────────────────────────────

def _mock_session(user: User | None) -> AsyncMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.mark.asyncio
async def test_authenticate_user_success():
    user = User(
        id=uuid.uuid4(),
        username="alice",
        hashed_password=hash_password("correctpass"),
        is_active=True,
    )
    result = await authenticate_user("alice", "correctpass", _mock_session(user))
    assert result is user


@pytest.mark.asyncio
async def test_authenticate_user_wrong_password_returns_none():
    user = User(
        id=uuid.uuid4(),
        username="alice",
        hashed_password=hash_password("correctpass"),
        is_active=True,
    )
    result = await authenticate_user("alice", "wrongpass", _mock_session(user))
    assert result is None


@pytest.mark.asyncio
async def test_authenticate_user_inactive_returns_none():
    """A deactivated account must not authenticate even with the correct password."""
    user = User(
        id=uuid.uuid4(),
        username="inactive",
        hashed_password=hash_password("password123"),
        is_active=False,
    )
    result = await authenticate_user("inactive", "password123", _mock_session(user))
    assert result is None


@pytest.mark.asyncio
async def test_authenticate_user_nonexistent_returns_none():
    result = await authenticate_user("nobody", "anypass", _mock_session(None))
    assert result is None
