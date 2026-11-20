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
    assert parent_id(spans["before"]) == span_id(spans["yielded setup"])
    assert parent_id(spans["returning"]) == span_id(spans["returned setup"])

    teardown = spans["test_spans_cover_setup_and_teardown.py::test_one::teardown"]
    assert parent_id(teardown) == span_id(test)
    assert parent_id(spans["yielded teardown"]) == span_id(teardown)
    assert parent_id(spans["returned teardown"]) == span_id(teardown)


def test_function_fixtures_are_children_of_setup_and_teardown(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    pytester.makepyfile("""
        import pytest
        from opentelemetry import trace

        tracer = trace.get_tracer('inside')

        @pytest.fixture(scope='function')
        def function_scoped():
            with tracer.start_as_current_span('creating'):
                pass
            yield
            with tracer.start_as_current_span('dropping'):
                pass

        def test_one(function_scoped):
            pass
    """)
    pytester.runpytest().assert_outcomes(passed=1)

    spans = span_recorder.spans_by_name()
    node = "test_function_fixtures_are_children_of_setup_and_teardown.py::test_one"

    setup = spans["function_scoped setup"]
    assert parent_id(setup) == span_id(spans[f"{node}::setup"])
    assert parent_id(spans["creating"]) == span_id(setup)
    assert setup.attributes
    assert setup.attributes["pytest.fixture_scope"] == "function"
    assert setup.attributes["pytest.span_type"] == "fixture"

    teardown = spans["function_scoped teardown"]
    assert parent_id(teardown) == span_id(spans[f"{node}::teardown"])
    assert parent_id(spans["dropping"]) == span_id(teardown)
    assert teardown.attributes == setup.attributes


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
