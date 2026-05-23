# Examples

This guide maps the example configs and helper scripts shipped with hydroPilot. Use it to find a starting point for your own project.

## Quick start: which example should I use?

| If you are... | Start with |
|---------------|-----------|
| New to hydroPilot | `test_daily.yaml` — simplest SWAT 2012 example |
| Using a non-SWAT model or want full control | `test_daily_general.yaml` or `test_xaj_general.yaml` |
| Working with monthly data | `test_monthly.yaml` |
| Calibrating parameters with spatial filters | `test_monthly_complex.yaml` |
| Working with XAJ (CSV-based model) | `test_xaj.yaml` |
| Exploring advanced features | Browse complex, series, and warning examples below |

All examples are designed for documentation and smoke testing. Adapt paths, parameters, and series to your own project before running real calibrations.

---

## Example configs at a glance

| File | Version | Model | Timestep | Highlights |
|------|---------|-------|----------|------------|
| `test_daily.yaml` | `swat` | SWAT 2012 | daily | 3 params, single objective (NSE) |
| `test_daily_general.yaml` | `general` | — | daily | Same scenario, fully expanded config |
| `test_monthly.yaml` | `swat` | SWAT 2012 | monthly | Subbasin filtering, period selection |
| `test_monthly_general.yaml` | `general` | — | monthly | Same scenario, fully expanded config |
| `test_monthly_complex.yaml` | `swat` | SWAT 2012 | monthly | Transformer, HRU filters, multi-objective, diagnostics, external functions |
| `test_monthly_series.yaml` | `swat` | SWAT 2012 | monthly | Period slicing (year, month, date), derived series, multi-series |
| `test_monthly_series_warning.yaml` | `swat` | SWAT 2012 | monthly | Call-type sim, warning/diagnostic behavior demo |
| `test_xaj.yaml` | `xaj` | XAJ | — | RIVID filtering, CSV readers/writers |
| `test_xaj_general.yaml` | `general` | — | — | Same XAJ scenario, fully expanded config |

---

## General examples (`version: general`)

General-mode configs use the full hydroPilot schema directly. No model template expansion is applied — you write out every reader, writer, and file location yourself.

### `test_daily_general.yaml`

A daily SWAT 2012 calibration config in general format. Three parameters (CN2, ALPHA_BF, GW_DELAY) applied to `.mgt` and `.gw` files via fixed-width writers. Observations read from a text file with `colNum`.

Use this to understand the fully expanded schema that template-mode configs produce.

### `test_monthly_general.yaml`

Same three-parameter scenario as the daily version, but with monthly timestep. Shows multi-segment `rowRanges` — the output file is read in three discontinuous blocks (months 1–11 per year, skipping yearly-average rows).

### `test_xaj_general.yaml`

A general-format config for the XAJ model. Defines CSV-based readers and writers explicitly. Two parameters (KC, WM) written to `parameters.csv`. Two series: streamflow and runoff yield from separate CSV output files.

---

## SWAT 2012 examples (`version: swat`)

SWAT 2012 configs use variable names (`FLOW_OUT`, `TN_OUT`) so you don't need raw column spans, and parameter names (`CN2`, `ALPHA_BF`) so you don't write the file layout by hand. The template resolves these against the SWAT 2012 knowledge database.

#### `test_daily.yaml`

The simplest SWAT 2012 example. Three parameters calibrated globally (no HRU filters). One series (`flow`) reading `FLOW_OUT` from `output.rch` at subbasin 33, period 2010–2015, daily timestep. Observation data from a text file. Single objective (NSE, maximized).

Usage after adapting paths:

```bash
hydropilot-validate examples/test_daily.yaml
hydropilot-test examples/test_daily.yaml
```

#### `test_monthly.yaml`

Monthly variant with subbasin 62, period 2019–2021. Uses `colSpan` for the sim column rather than looking up a variable name. Observation uses `colSpan` as well (columns 1–12 in the obs file).

Key differences from the daily example:
- Timestep is derived from the project's `file.cio` IPRINT setting (0=monthly, 1=daily), not set in the config. The SWAT template validator rejects `sim.timestep`.
- SWAT output rows are calculated per-month, skipping the yearly-average row (MON=13).
- `rowRanges` use a 3-element `[start, end, step]` format where step equals the number of subbasins.

#### `test_monthly_complex.yaml`

The most feature-rich example. Demonstrates:

- **Transformer**: 4 design parameters map to 6 physical parameters via `monthly_transform.py`. Design-space values (CN2_factor, ESCO_val, etc.) are transformed before writing.
- **HRU filters**: CN2 parameters filtered by land use (`AGRL` and `URHD`). ESCO_HRU split across two subbasin ranges (1–30 and 31–62). The filter engine (`filterHrus`) resolves `*.mgt` patterns to concrete filenames per HRU.
- **Multi-series**: Two series (`flow` and `tn`) from the same `output.rch` file using different column spans.
- **Multi-objective**: Two NSE objectives (flow and TN), both maximized.
- **Diagnostics**: KGE, RMSE, and an external function (`calc_annual_tn_load`) computed from the TN series — diagnostics are tracked but not optimized.
- **External functions**: `monthly_transform.py` provides the transformer; `calc_tn_load.py` provides the annual TN load diagnostic.

#### `test_monthly_series.yaml`

Demonstrates period slicing and derived series:

- Two sim blocks read the same variable (`FLOW_OUT`) from the same subbasin (62) with different period formats: `[2019-02, 2021-11]` (month-precision) and `[2019-02-03, 2021-11-01]` (day-precision, clipped to month boundaries for monthly output).
- Derived series via external functions: `flow_times_two` transforms the sim series, and `series_equal` compares the two period-sliced series.
- Both derived results appear as diagnostics.

#### `test_monthly_series_warning.yaml`

Demonstrates call-type sim blocks and warning behavior:

- The second series (`flow_matrix`) uses `sim.call` rather than `sim.file` — it computes the series by calling `flow_as_matrix` with the first series as input, producing a 2D (matrix-shaped) output.
- A non-scalar series (matrix) returned from a call function triggers a runtime warning — downstream objectives and diagnostics expect scalar or 1D series.
- Reporter `flushInterval` set to 1 to surface warnings immediately.

## XAJ examples (`version: xaj`)

XAJ (Xin'anjiang) is a CSV-based hydrological model. Its template uses CSV readers and writers rather than fixed-width text.

#### `test_xaj.yaml`

A two-parameter (KC, WM) XAJ config:

- **Parameter filtering by RIVID**: KC is filtered to a specific reach (`rivid: 60711600`). WM applies to all reaches (no filter). The XAJ template resolves RIVID-based parameter rows from the project's `parameters.csv`.
- **Series with variable names**: `Streamflow` and `Runoff` are resolved against the XAJ series database. Variables with `idHeader: true` (like `Runoff`) require a `rivid` to locate the correct output column.
- **CSV I/O**: Both readers and writers use CSV format with configurable delimiter, `headSkip`, and `colNum`.

---

## Daily vs monthly examples

The daily and monthly examples differ in three key areas at the user level:

| Aspect | Daily | Monthly |
|--------|-------|---------|
| Timestep source | Project `file.cio` IPRINT=1, auto-detected by template | Project `file.cio` IPRINT=0, auto-detected by template |
| `period` precision | Typically year-only: `[2010, 2015]` | Often year-precision: `[2019, 2021]` |
| Output rows | 365/366 per year per subbasin | 12 per year per subbasin (+ 1 yearly avg skipped) |
| `rowRanges` structure | Continuous ranges with step = n_subbasins | Multi-segment ranges skipping yearly-average rows |
| Observation file | `obs_flow.txt` (daily values) | `obs_flow_monthly.txt` (monthly values) |

The template-mode examples (`version: swat`) handle output row calculation and timestep detection automatically — timestep is read from the project's `file.cio` IPRINT setting, so you only provide `id` and `period`. The general-mode examples show the resolved `rowRanges` explicitly.

---

## Helper scripts

Four Python scripts in `examples/` provide reusable external functions.

### `monthly_transform.py`

A **transformer** that maps 4 design parameters to 6 physical parameters:

```
X[0] (CN2_factor)    → P[0] (CN2 for AGRL), P[1] (CN2 for URHD)
X[1] (ESCO_val)      → P[2] (ESCO sub 1–30), P[3] (ESCO sub 31–62)
X[2] (GW_DELAY_val)  → P[4] (GW_DELAY global)
X[3] (SURLAG_val)    → P[5] (SURLAG global)
```

Used by `test_monthly_complex.yaml` as a `transformer`. Referenced as `kind: external` in the functions block with `file: "monthly_transform.py"`.

### `series_transform.py`

Two functions for series manipulation:

- `flow_times_two(flow_month_sim)` — multiplies a series by 2, used as a derived-series transform.
- `series_equal(flow_month_sim, flow_date_sim)` — compares two series for equality (with NaN tolerance), returns 1.0 if equal, 0.0 otherwise. Used to verify that two period-sliced series from the same subbasin produce identical results.

Used by `test_monthly_series.yaml`.

### `series_transform_warning.py`

Two functions, one of which is designed to trigger a diagnostic warning:

- `flow_times_two(flow_month_sim)` — same scalar transform as `series_transform.py`.
- `flow_as_matrix(flow_month_sim)` — returns a 2D array by stacking the series with itself. This produces a non-scalar derived series, which triggers a runtime warning because matrix-shaped outputs are not expected by downstream objective/diagnostic evaluation.

Used by `test_monthly_series_warning.yaml`.

### `calc_tn_load.py`

An **external evaluation function** that computes annual average TN load from a monthly TN series:

```python
def calc_annual_tn_load(tn_sim):
    # Sums monthly values, divides by number of years
```

Used by `test_monthly_complex.yaml` as a diagnostic via `derived`. The function takes a single argument (`tn.sim`) and returns a scalar.

---

## Validating an example

Use `hydropilot-validate` to check a config without running the model:

```bash
# Template-mode SWAT 2012 config
hydropilot-validate examples/test_daily.yaml

# General-mode config
hydropilot-validate examples/test_daily_general.yaml
```

The validator reports errors (missing files, invalid syntax) and warnings (observation/simulation size mismatches). It does not execute the model.

Note: Several examples reference project directories (`E:\DJBasin\TxtInOutFSB`, `E:\BMPs\TxtInOut`) that only exist on the author's machine. Validation will report `projectPath: directory not found` for those. Adapt `basic.projectPath` to a local SWAT 2012 project before validating.

## Smoke testing an example

Use `hydropilot-test` to run a full smoke test (one evaluation with a default parameter vector):

```bash
hydropilot-test examples/test_daily.yaml
```

This loads the config, creates a temporary project copy, applies default parameters, runs the model command, extracts results, and writes a test report. It forces `parallel: 1` and `keepInstances: true`.

## Running a single evaluation

Use `hydropilot-run` with a run YAML to evaluate a specific parameter vector:

```yaml
# run_daily.yaml
config: examples/test_daily.yaml
mode: design
values:
  CN2: 72.5
  ALPHA_BF: 0.3
  GW_DELAY: 120
```

```bash
hydropilot-run run_daily.yaml
```

`hydropilot-run` is a single-run entry point — it evaluates one parameter vector and prints the result. For batch runs or optimization, use the Python API (`SimModel`).

---

## Adapting examples for real projects

The example configs are documentation and test artifacts, not production-ready calibration setups. When adapting one:

1. **Change `basic.projectPath`** to your local SWAT 2012 TxtInOut directory or XAJ project directory.
2. **Update `basic.command`** to match your model executable name and path.
3. **Review parameter bounds** — the example bounds are illustrative and may not be appropriate for your watershed.
4. **Verify output file structure** — subbasin count, output variable columns, and HRU land-use/soil/slope classifications vary between projects.
5. **Replace observation files** — point `obs.file` to your own observed data.
6. **Adjust timestep and period** to match your calibration window.
7. **Check `version`** — use `version: swat` for SWAT 2012 projects (template expands automatically) or `version: general` if you need full control over every reader/writer/file location.
