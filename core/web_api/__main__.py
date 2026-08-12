"""Run the local Celsius API during the incremental UI migration."""

from __future__ import annotations

import argparse
import ipaddress
import ssl

from core.mobile_access import (
    _create_server_ssl_context,
    ensure_mobile_certificate,
    get_lan_ip,
)


def _is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def main() -> int:
    # Restore stdlib SSL before importing FastAPI/Uvicorn. On some Windows
    # environments pip injects a client-only truststore context at startup.
    native_ssl_context = _create_server_ssl_context()
    ssl.SSLContext = type(native_ssl_context)

    import uvicorn

    from core.settings import get_settings
    from core.web_api.app import create_app

    parser = argparse.ArgumentParser(description="Executa a API local do Celsius.")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument(
        "--allow-lan",
        action="store_true",
        help="Permite exposicao explicita na rede local.",
    )
    parser.add_argument(
        "--http",
        action="store_true",
        help="Desativa HTTPS explicitamente (o microfone movel pode ser bloqueado).",
    )
    settings = get_settings()
    args = parser.parse_args()
    configured_lan = bool(settings.mobile.enabled and settings.mobile.allow_lan)
    # Binding all interfaces is allowed only after the explicit LAN checks below.
    host = args.host or (
        "0.0.0.0" if configured_lan else "127.0.0.1"  # nosec B104
    )
    if not _is_loopback(host) and not (args.allow_lan or configured_lan):
        parser.error("Use --allow-lan para expor a API fora deste computador.")
    if not _is_loopback(host) and args.http:
        parser.error("HTTP so e permitido em loopback. A rede local exige HTTPS.")

    use_https = bool(not _is_loopback(host) and settings.mobile.use_https and not args.http)
    cert_file = key_file = None
    if use_https:
        cert_file, key_file = ensure_mobile_certificate(
            settings.data_dir / "mobile_access",
            lan_ip=get_lan_ip(),
        )
        ssl_context = native_ssl_context
    else:
        ssl_context = None

    scheme = "https" if use_https else "http"
    display_host = get_lan_ip() if host in {"0.0.0.0", "::"} else host  # nosec B104
    print(f"Celsius Local API: {scheme}://{display_host}:{args.port}/api/docs")
    print("Use o botao de pareamento no Celsius para autorizar outro dispositivo.")
    application = create_app(
        settings=settings,
        lan_access_enabled=not _is_loopback(host),
        public_scheme=scheme,
        public_port=args.port,
    )
    if use_https:
        # pip/truststore can replace ssl.SSLContext with a client-only wrapper.
        # Uvicorn receives the native context on affected Windows installations.
        config = uvicorn.Config(application, host=host, port=args.port, log_level="info")
        config.load()
        ssl_context.load_cert_chain(str(cert_file), str(key_file))
        config.ssl = ssl_context
        uvicorn.Server(config).run()
    else:
        uvicorn.run(application, host=host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
