import os
import re
import sys
import tempfile

import pytest

from pytest_opentelemetry import resource


def test_process_attributes():
    attributes = resource.get_process_attributes()
    assert set(attributes.keys()) == {
        'process.pid',
        'process.executable.name',
        'process.executable.path',
        'process.command_line',
        'process.command',
        'process.command_args',
        'process.owner',
    }
    assert all(isinstance(value, (str, int)) for value in attributes.values())

    assert attributes['process.pid'] == os.getpid()
    assert 'pytest' in attributes['process.command_line']

    expected_command_line = (
        attributes['process.command'] + ' ' + attributes['process.command_args']
    )
    assert attributes['process.command_line'] == expected_command_line.strip()


def test_runtime_attributes():
    attributes = resource.get_runtime_attributes()
    assert set(attributes.keys()) == {
        'process.runtime.name',
        'process.runtime.version',
        'process.runtime.description',
    }
    assert all(isinstance(value, (str, int)) for value in attributes.values())

    assert attributes['process.runtime.name'] == sys.implementation.name
    assert attributes['process.runtime.description'] == sys.version


@pytest.fixture
def bare_codebase():
    previous = os.getcwd()
    with tempfile.TemporaryDirectory() as directory:
        project_path = os.path.join(directory, 'my-project')
        os.makedirs(project_path)
        os.chdir(project_path)
        try:
            yield project_path
        finally:
            os.chdir(previous)


def test_service_name_from_directory(bare_codebase):
    attributes = resource.get_codebase_attributes()
    assert attributes['service.name'] == 'my-project'


def test_service_version_unknown(bare_codebase):
    attributes = resource.get_codebase_attributes()
    assert attributes['service.version'] == '[unknown: not a git repository]'


@pytest.fixture
def broken_git_directory(bare_codebase):
    # making an empty .git directory will get us past the first check, but then
    # `git rev-parse HEAD` will fail
    os.makedirs('.git')
    return bare_codebase


def test_service_version_git_problems(broken_git_directory):
    attributes = resource.get_codebase_attributes()
    assert attributes['service.version'] == (
        "[unknown: Command '['git', 'rev-parse', 'HEAD']' "
        "returned non-zero exit status 128.]"
    )


@pytest.fixture
def git_repo_codebase(bare_codebase):
    if os.system('which git') > 0:  # pragma: no cover
        pytest.skip(reason='No git available on path')

    with open('README.md', 'w', encoding='utf-8') as readme:
        readme.write('# hi!\n')

    os.system('git init')
    os.system('git add README.md')
    os.system('git commit --message="Saying hi!"')

    return bare_codebase


def test_service_version_from_git_revision(git_repo_codebase):
    attributes = resource.get_codebase_attributes()
    version = attributes['service.version']
    assert len(version) == 40
    assert re.match(r'[\da-f]{40}', version)
