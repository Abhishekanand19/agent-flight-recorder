"""OpenTelemetry setup: one provider each for traces and logs, both
exporting to local SigNoz over OTLP.

Logs go through Python's stdlib logging via the OTel LoggingHandler, which
automatically stamps each record with the active span's trace_id and
span_id — so a log emitted inside any span is correlated to that trace in
SigNoz with no manual plumbing. Use get_logger(component) for a structured
logger and pass structured fields via `extra=`:

    log = get_logger("agent")
    log.info("refund requested", extra={"event": "tool.invoked", "tool.name": "issue_refund"})
"""

import logging
import os

from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# All flight-recorder loggers hang off this root, which owns the single OTel
# handler; component loggers (flight_recorder.agent, ...) propagate to it.
LOGGER_ROOT = "flight_recorder"

_initialized = False
_logger_provider: LoggerProvider | None = None


def init_telemetry(service_name: str = "support-agent") -> None:
    """Set up the global tracer and logger providers. Safe to call twice."""
    global _initialized, _logger_provider
    if _initialized:
        return
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    resource = Resource.create({"service.name": service_name})

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True)))
    trace.set_tracer_provider(tracer_provider)

    _logger_provider = LoggerProvider(resource=resource)
    _logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint, insecure=True))
    )
    set_logger_provider(_logger_provider)

    handler = LoggingHandler(level=logging.INFO, logger_provider=_logger_provider)
    root = logging.getLogger(LOGGER_ROOT)
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(handler)
    root.propagate = False  # keep flight-recorder logs off the app's root logger

    _initialized = True


def get_tracer() -> trace.Tracer:
    return trace.get_tracer("agent-flight-recorder")


def get_logger(component: str = "") -> logging.Logger:
    """Structured logger that exports to SigNoz and auto-correlates with the
    active span when the record is emitted inside one."""
    name = f"{LOGGER_ROOT}.{component}" if component else LOGGER_ROOT
    return logging.getLogger(name)


def shutdown_telemetry() -> None:
    """Flush pending spans and logs before the process exits."""
    provider = trace.get_tracer_provider()
    if isinstance(provider, TracerProvider):
        provider.shutdown()
    if _logger_provider is not None:
        _logger_provider.shutdown()
