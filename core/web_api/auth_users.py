"""Authentication endpoints for multi-user login, registration, and token management."""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from core.users import User, UserRole

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str = ""


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class UpdateUserRequest(BaseModel):
    display_name: str | None = None
    role: str | None = None
    is_active: bool | None = None


class UpdateProfileRequest(BaseModel):
    display_name: str | None = None
    avatar_url: str | None = None


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: str
    role: str
    is_active: bool
    created_at: str
    updated_at: str
    last_login: str
    avatar_url: str


def _user_to_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role.value,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login=user.last_login,
        avatar_url=user.avatar_url,
    )


async def get_current_user(request: Request) -> User:
    auth_header = request.headers.get("Authorization", "")
    token = ""
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()

    if not token:
        token = request.cookies.get("access_token", "")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticacao nao fornecido.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = request.app.state.user_service.validate_token(token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido ou expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return cast(User, user)


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores.",
        )
    return user


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(body: RegisterRequest, request: Request) -> UserResponse:
    service = request.app.state.user_service
    if service.list_users():
        await require_admin(await get_current_user(request))
    else:
        from core.web_api.auth import credential_is_valid, request_token

        if not credential_is_valid(
            request_token(request),
            access_token=request.app.state.access_token,
            sessions=request.app.state.browser_sessions,
        ):
            raise HTTPException(
                status_code=401, detail="Abra o Celsius neste computador ou use o pareamento."
            )
    try:
        user = service.register(
            email=body.email,
            password=body.password,
            display_name=body.display_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _user_to_response(user)


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response) -> dict[str, Any]:
    service = request.app.state.user_service
    try:
        tokens = service.authenticate(
            email=body.email,
            password=body.password,
            client_key=request.client.host if request.client else "unknown",
        )
    except ValueError as exc:
        status_code = 429 if "Muitas tentativas" in str(exc) else 401
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    response.set_cookie(
        "access_token",
        tokens.access_token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
        max_age=tokens.expires_in,
        path="/",
    )
    response.set_cookie(
        "refresh_token",
        tokens.refresh_token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
        max_age=30 * 24 * 60 * 60,
        path=f"{request.app.state.api_prefix}/auth"
        if hasattr(request.app.state, "api_prefix")
        else "/api/v1/auth",
    )
    return {
        "access_token": tokens.access_token,
        "token_type": tokens.token_type,
        "expires_in": tokens.expires_in,
    }


@router.post("/refresh")
async def refresh_token(
    request: Request, response: Response, body: RefreshRequest | None = None
) -> dict[str, Any]:
    service = request.app.state.user_service
    try:
        refresh_value = (body.refresh_token if body else "") or request.cookies.get(
            "refresh_token", ""
        )
        tokens = service.refresh(refresh_value)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    response.set_cookie(
        "access_token",
        tokens.access_token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
        max_age=tokens.expires_in,
        path="/",
    )
    response.set_cookie(
        "refresh_token",
        tokens.refresh_token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
        max_age=30 * 24 * 60 * 60,
        path="/api/v1/auth",
    )
    return {
        "access_token": tokens.access_token,
        "token_type": tokens.token_type,
        "expires_in": tokens.expires_in,
    }


@router.post("/logout")
async def logout(
    request: Request, response: Response, user: User = Depends(get_current_user)
) -> dict[str, Any]:
    auth_header = request.headers.get("Authorization", "")
    token = (
        auth_header[7:].strip()
        if auth_header.startswith("Bearer ")
        else request.cookies.get("access_token", "")
    )
    if token:
        request.app.state.user_service.logout(token)
    request.app.state.browser_sessions.revoke(request.cookies.get("celsius_session", ""))
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/api/v1/auth")
    response.delete_cookie("celsius_session", path="/")
    return {"ok": True}


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)) -> UserResponse:
    return _user_to_response(user)


@router.put("/me/password")
async def change_my_password(
    body: ChangePasswordRequest, request: Request, user: User = Depends(get_current_user)
) -> dict[str, Any]:
    try:
        request.app.state.user_service.change_password(
            user.id, body.old_password, body.new_password
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@router.put("/me", response_model=UserResponse)
async def update_me(
    body: UpdateProfileRequest, request: Request, user: User = Depends(get_current_user)
) -> UserResponse:
    try:
        user = request.app.state.user_service.update_user(
            user.id,
            display_name=body.display_name,
            avatar_url=body.avatar_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _user_to_response(user)


@router.get("/users", response_model=list[UserResponse])
async def list_users(request: Request, admin: User = Depends(require_admin)) -> list[UserResponse]:
    users = request.app.state.user_service.list_users()
    return [_user_to_response(u) for u in users]


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str, request: Request, admin: User = Depends(require_admin)
) -> UserResponse:
    user = request.app.state.user_service.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado.")
    return _user_to_response(user)


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    body: UpdateUserRequest,
    request: Request,
    admin: User = Depends(require_admin),
) -> UserResponse:
    role = None
    if body.role:
        try:
            role = UserRole(body.role)
        except ValueError:
            raise HTTPException(status_code=400, detail="Role invalida.") from None
    try:
        user = request.app.state.user_service.update_user(
            user_id,
            display_name=body.display_name,
            role=role,
            is_active=body.is_active,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _user_to_response(user)


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str, request: Request, admin: User = Depends(require_admin)
) -> dict[str, Any]:
    ok = request.app.state.user_service.delete_user(user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado.")
    return {"ok": True}
