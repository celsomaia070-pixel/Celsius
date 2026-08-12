"""Regression tests for security boundaries identified during the release audit."""

from __future__ import annotations

import socket

import pytest

from core.network_security import UnsafeNetworkTargetError, validate_public_http_url
from core.tool_approval import APPROVAL_REQUIRED_PREFIX, ToolApprovalStore, approval_message


def _dns_result(address: str):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    return [(family, socket.SOCK_STREAM, 6, "", (address, 443))]


class TestOutboundNetworkPolicy:
    @pytest.mark.parametrize(
        "url",
        [
            "file:///etc/passwd",
            "ftp://example.com/file",
            "http://user:password@example.com/",
            "http:///missing-host",
        ],
    )
    def test_rejects_unsafe_url_shapes(self, url):
        with pytest.raises(UnsafeNetworkTargetError):
            validate_public_http_url(url)

    @pytest.mark.parametrize(
        "address",
        ["127.0.0.1", "10.0.0.8", "169.254.169.254", "192.168.1.10", "::1"],
    )
    def test_rejects_local_private_and_metadata_addresses(self, monkeypatch, address):
        monkeypatch.setattr(socket, "getaddrinfo", lambda *_args, **_kwargs: _dns_result(address))
        with pytest.raises(UnsafeNetworkTargetError):
            validate_public_http_url("https://example.test/resource")

    def test_accepts_public_https_address(self, monkeypatch):
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda *_args, **_kwargs: _dns_result("93.184.216.34"),
        )
        assert validate_public_http_url("https://example.com/path") == "https://example.com/path"


class TestSensitiveToolApproval:
    def test_approval_is_exact_one_time_and_preserves_arguments(self):
        store = ToolApprovalStore(ttl_seconds=300)
        pending = store.request("executar_codigo", {"codigo": "print(42)"})

        assert store.parse_command(f"AUTORIZAR {pending.code}") == (
            "AUTORIZAR",
            pending.code,
        )
        assert store.parse_command(f"autorizar {pending.code} agora") is None
        assert store.consume(pending.code) == pending
        assert store.consume(pending.code) is None

    def test_approval_message_displays_tool_and_arguments(self):
        store = ToolApprovalStore()
        pending = store.request("navegar_web", {"url": "https://example.com"})
        message = approval_message(pending)

        assert message.startswith(APPROVAL_REQUIRED_PREFIX)
        assert pending.code in message
        assert "navegar_web" in message
        assert "https://example.com" in message
