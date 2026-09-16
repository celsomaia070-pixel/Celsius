"""Authentication endpoints for multi-user login, registration, and token management."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from core.users import UserRole

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class UpdateUserRequest(BaseModel):
    display_name: str | None = None
    role: str | None = None
    is_active: bool | None = None


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


def _user_to_response(user) -> UserResponse:
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


async def get_current_user(request: Request):
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
    return user


async def require_admin(user=Depends(get_current_user)):
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores.",
        )
    return user


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(body: RegisterRequest, request: Request):
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
async def login(body: LoginRequest, request: Request, response: Response):
    service = request.app.state.user_service
    try:
        tokens = service.authenticate(email=body.email, password=body.password)
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
    return {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "token_type": tokens.token_type,
        "expires_in": tokens.expires_in,
    }


@router.post("/refresh")
async def refresh_token(body: RefreshRequest, request: Request, response: Response):
    service = request.app.state.user_service
    try:
        tokens = service.refresh(body.refresh_token)
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
    return {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "token_type": tokens.token_type,
        "expires_in": tokens.expires_in,
    }


@router.post("/logout")
async def logout(request: Request, response: Response, user=Depends(get_current_user)):
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
    response.delete_cookie("celsius_session", path="/")
    return {"ok": True}


@router.get("/me", response_model=UserResponse)
async def get_me(user=Depends(get_current_user)):
    return _user_to_response(user)


@router.put("/me/password")
async def change_my_password(
    body: ChangePasswordRequest, request: Request, user=Depends(get_current_user)
):
    try:
        request.app.state.user_service.change_password(
            user.id, body.old_password, body.new_password
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@router.get("/users", response_model=list[UserResponse])
async def list_users(request: Request, admin=Depends(require_admin)):
    users = request.app.state.user_service.list_users()
    return [_user_to_response(u) for u in users]


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, request: Request, admin=Depends(require_admin)):
    user = request.app.state.user_service.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado.")
    return _user_to_response(user)


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str, body: UpdateUserRequest, request: Request, admin=Depends(require_admin)
):
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
async def delete_user(user_id: str, request: Request, admin=Depends(require_admin)):
    ok = request.app.state.user_service.delete_user(user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado.")
    return {"ok": True}
