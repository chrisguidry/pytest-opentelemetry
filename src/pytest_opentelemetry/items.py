import time
from collections.abc import Generator
from contextlib import ExitStack, contextmanager
from contextvars import Token

import pytest
from _pytest.nodes import Item
from opentelemetry import context, trace
from opentelemetry.context.context import Context
from opentelemetry.semconv._incubating.attributes.code_attributes import (  # pyright: ignore[reportMissingTypeStubs]
    CODE_FILEPATH,
    CODE_FUNCTION,
    CODE_LINENO,
)
from opentelemetry.trace import Span, Tracer

from .attributes import Attributes, parameter_attribute


def function_name(item: Item) -> str:
    """Gives the name of the function that a test runs.

    pytest adds the ID of a parametrized test's parameters to the test's name,
    and keeps the name of the function next to it.  The tests that other
    plugins collect, like tavern's, have only the one name."""
    if isinstance(item, pytest.Function):
        return item.originalname
    return item.name


def span_name(item: Item) -> str:
    """Names the span of a test with its node ID, without the ID of its
    parameters.

    The tests that pytest makes from one parametrized function then share a
    span name, so a tool that groups spans by name puts them together."""
    if isinstance(item, pytest.Function):
        parameters_id = item.name.removeprefix(item.originalname)
        return item.nodeid.removesuffix(parameters_id)
    return item.nodeid


def item_parameters(item: Item) -> dict[str, object]:
    """Finds the values that a test was parametrized with.

    pytest keeps them in the `callspec` of a parametrized function, both
    from `@pytest.mark.parametrize` and from a fixture's `params`, and
    tavern keeps them in `parametrize_vars` on its YAML tests."""
    parameters: dict[str, object] = {}
    if callspec := getattr(item, "callspec", None):
        parameters.update(callspec.params)
    parameters.update(getattr(item, "parametrize_vars", {}))
    return parameters


def item_attributes(item: Item) -> Attributes:
    filepath, line_number, _ = item.location
    attributes: Attributes = {
        CODE_FILEPATH: filepath,
        CODE_FUNCTION: function_name(item),
        "pytest.nodeid": item.nodeid,
        "pytest.span_type": "test",
    }
    # In some cases like tavern, line_number can be 0
    if line_number:
        attributes[CODE_LINENO] = line_number
    for name, value in item_parameters(item).items():
        attributes[f"pytest.param.{name}"] = parameter_attribute(value)
    return attributes


@contextmanager
def use_context(current: Context) -> Generator[None, None, None]:
    """Makes a context the current one."""
    token = context.attach(current)
    try:
        yield
    finally:
        context.detach(token)


class ItemSpans:
    """Starts and ends the spans for the test that pytest is running: one for
    the test, and under it one each for its setup, its call, and its teardown.

    The spans of a test cover only that test's own work.  pytest sets up a
    fixture of a wider scope at the start of the setup of the first test that
    uses it, and tears it down at the end of the teardown of the last.  So the
    test's span and its setup span start after pytest has set those fixtures
    up, and the test's span and its teardown span end before pytest tears them
    down.  Without this, the first and the last test of a module would include
    the time of every fixture that the whole module shares."""

    def __init__(self, tracer: Tracer) -> None:
        self._tracer = tracer
        self._name = ""
        self._attributes: Attributes = {}

        # The context for what is not the test's own work: the one that is
        # current when the test begins.
        self._outside = Context()

        # The names of the spans that have yet to start, outermost first, and
        # the time that they will start at.
        self._waiting: list[str] = []
        self._since = 0

        self._started: list[tuple[Span, Token[Context]]] = []

        # The time that the test's span ends at, when that is before the
        # moment pytest finishes with the test.
        self._ended_at: int | None = None

        self._teardown = ExitStack()
        self._tearing_down = False

    @contextmanager
    def running(self, item: Item) -> Generator[None, None, None]:
        """Covers everything pytest does for one test."""
        self._name = span_name(item)
        self._attributes = item_attributes(item)
        self._outside = context.get_current()
        self._ended_at = None
        self._wait(self._name)
        yield
        self._end(self._ended_at)

    @contextmanager
    def setting_up(self) -> Generator[None, None, None]:
        self._wait(f"{self._name}::setup")
        yield
        self._end()

    @contextmanager
    def calling(self) -> Generator[None, None, None]:
        with self._tracer.start_as_current_span(
            f"{self._name}::call", attributes=self._attributes
        ):
            yield

    @contextmanager
    def tearing_down(self) -> Generator[None, None, None]:
        self._ended_at = None
        with self._teardown:
            self._teardown.enter_context(
                self._tracer.start_as_current_span(
                    f"{self._name}::teardown", attributes=self._attributes
                )
            )
            self._tearing_down = True
            yield
            self._tearing_down = False

    def start(self) -> None:
        """Starts the spans that have yet to start, because the test's own work
        is about to.  They start at the time that work could first have
        started: when the setup began, or when the last fixture before it
        finished."""
        for name in self._waiting:
            span = self._tracer.start_span(
                name, attributes=self._attributes, start_time=self._since
            )
            token = context.attach(trace.set_span_in_context(span))
            self._started.append((span, token))
        self._waiting.clear()

    def postpone(self) -> None:
        """Moves the time that the spans yet to start will start at to now,
        because what ran until now was not the test's own work."""
        self._since = time.time_ns()

    def stop(self) -> None:
        """Ends the test's teardown, because what pytest tears down from now on
        outlived the test.  The test's span ends at this time too, and stays
        open for pytest to report on the test.

        Outside of a test's teardown there is nothing to end: a fixture that
        pytest tears down during a test's setup or call does so before the
        test's own work, or as a part of it."""
        if not self._tearing_down:
            return
        self._tearing_down = False
        self._teardown.close()
        self._ended_at = time.time_ns()
        self._teardown.enter_context(use_context(self._outside))

    def _wait(self, name: str) -> None:
        self._waiting.append(name)
        self._since = time.time_ns()

    def _end(self, end_time: int | None = None) -> None:
        self.start()
        span, token = self._started.pop()
        context.detach(token)
        span.end(end_time)
