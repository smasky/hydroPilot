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


def ensure_warnings(context: dict[str, Any]) -> list[RunError]:
    return context.setdefault(KEY_WARNINGS, [])


def append_warning(context: dict[str, Any], warning: RunError) -> None:
    warning.severity = "warning"
    ensure_warnings(context).append(warning)


def set_physical_params(context: dict[str, Any], P) -> None:
    context[KEY_P] = P


def set_run_error(context: dict[str, Any], error: RunError) -> None:
    error.severity = "fatal"
    context[KEY_ERROR] = error


def set_unexpected_error(context: dict[str, Any], exc: Exception) -> None:
    archive = context.get("runner_log_archive")
    message = str(exc)
    if archive:
        message = f"{message}; archived_logs={archive}"
    context[KEY_ERROR] = RunError(
        stage="unknown",
        code="UNEXPECTED_EXCEPTION",
        target="simulation",
        message=message,
        severity="fatal",
        traceback=traceback.format_exc(),
    )


def has_error(context: dict[str, Any]) -> bool:
    return KEY_ERROR in context


def apply_on_error_defaults(context: dict[str, Any], cfg) -> None:
    for item in cfg.objectives.items:
        context[item.id] = item.on_error
    for item in cfg.constraints.items:
        context[item.id] = item.on_error
    for item in cfg.diagnostics.items:
        context[item.id] = item.on_error


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
