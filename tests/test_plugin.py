import pytest_opentelemetry.plugin


def test_plugin_is_loaded(pytestconfig):
    plugin = pytestconfig.pluginmanager.get_plugin('pytest_opentelemetry')
    assert plugin is pytest_opentelemetry.plugin
    assert plugin
