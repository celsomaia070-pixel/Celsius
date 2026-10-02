"""Authenticated lifecycle controls; QR codes and session data are never public."""

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from core.web_api.settings_api import _get_current_user

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])
CurrentUser = Annotated[Any, Depends(_get_current_user)]


def owned_service(request, user):
    service = request.app.state.whatsapp_service
    if service.config.get("owner_id") not in (None, "", user.id):
        raise HTTPException(status_code=403, detail="A conexão WhatsApp pertence a outra conta do Celsius.")
    return service


@router.get("/status")
async def whatsapp_status(request: Request, user: CurrentUser):
    return {"ok": True, **owned_service(request, user).status(include_qr=True)}


@router.post("/connect", status_code=202)
async def whatsapp_connect(request: Request, user: CurrentUser):
    service = owned_service(request, user)
    try:
        result = await asyncio.to_thread(service.start, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (OSError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"ok": True, **result}


@router.post("/pause")
async def whatsapp_pause(request: Request, user: CurrentUser):
    await asyncio.to_thread(owned_service(request, user).pause)
    return {"ok": True}


@router.post("/self-chat")
async def whatsapp_self_chat(request: Request, user: CurrentUser):
    try:
        result = await asyncio.to_thread(owned_service(request, user).open_self_chat, resend=True)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (RuntimeError, OSError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"ok": True, **result}


@router.post("/logout")
async def whatsapp_logout(request: Request, user: CurrentUser):
    try:
        await asyncio.to_thread(owned_service(request, user).logout)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"ok": True}
