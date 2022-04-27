from typing import Dict, Sequence, cast

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


class SpanRecorder(InMemorySpanExporter):
    """An OpenTelemetry span exporter that remembers all of the Spans it has seen,
    and provides utility methods to inspect them during tests."""

    def finished_spans(self) -> Sequence[ReadableSpan]:
        """Returns read-only versions of all of the remembered Spans"""
        return cast(Sequence[ReadableSpan], super().get_finished_spans())

    def spans_by_name(self) -> Dict[str, ReadableSpan]:
        """Returns a dictionary of remembered spans keyed by their names"""
        return {s.name: s for s in self.finished_spans()}
