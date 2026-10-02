from pathlib import Path
import sys
from types import SimpleNamespace
import warnings

import numpy as np
import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

pytest.importorskip("UQPyL")

from hydropilot.api import BatchRunResult
from hydropilot.integrations import uqpyl


@pytest.fixture
def makeAdapter(monkeypatch):
    adapters = []

    def build(obs=None):
        sourceObs = np.array([10.0, 20.0, 30.0]) if obs is None else np.asarray(obs, dtype=float)

        class DummySimModel:
            nInput = 1
            nOutput = 1
            nConstraints = 0
            varType = [0]
            varSet = {}
            ub = [4.0]
            lb = [0.0]
            xLabels = ["x"]
            optType = ["min"]

            def __init__(self, cfgPath):
                self.cfg = SimpleNamespace(
                    basic=SimpleNamespace(name="NaNProbe"),
                    series=[SimpleNamespace(id="flow", obs=object())],
                )
                self.session = SimpleNamespace(executor=SimpleNamespace(
                    services=SimpleNamespace(obsStore=SimpleNamespace(get=lambda sid: sourceObs))
                ))

            def _runSimulation(self, X):
                X = np.atleast_2d(np.asarray(X, dtype=float))
                flow = np.tile([10.0, 20.0, 30.0], (len(X), 1))
                flow[X[:, 0] == 1, 1] = np.nan
                flow[X[:, 0] == 2, :] = np.nan
                if np.all(X[:, 0] == 3):
                    flow = flow[:, :2]
                series = {} if np.all(X[:, 0] == 4) else {"flow": flow}
                objs = np.where(X == 0, 0.0, np.inf)
                return BatchRunResult(
                    X=X, P=None, objs=objs, cons=None, diags=None,
                    series=series, obs={"flow": sourceObs},
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


@pytest.mark.parametrize("badInput, missingCount", [(1, 1), (2, 3), (3, 1), (4, 3)])
def test_nan_run_does_not_change_observations_or_later_runs(makeAdapter, badInput, missingCount):
    adapter = makeAdapter()
    originalObs = adapter.obs
    originalMask = adapter.mask
    with pytest.warns(RuntimeWarning, match=rf"sample 1, series 'flow': {missingCount}") as notices:
        badResult = adapter.evaluate([[badInput]])

    assert len(notices) == 1
    assert np.isnan(badResult.sims).sum() == missingCount
    assert np.isinf(badResult.objs).all()
    assert adapter.obs is originalObs
    assert adapter.mask is originalMask
    np.testing.assert_array_equal(adapter.obs[:, 0], [10.0, 20.0, 30.0])
    np.testing.assert_array_equal(adapter.mask[:, 0], [False, False, False])

    with warnings.catch_warnings(record=True) as notices:
        warnings.simplefilter("always")
        goodResult = adapter.evaluate([[0]])
    assert not notices
    np.testing.assert_array_equal(goodResult.sims[0, :, 0], [10.0, 20.0, 30.0])
    np.testing.assert_array_equal(goodResult.objs, [[0.0]])
    assert goodResult.cons is None
    np.testing.assert_array_equal(adapter.obs, originalObs)
    np.testing.assert_array_equal(adapter.mask, originalMask)


def test_nan_sample_does_not_mask_healthy_sample_in_same_batch(makeAdapter):
    adapter = makeAdapter()
    with pytest.warns(RuntimeWarning, match="sample 1, series 'flow': 1") as notices:
        result = adapter.evaluate([[1], [0]])
    assert len(notices) == 1
    assert np.isnan(result.sims[0, 1, 0])
    np.testing.assert_array_equal(result.sims[1, :, 0], adapter.obs[:, 0])
    assert not adapter.mask.any()
    assert np.isinf(result.objs[0, 0])
    assert result.objs[1, 0] == 0.0


def test_simulate_context_and_flatten_keep_original_observation_grid(makeAdapter):
    adapter = makeAdapter()
    earlierContext = adapter.simulate([[0]])
    with pytest.warns(RuntimeWarning, match="sample 1, series 'flow': 1"):
        context = adapter.simulate([[1]])
    assert np.isnan(adapter.flattenSim(context.sims)[0, 1])
    np.testing.assert_array_equal(context.obs[:, 0], [10.0, 20.0, 30.0])
    np.testing.assert_array_equal(context.mask[:, 0], [False, False, False])
    np.testing.assert_array_equal(earlierContext.obs, context.obs)
    np.testing.assert_array_equal(earlierContext.mask, context.mask)
    np.testing.assert_array_equal(adapter.flattenObs(), [10.0, 20.0, 30.0])
    np.testing.assert_array_equal(adapter.flattenMask(), [False, False, False])
    np.testing.assert_array_equal(adapter.objFunc([[0]], earlierContext), [[0.0]])
    assert np.isinf(adapter.objFunc([[1]], context)).all()


def test_nan_at_missing_observation_is_not_an_adapter_warning(makeAdapter):
    adapter = makeAdapter([10.0, np.nan, 30.0])
    with warnings.catch_warnings(record=True) as notices:
        warnings.simplefilter("always")
        result = adapter.evaluate([[1]])
    assert not notices
    assert np.isnan(result.sims[0, 1, 0])
    np.testing.assert_array_equal(adapter.obs[:, 0], [10.0, np.nan, 30.0])
    np.testing.assert_array_equal(adapter.mask[:, 0], [False, True, False])


def test_nan_output_validation_still_rejects_wrong_sample_count(makeAdapter):
    adapter = makeAdapter()
    with pytest.raises(ValueError, match="first dimension"):
        adapter._validate_sim(np.full((2, 3, 1), np.nan), 1)


def test_output_validation_still_rejects_non_numeric_values(makeAdapter):
    adapter = makeAdapter()
    with pytest.raises(TypeError, match="numeric"):
        adapter._validate_sim(np.array([[["bad"], ["bad"], ["bad"]]]), 1)
