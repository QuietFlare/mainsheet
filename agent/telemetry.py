"""Configure tracing: one tracer for the process, spans exported over OTLP."""
import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:6006/v1/traces")

_provider: TracerProvider | None = None


def tracer(service: str = "mainsheet") -> trace.Tracer:
    global _provider
    _provider = TracerProvider(resource=Resource.create({"service.name": service}))
    _provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=ENDPOINT)))
    trace.set_tracer_provider(_provider)
    return trace.get_tracer(service)


def shutdown() -> None:
    """Flush pending spans. Call once, on the way out, including on failure."""
    if _provider is not None:
        _provider.shutdown()