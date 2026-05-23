# Configuration Reference

This document describes the `version: general` configuration schema. It is the model-agnostic mode that all template configurations (SWAT 2012, XAJ) expand into at runtime.

## Config loading chain

```text
YAML file
  -> prepare_config()
     -> parse YAML
     -> template expansion (if version != general)
     -> validate_general_config()
     -> RunConfig.from_raw()
  -> PreparedConfig
```

`load_config()` wraps `prepare_config()` and additionally writes a resolved `*_general.yaml` beside the source YAML for inspection.

Validation is two-layer: structural checks run before `RunConfig` construction, then a fallback `RunConfig.from_raw()` call catches remaining issues.

## Top-level structure

A `version: general` YAML file has these top-level keys:

| Key | Required | Type |
|---|---|---|
| `version` | yes | `"general"` |
| `basic` | yes | mapping |
| `parameters` | yes | mapping |
| `series` | yes | non-empty list |
| `functions` | no (default `[]`) | list |
| `derived` | no (default `[]`) | list |
| `objectives` | no (default `[]`) | list |
| `constraints` | no (default `[]`) | list |
| `diagnostics` | no (default `[]`) | list |
| `reporter` | no (default `{}`) | mapping |

## `basic` — project, workspace, and command

```yaml
basic:
  projectPath: E:\BMPs\TxtInOut
  workPath: ./work
  command: swat.exe
  timeout: -1
  parallel: 1
  keepInstances: false
```

| Field | Required | Type | Default | Description |
|---|---|---|---|---|
| `projectPath` | yes | path | — | Directory containing model input files. Copied into each run instance. |
| `workPath` | yes | path | — | Working directory for run instances and archives. |
| `command` | yes | string or list | — | Model executable command. Can be a single string or a list of arguments. |
| `timeout` | no | int | `-1` | Per-run timeout in seconds. `-1` means no timeout. |
| `parallel` | no | int | `1` | Number of parallel worker threads. Each worker gets its own project copy. |
| `keepInstances` | no | bool | `false` | If `true`, per-run instance directories are preserved instead of cleaned up. |

`projectPath` and `workPath` are resolved relative to the configuration file directory.

## `parameters` — design variables and physical mapping

```yaml
parameters:
  design:
    - name: CN2
      type: float
      bounds: [35, 98]
    - name: ALPHA_BF
      type: float
      bounds: [0, 1]
  physical:
    - name: CN2
      type: float
      bounds: [35, 98]
      mode: v
      writerType: fixed_width
      file:
        name: '*.mgt'
        line: 11
        start: 1
        width: 16
        precision: 2
        maxNum: 1
    - name: ALPHA_BF
      type: float
      bounds: [0, 1]
      mode: v
      writerType: fixed_width
      file:
        name: '*.gw'
        line: 5
        start: 1
        width: 16
        precision: 4
        maxNum: 1
  hardBound: true
```

| Field | Required | Type | Default | Description |
|---|---|---|---|---|
| `design` | yes | non-empty list | — | Design variables exposed to the optimizer. |
| `physical` | yes | non-empty list | — | Physical parameters written to model input files. |
| `hardBound` | no | bool | `true` | If `true`, design values are clamped to `bounds` before transformation. |
| `transformer` | no | string or null | `null` | Name of a registered transformer that maps design space to physical space. |

### Design parameters

Each item in `design`:

| Field | Required | Type | Default | Description |
|---|---|---|---|---|
| `name` | yes | string | — | Parameter name. |
| `type` | no | `"float"`, `"int"`, `"discrete"` | `"float"` | Variable type. |
| `bounds` | no | `[lower, upper]` | `[0, 1]` | Allowed range. |
| `sets` | no | list | `[]` | Discrete value set (for `"discrete"` type). |

### Physical parameters

Each item in `physical`:

| Field | Required | Type | Default | Description |
|---|---|---|---|---|
| `name` | yes | string | — | Parameter name. |
| `type` | no | `"float"`, `"int"` | `"float"` | Value type. |
| `bounds` | no | `[lower, upper]` | `[0, 1]` | Allowed range. |
| `mode` | no | `"r"`, `"v"`, `"a"` | `"v"` | Write mode: relative, value, or absolute. |
| `writerType` | no | `"fixed_width"`, `"csv"` | `"fixed_width"` | Writer type. |
| `file` | yes | mapping | — | File target and write location (fields vary by writer). |
| `sets` | no | list | `[]` | Discrete value set. |

If `design` and `physical` lists have different lengths, a `transformer` must be provided.

### Transformer

When specified, `transformer` names a function that accepts the design vector `X` and returns a physical vector `P`. Without a transformer, design and physical values map one-to-one by position.

## `series` — simulation and observation extraction

```yaml
series:
  - id: flow
    desc: Monthly streamflow
    sim:
      readerType: text
      file: output.rch
      rowRanges:
        - [71, 753, 62]
      colSpan: [50, 61]
    obs:
      readerType: text
      file: obs_flow_monthly.txt
      rowRanges:
        - [1, 36]
      colSpan: [1, 12]
```

| Field | Required | Type | Description |
|---|---|---|---|
| `id` | yes | string | Unique series identifier. Used in context keys like `flow.sim` and `flow.obs`. |
| `desc` | no | string | Human-readable description. |
| `sim` | yes | mapping | Simulation extraction: reader or call node. |
| `obs` | no | mapping or null | Observation extraction: reader only. |

### `sim` — simulation data

The `sim` block must declare exactly one of `readerType` or `call`:

**Reader** — extracts data from a model output file:

```yaml
sim:
  readerType: text
  file: output.rch
  rowRanges:
    - [1, 365]
  colNum: 2
```

**Call** — derives simulation data from other series using a function:

```yaml
sim:
  call:
    func: sum_series
    args: [flow.sim, runoff.sim]
```

### `obs` — observation data

The `obs` block accepts only a reader (no `call`):

```yaml
obs:
  readerType: text
  file: obs_flow_monthly.txt
  rowRanges:
    - [1, 36]
  colNum: 1
```

Observation files are resolved relative to the configuration file directory.

### Reader fields

Common to all reader types:

| Field | Required | Type | Description |
|---|---|---|---|
| `readerType` | yes | `"text"` or `"csv"` | Reader type. |
| `file` | yes | path | File to read. For `sim`, resolved relative to the runtime working directory. For `obs`, resolved relative to the config file. |

Additional fields depend on the reader type (see [Reader and writer types](#reader-and-writer-types)).

## `functions` — evaluation functions

```yaml
functions:
  - name: NSE
    kind: builtin
  - name: my_custom
    kind: external
    file: ./my_func.py
```

| Field | Required | Type | Description |
|---|---|---|---|
| `name` | yes | string | Unique function name. |
| `kind` | yes | `"builtin"` or `"external"` | Function source. |
| `args` | no | list of strings | Additional positional arguments passed before derived args. |
| `file` | no | path | Python file path for external functions. Required when `kind: external`. |

Built-in functions do not need a `file`. The current built-in set includes `NSE`, `KGE`, `R2`, `RMSE`, `MSE`, `PBIAS`, `LogNSE`, and `sum_series`.

## `derived` — computed intermediate values

```yaml
derived:
  - id: nse_flow
    call:
      func: NSE
      args: [flow.sim, flow.obs]
```

| Field | Required | Type | Description |
|---|---|---|---|
| `id` | yes | string | Unique derived value identifier. |
| `desc` | no | string | Human-readable description. |
| `call.func` | yes | string | Function name (must match a defined function). |
| `call.args` | yes | list of strings | Arguments, usually context references like `flow.sim`. |

Derived values become available in the runtime context under their `id`. They can be referenced by objectives, constraints, diagnostics, or other derived values.

## `objectives` — optimization targets

```yaml
objectives:
  - id: obj_nse
    desc: Maximize NSE
    ref: nse_flow
    sense: max
```

| Field | Required | Type | Default | Description |
|---|---|---|---|---|
| `id` | yes | string | — | Unique objective identifier. |
| `desc` | no | string | — | Human-readable description. |
| `ref` | yes | string | — | Context reference (usually a derived value `id`). |
| `sense` | no | `"min"` or `"max"` | `"min"` | Optimization direction. |
| `on_error` | no | float | auto | Fallback value on error (see error semantics). |

Default `on_error`: `-inf` for `sense: max`, `+inf` for `sense: min`.

## `constraints` — evaluation constraints

```yaml
constraints:
  - id: con_volume
    ref: vol_ratio
```

| Field | Required | Type | Default | Description |
|---|---|---|---|---|
| `id` | yes | string | — | Unique constraint identifier. |
| `desc` | no | string | — | Human-readable description. |
| `ref` | yes | string | — | Context reference. |
| `on_error` | no | float | `+inf` | Fallback value on error. |

## `diagnostics` — informational metrics

```yaml
diagnostics:
  - id: diag_rmse
    name: RMSE diagnostic
    ref: rmse_flow
```

| Field | Required | Type | Default | Description |
|---|---|---|---|---|
| `id` | yes | string | — | Unique diagnostic identifier. |
| `name` | no | string | — | Display name. |
| `ref` | yes | string | — | Context reference. |
| `on_error` | no | float | `NaN` | Fallback value on error. |

Diagnostics are warning-oriented. A failed diagnostic does not invalidate the run.

## `reporter` — output persistence

```yaml
reporter:
  flushInterval: 50
  holdingPenLimit: 20
  series: []
```

| Field | Required | Type | Default | Description |
|---|---|---|---|---|
| `flushInterval` | no | int | `50` | Flush records to disk every N runs. |
| `holdingPenLimit` | no | int | `20` | Max records held before forced flush. |
| `series` | no | list of strings | `[]` | Series `id` values to export as per-run CSV files. |

Output artifacts in `archive/`:

- `results.db` — SQLite database with all run records
- `summary.csv` — CSV summary of objectives and constraints
- `error.jsonl` — structured error entries
- `error.log` — plain-text error log
- Per-series CSV files for each `id` listed in `reporter.series`

## Path semantics

### Configuration file resolution

- `basic.projectPath` — resolved relative to the config file directory. Must be an existing directory.
- `basic.workPath` — resolved relative to the config file directory.

### Observation files

`obs.file` is resolved relative to the **configuration file directory**. Example:

```yaml
# config.yaml is at ./project/config.yaml
# obs file is at ./project/obs_flow.txt
obs:
  file: obs_flow.txt
```

### Simulation output files

`sim.file` is resolved relative to the **runtime working directory** (the project copy inside the run instance). The model produces output files inside its working copy, so paths should be relative to that location:

```yaml
sim:
  file: output.rch
```

Do not use a path relative to the YAML file location for `sim.file`.

## Error and on_error semantics

### Error types

Runtime errors use two severity levels:

- `fatal` — the run cannot produce a valid result. Fallback values are applied.
- `warning` — the error is recorded but the run continues.

### Derived value dependencies

A derived value that is referenced by an objective or constraint is a **fatal** dependency. If it fails, the run gets fallback values.

A derived value referenced only by diagnostics is a **warning** dependency. Failure produces a warning and `NaN` without invalidating the run.

### Default fallback values

| Block | Direction | Default `on_error` |
|---|---|---|
| Objective | `sense: min` | `+inf` |
| Objective | `sense: max` | `-inf` |
| Constraint | — | `+inf` |
| Diagnostic | — | `NaN` |

All fallback values can be overridden with an explicit `on_error` field.

## Reader and writer types

### Readers

| Type | Description |
|---|---|
| `text` | Fixed-width or space-delimited text files. Supports `rowRanges`, `rowList`, `colSpan`, `colNum`. |
| `csv` | CSV files. Supports `rowRanges`, `rowList`, `colNum`, `delimiter`. |

**Text reader fields:**

| Field | Required | Description |
|---|---|---|
| `file` | yes | File path. |
| `rowRanges` or `rowList` | yes* | Row selection. |
| `colSpan` or `colNum` | yes* | Column selection. |

\* Exactly one row selector and exactly one column selector must be provided.

`rowRanges` format: `[start, end]` or `[start, end, step]`. 1-based, inclusive.

### Writers

| Type | Description |
|---|---|
| `fixed_width` | Write values into fixed-width positions in text files. Supports glob patterns in `file.name`. |
| `csv` | Write values into CSV cells. |

**Fixed-width writer `file` fields:**

| Field | Required | Description |
|---|---|---|
| `name` | yes | Target file name or glob pattern. |
| `line` | yes | Line number (1-based). |
| `start` | yes | Column start position (1-based). |
| `width` | yes | Field width in characters. |
| `precision` | no | Decimal places for float formatting. |
| `maxNum` | no | Number of sequential fields to scan from `start`. |
| `selectIndex` | no | When `maxNum` is set, pick only the Nth scanned entry (1-based). Omitted `selectIndex` writes all scanned entries. |

**CSV writer `file` fields:**

| Field | Required | Description |
|---|---|---|
| `name` | yes | Target file name. |
| `rowList` or `rowRanges` | yes | Row selection. |
| `colNum` | yes | Column number (1-based). |
| `delimiter` | no | Field delimiter (default `,`). |
| `precision` | no | Decimal places for float formatting. |

## Context references

The runtime context uses dot-separated keys:

- `X` — the input design vector
- `i` — the run index within a batch
- `P` — the resolved physical parameter vector
- `<series_id>.sim` — extracted simulation data (e.g. `flow.sim`)
- `<series_id>.obs` — loaded observation data (e.g. `flow.obs`)
- `<derived_id>` — computed derived value (e.g. `nse_flow`)

These keys are used in `call.args`, `derived.call.args`, and `ref` fields.

## Minimal example

```yaml
version: general

basic:
  projectPath: ./project
  workPath: ./work
  command: my_model.exe

parameters:
  design:
    - name: K
      bounds: [0, 1]
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
      file: model.out
      rowRanges:
        - [1, 365]
      colNum: 2
    obs:
      readerType: text
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
  - id: obj_nse
    ref: nse_flow
    sense: max
```
