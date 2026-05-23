# SWAT 2012 Parameters and Series — Decision Guide

This guide helps you make practical SWAT 2012 configuration decisions after your first daily run succeeds. It covers output file selection, variable expression, period and timestep choices, parameter writing strategies, and HRU filtering. Use it alongside the [SWAT 2012 template reference](../templates/swat-2012.md) and the [configuration reference](../configuration-reference.md).

## 1. Choosing the output file

SWAT 2012 produces three output files HydroPilot reads from. Pick the one that matches the spatial scale you want to evaluate.

### `output.rch` — reach-level

Each row is one reach (subbasin outlet) per timestep. `sim.id` is the subbasin ID.

```yaml
series:
  - id: flow
    sim:
      file: output.rch
      id: 62               # subbasin 62
      period: [2019, 2021]
      timestep: monthly
      variable: FLOW_OUT
```

**When to use:** streamflow calibration at subbasin outlets. This is the most common choice.

### `output.sub` — subbasin-level

Each row is one subbasin per timestep. `sim.id` is the subbasin ID. Contains subbasin-aggregated variables (water yield, sediment, nutrient loads).

```yaml
sim:
  file: output.sub
  id: 1
  period: [2010, 2015]
  timestep: yearly
  variable: WYLD
```

**When to use:** subbasin-aggregated variables like water yield or sediment load.

### `output.hru` — HRU-level

Each row is one HRU per timestep. `sim.id` is the **global** HRU index (1-based, counted across all subbasins sequentially). It's not the local HRU number within a subbasin.

```yaml
sim:
  file: output.hru
  id: 15               # global HRU index
  period: [2010, 2015]
  timestep: monthly
  colSpan: [5, 16]
```

**When to use:** HRU-level variables (ET, soil water, percolation). Verify the global HRU index from your project's subbasin layout — subbasin 1 HRUs come first, then subbasin 2, etc.

### Quick comparison

| Output file | `sim.id` meaning | Typical use |
|---|---|---|
| `output.rch` | Subbasin ID (1-based) | Streamflow at outlets |
| `output.sub` | Subbasin ID (1-based) | Subbasin-level water/sediment/nutrient |
| `output.hru` | Global HRU index (1-based) | HRU-level soil/ET variables |

## 2. Choosing the variable expression

You can identify SWAT output columns in two ways.

### `variable` — name-based lookup

```yaml
sim:
  file: output.rch
  id: 62
  period: [2019, 2021]
  timestep: monthly
  variable: FLOW_OUT
```

The template resolves `FLOW_OUT` to the correct `colSpan` from the SWAT variable database (`swat_db.yaml`). This is the preferred approach — you don't need to memorize SWAT output column positions.

Available variables per file:

| File | Common variables |
|---|---|
| `output.rch` | `FLOW_IN`, `FLOW_OUT`, `SED_OUT`, `ORGN_OUT`, `ORGP_OUT`, `NO3_OUT`, `NH4_OUT`, `NO2_OUT`, `TN_OUT`, `TP_OUT` |
| `output.sub` | `PREC`, `SNOMELT`, `PET`, `ET`, `SW`, `PERC`, `SURQ`, `GW_Q`, `WYLD`, `SYLD`, `ORGN`, `ORGP`, `NSURQ`, `SOLP`, `SEDP` |
| `output.hru` | `PREC`, `SNOMELT`, `PET`, `ET`, `SW_INIT`, `SW_END`, `PERC`, `GW_RCHG`, `SURQ_GEN`, `GW_Q`, `WYLD`, `SYLD`, `ORGN`, `ORGP` |

### `colSpan` — explicit column range

```yaml
sim:
  file: output.rch
  id: 62
  period: [2019, 2021]
  timestep: monthly
  colSpan: [50, 61]
```

**Use `colSpan` when:**
- You know the exact column positions and want them locked in.
- You're reading a variable that isn't in the SWAT database.
- You're debugging and want to bypass auto-resolution.

**Use `variable` when:**
- You want the template to resolve column positions for you.
- You're writing a reusable config that other SWAT 2012 projects can adapt.
- `colSpan` would vary between SWAT output configurations (IPRINT, ICALEN) and you want the template to handle that.

In most cases, start with `variable`. Switch to explicit `colSpan` when you need precise control or the variable is not in the database.

## 3. Understanding `period` and `timestep`

### `timestep`

Must match the SWAT project's IPRINT setting (read from `file.cio` during project discovery):

| IPRINT value | `timestep` | Rows per subbasin per year |
|---|---|---|
| 0 | `monthly` | 12 (months 1–12; yearly-average row MON=13 is skipped) |
| 1 | `daily` | 365 or 366 |
| 2 | `yearly` | 1 |

The template auto-detects the project timestep. Use the `timestep` field to override when extracting a series at a different frequency than the project default (rare).

### `period`

The time window for extraction. Formats, from simplest to most precise:

```yaml
# Year-only — most common
period: [2019, 2021]

# Month-precision
period: ["2019-06", "2021-09"]

# Day-precision
period: ["2019-02-03", "2021-11-01"]

# Multi-segment — non-contiguous windows
period: [[2019, 2019], [2021, 2021]]
```

**Decision rules:**
- Use year-only unless you need to trim partial years.
- Use month-precision to avoid partial-season data at the edges.
- Multi-segment is useful for split-sample calibration (calibrate on one period, validate on another from the same project).
- Period is clipped to the project's output window (NYSKIP respected).

### Period and `rowRanges`

The template calculates `rowRanges` from `id`, `period`, and `timestep`. In general-mode configs these ranges are explicit. For monthly output, `rowRanges` uses multi-segment format with step = n_subbasins:

```yaml
# Monthly output, 62 subbasins
rowRanges:
  - [71, 753, 62]    # months 1-11 per year, skipping MON=13
```

In template mode you rarely need to write these by hand — the SWAT template calculates them.

## 4. Parameter writing strategy

HydroPilot's parameter system has two layers: **design** (what the optimizer sees) and **physical** (what gets written to files). Choose your strategy based on how parameters relate to your model's spatial structure.

### Strategy A: Global parameters (no filter)

Every HRU or reach gets the same value. Simplest case.

```yaml
parameters:
  design:
    - name: CN2
      bounds: [35, 98]
    - name: ALPHA_BF
      bounds: [0, 1]
    - name: GW_DELAY
      bounds: [0, 500]

  physical:
    - name: CN2
      mode: v
    - name: ALPHA_BF
      mode: v
    - name: GW_DELAY
      mode: v
```

`mode: v` means the value is written directly (no relative change, no absolute offset). This is the default and most common mode.

**When to use:** uniform parameters across the entire watershed. One design variable = one physical parameter in every matching file.

### Strategy B: HRU-filtered parameters

Different HRU groups get independently calibrated values.

```yaml
parameters:
  design:
    - name: CN2_AGRL
      bounds: [35, 98]
    - name: CN2_FRST
      bounds: [30, 90]
    - name: ALPHA_BF
      bounds: [0, 1]

  physical:
    - name: CN2_AGRL
      mode: v
      filter:
        land_use: AGRL
    - name: CN2_FRST
      mode: v
      filter:
        land_use: FRST
    - name: ALPHA_BF
      mode: v
```

Each physical parameter with a filter only writes to HRUs matching that filter. `ALPHA_BF` (no filter) writes to all HRUs.

**When to use:** when different land uses, soil types, or slope classes need independent calibration. Each gets its own design variable and optimizer degree of freedom.

### Strategy C: Transformer (many-to-many mapping)

When the optimizer should tune fewer variables than the number of physical parameters, or when design values need a transformation before writing.

```yaml
parameters:
  design:
    - name: CN2_factor      # optimizer tunes one factor
      bounds: [-0.2, 0.2]
    - name: ESCO_val
      bounds: [0.1, 0.9]
    - name: GW_DELAY_val
      bounds: [0, 500]
    - name: SURLAG_val
      bounds: [0.5, 24]

  physical:
    - name: CN2_AGRL
      mode: v
      filter:
        land_use: AGRL
    - name: CN2_URHD
      mode: v
      filter:
        land_use: URHD
    - name: ESCO_1_30
      mode: v
    - name: ESCO_31_62
      mode: v
    - name: GW_DELAY
      mode: v
    - name: SURLAG
      mode: v

  transformer: monthly_transform
```

The transformer function (declared in `functions` as `kind: external`) receives the design vector `X` and returns the physical vector `P`:

```yaml
functions:
  - name: monthly_transform
    kind: external
    file: monthly_transform.py
```

In this example, 4 design parameters map to 6 physical parameters via the transformer. The optimizer only sees 4 dimensions.

**When to use:**
- Spatial regularization (one factor → many HRU groups with calibrated offsets).
- Non-linear transformations between optimizer space and physical space.
- Fewer design variables than physical targets.

### Strategy D: Discrete parameters

```yaml
design:
  - name: landuse_code
    type: discrete
    bounds: [1, 3]
    sets: [1, 2, 3]
```

Discrete variables map to `varType=2` in UQPyL, with `sets` as candidate values.

**When to use:** categorical choices (land-use scenarios, management options). Values must be numeric.

### Strategy summary

| Strategy | Design → Physical | Filter | When |
|---|---|---|---|
| Global | 1:1 | none | Uniform parameters |
| HRU-filtered | 1:1 per group | `filter` on each physical | Spatial variation |
| Transformer | M:N via function | optional | Regularization, non-linear transforms |
| Discrete | categorical sets | optional | Land-use/management scenarios |

## 5. HRU filters

Filters determine which HRU files a physical parameter writes to. A parameter entry without a filter writes to all HRUs.

### Filter fields

```yaml
filter:
  subbasin: [1, 3, 5]       # subbasin IDs
  land_use: AGRL             # land-use code from .hru header
  soil: "Haplic Luvisols"    # soil name from .hru header
  slope: "30-45"             # slope class from .hru header
  not:
    slope: "0-5"             # excluded slope class
```

| Field | Type | Matches |
|---|---|---|
| `subbasin` | int or list | Subbasin IDs |
| `land_use` | string or list | Luse field from `.hru` header |
| `soil` | string or list | Soil field from `.hru` header |
| `slope` | string or list | Slope field from `.hru` header |
| `not` | sub-filter | Exclusion block |

### AND/OR logic

- **Same field, multiple values → OR.** `subbasin: [1, 3, 5]` matches subbasin 1, 3, or 5.
- **Different fields → AND.** `land_use: AGRL` with `soil: "Haplic Luvisols"` matches only HRUs that are both AGRL and on Haplic Luvisols.
- **`not` block → exclusion.** `not: {slope: "0-5"}` removes flat-slope HRUs from the match set.

```yaml
# Matches HRUs that are:
#   - in subbasins 1 through 30
#   - AND have land_use AGRL or FRST
#   - AND do NOT have slope "0-5"
filter:
  subbasin: [1, 30]          # actually a range is not supported — use explicit list
  land_use: [AGRL, FRST]     # AGRL OR FRST
  not:
    slope: "0-5"             # exclude flat slopes
```

Note: `subbasin` does not support range syntax. List subbasin IDs explicitly: `[1, 2, 3, ..., 30]`.

### File expansion

HRU-filtered parameters with `*.mgt` or `*.hru` file patterns are expanded to concrete filenames during template expansion. Each matched HRU's file is written independently:

```text
Filter matches HRU 1 (subbasin 1, AGRL) → writes to 000010001.mgt
Filter matches HRU 3 (subbasin 1, FRST) → writes to 000010003.mgt
```

Global files like `basins.bsn` are never expanded — the pattern is kept as-is.

## 6. Example patterns

### Simplest global parameter case

Three parameters, one series, one objective. No filters, no transformers. This is what a first SWAT 2012 daily run looks like:

```yaml
version: swat

basic:
  projectPath: ./TxtInOut
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
  physical:
    - name: CN2
      mode: v
    - name: ALPHA_BF
      mode: v
    - name: GW_DELAY
      mode: v

series:
  - id: flow
    sim:
      file: output.rch
      id: 33
      period: [2010, 2015]
      variable: FLOW_OUT
    obs:
      file: obs_flow.txt
      rowRanges:
        - [1, 2190]
      colNum: 1

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

Reference: `examples/test_daily.yaml`.

### HRU-filtered case

Split CN2 calibration by land use, keep ALPHA_BF and GW_DELAY global:

```yaml
parameters:
  design:
    - name: CN2_AGRL
      bounds: [35, 98]
    - name: CN2_FRST
      bounds: [30, 90]
    - name: CN2_URHD
      bounds: [40, 95]
    - name: ALPHA_BF
      bounds: [0, 1]
    - name: GW_DELAY
      bounds: [0, 500]

  physical:
    - name: CN2_AGRL
      mode: v
      filter:
        land_use: AGRL
    - name: CN2_FRST
      mode: v
      filter:
        land_use: FRST
    - name: CN2_URHD
      mode: v
      filter:
        land_use: URHD
    - name: ALPHA_BF
      mode: v
    - name: GW_DELAY
      mode: v
      filter:
        subbasin: [1, 2, 3, 4, 5]
    - name: GW_DELAY
      mode: v
      filter:
        subbasin: [6, 7, 8, 9, 10]
```

Each CN2 variant is an independent design variable. GW_DELAY is split into two regions (subbasins 1–5 and 6–10), each calibrated separately.

Reference: `examples/test_monthly_complex.yaml` (demonstrates this pattern with a transformer on top).

### Multi-series case

Calibrate against both streamflow and total nitrogen from the same subbasin:

```yaml
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

  - id: tn
    sim:
      file: output.rch
      id: 62
      period: [2019, 2021]
      timestep: monthly
      colSpan: [76, 87]
    obs:
      file: obs_tn_monthly.txt
      rowRanges:
        - [1, 36]
      colNum: 1

functions:
  - name: NSE
    kind: builtin

derived:
  - id: nse_flow
    call:
      func: NSE
      args: [flow.sim, flow.obs]
  - id: nse_tn
    call:
      func: NSE
      args: [tn.sim, tn.obs]

objectives:
  - id: obj_nse_flow
    ref: nse_flow
    sense: max
  - id: obj_nse_tn
    ref: nse_tn
    sense: max
```

Both series read from the same `output.rch` file but different column ranges. Each gets its own derived value and objective. Multi-objective optimization is handled by the UQPyL algorithm (e.g., NSGA-II from `UQPyL.optimization.moea`).

Reference: `examples/test_monthly_series.yaml`.

## 7. Putting it together — decision flowchart

```text
Start: SWAT 2012 project directory (TxtInOut)

1. Which output file?
   ├── Streamflow at outlet  → output.rch
   ├── Subbasin aggregates   → output.sub
   └── HRU-level variables   → output.hru

2. Which variable or column?
   ├── Variable in database  → use variable: FLOW_OUT
   └── Custom/unknown        → use colSpan: [50, 61]

3. Which period and timestep?
   ├── Match project IPRINT  → timestep: daily|monthly|yearly
   ├── Full calibration window → period: [2010, 2015]
   └── Partial/subset        → period: ["2019-06", "2021-09"]

4. Parameter strategy?
   ├── All HRUs same         → no filter (global)
   ├── By land use/soil      → filter: {land_use: AGRL}
   ├── Regularized           → transformer
   └── Discrete scenarios    → type: discrete

5. Objectives?
   ├── Single metric         → one derived, one objective
   └── Multiple metrics      → multiple derived + objectives
```

## See also

- [SWAT 2012 daily step-by-step guide](swat-daily-step-by-step.md) — from zero to first runnable daily case.
- [SWAT 2012 monthly guide](swat-monthly-guide.md) — adapting daily workflows to monthly output.
- [SWAT 2012 template reference](../templates/swat-2012.md) — compact template config reference.
- [Configuration reference](../configuration-reference.md) — all general-mode fields.
- [Examples](../examples.md) — full example descriptions and prerequisites.
