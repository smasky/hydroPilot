import logging
import shutil
from pathlib import Path
from threading import Lock
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from ..api.results import BatchRunResult
from ..runtime.errors import RunError as SeriesRunError
from .errors import RunError
from .input_restore import InputRestorer
from .services import ExecutionServices
from .context import (
    PostResult,
    SimulationContext,
    append_warning,
    create_context,
    ensure_warnings,
    has_error,
    set_run_error,
    set_unexpected_error,
    to_float_or_nan,
)


logger = logging.getLogger(__name__)


class Executor:
    FAILED_RUNNER_LOG_DIR = "runner_failures"

    def __init__(self, cfg, workspace, reporter):
        self.cfg = cfg
        self.workspace = workspace
        self.reporter = reporter
        self.services = ExecutionServices.from_config(cfg)
        self.inputRestorer = InputRestorer(self.services.paramWritePlan)

        self.nInput, self.xLabels, self.varType, self.varSet, self.ub, self.lb = (
            self.services.paramSpace.get_param_info()
        )
        self.nOutput, self.optType, self.nConstraints = self.services.evaluator.get_evaluation_info()
        self.optSign = [1 if s == "min" else -1 for s in self.optType]
        self.initializeBatchCounter(0)

    def initializeBatchCounter(self, batchId):
        self._batchNo = int(batchId)
        self._batchLock = Lock()
        self._sourceToken = object()

    def run(self, X) -> BatchRunResult:
        simulation = self._runSimulation(X)
        processed = self._post(simulation)
        return BatchRunResult(
            X=simulation.X, P=simulation.P, objs=processed.objs,
            cons=processed.cons, diags=processed.diags,
            series=simulation.series, obs=simulation.obs,
        )

    def _runSimulation(self, X) -> SimulationContext:
        """Schedule parameter application and simulation on leased instances."""
        X = np.array(X, dtype=float, copy=True)
        if X.ndim == 1:
            X = X.reshape(1, -1)
        elif X.ndim != 2:
            raise ValueError(f"Expected X to be a 1D or 2D array, got {X.ndim}D")
        if X.shape[1] != self.nInput:
            raise ValueError(f"Expected {self.nInput} input parameters, got {X.shape[1]}")
        batchId = self._nextBatchId()
        n = X.shape[0]
        if self.cfg.basic.parallel > 1:
            with ThreadPoolExecutor(max_workers=self.cfg.basic.parallel) as pool:
                futures = [pool.submit(self._run_one, X[i], i, batchId) for i in range(n)]
                records = [future.result() for future in futures]
        else:
            records = [self._run_one(X[i], i, batchId) for i in range(n)]

        return self._finishSimulation(X, records)

    def _nextBatchId(self):
        with self._batchLock:
            self._batchNo += 1
            return self._batchNo

    def _finishSimulation(self, X, records):
        X = np.atleast_2d(X)
        n = len(X)
        series = self._build_series_buffers(records, n)
        obs = self._build_obs_buffers()
        P = None
        if self.cfg.parameters.physical:
            P = np.full((n, len(self.cfg.parameters.physical)), np.nan)
            for i, record in enumerate(records):
                values = np.asarray(record.get("P", []), dtype=float).ravel()
                P[i, :min(P.shape[1], values.size)] = values[:P.shape[1]]
        for record in records:
            record["archive_stage"] = "simulation"
            for sid, values in (obs or {}).items():
                record[f"{sid}.obs"] = values
            record["sim_status"] = "error" if has_error(record) else "warning" if record.get("warnings") else "ok"
            for block, config in [("obj", self.cfg.objectives), ("con", self.cfg.constraints), ("diag", self.cfg.diagnostics)]:
                record[f"{block}_state"] = "pending" if config.items else "skipped"
            self._notifyReporter(record)
        return SimulationContext(X, P, series, obs, tuple(records), self._sourceToken)

    def _post(self, simulation: SimulationContext, target=None) -> PostResult:
        if not isinstance(simulation, SimulationContext) or simulation.sourceToken is not self._sourceToken:
            raise ValueError("Use a simulation context created by this SimModel.")
        targets = ("objs", "cons", "diags") if target is None else (target,)
        if any(key not in ("objs", "cons", "diags") for key in targets):
            raise ValueError(f"Unknown post-processing target: {target!r}")
        blocks = {"objs": self.cfg.objectives.items, "cons": self.cfg.constraints.items,
                  "diags": self.cfg.diagnostics.items}
        with simulation.lock:
            for i, record in enumerate(simulation.records):
                state = simulation.postStates[i]
                if set(targets) <= state.completed and (target is not None or state.fullCompleted):
                    continue
                if has_error(record):
                    for key in targets:
                        state.errors[key] = record["error"]
                        state.values.update({item.id: item.on_error for item in blocks[key]})
                    state.completed.update(targets)
                    if target is None:
                        state.fullCompleted = True
                else:
                    self.services.evaluator._post(record, state, targets)
                # Match the existing finite/NaN conversion of run() and archive
                # exactly the values returned to the caller.
                for key in targets:
                    for j, item in enumerate(blocks[key]):
                        value = to_float_or_nan(state.values.get(item.id))
                        if np.isnan(value) and key != "diags":
                            value = self._objective_penalty(j) if key == "objs" else self._constraint_penalty()
                        state.values[item.id] = value
                snapshot = simulation.recordSnapshot(i)
                snapshot["archive_stage"] = "post"
                warning = self._notifyReporter(snapshot)
                if warning is not None and not any(
                    item.to_dict() == warning.to_dict() for item in record.get("warnings", []) + state.warnings
                ):
                    state.warnings.append(warning)

            def matrix(key):
                if key not in targets or (key != "objs" and not blocks[key]):
                    return None
                return np.asarray([[state.values[item.id] for item in blocks[key]]
                                   for state in simulation.postStates], dtype=float).reshape(len(simulation.records), len(blocks[key]))
            return PostResult(matrix("objs"), matrix("cons"), matrix("diags"))

    def _notifyReporter(self, record):
        if self.reporter is None:
            return None
        try:
            self.reporter.submit(record)
        except RuntimeError as error:
            warning = RunError(
                stage="reporter", code="REPORTER_SUBMIT_FAILED",
                target=str(self.workspace.archivePath),
                message=f"Could not archive run record: {error}. Run results are returned unchanged.",
                severity="warning",
            )
            if not any(item.to_dict() == warning.to_dict() for item in record.get("warnings", [])):
                append_warning(record, warning)
                logger.warning("batch=%s run=%s %s", record["batch_id"], record["i"] + 1, warning)
            return warning
        return None

    def _apply(self, workPath, X, context):
        """Transform and write parameters without executing or archiving a run."""
        self.services.paramApplier.apply(workPath, X, context)
        return context

    def _simulate(self, workPath, context):
        """Execute an already prepared instance and extract its series."""
        self.services.runner.run(workPath, self.cfg.basic.command, self.cfg.basic.timeout)
        context = self.services.seriesExtractor.extract(workPath, context)
        ensure_warnings(context)
        return context

    def _run_one(self, X, i, batch_id):
        workPath = self.workspace.acquire_instance()
        context = create_context(X, i, batch_id)
        restore_snapshot = None
        try:
            if getattr(self.cfg.basic, "reset", False):
                restore_snapshot = self.inputRestorer.capture(workPath)
            context = self._apply(workPath, X, context)
            context = self._simulate(workPath, context)
        except RunError as error:
            self._archive_runner_logs(workPath, context, error)
            set_run_error(context, error)
        except Exception as error:
            self._archive_runner_logs(workPath, context, error)
            set_unexpected_error(context, error)
        finally:
            if restore_snapshot is not None:
                try:
                    restore_snapshot.restore()
                except Exception as error:
                    append_warning(context, RunError(
                        "params", "INPUT_RESTORE_FAILED", workPath,
                        f"Failed to restore touched input files: {error}", severity="warning",
                    ))
            self.workspace.release_instance(workPath)
        return context

    def _objective_penalty(self, j):
        return np.inf * self.optSign[j]

    def _constraint_penalty(self):
        return np.inf

    def _build_series_buffers(self, records: list[dict], n_runs: int) -> dict[str, np.ndarray] | None:
        if not self.cfg.series:
            return None

        buffers: dict[str, np.ndarray] = {}
        for sid in self.cfg.series_index.keys():
            width = self._expected_series_width(sid)
            if width is None:
                actualWidths = [np.asarray(rec[f"{sid}.sim"]).size for rec in records if f"{sid}.sim" in rec]
                obs = self.services.obsStore.get(sid)
                width = max(actualWidths, default=0 if obs is None else np.asarray(obs).size)
            matrix = np.full((n_runs, width), np.nan)
            for rec in records:
                row_index = int(rec["i"])
                values = rec.get(f"{sid}.sim")
                if values is None:
                    continue
                arr = np.asarray(values, dtype=float).ravel()
                self._write_series_row(matrix, row_index, sid, arr, width, rec)
            buffers[sid] = matrix

        return buffers or None

    def _build_obs_buffers(self) -> dict[str, np.ndarray] | None:
        if not self.cfg.series:
            return None

        buffers: dict[str, np.ndarray] = {}
        for sid in self.cfg.series_index.keys():
            obs = self.services.obsStore.get(sid)
            if obs is None:
                continue
            buffers[sid] = np.asarray(obs, dtype=float).ravel()

        return buffers or None

    def _expected_series_width(self, sid: str) -> int | None:
        series_cfg = self.cfg.series_index.get(sid)
        if series_cfg is None:
            return None
        size = getattr(series_cfg, "size", None)
        if size is not None and int(size) > 0:
            return int(size)
        sim = getattr(series_cfg, "sim", None)
        spec = getattr(sim, "spec", None)
        if spec is not None:
            spec_size = getattr(spec, "size", None)
            if spec_size is not None and int(spec_size) > 0:
                return int(spec_size)
            rows = getattr(spec, "rows", None)
            if rows:
                return len(rows)
        return None

    @staticmethod
    def _write_series_row(matrix: np.ndarray, row_index: int, sid: str, arr: np.ndarray, width: int, rec: dict) -> None:
        if arr.size == width:
            matrix[row_index, :] = arr
            return

        limit = min(width, arr.size)
        if limit > 0:
            matrix[row_index, :limit] = arr[:limit]

        append_warning(
            rec,
            SeriesRunError(
                stage="series",
                code="LENGTH_MISMATCH",
                target=sid,
                message=f"Series '{sid}' expected length {width}, got {arr.size}; padded/truncated with NaN",
            ),
        )

    def _archive_runner_logs(self, work_path, context, exc: Exception) -> None:
        log_paths = self._get_runner_log_paths(work_path)
        if not log_paths:
            return

        existing = [path for path in log_paths if path.exists()]
        if not existing:
            return

        archive_root = Path(self.workspace.archivePath) / self.FAILED_RUNNER_LOG_DIR
        archive_root.mkdir(parents=True, exist_ok=True)

        copied = []
        for path in existing:
            target = archive_root / self._failure_log_name(context, path.name)
            shutil.copy2(path, target)
            copied.append(str(target))

        archive_note = self._format_archive_note(copied)
        if isinstance(exc, RunError):
            exc.message = f"{exc.message}; {archive_note}"
            return

        context["runner_log_archive"] = archive_note

    def _get_runner_log_paths(self, work_path) -> tuple[Path, ...]:
        log_paths = getattr(self.services.runner, "log_paths", None)
        if callable(log_paths):
            return tuple(Path(p) for p in log_paths(work_path))
        return ()

    @staticmethod
    def _failure_log_name(context, original_name: str) -> str:
        batch_id = int(context.get("batch_id", -1))
        run_id = int(context.get("i", -1)) + 1
        if original_name == "runner.stdout.log":
            suffix = "stdout.log"
        elif original_name == "runner.stderr.log":
            suffix = "stderr.log"
        else:
            suffix = original_name
        return f"{batch_id}_{run_id}.{suffix}"

    @staticmethod
    def _format_archive_note(paths: list[str]) -> str:
        joined = ", ".join(paths)
        return f"archived_logs={joined}"
