import pytest
from _pytest.pytester import Pytester
from opentelemetry.trace import SpanKind

from . import SpanRecorder, parent_id, span_id, trace_id


def test_simple_pytest_functions(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    pytester.makepyfile("""
        def test_one():
            assert 1 + 2 == 3

        def test_two():
            assert 2 + 2 == 4
    """)
    pytester.runpytest().assert_outcomes(passed=2)

    spans = span_recorder.spans_by_name()
    # assert len(spans) == 2 + 1

    span = spans["test run"]
    assert span.status.is_ok
    assert span.attributes
    assert span.attributes["pytest.span_type"] == "run"

    span = spans["test_simple_pytest_functions.py::test_one"]
    assert span.kind == SpanKind.INTERNAL
    assert span.status.is_ok
    assert span.attributes
    assert span.attributes["code.function"] == "test_one"
    assert span.attributes["code.filepath"] == "test_simple_pytest_functions.py"
    assert "code.lineno" not in span.attributes
    assert span.attributes["pytest.span_type"] == "test"
    assert (
        span.attributes["pytest.nodeid"] == "test_simple_pytest_functions.py::test_one"
    )

    span = spans["test_simple_pytest_functions.py::test_two"]
    assert span.kind == SpanKind.INTERNAL
    assert span.status.is_ok
    assert span.attributes
    assert span.attributes["code.function"] == "test_two"
    assert span.attributes["code.filepath"] == "test_simple_pytest_functions.py"
    assert span.attributes["code.lineno"] == 3
    assert span.attributes["pytest.span_type"] == "test"
    assert (
        span.attributes["pytest.nodeid"] == "test_simple_pytest_functions.py::test_two"
    )


def test_failures_and_errors(pytester: Pytester, span_recorder: SpanRecorder) -> None:
    pytester.makepyfile("""
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
    """)
    result = pytester.runpytest()
    result.assert_outcomes(passed=1, failed=3)

    spans = span_recorder.spans_by_name()
    # assert len(spans) == 4 + 1

    span = spans["test run"]
    assert not span.status.is_ok

    span = spans["test_failures_and_errors.py::test_one"]
    assert span.status.is_ok

    span = spans["test_failures_and_errors.py::test_two"]
    assert not span.status.is_ok
    assert span.attributes
    assert span.attributes["code.function"] == "test_two"
    assert span.attributes["code.filepath"] == "test_failures_and_errors.py"
    assert span.attributes["code.lineno"] == 5
    assert "exception.stacktrace" not in span.attributes
    assert len(span.events) == 1
    event = span.events[0]
    assert event.attributes
    assert event.attributes["exception.type"] == "AssertionError"

    span = spans["test_failures_and_errors.py::test_three"]
    assert not span.status.is_ok
    assert span.attributes
    assert span.attributes["code.function"] == "test_three"
    assert span.attributes["code.filepath"] == "test_failures_and_errors.py"
    assert span.attributes["code.lineno"] == 8
    assert "exception.stacktrace" not in span.attributes
    assert len(span.events) == 1
    event = span.events[0]
    assert event.attributes
    assert event.attributes["exception.type"] == "ValueError"
    assert event.attributes["exception.message"] == "woops"

    span = spans["test_failures_and_errors.py::test_four"]
    assert not span.status.is_ok
    assert span.attributes
    assert span.attributes["code.function"] == "test_four"
    assert span.attributes["code.filepath"] == "test_failures_and_errors.py"
    assert span.attributes["code.lineno"] == 11
    assert "exception.stacktrace" not in span.attributes
    assert len(span.events) == 1
    event = span.events[0]
    assert event.attributes
    assert event.attributes["exception.type"] == "Failed"
    # pytest 9 says "DID NOT RAISE ValueError"; earlier pytests said
    # "DID NOT RAISE <class 'ValueError'>"
    message = str(event.attributes["exception.message"])
    assert message.startswith("DID NOT RAISE")
    assert "ValueError" in message


def test_failures_in_fixtures(pytester: Pytester, span_recorder: SpanRecorder) -> None:
    pytester.makepyfile("""
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
    """)
    result = pytester.runpytest()
    result.assert_outcomes(passed=1, failed=1, errors=2)

    spans = span_recorder.spans_by_name()
    # assert len(spans) == 4 + 1

    assert "test run" in spans

    span = spans["test_failures_in_fixtures.py::test_one"]
    assert span.status.is_ok

    span = spans["test_failures_in_fixtures.py::test_two"]
    assert not span.status.is_ok

    span = spans["test_failures_in_fixtures.py::test_three"]
    assert not span.status.is_ok

    span = spans["test_failures_in_fixtures.py::test_four"]
    assert not span.status.is_ok


def test_parametrized_tests(pytester: Pytester, span_recorder: SpanRecorder) -> None:
    pytester.makepyfile("""
        import pytest

        @pytest.mark.parametrize('hello', ['world', 'people'])
        def test_one(hello):
            assert 1 + 2 == 3

        def test_two():
            assert 2 + 2 == 4
    """)
    pytester.runpytest().assert_outcomes(passed=3)

    assert "test run" in span_recorder.spans_by_name()

    spans = span_recorder.spans_by_nodeid("test_parametrized_tests.py::test_one")
    assert set(spans) == {
        "test_parametrized_tests.py::test_one[world]",
        "test_parametrized_tests.py::test_one[people]",
    }
    assert all(span.status.is_ok for span in spans.values())

    span = span_recorder.spans_by_name()["test_parametrized_tests.py::test_two"]
    assert span.status.is_ok
    assert span.attributes
    assert span.attributes["pytest.nodeid"] == "test_parametrized_tests.py::test_two"


@pytest.mark.parametrize("phase", ["", "::setup", "::call", "::teardown"])
def test_parametrized_tests_share_a_span_name(
    pytester: Pytester, span_recorder: SpanRecorder, phase: str
) -> None:
    pytester.makepyfile("""
        import pytest

        class TestThings:
            @pytest.mark.parametrize('hello', ['world', 'people'])
            def test_one(self, hello):
                assert 1 + 2 == 3
    """)
    pytester.runpytest().assert_outcomes(passed=2)

    nodeid = "test_parametrized_tests_share_a_span_name.py::TestThings::test_one"
    spans = span_recorder.spans_by_nodeid(f"{nodeid}{phase}")
    assert set(spans) == {f"{nodeid}[world]", f"{nodeid}[people]"}
    assert [(span.attributes or {})["code.function"] for span in spans.values()] == [
        "test_one",
        "test_one",
    ]


def test_class_tests(pytester: Pytester, span_recorder: SpanRecorder) -> None:
    pytester.makepyfile("""
        class TestThings:
            def test_one(self):
                assert 1 + 2 == 3

            def test_two(self):
                assert 2 + 2 == 4
    """)
    pytester.runpytest().assert_outcomes(passed=2)

    spans = span_recorder.spans_by_name()
    # assert len(spans) == 2 + 1

    assert "test run" in spans

    span = spans["test_class_tests.py::TestThings::test_one"]
    assert span.status.is_ok
    assert span.attributes
    assert (
        span.attributes["pytest.nodeid"] == "test_class_tests.py::TestThings::test_one"
    )

    span = spans["test_class_tests.py::TestThings::test_two"]
    assert span.status.is_ok
    assert span.attributes
    assert (
        span.attributes["pytest.nodeid"] == "test_class_tests.py::TestThings::test_two"
    )


def test_test_spans_are_children_of_sessions(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    pytester.makepyfile("""
        def test_one():
            assert 1 + 2 == 3
    """)
    pytester.runpytest().assert_outcomes(passed=1)

    spans = span_recorder.spans_by_name()
    # assert len(spans) == 2

    test_run = spans["test run"]
    test = spans["test_test_spans_are_children_of_sessions.py::test_one"]

    assert trace_id(test_run)
    assert trace_id(test) == trace_id(test_run)

    assert test.parent
    assert parent_id(test) == span_id(test_run)


def test_spans_within_tests_are_children_of_test_spans(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    pytester.makepyfile("""
        from opentelemetry import trace

        tracer = trace.get_tracer('inside')

        def test_one():
            with tracer.start_as_current_span('inner'):
                assert 1 + 2 == 3
    """)
    pytester.runpytest().assert_outcomes(passed=1)

    spans = span_recorder.spans_by_name()
    # assert len(spans) == 3

    test_run = spans["test run"]
    test = spans["test_spans_within_tests_are_children_of_test_spans.py::test_one"]
    test_call = spans[
        "test_spans_within_tests_are_children_of_test_spans.py::test_one::call"
    ]
    inner = spans["inner"]

    assert trace_id(test_run)
    assert trace_id(test) == trace_id(test_run)
    assert trace_id(test_call) == trace_id(test)
    assert trace_id(inner) == trace_id(test_call)

    assert test.parent
    assert parent_id(test) == span_id(test_run)

    assert test_call.parent
    assert parent_id(test_call) == span_id(test)

    assert inner.parent
    assert parent_id(inner) == span_id(test_call)


def test_test_that_another_plugin_runs_twice(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    # pytest-rerunfailures runs a test again inside one pytest_runtest_protocol.
    pytester.makeconftest("""
        from _pytest.runner import runtestprotocol

        def pytest_runtest_protocol(item, nextitem):
            runtestprotocol(item, nextitem=nextitem, log=False)
            runtestprotocol(item, nextitem=nextitem)
            return True
    """)
    pytester.makepyfile("""
        import pytest

        @pytest.fixture
        def thing():
            yield

        def test_one(thing):
            pass
    """)
    pytester.runpytest().assert_outcomes(passed=1)

    node = "test_test_that_another_plugin_runs_twice.py::test_one"
    (test,) = span_recorder.spans_named(node)

    for phase in ("setup", "call", "teardown"):
        first, second = span_recorder.spans_named(f"{node}::{phase}")
        assert parent_id(first) == span_id(test)
        assert parent_id(second) == span_id(test)

    setups = span_recorder.spans_named(f"{node}::setup")
    fixtures = span_recorder.spans_named("thing setup")
    assert len(fixtures) == 2
    assert {parent_id(fixture) for fixture in fixtures} == {
        span_id(setup) for setup in setups
    }
