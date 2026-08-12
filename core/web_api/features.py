"""HTTP contracts for memories, local models and voice output."""

from __future__ import annotations

import base64
import binascii

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from core.config import GGUF_MODELS
from core.model_catalog import get_model_spec
from core.tts import friendly_tts_error

router = APIRouter(tags=["assistant features"])


class MemoryCreateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2_000)


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5_000)


class VoiceTranscriptionRequest(BaseModel):
    audio_base64: str = Field(min_length=1, max_length=6_000_000)
    mime_type: str = Field(default="audio/wav", max_length=100)


@router.get("/memories")
def list_memories(request: Request) -> dict:
    memories = request.app.state.memory_service.get_all()
    items = []
    for index, memory in enumerate(memories):
        if isinstance(memory, dict):
            text = str(memory.get("texto", "")).strip()
            date = str(memory.get("data", "")).strip()
        else:
            text = str(memory).strip()
            date = ""
        if text:
            items.append({"index": index, "text": text, "date": date})
    return {"ok": True, "items": items, "count": len(items)}


@router.post("/memories", status_code=status.HTTP_201_CREATED)
def add_memory(payload: MemoryCreateRequest, request: Request) -> dict:
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="A memoria nao pode estar vazia.")
    existing = {
        str(item.get("texto", "")).strip().casefold()
        for item in request.app.state.memory_service.get_all()
        if isinstance(item, dict)
    }
    if text.casefold() in existing:
        raise HTTPException(status_code=409, detail="Esta memoria ja foi cadastrada.")
    try:
        memory = request.app.state.memory_service.add(text)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Nao foi possivel salvar a memoria: {exc}",
        ) from exc
    return {
        "ok": True,
        "memory": {
            "text": memory.get("texto", text),
            "date": memory.get("data", ""),
        },
    }


@router.get("/models")
def list_models(request: Request) -> dict:
    settings = request.app.state.settings
    items = []
    for model in GGUF_MODELS:
        model_path = settings.get_model_path(model.id)
        installed = model_path.is_file()
        projector_ready = not model.has_mmproj or settings.get_mmproj_path(model.id) is not None
        spec = get_model_spec(model.id)
        items.append(
            {
                "id": model.id,
                "name": model.name,
                "display_name": model.display_name,
                "category": model.category,
                "quant": model.quant,
                "size_gb": model.size_gb,
                "installed": installed,
                "ready": installed and projector_ready,
                "role": spec.role if spec else model.category,
                "notes": spec.notes if spec else "",
            }
        )
    return {
        "ok": True,
        "current": settings.llm_model,
        "automatic_routing": True,
        "items": items,
    }


@router.get("/voice")
def voice_capabilities(request: Request) -> dict:
    settings = request.app.state.settings
    provider = settings.voice.provider
    return {
        "ok": True,
        "provider": provider,
        "profile": settings.voice.profile,
        "voice": settings.voice.voice,
        "available": True,
        "requires_internet": provider == "edge-tts",
        "jarvis": {
            "available": True,
            "default_enabled": settings.ui.jarvis_enabled,
            "fps": settings.ui.jarvis_fps,
            "particle_count": settings.ui.jarvis_particle_count,
        },
    }


@router.post("/voice/synthesize")
async def synthesize_voice(payload: SpeechRequest, request: Request) -> Response:
    try:
        audio = await request.app.state.tts_provider.synthesize(payload.text.strip())
    except Exception as exc:
        raise HTTPException(status_code=503, detail=friendly_tts_error(exc)) from exc
    if not audio:
        raise HTTPException(status_code=503, detail="O mecanismo de voz nao retornou audio.")
    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "no-store",
            "X-Celsius-External-Service": str(
                request.app.state.settings.voice.provider == "edge-tts"
            ).lower(),
        },
    )


@router.post("/voice/transcribe")
def transcribe_voice(payload: VoiceTranscriptionRequest, request: Request) -> dict:
    if payload.mime_type.split(";", 1)[0].strip().lower() not in {
        "audio/wav",
        "audio/wave",
        "audio/x-wav",
    }:
        raise HTTPException(
            status_code=415,
            detail="Envie o audio do navegador no formato WAV.",
        )
    try:
        audio = base64.b64decode(payload.audio_base64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(status_code=400, detail="Audio codificado invalido.") from exc
    if not audio or len(audio) > 4_000_000:
        raise HTTPException(status_code=413, detail="Audio vazio ou maior que o limite local.")

    from core.mobile_voice import transcribe_mobile_wav

    try:
        transcript = transcribe_mobile_wav(
            audio,
            model_name=request.app.state.settings.model.whisper_model,
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "ok": True,
        "transcript": transcript,
        "processing_mode": "local",
    }
