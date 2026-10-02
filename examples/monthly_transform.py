"""External transformer: 4 design params -> 6 physical params.

Mapping:
  X[0] (CN2_factor)   -> P[0], P[1] (relative CN2 changes: factor - 1)
  X[1] (ESCO_val)     -> P[2] (ESCO sub 1-30), P[3] (ESCO sub 31-62)
  X[2] (GW_DELAY_val) -> P[4] (GW_DELAY global)
  X[3] (SURLAG_val)   -> P[5] (SURLAG global)
"""
import numpy as np


def monthly_transform(X):
    X = np.asarray(X).ravel()
    return np.array([
        X[0] - 1.0,  # CN2 relative change for AGRL
        X[0] - 1.0,  # CN2 relative change for URHD (same factor)
        X[1],  # ESCO for subbasin 1-30
        X[1],  # ESCO for subbasin 31-62 (same value)
        X[2],  # GW_DELAY global
        X[3],  # SURLAG global
    ])
