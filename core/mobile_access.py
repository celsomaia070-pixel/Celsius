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

CommandCallback = Callable[[str, str], tuple[bool, str] | bool | None]
VoiceCommandCallback = Callable[[bytes, str], tuple[bool, str, str] | str]


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
    valid_days: int = 3650,
) -> tuple[Path, Path]:
    """Create or reuse a local self-signed certificate for mobile pairing."""

    cert_path = Path(cert_dir) / "celsius-mobile.crt"
    key_path = Path(cert_dir) / "celsius-mobile.key"
    if cert_path.exists() and key_path.exists():
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
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path


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
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
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
                if auth == f"Bearer {server_ref.token}":
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
    @media (max-width: 420px) {{
      .app-shell {{ padding: 12px; gap: 12px; }}
      .brand strong {{ font-size: 23px; }}
      .brand span, .brand b {{ font-size: 15px; }}
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
      <div id="connectionChip" class="connection-chip">Local</div>
    </header>

    <section class="panel">
      <div class="section-row">
        <div class="section-title">Comando</div>
      </div>
      <p class="hint">Grave sua voz no celular ou digite. O Celsius processa no PC e responde aqui.</p>
      <textarea id="message" placeholder="Diga ou digite um comando..."></textarea>
      <div class="actions">
        <button id="record" class="voice" type="button">Gravar voz</button>
        <button id="send" class="primary" type="button">Enviar</button>
      </div>
      <div class="actions secondary-actions">
        <button id="test" class="subtle" type="button">Testar conexao</button>
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
    const recordBtn = document.querySelector("#record");
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
        statusEl.textContent = "Digite ou fale um comando primeiro.";
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
          if (autoSpeak.checked && data.kind !== "error") playPcAudio(lastResponseVersion);
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

    async function sendVoiceBlob(blob) {{
      statusEl.textContent = "Enviando voz otimizada para o PC...";
      recordBtn.disabled = true;
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
      recordBtn.disabled = false;
      if (data.transcript) message.value = data.transcript;
      statusEl.textContent = data.message || (data.ok ? "Voz enviada." : "Erro ao enviar voz.");
      if (data.ok) {{
        lastResponseVersion = Number(data.response_version || lastResponseVersion);
        waitForResponse();
      }}
    }}

    async function startLocalRecording() {{
      audioStream = await navigator.mediaDevices.getUserMedia({{ audio: true }});
      audioContext = new AudioContextClass();
      audioSource = audioContext.createMediaStreamSource(audioStream);
      audioProcessor = audioContext.createScriptProcessor(4096, 1, 1);
      audioChunks = [];
      audioProcessor.onaudioprocess = event => {{
        if (!recording) return;
        audioChunks.push(new Float32Array(event.inputBuffer.getChannelData(0)));
      }};
      audioSource.connect(audioProcessor);
      audioProcessor.connect(audioContext.destination);
      recording = true;
      recordBtn.textContent = "Parar e enviar";
      statusEl.textContent = "Gravando no celular...";
      recordingTimer = setTimeout(() => stopLocalRecording(), 15000);
    }}

    async function stopLocalRecording() {{
      if (!recording) return;
      recording = false;
      clearTimeout(recordingTimer);
      recordBtn.textContent = "Preparando envio...";
      recordBtn.disabled = true;

      if (audioProcessor) audioProcessor.disconnect();
      if (audioSource) audioSource.disconnect();
      if (audioStream) audioStream.getTracks().forEach(track => track.stop());
      const sampleRate = audioContext ? audioContext.sampleRate : 44100;
      if (audioContext) await audioContext.close();
      audioContext = null;
      audioStream = null;
      audioSource = null;
      audioProcessor = null;

      if (!audioChunks.length) {{
        statusEl.textContent = "Nenhum audio capturado.";
        recordBtn.textContent = "Gravar voz";
        recordBtn.disabled = false;
        return;
      }}
      await sendVoiceBlob(encodeWav(audioChunks, sampleRate));
      recordBtn.textContent = "Gravar voz";
      recordBtn.disabled = false;
    }}

    if (!voiceEnabled || !navigator.mediaDevices || !AudioContextClass) {{
      recordBtn.disabled = true;
      recordBtn.textContent = "Gravacao local indisponivel";
    }} else {{
      recordBtn.addEventListener("click", async () => {{
        if (recording) {{
          await stopLocalRecording();
          return;
        }}
        try {{
          await startLocalRecording();
        }} catch (error) {{
          statusEl.textContent = "Microfone bloqueado. Use o botao de voz do teclado ou habilite HTTPS.";
        }}
      }});
    }}
  </script>
</body>
</html>"""
