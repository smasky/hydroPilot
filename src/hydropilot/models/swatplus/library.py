from pathlib import Path
from typing import Any, Dict, List, Optional
import copy
import yaml

_SWATPLUS_DB_PATH = Path(__file__).parent / "swatplus_db.yaml"


def _load_swatplus_db() -> Dict[str, Any]:
    with open(_SWATPLUS_DB_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("swatplus_db.yaml must contain a mapping at the top level")
    return data


SWATPLUS_DB: Dict[str, Any] = _load_swatplus_db()
SWATPLUS_PARAM_LIBRARY: Dict[str, Dict[str, Any]] = SWATPLUS_DB.get("parameters", {})
SWATPLUS_SERIES_SOURCES: List[Dict[str, Any]] = SWATPLUS_DB.get("series", [])


def lookupParam(name: str) -> Optional[Dict[str, Any]]:
    entry = SWATPLUS_PARAM_LIBRARY.get(name)
    if entry is None:
        return None
    return copy.deepcopy(entry)


def lookupSeriesVariable(variableName: str, fileFilter: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Find a variable across all output files and return its file + column location.

    When *fileFilter* is provided, only sources whose ``file`` matches are
    checked — this lets ``sim.file`` scope a variable lookup to a specific
    output file (SWAT 2012-like ``file + variable`` pairing).

    Returns dict with keys: ``file``, ``colSpan`` or ``colNum``, plus
    ``object``, ``report``, ``frequency`` from the parent source entry.
    """
    for source in SWATPLUS_SERIES_SOURCES:
        if fileFilter is not None:
            if source.get("file", source.get("name", "")) != fileFilter:
                continue
        for variable in source.get("variables", []):
            if variable.get("name") == variableName:
                result: Dict[str, Any] = {}
                result["file"] = source.get("file", source.get("name", ""))
                if "colSpan" in variable:
                    result["colSpan"] = list(variable["colSpan"])
                elif "colNum" in variable:
                    result["colNum"] = int(variable["colNum"])
                for key in ("object", "report", "frequency"):
                    if key in source:
                        result[key] = source[key]
                return result
    return None


def lookupSeriesFile(fileName: str) -> Optional[Dict[str, Any]]:
    """Return metadata for a known output file (object, report, frequency, header_lines)."""
    for source in SWATPLUS_SERIES_SOURCES:
        if source.get("file", source.get("name", "")) == fileName:
            return {k: v for k, v in source.items() if k != "variables"}
    return None


def get_known_output_files() -> set[str]:
    return {source.get("file", source.get("name", "")) for source in SWATPLUS_SERIES_SOURCES}


def get_known_variable_names() -> set[str]:
    names: set[str] = set()
    for source in SWATPLUS_SERIES_SOURCES:
        for variable in source.get("variables", []):
            name = variable.get("name")
            if name:
                names.add(str(name))
    return names
