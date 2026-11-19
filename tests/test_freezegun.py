import sys

import pytest
from _pytest.pytester import Pytester

from pytest_opentelemetry.instrumentation import use_real_time_under_freezegun

from . import SpanRecorder


def test_spans_keep_real_time_while_time_is_frozen(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    pytester.makepyfile("""
        import datetime

        import pytest
        from freezegun import freeze_time
        from opentelemetry import trace

        @pytest.fixture
        def frozen():
            with freeze_time('2012-01-14'):
                yield

        def test_one(frozen):
            with trace.get_tracer('inside').start_as_current_span('inside'):
                assert datetime.date.today() == datetime.date(2012, 1, 14)
    """)
    pytester.runpytest().assert_outcomes(passed=1)

    spans = span_recorder.spans_by_name()
    test = spans['test_spans_keep_real_time_while_time_is_frozen.py::test_one']
    within_test = [
        spans['frozen setup'],
        spans['test_spans_keep_real_time_while_time_is_frozen.py::test_one::call'],
        spans['inside'],
        spans['frozen teardown'],
    ]
    assert all(
        test.start_time <= span.start_time <= span.end_time <= test.end_time
        for span in within_test
    )


def test_freezegun_is_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, 'freezegun', None)
    use_real_time_under_freezegun()
