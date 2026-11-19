from collections.abc import Sequence
from typing import cast

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


class SpanRecorder(InMemorySpanExporter):
    """An OpenTelemetry span exporter that remembers all of the Spans it has seen,
    and provides utility methods to inspect them during tests."""

    def finished_spans(self) -> Sequence[ReadableSpan]:
        """Returns read-only versions of all of the remembered Spans"""
        return cast(Sequence[ReadableSpan], super().get_finished_spans())

    def spans_by_name(self) -> dict[str, ReadableSpan]:
        """Returns a dictionary of remembered spans keyed by their names"""
        return {s.name: s for s in self.finished_spans()}


def span_id(span: ReadableSpan) -> int:
    assert span.context
    return span.context.span_id


def trace_id(span: ReadableSpan) -> int:
    assert span.context
    return span.context.trace_id


def parent_id(span: ReadableSpan) -> int:
    assert span.parent
    return span.parent.span_id


def start_time(span: ReadableSpan) -> int:
    assert span.start_time
    return span.start_time


def end_time(span: ReadableSpan) -> int:
    assert span.end_time
    return span.end_time
