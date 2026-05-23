from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_top_level_exports_sim_model():
    from hydropilot import BatchRunResult, SimModel
    from hydropilot.api import BatchRunResult as ApiBatchRunResult
    from hydropilot.api import SimModel as ApiSimModel

    assert SimModel is ApiSimModel
    assert BatchRunResult is ApiBatchRunResult


def test_migrated_layers_export_new_paths():
    from hydropilot.evaluation import Evaluator, FunctionManager
    from hydropilot.params import ParamApplier, ParamSpace, ParamWritePlan
    from hydropilot.series import ObsStore, SeriesExtractor, SeriesPlan, SeriesPlanItem
    from hydropilot.runtime import (
        ExecutionServices,
        Executor,
        Session,
        Workspace,
        create_context,
        ensure_warnings,
    )

    assert Evaluator.__name__ == "Evaluator"
    assert FunctionManager.__name__ == "FunctionManager"
    assert ParamSpace.__name__ == "ParamSpace"
    assert ParamWritePlan.__name__ == "ParamWritePlan"
    assert ParamApplier.__name__ == "ParamApplier"
    assert SeriesPlan.__name__ == "SeriesPlan"
    assert SeriesPlanItem.__name__ == "SeriesPlanItem"
    assert ObsStore.__name__ == "ObsStore"
    assert SeriesExtractor.__name__ == "SeriesExtractor"
    assert ExecutionServices.__name__ == "ExecutionServices"
    assert Executor.__name__ == "Executor"
    assert Session.__name__ == "Session"
    assert Workspace.__name__ == "Workspace"
    assert callable(create_context)
    assert callable(ensure_warnings)


def test_integrations_exports_uqpyl_adapter_when_optional_dep_available():
    pytest.importorskip("UQPyL")

    from hydropilot.integrations import UQPyLAdapter
    from hydropilot.integrations.uqpyl import UQPyLAdapter as DirectUQPyLAdapter

    assert UQPyLAdapter is DirectUQPyLAdapter


def test_uqpyl_adapter_matches_problem_eval_protocol(monkeypatch):
    pytest.importorskip("UQPyL")

    import numpy as np
    from UQPyL.problem import Eval

    from hydropilot.api import BatchRunResult
    from hydropilot.integrations import uqpyl

    class DummySimModel:
        nInput = 2
        nOutput = 1
        nConstraints = 1
        varType = [0, 0]
        varSet = {}
        ub = [1.0, 1.0]
        lb = [0.0, 0.0]
        xLabels = ["x1", "x2"]
        optType = ["min"]

        def __init__(self, cfgPath):
            self.cfgPath = cfgPath
            self.closed = False

        def run(self, X):
            X = np.asarray(X, dtype=float)
            if X.ndim == 1:
                X = X.reshape(1, -1)
            objs = np.sum(X, axis=1, keepdims=True)
            cons = objs - 1.0
            return BatchRunResult(X=X, P=None, objs=objs, cons=cons, diags=None, series=None)

        def close(self):
            self.closed = True

    monkeypatch.setattr(uqpyl, "SimModel", DummySimModel)

    adapter = uqpyl.UQPyLAdapter("dummy.yaml")
    result = adapter.evaluate([[0.25, 0.5]])

    assert isinstance(result, Eval)
    assert np.allclose(result.objs, [[0.75]])
    assert np.allclose(result.cons, [[-0.25]])
    assert np.allclose(adapter.objFunc([[0.25, 0.5]]), [[0.75]])
    assert np.allclose(adapter.conFunc([[0.25, 0.5]]), [[-0.25]])


def test_uqpyl_adapter_works_with_algorithm_run(monkeypatch):
    pytest.importorskip("UQPyL")

    import numpy as np
    from UQPyL.optimization.soea import GA

    from hydropilot.api import BatchRunResult
    from hydropilot.integrations import uqpyl

    class DummySimModel:
        nInput = 2
        nOutput = 1
        nConstraints = 0
        varType = [0, 0]
        varSet = []
        ub = [1.0, 1.0]
        lb = [0.0, 0.0]
        xLabels = ["x1", "x2"]
        optType = ["min"]

        def __init__(self, cfgPath):
            self.cfgPath = cfgPath

        def run(self, X):
            X = np.asarray(X, dtype=float)
            if X.ndim == 1:
                X = X.reshape(1, -1)
            objs = np.sum((X - 0.25) ** 2, axis=1, keepdims=True)
            return BatchRunResult(X=X, P=None, objs=objs, cons=None, diags=None, series=None)

        def close(self):
            return None

    monkeypatch.setattr(uqpyl, "SimModel", DummySimModel)

    problem = uqpyl.UQPyLAdapter("dummy.yaml")
    algorithm = GA(nPop=5, maxFEs=10, verboseFlag=False, logFlag=False, saveFlag=False)
    result = algorithm.run(problem, seed=1)

    assert result is not None
    assert hasattr(result, "bestDecs")
    assert hasattr(result, "bestObjs")
