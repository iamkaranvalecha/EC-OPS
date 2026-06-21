from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.schemas import TokenResponse, UserCreate, UserResponse
from src.auth.service import (
    authenticate_user,
    create_access_token,
    create_user,
    get_user_by_username,
)
from src.core.dependencies import get_session

router = APIRouter(prefix="/auth", tags=["auth"])

logger = logging.getLogger(__name__)


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(
    data: UserCreate,
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    existing = await get_user_by_username(data.username, session)
    if existing is not None:
        logger.warning("register rejected: username %r already taken", data.username)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{data.username}' is already taken",
        )
    user = await create_user(data, session)
    logger.info("user registered: id=%s username=%r", user.id, user.username)
    return UserResponse.model_validate(user)


@router.post("/token", response_model=TokenResponse)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    user = await authenticate_user(form.username, form.password, session)
    if user is None:
        logger.warning("login failed: username=%r", form.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(user.id, user.username)
    logger.info("login success: id=%s username=%r", user.id, user.username)
    return TokenResponse(access_token=token)
