from dataclasses import dataclass
from typing import Any, Dict, List, Union


TYPE_MAP = {"float": 0, "int": 1, "discrete": 2}
MODE_MAP = {"r": 0, "v": 1, "a": 2}

@dataclass
class DesignParamSpec:
    name: str
    index: int
    type: int
    bounds: List[float]
    sets: List[float]

    @staticmethod
    def fromDict(d: dict[str, Any], index: int) -> "DesignParamSpec":
        pName = d.get("name")
        if not pName:
            raise ValueError(f"Design parameter at index {index} missing 'name'")
        pType = TYPE_MAP.get(d.get("type", "float"), 0)
        if pType == 2 and "sets" not in d:
            raise ValueError(f"Discrete variable '{pName}' missing 'sets'")
        if pType in (0, 1) and "bounds" not in d:
            raise ValueError(f"Continuous variable '{pName}' missing 'bounds'")
        bounds = [0, 1] if pType == 2 else d.get("bounds", [0, 1])
        return DesignParamSpec(
            name=pName,
            index=index,
            type=pType,
            bounds=bounds,
            sets=d.get("sets", []),
        )

    @property
    def lb(self) -> float:
        return float(self.bounds[0])

    @property
    def ub(self) -> float:
        return float(self.bounds[1])


@dataclass
class PhysicalParamSpec:
    index: int
    name: str
    mode: int
    type: int
    bounds: List[float]
    writerType: str
    file: Dict[str, Any]

    @staticmethod
    def fromDict(d: Any, index: int) -> "PhysicalParamSpec":
        if not isinstance(d, dict):
            raise ValueError(f"Physical parameter at index {index} must be a mapping")
        name = d.get("name")
        if not name:
            raise ValueError(f"Physical parameter at index {index} missing 'name'")
        writer_type = d.get("writerType")
        if not writer_type:
            raise ValueError(f"Physical parameter '{name}' must declare writerType")
        file_spec = d.get("file")
        if not isinstance(file_spec, dict):
            raise ValueError(f"Physical parameter '{name}' missing writer-specific file spec")
        return PhysicalParamSpec(
            index=index,
            name=name,
            mode=MODE_MAP.get(d.get("mode", "v"), 1),
            type=TYPE_MAP.get(d.get("type", "float"), 0),
            bounds=d.get("bounds", [0, 1]),
            writerType=str(writer_type),
            file=dict(file_spec),
        )

    @property
    def lb(self) -> float:
        return float(self.bounds[0])

    @property
    def ub(self) -> float:
        return float(self.bounds[1])
