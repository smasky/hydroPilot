# Moving from Daily to Monthly SWAT 2012 Output

This guide assumes you have a working daily SWAT 2012 setup in hydroPilot and want to switch to monthly output. It explains what changes, what breaks if you keep daily assumptions, and how to avoid common mistakes.

## When to switch from daily to monthly

Switch to monthly when:

- Your calibration targets are monthly observations (common for water quality, reservoir operations, or long-duration studies).
- Your observed data is available only at monthly resolution.
- You want to reduce runtime — monthly output produces 12 data rows per year instead of 365 or 366.
- Your SWAT project IPRINT is already set to 0 (monthly). IPRINT is in `file.cio` line 59: `0` = monthly, `1` = daily, `2` = yearly.

If your SWAT project IPRINT is 1 (daily), you must change it to 0 and re-run the SWAT simulation before using monthly extraction in hydroPilot. hydroPilot derives the timestep automatically from the project's IPRINT setting — you don't set it in the config.

## What changes from the daily setup

Compared with the daily case, two things change in your config (timestep is handled automatically):

### 1. Timestep is derived from the project

Don't set `timestep` in the sim block. For SWAT 2012 configs (`version: swat`), the validator rejects `sim.timestep` — the timestep is derived from the project's `file.cio` IPRINT setting:

- IPRINT = 0 → monthly
- IPRINT = 1 → daily
- IPRINT = 2 → yearly

The template reads IPRINT during project discovery and calculates output rows accordingly. The same config structure works for daily and monthly — only the SWAT project's IPRINT value determines the timestep.

If your project IPRINT is 1 (daily), the template calculates daily row offsets (365/366 rows per year per subbasin). Change IPRINT to 0 and re-run SWAT to produce monthly output.

### 2. Period interpretation

Compared with the daily case, the same period `[2019, 2021]` means different things:

| Period | Daily rows | Monthly rows |
|--------|-----------|-------------|
| `[2019, 2021]` | 3 years × 365/366 ≈ 1,096 per subbasin | 3 years × 12 = 36 per subbasin |

The template calculates output rows differently for each timestep. See [Period forms](#period-forms) below for details.

### 2. Observation files

Your observation file must contain monthly values, not daily values:

```yaml
# Daily
obs:
  file: obs_flow.txt         # 2,191 daily values
  rowRanges:
    - [1, 2191]

# Monthly
obs:
  file: obs_flow_monthly.txt  # 36 monthly values
  rowRanges:
    - [1, 36]
```

The observation row count must match the number of months in your period: 12 per year × number of years. For `[2019, 2021]` (3 years), expect 36 rows.

## Why monthly SWAT output is trickier

Monthly SWAT output has two quirks that don't exist in daily output.

### The yearly-average row (MON=13)

SWAT output files append one extra row per year after the 12 monthly rows: MON=13, the yearly average. This row exists in every `output.rch`, `output.sub`, and `output.hru` file.

Compared with the daily case, where every row is a data row, monthly output has 13 rows per year per spatial unit — but you only want 12.

The template handles this by calculating discontinuous `rowRanges`. For a project with 62 subbasins reading subbasin 62, the monthly row pattern is:

```
Year 2019:
  MON=1, subbasin 1: file line 10
  ...
  MON=1, subbasin 62: file line 71
  MON=2, subbasin 62: file line 133
  ...
  MON=12, subbasin 62: file line 753
  MON=13 (avg), subbasin 62: line 815   ← skipped

Year 2020:
  MON=1, subbasin 62: file line 877
  ...
```

The resulting `rowRanges` in the expanded general config skips MON=13 rows:

```yaml
rowRanges:
  - [71, 753, 62]     # Year 2019: rows 71, 133, 195, ..., 753 (12 rows, step=62)
  - [877, 1559, 62]   # Year 2020: rows 877, 939, ..., 1559 (12 rows, step=62)
  - [1683, 2365, 62]  # Year 2021: rows 1683, ..., 2365 (12 rows, step=62)
```

Each range skips 12 × 62 = 744 rows per year, leaving a gap of 62 rows (MON=13 × n_subbasins) between year blocks. The 3-element `[start, end, step]` format tells the reader: "read every 62nd row from start to end."

### Why you see this in general-mode configs

In a template-mode config (`version: swat`), you only write `id: 62` and `period: [2019, 2021]`. The template calculates the discontinuous `rowRanges` for you. This is the main reason to use `version: swat` for monthly work — calculating these rows by hand is error-prone.

If you inspect the expanded `_general.yaml`, you will see multi-segment `rowRanges`. This is correct and expected. Don't merge them into one continuous range — that would include the MON=13 rows and produce wrong extractions.

## Walkthrough: from daily to monthly

Start with a working daily config:

```yaml
version: swat

basic:
  projectPath: "E:\\BMPs\\TxtInOut"
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
      id: 62
      period: [2019, 2021]
    obs:
      file: obs_flow.txt
      rowRanges:
        - [1, 1095]
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
    desc: "Maximize NSE"
    ref: nse_flow
    sense: max
```

To convert to monthly, make three changes (timestep is derived automatically from the project's IPRINT setting — you do not add it to the config):

### Step 1: Switch to monthly observation file

```yaml
obs:
  file: obs_flow_monthly.txt   # ← changed
  rowRanges:
    - [1, 36]                  # ← 3 years × 12 months = 36
  colSpan: [1, 12]             # ← optional, depends on obs file format
```

### Step 2: Update the series description

```yaml
desc: "Monthly streamflow at outlet"   # ← updated for clarity
```

### Step 3: Validate and test

```bash
hydropilot-validate config_monthly.yaml
hydropilot-test config_monthly.yaml
```

Compared with the daily case, the complete monthly config (`examples/test_monthly.yaml`) is structurally identical — only the observation file, row counts, and the description changed. The timestep is handled by the project's IPRINT setting, not the config.

## Period forms

Monthly extraction supports three levels of period precision.

### Year-precision

```yaml
period: [2019, 2021]
```

All 12 months of each year in the range. Start: January 1 of the first year. End: December 31 of the last year. This is the most common form.

### Month-precision

```yaml
period: ["2019-02", "2021-11"]
```

Partial years. Start: February 2019. End: November 2021. Useful for avoiding spin-up periods or aligning with an observation window that doesn't start in January.

Compared with the daily case, month-precision works the same way — the template clips to month boundaries automatically.

### Date-precision (clipped to month boundaries)

```yaml
period: ["2019-02-03", "2021-11-01"]
```

For monthly timestep, the exact day is ignored and the period is clipped to month boundaries: February 2019 to November 2021. This means `["2019-02-03", "2021-11-01"]` and `["2019-02-01", "2021-11-30"]` produce identical results in monthly mode.

The `test_monthly_series.yaml` example demonstrates this: two sim blocks read the same subbasin with month-precision and date-precision periods, and a `series_equal` diagnostic confirms they produce identical series.

### Multi-segment periods

```yaml
period:
  - [2019, 2019]
  - [2021, 2021]
```

Extracts only 2019 and 2021, skipping 2020. Each segment is a `[start, end]` pair. Useful when you want to calibrate on non-consecutive years or exclude a known anomalous year.

## Multi-series and warnings

The monthly examples include two advanced scenarios.

### Multi-series extraction (`test_monthly_series.yaml`)

Extracts two series from the same SWAT output file, each with a different period form:

```yaml
series:
  - id: flow_month
    sim:
      file: output.rch
      variable: FLOW_OUT
      id: 62
      period: ["2019-02", "2021-11"]

  - id: flow_date
    sim:
      file: output.rch
      variable: FLOW_OUT
      id: 62
      period: ["2019-02-03", "2021-11-01"]
```

Both extract `FLOW_OUT` from subbasin 62. The different period formats produce identical results for monthly timestep, verified by the `series_equal` derived function.

This example also demonstrates derived series: `flow_times_two` takes `flow_month.sim` and returns a transformed series as a diagnostic.

### Call-type sim and warnings (`test_monthly_series_warning.yaml`)

The second series uses `sim.call` rather than `sim.file`:

```yaml
series:
  - id: flow_matrix
    sim:
      call:
        func: flow_as_matrix
        args: [flow_month.sim]
```

`sim.call` computes a series from another series rather than reading from a file. The function `flow_as_matrix` returns a 2D (matrix-shaped) array by stacking the monthly series with itself.

Because downstream objectives and diagnostics expect 1D series, a matrix-shaped derived series triggers a runtime warning. This is expected behavior — the config is designed to demonstrate warning propagation. In a production config, ensure derived series return 1D arrays.

The reporter `flushInterval` is set to 1 to surface warnings immediately:

```yaml
reporter:
  flushInterval: 1
```

## Common monthly mistakes

### 1. Monthly obs length mismatch

The most common error: using daily observation row counts with monthly extraction.

```yaml
# Wrong — 1,095 rows but only 36 monthly values exist
obs:
  rowRanges:
    - [1, 1095]
```

For 3 years of monthly data: 3 × 12 = 36 rows. For 5 years: 60 rows. Count your observations carefully.

### 2. Wrong interpretation of period bounds

Period bounds are inclusive on both ends. `[2019, 2021]` includes all of 2019, 2020, and 2021 — that's 3 years, not 2. Compared with the daily case, where 3 years feels like a lot of data, 3 years of monthly output is only 36 rows — this is a small calibration dataset.

### 3. Assuming monthly rows are contiguous

In the expanded general config, `rowRanges` are multi-segment. This is correct — the MON=13 rows create gaps. If you write `rowRanges` manually in a general-mode config, use the multi-segment format:

```yaml
# Wrong — continuous range includes MON=13 rows
rowRanges:
  - [71, 2365]

# Correct — multi-segment skipping MON=13
rowRanges:
  - [71, 753, 62]
  - [877, 1559, 62]
  - [1683, 2365, 62]
```

### 4. Using daily assumptions for monthly extraction

- Daily: 365 or 366 rows per year per subbasin.
- Monthly: 12 rows per year per subbasin.

Don't divide daily row counts by 30 to estimate monthly positions. The template calculates monthly rows from the SWAT project structure — let it do the work.

### 5. Forgetting to match IPRINT

The SWAT project's `file.cio` line 59 (IPRINT) determines the output timestep: `0` = monthly, `1` = daily, `2` = yearly. hydroPilot derives the timestep automatically from this value. If IPRINT is 1 (daily), monthly configs will calculate wrong row positions. Check `file.cio` and re-run SWAT with IPRINT=0 before using monthly extraction.

### 6. Assuming timestep is set in the config

For SWAT 2012 configs (`version: swat`), don't write `timestep` in the sim block. The validator rejects it (timestep is derived from project metadata). The same config structure works for daily and monthly — change IPRINT in the SWAT project, not the hydroPilot config.

## See also

- [SWAT 2012 Template](../templates/swat-2012.md) — template reference and configuration shape.
- [Examples](../examples.md) — all example configs with prerequisites.
- [CLI Reference](../cli.md) — `hydropilot-validate` and `hydropilot-test` usage.
