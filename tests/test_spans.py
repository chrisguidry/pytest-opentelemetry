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
    # assert len(spans) == 2 + 1

    span = spans['test run']
    assert span.status.is_ok
    assert span.attributes
    assert span.attributes["pytest.span_type"] == "run"

    span = spans['test_simple_pytest_functions.py::test_one']
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

    span = spans['test_simple_pytest_functions.py::test_two']
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
        import pytest

        def test_one():
            assert 1 + 2 == 3

        def test_two():
            assert 2 + 2 == 5

        def test_three():
            raise ValueError('woops')

        def test_four():
            # Test did not raise case
            with pytest.raises(ValueError):
                pass
    """
    )
    result = pytester.runpytest()
    result.assert_outcomes(passed=1, failed=3)

    spans = span_recorder.spans_by_name()
    # assert len(spans) == 4 + 1

    span = spans['test run']
    assert not span.status.is_ok

    span = spans['test_failures_and_errors.py::test_one']
    assert span.status.is_ok

    span = spans['test_failures_and_errors.py::test_two']
    assert not span.status.is_ok
    assert span.attributes
    assert span.attributes['code.function'] == 'test_two'
    assert span.attributes['code.filepath'] == 'test_failures_and_errors.py'
    assert span.attributes['code.lineno'] == 5
    assert 'exception.stacktrace' not in span.attributes
    assert len(span.events) == 1
    event = span.events[0]
    assert event.attributes
    assert event.attributes['exception.type'] == 'AssertionError'

    span = spans['test_failures_and_errors.py::test_three']
    assert not span.status.is_ok
    assert span.attributes
    assert span.attributes['code.function'] == 'test_three'
    assert span.attributes['code.filepath'] == 'test_failures_and_errors.py'
    assert span.attributes['code.lineno'] == 8
    assert 'exception.stacktrace' not in span.attributes
    assert len(span.events) == 1
    event = span.events[0]
    assert event.attributes
    assert event.attributes['exception.type'] == 'ValueError'
    assert event.attributes['exception.message'] == 'woops'

    span = spans['test_failures_and_errors.py::test_four']
    assert not span.status.is_ok
    assert span.attributes
    assert span.attributes['code.function'] == 'test_four'
    assert span.attributes['code.filepath'] == 'test_failures_and_errors.py'
    assert span.attributes['code.lineno'] == 11
    assert 'exception.stacktrace' not in span.attributes
    assert len(span.events) == 1
    event = span.events[0]
    assert event.attributes
    assert event.attributes['exception.type'] == 'Failed'
    assert event.attributes['exception.message'] == "DID NOT RAISE <class 'ValueError'>"


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
    # assert len(spans) == 4 + 1

    assert 'test run' in spans

    span = spans['test_failures_in_fixtures.py::test_one']
    assert span.status.is_ok

    span = spans['test_failures_in_fixtures.py::test_two']
    assert not span.status.is_ok

    span = spans['test_failures_in_fixtures.py::test_three']
    assert not span.status.is_ok

    span = spans['test_failures_in_fixtures.py::test_four']
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
    # assert len(spans) == 3 + 1

    assert 'test run' in spans

    span = spans['test_parametrized_tests.py::test_one[world]']
    assert span.status.is_ok
    assert span.attributes
    assert (
        span.attributes["pytest.nodeid"]
        == "test_parametrized_tests.py::test_one[world]"
    )

    span = spans['test_parametrized_tests.py::test_one[people]']
    assert span.status.is_ok
    assert span.attributes
    assert (
        span.attributes["pytest.nodeid"]
        == "test_parametrized_tests.py::test_one[people]"
    )

    span = spans['test_parametrized_tests.py::test_two']
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
    # assert len(spans) == 2 + 1

    assert 'test run' in spans

    span = spans['test_class_tests.py::TestThings::test_one']
    assert span.status.is_ok
    assert span.attributes
    assert (
        span.attributes["pytest.nodeid"] == "test_class_tests.py::TestThings::test_one"
    )

    span = spans['test_class_tests.py::TestThings::test_two']
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
    # assert len(spans) == 2

    test_run = spans['test run']
    test = spans['test_test_spans_are_children_of_sessions.py::test_one']

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
    # assert len(spans) == 3

    test_run = spans['test run']
    test = spans['test_spans_within_tests_are_children_of_test_spans.py::test_one']
    inner = spans['inner']

    assert test_run.context.trace_id
    assert test.context.trace_id == test_run.context.trace_id
    assert inner.context.trace_id == test.context.trace_id

    assert test.parent
    assert test.parent.span_id == test_run.context.span_id

    assert inner.parent
    assert inner.parent.span_id == test.context.span_id


def test_spans_cover_setup_and_teardown(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    pytester.makepyfile(
        """
        import pytest
        from opentelemetry import trace

        tracer = trace.get_tracer('inside')

        @pytest.fixture
        def yielded() -> int:
            with tracer.start_as_current_span('before'):
                pass

            with tracer.start_as_current_span('yielding'):
                yield 1

            with tracer.start_as_current_span('after'):
                pass

        @pytest.fixture
        def returned() -> int:
            with tracer.start_as_current_span('returning'):
                return 2

        def test_one(yielded: int, returned: int):
            with tracer.start_as_current_span('during'):
                assert yielded + returned == 3
    """
    )
    pytester.runpytest().assert_outcomes(passed=1)

    spans = span_recorder.spans_by_name()

    test_run = spans['test run']
    assert test_run.context.trace_id
    assert all(
        span.context.trace_id == test_run.context.trace_id for span in spans.values()
    )

    test = spans['test_spans_cover_setup_and_teardown.py::test_one']

    setup = spans['setup']
    assert setup.parent.span_id == test.context.span_id

    assert spans['yielded'].parent.span_id == setup.context.span_id
    assert spans['returned'].parent.span_id == setup.context.span_id

    teardown = spans['teardown']
    assert teardown.parent.span_id == test.context.span_id


def test_spans_cover_fixtures_at_different_scopes(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    pytester.makepyfile(
        """
        import pytest
        from opentelemetry import trace

        tracer = trace.get_tracer('inside')

        @pytest.fixture(scope='session')
        def session_scoped() -> int:
            return 1

        @pytest.fixture(scope='module')
        def module_scoped() -> int:
            return 2

        @pytest.fixture(scope='function')
        def function_scoped() -> int:
            return 3

        def test_one(session_scoped: int, module_scoped: int, function_scoped: int):
            assert session_scoped + module_scoped + function_scoped == 6
    """
    )
    pytester.runpytest().assert_outcomes(passed=1)

    spans = span_recorder.spans_by_name()

    test_run = spans['test run']
    assert test_run.context.trace_id
    assert all(
        span.context.trace_id == test_run.context.trace_id for span in spans.values()
    )

    test = spans['test_spans_cover_fixtures_at_different_scopes.py::test_one']

    setup = spans['setup']
    assert setup.parent.span_id == test.context.span_id

    session_scoped = spans['session_scoped']
    module_scoped = spans['module_scoped']
    function_scoped = spans['function_scoped']

    assert session_scoped.parent.span_id == test_run.context.span_id
    assert module_scoped.parent.span_id == test_run.context.span_id
    assert function_scoped.parent.span_id == setup.context.span_id


def test_parametrized_fixture_names(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    pytester.makepyfile(
        """
        import pytest
        from opentelemetry import trace

        class Nope:
            def __str__(self):
                raise ValueError('nope')

        @pytest.fixture(params=[111, 222])
        def stringable(request) -> int:
            return request.param

        @pytest.fixture(params=[Nope(), Nope()])
        def unstringable(request) -> Nope:
            return request.param

        def test_one(stringable: int, unstringable: Nope):
            assert isinstance(stringable, int)
            assert isinstance(unstringable, Nope)
    """
    )
    pytester.runpytest().assert_outcomes(passed=4)

    spans = span_recorder.spans_by_name()

    test_run = spans['test run']
    assert test_run.context.trace_id
    assert all(
        span.context.trace_id == test_run.context.trace_id for span in spans.values()
    )

    # the stringable arguments are used in the span name
    assert 'stringable[111]' in spans
    assert 'stringable[222]' in spans

    # the indexes of non-stringable arguments are used in the span name
    assert 'unstringable[0]' in spans
    assert 'unstringable[1]' in spans
