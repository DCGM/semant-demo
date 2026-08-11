import logging
import os

from opentelemetry import _logs
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource

from semant_demo.config import config


def setup_logging_export() -> None:
    """Attach an OTLP log handler to the root logger, so every existing `logging.*` call is also shipped to the collector."""
    if not config.OTEL_ENABLED:
        return

    resource = Resource.create({
        "service.name": config.OTEL_SERVICE_NAME,
        "service.version": "0.1.0",
        "deployment.environment": config.DEPLOYMENT_ENVIRONMENT,
        "service.instance.id": os.getenv("HOSTNAME", "unknown"),
    })

    logger_provider = LoggerProvider(resource=resource)
    exporter = OTLPLogExporter(endpoint=f"{config.OTEL_EXPORTER_OTLP_ENDPOINT}/v1/logs")
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
    _logs.set_logger_provider(logger_provider)

    handler = LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)
    logging.getLogger().addHandler(handler)
