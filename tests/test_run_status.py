import pytest
from _pytest.pytester import Pytester
from opentelemetry.trace import StatusCode

from . import SpanRecorder


@pytest.mark.parametrize(
    "source, expected",
    [
        pytest.param(
            """
            def test_one():
                assert 1 + 2 == 3
            """,
            StatusCode.OK,
            id="passing",
        ),
        pytest.param(
            """
            import pytest

            @pytest.mark.skip
            def test_one():
                assert 1 + 2 == 4

            @pytest.mark.xfail
            def test_two():
                assert 1 + 2 == 4
            """,
            StatusCode.OK,
            id="skipped-and-expected-failure",
        ),
        pytest.param(
            """
            def test_one():
                assert 1 + 2 == 4
            """,
            StatusCode.ERROR,
            id="failing-test",
        ),
        pytest.param(
            """
            import pytest

            @pytest.fixture
            def broken():
                raise ValueError('woops')

            def test_one(broken):
                assert 1 + 2 == 3
            """,
            StatusCode.ERROR,
            id="error-in-fixture-setup",
        ),
        pytest.param(
            """
            import pytest

            @pytest.fixture
            def broken():
                yield
                raise ValueError('woops')

            def test_one(broken):
                assert 1 + 2 == 3
            """,
            StatusCode.ERROR,
            id="error-in-fixture-teardown",
        ),
        pytest.param(
            """
            raise ValueError('woops')
            """,
            StatusCode.ERROR,
            id="error-in-collection",
        ),
    ],
)
def test_run_status(
    pytester: Pytester,
    span_recorder: SpanRecorder,
    source: str,
    expected: StatusCode,
) -> None:
    pytester.makepyfile(source)
    pytester.runpytest()

    test_run = span_recorder.spans_by_name()["test run"]
    assert test_run.status.status_code == expected


def test_run_fails_after_a_test_that_another_plugin_ran(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    # pytest-forked runs a test in a child process.  In the parent it takes
    # over the test's protocol and only logs the reports that come back.
    pytester.makeconftest("""
        from _pytest.reports import TestReport

        def pytest_runtest_protocol(item):
            if item.name != 'test_ran_elsewhere':
                return None
            for when in ('setup', 'call', 'teardown'):
                item.ihook.pytest_runtest_logreport(
                    report=TestReport(
                        item.nodeid, item.location, {}, 'passed', None, when
                    )
                )
            return True
    """)
    pytester.makepyfile("""
        def test_ran_elsewhere():
            pass

        def test_fails_here():
            assert 1 + 2 == 4
    """)
    pytester.runpytest().assert_outcomes(passed=1, failed=1)

    spans = span_recorder.spans_by_name()
    node = "test_run_fails_after_a_test_that_another_plugin_ran.py"
    assert spans["test run"].status.status_code == StatusCode.ERROR
    assert spans[f"{node}::test_ran_elsewhere"].status.status_code == StatusCode.OK
