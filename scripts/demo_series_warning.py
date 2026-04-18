import os
import sys
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from hydro_pilot.sim_model import SimModel

CFG_PATH = os.path.join(os.path.dirname(__file__), "..", "examples", "test_monthly_series_warning.yaml")


def main():
    model = None
    try:
        model = SimModel(CFG_PATH)
        lb = np.array(model.lb)
        ub = np.array(model.ub)
        X = ((lb + ub) / 2).reshape(1, -1)
        result = model.evaluate(X)
        print(result["objs"])
        print(model.backupPath)
    finally:
        if model is not None:
            model.close()


if __name__ == "__main__":
    main()
