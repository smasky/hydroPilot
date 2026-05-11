from pathlib import Path
from typing import Any, Dict, List, Optional
import copy
import yaml


_XAJ_DB_PATH = Path(__file__).parent / "xaj_db.yaml"


def _load_xaj_db() -> Dict[str, Any]:
    with open(_XAJ_DB_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("xaj_db.yaml must contain a mapping at the top level")
    return data


XAJ_DB: Dict[str, Any] = _load_xaj_db()
XAJ_PARAM_LIBRARY: Dict[str, Dict[str, Any]] = XAJ_DB.get("parameters", {})
XAJ_SERIES_SOURCES: List[Dict[str, Any]] = XAJ_DB.get("series", [])


def lookupParam(name: str) -> Optional[Dict[str, Any]]:
    entry = XAJ_PARAM_LIBRARY.get(name)
    if entry is None:
        return None
    return copy.deepcopy(entry)


def lookupSeriesVariable(variableName: str) -> Optional[Dict[str, Any]]:
    for source in XAJ_SERIES_SOURCES:
        for variable in source.get("variables", []):
            if variable.get("name") == variableName:
                result = copy.deepcopy(variable)
                result["file"] = source.get("name")
                return result
    return None
