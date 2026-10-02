import traceback
from copy import deepcopy
from dataclasses import dataclass, field
from threading import RLock
from typing import Any

import numpy as np

from .errors import RunError


@dataclass
class PostState:
    values: dict = field(default_factory=dict)
    derivedValues: dict = field(default_factory=dict)
    derivedErrors: dict = field(default_factory=dict)
    errors: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    completed: set = field(default_factory=set)
    fullCompleted: bool = False


@dataclass
class PostResult:
    objs: np.ndarray | None
    cons: np.ndarray | None
    diags: np.ndarray | None


@dataclass
class SimulationContext:
    """Owned simulation data and post-processing state for one batch."""

    X: np.ndarray
    P: np.ndarray | None
    series: dict[str, np.ndarray] | None
    obs: dict[str, np.ndarray] | None
    records: tuple[dict, ...]
    sourceToken: object = field(repr=False)
    postStates: list[PostState] = field(default_factory=list, repr=False)
    lock: Any = field(default_factory=RLock, repr=False)

    def __post_init__(self):
        self.records = tuple(deepcopy(record) for record in self.records)
        self.X = self._ownArray(self.X)
        self.P = None if self.P is None else self._ownArray(self.P)
        self.series = self._ownArrays(self.series)
        self.obs = self._ownArrays(self.obs)
        self.postStates = [PostState() for _ in self.records]

    @staticmethod
    def _ownArray(values):
        array = np.array(values, copy=True)
        array.setflags(write=False)
        return array

    @classmethod
    def _ownArrays(cls, values):
        return None if values is None else {key: cls._ownArray(value) for key, value in values.items()}

    def recordSnapshot(self, index):
        record = deepcopy(self.records[index])
        state = self.postStates[index]
        record.update(deepcopy(state.derivedValues))
        record.update(deepcopy(state.values))
        record["postErrors"] = list(state.errors.values())
        if state.errors and "error" not in record:
            record["error"] = next(iter(state.errors.values()))
        record["warnings"] = record.get("warnings", []) + deepcopy(state.warnings)
        for target, block in [("objs", "obj"), ("cons", "con"), ("diags", "diag")]:
            record[f"{block}_state"] = (
                "skipped" if record.get(f"{block}_state") == "skipped" else
                "error" if target in state.errors else "done" if target in state.completed
                else record.get(f"{block}_state", "pending")
            )
        return record

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
