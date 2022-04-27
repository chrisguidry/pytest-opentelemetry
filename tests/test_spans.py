from opentelemetry.trace import SpanKind


def test_simple_pytest_functions(testdir, span_recorder):
    testdir.makepyfile(
        """
        def test_one():
            assert 1 + 2 == 3

        def test_two():
            assert 2 + 2 == 4
    """
    )
    testdir.runpytest().assert_outcomes(passed=2)

    spans = {s.name: s for s in span_recorder.get_finished_spans()}
    assert len(spans) == 2 + 1

    assert 'test session' in spans

    key = 'test_simple_pytest_functions.py::test_one'
    assert key in spans
    assert spans[key].kind == SpanKind.INTERNAL
    assert spans[key].status.is_ok
    assert spans[key].attributes['code.function'] == 'test_one'
    assert spans[key].attributes['code.filepath'] == 'test_simple_pytest_functions.py'
    assert spans[key].attributes['code.lineno'] == '0'

    key = 'test_simple_pytest_functions.py::test_two'
    assert key in spans
    assert spans[key].kind == SpanKind.INTERNAL
    assert spans[key].status.is_ok
    assert spans[key].attributes['code.function'] == 'test_two'
    assert spans[key].attributes['code.filepath'] == 'test_simple_pytest_functions.py'
    assert spans[key].attributes['code.lineno'] == '3'


def test_failures_and_errors(testdir, span_recorder):
    testdir.makepyfile(
        """
        def test_one():
            assert 1 + 2 == 3

        def test_two():
            assert 2 + 2 == 5

        def test_three():
            raise ValueError('woops')
    """
    )
    result = testdir.runpytest()
    result.assert_outcomes(passed=1, failed=2)

    spans = {s.name: s for s in span_recorder.get_finished_spans()}
    assert len(spans) == 3 + 1

    assert 'test session' in spans

    key = 'test_failures_and_errors.py::test_one'
    assert key in spans
    assert spans[key].status.is_ok

    key = 'test_failures_and_errors.py::test_two'
    assert key in spans
    assert not spans[key].status.is_ok
    assert spans[key].attributes['code.function'] == 'test_two'
    assert spans[key].attributes['code.filepath'] == 'test_failures_and_errors.py'
    assert spans[key].attributes['code.lineno'] == '3'
    assert 'exception.stacktrace' not in spans[key].attributes
    assert len(spans[key].events) == 1
    assert spans[key].events[0].attributes['exception.type'] == 'AssertionError'

    key = 'test_failures_and_errors.py::test_three'
    assert key in spans
    assert not spans[key].status.is_ok
    assert spans[key].attributes['code.function'] == 'test_three'
    assert spans[key].attributes['code.filepath'] == 'test_failures_and_errors.py'
    assert spans[key].attributes['code.lineno'] == '6'
    assert 'exception.stacktrace' not in spans[key].attributes
    assert len(spans[key].events) == 1
    assert spans[key].events[0].attributes['exception.type'] == 'ValueError'
    assert spans[key].events[0].attributes['exception.message'] == 'woops'


def test_failures_in_fixtures(testdir, span_recorder):
    testdir.makepyfile(
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
    result = testdir.runpytest()
    result.assert_outcomes(passed=1, failed=1, errors=2)

    spans = {s.name: s for s in span_recorder.get_finished_spans()}
    assert len(spans) == 4 + 1

    assert 'test session' in spans

    key = 'test_failures_in_fixtures.py::test_one'
    assert spans[key].status.is_ok

    key = 'test_failures_in_fixtures.py::test_two'
    assert not spans[key].status.is_ok

    key = 'test_failures_in_fixtures.py::test_three'
    assert not spans[key].status.is_ok

    key = 'test_failures_in_fixtures.py::test_four'
    assert not spans[key].status.is_ok


def test_parametrized_tests(testdir, span_recorder):
    testdir.makepyfile(
        """
        import pytest

        @pytest.mark.parametrize('hello', ['world', 'people'])
        def test_one(hello):
            assert 1 + 2 == 3

        def test_two():
            assert 2 + 2 == 4
    """
    )
    testdir.runpytest().assert_outcomes(passed=3)

    spans = {s.name: s for s in span_recorder.get_finished_spans()}
    assert len(spans) == 3 + 1

    assert 'test session' in spans

    key = 'test_parametrized_tests.py::test_one[world]'
    assert key in spans
    assert spans[key].status.is_ok

    key = 'test_parametrized_tests.py::test_one[people]'
    assert key in spans
    assert spans[key].status.is_ok

    key = 'test_parametrized_tests.py::test_two'
    assert key in spans
    assert spans[key].status.is_ok


def test_class_tests(testdir, span_recorder):
    testdir.makepyfile(
        """
        class TestThings:
            def test_one(self):
                assert 1 + 2 == 3

            def test_two(self):
                assert 2 + 2 == 4
    """
    )
    testdir.runpytest().assert_outcomes(passed=2)

    spans = {s.name: s for s in span_recorder.get_finished_spans()}
    assert len(spans) == 2 + 1

    assert 'test session' in spans

    key = 'test_class_tests.py::TestThings::test_one'
    assert key in spans
    assert spans[key].status.is_ok

    key = 'test_class_tests.py::TestThings::test_two'
    assert key in spans
    assert spans[key].status.is_ok


def test_test_spans_are_children_of_sessions(testdir, span_recorder):
    testdir.makepyfile(
        """
        def test_one():
            assert 1 + 2 == 3
    """
    )
    testdir.runpytest().assert_outcomes(passed=1)

    spans = {s.name: s for s in span_recorder.get_finished_spans()}
    assert len(spans) == 2

    session = spans['test session']
    test = spans['test_test_spans_are_children_of_sessions.py::test_one']

    assert test.context.trace_id == session.context.trace_id
    assert test.parent.span_id == session.context.span_id


def test_spans_within_tests_are_children_of_test_spans(testdir, span_recorder):
    testdir.makepyfile(
        """
        from opentelemetry import trace

        tracer = trace.get_tracer('inside')

        def test_one():
            with tracer.start_as_current_span('inner'):
                assert 1 + 2 == 3
    """
    )
    testdir.runpytest().assert_outcomes(passed=1)

    spans = {s.name: s for s in span_recorder.get_finished_spans()}
    assert len(spans) == 3

    session = spans['test session']
    test = spans['test_spans_within_tests_are_children_of_test_spans.py::test_one']
    inner = spans['inner']

    assert test.context.trace_id == session.context.trace_id
    assert test.parent.span_id == session.context.span_id

    assert inner.context.trace_id == test.context.trace_id
    assert inner.parent.span_id == test.context.span_id
