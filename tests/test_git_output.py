import subprocess

import pytest
from _pytest.pytester import Pytester

from pytest_opentelemetry.resource import CodebaseResourceDetector


def test_no_output_outside_a_git_repository(
    pytester: Pytester, capfd: pytest.CaptureFixture[str]
) -> None:
    version = CodebaseResourceDetector.get_codebase_version()

    assert version == "[unknown: not a git repository]"
    assert capfd.readouterr() == ("", "")


def test_no_output_in_a_git_repository_without_commits(
    pytester: Pytester, capfd: pytest.CaptureFixture[str]
) -> None:
    subprocess.check_call(["git", "init", "--quiet"])

    version = CodebaseResourceDetector.get_codebase_version()

    assert version.startswith("[unknown: ")
    assert capfd.readouterr() == ("", "")
