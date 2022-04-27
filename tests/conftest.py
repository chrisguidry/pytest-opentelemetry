import pytest
from opentelemetry import trace
from opentelemetry.sdk import trace as trace_sdk
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from . import SpanRecorder

pytest_plugins = ["pytester"]


@pytest.fixture(scope='session')
def tracer_provider() -> trace_sdk.TracerProvider:
    provider = trace.get_tracer_provider()
    assert isinstance(provider, trace_sdk.TracerProvider)
    return provider


@pytest.fixture(scope='session')
def span_processor(tracer_provider: trace_sdk.TracerProvider) -> SimpleSpanProcessor:
    span_processor = SimpleSpanProcessor(SpanRecorder())
    tracer_provider.add_span_processor(span_processor)
    return span_processor


@pytest.fixture(scope='function')
def span_recorder(span_processor: SimpleSpanProcessor) -> SpanRecorder:
    span_processor.span_exporter = SpanRecorder()
    return span_processor.span_exporter
