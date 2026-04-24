from pathlib import Path
from typing import Any, Dict, List, Optional
import copy
import yaml

# Load SWAT knowledge database from YAML
_SWAT_DB_PATH = Path(__file__).parent / "swat_db.yaml"


def _load_swat_db() -> Dict[str, Any]:
    """Load SWAT knowledge database from swat_db.yaml."""
    with open(_SWAT_DB_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("swat_db.yaml must contain a mapping at the top level")
    return data


SWAT_DB: Dict[str, Any] = _load_swat_db()
SWAT_PARAM_LIBRARY: Dict[str, Dict[str, Any]] = SWAT_DB.get("parameters", {})
SWAT_SERIES_SOURCES: List[Dict[str, Any]] = SWAT_DB.get("series", [])


def normalizeSwatOutputFileName(fileName: str) -> str:
    """Normalize SWAT output path-like strings to a basename."""
    text = str(fileName).replace("\\", "/")
    return text.rsplit("/", 1)[-1]


def lookupParam(name: str) -> Optional[Dict[str, Any]]:
    """Look up a single parameter definition from the database.

    Returns a deep copy of the entry, or None if not found.
    """
    entry = SWAT_PARAM_LIBRARY.get(name)
    if entry is None:
        return None
    return copy.deepcopy(entry)


def lookupSeriesVariable(fileName: str, variableName: str) -> Optional[Dict[str, Any]]:
    """Look up a SWAT output variable definition by file and variable name."""
    normalizedFileName = normalizeSwatOutputFileName(fileName)
    for source in SWAT_SERIES_SOURCES:
        if source.get("name") != normalizedFileName:
            continue
        for variable in source.get("variables", []):
            if variable.get("name") == variableName:
                return copy.deepcopy(variable)
        return None
    return None


def getSeriesVariableNames(fileName: str) -> List[str]:
    """Return all known SWAT variable names for a given output file."""
    normalizedFileName = normalizeSwatOutputFileName(fileName)
    for source in SWAT_SERIES_SOURCES:
        if source.get("name") == normalizedFileName:
            return [str(variable.get("name")) for variable in source.get("variables", []) if variable.get("name")]
    return []


def get_swat_library(
    param_names: List[str],
    meta: Dict[str, Any],
    overrides: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Generate library and design parameter definitions for given param names.

    Args:
        param_names: List of parameter names to calibrate.
        meta: Metadata from discover().
        overrides: Per-parameter overrides, e.g.
            {"CN2": {"bounds": [40, 90]}}
            Supported override keys: bounds, type

    Returns:
        Dict with 'library' and 'design_params' keys.
    """
    overrides = overrides or {}
    library_items = []
    design_items = []

    for name in param_names:
        if name not in SWAT_PARAM_LIBRARY:
            available = sorted(SWAT_PARAM_LIBRARY.keys())
            raise ValueError(
                f"Unknown SWAT parameter '{name}'. "
                f"Available: {available}"
            )

        param_def = copy.deepcopy(SWAT_PARAM_LIBRARY[name])
        user_override = overrides.get(name, {})

        # Apply overrides
        if "bounds" in user_override:
            param_def["bounds"] = user_override["bounds"]
        if "type" in user_override:
            param_def["type"] = user_override["type"]

        library_items.append({
            "name": name,
            "type": param_def["type"],
            "bounds": param_def["bounds"],
            "file": param_def["file"],
        })
        design_items.append({
            "name": name,
            "type": param_def["type"],
            "bounds": param_def["bounds"],
        })

    return {
        "library": {"parameter_library": library_items},
        "design_params": {"design_parameters": design_items},
    }
