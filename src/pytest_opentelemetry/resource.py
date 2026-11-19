import subprocess

from opentelemetry.sdk.resources import Resource, ResourceDetector
from opentelemetry.semconv.attributes.service_attributes import (
    SERVICE_NAME,
    SERVICE_VERSION,
)
from pytest import Config

Attributes = dict[str, str | bool | int | float]


JUNIT_SUITE_NAME_DEFAULT = "pytest"


class CodebaseResourceDetector(ResourceDetector):
    """Detects OpenTelemetry Resource attributes for an operating system process,
    providing the `process.*` attributes"""

    def __init__(self, config: Config):
        self.config = config
        ResourceDetector.__init__(self)

    def get_suite_name(self) -> str:
        """Get the junit_suite_name setting when the project has set one.

        The setting exists only while the junitxml plugin is enabled, and that
        plugin's default for it is "pytest".  pytest does not say whether a
        value came from the project or from the default, so a suite named
        "pytest" counts as not set; otherwise every project without the setting
        would be named "pytest"."""
        try:
            name = str(self.config.getini("junit_suite_name"))
        except ValueError:
            return ""
        return "" if name == JUNIT_SUITE_NAME_DEFAULT else name

    def get_codebase_name(self) -> str:
        """Get the name of the codebase.

        In order of preference:
        junit_suite_name
        --junitprefix
        rootpath: Guaranteed to exist, the reference used to construct nodeid
        """
        return str(
            self.get_suite_name()
            or self.config.getoption("--junitprefix", None)
            or self.config.rootpath.name
        )

    @staticmethod
    def get_codebase_version() -> str:
        # git explains each failure on stderr, which would print on every test
        # run outside a repository.  The returned version says what failed.
        try:
            response = subprocess.check_output(
                ["git", "rev-parse", "--is-inside-work-tree"],
                stderr=subprocess.DEVNULL,
            )
            if response.strip() != b"true":
                return "[unknown: not a git repository]"
        except Exception:  # pylint: disable=broad-except
            return "[unknown: not a git repository]"

        try:
            version = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
            )
        except Exception as exception:  # pylint: disable=broad-except
            return f"[unknown: {exception!s}]"

        return version.decode().strip()

    def detect(self) -> Resource:
        return Resource(
            {
                SERVICE_NAME: self.get_codebase_name(),
                SERVICE_VERSION: self.get_codebase_version(),
            }
        )
