import csv
from pathlib import Path
from typing import Any, Dict, List

import yaml


def discover_xaj_project(project_path: Path) -> Dict[str, Any]:
    project_path = Path(project_path)
    config_path = project_path / "xaj.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"XAJ config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    if not isinstance(config, dict):
        raise ValueError("xaj.yaml must contain a mapping at the top level")

    parameter_file = _get_nested(config, ["inputs", "parameters"])
    if parameter_file is None:
        parameter_file = _get_nested(config, ["case", "parameter"])
    if parameter_file is None:
        parameter_file = "parameters.csv"

    parameter_path = project_path / str(parameter_file)
    parameter_rows = _read_csv(parameter_path)
    if not parameter_rows:
        raise ValueError(f"XAJ parameter file is empty: {parameter_path}")

    header = parameter_rows[0]
    rivid_index = _find_unique_header(header, "RIVID")
    rivid_rows: Dict[str, int] = {}
    for data_index, row in enumerate(parameter_rows[1:], start=1):
        if rivid_index >= len(row):
            raise ValueError(f"XAJ parameter row {data_index} has no RIVID column")
        rivid = row[rivid_index].strip()
        if not rivid:
            raise ValueError(f"XAJ parameter row {data_index} has empty RIVID")
        if rivid in rivid_rows:
            raise ValueError(f"Duplicate XAJ RIVID in parameter file: {rivid}")
        rivid_rows[rivid] = data_index

    output_headers = {}
    for name in ["streamflow.csv", "Runoff_Yield.csv", "ET.csv", "WD.csv", "WL.csv"]:
        path = project_path / name
        if path.exists():
            rows = _read_csv(path)
            if rows:
                output_headers[name] = rows[0]

    return {
        "projectPath": project_path,
        "xajConfig": config,
        "parameterFile": str(parameter_file),
        "parameterHeader": header,
        "rividRows": rivid_rows,
        "allDataRows": list(range(1, len(parameter_rows))),
        "outputHeaders": output_headers,
    }


def _get_nested(data: Dict[str, Any], keys: List[str]) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def _read_csv(path: Path) -> List[List[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.reader(f))


def _find_unique_header(header: List[str], name: str) -> int:
    matches = [idx for idx, value in enumerate(header) if value.strip() == name]
    if not matches:
        raise ValueError(f"XAJ CSV header missing column '{name}'")
    if len(matches) > 1:
        raise ValueError(f"XAJ CSV header has duplicate column '{name}'")
    return matches[0]
