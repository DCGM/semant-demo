"""OpenTelemetry export for logs, metrics, and traces."""

from __future__ import annotations

import logging
import socket
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urljoin

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

from semant_demo.config import config

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
    trace_provider: TracerProvider
    meter_provider: MeterProvider
    log_provider: LoggerProvider
    logging_handler: LoggingHandler
    logging_instrumentator: LoggingInstrumentor
    system_metric_instrumentator: SystemMetricsInstrumentor
    fastapi_instrumentator: FastAPIInstrumentor
    app: FastAPI | None = None

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


def initialize_opentelemetry() -> OpenTelemetry | None:
    """Configure OTLP/HTTP exporters and application instrumentors."""
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
        trace_provider=trace_provider,
        meter_provider=meter_provider,
        log_provider=log_provider,
        logging_handler=logging_handler,
        logging_instrumentator=logging_instrumentator,
        system_metric_instrumentator=system_metric_instrumentator,
        fastapi_instrumentator=fastapi_instrumentator,
    )
