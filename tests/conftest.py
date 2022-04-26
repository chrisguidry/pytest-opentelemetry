import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

pytest_plugins = ["pytester"]


@pytest.fixture(scope='session')
def span_processor():
    provider = trace.get_tracer_provider()
    span_processor = SimpleSpanProcessor(InMemorySpanExporter())
    provider.add_span_processor(span_processor)
    return span_processor


@pytest.fixture(scope='function')
def span_recorder(span_processor):
    span_processor.span_exporter = InMemorySpanExporter()
    return span_processor.span_exporter
