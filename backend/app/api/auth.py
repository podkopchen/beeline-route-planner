"""Authentication endpoints for the local RouteFlow dispatcher."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.core.auth_config import auth_config
from app.services.auth import (
    COOKIE_NAME,
    AuthUser,
    authenticate,
    issue_session,
    read_session,
)

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class UserResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str
    display_name: str
    role: str


def user_response(user: AuthUser) -> UserResponse:
    return UserResponse(
        username=user.username, display_name=user.display_name, role=user.role
    )


@router.post("/login", response_model=UserResponse)
def login(payload: LoginRequest, response: Response) -> UserResponse:
    config = auth_config()
    user = authenticate(payload.username.strip(), payload.password, config)
    if user is None:
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    response.set_cookie(
        COOKIE_NAME,
        issue_session(user, config),
        max_age=config.session_ttl_seconds,
        httponly=True,
        secure=config.cookie_secure,
        samesite="lax",
        path="/",
    )
    return user_response(user)


@router.get("/me", response_model=UserResponse)
def me(request: Request) -> UserResponse:
    config = auth_config()
    if not config.enabled:
        return user_response(
            AuthUser(config.username, config.display_name, config.role)
        )
    user = read_session(request.cookies.get(COOKIE_NAME), config)
    if user is None:
        raise HTTPException(status_code=401, detail="Требуется вход")
    return user_response(user)


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")
