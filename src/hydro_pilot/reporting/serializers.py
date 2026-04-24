import sqlite3

import numpy as np


def to_1d_float_list(value):
    if value is None:
        return []
    arr = np.asarray(value, dtype=float).ravel()
    return arr.tolist()


def series_blob(value):
    simData = np.asarray(value, dtype=np.float32).ravel()
    return simData, sqlite3.Binary(simData.tobytes())
