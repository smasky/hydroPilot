from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

SWAT_VALIDATION_PROJECT = Path(r"E:\DJBasin\TxtInOutFSB")


def _requires_swat_validation_project():
    if not SWAT_VALIDATION_PROJECT.exists():
        pytest.skip(f"SWAT validation project not found: {SWAT_VALIDATION_PROJECT}")


from hydropilot.config.loader import load_config, prepare_config
from hydropilot.models.swat.validate import AMBIGUOUS_SWAT_PARAMETER_ALIASES, validate_swat_config
from hydropilot.validation.entry import validate_config


def test_validate_general_config_success(tmp_path: Path):
    config = {
        "version": "general",
        "basic": {
            "projectPath": ".",
            "workPath": "./work",
            "command": "swat.exe",
        },
        "parameters": {
            "design": [{"name": "x1", "bounds": [0, 1]}],
            "physical": [{
                "name": "x1",
                "type": "float",
                "bounds": [0, 1],
                "writerType": "fixed_width",
                "file": {
                    "name": "params.txt",
                    "line": 1,
                    "start": 1,
                    "width": 10,
                    "precision": 2,
                },
            }],
        },
        "series": [{
            "id": "flow",
            "sim": {
                "file": "output.txt",
                "readerType": "text",
                "rowRanges": [[1, 3]],
                "colSpan": [1, 10],
            },
            "obs": {
                "file": "obs.txt",
                "readerType": "text",
                "rowRanges": [[1, 3]],
                "colSpan": [1, 10],
            },
        }],
        "functions": [],
        "derived": [],
        "objectives": [],
        "constraints": [],
        "diagnostics": [],
        "reporter": {},
    }

    (tmp_path / "obs.txt").write_text("1\n2\n3\n", encoding="utf-8")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    diagnostics = validate_config(config_path)
    prepared = prepare_config(config_path)
    loaded = load_config(config_path)
    resolved_path = config_path.with_name(f"{config_path.stem}_general.yaml")
    resolved = yaml.safe_load(resolved_path.read_text(encoding="utf-8"))

    assert diagnostics == []
    assert prepared.version == "general"
    assert prepared.expanded_raw == prepared.raw
    assert loaded.version == "general"
    assert loaded.basic.keepInstances is False
    assert resolved["version"] == "general"
    assert resolved["basic"]["keepInstances"] is False
    assert "configPath" not in resolved["basic"]
    assert "sets" not in resolved["parameters"]["design"][0]
    assert "sets" not in resolved["parameters"]["physical"][0]


def test_general_resolved_config_uses_stable_top_level_order(tmp_path: Path):
    config = {
        "version": "general",
        "basic": {
            "projectPath": ".",
            "workPath": "./work",
            "command": "swat.exe",
        },
        "parameters": {
            "design": [{"name": "x1", "bounds": [0, 1]}],
            "physical": [{
                "name": "x1",
                "type": "float",
                "bounds": [0, 1],
                "writerType": "fixed_width",
                "file": {
                    "name": "params.txt",
                    "line": 1,
                    "start": 1,
                    "width": 10,
                    "precision": 2,
                },
            }],
        },
        "series": [{
            "id": "flow",
            "sim": {
                "file": "output.txt",
                "readerType": "text",
                "rowRanges": [[1, 3]],
                "colSpan": [1, 10],
            },
            "obs": {
                "file": "obs.txt",
                "readerType": "text",
                "rowRanges": [[1, 3]],
                "colSpan": [1, 10],
            },
        }],
        "functions": [{"name": "NSE", "kind": "builtin"}],
        "derived": [{"id": "nse_flow", "call": {"func": "NSE", "args": ["flow.sim", "flow.obs"]}}],
        "objectives": [{"id": "obj_nse", "ref": "nse_flow", "sense": "max"}],
        "constraints": [],
        "diagnostics": [{"id": "diag_nse", "ref": "nse_flow"}],
        "reporter": {},
    }

    (tmp_path / "obs.txt").write_text("1\n2\n3\n", encoding="utf-8")
    config_path = tmp_path / "ordered.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    load_config(config_path)
    resolved_path = config_path.with_name("ordered_general.yaml")
    top_level = [
        line.split(":", 1)[0]
        for line in resolved_path.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith(" ") and ":" in line
    ]

    assert top_level == [
        "version",
        "basic",
        "functions",
        "parameters",
        "series",
        "derived",
        "objectives",
        "constraints",
        "diagnostics",
        "reporter",
    ]


def test_general_resolved_config_omits_absent_empty_optional_blocks(tmp_path: Path):
    config = {
        "version": "general",
        "basic": {
            "projectPath": ".",
            "workPath": "./work",
            "command": "swat.exe",
        },
        "parameters": {
            "design": [{"name": "x1", "bounds": [0, 1]}],
            "physical": [{
                "name": "x1",
                "type": "float",
                "bounds": [0, 1],
                "writerType": "fixed_width",
                "file": {
                    "name": "params.txt",
                    "line": 1,
                    "start": 1,
                    "width": 10,
                    "precision": 2,
                },
            }],
        },
        "series": [{
            "id": "flow",
            "sim": {
                "file": "output.txt",
                "readerType": "text",
                "rowRanges": [[1, 3]],
                "colSpan": [1, 10],
            },
            "obs": {
                "file": "obs.txt",
                "readerType": "text",
                "rowRanges": [[1, 3]],
                "colSpan": [1, 10],
            },
        }],
        "objectives": [],
    }

    (tmp_path / "obs.txt").write_text("1\n2\n3\n", encoding="utf-8")
    config_path = tmp_path / "minimal.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    loaded = load_config(config_path)
    resolved = yaml.safe_load(config_path.with_name("minimal_general.yaml").read_text(encoding="utf-8"))

    assert loaded.functions == {}
    assert loaded.constraints.items == []
    assert loaded.diagnostics.items == []
    assert "functions" not in resolved
    assert "derived" not in resolved
    assert "constraints" not in resolved
    assert "diagnostics" not in resolved


def test_validate_general_config_reports_parameter_count_mismatch_without_transformer(tmp_path: Path):
    config = {
        "version": "general",
        "basic": {
            "projectPath": ".",
            "workPath": "./work",
            "command": "swat.exe",
        },
        "parameters": {
            "design": [
                {"name": "x1", "bounds": [0, 1]},
                {"name": "x2", "bounds": [0, 1]},
            ],
            "physical": [{
                "name": "p1",
                "type": "float",
                "bounds": [0, 1],
                "writerType": "fixed_width",
                "file": {"name": "params.txt", "line": 1, "start": 1, "width": 10, "precision": 2},
            }],
        },
        "series": [{
            "id": "flow",
            "sim": {"file": "output.txt", "readerType": "text", "rowRanges": [[1, 3]], "colSpan": [1, 10]},
            "obs": {"file": "obs.txt", "readerType": "text", "rowRanges": [[1, 3]], "colSpan": [1, 10]},
        }],
        "functions": [],
        "derived": [],
        "objectives": [],
        "constraints": [],
        "diagnostics": [],
        "reporter": {},
    }

    (tmp_path / "obs.txt").write_text("1\n2\n3\n", encoding="utf-8")
    config_path = tmp_path / "mismatch.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    diagnostics = validate_config(config_path)

    assert diagnostics
    assert diagnostics[0].level == "error"
    assert diagnostics[0].path == "parameters"
    assert "without parameters.transformer" in diagnostics[0].message


def test_validate_general_config_warns_parameter_count_mismatch_with_transformer(tmp_path: Path):
    config = {
        "version": "general",
        "basic": {
            "projectPath": ".",
            "workPath": "./work",
            "command": "swat.exe",
        },
        "parameters": {
            "transformer": "expand_params",
            "design": [{"name": "x1", "bounds": [0, 1]}],
            "physical": [
                {
                    "name": "p1",
                    "type": "float",
                    "bounds": [0, 1],
                    "writerType": "fixed_width",
                    "file": {"name": "params.txt", "line": 1, "start": 1, "width": 10, "precision": 2},
                },
                {
                    "name": "p2",
                    "type": "float",
                    "bounds": [0, 1],
                    "writerType": "fixed_width",
                    "file": {"name": "params.txt", "line": 1, "start": 11, "width": 10, "precision": 2},
                },
            ],
        },
        "series": [{
            "id": "flow",
            "sim": {"file": "output.txt", "readerType": "text", "rowRanges": [[1, 3]], "colSpan": [1, 10]},
            "obs": {"file": "obs.txt", "readerType": "text", "rowRanges": [[1, 3]], "colSpan": [1, 10]},
        }],
        "functions": [{"name": "expand_params", "kind": "external", "file": "transform.py", "args": ["X"]}],
        "derived": [],
        "objectives": [],
        "constraints": [],
        "diagnostics": [],
        "reporter": {},
    }

    (tmp_path / "obs.txt").write_text("1\n2\n3\n", encoding="utf-8")
    (tmp_path / "transform.py").write_text("def expand_params(X):\n    return [X[0], X[0]]\n", encoding="utf-8")
    config_path = tmp_path / "transformer_mismatch.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    diagnostics = validate_config(config_path)

    assert diagnostics
    assert diagnostics[0].level == "warning"
    assert diagnostics[0].path == "parameters.transformer"
    assert "transformer must return 2 physical parameter values" in diagnostics[0].message


def test_validate_general_config_reports_missing_obs_column_with_series_id(tmp_path: Path):
    config = {
        "version": "general",
        "basic": {
            "projectPath": ".",
            "workPath": "./work",
            "command": "swat.exe",
        },
        "parameters": {
            "design": [{"name": "x1", "bounds": [0, 1]}],
            "physical": [{
                "name": "x1",
                "type": "float",
                "bounds": [0, 1],
                "writerType": "fixed_width",
                "file": {
                    "name": "params.txt",
                    "line": 1,
                    "start": 1,
                    "width": 10,
                    "precision": 2,
                },
            }],
        },
        "series": [{
            "id": "flow",
            "sim": {
                "file": "output.txt",
                "readerType": "text",
                "rowRanges": [[1, 3]],
                "colSpan": [1, 10],
            },
            "obs": {
                "file": "obs.txt",
                "readerType": "text",
                "rowRanges": [[1, 3]],
            },
        }],
        "functions": [],
        "derived": [],
        "objectives": [],
        "constraints": [],
        "diagnostics": [],
        "reporter": {},
    }
    (tmp_path / "obs.txt").write_text("1\n2\n3\n", encoding="utf-8")
    config_path = tmp_path / "missing_obs_col.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    diagnostics = validate_config(config_path)
    assert len(diagnostics) == 1
    assert diagnostics[0].path == "series[flow].obs"
    assert diagnostics[0].message == "missing column location, expected one of colSpan or colNum"
    assert diagnostics[0].suggestion == "add colSpan: [start, end] or colNum: <int>"


def test_validate_general_config_reports_missing_sim_rows(tmp_path: Path):
    config = {
        "version": "general",
        "basic": {
            "projectPath": ".",
            "workPath": "./work",
            "command": "swat.exe",
        },
        "parameters": {
            "design": [{"name": "x1", "bounds": [0, 1]}],
            "physical": [{
                "name": "x1",
                "type": "float",
                "bounds": [0, 1],
                "writerType": "fixed_width",
                "file": {
                    "name": "params.txt",
                    "line": 1,
                    "start": 1,
                    "width": 10,
                    "precision": 2,
                },
            }],
        },
        "series": [{
            "id": "flow",
            "sim": {
                "file": "output.txt",
                "readerType": "text",
                "colSpan": [1, 10],
            },
            "obs": {
                "file": "obs.txt",
                "readerType": "text",
                "rowRanges": [[1, 3]],
                "colSpan": [1, 10],
            },
        }],
        "functions": [],
        "derived": [],
        "objectives": [],
        "constraints": [],
        "diagnostics": [],
        "reporter": {},
    }
    (tmp_path / "obs.txt").write_text("1\n2\n3\n", encoding="utf-8")
    config_path = tmp_path / "missing_sim_rows.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    diagnostics = validate_config(config_path)
    assert len(diagnostics) == 1
    assert diagnostics[0].path == "series[flow].sim"
    assert diagnostics[0].message == "missing row selection, expected rowRanges or rowList"


def test_validate_general_config_reports_missing_physical_precision(tmp_path: Path):
    config = {
        "version": "general",
        "basic": {
            "projectPath": ".",
            "workPath": "./work",
            "command": "swat.exe",
        },
        "parameters": {
            "design": [{"name": "x1", "bounds": [0, 1]}],
            "physical": [{
                "name": "x1",
                "type": "float",
                "bounds": [0, 1],
                "writerType": "fixed_width",
                "file": {
                    "name": "params.txt",
                    "line": 1,
                    "start": 1,
                    "width": 10,
                },
            }],
        },
        "series": [{
            "id": "flow",
            "sim": {
                "file": "output.txt",
                "readerType": "text",
                "rowRanges": [[1, 3]],
                "colSpan": [1, 10],
            },
            "obs": {
                "file": "obs.txt",
                "readerType": "text",
                "rowRanges": [[1, 3]],
                "colSpan": [1, 10],
            },
        }],
        "functions": [],
        "derived": [],
        "objectives": [],
        "constraints": [],
        "diagnostics": [],
        "reporter": {},
    }
    (tmp_path / "obs.txt").write_text("1\n2\n3\n", encoding="utf-8")
    config_path = tmp_path / "missing_precision.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    diagnostics = validate_config(config_path)
    assert len(diagnostics) == 1
    assert diagnostics[0].path == "parameters.physical[x1]"
    assert diagnostics[0].message == "missing fixed_width field 'precision'"


def test_validate_general_config_reports_fixed_width_select_index_greater_than_max_num(tmp_path: Path):
    config = {
        "version": "general",
        "basic": {
            "projectPath": ".",
            "workPath": "./work",
            "command": "swat.exe",
        },
        "parameters": {
            "design": [{"name": "x1", "bounds": [0, 1]}],
            "physical": [{
                "name": "x1",
                "type": "float",
                "bounds": [0, 1],
                "writerType": "fixed_width",
                "file": {
                    "name": "params.txt",
                    "line": 1,
                    "start": 1,
                    "width": 10,
                    "precision": 2,
                    "maxNum": 3,
                    "selectIndex": 4,
                },
            }],
        },
        "series": [{
            "id": "flow",
            "sim": {
                "file": "output.txt",
                "readerType": "text",
                "rowRanges": [[1, 3]],
                "colSpan": [1, 10],
            },
            "obs": {
                "file": "obs.txt",
                "readerType": "text",
                "rowRanges": [[1, 3]],
                "colSpan": [1, 10],
            },
        }],
        "functions": [],
        "derived": [],
        "objectives": [],
        "constraints": [],
        "diagnostics": [],
        "reporter": {},
    }
    (tmp_path / "obs.txt").write_text("1\n2\n3\n", encoding="utf-8")
    config_path = tmp_path / "bad_select_index.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    diagnostics = validate_config(config_path)

    assert len(diagnostics) == 1
    assert diagnostics[0].path == "parameters.physical[x1]"
    assert diagnostics[0].message == "fixed_width selectIndex must be <= maxNum"


def test_validate_general_config_reports_unknown_reader_type(tmp_path: Path):
    config = {
        "version": "general",
        "basic": {
            "projectPath": ".",
            "workPath": "./work",
            "command": "swat.exe",
        },
        "parameters": {
            "design": [{"name": "x1", "bounds": [0, 1]}],
            "physical": [{
                "name": "x1",
                "type": "float",
                "bounds": [0, 1],
                "writerType": "fixed_width",
                "file": {
                    "name": "params.txt",
                    "line": 1,
                    "start": 1,
                    "width": 10,
                    "precision": 2,
                },
            }],
        },
        "series": [{
            "id": "flow",
            "sim": {
                "file": "output.txt",
                "readerType": "missing_reader",
                "rowRanges": [[1, 3]],
                "colSpan": [1, 10],
            },
            "obs": {
                "file": "obs.txt",
                "readerType": "text",
                "rowRanges": [[1, 3]],
                "colSpan": [1, 10],
            },
        }],
        "functions": [],
        "derived": [],
        "objectives": [],
        "constraints": [],
        "diagnostics": [],
        "reporter": {},
    }
    (tmp_path / "obs.txt").write_text("1\n2\n3\n", encoding="utf-8")
    config_path = tmp_path / "missing_reader.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    diagnostics = validate_config(config_path)
    assert len(diagnostics) == 1
    assert diagnostics[0].path == "series[flow].sim"
    assert "Unknown reader type" in diagnostics[0].message

def test_validate_swat_config_requires_variable_or_explicit_column_for_swat_shortcut(tmp_path: Path):
    _requires_swat_validation_project()

    config = {
        "version": "swat",
        "basic": {
            "projectPath": str(SWAT_VALIDATION_PROJECT),
            "workPath": "./work",
            "command": "swat.exe",
        },
        "parameters": {
            "design": [{"name": "CN2", "bounds": [35, 98]}],
        },
        "series": [{
            "id": "flow",
            "sim": {
                "file": "output.rch",
                "id": 33,
                "period": [2010, 2015],
            },
            "obs": {
                "file": "obs_flow.txt",
                "rowRanges": [[1, 2191]],
                "colNum": 1,
            },
        }],
        "functions": [{"name": "NSE", "kind": "builtin"}],
        "derived": [{"id": "nse_flow", "call": {"func": "NSE", "args": ["flow.sim", "flow.obs"]}}],
        "objectives": [{"id": "obj_nse", "ref": "nse_flow", "sense": "max"}],
        "constraints": [],
        "diagnostics": [],
        "reporter": {},
    }

    config_path = tmp_path / "missing_swat_column_source.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    diagnostics = validate_config(config_path)
    assert len(diagnostics) == 1
    assert diagnostics[0].path == "series[flow].sim"
    assert diagnostics[0].message == "missing SWAT output variable or explicit column location"


def test_validate_general_config_does_not_apply_swat_field_policy(tmp_path: Path):
    config = {
        "version": "general",
        "basic": {
            "projectPath": ".",
            "workPath": "./work",
            "command": "swat.exe",
        },
        "parameters": {
            "design": [{"name": "x1", "bounds": [0, 1]}],
            "physical": [{
                "name": "x1",
                "type": "float",
                "bounds": [0, 1],
                "writerType": "fixed_width",
                "file": {
                    "name": "params.txt",
                    "line": 1,
                    "start": 1,
                    "width": 10,
                    "precision": 2,
                },
            }],
        },
        "series": [{
            "id": "flow",
            "sim": {
                "file": "output.rch",
                "readerType": "text",
                "rowRanges": [[1, 3]],
                "variable": "FLOW_OUT",
                "colSpan": [1, 10],
            },
        }],
        "functions": [],
        "derived": [],
        "objectives": [],
        "constraints": [],
        "diagnostics": [],
        "reporter": {},
    }

    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    assert validate_config(config_path) == []


def test_validate_general_config_handles_windows_style_external_function_path(tmp_path: Path):
    external_file = tmp_path / "calc.py"
    external_file.write_text("def calc():\n    return 1\n", encoding="utf-8")

    config = {
        "version": "general",
        "basic": {
            "projectPath": ".",
            "workPath": "./work",
            "command": "swat.exe",
        },
        "parameters": {
            "design": [{"name": "x1", "bounds": [0, 1]}],
            "physical": [{
                "name": "x1",
                "type": "float",
                "bounds": [0, 1],
                "writerType": "fixed_width",
                "file": {
                    "name": "params.txt",
                    "line": 1,
                    "start": 1,
                    "width": 10,
                    "precision": 2,
                },
            }],
        },
        "series": [{
            "id": "flow",
            "sim": {
                "file": "output.txt",
                "readerType": "text",
                "rowRanges": [[1, 3]],
                "colSpan": [1, 10],
            },
            "obs": {
                "file": "obs.txt",
                "readerType": "text",
                "rowRanges": [[1, 3]],
                "colSpan": [1, 10],
            },
        }],
        "functions": [{
            "name": "calc",
            "kind": "external",
            "file": str(external_file),
        }],
        "derived": [],
        "objectives": [],
        "constraints": [],
        "diagnostics": [],
        "reporter": {},
    }

    (tmp_path / "obs.txt").write_text("1\n2\n3\n", encoding="utf-8")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    assert validate_config(config_path) == []


def test_validate_general_config_reports_missing_writer_type(tmp_path: Path):
    config = {
        "version": "general",
        "basic": {
            "projectPath": ".",
            "workPath": "./work",
            "command": "swat.exe",
        },
        "parameters": {
            "design": [{"name": "x1", "bounds": [0, 1]}],
            "physical": [{
                "name": "x1",
                "type": "float",
                "bounds": [0, 1],
                "file": {
                    "name": "params.txt",
                    "line": 1,
                    "start": 1,
                    "width": 10,
                    "precision": 2,
                },
            }],
        },
        "series": [{
            "id": "flow",
            "sim": {
                "readerType": "text",
                "file": {
                    "name": "output.txt",
                    "rowRanges": [[1, 3]],
                    "colSpan": [1, 10],
                },
            },
            "obs": {
                "readerType": "text",
                "file": {
                    "name": "obs.txt",
                    "rowRanges": [[1, 3]],
                    "colSpan": [1, 10],
                },
            },
        }],
        "functions": [],
        "derived": [],
        "objectives": [],
        "constraints": [],
        "diagnostics": [],
        "reporter": {},
    }
    (tmp_path / "obs.txt").write_text("1\n2\n3\n", encoding="utf-8")
    config_path = tmp_path / "missing_writer_type.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    diagnostics = validate_config(config_path)
    assert len(diagnostics) == 1
    assert diagnostics[0].path == "parameters.physical[x1]"
    assert diagnostics[0].message == "missing writerType"



def test_validate_general_config_reports_missing_fixed_width_file_name(tmp_path: Path):
    config = {
        "version": "general",
        "basic": {
            "projectPath": ".",
            "workPath": "./work",
            "command": "swat.exe",
        },
        "parameters": {
            "design": [{"name": "x1", "bounds": [0, 1]}],
            "physical": [{
                "name": "x1",
                "type": "float",
                "bounds": [0, 1],
                "writerType": "fixed_width",
                "file": {
                    "line": 1,
                    "start": 1,
                    "width": 10,
                    "precision": 2,
                },
            }],
        },
        "series": [{
            "id": "flow",
            "sim": {
                "readerType": "text",
                "file": {
                    "name": "output.txt",
                    "rowRanges": [[1, 3]],
                    "colSpan": [1, 10],
                },
            },
            "obs": {
                "readerType": "text",
                "file": {
                    "name": "obs.txt",
                    "rowRanges": [[1, 3]],
                    "colSpan": [1, 10],
                },
            },
        }],
        "functions": [],
        "derived": [],
        "objectives": [],
        "constraints": [],
        "diagnostics": [],
        "reporter": {},
    }
    (tmp_path / "obs.txt").write_text("1\n2\n3\n", encoding="utf-8")
    config_path = tmp_path / "missing_fixed_width_name.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    diagnostics = validate_config(config_path)
    assert len(diagnostics) == 1
    assert diagnostics[0].path == "parameters.physical[x1]"
    assert diagnostics[0].message == "missing physical file name"


    config = {
        "version": "general",
        "basic": {
            "projectPath": ".",
            "workPath": "./work",
            "command": "swat.exe",
        },
        "parameters": {
            "design": [{"name": "x1", "bounds": [0, 1]}],
            "physical": [{
                "name": "x1",
                "type": "float",
                "bounds": [0, 1],
                "writerType": "fixed_width",
                "file": {
                    "name": "params.txt",
                    "line": 1,
                    "start": 1,
                    "width": 10,
                    "precision": 2,
                },
            }],
        },
        "series": [
            {
                "id": "flow",
                "sim": {
                    "file": "output1.txt",
                    "readerType": "text",
                    "rowRanges": [[1, 3]],
                    "colSpan": [1, 10],
                },
                "obs": {
                    "file": "obs.txt",
                    "readerType": "text",
                    "rowRanges": [[1, 3]],
                    "colSpan": [1, 10],
                },
            },
            {
                "id": "flow",
                "sim": {
                    "file": "output2.txt",
                    "readerType": "text",
                    "rowRanges": [[1, 3]],
                    "colSpan": [1, 10],
                },
                "obs": {
                    "file": "obs.txt",
                    "readerType": "text",
                    "rowRanges": [[1, 3]],
                    "colSpan": [1, 10],
                },
            },
        ],
        "functions": [],
        "derived": [],
        "objectives": [],
        "constraints": [],
        "diagnostics": [],
        "reporter": {},
    }
    (tmp_path / "obs.txt").write_text("1\n2\n3\n", encoding="utf-8")
    config_path = tmp_path / "duplicate_series.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    diagnostics = validate_config(config_path)
    assert len(diagnostics) == 1
    assert diagnostics[0].path == "series[flow]"
    assert diagnostics[0].message == "duplicate series id: flow"
    assert diagnostics[0].suggestion == "make each series.id unique"



def test_validate_general_config_reports_duplicate_function_name(tmp_path: Path):
    config = {
        "version": "general",
        "basic": {
            "projectPath": ".",
            "workPath": "./work",
            "command": "swat.exe",
        },
        "parameters": {
            "design": [{"name": "x1", "bounds": [0, 1]}],
            "physical": [{
                "name": "x1",
                "type": "float",
                "bounds": [0, 1],
                "writerType": "fixed_width",
                "file": {
                    "name": "params.txt",
                    "line": 1,
                    "start": 1,
                    "width": 10,
                    "precision": 2,
                },
            }],
        },
        "series": [{
            "id": "flow",
            "sim": {
                "file": "output.txt",
                "readerType": "text",
                "rowRanges": [[1, 3]],
                "colSpan": [1, 10],
            },
            "obs": {
                "file": "obs.txt",
                "readerType": "text",
                "rowRanges": [[1, 3]],
                "colSpan": [1, 10],
            },
        }],
        "functions": [
            {"name": "NSE", "kind": "builtin"},
            {"name": "NSE", "kind": "builtin"},
        ],
        "derived": [],
        "objectives": [],
        "constraints": [],
        "diagnostics": [],
        "reporter": {},
    }
    (tmp_path / "obs.txt").write_text("1\n2\n3\n", encoding="utf-8")
    config_path = tmp_path / "duplicate_function.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    diagnostics = validate_config(config_path)
    assert len(diagnostics) == 1
    assert diagnostics[0].path == "functions[NSE]"
    assert diagnostics[0].message == "duplicate function name: NSE"
    assert diagnostics[0].suggestion == "make each function.name unique"



def test_validate_general_config_reports_missing_dependencies_path(tmp_path: Path):
    config = {
        "version": "general",
        "basic": {
            "projectPath": ".",
            "workPath": "./work",
            "command": "swat.exe",
        },
        "parameters": {
            "design": [{"name": "x1", "bounds": [0, 1]}],
            "physical": [{
                "name": "x1",
                "type": "float",
                "bounds": [0, 1],
                "writerType": "fixed_width",
                "file": {
                    "name": "params.txt",
                    "line": 1,
                    "start": 1,
                    "width": 10,
                    "precision": 2,
                },
            }],
        },
        "series": [{
            "id": "flow",
            "sim": {
                "file": "output.txt",
                "readerType": "text",
                "rowRanges": [[1, 3]],
                "colSpan": [1, 10],
            },
            "obs": {
                "file": "obs.txt",
                "readerType": "text",
                "rowRanges": [[1, 3]],
                "colSpan": [1, 10],
            },
        }],
        "functions": [{"name": "NSE", "kind": "builtin"}],
        "derived": [{"id": "nse_flow", "call": {"func": "NSE", "args": ["missing.sim", "flow.obs"]}}],
        "objectives": [{"id": "obj_nse", "ref": "nse_flow", "sense": "max"}],
        "constraints": [],
        "diagnostics": [],
        "reporter": {},
    }
    (tmp_path / "obs.txt").write_text("1\n2\n3\n", encoding="utf-8")
    config_path = tmp_path / "missing_dependency.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    diagnostics = validate_config(config_path)
    assert len(diagnostics) == 1
    assert diagnostics[0].path == "config.dependencies"
    assert "Missing dependencies in environment" in diagnostics[0].message
    assert diagnostics[0].suggestion == "check derived/objectives/constraints/diagnostics refs and function args"



def test_validate_swat_config_reports_unknown_design_parameter(tmp_path: Path):
    _requires_swat_validation_project()

    config = {
        "version": "swat",
        "basic": {
            "projectPath": str(SWAT_VALIDATION_PROJECT),
            "workPath": "./work",
            "command": "swat.exe",
        },
        "parameters": {
            "design": [{"name": "NOT_A_SWAT_PARAM", "bounds": [35, 98]}],
        },
        "series": [{
            "id": "flow",
            "sim": {
                "file": "output.rch",
                "id": 33,
                "variable": "FLOW_OUT",
                "period": [2010, 2015],
            },
            "obs": {
                "file": "obs_flow.txt",
                "rowRanges": [[1, 2191]],
                "colNum": 1,
            },
        }],
        "functions": [{"name": "NSE", "kind": "builtin"}],
        "derived": [{"id": "nse_flow", "call": {"func": "NSE", "args": ["flow.sim", "flow.obs"]}}],
        "objectives": [{"id": "obj_nse", "ref": "nse_flow", "sense": "max"}],
        "constraints": [],
        "diagnostics": [],
        "reporter": {},
    }

    config_path = tmp_path / "bad_param.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    diagnostics = validate_config(config_path)
    assert diagnostics
    assert diagnostics[0].path == "parameters.design[NOT_A_SWAT_PARAM]"


def test_validate_swat_config_reports_ambiguous_parameter_name(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "file.cio").write_text("", encoding="utf-8")
    (project / "fig.fig").write_text("", encoding="utf-8")

    config = {
        "version": "swat",
        "basic": {
            "projectPath": str(project),
            "workPath": "./work",
            "command": "swat.exe",
        },
        "parameters": {
            "design": [{"name": "ESCO", "bounds": [0, 1]}],
        },
        "series": [],
    }

    diagnostics = validate_swat_config(config, tmp_path)

    assert diagnostics
    assert diagnostics[0].path == "parameters.design[ESCO]"
    assert "ambiguous SWAT parameter name" in diagnostics[0].message
    assert "ESCO_BSN" in diagnostics[0].suggestion
    assert "ESCO_HRU" in diagnostics[0].suggestion


def test_validate_swat_config_reports_ambiguous_parameter_alias_library(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "file.cio").write_text("", encoding="utf-8")
    (project / "fig.fig").write_text("", encoding="utf-8")

    config = {
        "version": "swat",
        "basic": {
            "projectPath": str(project),
            "workPath": "./work",
            "command": "swat.exe",
        },
        "parameters": {
            "design": [{"name": name, "bounds": [0, 1]} for name in sorted(AMBIGUOUS_SWAT_PARAMETER_ALIASES)],
        },
        "series": [],
    }

    diagnostics = validate_swat_config(config, tmp_path)
    by_path = {item.path: item for item in diagnostics}

    for name, candidates in AMBIGUOUS_SWAT_PARAMETER_ALIASES.items():
        diagnostic = by_path[f"parameters.design[{name}]"]
        assert "ambiguous SWAT parameter name" in diagnostic.message
        for candidate in candidates:
            assert candidate in diagnostic.suggestion


def test_validate_cli_reports_yaml_root_error(tmp_path: Path):
    config_path = tmp_path / "bad.yaml"
    config_path.write_text("[]\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "hydropilot.cli.validate", str(config_path)],
        cwd=SRC,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "YAML root must be a mapping/object" in result.stdout


def test_validate_cli_prints_success_message(tmp_path: Path):
    config = {
        "version": "general",
        "basic": {
            "projectPath": ".",
            "workPath": "./work",
            "command": "swat.exe",
        },
        "parameters": {
            "design": [{"name": "x1", "bounds": [0, 1]}],
            "physical": [{
                "name": "x1",
                "type": "float",
                "bounds": [0, 1],
                "writerType": "fixed_width",
                "file": {
                    "name": "params.txt",
                    "line": 1,
                    "start": 1,
                    "width": 10,
                    "precision": 2,
                },
            }],
        },
        "series": [{
            "id": "flow",
            "sim": {
                "file": "output.txt",
                "readerType": "text",
                "rowRanges": [[1, 3]],
                "colSpan": [1, 10],
            },
            "obs": {
                "file": "obs.txt",
                "readerType": "text",
                "rowRanges": [[1, 3]],
                "colSpan": [1, 10],
            },
        }],
        "functions": [],
        "derived": [],
        "objectives": [],
        "constraints": [],
        "diagnostics": [],
        "reporter": {},
    }
    (tmp_path / "obs.txt").write_text("1\n2\n3\n", encoding="utf-8")
    config_path = tmp_path / "ok.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "hydropilot.cli.validate", str(config_path)],
        cwd=SRC,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert f"Validation passed: {config_path}" in result.stdout

