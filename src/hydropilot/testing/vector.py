import numpy as np


def build_default_test_vector(cfg) -> np.ndarray:
    values = []
    for item in cfg.parameters.design:
        if item.type == "discrete":
            if not item.sets:
                raise ValueError(f"Design parameter '{item.name}' is discrete but has no sets")
            values.append(float(item.sets[0]))
            continue
        midpoint = (float(item.lb) + float(item.ub)) / 2.0
        if item.type == "int":
            midpoint = float(round(midpoint))
        values.append(midpoint)
    return np.asarray(values, dtype=float)
