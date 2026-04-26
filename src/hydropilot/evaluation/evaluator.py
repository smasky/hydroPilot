import numpy as np

from ..runtime.context import append_warning, ensure_warnings
from ..runtime.errors import RunError


class Evaluator:
    def __init__(self, cfg, funcManager):
        self.cfg = cfg
        self.funcManager = funcManager

        self.nOutput, self.optType, self.obj_refs, self.nConstraints, self.con_refs = (
            self._parse_objectives_constraints()
        )
        self.diag_refs = self._parse_diagnostics()
        self.fatalDerivedIds = self._build_fatal_derived_ids()

    def _parse_objectives_constraints(self):
        optType = []
        obj_refs = {}
        con_refs = {}

        for obj_cfg in self.cfg.objectives.items:
            optType.append(obj_cfg.sense)
            obj_refs[obj_cfg.id] = obj_cfg.ref

        nOutput = len(optType)

        for con_cfg in self.cfg.constraints.items:
            con_refs[con_cfg.id] = con_cfg.ref

        nConstraints = len(con_refs)

        return nOutput, optType, obj_refs, nConstraints, con_refs

    def _parse_diagnostics(self):
        diag_refs = {}
        for diag_cfg in self.cfg.diagnostics.items:
            diag_refs[diag_cfg.id] = diag_cfg.ref
        return diag_refs

    def _build_fatal_derived_ids(self):
        """Build set of derived ids that are required by objectives or constraints.

        A derived whose failure would prevent computing an objective or constraint
        is fatal. A derived only referenced by diagnostics is non-fatal (warning).
        """
        # Collect all ref targets from objectives and constraints
        fatalRefs = set()
        for ref in self.obj_refs.values():
            fatalRefs.add(ref)
        for ref in self.con_refs.values():
            fatalRefs.add(ref)

        # Build derived dependency map: derived_id -> set of dependency ids
        derivedDeps = {}
        for d in self.cfg.derived:
            deps = set()
            if d.call:
                for contextKey in d.call.args:
                    deps.add(contextKey)
            derivedDeps[d.id] = deps

        # Traverse: any derived that is in fatalRefs or is depended on by a fatal derived
        fatalIds = set()
        changed = True
        while changed:
            changed = False
            for d in self.cfg.derived:
                if d.id in fatalIds:
                    continue
                # Direct: this derived is referenced by an objective/constraint
                if d.id in fatalRefs:
                    fatalIds.add(d.id)
                    changed = True
                    continue
                # Indirect: a fatal derived depends on this derived
                for otherId in fatalIds:
                    if d.id in derivedDeps.get(otherId, set()):
                        fatalIds.add(d.id)
                        changed = True
                        break

        return fatalIds

    def _normalize_value(self, val):
        if isinstance(val, (list, tuple, np.ndarray)):
            return np.asarray(val).ravel()
        return val

    def _to_scalar(self, value, label: str) -> float:
        value = self._normalize_value(value)
        if isinstance(value, np.ndarray):
            if value.size != 1:
                raise ValueError(
                    f"{label} must be scalar, but got array with shape {value.shape}"
                )
            return float(value.item())
        return float(value)

    def _collect_record_values(self, refs: dict, env: dict, kind: str) -> dict:
        result = {}
        for item_id, ref_id in refs.items():
            if ref_id not in env:
                raise RunError(
                    stage="evaluator",
                    code="MISSING_CONTEXT",
                    target=item_id,
                    message=f"{kind} '{item_id}' requires context key '{ref_id}'"
                )
            try:
                result[item_id] = self._to_scalar(env[ref_id], f"{kind} '{item_id}'")
            except Exception as e:
                raise RunError(
                    stage="evaluator",
                    code="INVALID_VALUE",
                    target=item_id,
                    message=f"{kind} '{item_id}' cannot be converted to scalar: {e}"
                ) from e
        return result

    def _collect_diagnostic_values(self, refs: dict, env: dict, context: dict) -> dict:
        """Collect diagnostic values with warning-on-failure semantics."""
        result = {}
        ensure_warnings(context)
        for item_id, ref_id in refs.items():
            diagCfg = next(item for item in self.cfg.diagnostics.items if item.id == item_id)
            if ref_id not in env:
                append_warning(context, RunError(
                    stage="evaluator", code="MISSING_CONTEXT", target=item_id,
                    message=f"Diagnostic '{item_id}' requires context key '{ref_id}'",
                ))
                result[item_id] = diagCfg.on_error
                continue
            try:
                result[item_id] = self._to_scalar(env[ref_id], f"Diagnostic '{item_id}'")
            except Exception as e:
                append_warning(context, RunError(
                    stage="evaluator", code="INVALID_VALUE", target=item_id,
                    message=f"Diagnostic '{item_id}' cannot be converted to scalar: {e}",
                ))
                result[item_id] = diagCfg.on_error
        return result

    def evaluate_all(self, context):
        env = context
        record = {}
        ensure_warnings(context)

        for derived in self.cfg.derived:
            d_id = derived.id
            isFatal = d_id in self.fatalDerivedIds

            try:
                func_name = derived.call.func
                args_list = derived.call.args
                func_args = []
                for context_key in args_list:
                    if context_key not in env:
                        raise RunError(
                            stage="derived",
                            code="DEPENDENCY_MISSING",
                            target=d_id,
                            message=f"Derived '{d_id}' requires context key '{context_key}'"
                        )
                    func_args.append(self._normalize_value(env[context_key]))
                result = self.funcManager.call(func_name, *func_args)

                if result is None:
                    raise RunError(
                        stage="derived",
                        code="EMPTY_RESULT",
                        target=d_id,
                        message=f"Derived '{d_id}' returned None"
                    )

                env[d_id] = result

            except RunError as e:
                if isFatal:
                    raise
                append_warning(context, e)
                env[d_id] = float("nan")

            except Exception as e:
                err = RunError(
                    stage="derived",
                    code="UNEXPECTED_ERROR",
                    target=d_id,
                    message=f"Derived '{d_id}' failed: {e}",
                )
                if isFatal:
                    raise err from e
                append_warning(context, err)
                env[d_id] = float("nan")

        record.update(self._collect_record_values(self.obj_refs, env, "Objective"))
        record.update(self._collect_record_values(self.con_refs, env, "Constraint"))
        record.update(self._collect_diagnostic_values(self.diag_refs, env, context))

        return record

    def get_evaluation_info(self):
        return self.nOutput, self.optType, self.nConstraints
