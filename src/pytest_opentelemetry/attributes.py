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
    text = value if isinstance(value, str) else repr(value)
    if len(text) <= MAX_PARAMETER_LENGTH:
        return text
    head = MAX_PARAMETER_LENGTH // 2
    tail = MAX_PARAMETER_LENGTH - head - 1
    return f"{text[:head]}…{text[-tail:]}"
