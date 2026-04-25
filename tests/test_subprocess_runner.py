from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hydro_pilot.config.schema.basic import BasicSpec
from hydro_pilot.io.runners.subprocess_runner import SubprocessRunner
from hydro_pilot.runtime.executor import Executor
from hydro_pilot.runtime.errors import RunError


def test_basic_spec_accepts_command_list(tmp_path: Path):
    project = tmp_path / "project"
    work = tmp_path / "work"
    project.mkdir()
    work.mkdir()

    spec = BasicSpec.from_raw(
        {
            "projectPath": str(project),
            "workPath": str(work),
            "command": [sys.executable, "-c", "print('ok')"],
        },
        tmp_path,
    )

    assert spec.command == [sys.executable, "-c", "print('ok')"]


def test_build_command_keeps_path_lookup_for_missing_local_executable(tmp_path: Path):
    cmd = SubprocessRunner._build_command(str(tmp_path), "python -V")

    assert cmd[0] == "python"


def test_build_command_resolves_existing_local_executable(tmp_path: Path):
    exe = tmp_path / "swat.exe"
    exe.write_text("stub", encoding="utf-8")

    cmd = SubprocessRunner._build_command(str(tmp_path), "swat.exe")

    assert cmd[0] == str(exe)


def test_runner_writes_stdout_and_stderr_logs(tmp_path: Path):
    script = tmp_path / "emit_logs.py"
    script.write_text(
        "import sys\n"
        "print('hello stdout')\n"
        "print('hello stderr', file=sys.stderr)\n",
        encoding="utf-8",
    )

    runner = SubprocessRunner()
    rc = runner.run(str(tmp_path), [sys.executable, str(script)], timeout=5)

    assert rc == 0
    assert (tmp_path / runner.STDOUT_LOG).read_text(encoding="utf-8").strip() == "hello stdout"
    assert (tmp_path / runner.STDERR_LOG).read_text(encoding="utf-8").strip() == "hello stderr"


def test_runner_maps_missing_executable_to_run_error(tmp_path: Path):
    runner = SubprocessRunner()

    with pytest.raises(RunError, match="Executable not found") as exc_info:
        runner.run(str(tmp_path), ["__definitely_missing_hydropilot_executable__"], timeout=5)

    assert exc_info.value.code == "EXECUTABLE_NOT_FOUND"


def test_runner_nonzero_exit_reports_logs_and_tails(tmp_path: Path):
    script = tmp_path / "fail.py"
    script.write_text(
        "import sys\n"
        "print('stdout before failure')\n"
        "print('stderr before failure', file=sys.stderr)\n"
        "raise SystemExit(3)\n",
        encoding="utf-8",
    )

    runner = SubprocessRunner()

    with pytest.raises(RunError) as exc_info:
        runner.run(str(tmp_path), [sys.executable, str(script)], timeout=5)

    err = exc_info.value
    assert err.code == "NONZERO_EXIT"
    assert "stderr before failure" in err.message
    assert str(tmp_path / runner.STDOUT_LOG) in err.message
    assert str(tmp_path / runner.STDERR_LOG) in err.message


def test_runner_timeout_reports_log_paths(tmp_path: Path):
    script = tmp_path / "sleep.py"
    script.write_text(
        "import time\n"
        "print('starting')\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )

    runner = SubprocessRunner()

    with pytest.raises(RunError) as exc_info:
        runner.run(str(tmp_path), [sys.executable, str(script)], timeout=1)

    err = exc_info.value
    assert err.code == "TIMEOUT"
    assert str(tmp_path / runner.STDOUT_LOG) in err.message
    assert str(tmp_path / runner.STDERR_LOG) in err.message


def test_executor_archives_failed_runner_logs(tmp_path: Path):
    work_path = tmp_path / "instance_0"
    archive_path = tmp_path / "archive"
    work_path.mkdir()
    archive_path.mkdir()

    stdout_path, stderr_path = SubprocessRunner.log_paths(str(work_path))
    stdout_path.write_text("stdout failure log\n", encoding="utf-8")
    stderr_path.write_text("stderr failure log\n", encoding="utf-8")

    class DummyWorkspace:
        def __init__(self, archive):
            self.archivePath = archive

    executor = Executor.__new__(Executor)
    executor.workspace = DummyWorkspace(archive_path)
    executor.services = type(
        "DummyServices",
        (),
        {"runner": SubprocessRunner()},
    )()

    context = {"batch_id": 2, "i": 4}
    err = RunError("subprocess", "NONZERO_EXIT", "simulation", "failed")

    executor._archive_runner_logs(str(work_path), context, err)

    archive_root = archive_path / Executor.FAILED_RUNNER_LOG_DIR
    stdout_archive = archive_root / "2_5.stdout.log"
    stderr_archive = archive_root / "2_5.stderr.log"
    assert stdout_archive.read_text(encoding="utf-8") == "stdout failure log\n"
    assert stderr_archive.read_text(encoding="utf-8") == "stderr failure log\n"
    assert str(stdout_archive) in err.message
    assert str(stderr_archive) in err.message
