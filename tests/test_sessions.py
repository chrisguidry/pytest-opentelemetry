import os
from contextlib import contextmanager
from typing import Dict, Generator, List, Optional
from unittest.mock import Mock, patch

import pytest
from _pytest.pytester import Pytester
from opentelemetry import trace

from pytest_opentelemetry.instrumentation import (
    OpenTelemetryPlugin,
    PerTestOpenTelemetryPlugin,
    XdistOpenTelemetryPlugin,
)

from . import SpanRecorder


@contextmanager
def environment(**overrides: Optional[str]) -> Generator[None, None, None]:
    original: Dict[str, Optional[str]] = {}
    for key, value in overrides.items():
        original[key] = os.environ.pop(key, None)
        if value is not None:
            os.environ[key] = value

    try:
        yield
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_environment_manipulation():
    assert 'VALUE' not in os.environ
    with environment(VALUE='outer'):
        assert os.environ['VALUE'] == 'outer'
        with environment(VALUE='inner'):
            assert os.environ['VALUE'] == 'inner'
            with environment(VALUE=None):
                assert 'VALUE' not in os.environ
                with environment(VALUE='once more'):
                    assert os.environ['VALUE'] == 'once more'
                assert 'VALUE' not in os.environ
            assert os.environ['VALUE'] == 'inner'
        assert os.environ['VALUE'] == 'outer'
    assert 'VALUE' not in os.environ


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


def test_getting_trace_id_from_environment_variable(pytester: Pytester) -> None:
    config = pytester.parseconfig()

    with environment(
        TRACEPARENT='00-1234567890abcdef1234567890abcdef-fedcba0987654321-01'
    ):
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


@pytest.mark.parametrize(
    'args',
    [
        pytest.param([], id="default"),
        pytest.param(['-n', '2'], id="xdist"),
        pytest.param(['-p', 'no:xdist'], id='no:xdist'),
    ],
)
def test_trace_per_test(
    pytester: Pytester, span_recorder: SpanRecorder, args: List[str]
) -> None:
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
        '--trace-per-test',
        *args,
        '--trace-parent',
        '00-1234567890abcdef1234567890abcdef-fedcba0987654321-01',
    )
    result.assert_outcomes(passed=2)


@patch.object(trace, 'get_tracer_provider')
def test_force_flush_with_supported_provider(mock_get_tracer_provider):
    provider = Mock()
    provider.force_flush = Mock(return_value=None)
    mock_get_tracer_provider.return_value = provider

    for plugin in (
        OpenTelemetryPlugin,
        XdistOpenTelemetryPlugin,
        PerTestOpenTelemetryPlugin,
    ):
        assert plugin.try_force_flush() is True


@patch.object(trace, 'get_tracer_provider')
def test_force_flush_with_unsupported_provider(mock_get_tracer_provider):
    provider = Mock(spec=trace.ProxyTracerProvider)
    mock_get_tracer_provider.return_value = provider

    for plugin in (
        OpenTelemetryPlugin,
        XdistOpenTelemetryPlugin,
        PerTestOpenTelemetryPlugin,
    ):
        assert plugin.try_force_flush() is False
