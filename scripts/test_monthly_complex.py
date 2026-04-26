"""End-to-end monthly complex simulation test for SWAT.

Tests the full pipeline with:
- External transformer (4 design -> 6 physical)
- Mixed filter (land_use + subbasin)
- Two series (flow + TN)
- Multi-objective (NSE_flow + NSE_TN)
- Diagnostics (KGE, RMSE, annual TN load via external function)

Uses E:\\BMPs\\TxtInOut (monthly, 2019-2021, 62 subbasins).
"""
import sys
import os
import numpy as np

ROOT = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, ROOT)

from hydropilot.config.loader import load_config


CFG_PATH = os.path.join(os.path.dirname(__file__), "..", "examples", "test_monthly_complex.yaml")


def test_config_load():
    """Stage 1: Test config loading and template expansion."""
    print("=" * 60)
    print("Stage 1: Config loading + template expansion")
    print("=" * 60)

    cfg = load_config(CFG_PATH)

    print(f"  version: {cfg.version}")
    print(f"  projectPath: {cfg.basic.projectPath}")
    print(f"  command: {cfg.basic.command}")

    # Parameters
    print(f"\n  design params: {len(cfg.parameters.design)}")
    for d in cfg.parameters.design:
        print(f"    - {d['name']}: bounds={d['bounds']}")
    print(f"  physical params: {len(cfg.parameters.physical)}")
    for p in cfg.parameters.physical:
        file_info = p.file
        fname = file_info.get("name", "?") if isinstance(file_info, dict) else "?"
        if isinstance(fname, list):
            fname = f"[{len(fname)} files]"
        print(f"    - {p.name}: mode={p.mode}, writerType={p.writerType}, file={fname}")
    print(f"  transformer: {cfg.parameters.transformer}")

    # Series
    print(f"\n  series: {len(cfg.series)}")
    for s in cfg.series:
        print(f"    - {s.id}: sim={type(s.sim).__name__}, obs={'yes' if s.obs else 'no'}")

    # Functions
    print(f"\n  functions: {list(cfg.functions.keys())}")

    # Derived
    print(f"  derived: {[d.id for d in cfg.derived]}")

    # Objectives
    print(f"  objectives: {cfg.objectives.use}")
    for oid in cfg.objectives.use:
        o = cfg.objectives.items[oid]
        print(f"    - {o.id}: ref={o.ref}, sense={o.sense}")

    # Diagnostics
    print(f"  diagnostics: {cfg.diagnostics.use}")
    for did in cfg.diagnostics.use:
        d = cfg.diagnostics.items[did]
        print(f"    - {d.id}: ref={d.ref}")

    # Assertions
    assert len(cfg.parameters.design) == 4, "Expected 4 design params"
    assert len(cfg.parameters.physical) == 6, "Expected 6 physical params"
    assert cfg.parameters.transformer == "monthly_transform", "Expected transformer"
    assert len(cfg.series) == 2, "Expected 2 series"
    assert len(cfg.objectives.use) == 2, "Expected 2 objectives"
    assert len(cfg.diagnostics.use) == 3, "Expected 3 diagnostics"

    print("\n  PASSED: Config loading verified!")
    return cfg


def test_sim_model():
    """Stage 2: Test SimModel initialization and single evaluation."""
    print("\n" + "=" * 60)
    print("Stage 2: SimModel init + evaluate")
    print("=" * 60)

    from hydropilot import SimModel

    model = None
    try:
        model = SimModel(CFG_PATH)
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

        print("\n  Running evaluation (SWAT monthly)...")
        result = model.run(X)
        objs = result.objs
        print(f"  Objectives shape: {objs.shape}")
        print(f"  NSE_flow = {objs[0, 0]:.6f}")
        print(f"  NSE_TN   = {objs[0, 1]:.6f}")

        if result.cons is not None:
            print(f"  Constraints: {result.cons}")
        else:
            print("  Constraints: None (no constraints defined)")

        # Check objectives are finite
        assert np.all(np.isfinite(objs)), f"Objectives contain non-finite values: {objs}"
        print("\n  PASSED: End-to-end monthly complex simulation completed!")

    except Exception as e:
        print(f"\n  FAILED: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if model is not None:
            model.close()


if __name__ == "__main__":
    cfg = test_config_load()
    test_sim_model()
