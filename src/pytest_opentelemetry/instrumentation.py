import os
import subprocess
import sys
from typing import Dict

from _pytest.reports import TestReport
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.trace import Status, StatusCode
from psutil import Process


class OpenTelemetryPlugin:
    def __init__(self):
        self.provider = None
        self.tracer = trace.get_tracer('pytest-opentelemetry')
        self.test_spans = {}
        self.phase_spans = {}

    @staticmethod
    def _initialize_trace_provider(resource: Resource, export: bool) -> TracerProvider:
        provider = trace.get_tracer_provider()
        if not hasattr(provider, "add_span_processor"):  # pragma: no cover
            provider = TracerProvider(resource=resource)
            trace.set_tracer_provider(provider)

        if export:  # pragma: no cover
            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))

        return provider

    @staticmethod
    def _get_process_attributes() -> Dict:
        # https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/resource/semantic_conventions/process.md#process
        process = Process()
        with process.oneshot():
            command_line = process.cmdline()
            command, *arguments = command_line
            return {
                ResourceAttributes.PROCESS_PID: process.pid,
                ResourceAttributes.PROCESS_EXECUTABLE_NAME: process.name(),
                ResourceAttributes.PROCESS_EXECUTABLE_PATH: process.exe(),
                ResourceAttributes.PROCESS_COMMAND_LINE: ' '.join(command_line),
                ResourceAttributes.PROCESS_COMMAND: command,
                ResourceAttributes.PROCESS_COMMAND_ARGS: ' '.join(arguments),
                ResourceAttributes.PROCESS_OWNER: process.username(),
            }

    @staticmethod
    def _get_runtime_attributes() -> Dict:
        # https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/resource/semantic_conventions/process.md#python-runtimes
        version = sys.implementation.version
        version = ".".join(
            map(
                str,
                version[:3]
                if version.releaselevel == "final" and not version.serial
                else version,
            )
        )
        return {
            ResourceAttributes.PROCESS_RUNTIME_NAME: sys.implementation.name,
            ResourceAttributes.PROCESS_RUNTIME_VERSION: version,
            ResourceAttributes.PROCESS_RUNTIME_DESCRIPTION: sys.version,
        }

    @classmethod
    def _get_codebase_attributes(cls):
        return {
            ResourceAttributes.SERVICE_NAME: cls._get_codebase_name(),
            ResourceAttributes.SERVICE_VERSION: cls._get_codebase_version(),
        }

    @staticmethod
    def _get_codebase_name():
        # TODO: any better ways to get this?
        return os.path.split(os.getcwd())[-1]

    @staticmethod
    def _get_codebase_version():
        if not os.path.exists('.git'):
            return None

        try:
            version = subprocess.check_output(['git', 'rev-parse', 'HEAD'])
        except Exception:  # pragma: no cover pylint: disable=broad-except
            return None

        return version.decode().strip()

    def pytest_configure(self, config):
        attributes = {
            **self._get_process_attributes(),
            **self._get_runtime_attributes(),
            **self._get_codebase_attributes(),
        }
        resource = Resource.create(attributes)

        export = config.getoption('--export-traces')

        self.provider = self._initialize_trace_provider(resource, export)

    def pytest_runtest_logreport(self, report: TestReport):
        getattr(self, f'on_test_{report.when}')(report)

    def on_test_setup(self, report: TestReport):
        test_span = self.tracer.start_span(report.nodeid)
        self.test_spans[report.nodeid] = test_span

    def on_test_call(self, report: TestReport):
        test_span = self.test_spans[report.nodeid]
        if report.outcome == 'failed':
            test_span.set_status(Status(StatusCode.ERROR))
        else:
            test_span.set_status(Status(StatusCode.OK))

    def on_test_teardown(self, report: TestReport):
        test_span = self.test_spans.pop(report.nodeid)
        test_span.end()
