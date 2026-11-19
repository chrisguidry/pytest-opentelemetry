import pytest
from _pytest.pytester import Pytester

from pytest_opentelemetry.resource import CodebaseResourceDetector


def service_name(config: pytest.Config) -> object:
    return CodebaseResourceDetector(config).detect().attributes["service.name"]


def test_service_name_defaults_to_the_project_directory(pytester: Pytester) -> None:
    config = pytester.parseconfig()
    assert service_name(config) == pytester.path.name


def test_service_name_from_the_junit_suite_name(pytester: Pytester) -> None:
    pytester.makeini("""
        [pytest]
        junit_suite_name = my-suite
    """)
    config = pytester.parseconfig()
    assert service_name(config) == "my-suite"


def test_service_name_from_the_junit_prefix(pytester: Pytester) -> None:
    config = pytester.parseconfig("--junitprefix", "my-prefix")
    assert service_name(config) == "my-prefix"


def test_service_name_prefers_the_junit_suite_name(pytester: Pytester) -> None:
    config = pytester.parseconfig(
        "-o", "junit_suite_name=my-suite", "--junitprefix", "my-prefix"
    )
    assert service_name(config) == "my-suite"


def test_service_name_without_the_junitxml_plugin(pytester: Pytester) -> None:
    config = pytester.parseconfig("-p", "no:junitxml")
    assert service_name(config) == pytester.path.name
