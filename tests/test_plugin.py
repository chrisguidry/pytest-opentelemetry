from _pytest.config import Config
from packaging.version import Version

import pytest_opentelemetry.plugin
from pytest_opentelemetry import __version__


def test_version_is_sane() -> None:
    assert __version__
    assert Version(__version__)
    assert Version(__version__) > Version('0.4.0')  # before we introduced __version__


def test_plugin_is_loaded(pytestconfig: Config) -> None:
    plugin = pytestconfig.pluginmanager.get_plugin('pytest_opentelemetry')
    assert plugin is pytest_opentelemetry.plugin
    assert plugin
