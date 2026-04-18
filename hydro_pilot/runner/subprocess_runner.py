import os
import shlex
import subprocess

from ..errors import RunError
from .base import ModelRunner


class SubprocessRunner(ModelRunner):
    """Runs a model via subprocess."""

    def run(self, work_path: str, command, timeout: int) -> int:
        cmd = self._build_command(work_path, command)
        effective_timeout = timeout if timeout > 0 else None

        process = subprocess.Popen(
            cmd,
            cwd=work_path,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        try:
            stdout, stderr = process.communicate(timeout=effective_timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise RunError(
                stage="subprocess",
                code="TIMEOUT",
                target="simulation",
                message=f"Simulation timed out after {effective_timeout}s"
            )

        if process.returncode != 0:
            stderr_tail = stderr[-500:] if stderr else ""
            raise RunError(
                stage="subprocess",
                code="NONZERO_EXIT",
                target="simulation",
                message=f"Return code {process.returncode}; stderr={stderr_tail}"
            )

        return process.returncode

    @staticmethod
    def _build_command(work_path: str, raw_cmd):
        if isinstance(raw_cmd, (list, tuple)):
            cmd = list(raw_cmd)
        else:
            cmd = shlex.split(str(raw_cmd))

        if not cmd:
            raise ValueError("command is empty")

        if not os.path.isabs(cmd[0]):
            cmd[0] = os.path.join(work_path, cmd[0])

        return cmd
