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
    assert len(spans) == 2

    key = 'test_simple_pytest_functions.py::test_one'
    assert key in spans
    assert spans[key].kind == SpanKind.INTERNAL
    assert spans[key].status.is_ok

    key = 'test_simple_pytest_functions.py::test_two'
    assert key in spans
    assert spans[key].kind == SpanKind.INTERNAL
    assert spans[key].status.is_ok


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
    assert len(spans) == 3

    key = 'test_failures_and_errors.py::test_one'
    assert key in spans
    assert spans[key].kind == SpanKind.INTERNAL
    assert spans[key].status.is_ok

    key = 'test_failures_and_errors.py::test_two'
    assert key in spans
    assert spans[key].kind == SpanKind.INTERNAL
    assert not spans[key].status.is_ok

    key = 'test_failures_and_errors.py::test_three'
    assert key in spans
    assert spans[key].kind == SpanKind.INTERNAL
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
    assert len(spans) == 3

    key = 'test_parametrized_tests.py::test_one[world]'
    assert key in spans
    assert spans[key].kind == SpanKind.INTERNAL
    assert spans[key].status.is_ok

    key = 'test_parametrized_tests.py::test_one[people]'
    assert key in spans
    assert spans[key].kind == SpanKind.INTERNAL
    assert spans[key].status.is_ok

    key = 'test_parametrized_tests.py::test_two'
    assert key in spans
    assert spans[key].kind == SpanKind.INTERNAL
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
    assert len(spans) == 2

    key = 'test_class_tests.py::TestThings::test_one'
    assert key in spans
    assert spans[key].kind == SpanKind.INTERNAL
    assert spans[key].status.is_ok

    key = 'test_class_tests.py::TestThings::test_two'
    assert key in spans
    assert spans[key].kind == SpanKind.INTERNAL
    assert spans[key].status.is_ok
