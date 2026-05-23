# UQPyL Integration

HydroPilot provides `UQPyLAdapter` to bridge HydroPilot configurations into UQPyL optimization workflows. The adapter wraps a `SimModel` as a UQPyL `Problem`, so any UQPyL algorithm can optimize parameters defined in a HydroPilot config.

## Installation

HydroPilot with UQPyL support:

```bash
pip install -e ".[uqpyl]"
```

This workspace uses a `py312` conda environment for validation:

```bash
conda run -n py312 python -m pytest tests/test_public_imports.py -q
```

UQPyL must be installed separately. The current verified integration target in this repository is the latest installable PyPI release available during validation on May 23, 2026: `UQPyL==2.1.6`.

## Import

```python
from hydropilot.integrations import UQPyLAdapter
```

## How it works

`UQPyLAdapter` subclasses `UQPyL.problem.Problem`. It creates a `SimModel` from a HydroPilot config and registers a private evaluation callable with `Problem`:

```python
class UQPyLAdapter(Problem):
    def __init__(self, cfgPath: str):
        self.model = SimModel(cfgPath)
        super().__init__(
            nInput=self.model.nInput,
            nObj=self.model.nOutput,
            nCon=self.model.nConstraints,
            varType=self.model.varType,
            varSet=self.model.varSet,
            ub=self.model.ub,
            lb=self.model.lb,
            xLabels=self.model.xLabels,
            optType=self.model.optType,
            evaluate=self._evaluate,
        )

    def _evaluate(self, X):
        result = self.model.run(X)
        return Eval(objs=result.objs, cons=result.cons)
```

The adapter maps HydroPilot's config structure into UQPyL's `Problem` constructor:

| HydroPilot config | UQPyL Problem parameter |
|---|---|
| Design parameter count | `nInput` |
| Objective count | `nObj` |
| Constraint count | `nCon` |
| `type: discrete` parameters | `varType` + `varSet` |
| Design bounds | `ub` / `lb` |

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

`evaluate(X)` returns a `UQPyL.problem.Eval` object with `.objs` and `.cons` attributes.

`X` can be:

- **1D array** — a single parameter vector, shape `(n_input,)`. The adapter handles this and returns single-row results.
- **2D array** — a batch of parameter vectors, shape `(n_samples, n_input)`. Each row is one evaluation.

The inherited `objFunc(X)` and `conFunc(X)` accessors are also available and return the same arrays as `evaluate(X).objs` / `.cons`.

## Using with a UQPyL optimizer

Import an algorithm from a UQPyL optimization group, create it, and call `run(problem, seed=...)`:

```python
from UQPyL.optimization.soea import GA
from hydropilot.integrations import UQPyLAdapter

with UQPyLAdapter("examples/test_monthly.yaml") as problem:
    algorithm = GA()
    algorithm.run(problem, seed=42)
```

The algorithm reads problem bounds, types, and objectives from the adapter and calls `evaluate()` internally during optimization.

Other algorithm groups include `UQPyL.optimization.moea` for multi-objective optimization.

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

`UQPyLAdapter` is a bridge, not an analysis library:

- **HydroPilot handles**: configuration loading, parameter writing, model execution, series extraction, objective/constraint evaluation.
- **UQPyL handles**: optimization algorithms, sensitivity analysis, surrogate modeling, and all other advanced UQPyL workflows.
- **What HydroPilot does not provide**: UQPyL algorithm implementations, UQPyL analysis methods, or any guarantee about UQPyL optimizer convergence behavior.

For UQPyL documentation beyond this integration guide, refer to the UQPyL project directly.

## See also

- [Python API](python-api.md) — `SimModel` and `BatchRunResult` reference.
- [Configuration Reference](configuration-reference.md) — all config fields that feed into the adapter.
- [Examples](examples.md) — example configs compatible with UQPyL optimization.
