from pathlib import Path
from typing import Any

from hydropilot.config.paths import resolve_config_path
from hydropilot.models.swat.discovery import discover_swat_project
from hydropilot.models.swat.variables import normalize_period_window
from hydropilot.validation.diagnostics import Diagnostic, error, warning


SWAT_ROW_FIELDS = {"id", "period"}
SWAT_OUTPUT_FILES = {"output.rch", "output.sub", "output.hru"}
AMBIGUOUS_SWAT_PARAMETER_ALIASES = {
    "DDRAIN": ["DDRAIN_BSN", "DDRAIN_MGT"],
    "EPCO": ["EPCO_BSN", "EPCO_HRU"],
    "ESCO": ["ESCO_BSN", "ESCO_HRU"],
    "GDRAIN": ["GDRAIN_BSN", "GDRAIN_MGT"],
    "R2ADJ": ["R2ADJ_BSN", "R2ADJ_HRU"],
    "SURLAG": ["SURLAG_BSN", "SURLAG_HRU"],
    "TDRAIN": ["TDRAIN_BSN", "TDRAIN_MGT"],
}


def validate_swat_config(
    raw: dict[str, Any],
    base_path: Path,
    *,
    meta_override: dict[str, Any] | None = None,
) -> list[Diagnostic]:
    diagnostics = _validate_swat_project(raw, base_path)
    if diagnostics:
        return diagnostics
    diagnostics.extend(_validate_swat_parameter_names(raw))
    meta = meta_override
    if _needs_swat_meta(raw):
        meta = meta or _load_swat_meta(raw, base_path)
    diagnostics.extend(_validate_swat_series_inputs(raw, meta))
    return diagnostics


def _validate_swat_project(raw: dict[str, Any], base_path: Path) -> list[Diagnostic]:
    basic = raw.get("basic")
    if not isinstance(basic, dict):
        return [error("basic", "missing basic block")]
    project_path = basic.get("projectPath")
    if project_path is None:
        return [error("basic.projectPath", "missing SWAT projectPath")]
    root = resolve_config_path(project_path, base_path)
    if root is None:
        return [error("basic.projectPath", "missing SWAT projectPath")]
    missing: list[Diagnostic] = []
    if not (root / "file.cio").exists():
        missing.append(error("basic.projectPath", f"SWAT project file not found: {(root / 'file.cio')}"))
    if not (root / "fig.fig").exists():
        missing.append(error("basic.projectPath", f"SWAT project file not found: {(root / 'fig.fig')}"))
    return missing


def _validate_swat_series_inputs(raw: dict[str, Any], meta: dict[str, Any] | None) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for series in raw.get("series", []):
        if not isinstance(series, dict):
            continue
        series_id = str(series.get("id", "<unknown>"))
        sim = series.get("sim")
        if not isinstance(sim, dict):
            continue
        if not _uses_swat_series_shortcut(sim):
            continue
        sim_path = f"series[{series_id}].sim"
        diagnostics.extend(_validate_swat_series_columns(sim, sim_path))
        diagnostics.extend(_validate_swat_series_rows(sim, sim_path))
        if meta is not None:
            diagnostics.extend(_validate_swat_period(sim, sim_path, meta))
    return diagnostics


def _validate_swat_series_columns(sim: dict[str, Any], path: str) -> list[Diagnostic]:
    has_variable = "variable" in sim
    has_explicit_column = "colSpan" in sim or "colNum" in sim
    if has_variable and has_explicit_column:
        return [error(path, "SWAT variable conflicts with explicit column location")]
    if has_variable or has_explicit_column:
        return []
    return [error(
        path,
        "missing SWAT output variable or explicit column location",
        "add sim.variable, or add sim.colSpan/sim.colNum if this project uses a custom output layout",
    )]


def _validate_swat_series_rows(sim: dict[str, Any], path: str) -> list[Diagnostic]:
    has_explicit_rows = "rowRanges" in sim or "rowList" in sim
    has_shortcut_rows = any(field in sim for field in SWAT_ROW_FIELDS)
    if has_explicit_rows and has_shortcut_rows:
        return [error(path, "explicit rowRanges/rowList conflicts with SWAT row shortcut fields")]
    if has_explicit_rows:
        return []
    if "timestep" in sim:
        return [error(f"{path}.timestep", "sim.timestep is not supported for SWAT; timestep is derived from project metadata")]
    if "id" in sim:
        return []
    return [error(
        path,
        "missing SWAT row selector or explicit row selection",
        "add sim.id with optional period, or add sim.rowRanges/sim.rowList explicitly",
    )]


def _uses_swat_series_shortcut(sim: dict[str, Any]) -> bool:
    sim_file = str(sim.get("file", ""))
    base_name = sim_file.replace("\\", "/").rsplit("/", 1)[-1]
    return base_name in SWAT_OUTPUT_FILES or any(field in sim for field in (SWAT_ROW_FIELDS | {"timestep"}))


def _validate_swat_period(sim: dict[str, Any], path: str, meta: dict[str, Any]) -> list[Diagnostic]:
    period = sim.get("period")
    if period is None:
        return []

    try:
        requested_start, requested_end, clipped_start, clipped_end = normalize_period_window(period, meta)
    except ValueError as exc:
        return [error(f"{path}.period", str(exc))]

    output_start = f"{meta['output_start_year']}-01-01"
    output_end = f"{meta['output_end_year']}-12-31"
    if clipped_start > clipped_end:
        return [warning(
            f"{path}.period",
            f"period resolves outside the SWAT output window [{output_start}, {output_end}] and will select no rows",
            "adjust sim.period to overlap the SWAT output years",
        )]
    if requested_start != clipped_start or requested_end != clipped_end:
        return [warning(
            f"{path}.period",
            (
                f"period extends outside the SWAT output window [{output_start}, {output_end}] "
                f"and will be clipped to [{clipped_start.isoformat()}, {clipped_end.isoformat()}]"
            ),
            "adjust sim.period if the clipped range is not intended",
        )]
    return []


def _validate_swat_parameter_names(raw: dict[str, Any]) -> list[Diagnostic]:
    params = raw.get("parameters")
    if not isinstance(params, dict):
        return []

    diagnostics: list[Diagnostic] = []
    diagnostics.extend(_validate_swat_parameter_name_list(params.get("design", []), "parameters.design"))
    diagnostics.extend(_validate_swat_parameter_name_list(params.get("physical", []), "parameters.physical"))
    return diagnostics


def _validate_swat_parameter_name_list(items: Any, path_prefix: str) -> list[Diagnostic]:
    if not isinstance(items, list):
        return []

    diagnostics: list[Diagnostic] = []
    for item in items:
        if not isinstance(item, dict) or "name" not in item:
            continue
        name = str(item["name"])
        candidates = AMBIGUOUS_SWAT_PARAMETER_ALIASES.get(name)
        if candidates:
            diagnostics.append(error(
                f"{path_prefix}[{name}]",
                f"ambiguous SWAT parameter name '{name}'",
                f"use one of the explicit SWAT parameter names: {', '.join(candidates)}",
            ))
    return diagnostics


def _load_swat_meta(raw: dict[str, Any], base_path: Path) -> dict[str, Any]:
    basic = raw.get("basic")
    if not isinstance(basic, dict):
        raise ValueError("missing basic block")
    project_path = basic.get("projectPath")
    root = resolve_config_path(project_path, base_path)
    if root is None:
        raise ValueError("missing SWAT projectPath")
    return discover_swat_project(root)


def _needs_swat_meta(raw: dict[str, Any]) -> bool:
    for series in raw.get("series", []):
        if not isinstance(series, dict):
            continue
        sim = series.get("sim")
        if not isinstance(sim, dict):
            continue
        if "period" in sim and _uses_swat_series_shortcut(sim):
            return True
    return False


def translate_swat_exception(raw: dict[str, Any], exc: Exception) -> Diagnostic:
    message = str(exc)

    translated = _translate_swat_series_error(raw, message)
    if translated is not None:
        return translated

    translated = _translate_swat_parameter_error(raw, message)
    if translated is not None:
        return translated

    return error("swat", message)


def _translate_swat_series_error(raw: dict[str, Any], message: str) -> Diagnostic | None:
    for series in raw.get("series", []):
        if not isinstance(series, dict):
            continue
        series_id = str(series.get("id", "<unknown>"))
        sim = series.get("sim")
        if not isinstance(sim, dict):
            continue
        sim_path = f"series[{series_id}].sim"

        sim_file = str(sim.get("file", ""))
        variable = sim.get("variable")
        object_id = sim.get("id")
        period = sim.get("period")

        if variable is not None:
            if "requires a SWAT output file" in message:
                return error(
                    f"{sim_path}.variable",
                    "variable is only supported for output.rch, output.sub, and output.hru",
                    "use output.rch/output.sub/output.hru or provide sim.colSpan/sim.colNum explicitly",
                )
            if "does not match file" in message and str(variable) in message:
                return error(
                    f"{sim_path}.variable",
                    f"variable '{variable}' does not match file '{sim_file}'",
                )

        if object_id is not None and str(object_id) in message and "id" in message.lower():
            return error(f"{sim_path}.id", message)

        if period is not None and ("period" in message.lower() or "outside" in message.lower()):
            return error(f"{sim_path}.period", message)

    return None


def _translate_swat_parameter_error(raw: dict[str, Any], message: str) -> Diagnostic | None:
    params = raw.get("parameters")
    if not isinstance(params, dict):
        return None

    for item in params.get("design", []):
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if name and str(name) in message:
            return error(f"parameters.design[{name}]", message)

    for item in params.get("physical", []):
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if name and str(name) in message:
            return error(f"parameters.physical[{name}]", message)

    return None
