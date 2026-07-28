"""Simple HTTP server for exposing metrics and health check endpoints.

Endpoints:
- GET /metrics  - All metrics as JSON
- GET /health   - Health check status
- GET /circuit-breakers - Circuit breaker states
"""

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

logger = logging.getLogger(__name__)


class _MetricsHandler(BaseHTTPRequestHandler):
    """Handler for metrics HTTP endpoints."""

    def do_GET(self):
        from core.circuit_breaker import get_all_breakers
        from core.metrics import get_metrics

        if self.path == "/metrics":
            metrics = get_metrics()
            data = metrics.snapshot()
            self._respond(200, data)

        elif self.path == "/health":
            try:
                from core.llama_cpp import get_llama_manager

                manager = get_llama_manager()
                healthy = manager.is_healthy() if manager._started else False
                self._respond(
                    200,
                    {
                        "status": "healthy" if healthy else "degraded",
                        "model_loaded": manager._started,
                        "model_id": manager.current_model_id,
                    },
                )
            except Exception as e:
                self._respond(200, {"status": "error", "error": str(e)})

        elif self.path == "/circuit-breakers":
            breakers = get_all_breakers()
            self._respond(200, {"breakers": breakers})

        else:
            self._respond(404, {"error": "Not found"})

    def _respond(self, status: int, data: dict):
        body = json.dumps(data, indent=2, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Suppress default access logs
        pass


class MetricsServer:
    """Background HTTP server for metrics and health endpoints."""

    def __init__(self, host: str = "127.0.0.1", port: int = 9090):
        self._host = host
        self._port = port
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._server is not None:
            return
        try:
            self._server = HTTPServer((self._host, self._port), _MetricsHandler)
            self._thread = threading.Thread(
                target=self._server.serve_forever,
                daemon=True,
                name="metrics-server",
            )
            self._thread.start()
            logger.info("Metrics server started on http://%s:%d", self._host, self._port)
        except Exception as e:
            logger.warning("Failed to start metrics server: %s", e)

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server = None
            self._thread = None
            logger.info("Metrics server stopped")


# Global singleton
_metrics_server: MetricsServer | None = None


def get_metrics_server() -> MetricsServer:
    global _metrics_server
    if _metrics_server is None:
        _metrics_server = MetricsServer()
    return _metrics_server
