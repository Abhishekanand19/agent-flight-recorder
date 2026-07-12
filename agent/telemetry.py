"""OpenTelemetry setup: one tracer provider exporting to local SigNoz."""

import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_initialized = False


def init_telemetry(service_name: str = "support-agent") -> None:
    """Set up the global tracer provider. Safe to call more than once."""
    global _initialized
    if _initialized:
        return
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True)))
    trace.set_tracer_provider(provider)
    _initialized = True


def get_tracer() -> trace.Tracer:
    return trace.get_tracer("agent-flight-recorder")


def shutdown_telemetry() -> None:
    """Flush pending spans before the process exits."""
    provider = trace.get_tracer_provider()
    if isinstance(provider, TracerProvider):
        provider.shutdown()
