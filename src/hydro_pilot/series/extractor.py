import numpy as np

from ..config.specs import CallSpec
from ..io.readers.dispatcher import read_extract
from ..runtime.context import append_warning
from ..runtime.errors import RunError


class SeriesExtractor:
    def __init__(self, cfg, func_manager, series_plan, obs_store):
        self.cfg = cfg
        self.funcManager = func_manager
        self.seriesPlan = series_plan
        self.obsStore = obs_store

    def _append_warning(self, context: dict, code: str, target: str, message: str):
        append_warning(context, RunError(
            stage="series",
            code=code,
            target=target,
            message=message,
        ))

    def _normalize_called_series(self, value, sid: str, context: dict):
        arr = np.asarray(value)
        if arr.ndim == 0:
            self._append_warning(
                context,
                code="SERIES_CALL_SCALAR",
                target=sid,
                message=f"Derived series '{sid}' returned a scalar; expected a 1D series",
            )
            return arr.reshape(1)
        if arr.ndim > 1:
            self._append_warning(
                context,
                code="SERIES_CALL_NON_1D",
                target=sid,
                message=f"Derived series '{sid}' returned shape {arr.shape}; flattening to 1D",
            )
        flat = arr.ravel()
        if flat.size == 0:
            self._append_warning(
                context,
                code="SERIES_CALL_EMPTY",
                target=sid,
                message=f"Derived series '{sid}' returned an empty series",
            )
        return flat

    def _read_extract(self, work_path, extract_spec):
        return read_extract(work_path, extract_spec)

    def extract(self, work_path: str, context: dict) -> dict:
        env = context.copy()

        for sid, item in self.seriesPlan.items.items():
            sim_item = item["simItem"]
            obs_item = item["obsItem"]

            if isinstance(sim_item, CallSpec):
                func_name = sim_item.func
                raw_args = sim_item.args
                func_args = []
                for arg_ref in raw_args:
                    if arg_ref not in env:
                        raise RunError(
                            stage="series",
                            code="DEPENDENCY_ORDER_ERROR",
                            target=sid,
                            message=f"Derived series '{sid}' requires '{arg_ref}' to be defined earlier in series order",
                        )
                    func_args.append(env[arg_ref])
                try:
                    func_result = self.funcManager.call(func_name, *func_args)
                    env[f"{sid}.sim"] = self._normalize_called_series(func_result, sid, env)
                except Exception as e:
                    raise RunError(
                        stage="series",
                        code="FUNC_CALL_FAILED",
                        target=sid,
                        message=f"Error calling function '{func_name}': {e}"
                    )
                if obs_item is not None:
                    env[f"{sid}.obs"] = self.obsStore.get(sid)
            else:
                sim_key = f"{sid}.sim"
                obs_key = f"{sid}.obs"
                if sim_key not in env:
                    try:
                        env[sim_key] = self._read_extract(work_path, sim_item)
                    except Exception as e:
                        raise RunError(
                            stage="series",
                            code="FILE_READ_ERROR",
                            target=sid,
                            message=f"Error reading simulation file for '{sid}': {e}"
                        )
                if obs_key not in env and obs_item is not None:
                    env[obs_key] = self.obsStore.get(sid)

        return env
