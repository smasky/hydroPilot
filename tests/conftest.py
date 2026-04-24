from pathlib import Path
import shutil

import pytest


ROOT = Path(__file__).resolve().parents[1]
TEST_TMP_ROOT = ROOT / "work" / ".pytest_tmp_work"
WORKSPACE_TMP_DIRS = (
    ".pytest_tmp",
    ".pytest_tmp_run",
    ".pytest_work",
    ".pytest_work2",
    ".tmp",
    ".tmp_fix_probe",
    ".tmp_probe",
    ".tmp_probe2",
    ".tmp_mode_default",
    ".tmp_mode_700",
    ".tmp_mode_777",
)


def _cleanup_workspace_tmp_dirs() -> None:
    for name in WORKSPACE_TMP_DIRS:
        shutil.rmtree(ROOT / name, ignore_errors=True)


@pytest.fixture
def tmp_path(request):
    """Create per-test temp dirs under work/ to avoid sandboxed Windows temp issues."""
    safe_name = request.node.name.replace("[", "_").replace("]", "_")
    path = TEST_TMP_ROOT / safe_name
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    yield path.resolve()
    shutil.rmtree(path, ignore_errors=True)


def pytest_sessionstart(session):
    _cleanup_workspace_tmp_dirs()
    TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)


def pytest_sessionfinish(session, exitstatus):
    _cleanup_workspace_tmp_dirs()
