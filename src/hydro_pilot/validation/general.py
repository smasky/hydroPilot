from pathlib import Path
from typing import Any

import yaml

from hydro_pilot.config.paths import resolve_config_path
from hydro_pilot.config.specs import RunConfig
from hydro_pilot.io.writers import getWriter
from hydro_pilot.io.readers import getReader
from hydro_pilot.validation.diagnostics import Diagnostic, error, has_error


GENERAL_ERROR_TRANSLATIONS = {
    "Must set exactly one of colSpan or colNum": (
        "missing column location, expected one of colSpan or colNum",
        "add colSpan: [start, end] or colNum: <int>",
    ),
    "must define at least one row via 'rowRanges' or 'rowList'": (
        "missing row selection, expected rowRanges or rowList",
        "add rowRanges: [[start, end]] or rowList: [row1, row2, ...]",
    ),
    "missing 'file'": (
        "missing file path for extract",
        "add file: <path>",
    ),
}


def validate_general_config(raw: dict[str, Any], base_path: Path) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    diagnostics.extend(_validate_general_structure(raw))
    diagnostics.extend(_validate_general_parameters(raw))
    diagnostics.extend(_validate_general_series(raw, base_path))
    diagnostics.extend(_validate_general_functions(raw, base_path))
    diagnostics.extend(_validate_general_dependencies(raw))

    if has_error(diagnostics):
        return diagnostics

    fallback = _run_general_fallback(raw, base_path)
    if fallback:
        diagnostics.extend(fallback)
    return diagnostics


def _validate_general_structure(raw: dict[str, Any]) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if raw.get("version", "general") != "general":
        diagnostics.append(error("config.version", "general validation requires version: general"))

    basic = raw.get("basic")
    if not isinstance(basic, dict):
        diagnostics.append(error("basic", "missing basic block"))
        return diagnostics

    for key in ("projectPath", "workPath", "command"):
        if key not in basic:
            diagnostics.append(error(f"basic.{key}", f"missing required basic field '{key}'"))
    return diagnostics


def _validate_general_parameters(raw: dict[str, Any]) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    params = raw.get("parameters")
    if not isinstance(params, dict):
        return [error("parameters", "missing parameters block")]

    design = params.get("design")
    if not isinstance(design, list) or not design:
        diagnostics.append(error("parameters.design", "parameters.design must be a non-empty list"))
    else:
        diagnostics.extend(_validate_general_design(design))

    physical = params.get("physical")
    if not isinstance(physical, list) or not physical:
        diagnostics.append(error("parameters.physical", "parameters.physical must be a non-empty list"))
    else:
        diagnostics.extend(_validate_general_physical(physical))
    return diagnostics


def _validate_general_design(design: list[Any]) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for index, item in enumerate(design):
        if not isinstance(item, dict):
            diagnostics.append(error(f"parameters.design[{index}]", "design item must be a mapping"))
            continue
        name = str(item.get("name", index))
        path = f"parameters.design[{name}]"
        if "name" not in item:
            diagnostics.append(error(path, "missing design parameter name"))
        if "bounds" not in item:
            diagnostics.append(error(path, "missing design parameter bounds"))
        elif not _valid_bounds(item["bounds"]):
            diagnostics.append(error(path, "bounds must be [lower, upper]"))
    return diagnostics


def _validate_general_physical(physical: list[Any]) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for index, item in enumerate(physical):
        if not isinstance(item, dict):
            diagnostics.append(error(f"parameters.physical[{index}]", "physical item must be a mapping"))
            continue
        name = str(item.get("name", index))
        path = f"parameters.physical[{name}]"
        if "name" not in item:
            diagnostics.append(error(path, "missing physical parameter name"))
        diagnostics.extend(_validate_writer_node(item, path))
    return diagnostics


def _validate_writer_node(node: dict[str, Any], path: str) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    writerType = node.get("writerType")
    if not writerType:
        diagnostics.append(error(path, "missing writerType"))
        return diagnostics

    try:
        writerCls = getWriter(str(writerType))
        writerCls.validateSpec(node)
    except (ValueError, TypeError) as exc:
        diagnostics.append(error(path, str(exc)))
    return diagnostics


def _validate_general_series(raw: dict[str, Any], base_path: Path) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    series_list = raw.get("series", [])
    if not isinstance(series_list, list):
        return [error("series", "series must be a list")]

    for index, series in enumerate(series_list):
        if not isinstance(series, dict):
            diagnostics.append(error(f"series[{index}]", "series item must be a mapping"))
            continue
        series_id = str(series.get("id", index))
        series_path = f"series[{series_id}]"
        if "id" not in series:
            diagnostics.append(error(series_path, "missing series id"))
        diagnostics.extend(_validate_extract_node(series.get("sim"), f"{series_path}.sim", is_obs=False, base_path=base_path))
        diagnostics.extend(_validate_extract_node(series.get("obs"), f"{series_path}.obs", is_obs=True, base_path=base_path))
    return diagnostics


def _validate_extract_node(node: Any, path: str, *, is_obs: bool, base_path: Path) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if node is None:
        return diagnostics
    if not isinstance(node, dict):
        return [error(path, "extract node must be a mapping")]

    has_call = "call" in node
    has_reader = "readerType" in node
    if has_call == has_reader:
        return [error(path, "must declare exactly one of call or readerType")]

    if has_call:
        if is_obs:
            return [error(path, "obs does not support call nodes")]
        return _validate_call_extract(node.get("call"), path)

    diagnostics.extend(_validate_reader_node(node, path, is_obs=is_obs, base_path=base_path))
    return diagnostics


def _validate_call_extract(call: Any, path: str) -> list[Diagnostic]:
    if not isinstance(call, dict):
        return [error(path, "call extract must be a mapping")]

    diagnostics: list[Diagnostic] = []
    if "func" not in call:
        diagnostics.append(error(path, "missing call.func"))
    if "args" not in call:
        diagnostics.append(error(path, "missing call.args"))
    return diagnostics


def _validate_reader_node(node: dict[str, Any], path: str, *, is_obs: bool, base_path: Path) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    readerType = node.get("readerType")
    if not readerType:
        diagnostics.append(error(path, "missing readerType"))
        return diagnostics

    try:
        readerCls = getReader(str(readerType))
        readerCls.validateSpec(node, base_path=base_path, check_file=is_obs)
    except (ValueError, TypeError) as exc:
        message, suggestion = _split_suggestion(str(exc))
        diagnostics.append(error(path, message, suggestion))
    return diagnostics


def _validate_general_functions(raw: dict[str, Any], base_path: Path) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for index, func in enumerate(raw.get("functions", [])):
        if not isinstance(func, dict):
            diagnostics.append(error(f"functions[{index}]", "function item must be a mapping"))
            continue
        name = str(func.get("name", index))
        path = f"functions[{name}]"
        if "name" not in func:
            diagnostics.append(error(path, "missing function name"))
        if func.get("kind") == "external" and "file" in func:
            file_path = resolve_config_path(func["file"], base_path)
            if file_path is None or not file_path.exists():
                diagnostics.append(error(path, f"external function file not found: {func['file']}"))
    return diagnostics


def _validate_general_dependencies(raw: dict[str, Any]) -> list[Diagnostic]:
    return []


def _run_general_fallback(raw: dict[str, Any], base_path: Path) -> list[Diagnostic]:
    try:
        RunConfig.from_raw(raw, base_path)
    except (ValueError, FileNotFoundError, yaml.YAMLError) as exc:
        return [_translate_general_exception(raw, exc)]
    return []


def _translate_general_exception(raw: dict[str, Any], exc: Exception) -> Diagnostic:
    message = str(exc)
    path = "config"
    suggestion = None

    for series in raw.get("series", []):
        if not isinstance(series, dict):
            continue
        series_id = str(series.get("id", "<unknown>"))
        sim = series.get("sim")
        obs = series.get("obs")

        if "series[" in message and f"series[{series_id}]" in message:
            if ".sim" in message:
                path = f"series[{series_id}].sim"
            elif ".obs" in message:
                path = f"series[{series_id}].obs"

        if isinstance(obs, dict) and _is_missing_column_error(message) and _missing_column(obs):
            path = f"series[{series_id}].obs"
        elif isinstance(sim, dict) and _is_missing_column_error(message) and _missing_column(sim):
            path = f"series[{series_id}].sim"

        if isinstance(obs, dict) and _is_missing_rows_error(message) and _missing_rows(obs):
            path = f"series[{series_id}].obs"
        elif isinstance(sim, dict) and _is_missing_rows_error(message) and _missing_rows(sim):
            path = f"series[{series_id}].sim"

        if isinstance(obs, dict) and _is_missing_file_error(message) and "file" not in obs:
            path = f"series[{series_id}].obs"
        elif isinstance(sim, dict) and _is_missing_file_error(message) and "file" not in sim:
            path = f"series[{series_id}].sim"

    translated_message, suggestion = _translate_message(message, suggestion)
    if translated_message.startswith("Duplicate series id: "):
        series_id = translated_message.removeprefix("Duplicate series id: ")
        return error(f"series[{series_id}]", f"duplicate series id: {series_id}", "make each series.id unique")
    if translated_message.startswith("Duplicate function name: "):
        function_name = translated_message.removeprefix("Duplicate function name: ")
        return error(f"functions[{function_name}]", f"duplicate function name: {function_name}", "make each function.name unique")
    if translated_message.startswith("Missing dependencies in environment: "):
        return error(
            "config.dependencies",
            translated_message,
            "check derived/objectives/constraints/diagnostics refs and function args",
        )
    return error(path, translated_message, suggestion)


def _translate_message(message: str, suggestion: str | None) -> tuple[str, str | None]:
    for key, translated in GENERAL_ERROR_TRANSLATIONS.items():
        if key in message:
            return translated
    return message, suggestion


def _is_missing_column_error(message: str) -> bool:
    return "Must set exactly one of colSpan or colNum" in message


def _is_missing_rows_error(message: str) -> bool:
    return "must define at least one row via 'rowRanges' or 'rowList'" in message


def _is_missing_file_error(message: str) -> bool:
    return "missing 'file'" in message


def _missing_column(node: dict[str, Any]) -> bool:
    return "colSpan" not in node and "colNum" not in node


def _missing_rows(node: dict[str, Any]) -> bool:
    return not node.get("rowRanges") and not node.get("rowList")


def _valid_bounds(value: Any) -> bool:
    return isinstance(value, list) and len(value) == 2


def _split_suggestion(message: str) -> tuple[str, str | None]:
    if "|" not in message:
        return message, None
    msg, suggestion = message.split("|", 1)
    return msg, suggestion
