# XAJ Template

`version: xaj` is the template for **XAJ** hydrological model projects. It expands a compact XAJ-aware configuration into a standard `version: general` config backed by CSV readers and CSV writers.

## What the template expands into

| Aspect | Template input | Expanded general output |
|---|---|---|
| Writer type | implicit (XAJ knowledge) | `writerType: csv` |
| Reader type | implicit (XAJ knowledge) | `readerType: csv` |
| Parameter locations | variable name + optional RIVID filter | concrete `parameters.csv` row/column positions |
| Series columns | `variable` + optional `rivid` | resolved `colNum` from CSV output headers |
| Row offsets | `headSkip` | added to all `rowRanges` / `rowList` values |

The template expansion happens inside `XajTemplate.build_config()`. The runtime always executes against the expanded `version: general` config. You can inspect the result — HydroPilot writes `<stem>_general.yaml` next to the source YAML after a successful `load_config()` call.

## Project layout

An XAJ project directory must contain:

| File | Purpose |
|---|---|
| `xaj.yaml` | Project descriptor — declares inputs, case settings, and parameter file path |
| `parameters.csv` | Parameter table with a `RIVID` column and parameter value columns |
| `streamflow.csv` | Model output (reach-level streamflow) |
| `Runoff_Yield.csv` | Model output (runoff yield per reach) |
| `ET.csv`, `WD.csv`, `WL.csv` | Optional output files (evapotranspiration, water demand, water level) |

The `xaj.yaml` descriptor is read during project discovery. HydroPilot never modifies it.

## Configuration shape

### `version`

```yaml
version: xaj
```

### `basic`

```yaml
basic:
  projectPath: "../xaj"
  workPath: "./work"
  command: "./pyxaj.exe run xaj.yaml"
```

### `parameters`

Two-layer design, same general pattern:

- `design` — variables the optimizer sees.
- `physical` — how variables map to `parameters.csv` rows and columns.

```yaml
parameters:
  design:
    - name: KC
      bounds: [0.5, 2.0]
    - name: WM
      bounds: [80, 200]

  physical:
    - name: KC
      mode: v
      filter:
        rivid: 60711600
    - name: WM
      mode: v
```

#### RIVID-based parameter filtering

The XAJ template supports a `rivid` filter on physical parameters. When set, the template resolves the parameter to a specific row in `parameters.csv` where the `RIVID` column matches:

```yaml
physical:
  - name: KC
    mode: v
    filter:
      rivid: 60711600       # writes only to the row for RIVID 60711600
```

Without a filter, the parameter writes to all data rows in `parameters.csv`.

The parameter file is expected to be `parameters.csv` unless the `xaj.yaml` descriptor specifies a different path under `inputs.parameters` or `case.parameter`.

### `series`

XAJ series use `variable` names to identify output files and column positions:

```yaml
series:
  - id: flow
    desc: "XAJ outlet streamflow"
    sim:
      variable: Streamflow
      rowRanges:
        - [1, 1000]
    obs:
      file: "../xaj/streamflow.csv"
      rowRanges:
        - [2, 1001]
      colNum: 2
```

Key fields:

| Field | Purpose |
|---|---|
| `sim.variable` | Named output variable (`Streamflow`, `Runoff`, etc.) — resolves to file + column automatically |
| `sim.rivid` | When the output CSV uses RIVID-based column headers, identifies which column to read |
| `sim.file` | Override the auto-resolved output file name |
| `sim.headSkip` | Number of header rows to skip (default depends on variable) |
| `sim.rowRanges` | Row ranges for extraction. When `headSkip` is set, these are shifted automatically |
| `obs.file` | Observation CSV, resolved relative to the config file |
| `obs.rowRanges` | Row ranges, not auto-shifted |

#### Variable-based column resolution

When you write `variable: Streamflow` without a `colNum`, the template:

1. Looks up the variable in the XAJ variable database.
2. Resolves which output file it belongs to (`streamflow.csv`).
3. If the output file uses RIVID-based headers, uses `rivid` to find the correct column.
4. Applies `headSkip` to shift all row positions.

```yaml
# Compact form with auto-resolution
sim:
  variable: Streamflow
  rivid: 60711600
  rowRanges:
    - [1, 1000]

# Is equivalent to writing out the resolved file + colNum explicitly
```

#### Multi-series example

```yaml
series:
  - id: flow
    sim:
      variable: Streamflow
      rowRanges:
        - [1, 1000]
    obs:
      file: "../xaj/streamflow.csv"
      rowRanges:
        - [2, 1001]
      colNum: 2

  - id: runoff
    sim:
      variable: Runoff
      rivid: 60711600
      rowRanges:
        - [1, 1000]
```

You can omit `obs` for a series — the series will carry simulation data only.

### `functions`, `derived`, `objectives`

Same structure as general mode:

```yaml
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

## Project discovery

When the template loads, it reads `xaj.yaml` from the project directory to find the parameter file path. It then scans `parameters.csv` to:

- Index `RIVID` → data row mapping (used by parameter filtering).
- Record all data row indices (used by unfiltered parameters).
- Scan available output CSVs (`streamflow.csv`, `Runoff_Yield.csv`, `ET.csv`, `WD.csv`, `WL.csv`) and cache their headers for column resolution.

## Reference examples

- `examples/test_xaj.yaml` — XAJ single-basin case with `rivid`-filtered parameters, streamflow and runoff series.
- `examples/test_xaj_general.yaml` — The expanded general config produced from `test_xaj.yaml`, showing the resolved CSV writer rows/columns.

## Boundary

- This template works with XAJ model projects that use `xaj.yaml` as a project descriptor and CSV files for parameters and output.
- It doesn't cover non-CSV XAJ workflows.
- The `version: xaj` config key is separate from `version: swat` and `version: general`.

## See also

- [SWAT 2012 Template](swat-2012.md) — the other built-in template.
- [Configuration Reference](../configuration-reference.md) — all general-mode fields.
- [Examples](../examples.md) — full example descriptions.
