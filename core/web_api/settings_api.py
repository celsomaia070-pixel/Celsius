"""HTTP API for global and user settings persistence."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, StrictBool

from core.mobile_access import rotate_mobile_token
from core.modules import (
    MANDATORY_MODULE_IDS,
    MODULE_CATALOG,
    get_module_definition,
    normalize_module_ids,
    suggest_modules_for_company,
)
from core.tts import available_tts_profiles

router = APIRouter(tags=["settings"])


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def _get_current_user(request: Request) -> Any:
    """Return the authenticated user from bearer token, or raise 401."""
    auth = request.headers.get("Authorization", "")
    token = ""
    if auth.startswith("Bearer "):
        token = auth[7:].strip()
    if not token:
        token = request.cookies.get("access_token", "")
    if not token:
        raise HTTPException(status_code=401, detail="Token de autenticacao nao fornecido.")
    user = request.app.state.user_service.validate_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Token invalido ou expirado.")
    return user


# ──────────────────────────────────────────────
# Schemas — match ConfiguracoesDialog field order
# ──────────────────────────────────────────────


class CustomerPayload(BaseModel):
    user_name: str = ""
    company_name: str = ""
    company_sector: str = ""
    company_size: str = ""
    company_description: str = ""
    user_role: str = ""
    preferred_tone: str = "profissional e direto"
    business_context: str = ""
    main_needs: str = ""
    timezone: str = "America/Sao_Paulo"
    local_offline_required: bool = True


class ResponseStylePayload(BaseModel):
    mode: str = "natural"
    detail_level: str = "detalhado"
    temperature: float = 0.45
    top_p: float = 0.9
    short_answer_max_chars: int = 320
    max_simple_sentences: int = 5


class VoicePayload(BaseModel):
    enabled: bool = True
    provider: str = "edge-tts"
    profile: str = "natural_male_br"
    voice: str = "pt-BR-AntonioNeural"
    rate: str = "+5%"
    pitch: str = "-2Hz"
    volume: str = "+0%"


class MobilePayload(BaseModel):
    enabled: bool = False
    host: str = "0.0.0.0"  # nosec B104 - configuration value; LAN still requires opt-in
    port: int = 8787
    pairing_token: str = ""
    allow_lan: bool = False
    voice_commands_enabled: bool = True
    use_https: bool = True


class NotificationsPayload(BaseModel):
    enabled: bool = False
    external_services_allowed: bool = False
    require_confirmation: bool = True
    default_channel: str = "whatsapp"
    whatsapp_provider: str = "meta_cloud_api"
    whatsapp_phone_number_id: str = ""
    whatsapp_token_env_var: str = ""
    email_provider: str = ""
    email_from: str = ""
    sms_provider: str = ""
    sms_sender_id: str = ""


class SecurityPayload(BaseModel):
    allowed_file_roots: list[str] = []


class ModuleInfo(BaseModel):
    id: str
    name: str
    mandatory: bool = False
    description: str = ""
    status: str = ""
    enabled: bool = True
    show_in_sidebar: bool = True
    sidebar_visible: bool | None = None
    config: dict[str, Any] | None = None


class SettingsPayload(BaseModel):
    customer: CustomerPayload
    response: ResponseStylePayload
    voice: VoicePayload
    mobile: MobilePayload
    notifications: NotificationsPayload
    security: SecurityPayload
    modules: dict[str, ModuleInfo] | None = None


class SidebarPreferencesPayload(BaseModel):
    enabled: list[str] | None = None
    sidebar_visible: dict[str, StrictBool] = Field(default_factory=dict)
    show_memories: StrictBool | None = None
    show_conversations: StrictBool | None = None


@router.patch("/settings/sidebar")
async def patch_sidebar_preferences(
    payload: SidebarPreferencesPayload,
    request: Request,
    user: Any = Depends(_get_current_user),
) -> dict[str, Any]:
    """Store a menu preference for this account; never alter company data or roles."""
    changes = payload.model_dump(exclude_none=True, exclude_unset=True)
    module_ids = set(payload.sidebar_visible) | set(payload.enabled or [])
    if any(get_module_definition(module_id) is None for module_id in module_ids):
        raise HTTPException(status_code=422, detail="Modulo desconhecido.")
    if payload.enabled is not None:
        changes["enabled"] = normalize_module_ids(payload.enabled)
    if "sidebar_visible" in changes:
        for module_id in MANDATORY_MODULE_IDS:
            changes["sidebar_visible"][module_id] = True
    updated = request.app.state.user_service.update_sidebar_preferences(user.id, changes)
    request.app.state.event_hub.publish("sidebar.updated", {"user_id": user.id})
    return {"ok": True, "preferences": updated.sidebar_preferences}


# ──────────────────────────────────────────────
# GET /settings — return full payload
# ──────────────────────────────────────────────


@router.get("/settings", tags=["settings"])
async def get_settings_endpoint(request: Request) -> dict[str, Any]:
    """Return the full settings payload mirroring the ConfiguracoesDialog."""
    settings = request.app.state.settings

    # Customer — use model fields directly (BaseSettings has model_dump)
    customer = settings.customer
    customer_payload = CustomerPayload(
        user_name=customer.user_name,
        company_name=getattr(customer, "company_name", "") or "",
        company_sector=getattr(customer, "company_sector", "") or "",
        company_size=getattr(customer, "company_size", "") or "",
        company_description=getattr(customer, "company_description", "") or "",
        user_role=getattr(customer, "user_role", "") or "",
        preferred_tone=getattr(customer, "preferred_tone", "profissional e direto") or "",
        business_context=getattr(customer, "business_context", "") or "",
        main_needs=getattr(customer, "main_needs", "") or "",
        timezone=getattr(customer, "timezone", "America/Sao_Paulo") or "",
        local_offline_required=bool(getattr(customer, "local_offline_required", True)),
    )

    # Response style
    response = settings.response
    response_payload = ResponseStylePayload(
        mode=getattr(response, "mode", "natural") or "natural",
        detail_level=getattr(response, "detail_level", "detalhado") or "detalhado",
        temperature=float(getattr(response, "temperature", 0.45) or 0.45),
        top_p=float(getattr(response, "top_p", 0.9) or 0.9),
        short_answer_max_chars=int(getattr(response, "short_answer_max_chars", 320) or 320),
        max_simple_sentences=int(getattr(response, "max_simple_sentences", 5) or 5),
    )

    # Voice
    voice = settings.voice
    voice_payload = VoicePayload(
        enabled=bool(getattr(voice, "enabled", True)),
        provider=getattr(voice, "provider", "edge-tts") or "edge-tts",
        profile=getattr(voice, "profile", "natural_male_br") or "natural_male_br",
        voice=getattr(voice, "voice", "pt-BR-AntonioNeural") or "pt-BR-AntonioNeural",
        rate=getattr(voice, "rate", "+5%") or "+5%",
        pitch=getattr(voice, "pitch", "-2Hz") or "-2Hz",
        volume=getattr(voice, "volume", "+0%") or "+0%",
    )

    # Mobile
    mobile = settings.mobile
    mobile_payload = MobilePayload(
        enabled=bool(getattr(mobile, "enabled", False)),
        host=getattr(mobile, "host", "0.0.0.0") or "0.0.0.0",  # nosec B104
        port=int(getattr(mobile, "port", 8787) or 8787),
        pairing_token=getattr(mobile, "pairing_token", "") or "",
        allow_lan=bool(getattr(mobile, "allow_lan", False)),
        voice_commands_enabled=bool(getattr(mobile, "voice_commands_enabled", True)),
        use_https=bool(getattr(mobile, "use_https", True)),
    )

    # Notifications
    notif = settings.notifications
    notifications_payload = NotificationsPayload(
        enabled=bool(getattr(notif, "enabled", False)),
        external_services_allowed=bool(getattr(notif, "external_services_allowed", False)),
        require_confirmation=bool(getattr(notif, "require_confirmation", True)),
        default_channel=getattr(notif, "default_channel", "whatsapp") or "whatsapp",
        whatsapp_provider=getattr(notif, "whatsapp_provider", "meta_cloud_api") or "meta_cloud_api",
        whatsapp_phone_number_id=getattr(notif, "whatsapp_phone_number_id", "") or "",
        whatsapp_token_env_var=getattr(notif, "whatsapp_token_env_var", "") or "",
        email_provider=getattr(notif, "email_provider", "") or "",
        email_from=getattr(notif, "email_from", "") or "",
        sms_provider=getattr(notif, "sms_provider", "") or "",
        sms_sender_id=getattr(notif, "sms_sender_id", "") or "",
    )

    # Security — allowed file roots
    security = settings.security
    allowed_roots = getattr(security, "allowed_file_roots", ())
    allowed_roots_list = list(allowed_roots) if allowed_roots else []

    # Modules map from core.modules.MODULE_CATALOG
    enabled_ids = (
        normalize_module_ids(settings.modules.enabled)
        if hasattr(settings.modules, "enabled")
        else []
    )
    modules_map: dict[str, ModuleInfo] = {}
    for module in MODULE_CATALOG:
        modules_map[module.id] = ModuleInfo(
            id=module.id,
            name=module.name,
            mandatory=module.mandatory,
            description=module.description,
            status=module.status,
            enabled=module.id in enabled_ids,
            show_in_sidebar=module.show_in_sidebar,
            sidebar_visible=settings.modules.sidebar_visible.get(module.id, True),
            config=dict(module.config) if module.config else None,
        )

    # Voice profiles from core.tts
    tts_profiles: list[dict[str, Any]] = []
    for profile in available_tts_profiles(None):
        tts_profiles.append(
            {
                "id": profile.id,
                "name": profile.name,
                "provider": profile.provider,
                "voice": profile.voice,
                "rate": profile.rate,
                "pitch": profile.pitch,
                "volume": profile.volume,
                "description": profile.description,
                "experimental": profile.experimental,
            }
        )

    return {
        "ok": True,
        "customer": customer_payload.model_dump(),
        "response": response_payload.model_dump(),
        "voice": voice_payload.model_dump(),
        "mobile": mobile_payload.model_dump(),
        "notifications": notifications_payload.model_dump(),
        "security": {"allowed_file_roots": allowed_roots_list},
        "modules": modules_map,
        "voice_profiles": tts_profiles,
    }


# ──────────────────────────────────────────────
# PUT /settings — persist payload
# ──────────────────────────────────────────────


@router.put("/settings", tags=["settings"])
async def put_settings_endpoint(
    payload: SettingsPayload,
    request: Request,
    user: Any = Depends(_get_current_user),
) -> dict[str, Any]:
    """Persist settings payload. Matches the ConfiguracoesDialog field layout."""
    settings = request.app.state.settings

    # --- Customer ---
    customer_data = payload.customer.model_dump()
    settings.customer.apply_storage(customer_data, preserve_explicit=True)
    settings.assistant.owner_name = settings.customer.user_name

    # --- Response style ---
    response_data = payload.response.model_dump()
    settings.response.apply_storage(response_data, preserve_explicit=True)

    # --- Voice ---
    voice_data = payload.voice.model_dump()
    settings.voice.apply_storage(voice_data, preserve_explicit=True)

    # --- Mobile ---
    mobile_data = payload.mobile.model_dump()
    settings.mobile.apply_storage(mobile_data, preserve_explicit=True)

    # --- Notifications ---
    notif_data = payload.notifications.model_dump()
    settings.notifications.apply_storage(notif_data, preserve_explicit=True)

    # --- Security (allowed file roots) ---
    security_data = payload.security.model_dump()
    settings.security.apply_storage(security_data, preserve_explicit=True)

    # --- Modules ---
    # Collect enabled ids from the payload.modules dict
    enabled_ids: list[str] = []
    for module_def in (payload.modules or {}).values():
        if getattr(module_def, "enabled", False):
            enabled_ids.append(module_def.id)
        if module_def.sidebar_visible is not None:
            settings.modules.sidebar_visible[module_def.id] = (
                True if module_def.mandatory else module_def.sidebar_visible
            )
    # Normalize and apply
    if payload.modules is not None:
        settings.modules.set_enabled(enabled_ids)

    # Persist to disk
    settings.save_customer_profile()
    settings.save_local_preferences()

    return {"ok": True}


# ──────────────────────────────────────────────
# POST /settings/modules/suggest
# ──────────────────────────────────────────────


@router.post("/modules/suggest", tags=["settings"])
async def post_modules_suggest(
    request: Request,
    segment: str = "",
    needs: list[str] | None = None,
    user: Any = Depends(_get_current_user),
) -> dict[str, Any]:
    """Return suggested module ids based on segment/needs (mirrors desktop 'Sugerir modulos')."""
    suggested = suggest_modules_for_company(segment=segment, needs=needs or [])
    return {"ok": True, "suggested": suggested}


# ──────────────────────────────────────────────
# POST /settings/mobile/token/regenerate
# ──────────────────────────────────────────────


@router.post("/mobile/token/regenerate", tags=["settings"])
async def post_mobile_token_regenerate(
    request: Request,
    user: Any = Depends(_get_current_user),
) -> dict[str, Any]:
    """Regenerate the mobile pairing token and persist settings."""
    settings = request.app.state.settings
    new_token = rotate_mobile_token(settings=settings, current=settings.mobile.pairing_token)
    settings.mobile.pairing_token = new_token
    settings.save_local_preferences()
    return {"ok": True, "pairing_token": new_token}


# ──────────────────────────────────────────────
# POST /settings/mobile/restart
# ──────────────────────────────────────────────


@router.post("/mobile/restart", tags=["settings"])
async def post_mobile_restart(
    request: Request,
    user: Any = Depends(_get_current_user),
) -> dict[str, Any]:
    """Restart the local mobile access server (mirrors desktop gear 'Reiniciar acesso')."""
    ensure_mobile_access = request.app.state.ensure_mobile_access
    server = ensure_mobile_access(allow_lan=False)
    from urllib.parse import urlencode

    from core.mobile_access import get_lan_ip

    pairing_code = request.app.state.browser_sessions.issue_pairing_code()
    query = urlencode({"pair": pairing_code})
    lan_ip = get_lan_ip()
    https = bool(server.use_https)
    authority = lan_ip if https else "127.0.0.1"
    url = f"{'https' if https else 'http'}://{authority}:{server.port}/?{query}"

    return {
        "ok": True,
        "message": "Acesso mobile reiniciado.",
        "pairing_code": pairing_code,
        "lan_ip": lan_ip,
        "server_url": url,
    }
