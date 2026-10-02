"""Tests for local mobile access server."""

import base64
import json
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.mobile_access import (
    MobileAccessRuntime,
    MobileAccessServer,
    _create_server_ssl_context,
    _mobile_html,
    build_mobile_url,
    ensure_mobile_certificate,
    ensure_mobile_token,
    get_mobile_runtime,
    start_for_settings,
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

    def test_mobile_page_uses_sphere_chat_voice_interface(self):
        html = _mobile_html("secret", True)

        assert "Falar comando" not in html
        assert "SpeechRecognition" not in html
        assert "SpeechDetection" not in html
        assert "token=" not in html
        assert "Bearer " not in html
        assert "voiceSession" not in html
        assert "themeToggle" not in html
        assert "composerBody" not in html
        assert "scheduleAutomaticWakeListening" not in html
        assert "voiceEnabled = true;" in html
        assert 'canvas id="orb"' in html
        assert "drawOrb" in html
        assert "playbackLevel" in html
        assert "micDrive" in html
        assert 'id="micBtn"' in html
        assert 'id="sendBtn"' in html
        assert 'id="input"' in html
        assert "waitForResponse" in html
        assert "/api/command" in html
        assert "/api/voice-command" in html
        assert "/api/last-audio" in html
        assert "command_submitted" in html
        assert "TARGET_SAMPLE_RATE = 16000" in html
        assert "encodeWav" in html
        assert "noiseSuppression: true" in html
        assert "history.replaceState" in html

    def test_generates_pairing_token(self):
        token = ensure_mobile_token()

        assert len(token) >= 24
        assert ensure_mobile_token("abc") == "abc"

    def test_builds_https_mobile_url(self):
        url = build_mobile_url("127.0.0.1", 8787, "secret", use_https=True)

        assert url == "https://127.0.0.1:8787/?pair=secret"

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
            with urllib.request.urlopen(server.url, timeout=5) as response:
                cache_control = response.headers.get("Cache-Control", "")
        finally:
            server.stop()

        assert "no-store" in cache_control

    def test_consumed_qr_link_is_replaced_immediately(self):
        server = MobileAccessServer("127.0.0.1", 0, "secret", lambda *_args: True).start()
        try:
            first_url = server.url
            with urllib.request.urlopen(first_url, timeout=5):
                pass
            second_url = server.url
        finally:
            server.stop()

        assert second_url != first_url

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

    def test_publish_partial_streams_live_text_without_consuming_version(self):
        server = MobileAccessServer("127.0.0.1", 0, "secret", lambda *_args: True).start()
        try:
            server.publish_partial("Ol")
            partial = server.latest_response()
            version = partial["version"]
            final = server.publish_response("Ola final")
        finally:
            server.stop()

        assert partial["live_active"] is True
        assert partial["live_text"] == "Ol"
        assert version == 0
        assert server.latest_response()["live_active"] is False
        assert final == 1
        assert server.latest_response()["text"] == "Ola final"

    def test_live_text_not_final_via_http_endpoint(self):
        server = MobileAccessServer("127.0.0.1", 0, "secret", lambda *_args: True).start()
        try:
            server.publish_partial("Gerando...")
            port = server._httpd.server_address[1]
            response = _request_json(
                f"http://127.0.0.1:{port}/api/last-response?after=0",
                token="secret",
            )
        finally:
            server.stop()

        assert response["ok"] is True
        assert response["has_new"] is False
        assert response["live_active"] is True
        assert response["live_text"] == "Gerando..."

    def test_publish_partial_ignores_empty(self):
        server = MobileAccessServer("127.0.0.1", 0, "secret", lambda *_args: True).start()
        try:
            server.publish_partial("   ")
            state = server.latest_response()
        finally:
            server.stop()

        assert state["live_active"] is False
        assert state["live_text"] == ""

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
        assert data["message"] == "Erro interno ao entregar comando ao Celsius."

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

    def test_command_callback_can_return_job_metadata(self):
        server = MobileAccessServer(
            "127.0.0.1",
            0,
            "secret",
            lambda *_args: {
                "ok": True,
                "message": "Comando enviado ao Celsius.",
                "job_id": "job-mobile-1",
                "conversation_id": "abc123def456",
                "command_submitted": True,
            },
        ).start()
        try:
            port = server._httpd.server_address[1]
            response = _request_json(
                f"http://127.0.0.1:{port}/api/command",
                token="secret",
                payload={"message": "Ola", "source": "phone_text"},
            )
        finally:
            server.stop()

        assert response["ok"] is True
        assert response["job_id"] == "job-mobile-1"
        assert response["conversation_id"] == "abc123def456"

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


def _fake_mobile_settings(
    *,
    data_dir: Path,
    port: int = 0,
    allow_lan: bool = False,
    https: bool = False,
    token: str = "s3cret",
    voice: bool = True,
):
    mobile = SimpleNamespace(
        host="127.0.0.1",
        port=port,
        allow_lan=allow_lan,
        use_https=https,
        voice_commands_enabled=voice,
        pairing_token=token,
    )
    return SimpleNamespace(data_dir=data_dir, mobile=mobile)


class TestMobileAccessRuntime:
    def test_answers_starting_notice_before_sink_is_attached(self):
        runtime = MobileAccessRuntime()

        ok, message = runtime.command("olar", "phone")
        ok_voice, transcript, message_voice = runtime.voice(b"audio", "audio/wav")

        assert ok is False
        assert "iniciando" in message
        assert ok_voice is False
        assert transcript == ""
        assert "iniciando" in message_voice

    def test_forwards_commands_to_attached_sink(self):
        runtime = MobileAccessRuntime()

        class Sink:
            def _queue_mobile_command(self, message, source):
                return True, f"recebido {source}: {message}"

            def _queue_mobile_voice_command(self, audio, mime_type):
                return True, "voz", f"voz {mime_type}"

        runtime.set_sink(Sink())

        ok, message = runtime.command("abrir agenda", "phone")
        ok_voice, transcript, message_voice = runtime.voice(b"audio", "audio/wav")

        assert ok is True
        assert message == "recebido phone: abrir agenda"
        assert ok_voice is True
        assert transcript == "voz"
        assert message_voice == "voz audio/wav"

    def test_close_stops_server_and_clears_sink(self):
        runtime = MobileAccessRuntime()

        class Sink:
            def _queue_mobile_command(self, message, source):
                return True, message

        runtime.set_sink(Sink())
        assert runtime.sink is not None
        runtime.close()

        assert runtime.server is None
        assert runtime.sink is None
        ok, _message = runtime.command("x", "phone")
        assert ok is False


class TestStartForSettings:
    def test_starts_loopback_http_server_and_returns_notice(self, tmp_path):
        server, notice = start_for_settings(
            _fake_mobile_settings(data_dir=tmp_path),
            command_callback=lambda message, source: (True, "ok"),
        )
        try:
            assert server.is_running
            assert server._httpd.server_address[1] != 0
            assert server.host == "127.0.0.1"
            assert server.use_https is False
            assert notice == ""
            response = _request_json(
                f"http://127.0.0.1:{server._httpd.server_address[1]}/api/command",
                token="s3cret",
                payload={"message": "abrir agenda", "source": "phone"},
            )
        finally:
            server.stop()

        assert response["ok"] is True
        assert response["message"] == "ok"

    def test_serves_runtime_commands_before_window_attaches(self, tmp_path):
        runtime = get_mobile_runtime()
        runtime.close()
        server, _notice = start_for_settings(
            _fake_mobile_settings(data_dir=tmp_path),
            command_callback=runtime.command,
            voice_command_callback=runtime.voice,
        )
        runtime.attach(server)
        try:
            port = server._httpd.server_address[1]
            response = _request_json(
                f"http://127.0.0.1:{port}/api/command",
                token="s3cret",
                payload={"message": "abrir agenda", "source": "phone"},
            )
        finally:
            runtime.close()

        assert response["ok"] is False
        assert "iniciando" in response["message"]

    def test_preserves_loopback_https_when_certificate_available(self, tmp_path):
        pytest.importorskip("cryptography", reason="HTTPS local depende de cryptography")

        server, notice = start_for_settings(
            _fake_mobile_settings(data_dir=tmp_path, https=True),
            command_callback=lambda message, source: (True, "ok"),
        )
        try:
            assert server.use_https is True
            assert "Aviso" not in notice
        finally:
            server.stop()
