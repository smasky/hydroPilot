from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
from threading import Event
from types import SimpleNamespace

import numpy as np
import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

pytest.importorskip("UQPyL")

from UQPyL.problem import ModelProblem, SimContext, SimulatorBase

from hydropilot.api import BatchRunResult
from hydropilot.integrations import uqpyl


@pytest.fixture
def makeAdapter(monkeypatch):
    adapters = []

    def build(withObs=True, constraintCount=1):
        class DummySimModel:
            nInput = 1
            nOutput = 1
            nConstraints = constraintCount
            varType = [0]
            varSet = {}
            ub = [1.0]
            lb = [0.0]
            xLabels = ["parameter"]
            optType = ["min"]

            def __init__(self, cfgPath):
                self.runCalls = []
                self.failNext = False
                self.cfg = SimpleNamespace(
                    basic=SimpleNamespace(name="ModelProblemProbe"),
                    series=[SimpleNamespace(id="flow", obs=object() if withObs else None)],
                    objectives=SimpleNamespace(items=[SimpleNamespace(id="score")]),
                    constraints=SimpleNamespace(items=[SimpleNamespace(id="balance")] if constraintCount else []),
                )
                self.session = SimpleNamespace(executor=SimpleNamespace(
                    services=SimpleNamespace(obsStore=SimpleNamespace(
                        get=lambda sid: np.array([0.0, 1.0]) if withObs else None,
                    ))
                ))

            def _runSimulation(self, X):
                X = np.atleast_2d(np.asarray(X, dtype=float))
                self.runCalls.append(X.copy())
                runIndex = len(self.runCalls)
                if self.failNext:
                    self.failNext = False
                    raise RuntimeError("simulation failed")
                return BatchRunResult(
                    X=X, P=X.copy(), objs=X + runIndex / 10,
                    cons=X - 0.5 if constraintCount else None,
                    diags=np.full(X.shape, runIndex, dtype=float),
                    series={"flow": np.hstack([X, X + runIndex])},
                    obs={"flow": np.array([0.0, 1.0])} if withObs else None,
                )

            def _post(self, simulation, target=None):
                from hydropilot.runtime.context import PostResult
                return PostResult(
                    simulation.objs if target in (None, "objs") else None,
                    simulation.cons if target in (None, "cons") else None,
                    simulation.diags if target in (None, "diags") else None,
                )

            def close(self):
                pass

        monkeypatch.setattr(uqpyl, "SimModel", DummySimModel)
        adapter = uqpyl.UQPyLAdapter("dummy.yaml")
        adapters.append(adapter)
        return adapter

    yield build
    for adapter in adapters:
        adapter.close()


def test_adapter_inherits_model_problem_public_interfaces():
    for name in ["evaluate", "simulate", "simFunc", "objFunc", "conFunc"]:
        assert getattr(uqpyl.UQPyLAdapter, name) is getattr(ModelProblem, name)


@pytest.mark.parametrize("withObs", [True, False])
@pytest.mark.parametrize("target", [None, "objs", "cons", "sims"])
def test_native_evaluate_targets_run_the_model_once(makeAdapter, withObs, target):
    adapter = makeAdapter(withObs=withObs)
    result = adapter.evaluate([[0.2], [0.8]], target=target)
    assert len(adapter.model.runCalls) == 1
    if target in (None, "objs"):
        np.testing.assert_allclose(result.objs, [[0.3], [0.9]])
    else:
        assert result.objs is None
    if target in (None, "cons"):
        np.testing.assert_allclose(result.cons, [[-0.3], [0.3]])
    else:
        assert result.cons is None
    if target in (None, "sims"):
        np.testing.assert_allclose(result.sims[:, :, 0], [[0.2, 1.2], [0.8, 1.8]])
    else:
        assert result.sims is None


@pytest.mark.parametrize("sameParameters", [False, True])
def test_interleaved_contexts_keep_their_own_objectives_and_constraints(makeAdapter, sameParameters):
    adapter = makeAdapter()
    firstX = np.array([[0.2]])
    nextX = firstX if sameParameters else np.array([[0.8]])
    firstContext = adapter.simulate(firstX)
    nextContext = adapter.simulate(nextX)
    assert isinstance(firstContext, SimContext)
    np.testing.assert_allclose(adapter.objFunc(firstX, firstContext), [[0.3]])
    np.testing.assert_allclose(adapter.conFunc(firstX, firstContext), [[-0.3]])
    np.testing.assert_allclose(adapter.objFunc(nextX, nextContext), nextX + 0.2)
    np.testing.assert_allclose(adapter.conFunc(nextX, nextContext), nextX - 0.5)
    # Reusing either context must not execute the model again.
    assert len(adapter.model.runCalls) == 2


def test_sim_func_returns_array_without_invalidating_existing_context(makeAdapter):
    adapter = makeAdapter()
    context = adapter.simulate([0.2])
    sims = adapter.simFunc([0.8])
    np.testing.assert_allclose(sims[0, :, 0], [0.8, 2.8])
    np.testing.assert_allclose(adapter.objFunc([0.2], context), [[0.3]])
    np.testing.assert_allclose(adapter.conFunc([0.2], context), [[-0.3]])
    np.testing.assert_allclose(adapter.flattenSim(context.sims), [[0.2, 1.2]])
    np.testing.assert_array_equal(adapter.flattenObs(), [0.0, 1.0])
    np.testing.assert_array_equal(adapter.flattenMask(), [False, False])
    assert len(adapter.model.runCalls) == 2


def test_simulator_and_evaluator_composition_reuses_context(makeAdapter):
    adapter = makeAdapter()
    assert isinstance(adapter.simulator, SimulatorBase)
    context = adapter.simulator.run([0.2])
    adapter.simulator.run([0.8])
    result = adapter.evaluator.evaluate([[0.2]], context)
    np.testing.assert_allclose(result.objs, [[0.3]])
    np.testing.assert_allclose(result.cons, [[-0.3]])
    np.testing.assert_allclose(result.sims[0, :, 0], [0.2, 1.2])
    np.testing.assert_array_equal(context.simulation.P, [[0.2]])
    np.testing.assert_array_equal(context.simulation.diags, [[1.0]])
    assert len(adapter.model.runCalls) == 2


@pytest.mark.parametrize("hookName", ["objFunc", "conFunc"])
def test_parameters_must_match_context_without_triggering_a_model_run(makeAdapter, hookName):
    adapter = makeAdapter()
    context = adapter.simulate([[0.2]])
    with pytest.raises(ValueError, match="does not match"):
        getattr(adapter, hookName)([[0.8]], context)
    assert len(adapter.model.runCalls) == 1


@pytest.mark.parametrize("hookName", ["objFunc", "conFunc"])
@pytest.mark.parametrize("contextSource", ["plain", "other_adapter"])
def test_context_must_carry_results_from_this_adapter(makeAdapter, hookName, contextSource):
    adapter = makeAdapter()
    context = adapter.simulate([[0.2]])
    if contextSource == "plain":
        context = SimContext(sims=context.sims, obs=context.obs, mask=context.mask)
    else:
        otherAdapter = makeAdapter()
        context = otherAdapter.simulate([[0.2]])
    with pytest.raises(ValueError, match="context returned by this UQPyLAdapter"):
        getattr(adapter, hookName)([[0.2]], context)
    assert len(adapter.model.runCalls) == 1


def test_mutating_input_array_does_not_change_context_parameters(makeAdapter):
    adapter = makeAdapter()
    X = np.array([[0.2]])
    context = adapter.simulate(X)
    X[0, 0] = 0.8
    np.testing.assert_allclose(adapter.objFunc([[0.2]], context), [[0.3]])
    np.testing.assert_allclose(context.simulation.X, [[0.2]])
    with pytest.raises(ValueError, match="does not match"):
        adapter.objFunc(X, context)
    assert len(adapter.model.runCalls) == 1


def test_failed_later_simulation_does_not_invalidate_earlier_context(makeAdapter):
    adapter = makeAdapter()
    context = adapter.simulate([[0.2]])
    adapter.model.failNext = True
    with pytest.raises(RuntimeError, match="simulation failed"):
        adapter.simulate([[0.8]])
    np.testing.assert_allclose(adapter.objFunc([[0.2]], context), [[0.3]])
    np.testing.assert_allclose(adapter.conFunc([[0.2]], context), [[-0.3]])
    assert len(adapter.model.runCalls) == 2


def test_overlapping_evaluations_return_their_own_results(makeAdapter, monkeypatch):
    adapter = makeAdapter()
    firstRunReady = Event()
    releaseFirstRun = Event()
    originalRun = adapter.model._runSimulation

    def runWithGate(X):
        result = originalRun(X)
        if X[0, 0] == 0.2:
            firstRunReady.set()
            if not releaseFirstRun.wait(timeout=10):
                raise RuntimeError("test gate timed out")
        return result

    monkeypatch.setattr(adapter.model, "_runSimulation", runWithGate)
    with ThreadPoolExecutor(max_workers=2) as pool:
        firstFuture = pool.submit(adapter.evaluate, [[0.2]])
        try:
            assert firstRunReady.wait(timeout=10)
            secondResult = pool.submit(adapter.evaluate, [[0.8]]).result(timeout=10)
        finally:
            releaseFirstRun.set()
        firstResult = firstFuture.result(timeout=10)
    np.testing.assert_allclose(firstResult.objs, [[0.3]])
    np.testing.assert_allclose(secondResult.objs, [[1.0]])
    np.testing.assert_allclose(firstResult.cons, [[-0.3]])
    np.testing.assert_allclose(secondResult.cons, [[0.3]])
    assert len(adapter.model.runCalls) == 2


def test_problem_labels_and_input_validation_use_native_interfaces(makeAdapter):
    adapter = makeAdapter()
    assert adapter.name == "ModelProblemProbe"
    assert adapter.xLabels == ["parameter"]
    assert adapter.objLabels == ["score"]
    assert adapter.conLabels == ["balance"]
    assert adapter.seriesLabels == ["flow"]
    assert adapter.obsShape == (2, 1)
    assert adapter.nObs == 2
    with pytest.raises(ValueError, match="target"):
        adapter.evaluate([[0.2]], target="unknown")
    with pytest.raises(ValueError, match="input dimension"):
        adapter.simulate([[0.2, 0.8]])
    assert len(adapter.model.runCalls) == 0


def test_no_observations_supports_optimization_and_optional_constraints(makeAdapter):
    from UQPyL.optimization.soea import GA

    adapter = makeAdapter(withObs=False, constraintCount=0)
    assert adapter.obs is None and adapter.mask is None
    assert adapter.obsShape is None and adapter.nObs is None
    assert adapter.conFunc([[0.2]], None) is None
    with pytest.raises(ValueError, match="Observation"):
        adapter.flattenObs()
    result = GA(nPop=5, maxFEs=10, verboseFlag=False, logFlag=False, saveFlag=False).run(adapter, seed=1)
    assert result.bestDecs.shape == (1, 1)
    assert np.isfinite(result.bestObjs).all()


def test_no_observations_nan_warns_without_invalidating_context(makeAdapter, monkeypatch):
    adapter = makeAdapter(withObs=False)
    originalRun = adapter.model._runSimulation

    def runWithNaN(X):
        result = originalRun(X)
        if X[0, 0] == 0.2:
            result.series["flow"][0, 1] = np.nan
            result.objs[0, 0] = np.inf
        return result

    monkeypatch.setattr(adapter.model, "_runSimulation", runWithNaN)
    with pytest.warns(RuntimeWarning, match="1 simulation values are NaN in simulation output"):
        missingContext = adapter.simulate([0.2])
    healthyContext = adapter.simulate([0.8])
    assert missingContext.obs is None and missingContext.mask is None
    assert np.isnan(adapter.flattenSim(missingContext.sims)[0, 1])
    np.testing.assert_array_equal(adapter.objFunc([0.2], missingContext), [[np.inf]])
    np.testing.assert_allclose(adapter.objFunc([0.8], healthyContext), [[1.0]])
    assert len(adapter.model.runCalls) == 2
