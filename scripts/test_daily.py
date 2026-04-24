"""End-to-end daily simulation test for SWAT.

Tests the full pipeline: config load -> param write -> SWAT run -> series extract -> evaluate.
Uses E:\DJBasin\TxtInOutFSB with 3 design parameters (CN2, ALPHA_BF, GW_DELAY).
"""
import sys
import os
import numpy as np

ROOT = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, ROOT)

from hydro_pilot.config.loader import load_config


def test_config_load():
    """Step 1: Test config loading and template expansion."""
    print("=" * 60)
    print("Step 1: Config loading")
    print("=" * 60)

    cfg_path = os.path.join(os.path.dirname(__file__), "..", "examples", "test_daily.yaml")
    cfg = load_config(cfg_path)

    print(f"  version: {cfg.version}")
    print(f"  projectPath: {cfg.basic.projectPath}")
    print(f"  command: {cfg.basic.command}")
    print(f"  design params: {len(cfg.parameters.design)}")
    for d in cfg.parameters.design:
        print(f"    - {d['name']}: bounds={d['bounds']}")
    print(f"  physical params: {len(cfg.parameters.physical)}")
    print(f"  series: {len(cfg.series)}")
    for s in cfg.series:
        print(f"    - {s.id}: sim={type(s.sim).__name__}, obs={'yes' if s.obs else 'no'}")
    print(f"  functions: {list(cfg.functions.keys())}")
    print(f"  derived: {[d.id for d in cfg.derived]}")
    print(f"  objectives: {cfg.objectives.use}")
    print()
    return cfg


def test_sim_model():
    """Step 2: Test SimModel initialization and single evaluation."""
    print("=" * 60)
    print("Step 2: SimModel init + evaluate")
    print("=" * 60)

    from hydro_pilot import SimModel

    cfg_path = os.path.join(os.path.dirname(__file__), "..", "examples", "test_daily.yaml")
    model = None
    try:
        model = SimModel(cfg_path)
        print(f"  nInput: {model.nInput}")
        print(f"  xLabels: {model.xLabels}")
        print(f"  nOutput: {model.nOutput}")
        print(f"  optType: {model.optType}")
        print(f"  lb: {model.lb}")
        print(f"  ub: {model.ub}")

        # Use midpoint of bounds as test X
        lb = np.array(model.lb)
        ub = np.array(model.ub)
        X = ((lb + ub) / 2).reshape(1, -1)
        print(f"\n  Test X (midpoint): {X[0]}")

        print("\n  Running evaluation...")
        result = model.evaluate(X)
        objs = result["objs"]
        print(f"  Objectives: {objs}")
        print(f"  NSE = {objs[0, 0]:.6f}")

        if result["cons"] is not None:
            print(f"  Constraints: {result['cons']}")

        print("\n  SUCCESS: End-to-end daily simulation completed!")
    except Exception as e:
        print(f"\n  FAILED: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if model is not None:
            model.close()


if __name__ == "__main__":
    cfg = test_config_load()
    print()
    test_sim_model()
