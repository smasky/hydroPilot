# HydroPilot Documentation

Welcome to the HydroPilot documentation. HydroPilot is a configuration-first orchestration framework for hydrological model calibration, evaluation, and optimization.

Chinese-language documentation is available under [`docs/cn/`](cn/index.md).

## Documentation map

### Core references

- [Architecture](architecture.md) — config chain, runtime chain, module layout, and execution model
- [CLI reference](cli.md) — `hydropilot-validate`, `hydropilot-test`, `hydropilot-apply`, `hydropilot-run`
- [Configuration reference](configuration-reference.md) — field-by-field reference for all configuration modes
- [Examples](examples.md) — example config index and walkthrough
- [Python API](python-api.md) — `SimModel`, `BatchRunResult`, `UQPyLAdapter`
- [UQPyL integration](uqpyl.md) — bridge to UQPyL optimization, `Eval` protocol, optimizer patterns

### General mode

- [Configuration reference](configuration-reference.md) — the full `version: general` schema and path semantics
- [Examples](examples.md) — general-mode examples alongside template-mode comparisons

### SWAT 2012

- [SWAT 2012 template](templates/swat-2012.md) — `version: swat` configuration, parameter library, and output variables
- [SWAT 2012 daily step-by-step](guides/swat-daily-step-by-step.md) — first runnable SWAT 2012 workflow
- [SWAT 2012 monthly guide](guides/swat-monthly-guide.md) — moving the same workflow to monthly output
- [SWAT 2012 parameters and series](guides/swat-parameters-and-series.md) — output files, variables, filters, and parameter strategies

### SWAT+

- [SWAT+ template](templates/swatplus.md) — `version: swatplus` configuration, parameter database, and output variables
- [SWAT+ support status](guides/swatplus-support-status.md) — current implemented scope and remaining boundaries
- [SWAT+ calibration.cal write path](guides/swatplus-calibration-cal.md) — how SWAT+ parameters are written through `calibration.cal`
- [SWAT+ calibration.cal user guide](guides/swatplus-calibration-cal-user-guide.md) — how to use the new SWAT+ parameter-writing route in practice
- [SWAT+ flow extraction guide](guides/swatplus-flow-extraction.md) — how to extract streamflow from SWAT+ output files

### XAJ

- [XAJ template](templates/xaj.md) — `version: xaj` configuration and project structure
- [Examples](examples.md) — includes the XAJ template example and its expanded general counterpart

## Quick links

- [README](../README.md) — project overview, installation, and quick start
- [Architecture](architecture.md) — implementation-oriented architecture guide

## Configuration modes

HydroPilot supports two configuration modes:

- **General mode** (`version: general`) — full control over a model-agnostic workflow. You define parameter writing and series readers explicitly.
- **Template mode** — shorter model-specific config. Current templates: SWAT 2012 (`version: swat`), SWAT+ (`version: swatplus`), and XAJ (`version: xaj`). Templates expand into the standard general config at runtime.

## CLI tools

Four CLI entry points are available:

| Command | Purpose |
|---|---|
| `hydropilot-validate` | Validate a configuration and report diagnostics |
| `hydropilot-test` | Run a single deterministic test through the full runtime |
| `hydropilot-apply` | Apply parameters to a project copy |
| `hydropilot-run` | Single-run YAML entry point |

## Python API

Primary public API exports:

| Symbol | Purpose |
|---|---|
| `SimModel` | Main runtime entry point for model evaluation |
| `BatchRunResult` | Result container for batch evaluation |
| `UQPyLAdapter` | Bridge to UQPyL optimization |

Import examples:

```python
from hydropilot import SimModel, BatchRunResult
from hydropilot.integrations import UQPyLAdapter
```
