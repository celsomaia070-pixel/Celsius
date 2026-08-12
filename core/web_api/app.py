"""Versioned local API used by the future desktop and mobile web interfaces."""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import logging
import ssl
import threading
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles

from core.agenda import AgendaService, get_agenda_service
from core.business_records import BusinessRecordService
from core.chat_service import ChatCoordinator
from core.documents import DocumentLibraryService, get_document_library_service
from core.memory import MemoryService, get_memory_service
from core.mobile_access import MobileAccessServer, ensure_mobile_certificate
from core.modules import module_catalog
from core.operations import BusinessOperationsService, get_operations_service
from core.relationships import RelationshipService, get_relationship_service
from core.settings import get_settings
from core.tts import TTSVoiceConfig, create_tts_provider
from core.web_api.agenda import agenda_event_payload
from core.web_api.agenda import router as agenda_router
from core.web_api.auth import (
    request_token,
    resolve_access_token,
    token_matches,
    websocket_token,
)
from core.web_api.chat import router as chat_router
from core.web_api.documents import router as documents_router
from core.web_api.events import EventHub, get_event_hub
from core.web_api.features import router as features_router
from core.web_api.mobile import router as mobile_router
from core.web_api.mobile_bridge import MobileChatBridge
from core.web_api.operations import router as operations_router
from core.web_api.relationships import router as relationships_router
from core.web_api.workflows import router as workflows_router
from core.workflows import BusinessWorkflowService, get_workflow_service

API_PREFIX = "/api/v1"
STATIC_DIR = Path(__file__).with_name("static")
logger = logging.getLogger(__name__)
_bearer_auth = HTTPBearer(auto_error=False)
BearerCredentials = Annotated[
    HTTPAuthorizationCredentials | None,
    Depends(_bearer_auth),
]


def _application_version() -> str:
    try:
        return version("celsius")
    except PackageNotFoundError:
        return "1.0.0"


def _module_payload(settings, module) -> dict[str, Any]:
    enabled = settings.modules.is_enabled(module.id)
    sidebar_preference = settings.modules.sidebar_visible.get(module.id, True)
    in_navigation = bool(
        enabled and module.is_ready and module.show_in_sidebar and sidebar_preference
    )
    return {
        "id": module.id,
        "name": module.name,
        "icon": module.icon,
        "description": module.description,
        "status": module.status,
        "enabled": enabled,
        "mandatory": module.mandatory,
        "sidebar_visible": sidebar_preference,
        "in_navigation": in_navigation,
        "route": f"/app/{module.route}" if module.route else "",
        "sensitive_domains": list(module.sensitive_domains),
        "config": dict(module.config),
    }


def _is_loopback_request(request: Request) -> bool:
    host = request.client.host if request.client else ""
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def create_app(
    *,
    settings=None,
    event_hub: EventHub | None = None,
    chat_coordinator: ChatCoordinator | None = None,
    memory_service=None,
    tts_provider=None,
    agenda_service: AgendaService | None = None,
    document_service: DocumentLibraryService | None = None,
    relationship_service: RelationshipService | None = None,
    operations_service: BusinessOperationsService | None = None,
    workflow_service: BusinessWorkflowService | None = None,
    lan_access_enabled: bool = False,
    public_scheme: str = "",
    public_port: int | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    event_hub = event_hub or get_event_hub()
    if memory_service is None:
        memory_service = (
            get_memory_service() if settings is get_settings() else MemoryService(settings)
        )
    chat_coordinator = chat_coordinator or ChatCoordinator(
        settings=settings,
        event_hub=event_hub,
        memory_service=memory_service,
    )
    if getattr(chat_coordinator, "memory_service", None) is None:
        chat_coordinator.memory_service = memory_service
    voice = settings.voice
    tts_provider = tts_provider or create_tts_provider(
        TTSVoiceConfig(
            voice=voice.voice,
            rate=voice.rate,
            pitch=voice.pitch,
            volume=voice.volume,
            provider=voice.provider,
            profile=voice.profile,
        )
    )
    if agenda_service is None:
        agenda_service = (
            get_agenda_service()
            if settings is get_settings()
            else AgendaService(BusinessRecordService(settings=settings))
        )
    if document_service is None:
        document_service = (
            get_document_library_service()
            if settings is get_settings()
            else DocumentLibraryService(settings=settings, event_hub=event_hub)
        )
    elif getattr(document_service, "event_hub", None) is None:
        document_service.event_hub = event_hub
    if relationship_service is None:
        relationship_service = (
            get_relationship_service()
            if settings is get_settings()
            else RelationshipService(settings=settings, event_hub=event_hub)
        )
    elif getattr(relationship_service, "event_hub", None) is None:
        relationship_service.event_hub = event_hub
    if operations_service is None:
        operations_service = (
            get_operations_service()
            if settings is get_settings()
            else BusinessOperationsService(settings=settings, event_hub=event_hub)
        )
    elif getattr(operations_service, "event_hub", None) is None:
        operations_service.event_hub = event_hub
    if workflow_service is None:
        workflow_service = (
            get_workflow_service()
            if settings is get_settings()
            else BusinessWorkflowService(
                settings=settings,
                operations_service=operations_service,
                relationship_service=relationship_service,
                event_hub=event_hub,
            )
        )
    else:
        if getattr(workflow_service, "event_hub", None) is None:
            workflow_service.event_hub = event_hub
    if getattr(workflow_service, "operations_service", None) is None:
        workflow_service.operations_service = operations_service
    if getattr(workflow_service, "relationship_service", None) is None:
        workflow_service.relationship_service = relationship_service
    if getattr(workflow_service, "event_hub", None) is None:
        workflow_service.event_hub = event_hub
    access_token = resolve_access_token(settings)
    mobile_server_lock = threading.Lock()
    mobile_bridge = MobileChatBridge(
        chat_coordinator=chat_coordinator,
        whisper_model=settings.model.whisper_model,
    )

    def ensure_mobile_access() -> MobileAccessServer:
        with mobile_server_lock:
            current = getattr(app.state, "mobile_server", None)
            if current is not None and current.is_running:
                return current

            # This branch is the explicit LAN mode, protected with HTTPS.
            host = (
                "0.0.0.0" if lan_access_enabled else "127.0.0.1"  # nosec B104
            )
            use_https = bool(settings.mobile.use_https)
            cert_file = key_file = None
            if use_https:
                try:
                    cert_file, key_file = ensure_mobile_certificate(
                        Path(settings.data_dir) / "mobile_access"
                    )
                except RuntimeError as exc:
                    logger.warning("HTTPS movel indisponivel: %s", exc)
                    if lan_access_enabled:
                        raise
                    use_https = False

            def build_server(port: int, https: bool) -> MobileAccessServer:
                return MobileAccessServer(
                    host=host,
                    port=port,
                    token=access_token,
                    command_callback=mobile_bridge.handle_command,
                    voice_enabled=bool(settings.mobile.voice_commands_enabled),
                    voice_command_callback=mobile_bridge.handle_voice,
                    use_https=https,
                    cert_file=cert_file if https else None,
                    key_file=key_file if https else None,
                )

            configured_port = int(settings.mobile.port)
            try:
                server = build_server(configured_port, use_https).start()
            except OSError:
                logger.warning(
                    "Porta movel %s ocupada; usando uma porta local livre.", configured_port
                )
                server = build_server(0, use_https).start()
            except (ValueError, ssl.SSLError) as exc:
                if lan_access_enabled:
                    raise RuntimeError("O acesso pela rede local exige HTTPS valido.") from exc
                logger.warning("Falha no HTTPS movel; usando HTTP apenas local: %s", exc)
                server = build_server(configured_port, False).start()

            app.state.mobile_server = server
            return server

    async def watch_agenda_reminders() -> None:
        while True:
            reminders = await asyncio.to_thread(agenda_service.due_reminders)
            for reminder in reminders:
                if reminder.id in pending_agenda_reminders:
                    continue
                pending_agenda_reminders.add(reminder.id)
                event_hub.publish(
                    "agenda.reminder",
                    {"event": agenda_event_payload(reminder)},
                )
            await asyncio.sleep(5)

    async def forward_mobile_responses() -> None:
        async with event_hub.subscribe() as queue:
            while True:
                event = await queue.get()
                server = getattr(app.state, "mobile_server", None)
                if server is None or not server.is_running:
                    continue
                payload = event.get("payload", {})
                if event.get("type") == "chat.completed":
                    text = str(payload.get("text", "")).strip()
                    if not text:
                        continue
                    server.publish_response(text, kind="assistant")
                    try:
                        audio = await tts_provider.synthesize(text)
                        server.publish_audio(audio, mime_type="audio/mpeg")
                    except Exception as exc:
                        logger.warning("Audio movel nao foi gerado: %s", exc)
                elif event.get("type") == "chat.failed":
                    error = str(payload.get("error", "Falha local")).strip()
                    server.publish_response(f"Erro ao responder: {error}", kind="error")

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        reminder_task = asyncio.create_task(watch_agenda_reminders())
        mobile_response_task = asyncio.create_task(forward_mobile_responses())
        try:
            yield
        finally:
            reminder_task.cancel()
            mobile_response_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reminder_task
            with contextlib.suppress(asyncio.CancelledError):
                await mobile_response_task
            mobile_server = getattr(_app.state, "mobile_server", None)
            if mobile_server is not None:
                await asyncio.to_thread(mobile_server.stop)
            chat_coordinator.shutdown()
            document_service.shutdown()

    app = FastAPI(
        title="Celsius Local API",
        version=_application_version(),
        docs_url=None if lan_access_enabled else "/api/docs",
        redoc_url=None,
        openapi_url=None if lan_access_enabled else f"{API_PREFIX}/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.event_hub = event_hub
    app.state.access_token = access_token
    app.state.chat_coordinator = chat_coordinator
    app.state.memory_service = memory_service
    app.state.tts_provider = tts_provider
    app.state.agenda_service = agenda_service
    app.state.document_service = document_service
    app.state.relationship_service = relationship_service
    app.state.operations_service = operations_service
    app.state.workflow_service = workflow_service
    app.state.lan_access_enabled = lan_access_enabled
    app.state.public_scheme = public_scheme
    app.state.public_port = public_port
    app.state.mobile_server = None
    app.state.ensure_mobile_access = ensure_mobile_access
    pending_agenda_reminders: set[str] = set()
    app.state.pending_agenda_reminders = pending_agenda_reminders
    app.mount("/app/assets", StaticFiles(directory=STATIC_DIR), name="web-assets")

    async def require_access(
        request: Request,
        credentials: BearerCredentials,
    ) -> None:
        candidate = credentials.credentials if credentials else request_token(request)
        if not token_matches(candidate, access_token):
            raise HTTPException(status_code=401, detail="Pareamento do Celsius necessario.")

    @app.exception_handler(HTTPException)
    async def http_error_handler(_request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"ok": False, "error": exc.detail},
        )

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/app")

    @app.get("/app", include_in_schema=False)
    @app.get("/app/", include_in_schema=False)
    async def web_app(request: Request):
        paired = token_matches(request_token(request), access_token)
        if not paired and not _is_loopback_request(request):
            raise HTTPException(status_code=401, detail="Pareamento do Celsius necessario.")
        response = FileResponse(STATIC_DIR / "index.html")
        response.set_cookie(
            "celsius_session",
            access_token,
            httponly=True,
            samesite="strict",
            secure=request.url.scheme == "https",
            path="/",
        )
        return response

    @app.get(f"{API_PREFIX}/health")
    async def health() -> dict[str, Any]:
        return {
            "ok": True,
            "service": "Celsius Project AI",
            "version": _application_version(),
            "api_version": "v1",
            "processing_mode": "local",
        }

    @app.get(f"{API_PREFIX}/session", dependencies=[Depends(require_access)])
    async def session() -> dict[str, Any]:
        customer = settings.customer
        return {
            "ok": True,
            "assistant": {
                "name": settings.assistant_name,
                "profile": settings.assistant_profile,
            },
            "company": {
                "configured": customer.is_configured(),
                "name": customer.company_name,
                "segment": customer.company_sector,
                "size": customer.company_size,
                "user_name": customer.user_name,
                "user_role": customer.user_role,
            },
            "privacy": {
                "local_first": customer.local_offline_required,
                "external_services_are_optional": True,
            },
        }

    @app.get(f"{API_PREFIX}/modules", dependencies=[Depends(require_access)])
    async def modules() -> dict[str, Any]:
        return {
            "ok": True,
            "items": [_module_payload(settings, module) for module in module_catalog()],
        }

    @app.get(f"{API_PREFIX}/navigation", dependencies=[Depends(require_access)])
    async def navigation() -> dict[str, Any]:
        items = [_module_payload(settings, module) for module in module_catalog()]
        return {"ok": True, "items": [item for item in items if item["in_navigation"]]}

    app.include_router(
        chat_router,
        prefix=API_PREFIX,
        dependencies=[Depends(require_access)],
    )
    app.include_router(
        features_router,
        prefix=API_PREFIX,
        dependencies=[Depends(require_access)],
    )
    app.include_router(
        agenda_router,
        prefix=API_PREFIX,
        dependencies=[Depends(require_access)],
    )
    app.include_router(
        documents_router,
        prefix=API_PREFIX,
        dependencies=[Depends(require_access)],
    )
    app.include_router(
        relationships_router,
        prefix=API_PREFIX,
        dependencies=[Depends(require_access)],
    )
    app.include_router(
        operations_router,
        prefix=API_PREFIX,
        dependencies=[Depends(require_access)],
    )
    app.include_router(
        workflows_router,
        prefix=API_PREFIX,
        dependencies=[Depends(require_access)],
    )
    app.include_router(
        mobile_router,
        prefix=API_PREFIX,
        dependencies=[Depends(require_access)],
    )

    @app.websocket(f"{API_PREFIX}/events")
    async def events(websocket: WebSocket) -> None:
        if not token_matches(websocket_token(websocket), access_token):
            await websocket.close(code=1008, reason="Pareamento do Celsius necessario.")
            return

        await websocket.accept()
        async with event_hub.subscribe() as queue:
            await websocket.send_json(
                {
                    "type": "system.connected",
                    "payload": {"api_version": "v1"},
                }
            )
            while True:
                receive_task = asyncio.create_task(websocket.receive_json())
                event_task = asyncio.create_task(queue.get())
                done, pending = await asyncio.wait(
                    (receive_task, event_task),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                for task in pending:
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
                try:
                    if event_task in done:
                        await websocket.send_json(event_task.result())
                    if receive_task in done:
                        message = receive_task.result()
                        if message.get("type") == "ping":
                            await websocket.send_json(
                                {"type": "pong", "payload": message.get("payload", {})}
                            )
                except WebSocketDisconnect:
                    break

    return app
