"""Versioned local API used by the future desktop and mobile web interfaces."""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import logging
import ssl
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from core.agenda import AgendaService, get_agenda_service
from core.agent_schedule import AgentScheduleStore
from core.audit_log import AuditLogger
from core.business_records import BusinessRecordService
from core.chat_service import ChatBusyError, ChatCoordinator, ChatNotFoundError
from core.conversation_history import ConversationHistoryService
from core.documents import DocumentLibraryService, get_document_library_service
from core.memory import MemoryService, get_memory_service
from core.mobile_access import MobileAccessServer, ensure_mobile_certificate, get_lan_ip
from core.modules import effective_module_preferences, module_catalog
from core.operations import BusinessOperationsService, get_operations_service
from core.proactive_notifications import ProactiveNotificationService
from core.relationships import RelationshipService, get_relationship_service
from core.settings import get_settings
from core.tts import TTSVoiceConfig, create_tts_provider
from core.users import UserRole, UserService
from core.web_api.admin_dashboard import router as admin_router
from core.web_api.agenda import agenda_event_payload
from core.web_api.agenda import router as agenda_router
from core.web_api.agents import router as agents_router
from core.web_api.auth import (
    BrowserSessionStore,
    credential_is_valid,
    request_token,
    resolve_access_token,
    websocket_token,
)
from core.web_api.auth_users import router as auth_router
from core.web_api.chat import router as chat_router
from core.web_api.chat_history import router as chat_history_router
from core.web_api.documents import router as documents_router
from core.web_api.events import EventHub, get_event_hub
from core.web_api.features import router as features_router
from core.web_api.mobile import router as mobile_router
from core.web_api.mobile_bridge import MobileChatBridge
from core.web_api.notifications_api import router as notifications_router
from core.web_api.operations import router as operations_router
from core.web_api.relationships import router as relationships_router
from core.web_api.settings_api import router as settings_router
from core.web_api.whatsapp_api import router as whatsapp_router
from core.web_api.workflows import router as workflows_router
from core.whatsapp import WhatsAppService
from core.workflows import BusinessWorkflowService, get_workflow_service

API_PREFIX = "/api/v1"
STATIC_DIR = Path(__file__).with_name("static")
logger = logging.getLogger(__name__)
_bearer_auth = HTTPBearer(auto_error=False)
BearerCredentials = Annotated[
    HTTPAuthorizationCredentials | None,
    Depends(_bearer_auth),
]


class _RequestRateLimiter:
    def __init__(self) -> None:
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, *, limit: int, window_seconds: int = 60) -> bool:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            bucket = self._requests[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            return True


def _application_version() -> str:
    try:
        return version("celsius")
    except PackageNotFoundError:
        return "1.0.0"


def _module_payload(settings, module, user=None) -> dict[str, Any]:
    enabled_ids, visibility = effective_module_preferences(settings, user)
    enabled = module.id in enabled_ids
    sidebar_preference = visibility.get(module.id, True)
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


def _websocket_origin_is_same_host(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin", "").strip().lower()
    if not origin:
        return True
    host = websocket.headers.get("host", "").strip().lower()
    return origin in {f"http://{host}", f"https://{host}"}


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

    def ensure_mobile_access(*, allow_lan: bool = False) -> MobileAccessServer:
        with mobile_server_lock:
            current = getattr(app.state, "mobile_server", None)
            if current is not None and current.is_running:
                return current

            # A pairing request is an explicit user action. It may expose the
            # dedicated companion server on the current Wi-Fi network even when
            # the main responsive web server itself is bound to 127.0.0.1.
            # Non-loopback access is always protected with local HTTPS.
            mobile_lan_enabled = lan_access_enabled or allow_lan or bool(settings.mobile.allow_lan)
            host = "0.0.0.0" if mobile_lan_enabled else "127.0.0.1"  # nosec B104
            use_https = mobile_lan_enabled or bool(settings.mobile.use_https)
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
                # The companion is a TLS-only loopback proxy for the responsive
                # web UI. The phone therefore gets every existing module while
                # the main API remains bound to localhost.
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
                    # The phone companion is intentionally a focused voice
                    # conversation surface. The full web UI remains available
                    # at /app on desktop browsers.
                    web_proxy_url="",
                    web_pairing_code_callback=None,
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

    async def run_agent_schedules() -> None:
        """Dispatch due schedules through the same single-worker chat queue."""
        while True:
            schedule_store = getattr(app.state, "agent_schedule_store", None)
            if schedule_store is not None:
                for item in await asyncio.to_thread(schedule_store.due):
                    try:
                        request = await asyncio.to_thread(
                            chat_coordinator.submit,
                            message=f"TAREFA: {item['objective']}",
                            conversation_id=item["scope"],
                            agent_mode=item["mode"],
                        )
                        event_hub.publish(
                            "agent.schedule_started", {"schedule_id": item["id"], "job": request}
                        )
                        await asyncio.to_thread(
                            schedule_store.record_dispatch, item["id"], request["id"]
                        )
                    except ChatBusyError as exc:
                        await asyncio.to_thread(
                            schedule_store.defer, item["id"], str(exc), retry_seconds=30
                        )
                    except ChatNotFoundError as exc:
                        await asyncio.to_thread(schedule_store.record_error, item["id"], str(exc))
                        await asyncio.to_thread(
                            schedule_store.set_enabled, item["id"], item["scope"], False
                        )
                    except ValueError as exc:
                        await asyncio.to_thread(schedule_store.record_error, item["id"], str(exc))
            await asyncio.sleep(10)

    async def forward_mobile_responses() -> None:
        partial_by_job: dict[str, str] = {}
        async with event_hub.subscribe() as queue:
            while True:
                event = await queue.get()
                server = getattr(app.state, "mobile_server", None)
                if server is None or not server.is_running:
                    continue
                payload = event.get("payload", {})
                job_id = str(payload.get("job_id", ""))
                if not mobile_bridge.owns_job(job_id):
                    continue
                if event.get("type") == "chat.status":
                    status_text = str(payload.get("text", "")).strip()
                    if status_text:
                        server.publish_partial(status_text)
                elif event.get("type") == "chat.chunk":
                    partial_by_job[job_id] = partial_by_job.get(job_id, "") + str(
                        payload.get("text", "")
                    )
                    server.publish_partial(partial_by_job[job_id])
                elif event.get("type") == "chat.completed":
                    text = str(payload.get("text", "")).strip()
                    if not text:
                        continue
                    server.publish_response(text, kind="assistant")
                    try:
                        audio = await tts_provider.synthesize(text)
                        server.publish_audio(audio, mime_type="audio/mpeg")
                    except Exception as exc:
                        logger.warning("Audio movel nao foi gerado: %s", exc)
                    partial_by_job.pop(job_id, None)
                    mobile_bridge.finish_job(job_id)
                elif event.get("type") == "chat.failed":
                    error = str(payload.get("error", "Falha local")).strip()
                    server.publish_response(f"Erro ao responder: {error}", kind="error")
                    partial_by_job.pop(job_id, None)
                    mobile_bridge.finish_job(job_id)
                elif event.get("type") == "chat.cancelled":
                    server.publish_response("Resposta interrompida no computador.", kind="error")
                    partial_by_job.pop(job_id, None)
                    mobile_bridge.finish_job(job_id)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await asyncio.to_thread(_app.state.whatsapp_service.resume)
        reminder_task = asyncio.create_task(watch_agenda_reminders())
        mobile_response_task = asyncio.create_task(forward_mobile_responses())
        agent_schedule_task = asyncio.create_task(run_agent_schedules())
        try:
            yield
        finally:
            await asyncio.to_thread(_app.state.whatsapp_service.shutdown)
            reminder_task.cancel()
            mobile_response_task.cancel()
            agent_schedule_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reminder_task
            with contextlib.suppress(asyncio.CancelledError):
                await mobile_response_task
            with contextlib.suppress(asyncio.CancelledError):
                await agent_schedule_task
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
    allowed_hosts = ["localhost", "127.0.0.1", "[::1]", "testserver", get_lan_ip()]
    configured_host = str(getattr(settings.mobile, "host", "")).strip()
    if configured_host and configured_host not in {"0.0.0.0", "::"}:  # nosec B104
        allowed_hosts.append(configured_host)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(dict.fromkeys(allowed_hosts)))

    browser_sessions = BrowserSessionStore(
        pairing_ttl_seconds=settings.mobile.pairing_ttl_seconds,
        session_ttl_seconds=settings.mobile.session_ttl_seconds,
        max_sessions=settings.mobile.max_browser_sessions,
    )
    request_limiter = _RequestRateLimiter()
    audit_logger = AuditLogger(Path(settings.data_dir) / "audit.log")
    app.state.settings = settings
    app.state.user_service = UserService(data_dir=settings.data_dir)
    app.state.whatsapp_service = WhatsAppService(
        settings=settings, coordinator=chat_coordinator,
        user_service=app.state.user_service, event_hub=event_hub,
    )
    app.state.history_service = ConversationHistoryService(
        base_dir=settings.data_dir / "conversation_history"
    )
    app.state.notification_service = ProactiveNotificationService(data_dir=settings.data_dir)
    app.state.agent_schedule_store = AgentScheduleStore(settings.data_dir)
    app.state.event_hub = event_hub
    app.state.access_token = access_token
    app.state.browser_sessions = browser_sessions
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
    app.state.web_port = int(public_port or settings.web.port)
    pending_agenda_reminders: set[str] = set()
    app.state.pending_agenda_reminders = pending_agenda_reminders
    app.mount("/app/assets", StaticFiles(directory=STATIC_DIR), name="web-assets")

    @app.middleware("http")
    async def harden_http(request: Request, call_next):
        if request.url.path.startswith(API_PREFIX):
            client_host = request.client.host if request.client else "unknown"
            expensive = request.url.path.startswith(
                (
                    f"{API_PREFIX}/chat/messages",
                    f"{API_PREFIX}/chat/attachments",
                    f"{API_PREFIX}/documents/upload",
                    f"{API_PREFIX}/voice/",
                )
            )
            limit = 30 if expensive else 240
            key = f"{client_host}:{'expensive' if expensive else 'api'}"
            if not request_limiter.allow(key, limit=limit):
                return JSONResponse(
                    status_code=429,
                    content={"ok": False, "error": "Muitas requisicoes. Aguarde um minuto."},
                    headers={"Retry-After": "60"},
                )

        origin = request.headers.get("origin", "").strip().lower()
        host = request.headers.get("host", "").strip().lower()
        if origin and origin not in {f"http://{host}", f"https://{host}"}:
            return JSONResponse(
                status_code=403,
                content={"ok": False, "error": "Origem nao autorizada."},
            )

        response = await call_next(request)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            credential = request_token(request)
            audit_logger.record(
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                actor=audit_logger.actor_fingerprint(credential),
                client=request.client.host if request.client else "unknown",
            )
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; "
            "img-src 'self' data: blob:; media-src 'self' blob:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self'",
        )
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(self)")
        if request.url.path == "/app" or request.url.path.startswith(API_PREFIX):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    async def require_access(
        request: Request,
        credentials: BearerCredentials,
    ) -> None:
        candidate = (
            credentials.credentials if credentials else request.cookies.get("access_token", "")
        )
        user = app.state.user_service.validate_token(candidate) if candidate else None
        if user is not None:
            request.state.current_user = user
            personal_menu_update = (
                request.method == "PATCH" and request.url.path == f"{API_PREFIX}/settings/sidebar"
            )
            if (
                user.role == UserRole.VIEWER
                and request.method not in {"GET", "HEAD", "OPTIONS"}
                and not personal_menu_update
            ):
                raise HTTPException(
                    status_code=403, detail="Este usuario possui acesso somente de leitura."
                )
            return
        if app.state.user_service.list_users():
            raise HTTPException(status_code=401, detail="Entre com sua conta do Celsius.")
        candidate = credentials.credentials if credentials else request_token(request)
        if not credential_is_valid(
            candidate,
            access_token=access_token,
            sessions=browser_sessions,
        ):
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

    @app.get("/mobile", include_in_schema=False)
    async def mobile_app(request: Request) -> RedirectResponse:
        """Open the dedicated voice companion for a phone on the LAN."""

        if not _is_loopback_request(request):
            candidate = request_token(request)
            user = app.state.user_service.validate_token(candidate) if candidate else None
            if user is None and not browser_sessions.is_valid(candidate):
                raise HTTPException(
                    status_code=401,
                    detail="Abra o companion pelo QR Code gerado no Celsius.",
                )

        server = app.state.ensure_mobile_access(allow_lan=True)
        return RedirectResponse(url=server.url, status_code=307)

    @app.get("/app", include_in_schema=False)
    @app.get("/app/", include_in_schema=False)
    async def web_app(request: Request):
        pairing_code = request.query_params.get("pair", "").strip()
        session_token = request_token(request)
        new_session = ""

        if pairing_code:
            new_session = browser_sessions.exchange_pairing_code(pairing_code) or ""
            if not new_session:
                raise HTTPException(status_code=401, detail="Pareamento expirado ou ja utilizado.")
        elif not browser_sessions.is_valid(session_token):
            if _is_loopback_request(request) or credential_is_valid(
                session_token,
                access_token=access_token,
                sessions=browser_sessions,
            ):
                new_session = browser_sessions.issue_session()
            elif app.state.lan_access_enabled:
                # A LAN client may open the login screen directly.  The
                # authenticated API routes remain protected by the user
                # account, while pairing stays available as a one-click QR
                # shortcut from the desktop.
                pass
            else:
                raise HTTPException(status_code=401, detail="Pareamento do Celsius necessario.")

        if pairing_code:
            response: Response = RedirectResponse(url="/app", status_code=303)
        else:
            response = FileResponse(STATIC_DIR / "index.html")
        if new_session:
            response.set_cookie(
                "celsius_session",
                new_session,
                max_age=browser_sessions.session_ttl_seconds,
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
    async def modules(request: Request) -> dict[str, Any]:
        user = getattr(request.state, "current_user", None)
        return {
            "ok": True,
            "items": [_module_payload(settings, module, user) for module in module_catalog()],
        }

    @app.get(f"{API_PREFIX}/navigation", dependencies=[Depends(require_access)])
    async def navigation(request: Request) -> dict[str, Any]:
        user = getattr(request.state, "current_user", None)
        items = [_module_payload(settings, module, user) for module in module_catalog()]
        return {
            "ok": True,
            "items": [item for item in items if item["in_navigation"]],
            "preferences": getattr(user, "sidebar_preferences", {}) or {},
        }

    app.include_router(auth_router, prefix=API_PREFIX)
    app.include_router(whatsapp_router, prefix=API_PREFIX, dependencies=[Depends(require_access)])
    app.include_router(chat_history_router, prefix=API_PREFIX)
    app.include_router(admin_router, prefix=API_PREFIX)
    app.include_router(notifications_router, prefix=API_PREFIX)
    app.include_router(
        agents_router,
        prefix=API_PREFIX,
        dependencies=[Depends(require_access)],
    )
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
    app.include_router(
        settings_router,
        prefix=API_PREFIX,
        dependencies=[Depends(require_access)],
    )

    @app.websocket(f"{API_PREFIX}/events")
    async def events(websocket: WebSocket) -> None:
        if not _websocket_origin_is_same_host(websocket):
            await websocket.close(code=1008, reason="Origem nao autorizada.")
            return

        def authorized() -> bool:
            user_token = websocket.headers.get("authorization", "").removeprefix("Bearer ").strip()
            user_token = user_token or websocket.cookies.get("access_token", "")
            if app.state.user_service.validate_token(user_token):
                return True
            return not app.state.user_service.list_users() and credential_is_valid(
                websocket_token(websocket), access_token=access_token, sessions=browser_sessions
            )

        if not authorized():
            await websocket.close(code=1008, reason="Pareamento do Celsius necessario.")
            return

        if event_hub.subscriber_count >= event_hub.max_subscribers:
            await websocket.close(code=1013, reason="Limite de conexoes atingido.")
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
                if not authorized():
                    await websocket.close(code=1008, reason="Sessao encerrada.")
                    break
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
                    if not authorized():
                        await websocket.close(code=1008, reason="Sessao encerrada.")
                        break
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
