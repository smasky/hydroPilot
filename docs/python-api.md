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

- `X` — a list or numpy array of design parameter values, in the same order as defined in the config's `parameters.design` list. A 1D array runs a single evaluation; a 2D array of shape `(n_samples, n_input)` runs a batch. Named values via dict are also accepted for single evaluations: `model.run({"CN2": 72.5, "ALPHA_BF": 0.3, "GW_DELAY": 120})`.
- Returns a `BatchRunResult`. For batch runs, `result.objs` has shape `(n_samples, n_objectives)`.

What happens internally for each evaluation:
1. A project copy is created from `basic.projectPath` into a temporary instance directory under `basic.workPath`.
2. Design values are transformed to physical parameters and written to model input files.
3. The model command (`basic.command`) is executed in the project copy.
4. Simulation output is extracted and evaluated (objectives, constraints, diagnostics).
5. Results and artifacts are archived, and the project copy is released (or kept if `keepInstances: true`).

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
| `xLabels` | `list[str]` | Names of design parameters |
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

### Usage

```python
result = model.run([72.5, 0.3, 120])
print(result.objs)     # e.g. [[0.78]]
print(result.X)        # [[72.5, 0.3, 120.0]]
```

For a single run, array dimensions have `n_samples = 1`.

---

## `UQPyLAdapter`

Wraps `SimModel` as a UQPyL `Problem` for use with UQPyL's optimization and analysis algorithms.

```python
from hydropilot.integrations import UQPyLAdapter

adapter = UQPyLAdapter("path/to/config.yaml")
```

### Description

`UQPyLAdapter` extends `UQPyL.problem.Problem` and delegates to `SimModel` internally. It sets up the UQPyL problem definition (`nInput`, `nObj`, `nCon`, bounds, variable types, objective directions) from the hydroPilot config.

### Context manager

```python
with UQPyLAdapter("config.yaml") as adapter:
    result = adapter.evaluate(X)
    objs = result.objs
```

### Methods

#### `evaluate(X)`

```python
result = adapter.evaluate(X)
objs = result.objs
cons = result.cons
```

Runs the model and returns a `UQPyL.problem.Eval` object. Compatible with UQPyL algorithms that call `evaluate()`.

#### `objFunc(X)`

```python
objectives = adapter.objFunc(X)
```

Returns only the objective values as a NumPy array. Compatible with UQPyL optimizers that call `objFunc(X)`.

#### `conFunc(X)`

```python
constraints = adapter.conFunc(X)
```

Returns only the constraint values as a NumPy array, or `None` if no constraints are defined in the config.

### Scope

The adapter provides the basic UQPyL `Problem` interface: problem definition, `Eval`-returning evaluation, and objective/constraint accessors. It does not implement UQPyL-specific analysis methods (sensitivity analysis, surrogate modeling, etc.). For advanced UQPyL workflows, use the adapter as a `Problem` and call UQPyL's own analysis functions directly.

### Example: using the adapter

```python
from hydropilot.integrations import UQPyLAdapter

with UQPyLAdapter("config.yaml") as adapter:
    # Evaluate a parameter vector
    result = adapter.evaluate(X)
    objs = result.objs
    cons = result.cons

    # Or access objectives and constraints separately
    objs = adapter.objFunc(X)
    cons = adapter.conFunc(X)
```

The adapter can be passed to any UQPyL algorithm that accepts a `Problem` instance.

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
