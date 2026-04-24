import traceback
from typing import Any

import numpy as np

from .errors import RunError

KEY_X = "X"
KEY_P = "P"
KEY_INDEX = "i"
KEY_BATCH_ID = "batch_id"
KEY_WARNINGS = "warnings"
KEY_ERROR = "error"


def create_context(X, i: int, batch_id: int) -> dict[str, Any]:
    return {
        KEY_X: np.asarray(X).ravel(),
        KEY_INDEX: int(i),
        KEY_BATCH_ID: int(batch_id),
        KEY_WARNINGS: [],
    }


def ensure_warnings(context: dict[str, Any]) -> list:
    return context.setdefault(KEY_WARNINGS, [])


def append_warning(context: dict[str, Any], warning: RunError) -> None:
    warning.severity = "warning"
    ensure_warnings(context).append(warning)


def set_physical_params(context: dict[str, Any], P) -> None:
    context[KEY_P] = P


def set_run_error(context: dict[str, Any], error: RunError) -> None:
    context[KEY_ERROR] = {
        "stage": error.stage,
        "code": error.code,
        "target": error.target,
        "message": error.message,
        "severity": "fatal",
        "traceback": error.traceback,
    }


def set_unexpected_error(context: dict[str, Any], exc: Exception) -> None:
    context[KEY_ERROR] = {
        "stage": "unknown",
        "code": "UNEXPECTED_EXCEPTION",
        "target": "simulation",
        "message": str(exc),
        "severity": "fatal",
        "traceback": traceback.format_exc(),
    }


def has_error(context: dict[str, Any]) -> bool:
    return KEY_ERROR in context


def apply_on_error_defaults(context: dict[str, Any], cfg) -> None:
    for obj_id in cfg.objectives.use:
        context[obj_id] = cfg.objectives.items[obj_id].on_error
    for con_id in cfg.constraints.use:
        context[con_id] = cfg.constraints.items[con_id].on_error
    for diag_id in cfg.diagnostics.use:
        context[diag_id] = cfg.diagnostics.items[diag_id].on_error


def to_float_or_nan(value) -> float:
    if value is None:
        return np.nan
    if hasattr(value, "item"):
        try:
            return float(value.item())
        except Exception:
            pass
    arr = np.asarray(value)
    if arr.size == 0:
        return np.nan
    if arr.size == 1:
        return float(arr.reshape(-1)[0])
    return np.nan
