"""Tests for local mobile access server."""

import base64
import json
import ssl
import urllib.error
import urllib.request

import pytest

from core.mobile_access import (
    MobileAccessServer,
    _create_server_ssl_context,
    _mobile_html,
    build_mobile_url,
    ensure_mobile_certificate,
    ensure_mobile_token,
)


def _request_json(
    url: str,
    token: str = "",
    payload: dict | None = None,
    *,
    context=None,
):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        url, data=data, headers=headers, method="POST" if data else "GET"
    )
    with urllib.request.urlopen(request, timeout=5, context=context) as response:
        return json.loads(response.read().decode("utf-8"))


def _request_bytes(url: str, token: str = "") -> tuple[bytes, str, int, int]:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=5) as response:
        return (
            response.read(),
            response.headers.get("Content-Type", ""),
            response.status,
            int(response.headers.get("X-Celsius-Audio-Version", "0")),
        )


class TestMobileAccess:
    def test_rejects_plain_http_outside_loopback(self):
        with pytest.raises(ValueError, match="exige HTTPS"):
            MobileAccessServer("0.0.0.0", 0, "secret", lambda *_args: True)

    def test_server_ssl_context_ignores_client_only_truststore_wrapper(self, monkeypatch):
        native_context = object()

        class TruststoreContext:
            __module__ = "pip._vendor.truststore._api"

            def __init__(self, _protocol):
                self._ctx = native_context

        monkeypatch.setattr(ssl, "SSLContext", TruststoreContext)

        assert _create_server_ssl_context() is native_context

    def test_mobile_page_uses_single_optimized_voice_button(self):
        html = _mobile_html("secret", True)

        assert "Falar comando" not in html
        assert "SpeechRecognition" not in html
        assert "speechSynthesis" in html
        assert "Gravar voz" in html
        assert "Parar e enviar" in html
        assert "Digitar mensagem" in html
        assert "composerBody" in html
        assert 'aria-expanded="false"' in html
        assert "Use quando preferir escrever" in html
        assert "voiceOrb" in html
        assert "Ativar escuta" in html
        assert 'Aguardando "Celsius"' in html
        assert "scheduleAutomaticWakeListening" in html
        assert "command_submitted" in html
        assert "themeToggle" in html
        assert "celsiusMobileTheme" in html
        assert "color-scheme: light" in html
        assert "voiceRing" in html
        assert "SILENCE_TO_SEND_MS" in html
        assert "MIN_VOICE_THRESHOLD" in html
        assert 'audioContext.state !== "running"' in html
        assert "audioContext.resume()" in html
        assert "noiseSuppression: true" in html
        assert 'setVoiceVisualState("needs-gesture")' in html
        assert "resumeVoiceConversation" in html
        assert "TARGET_SAMPLE_RATE = 16000" in html
        assert "/api/last-audio" in html
        assert "Celsius mobile - identidade visual compartilhada com o site" in html
        assert "--page: #F4F7F6" in html
        assert "--surface: #FFFFFF" in html
        assert "--primary: #087E72" in html
        assert "--page: #101715" in html
        assert "--primary: #42C6B7" in html
        assert "Processado no seu PC" in html
        assert "Fale com o Celsius" in html
        assert "Ocultar campo" in html

    def test_generates_pairing_token(self):
        token = ensure_mobile_token()

        assert len(token) >= 24
        assert ensure_mobile_token("abc") == "abc"

    def test_builds_https_mobile_url(self):
        url = build_mobile_url("127.0.0.1", 8787, "secret", use_https=True)

        assert url == "https://127.0.0.1:8787/?token=secret"

    def test_generates_local_https_certificate(self, tmp_path):
        pytest.importorskip("cryptography", reason="HTTPS local depende de cryptography")

        cert_file, key_file = ensure_mobile_certificate(tmp_path, lan_ip="192.168.0.10")

        assert cert_file.exists()
        assert key_file.exists()
        assert b"BEGIN CERTIFICATE" in cert_file.read_bytes()
        assert b"BEGIN RSA PRIVATE KEY" in key_file.read_bytes()

    def test_status_requires_token(self):
        server = MobileAccessServer("127.0.0.1", 0, "secret", lambda *_args: True).start()
        try:
            try:
                _request_json(f"http://127.0.0.1:{server._httpd.server_address[1]}/api/status")
            except urllib.error.HTTPError as exc:
                assert exc.code == 401
            else:
                raise AssertionError("Expected unauthorized response.")
        finally:
            server.stop()

    def test_mobile_page_disables_browser_cache(self):
        server = MobileAccessServer("127.0.0.1", 0, "secret", lambda *_args: True).start()
        try:
            port = server._httpd.server_address[1]
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/?token=secret", timeout=5
            ) as response:
                cache_control = response.headers.get("Cache-Control", "")
        finally:
            server.stop()

        assert "no-store" in cache_control

    def test_accepts_authorized_command(self):
        received = []

        def callback(message: str, source: str):
            received.append((message, source))
            return True, "ok"

        server = MobileAccessServer("127.0.0.1", 0, "secret", callback).start()
        try:
            port = server._httpd.server_address[1]
            response = _request_json(
                f"http://127.0.0.1:{port}/api/command",
                token="secret",
                payload={"message": "abrir agenda", "source": "phone_voice"},
            )
        finally:
            server.stop()

        assert response["ok"] is True
        assert response["message"] == "ok"
        assert response["response_version"] == 0
        assert received == [("abrir agenda", "phone_voice")]

    def test_publishes_latest_response_for_mobile_client(self):
        server = MobileAccessServer("127.0.0.1", 0, "secret", lambda *_args: True).start()
        try:
            version = server.publish_response("Resposta pronta")
            port = server._httpd.server_address[1]
            response = _request_json(
                f"http://127.0.0.1:{port}/api/last-response?after=0",
                token="secret",
            )
            stale = _request_json(
                f"http://127.0.0.1:{port}/api/last-response?after={version}",
                token="secret",
            )
        finally:
            server.stop()

        assert response["ok"] is True
        assert response["has_new"] is True
        assert response["version"] == version
        assert response["text"] == "Resposta pronta"
        assert response["audio_ready"] is False
        assert stale["has_new"] is False

    def test_publishes_pc_generated_audio_for_mobile_client(self):
        server = MobileAccessServer("127.0.0.1", 0, "secret", lambda *_args: True).start()
        try:
            response_version = server.publish_response("Resposta com audio")
            audio_version = server.publish_audio(b"mp3-bytes", mime_type="audio/mpeg")
            next_audio_version = server.publish_audio(b"mp3-next", mime_type="audio/mpeg")
            port = server._httpd.server_address[1]
            response = _request_json(
                f"http://127.0.0.1:{port}/api/last-response?after=0",
                token="secret",
            )
            audio, content_type, status, header_version = _request_bytes(
                f"http://127.0.0.1:{port}/api/last-audio?response_version={response_version}",
                token="secret",
            )
            next_audio, _next_content_type, _next_status, next_header_version = _request_bytes(
                "http://127.0.0.1:"
                f"{port}/api/last-audio?response_version={response_version}"
                f"&after_audio_version={header_version}",
                token="secret",
            )
        finally:
            server.stop()

        assert audio_version > 0
        assert response["audio_ready"] is True
        assert response["audio_version"] == next_audio_version
        assert audio == b"mp3-bytes"
        assert content_type == "audio/mpeg"
        assert status == 200
        assert header_version == audio_version
        assert next_audio == b"mp3-next"
        assert next_header_version == next_audio_version

    def test_command_response_includes_current_response_version(self):
        server = MobileAccessServer("127.0.0.1", 0, "secret", lambda *_args: True).start()
        try:
            version = server.publish_response("Resposta anterior")
            port = server._httpd.server_address[1]
            response = _request_json(
                f"http://127.0.0.1:{port}/api/command",
                token="secret",
                payload={"message": "abrir agenda", "source": "phone_text"},
            )
        finally:
            server.stop()

        assert response["ok"] is True
        assert response["response_version"] == version

    def test_command_callback_errors_return_json(self):
        def callback(_message: str, _source: str):
            raise RuntimeError("falha simulada")

        server = MobileAccessServer("127.0.0.1", 0, "secret", callback).start()
        try:
            port = server._httpd.server_address[1]
            try:
                _request_json(
                    f"http://127.0.0.1:{port}/api/command",
                    token="secret",
                    payload={"message": "abrir agenda", "source": "phone_text"},
                )
            except urllib.error.HTTPError as exc:
                data = json.loads(exc.read().decode("utf-8"))
                assert exc.code == 500
            else:
                raise AssertionError("Expected internal server error response.")
        finally:
            server.stop()

        assert data["ok"] is False
        assert "falha simulada" in data["message"]

    def test_accepts_authorized_voice_command(self):
        received = []

        def callback(audio: bytes, mime_type: str):
            received.append((audio, mime_type))
            return True, "abrir estoque", "voz ok"

        server = MobileAccessServer(
            "127.0.0.1",
            0,
            "secret",
            lambda *_args: True,
            voice_command_callback=callback,
        ).start()
        try:
            port = server._httpd.server_address[1]
            response = _request_json(
                f"http://127.0.0.1:{port}/api/voice-command",
                token="secret",
                payload={
                    "audio_base64": base64.b64encode(b"audio").decode("ascii"),
                    "mime_type": "audio/webm",
                },
            )
        finally:
            server.stop()

        assert response["ok"] is True
        assert response["message"] == "voz ok"
        assert response["transcript"] == "abrir estoque"
        assert response["response_version"] == 0
        assert received == [(b"audio", "audio/webm")]

    def test_voice_callback_can_return_wake_word_state(self):
        def callback(_audio: bytes, _mime_type: str):
            return {
                "ok": True,
                "transcript": "Celsius",
                "message": "Estou ouvindo",
                "wake_detected": True,
                "command_submitted": False,
                "acknowledgement": "Estou ouvindo",
            }

        server = MobileAccessServer(
            "127.0.0.1",
            0,
            "secret",
            lambda *_args: True,
            voice_command_callback=callback,
        ).start()
        try:
            port = server._httpd.server_address[1]
            response = _request_json(
                f"http://127.0.0.1:{port}/api/voice-command",
                token="secret",
                payload={
                    "audio_base64": base64.b64encode(b"audio").decode("ascii"),
                    "mime_type": "audio/wav",
                },
            )
        finally:
            server.stop()

        assert response["ok"] is True
        assert response["wake_detected"] is True
        assert response["command_submitted"] is False
        assert response["response_version"] == 0

    def test_serves_status_over_https_with_local_certificate(self, tmp_path):
        pytest.importorskip("cryptography", reason="HTTPS local depende de cryptography")

        cert_file, key_file = ensure_mobile_certificate(tmp_path, lan_ip="127.0.0.1")
        server = MobileAccessServer(
            "127.0.0.1",
            0,
            "secret",
            lambda *_args: True,
            use_https=True,
            cert_file=cert_file,
            key_file=key_file,
        ).start()
        try:
            port = server._httpd.server_address[1]
            response = _request_json(
                f"https://127.0.0.1:{port}/api/status",
                token="secret",
                context=ssl._create_unverified_context(),
            )
        finally:
            server.stop()

        assert response["ok"] is True
        assert response["https"] is True
