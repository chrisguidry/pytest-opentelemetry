import os
from collections.abc import Iterator
from types import CodeType
from typing import TYPE_CHECKING, Any

import pytest
from _pytest.config import Config
from _pytest.fixtures import FixtureDef, FixtureRequest, SubRequest
from _pytest.main import Session
from _pytest.nodes import Item, Node
from _pytest.reports import TestReport
from _pytest.runner import CallInfo
from opentelemetry import propagate, trace
from opentelemetry.context.context import Context
from opentelemetry.sdk.resources import OTELResourceDetector, ResourceDetector
from opentelemetry.semconv._incubating.attributes.code_attributes import (  # pyright: ignore[reportMissingTypeStubs]
    CODE_FILEPATH,
    CODE_FUNCTION,
    CODE_LINENO,
)
from opentelemetry.semconv.attributes.exception_attributes import EXCEPTION_STACKTRACE
from opentelemetry.trace import Span, Status, StatusCode, Tracer
from opentelemetry_container_distro import (
    OpenTelemetryContainerConfigurator,
    OpenTelemetryContainerDistro,
)

from .resource import CodebaseResourceDetector

if TYPE_CHECKING:
    from xdist.workermanage import (  # pyright: ignore[reportMissingTypeStubs]
        WorkerController,
    )

tracer: Tracer = trace.get_tracer("pytest-opentelemetry")


def use_real_time_under_freezegun() -> None:
    """Tells freezegun, when it is installed, to give OpenTelemetry the real time.

    freezegun replaces the clock that OpenTelemetry reads for a span's start and
    end.  A span that starts before a test freezes time and ends while time is
    frozen gets a negative duration, and a span that both starts and ends in
    frozen time gets a duration of zero."""
    try:
        import freezegun
    except ImportError:
        return

    freezegun.configure(extend_ignore_list=["opentelemetry"])


class PerTestOpenTelemetryPlugin:
    """base logic for all otel pytest integration"""

    trace_parent: Context | None = None

    # The span for the fixture that pytest tears down next, while a test's
    # teardown is running.
    _fixture_teardown_span: Span | None = None

    @property
    def item_parent(self) -> Context | None:
        return self.trace_parent

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

        # This can't be tested both ways in one process
        if config.getoption("--export-traces"):  # pragma: no cover
            OpenTelemetryContainerDistro().configure()  # pyright: ignore[reportUnknownMemberType]

        configurator = OpenTelemetryContainerConfigurator()
        detectors: list[ResourceDetector] = configurator.resource_detectors  # pyright: ignore[reportAssignmentType]
        detectors.append(CodebaseResourceDetector(config))
        detectors.append(OTELResourceDetector())
        configurator.configure()  # pyright: ignore[reportUnknownMemberType]

    def pytest_sessionfinish(self, session: Session) -> None:
        self.try_force_flush()

    def _attributes_from_item(self, item: Item) -> dict[str, str | int]:
        filepath, line_number, _ = item.location
        attributes: dict[str, str | int] = {
            CODE_FILEPATH: filepath,
            CODE_FUNCTION: item.name,
            "pytest.nodeid": item.nodeid,
            "pytest.span_type": "test",
        }
        # In some cases like tavern, line_number can be 0
        if line_number:
            attributes[CODE_LINENO] = line_number
        return attributes

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_protocol(self, item: Item) -> Iterator[None]:
        with tracer.start_as_current_span(
            item.nodeid,
            attributes=self._attributes_from_item(item),
            context=self.item_parent,
        ):
            yield

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_setup(self, item: Item) -> Iterator[None]:
        with tracer.start_as_current_span(
            f"{item.nodeid}::setup",
            attributes=self._attributes_from_item(item),
        ):
            yield

    def _attributes_from_fixturedef(
        self, fixturedef: FixtureDef[Any]
    ) -> dict[str, str | int]:
        attributes: dict[str, str | int] = {
            CODE_FUNCTION: fixturedef.argname,
            "pytest.fixture_scope": fixturedef.scope,
            "pytest.span_type": "fixture",
        }
        if code := self._code_from_fixturedef(fixturedef):
            attributes[CODE_FILEPATH] = code.co_filename
            attributes[CODE_LINENO] = code.co_firstlineno
        return attributes

    @staticmethod
    def _code_from_fixturedef(fixturedef: FixtureDef[Any]) -> CodeType | None:
        """Finds the Python code that a fixture runs, when there is any.

        pytest accepts any callable as a fixture.  A function has its own code,
        an instance of a class with a `__call__` method has that method's code,
        and a callable implemented in C has none."""
        for candidate in (fixturedef.func, type(fixturedef.func).__call__):
            if code := getattr(candidate, "__code__", None):
                return code
        return None

    def _name_from_fixturedef(
        self, fixturedef: FixtureDef[Any], request: FixtureRequest
    ) -> str:
        if fixturedef.params and "request" in fixturedef.argnames:
            try:
                parameter = str(request.param)
            except Exception:
                parameter = str(
                    request.param_index if isinstance(request, SubRequest) else "?"
                )
            return f"{fixturedef.argname}[{parameter}]"
        return fixturedef.argname

    @pytest.hookimpl(hookwrapper=True)
    def pytest_fixture_setup(
        self, fixturedef: FixtureDef[Any], request: FixtureRequest
    ) -> Iterator[None]:
        with tracer.start_as_current_span(
            name=f"{self._name_from_fixturedef(fixturedef, request)} setup",
            attributes=self._attributes_from_fixturedef(fixturedef),
        ):
            yield

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_call(self, item: Item) -> Iterator[None]:
        with tracer.start_as_current_span(
            name=f"{item.nodeid}::call",
            attributes=self._attributes_from_item(item),
        ):
            yield

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_teardown(self, item: Item) -> Iterator[None]:
        with tracer.start_as_current_span(
            name=f"{item.nodeid}::teardown",
            attributes=self._attributes_from_item(item),
        ):
            # Since there is no pytest_fixture_teardown hook, we have to be a
            # little clever to capture the spans for each fixture's teardown.
            # The pytest_fixture_post_finalizer hook is called at the end of a
            # fixture's teardown, but we don't know when the fixture actually
            # began tearing down.
            #
            # Instead start a span here for the first fixture to be torn down,
            # but give it a temporary name, since we don't know which fixture it
            # will be. Then, in pytest_fixture_post_finalizer, when we do know
            # which fixture is being torn down, update the name and attributes
            # to the actual fixture, end the span, and create the span for the
            # next fixture in line to be torn down.
            self._fixture_teardown_span = tracer.start_span("fixture teardown")
            yield

        # The last call to pytest_fixture_post_finalizer will create
        # a span that is unneeded, so drop it.
        self._fixture_teardown_span = None

    @pytest.hookimpl(hookwrapper=True)
    def pytest_fixture_post_finalizer(
        self, fixturedef: FixtureDef[Any], request: SubRequest
    ) -> Iterator[None]:
        """When the span for a fixture teardown is created by
        pytest_runtest_teardown or a previous pytest_fixture_post_finalizer, we
        need to update the name and attributes now that we know which fixture it
        was for."""

        # If the fixture has already been torn down, then it will have no cached
        # result, so we can skip this one. pytest 9 tears fixtures down before
        # this hook, so only earlier pytests reach this branch.
        if (
            fixturedef.cached_result is None
            or (span := self._fixture_teardown_span) is None
        ):  # pragma: no cover
            yield
        else:
            # If we've gotten here, we have a real fixture about to be torn down.
            name = f"{self._name_from_fixturedef(fixturedef, request)} teardown"
            span.update_name(name)
            span.set_attributes(self._attributes_from_fixturedef(fixturedef))
            yield
            span.end()

        # Create the span for the next fixture to be torn down. When there are
        # no more fixtures remaining, this will be an empty, useless span, so it
        # needs to be dropped by pytest_runtest_teardown.
        self._fixture_teardown_span = tracer.start_span("fixture teardown")

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

    def pytest_sessionfinish(self, session: Session) -> None:
        self.session_span.set_status(
            StatusCode.ERROR if self.has_error else StatusCode.OK
        )

        self.session_span.end()
        super().pytest_sessionfinish(session)

    def pytest_runtest_logreport(self, report: TestReport) -> None:
        super().pytest_runtest_logreport(report)
        self.has_error |= report.when == "call" and report.outcome == "failed"


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
