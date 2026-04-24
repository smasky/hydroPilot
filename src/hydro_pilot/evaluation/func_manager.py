import hashlib
import importlib.util
import inspect
import sys
from pathlib import Path
from typing import Any, Callable, Dict

import numpy as np


# -------------------------------------------------------------
# Built-in metric functions
# -------------------------------------------------------------

def _r_square(sim: np.ndarray, obs: np.ndarray) -> float:
    """Coefficient of determination (R2)."""
    ssTot = np.sum((obs - np.mean(obs)) ** 2)
    ssRes = np.sum((obs - sim) ** 2)
    if ssTot == 0:
        return 1.0 if ssRes == 0 else 0.0
    return float(1.0 - ssRes / ssTot)


def _mse(sim: np.ndarray, obs: np.ndarray) -> float:
    """Mean Squared Error."""
    return float(np.mean((obs - sim) ** 2))


def _rmse(sim: np.ndarray, obs: np.ndarray) -> float:
    """Root Mean Squared Error."""
    return float(np.sqrt(np.mean((obs - sim) ** 2)))


def _nse(sim: np.ndarray, obs: np.ndarray) -> float:
    """Nash-Sutcliffe Efficiency."""
    denominator = np.sum((obs - np.mean(obs)) ** 2)
    numerator = np.sum((obs - sim) ** 2)
    if denominator == 0:
        return 1.0 if numerator == 0 else float("-inf")
    return float(1.0 - numerator / denominator)


def _kge(sim: np.ndarray, obs: np.ndarray) -> float:
    """Kling-Gupta Efficiency."""
    meanSim = np.mean(sim)
    meanObs = np.mean(obs)
    stdSim = np.std(sim, ddof=0)
    stdObs = np.std(obs, ddof=0)

    if stdObs == 0 or meanObs == 0:
        return float("-inf")

    r = np.corrcoef(sim, obs)[0, 1] if stdSim > 0 else 0.0
    beta = meanSim / meanObs
    gamma = (stdSim / meanSim) / (stdObs / meanObs) if meanSim != 0 else 0.0

    return float(1.0 - np.sqrt((r - 1.0) ** 2 + (beta - 1.0) ** 2 + (gamma - 1.0) ** 2))


def _pbias(sim: np.ndarray, obs: np.ndarray) -> float:
    """Percent Bias (%)."""
    sumObs = np.sum(obs)
    if sumObs == 0:
        return 0.0
    return float(100.0 * np.sum(sim - obs) / sumObs)


def _log_nse(sim: np.ndarray, obs: np.ndarray) -> float:
    """Nash-Sutcliffe Efficiency on log-transformed values.

    Zeros and negatives are replaced with a small epsilon before log.
    """
    eps = 1e-6
    logSim = np.log(np.maximum(sim, eps))
    logObs = np.log(np.maximum(obs, eps))
    return _nse(logSim, logObs)


def _sum_series(*args) -> np.ndarray:
    """Sum multiple series arrays element-wise."""
    arrays = [np.asarray(v) for v in args]
    return np.sum(arrays, axis=0)


BUILTIN_FUNCS: Dict[str, Callable[..., Any]] = {
    "R2": lambda sim, obs: _r_square(np.asarray(sim), np.asarray(obs)),
    "RMSE": lambda sim, obs: _rmse(np.asarray(sim), np.asarray(obs)),
    "MSE": lambda sim, obs: _mse(np.asarray(sim), np.asarray(obs)),
    "NSE": lambda sim, obs: _nse(np.asarray(sim), np.asarray(obs)),
    "KGE": lambda sim, obs: _kge(np.asarray(sim), np.asarray(obs)),
    "PBIAS": lambda sim, obs: _pbias(np.asarray(sim), np.asarray(obs)),
    "LogNSE": lambda sim, obs: _log_nse(np.asarray(sim), np.asarray(obs)),
    "sum_series": _sum_series,
}


class FunctionManager:
    def __init__(self, cfg):
        self.cfg = cfg
        self.functions: Dict[str, Callable[..., Any]] = {}
        self._module_cache: Dict[Path, Any] = {}
        self._load_functions()

    def _load_functions(self) -> None:
        for alias, f_spec in self.cfg.functions.items():
            if f_spec.kind == "builtin":
                self.functions[alias] = self._load_builtin_func(alias, f_spec.name)
            elif f_spec.kind == "external":
                self.functions[alias] = self._load_external_func(
                    alias=alias,
                    func_name=f_spec.name,
                    file_path=f_spec.file,
                )
                self._validate_declared_args(alias, self.functions[alias], f_spec.args)
            else:
                raise ValueError(f"Unsupported function kind: {f_spec.kind}")

    def _load_builtin_func(self, alias: str, builtin_name: str) -> Callable[..., Any]:
        if builtin_name not in BUILTIN_FUNCS:
            available = ", ".join(sorted(BUILTIN_FUNCS))
            raise ValueError(
                f"Unknown builtin function '{builtin_name}' for alias '{alias}'. "
                f"Available builtins: {available}"
            )
        return BUILTIN_FUNCS[builtin_name]

    def _load_external_func(self, alias: str, func_name: str, file_path: Path) -> Callable[..., Any]:
        if file_path is None:
            raise ValueError(f"External function '{alias}' requires a file path.")
        if not file_path.exists():
            raise FileNotFoundError(f"External function file not found: {file_path}")
        module = self._load_module_from_file(file_path)
        if not hasattr(module, func_name):
            raise ValueError(f"Function '{func_name}' not found in external file: {file_path}")
        func = getattr(module, func_name)
        if not callable(func):
            raise TypeError(f"Attribute '{func_name}' in {file_path} exists but is not callable.")
        return func

    def _load_module_from_file(self, file_path: Path):
        if file_path in self._module_cache:
            return self._module_cache[file_path]
        unique_name = self._build_module_name(file_path)
        spec = importlib.util.spec_from_file_location(unique_name, str(file_path))
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot create import spec from file: {file_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[unique_name] = module
        spec.loader.exec_module(module)
        self._module_cache[file_path] = module
        return module

    @staticmethod
    def _build_module_name(file_path: Path) -> str:
        digest = hashlib.md5(str(file_path).encode("utf-8")).hexdigest()[:10]
        return f"_uq_func_{file_path.stem}_{digest}"

    @staticmethod
    def _validate_declared_args(alias: str, func: Callable[..., Any], declared_args) -> None:
        if not declared_args:
            return
        sig = inspect.signature(func)
        params = sig.parameters
        has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
        if has_var_kw:
            return
        missing = [arg for arg in declared_args if arg not in params]
        if missing:
            raise ValueError(
                f"Function '{alias}' declared args {missing}, "
                f"but callable signature is {sig}"
            )

    def has_function(self, func_name: str) -> bool:
        return func_name in self.functions

    def get(self, func_name: str) -> Callable[..., Any]:
        if func_name not in self.functions:
            available = ", ".join(sorted(self.functions))
            raise ValueError(
                f"Function '{func_name}' is not registered. "
                f"Available functions: {available}"
            )
        return self.functions[func_name]

    def call(self, func_name: str, *args):
        func = self.get(func_name)
        try:
            return func(*args)
        except TypeError as e:
            raise TypeError(
                f"Failed calling function '{func_name}' with {len(args)} args: {e}"
            ) from e
