import os
import subprocess
from typing import Dict, Union

from opentelemetry.sdk.resources import Resource, ResourceDetector
from opentelemetry.semconv.resource import ResourceAttributes

Attributes = Dict[str, Union[str, bool, int, float]]


class CodebaseResourceDetector(ResourceDetector):
    """Detects OpenTelemetry Resource attributes for an operating system process,
    providing the `process.*` attributes"""

    @staticmethod
    def get_codebase_name() -> str:
        # TODO: any better ways to guess the name of the codebase?
        # TODO: look into methods for locating packaging information
        return os.path.split(os.getcwd())[-1]

    @staticmethod
    def get_codebase_version() -> str:
        if not os.path.exists('.git'):
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
