from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from pydantic import Field

from .base import ConfigNode
from ...io.readers import getReader


class ReaderSpec(ConfigNode):
    readerType: str
    raw: Dict[str, Any]
    spec: Any

    @classmethod
    def from_raw(cls, raw: Dict[str, Any], base_path: Path, field_name: str, check_file: bool = True) -> "ReaderSpec":
        if not isinstance(raw, dict):
            raise ValueError(f"{field_name} must be a mapping/object, got: {type(raw)}")
        reader_type = raw.get("readerType")
        if not reader_type:
            raise ValueError(f"{field_name} must declare exactly one of 'call' or 'readerType'")
        reader_cls = getReader(str(reader_type))
        built_spec = reader_cls.buildSpec(raw, base_path=base_path, check_file=check_file)
        return cls.model_validate({
            "readerType": str(reader_type),
            "raw": dict(raw),
            "spec": built_spec,
        })

    def get_env_dep_list(self) -> Tuple[List[str], List[str]]:
        return [], []


class CallSpec(ConfigNode):
    func: str
    args: List[str] = Field(default_factory=list)

    def get_env_dep_list(self) -> Tuple[List[str], List[str]]:
        deps = [v for v in self.args if isinstance(v, str)]
        return [], deps


class SeriesSpec(ConfigNode):
    id: str
    name: str
    sim: Union[ReaderSpec, CallSpec]
    obs: Optional[ReaderSpec] = None
    size: int = -1

    @classmethod
    def from_raw(cls, raw: Dict[str, Any], base_path: Path) -> "SeriesSpec":
        if not isinstance(raw, dict):
            raise ValueError("SeriesSpec must be a mapping/object")
        sid = raw.get("id")
        if not sid:
            raise ValueError(f"SeriesSpec missing id: {raw}")

        sim_raw = raw.get("sim")
        if not isinstance(sim_raw, dict):
            raise ValueError(f"Series {sid}: 'sim' block must be a dictionary")

        if "call" in sim_raw and "readerType" in sim_raw:
            raise ValueError(f"Series {sid}: sim must declare exactly one of 'call' or 'readerType'")
        if "call" in sim_raw:
            call_raw = sim_raw["call"]
            if not isinstance(call_raw, dict):
                raise ValueError(f"Series {sid}: sim.call must be a dictionary")
            sim = CallSpec.model_validate(call_raw)
        else:
            sim = ReaderSpec.from_raw(sim_raw, base_path, f"series[{sid}].sim", check_file=False)

        obs_raw = raw.get("obs")
        if obs_raw is None:
            obs = None
        else:
            if not isinstance(obs_raw, dict):
                raise ValueError(f"Series {sid}: 'obs' block must be a dictionary")
            if "call" in obs_raw and "readerType" in obs_raw:
                raise ValueError(f"Series {sid}: obs must declare exactly one of 'call' or 'readerType'")
            if "call" in obs_raw:
                raise ValueError(f"Series {sid}: obs does not support call nodes")
            obs = ReaderSpec.from_raw(obs_raw, base_path, f"series[{sid}].obs", check_file=True)

        payload = {
            "id": str(sid),
            "name": str(raw.get("desc", sid)),
            "sim": sim,
            "obs": obs,
            "size": int(raw.get("size", -1)),
        }
        return cls.model_validate(payload)

    def get_env_dep_list(self) -> Tuple[List[str], List[str]]:
        env: List[str] = [f"{self.id}.sim"]
        dep: List[str] = []
        if self.obs:
            env.append(f"{self.id}.obs")
        sim_env, sim_dep = self.sim.get_env_dep_list()
        env.extend(sim_env)
        dep.extend(sim_dep)
        return env, dep
