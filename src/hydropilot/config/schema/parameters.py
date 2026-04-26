from typing import Any, Dict, List, Optional

from pydantic import Field

from .base import ConfigNode

TYPE_MAP = {"float": 0, "int": 1, "discrete": 2}
MODE_MAP = {"r": 0, "v": 1, "a": 2}


class DesignParameterSpec(ConfigNode):
    index: int = -1
    name: str
    type: str = "float"
    bounds: List[float] = Field(default_factory=lambda: [0, 1])
    sets: List[float] = Field(default_factory=list)

    @property
    def typeCode(self) -> int:
        return TYPE_MAP.get(self.type, 0)

    @property
    def lb(self) -> float:
        return float(self.bounds[0])

    @property
    def ub(self) -> float:
        return float(self.bounds[1])


class PhysicalParameterSpec(ConfigNode):
    index: int = -1
    name: str
    type: str = "float"
    mode: str = "v"
    bounds: List[float] = Field(default_factory=lambda: [0, 1])
    writerType: str = "fixed_width"
    file: Dict[str, Any]
    sets: List[float] = Field(default_factory=list)

    @property
    def typeCode(self) -> int:
        return TYPE_MAP.get(self.type, 0)

    @property
    def modeCode(self) -> int:
        return MODE_MAP.get(self.mode, 1)

    @property
    def lb(self) -> float:
        return float(self.bounds[0])

    @property
    def ub(self) -> float:
        return float(self.bounds[1])


class ParametersSpec(ConfigNode):
    design: List[DesignParameterSpec]
    physical: List[PhysicalParameterSpec]
    hardBound: bool = Field(default=True, alias="hard_bound")
    transformer: Optional[str] = None

    @classmethod
    def from_raw(cls, raw: Dict[str, Any], base_path) -> "ParametersSpec":
        if not isinstance(raw, dict):
            raise ValueError("parameters must be a mapping/object")
        payload = {
            "design": [dict(item, index=index) for index, item in enumerate(raw.get("design", []))],
            "physical": [dict(item, index=index) for index, item in enumerate(raw.get("physical", []))],
            "hardBound": raw.get("hardBound", True),
            "transformer": raw.get("transformer"),
        }
        return cls.model_validate(payload)

    def get_env_dep_list(self):
        return ["P"], []
