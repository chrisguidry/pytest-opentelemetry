from _pytest.pytester import Pytester
from opentelemetry.trace import StatusCode

from . import SpanRecorder, end_time, parent_id, span_id, start_time


def test_collection_is_a_child_of_the_test_run(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    pytester.makepyfile("""
        def test_one():
            assert 1 + 2 == 3
    """)
    pytester.runpytest().assert_outcomes(passed=1)

    spans = span_recorder.spans_by_name()
    collection = spans["collection"]
    test_run = spans["test run"]
    test = spans["test_collection_is_a_child_of_the_test_run.py::test_one"]

    assert parent_id(collection) == span_id(test_run)
    assert collection.attributes
    assert collection.attributes["pytest.span_type"] == "collection"
    assert end_time(collection) <= start_time(test)


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
    assert parent_id(spans["importing"]) == span_id(spans["collection"])


def test_collection_errors_are_recorded(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    pytester.makepyfile("""
        raise ValueError('woops')
    """)
    pytester.runpytest().assert_outcomes(errors=1)

    collection = span_recorder.spans_by_name()["collection"]
    assert collection.status.status_code == StatusCode.ERROR
    assert [event.name for event in collection.events] == ["exception"]


def test_xdist_controller_has_no_collection_span(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    pytester.makepyfile("""
        def test_one():
            assert 1 + 2 == 3
    """)
    pytester.runpytest("-n", "1").assert_outcomes(passed=1)

    spans = span_recorder.spans_by_name()
    assert "test run" in spans
    assert "collection" not in spans


def test_trace_per_test_has_no_collection_span(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    pytester.makepyfile("""
        def test_one():
            assert 1 + 2 == 3
    """)
    pytester.runpytest("--trace-per-test").assert_outcomes(passed=1)

    spans = span_recorder.spans_by_name()
    assert "test_trace_per_test_has_no_collection_span.py::test_one" in spans
    assert "collection" not in spans
