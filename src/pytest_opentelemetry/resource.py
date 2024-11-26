import subprocess
from typing import Dict, Union

from opentelemetry.sdk.resources import Resource, ResourceDetector
from opentelemetry.semconv.resource import ResourceAttributes
from pytest import Config

Attributes = Dict[str, Union[str, bool, int, float]]


class CodebaseResourceDetector(ResourceDetector):
    """Detects OpenTelemetry Resource attributes for an operating system process,
    providing the `process.*` attributes"""

    def __init__(self, config: Config):
        self.config = config
        ResourceDetector.__init__(self)

    def get_codebase_name(self) -> str:
        """Get the name of the codebase.

        In order of preference:
        junit_suite_name
        --junitprefix
        rootpath: Guaranteed to exist, the reference used to construct nodeid
        """
        return str(
            self.config.inicfg.get('junit_suite_name')
            or self.config.getoption("--junitprefix", None)
            or self.config.rootpath.name
        )

    @staticmethod
    def get_codebase_version() -> str:
        try:
            response = subprocess.check_output(
                ['git', 'rev-parse', '--is-inside-work-tree']
            )
            if response.strip() != b'true':
                return '[unknown: not a git repository]'
        except Exception:  # pylint: disable=broad-except
            return '[unknown: not a git repository]'

        try:
            version = subprocess.check_output(['git', 'rev-parse', 'HEAD'])
        except Exception as exception:  # pylint: disable=broad-except
            return f'[unknown: {str(exception)}]'

        return version.decode().strip()

    def detect(self) -> Resource:
        return Resource(
            {
                ResourceAttributes.SERVICE_NAME: self.get_codebase_name(),
                ResourceAttributes.SERVICE_VERSION: self.get_codebase_version(),
            }
        )
