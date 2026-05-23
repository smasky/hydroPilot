# CLI Reference

hydroPilot provides four command-line entry points for validation, testing, parameter application, and single-run evaluation.

## Installation

All four commands become available after installing the package:

```bash
pip install hydropilot
```

They are registered as console scripts in `pyproject.toml` and do not require a Python import.

---

## `hydropilot-validate`

Validate a hydroPilot configuration file.

```bash
hydropilot-validate <config.yaml>
```

### What it does

1. Parses the YAML configuration file.
2. If the config uses a model-specific version (e.g. `version: "swat"` or `version: "xaj"`), expands it through the corresponding template into a general-format config.
3. Runs general-config validation checks.
4. Prints diagnostics to stdout, one per line.

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Validation passed (no errors; warnings are printed but do not cause failure) |
| 1 | Validation failed (at least one error-level diagnostic) |

### Example output

```
ERROR basic.projectPath: directory not found: /nonexistent/project
```

```
WARNING series[flow].obs: observation file has fewer rows than sim
Validation passed: config.yaml
```

### Usage notes

- The config file must exist and be valid YAML.
- Template-expanded configs (swat, xaj) are validated after expansion, so template-level errors (e.g. missing `file.cio` for SWAT 2012) are surfaced as validation diagnostics.
- This command is read-only: it does not run the model or modify any files.

---

## `hydropilot-test`

Run a full configuration smoke test.

```bash
hydropilot-test <config.yaml>
```

### What it does

1. Loads and validates the configuration (same path as `hydropilot-validate`).
2. Builds a default test vector from the design parameter bounds.
3. Creates a temporary project copy, applies parameters, runs the model command once, and extracts results.
4. Evaluates all objectives, constraints, and diagnostics.
5. Prints a terminal summary and writes `test-report.md` and CSV artifacts to the archive directory.

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Smoke test passed |
| 1 | Smoke test failed |

### Usage notes

- Forces `parallel = 1` and `keepInstances = true` regardless of config settings.
- A full model execution happens — this is not a dry run.
- Use this to verify that a config is fully wired: project files exist, the model executable runs, output files are readable, and evaluation produces results.

---

## `hydropilot-apply`

Apply design or physical parameters to a project copy.

```bash
hydropilot-apply <apply.yaml>
```

### Apply YAML format

The apply YAML references a hydroPilot config and specifies what to apply:

```yaml
config: path/to/config.yaml
mode: design        # or "physical"
values:
  CN2: 72.5
  ALPHA_BF: 0.3
  GW_DELAY: 120
outDir: ./applied_project
```

- `config` — path to a hydroPilot configuration YAML.
- `mode` — `"design"` (transforms design-space values to physical parameters and writes them) or `"physical"` (writes physical-parameter values directly to model input files).
- `values` — a flat list or a dict keyed by parameter name. Named keys are checked against the config's parameter list; missing or extra keys raise an error.
- `outDir` — target directory. Must not already exist. The project is copied into it before parameters are applied.

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Parameters applied successfully |
| 1 | Error (bad YAML, missing values, target exists, etc.) |

### Usage notes

- `mode: design` runs the full design-to-physical pipeline: the design values are transformed through the parameter builder and written to model input files via the registered writer (fixed-width for SWAT 2012, CSV for XAJ).
- `mode: physical` writes physical-parameter values directly, bypassing the design layer.
- The output directory is a complete, runnable project copy with parameters applied.

---

## `hydropilot-run`

Run a single evaluation from a run YAML.

```bash
hydropilot-run <run.yaml>
```

### Run YAML format

```yaml
config: path/to/config.yaml
mode: design           # or "physical"
values:
  - 72.5               # positional, matches design parameter order
  - 0.3
  - 120
```

Or with named values:

```yaml
config: path/to/config.yaml
mode: design
values:
  CN2: 72.5
  ALPHA_BF: 0.3
  GW_DELAY: 120
```

### What it does

1. Loads the configuration referenced by `config`.
2. Runs a single model evaluation with the given parameter values.
3. Prints a summary including objectives, constraints, diagnostics, and output file paths.

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Run passed |
| 1 | Run failed |

### Scope

`hydropilot-run` is a **single-run entry point** — it evaluates one parameter vector and prints the result. It does not perform optimization, batch execution, or experiment management. For multi-run or optimization workflows, use the Python API (`SimModel`) directly or integrate with UQPyL via `UQPyLAdapter`.

---

## Command comparison

| Command | Purpose | Runs model? | Writes files? |
|---------|---------|-------------|---------------|
| `hydropilot-validate` | Check config correctness | No | No |
| `hydropilot-test` | Full smoke test | Yes, once | Yes (report + CSVs) |
| `hydropilot-apply` | Apply parameters to a project copy | No | Yes (project copy) |
| `hydropilot-run` | Single evaluation from a run YAML | Yes, once | Yes (archive) |
