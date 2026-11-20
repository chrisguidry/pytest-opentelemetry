import os
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import pytest
from _pytest.config import Config
from _pytest.fixtures import FixtureDef, SubRequest
from _pytest.main import Session
from _pytest.nodes import Item, Node
from _pytest.reports import CollectReport, TestReport
from _pytest.runner import CallInfo
from opentelemetry import context, propagate, trace
from opentelemetry.context.context import Context
from opentelemetry.semconv.attributes.exception_attributes import EXCEPTION_STACKTRACE
from opentelemetry.trace import Span, Status, StatusCode, Tracer
from pluggy import Result

from .fixtures import trace_fixture
from .items import ItemSpans, use_context
from .provider import build_tracer_provider

if TYPE_CHECKING:
    from xdist.workermanage import (  # pyright: ignore[reportMissingTypeStubs]
        WorkerController,
    )

tracer: Tracer = trace.get_tracer("pytest-opentelemetry")


def use_real_time_under_freezegun() -> None:
    """Tells freezegun, when it is installed, to give OpenTelemetry and this
    plugin the real time.

    freezegun replaces the clock that both read for a span's start and end.  A
    span that starts before a test freezes time and ends while time is frozen
    gets a negative duration, and a span that both starts and ends in frozen
    time gets a duration of zero."""
    try:
        import freezegun
    except ImportError:
        return

    freezegun.configure(extend_ignore_list=["opentelemetry", "pytest_opentelemetry"])


class PerTestOpenTelemetryPlugin:
    """base logic for all otel pytest integration"""

    trace_parent: Context | None = None

    def __init__(self) -> None:
        self._item_spans = ItemSpans(tracer)

    @property
    def item_parent(self) -> Context | None:
        return self.trace_parent

    @contextmanager
    def outside_tests(self) -> Generator[None, None, None]:
        """Makes the parent of the test spans current, for what pytest does
        that is not a part of one test."""
        parent = self.item_parent
        if parent is None:
            parent = context.get_current()
        with use_context(parent):
            yield

    @classmethod
    def get_trace_parent(cls, config: Config) -> Context | None:
        if trace_parent := config.getoption("--trace-parent"):
            return propagate.extract({"traceparent": trace_parent})

        if trace_parent := os.environ.get("TRACEPARENT"):
            return propagate.extract({"traceparent": trace_parent})

        return None

    @classmethod
    def try_force_flush(cls) -> bool:
        provider = trace.get_tracer_provider()

        # Not all providers (e.g. ProxyTraceProvider) implement force flush
        force_flush = getattr(provider, "force_flush", None)
        if force_flush is None:
            return False

        force_flush()
        return True

    def pytest_configure(self, config: Config) -> None:
        self.trace_parent = self.get_trace_parent(config)

        use_real_time_under_freezegun()

        trace.set_tracer_provider(build_tracer_provider(config))

    @pytest.hookimpl(hookwrapper=True)
    def pytest_sessionfinish(self, session: Session) -> Iterator[None]:
        # When a test stops the whole run, as pytest.exit() and Ctrl-C do,
        # pytest tears down here the fixtures that are still set up.
        with self.outside_tests():
            yield
        self.end_run()

    def end_run(self) -> None:
        self.try_force_flush()

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_protocol(self, item: Item) -> Iterator[None]:
        with self.outside_tests(), self._item_spans.running(item):
            yield

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_setup(self, item: Item) -> Generator[None, Result[object], None]:
        with self._item_spans.setting_up(item):
            outcome = yield
            # A test without fixtures gets the finalizer here.  A setup that
            # failed may have stopped before pytest reached the test, as it
            # does for a skip mark, and pytest then takes no finalizer for it.
            if outcome.exception is None:
                self._item_spans.mark_teardown()

    @pytest.hookimpl(hookwrapper=True)
    def pytest_fixture_setup(
        self, fixturedef: FixtureDef[Any], request: SubRequest
    ) -> Generator[None, Result[object], None]:
        yield from trace_fixture(tracer, self._item_spans, fixturedef, request)

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_call(self, item: Item) -> Iterator[None]:
        with self._item_spans.calling():
            yield

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_teardown(self, item: Item) -> Iterator[None]:
        with self._item_spans.tearing_down():
            yield

    @staticmethod
    def pytest_exception_interact(
        node: Node,
        call: CallInfo[Any],
        report: TestReport,
    ) -> None:
        excinfo = call.excinfo
        assert excinfo
        assert isinstance(excinfo.value, BaseException)

        test_span = trace.get_current_span()

        test_span.record_exception(
            # Interface says Exception, but BaseException seems to work fine
            # This is needed because pytest's Failed exception inherits from
            # BaseException, not Exception
            exception=excinfo.value,  # type: ignore[arg-type]
            attributes={
                EXCEPTION_STACKTRACE: str(report.longrepr),
            },
        )
        test_span.set_status(
            Status(
                status_code=StatusCode.ERROR,
                description=f"{excinfo.type}: {excinfo.value}",
            )
        )

    def pytest_runtest_logreport(self, report: TestReport) -> None:
        if report.when != "call":
            return

        has_error = report.outcome == "failed"
        status_code = StatusCode.ERROR if has_error else StatusCode.OK
        # The test's span has not started when another plugin runs the test
        # somewhere else and only reports on it here, and the current span is
        # then the parent of the tests.
        self._item_spans.start_deferred()
        trace.get_current_span().set_status(status_code)


class OpenTelemetryPlugin(PerTestOpenTelemetryPlugin):
    """A pytest plugin which produces OpenTelemetry spans around test sessions and
    individual test runs."""

    session_span: Span
    has_error: bool = False
    _session_name: str | None = None

    @property
    def session_name(self) -> str:
        # Lazy initialise session name
        if self._session_name is None:
            self._session_name = os.environ.get("PYTEST_RUN_NAME", "test run")
        return self._session_name

    @session_name.setter
    def session_name(self, name: str) -> None:
        self._session_name = name

    @property
    def item_parent(self) -> Context | None:
        return trace.set_span_in_context(self.session_span)

    def pytest_sessionstart(self, session: Session) -> None:
        self.session_span = tracer.start_span(
            self.session_name,
            context=self.trace_parent,
            attributes={
                "pytest.span_type": "run",
            },
        )
        self.has_error = False

    @pytest.hookimpl(hookwrapper=True)
    def pytest_collection(self, session: Session) -> Iterator[None]:
        # The span is current while pytest imports the test modules, so spans
        # that those imports create become its children, and an error that
        # stops a module from importing is recorded on it.
        with tracer.start_as_current_span(
            "collection",
            context=self.item_parent,
            attributes={
                "pytest.span_type": "collection",
            },
        ):
            yield

    def end_run(self) -> None:
        self.session_span.set_status(
            StatusCode.ERROR if self.has_error else StatusCode.OK
        )

        self.session_span.end()
        super().end_run()

    def pytest_collectreport(self, report: CollectReport) -> None:
        self.has_error |= report.failed

    def pytest_runtest_logreport(self, report: TestReport) -> None:
        super().pytest_runtest_logreport(report)
        # A test fails in its call, and errors in a fixture's setup or teardown.
        self.has_error |= report.failed


class XdistOpenTelemetryPlugin(OpenTelemetryPlugin):
    """An xdist-aware version of the OpenTelemetryPlugin"""

    @classmethod
    def get_trace_parent(cls, config: Config) -> Context | None:
        if workerinput := getattr(config, "workerinput", None):
            return propagate.extract(workerinput)

        return super().get_trace_parent(config)

    def pytest_configure(self, config: Config) -> None:
        super().pytest_configure(config)
        worker_id = getattr(config, "workerinput", {}).get("workerid")
        self.session_name = (
            f"test worker {worker_id}" if worker_id else self.session_name
        )

    @pytest.hookimpl(hookwrapper=True)
    def pytest_collection(self, session: Session) -> Iterator[None]:
        # The controller hands collection to its workers, and each worker
        # records its own collection span under its own session span.
        from xdist import (  # pyright: ignore[reportMissingTypeStubs]
            is_xdist_controller,
        )

        if is_xdist_controller(session):
            yield
        else:
            yield from super().pytest_collection(session)

    def pytest_configure_node(
        self, node: "WorkerController"
    ) -> None:  # pragma: no cover
        with trace.use_span(self.session_span, end_on_exit=False):
            propagate.inject(node.workerinput)  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]

    def pytest_xdist_node_collection_finished(
        self, node: "WorkerController", ids: list[str]
    ) -> None:  # pragma: no cover
        self.try_force_flush()
