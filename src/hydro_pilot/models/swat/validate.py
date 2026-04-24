from pathlib import Path
from typing import Any

from hydro_pilot.config.paths import resolve_config_path
from hydro_pilot.validation.diagnostics import Diagnostic, error


SWAT_ROW_FIELDS = {"id", "period", "timestep"}
SWAT_OUTPUT_FILES = {"output.rch", "output.sub", "output.hru"}


def validate_swat_config(raw: dict[str, Any], base_path: Path) -> list[Diagnostic]:
    diagnostics = _validate_swat_project(raw, base_path)
    if diagnostics:
        return diagnostics
    return _validate_swat_series_inputs(raw)


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


def _validate_swat_series_inputs(raw: dict[str, Any]) -> list[Diagnostic]:
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
    if "id" in sim:
        return []
    return [error(
        path,
        "missing SWAT row selector or explicit row selection",
        "add sim.id with optional period/timestep, or add sim.rowRanges/sim.rowList explicitly",
    )]


def _uses_swat_series_shortcut(sim: dict[str, Any]) -> bool:
    sim_file = str(sim.get("file", ""))
    base_name = sim_file.replace("\\", "/").rsplit("/", 1)[-1]
    return base_name in SWAT_OUTPUT_FILES or any(field in sim for field in SWAT_ROW_FIELDS)


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
