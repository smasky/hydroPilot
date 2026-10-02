from copy import deepcopy
from dataclasses import replace

import numpy as np

from ..runtime.context import PostState, append_warning, ensure_warnings
from ..runtime.errors import RunError


class Evaluator:
    def __init__(self, cfg, funcManager):
        self.cfg = cfg
        self.funcManager = funcManager

        self.nOutput, self.optType, self.obj_refs, self.nConstraints, self.con_refs = (
            self._parse_objectives_constraints()
        )
        self.diag_refs = self._parse_diagnostics()
        self.derivedIndex = {item.id: item for item in cfg.derived}
        self.blocks = {
            "objs": cfg.objectives.items,
            "cons": cfg.constraints.items,
            "diags": cfg.diagnostics.items,
        }

    def _requiredDerived(self, refs):
        required = set()
        pending = list(refs)
        while pending:
            key = pending.pop()
            if key not in self.derivedIndex or key in required:
                continue
            required.add(key)
            pending.extend(self.derivedIndex[key].call.args)
        return required

    @staticmethod
    def _addWarning(state, error):
        warning = replace(error, severity="warning")
        if not any(item.to_dict() == warning.to_dict() for item in state.warnings):
            state.warnings.append(warning)

    def _compute(self, context, state, targets, includeUnused=False):
        env = deepcopy(context)
        env.update(deepcopy(state.derivedValues))
        refs = [item.ref for target in targets for item in self.blocks[target]]
        required = self._requiredDerived(refs)
        fatalTargets = tuple(self.blocks) if includeUnused else targets
        fatal = self._requiredDerived(
            item.ref for target in fatalTargets if target != "diags" for item in self.blocks[target]
        )
        if includeUnused:
            required.update(self.derivedIndex)

        for derived in self.cfg.derived:
            key = derived.id
            if key not in required:
                continue
            if key not in state.derivedValues and key not in state.derivedErrors:
                try:
                    missing = next((arg for arg in derived.call.args if arg not in env), None)
                    if missing is not None:
                        raise RunError("derived", "DEPENDENCY_MISSING", key,
                                       f"Derived '{key}' requires context key '{missing}'")
                    upstream = next((arg for arg in derived.call.args if arg in state.derivedErrors), None)
                    if upstream is not None:
                        raise RunError("derived", "DEPENDENCY_FAILED", key,
                                       f"Derived '{key}' requires failed derived '{upstream}'")
                    args = [self._normalize_value(deepcopy(env[arg])) for arg in derived.call.args]
                    value = self.funcManager.call(derived.call.func, *args)
                    if value is None:
                        raise RunError("derived", "EMPTY_RESULT", key, f"Derived '{key}' returned None")
                    state.derivedValues[key] = deepcopy(value)
                except RunError as error:
                    state.derivedErrors[key] = replace(error, severity="fatal")
                except Exception as error:
                    state.derivedErrors[key] = RunError(
                        "derived", "UNEXPECTED_ERROR", key, f"Derived '{key}' failed: {error}"
                    )
            if key in state.derivedErrors:
                error = state.derivedErrors[key]
                if key in fatal:
                    raise replace(error, severity="fatal")
                self._addWarning(state, error)
                env[key] = np.nan
                state.derivedValues[key] = np.nan
            else:
                env[key] = deepcopy(state.derivedValues[key])

        for target in targets:
            items = self.blocks[target]
            refsById = {item.id: item.ref for item in items}
            if target == "diags":
                warningContext = {"warnings": []}
                values = self._collect_diagnostic_values(refsById, env, warningContext)
                for warning in warningContext["warnings"]:
                    self._addWarning(state, warning)
            else:
                values = self._collect_record_values(refsById, env, "Objective" if target == "objs" else "Constraint")
            state.values.update(values)

    def _post(self, context, state, targets):
        """Compute requested blocks once, with caches owned by this simulation."""
        pending = tuple(key for key in self.blocks if key in targets and key not in state.completed)
        isFull = set(targets) == set(self.blocks)
        if not pending and (not isFull or state.fullCompleted):
            return
        try:
            previousError = next((state.errors[key] for key in targets if key in state.errors), None)
            if previousError is not None:
                raise previousError
            self._compute(context, state, pending, includeUnused=isFull)
        except RunError as error:
            for target in targets:
                state.errors[target] = error
                state.values.update({item.id: item.on_error for item in self.blocks[target]})
        except Exception as error:
            failure = RunError("evaluator", "UNEXPECTED_ERROR", "post", str(error))
            for target in targets:
                state.errors[target] = failure
                state.values.update({item.id: item.on_error for item in self.blocks[target]})
        finally:
            state.completed.update(targets)
            if isFull:
                state.fullCompleted = True

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
        state = PostState()
        try:
            self._compute(context, state, tuple(self.blocks), includeUnused=True)
        finally:
            context.update(state.derivedValues)
            ensure_warnings(context).extend(state.warnings)
        return state.values

    def get_evaluation_info(self):
        return self.nOutput, self.optType, self.nConstraints
