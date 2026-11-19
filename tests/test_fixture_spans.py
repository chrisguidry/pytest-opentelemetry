from collections import Counter
import pytest
from _pytest.pytester import Pytester

from . import SpanRecorder, parent_id, span_id, trace_id


def test_spans_cover_setup_and_teardown(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    pytester.makepyfile("""
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
    """)
    pytester.runpytest().assert_outcomes(passed=1)

    spans = span_recorder.spans_by_name()

    test_run = spans["test run"]
    assert trace_id(test_run)
    assert all(trace_id(span) == trace_id(test_run) for span in spans.values())

    test = spans["test_spans_cover_setup_and_teardown.py::test_one"]

    setup = spans["test_spans_cover_setup_and_teardown.py::test_one::setup"]
    assert parent_id(setup) == span_id(test)

    assert parent_id(spans["yielded setup"]) == span_id(setup)
    assert parent_id(spans["returned setup"]) == span_id(setup)

    teardown = spans["test_spans_cover_setup_and_teardown.py::test_one::teardown"]
    assert parent_id(teardown) == span_id(test)
    assert parent_id(spans["yielded teardown"]) == span_id(teardown)
    assert parent_id(spans["returned teardown"]) == span_id(teardown)


def test_spans_cover_fixtures_at_different_scopes(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    pytester.makepyfile("""
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
    """)
    pytester.runpytest().assert_outcomes(passed=1)

    spans = span_recorder.spans_by_name()

    test_run = spans["test run"]
    assert trace_id(test_run)
    assert all(trace_id(span) == trace_id(test_run) for span in spans.values())

    test = spans["test_spans_cover_fixtures_at_different_scopes.py::test_one"]

    setup = spans["test_spans_cover_fixtures_at_different_scopes.py::test_one::setup"]
    assert parent_id(setup) == span_id(test)

    session_scoped = spans["session_scoped setup"]
    module_scoped = spans["module_scoped setup"]
    function_scoped = spans["function_scoped setup"]

    assert parent_id(session_scoped) == span_id(setup)
    assert parent_id(module_scoped) == span_id(setup)
    assert parent_id(function_scoped) == span_id(setup)


@pytest.mark.parametrize(
    "args",
    [
        pytest.param([], id="trace-per-suite"),
        pytest.param(["--trace-per-test"], id="trace-per-test"),
    ],
)
def test_spans_from_fixutres_used_multiple_times(
    pytester: Pytester,
    span_recorder: SpanRecorder,
    args: list[str],
) -> None:
    pytester.makepyfile("""
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

        @pytest.fixture(scope='class')
        def class_scoped() -> int:
            return 4

        def test_one(session_scoped: int, module_scoped: int, function_scoped: int):
            assert session_scoped + module_scoped + function_scoped == 6

        def test_two(session_scoped: int, module_scoped: int, function_scoped: int):
            assert session_scoped + module_scoped + function_scoped == 6

        class TestClass:
            def test_a(self, class_scoped: int, session_scoped: int):
                assert class_scoped + session_scoped == 5

            def test_b(self, class_scoped: int, module_scoped: int):
                assert class_scoped + module_scoped == 6

            def test_c(self, class_scoped: int, function_scoped: int):
                assert class_scoped + function_scoped == 7

    """)
    pytester.runpytest(*args).assert_outcomes(passed=5)
    spans = Counter(span.name for span in span_recorder.finished_spans())

    assert spans["session_scoped setup"] == 1
    assert spans["session_scoped teardown"] == 1

    assert spans["module_scoped setup"] == 1
    assert spans["module_scoped teardown"] == 1

    assert spans["class_scoped setup"] == 1
    assert spans["class_scoped teardown"] == 1

    assert spans["function_scoped setup"] == 3
    assert spans["function_scoped teardown"] == 3


def test_parametrized_fixture_names(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    pytester.makepyfile("""
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
    """)
    pytester.runpytest().assert_outcomes(passed=4)

    spans = span_recorder.spans_by_name()

    test_run = spans["test run"]
    assert trace_id(test_run)
    assert all(trace_id(span) == trace_id(test_run) for span in spans.values())

    # the stringable arguments are used in the span name
    assert "stringable[111] setup" in spans
    assert "stringable[111] teardown" in spans
    assert "stringable[222] setup" in spans
    assert "stringable[222] teardown" in spans

    # the indexes of non-stringable arguments are used in the span name
    assert "unstringable[0] setup" in spans
    assert "unstringable[0] teardown" in spans
    assert "unstringable[1] setup" in spans
    assert "unstringable[1] teardown" in spans
