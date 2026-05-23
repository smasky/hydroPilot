from pathlib import Path
from typing import Any, Dict, List, Optional

from ...config.paths import resolve_config_path
from ...validation.diagnostics import Diagnostic, error, warning
from .discovery import FILTERABLE_HRU_FIELDS
from .library import SWATPLUS_PARAM_LIBRARY, get_known_output_files, get_known_variable_names


# Files expected in every SWAT+ TxtInOut directory.
_REQUIRED_PROJECT_FILES = ("file.cio", "time.sim", "print.prt", "hru-data.hru")

# Source files whose parameters support HRU-level attribute filtering.
#   hydrology.hyd — per-HRU hydrologic parameters (e.g. esco, perco)
#   soils.sol     — per-soil parameters; FORTRAN source confirms
#                   ob_typ=sol uses sp_ob%hru (HRU IDs) as the object
#                   space (cal_parmchg_read.f90:118).  soil-name filter
#                   resolves to HRU IDs via hru_meta.soil (exact match).
# Filters on parameters from other files (parameters.bsn,
# hyd-sed-lte.cha handled separately via object_id) are rejected.
_FILTERABLE_SOURCE_FILES = {"hydrology.hyd", "soils.sol"}

# Source files whose parameters support ONLY object_id filtering
# (direct passthrough to OBJ_TOT tail).  Non-object_id filter keys on
# these parameters are rejected at validation time.
_OBJECT_ID_ONLY_FILES = {"hyd-sed-lte.cha"}

# Valid filter keys for object_id-only files.  Only "object_id" is
# allowed — attribute-based filters (lu_mgt, soil, etc.) are rejected.
_OBJECT_ID_FILTER_KEYS = {"object_id"}


def validate_swatplus_config(
    raw: Dict[str, Any],
    base_path: Path,
    *,
    meta_override: Optional[Dict[str, Any]] = None,
) -> List[Diagnostic]:
    diagnostics: List[Diagnostic] = []

    basic = raw.get("basic")
    if not isinstance(basic, dict):
        return [error("basic", "missing basic block")]

    project_path = basic.get("projectPath")
    if project_path is None:
        diagnostics.append(error("basic.projectPath", "missing SWAT+ projectPath"))
    else:
        root = resolve_config_path(project_path, base_path)
        if root is None or not root.exists():
            diagnostics.append(error("basic.projectPath", f"SWAT+ project directory not found: {project_path}"))
        else:
            for req_file in _REQUIRED_PROJECT_FILES:
                if not (root / req_file).exists():
                    diagnostics.append(error(
                        "basic.projectPath",
                        f"required SWAT+ file not found in project: {req_file}",
                    ))

    diagnostics.extend(_validate_swatplus_parameters(raw))
    diagnostics.extend(_validate_swatplus_series(raw))
    return diagnostics


# ---------------------------------------------------------------------------
# parameters
# ---------------------------------------------------------------------------

def _validate_swatplus_parameters(raw: Dict[str, Any]) -> List[Diagnostic]:
    diagnostics: List[Diagnostic] = []
    params = raw.get("parameters", {})
    design = params.get("design", [])
    if not isinstance(design, list):
        return [error("parameters.design", "parameters.design must be a list")]

    for d in design:
        if not isinstance(d, dict):
            continue
        name = str(d.get("name", "<unknown>"))
        if name not in SWATPLUS_PARAM_LIBRARY:
            diagnostics.append(error(
                f"parameters.design[{name}]",
                f"unknown SWAT+ parameter '{name}'",
            ))

    physical = params.get("physical", [])
    if isinstance(physical, list):
        for idx, p in enumerate(physical):
            if not isinstance(p, dict):
                continue
            pname = str(p.get("name", f"<unknown>"))
            filterSpec = p.get("filter")
            if not isinstance(filterSpec, dict):
                continue

            # Only HRU-scoped parameters (hydrology.hyd, soils.sol) support
            # attribute-based filtering.  hyd-sed-lte.cha supports object_id
            # only.  All other origin files reject filters entirely.
            db_entry = SWATPLUS_PARAM_LIBRARY.get(pname)
            origin_file = db_entry.get("file", {}).get("name", "") if db_entry else ""
            if origin_file in _FILTERABLE_SOURCE_FILES:
                diagnostics.extend(_validate_filter_spec(filterSpec, pname, f"parameters.physical[{pname}]"))
            elif origin_file in _OBJECT_ID_ONLY_FILES:
                for field in filterSpec:
                    if field not in _OBJECT_ID_FILTER_KEYS:
                        diagnostics.append(error(
                            f"parameters.physical[{pname}].filter.{field}",
                            f"channel parameters only support 'object_id' filter; "
                            f"'{field}' is not supported.",
                        ))
            else:
                diagnostics.append(error(
                    f"parameters.physical[{pname}].filter",
                    f"filter is only supported for per-HRU parameters "
                    f"(source file hydrology.hyd) and per-channel object_id.  "
                    f"'{pname}' originates from '{origin_file}' "
                    f"and does not support per-object filtering.",
                ))
                continue

    return diagnostics


def _validate_filter_spec(
    filterSpec: Dict[str, Any],
    param_name: str,
    base_path: str,
) -> List[Diagnostic]:
    diagnostics: List[Diagnostic] = []
    for field in filterSpec:
        if field == "not":
            not_spec = filterSpec["not"]
            if isinstance(not_spec, dict):
                for not_field in not_spec:
                    if not_field not in FILTERABLE_HRU_FIELDS:
                        diagnostics.append(error(
                            f"{base_path}.filter.not.{not_field}",
                            f"unknown filter field 'not.{not_field}'; supported fields: {list(FILTERABLE_HRU_FIELDS)}",
                        ))
        elif field not in FILTERABLE_HRU_FIELDS:
            diagnostics.append(error(
                f"{base_path}.filter.{field}",
                f"unknown filter field '{field}'; supported fields: {list(FILTERABLE_HRU_FIELDS)}",
            ))
    return diagnostics


# ---------------------------------------------------------------------------
# series
# ---------------------------------------------------------------------------

def _validate_swatplus_series(raw: Dict[str, Any]) -> List[Diagnostic]:
    diagnostics: List[Diagnostic] = []
    known_variables = get_known_variable_names()
    known_files = get_known_output_files()

    for series in raw.get("series", []):
        if not isinstance(series, dict):
            continue
        series_id = str(series.get("id", "<unknown>"))
        sim = series.get("sim")
        if not isinstance(sim, dict):
            continue

        sim_path = f"series[{series_id}].sim"
        has_variable = "variable" in sim
        has_explicit_column = "colSpan" in sim or "colNum" in sim

        if has_variable:
            var_name = str(sim["variable"])
            if var_name not in known_variables:
                diagnostics.append(error(
                    f"{sim_path}.variable",
                    f"unknown SWAT+ output variable '{var_name}'",
                ))

        if not has_variable and not has_explicit_column:
            diagnostics.append(error(
                sim_path,
                "missing column specification",
                "add sim.variable (looked up from series_db.yaml) or sim.colSpan/sim.colNum",
            ))

        sim_file = sim.get("file")
        if sim_file and sim_file not in known_files:
            diagnostics.append(warning(
                sim_path,
                f"output file '{sim_file}' is not in the known series database; "
                "file lookup by variable name will not work",
                "add the file and its variables to swatplus_db.yaml, "
                "or use sim.colSpan/sim.colNum directly",
            ))

        has_spatial_id = "id" in sim
        has_explicit_rows = "rowRanges" in sim or "rowList" in sim
        if not has_spatial_id and not has_explicit_rows:
            diagnostics.append(error(
                sim_path,
                "missing row selection",
                "add sim.id (spatial object id from hru-data.hru, rout_unit.con, etc.) "
                "or sim.rowRanges/sim.rowList",
            ))

    return diagnostics
