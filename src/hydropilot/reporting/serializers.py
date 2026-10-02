import json

import numpy as np


def encodeArray(value):
    array = np.asarray(value)
    if array.dtype.hasobject:
        raise TypeError("Archived arrays must not contain Python objects.")
    return array.dtype.str, json.dumps(array.shape), array.tobytes(order="C")


def decodeArray(data, dtype, shape):
    return np.frombuffer(data, dtype=np.dtype(dtype)).reshape(json.loads(shape)).copy()
