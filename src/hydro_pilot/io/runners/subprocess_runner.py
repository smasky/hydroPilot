import os
from pathlib import Path
import shlex
import shutil
import subprocess
from collections.abc import Sequence

from ...runtime.errors import RunError
from .base import ModelRunner


class SubprocessRunner(ModelRunner):
    """Runs a model via subprocess."""

    STDOUT_LOG = "runner.stdout.log"
    STDERR_LOG = "runner.stderr.log"
    TAIL_BYTES = 500

    def run(self, work_path: str, command: str | Sequence[str], timeout: int) -> int:
        cmd = self._build_command(work_path, command)
        effective_timeout = timeout if timeout > 0 else None
        stdout_path, stderr_path = self._log_paths(work_path)

        with open(stdout_path, "wb") as stdout_file, open(stderr_path, "wb") as stderr_file:
            try:
                process = subprocess.Popen(
                    cmd,
                    cwd=work_path,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    **self._popen_session_kwargs(),
                )
            except FileNotFoundError as exc:
                raise RunError(
                    stage="subprocess",
                    code="EXECUTABLE_NOT_FOUND",
                    target="simulation",
                    message=(
                        f"Executable not found: {cmd[0]}. "
                        f"Command={self._display_command(cmd)}"
                    ),
                ) from exc
            except OSError as exc:
                raise RunError(
                    stage="subprocess",
                    code="SPAWN_FAILED",
                    target="simulation",
                    message=(
                        f"Failed to start command {self._display_command(cmd)}: {exc}"
                    ),
                ) from exc

            try:
                process.communicate(timeout=effective_timeout)
            except subprocess.TimeoutExpired:
                self._terminate_process_tree(process)
                process.communicate()
                raise RunError(
                    stage="subprocess",
                    code="TIMEOUT",
                    target="simulation",
                    message=(
                        f"Simulation timed out after {effective_timeout}s; "
                        f"stdout={stdout_path}; stderr={stderr_path}; "
                        f"stderr_tail={self._tail_text(stderr_path)}"
                    ),
                )

        if process.returncode != 0:
            raise RunError(
                stage="subprocess",
                code="NONZERO_EXIT",
                target="simulation",
                message=(
                    f"Return code {process.returncode}; "
                    f"stdout={stdout_path}; stderr={stderr_path}; "
                    f"stderr_tail={self._tail_text(stderr_path)}; "
                    f"stdout_tail={self._tail_text(stdout_path)}"
                ),
            )

        return process.returncode

    @staticmethod
    def _build_command(work_path: str, raw_cmd: str | Sequence[str]) -> list[str]:
        if isinstance(raw_cmd, Sequence) and not isinstance(raw_cmd, str):
            cmd = [str(part) for part in raw_cmd]
        else:
            cmd = SubprocessRunner._split_command(str(raw_cmd))

        if not cmd:
            raise ValueError("command is empty")

        candidate = Path(work_path) / SubprocessRunner._strip_wrapping_quotes(cmd[0])
        if not os.path.isabs(cmd[0]) and candidate.exists():
            cmd[0] = str(candidate)

        return cmd

    @staticmethod
    def _split_command(raw_cmd: str) -> list[str]:
        if os.name == "nt":
            return [SubprocessRunner._strip_wrapping_quotes(part) for part in shlex.split(raw_cmd, posix=False)]
        return shlex.split(raw_cmd)

    @staticmethod
    def _strip_wrapping_quotes(value: str) -> str:
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            return value[1:-1]
        return value

    @classmethod
    def _log_paths(cls, work_path: str) -> tuple[Path, Path]:
        base = Path(work_path)
        return base / cls.STDOUT_LOG, base / cls.STDERR_LOG

    @classmethod
    def log_paths(cls, work_path: str) -> tuple[Path, Path]:
        return cls._log_paths(work_path)

    @staticmethod
    def _display_command(cmd: Sequence[str]) -> str:
        if os.name == "nt":
            return subprocess.list2cmdline(list(cmd))
        return shlex.join(list(cmd))

    @staticmethod
    def _popen_session_kwargs() -> dict:
        if os.name == "nt":
            return {
                "creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            }
        return {"start_new_session": True}

    @staticmethod
    def _terminate_process_tree(process: subprocess.Popen) -> None:
        if process.poll() is not None:
            return

        if os.name == "nt":
            taskkill = shutil.which("taskkill")
            if taskkill:
                subprocess.run(
                    [taskkill, "/T", "/F", "/PID", str(process.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            else:
                process.kill()
            return

        try:
            os.killpg(process.pid, 9)
        except Exception:
            process.kill()

    @classmethod
    def _tail_text(cls, path: Path) -> str:
        if not path.exists():
            return ""
        data = path.read_bytes()
        if not data:
            return ""
        tail = data[-cls.TAIL_BYTES:].decode("utf-8", errors="replace")
        return " | ".join(line.strip() for line in tail.splitlines() if line.strip())
