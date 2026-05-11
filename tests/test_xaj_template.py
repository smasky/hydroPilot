from pathlib import Path
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hydropilot.config.loader import prepare_config
from hydropilot.models.xaj.series import buildXajSeries
from hydropilot.models.xaj.template import XajTemplate


def _write_xaj_project(path: Path) -> None:
    path.mkdir()
    (path / "xaj.yaml").write_text(
        "\n".join([
            "case:",
            "  name: case_001",
            "  parameter: parameters.csv",
            "inputs:",
            "  parameters: parameters.csv",
            "  precipitation: prec.csv",
            "  evaporation: ep.csv",
        ]),
        encoding="utf-8",
    )
    (path / "parameters.csv").write_text(
        "\n".join([
            "RIVID,Area,DP,KC,B,C,IMP,WM,WUM,WLM,SM,EX,KG,KI,CG,CI,CS,LAG,KE,XE",
            "60711600,2732,0,1.2,0.25,0.15,0.02,121,24,60,16,1.2,0.2,0.5,0.999,0.5,0.68,10,24,0.5",
            "60711700,1000,0,1.1,0.20,0.12,0.01,120,20,55,12,1.1,0.3,0.4,0.900,0.4,0.60,2,24,0.3",
        ]),
        encoding="utf-8-sig",
    )
    (path / "streamflow.csv").write_text("Date,streamflow\n2016/1/1 0:00,0\n", encoding="utf-8-sig")
    (path / "Runoff_Yield.csv").write_text("Date,60711600,60711700\n2016/1/1 0:00,1,2\n", encoding="utf-8-sig")


def _base_config(project: Path, work: Path) -> dict:
    return {
        "version": "xaj",
        "basic": {
            "projectPath": str(project),
            "workPath": str(work),
            "command": "python run_xaj.py",
        },
        "parameters": {
            "design": [
                {"name": "KC"},
                {"name": "WM"},
            ],
            "physical": [
                {"name": "KC", "mode": "v", "filter": {"rivid": 60711600}},
                {"name": "WM", "mode": "v"},
            ],
        },
        "series": [
            {
                "id": "q",
                "sim": {"variable": "Streamflow", "rowRanges": [[1, 1]]},
                "obs": {"file": "obs.csv", "headSkip": 1, "rowRanges": [[1, 1]], "colNum": 2},
            },
            {
                "id": "runoff",
                "sim": {"variable": "Runoff", "rivid": 60711700, "rowRanges": [[1, 1]]},
            },
        ],
        "objectives": [{"id": "obj_q", "ref": "q.sim", "sense": "max"}],
    }


def test_xaj_template_expands_parameter_and_series_libraries(tmp_path: Path):
    project = tmp_path / "xaj_project"
    work = tmp_path / "work"
    _write_xaj_project(project)
    (tmp_path / "obs.csv").write_text("Date,q\n2016/1/1 0:00,0\n", encoding="utf-8-sig")

    raw = _base_config(project, work)
    expanded = XajTemplate().build_config(raw, tmp_path)

    assert expanded["version"] == "general"
    assert expanded["parameters"]["design"] == [
        {"name": "KC", "type": "float", "bounds": [0.5, 2.0]},
        {"name": "WM", "type": "float", "bounds": [80, 200]},
    ]
    assert expanded["parameters"]["physical"][0]["writerType"] == "csv"
    assert expanded["parameters"]["physical"][0]["file"] == {
        "name": "parameters.csv",
        "rowList": [2],
        "colNum": 4,
        "delimiter": ",",
        "precision": 3,
    }
    assert expanded["parameters"]["physical"][1]["file"]["rowList"] == [2, 3]
    assert expanded["parameters"]["physical"][1]["file"]["colNum"] == 8

    assert expanded["series"][0]["sim"] == {
        "readerType": "csv",
        "file": "streamflow.csv",
        "rowRanges": [[2, 2]],
        "colNum": 2,
    }
    assert expanded["series"][1]["sim"] == {
        "readerType": "csv",
        "file": "Runoff_Yield.csv",
        "rowRanges": [[2, 2]],
        "colNum": 3,
    }
    assert "headSkip" not in expanded["parameters"]["physical"][0]["file"]
    assert "headSkip" not in expanded["parameters"]["physical"][1]["file"]
    assert "variable" not in expanded["series"][0]["sim"]
    assert "rivid" not in expanded["series"][0]["sim"]
    assert "headSkip" not in expanded["series"][0]["sim"]
    assert "variable" not in expanded["series"][1]["sim"]
    assert "rivid" not in expanded["series"][1]["sim"]
    assert "headSkip" not in expanded["series"][1]["sim"]


def test_prepare_config_supports_xaj_version(tmp_path: Path):
    project = tmp_path / "xaj_project"
    work = tmp_path / "work"
    _write_xaj_project(project)
    (tmp_path / "obs.csv").write_text("Date,q\n2016/1/1 0:00,0\n", encoding="utf-8-sig")
    cfg_path = tmp_path / "xaj_case.yaml"
    cfg_path.write_text(yaml.safe_dump(_base_config(project, work), sort_keys=False), encoding="utf-8")

    prepared = prepare_config(cfg_path)

    assert prepared.version == "xaj"
    assert prepared.config.version == "general"
    assert prepared.config.parameters.physical[0].writerType == "csv"
    assert prepared.config.series[0].sim.readerType == "csv"


def test_xaj_resolved_general_writes_reader_type_first(tmp_path: Path):
    project = tmp_path / "xaj_project"
    work = tmp_path / "work"
    _write_xaj_project(project)
    (tmp_path / "obs.csv").write_text("Date,q\n2016/1/1 0:00,0\n", encoding="utf-8-sig")
    cfg_path = tmp_path / "xaj_case.yaml"
    cfg_path.write_text(yaml.safe_dump(_base_config(project, work), sort_keys=False), encoding="utf-8")

    from hydropilot.config.loader import load_config

    load_config(cfg_path)
    general_text = cfg_path.with_name("xaj_case_general.yaml").read_text(encoding="utf-8")

    assert "sim:\n      readerType: csv\n" in general_text
    assert "obs:\n      readerType: csv\n" in general_text


def test_xaj_resolved_general_uses_stable_csv_field_order(tmp_path: Path):
    project = tmp_path / "xaj_project"
    work = tmp_path / "work"
    _write_xaj_project(project)
    (tmp_path / "obs.csv").write_text("Date,q\n2016/1/1 0:00,0\n", encoding="utf-8-sig")
    cfg_path = tmp_path / "xaj_case.yaml"
    cfg_path.write_text(yaml.safe_dump(_base_config(project, work), sort_keys=False), encoding="utf-8")

    from hydropilot.config.loader import load_config

    load_config(cfg_path)
    general_text = cfg_path.with_name("xaj_case_general.yaml").read_text(encoding="utf-8")

    assert (
        "writerType: csv\n"
        "      file:\n"
        "        name: parameters.csv\n"
        "        rowList: [2]\n"
        "        colNum: 4\n"
        "        delimiter: ','\n"
        "        precision: 3\n"
    ) in general_text
    assert (
        "sim:\n"
        "      readerType: csv\n"
        "      file: streamflow.csv\n"
        "      rowRanges:\n"
        "        - [2, 2]\n"
        "      colNum: 2\n"
    ) in general_text
    assert "size:" not in general_text


def test_xaj_series_requires_rivid_for_partition_outputs(tmp_path: Path):
    project = tmp_path / "xaj_project"
    _write_xaj_project(project)
    meta = XajTemplate().discover(project)

    with pytest.raises(ValueError, match="requires rivid"):
        buildXajSeries([{"id": "runoff", "sim": {"variable": "Runoff", "rowRanges": [[1, 1]]}}], meta)
