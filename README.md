[English](./README.md) | [简体中文](./README.zh-CN.md) | [中文文档](./docs/cn/index.md)

# HydroPilot

> A configuration-first orchestration framework for hydrological model calibration, evaluation, and optimization.

HydroPilot turns the repetitive glue code around hydrological modeling into a reusable workflow: parameter mapping, input writing, model execution, result extraction, objective evaluation, and run reporting. The core is model-agnostic. Built-in templates give you shorter, model-specific configuration for supported models.

## Current status

What is available today:

- `version: general` — model-agnostic workflow mode
- `version: swat` — template for SWAT 2012
- `version: xaj` — template for XAJ (Xinanjiang)
- readers: `text`, `csv`
- writers: `fixed_width`, `csv`
- subprocess-based model execution
- built-in and external evaluation functions
- SQLite and CSV run reporting
- UQPyL integration

CLI entry points:

- `hydropilot-validate` — validate a configuration
- `hydropilot-test` — run one configuration test
- `hydropilot-apply` — apply parameters to a project copy
- `hydropilot-run` — single-run YAML entry point

Public Python API:

- `SimModel` — main runtime entry point
- `BatchRunResult` — batch evaluation result
- `UQPyLAdapter` — bridge to UQPyL optimization

Planned, not yet available:

- APEX
- HBV
- VIC
- HEC-HMS

## Installation

Requires Python 3.10+.

```bash
pip install hydropilot
```

For local development:

```bash
pip install -e .
pip install -e .[dev]
```

With UQPyL integration:

```bash
pip install -e .[uqpyl]
```

## Quick start

### Validate a configuration

```bash
hydropilot-validate path/to/config.yaml
```

### Test a configuration

```bash
hydropilot-test path/to/config.yaml
```

Runs one deterministic parameter vector through the full runtime, forces `parallel = 1`, keeps the runtime project copy, and writes `test-report.md` under the run archive.

### Apply parameters to a project

```bash
hydropilot-apply path/to/apply.yaml
```

### Run from a YAML definition

```bash
hydropilot-run path/to/run.yaml
```

Executes one parameter vector described by a run YAML file. It's a single-run entry point — it doesn't manage full experiments.

### Evaluate parameter vectors with SimModel

```python
import numpy as np
from hydropilot import SimModel

X = np.array([
    [50.0, 0.5, 100.0],
])

with SimModel("examples/test_monthly.yaml") as model:
    result = model.run(X)
    print(result.objs)
```

### Use with UQPyL

```python
from hydropilot.integrations import UQPyLAdapter

with UQPyLAdapter("examples/test_daily.yaml") as adapter:
    result = adapter.evaluate(X)
    print(result.objs)
    print(result.cons)
```

## Support matrix

| Capability | Status |
|---|---|
| General configuration mode (`version: general`) | Available |
| SWAT 2012 template (`version: swat`) | Available |
| XAJ template (`version: xaj`) | Available |
| Fixed-width parameter writing | Available |
| CSV parameter writing | Available |
| Text-based series extraction | Available |
| CSV series extraction | Available |
| Subprocess runner | Available |
| SQLite + CSV reporting | Available |
| UQPyL adapter | Available |
| `hydropilot-validate` | Available |
| `hydropilot-test` | Available |
| `hydropilot-apply` | Available |
| `hydropilot-run` | Available |
| APEX template | Planned |
| HBV template | Planned |
| VIC template | Planned |
| HEC-HMS template | Planned |

## Documentation

- [Documentation hub](docs/index.md) — index of all documentation
- [Architecture](docs/architecture.md) — config chain, runtime chain, and module layout

## License

MIT
