import os
from importlib.metadata import entry_points

import pytest
from opentelemetry.environment_variables import OTEL_TRACES_EXPORTER
from opentelemetry.sdk.environment_variables import (
    OTEL_EXPORTER_OTLP_PROTOCOL,
    OTEL_EXPORTER_OTLP_TRACES_PROTOCOL,
)
from opentelemetry.sdk.resources import (
    OTELResourceDetector,
    ResourceDetector,
    get_aggregated_resources,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter

from .resource import CodebaseResourceDetector

# The names that OTEL_TRACES_EXPORTER uses for the OTLP exporter of each
# protocol that OTEL_EXPORTER_OTLP_PROTOCOL can name.
OTLP_EXPORTERS = {
    "grpc": "otlp_proto_grpc",
    "http/protobuf": "otlp_proto_http",
}


def build_tracer_provider(config: pytest.Config) -> TracerProvider:
    """Builds the tracer provider for a test run.

    Its resource describes the codebase under test and, when
    opentelemetry-container-distro is installed, the process and container
    that the tests run in.  OTELResourceDetector is last, so OTEL_SERVICE_NAME
    and OTEL_RESOURCE_ATTRIBUTES override what the other detectors found.

    The provider exports spans only with --export-traces."""
    resource = get_aggregated_resources(
        [
            *container_resource_detectors(),
            CodebaseResourceDetector(config),
            OTELResourceDetector(),
        ]
    )
    provider = TracerProvider(resource=resource)

    if config.getoption("--export-traces"):
        for exporter in span_exporters():
            provider.add_span_processor(BatchSpanProcessor(exporter))

    return provider


def container_resource_detectors() -> list[ResourceDetector]:
    """Returns the resource detectors of opentelemetry-container-distro, or none
    when it is not installed."""
    try:
        from opentelemetry_container_distro import OpenTelemetryContainerConfigurator
    except ImportError:
        return []

    return list(OpenTelemetryContainerConfigurator().resource_detectors)


def span_exporters() -> list[SpanExporter]:
    """Creates the exporters that OTEL_TRACES_EXPORTER names, which is OTLP over
    gRPC when it is not set."""
    names = os.environ.get(OTEL_TRACES_EXPORTER, "otlp_proto_grpc")
    return [
        _load_span_exporter(name.strip())
        for name in names.split(",")
        if name.strip().lower() != "none"
    ]


def _load_span_exporter(name: str) -> SpanExporter:
    if name == "otlp":
        name = _otlp_exporter_name()

    found = entry_points(group="opentelemetry_traces_exporter", name=name)
    if not found:
        raise pytest.UsageError(
            f"OTEL_TRACES_EXPORTER names the span exporter {name!r}, which is not "
            "installed.  Install the package that provides it, or choose another "
            "exporter."
        )

    exporter_class: type[SpanExporter] = found[name].load()
    return exporter_class()


def _otlp_exporter_name() -> str:
    protocol = (
        os.environ.get(OTEL_EXPORTER_OTLP_TRACES_PROTOCOL)
        or os.environ.get(OTEL_EXPORTER_OTLP_PROTOCOL)
        or "grpc"
    )
    if protocol not in OTLP_EXPORTERS:
        raise pytest.UsageError(
            f"{protocol!r} is not an OTLP protocol that pytest-opentelemetry can "
            f"export with.  Use one of: {', '.join(OTLP_EXPORTERS)}."
        )
    return OTLP_EXPORTERS[protocol]
