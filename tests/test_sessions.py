from _pytest.pytester import Pytester
from opentelemetry import trace

from pytest_opentelemetry.instrumentation import (
    OpenTelemetryPlugin,
    XdistOpenTelemetryPlugin,
)

from . import SpanRecorder


def test_getting_no_trace_id(pytester: Pytester) -> None:
    config = pytester.parseconfig()
    context = OpenTelemetryPlugin.get_trace_parent(config)
    assert context is None


def test_getting_trace_id_from_command_line(pytester: Pytester) -> None:
    config = pytester.parseconfig(
        '--trace-parent',
        '00-1234567890abcdef1234567890abcdef-fedcba0987654321-01',
    )
    context = OpenTelemetryPlugin.get_trace_parent(config)
    assert context

    parent_span = next(iter(context.values()))
    assert isinstance(parent_span, trace.Span)

    parent = parent_span.get_span_context()
    assert parent.trace_id == 0x1234567890ABCDEF1234567890ABCDEF
    assert parent.span_id == 0xFEDCBA0987654321


def test_getting_trace_id_from_worker_input(pytester: Pytester) -> None:
    config = pytester.parseconfig()
    setattr(
        config,
        'workerinput',
        {'traceparent': '00-1234567890abcdef1234567890abcdef-fedcba0987654321-01'},
    )
    context = XdistOpenTelemetryPlugin.get_trace_parent(config)
    assert context

    parent_span = next(iter(context.values()))
    assert isinstance(parent_span, trace.Span)

    parent = parent_span.get_span_context()
    assert parent.trace_id == 0x1234567890ABCDEF1234567890ABCDEF
    assert parent.span_id == 0xFEDCBA0987654321


def test_passing_trace_id(pytester: Pytester, span_recorder: SpanRecorder) -> None:
    pytester.makepyfile(
        """
        from opentelemetry import trace

        def test_one(worker_id):
            # confirm that this is not an xdist worker
            assert not worker_id.startswith('gw')

            span = trace.get_current_span()
            assert span.context.trace_id == 0x1234567890abcdef1234567890abcdef
            assert span.context.span_id != 0xfedcba0987654321

        def test_two(worker_id):
            # confirm that this is not an xdist worker
            assert not worker_id.startswith('gw')

            span = trace.get_current_span()
            assert span.context.trace_id == 0x1234567890abcdef1234567890abcdef
            assert span.context.span_id != 0xfedcba0987654321
    """
    )
    result = pytester.runpytest_subprocess(
        '--trace-parent',
        '00-1234567890abcdef1234567890abcdef-fedcba0987654321-01',
    )
    result.assert_outcomes(passed=2)


def test_multiple_workers(pytester: Pytester, span_recorder: SpanRecorder) -> None:
    pytester.makepyfile(
        """
        from opentelemetry import trace

        def test_one(worker_id):
            # confirm that this is an xdist worker
            assert worker_id in {'gw0', 'gw1'}

            span = trace.get_current_span()
            assert span.context.trace_id == 0x1234567890abcdef1234567890abcdef

        def test_two(worker_id):
            # confirm that this is an xdist worker
            assert worker_id in {'gw0', 'gw1'}

            span = trace.get_current_span()
            assert span.context.trace_id == 0x1234567890abcdef1234567890abcdef
    """
    )
    result = pytester.runpytest_subprocess(
        '-n',
        '2',
        '--trace-parent',
        '00-1234567890abcdef1234567890abcdef-fedcba0987654321-01',
    )
    result.assert_outcomes(passed=2)


def test_works_without_xdist(pytester: Pytester, span_recorder: SpanRecorder) -> None:
    pytester.makepyfile(
        """
        from opentelemetry import trace

        def test_one():
            span = trace.get_current_span()
            assert span.context.trace_id == 0x1234567890abcdef1234567890abcdef

        def test_two():
            span = trace.get_current_span()
            assert span.context.trace_id == 0x1234567890abcdef1234567890abcdef
    """
    )
    result = pytester.runpytest_subprocess(
        '-p',
        'no:xdist',
        '--trace-parent',
        '00-1234567890abcdef1234567890abcdef-fedcba0987654321-01',
    )
    result.assert_outcomes(passed=2)
