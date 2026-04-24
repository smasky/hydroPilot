from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict

import numpy as np


class SeriesReader(ABC):
    """Abstract interface for reading series data from model output files."""

    @classmethod
    @abstractmethod
    def validateSpec(cls, raw_spec: Dict[str, Any], *, base_path: Path, check_file: bool) -> None:
        """Validate reader-specific raw extract spec payload."""

    @classmethod
    @abstractmethod
    def buildSpec(cls, raw_spec: Dict[str, Any], *, base_path: Path, check_file: bool):
        """Build reader-specific runtime spec from raw config node."""

    @abstractmethod
    def read(self, dir_path, spec) -> np.ndarray:
        """Read series data from a model output file."""
