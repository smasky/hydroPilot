import numpy as np


def flow_times_two(flow_month_sim):
    return np.asarray(flow_month_sim).ravel() * 2.0


def series_equal(flow_month_sim, flow_date_sim):
    left_arr = np.asarray(flow_month_sim).ravel()
    right_arr = np.asarray(flow_date_sim).ravel()
    if left_arr.shape != right_arr.shape:
        return 0.0
    return float(np.allclose(left_arr, right_arr, equal_nan=True))
