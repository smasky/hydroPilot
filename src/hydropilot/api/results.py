from dataclasses import dataclass

import numpy as np


@dataclass(slots=True)
class BatchRunResult:
    X: np.ndarray
    P: np.ndarray | None
    objs: np.ndarray
    cons: np.ndarray | None
    diags: np.ndarray | None
    series: dict[str, np.ndarray] | None
