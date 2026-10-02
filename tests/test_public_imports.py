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


def test_uqpyl_adapter_builds_model_problem_views(monkeypatch):
    pytest.importorskip("UQPyL")

    import numpy as np
    from types import SimpleNamespace
    from UQPyL.problem import Eval, ModelProblem

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
            self.cfg = SimpleNamespace(
                basic=SimpleNamespace(name="DummyModel"),
                series=[
                    SimpleNamespace(id="flow", obs=object()),
                    SimpleNamespace(id="sed", obs=None),
                    SimpleNamespace(id="tn", obs=object()),
                ],
            )
            obs_store = SimpleNamespace(
                get=lambda sid: {
                    "flow": np.array([10.0, np.nan, 30.0]),
                    "tn": np.array([1.0, 2.0]),
                }.get(sid)
            )
            self.session = SimpleNamespace(
                executor=SimpleNamespace(
                    services=SimpleNamespace(obsStore=obs_store)
                )
            )

        def _runSimulation(self, X):
            X = np.asarray(X, dtype=float)
            if X.ndim == 1:
                X = X.reshape(1, -1)
            objs = np.sum(X, axis=1, keepdims=True)
            cons = objs - 1.0
            flow = np.array([[100.0, np.nan, 300.0], [400.0, 500.0, np.nan]])[: X.shape[0]]
            sed = np.array([[9.0, 8.0, 7.0], [6.0, 5.0, 4.0]])[: X.shape[0]]
            tn = np.array([[1.0, 2.0], [3.0, np.nan]])[: X.shape[0]]
            return BatchRunResult(
                X=X,
                P=None,
                objs=objs,
                cons=cons,
                diags=None,
                series={"flow": flow, "sed": sed, "tn": tn},
                obs={"flow": np.array([10.0, np.nan, 30.0]), "tn": np.array([1.0, 2.0])},
            )

        def _post(self, simulation, target=None):
            from hydropilot.runtime.context import PostResult
            return PostResult(
                simulation.objs if target in (None, "objs") else None,
                simulation.cons if target in (None, "cons") else None,
                simulation.diags if target in (None, "diags") else None,
            )

        def close(self):
            return None

    monkeypatch.setattr(uqpyl, "SimModel", DummySimModel)

    adapter = uqpyl.UQPyLAdapter("dummy.yaml")
    assert adapter.seriesLabels == ["flow", "tn"]
    assert np.allclose(adapter.obs[:, 0], np.array([10.0, np.nan, 30.0]), equal_nan=True)
    assert np.allclose(adapter.obs[:, 1], np.array([1.0, 2.0, np.nan]), equal_nan=True)
    assert np.array_equal(
        adapter.mask,
        np.array([[False, False], [True, False], [False, True]]),
    )

    with pytest.warns(RuntimeWarning) as recordedWarnings:
        result = adapter.evaluate([[0.25, 0.5], [0.1, 0.2]])
    assert len(recordedWarnings) == 2

    assert isinstance(adapter, ModelProblem)
    assert isinstance(result, Eval)
    assert np.array_equal(
        adapter.mask,
        np.array([[False, False], [True, False], [False, True]]),
    )
    assert result.sims.shape == (2, 3, 2)
    assert np.allclose(result.sims[0, :, 0], np.array([100.0, np.nan, 300.0]), equal_nan=True)
    assert np.allclose(result.sims[1, :, 1], np.array([3.0, np.nan, np.nan]), equal_nan=True)
    assert np.allclose(adapter.obs[:, 0], np.array([10.0, np.nan, 30.0]), equal_nan=True)
    assert np.allclose(adapter.obs[:, 1], np.array([1.0, 2.0, np.nan]), equal_nan=True)
    assert np.allclose(result.objs, np.array([[0.75], [0.3]]))
    assert np.allclose(result.cons, np.array([[-0.25], [-0.7]]))


def test_uqpyl_adapter_works_with_algorithm_run(monkeypatch):
    pytest.importorskip("UQPyL")

    import numpy as np
    from types import SimpleNamespace
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
            self.cfg = SimpleNamespace(
                basic=SimpleNamespace(name="DummyModel"),
                series=[SimpleNamespace(id="flow", obs=object())],
            )
            obs_store = SimpleNamespace(
                get=lambda sid: np.array([0.25, 0.25]) if sid == "flow" else None
            )
            self.session = SimpleNamespace(
                executor=SimpleNamespace(
                    services=SimpleNamespace(obsStore=obs_store)
                )
            )

        def _runSimulation(self, X):
            X = np.asarray(X, dtype=float)
            if X.ndim == 1:
                X = X.reshape(1, -1)
            objs = np.sum((X - 0.25) ** 2, axis=1, keepdims=True)
            sim = np.asarray(X, dtype=float)
            return BatchRunResult(
                X=X,
                P=None,
                objs=objs,
                cons=None,
                diags=None,
                series={"flow": sim},
                obs={"flow": np.array([0.25, 0.25])},
            )

        def _post(self, simulation, target=None):
            from hydropilot.runtime.context import PostResult
            return PostResult(
                simulation.objs if target in (None, "objs") else None,
                simulation.cons if target in (None, "cons") else None,
                simulation.diags if target in (None, "diags") else None,
            )

        def close(self):
            return None

    monkeypatch.setattr(uqpyl, "SimModel", DummySimModel)

    problem = uqpyl.UQPyLAdapter("dummy.yaml")
    algorithm = GA(nPop=5, maxFEs=10, verboseFlag=False, logFlag=False, saveFlag=False)
    result = algorithm.run(problem, seed=1)

    assert result is not None
    assert hasattr(result, "bestDecs")
    assert hasattr(result, "bestObjs")

def test_uqpyl_adapter_works_with_glue(monkeypatch):
    pytest.importorskip("UQPyL")

    import numpy as np
    from types import SimpleNamespace
    from UQPyL.calibration import GLUE

    from hydropilot.api import BatchRunResult
    from hydropilot.integrations import uqpyl

    class DummySimModel:
        nInput = 2
        nOutput = 1
        nConstraints = 0
        varType = [0, 0]
        varSet = {}
        ub = [1.0, 1.0]
        lb = [0.0, 0.0]
        xLabels = ["x1", "x2"]
        optType = ["min"]

        def __init__(self, cfgPath):
            self.cfgPath = cfgPath
            self.cfg = SimpleNamespace(
                basic=SimpleNamespace(name="DummyModel"),
                series=[SimpleNamespace(id="flow", obs=object())],
            )
            obs_store = SimpleNamespace(
                get=lambda sid: np.array([10.0, np.nan, 30.0]) if sid == "flow" else None
            )
            self.session = SimpleNamespace(
                executor=SimpleNamespace(
                    services=SimpleNamespace(obsStore=obs_store)
                )
            )

        def _runSimulation(self, X):
            X = np.asarray(X, dtype=float)
            if X.ndim == 1:
                X = X.reshape(1, -1)
            objs = np.sum(X, axis=1, keepdims=True)
            sim_rows = []
            for row in X:
                if np.allclose(row, [0.1, 0.2]):
                    sim_rows.append([10.0, np.nan, 30.0])
                else:
                    sim_rows.append([15.0, np.nan, 25.0])
            return BatchRunResult(
                X=X,
                P=None,
                objs=objs,
                cons=None,
                diags=None,
                series={"flow": np.asarray(sim_rows, dtype=float)},
                obs={"flow": np.array([10.0, np.nan, 30.0])},
            )

        def _post(self, simulation, target=None):
            from hydropilot.runtime.context import PostResult
            return PostResult(
                simulation.objs if target in (None, "objs") else None,
                simulation.cons if target in (None, "cons") else None,
                simulation.diags if target in (None, "diags") else None,
            )

        def close(self):
            return None

    monkeypatch.setattr(uqpyl, "SimModel", DummySimModel)

    problem = uqpyl.UQPyLAdapter("dummy.yaml")
    X = np.array([[0.8, 0.9], [0.1, 0.2]])
    result = GLUE(metric="rmse", verboseFlag=False, logFlag=False, saveFlag=False).run(
        problem,
        X,
        threshold=0.1,
    )

    assert result is not None
    assert result.bestDecs.shape == (1, 2)
    assert np.allclose(result.bestDecs[0], np.array([0.1, 0.2]))


def test_uqpyl_adapter_works_with_sufi2(monkeypatch):
    pytest.importorskip("UQPyL")

    import numpy as np
    from types import SimpleNamespace
    from UQPyL.calibration import SUFI2

    from hydropilot.api import BatchRunResult
    from hydropilot.integrations import uqpyl

    class DummySimModel:
        nInput = 2
        nOutput = 1
        nConstraints = 0
        varType = [0, 0]
        varSet = {}
        ub = [3.0, 3.0]
        lb = [0.0, 0.0]
        xLabels = ["x1", "x2"]
        optType = ["min"]

        def __init__(self, cfgPath):
            self.cfgPath = cfgPath
            self.cfg = SimpleNamespace(
                basic=SimpleNamespace(name="DummyModel"),
                series=[SimpleNamespace(id="flow", obs=object())],
            )
            obs_store = SimpleNamespace(
                get=lambda sid: np.array([1.0, 2.0]) if sid == "flow" else None
            )
            self.session = SimpleNamespace(
                executor=SimpleNamespace(
                    services=SimpleNamespace(obsStore=obs_store)
                )
            )

        def _runSimulation(self, X):
            X = np.asarray(X, dtype=float)
            if X.ndim == 1:
                X = X.reshape(1, -1)
            objs = np.sum((X - np.array([[1.0, 2.0]])) ** 2, axis=1, keepdims=True)
            sim = np.zeros((X.shape[0], 2), dtype=float)
            sim[:, 0] = X[:, 0]
            sim[:, 1] = X[:, 1]
            return BatchRunResult(
                X=X,
                P=None,
                objs=objs,
                cons=None,
                diags=None,
                series={"flow": sim},
                obs={"flow": np.array([1.0, 2.0])},
            )

        def _post(self, simulation, target=None):
            from hydropilot.runtime.context import PostResult
            return PostResult(
                simulation.objs if target in (None, "objs") else None,
                simulation.cons if target in (None, "cons") else None,
                simulation.diags if target in (None, "diags") else None,
            )

        def close(self):
            return None

    monkeypatch.setattr(uqpyl, "SimModel", DummySimModel)

    problem = uqpyl.UQPyLAdapter("dummy.yaml")
    X = np.array([
        [1.0, 2.0],
        [1.2, 2.2],
        [0.0, 0.0],
    ])
    result = SUFI2(verboseFlag=False, logFlag=False, saveFlag=False).run(
        problem,
        X,
        eliteSize=2,
    )

    assert result is not None
    assert np.allclose(result.bestDecs, [[1.0, 2.0]])
    assert np.allclose(result.eliteDecs, [[1.0, 2.0], [1.2, 2.2]])
    assert np.allclose(result.diagnostics["updatedLb"], [1.0, 2.0])
    assert np.allclose(result.diagnostics["updatedUb"], [1.2, 2.2])
