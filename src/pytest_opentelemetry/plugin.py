from _pytest.config import Config
from _pytest.config.argparsing import Parser


def pytest_addoption(parser: Parser) -> None:
    parser.addoption("--export-traces", action="store_true", default=False)
    parser.addoption("--trace-parent", action="store", default=None)


def pytest_configure(config: Config) -> None:
    # pylint: disable=import-outside-toplevel
    from pytest_opentelemetry.instrumentation import OpenTelemetryPlugin

    config.pluginmanager.register(OpenTelemetryPlugin())
