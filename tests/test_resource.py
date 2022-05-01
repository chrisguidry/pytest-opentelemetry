import os
import re
import tempfile
from typing import Generator

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
    return CodebaseResourceDetector().detect()


def test_service_name_from_directory(bare_codebase: str, resource: Resource) -> None:
    assert resource.attributes['service.name'] == 'my-project'


def test_service_version_unknown(bare_codebase: str, resource: Resource) -> None:
    assert resource.attributes['service.version'] == '[unknown: not a git repository]'


@pytest.fixture
def broken_repo(bare_codebase: str) -> str:
    # making an empty .git directory will get us past the first check, but then
    # `git rev-parse HEAD` will fail
    os.makedirs('.git')
    return bare_codebase


def test_service_version_git_problems(broken_repo: str, resource: Resource) -> None:
    assert resource.attributes['service.version'] == (
        "[unknown: Command '['git', 'rev-parse', 'HEAD']' "
        "returned non-zero exit status 128.]"
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
