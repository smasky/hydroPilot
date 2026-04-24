"""End-to-end monthly series test for SWAT.

Tests:
- Monthly period parsing consistency: [2019-02, 2021-11] vs [2019-02-03, 2021-11-01]
- External series derivation on flow.sim
"""
import os
import sys
import numpy as np

ROOT = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, ROOT)

from hydro_pilot.config.loader import load_config


CFG_PATH = os.path.join(os.path.dirname(__file__), "..", "examples", "test_monthly_series.yaml")


def test_config_load():
    print("=" * 60)
    print("Stage 1: Config loading")
    print("=" * 60)

    cfg = load_config(CFG_PATH)

    print(f"  version: {cfg.version}")
    print(f"  projectPath: {cfg.basic.projectPath}")
    print(f"  command: {cfg.basic.command}")
    print(f"  series: {[s.id for s in cfg.series]}")
    print(f"  functions: {list(cfg.functions.keys())}")
    print(f"  derived: {[d.id for d in cfg.derived]}")
    print(f"  diagnostics: {cfg.diagnostics.use}")

    assert len(cfg.series) == 2, "Expected 2 series"
    assert "flow_times_two" in cfg.functions, "Expected external function"
    assert "series_equal" in cfg.functions, "Expected compare function"

    print("\n  PASSED: Config loading verified!")
    return cfg


def test_sim_model():
    print("\n" + "=" * 60)
    print("Stage 2: SimModel init + evaluate")
    print("=" * 60)

    from hydro_pilot import SimModel

    model = None
    try:
        model = SimModel(CFG_PATH)
        print(f"  nInput: {model.nInput}")
        print(f"  xLabels: {model.xLabels}")
        print(f"  nOutput: {model.nOutput}")
        print(f"  lb: {model.lb}")
        print(f"  ub: {model.ub}")

        lb = np.array(model.lb)
        ub = np.array(model.ub)
        X = ((lb + ub) / 2).reshape(1, -1)
        print(f"\n  Test X (midpoint): {X[0]}")

        print("\n  Running evaluation (SWAT monthly series)...")
        result = model.evaluate(X)
        objs = result["objs"]
        print(f"  Objectives: {objs}")
        assert np.all(np.isfinite(objs)), f"Objectives contain non-finite values: {objs}"

        if result["cons"] is not None:
            print(f"  Constraints: {result['cons']}")
        else:
            print("  Constraints: None")

        raw = result.get("raw", {})
        records = raw.get("records") if isinstance(raw, dict) else None
        if records:
            record = records[0]
            diagnostics = record.get("diagnostics", {})
            derived = record.get("derived", {})

            period_equal = derived.get("period_series_equal")
            doubled_flow = derived.get("flow_month_times_two")
            flow_series = record.get("series", {}).get("flow_month", {}).get("sim")

            print(f"  period_series_equal = {period_equal}")
            if period_equal is not None:
                assert float(period_equal) == 1.0, "Expected identical monthly series for both period formats"

            if flow_series is not None and doubled_flow is not None:
                flow_arr = np.asarray(flow_series).ravel()
                doubled_arr = np.asarray(doubled_flow).ravel()
                assert flow_arr.shape == doubled_arr.shape, "Derived series shape mismatch"
                assert np.allclose(doubled_arr, flow_arr * 2.0), "Derived series should be flow * 2"
                print(f"  Verified derived series length: {len(doubled_arr)}")

            print(f"  diagnostics keys: {list(diagnostics.keys())}")

        print("\n  PASSED: Monthly series test completed!")
    except Exception as e:
        print(f"\n  FAILED: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        if model is not None:
            model.close()


if __name__ == "__main__":
    test_config_load()
    test_sim_model()
