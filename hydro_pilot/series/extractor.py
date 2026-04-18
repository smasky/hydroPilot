import numpy as np

from ..config.specs import CallSpec
from ..series.readers import getReader
from ..errors import RunError


class SeriesExtractor:
    def __init__(self, cfg, funcManager):
        self.cfg = cfg
        self.funcManager = funcManager
        self.seriesDict = self._init_series()

    def _append_warning(self, context: dict, code: str, target: str, message: str):
        warnings = context.setdefault("warnings", [])
        warnings.append(RunError(
            stage="series",
            code=code,
            target=target,
            message=message,
            severity="warning",
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

    def _read_extract(self, workPath, extractSpec):
        readerCls = getReader(extractSpec.readerType)
        reader = readerCls()
        return reader.read(workPath, extractSpec)

    def _init_series(self) -> dict:
        """Initialize all series — no cache filtering, all series are extracted."""
        seriesDict = {}

        for s in self.cfg.series:
            obsData = None
            if s.obs:
                obsData = self._read_extract(None, s.obs)

            seriesDict[s.id] = {
                "obs": obsData,
                "simItem": s.sim,
                "obsItem": s.obs,
            }

        return seriesDict

    def _resolve_series_ref(self, ref: str, workPath: str, env: dict):
        if ref in env:
            return env[ref]

        is_obs = ref.endswith(".obs")
        base_id = ref.replace(".sim", "").replace(".obs", "")

        if base_id not in self.cfg.series_index:
            raise RunError(
                stage="series",
                code="DEPENDENCY_MISSING",
                target=ref,
                message=f"Unknown series dependency '{ref}'"
            )

        if is_obs:
            if base_id not in self.seriesDict:
                raise RunError(
                    stage="series",
                    code="OBS_NOT_INITIALIZED",
                    target=ref,
                    message=f"Obs dependency '{ref}' is not initialized in seriesDict"
                )

            obs_data = self.seriesDict[base_id]["obs"]
            if obs_data is None:
                raise RunError(
                    stage="series",
                    code="MISSING_OBS_FILE",
                    target=ref,
                    message=f"Dependency '{ref}' requested, but '{base_id}' has no obs file"
                )

            env[ref] = obs_data
        else:
            sim_item = self.cfg.series_index[base_id].sim
            try:
                env[ref] = self._read_extract(workPath, sim_item)
            except Exception as e:
                raise RunError(
                    stage="series",
                    code="FILE_READ_ERROR",
                    target=ref,
                    message=f"Error reading simulation file for '{base_id}': {e}"
                )

        return env[ref]

    def extract_all(self, workPath: str, context: dict) -> dict:
        env = context.copy()

        for sid, item in self.seriesDict.items():
            simItem = item["simItem"]

            if isinstance(simItem, CallSpec):
                func_name = simItem.func
                raw_args = simItem.args
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
                if item["obs"] is not None:
                    env[f"{sid}.obs"] = item["obs"]

            else:
                # ExtractSpec — read from file
                sim_key = f"{sid}.sim"
                obs_key = f"{sid}.obs"
                if sim_key not in env:
                    try:
                        val = self._read_extract(workPath, simItem)
                        env[sim_key] = val
                    except Exception as e:
                        raise RunError(
                            stage="series",
                            code="FILE_READ_ERROR",
                            target=sid,
                            message=f"Error reading simulation file for '{sid}': {e}"
                        )
                if obs_key not in env:
                    if item["obs"] is not None:
                        env[obs_key] = item["obs"]

        return env
