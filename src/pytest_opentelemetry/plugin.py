# pylint: disable=import-outside-toplevel


def pytest_addoption(parser):  # pragma: no cover
    parser.addoption("--export-traces", action="store_true", default=False)


def pytest_configure(config):  # pragma: no cover
    from pytest_opentelemetry.instrumentation import OpenTelemetryPlugin

    config.pluginmanager.register(OpenTelemetryPlugin())
