"""Outbound URL validation shared by browser and multimodal loaders."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit


class UnsafeNetworkTargetError(ValueError):
    """Raised when an outbound URL can reach a local or privileged network."""


def _is_public_address(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return bool(ip.is_global and not ip.is_multicast and not ip.is_unspecified)


def validate_public_http_url(url: str) -> str:
    """Allow only public HTTP(S) targets and reject credentials/private DNS results."""
    parsed = urlsplit(str(url or "").strip())
    if parsed.scheme.lower() not in {"http", "https"}:
        raise UnsafeNetworkTargetError("Somente URLs http ou https sao permitidas.")
    if not parsed.hostname:
        raise UnsafeNetworkTargetError("A URL precisa informar um host valido.")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeNetworkTargetError("URLs com credenciais incorporadas nao sao permitidas.")

    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(
                parsed.hostname,
                parsed.port or (443 if parsed.scheme.lower() == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        }
    except socket.gaierror as error:
        raise UnsafeNetworkTargetError(
            f"Nao foi possivel resolver o host: {parsed.hostname}"
        ) from error
    if not addresses or any(not _is_public_address(address) for address in addresses):
        raise UnsafeNetworkTargetError(
            "Acesso a enderecos locais, privados ou reservados foi bloqueado."
        )
    return parsed.geturl()
