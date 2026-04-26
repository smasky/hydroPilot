from typing import Any, List

from pydantic import Field

from .base import ConfigNode


class ReporterSpec(ConfigNode):
    flushInterval: int = 50
    holdingPenLimit: int = 20
    series: List[str] = Field(default_factory=list)

    @classmethod
    def from_raw(cls, raw: Any) -> "ReporterSpec":
        if not isinstance(raw, dict):
            raw = {}
        if "flush_interval" in raw and "flushInterval" not in raw:
            raw["flushInterval"] = raw.pop("flush_interval")
        return cls.model_validate(raw)
