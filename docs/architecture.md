# Architecture

This document describes the architecture that exists in the current HydroPilot codebase. It is intentionally implementation-oriented: the goal is to explain the real execution path in `src/hydro_pilot`, not an idealized future design.

## Overview

HydroPilot has two major chains:

```text
Config chain
  YAML config
    -> validation and template expansion
    -> RunConfig
```

```text
Runtime chain
  SimModel
    -> Session
    -> Workspace
    -> Executor
    -> ExecutionServices
    -> RunReporter
```

These chains are related but not identical.

- The config chain turns a user YAML file into a validated `RunConfig`.
- The runtime chain uses that `RunConfig` to execute model runs, extract outputs, evaluate metrics, and persist results.
- The CLI validator uses the config chain only.
- `SimModel` uses both the config chain and the runtime chain.

## Main Components

The main runtime-facing modules are:

```text
src/hydro_pilot/
  api/           public entry points such as SimModel
  cli/           command-line interfaces
  config/        config loading, path resolution, schema conversion
  evaluation/    derived values, objectives, constraints, diagnostics
  io/            model runners, file readers, file writers
  models/        template registry and model-specific template logic
  params/        parameter space and parameter application
  reporting/     run persistence and output artifacts
  runtime/       session, workspace, executor, runtime context
  series/        simulation/observation extraction planning
  validation/    user-facing config diagnostics
```

## Config Chain

The config chain starts from a YAML file and ends with a `RunConfig`.

```text
YAML
  -> prepare_config()
  -> optional template expansion
  -> general validation
  -> RunConfig.from_raw()
  -> load_config()
```

### 1. Raw YAML loading

`config.loader.prepare_config()` is the shared core entry point for configuration preparation.

Its responsibilities are:

- resolve the config file path
- parse YAML into a Python mapping
- read `version`
- expand template configs when `version != general`
- run validation on the expanded config
- build the final `RunConfig`

If any of these steps fail, it raises `ConfigPreparationError` with translated diagnostics.

### 2. Template expansion

HydroPilot supports a general mode and template modes.

- `version: general` means the YAML already describes the runtime config directly.
- Other versions such as `version: swat` are resolved through the template registry in `models.registry`.

The flow is:

```text
version != general
  -> get_template(version)
  -> template.build_config(raw, base_path)
  -> expanded general config
```

Important behavior:

- template-specific validation can run before expansion
- the runtime always executes against the expanded general config
- when `load_config()` succeeds, HydroPilot writes `<source_stem>_general.yaml` beside the source YAML for inspection; template configs are expanded, and general configs are written with runtime defaults filled in

That last step happens during `load_config()`, not during CLI validation.

### 3. Validation

HydroPilot has two validation layers.

`validation.entry.validate_config()` is the user-facing validation entry point. It calls `prepare_config()` and converts exceptions into a list of diagnostics suitable for CLI output.

`validation.general.validate_general_config()` is the structural and semantic validator for general configs. It checks areas such as:

- required `basic` fields
- parameter definitions
- writer specs
- series extraction specs
- function file existence

There is also template-specific validation, such as SWAT validation before template expansion.

### 4. Direct runtime loading

The public Python API does not call the CLI validator. It calls `load_config()`.

```text
SimModel(...)
  -> load_config(...)
  -> prepare_config(...)
  -> RunConfig
```

This means:

- the underlying validation and config preparation logic is reused
- CLI-specific behavior is not reused
- direct runtime loading raises errors instead of printing diagnostics and returning an exit code

## CLI Validation Chain

The current CLI command is a thin wrapper around the validation entry point.

```text
hydropilot-validate
  -> hydro_pilot.cli.validate.main()
  -> validate_config()
  -> prepare_config()
```

Its responsibilities are limited to:

- parse the config path argument
- run validation
- print diagnostics
- return exit code `1` when errors are present, otherwise `0`

The CLI does not create a `Session`, `Workspace`, or `Executor`. It validates configuration only.

## Runtime Chain

The public runtime path starts from `SimModel`.

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

### 1. SimModel

`api.sim_model.SimModel` is the main public API object.

It:

- loads the config
- creates a `Session`
- exposes runtime metadata such as input bounds and output counts
- delegates evaluation to `Session.evaluate()`

`SimModel` is a thin API facade, not the orchestration layer.

### 2. Session

`runtime.session.Session` owns the runtime lifecycle for one loaded config.

It creates:

- a `Workspace`
- an `Executor`
- a `RunReporter`

It also:

- wires the reporter into the executor
- provides `evaluate()`
- handles cleanup on normal close, process exit, and some signals

This makes `Session` the lifecycle boundary for one working runtime instance.
By default, `Session.close()` removes `instance_*` directories and keeps the run `archive/`.
Set `basic.keepInstances: true` to preserve instance directories for debugging.

### 3. Workspace

`runtime.workspace.Workspace` creates an isolated run directory under:

```text
<workPath>/tempRun/<timestamp>/
```

Inside that run directory it:

- creates one `instance_<n>` directory per parallel worker
- copies the configured `projectPath` into each instance directory
- creates an `archive/` directory
- copies the original config into `archive/`
- copies the resolved `_general.yaml` into `archive/` when that file exists
- copies configured observation files into `archive/` when available

Instance directories are temporary by default. They are preserved only when
`basic.keepInstances` is enabled.

The workspace also manages instance acquisition and release through a queue, so the executor can safely reuse prepared model copies.

### 4. ExecutionServices

`runtime.services.ExecutionServices` builds the concrete service graph from `RunConfig`.

It assembles:

- `FunctionManager`
- `ParamSpace`
- `ParamWritePlan`
- `ParamApplier`
- `SeriesPlan`
- `ObsStore`
- `SubprocessRunner`
- `SeriesExtractor`
- `Evaluator`

This is the internal dependency bundle used by `Executor`.

### 5. Executor

`runtime.executor.Executor` is the main orchestration component for evaluation.

Its responsibilities are:

- accept a batch of input vectors `X`
- execute runs sequentially or in parallel depending on `cfg.basic.parallel`
- collect objective and constraint outputs into arrays
- apply penalties when required outputs are missing
- submit run records to the reporter

The core per-run flow in `_run_one()` is:

```text
Acquire workspace instance
  -> apply parameters
  -> run external model command
  -> extract series
  -> evaluate derived values / objectives / constraints / diagnostics
  -> release workspace instance
  -> apply on-error defaults if needed
  -> submit record to reporter
```

### 6. Param application

Parameter handling is split into distinct parts:

- `ParamSpace` exposes optimization-facing parameter metadata such as bounds
- `ParamWritePlan` resolves how physical parameters should be written
- `ParamApplier` maps input vectors into physical values and writes them into model files

This separation keeps the optimization-facing parameter space distinct from file-writing details.

### 7. Model execution

HydroPilot currently runs the external model through `SubprocessRunner`.

At this layer, HydroPilot does not simulate the model itself. It:

- prepares an isolated working copy
- executes the configured command in that working copy
- expects downstream extraction to read model outputs from files

### 8. Series extraction

Series handling is organized around:

- `SeriesPlan` for extraction planning
- `ObsStore` for observation loading/reuse
- `SeriesExtractor` for simulation and observation retrieval

The extractor updates the runtime context with data series that later steps can reference.

### 9. Evaluation

`evaluation.evaluator.Evaluator` consumes the runtime context and produces:

- derived values
- objectives
- constraints
- diagnostics

Important behavior:

- derived values required by objectives or constraints are treated as fatal dependencies
- derived values used only by diagnostics can fail as warnings
- diagnostics are warning-oriented and fall back to configured `on_error` values

This allows HydroPilot to distinguish between failures that invalidate the run and failures that should merely be recorded.

## Runtime Context and Error Handling

Each run is represented internally by a mutable context dictionary.

The context is initialized with values such as:

- the input vector `X`
- the run index `i`
- the batch id
- a warnings list

As the run proceeds, the context is enriched with:

- physical parameter values
- extracted series
- derived values
- objective, constraint, and diagnostic scalars
- warning or fatal error objects

HydroPilot uses `runtime.errors.RunError` for domain-level runtime failures.

The executor distinguishes between:

- expected runtime failures represented as `RunError`
- unexpected Python exceptions, which are wrapped into a fatal `RunError`

If a run ends with an error:

- the workspace instance is still released
- configured `on_error` defaults are applied to objectives, constraints, and diagnostics
- the run record is still submitted to the reporter when possible

This design favors batch robustness: one failed run should not necessarily prevent recording or completing the rest of the batch.

## Reporting and Persistence

`reporting.reporter.RunReporter` persists run artifacts asynchronously on a background thread.

By default it writes into the run `archive/` directory:

- `results.db`
- `summary.csv`
- `error.jsonl`
- `error.log`
- per-series CSV files for configured output series

The reporter accepts runtime records from the executor and flushes them in batches.

Key properties of this design:

- model execution is decoupled from disk persistence
- failed runs can still be recorded
- results are available in both SQLite and flat-file forms

The reporter is designed to preserve ordering within a batch even when execution is parallel.

## Parallel Execution Model

HydroPilot parallelizes at the run level.

- `cfg.basic.parallel` controls the number of worker threads used by the executor
- the workspace pre-creates the same number of isolated project copies
- each run acquires one prepared instance directory, executes there, then releases it back to the queue

This avoids multiple workers writing into the same model project directory.

The current concurrency model is therefore:

```text
Parallel threads
  -> isolated instance directories
  -> one external model process per active run
  -> one asynchronous reporter thread
```

## Extension Points

The current architecture has several explicit extension seams.

### Templates

New model families can plug in through `ModelTemplate` and the template registry.

A template is responsible for converting a model-specific config shape into a standard general config.

### Writers and readers

Parameter writers and series readers are resolved by type.

This allows HydroPilot to support new file formats without changing the top-level runtime chain.

### Functions

Derived values and evaluations use `FunctionManager`, which supports built-in and external functions.

This keeps objective logic outside the executor and makes function extension mostly declarative.

### Runners

The runtime currently uses `SubprocessRunner`, but the runner abstraction leaves room for alternative execution backends later.

## Design Intent

At a high level, the architecture separates concerns in four layers:

- config preparation turns YAML into validated runtime data
- orchestration coordinates run lifecycle and batching
- services perform concrete work such as writing, running, reading, and evaluating
- reporting persists artifacts and diagnostics

That separation is what allows HydroPilot to support both:

- a lightweight validation-only CLI
- a reusable Python runtime for repeated model evaluation

## Practical Reading Guide

If you are new to the codebase, read the modules in this order:

1. `src/hydro_pilot/api/sim_model.py`
2. `src/hydro_pilot/config/loader.py`
3. `src/hydro_pilot/runtime/session.py`
4. `src/hydro_pilot/runtime/executor.py`
5. `src/hydro_pilot/runtime/services.py`
6. `src/hydro_pilot/reporting/reporter.py`

If you are debugging config issues, start here instead:

1. `src/hydro_pilot/validation/entry.py`
2. `src/hydro_pilot/validation/general.py`
3. `src/hydro_pilot/config/loader.py`
4. `src/hydro_pilot/models/swat/validate.py`
