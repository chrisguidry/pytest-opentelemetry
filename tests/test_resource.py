import os
import re
import subprocess
import tempfile
from typing import Generator
from unittest.mock import MagicMock, Mock, patch

import pytest
from opentelemetry.sdk.resources import Resource

from pytest_opentelemetry.resource import CodebaseResourceDetector


@pytest.fixture
def bare_codebase() -> Generator[str, None, None]:
    previous = os.getcwd()
    with tempfile.TemporaryDirectory() as directory:
        project_path = os.path.join(directory, 'my-project')
        os.makedirs(project_path)
        os.chdir(project_path)
        try:
            yield project_path
        finally:
            os.chdir(previous)


@pytest.fixture
def resource() -> Resource:
    return CodebaseResourceDetector(Mock()).detect()


@pytest.fixture
def config() -> MagicMock:
    config = MagicMock()
    config.getini.return_value = ''
    config.getoption.return_value = None
    config.rootpath.name = None
    return config


def test_codebase_name_from_suite_name(config: MagicMock) -> None:
    config.getini.return_value = 'my-project'
    assert CodebaseResourceDetector(config).get_codebase_name() == 'my-project'


def test_codebase_name_from_junit_prefix(config: MagicMock) -> None:
    config.getoption.return_value = 'my-project'
    assert CodebaseResourceDetector(config).get_codebase_name() == 'my-project'


def test_codebase_name_from_root_path(config: MagicMock) -> None:
    config.rootpath.name = 'my-project'
    assert CodebaseResourceDetector(config).get_codebase_name() == 'my-project'


def test_codebase_name_without_the_junitxml_plugin(config: MagicMock) -> None:
    config.getini.side_effect = ValueError('unknown configuration value')
    config.rootpath.name = 'my-project'
    assert CodebaseResourceDetector(config).get_codebase_name() == 'my-project'


def test_service_version_unknown(bare_codebase: str, resource: Resource) -> None:
    assert resource.attributes['service.version'] == '[unknown: not a git repository]'


def test_service_version_git_problems() -> None:
    with patch(
        'pytest_opentelemetry.resource.subprocess.check_output',
        side_effect=[
            b'true',
            subprocess.CalledProcessError(128, ['git', 'rev-parse', 'HEAD']),
        ],
    ):
        resource = CodebaseResourceDetector(Mock()).detect()
        assert resource.attributes['service.version'] == (
            "[unknown: Command '['git', 'rev-parse', 'HEAD']' "
            "returned non-zero exit status 128.]"
        )
    with patch(
        'pytest_opentelemetry.resource.subprocess.check_output', side_effect=[b'false']
    ):
        resource = CodebaseResourceDetector(Mock()).detect()
        assert resource.attributes['service.version'] == (
            "[unknown: not a git repository]"
        )


@pytest.fixture
def git_repo(bare_codebase: str) -> str:
    if os.system('which git') > 0:  # pragma: no cover
        pytest.skip('No git available on path')

    with open('README.md', 'w', encoding='utf-8') as readme:
        readme.write('# hi!\n')

    os.system('git init')
    os.system('git config user.email "testing@example.com"')
    os.system('git config user.name "Testy McTesterson"')
    os.system('git add README.md')
    os.system('git commit --message="Saying hi!"')

    return bare_codebase


def test_service_version_from_git_revision(git_repo: str, resource: Resource) -> None:
    version = resource.attributes['service.version']
    assert isinstance(version, str)
    assert len(version) == 40
    assert re.match(r'[\da-f]{40}', version)
