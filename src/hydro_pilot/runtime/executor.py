from concurrent.futures import ThreadPoolExecutor

import numpy as np

from .errors import RunError
from .services import ExecutionServices
from .context import (
    apply_on_error_defaults,
    create_context,
    ensure_warnings,
    has_error,
    set_physical_params,
    set_run_error,
    set_unexpected_error,
    to_float_or_nan,
)


class Executor:
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

    def evaluate(self, X):
        X = np.asarray(X)
        n = X.shape[0]
        n_obj = self.services.evaluator.nOutput
        n_con = self.services.evaluator.nConstraints

        objs = np.zeros((n, n_obj))
        cons = np.full((n, n_con), self._constraint_penalty()) if n_con > 0 else None

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
            for j, obj_id in enumerate(self.cfg.objectives.use):
                val = to_float_or_nan(rec.get(obj_id, np.nan))
                if np.isnan(val):
                    val = self._objective_penalty(j)
                objs[i, j] = val
            if cons is not None:
                for j, con_id in enumerate(self.cfg.constraints.use):
                    val = to_float_or_nan(rec.get(con_id, np.nan))
                    if np.isnan(val):
                        val = self._constraint_penalty()
                    cons[i, j] = val

        return {"objs": objs, "cons": cons}

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
            set_run_error(context, e)
        except Exception as e:
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
