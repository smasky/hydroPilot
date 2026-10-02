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


def getParameterScopes(paramDb: Dict[str, Dict[str, Any]]) -> Dict[str, List[str]]:
    scopes: Dict[str, List[str]] = {}
    for key, entry in paramDb.items():
        if "." in key:
            name, scope = key.rsplit(".", 1)
        else:
            name = key
            scope = Path(entry["file"]["name"]).suffix.lstrip(".")
        scopes.setdefault(name, []).append(scope)
    return {name: sorted(set(values)) for name, values in scopes.items()}


def defaultParameterScope(name: str, scopes: Dict[str, List[str]]) -> Optional[str]:
    candidates = scopes.get(name, [])
    if len(candidates) <= 1:
        return None
    localScopes = [scope for scope in candidates if scope != "bsn"]
    if len(localScopes) == 1:
        return localScopes[0]
    raise ValueError(f"SWAT parameter '{name}' has no unique default scope; specify one of: {', '.join(candidates)}")


def validateParameterScope(item: Dict[str, Any], scopes: Dict[str, List[str]]) -> None:
    name = item["name"]
    scope = item.get("scope")
    if not isinstance(name, str) or not name:
        raise ValueError("SWAT parameter name must be a non-empty string")
    if scope is not None and (not isinstance(scope, str) or not scope or any(c.isspace() for c in scope)):
        raise ValueError("scope must be a non-empty string without whitespace")
    if "." in name:
        baseName, suffix = name.rsplit(".", 1)
        if suffix in scopes.get(baseName, []):
            raise ValueError(
                f"SWAT parameter '{name}' must separate name and scope; use name: {baseName}, scope: {suffix}"
            )
    candidates = scopes.get(name, [])
    if scope is None:
        defaultParameterScope(name, scopes)
    if candidates and scope is not None and scope not in candidates:
        raise ValueError(f"invalid scope '{scope}' for SWAT parameter '{name}'; expected one of: {', '.join(candidates)}")


def resolveParameterScope(item: Dict[str, Any], scopes: Dict[str, List[str]]) -> Dict[str, Any]:
    validateParameterScope(item, scopes)
    result = copy.deepcopy(item)
    if result.get("scope") is None:
        scope = defaultParameterScope(result["name"], scopes)
        if scope is not None:
            result["scope"] = scope
    return result


SWAT_PARAMETER_SCOPES = getParameterScopes(SWAT_PARAM_LIBRARY)


def normalizeSwatOutputFileName(fileName: str) -> str:
    """Normalize SWAT output path-like strings to a basename."""
    text = str(fileName).replace("\\", "/")
    return text.rsplit("/", 1)[-1]


def lookupParam(name: str) -> Optional[Dict[str, Any]]:
    """Look up a single parameter definition from the database.

    Returns a deep copy of the entry, or None if not found.
    """
    scope = defaultParameterScope(name, SWAT_PARAMETER_SCOPES)
    key = f"{name}.{scope}" if scope is not None else name
    entry = SWAT_PARAM_LIBRARY.get(key)
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
        defaultScope = defaultParameterScope(name, SWAT_PARAMETER_SCOPES)
        key = f"{name}.{defaultScope}" if defaultScope is not None else name
        if key not in SWAT_PARAM_LIBRARY:
            available = sorted(SWAT_PARAM_LIBRARY.keys())
            raise ValueError(
                f"Unknown SWAT parameter '{name}'. "
                f"Available: {available}"
            )

        param_def = copy.deepcopy(SWAT_PARAM_LIBRARY[key])
        user_override = overrides.get(name, {})

        # Apply overrides
        if "bounds" in user_override:
            param_def["bounds"] = user_override["bounds"]
        if "type" in user_override:
            param_def["type"] = user_override["type"]

        paramName, scope = key.rsplit(".", 1) if "." in key else (key, None)
        library_items.append({
            "name": paramName,
            "type": param_def["type"],
            "bounds": param_def["bounds"],
            "file": param_def["file"],
        })
        design_items.append({
            "name": paramName,
            "type": param_def["type"],
            "bounds": param_def["bounds"],
        })
        if scope is not None:
            library_items[-1]["scope"] = scope
            design_items[-1]["scope"] = scope

    return {
        "library": {"parameter_library": library_items},
        "design_params": {"design_parameters": design_items},
    }
