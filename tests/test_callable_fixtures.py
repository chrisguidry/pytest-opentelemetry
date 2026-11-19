from _pytest.pytester import Pytester

from . import SpanRecorder


def test_fixture_from_a_callable_instance(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    pytester.makepyfile("""
        import pytest

        class Answer:
            __name__ = 'answer'

            def __call__(self) -> int:
                return 42

        answer = pytest.fixture(name='answer')(Answer())

        def test_one(answer: int):
            assert answer == 42
    """)
    pytester.runpytest().assert_outcomes(passed=1)

    span = span_recorder.spans_by_name()['answer setup']
    assert span.attributes
    assert span.attributes['code.function'] == 'answer'
    assert span.attributes['code.filepath'].endswith(
        'test_fixture_from_a_callable_instance.py'
    )
    assert span.attributes['code.lineno'] == 6


def test_fixture_from_a_callable_without_python_code(
    pytester: Pytester, span_recorder: SpanRecorder
) -> None:
    pytester.makepyfile("""
        from functools import partial

        import pytest

        class Answer:
            __name__ = 'answer'
            __call__ = staticmethod(partial(lambda: 42))

        answer = pytest.fixture(name='answer')(Answer())

        def test_one(answer: int):
            assert answer == 42
    """)
    pytester.runpytest().assert_outcomes(passed=1)

    span = span_recorder.spans_by_name()['answer setup']
    assert span.attributes
    assert span.attributes['code.function'] == 'answer'
    assert 'code.filepath' not in span.attributes
    assert 'code.lineno' not in span.attributes
