from abc import ABC, abstractmethod
from pathlib import Path
from typing import List

import numpy as np


class ParamWriter(ABC):
    """Abstract interface for writing parameter values to model input files."""

    @abstractmethod
    def register_param(self, spec, lib_info, hard_bound: bool = True) -> bool:
        """Register a parameter for writing.

        Args:
            spec: Physical parameter spec (name, index, mode).
            lib_info: Library info (type, bounds, file location).
            hard_bound: Whether to enforce bounds clamping.
        """

    @abstractmethod
    def set_values_and_save(
        self,
        output_filepath: str,
        indices: List[int],
        vals: List[float],
    ) -> List[dict]:
        """Apply parameter values and write to the output file.

        Returns:
            List of clamping events (dicts with file, param, raw, clamped, etc.).
        """
