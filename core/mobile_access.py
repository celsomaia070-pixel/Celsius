import base64
import contextlib
import datetime as dt
import hashlib
import ipaddress
import json
import logging
import secrets
import socket
import ssl
import threading
import time
from collections.abc import Callable
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from core.file_security import restrict_private_file

CommandCallback = Callable[[str, str], dict[str, Any] | tuple[bool, str] | bool | None]
VoiceCommandCallback = Callable[[bytes, str], tuple[bool, str, str] | dict | str]
PairingCodeCallback = Callable[[], str]
logger = logging.getLogger(__name__)


class _NoRedirect(HTTPRedirectHandler):
    """Keep upstream redirects under the mobile HTTPS origin."""

    def redirect_request(
        self,
        _req: Any,
        _fp: Any = None,
        _code: int = 0,
        _msg: str = "",
        _headers: Any = None,
        _newurl: str = "",
    ) -> None:
        return None


def ensure_mobile_token(current: str = "") -> str:
    token = (current or "").strip()
    if token:
        return token
    return secrets.token_urlsafe(24)


def rotate_mobile_token(settings: Any, current: str | None = None) -> str:
    """Return a pairing token, regenerating it when none or stale.

    ``settings.mobile.token_rotation_days`` controls the maximum age (0 or a
    negative value disables rotation). The issue timestamp is stored in
    ``settings.mobile.pairing_token_issued_at`` so expiry survives restart.
    """
    max_age_days = int(getattr(settings.mobile, "token_rotation_days", 30))
    token = (current or settings.mobile.pairing_token or "").strip()
    if max_age_days <= 0:
        return token or secrets.token_urlsafe(24)

    issued = None
    issued_raw = (settings.mobile.pairing_token_issued_at or "").strip()
    if issued_raw:
        with contextlib.suppress(ValueError, TypeError):
            issued = dt.datetime.fromisoformat(issued_raw)

    now = dt.datetime.now(dt.timezone.utc)
    expired = issued is not None and (now - issued).total_seconds() >= max_age_days * 86400
    stale = not token or expired
    if stale:
        token = secrets.token_urlsafe(24)
        settings.mobile.pairing_token = token
        settings.mobile.pairing_token_issued_at = now.isoformat()
    return token


def get_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return str(sock.getsockname()[0])
    except OSError:
        return "127.0.0.1"


def build_mobile_url(host: str, port: int, pairing_code: str, *, use_https: bool = False) -> str:
    display_host = get_lan_ip() if host in {"0.0.0.0", "::"} else host  # nosec B104
    scheme = "https" if use_https else "http"
    return f"{scheme}://{display_host}:{port}/?pair={pairing_code}"


def ensure_mobile_certificate(
    cert_dir: str | Path,
    *,
    lan_ip: str | None = None,
    valid_days: int = 365,
) -> tuple[Path, Path]:
    """Create or reuse a local self-signed certificate for mobile pairing."""

    cert_path = Path(cert_dir) / "celsius-mobile.crt"
    key_path = Path(cert_dir) / "celsius-mobile.key"
    if cert_path.exists() and key_path.exists():
        restrict_private_file(key_path)
        return cert_path, key_path

    cert_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "A dependencia cryptography e necessaria para gerar HTTPS local. "
            "Instale com: python -m pip install cryptography"
        ) from exc

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Celsius Project AI"),
            x509.NameAttribute(NameOID.COMMON_NAME, "Celsius Local Mobile Access"),
        ]
    )

    ip_value = lan_ip or get_lan_ip()
    san_items: list[x509.GeneralName] = [x509.DNSName("localhost")]
    for value in {"127.0.0.1", ip_value}:
        try:
            san_items.append(x509.IPAddress(ipaddress.ip_address(value)))
        except ValueError:
            san_items.append(x509.DNSName(value))

    now = dt.datetime.now(dt.timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=valid_days))
        .add_extension(x509.SubjectAlternativeName(san_items), critical=False)
        .sign(key, hashes.SHA256())
    )

    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    restrict_private_file(key_path)
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path


def mobile_certificate_fingerprint(cert_file: str | Path) -> str:
    path = Path(cert_file)
    if not path.is_file():
        return ""
    try:
        der = ssl.PEM_cert_to_DER_cert(path.read_text(encoding="ascii"))
        digest = hashlib.sha256(der).hexdigest().upper()
        return ":".join(digest[index : index + 2] for index in range(0, len(digest), 2))
    except (OSError, ValueError):
        return ""


def _is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _create_server_ssl_context() -> ssl.SSLContext:
    """Create a TLS server context unaffected by client-only truststore injection."""

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    if type(context).__module__.endswith("truststore._api"):
        context = getattr(context, "_ctx", context)
    return context


class MobileAccessServer:
    """Small local HTTP server for phone-to-PC commands."""

    def __init__(
        self,
        host: str,
        port: int,
        token: str,
        command_callback: CommandCallback,
        *,
        voice_enabled: bool = True,
        voice_command_callback: VoiceCommandCallback | None = None,
        use_https: bool = False,
        cert_file: str | Path | None = None,
        key_file: str | Path | None = None,
        web_proxy_url: str = "",
        web_pairing_code_callback: PairingCodeCallback | None = None,
    ):
        self.host = host
        self.port = port
        self.token = ensure_mobile_token(token)
        self.command_callback = command_callback
        self.voice_enabled = voice_enabled
        self.voice_command_callback = voice_command_callback
        self.use_https = use_https
        if not _is_loopback_host(host) and not use_https:
            raise ValueError("Acesso movel fora do computador exige HTTPS.")
        self.cert_file = Path(cert_file) if cert_file else None
        self.key_file = Path(key_file) if key_file else None
        self.web_proxy_url = web_proxy_url.rstrip("/")
        self.web_pairing_code_callback = web_pairing_code_callback
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._response_lock = threading.Lock()
        self._response_version = 0
        self._last_response_text = ""
        self._live_text = ""
        self._last_response_kind = "assistant"
        self._audio_version = 0
        self._last_audio = b""
        self._last_audio_mime = "audio/mpeg"
        self._last_audio_response_version = 0
        self._response_audio_version = 0
        self._audio_chunks: list[dict[str, bytes | str | int]] = []
        self._auth_lock = threading.RLock()
        self._pairing_codes: dict[str, float] = {}
        self._sessions: dict[str, float] = {}
        # Stable pairing code for display/QR code - generated once at startup
        self._display_pairing_code: str = secrets.token_urlsafe(24)
        self._display_pairing_expires_at = 0.0

    @property
    def is_running(self) -> bool:
        return self._httpd is not None

    @property
    def url(self) -> str:
        """Return the mobile access URL with a stable pairing code for QR display."""
        self._refresh_display_pairing_code()
        port = self._httpd.server_address[1] if self._httpd else self.port
        return build_mobile_url(
            self.host,
            port,
            self._display_pairing_code,
            use_https=self.use_https,
        )

    @property
    def pairing_code(self) -> str:
        """Return the stable pairing code for QR code generation."""
        self._refresh_display_pairing_code()
        return self._display_pairing_code

    def _refresh_display_pairing_code(self) -> None:
        now = time.monotonic()
        if now < self._display_pairing_expires_at:
            return
        with self._auth_lock:
            now = time.monotonic()
            if now < self._display_pairing_expires_at:
                return
            self._display_pairing_code = secrets.token_urlsafe(24)
            self._display_pairing_expires_at = now + 120
            self._pairing_codes[self._display_pairing_code] = self._display_pairing_expires_at

    def _purge_auth(self) -> None:
        now = time.monotonic()
        self._pairing_codes = {
            code: expiry for code, expiry in self._pairing_codes.items() if expiry > now
        }
        self._sessions = {token: expiry for token, expiry in self._sessions.items() if expiry > now}

    def _issue_pairing_code(self) -> str:
        with self._auth_lock:
            self._purge_auth()
            code = secrets.token_urlsafe(24)
            self._pairing_codes[code] = time.monotonic() + 120
            return code

    def _exchange_pairing_code(self, code: str) -> str:
        with self._auth_lock:
            self._purge_auth()
            if not self._pairing_codes.pop(code, None):
                return ""
            if secrets.compare_digest(code, self._display_pairing_code):
                self._display_pairing_expires_at = 0.0
            session = secrets.token_urlsafe(32)
            self._sessions[session] = time.monotonic() + 12 * 60 * 60
            return session

    def _valid_session(self, token: str) -> bool:
        with self._auth_lock:
            self._purge_auth()
            return bool(token and token in self._sessions)

    def start(self) -> "MobileAccessServer":
        if self._httpd is not None:
            return self
        self._refresh_display_pairing_code()
        handler = self._make_handler()
        self._httpd = ThreadingHTTPServer((self.host, self.port), handler)
        if self.use_https:
            if self.cert_file is None or self.key_file is None:
                raise ValueError("HTTPS mobile access requires certificate and key files.")
            context = _create_server_ssl_context()
            context.load_cert_chain(str(self.cert_file), str(self.key_file))
            self._httpd.socket = context.wrap_socket(self._httpd.socket, server_side=True)
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="CelsiusMobileAccess",
            daemon=True,
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._httpd is None:
            return
        self._httpd.shutdown()
        self._httpd.server_close()
        self._httpd = None
        self._thread = None

    def publish_response(self, text: str, *, kind: str = "assistant") -> int:
        """Publish the latest Celsius response for paired mobile clients."""

        clean_text = (text or "").strip()
        if not clean_text:
            return self._response_version
        with self._response_lock:
            self._response_version += 1
            self._last_response_text = clean_text
            self._last_response_kind = kind or "assistant"
            self._response_audio_version = 0
            self._audio_chunks = []
            self._live_text = ""
            return self._response_version

    def publish_partial(self, text: str) -> None:
        """Publish the in-progress response so paired clients see live typing."""

        clean_text = (text or "").strip()
        if not clean_text:
            return
        with self._response_lock:
            self._live_text = clean_text

    def publish_audio(self, audio: bytes, *, mime_type: str = "audio/mpeg") -> int:
        """Publish audio generated on the PC for the latest Celsius response."""

        if not audio:
            return self._audio_version
        with self._response_lock:
            if self._response_version <= 0:
                return self._audio_version
            self._audio_version += 1
            self._last_audio = bytes(audio)
            self._last_audio_mime = mime_type or "audio/mpeg"
            self._last_audio_response_version = self._response_version
            self._response_audio_version = self._audio_version
            self._audio_chunks.append(
                {
                    "version": self._audio_version,
                    "response_version": self._response_version,
                    "audio": bytes(audio),
                    "mime_type": self._last_audio_mime,
                }
            )
            return self._audio_version

    def latest_response(self) -> dict[str, str | int | bool]:
        with self._response_lock:
            return {
                "version": self._response_version,
                "text": self._last_response_text,
                "kind": self._last_response_kind,
                "live_text": self._live_text,
                "live_active": bool(self._live_text),
                "audio_version": self._response_audio_version,
                "audio_ready": self._response_audio_version > 0,
            }

    def latest_audio(
        self,
        response_version: int,
        *,
        after_audio_version: int = 0,
    ) -> tuple[bytes, str, int] | None:
        with self._response_lock:
            if response_version <= 0:
                return None
            for chunk in self._audio_chunks:
                if (
                    int(chunk["response_version"]) == response_version
                    and int(chunk["version"]) > after_audio_version
                ):
                    return (
                        cast(bytes, chunk["audio"]),
                        str(chunk["mime_type"]),
                        int(chunk["version"]),
                    )
            return None

    def _make_handler(self) -> type:
        server_ref = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, _format: str, *_args: Any) -> None:
                return

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path == "/":
                    code = parse_qs(parsed.query).get("pair", [""])[0]
                    session = server_ref._exchange_pairing_code(code) if code else ""
                    existing_session = self._session_cookie()
                    if not session and not server_ref._valid_session(existing_session):
                        self._send_json(
                            {"ok": False, "error": "pairing_required"},
                            HTTPStatus.UNAUTHORIZED,
                        )
                        return
                    if server_ref.web_proxy_url and server_ref.web_pairing_code_callback:
                        self._open_full_web_interface(session=session)
                        return
                    self._send_html(
                        _mobile_html("", server_ref.voice_enabled),
                        session=session,
                    )
                    return
                if self._is_web_proxy_path(parsed.path):
                    self._proxy_web_request()
                    return
                if parsed.path == "/api/status":
                    if not self._authorized():
                        self._send_json(
                            {"ok": False, "error": "unauthorized"}, HTTPStatus.UNAUTHORIZED
                        )
                        return
                    self._send_json(
                        {
                            "ok": True,
                            "name": "Celsius Project AI",
                            "voice_enabled": server_ref.voice_enabled,
                            "https": server_ref.use_https,
                            "response_version": server_ref.latest_response()["version"],
                            "audio_version": server_ref.latest_response()["audio_version"],
                        }
                    )
                    return
                if parsed.path == "/api/last-response":
                    if not self._authorized():
                        self._send_json(
                            {"ok": False, "error": "unauthorized"}, HTTPStatus.UNAUTHORIZED
                        )
                        return
                    response = server_ref.latest_response()
                    after = parse_qs(parsed.query).get("after", ["0"])[0]
                    try:
                        after_version = int(after)
                    except ValueError:
                        after_version = 0
                    has_new = int(response["version"]) > after_version
                    self._send_json({"ok": True, "has_new": has_new, **response})
                    return
                if parsed.path == "/api/last-audio":
                    if not self._authorized():
                        self._send_json(
                            {"ok": False, "error": "unauthorized"}, HTTPStatus.UNAUTHORIZED
                        )
                        return
                    version = parse_qs(parsed.query).get("response_version", ["0"])[0]
                    after = parse_qs(parsed.query).get("after_audio_version", ["0"])[0]
                    try:
                        response_version = int(version)
                    except ValueError:
                        response_version = 0
                    try:
                        after_audio_version = int(after)
                    except ValueError:
                        after_audio_version = 0
                    audio = server_ref.latest_audio(
                        response_version,
                        after_audio_version=after_audio_version,
                    )
                    if audio is None:
                        self.send_response(HTTPStatus.NO_CONTENT)
                        self.send_header("Cache-Control", "no-store")
                        self.end_headers()
                        return
                    audio_bytes, mime_type, audio_version = audio
                    self._send_audio(audio_bytes, mime_type, audio_version)
                    return
                self._send_json({"ok": False, "error": "not_found"}, HTTPStatus.NOT_FOUND)

            def do_POST(self) -> None:
                parsed = urlparse(self.path)
                if self._is_web_proxy_path(parsed.path):
                    self._proxy_web_request()
                    return
                if parsed.path != "/api/command":
                    if parsed.path == "/api/voice-command":
                        self._handle_voice_command()
                        return
                    self._send_json({"ok": False, "error": "not_found"}, HTTPStatus.NOT_FOUND)
                    return
                if not self._authorized():
                    self._send_json({"ok": False, "error": "unauthorized"}, HTTPStatus.UNAUTHORIZED)
                    return

                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    raw = self.rfile.read(min(length, 10000))
                    payload = json.loads(raw.decode("utf-8"))
                except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
                    self._send_json({"ok": False, "error": "invalid_json"}, HTTPStatus.BAD_REQUEST)
                    return

                message = str(payload.get("message", "")).strip()
                source = str(payload.get("source", "phone")).strip() or "phone"
                if not message:
                    self._send_json({"ok": False, "error": "empty_message"}, HTTPStatus.BAD_REQUEST)
                    return

                try:
                    result = server_ref.command_callback(message, source)
                except Exception as exc:
                    logger.exception("Falha ao entregar comando movel: %s", exc)
                    self._send_json(
                        {
                            "ok": False,
                            "message": "Erro interno ao entregar comando ao Celsius.",
                        },
                        HTTPStatus.INTERNAL_SERVER_ERROR,
                    )
                    return
                extra: dict[str, Any] = {}
                if isinstance(result, dict):
                    accepted = bool(result.get("ok"))
                    detail = str(result.get("message", "Comando enviado ao Celsius."))
                    extra = {
                        key: result[key]
                        for key in ("job_id", "conversation_id", "command_submitted")
                        if key in result
                    }
                elif isinstance(result, tuple):
                    accepted, detail = result
                else:
                    accepted, detail = bool(result is not False), "Comando enviado ao Celsius."
                self._send_json(
                    {
                        "ok": bool(accepted),
                        "message": detail,
                        "response_version": server_ref.latest_response()["version"],
                        **extra,
                    }
                )

            def _handle_voice_command(self) -> None:
                if not self._authorized():
                    self._send_json({"ok": False, "error": "unauthorized"}, HTTPStatus.UNAUTHORIZED)
                    return
                if not server_ref.voice_enabled or server_ref.voice_command_callback is None:
                    self._send_json(
                        {"ok": False, "message": "Comando de voz local indisponivel."},
                        HTTPStatus.SERVICE_UNAVAILABLE,
                    )
                    return

                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    raw = self.rfile.read(min(length, 4_000_000))
                    payload = json.loads(raw.decode("utf-8"))
                    audio = base64.b64decode(str(payload.get("audio_base64", "")), validate=True)
                    mime_type = str(payload.get("mime_type", "audio/webm")).strip()
                except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
                    self._send_json({"ok": False, "error": "invalid_json"}, HTTPStatus.BAD_REQUEST)
                    return

                if not audio:
                    self._send_json({"ok": False, "error": "empty_audio"}, HTTPStatus.BAD_REQUEST)
                    return

                try:
                    result = server_ref.voice_command_callback(audio, mime_type)
                except Exception as exc:
                    logger.exception("Falha ao processar voz movel: %s", exc)
                    self._send_json(
                        {
                            "ok": False,
                            "message": "Erro interno ao processar voz no Celsius.",
                            "transcript": "",
                        },
                        HTTPStatus.INTERNAL_SERVER_ERROR,
                    )
                    return
                if isinstance(result, dict):
                    response = dict(result)
                    response.setdefault("ok", True)
                    response.setdefault("message", "Voz enviada.")
                    response.setdefault("transcript", "")
                    response.setdefault("response_version", server_ref.latest_response()["version"])
                    self._send_json(response)
                    return
                if isinstance(result, tuple):
                    accepted, transcript, detail = result
                else:
                    accepted, transcript, detail = True, str(result).strip(), "Voz enviada."

                self._send_json(
                    {
                        "ok": bool(accepted),
                        "message": detail,
                        "transcript": transcript,
                        "response_version": server_ref.latest_response()["version"],
                    }
                )

            def _authorized(self) -> bool:
                auth = self.headers.get("Authorization", "")
                expected_auth = f"Bearer {server_ref.token}"
                if secrets.compare_digest(auth, expected_auth):
                    return True
                return server_ref._valid_session(self._session_cookie())

            @staticmethod
            def _is_web_proxy_path(path: str) -> bool:
                return path == "/app" or path.startswith("/app/") or path.startswith("/api/v1/")

            def _open_full_web_interface(self, *, session: str) -> None:
                """Bootstrap a web session, then redirect the phone to the full UI."""

                assert server_ref.web_pairing_code_callback is not None
                pairing_code = server_ref.web_pairing_code_callback()
                upstream_path = f"/app?pair={quote(pairing_code, safe='')}"
                try:
                    _body, headers, _status = self._upstream_request("GET", upstream_path)
                except OSError as exc:
                    logger.warning("Falha ao abrir interface web movel: %s", exc)
                    self._send_json(
                        {"ok": False, "error": "web_interface_unavailable"},
                        HTTPStatus.SERVICE_UNAVAILABLE,
                    )
                    return

                self.send_response(HTTPStatus.SEE_OTHER)
                self.send_header("Location", "/app")
                self._security_headers()
                attributes = "Path=/; HttpOnly; SameSite=Strict; Max-Age=43200"
                if server_ref.use_https:
                    attributes += "; Secure"
                self.send_header("Set-Cookie", f"celsius_mobile_session={session}; {attributes}")
                for cookie in headers.get_all("Set-Cookie", []):
                    self.send_header("Set-Cookie", cookie)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()

            def _proxy_web_request(self) -> None:
                if not self._authorized():
                    self._send_json({"ok": False, "error": "unauthorized"}, HTTPStatus.UNAUTHORIZED)
                    return
                length = int(self.headers.get("Content-Length", "0") or 0)
                if length < 0 or length > 35_000_000:
                    self._send_json(
                        {"ok": False, "error": "payload_too_large"},
                        HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    )
                    return
                body = self.rfile.read(length) if length else None
                try:
                    response_body, headers, status = self._upstream_request(
                        self.command, self.path, body=body
                    )
                except OSError as exc:
                    logger.warning("Falha ao encaminhar requisicao movel: %s", exc)
                    self._send_json(
                        {"ok": False, "error": "web_interface_unavailable"},
                        HTTPStatus.SERVICE_UNAVAILABLE,
                    )
                    return

                self.send_response(status)
                for name in (
                    "Content-Type",
                    "Cache-Control",
                    "Content-Disposition",
                    "ETag",
                    "Last-Modified",
                ):
                    value = headers.get(name)
                    if value:
                        self.send_header(name, value)
                for cookie in headers.get_all("Set-Cookie", []):
                    self.send_header("Set-Cookie", cookie)
                self._security_headers()
                self.send_header("Content-Length", str(len(response_body)))
                self.end_headers()
                self.wfile.write(response_body)

            def _upstream_request(
                self, method: str, path: str, *, body: bytes | None = None
            ) -> tuple[bytes, Any, int]:
                """Relay only to the local web server; never to an arbitrary URL."""

                if not server_ref.web_proxy_url:
                    raise OSError("Proxy web local nao configurado.")
                headers = {"Accept": self.headers.get("Accept", "*/*")}
                for name in ("Content-Type", "Cookie", "Authorization"):
                    value = self.headers.get(name)
                    if value:
                        headers[name] = value
                request = Request(
                    f"{server_ref.web_proxy_url}{path}",
                    data=body,
                    headers=headers,
                    method=method,
                )
                handlers: list[Any] = [_NoRedirect()]
                if server_ref.web_proxy_url.lower().startswith("https://"):
                    # The upstream is the local Celsius API, which uses the
                    # self-signed LAN certificate generated for phone access.
                    # TLS is still enforced on the phone-facing listener; this
                    # hop never leaves the local machine.
                    handlers.append(HTTPSHandler(context=ssl._create_unverified_context()))  # nosec B323
                opener = build_opener(*handlers)
                try:
                    with opener.open(request, timeout=60) as response:
                        return response.read(), response.headers, response.status
                except HTTPError as exc:
                    return exc.read(), exc.headers, exc.code

            def _session_cookie(self) -> str:
                cookie = SimpleCookie()
                cookie.load(self.headers.get("Cookie", ""))
                morsel = cookie.get("celsius_mobile_session")
                return morsel.value if morsel else ""

            def _security_headers(self) -> None:
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "DENY")

            def _send_json(
                self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK
            ) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self._security_headers()
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_html(self, html: str, *, session: str = "") -> None:
                body = html.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
                self.send_header("Pragma", "no-cache")
                self._security_headers()
                if session:
                    attributes = "Path=/; HttpOnly; SameSite=Strict; Max-Age=43200"
                    if server_ref.use_https:
                        attributes += "; Secure"
                    self.send_header(
                        "Set-Cookie",
                        f"celsius_mobile_session={session}; {attributes}",
                    )
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_audio(self, audio: bytes, mime_type: str, audio_version: int) -> None:
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", mime_type or "audio/mpeg")
                self.send_header("Cache-Control", "no-store")
                self._security_headers()
                self.send_header("X-Celsius-Audio-Version", str(audio_version))
                self.send_header("Content-Length", str(len(audio)))
                self.end_headers()
                self.wfile.write(audio)

        return Handler


class MobileAccessRuntime:
    """Shared mobile server that can answer the phone before the LLM loads.

    The server binds early during startup and forwards commands to the desktop
    window only after it exists; until then the phone receives a friendly
    "still starting" notice instead of a connection error.
    """

    def __init__(self) -> None:
        self.server: MobileAccessServer | None = None
        self.sink: object | None = None

    def attach(self, server: MobileAccessServer) -> None:
        self.server = server

    def set_sink(self, sink: object) -> None:
        self.sink = sink

    def command(self, message: str, source: str) -> dict[str, Any] | tuple[bool, str] | bool | None:
        if self.sink is None:
            return (
                False,
                "O Celsius ainda esta iniciando. Tente novamente em instantes.",
            )
        handler = getattr(self.sink, "_queue_mobile_command", None)
        if not callable(handler):
            return False, "O Celsius ainda esta iniciando. Tente novamente em instantes."
        return cast(CommandCallback, handler)(message, source)

    def voice(self, audio: bytes, mime_type: str) -> tuple[bool, str, str] | dict | str:
        if self.sink is None:
            return (
                False,
                "",
                "O Celsius ainda esta iniciando. Tente novamente em instantes.",
            )
        handler = getattr(self.sink, "_queue_mobile_voice_command", None)
        if not callable(handler):
            return (
                False,
                "",
                "O Celsius ainda esta iniciando. Tente novamente em instantes.",
            )
        return cast(VoiceCommandCallback, handler)(audio, mime_type)

    def close(self) -> None:
        if self.server is not None:
            self.server.stop()
        self.server = None
        self.sink = None


_MOBILE_RUNTIME = MobileAccessRuntime()


def get_mobile_runtime() -> MobileAccessRuntime:
    """Return the process-wide mobile access runtime."""
    return _MOBILE_RUNTIME


def start_for_settings(
    settings: Any,
    *,
    command_callback: CommandCallback,
    voice_command_callback: VoiceCommandCallback | None = None,
    web_proxy_url: str = "",
    web_pairing_code_callback: PairingCodeCallback | None = None,
) -> tuple[MobileAccessServer, str]:
    """Start the mobile server using app settings; returns (server, notice)."""
    host = settings.mobile.host if settings.mobile.allow_lan else "127.0.0.1"
    cert_file = None
    key_file = None
    use_https = bool(settings.mobile.use_https)
    notice = ""
    if use_https:
        try:
            cert_file, key_file = ensure_mobile_certificate(
                Path(settings.data_dir) / "mobile_access"
            )
        except RuntimeError as exc:
            use_https = False
            notice = (
                f"\n\nAviso: HTTPS local indisponivel ({exc}). "
                "O acesso pelo celular foi iniciado em HTTP; alguns navegadores podem bloquear o microfone."
            )

    def build(https: bool) -> MobileAccessServer:
        return MobileAccessServer(
            host=host,
            port=int(settings.mobile.port),
            token=ensure_mobile_token(settings.mobile.pairing_token),
            command_callback=command_callback,
            voice_enabled=bool(settings.mobile.voice_commands_enabled),
            voice_command_callback=voice_command_callback,
            use_https=https,
            cert_file=cert_file if https else None,
            key_file=key_file if https else None,
            web_proxy_url=web_proxy_url,
            web_pairing_code_callback=web_pairing_code_callback,
        )

    server = build(use_https)
    try:
        server.start()
    except Exception as exc:
        if not use_https:
            raise
        notice = (
            f"\n\nAviso: nao foi possivel iniciar HTTPS local ({exc}). "
            "O acesso pelo celular foi iniciado em HTTP; alguns navegadores podem bloquear o microfone."
        )
        server = build(False).start()
    return server, notice


def _mobile_html(_token: str, voice_enabled: bool = True) -> str:
    voice_flag = "true" if voice_enabled else "false"
    return f"""
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>Celsius</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #050706;
      --panel: rgba(28, 32, 30, .88);
      --panel-strong: #202522;
      --bubble-user: #303632;
      --bubble-ai: transparent;
      --bubble-error: rgba(127, 29, 29, .48);
      --text: #f4f6f5;
      --muted: #a0a7a3;
      --quiet: #717975;
      --accent: #79d8b4;
      --accent-strong: #20b887;
      --danger: #ef5b64;
      --ok: #67d6a7;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ height: 100%; }}
    body {{
      margin: 0;
      background:
        radial-gradient(circle at 50% 27%, rgba(45, 111, 88, .18), transparent 34%),
        radial-gradient(circle at 18% 82%, rgba(38, 74, 62, .11), transparent 32%),
        var(--bg);
      color: var(--text);
      font: 15px/1.45 Inter, "Segoe UI", system-ui, -apple-system, sans-serif;
      display: flex;
      flex-direction: column;
      height: 100dvh;
      overflow: hidden;
    }}
    header {{
      min-height: 70px;
      padding: max(14px, env(safe-area-inset-top)) 18px 8px;
      display: flex;
      align-items: center;
      gap: 11px;
      z-index: 3;
    }}
    .brand-mark {{
      width: 34px;
      height: 34px;
      border: 1px solid rgba(255,255,255,.12);
      border-radius: 12px;
      display: grid;
      place-items: center;
      background: linear-gradient(145deg, rgba(121,216,180,.2), rgba(255,255,255,.03));
      box-shadow: inset 0 1px rgba(255,255,255,.1);
      color: var(--accent);
      font-weight: 750;
      font-size: 15px;
    }}
    .brand-copy {{ min-width: 0; }}
    .brand-copy span {{
      display: block;
      margin-top: 1px;
      color: var(--quiet);
      font-size: 10px;
      font-weight: 650;
      letter-spacing: .08em;
      text-transform: uppercase;
    }}
    header h1 {{
      margin: 0;
      font-size: 16px;
      font-weight: 680;
      line-height: 1.1;
      letter-spacing: -.01em;
    }}
    .chip {{
      margin-left: auto;
      display: flex;
      align-items: center;
      gap: 7px;
      min-height: 30px;
      padding: 0 11px;
      border: 1px solid rgba(255,255,255,.08);
      border-radius: 999px;
      background: rgba(255,255,255,.035);
      font-size: 11px;
      color: var(--muted);
    }}
    .chip .dot {{
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--ok);
      box-shadow: 0 0 0 4px rgba(103,214,167,.08), 0 0 10px rgba(103,214,167,.5);
    }}
    .stage {{
      position: relative;
      min-height: 280px;
      flex: 1 1 auto;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      overflow: hidden;
      padding: 6px 20px 16px;
    }}
    .orb-wrap {{
      position: relative;
      display: grid;
      place-items: center;
      width: min(92vw, 49vh, 380px);
      aspect-ratio: 1;
      isolation: isolate;
    }}
    .orb-wrap::before,
    .orb-wrap::after {{
      position: absolute;
      border-radius: 50%;
      content: "";
      pointer-events: none;
    }}
    .orb-wrap::before {{
      inset: 4%;
      border: 1px solid rgba(121,216,180,.08);
      box-shadow: 0 0 70px rgba(45,170,128,.14);
    }}
    .orb-wrap::after {{
      inset: 17%;
      z-index: -1;
      background: rgba(46, 152, 117, .16);
      filter: blur(34px);
    }}
    canvas#orb {{ width: 100%; height: 100%; }}
    .stage-copy {{
      min-height: 58px;
      margin-top: -7px;
      text-align: center;
    }}
    .stage-copy strong {{
      display: block;
      color: var(--text);
      font-size: 18px;
      font-weight: 620;
      letter-spacing: -.02em;
    }}
    #orbHint {{
      min-height: 20px;
      margin-top: 5px;
      font-size: 12px;
      color: var(--muted);
    }}
    #chat {{
      flex: 0 1 auto;
      max-height: 26dvh;
      overflow-y: auto;
      padding: 0 18px 10px;
      display: flex;
      flex-direction: column;
      gap: 9px;
      -webkit-overflow-scrolling: touch;
      scrollbar-width: none;
    }}
    #chat::-webkit-scrollbar {{ display: none; }}
    .msg {{
      max-width: 88%;
      padding: 10px 13px;
      border-radius: 18px;
      font-size: 14px;
      line-height: 1.45;
      white-space: pre-wrap;
      word-break: break-word;
    }}
    .msg.user {{
      align-self: flex-end;
      background: var(--bubble-user);
      border-bottom-right-radius: 6px;
    }}
    .msg.ai {{
      align-self: flex-start;
      background: var(--bubble-ai);
      color: #e4e9e6;
      padding-left: 2px;
    }}
    .msg.err {{
      align-self: flex-start;
      background: var(--bubble-error);
      border-bottom-left-radius: 4px;
    }}
    .msg.ref {{
      align-self: center;
      background: transparent;
      color: var(--muted);
      font-size: clamp(11px, 3.2vw, 13px);
      padding: 2px 8px;
      max-width: 92%;
    }}
    .empty {{
      margin: 0 auto;
      text-align: center;
      color: var(--quiet);
      font-size: 12px;
      padding: 0 20px;
    }}
    footer {{
      position: relative;
      z-index: 4;
      padding: 10px 12px max(12px, env(safe-area-inset-bottom));
      display: flex;
      gap: 8px;
      align-items: center;
      background: linear-gradient(transparent, rgba(5,7,6,.97) 26%);
    }}
    #input {{
      flex: 1;
      resize: none;
      min-height: 50px;
      max-height: 120px;
      background: var(--panel);
      color: var(--text);
      border: 1px solid rgba(255,255,255,.09);
      border-radius: 25px;
      padding: 14px 16px;
      font: 14px/1.35 inherit;
      outline: none;
      box-shadow: inset 0 1px rgba(255,255,255,.035);
    }}
    #input:focus {{ border-color: rgba(121,216,180,.42); }}
    #input::placeholder {{ color: #727a76; }}
    .icon-btn {{
      width: 50px;
      height: 50px;
      flex: 0 0 auto;
      border: 1px solid rgba(255,255,255,.09);
      border-radius: 50%;
      background: var(--panel);
      color: var(--text);
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      touch-action: manipulation;
      -webkit-tap-highlight-color: transparent;
      transition: transform .16s ease, background .16s ease, box-shadow .16s ease;
    }}
    .icon-btn:active {{ transform: scale(.93); }}
    .icon-btn:disabled {{ opacity: 0.4; }}
    .icon-btn.send {{
      width: 46px;
      height: 46px;
      border-color: transparent;
      background: #f2f5f3;
      color: #111513;
    }}
    .icon-btn.mic {{
      width: 58px;
      height: 58px;
      border-color: rgba(121,216,180,.28);
      background: linear-gradient(145deg, #88e2c0, #47bd91);
      color: #062118;
      box-shadow: 0 8px 28px rgba(32,184,135,.22), inset 0 1px rgba(255,255,255,.38);
    }}
    .icon-btn.mic.rec {{ background: var(--danger); color: #fff; }}
    .icon-btn.mic.busy {{ animation: pulsebusy 1.4s infinite; }}
    @keyframes pulsebusy {{
      0%, 100% {{ box-shadow: 0 0 0 0 rgba(56, 189, 248, 0.35); }}
      50% {{ box-shadow: 0 0 0 8px rgba(56, 189, 248, 0); }}
    }}
    .icon-btn svg {{ width: 21px; height: 21px; }}
    .icon-btn.mic svg {{ width: 25px; height: 25px; }}
    @media (max-height: 700px) {{
      header {{ min-height: 58px; padding-top: 10px; }}
      .stage {{ min-height: 230px; padding-bottom: 4px; }}
      .orb-wrap {{ width: min(64vw, 38vh, 260px); }}
      #chat {{ max-height: 21dvh; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="brand-mark">C</div>
    <div class="brand-copy"><h1>Celsius</h1><span>Conversa por voz</span></div>
    <div class="chip"><span class="dot"></span><span id="statusText">Local</span></div>
  </header>
  <div class="stage">
    <div class="orb-wrap"><canvas id="orb" width="340" height="340"></canvas></div>
    <div class="stage-copy">
      <strong id="voiceState">Como posso ajudar?</strong>
      <div id="orbHint"></div>
    </div>
  </div>
  <div id="chat">
    <div class="empty" id="chatEmpty">Fale ou digite para conversar com o Celsius.</div>
  </div>
  <footer>
    <textarea id="input" rows="1" placeholder="Mensagem ao Celsius"></textarea>
    <button class="icon-btn send" id="sendBtn" type="button" title="Enviar" aria-label="Enviar">
      <svg viewBox="0 0 24 24" fill="currentColor"><path d="M3.4 20.4 20.85 12 3.4 3.6l.5 6.5 10.7 1.9-10.7 1.9z"/></svg>
    </button>
    <button class="icon-btn mic" id="micBtn" type="button" title="Falar ao vivo" aria-label="Falar ao vivo">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0"/><path d="M12 18v3"/></svg>
    </button>
  </footer>
  <script>
    if (location.search) history.replaceState(null, "", location.pathname);
    const voiceEnabled = {voice_flag};
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    const TARGET_SAMPLE_RATE = 16000;

    function $(id) {{ return document.getElementById(id); }}
    const statusText = $("statusText");
    const voiceState = $("voiceState");
    const orbHint = $("orbHint");
    const chatEl = $("chat");
    const chatEmpty = $("chatEmpty");
    const inputEl = $("input");
    const sendBtn = $("sendBtn");
    const micBtn = $("micBtn");
    const orbCanvas = $("orb");
    const orbCtx = orbCanvas.getContext("2d");

    function resizeOrb() {{
      const rect = orbCanvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 3);
      const px = Math.round(Math.max(1, rect.width) * dpr);
      if (orbCanvas.width !== px) orbCanvas.width = px;
      if (orbCanvas.height !== px) orbCanvas.height = px;
    }}
    window.addEventListener("resize", resizeOrb);
    window.addEventListener("orientationchange", function () {{
      setTimeout(resizeOrb, 120);
    }});
    if (window.visualViewport) {{
      window.visualViewport.addEventListener("resize", resizeOrb);
    }}
    resizeOrb();

    let lastResponseVersion = 0;
    let lastResponseAudioVersion = 0;
    const responseAudio = new Audio();
    let responseAudioUrl = "";
    let responsePollTimer = null;
    let audioCtx = null;
    let stream = null;
    let sourceNode = null;
    let processor = null;
    let recording = false;
    let autoStopping = false;
    let chunks = [];
    let samplesBuffer = null;
    let speechStartedAt = 0;
    let silenceStartedAt = 0;
    let noiseFloor = 0.006;
    let micDrive = 0;
    let decodedBuffer = null;
    let decodedRate = 0;
    let decodeCtx = null;
    let orbState = "idle";
    let drive = 0;
    let rings = [];

    function setStatus(text) {{
      statusText.textContent = text;
      const normalized = (text || "").toLowerCase();
      if (normalized.includes("ouvindo") || normalized.includes("gravando")) {{
        voiceState.textContent = "Estou ouvindo";
      }} else if (normalized.includes("process") || normalized.includes("enviando")) {{
        voiceState.textContent = "Pensando...";
      }} else if (normalized.includes("falando")) {{
        voiceState.textContent = "Respondendo";
      }} else if (normalized.includes("erro")) {{
        voiceState.textContent = "Tente novamente";
      }} else if (normalized.includes("conectado") || normalized.includes("local")) {{
        voiceState.textContent = "Como posso ajudar?";
      }}
    }}
    function setHint(text) {{ orbHint.textContent = text || ""; }}
    function setDot(ok) {{
      const dot = document.querySelector(".chip .dot");
      dot.style.background = ok ? "var(--ok)" : "#64748b";
      dot.style.boxShadow = ok ? "0 0 6px var(--ok)" : "none";
    }}

    function addMsg(role, text) {{
      if (chatEmpty) chatEmpty.remove();
      const div = document.createElement("div");
      div.className = "msg " + role;
      div.textContent = text || "";
      chatEl.appendChild(div);
      chatEl.scrollTop = chatEl.scrollHeight;
      return div;
    }}

    function replaceAiBubble(text) {{
      let bubble = chatEl.querySelector(":scope > .msg.ai, :scope > .msg.err");
      if (!bubble) bubble = addMsg("ai", "");
      bubble.textContent = text || "";
      chatEl.scrollTop = chatEl.scrollHeight;
      return bubble;
    }}

    function sleep(ms) {{ return new Promise(resolve => setTimeout(resolve, ms)); }}

    async function fetchJson(path, options, timeoutMs) {{
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), timeoutMs || 12000);
      try {{
        const response = await fetch(path, {{
          ...options,
          credentials: "same-origin",
          signal: controller.signal
        }});
        let data = {{}};
        try {{ data = await response.json(); }} catch (err) {{ data = {{}}; }}
        if (!response.ok && !data.message) {{
          data.message = "Erro HTTP " + response.status + " ao falar com o Celsius.";
        }}
        return data;
      }} catch (err) {{
        if (err.name === "AbortError") {{
          return {{ ok: false, message: "Tempo esgotado. Verifique a rede Wi-Fi e o firewall." }};
        }}
        return {{ ok: false, message: "Falha de conexao. Confirme o certificado e a rede Wi-Fi." }};
      }} finally {{
        clearTimeout(timer);
      }}
    }}

    function clearResponseAudio() {{
      responseAudio.pause();
      responseAudio.removeAttribute("src");
      responseAudio.load();
      if (responseAudioUrl) URL.revokeObjectURL(responseAudioUrl);
      responseAudioUrl = "";
      decodedBuffer = null;
      decodedRate = 0;
    }}

    function stopPcAudio() {{
      responseAudio.pause();
      responseAudio.currentTime = 0;
      setHint("Audio parado.");
    }}

    async function loadPcAudio(responseVersion, retries) {{
      if (!responseVersion) return false;
      const tries = retries || 16;
      for (let attempt = 0; attempt < tries; attempt++) {{
        const url = "/api/last-audio?response_version=" + responseVersion
          + "&after_audio_version=" + lastResponseAudioVersion + "&t=" + Date.now();
        const response = await fetch(url, {{ credentials: "same-origin" }});
        if (response.status === 200) {{
          const blob = await response.blob();
          clearResponseAudio();
          responseAudioUrl = URL.createObjectURL(blob);
          responseAudio.src = responseAudioUrl;
          lastResponseAudioVersion = Number(
            response.headers.get("X-Celsius-Audio-Version") || lastResponseAudioVersion
          );
          startDecode(blob);
          return true;
        }}
        if (response.status !== 204) return false;
        await sleep(500);
      }}
      return false;
    }}

    function startDecode(blob) {{
      try {{
        decodeCtx = decodeCtx || new AudioContextClass();
        blob.arrayBuffer()
          .then(buf => decodeCtx.decodeAudioData(buf))
          .then(decoded => {{
            if (!responseAudio.src) return;
            decodedBuffer = decoded.getChannelData(0);
            decodedRate = decoded.sampleRate;
          }})
          .catch(() => {{ decodedBuffer = null; }});
      }} catch (err) {{
        decodedBuffer = null;
      }}
    }}

    function playbackLevel() {{
      if (responseAudio.paused || responseAudio.ended || !decodedBuffer || !decodedRate) return 0;
      const start = Math.floor(responseAudio.currentTime * decodedRate);
      if (start < 0 || start >= decodedBuffer.length - 1) return 0;
      const win = Math.min(4000, decodedBuffer.length - start - 1);
      let sum = 0;
      for (let i = 0; i < win; i++) {{
        const s = decodedBuffer[start + i];
        sum += s * s;
      }}
      return Math.sqrt(sum / win) * 6;
    }}

    async function playPcAudio(responseVersion) {{
      if (!responseVersion) return false;
      const loaded = await loadPcAudio(responseVersion);
      if (!loaded) {{
        setHint("Ainda sem audio gerado no PC.");
        return false;
      }}
      try {{
        await responseAudio.play();
        setHint("Celsius falando...");
        orbState = "idle";
        return true;
      }} catch (err) {{
        setHint("Toque na esfera para ouvir a resposta.");
        return false;
      }}
    }}

    function toggleOrbPlayback() {{
      if (!responseAudio.src) return;
      if (!responseAudio.paused) {{
        stopPcAudio();
        return;
      }}
      playPcAudio(lastResponseVersion);
    }}

    orbCanvas.addEventListener("pointerdown", () => {{
      if (recording) return;
      toggleOrbPlayback();
    }});

    async function sendCommand(text) {{
      const clean = (text || "").trim();
      if (!clean) return;
      addMsg("user", clean);
      inputEl.value = "";
      inputEl.style.height = "42px";
      sendBtn.disabled = true;
      setStatus("Enviando...");
      const data = await fetchJson("/api/command", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ message: clean, source: "phone_text" }})
      }}, 20000);
      if (data.ok) {{
        lastResponseVersion = Number(data.response_version || lastResponseVersion);
        waitForResponse();
      }} else {{
        setStatus("Erro");
        addMsg("ref", data.message || "Nao foi possivel enviar a mensagem.");
      }}
    }}

    function waitForResponse() {{
      clearInterval(responsePollTimer);
      setStatus("Gerando...");
      setHint("");
      orbState = "thinking";
      replaceAiBubble("");
      const started = Date.now();
      responsePollTimer = setInterval(async () => {{
        const data = await fetchJson(
          "/api/last-response?after=" + lastResponseVersion, {{}}, 12000
        );
        if (data.ok && data.live_active && data.live_text) {{
          replaceAiBubble(data.live_text);
          return;
        }}
        if (data.ok && data.has_new && data.text) {{
          clearInterval(responsePollTimer);
          lastResponseVersion = Number(data.version || lastResponseVersion);
          const isError = data.kind === "error";
          const bubble = replaceAiBubble(data.text);
          if (isError) bubble.className = "msg err";
          setStatus(isError ? "Erro no PC" : "Resposta recebida");
          orbState = "idle";
          if (!isError) playPcAudio(lastResponseVersion);
          return;
        }}
        if (Date.now() - started > 120000) {{
          clearInterval(responsePollTimer);
          setStatus("Sem resposta");
          setHint("Veja se o Celsius terminou de responder no PC.");
          orbState = "idle";
        }}
      }}, 1200);
    }}

    function calculateRms(samples) {{
      let sum = 0;
      for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
      return Math.sqrt(sum / Math.max(1, samples.length));
    }}

    async function startRecording() {{
      if (recording) return;
      try {{
        stream = await navigator.mediaDevices.getUserMedia({{
          audio: {{
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
            channelCount: 1
          }}
        }});
        audioCtx = audioCtx || new AudioContextClass();
        if (audioCtx.state === "suspended") await audioCtx.resume();
        sourceNode = audioCtx.createMediaStreamSource(stream);
        processor = audioCtx.createScriptProcessor(4096, 1, 1);
        chunks = [];
        samplesBuffer = null;
        speechStartedAt = 0;
        silenceStartedAt = 0;
        noiseFloor = 0.006;
        autoStopping = false;
        recording = true;
        micDrive = 0;
        orbState = "listening";
        setStatus("Ouvindo voce...");
        setHint("Continue falando; para de falar para enviar.");
        micBtn.classList.add("rec");
        processor.onaudioprocess = (event) => {{
          const samples = event.inputBuffer.getChannelData(0);
          samplesBuffer = samples;
          const level = calculateRms(samples);
          micDrive = Math.min(1, level * 10);
          if (!recording) return;
          chunks.push(new Float32Array(samples));
          const now = Date.now();
          const threshold = Math.max(0.012, Math.min(0.034, noiseFloor * 2.8));
          if (level <= threshold) {{
            noiseFloor = Math.min(0.012, noiseFloor * 0.96 + level * 0.04);
            if (speechStartedAt && !silenceStartedAt) silenceStartedAt = now;
          }} else {{
            if (!speechStartedAt) speechStartedAt = now;
            silenceStartedAt = 0;
          }}
          if (speechStartedAt && silenceStartedAt
            && now - speechStartedAt >= 300 && now - silenceStartedAt >= 1100) {{
            if (!autoStopping) {{ autoStopping = true; stopRecording(); }}
          }}
        }};
        sourceNode.connect(processor);
        processor.connect(audioCtx.destination);
        setTimeout(() => {{ if (recording) stopRecording(); }}, 15000);
      }} catch (err) {{
        setStatus("Microfone bloqueado");
        setHint("Autorize o microfone do site HTTPS no navegador.");
        orbState = "idle";
        cleanupAudio();
      }}
    }}

    function hasEnergy(list) {{
      for (const c of list) {{
        let s = 0;
        for (let i = 0; i < c.length; i++) s += c[i] * c[i];
        if (Math.sqrt(s / Math.max(1, c.length)) > 0.008) return true;
      }}
      return false;
    }}

    async function stopRecording() {{
      if (!recording) return;
      recording = false;
      micBtn.classList.remove("rec");
      orbState = "idle";
      micDrive = 0;
      const audio = chunks.slice();
      const hasSpeech = Boolean(audio.length && hasEnergy(audio));
      const sampleRate = audioCtx ? audioCtx.sampleRate : 44100;
      cleanupAudio();
      if (!hasSpeech) {{
        setStatus("Pronto");
        setHint("Nenhuma fala detectada.");
        return;
      }}
      setStatus("Transcrevendo no PC...");
      await sendVoice(encodeWav(audio, sampleRate));
    }}

    function cleanupAudio() {{
      if (processor) processor.disconnect();
      if (sourceNode) sourceNode.disconnect();
      if (stream) stream.getTracks().forEach(track => track.stop());
      if (audioCtx && audioCtx.state === "running") audioCtx.close().catch(() => {{}});
      audioCtx = null;
      stream = null;
      sourceNode = null;
      processor = null;
      samplesBuffer = null;
      chunks = [];
      micDrive = 0;
    }}

    function blobToBase64(blob) {{
      return new Promise((resolve, reject) => {{
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result).split(",")[1]);
        reader.onerror = reject;
        reader.readAsDataURL(blob);
      }});
    }}

    function flattenAudio(chunks) {{
      const length = chunks.reduce((total, chunk) => total + chunk.length, 0);
      const samples = new Float32Array(length);
      let offset = 0;
      for (const chunk of chunks) {{
        samples.set(chunk, offset);
        offset += chunk.length;
      }}
      return samples;
    }}

    function downsample(samples, sourceRate, targetRate) {{
      if (sourceRate === targetRate) return samples;
      const ratio = sourceRate / targetRate;
      const newLength = Math.max(1, Math.round(samples.length / ratio));
      const result = new Float32Array(newLength);
      for (let i = 0; i < newLength; i++) {{
        const start = Math.floor(i * ratio);
        const end = Math.min(Math.floor((i + 1) * ratio), samples.length);
        let sum = 0;
        let count = 0;
        for (let j = start; j < end; j++) {{
          sum += samples[j];
          count++;
        }}
        result[i] = count ? sum / count : samples[Math.min(start, samples.length - 1)];
      }}
      return result;
    }}

    function encodeWav(chunks, sampleRate) {{
      const sourceSamples = flattenAudio(chunks);
      const samples = downsample(sourceSamples, sampleRate, TARGET_SAMPLE_RATE);
      const buffer = new ArrayBuffer(44 + samples.length * 2);
      const view = new DataView(buffer);
      writeAscii(view, 0, "RIFF");
      view.setUint32(4, 36 + samples.length * 2, true);
      writeAscii(view, 8, "WAVE");
      writeAscii(view, 12, "fmt ");
      view.setUint32(16, 16, true);
      view.setUint16(20, 1, true);
      view.setUint16(22, 1, true);
      view.setUint32(24, TARGET_SAMPLE_RATE, true);
      view.setUint32(28, TARGET_SAMPLE_RATE * 2, true);
      view.setUint16(32, 2, true);
      view.setUint16(34, 16, true);
      writeAscii(view, 36, "data");
      view.setUint32(40, samples.length * 2, true);
      let index = 44;
      for (let i = 0; i < samples.length; i++) {{
        const sample = Math.max(-1, Math.min(1, samples[i]));
        view.setInt16(index, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
        index += 2;
      }}
      return new Blob([view], {{ type: "audio/wav" }});
    }}

    function writeAscii(view, offset, text) {{
      for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i));
    }}

    async function sendVoice(blob) {{
      const data = await fetchJson("/api/voice-command", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{
          audio_base64: await blobToBase64(blob),
          mime_type: blob.type || "audio/wav"
        }})
      }}, 45000);
      if (data.ok && data.transcript) {{
        addMsg("user", data.transcript);
        if (data.command_submitted === false) {{
          setStatus("Escuta ativa");
          setHint("Fale seu pedido agora.");
          orbState = "listening";
          return;
        }}
        lastResponseVersion = Number(data.response_version || lastResponseVersion);
        waitForResponse();
      }} else {{
        setStatus("Erro ao enviar voz");
        addMsg("ref", data.message || "Nao foi possivel enviar a voz.");
        orbState = "idle";
      }}
    }}

    micBtn.addEventListener("click", async () => {{
      if (recording) {{
        await stopRecording();
        return;
      }}
      if (!voiceEnabled || !navigator.mediaDevices || !AudioContextClass) {{
        setStatus("Voz indisponivel neste navegador");
        return;
      }}
      await startRecording();
    }});

    sendBtn.addEventListener("click", () => sendCommand(inputEl.value));

    inputEl.addEventListener("keydown", (event) => {{
      if (event.key === "Enter" && !event.shiftKey) {{
        event.preventDefault();
        sendCommand(inputEl.value);
      }}
    }});

    inputEl.addEventListener("input", () => {{
      inputEl.style.height = "42px";
      inputEl.style.height = Math.min(120, inputEl.scrollHeight) + "px";
      sendBtn.disabled = !inputEl.value.trim();
    }});

    responseAudio.addEventListener("ended", () => {{
      orbState = "idle";
      setHint("Toque na esfera para ouvir de novo.");
    }});

    responseAudio.addEventListener("pause", () => {{
      if (orbState === "speaking") orbState = "idle";
    }});

    function sphereColor(state) {{
      if (state === "speaking") return [167, 139, 250];
      if (state === "listening") return [104, 218, 177];
      if (state === "thinking") return [110, 168, 245];
      return [72, 177, 143];
    }}

    function drawOrb(now) {{
      const w = orbCanvas.width;
      const h = orbCanvas.height;
      const state = orbState;
      const level = Math.max(micDrive, playbackLevel());
      let target = level;
      if (state === "thinking") target = Math.max(target, 0.35);
      if (state === "speaking") target = Math.max(target, 0.5);
      drive += (target - drive) * 0.1;
      const breathe = 0.5 + 0.5 * Math.sin(now / 900);
      const scale = 1 + drive * 0.3 + (state === "idle" ? breathe * 0.05 : 0);
      const r = w * 0.35 * scale;
      const base = sphereColor(state);

      rings.push({{ r: r, speed: 1.6, alpha: Math.max(0, Math.min(0.6, drive * 0.7)) }});
      rings.forEach(ring => {{
        ring.r += ring.speed;
        ring.alpha *= 0.94;
      }});
      rings = rings.filter(ring => ring.alpha > 0.02 && ring.r < w * 0.7);

      orbCtx.clearRect(0, 0, w, h);
      const cx = w / 2;
      const cy = h / 2;

      const glue = "rgba(" + base[0] + "," + base[1] + "," + base[2] + ",";
      const glow = orbCtx.createRadialGradient(cx, cy, r * 0.2, cx, cy, r * 1.9);
      glow.addColorStop(0, glue + (0.22 * drive + 0.08) + ")");
      glow.addColorStop(1, glue + "0)");
      orbCtx.fillStyle = glow;
      orbCtx.fillRect(0, 0, w, h);

      for (const ring of rings) {{
        orbCtx.beginPath();
        orbCtx.arc(cx, cy, ring.r, 0, Math.PI * 2);
        orbCtx.strokeStyle = glue + ring.alpha + ")";
        orbCtx.lineWidth = 2;
        orbCtx.stroke();
      }}

      const hi0 = Math.min(255, base[0] + 45);
      const hi1 = Math.min(255, base[1] + 45);
      const hi2 = Math.min(255, base[2] + 45);
      const gn = orbCtx.createRadialGradient(cx - r * 0.3, cy - r * 0.35, r * 0.1, cx, cy, r * 1.15);
      gn.addColorStop(0, "rgb(" + hi0 + "," + hi1 + "," + hi2 + ")");
      gn.addColorStop(0.45, "rgb(" + base[0] + "," + base[1] + "," + base[2] + ")");
      gn.addColorStop(1, "rgb(" + Math.round(base[0] * 0.25) + "," + Math.round(base[1] * 0.25) + "," + Math.round(base[2] * 0.25) + ")");
      orbCtx.beginPath();
      orbCtx.arc(cx, cy, r, 0, Math.PI * 2);
      orbCtx.fillStyle = gn;
      orbCtx.fill();

      const coreAlpha = Math.min(0.7, 0.2 + drive * 0.55 + (state === "speaking" ? 0.2 : 0));
      const coreGlow = orbCtx.createRadialGradient(cx, cy, 1, cx, cy, r * 0.6);
      coreGlow.addColorStop(0, "rgba(255,255,255," + coreAlpha + ")");
      coreGlow.addColorStop(1, "rgba(255,255,255,0)");
      orbCtx.beginPath();
      orbCtx.arc(cx, cy, r * 0.6, 0, Math.PI * 2);
      orbCtx.fillStyle = coreGlow;
      orbCtx.fill();

      requestAnimationFrame(drawOrb);
    }}

    try {{
      if (!navigator.mediaDevices || !AudioContextClass) {{
        micBtn.disabled = true;
        micBtn.title = "Voz indisponivel";
      }}
      inputEl.style.height = "42px";
      sendBtn.disabled = true;
      requestAnimationFrame(drawOrb);
      fetchJson("/api/status", {{}}, 6000).then(data => {{
        if (data.ok) {{
          setStatus("Conectado");
          setDot(true);
          setHint("Fale ao vivo ou digite uma mensagem.");
        }}
      }});
    }} catch (err) {{
      setStatus("Erro ao iniciar");
    }}
  </script>
</body>
</html>
"""
