"""Exercise Uvicorn, ASGI lifespan and HTTP on a kernel-selected loopback port."""

import json
import socket
import urllib.error
import urllib.request


def _server():
    from core.settings import get_settings
    from core.web_api.server import LocalWebApiServer

    server = LocalWebApiServer(host="127.0.0.1", port=0, settings=get_settings())
    assert server.start(timeout=10), "LocalWebApiServer failed to bind/start"
    sockets = [sock for listener in server._server.servers for sock in listener.sockets]
    assert len(sockets) == 1
    port = sockets[0].getsockname()[1]
    return server, port


def _get(port, path, **headers):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers=headers)
    return opener.open(request, timeout=3)


def _assert_http(server, port):
    with _get(port, "/api/v1/health") as response:
        body = json.load(response)
        assert response.status == 200
        assert body["ok"] is True and body["processing_mode"] == "local"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
    try:
        _get(port, "/api/v1/session")
    except urllib.error.HTTPError as exc:
        assert exc.code == 401
        exc.close()
    else:
        raise AssertionError("Unauthenticated HTTP session request was accepted")
    token = server.app.state.access_token
    with _get(port, "/api/v1/session", Authorization=f"Bearer {token}") as response:
        assert json.load(response)["ok"] is True
    with _get(port, "/app/") as response:
        assert b"<html" in response.read().lower()


def lifecycle():
    server, port = _server()
    try:
        thread = server._thread
        assert server.start() and server._thread is thread
        _assert_http(server, port)
    finally:
        server.stop(timeout=10)
    assert not server._thread.is_alive(), "Uvicorn thread survived shutdown"
    assert server.app.state.mobile_server is None, "Smoke unexpectedly started mobile LAN access"
    server.stop()
    with socket.socket() as probe:
        probe.settimeout(1)
        assert probe.connect_ex(("127.0.0.1", port)) != 0, "HTTP listener survived stop()"


def restart():
    server, _ = _server()
    server.stop(timeout=10)
    assert not server._thread.is_alive()
    try:
        assert server.start(timeout=5), "Restart returned failure"
        assert server._thread.is_alive(), "Restart reported success with no server thread"
        sockets = [sock for listener in server._server.servers for sock in listener.sockets]
        assert sockets, "Restart reported success but left no listening sockets"
        port = sockets[0].getsockname()[1]
        _assert_http(server, port)
    finally:
        server.stop(timeout=10)
    assert not server._thread.is_alive()
