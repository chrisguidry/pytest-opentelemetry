Attributes = dict[str, str | bool | int | float]

# The longest a parameter's value may be in a span attribute, in characters.
MAX_PARAMETER_LENGTH = 120


def parameter_attribute(value: object) -> str | bool | int | float:
    """Gives the value of a test's or a fixture's parameter as a span attribute.

    OpenTelemetry takes only strings, booleans, and numbers as attribute
    values, so any other value becomes its `repr()`.  A string longer than
    `MAX_PARAMETER_LENGTH` keeps its start and its end, with an ellipsis in
    place of the middle."""
    if isinstance(value, bool | int | float):
        return value
    text = value if isinstance(value, str) else safe_repr(value)
    if len(text) <= MAX_PARAMETER_LENGTH:
        return text
    head = MAX_PARAMETER_LENGTH // 2
    tail = MAX_PARAMETER_LENGTH - head - 1
    return f"{text[:head]}…{text[-tail:]}"


def safe_repr(value: object) -> str:
    """Gives the `repr()` of a value, or the one that every object has when
    the value's own raises.  A parameter that cannot describe itself must not
    stop the test run."""
    try:
        return repr(value)
    except Exception:
        return object.__repr__(value)
