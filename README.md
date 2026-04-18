[English](./README.md) | [简体中文](./README.zh-CN.md)

# HydroPilot

> A declarative orchestration framework for hydrological model calibration, evaluation, and optimization.

HydroPilot is a model-agnostic framework for running hydrological modeling workflows through configuration rather than project-specific glue scripts. It abstracts parameter mapping, input writing, model execution, result extraction, metric evaluation, objective calculation, and run reporting into one unified pipeline.

HydroPilot is the **project name**.

## What HydroPilot is

HydroPilot is:

- a **general orchestration framework** for hydrological model experiments
- a **configuration-first workflow** built around YAML
- a **plugin-oriented architecture** for model templates, parameter writers, result readers, runners, and evaluators
- a framework intended to support **multiple hydrological models**, not just one model family

## What HydroPilot is not

HydroPilot is **not**:

- a SWAT-only parameter editing script collection
- a single hard-coded workflow tied to one model’s file structure
- an optimizer by itself
- a finished platform with every model integration already implemented

SWAT is currently the **most mature built-in template** and the **first fully implemented template** in the repository, but the framework itself is designed to be broader than SWAT.

## Why configuration instead of scripts?

In many calibration projects, most of the maintenance burden is not the optimization algorithm itself, but the surrounding scripting work:

- writing parameters into multiple input files
- launching the external model safely for repeated runs
- parsing model outputs into comparable series
- computing metrics, objectives, constraints, and diagnostics
- storing runs in a reproducible way

HydroPilot moves that repeated logic into a reusable architecture so that a calibration workflow becomes mostly a **configuration task** instead of a new scripting task for every project.

## Core concepts

### 1. General mode vs template mode

HydroPilot currently supports two entry styles:

- **General mode**: `version: general`
  - You define the workflow explicitly using the generic schema.
  - This is the model-agnostic core of the framework.
- **Template mode**: for example `version: swat`
  - A model template expands a simplified configuration into a standard general configuration.

This separation is important: HydroPilot is not defined by SWAT templates. Templates are just one way to make specific models easier to use.

### 2. Design space vs physical space

HydroPilot uses a two-layer parameter architecture:

- **design parameters**: the variables seen by the optimizer
- **physical parameters**: the values ultimately written into model input files

A transformer connects the two spaces. This makes it possible to support one-to-one mappings, one-to-many mappings, grouped mappings, or custom transformations.

### 3. Series, derived values, objectives, and diagnostics

The evaluation pipeline is structured as:

- **series**: extracted or computed simulation/observation series
- **derived**: values computed from series or previous results
- **objectives**: values exposed to the optimizer
- **constraints**: optional feasibility terms
- **diagnostics**: values recorded for analysis but not optimized directly

## Current repository status

This repository already contains the core orchestration pipeline:

- configuration loading and validation
- parameter transformation and writing
- subprocess-based model execution
- text-based series extraction
- derived/objective/constraint evaluation
- run reporting to SQLite and CSV
- a UQPyL adapter for optimization workflows

At the current code state:

- **general configuration mode** is available
- **SWAT template mode** is available
- **SWAT is the only registered built-in template**
- other model templates such as **APEX / HBV / VIC / HEC-HMS** should be described as **planned**, not already implemented

## Quick start

### General mode

General mode is the model-agnostic core schema. It is the right entry point when you want to wire a custom model manually.

A minimal illustrative configuration looks like this:

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
      file:
        name: model.inp
        line: 12
        start: 1
        width: 10
        precision: 4

series:
  - id: flow
    sim:
      file: model.out
      rowRanges:
        - [1, 365]
      colNum: 2
    obs:
      file: obs_flow.txt
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
  items:
    - id: obj_nse
      ref: nse_flow
      sense: max
```

You can evaluate a batch of parameter vectors directly with `SimModel`:

```python
import numpy as np
from model_driver.sim_model import SimModel

X = np.array([
    [0.5],
])

with SimModel("path/to/general.yaml") as model:
    result = model.evaluate(X)
    print(result["objs"])
```

Notes:

- The example above is meant to show the generic schema.
- In the current repository, the most complete ready-made examples are still the SWAT-based examples under `examples/`.

### Template mode

Template mode is for model-specific integrations. In the current repository, the built-in template is `swat`.

A real example already included in the repository is:

```yaml
version: "swat"

basic:
  projectPath: "E:\\DJBasin\\TxtInOutFSB"
  workPath: "./work"
  command: "swat.exe"

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
    desc: "Daily streamflow at outlet"
    sim:
      file: output.rch
      subbasin: 33
      period: [2010, 2015]
      timestep: daily
      colSpan: [50, 61]
    obs:
      file: obs_flow.txt
      rowRanges:
        - [1, 2191]
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
  items:
    - id: obj_nse
      desc: "Maximize NSE"
      ref: nse_flow
      sense: max
```

To run an optimization workflow with UQPyL:

```python
from model_driver.wrappers import UQPyLAdapter
from UQPyL.optimization import DE

with UQPyLAdapter("examples/test_daily.yaml") as problem:
    optimizer = DE(problem)
    optimizer.run()
```

## Built-in functions currently available

HydroPilot currently includes these built-in functions in the codebase:

- `NSE`
- `KGE`
- `R2`
- `RMSE`
- `MSE`
- `PBIAS`
- `LogNSE`
- `sum_series`

External Python functions are also supported through the function registry.

## Current support matrix

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

## Architecture

```text
Config Loading
  -> Parameter Writing
  -> Model Execution
  -> Result Extraction
  -> Metric / Objective Evaluation
  -> Result Recording
```

```text
SimModel
  └─ ModelAdapter
      ├─ ParamManager
      │   └─ Transformer
      │   └─ ParamWriter
      ├─ ModelRunner
      ├─ SeriesExtractor
      │   └─ SeriesReader
      ├─ Evaluator
      │   └─ FunctionManager
      └─ RunReporter
```

The main architectural idea is simple:

- keep the core pipeline stable
- push model-specific details to templates and plugins
- separate optimization-space variables from file-space parameters
- make workflows reproducible and inspectable

## Outputs and run records

Each run creates an isolated working area and a backup folder that can contain:

- the original configuration file
- the resolved general configuration generated by template expansion
- copied observation files when applicable
- `summary.csv`
- `results.db`
- `error.jsonl`
- `error.log`

This gives HydroPilot a basic but useful experiment trail for debugging and comparison.

## Installation status

HydroPilot is currently **source-layout first** in this repository.

That means:

- the project name is **HydroPilot**
- the current package name is still **`model_driver`**
- a formal packaging flow (`pyproject.toml`, install extras, release metadata) should be treated as a near-term roadmap item

At minimum, the current codebase expects an environment with packages such as:

- `numpy`
- `PyYAML`
- `pydantic`

For optimization workflows, `UQPyL` is also needed.

## Roadmap

### Near term

- unify branding around **HydroPilot**
- align documentation with the current code API
- add packaging metadata and installation guidance
- improve example coverage for both general mode and template mode
- add CLI entry points such as `validate`, `run`, and `expand`

### Mid term

- add more model templates
- add more readers and writers beyond fixed-width text
- strengthen tests and schema documentation
- improve result inspection and experiment metadata

### Long term

- evolve toward a broader multi-model hydrological experimentation platform
- support more execution backends
- add richer experiment management and visualization tooling

## Project status

HydroPilot should currently be understood as:

> a strong framework prototype for hydrological model orchestration, with a general core already in place and SWAT as the first fully implemented template.

It is already useful as a research and engineering foundation, but it is still moving toward a more complete public release state.
