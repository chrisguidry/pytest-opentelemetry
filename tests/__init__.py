from typing import Dict, Sequence, cast

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


class SpanRecorder(InMemorySpanExporter):
    def get_finished_spans(self) -> Sequence[ReadableSpan]:
        return cast(Sequence[ReadableSpan], super().get_finished_spans())

    def spans_by_name(self) -> Dict[str, ReadableSpan]:
        return {s.name: s for s in self.get_finished_spans()}
