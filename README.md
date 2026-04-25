[English](./README.md) | [简体中文](./README.zh-CN.md)

# HydroPilot

> A configuration-first orchestration framework for hydrological model calibration, evaluation, and optimization.

HydroPilot turns the repetitive glue code around hydrological modeling into a reusable workflow: parameter mapping, input writing, model execution, result extraction, objective evaluation, and run reporting.

The core is model-agnostic. In the current repository, SWAT is the first built-in template and the most mature integration.

## What HydroPilot is

HydroPilot is:

- a configuration-driven workflow framework
- a reusable runtime for repeated model experiments
- a general schema that is not tied to one model family
- a template system that can make specific models easier to configure

HydroPilot is not:

- a SWAT-only script bundle
- an optimizer by itself
- a finished multi-model platform with every template already implemented

## Current status

What is already available in code today:

- `version: general` workflow mode
- `version: swat` template mode
- fixed-width parameter writing
- text-based series extraction
- subprocess-based model execution
- built-in and external evaluation functions
- SQLite and CSV run reporting
- UQPyL integration
- `hydropilot-validate` CLI

What is planned rather than built-in today:

- APEX
- HBV
- VIC
- HEC-HMS

## Why this exists

In hydrological calibration work, the optimizer is often not the painful part. The painful part is the surrounding scripting:

- mapping optimizer variables to physical parameters
- writing values into multiple model input files
- launching an external model repeatedly and safely
- extracting comparable output series
- computing objectives, constraints, and diagnostics
- keeping run records for debugging and comparison

HydroPilot packages that repeated work into one reproducible pipeline.

## Two configuration modes

### 1. General mode

Use `version: general` when you want full control over a model-agnostic workflow.

- you define parameter writing explicitly
- you define series readers explicitly
- this is the real framework core

### 2. Template mode

Use a template version such as `version: swat` when you want a shorter model-specific config.

- the template expands a compact config into a standard general config
- runtime execution still happens through the same general pipeline
- in the current codebase, `swat` is the only built-in template

## Installation

Requires Python 3.10+.

Install the package in editable mode:

```bash
pip install -e .
```

Install development dependencies:

```bash
pip install -e .[dev]
```

Install UQPyL integration support:

```bash
pip install -e .[uqpyl]
```

## Quick start

### Validate a configuration

```bash
hydropilot-validate path/to/config.yaml
```

### Evaluate parameter vectors with `SimModel`

```python
import numpy as np
from hydro_pilot import SimModel

X = np.array([
    [50.0, 0.5, 100.0],
])

with SimModel("examples/test_monthly.yaml") as model:
    result = model.run(X)
    print(result.objs)
```

### Use with UQPyL

```python
from hydro_pilot.integrations import UQPyLAdapter
from UQPyL.optimization import DE

with UQPyLAdapter("examples/test_daily.yaml") as problem:
    optimizer = DE(problem)
    optimizer.run()
```

## Minimal general-mode example

This example reflects the current general schema more closely than the older simplified drafts:

```yaml
version: general

basic:
  projectPath: ./project
  workPath: ./work
  command: my_model.exe

parameters:
  design:
    - name: K
      bounds: [0.0, 1.0]
  physical:
    - name: K
      mode: v
      writerType: fixed_width
      file:
        name: model.inp
        line: 12
        start: 1
        width: 10
        precision: 4

series:
  - id: flow
    sim:
      readerType: text
      file:
        name: model.out
        rowRanges:
          - [1, 365]
        colNum: 2
    obs:
      readerType: text
      file:
        name: obs_flow.txt
        rowRanges:
          - [1, 365]
        colNum: 2

functions:
  - name: NSE
    kind: builtin

derived:
  - id: nse_flow
    call:
      func: NSE
      args: [flow.sim, flow.obs]

objectives:
  - id: obj_nse
    ref: nse_flow
    sense: max
```

## Template example

The repository currently has working SWAT examples such as:

- `examples/test_daily.yaml`
- `examples/test_monthly.yaml`
- `examples/test_monthly_complex.yaml`
- `examples/test_monthly_series.yaml`

A compact SWAT config looks like this:

```yaml
version: swat

basic:
  projectPath: E:\BMPs\TxtInOut
  workPath: ./work
  command: swat.exe

parameters:
  design:
    - name: CN2
      bounds: [35, 98]
    - name: ALPHA_BF
      bounds: [0, 1]
    - name: GW_DELAY
      bounds: [0, 500]

series:
  - id: flow
    sim:
      file: output.rch
      id: 62
      period: [2019, 2021]
      timestep: monthly
      colSpan: [50, 61]
    obs:
      file: obs_flow_monthly.txt
      rowRanges:
        - [1, 36]
      colSpan: [1, 12]

functions:
  - name: NSE
    kind: builtin

derived:
  - id: nse_flow
    call:
      func: NSE
      args: [flow.sim, flow.obs]

objectives:
  - id: obj_nse
    ref: nse_flow
    sense: max
```

## Path semantics

This is important in the current implementation:

- observation files such as `obs.file` are resolved relative to the config file
- simulation output files such as `sim.file` are resolved relative to the runtime project copy / work instance

So if your model produces `output.rch` inside the run workspace, the config should usually keep it as:

```yaml
sim:
  readerType: text
  file: output.rch
  rowRanges:
    - [1, 365]
  colNum: 1
```

not as a path relative to the YAML file location.

## Runtime chain

HydroPilot now has two distinct chains that are worth understanding.

### Config and template chain

```text
YAML config
  -> config.loader
  -> template registry (if version != general)
  -> template expansion to general config
  -> RunConfig
```

For example, `version: swat` goes through the SWAT template and becomes a standard `version: general` runtime config.

### Runtime execution chain

```text
SimModel
  -> Session
  -> Workspace
  -> Executor
     -> ExecutionServices
        -> ParamSpace
        -> ParamWritePlan
        -> ParamApplier
        -> SeriesPlan
        -> ObsStore
        -> SubprocessRunner
        -> SeriesExtractor
        -> Evaluator
  -> RunReporter
```

Conceptually, the runtime pipeline is:

```text
Parameter writing
  -> Model execution
  -> Series extraction
  -> Derived/objective evaluation
  -> Run reporting
```

## Repository layout

```text
src/hydro_pilot/
  api/           public API entry points
  cli/           command-line interfaces
  config/        config loading, schema, path resolution
  evaluation/    functions and scalar evaluation
  integrations/  external optimization adapters
  io/            readers, writers, runners
  models/        template registry and model-specific knowledge
  params/        parameter space and write application
  reporting/     run persistence and artifacts
  runtime/       session, workspace, orchestration
  series/        series planning, obs store, extraction
  validation/    user-facing config diagnostics
```

## Built-in functions

The current built-in function set includes:

- `NSE`
- `KGE`
- `R2`
- `RMSE`
- `MSE`
- `PBIAS`
- `LogNSE`
- `sum_series`

External Python functions are also supported.

## Outputs and run records

Each run creates an isolated runtime workspace plus an archive area. Depending on the config and execution path, outputs can include:

- original config copy
- resolved general config copy
- copied observation files when applicable
- `summary.csv`
- `results.db`
- `error.jsonl`
- `error.log`
- optional exported series CSV files

## CLI status

Right now, the documented built-in CLI is:

- `hydropilot-validate`

Commands such as `run` and `expand` are still better treated as roadmap items until they are added as real entry points.

## Support matrix

| Capability | Status |
|---|---|
| General configuration mode | Available |
| Template system | Available |
| Built-in registered templates | SWAT |
| Fixed-width parameter writing | Available |
| Text-based series extraction | Available |
| Subprocess runner | Available |
| SQLite + CSV reporting | Available |
| UQPyL adapter | Available |
| APEX template | Planned |
| HBV template | Planned |
| VIC template | Planned |
| HEC-HMS template | Planned |

## Roadmap

### Near term

- improve README and onboarding guidance
- add more complete CLI workflows such as `run` and `expand`
- strengthen tests and cross-platform behavior
- improve example coverage

### Mid term

- formalize extension contracts for templates, readers, writers, and runners
- add more IO protocols beyond fixed-width text
- improve experiment metadata and inspection workflows

### Long term

- support more hydrological model templates
- support more execution backends
- evolve toward a broader experiment management platform

## Project summary

HydroPilot already has a usable orchestration core and a real SWAT integration. The next step is not reinventing the runtime again, but making the framework easier to understand, easier to extend, and easier to adopt.



