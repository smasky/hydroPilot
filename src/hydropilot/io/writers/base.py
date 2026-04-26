from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List


class ParamWriter(ABC):
    """Abstract interface for writing parameter values to model input files."""

    @classmethod
    @abstractmethod
    def validateSpec(cls, raw_spec: Dict[str, Any]) -> None:
        """Validate writer-specific raw parameter payload."""

    @classmethod
    @abstractmethod
    def buildSpec(cls, raw_spec: Dict[str, Any]):
        """Build writer-specific runtime spec from raw config node."""

    @abstractmethod
    def register_param(self, spec, lib_info, hard_bound: bool = True) -> bool:
        """Register a parameter for writing."""

    @abstractmethod
    def set_values_and_save(
        self,
        output_filepath: str,
        indices: List[int],
        vals: List[float],
    ) -> List[dict]:
        """Apply parameter values and write to the output file."""
