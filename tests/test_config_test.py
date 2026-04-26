from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hydropilot.config.loader import load_config
from hydropilot.testing.runner import run_config_test
from hydropilot.testing.vector import build_default_test_vector


def _write_basic_project(tmp_path: Path) -> tuple[Path, Path]:
    project = tmp_path / "project"
    project.mkdir()
    (project / "params.txt").write_text("  0.00  0.00  0.00\n  1.00  2.00  3.00\n", encoding="ascii")
    runner = project / "write_output.py"
    runner.write_text(
        "\n".join([
            "from pathlib import Path",
            "Path('output.txt').write_text('1.0\\nnan\\n3.0\\n', encoding='ascii')",
        ]),
        encoding="utf-8",
    )
    return project, runner


def _write_config(tmp_path: Path, command: list[str]) -> Path:
    project, _runner = _write_basic_project(tmp_path)
    obs = tmp_path / "obs.txt"
    obs.write_text("1.0\n2.0\n", encoding="ascii")
    config = {
        "version": "general",
        "basic": {
            "projectPath": str(project),
            "workPath": str(tmp_path / "work"),
            "command": command,
            "parallel": 4,
            "keepInstances": False,
        },
        "parameters": {
            "design": [
                {"name": "x_float", "type": "float", "bounds": [0, 10]},
                {"name": "x_int", "type": "int", "bounds": [1, 4]},
                {"name": "x_disc", "type": "discrete", "bounds": [7, 9], "sets": [7, 9]},
                {"name": "x_multi", "type": "float", "bounds": [0, 10]},
            ],
            "physical": [
                {
                    "name": "p_float",
                    "type": "float",
                    "bounds": [0, 10],
                    "writerType": "fixed_width",
                    "file": {"name": "params.txt", "line": 1, "start": 1, "width": 6, "precision": 2},
                },
                {
                    "name": "p_int",
                    "type": "int",
                    "bounds": [1, 4],
                    "writerType": "fixed_width",
                    "file": {"name": "params.txt", "line": 1, "start": 7, "width": 6, "precision": 0},
                },
                {
                    "name": "p_disc",
                    "type": "discrete",
                    "bounds": [7, 9],
                    "sets": [7, 9],
                    "writerType": "fixed_width",
                    "file": {"name": "params.txt", "line": 1, "start": 13, "width": 6, "precision": 0},
                },
                {
                    "name": "p_multi",
                    "type": "float",
                    "bounds": [0, 10],
                    "writerType": "fixed_width",
                    "file": {"name": "params.txt", "line": 2, "start": 1, "width": 6, "precision": 2, "maxNum": 3},
                },
            ],
        },
        "series": [{
            "id": "flow",
            "sim": {"file": "output.txt", "readerType": "text", "rowRanges": [[1, 3]], "colNum": 1},
            "obs": {"file": str(obs), "readerType": "text", "rowRanges": [[1, 2]], "colNum": 1},
            "size": 3,
        }],
        "functions": [],
        "derived": [],
        "objectives": [],
        "constraints": [],
        "diagnostics": [],
        "reporter": {"series": ["flow"]},
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return config_path


def test_default_test_vector_uses_midpoints_and_first_discrete(tmp_path: Path):
    config_path = _write_config(tmp_path, [sys.executable, "write_output.py"])
    cfg = load_config(config_path)

    vector = build_default_test_vector(cfg)

    assert vector.tolist() == [5.0, 2.0, 7.0, 5.0]


def test_run_config_test_forces_serial_keeps_instance_and_writes_md_report(tmp_path: Path):
    config_path = _write_config(tmp_path, [sys.executable, "write_output.py"])

    result = run_config_test(config_path)

    assert result.status == "passed"
    assert result.batchId == 1
    assert result.runId == 1
    assert result.runPath.name.startswith("0") or result.runPath.name
    assert result.projectCopy.name == "instance_0"
    assert result.projectCopy.exists()
    assert (result.projectCopy / "runner.stdout.log").exists()
    assert result.archivePath.exists()
    assert result.reportPath.exists()

    report = result.reportPath.read_text(encoding="utf-8")
    assert "# HydroPilot Test Report" in report
    assert "| parallel | 1 |" in report
    assert "| keepInstances | true |" in report
    assert "instance_0" in report
    assert "## Inputs" in report
    assert "### Design Parameters" in report
    assert "| x_float | 5.0 |" in report
    assert "### Physical Parameters" in report
    assert "| p_float | 5.0 |" in report
    assert "## Results" in report

    summary_header = (result.archivePath / "summary.csv").read_text(encoding="utf-8-sig").splitlines()[0]
    assert "X_x_float" in summary_header
    assert "P_p_float" in summary_header

    series_csv = (result.archivePath / "test_series.csv").read_text(encoding="utf-8-sig").splitlines()
    assert series_csv == [
        "index,flow.sim,flow.obs",
        "1,1.0,1.0",
        "2,NaN,2.0",
        "3,3.0,",
    ]

    param_csv = (result.archivePath / "test_param.csv").read_text(encoding="utf-8-sig").splitlines()
    assert param_csv[0] == "file,param,old_value,new_value,locator"
    assert "params.txt,p_float,0.0,5.0,line=1;start=1;width=6" in param_csv
    assert "params.txt,p_multi_1,1.0,5.0,line=2;start=1;width=6" in param_csv
    assert "params.txt,p_multi_2,2.0,5.0,line=2;start=7;width=6" in param_csv
    assert "params.txt,p_multi_3,3.0,5.0,line=2;start=13;width=6" in param_csv


def test_run_config_test_fixed_width_select_index_writes_only_selected_entry(tmp_path: Path):
    config_path = _write_config(tmp_path, [sys.executable, "write_output.py"])
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["parameters"]["design"] = [
        {"name": "x_layer", "type": "float", "bounds": [0, 10]},
    ]
    config["parameters"]["physical"] = [
        {
            "name": "p_layer",
            "type": "float",
            "bounds": [0, 10],
            "writerType": "fixed_width",
            "file": {
                "name": "params.txt",
                "line": 2,
                "start": 1,
                "width": 6,
                "precision": 2,
                "maxNum": 3,
                "selectIndex": 2,
            },
        },
    ]
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    result = run_config_test(config_path)

    assert result.status == "passed"
    assert (result.projectCopy / "params.txt").read_text(encoding="ascii").splitlines()[1] == "  1.00  5.00  3.00"
    param_csv = (result.archivePath / "test_param.csv").read_text(encoding="utf-8-sig").splitlines()
    assert "params.txt,p_layer,2.0,5.0,line=2;start=7;width=6" in param_csv
    assert all("p_layer_1" not in row for row in param_csv)
    assert all("p_layer_3" not in row for row in param_csv)


def test_run_config_test_fixed_width_select_index_fails_when_no_target_entry_exists(tmp_path: Path):
    config_path = _write_config(tmp_path, [sys.executable, "write_output.py"])
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["parameters"]["design"] = [
        {"name": "x_layer", "type": "float", "bounds": [0, 10]},
    ]
    config["parameters"]["physical"] = [
        {
            "name": "p_layer",
            "type": "float",
            "bounds": [0, 10],
            "writerType": "fixed_width",
            "file": {
                "name": "params.txt",
                "line": 2,
                "start": 1,
                "width": 6,
                "precision": 2,
                "maxNum": 5,
                "selectIndex": 4,
            },
        },
    ]
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="No writable entries found for parameter 'p_layer' in any target file"):
        run_config_test(config_path)


def test_hydropilot_test_cli_prints_summary_and_report_path(tmp_path: Path):
    config_path = _write_config(tmp_path, [sys.executable, "write_output.py"])

    proc = subprocess.run(
        [sys.executable, "-m", "hydropilot.cli.test", str(config_path)],
        cwd=SRC,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0
    assert "HydroPilot test PASSED" in proc.stdout
    assert "Inputs:" in proc.stdout
    assert "X:" in proc.stdout
    assert "P:" in proc.stdout
    assert "instance_0" in proc.stdout
    assert "test-report.md" in proc.stdout


def test_run_config_test_failure_report_keeps_inputs_and_project_copy(tmp_path: Path):
    config_path = _write_config(tmp_path, [sys.executable, "-c", "import sys; print('bad model'); sys.exit(3)"])

    result = run_config_test(config_path)

    assert result.status == "failed"
    assert result.projectCopy.exists()
    assert result.context["error"].code == "NONZERO_EXIT"
    report = result.reportPath.read_text(encoding="utf-8")
    assert "## Inputs" in report
    assert "| x_float | 5.0 |" in report
    assert "| p_float | 5.0 |" in report
    assert "NONZERO_EXIT" in report
