from typing import Any, Callable, Dict

import numpy as np


def _r_square(sim: np.ndarray, obs: np.ndarray) -> float:
    ssTot = np.sum((obs - np.mean(obs)) ** 2)
    ssRes = np.sum((obs - sim) ** 2)
    if ssTot == 0:
        return 1.0 if ssRes == 0 else 0.0
    return float(1.0 - ssRes / ssTot)


def _mse(sim: np.ndarray, obs: np.ndarray) -> float:
    return float(np.mean((obs - sim) ** 2))


def _rmse(sim: np.ndarray, obs: np.ndarray) -> float:
    return float(np.sqrt(np.mean((obs - sim) ** 2)))


def _nse(sim: np.ndarray, obs: np.ndarray) -> float:
    denominator = np.sum((obs - np.mean(obs)) ** 2)
    numerator = np.sum((obs - sim) ** 2)
    if denominator == 0:
        return 1.0 if numerator == 0 else float("-inf")
    return float(1.0 - numerator / denominator)


def _kge(sim: np.ndarray, obs: np.ndarray) -> float:
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
    sumObs = np.sum(obs)
    if sumObs == 0:
        return 0.0
    return float(100.0 * np.sum(sim - obs) / sumObs)


def _log_nse(sim: np.ndarray, obs: np.ndarray) -> float:
    eps = 1e-6
    logSim = np.log(np.maximum(sim, eps))
    logObs = np.log(np.maximum(obs, eps))
    return _nse(logSim, logObs)


def _sum_series(*args) -> np.ndarray:
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
