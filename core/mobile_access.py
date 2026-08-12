import base64
import datetime as dt
import ipaddress
import json
import secrets
import socket
import ssl
import threading
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from core.file_security import restrict_private_file

CommandCallback = Callable[[str, str], tuple[bool, str] | bool | None]
VoiceCommandCallback = Callable[[bytes, str], tuple[bool, str, str] | dict | str]


def ensure_mobile_token(current: str = "") -> str:
    token = (current or "").strip()
    if token:
        return token
    return secrets.token_urlsafe(24)


def get_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def build_mobile_url(host: str, port: int, token: str, *, use_https: bool = False) -> str:
    display_host = get_lan_ip() if host in {"0.0.0.0", "::"} else host
    scheme = "https" if use_https else "http"
    return f"{scheme}://{display_host}:{port}/?token={token}"


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
    san_items = [x509.DNSName("localhost")]
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


def _is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _create_server_ssl_context():
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
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._response_lock = threading.Lock()
        self._response_version = 0
        self._last_response_text = ""
        self._last_response_kind = "assistant"
        self._audio_version = 0
        self._last_audio = b""
        self._last_audio_mime = "audio/mpeg"
        self._last_audio_response_version = 0
        self._response_audio_version = 0
        self._audio_chunks: list[dict[str, bytes | str | int]] = []

    @property
    def is_running(self) -> bool:
        return self._httpd is not None

    @property
    def url(self) -> str:
        port = self._httpd.server_address[1] if self._httpd else self.port
        return build_mobile_url(self.host, port, self.token, use_https=self.use_https)

    def start(self):
        if self._httpd is not None:
            return self
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

    def stop(self):
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
            return self._response_version

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
                        bytes(chunk["audio"]),
                        str(chunk["mime_type"]),
                        int(chunk["version"]),
                    )
            return None

    def _make_handler(self):
        server_ref = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, _format, *_args):
                return

            def do_GET(self):
                parsed = urlparse(self.path)
                if parsed.path == "/":
                    token = parse_qs(parsed.query).get("token", [""])[0]
                    page_token = token if secrets.compare_digest(token, server_ref.token) else ""
                    self._send_html(_mobile_html(page_token, server_ref.voice_enabled))
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

            def do_POST(self):
                parsed = urlparse(self.path)
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
                    self._send_json(
                        {
                            "ok": False,
                            "message": f"Erro ao entregar comando ao Celsius: {exc}",
                        },
                        HTTPStatus.INTERNAL_SERVER_ERROR,
                    )
                    return
                if isinstance(result, tuple):
                    accepted, detail = result
                else:
                    accepted, detail = bool(result is not False), "Comando enviado ao Celsius."
                self._send_json(
                    {
                        "ok": bool(accepted),
                        "message": detail,
                        "response_version": server_ref.latest_response()["version"],
                    }
                )

            def _handle_voice_command(self):
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
                    self._send_json(
                        {
                            "ok": False,
                            "message": f"Erro ao processar voz no Celsius: {exc}",
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
                token = parse_qs(urlparse(self.path).query).get("token", [""])[0]
                return secrets.compare_digest(token, server_ref.token)

            def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK):
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_html(self, html: str):
                body = html.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
                self.send_header("Pragma", "no-cache")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_audio(self, audio: bytes, mime_type: str, audio_version: int):
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", mime_type or "audio/mpeg")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Celsius-Audio-Version", str(audio_version))
                self.send_header("Content-Length", str(len(audio)))
                self.end_headers()
                self.wfile.write(audio)

        return Handler


def _mobile_html(token: str, voice_enabled: bool) -> str:
    voice_flag = "true" if voice_enabled else "false"
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Celsius Project AI</title>
  <style>
    :root {{
      color-scheme: dark;
      font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
      background: #0D1117;
      color: #E6EDF3;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      background: #0D1117;
      color: #E6EDF3;
    }}
    .app-shell {{
      width: min(100%, 560px);
      min-height: 100vh;
      margin: 0 auto;
      display: grid;
      grid-template-rows: auto auto 1fr auto;
      gap: 14px;
      padding: 16px;
    }}
    .topbar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 10px 2px 4px;
    }}
    .brand {{
      display: flex;
      align-items: baseline;
      gap: 6px;
      letter-spacing: 0;
      white-space: nowrap;
    }}
    .brand strong {{ color: #E6EDF3; font-size: 25px; line-height: 1; }}
    .brand span {{ color: #8B949E; font-size: 17px; font-weight: 600; }}
    .brand b {{ color: #58A6FF; font-size: 17px; }}
    .connection-chip {{
      border: 1px solid #30363D;
      background: #161B22;
      color: #8B949E;
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 12px;
      font-weight: 700;
    }}
    .panel {{
      border: 1px solid #30363D;
      background: #161B22;
      border-radius: 8px;
      padding: 14px;
      box-shadow: 0 8px 20px rgba(0, 0, 0, 0.18);
    }}
    .section-row {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 10px;
    }}
    .section-title {{
      color: #E6EDF3;
      font-size: 13px;
      font-weight: 800;
      text-transform: uppercase;
    }}
    .hint {{
      color: #8B949E;
      font-size: 13px;
      line-height: 1.45;
      margin: 0 0 12px;
    }}
    .voice-stage {{
      display: grid;
      place-items: center;
      gap: 14px;
      padding: 20px 12px 10px;
    }}
    .voice-orb {{
      --level: 0;
      width: 176px;
      aspect-ratio: 1;
      border-radius: 50%;
      border: 1px solid rgba(88, 166, 255, 0.38);
      background:
        radial-gradient(circle at 35% 30%, rgba(255, 255, 255, 0.9), transparent 0 9%),
        radial-gradient(circle at 50% 45%, rgba(88, 166, 255, 0.92), rgba(35, 134, 54, 0.72) 40%, rgba(88, 166, 255, 0.14) 72%),
        #0D1117;
      box-shadow:
        0 0 calc(22px + var(--level) * 56px) rgba(88, 166, 255, 0.42),
        inset 0 0 42px rgba(255, 255, 255, 0.08);
      transform: scale(calc(1 + var(--level) * 0.12));
      transition: transform 90ms linear, box-shadow 90ms linear, filter 160ms ease;
    }}
    .voice-orb.listening {{
      animation: orbPulse 2.4s ease-in-out infinite;
      filter: saturate(1.18);
    }}
    .voice-orb.speaking {{
      border-color: rgba(126, 231, 135, 0.62);
      filter: hue-rotate(26deg) saturate(1.35);
    }}
    .voice-state {{
      color: #E6EDF3;
      min-height: 20px;
      font-size: 14px;
      font-weight: 760;
      text-align: center;
    }}
    .voice-substate {{
      color: #8B949E;
      min-height: 18px;
      font-size: 12px;
      text-align: center;
    }}
    .voice-primary {{
      width: min(100%, 280px);
      background: #1F6FEB;
      border-color: #58A6FF;
      color: #FFFFFF;
    }}
    .voice-primary.active {{
      background: #DA3633;
      border-color: #F85149;
    }}
    @keyframes orbPulse {{
      0%, 100% {{ box-shadow: 0 0 24px rgba(88, 166, 255, 0.36), inset 0 0 42px rgba(255, 255, 255, 0.08); }}
      50% {{ box-shadow: 0 0 48px rgba(88, 166, 255, 0.58), inset 0 0 48px rgba(255, 255, 255, 0.12); }}
    }}
    textarea {{
      width: 100%;
      min-height: 132px;
      resize: vertical;
      border-radius: 8px;
      border: 1px solid #30363D;
      background: #0D1117;
      color: #E6EDF3;
      padding: 13px;
      font-size: 16px;
      line-height: 1.45;
      outline: none;
    }}
    textarea:focus {{ border-color: #58A6FF; }}
    .actions {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
      margin-top: 10px;
    }}
    .secondary-actions {{
      grid-template-columns: 1fr 1fr;
      margin-top: 10px;
    }}
    #test {{ grid-column: 1 / -1; }}
    button {{
      min-height: 46px;
      border: 1px solid #30363D;
      background: #21262D;
      color: #E6EDF3;
      border-radius: 8px;
      padding: 12px 14px;
      font-weight: 750;
      font-size: 15px;
      cursor: pointer;
    }}
    button:disabled {{
      cursor: not-allowed;
      opacity: 0.55;
    }}
    button.primary {{
      background: #238636;
      border-color: #238636;
      color: #FFFFFF;
    }}
    button.voice {{
      background: #1F6FEB;
      border-color: #1F6FEB;
      color: #FFFFFF;
    }}
    button.subtle {{
      background: #161B22;
      color: #8B949E;
    }}
    .toggle {{
      color: #8B949E;
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 13px;
      font-weight: 650;
      user-select: none;
    }}
    .toggle input {{ accent-color: #58A6FF; }}
    #response {{
      min-height: 128px;
      white-space: pre-wrap;
      border: 1px solid #30363D;
      background: #0D1117;
      border-radius: 8px;
      padding: 14px;
      color: #E6EDF3;
      line-height: 1.5;
      font-size: 15px;
    }}
    #status {{
      position: sticky;
      bottom: 0;
      min-height: 44px;
      border: 1px solid #30363D;
      background: #161B22;
      color: #8B949E;
      border-radius: 8px;
      padding: 12px 14px;
      font-size: 13px;
      line-height: 1.35;
    }}
    .top-actions {{
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 8px;
    }}
    .theme-toggle {{
      min-height: 34px;
      border-radius: 999px;
      padding: 7px 10px;
      font-size: 12px;
      font-weight: 800;
    }}
    :root {{
      color-scheme: light;
      --bg: #FFFFFF;
      --surface: #FAFAFA;
      --surface-strong: #F5F5F5;
      --input: #FFFFFF;
      --text: #171717;
      --muted: #525252;
      --faint: #737373;
      --border: #E5E5E5;
      --border-strong: #D4D4D4;
      --brand: #171717;
      --brand-soft: #F5F5F5;
      --accent: #2563EB;
      --accent-hover: #1D4ED8;
      --success: #16A34A;
      --danger: #DC2626;
      --shadow: rgba(15, 23, 42, 0.08);
    }}
    body.dark {{
      color-scheme: dark;
      --bg: #0D1117;
      --surface: #161B22;
      --surface-strong: #21262D;
      --input: #0D1117;
      --text: #E6EDF3;
      --muted: #8B949E;
      --faint: #6E7681;
      --border: #30363D;
      --border-strong: #484F58;
      --brand: #58A6FF;
      --brand-soft: #1A3A5C;
      --accent: #1F6FEB;
      --accent-hover: #388BF0;
      --success: #3FB950;
      --danger: #F85149;
      --shadow: rgba(0, 0, 0, 0.22);
    }}
    body {{
      background: var(--bg);
      color: var(--text);
    }}
    .brand strong {{ color: var(--text); }}
    .brand span {{ color: var(--muted); }}
    .brand b {{ color: var(--accent); }}
    .connection-chip,
    .panel,
    #status {{
      border-color: var(--border);
      background: var(--surface);
      color: var(--muted);
      box-shadow: 0 8px 20px var(--shadow);
    }}
    .section-title,
    .voice-state {{
      color: var(--text);
    }}
    .hint,
    .voice-substate,
    .toggle {{
      color: var(--muted);
    }}
    textarea,
    #response {{
      border-color: var(--border);
      background: var(--input);
      color: var(--text);
    }}
    textarea:focus {{ border-color: var(--accent); }}
    button {{
      border-color: var(--border);
      background: var(--surface-strong);
      color: var(--text);
    }}
    button.primary {{
      background: var(--success);
      border-color: var(--success);
      color: #FFFFFF;
    }}
    button.voice,
    .voice-primary {{
      background: var(--accent);
      border-color: var(--accent);
      color: #FFFFFF;
    }}
    button.subtle,
    .theme-toggle {{
      background: var(--surface);
      color: var(--muted);
      border-color: var(--border);
    }}
    .composer-panel {{
      padding: 0;
      overflow: hidden;
    }}
    .composer-toggle {{
      width: 100%;
      min-height: 58px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      border: 0;
      border-radius: 0;
      background: var(--surface);
      color: var(--text);
      padding: 16px;
      text-align: left;
    }}
    .composer-toggle span {{
      font-weight: 800;
      font-size: 15px;
    }}
    .composer-toggle small {{
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }}
    .composer-toggle::after {{
      content: "+";
      width: 28px;
      height: 28px;
      border: 1px solid var(--border);
      border-radius: 999px;
      display: grid;
      place-items: center;
      color: var(--accent);
      font-size: 20px;
      line-height: 1;
      flex: 0 0 auto;
    }}
    .composer-toggle[aria-expanded="true"]::after {{
      content: "-";
    }}
    .composer-body {{
      border-top: 1px solid var(--border);
      padding: 16px;
    }}
    .composer-body[hidden] {{
      display: none;
    }}
    .voice-primary.active {{
      background: var(--danger);
      border-color: var(--danger);
    }}
    .voice-orb {{
      position: relative;
      overflow: hidden;
      width: 172px;
      background:
        radial-gradient(circle at center, var(--input) 0 34%, transparent 35%),
        conic-gradient(from 180deg, var(--accent), var(--success), var(--accent));
      border: 1px solid var(--border-strong);
      box-shadow:
        0 0 calc(10px + var(--level) * 36px) rgba(37, 99, 235, 0.22),
        inset 0 0 0 14px color-mix(in srgb, var(--surface) 72%, transparent);
      transform: scale(calc(1 + var(--level) * 0.08));
    }}
    .voice-orb::before,
    .voice-orb::after {{
      content: "";
      position: absolute;
      inset: 20%;
      border: 1px solid color-mix(in srgb, var(--accent) 42%, transparent);
      border-radius: 50%;
      transform: scale(calc(1 + var(--level) * 0.55));
      opacity: calc(0.25 + var(--level) * 0.55);
      transition: transform 90ms linear, opacity 90ms linear;
    }}
    .voice-orb::after {{
      inset: 34%;
      background: var(--accent);
      border: 0;
      box-shadow: 0 0 calc(12px + var(--level) * 28px) rgba(37, 99, 235, 0.38);
      opacity: calc(0.78 + var(--level) * 0.2);
    }}
    .voice-orb.listening {{
      animation: voiceRing 2.1s ease-in-out infinite;
      filter: none;
    }}
    .voice-orb.speaking {{
      border-color: color-mix(in srgb, var(--success) 65%, var(--border));
      filter: none;
    }}
    @keyframes voiceRing {{
      0%, 100% {{ box-shadow: 0 0 18px rgba(37, 99, 235, 0.16), inset 0 0 0 14px color-mix(in srgb, var(--surface) 72%, transparent); }}
      50% {{ box-shadow: 0 0 42px rgba(37, 99, 235, 0.34), inset 0 0 0 10px color-mix(in srgb, var(--surface) 64%, transparent); }}
    }}
    @supports not (color: color-mix(in srgb, white, black)) {{
      .voice-orb {{ box-shadow: 0 0 24px rgba(37, 99, 235, 0.22); }}
      .voice-orb::before {{ border-color: rgba(37, 99, 235, 0.28); }}
    }}
    @media (max-width: 420px) {{
      .app-shell {{ padding: 12px; gap: 12px; }}
      .brand strong {{ font-size: 23px; }}
      .brand span, .brand b {{ font-size: 15px; }}
      .topbar {{ align-items: flex-start; }}
      .top-actions {{ flex-direction: column; align-items: flex-end; }}
      .actions, .secondary-actions {{ grid-template-columns: 1fr; }}
      button {{ width: 100%; }}
      .theme-toggle {{ width: auto; }}
    }}

    /* Celsius mobile - identidade visual compartilhada com o site */
    :root {{
      color-scheme: light;
      --page: #F4F7F6;
      --surface: #FFFFFF;
      --surface-soft: #EAF1EF;
      --ink: #14211F;
      --muted: #52615E;
      --faint: #7C8A86;
      --line: #CFDBD7;
      --line-strong: #A9BBB5;
      --primary: #087E72;
      --primary-strong: #05645B;
      --primary-soft: #DFF1ED;
      --green: #237B4B;
      --green-soft: #E2F1E8;
      --coral: #C9463C;
      --focus: #E59B2D;
      --shadow-soft: 0 8px 24px rgba(20, 33, 31, 0.08);
      font-family: "Segoe UI", Arial, sans-serif;
      background: var(--page);
      color: var(--ink);
    }}
    body.dark {{
      color-scheme: dark;
      --page: #101715;
      --surface: #18211F;
      --surface-soft: #202D2A;
      --ink: #EDF5F2;
      --muted: #AABBB5;
      --faint: #728780;
      --line: #344440;
      --line-strong: #52655F;
      --primary: #42C6B7;
      --primary-strong: #7ED8CE;
      --primary-soft: #1D403B;
      --green: #69C58D;
      --green-soft: #1D3D2A;
      --coral: #FF8178;
      --focus: #FFC267;
      --shadow-soft: 0 8px 24px rgba(0, 0, 0, 0.22);
    }}
    html {{
      min-height: 100%;
      background: var(--page);
    }}
    body {{
      min-width: 320px;
      min-height: 100svh;
      background: var(--page);
      color: var(--ink);
      font-size: 15px;
      line-height: 1.5;
      letter-spacing: 0;
    }}
    button,
    textarea,
    input {{
      font: inherit;
      letter-spacing: 0;
    }}
    button:focus-visible,
    textarea:focus-visible,
    input:focus-visible {{
      outline: 3px solid var(--focus);
      outline-offset: 2px;
    }}
    .app-shell {{
      width: min(100%, 600px);
      min-height: 100svh;
      grid-template-rows: auto auto auto auto;
      align-content: start;
      gap: 14px;
      padding: 0 18px 24px;
    }}
    .topbar {{
      position: sticky;
      top: 0;
      z-index: 20;
      min-height: 72px;
      margin: 0 -18px;
      padding: 0 18px;
      border-bottom: 1px solid var(--line);
      background: color-mix(in srgb, var(--surface) 94%, transparent);
      backdrop-filter: blur(14px);
    }}
    .brand {{
      align-items: center;
      gap: 5px;
      color: var(--ink);
    }}
    .brand strong,
    .brand span,
    .brand b {{
      font-size: 17px;
      line-height: 1;
    }}
    .brand strong {{ color: var(--ink); font-weight: 780; }}
    .brand span {{ color: var(--muted); font-weight: 650; }}
    .brand b {{ color: var(--primary); font-weight: 800; }}
    .top-actions {{
      flex-direction: row;
      align-items: center;
      gap: 8px;
    }}
    .connection-chip {{
      min-height: 32px;
      display: inline-flex;
      align-items: center;
      gap: 7px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--surface);
      color: var(--muted);
      box-shadow: none;
      padding: 6px 9px;
      font-size: 11px;
      font-weight: 700;
    }}
    .connection-chip::before {{
      content: "";
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: var(--green);
      box-shadow: 0 0 0 3px var(--green-soft);
    }}
    .theme-toggle {{
      width: 68px;
      min-height: 36px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--surface);
      color: var(--ink);
      padding: 7px 9px;
      font-size: 11px;
      font-weight: 700;
    }}
    .theme-toggle:hover {{
      border-color: var(--primary);
      color: var(--primary);
    }}
    .panel {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--surface);
      box-shadow: var(--shadow-soft);
      padding: 18px;
    }}
    .voice-panel {{
      margin-top: 4px;
      overflow: hidden;
    }}
    .panel-heading {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 16px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--line);
    }}
    .eyebrow {{
      display: block;
      margin-bottom: 4px;
      color: var(--primary);
      font-size: 11px;
      font-weight: 800;
      text-transform: uppercase;
    }}
    .panel-heading h1 {{
      margin: 0;
      color: var(--ink);
      font-size: 21px;
      line-height: 1.2;
      font-weight: 760;
    }}
    .privacy-chip {{
      flex: 0 0 auto;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--surface-soft);
      color: var(--muted);
      padding: 6px 8px;
      font-size: 10px;
      font-weight: 700;
    }}
    .voice-stage {{
      gap: 12px;
      padding: 26px 8px 4px;
    }}
    .voice-orb {{
      --level: 0;
      position: relative;
      width: 156px;
      aspect-ratio: 1;
      overflow: visible;
      border: 1px solid var(--line-strong);
      border-radius: 50%;
      background: var(--surface-soft);
      box-shadow:
        0 0 0 calc(10px + var(--level) * 12px) color-mix(in srgb, var(--primary) 10%, transparent),
        0 0 calc(18px + var(--level) * 34px) color-mix(in srgb, var(--primary) 30%, transparent);
      transform: scale(calc(1 + var(--level) * 0.06));
      transition: transform 90ms linear, box-shadow 90ms linear;
    }}
    .voice-orb::before {{
      content: "";
      position: absolute;
      inset: 22px;
      border: 1px solid color-mix(in srgb, var(--primary) 46%, var(--line));
      border-radius: 50%;
      background: var(--surface);
      transform: scale(calc(1 + var(--level) * 0.18));
      transition: transform 90ms linear;
    }}
    .voice-orb::after {{
      content: "C";
      position: absolute;
      inset: 48px;
      display: grid;
      place-items: center;
      border: 0;
      border-radius: 50%;
      background: var(--primary);
      color: #FFFFFF;
      box-shadow: 0 8px 24px color-mix(in srgb, var(--primary) 32%, transparent);
      font-size: 28px;
      font-weight: 800;
      opacity: 1;
      transform: scale(calc(1 + var(--level) * 0.2));
      transition: transform 90ms linear, background 160ms ease;
    }}
    .voice-orb.listening {{
      animation: celsiusVoiceRing 1.8s ease-in-out infinite;
      filter: none;
    }}
    .voice-orb.listening::after {{ background: #286FA1; }}
    .voice-orb.speaking {{ border-color: var(--green); filter: none; }}
    .voice-orb.speaking::after {{ background: var(--green); }}
    @keyframes celsiusVoiceRing {{
      0%, 100% {{
        box-shadow:
          0 0 0 10px color-mix(in srgb, var(--primary) 8%, transparent),
          0 0 18px color-mix(in srgb, var(--primary) 22%, transparent);
      }}
      50% {{
        box-shadow:
          0 0 0 17px color-mix(in srgb, var(--primary) 13%, transparent),
          0 0 38px color-mix(in srgb, var(--primary) 34%, transparent);
      }}
    }}
    .voice-state {{
      min-height: 22px;
      color: var(--ink);
      font-size: 16px;
      font-weight: 760;
    }}
    .voice-substate {{
      max-width: 360px;
      min-height: 36px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.5;
    }}
    button {{
      min-height: 44px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--surface);
      color: var(--ink);
      padding: 10px 14px;
      font-size: 14px;
      font-weight: 720;
      transition: background 150ms ease, border-color 150ms ease, color 150ms ease;
    }}
    button:hover {{ border-color: var(--primary); }}
    button:active {{ transform: translateY(1px); }}
    button:disabled {{ opacity: 0.48; }}
    .voice-primary,
    button.primary,
    button.voice {{
      border-color: var(--primary);
      background: var(--primary);
      color: #FFFFFF;
    }}
    .voice-primary:hover,
    button.primary:hover,
    button.voice:hover {{
      border-color: var(--primary-strong);
      background: var(--primary-strong);
    }}
    .voice-primary {{ width: min(100%, 300px); min-height: 48px; }}
    .voice-primary.active {{
      border-color: var(--coral);
      background: var(--coral);
    }}
    button.subtle {{
      border-color: var(--line);
      background: var(--surface);
      color: var(--muted);
    }}
    button.subtle:hover {{
      border-color: var(--primary);
      background: var(--primary-soft);
      color: var(--primary);
    }}
    .composer-panel {{ padding: 0; overflow: hidden; }}
    .composer-toggle {{
      width: 100%;
      min-height: 60px;
      border: 0;
      border-radius: 0;
      background: var(--surface);
      color: var(--ink);
      padding: 16px 18px;
    }}
    .composer-toggle:hover {{
      border-color: transparent;
      background: var(--surface-soft);
    }}
    .composer-toggle span {{ font-size: 14px; font-weight: 760; }}
    .composer-toggle small {{
      margin-left: auto;
      color: var(--muted);
      font-size: 11px;
      font-weight: 650;
    }}
    .composer-toggle::after {{
      width: 30px;
      height: 30px;
      border: 1px solid var(--line);
      border-radius: 6px;
      color: var(--primary);
    }}
    .composer-body {{ border-color: var(--line); padding: 18px; }}
    .hint {{ color: var(--muted); font-size: 12px; }}
    textarea {{
      min-height: 120px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--page);
      color: var(--ink);
      padding: 13px 14px;
      font-size: 16px;
      line-height: 1.5;
    }}
    textarea::placeholder {{ color: var(--faint); }}
    textarea:focus {{ border-color: var(--primary); }}
    .actions {{ gap: 10px; margin-top: 12px; }}
    .secondary-actions {{ margin-top: 10px; }}
    .section-row {{
      margin-bottom: 12px;
      padding-bottom: 12px;
      border-bottom: 1px solid var(--line);
    }}
    .section-title {{
      color: var(--ink);
      font-size: 12px;
      font-weight: 800;
    }}
    .toggle {{ color: var(--muted); font-size: 12px; }}
    .toggle input {{
      width: 34px;
      height: 18px;
      accent-color: var(--primary);
    }}
    #response {{
      min-height: 132px;
      overflow-wrap: anywhere;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--page);
      color: var(--ink);
      padding: 15px;
      font-size: 14px;
      line-height: 1.6;
    }}
    #status {{
      position: sticky;
      bottom: 12px;
      z-index: 15;
      min-height: 46px;
      margin: 0;
      border: 1px solid var(--line);
      border-left: 4px solid var(--primary);
      border-radius: 6px;
      background: var(--surface);
      color: var(--muted);
      box-shadow: var(--shadow-soft);
      padding: 12px 14px;
      font-size: 12px;
    }}
    @media (max-width: 460px) {{
      .app-shell {{ gap: 12px; padding: 0 12px 20px; }}
      .topbar {{
        min-height: 64px;
        margin: 0 -12px;
        padding: 0 12px;
        align-items: center;
      }}
      .brand strong, .brand span, .brand b {{ font-size: 15px; }}
      .top-actions {{ flex-direction: row; }}
      .connection-chip {{ min-height: 30px; padding: 5px 8px; }}
      .theme-toggle {{ width: 58px; min-height: 34px; padding: 6px; }}
      .panel {{ padding: 15px; }}
      .panel-heading h1 {{ font-size: 19px; }}
      .privacy-chip {{
        max-width: 110px;
        white-space: normal;
        text-align: right;
      }}
      .voice-orb {{ width: 142px; }}
      .voice-orb::after {{ inset: 43px; }}
      .actions, .secondary-actions {{ grid-template-columns: 1fr 1fr; }}
      button {{ width: auto; }}
    }}
    @media (max-width: 350px) {{
      .brand span {{ display: none; }}
      .actions, .secondary-actions {{ grid-template-columns: 1fr; }}
      button {{ width: 100%; }}
    }}
  </style>
</head>
<body>
  <main class="app-shell">
    <header class="topbar">
      <div class="brand" aria-label="Celsius Project AI">
        <strong>Celsius</strong><span>Project</span><b>AI</b>
      </div>
      <div class="top-actions">
        <button id="themeToggle" class="theme-toggle" type="button" aria-label="Alternar tema">Escuro</button>
        <div id="connectionChip" class="connection-chip">Local</div>
      </div>
    </header>

    <section class="panel voice-panel">
      <div class="panel-heading">
        <div>
          <span class="eyebrow">Assistente local</span>
          <h1>Fale com o Celsius</h1>
        </div>
        <span class="privacy-chip">Processado no seu PC</span>
      </div>
      <div class="voice-stage">
        <div id="voiceOrb" class="voice-orb" aria-hidden="true"></div>
        <div id="voiceState" class="voice-state">Aguardando "Celsius"</div>
        <div id="voiceSubstate" class="voice-substate">Diga Celsius para ativar o assistente.</div>
        <button id="voiceSession" class="voice-primary" type="button">Ativar escuta</button>
      </div>
    </section>

    <section id="textComposerPanel" class="panel composer-panel collapsed">
      <button id="toggleComposer" class="composer-toggle" type="button" aria-expanded="false" aria-controls="composerBody">
        <span>Digitar mensagem</span>
        <small>Opcional</small>
      </button>
      <div id="composerBody" class="composer-body" hidden>
        <p class="hint">Use quando preferir escrever ou revisar a pergunta antes de enviar.</p>
        <textarea id="message" placeholder="Digite sua mensagem para o Celsius..."></textarea>
        <div class="actions">
          <button id="record" class="voice" type="button">Gravar voz</button>
          <button id="send" class="primary" type="button">Enviar</button>
        </div>
        <div class="actions secondary-actions">
          <button id="test" class="subtle" type="button">Testar conexao</button>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="section-row">
        <div class="section-title">Resposta</div>
        <label class="toggle"><input id="autoSpeak" type="checkbox" checked> Audio</label>
      </div>
      <div id="response">A resposta do Celsius aparecera aqui.</div>
      <div class="actions secondary-actions">
        <button id="speak" class="subtle" type="button">Ouvir</button>
        <button id="stopSpeak" class="subtle" type="button">Parar audio</button>
      </div>
    </section>

    <p id="status">Pronto para conectar ao Celsius.</p>
  </main>
  <script>
    const token = new URLSearchParams(location.search).get("token") || "{token}";
    const voiceEnabled = {voice_flag};
    const message = document.querySelector("#message");
    const statusEl = document.querySelector("#status");
    const responseEl = document.querySelector("#response");
    const connectionChip = document.querySelector("#connectionChip");
    const themeToggle = document.querySelector("#themeToggle");
    const toggleComposerBtn = document.querySelector("#toggleComposer");
    const composerBody = document.querySelector("#composerBody");
    const recordBtn = document.querySelector("#record");
    const voiceSessionBtn = document.querySelector("#voiceSession");
    const voiceOrb = document.querySelector("#voiceOrb");
    const voiceState = document.querySelector("#voiceState");
    const voiceSubstate = document.querySelector("#voiceSubstate");
    const autoSpeak = document.querySelector("#autoSpeak");
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    const TARGET_SAMPLE_RATE = 16000;
    let lastResponseVersion = 0;
    let lastResponseText = "";
    let lastResponseAudioVersion = 0;
    let responsePollTimer = null;
    const responseAudio = new Audio();
    let responseAudioUrl = "";
    let mobileAudioPlaying = false;
    let mobileAudioStopRequested = false;
    let audioContext = null;
    let audioStream = null;
    let audioSource = null;
    let audioProcessor = null;
    let audioChunks = [];
    let recording = false;
    let recordingTimer = null;
    let voiceConversationActive = false;
    let autoListening = false;
    let speechDetected = false;
    let speechStartedAt = 0;
    let silenceStartedAt = 0;
    let autoStopping = false;
    let voiceActivationInProgress = false;
    let noiseFloor = 0.006;
    const MIN_VOICE_THRESHOLD = 0.012;
    const SILENCE_TO_SEND_MS = 500;
    const MIN_SPEECH_MS = 220;
    const AUTO_MAX_RECORDING_MS = 10000;

    function applyMobileTheme(theme) {{
      const dark = theme === "dark";
      document.body.classList.toggle("dark", dark);
      themeToggle.textContent = dark ? "Claro" : "Escuro";
      localStorage.setItem("celsiusMobileTheme", dark ? "dark" : "light");
    }}

    themeToggle.addEventListener("click", () => {{
      applyMobileTheme(document.body.classList.contains("dark") ? "light" : "dark");
    }});
    applyMobileTheme(localStorage.getItem("celsiusMobileTheme") || "light");

    function setComposerExpanded(expanded, focusInput = false) {{
      toggleComposerBtn.setAttribute("aria-expanded", expanded ? "true" : "false");
      toggleComposerBtn.querySelector("span").textContent = expanded ? "Ocultar campo" : "Digitar mensagem";
      composerBody.hidden = !expanded;
      if (expanded && focusInput) {{
        setTimeout(() => message.focus(), 80);
      }}
    }}

    toggleComposerBtn.addEventListener("click", () => {{
      const expanded = toggleComposerBtn.getAttribute("aria-expanded") === "true";
      setComposerExpanded(!expanded, !expanded);
    }});

    async function fetchJson(path, options = {{}}, timeoutMs = 12000) {{
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), timeoutMs);
      try {{
        const separator = path.includes("?") ? "&" : "?";
        const response = await fetch(`${{path}}${{separator}}token=${{encodeURIComponent(token)}}`, {{
          ...options,
          signal: controller.signal
        }});
        let data = {{}};
        try {{
          data = await response.json();
        }} catch (error) {{
          data = {{}};
        }}
        if (!response.ok && !data.message) {{
          data.message = `Erro HTTP ${{response.status}} ao falar com o Celsius.`;
        }}
        return data;
      }} catch (error) {{
        if (error.name === "AbortError") {{
          return {{
            ok: false,
            message: "Tempo esgotado. Verifique se o Celsius esta aberto, se o celular esta na mesma rede e se o firewall permitiu a porta."
          }};
        }}
        return {{
          ok: false,
          message: "Falha de conexao com o Celsius. Confirme o aviso do certificado, a rede Wi-Fi e o firewall do Windows."
        }};
      }} finally {{
        clearTimeout(timer);
      }}
    }}

    async function sendCommand(source = "phone") {{
      const text = message.value.trim();
      if (!text) {{
        setComposerExpanded(true, true);
        statusEl.textContent = "Digite uma mensagem ou inicie a conversa por voz.";
        return;
      }}
      statusEl.textContent = "Enviando...";
      document.querySelector("#send").disabled = true;
      const data = await fetchJson("/api/command", {{
        method: "POST",
        headers: {{
          "Content-Type": "application/json",
          "Authorization": `Bearer ${{token}}`
        }},
        body: JSON.stringify({{ message: text, source }})
      }});
      statusEl.textContent = data.message || (data.ok ? "Enviado." : "Erro ao enviar.");
      if (data.ok) {{
        lastResponseVersion = Number(data.response_version || lastResponseVersion);
        message.value = "";
        setComposerExpanded(false);
        waitForResponse();
      }}
      document.querySelector("#send").disabled = false;
    }}

    document.querySelector("#send").addEventListener("click", () => sendCommand("phone_text"));
    document.querySelector("#test").addEventListener("click", async () => {{
      statusEl.textContent = "Testando conexao...";
      const data = await fetchJson("/api/status", {{
        headers: {{
          "Authorization": `Bearer ${{token}}`
        }}
      }});
      statusEl.textContent = data.ok
        ? `Conexao ok com ${{data.name}}. HTTPS: ${{data.https ? "sim" : "nao"}}.`
        : (data.message || "Nao consegui confirmar a conexao.");
      connectionChip.textContent = data.ok ? "Conectado" : "Offline";
    }});
    document.querySelector("#speak").addEventListener("click", () => playPcAudio(lastResponseVersion));
    document.querySelector("#stopSpeak").addEventListener("click", stopPcAudio);

    function sleep(ms) {{
      return new Promise(resolve => setTimeout(resolve, ms));
    }}

    function clearResponseAudio() {{
      responseAudio.pause();
      responseAudio.removeAttribute("src");
      responseAudio.load();
      if (responseAudioUrl) URL.revokeObjectURL(responseAudioUrl);
      responseAudioUrl = "";
    }}

    function stopPcAudio() {{
      mobileAudioStopRequested = true;
      responseAudio.pause();
      responseAudio.currentTime = 0;
      statusEl.textContent = "Audio pausado no celular.";
    }}

    async function loadPcAudio(responseVersion, retries = 12) {{
      if (!responseVersion) return false;
      for (let attempt = 0; attempt < retries; attempt++) {{
        const separator = "/api/last-audio".includes("?") ? "&" : "?";
        const url = `/api/last-audio${{separator}}token=${{encodeURIComponent(token)}}&response_version=${{responseVersion}}&after_audio_version=${{lastResponseAudioVersion}}&t=${{Date.now()}}`;
        const response = await fetch(url, {{
          headers: {{ "Authorization": `Bearer ${{token}}` }}
        }});
        if (response.status === 200) {{
          const blob = await response.blob();
          clearResponseAudio();
          responseAudioUrl = URL.createObjectURL(blob);
          responseAudio.src = responseAudioUrl;
          lastResponseAudioVersion = Number(
            response.headers.get("X-Celsius-Audio-Version") || lastResponseAudioVersion
          );
          return true;
        }}
        if (response.status !== 204) return false;
        await sleep(500);
      }}
      return false;
    }}

    async function playPcAudio(responseVersion) {{
      if (mobileAudioPlaying) return;
      if (!responseVersion) {{
        statusEl.textContent = "Ainda nao ha resposta com audio para tocar.";
        return;
      }}
      mobileAudioPlaying = true;
      mobileAudioStopRequested = false;
      try {{
        while (!mobileAudioStopRequested) {{
          statusEl.textContent = "Aguardando audio gerado no PC...";
          const loaded = await loadPcAudio(responseVersion);
          if (!loaded || mobileAudioStopRequested) break;
          statusEl.textContent = "Reproduzindo audio gerado no PC.";
          await new Promise(resolve => {{
            responseAudio.onended = resolve;
            responseAudio.onerror = resolve;
            responseAudio.play().catch(() => {{
              statusEl.textContent = "Toque em Ouvir para liberar o audio no celular.";
              resolve();
            }});
          }});
        }}
        if (!mobileAudioStopRequested) {{
          statusEl.textContent = "Audio concluido.";
        }}
      }} finally {{
        mobileAudioPlaying = false;
      }}
    }}

    async function waitForResponse() {{
      clearInterval(responsePollTimer);
      statusEl.textContent = "Aguardando resposta do Celsius...";
      const started = Date.now();
      responsePollTimer = setInterval(async () => {{
        const data = await fetchJson(`/api/last-response?after=${{lastResponseVersion}}`, {{}}, 12000);
        if (data.ok && data.has_new && data.text) {{
          clearInterval(responsePollTimer);
          lastResponseVersion = Number(data.version || lastResponseVersion);
          lastResponseText = data.text;
          mobileAudioStopRequested = true;
          lastResponseAudioVersion = 0;
          clearResponseAudio();
          responseEl.textContent = data.text;
          statusEl.textContent = data.kind === "error" ? "O Celsius retornou um erro." : "Resposta recebida.";
          setVoiceVisualState(data.kind === "error" ? "idle" : "speaking");
          if (autoSpeak.checked && data.kind !== "error") {{
            playPcAudio(lastResponseVersion).finally(() => resumeVoiceConversation());
          }} else {{
            resumeVoiceConversation();
          }}
          return;
        }}
        if (Date.now() - started > 120000) {{
          clearInterval(responsePollTimer);
          statusEl.textContent = "Ainda sem resposta nova. Veja se o Celsius terminou de responder no PC.";
        }}
      }}, 1500);
    }}

    async function blobToBase64(blob) {{
      const buffer = await blob.arrayBuffer();
      let binary = "";
      const bytes = new Uint8Array(buffer);
      for (let i = 0; i < bytes.byteLength; i++) {{
        binary += String.fromCharCode(bytes[i]);
      }}
      return btoa(binary);
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
      for (let i = 0; i < text.length; i++) {{
        view.setUint8(offset + i, text.charCodeAt(i));
      }}
    }}

    async function sendVoiceBlob(blob, autoMode = false) {{
      statusEl.textContent = autoMode ? "Enviando sua fala para o Celsius..." : "Enviando voz otimizada para o PC...";
      if (!autoMode) recordBtn.disabled = true;
      const data = await fetchJson("/api/voice-command", {{
        method: "POST",
        headers: {{
          "Content-Type": "application/json",
          "Authorization": `Bearer ${{token}}`
        }},
        body: JSON.stringify({{
          audio_base64: await blobToBase64(blob),
          mime_type: blob.type || "audio/wav"
        }})
      }}, 45000);
      recordBtn.disabled = voiceConversationActive;
      if (data.transcript) message.value = data.transcript;
      statusEl.textContent = data.message || (data.ok ? "Voz enviada." : "Erro ao enviar voz.");
      if (data.ok && data.command_submitted === false) {{
        if (data.wake_detected && data.acknowledgement) {{
          setVoiceVisualState("armed");
          await speakWakeAcknowledgement(data.acknowledgement);
        }} else {{
          setVoiceVisualState("listening");
        }}
        resumeVoiceConversation(120);
      }} else if (data.ok) {{
        lastResponseVersion = Number(data.response_version || lastResponseVersion);
        setVoiceVisualState("thinking");
        waitForResponse();
      }} else {{
        resumeVoiceConversation();
      }}
    }}

    function speakWakeAcknowledgement(text) {{
      if (!("speechSynthesis" in window) || !text) return Promise.resolve();
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = "pt-BR";
      utterance.rate = 1.12;
      utterance.pitch = 0.92;
      return new Promise(resolve => {{
        utterance.onend = resolve;
        utterance.onerror = resolve;
        window.speechSynthesis.speak(utterance);
      }});
    }}

    function calculateRms(samples) {{
      let sum = 0;
      for (let i = 0; i < samples.length; i++) {{
        sum += samples[i] * samples[i];
      }}
      return Math.sqrt(sum / Math.max(1, samples.length));
    }}

    function setVoiceVisualState(state) {{
      voiceOrb.classList.toggle("listening", state === "listening");
      voiceOrb.classList.toggle("speaking", state === "speaking");
      if (state === "listening") {{
        voiceState.textContent = "Aguardando \"Celsius\"";
        voiceSubstate.textContent = "Diga Celsius para ativar o assistente.";
      }} else if (state === "armed") {{
        voiceState.textContent = "Estou ouvindo";
        voiceSubstate.textContent = "Pode falar seu pedido agora.";
      }} else if (state === "speaking") {{
        voiceState.textContent = "Celsius respondendo";
        voiceSubstate.textContent = "O audio gerado no PC sera reproduzido aqui.";
      }} else if (state === "thinking") {{
        voiceState.textContent = "Pensando";
        voiceSubstate.textContent = "Sua fala foi enviada para o Celsius.";
      }} else if (state === "needs-gesture") {{
        voiceState.textContent = "Ative o microfone";
        voiceSubstate.textContent = "Toque em Ativar escuta e permita o uso do microfone.";
      }} else {{
        voiceState.textContent = "Aguardando \"Celsius\"";
        voiceSubstate.textContent = "Diga Celsius para ativar o assistente.";
        voiceOrb.style.setProperty("--level", 0);
      }}
    }}

    function updateVoiceOrb(level) {{
      const scaled = Math.min(1, Math.max(0, level * 12));
      voiceOrb.style.setProperty("--level", scaled.toFixed(3));
    }}

    function handleAutoVoiceLevel(level) {{
      const now = Date.now();
      const threshold = Math.max(MIN_VOICE_THRESHOLD, Math.min(0.034, noiseFloor * 2.8));
      if (!speechDetected && level <= threshold) {{
        noiseFloor = Math.min(0.012, noiseFloor * 0.96 + level * 0.04);
        return;
      }}
      if (level > threshold) {{
        if (mobileAudioPlaying) stopPcAudio();
        if (!speechDetected) {{
          speechDetected = true;
          speechStartedAt = now;
          voiceState.textContent = "Ouvindo voce";
        }}
        silenceStartedAt = 0;
        return;
      }}
      if (!speechDetected) return;
      if (!silenceStartedAt) silenceStartedAt = now;
      const speechMs = now - speechStartedAt;
      const silenceMs = now - silenceStartedAt;
      if (!autoStopping && speechMs >= MIN_SPEECH_MS && silenceMs >= SILENCE_TO_SEND_MS) {{
        autoStopping = true;
        stopLocalRecording(true);
      }}
    }}

    async function startLocalRecording(autoMode = false) {{
      audioStream = await navigator.mediaDevices.getUserMedia({{
        audio: {{
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          channelCount: 1
        }}
      }});
      audioContext = new AudioContextClass();
      if (audioContext.state === "suspended") await audioContext.resume();
      if (audioContext.state !== "running") {{
        audioStream.getTracks().forEach(track => track.stop());
        await audioContext.close();
        audioStream = null;
        audioContext = null;
        throw new Error("O navegador exige um toque para iniciar o audio.");
      }}
      audioSource = audioContext.createMediaStreamSource(audioStream);
      audioProcessor = audioContext.createScriptProcessor(4096, 1, 1);
      audioChunks = [];
      speechDetected = false;
      speechStartedAt = 0;
      silenceStartedAt = 0;
      autoStopping = false;
      noiseFloor = 0.006;
      autoListening = autoMode;
      audioProcessor.onaudioprocess = event => {{
        const samples = new Float32Array(event.inputBuffer.getChannelData(0));
        const level = calculateRms(samples);
        updateVoiceOrb(level);
        if (!recording) return;
        audioChunks.push(samples);
        if (autoListening) handleAutoVoiceLevel(level);
      }};
      audioSource.connect(audioProcessor);
      audioProcessor.connect(audioContext.destination);
      recording = true;
      if (autoMode) {{
        setVoiceVisualState("listening");
        statusEl.textContent = "Escuta ativa. Diga Celsius para comecar.";
        recordingTimer = setTimeout(() => stopLocalRecording(true), AUTO_MAX_RECORDING_MS);
      }} else {{
        recordBtn.textContent = "Parar e enviar";
        statusEl.textContent = "Gravando no celular...";
        recordingTimer = setTimeout(() => stopLocalRecording(false), 15000);
      }}
    }}

    async function stopLocalRecording(autoMode = false) {{
      if (!recording) return;
      recording = false;
      clearTimeout(recordingTimer);
      if (!autoMode) {{
        recordBtn.textContent = "Preparando envio...";
        recordBtn.disabled = true;
      }} else {{
        setVoiceVisualState("thinking");
      }}

      if (audioProcessor) audioProcessor.disconnect();
      if (audioSource) audioSource.disconnect();
      if (audioStream) audioStream.getTracks().forEach(track => track.stop());
      const sampleRate = audioContext ? audioContext.sampleRate : 44100;
      if (audioContext) await audioContext.close();
      audioContext = null;
      audioStream = null;
      audioSource = null;
      audioProcessor = null;

      if (!audioChunks.length || (autoMode && !speechDetected)) {{
        statusEl.textContent = autoMode ? "Nenhuma fala detectada." : "Nenhum audio capturado.";
        recordBtn.textContent = "Gravar voz";
        recordBtn.disabled = voiceConversationActive;
        resumeVoiceConversation();
        return;
      }}
      await sendVoiceBlob(encodeWav(audioChunks, sampleRate), autoMode);
      recordBtn.textContent = "Gravar voz";
      recordBtn.disabled = voiceConversationActive;
    }}

    function stopAudioCaptureOnly() {{
      recording = false;
      autoListening = false;
      clearTimeout(recordingTimer);
      if (audioProcessor) audioProcessor.disconnect();
      if (audioSource) audioSource.disconnect();
      if (audioStream) audioStream.getTracks().forEach(track => track.stop());
      if (audioContext) audioContext.close();
      audioContext = null;
      audioStream = null;
      audioSource = null;
      audioProcessor = null;
      audioChunks = [];
      updateVoiceOrb(0);
    }}

    async function startVoiceConversation() {{
      if (voiceActivationInProgress) return;
      if (voiceConversationActive) {{
        voiceConversationActive = false;
        voiceSessionBtn.classList.remove("active");
        voiceSessionBtn.textContent = "Ativar escuta";
        recordBtn.disabled = false;
        stopAudioCaptureOnly();
        stopPcAudio();
        setVoiceVisualState("idle");
        statusEl.textContent = "Conversa por voz encerrada.";
        return;
      }}
      voiceActivationInProgress = true;
      voiceConversationActive = true;
      voiceSessionBtn.classList.add("active");
      voiceSessionBtn.textContent = "Pausar escuta";
      recordBtn.disabled = true;
      try {{
        await startLocalRecording(true);
      }} catch (error) {{
        stopAudioCaptureOnly();
        voiceConversationActive = false;
        voiceSessionBtn.classList.remove("active");
        voiceSessionBtn.textContent = "Ativar escuta";
        recordBtn.disabled = false;
        setVoiceVisualState("needs-gesture");
        statusEl.textContent = "Toque em Ativar escuta e autorize o microfone deste site HTTPS.";
      }} finally {{
        voiceActivationInProgress = false;
      }}
    }}

    function resumeVoiceConversation(delayMs = 300) {{
      if (!voiceConversationActive || recording) return;
      setTimeout(() => {{
        if (!voiceConversationActive || recording) return;
        startLocalRecording(true).catch(() => {{
          voiceConversationActive = false;
          voiceSessionBtn.classList.remove("active");
          voiceSessionBtn.textContent = "Ativar escuta";
          recordBtn.disabled = false;
          setVoiceVisualState("idle");
        }});
      }}, delayMs);
    }}

    function scheduleAutomaticWakeListening() {{
      setTimeout(() => {{
        if (!voiceConversationActive) startVoiceConversation();
      }}, 250);
      document.addEventListener("pointerdown", () => {{
        if (!voiceConversationActive && !voiceActivationInProgress) {{
          startVoiceConversation();
        }}
      }}, {{ once: true, capture: true }});
    }}

    if (!voiceEnabled || !navigator.mediaDevices || !AudioContextClass) {{
      recordBtn.disabled = true;
      voiceSessionBtn.disabled = true;
      recordBtn.textContent = "Gravacao local indisponivel";
      voiceSessionBtn.textContent = "Voz indisponivel";
    }} else {{
      voiceSessionBtn.addEventListener("click", startVoiceConversation);
      recordBtn.addEventListener("click", async () => {{
        if (recording) {{
          await stopLocalRecording(false);
          return;
        }}
        try {{
          await startLocalRecording(false);
        }} catch (error) {{
          stopAudioCaptureOnly();
          statusEl.textContent = "Microfone bloqueado. Use o botao de voz do teclado ou habilite HTTPS.";
        }}
      }});
      scheduleAutomaticWakeListening();
    }}
  </script>
</body>
</html>"""
