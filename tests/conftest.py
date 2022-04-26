import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

pytest_plugins = ["pytester"]


@pytest.fixture(scope='session', autouse=True)
def provider():
    provider = TracerProvider()
    trace.set_tracer_provider(provider)
    return provider


@pytest.fixture()
def span_recorder(provider):
    span_recorder = InMemorySpanExporter()

    # pylint: disable=protected-access
    provider._active_span_processor = SimpleSpanProcessor(span_recorder)
    # pylint: enable=protected-access

    return span_recorder
