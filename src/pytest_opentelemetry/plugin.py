from _pytest.config import Config
from _pytest.config.argparsing import Parser


def pytest_addoption(parser: Parser) -> None:
    group = parser.getgroup('pytest-opentelemetry', 'OpenTelemetry for test runs')
    group.addoption(
        "--export-traces",
        action="store_true",
        default=False,
        help=(
            'Enables exporting of OpenTelemetry traces via OTLP, by default to '
            'http://localhost:4317.  Set the OTEL_EXPORTER_OTLP_ENDPOINT environment '
            'variable to specify an alternative endpoint.'
        ),
    )
    group.addoption(
        "--trace-parent",
        action="store",
        default=None,
        help=(
            'Specify a trace parent for this pytest run, in the form of a W3C '
            'traceparent header, like '
            '00-1234567890abcdef1234567890abcdef-fedcba0987654321-01.  If a trace '
            'parent is provided, this test run will appear as a span within that '
            'trace.  If it is omitted, this test run will start a new trace.'
        ),
    )


def pytest_configure(config: Config) -> None:
    # pylint: disable=import-outside-toplevel
    from pytest_opentelemetry.instrumentation import OpenTelemetryPlugin

    config.pluginmanager.register(OpenTelemetryPlugin())
