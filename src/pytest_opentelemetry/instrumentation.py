from typing import Any, Generator, Optional

import pytest
from _pytest.config import Config
from _pytest.main import Session
from _pytest.nodes import Item, Node
from _pytest.reports import TestReport
from _pytest.runner import CallInfo
from opentelemetry import propagate, trace
from opentelemetry.context.context import Context
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import Status, StatusCode
from opentelemetry_container_distro import (
    OpenTelemetryContainerConfigurator,
    OpenTelemetryContainerDistro,
)

from .resource import CodebaseResourceDetector

try:
    from xdist.workermanage import WorkerController  # pylint: disable=unused-import
except ImportError:  # pragma: no cover
    WorkerController = None

tracer = trace.get_tracer('pytest-opentelemetry')


class OpenTelemetryPlugin:
    """A pytest plugin which produces OpenTelemetry spans around test sessions and
    individual test runs."""

    @staticmethod
    def get_trace_parent(config: Config) -> Optional[Context]:
        if trace_parent := config.getvalue('--trace-parent'):
            from_arguments = {'traceparent': trace_parent}
            return propagate.extract(from_arguments)

        if workerinput := getattr(config, 'workerinput', None):
            return propagate.extract(workerinput)

        return None

    def pytest_configure(self, config: Config) -> None:
        self.trace_parent = self.get_trace_parent(config)
        self.worker_id = getattr(config, 'workerinput', {}).get('workerid')

        # This can't be tested both ways in one process
        if config.getoption('--export-traces'):  # pragma: no cover
            OpenTelemetryContainerDistro().configure()

        configurator = OpenTelemetryContainerConfigurator()
        configurator.resource_detectors.append(CodebaseResourceDetector())
        configurator.configure()

    def pytest_sessionstart(self, session: Session) -> None:
        session_name = f'test worker {self.worker_id}' if self.worker_id else 'test run'
        self.session_span = tracer.start_span(session_name, context=self.trace_parent)

    def pytest_configure_node(self, node: WorkerController) -> None:  # pragma: no cover
        with trace.use_span(self.session_span, end_on_exit=False):
            propagate.inject(node.workerinput)

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
