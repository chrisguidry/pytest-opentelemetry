from collections.abc import Generator
from contextlib import ExitStack
from types import CodeType
from typing import Any

import pytest
from _pytest.fixtures import FixtureDef, SubRequest
from _pytest.python import get_direct_param_fixture_func
from opentelemetry.semconv._incubating.attributes.code_attributes import (  # pyright: ignore[reportMissingTypeStubs]
    CODE_FILEPATH,
    CODE_FUNCTION,
    CODE_LINENO,
)
from opentelemetry.trace import Span, Status, StatusCode, Tracer
from pluggy import Result

from .attributes import Attributes, parameter_attribute
from .items import ItemSpans

# Stands for the parameter of a fixture that has none, because None can be a
# fixture's parameter.
NO_PARAMETER = object()


def trace_fixture(
    tracer: Tracer,
    item_spans: ItemSpans,
    fixturedef: FixtureDef[Any],
    request: SubRequest,
) -> Generator[None, Result[object], None]:
    """Makes the spans for the setup and the teardown of one fixture, as a
    wrapper of pytest_fixture_setup.

    Each span is current while its half of the fixture runs, so the spans that
    the fixture creates are its children.  A span's parent is the span that is
    current when it starts.  For a fixture that pytest sets up for one test,
    that is the setup or the teardown span of the test.  For a fixture that
    tests share, it is the parent of the tests, because `ItemSpans` keeps the
    test's spans from being current while pytest sets those fixtures up and
    tears them down."""
    # pytest gives each argument of a parametrized test to the test through a
    # fixture that only returns the argument, which the test's spans have as
    # an attribute.
    if fixturedef.func is get_direct_param_fixture_func:
        yield
        return

    name = fixturedef.argname
    attributes = fixture_attributes(fixturedef, request)
    teardown = ExitStack()

    def start_teardown() -> None:
        teardown.enter_context(
            tracer.start_as_current_span(f"{name} teardown", attributes=attributes)
        )

    # pytest has no hook for the start of a fixture's teardown, but it runs a
    # fixture's finalizers from the last one added to the first.  These two go
    # on before and after everything the fixture itself adds while it sets up,
    # so they run after and before the fixture's own teardown.
    request.addfinalizer(teardown.close)

    item_spans.mark_teardown()
    # The scope that a fixture declares does not say whether tests share it.
    # pytest sets up a class-scoped fixture for each test that is not in a
    # class, and the node of the request is then the test itself.
    if isinstance(request.node, pytest.Item):
        item_spans.start_deferred()
    with tracer.start_as_current_span(f"{name} setup", attributes=attributes) as span:
        outcome = yield
        record_error(span, outcome.exception)
    item_spans.postpone()

    # A fixture that did not set up has no teardown of its own.
    if outcome.exception is None:
        request.addfinalizer(start_teardown)


def fixture_attributes(fixturedef: FixtureDef[Any], request: SubRequest) -> Attributes:
    attributes: Attributes = {
        CODE_FUNCTION: fixturedef.argname,
        "pytest.fixture_scope": fixturedef.scope,
        "pytest.span_type": "fixture",
    }
    if code := code_from_fixturedef(fixturedef):
        attributes[CODE_FILEPATH] = code.co_filename
        attributes[CODE_LINENO] = code.co_firstlineno
    # pytest sets `param` on the request only for a fixture with a parameter,
    # whether from the fixture's `params` or from a test that parametrizes it.
    parameter = getattr(request, "param", NO_PARAMETER)
    if parameter is not NO_PARAMETER:
        attributes[f"pytest.param.{fixturedef.argname}"] = parameter_attribute(
            parameter
        )
    return attributes


def code_from_fixturedef(fixturedef: FixtureDef[Any]) -> CodeType | None:
    """Finds the Python code that a fixture runs, when there is any.

    pytest accepts any callable as a fixture.  A function has its own code,
    an instance of a class with a `__call__` method has that method's code,
    and a callable implemented in C has none."""
    for candidate in (fixturedef.func, type(fixturedef.func).__call__):
        if code := getattr(candidate, "__code__", None):
            return code
    return None


def record_error(span: Span, exception: BaseException | None) -> None:
    """Records the exception that stopped a fixture's setup on the fixture's
    span.

    pytest reports the error against the test that asked for the fixture.  The
    span of a fixture of a wider scope is not inside that test, so it has to
    show the error itself.  A fixture that skips the test, or that expects it
    to fail, has not failed."""
    if exception is None or isinstance(
        exception, pytest.skip.Exception | pytest.xfail.Exception
    ):
        return
    span.record_exception(exception)
    span.set_status(
        Status(StatusCode.ERROR, f"{type(exception).__name__}: {exception}")
    )
