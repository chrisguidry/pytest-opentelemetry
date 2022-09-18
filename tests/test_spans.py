from _pytest.pytester import Pytester
from opentelemetry.trace import SpanKind

from . import SpanRecorder


def test_simple_pytest_functions(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    pytester.makepyfile(
        """
        def test_one():
            assert 1 + 2 == 3

        def test_two():
            assert 2 + 2 == 4
    """
    )
    pytester.runpytest().assert_outcomes(passed=2)

    spans = span_recorder.spans_by_name()
    assert len(spans) == 2 + 1

    span = spans['test run']
    assert span.status.is_ok
    assert span.attributes
    assert span.attributes["pytest.span_type"] == "run"

    span = spans['test_one']
    assert span.kind == SpanKind.INTERNAL
    assert span.status.is_ok
    assert span.attributes
    assert span.attributes['code.function'] == 'test_one'
    assert span.attributes['code.filepath'] == 'test_simple_pytest_functions.py'
    assert 'code.lineno' not in span.attributes
    assert span.attributes["pytest.span_type"] == "test"
    assert (
        span.attributes["pytest.nodeid"] == "test_simple_pytest_functions.py::test_one"
    )

    span = spans['test_two']
    assert span.kind == SpanKind.INTERNAL
    assert span.status.is_ok
    assert span.attributes
    assert span.attributes['code.function'] == 'test_two'
    assert span.attributes['code.filepath'] == 'test_simple_pytest_functions.py'
    assert span.attributes['code.lineno'] == 3
    assert span.attributes["pytest.span_type"] == "test"
    assert (
        span.attributes["pytest.nodeid"] == "test_simple_pytest_functions.py::test_two"
    )


def test_failures_and_errors(pytester: Pytester, span_recorder: SpanRecorder) -> None:
    pytester.makepyfile(
        """
        def test_one():
            assert 1 + 2 == 3

        def test_two():
            assert 2 + 2 == 5

        def test_three():
            raise ValueError('woops')
    """
    )
    result = pytester.runpytest()
    result.assert_outcomes(passed=1, failed=2)

    spans = span_recorder.spans_by_name()
    assert len(spans) == 3 + 1

    span = spans['test run']
    assert not span.status.is_ok

    span = spans['test_one']
    assert span.status.is_ok

    span = spans['test_two']
    assert not span.status.is_ok
    assert span.attributes
    assert span.attributes['code.function'] == 'test_two'
    assert span.attributes['code.filepath'] == 'test_failures_and_errors.py'
    assert span.attributes['code.lineno'] == 3
    assert 'exception.stacktrace' not in span.attributes
    assert len(span.events) == 1
    event = span.events[0]
    assert event.attributes
    assert event.attributes['exception.type'] == 'AssertionError'

    span = spans['test_three']
    assert not span.status.is_ok
    assert span.attributes
    assert span.attributes['code.function'] == 'test_three'
    assert span.attributes['code.filepath'] == 'test_failures_and_errors.py'
    assert span.attributes['code.lineno'] == 6
    assert 'exception.stacktrace' not in span.attributes
    assert len(span.events) == 1
    event = span.events[0]
    assert event.attributes
    assert event.attributes['exception.type'] == 'ValueError'
    assert event.attributes['exception.message'] == 'woops'


def test_failures_in_fixtures(pytester: Pytester, span_recorder: SpanRecorder) -> None:
    pytester.makepyfile(
        """
        import pytest

        @pytest.fixture
        def borked_fixture():
            raise ValueError('newp')

        def test_one():
            assert 1 + 2 == 3

        def test_two(borked_fixture):
            assert 2 + 2 == 5

        def test_three(borked_fixture):
            assert 2 + 2 == 4

        def test_four():
            assert 2 + 2 == 5
    """
    )
    result = pytester.runpytest()
    result.assert_outcomes(passed=1, failed=1, errors=2)

    spans = span_recorder.spans_by_name()
    assert len(spans) == 4 + 1

    assert 'test run' in spans

    span = spans['test_one']
    assert span.status.is_ok

    span = spans['test_two']
    assert not span.status.is_ok

    span = spans['test_three']
    assert not span.status.is_ok

    span = spans['test_four']
    assert not span.status.is_ok


def test_parametrized_tests(pytester: Pytester, span_recorder: SpanRecorder) -> None:
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.parametrize('hello', ['world', 'people'])
        def test_one(hello):
            assert 1 + 2 == 3

        def test_two():
            assert 2 + 2 == 4
    """
    )
    pytester.runpytest().assert_outcomes(passed=3)

    spans = span_recorder.spans_by_name()
    assert len(spans) == 3 + 1

    assert 'test run' in spans

    span = spans['test_one[world]']
    assert span.status.is_ok
    assert span.attributes
    assert (
        span.attributes["pytest.nodeid"]
        == "test_parametrized_tests.py::test_one[world]"
    )

    span = spans['test_one[people]']
    assert span.status.is_ok
    assert span.attributes
    assert (
        span.attributes["pytest.nodeid"]
        == "test_parametrized_tests.py::test_one[people]"
    )

    span = spans['test_two']
    assert span.status.is_ok
    assert span.attributes
    assert span.attributes["pytest.nodeid"] == "test_parametrized_tests.py::test_two"


def test_class_tests(pytester: Pytester, span_recorder: SpanRecorder) -> None:
    pytester.makepyfile(
        """
        class TestThings:
            def test_one(self):
                assert 1 + 2 == 3

            def test_two(self):
                assert 2 + 2 == 4
    """
    )
    pytester.runpytest().assert_outcomes(passed=2)

    spans = span_recorder.spans_by_name()
    assert len(spans) == 2 + 1

    assert 'test run' in spans

    span = spans['test_one']
    assert span.status.is_ok
    assert span.attributes
    assert (
        span.attributes["pytest.nodeid"] == "test_class_tests.py::TestThings::test_one"
    )

    span = spans['test_two']
    assert span.status.is_ok
    assert span.attributes
    assert (
        span.attributes["pytest.nodeid"] == "test_class_tests.py::TestThings::test_two"
    )


def test_test_spans_are_children_of_sessions(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    pytester.makepyfile(
        """
        def test_one():
            assert 1 + 2 == 3
    """
    )
    pytester.runpytest().assert_outcomes(passed=1)

    spans = span_recorder.spans_by_name()
    assert len(spans) == 2

    test_run = spans['test run']
    test = spans['test_one']

    assert test_run.context.trace_id
    assert test.context.trace_id == test_run.context.trace_id

    assert test.parent
    assert test.parent.span_id == test_run.context.span_id


def test_spans_within_tests_are_children_of_test_spans(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    pytester.makepyfile(
        """
        from opentelemetry import trace

        tracer = trace.get_tracer('inside')

        def test_one():
            with tracer.start_as_current_span('inner'):
                assert 1 + 2 == 3
    """
    )
    pytester.runpytest().assert_outcomes(passed=1)

    spans = span_recorder.spans_by_name()
    assert len(spans) == 3

    test_run = spans['test run']
    test = spans['test_one']
    inner = spans['inner']

    assert test_run.context.trace_id
    assert test.context.trace_id == test_run.context.trace_id
    assert inner.context.trace_id == test.context.trace_id

    assert test.parent
    assert test.parent.span_id == test_run.context.span_id

    assert inner.parent
    assert inner.parent.span_id == test.context.span_id
