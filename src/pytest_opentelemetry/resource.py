import os
import subprocess
import sys
from typing import Dict, Union

from opentelemetry.semconv.resource import ResourceAttributes
from psutil import Process


def get_process_attributes() -> Dict[str, Union[str, bool, int, float]]:
    # https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/resource/semantic_conventions/process.md#process
    process = Process()
    with process.oneshot():
        command_line = process.cmdline()
        command, *arguments = command_line
        return {
            ResourceAttributes.PROCESS_PID: process.pid,
            ResourceAttributes.PROCESS_EXECUTABLE_NAME: process.name(),
            ResourceAttributes.PROCESS_EXECUTABLE_PATH: process.exe(),
            ResourceAttributes.PROCESS_COMMAND_LINE: ' '.join(command_line),
            ResourceAttributes.PROCESS_COMMAND: command,
            ResourceAttributes.PROCESS_COMMAND_ARGS: ' '.join(arguments),
            ResourceAttributes.PROCESS_OWNER: process.username(),
        }


def get_runtime_attributes() -> Dict[str, Union[str, bool, int, float]]:
    # https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/resource/semantic_conventions/process.md#python-runtimes
    version = sys.implementation.version
    version_string = ".".join(
        map(
            str,
            version[:3]
            if version.releaselevel == "final" and not version.serial
            else version,
        )
    )
    return {
        ResourceAttributes.PROCESS_RUNTIME_NAME: sys.implementation.name,
        ResourceAttributes.PROCESS_RUNTIME_VERSION: version_string,
        ResourceAttributes.PROCESS_RUNTIME_DESCRIPTION: sys.version,
    }


def get_codebase_attributes() -> Dict[str, Union[str, bool, int, float]]:
    return {
        ResourceAttributes.SERVICE_NAME: get_codebase_name(),
        ResourceAttributes.SERVICE_VERSION: get_codebase_version(),
    }


def get_codebase_name() -> str:
    # TODO: any better ways to guess the name of the codebase?
    # TODO: look into methods for locating packaging information
    return os.path.split(os.getcwd())[-1]


def get_codebase_version() -> str:
    if not os.path.exists('.git'):
        return '[unknown: not a git repository]'

    try:
        version = subprocess.check_output(['git', 'rev-parse', 'HEAD'])
    except Exception as e:  # pylint: disable=broad-except
        return f'[unknown: {str(e)}]'

    return version.decode().strip()
