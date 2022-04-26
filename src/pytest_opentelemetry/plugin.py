# pylint: disable=import-outside-toplevel


def pytest_configure(config):  # pragma: no cover
    from pytest_opentelemetry.instrumentation import OpenTelemetryPlugin

    config.pluginmanager.register(OpenTelemetryPlugin())
