import pytest
from _pytest.pytester import Pytester
from opentelemetry.trace import StatusCode

from . import SpanRecorder


def test_fixture_that_raises_records_its_own_error(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    pytester.makepyfile("""
        import pytest

        @pytest.fixture(scope='session')
        def broken():
            raise ValueError('woops')

        def test_one(broken):
            pass
    """)
    pytester.runpytest().assert_outcomes(errors=1)

    spans = span_recorder.spans_by_name()

    setup = spans["broken setup"]
    assert setup.status.status_code == StatusCode.ERROR
    assert setup.status.description == "ValueError: woops"
    (event,) = setup.events
    assert event.attributes
    assert event.attributes["exception.type"] == "ValueError"
    assert event.attributes["exception.message"] == "woops"

    test = spans["test_fixture_that_raises_records_its_own_error.py::test_one"]
    assert test.status.status_code == StatusCode.ERROR

    # The fixture never set up, so it has nothing to tear down.
    assert "broken teardown" not in spans


@pytest.mark.parametrize(
    "outcome, expected",
    [
        pytest.param("skip", {"skipped": 1}, id="skip"),
        pytest.param("xfail", {"xfailed": 1}, id="xfail"),
    ],
)
def test_fixture_that_skips_or_expects_a_failure_is_not_an_error(
    pytester: Pytester,
    span_recorder: SpanRecorder,
    outcome: str,
    expected: dict[str, int],
) -> None:
    pytester.makepyfile(f"""
        import pytest

        @pytest.fixture
        def undecided():
            pytest.{outcome}('not today')

        def test_one(undecided):
            pass
    """)
    pytester.runpytest().assert_outcomes(**expected)

    setup = span_recorder.spans_by_name()["undecided setup"]
    assert setup.status.status_code == StatusCode.UNSET
    assert not setup.events


@pytest.mark.parametrize("scope", ["function", "session"])
def test_fixture_that_raises_in_teardown_marks_the_teardown_of_the_test(
    pytester: Pytester, span_recorder: SpanRecorder, scope: str
) -> None:
    # pytest reports the error of a shared fixture's teardown against the last
    # test that used the fixture.
    pytester.makepyfile(f"""
        import pytest

        @pytest.fixture(scope='{scope}')
        def broken():
            yield
            raise ValueError('woops')

        def test_one(broken):
            pass
    """)
    pytester.runpytest().assert_outcomes(passed=1, errors=1)

    spans = span_recorder.spans_by_name()
    node = (
        "test_fixture_that_raises_in_teardown_marks_the_teardown_of_the_test.py"
        "::test_one"
    )

    teardown = spans[f"{node}::teardown"]
    assert teardown.status.status_code == StatusCode.ERROR
    assert teardown.status.description == "ValueError: woops"
    (event,) = teardown.events
    assert event.attributes
    assert event.attributes["exception.type"] == "ValueError"

    # The test itself passed.
    assert spans[node].status.status_code == StatusCode.OK
    assert spans["test run"].status.status_code == StatusCode.ERROR
