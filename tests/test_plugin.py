import pytest
from _pytest.config import Config
from _pytest.pytester import Pytester
from packaging.version import Version

import pytest_opentelemetry.plugin
from pytest_opentelemetry import __version__
from pytest_opentelemetry.instrumentation import (
    OpenTelemetryPlugin,
    PerTestOpenTelemetryPlugin,
    XdistOpenTelemetryPlugin,
)


def test_version_is_sane() -> None:
    assert __version__
    assert Version(__version__)
    assert Version(__version__) > Version("0.4.0")  # before we introduced __version__


def test_plugin_is_loaded(pytestconfig: Config) -> None:
    plugin = pytestconfig.pluginmanager.get_plugin("pytest_opentelemetry")
    assert plugin is pytest_opentelemetry.plugin
    assert plugin


@pytest.mark.parametrize(
    "args, expected",
    [
        pytest.param([], XdistOpenTelemetryPlugin, id="xdist"),
        pytest.param(["-p", "no:xdist"], OpenTelemetryPlugin, id="no-xdist"),
        pytest.param(
            ["--trace-per-test"], PerTestOpenTelemetryPlugin, id="trace-per-test"
        ),
    ],
)
def test_instrumentation_is_registered_by_name(
    pytester: Pytester, args: list[str], expected: type
) -> None:
    config = pytester.parseconfigure(*args)
    assert type(config.pluginmanager.get_plugin("opentelemetry")) is expected
