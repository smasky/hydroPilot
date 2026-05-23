# SWAT 2012 Daily — Step-by-Step Guide

This guide walks you through your first HydroPilot workflow with a SWAT 2012 project. You will go from a plain TxtInOut directory to a validated, smoke-tested configuration that you can build on.

## What you need before starting

- A **SWAT 2012 TxtInOut project directory** — the folder containing `file.cio`, `fig.fig`, `*.sub`, `*.mgt`, `*.gw`, and other SWAT input files. This is the same directory you would point SWAT Editor to.
- The **SWAT 2012 executable** (typically `swat.exe` on Windows, or `swat` on Linux with Wine).
- **HydroPilot installed** — `pip install hydropilot` (requires Python 3.10+).

If you do not have a project ready, you can follow along with any valid SWAT 2012 TxtInOut directory. The steps are the same.

---

## Step 1: Identify your project and executable

HydroPilot needs to know three things about your project:

| Setting | What it is | Example |
|---|---|---|
| `projectPath` | Path to your TxtInOut directory | `E:\BMPs\TxtInOut` |
| `workPath` | Where HydroPilot creates run copies | `./work` |
| `command` | The model executable name | `swat.exe` |

`projectPath` and `workPath` are relative to where your config file lives. If your config is at `E:\myCalibration\my_config.yaml`, then `./work` means `E:\myCalibration\work`.

You can use absolute paths if you prefer:

```yaml
basic:
  projectPath: E:\BMPs\TxtInOut
  workPath: E:\myCalibration\work
  command: swat.exe
```

**Why this matters:** HydroPilot copies your `projectPath` into an isolated workspace for each run. This means it never modifies your original project files. The model runs from the copy, and results go into the workspace.

---

## Step 2: Create a minimal daily config

Create a new YAML file — call it `my_first.yaml`. Start with `version: swat`. This tells HydroPilot to use the SWAT 2012 template, which handles column positions and row calculations for you.

### Complete minimal config

```yaml
version: swat

basic:
  projectPath: E:\myProject\TxtInOut
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
    desc: Daily streamflow at outlet
    sim:
      file: output.rch
      id: 33
      variable: FLOW_OUT
      period: [2010, 2015]
    obs:
      file: obs_flow.txt
      rowRanges:
        - [1, 2191]
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
    desc: Maximize NSE
    ref: nse_flow
    sense: max
```

Let us go through each block.

### `basic`

```yaml
basic:
  projectPath: E:\myProject\TxtInOut
  workPath: ./work
  command: swat.exe
```

`projectPath` points to your TxtInOut directory. `workPath` is where run workspaces go. `command` is your SWAT 2012 executable — this can be just `swat.exe` if it is on your system PATH, or a full path like `C:\SWAT\swat.exe`.

### `parameters` — what to calibrate

```yaml
parameters:
  design:
    - name: CN2
      bounds: [35, 98]
    - name: ALPHA_BF
      bounds: [0, 1]
    - name: GW_DELAY
      bounds: [0, 500]
```

`design` lists the parameters your optimizer will adjust. Each one needs a name and a valid range (`bounds`). These three (CN2, ALPHA_BF, GW_DELAY) are common starting points for a first daily calibration.

With `version: swat`, you don't need to specify which SWAT files to modify or which columns to write — the template resolves parameter locations from the built-in SWAT 2012 database.

### `series` — simulation and observation data

```yaml
series:
  - id: flow
    desc: Daily streamflow at outlet
    sim:
      file: output.rch
      id: 33
      variable: FLOW_OUT
      period: [2010, 2015]
    obs:
      file: obs_flow.txt
      rowRanges:
        - [1, 2191]
      colNum: 1
```

- `id: flow` — a name you choose. HydroPilot uses this to form context keys like `flow.sim` and `flow.obs`.
- `sim.file: output.rch` — the SWAT output file that contains your variable. Use `output.rch` for reach/channel variables.
- `sim.id: 33` — the reach number (subbasin outlet) you want to read. Find this in your SWAT project's `fig.fig` or watershed setup.
- `sim.variable: FLOW_OUT` — the variable name. The template looks up the correct column range in `output.rch` from the SWAT 2012 database.
- `sim.period: [2010, 2015]` — the calibration years. Must fall within your SWAT project's simulation period (from `file.cio`).
- `obs.file: obs_flow.txt` — your observed flow data file, placed next to the config file. One value per line, matching the timestep (daily).
- `obs.rowRanges: [[1, 2191]]` — which rows to read from your observation file. 2191 days = 6 years from 2010 to 2015 inclusive.
- `obs.colNum: 1` — which column contains the data.

The template calculates `sim` rows automatically from `id`, `period`, and your project's metadata (subbasin count, simulation start date).

### `functions`, `derived`, `objectives` — evaluation

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
    desc: Maximize NSE
    ref: nse_flow
    sense: max
```

- `functions` declares which evaluation functions you need. `NSE` is built-in.
- `derived` computes intermediate values. Here, `nse_flow` calls `NSE` with the simulated and observed flow.
- `objectives` tells the optimizer what to target. `ref: nse_flow` points to the derived value. `sense: max` means higher NSE is better.

---

## Step 3: Validate the config

Run the validator:

```bash
hydropilot-validate my_first.yaml
```

This checks your config without running the model. For a `version: swat` config, the validator checks that:

- `projectPath` exists and contains the required SWAT 2012 files (`file.cio`, `fig.fig`)
- Parameter names are recognized and unambiguous
- Each series `sim` has a valid SWAT output file (`output.rch`, `output.sub`, or `output.hru`)
- Each `sim` declares a variable name (`variable`) or explicit column location (`colSpan`/`colNum`)
- Each `sim` has a subbasin/reach ID (`id`) or explicit row selection
- Observation files exist and are readable
- Row and column selectors are provided for observation readers
- The calibration period falls within the project's simulation period

If everything is correct, you will see:

```
Config is valid.
```

If there are errors, the validator prints each one with a path (like `series[flow].obs`) and a suggestion. Fix them one by one.

Common first-time errors:
- `projectPath: directory not found` — check the path. Use an absolute path if unsure.
- `observation file not found` — make sure `obs_flow.txt` is in the same directory as your config file.
- `sim.id` out of range — your project may have fewer subbasins. Check `fig.fig`.

The validator only checks that the configuration makes sense — it doesn't run the model.

---

## Step 4: Run a smoke test

Once validation passes, run a smoke test:

```bash
hydropilot-test my_first.yaml
```

HydroPilot-test does the following:
1. Loads your config and expands the template.
2. Creates an isolated project copy in `workPath`.
3. Applies a default parameter vector (midpoint of each parameter's bounds).
4. Runs your model command in that copy.
5. Extracts simulation output using your series definition.
6. Computes the objective value (NSE, in this case).
7. Writes a test report to `test-report.md` under the run archive.

This proves that:

- Your model executable runs correctly.
- The parameter-to-file wiring works (HydroPilot found the right files to modify).
- Series extraction resolves to actual rows and columns.
- The objective function produces a real number.

What the smoke test does **not** prove:

- That your parameter bounds are good for calibration.
- That multiple runs work without interference.
- That parallel execution works.
- That your observation data is correct or well-aligned.

It's a wiring check — it doesn't validate your calibration setup.

---

## Step 5: Inspect the expanded general config

After `hydropilot-test` succeeds, look next to your config file. You will find a file named:

```
my_first_general.yaml
```

This is the fully expanded `version: general` config that the runtime actually uses. The SWAT 2012 template has resolved:

- `variable: FLOW_OUT` → concrete `colSpan: [52, 61]`
- `id: 33, period: [2010, 2015]` → concrete `rowRanges: [[24165, 96435, 33]]`
- Parameter names (CN2, ALPHA_BF, GW_DELAY) → concrete `file.name`, `line`, `start`, `width`, and `precision` for each SWAT input file

Inspecting this file is useful when:

- You want to verify that the template resolved parameters to the rows and columns you expect.
- You need to debug a series extraction issue.
- You are transitioning from template mode to general mode for full control.

You don't need to edit this file — it's regenerated every time HydroPilot loads your config. Edit your `version: swat` config instead.

---

## Step 6: Connect your own observation file

Now replace `obs_flow.txt` with your own observed data.

Requirements for a daily observation file:

- One row per day, in chronological order, matching the start and end of your `period`.
- One value per row (or one value per row in a specific column, if using `colNum`).
- Plain text, no headers.

Example — if your calibration period is 2010–2015 (2192 days), your file needs 2192 rows. Count them:

```bash
# On Linux/Mac
wc -l obs_flow.txt

# On Windows (PowerShell)
(Get-Content obs_flow.txt).Count
```

Update your config:

```yaml
series:
  - id: flow
    sim:
      file: output.rch
      id: 33
      variable: FLOW_OUT
      period: [2010, 2015]
    obs:
      file: my_observed_flow.txt
      rowRanges:
        - [1, 2192]
      colNum: 1
```

Re-validate and re-test:

```bash
hydropilot-validate my_first.yaml
hydropilot-test my_first.yaml
```

**Important:** If your observation file has a different number of rows than the simulation period, the validator will warn you but the test may still run. A mismatch usually means your `period`, `timestep`, or row count is wrong. Fix it before moving to calibration.

---

## Step 7: Adjust the first calibration target

With a working config, you can now choose what to calibrate against.

### Start with one objective

For your first real calibration, aim for one objective at one outlet. A single-objective setup is easier to debug and faster to run.

```yaml
objectives:
  - id: obj_nse
    desc: NSE at outlet 33
    ref: nse_flow
    sense: max
```

The `derived` block computes the metric:

```yaml
derived:
  - id: nse_flow
    call:
      func: NSE
      args: [flow.sim, flow.obs]
```

### Choosing the right variable

`FLOW_OUT` is a good first choice because it is well-constrained (total outflow at a subbasin must match observed discharge). It is also the most commonly available observation.

If you want to calibrate against water quality or other variables later, you add more `series` entries and point new `derived` + `objectives` at them. But start with one.

### Checking the subbasin range

Your `sim.id` must be a reach ID that exists in your project. To find valid IDs:

- Open `fig.fig` in your TxtInOut directory. The first line is the number of subbasins.
- Subbasin IDs are 1 to the subbasin count.
- Each subbasin has one reach outlet (`output.rch` row), so reach IDs match subbasin IDs.

If your config says `id: 33` but your project only has 25 subbasins, the template will reject it during validation.

### What to do next

Once your configuration validates and smoke-tests with your own observations:

- Add constraints if you have physical limits (e.g., minimum volume ratios).
- Add diagnostics (RMSE, KGE) to track alongside your objective without optimizing them.
- Move to batch runs or UQPyL optimization via the Python API.

---

## Common first-pass mistakes

### Wrong `projectPath`

```yaml
# Wrong — this is the config's own directory
basic:
  projectPath: ./
```

`projectPath` must point to your SWAT 2012 TxtInOut directory, not the config file directory. Use an absolute path if unsure:

```yaml
basic:
  projectPath: E:\SWAT_Projects\MyWatershed\TxtInOut
```

### Wrong executable name or path

If your model executable is not on the system PATH, use the full path:

```yaml
basic:
  command: C:\SWAT\SWAT_Edit\swat.exe
```

On Linux with Wine, the command might be:

```yaml
basic:
  command: wine swat.exe
```

### Observation length mismatch

Suppose your `period` is `[2010, 2015]` at daily timestep. That is 6 years × 365/366 days ≈ 2192 days. If your observation file has 1800 rows, results will be misaligned. Count your rows and match them to the period.

For daily data, leap years add one day. 2012 was a leap year, so 2010–2015 inclusive is 2192 days (6 × 365 + 1).

### Choosing a `sim.id` outside the discovered range

The template reads your project's `fig.fig` to find the subbasin count. If you specify `id: 62` in a project with 33 subbasins, validation will fail. Check your project's subbasin count first.

### Timestep is derived, not declared

The SWAT template derives the timestep automatically from your project's IPRINT setting in `file.cio`. Don't declare `timestep` in the `sim` block — the SWAT validator rejects it:

```yaml
# WRONG — the SWAT validator rejects timestep:
sim:
  file: output.rch
  id: 33
  variable: FLOW_OUT
  period: [2010, 2015]
  timestep: monthly
```

If you need a different timestep (for example, monthly instead of daily), change the IPRINT setting in your SWAT project and re-run the SWAT model to regenerate the output files. HydroPilot reads the timestep from the project metadata during template expansion.

### Same `obs.file` path misunderstanding

Observation files are resolved relative to the config file, not the model project directory. If your config is at `E:\myCalibration\config.yaml`, then `obs.file: obs_flow.txt` means `E:\myCalibration\obs_flow.txt`.

```yaml
# Your config is at: E:\myCalibration\my_config.yaml
# This obs file will be looked for at: E:\myCalibration\my_data\flow.txt
obs:
  file: my_data/flow.txt
```

---

## See also

- [SWAT 2012 Template Reference](../templates/swat-2012.md) — full template features and configuration shape.
- [Configuration Reference](../configuration-reference.md) — all general-mode fields and their defaults.
- [Examples](../examples.md) — all example configs with descriptions.
- [CLI Reference](../cli.md) — all four CLI commands.
