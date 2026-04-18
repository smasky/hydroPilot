from typing import Any, Dict, List, Optional
from pathlib import Path
import copy
import yaml

# Load parameter database from YAML
_PARAM_DB_PATH = Path(__file__).parent / "param_db.yaml"

def _load_param_db() -> Dict[str, Dict[str, Any]]:
    """Load SWAT parameter database from param_db.yaml."""
    with open(_PARAM_DB_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

SWAT_PARAM_LIBRARY: Dict[str, Dict[str, Any]] = _load_param_db()


def lookupParam(name: str) -> Optional[Dict[str, Any]]:
    """Look up a single parameter definition from the database.

    Returns a deep copy of the entry, or None if not found.
    """
    entry = SWAT_PARAM_LIBRARY.get(name)
    if entry is None:
        return None
    return copy.deepcopy(entry)


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
