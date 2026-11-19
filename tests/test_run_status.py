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
