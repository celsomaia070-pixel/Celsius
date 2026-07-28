"""OpenTelemetry instrumentation for Celsius.

Provides tracing, metrics, and auto-instrumentation.
Falls back to no-op if opentelemetry packages are not installed.
"""

import logging
import os
from collections.abc import Generator
from contextlib import contextmanager, suppress
from typing import Any

_logger = logging.getLogger(__name__)

_OTEL_AVAILABLE = False
try:
    from opentelemetry import metrics, trace  # type: ignore[no-redef]
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.metrics import MeterProvider  # type: ignore[no-redef]
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
    from opentelemetry.sdk.trace import TracerProvider  # type: ignore[no-redef]
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.trace import Status, StatusCode

    _OTEL_AVAILABLE = True
except ImportError:
    pass

_INSTRUMENTORS_AVAILABLE = False
try:
    from opentelemetry.instrumentation.logging import LoggingInstrumentor  # type: ignore[no-redef]
    from opentelemetry.instrumentation.requests import (
        RequestsInstrumentor,  # type: ignore[no-redef]
    )
    from opentelemetry.instrumentation.urllib import URLLibInstrumentor  # type: ignore[no-redef]

    _INSTRUMENTORS_AVAILABLE = True
except ImportError:
    pass

try:
    from opentelemetry.instrumentation.httpx import (
        HTTPXClientInstrumentor,  # type: ignore[no-redef]
    )
except ImportError:
    HTTPXClientInstrumentor = None  # type: ignore[assignment,misc]

try:
    from opentelemetry.instrumentation.aiohttp_client import (
        AioHttpClientInstrumentor,  # type: ignore[no-redef]
    )
except ImportError:
    AioHttpClientInstrumentor = None  # type: ignore[assignment,misc]

_tracer_provider: Any = None
_meter_provider: Any = None
_tracer: Any = None
_meter: Any = None


class MetricNames:
    LLM_REQUESTS_TOTAL = "celsius.llm.requests.total"
    LLM_TOKENS_TOTAL = "celsius.llm.tokens.total"
    LLM_INFERENCE_SECONDS = "celsius.llm.inference.duration"
    LLM_STREAM_CHUNKS = "celsius.llm.stream.chunks"
    TOOL_CALLS_TOTAL = "celsius.tool.calls.total"
    TOOL_DURATION_SECONDS = "celsius.tool.duration"
    TOOL_ERRORS_TOTAL = "celsius.tool.errors.total"
    RAG_QUERIES_TOTAL = "celsius.rag.queries.total"
    RAG_RETRIEVAL_SECONDS = "celsius.rag.retrieval.duration"
    RAG_CHUNKS_RETRIEVED = "celsius.rag.chunks.retrieved"
    MEMORY_SEARCHES_TOTAL = "celsius.memory.searches.total"
    MEMORY_SEARCH_SECONDS = "celsius.memory.search.duration"
    WORKER_JOBS_TOTAL = "celsius.worker.jobs.total"
    WORKER_JOB_DURATION_SECONDS = "celsius.worker.job.duration"
    WORKER_ERRORS_TOTAL = "celsius.worker.errors.total"
    HEALTH_CHECK_TOTAL = "celsius.health.checks.total"
    MODEL_LOAD_SECONDS = "celsius.model.load.duration"
    HTTP_REQUESTS_TOTAL = "celsius.http.requests.total"
    HTTP_REQUEST_DURATION_SECONDS = "celsius.http.request.duration"


class _NoOpSpan:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def set_attribute(self, *a):
        pass

    def set_status(self, *a):
        pass

    def record_exception(self, *a):
        pass


class _NoOpTracer:
    def start_as_current_span(self, name, **kw):
        return _NoOpSpan()


class _NoOpCounter:
    def add(self, *a, **kw):
        pass


class _NoOpHistogram:
    def record(self, *a, **kw):
        pass


class _NoOpMeter:
    def create_counter(self, *a, **kw):
        return _NoOpCounter()

    def create_histogram(self, *a, **kw):
        return _NoOpHistogram()


_noop_tracer = _NoOpTracer()
_noop_meter = _NoOpMeter()


def init_telemetry(
    service_name: str = "celsius",
    service_version: str = "1.0.0",
    otlp_endpoint: str = "http://localhost:4317",
    sample_rate: float = 1.0,
    log_level: str = "INFO",
) -> tuple:
    global _tracer_provider, _meter_provider, _tracer, _meter

    if _tracer is not None and not isinstance(_tracer, _NoOpTracer):
        return _tracer, _meter

    if not _OTEL_AVAILABLE:
        _logger.info("opentelemetry not installed — using no-op telemetry")
        _tracer = _noop_tracer
        _meter = _noop_meter
        return _tracer, _meter

    if _tracer_provider is not None:
        return _tracer, _meter

    resource = Resource.create(
        {
            SERVICE_NAME: service_name,
            SERVICE_VERSION: service_version,
            "deployment.environment": os.getenv("ENVIRONMENT", "development"),
        }
    )

    _tracer_provider = TracerProvider(resource=resource)
    otlp_trace_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    _tracer_provider.add_span_processor(BatchSpanProcessor(otlp_trace_exporter))
    trace.set_tracer_provider(_tracer_provider)
    _tracer = trace.get_tracer(__name__, service_version)

    otlp_metric_exporter = OTLPMetricExporter(endpoint=otlp_endpoint, insecure=True)
    metric_reader = PeriodicExportingMetricReader(
        exporter=otlp_metric_exporter, export_interval_millis=60000
    )
    _meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(_meter_provider)
    _meter = metrics.get_meter(__name__, service_version)

    if _INSTRUMENTORS_AVAILABLE:
        with suppress(Exception):
            LoggingInstrumentor().instrument(set_logging_format=True)
        with suppress(Exception):
            RequestsInstrumentor().instrument()
        URLLibInstrumentor().instrument()
    if HTTPXClientInstrumentor is not None:
        with suppress(Exception):
            HTTPXClientInstrumentor().instrument()
    if AioHttpClientInstrumentor is not None:
        with suppress(Exception):
            AioHttpClientInstrumentor().instrument()

    _logger.info(
        "OpenTelemetry initialized",
        extra={"service_name": service_name, "otlp_endpoint": otlp_endpoint},
    )
    return _tracer, _meter


def get_tracer() -> Any:
    global _tracer
    if _tracer is None:
        init_telemetry()
    return _tracer


def get_meter() -> Any:
    global _meter
    if _meter is None:
        init_telemetry()
    return _meter


def shutdown_telemetry() -> None:
    global _tracer_provider, _meter_provider, _tracer, _meter
    if _tracer_provider and _OTEL_AVAILABLE:
        _tracer_provider.shutdown()
    if _meter_provider and _OTEL_AVAILABLE:
        _meter_provider.shutdown()
    _tracer_provider = None
    _meter_provider = None
    _tracer = None
    _meter = None


def trace_function(name: str | None = None, attributes: dict | None = None):
    def decorator(func):
        def wrapper(*args, **kwargs):
            tracer = get_tracer()
            span_name = name or f"{func.__module__}.{func.__qualname__}"
            with tracer.start_as_current_span(span_name) as span:
                if attributes:
                    for k, v in attributes.items():
                        span.set_attribute(k, v)
                try:
                    result = func(*args, **kwargs)
                    if _OTEL_AVAILABLE:
                        span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    if _OTEL_AVAILABLE:
                        span.set_status(Status(StatusCode.ERROR, str(e)))
                        span.record_exception(e)
                    raise

        return wrapper

    return decorator


@contextmanager
def trace_span(name: str, attributes: dict | None = None) -> Generator:
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as span:
        if attributes:
            for k, v in attributes.items():
                span.set_attribute(k, v)
        try:
            yield span
            if _OTEL_AVAILABLE:
                span.set_status(Status(StatusCode.OK))
        except Exception as e:
            if _OTEL_AVAILABLE:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
            raise


def record_metric(name: str, value: float, attributes: dict | None = None) -> None:
    meter = get_meter()
    counter = meter.create_counter(name)
    counter.add(value, attributes or {})


def record_histogram(name: str, value: float, attributes: dict | None = None) -> None:
    meter = get_meter()
    histogram = meter.create_histogram(name)
    histogram.record(value, attributes or {})


def create_llm_instruments(meter: Any = None) -> dict:
    m = meter or get_meter()
    return {
        "requests": m.create_counter(MetricNames.LLM_REQUESTS_TOTAL),
        "tokens": m.create_counter(MetricNames.LLM_TOKENS_TOTAL),
        "inference_duration": m.create_histogram(MetricNames.LLM_INFERENCE_SECONDS),
        "stream_chunks": m.create_counter(MetricNames.LLM_STREAM_CHUNKS),
    }


def create_tool_instruments(meter: Any = None) -> dict:
    m = meter or get_meter()
    return {
        "calls": m.create_counter(MetricNames.TOOL_CALLS_TOTAL),
        "duration": m.create_histogram(MetricNames.TOOL_DURATION_SECONDS),
        "errors": m.create_counter(MetricNames.TOOL_ERRORS_TOTAL),
    }


def create_rag_instruments(meter: Any = None) -> dict:
    m = meter or get_meter()
    return {
        "queries": m.create_counter(MetricNames.RAG_QUERIES_TOTAL),
        "retrieval_duration": m.create_histogram(MetricNames.RAG_RETRIEVAL_SECONDS),
        "chunks_retrieved": m.create_histogram(MetricNames.RAG_CHUNKS_RETRIEVED),
    }


def create_worker_instruments(meter: Any = None) -> dict:
    m = meter or get_meter()
    return {
        "jobs": m.create_counter(MetricNames.WORKER_JOBS_TOTAL),
        "job_duration": m.create_histogram(MetricNames.WORKER_JOB_DURATION_SECONDS),
        "errors": m.create_counter(MetricNames.WORKER_ERRORS_TOTAL),
    }
