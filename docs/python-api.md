# Python API Reference

hydroPilot's public Python API provides programmatic access to model simulation, batch runs, and optional UQPyL integration.

## Main imports

```python
from hydropilot import SimModel, BatchRunResult
from hydropilot.integrations import UQPyLAdapter
```

These are the only stable public imports. Other modules and classes are internal and may change without notice.

---

## `SimModel`

`SimModel` is the primary entry point for running simulations from Python.

```python
from hydropilot import SimModel

model = SimModel("path/to/config.yaml")
```

### Constructor

`SimModel(cfgPath: str)` loads and validates the configuration at `cfgPath`. The config version determines whether a model template (SWAT 2012 or XAJ) is used for expansion. On success, a runtime session is initialized.

### Context manager

`SimModel` supports the context-manager protocol. The session is automatically closed on exit:

```python
with SimModel("path/to/config.yaml") as model:
    result = model.run([72.5, 0.3, 120])
# session closed here
```

### `run(X)`

Run one or more evaluations with the given design parameter values.

```python
# Single evaluation — 1D array
result: BatchRunResult = model.run([72.5, 0.3, 120])

# Batch evaluation — 2D array of shape (n_samples, n_input)
result: BatchRunResult = model.run([
    [72.5, 0.3, 120],
    [65.0, 0.5, 200],
    [80.0, 0.2, 80],
])
```

- `X` — a list or numpy array of design parameter values, in the same order as defined in the config's `parameters.design` list. A 1D array runs a single evaluation; a 2D array of shape `(n_samples, n_input)` runs a batch.
- Returns a `BatchRunResult`. For batch runs, `result.objs` has shape `(n_samples, n_objectives)`.

`run(X)` combines parameter application, simulation, and post-processing and operates independently of UQPyL. The session prepares project copies under `basic.workPath` once and reuses them for simulations.

For each sample:

1. The batch scheduler `_runSimulation(X)` leases a project copy for each sample and calls `_apply(workPath, X, context)` to transform design values into physical parameters, write the inputs, and record the write details.
2. `_simulate(workPath, context)` executes `basic.command` and extracts series from the same prepared copy. The scheduler releases that copy after extraction, assembles the owned batch context, and submits simulation snapshots for archiving. Metrics remain pending.
3. `_post` computes derived values, objectives, constraints, and diagnostics from that context. It caches the results and submits a snapshot updating the same sample record.
4. The reporter commits snapshots to SQLite and exports CSV files and error logs from the committed data.

Closing the session drains the reporter and removes project copies unless `keepCopies: true`. Retained copies keep outputs and logs, while touched input files are restored to their session-start contents. Set `reset: true` to also restore inputs after each simulation for debugging; it defaults to `false`.

The internal `_apply` and `_simulate` steps can be composed separately. `_apply` does not execute the model or allocate an evaluation record; `_simulate` uses the prepared inputs without transforming or writing parameters again. Batch scheduling handles IDs, instance ownership, error handling, and archiving. For a standalone project copy, use the public `apply_design` or `apply_params` methods below.

### `apply_design(X, out_dir)`

Apply design parameters to a fresh project copy.

```python
model.apply_design([72.5, 0.3, 120], "./my_project")
```

- Transforms design values through the full design-to-physical pipeline.
- Writes physical parameters to model input files in the output directory.
- The output directory can be inspected or run manually.

### `apply_params(P, out_dir)`

Apply physical parameters directly to a fresh project copy, bypassing the design layer.

```python
model.apply_params([0.75, 0.003, 0.22], "./my_project")
```

- `P` — a list or array of physical parameter values, matching the config's `parameters.physical` order.
- Useful for applying already-resolved physical parameters.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `nInput` | `int` | Number of design input parameters |
| `xLabels` | `list[str]` | Design parameter labels, including scope when present (for example `ESCO.bsn`) |
| `lb` | `list[float]` | Lower bounds per design parameter |
| `ub` | `list[float]` | Upper bounds per design parameter |
| `varType` | `list[int]` | Variable type codes (0=float, 1=int, 2=discrete) |
| `nOutput` | `int` | Number of objectives |
| `nConstraints` | `int` | Number of constraints |
| `optType` | `list[str]` | Optimization direction strings per objective (`"min"` or `"max"`) |
| `cfgPath` | `str` | Path to the loaded config file |

---

## `BatchRunResult`

A dataclass returned by `SimModel.run()` and the internal batch executor.

```python
from hydropilot import BatchRunResult
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `X` | `np.ndarray` | Design parameter values that were evaluated, shape `(n_samples, n_input)` |
| `P` | `np.ndarray` or `None` | Resolved physical parameter values, shape `(n_samples, n_physical)` |
| `objs` | `np.ndarray` | Objective function values, shape `(n_samples, n_objectives)` |
| `cons` | `np.ndarray` or `None` | Constraint values, shape `(n_samples, n_constraints)`. `None` if no constraints defined. |
| `diags` | `np.ndarray` or `None` | Diagnostic values, shape `(n_samples, n_diagnostics)`. `None` if no diagnostics defined. |
| `series` | `dict[str, np.ndarray]` or `None` | Extracted time series keyed by series id, each with shape `(n_samples, n_timesteps)`. `None` if series extraction was not performed. |
| `obs` | `dict[str, np.ndarray]` or `None` | Observation arrays keyed by series id, each with shape `(n_timesteps,)`. `None` when no observations are configured. |

### Usage

```python
result = model.run([72.5, 0.3, 120])
print(result.objs)     # e.g. [[0.78]]
print(result.X)        # [[72.5, 0.3, 120.0]]
```

For a single run, array dimensions have `n_samples = 1`.

---

## UQPyL adapter

HydroPilot provides one public UQPyL integration class:

| Class | UQPyL base class | Use case |
|-------|------------------|----------|
| `UQPyLAdapter` | `UQPyL.problem.ModelProblem` | Optimization with simulated series; calibration with simulated and observed series |

### `UQPyLAdapter`

Wraps `SimModel` as a UQPyL `ModelProblem` for use with UQPyL optimization and calibration algorithms.

```python
from hydropilot.integrations import UQPyLAdapter

adapter = UQPyLAdapter("path/to/config.yaml")
```

#### Description

`UQPyLAdapter` directly inherits the public interfaces of `UQPyL.problem.ModelProblem` and delegates model execution to `SimModel`. It sets up the problem definition (`nInput`, `nObj`, `nCon`, bounds, variable types, objective directions, and labels) from the HydroPilot config, and builds `obs`, `mask`, and `seriesLabels` from HydroPilot series definitions.

#### Context manager

```python
with UQPyLAdapter("config.yaml") as adapter:
    result = adapter.evaluate(X)
    objs = result.objs
```

#### Methods

##### `evaluate(X, target=None)`

```python
result = adapter.evaluate(X)
objs = result.objs
cons = result.cons
sim = result.sims
```

Runs the model and returns a `UQPyL.problem.Eval` object. The returned `.sims` tensor has shape `(n_samples, n_time, n_series)`.

`target` can be `None` (all fields), `"objs"`, `"cons"`, or `"sims"`. The default executes simulation and all post-processing, including archived diagnostics. Targets `"objs"` and `"cons"` compute only the selected block and its dependencies; `"sims"` skips post-processing. Every call starts a new simulation.

##### Separate simulation and evaluation

| Method | Result |
|---|---|
| `simulate(X)` | A `SimContext` subclass with `sims`, `obs`, `mask`, and full HydroPilot simulation data in `simulation`; metrics are not computed |
| `simFunc(X)` | Simulation array with shape `(n_samples, n_time, n_series)` |
| `objFunc(X, context)` | Compute this context's objectives and dependencies, reusing prior results |
| `conFunc(X, context)` | Compute this context's constraints and dependencies, or return `None` if no constraints are configured |

```python
with UQPyLAdapter("config.yaml") as problem:
    contextA = problem.simulate(XA)
    contextB = problem.simulate(XB)
    objA = problem.objFunc(XA, contextA)
    physicalA = contextA.simulation.P
```

Each context retains its own simulation and post-processing state. Objective/constraint calls compute the requested block without running the model again; repeated calls reuse results. These stages archive into the same sample record, including simulation-only records with pending metrics. Use a context from the same adapter with the parameters that produced it; mismatched parameters, another adapter's context, and manually constructed contexts raise `ValueError`. Native helpers `flattenSim`, `flattenObs`, and `flattenMask` are also inherited.

#### Scope

The adapter provides a UQPyL `ModelProblem` interface: problem definition, simulation-backed evaluation, objective/constraint evaluation, and observed-series metadata. It does not implement UQPyL-specific analysis methods.

#### Example: using the adapter

```python
from hydropilot.integrations import UQPyLAdapter

with UQPyLAdapter("config.yaml") as adapter:
    # Evaluate a parameter vector
    result = adapter.evaluate(X)
    objs = result.objs
    cons = result.cons

    sim = result.sims
```

The adapter can be passed to any UQPyL algorithm that accepts a `ModelProblem` instance.

Current UQPyL optimizers use `algorithm.run(problem)`:

```python
from UQPyL.optimization.soea import GA
from hydropilot.integrations import UQPyLAdapter

with UQPyLAdapter("config.yaml") as problem:
    algorithm = GA(nPop=20, maxFEs=100, verboseFlag=False, logFlag=False, saveFlag=False)
    result = algorithm.run(problem, seed=123)
    print(result.bestDecs)
    print(result.bestObjs)
```

When observations are available, `series` entries that define `obs` are exposed as model series. Their ids become `adapter.seriesLabels`. Without observations, all configured simulation series are exposed.

The adapter builds:

| Attribute | Type | Description |
|-----------|------|-------------|
| `obs` | `np.ndarray` or `None` | Observed values with shape `(n_time, n_series)`, if available |
| `mask` | `np.ndarray` or `None` | Boolean mask with shape `(n_time, n_series)`; `True` marks missing observations or observation-length padding, independent of simulation results |
| `seriesLabels` | `list[str]` | Series ids in column order |

At least one simulation series is required. Observations are optional for ordinary optimization; without observations, `obs` and `mask` are `None`.

#### Example: GLUE and SUFI2

```python
import numpy as np
from UQPyL.calibration import GLUE, SUFI2
from hydropilot.integrations import UQPyLAdapter

X = np.array([
    [72.5, 0.3, 120],
    [65.0, 0.5, 200],
])

with UQPyLAdapter("config.yaml") as problem:
    glue_result = GLUE(metric="rmse", verboseFlag=False).run(
        problem,
        X,
        threshold=0.1,
    )

    sufi2_result = SUFI2(verboseFlag=False).run(
        problem,
        X,
        eliteSize=2,
    )
```

Use `UQPyLAdapter` for ordinary optimization and calibration. Methods that compare simulations with observations, including GLUE and SUFI2, require observed series.
