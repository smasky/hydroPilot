"""External evaluation function: calculate annual average TN load.

Takes monthly TN series (kg) and returns annual average TN load (kg/yr).
"""
import numpy as np


def calc_annual_tn_load(tn_sim):
    tn = np.asarray(tn_sim).ravel()
    n_months = len(tn)
    n_years = n_months / 12.0
    total_load = np.sum(tn)
    return float(total_load / n_years)
