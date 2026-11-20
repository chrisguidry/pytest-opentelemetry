from _pytest.pytester import Pytester

from . import SpanRecorder, end_time, parent_id, span_id, start_time


def test_finalizer_added_late_to_a_shared_fixture_is_outside_the_test(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    # A factory fixture adds a finalizer each time a test calls it.  pytest
    # runs those before the fixture's own teardown.
    pytester.makepyfile("""
        import pytest
        from opentelemetry import trace

        tracer = trace.get_tracer('inside')

        def stop():
            with tracer.start_as_current_span('stopping'):
                pass

        @pytest.fixture(scope='session')
        def make_server(request):
            def make():
                request.addfinalizer(stop)
            yield make

        def test_one(make_server):
            make_server()
    """)
    pytester.runpytest().assert_outcomes(passed=1)

    spans = span_recorder.spans_by_name()
    test = spans[
        "test_finalizer_added_late_to_a_shared_fixture_is_outside_the_test.py::test_one"
    ]
    assert parent_id(spans["stopping"]) == span_id(spans["test run"])
    assert end_time(test) <= start_time(spans["stopping"])


def test_finalizer_that_a_test_adds_is_inside_the_test(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    pytester.makepyfile("""
        from opentelemetry import trace

        tracer = trace.get_tracer('inside')

        def clean():
            with tracer.start_as_current_span('cleaning'):
                pass

        def test_one(request):
            request.addfinalizer(clean)
    """)
    pytester.runpytest().assert_outcomes(passed=1)

    spans = span_recorder.spans_by_name()
    teardown = spans[
        "test_finalizer_that_a_test_adds_is_inside_the_test.py::test_one::teardown"
    ]
    assert parent_id(spans["cleaning"]) == span_id(teardown)


def test_teardown_of_a_package_is_outside_the_test(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    package = pytester.mkpydir("package")
    package.joinpath("__init__.py").write_text(
        """
from opentelemetry import trace

def teardown_module():
    with trace.get_tracer('inside').start_as_current_span('leaving'):
        pass
"""
    )
    package.joinpath("test_inside.py").write_text(
        """
def test_one():
    pass
"""
    )
    pytester.runpytest().assert_outcomes(passed=1)

    spans = span_recorder.spans_by_name()
    test = spans["package/test_inside.py::test_one"]
    assert parent_id(spans["leaving"]) == span_id(spans["test run"])
    assert end_time(test) <= start_time(spans["leaving"])


def test_skipped_test_after_one_that_ended_early_has_its_own_end(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    # The first test's span ends when its class's fixture starts to tear down.
    # pytest never sets the second test up, so nothing ends its span early.
    pytester.makepyfile("""
        import pytest

        @pytest.fixture(scope='class')
        def class_scoped():
            yield

        class TestThings:
            def test_one(self, class_scoped):
                pass

        @pytest.mark.skip
        def test_two():
            pass
    """)
    pytester.runpytest().assert_outcomes(passed=1, skipped=1)

    spans = span_recorder.spans_by_name()
    test = spans[
        "test_skipped_test_after_one_that_ended_early_has_its_own_end.py::test_two"
    ]
    assert start_time(test) <= end_time(test)
