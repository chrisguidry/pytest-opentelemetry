import sys
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from _pytest.pytester import Pytester
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter as GRPCSpanExporter,
)
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter as HTTPSpanExporter,
)
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SpanExporter

from pytest_opentelemetry.provider import build_tracer_provider, span_exporters


@pytest.fixture(autouse=True)
def no_opentelemetry_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "OTEL_TRACES_EXPORTER",
        "OTEL_EXPORTER_OTLP_PROTOCOL",
        "OTEL_EXPORTER_OTLP_TRACES_PROTOCOL",
        "OTEL_SERVICE_NAME",
        "OTEL_RESOURCE_ATTRIBUTES",
    ):
        monkeypatch.delenv(name, raising=False)


def test_resource_describes_the_codebase(pytester: Pytester) -> None:
    provider = build_tracer_provider(pytester.parseconfig())

    attributes = provider.resource.attributes
    assert attributes["service.version"] == "[unknown: not a git repository]"


def test_resource_prefers_the_standard_environment_variables(
    pytester: Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OTEL_SERVICE_NAME", "my-service")
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "deployment.environment=ci")

    provider = build_tracer_provider(pytester.parseconfig())

    attributes = provider.resource.attributes
    assert attributes["service.name"] == "my-service"
    assert attributes["deployment.environment"] == "ci"


def test_resource_includes_the_container_distro_when_installed(
    pytester: Pytester,
) -> None:
    provider = build_tracer_provider(pytester.parseconfig())

    assert "process.pid" in provider.resource.attributes


def test_resource_without_the_container_distro(
    pytester: Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "opentelemetry_container_distro", None)

    provider = build_tracer_provider(pytester.parseconfig())

    attributes = provider.resource.attributes
    assert attributes["service.version"] == "[unknown: not a git repository]"
    assert "process.pid" not in attributes


@pytest.fixture
def collector(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """An OTLP over HTTP endpoint that records the path of each request, with
    the environment set to export to it."""
    paths: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            paths.append(self.path)
            self.send_response(200)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()

    monkeypatch.setenv("OTEL_TRACES_EXPORTER", "otlp_proto_http")
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT", f"http://127.0.0.1:{server.server_port}"
    )
    try:
        yield paths
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_spans_are_not_exported_by_default(
    pytester: Pytester, collector: list[str]
) -> None:
    provider = build_tracer_provider(pytester.parseconfig())
    provider.get_tracer("test").start_span("example").end()
    provider.shutdown()

    assert collector == []


def test_spans_are_exported_with_export_traces(
    pytester: Pytester, collector: list[str]
) -> None:
    provider = build_tracer_provider(pytester.parseconfig("--export-traces"))
    provider.get_tracer("test").start_span("example").end()
    provider.shutdown()

    assert collector == ["/v1/traces"]


@pytest.mark.parametrize(
    "environment, expected",
    [
        pytest.param({}, [GRPCSpanExporter], id="default"),
        pytest.param(
            {"OTEL_TRACES_EXPORTER": "otlp_proto_http"},
            [HTTPSpanExporter],
            id="http-by-name",
        ),
        pytest.param({"OTEL_TRACES_EXPORTER": "otlp"}, [GRPCSpanExporter], id="otlp"),
        pytest.param(
            {
                "OTEL_TRACES_EXPORTER": "otlp",
                "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
            },
            [HTTPSpanExporter],
            id="otlp-http-protocol",
        ),
        pytest.param(
            {
                "OTEL_TRACES_EXPORTER": "otlp",
                "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
                "OTEL_EXPORTER_OTLP_TRACES_PROTOCOL": "grpc",
            },
            [GRPCSpanExporter],
            id="otlp-traces-protocol",
        ),
        pytest.param(
            {"OTEL_TRACES_EXPORTER": "console, otlp_proto_grpc"},
            [ConsoleSpanExporter, GRPCSpanExporter],
            id="several",
        ),
        pytest.param({"OTEL_TRACES_EXPORTER": "none"}, [], id="none"),
    ],
)
def test_span_exporters_come_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
    environment: dict[str, str],
    expected: list[type[SpanExporter]],
) -> None:
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    assert [type(exporter) for exporter in span_exporters()] == expected


@pytest.mark.parametrize(
    "environment, message",
    [
        pytest.param(
            {"OTEL_TRACES_EXPORTER": "carrier_pigeon"},
            "carrier_pigeon",
            id="unknown-exporter",
        ),
        pytest.param(
            {
                "OTEL_TRACES_EXPORTER": "otlp",
                "OTEL_EXPORTER_OTLP_PROTOCOL": "smoke-signals",
            },
            "smoke-signals",
            id="unknown-protocol",
        ),
    ],
)
def test_span_exporters_that_are_not_installed(
    monkeypatch: pytest.MonkeyPatch, environment: dict[str, str], message: str
) -> None:
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    with pytest.raises(pytest.UsageError, match=message):
        span_exporters()
