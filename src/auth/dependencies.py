from __future__ import annotations

import uuid

from fastapi import Depends, Header, HTTPException, Query, status
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.auth.service import decode_token, get_user_by_id
from src.core.dependencies import get_session

_CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def _resolve_token(
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None),
) -> str:
    """Extract Bearer token from Authorization header or ?token= query param.

    The query param fallback exists for browser EventSource clients that cannot
    set custom headers.
    """
    if authorization and authorization.startswith("Bearer "):
        return authorization[7:]
    if token:
        return token
    raise _CREDENTIALS_EXCEPTION


async def get_current_user(
    raw_token: str = Depends(_resolve_token),
    session: AsyncSession = Depends(get_session),
) -> User:
    try:
        payload = decode_token(raw_token)
        user_id = uuid.UUID(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise _CREDENTIALS_EXCEPTION

    user = await get_user_by_id(user_id, session)
    if user is None or not user.is_active:
        raise _CREDENTIALS_EXCEPTION
    return user
