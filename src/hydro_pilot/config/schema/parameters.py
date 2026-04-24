from typing import Any, Dict, List, Optional

from pydantic import Field

from .base import ConfigNode


class PhysicalParameterSpec(ConfigNode):
    name: str
    type: str = "float"
    mode: str = "v"
    bounds: List[float] = Field(default_factory=lambda: [0, 1])
    writerType: str = "fixed_width"
    file: Dict[str, Any]
    sets: List[float] = Field(default_factory=list)


class ParametersSpec(ConfigNode):
    design: List[Dict[str, Any]]
    physical: List[PhysicalParameterSpec]
    hardBound: bool = Field(default=True, alias="hard_bound")
    transformer: Optional[str] = None

    @classmethod
    def from_raw(cls, raw: Dict[str, Any], base_path) -> "ParametersSpec":
        if not isinstance(raw, dict):
            raise ValueError("parameters must be a mapping/object")
        payload = {
            "design": raw.get("design", []),
            "physical": raw.get("physical", []),
            "hardBound": raw.get("hardBound", True),
            "transformer": raw.get("transformer"),
        }
        return cls.model_validate(payload)

    def get_env_dep_list(self):
        return ["P"], []
