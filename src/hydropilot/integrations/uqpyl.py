from dataclasses import dataclass, field
import warnings

import numpy as np

from UQPyL import problem as _uqpylProblem

_requiredInterfaces = ("SimContext", "SimulatorBase", "ModelEvaluatorBase")
_missingInterfaces = [name for name in _requiredInterfaces if not hasattr(_uqpylProblem, name)]
if _missingInterfaces:
    raise ImportError(
        "HydroPilot UQPyLAdapter requires the updated UQPyL ModelProblem interfaces: "
        f"{', '.join(_missingInterfaces)}. Install the updated UQPyL development source; "
        "the PyPI UQPyL 2.1.6 package does not expose these interfaces."
    )

from UQPyL.problem import Eval, ModelEvaluatorBase, ModelProblem, SimContext, SimulatorBase

from ..api.sim_model import SimModel
from ..runtime.context import SimulationContext


def _problem_name(model: SimModel) -> str | None:
    cfg = getattr(model, "cfg", None)
    basic = getattr(cfg, "basic", None)
    return getattr(basic, "name", None)


def _recordLabels(model: SimModel, blockName: str) -> list[str] | None:
    block = getattr(model.cfg, blockName, None)
    items = getattr(block, "items", None)
    return None if items is None else [item.id for item in items]


@dataclass(frozen=True, kw_only=True)
class _HydroPilotSimContext(SimContext):
    """Carries the complete HydroPilot simulation behind the UQPyL view."""

    simulation: SimulationContext = field(repr=False, compare=False)
    _sourceToken: object = field(repr=False, compare=False)


class _HydroPilotSimulator(SimulatorBase):
    """Runs only simulation and extraction for each native context."""

    def __init__(self, problem):
        self.problem = problem

    def run(self, X):
        return self.problem._runContext(self.problem.validate(X))


class _HydroPilotEvaluator(ModelEvaluatorBase):
    def __init__(self, problem):
        self.problem = problem

    def evaluate(self, X, simContext, target=None):
        if target not in (None, "objs", "cons", "sims"):
            raise ValueError(f"Unknown UQPyL evaluation target: {target!r}")
        simulation = self.problem._getSimulation(X, simContext)
        if target == "sims":
            return Eval(sims=simContext.sims, target=target)
        processed = self.problem.model._post(simulation, target=target)
        return Eval(objs=processed.objs, cons=processed.cons, sims=simContext.sims, target=target)


class UQPyLAdapter(ModelProblem):
    """Wraps SimModel using native ModelProblem interfaces and per-run contexts."""

    def __init__(self, cfgPath: str):
        self.model = SimModel(cfgPath)
        self.seriesLabels = self._collect_series_labels()
        self._contextToken = object()

        obs, mask = self._build_obs_and_mask()
        if not self.seriesLabels:
            self.model.close()
            raise ValueError("UQPyLAdapter requires at least one simulation series.")

        super().__init__(
            nInput=self.model.nInput,
            nObj=self.model.nOutput,
            nCon=self.model.nConstraints,
            varType=self.model.varType,
            varSet=self.model.varSet,
            ub=self.model.ub,
            lb=self.model.lb,
            xLabels=self.model.xLabels,
            optType=self.model.optType,
            simFunc=self._sim_func,
            objFunc=self._objFunc,
            conFunc=self._conFunc if self.model.nConstraints > 0 else None,
            obs=obs,
            mask=mask,
            seriesLabels=self.seriesLabels,
            objLabels=_recordLabels(self.model, "objectives"),
            conLabels=_recordLabels(self.model, "constraints"),
            name=_problem_name(self.model),
        )
        self.simulator = _HydroPilotSimulator(self)
        self.evaluator = _HydroPilotEvaluator(self)

    def _collect_series_labels(self) -> list[str]:
        series_items = getattr(self.model.cfg, "series", [])
        labels: list[str] = []
        for item in series_items:
            if getattr(item, "obs", None) is None:
                continue
            labels.append(item.id)
        return labels or [item.id for item in series_items]

    def _build_obs_and_mask(self) -> tuple[np.ndarray | None, np.ndarray | None]:
        obs_by_series = {}
        max_len = 0
        for sid in self.seriesLabels:
            item = self.model.session.executor.services.obsStore.get(sid)
            if item is None:
                continue
            arr = np.asarray(item, dtype=float).ravel()
            obs_by_series[sid] = arr
            max_len = max(max_len, arr.size)

        if not obs_by_series or max_len == 0:
            self.seriesLabels = [item.id for item in self.model.cfg.series]
            return None, None

        labels = [sid for sid in self.seriesLabels if sid in obs_by_series]
        self.seriesLabels = labels
        n_series = len(labels)
        obs = np.full((max_len, n_series), np.nan, dtype=float)
        mask = np.ones((max_len, n_series), dtype=bool)

        for col, sid in enumerate(labels):
            arr = obs_by_series[sid]
            obs[:arr.size, col] = arr
            mask[:arr.size, col] = False
            mask[np.isnan(obs[:, col]), col] = True

        return obs, mask

    def _runContext(self, X):
        # Snapshot inputs so later edits to the caller's array cannot change
        # which parameters belong to this simulation context.
        parameters = np.array(X, dtype=float, copy=True)
        result = self.model._runSimulation(parameters)
        sim = self._validate_sim(self._build_sim_tensor(result), parameters.shape[0])
        return _HydroPilotSimContext(
            sims=sim,
            obs=self.obs,
            mask=self.mask,
            simulation=result,
            _sourceToken=self._contextToken,
        )

    def _build_sim_tensor(self, result) -> np.ndarray:
        if result.series is None:
            raise ValueError("HydroPilot simulation did not return any series data.")

        n_samples = result.X.shape[0]
        valuesBySeries = {}
        for sid in self.seriesLabels:
            values = result.series.get(sid)
            if values is None:
                continue
            arr = np.asarray(values, dtype=float)
            if arr.ndim == 1:
                arr = arr.reshape(1, -1)
            if arr.ndim != 2 or arr.shape[0] != n_samples:
                raise ValueError(
                    f"Simulation series '{sid}' must have shape (n_samples, n_time); got {arr.shape}."
                )
            valuesBySeries[sid] = arr

        if self.obs is None:
            n_time = max((arr.shape[1] for arr in valuesBySeries.values()), default=0)
            n_series = len(self.seriesLabels)
        else:
            n_time, n_series = self.obs.shape
        sim = np.full((n_samples, n_time, n_series), np.nan, dtype=float)

        for col, sid in enumerate(self.seriesLabels):
            arr = valuesBySeries.get(sid)
            if arr is None:
                continue
            width = min(n_time, arr.shape[1])
            sim[:, :width, col] = arr[:, :width]

        self._warnSimNaN(sim)
        return sim

    def _warnSimNaN(self, sim: np.ndarray) -> None:
        missing = np.isnan(sim)
        if self.mask is not None:
            missing &= ~self.mask[None, :, :]
        positions = "at observed positions" if self.obs is not None else "in simulation output"
        for sampleIndex, seriesIndex in np.argwhere(missing.any(axis=1)):
            count = int(missing[sampleIndex, :, seriesIndex].sum())
            warnings.warn(
                f"UQPyL sample {sampleIndex + 1}, series '{self.seriesLabels[seriesIndex]}': "
                f"{count} simulation values are NaN {positions}; "
                "missing values are limited to this run. Observations and mask are unchanged.",
                RuntimeWarning,
                stacklevel=3,
            )

    def _validate_sim(self, sims, n_samples: int):
        if (
            isinstance(sims, np.ndarray)
            and sims.ndim > 0
            and np.issubdtype(sims.dtype, np.number)
            and (
                (self.obs is not None and sims.shape[1:] == self.obs.shape)
                or (self.obs is None and sims.ndim == 3 and sims.shape[2] == len(self.seriesLabels))
            )
        ):
            # Keep run-specific NaNs in the output without expanding the shared
            # observation mask. Delegate all other checks to ModelProblem.
            nanPositions = np.isnan(sims)
            if nanPositions.any():
                validationValues = sims.copy()
                validationValues[nanPositions] = 0
                super()._validate_sim(validationValues, n_samples)
                return sims
        return super()._validate_sim(sims, n_samples)

    def _sim_func(self, X):
        return self.simulator.run(X).sims

    def _getSimulation(self, X, context):
        if not isinstance(context, _HydroPilotSimContext) or context._sourceToken is not self._contextToken:
            raise ValueError("Use a simulation context returned by this UQPyLAdapter's simulate(X).")
        result = context.simulation
        if not np.array_equal(result.X, self.validate(X), equal_nan=True):
            raise ValueError("X does not match the parameters in the simulation context.")
        return result

    def _objFunc(self, X, context):
        return self.model._post(self._getSimulation(X, context), target="objs").objs

    def _conFunc(self, X, context):
        return self.model._post(self._getSimulation(X, context), target="cons").cons

    def close(self):
        self.model.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
