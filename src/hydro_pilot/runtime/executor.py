import shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from ..api.results import BatchRunResult
from ..runtime.errors import RunError as SeriesRunError
from .errors import RunError
from .services import ExecutionServices
from .context import (
    apply_on_error_defaults,
    append_warning,
    create_context,
    ensure_warnings,
    has_error,
    set_physical_params,
    set_run_error,
    set_unexpected_error,
    to_float_or_nan,
)


class Executor:
    FAILED_RUNNER_LOG_DIR = "runner_failures"

    def __init__(self, cfg, workspace, reporter):
        self.cfg = cfg
        self.workspace = workspace
        self.reporter = reporter
        self.services = ExecutionServices.from_config(cfg)

        self.nInput, self.xLabels, self.varType, self.varSet, self.ub, self.lb = (
            self.services.paramSpace.get_param_info()
        )
        self.nOutput, self.optType, self.nConstraints = self.services.evaluator.get_evaluation_info()
        self.optSign = [1 if s == "min" else -1 for s in self.optType]

    def run(self, X) -> BatchRunResult:
        X = np.asarray(X)
        if X.ndim == 1:
            X = X.reshape(1, -1)
        n = X.shape[0]
        n_obj = self.services.evaluator.nOutput
        n_con = self.services.evaluator.nConstraints
        n_diag = len(self.cfg.diagnostics.items)

        objs = np.zeros((n, n_obj))
        cons = np.full((n, n_con), self._constraint_penalty()) if n_con > 0 else None
        diags = np.full((n, n_diag), np.nan) if n_diag > 0 else None
        P = None
        if self.cfg.parameters.physical:
            P = np.full((n, len(self.cfg.parameters.physical)), np.nan)

        batch_id = self.reporter.newBatchId()
        records = []

        if self.cfg.basic.parallel > 1:
            with ThreadPoolExecutor(max_workers=self.cfg.basic.parallel) as executor:
                futures = [
                    executor.submit(self._run_one, X[i, :], i, batch_id)
                    for i in range(n)
                ]
                records = [future.result() for future in futures]
        else:
            for i in range(n):
                records.append(self._run_one(X[i, :], i, batch_id))

        for rec in records:
            i = int(rec["i"])
            for j, obj_cfg in enumerate(self.cfg.objectives.items):
                val = to_float_or_nan(rec.get(obj_cfg.id, np.nan))
                if np.isnan(val):
                    val = self._objective_penalty(j)
                objs[i, j] = val
            if cons is not None:
                for j, con_cfg in enumerate(self.cfg.constraints.items):
                    val = to_float_or_nan(rec.get(con_cfg.id, np.nan))
                    if np.isnan(val):
                        val = self._constraint_penalty()
                    cons[i, j] = val
            if diags is not None:
                for j, diag_cfg in enumerate(self.cfg.diagnostics.items):
                    diags[i, j] = to_float_or_nan(rec.get(diag_cfg.id, np.nan))
            if P is not None:
                p_vals = np.asarray(rec.get("P", []), dtype=float).ravel()
                if p_vals.size:
                    P[i, :min(P.shape[1], p_vals.size)] = p_vals[:P.shape[1]]

        series = self._build_series_buffers(records, n)

        return BatchRunResult(
            X=np.asarray(X),
            P=P,
            objs=objs,
            cons=cons,
            diags=diags,
            series=series,
        )

    def _run_one(self, X, i, batch_id):
        workPath = self.workspace.acquire_instance()
        context = create_context(X, i, batch_id)
        try:
            self.services.paramApplier.apply(workPath, X, context)
            set_physical_params(context, self.services.paramApplier.get_physical_params(X))
            self.services.runner.run(workPath, self.cfg.basic.command, self.cfg.basic.timeout)
            context = self.services.seriesExtractor.extract(workPath, context)
            ensure_warnings(context)
            scalars = self.services.evaluator.evaluate_all(context)
            context.update(scalars)
        except RunError as e:
            self._archive_runner_logs(workPath, context, e)
            set_run_error(context, e)
        except Exception as e:
            self._archive_runner_logs(workPath, context, e)
            set_unexpected_error(context, e)
        finally:
            self.workspace.release_instance(workPath)
            if has_error(context):
                apply_on_error_defaults(context, self.cfg)
            if self.reporter is not None:
                try:
                    self.reporter.submit(context)
                except RuntimeError:
                    pass
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
                raise ValueError(
                    f"Series '{sid}' has no fixed size in config/template; "
                    "run(X) requires a precomputable series length"
                )
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
