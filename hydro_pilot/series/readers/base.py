from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np


class SeriesReader(ABC):
    """Abstract interface for reading series data from model output files."""

    @abstractmethod
    def read(self, dir_path, extract_spec) -> np.ndarray:
        """Read series data from a model output file.

        Args:
            dir_path: Working directory (None for absolute paths).
            extract_spec: Extraction specification (file, rows, column, etc.).

        Returns:
            1-D numpy array of extracted values.
        """
