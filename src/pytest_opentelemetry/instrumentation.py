from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode


class OpenTelemetryPlugin:
    def __init__(self):
        self.test_spans = {}
        self.phase_spans = {}
        self.tracer = trace.get_tracer('pytest-opentelemetry')

    def pytest_runtest_logreport(self, report):
        getattr(self, f'on_test_{report.when}')(report)

    def on_test_setup(self, report):
        test_span = self.tracer.start_span(report.nodeid)
        self.test_spans[report.nodeid] = test_span

    def on_test_call(self, report):
        test_span = self.test_spans[report.nodeid]
        if report.outcome == 'failed':
            test_span.set_status(Status(StatusCode.ERROR))
        else:
            test_span.set_status(Status(StatusCode.OK))

    def on_test_teardown(self, report):
        test_span = self.test_spans.pop(report.nodeid)
        test_span.end()
