"""OpenTelemetry log export for the first observability phase."""

from __future__ import annotations

import logging
import socket
from dataclasses import dataclass
from urllib.parse import urljoin

from opentelemetry import _logs
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource

from semant_demo.config import config


@dataclass
class LogTelemetry:
    """Objects that need to be flushed when the application stops."""

    log_provider: LoggerProvider
    logging_handler: LoggingHandler

    def shutdown(self) -> None:
        logging.getLogger().removeHandler(self.logging_handler)
        self.log_provider.shutdown()


def setup_logging_export() -> LogTelemetry | None:
    """Forward standard Python log records to the OTLP/HTTP collector."""
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
        level={
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
        }[config.LOG_LEVEL],
        logger_provider=log_provider,
    )
    logging.getLogger().addHandler(logging_handler)

    logging.getLogger(__name__).info(
        "OpenTelemetry log export enabled",
        extra={
            "otel.exporter.endpoint": config.OTEL_EXPORTER_OTLP_ENDPOINT,
            "deployment.environment.name": config.DEPLOYMENT_ENVIRONMENT,
        },
    )
    return LogTelemetry(log_provider, logging_handler)
