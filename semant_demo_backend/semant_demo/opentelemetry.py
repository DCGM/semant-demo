"""OpenTelemetry export for logs, metrics, and traces."""

from __future__ import annotations

import logging
import socket
from dataclasses import dataclass
from time import perf_counter
from typing import TYPE_CHECKING
from urllib.parse import urljoin
from uuid import uuid4

from opentelemetry import _logs, metrics, trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.system_metrics import SystemMetricsInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from semant_demo.config import Config

if TYPE_CHECKING:
    from fastapi import FastAPI


LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

SYSTEM_METRICS = {
    "process.cpu.time": ["user", "system"],
    "process.cpu.utilization": None,
    "process.memory.usage": None,
    "process.thread.count": None,
}


def feature_for_request(path: str, method: str) -> str | None:
    """Return the dashboard feature name for a user-initiated action.

    Read-only configuration and polling endpoints are deliberately excluded so
    the counter represents use of application features rather than browser
    background traffic.
    """
    if method != "POST":
        return None

    if path in {"/api/rag", "/api/rag/explain"}:
        return "rag"
    if path == "/api/search":
        return "search"
    if path.startswith("/api/summarize/") or path.startswith("/api/question/"):
        return "summarize"
    if path.startswith("/api/ai/"):
        return "ai_assistance"
    if path in {"/api/tags", "/api/tag_spans", "/api/tag_spans/batch", "/api/tag_spans/bulk_update"}:
        return "tagging"
    return None


def request_outcome(status_code: int) -> str:
    """Map an HTTP status code to a low-cardinality metric attribute."""
    if status_code >= 500:
        return "server_error"
    if status_code >= 400:
        return "client_error"
    return "success"


def request_authentication(authorization: str | None) -> str:
    """Classify the request without recording a user identity or token."""
    if authorization and authorization.lower().startswith("bearer "):
        return "bearer_token"
    return "anonymous"


class _SkipExporterInternals(logging.Filter):
    """Prevent collector errors from recursively generating more OTLP logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.name.startswith("opentelemetry.exporter")


@dataclass
class OpenTelemetry:
    """Providers and instrumentors owned by the application."""

    tracer: object
    meter: object
    logger: object
    feature_request_counter: object
    feature_request_duration_histogram: object
    trace_provider: TracerProvider
    meter_provider: MeterProvider
    log_provider: LoggerProvider
    logging_handler: LoggingHandler
    logging_instrumentator: LoggingInstrumentor
    system_metric_instrumentator: SystemMetricsInstrumentor
    fastapi_instrumentator: FastAPIInstrumentor
    app: FastAPI | None = None

    def record_feature_request(
        self,
        *,
        feature: str,
        authentication: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        """Record one completed dashboard feature action and its duration."""
        attributes = {
            "feature": feature,
            "authentication": authentication,
            "outcome": request_outcome(status_code),
        }
        self.feature_request_counter.add(
            1,
            attributes=attributes,
        )
        self.feature_request_duration_histogram.record(
            duration_seconds,
            attributes=attributes,
        )

    def instrument_app(self, app: FastAPI) -> None:
        self.fastapi_instrumentator.instrument_app(
            app,
            tracer_provider=self.trace_provider,
            meter_provider=self.meter_provider,
        )
        self.app = app

    def shutdown(self) -> None:
        """Stop instrumentation and flush all buffered telemetry."""
        if self.app is not None:
            self.fastapi_instrumentator.uninstrument_app(self.app)
        self.system_metric_instrumentator.uninstrument()
        self.logging_instrumentator.uninstrument()
        logging.getLogger().removeHandler(self.logging_handler)
        self.log_provider.shutdown()
        self.meter_provider.shutdown()
        self.trace_provider.shutdown()


UNMATCHED_ROUTE = "<unmatched>"

# Server-span attributes that FastAPIInstrumentor fills from the raw request URL.
_RAW_URL_SPAN_ATTRIBUTES = ("http.target", "http.url", "url.path", "url.full", "url.query")


def route_template(scope: Scope) -> str:
    """The matched route's path template, e.g. ``/api/question/{question_text}``.

    Never the raw path: path parameters can carry user text (a question, a search).
    """
    return getattr(scope.get("route"), "path_format", None) or UNMATCHED_ROUTE


def _redact_server_span(route: str) -> None:
    """Replace the raw URL on the current server span with the route template."""
    span = trace.get_current_span()
    if not span.is_recording():
        return
    recorded = getattr(span, "attributes", None) or {}
    for key in _RAW_URL_SPAN_ATTRIBUTES:
        if key in recorded:
            span.set_attribute(key, "" if key == "url.query" else route)


class RequestTelemetryMiddleware:
    """Create one structured ``INFO`` log record for every completed HTTP request.

    Also records the feature metrics when ``telemetry`` is enabled. Logs and the server
    span carry the route template, not the raw URL. It is a plain ASGI middleware so a
    streamed response is timed until its end and a client disconnect still reaches the
    endpoint, which cancels its remaining work.
    """

    def __init__(self, app: ASGIApp, telemetry: OpenTelemetry | None = None):
        self.app = app
        self.telemetry = telemetry

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request_id = headers.get("x-request-id", str(uuid4()))
        started_at = perf_counter()
        attributes = {
            "request.id": request_id,
            "http.request.method": scope["method"],
        }
        feature = feature_for_request(scope["path"], scope["method"])
        authentication = request_authentication(headers.get("authorization"))
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
                # The server span ends with the response body, so redact it now.
                _redact_server_span(route_template(scope))
            await send(message)

        def record(status: int, duration_seconds: float) -> None:
            # Known only after routing; also set when the endpoint raised.
            attributes["http.route"] = route_template(scope)
            _redact_server_span(attributes["http.route"])  # a span still open after an error
            attributes["http.response.status_code"] = status
            attributes["http.server.request.duration_ms"] = round(duration_seconds * 1000, 2)
            if self.telemetry is not None and feature is not None:
                self.telemetry.record_feature_request(
                    feature=feature,
                    authentication=authentication,
                    status_code=status,
                    duration_seconds=duration_seconds,
                )

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            record(500, perf_counter() - started_at)
            logging.getLogger(__name__).exception("HTTP request failed", extra=attributes)
            raise

        record(status_code, perf_counter() - started_at)
        logging.getLogger(__name__).info("HTTP request completed", extra=attributes)


def initialize_opentelemetry(config: Config) -> OpenTelemetry | None:
    """Configure OTLP/HTTP exporters and application instrumentors.

    Providers are process-wide, so call this once per process (``create_app`` does).
    """
    if not config.OTEL_ENABLED:
        return None

    resource = Resource.create(
        {
            "service.name": config.OTEL_SERVICE_NAME,
            "service.version": "0.1.0",
            "service.instance.id": socket.gethostname(),
            "deployment.environment.name": config.DEPLOYMENT_ENVIRONMENT,
        }
    )

    trace_exporter = OTLPSpanExporter(
        endpoint=urljoin(
            config.OTEL_EXPORTER_OTLP_ENDPOINT,
            config.OTEL_EXPORTER_OTLP_TRACES_PATH,
        )
    )
    trace_processor = BatchSpanProcessor(trace_exporter)
    trace_provider = TracerProvider(resource=resource)
    trace_provider.add_span_processor(trace_processor)
    trace.set_tracer_provider(trace_provider)
    tracer = trace.get_tracer(__name__)

    meter_exporter = OTLPMetricExporter(
        endpoint=urljoin(
            config.OTEL_EXPORTER_OTLP_ENDPOINT,
            config.OTEL_EXPORTER_OTLP_METRICS_PATH,
        )
    )
    meter_reader = PeriodicExportingMetricReader(
        meter_exporter,
        export_interval_millis=config.OTEL_METRIC_EXPORT_INTERVAL_MS,
    )
    meter_provider = MeterProvider(
        metric_readers=[meter_reader],
        resource=resource,
    )
    metrics.set_meter_provider(meter_provider)
    meter = metrics.get_meter(__name__)
    feature_request_counter = meter.create_counter(
        "semant_demo.feature.requests",
        unit="{request}",
        description="Completed user-initiated application feature requests.",
    )
    feature_request_duration_histogram = meter.create_histogram(
        "semant_demo.feature.request.duration",
        unit="s",
        description="Duration of completed user-initiated application feature requests.",
    )

    log_exporter = OTLPLogExporter(
        endpoint=urljoin(
            config.OTEL_EXPORTER_OTLP_ENDPOINT,
            config.OTEL_EXPORTER_OTLP_LOGS_PATH,
        )
    )
    log_processor = BatchLogRecordProcessor(log_exporter)
    log_provider = LoggerProvider(resource=resource)
    log_provider.add_log_record_processor(log_processor)
    _logs.set_logger_provider(log_provider)
    logger = _logs.get_logger(__name__)

    logging_handler = LoggingHandler(
        level=LOG_LEVELS[config.LOG_LEVEL],
        logger_provider=log_provider,
    )
    logging_handler.addFilter(_SkipExporterInternals())
    logging.getLogger().addHandler(logging_handler)

    logging_instrumentator = LoggingInstrumentor()
    system_metric_instrumentator = SystemMetricsInstrumentor(config=SYSTEM_METRICS)
    fastapi_instrumentator = FastAPIInstrumentor()
    logging_instrumentator.instrument(
        set_logging_format=True,
        log_level=LOG_LEVELS[config.LOG_LEVEL],
    )
    system_metric_instrumentator.instrument(meter_provider=meter_provider)

    logging.getLogger(__name__).info(
        "OpenTelemetry export enabled",
        extra={
            "otel.exporter.endpoint": config.OTEL_EXPORTER_OTLP_ENDPOINT,
            "deployment.environment.name": config.DEPLOYMENT_ENVIRONMENT,
        },
    )

    return OpenTelemetry(
        tracer=tracer,
        meter=meter,
        logger=logger,
        feature_request_counter=feature_request_counter,
        feature_request_duration_histogram=feature_request_duration_histogram,
        trace_provider=trace_provider,
        meter_provider=meter_provider,
        log_provider=log_provider,
        logging_handler=logging_handler,
        logging_instrumentator=logging_instrumentator,
        system_metric_instrumentator=system_metric_instrumentator,
        fastapi_instrumentator=fastapi_instrumentator,
    )
