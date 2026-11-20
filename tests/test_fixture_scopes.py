import pytest
from _pytest.pytester import Pytester

from . import SpanRecorder, end_time, parent_id, span_id, start_time


def test_wider_fixtures_are_children_of_the_test_run(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    pytester.makepyfile("""
        import pytest
        from opentelemetry import trace

        tracer = trace.get_tracer('inside')

        @pytest.fixture(scope='session')
        def database():
            with tracer.start_as_current_span('creating'):
                pass
            yield
            with tracer.start_as_current_span('dropping'):
                pass

        def test_one(database):
            pass
    """)
    pytester.runpytest().assert_outcomes(passed=1)

    spans = span_recorder.spans_by_name()
    test_run = spans["test run"]

    setup = spans["database setup"]
    assert parent_id(setup) == span_id(test_run)
    assert parent_id(spans["creating"]) == span_id(setup)

    teardown = spans["database teardown"]
    assert parent_id(teardown) == span_id(test_run)
    assert parent_id(spans["dropping"]) == span_id(teardown)


@pytest.mark.parametrize(
    "args",
    [
        pytest.param([], id="trace-per-suite"),
        pytest.param(["--trace-per-test"], id="trace-per-test"),
    ],
)
@pytest.mark.parametrize("scope", ["class", "module", "package", "session"])
def test_wider_fixtures_are_siblings_of_the_tests(
    pytester: Pytester, span_recorder: SpanRecorder, args: list[str], scope: str
) -> None:
    pytester.makepyfile(f"""
        import pytest

        @pytest.fixture(scope='{scope}')
        def wide():
            yield

        class TestThings:
            def test_one(self, wide):
                pass
    """)
    pytester.runpytest(*args).assert_outcomes(passed=1)

    spans = span_recorder.spans_by_name()
    test = spans[
        "test_wider_fixtures_are_siblings_of_the_tests.py::TestThings::test_one"
    ]
    assert parent_id(spans["wide setup"]) == parent_id(test)
    assert parent_id(spans["wide teardown"]) == parent_id(test)


def test_tests_exclude_the_time_of_wider_fixtures(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    pytester.makepyfile("""
        import pytest

        @pytest.fixture(scope='session')
        def session_scoped():
            yield

        @pytest.fixture(scope='module')
        def module_scoped():
            yield

        @pytest.fixture
        def function_scoped():
            yield

        def test_one(session_scoped, module_scoped, function_scoped):
            pass

        def test_two(session_scoped, module_scoped, function_scoped):
            pass
    """)
    pytester.runpytest().assert_outcomes(passed=2)

    spans = span_recorder.spans_by_name()
    node = "test_tests_exclude_the_time_of_wider_fixtures.py"
    first = spans[f"{node}::test_one"]
    last = spans[f"{node}::test_two"]

    in_order = [
        start_time(spans["session_scoped setup"]),
        end_time(spans["session_scoped setup"]),
        start_time(spans["module_scoped setup"]),
        end_time(spans["module_scoped setup"]),
        start_time(first),
        start_time(spans[f"{node}::test_one::setup"]),
        end_time(first),
        start_time(last),
        end_time(spans[f"{node}::test_two::teardown"]),
        end_time(last),
        start_time(spans["module_scoped teardown"]),
        end_time(spans["module_scoped teardown"]),
        start_time(spans["session_scoped teardown"]),
        end_time(spans["session_scoped teardown"]),
        end_time(spans["test run"]),
    ]
    assert in_order == sorted(in_order)


def test_fixture_torn_down_for_its_next_parameter(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    # pytest tears down a parametrized fixture of a wider scope during the
    # setup of the first test that uses its next parameter.
    pytester.makepyfile("""
        import pytest

        @pytest.fixture(scope='module', params=['x', 'y'])
        def server(request):
            yield request.param

        def test_one(server):
            pass
    """)
    pytester.runpytest().assert_outcomes(passed=2)

    test_run = span_recorder.spans_by_name()["test run"]
    node = "test_fixture_torn_down_for_its_next_parameter.py::test_one"
    second_test = span_recorder.spans_by_nodeid(node)[f"{node}[y]"]

    for_x, for_y = sorted(span_recorder.spans_named("server teardown"), key=start_time)
    assert parent_id(for_x) == span_id(test_run)
    assert parent_id(for_y) == span_id(test_run)
    assert end_time(for_x) <= start_time(second_test)
    assert end_time(second_test) <= start_time(for_y)


def test_fixtures_torn_down_after_the_run_stops_early(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    # When a failure makes -x stop the run, pytest tears down every fixture in
    # the teardown of the test that failed.
    pytester.makepyfile("""
        import pytest

        @pytest.fixture(scope='session')
        def session_scoped():
            yield

        def test_one(session_scoped):
            assert 1 + 2 == 4

        def test_two(session_scoped):
            pass
    """)
    pytester.runpytest("-x").assert_outcomes(failed=1)

    spans = span_recorder.spans_by_name()
    test_run = spans["test run"]
    teardown = spans["session_scoped teardown"]

    assert parent_id(teardown) == span_id(test_run)
    assert end_time(teardown) <= end_time(test_run)


def test_fixture_first_requested_inside_a_test_is_inside_that_test(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    pytester.makepyfile("""
        import pytest

        @pytest.fixture(scope='session')
        def session_scoped():
            yield

        def test_one(request):
            request.getfixturevalue('session_scoped')
    """)
    pytester.runpytest().assert_outcomes(passed=1)

    spans = span_recorder.spans_by_name()
    call = spans[
        "test_fixture_first_requested_inside_a_test_is_inside_that_test.py"
        "::test_one::call"
    ]
    assert parent_id(spans["session_scoped setup"]) == span_id(call)


@pytest.mark.parametrize(
    "source, fixture",
    [
        pytest.param(
            """
            import pytest

            @pytest.fixture(scope='class')
            def per_class():
                yield

            def test_one(per_class):
                pass
            """,
            "per_class",
            id="class-fixture-of-a-plain-function",
        ),
        pytest.param(
            """
            import pytest

            @pytest.fixture(scope='module')
            def server(request):
                yield request.param

            @pytest.mark.parametrize(
                'server, header', [('a', 1)], indirect=['server']
            )
            def test_one(server, header):
                pass
            """,
            "server",
            id="fixture-parametrized-along-with-a-plain-argument",
        ),
    ],
)
def test_fixture_that_pytest_binds_to_one_test_is_inside_that_test(
    pytester: Pytester, span_recorder: SpanRecorder, source: str, fixture: str
) -> None:
    # pytest sets up and tears down these fixtures for every test, whatever
    # scope they declare.
    pytester.makepyfile(source)
    pytester.runpytest().assert_outcomes(passed=1)

    spans = span_recorder.spans_by_name()
    node = "test_fixture_that_pytest_binds_to_one_test_is_inside_that_test.py::test_one"
    assert parent_id(spans[f"{fixture} setup"]) == span_id(spans[f"{node}::setup"])
    assert parent_id(spans[f"{fixture} teardown"]) == span_id(
        spans[f"{node}::teardown"]
    )


def test_fixtures_torn_down_after_the_run_stops_inside_a_test(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    # pytest.exit() and Ctrl-C end a test without its teardown, and pytest then
    # tears down every fixture as the session finishes.
    pytester.makepyfile("""
        import pytest

        @pytest.fixture(scope='session')
        def session_scoped():
            yield

        @pytest.fixture
        def function_scoped():
            yield

        def test_one(session_scoped, function_scoped):
            pytest.exit('enough')
    """)
    assert pytester.runpytest().ret == pytest.ExitCode.INTERRUPTED

    spans = span_recorder.spans_by_name()
    test_run = spans["test run"]
    assert parent_id(spans["function_scoped teardown"]) == span_id(test_run)
    assert parent_id(spans["session_scoped teardown"]) == span_id(test_run)
    assert end_time(spans["session_scoped teardown"]) <= end_time(test_run)
