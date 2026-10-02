# UQPyL Integration

HydroPilot 0.1.4 currently requires the updated UQPyL development checkout exposing `SimContext`, `SimulatorBase` and `ModelEvaluatorBase`. PyPI UQPyL 2.1.6 does not yet provide these interfaces; install the matching source with `pip install -e /path/to/UQPyL`. Standalone SimModel does not require UQPyL.

HydroPilot provides a single UQPyL adapter:

- `UQPyLAdapter` wraps `SimModel` as a UQPyL `ModelProblem`.

The adapter directly inherits UQPyL's public `ModelProblem` interfaces, including complete evaluation and separate simulation/objective/constraint calls. Observations are optional for ordinary optimization.

## Installation

HydroPilot with UQPyL support:

```bash
pip install -e ".[uqpyl]"
```

This workspace uses a `py312` conda environment for validation:

```bash
conda run -n py312 python -m pytest tests/test_public_imports.py -q
```

The verified integration target is `UQPyL==2.1.6`, including the local UQPyL source used for validation on October 1, 2026.

## Import

```python
from hydropilot.integrations import UQPyLAdapter
```

## How it works

### `UQPyLAdapter`

`UQPyLAdapter` subclasses `UQPyL.problem.ModelProblem` and inherits `evaluate`, `simulate`, `simFunc`, `objFunc`, and `conFunc` directly. It creates a `SimModel` from the HydroPilot config and supplies UQPyL with problem metadata and private callbacks.

Its `SimulatorBase` implementation calls the internal batch scheduler `SimModel._runSimulation(X)` and returns a `SimContext` subclass. For each sample, the scheduler composes `_apply` (parameter transformation and writing) with `_simulate` (model execution and series extraction), holding the same project copy until extraction finishes. The context contains `sims`, `obs`, and `mask`, plus `simulation`, the complete HydroPilot simulation data (X, P, all simulation/observation series, and per-sample records). Metrics are not computed during this phase.

Objective and constraint calls delegate to the internal `_post` step. It computes only the requested block and its derived dependencies, retaining results in this context's post-processing state. Shared derived values and repeated requests reuse that state without another model run. `SimModel.run(X)` remains the independent HydroPilot entry point that combines simulation and full post-processing.

The adapter maps HydroPilot's config structure into UQPyL's `ModelProblem` constructor:

| HydroPilot config | UQPyL ModelProblem parameter |
|---|---|
| Design parameter count | `nInput` |
| Objective count | `nObj` |
| Constraint count | `nCon` |
| `type: discrete` parameters | `varType` + `varSet` |
| Design bounds | `ub` / `lb` |
| Objective / constraint ids | `objLabels` / `conLabels` |

When observations are available, series that define `obs` are exposed to `ModelProblem`. Observations are read through HydroPilot's `ObsStore` and packed into:

| Field | Shape | Description |
|---|---:|---|
| `obs` | `(n_time, n_series)` | Observed values aligned by series column |
| `mask` | `(n_time, n_series)` | `True` for missing observations and observation-length padding; independent of simulation results |
| `seriesLabels` | `list[str]` | Series ids in column order |

Without observations, all configured simulation series are exposed, and `obs` and `mask` are `None`. Ordinary optimization can use this mode; calibration methods that compare simulations with observations require observed series. At least one simulation series is required in either mode.

Simulation NaNs remain in the affected sample's output without changing `obs` or `mask`, other samples in the batch, or later runs. Series extraction records a `SIM_NAN` warning in the reporter's error logs. The adapter also emits a `RuntimeWarning` for simulation NaNs at observed positions, identifying the sample, series, and missing-value count. NaNs at missing-observation or padding positions do not trigger adapter warnings.

Without observations, simulation NaNs also trigger a `RuntimeWarning` and remain in the simulation output.

The adapter neither fills NaNs nor drops dates to recompute objectives. Objectives, constraints, and diagnostics retain HydroPilot's existing function and `on_error` semantics. UQPyL methods that consume simulation arrays directly must handle these NaNs according to their own rules.

## Basic evaluation

Call `evaluate(X)` to run a parameter vector or batch through the full HydroPilot runtime:

```python
import numpy as np
from hydropilot.integrations import UQPyLAdapter

X = np.array([
    [50.0, 0.5, 100.0],
])

with UQPyLAdapter("examples/test_monthly.yaml") as adapter:
    result = adapter.evaluate(X)
    print(result.objs)   # objective values
    print(result.cons)   # constraint values
```

`evaluate(X)` returns a `UQPyL.problem.Eval` object with `.objs`, `.cons`, and `.sims` attributes.

`X` can be:

- **1D array** — a single parameter vector, shape `(n_input,)`. The adapter handles this and returns single-row results.
- **2D array** — a batch of parameter vectors, shape `(n_samples, n_input)`. Each row is one evaluation.

The native interfaces are:

| Method | Result |
|---|---|
| `evaluate(X, target=None)` | `Eval` containing objectives, constraints, and simulations; `target` can select `"objs"`, `"cons"`, or `"sims"` |
| `simulate(X)` | Simulation context with `sims`, `obs`, `mask`, and complete simulation data in `simulation` |
| `simFunc(X)` | Simulation array with shape `(n_samples, n_time, n_series)` |
| `objFunc(X, context)` | Compute objectives and their dependencies from the supplied context; reuse previously computed results |
| `conFunc(X, context)` | Compute constraints and their dependencies, or return `None` when no constraints are configured |

`evaluate(X)` executes simulation and full post-processing, including diagnostics saved in the archive. `target="objs"` or `"cons"` computes only that block and its dependencies; `target="sims"` skips post-processing. Every `evaluate` call starts a new simulation. Native helpers `flattenSim`, `flattenObs`, and `flattenMask` are also inherited.

Separate calls can reuse earlier contexts:

```python
with UQPyLAdapter("config.yaml") as problem:
    contextA = problem.simulate(XA)
    contextB = problem.simulate(XB)
    objA = problem.objFunc(XA, contextA)  # A's values, even after B runs
    objB = problem.objFunc(XB, contextB)
    physicalA = contextA.simulation.P
```

Use the context returned by the same adapter and the parameters that produced it. A mismatched parameter array, another adapter's context, or a manually constructed `SimContext` raises `ValueError` because it cannot identify the corresponding HydroPilot simulation. A later simulation does not invalidate an earlier context.

Simulation and post-processing each submit owned snapshots to the asynchronous reporter. They update the same `(batch_id, run_id)` record; repeated post-processing does not add evaluations. SQLite is committed first, and CSV/error-log exports are generated from committed data. Simulation-only records remain available with pending metric states. See [reporter configuration](configuration-reference.md#reporter--output-persistence).

## Using with a UQPyL optimizer

Import an algorithm from a UQPyL optimization group, create it, and call `run(problem, seed=...)`:

```python
from UQPyL.optimization.soea import GA
from hydropilot.integrations import UQPyLAdapter

with UQPyLAdapter("examples/test_monthly.yaml") as problem:
    algorithm = GA()
    algorithm.run(problem, seed=42)
```

The algorithm reads problem bounds, types, objectives, and simulation metadata from the adapter and calls `evaluate()` internally during optimization.

Other algorithm groups include `UQPyL.optimization.moea` for multi-objective optimization.

## Using with UQPyL calibration

The same `UQPyLAdapter` is used when the UQPyL method needs simulated and observed series.

```python
import numpy as np
from UQPyL.calibration import GLUE, SUFI2
from hydropilot.integrations import UQPyLAdapter

X = np.array([
    [50.0, 0.5, 100.0],
    [65.0, 0.3, 120.0],
])

with UQPyLAdapter("examples/test_monthly.yaml") as problem:
    glue_result = GLUE(metric="rmse").run(problem, X, threshold=0.1)
    sufi2_result = SUFI2().run(problem, X, eliteSize=2)
```

`UQPyLAdapter.evaluate(X)` returns a `UQPyL.problem.Eval` object with `.objs`, `.cons`, and `.sims`. The simulation tensor has shape `(n_samples, n_time, n_series)`, matching UQPyL `ModelProblem` conventions.

HydroPilot series ids become UQPyL `seriesLabels`. For example, if the config has observed series `flow` and `tn`, `problem.seriesLabels` is `["flow", "tn"]`, and `result.sims[:, :, 0]` contains simulated `flow`.

## Lifecycle

Always close the adapter to release runtime resources:

```python
# Context manager (recommended)
with UQPyLAdapter("config.yaml") as problem:
    algorithm.run(problem, seed=42)

# Explicit close
adapter = UQPyLAdapter("config.yaml")
try:
    algorithm.run(adapter, seed=42)
finally:
    adapter.close()
```

The context manager calls `close()` on exit, which shuts down the underlying `SimModel` session and cleans up temporary workspace directories.

## Scope and limits

The UQPyL adapters are bridges, not analysis libraries:

- **HydroPilot handles**: configuration loading, parameter writing, model execution, series extraction, objective/constraint evaluation.
- **UQPyL handles**: optimization algorithms, sensitivity analysis, surrogate modeling, and all other advanced UQPyL workflows.
- **What HydroPilot does not provide**: UQPyL algorithm implementations, UQPyL analysis methods, or any guarantee about UQPyL optimizer convergence behavior.

For UQPyL documentation beyond this integration guide, refer to the UQPyL project directly.

## See also

- [Python API](python-api.md) — `SimModel`, `BatchRunResult`, and `UQPyLAdapter` reference.
- [Configuration Reference](configuration-reference.md) — all config fields that feed into the adapter.
- [Examples](examples.md) — example configs compatible with UQPyL optimization.
