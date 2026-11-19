from _pytest.pytester import Pytester
from opentelemetry.trace import StatusCode

from . import SpanRecorder


def test_collection_is_a_child_of_the_test_run(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    pytester.makepyfile("""
        def test_one():
            assert 1 + 2 == 3
    """)
    pytester.runpytest().assert_outcomes(passed=1)

    spans = span_recorder.spans_by_name()
    collection = spans['collection']
    test_run = spans['test run']
    test = spans['test_collection_is_a_child_of_the_test_run.py::test_one']

    assert collection.parent.span_id == test_run.context.span_id
    assert collection.attributes
    assert collection.attributes['pytest.span_type'] == 'collection'
    assert collection.end_time <= test.start_time


def test_spans_from_importing_test_modules_are_children_of_collection(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    pytester.makepyfile("""
        from opentelemetry import trace

        with trace.get_tracer('inside').start_as_current_span('importing'):
            pass

        def test_one():
            assert 1 + 2 == 3
    """)
    pytester.runpytest().assert_outcomes(passed=1)

    spans = span_recorder.spans_by_name()
    assert spans['importing'].parent.span_id == spans['collection'].context.span_id


def test_collection_errors_are_recorded(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    pytester.makepyfile("""
        raise ValueError('woops')
    """)
    pytester.runpytest().assert_outcomes(errors=1)

    collection = span_recorder.spans_by_name()['collection']
    assert collection.status.status_code == StatusCode.ERROR
    assert [event.name for event in collection.events] == ['exception']


def test_xdist_controller_has_no_collection_span(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    pytester.makepyfile("""
        def test_one():
            assert 1 + 2 == 3
    """)
    pytester.runpytest('-n', '1').assert_outcomes(passed=1)

    spans = span_recorder.spans_by_name()
    assert 'test run' in spans
    assert 'collection' not in spans


def test_trace_per_test_has_no_collection_span(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    pytester.makepyfile("""
        def test_one():
            assert 1 + 2 == 3
    """)
    pytester.runpytest('--trace-per-test').assert_outcomes(passed=1)

    spans = span_recorder.spans_by_name()
    assert 'test_trace_per_test_has_no_collection_span.py::test_one' in spans
    assert 'collection' not in spans
