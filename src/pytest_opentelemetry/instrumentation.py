from typing import Any, Generator

import opentelemetry.sdk.trace as trace_sdk
import pytest
from _pytest.config import Config
from _pytest.main import Session
from _pytest.nodes import Item, Node
from _pytest.reports import TestReport
from _pytest.runner import CallInfo
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import Status, StatusCode, TracerProvider

from . import resource

tracer = trace.get_tracer('pytest-opentelemetry')


class OpenTelemetryPlugin:
    @staticmethod
    def _initialize_trace_provider(resource: Resource, export: bool) -> TracerProvider:
        provider = trace.get_tracer_provider()

        if not isinstance(provider, trace_sdk.TracerProvider):  # pragma: no cover
            provider = trace_sdk.TracerProvider(resource=resource)
            trace.set_tracer_provider(provider)

        if export:  # pragma: no cover
            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))

        return provider

    def pytest_configure(self, config: Config) -> None:
        attributes = {
            **resource.get_process_attributes(),
            **resource.get_runtime_attributes(),
            **resource.get_codebase_attributes(),
        }

        self.provider = self._initialize_trace_provider(
            resource=Resource.create(attributes),
            export=config.getoption('--export-traces'),
        )

    def pytest_sessionstart(self, session: Session) -> None:
        self.session_span = tracer.start_span('test session')

    def pytest_sessionfinish(self, session: Session) -> None:
        self.session_span.end()

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_protocol(self, item: Item) -> Generator[None, None, None]:
        context = trace.set_span_in_context(self.session_span)
        with tracer.start_as_current_span(item.nodeid, context=context) as test_span:
            filepath, line_number, domain = item.location
            test_span.set_attributes(
                {
                    SpanAttributes.CODE_FUNCTION: domain,
                    SpanAttributes.CODE_FILEPATH: filepath,
                    SpanAttributes.CODE_LINENO: str(line_number),
                }
            )

            yield

    @staticmethod
    def pytest_exception_interact(
        node: Node,
        call: CallInfo[Any],
        report: TestReport,
    ) -> None:
        excinfo = call.excinfo
        assert excinfo
        assert isinstance(excinfo.value, Exception)

        test_span = trace.get_current_span()

        test_span.record_exception(
            exception=excinfo.value,
            attributes={
                SpanAttributes.EXCEPTION_STACKTRACE: str(report.longrepr),
            },
        )
        test_span.set_status(
            Status(
                status_code=StatusCode.ERROR,
                description=f"{excinfo.type}: {excinfo.value}",
            )
        )

    @staticmethod
    def pytest_runtest_logreport(report: TestReport) -> None:
        if report.when != 'call':
            return

        status_code = StatusCode.ERROR if report.outcome == 'failed' else StatusCode.OK
        trace.get_current_span().set_status(Status(status_code))
